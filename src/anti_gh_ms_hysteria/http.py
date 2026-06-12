from __future__ import annotations

import json
import socket
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from .models import RetryConfig, TokenCredential
from .tokens import TokenPool
from .ui import UI
from .utils import scrub_secret


class HttpError(RuntimeError):
    def __init__(self, status: int, message: str, body: str = "", headers: dict[str, str] | None = None):
        super().__init__(message)
        self.status = status
        self.body = body
        self.headers = headers or {}


@dataclass
class JsonResponse:
    data: Any
    headers: dict[str, str]
    status: int


class ApiClient:
    def __init__(
        self,
        base_url: str,
        token_pool: TokenPool,
        retry: RetryConfig,
        ui: UI,
        auth_style: str = "bearer",
        proxy: str | None = None,
        insecure_tls: bool = False,
        user_agent: str = "anti-GH-MS-hysteria/0.1",
    ):
        self.base_url = base_url.rstrip("/")
        self.token_pool = token_pool
        self.retry = retry
        self.ui = ui
        self.auth_style = auth_style
        self.proxy = proxy
        self.insecure_tls = insecure_tls
        self.user_agent = user_agent
        self.opener = self._build_opener(proxy, insecure_tls)

    def request_json(
        self,
        method: str,
        path_or_url: str,
        body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        allow_not_found: bool = False,
    ) -> JsonResponse:
        attempt = 0
        while True:
            lease = self.token_pool.acquire()
            if lease.wait_seconds > 0:
                if not self.retry.wait_on_rate_limit:
                    raise HttpError(429, f"All {self.token_pool.label} tokens are rate limited")
                wait = max(1, int(lease.wait_seconds))
                self.ui.warning(f"All {self.token_pool.label} tokens are cooling down; waiting {wait}s")
                time.sleep(wait)
                continue
            token = lease.token
            try:
                return self._request_once(method, path_or_url, body, headers, token)
            except HttpError as exc:
                if exc.status == 404 and allow_not_found:
                    return JsonResponse(None, exc.headers, 404)
                if exc.status == 401:
                    self.token_pool.mark_limited(token, time.time() + self.retry.rate_limit_sleep_seconds)
                    next_lease = self.token_pool.acquire()
                    if next_lease.token is not None and next_lease.token != token:
                        self.ui.warning(
                            f"{self.token_pool.label} token {token.display_name if token else 'anonymous'} was rejected; rotating"
                        )
                        continue
                    raise
                if exc.status in {403, 429} and _looks_rate_limited(exc):
                    reset_epoch = _rate_limit_reset(exc.headers, self.retry.rate_limit_sleep_seconds)
                    self.token_pool.mark_limited(token, reset_epoch)
                    next_lease = self.token_pool.acquire()
                    if next_lease.token is not None and next_lease.token != token:
                        self.ui.warning(
                            f"{self.token_pool.label} token {token.display_name if token else 'anonymous'} failed with HTTP {exc.status}; rotating"
                        )
                        continue
                    if self.retry.wait_on_rate_limit:
                        wait = max(1, int((reset_epoch or time.time() + self.retry.rate_limit_sleep_seconds) - time.time()))
                        self.ui.warning(f"Rate limited by {self.base_url}; waiting {wait}s before retry")
                        time.sleep(wait)
                        continue
                if exc.status >= 500 and attempt < self.retry.max_retries:
                    attempt += 1
                    wait = min(self.retry.max_delay_seconds, self.retry.base_delay_seconds * (2 ** (attempt - 1)))
                    self.ui.warning(f"HTTP {exc.status} from {self.base_url}; retrying in {wait:.1f}s")
                    time.sleep(wait)
                    continue
                raise
            except (OSError, TimeoutError, urllib.error.URLError) as exc:
                detail = _network_error_detail(exc)
                if attempt >= self.retry.max_retries:
                    raise HttpError(0, f"Network error from {self.base_url}: {detail}") from exc
                attempt += 1
                wait = min(self.retry.max_delay_seconds, self.retry.base_delay_seconds * (2 ** (attempt - 1)))
                self.ui.warning(f"Network error from {self.base_url}: {detail}; retrying in {wait:.1f}s")
                time.sleep(wait)

    def _request_once(
        self,
        method: str,
        path_or_url: str,
        body: dict[str, Any] | None,
        headers: dict[str, str] | None,
        token: TokenCredential | None,
    ) -> JsonResponse:
        url = path_or_url if path_or_url.startswith("http") else f"{self.base_url}/{path_or_url.lstrip('/')}"
        payload = None
        request_headers = {
            "Accept": "application/json",
            "User-Agent": self.user_agent,
            **(headers or {}),
        }
        if body is not None:
            payload = json.dumps(body).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
        if token:
            if self.auth_style == "github":
                request_headers["Authorization"] = f"Bearer {token.secret}"
                request_headers["X-GitHub-Api-Version"] = "2022-11-28"
            elif self.auth_style == "gitlab":
                request_headers["PRIVATE-TOKEN"] = token.secret
            elif self.auth_style == "forgejo":
                request_headers["Authorization"] = f"token {token.secret}"
            elif self.auth_style == "basic":
                import base64

                username = token.username or "x-token-auth"
                raw = f"{username}:{token.secret}".encode("utf-8")
                request_headers["Authorization"] = f"Basic {base64.b64encode(raw).decode('ascii')}"
            else:
                request_headers["Authorization"] = f"Bearer {token.secret}"

        req = urllib.request.Request(url, data=payload, headers=request_headers, method=method.upper())
        self.ui.debug(f"API {method.upper()} {url}")
        try:
            with self.opener.open(req, timeout=self.retry.request_timeout_seconds) as response:
                raw = response.read().decode("utf-8")
                self._debug_http_response(method, url, response.status, dict(response.headers), raw, success=True)
                data = json.loads(raw) if raw else None
                return JsonResponse(data=data, headers=dict(response.headers), status=response.status)
        except urllib.error.HTTPError as exc:
            body_text = exc.read().decode("utf-8", errors="replace")
            headers_dict = dict(exc.headers)
            self._debug_http_response(method, url, exc.code, headers_dict, body_text, success=False)
            message = _http_message(exc.code, body_text)
            raise HttpError(exc.code, message, body_text, headers_dict) from exc

    def _build_opener(self, proxy: str | None, insecure_tls: bool) -> urllib.request.OpenerDirector:
        handlers: list[urllib.request.BaseHandler] = []
        if proxy:
            handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
        if insecure_tls:
            context = ssl._create_unverified_context()
            handlers.append(urllib.request.HTTPSHandler(context=context))
        return urllib.request.build_opener(*handlers)

    def _debug_http_response(
        self,
        method: str,
        url: str,
        status: int,
        headers: dict[str, str],
        body: str,
        success: bool,
    ) -> None:
        if self.ui.verbose <= 0:
            return
        if success and self.ui.verbose < 2:
            self.ui.debug(f"HTTP {status} {method.upper()} {url}")
            return

        header_lines = [f"{key}: {value}" for key, value in headers.items()]
        text = "\n".join(
            [
                f"HTTP RESPONSE {method.upper()} {url}",
                f"Status: {status}",
                "Headers:",
                *(header_lines or ["<none>"]),
                "Body:",
                body if body else "<empty>",
            ]
        )
        self.ui.debug(scrub_secret(text, self.token_pool.all_secrets()))


def _http_message(status: int, body: str) -> str:
    try:
        data = json.loads(body)
    except Exception:
        return f"HTTP {status}: {body[:300]}"
    if isinstance(data, dict):
        message = data.get("message") or data.get("error") or data.get("error_description")
        if message:
            return f"HTTP {status}: {message}"
    return f"HTTP {status}"


def _rate_limit_reset(headers: dict[str, str], fallback_seconds: int) -> float:
    retry_after = headers.get("Retry-After") or headers.get("retry-after")
    if retry_after:
        try:
            return time.time() + int(retry_after)
        except ValueError:
            pass
    reset = headers.get("X-RateLimit-Reset") or headers.get("x-ratelimit-reset")
    if reset:
        try:
            return float(reset)
        except ValueError:
            pass
    return time.time() + fallback_seconds


def _looks_rate_limited(exc: HttpError) -> bool:
    if exc.status == 429:
        return True
    remaining = exc.headers.get("X-RateLimit-Remaining") or exc.headers.get("x-ratelimit-remaining")
    if remaining == "0":
        return True
    text = f"{exc} {exc.body}".lower()
    return "rate limit" in text or "too many requests" in text


def _network_error_detail(exc: BaseException) -> str:
    if isinstance(exc, socket.timeout):
        return "request timed out"
    reason = getattr(exc, "reason", None)
    if reason is None:
        return str(exc)
    return str(reason)
