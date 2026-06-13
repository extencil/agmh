from __future__ import annotations

import html
import json
import os
import ssl
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from .models import AppConfig, WebhookConfig
from .ui import UI
from .utils import safe_display_url, scrub_secret, utc_now_iso


ALL_NOTIFICATION_EVENTS = {
    "start",
    "finish",
    "local_saved",
    "remote_saved",
    "watch_check",
    "watch_update",
    "watch_none",
    "error",
}


@dataclass(frozen=True)
class Notification:
    event: str
    title: str
    message: str
    data: dict[str, Any]
    timestamp: str


class Notifier:
    def __init__(self, cfg: AppConfig, ui: UI):
        self.cfg = cfg
        self.ui = ui
        self.enabled = cfg.notifications.enabled and bool(cfg.notifications.webhooks)
        self.opener = self._build_opener()

    def secrets(self) -> list[str]:
        secrets: list[str] = []
        for webhook in self.cfg.notifications.webhooks:
            for value in (
                webhook.url,
                _env_value(webhook.url_env),
                webhook.bot_token,
                _env_value(webhook.bot_token_env),
            ):
                if value:
                    secrets.append(value)
        return secrets

    def notify(
        self,
        event: str,
        title: str,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        if not self.enabled:
            return
        if not _event_allowed(event, self.cfg.notifications.events):
            return
        notification = Notification(
            event=event,
            title=title,
            message=message,
            data=data or {},
            timestamp=utc_now_iso(),
        )
        for webhook in self.cfg.notifications.webhooks:
            if not webhook.enabled or not _event_allowed(event, webhook.events):
                continue
            try:
                self._send(webhook, notification)
            except Exception as exc:
                detail = scrub_secret(str(exc), self.secrets())
                if self.cfg.notifications.fail_silently:
                    self.ui.warning(f"Webhook {webhook.name} failed for event {event}: {detail}")
                else:
                    raise

    def _send(self, webhook: WebhookConfig, notification: Notification) -> None:
        if webhook.platform == "discord":
            url = _required_secret(webhook.url, webhook.url_env, f"webhook {webhook.name} url")
            if webhook.thread_id:
                url = _append_query(url, {"thread_id": webhook.thread_id})
            self._post_json(url, _discord_payload(webhook, notification), {})
            return
        if webhook.platform == "telegram":
            token = _required_secret(
                webhook.bot_token,
                webhook.bot_token_env,
                f"webhook {webhook.name} bot_token",
            )
            chat_id = _required_secret(webhook.chat_id, webhook.chat_id_env, f"webhook {webhook.name} chat_id")
            url = f"{webhook.api_base.rstrip('/')}/bot{urllib.parse.quote(token, safe=':-_')}/sendMessage"
            self._post_json(url, _telegram_payload(webhook, notification, chat_id), {})
            return
        url = _required_secret(webhook.url, webhook.url_env, f"webhook {webhook.name} url")
        self._post_json(url, _generic_payload(notification), webhook.headers)

    def _post_json(self, url: str, payload: dict[str, Any], headers: dict[str, str]) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        request_headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "agmh/0.1",
            **headers,
        }
        req = urllib.request.Request(url, data=body, headers=request_headers, method="POST")
        with self.opener.open(req, timeout=self.cfg.notifications.timeout_seconds) as response:
            response.read()

    def _build_opener(self) -> urllib.request.OpenerDirector:
        handlers: list[urllib.request.BaseHandler] = []
        if self.cfg.proxy:
            handlers.append(urllib.request.ProxyHandler({"http": self.cfg.proxy, "https": self.cfg.proxy}))
        if self.cfg.insecure_tls:
            handlers.append(urllib.request.HTTPSHandler(context=ssl._create_unverified_context()))
        return urllib.request.build_opener(*handlers)


def safe_config_snapshot(cfg: AppConfig) -> dict[str, Any]:
    return {
        "mode": cfg.mode,
        "dry_run": cfg.dry_run,
        "workspace": str(cfg.workspace),
        "sources_file": str(cfg.sources_file) if cfg.sources_file else None,
        "destinations_file": str(cfg.destinations_file) if cfg.destinations_file else None,
        "sources": [
            {
                "url": safe_display_url(source.url),
                "platform": source.platform,
                "api_base": safe_display_url(source.api_base),
                "owner": source.owner,
                "token_count": len(source.tokens),
                "watch": source.watch,
                "watch_interval_seconds": source.watch_interval_seconds,
                "watch_action": source.watch_action,
            }
            for source in cfg.sources
        ],
        "destinations": [
            {
                "url": safe_display_url(destination.url),
                "platform": destination.platform,
                "api_base": safe_display_url(destination.api_base),
                "owner": destination.owner,
                "token_count": len(destination.tokens),
                "visibility": destination.visibility,
                "push_mode": destination.push_mode,
                "create": destination.create,
                "allow_existing": destination.allow_existing,
            }
            for destination in cfg.destinations
        ],
        "backup": {
            "local_dir": str(cfg.backup.local_dir),
            "clone_protocol": cfg.backup.clone_protocol,
            "include_archived": cfg.backup.include_archived,
            "include_forks": cfg.backup.include_forks,
            "include_private_for_authenticated_user": cfg.backup.include_private_for_authenticated_user,
            "lfs": cfg.backup.lfs,
            "marker_enabled": cfg.backup.marker_enabled,
            "marker_filename": cfg.backup.marker_filename,
            "push_mode": cfg.backup.push_mode,
        },
        "watch": {
            "interval_seconds": cfg.watch.interval_seconds,
            "action": cfg.watch.action,
            "initial_run": cfg.watch.initial_run,
            "once": cfg.watch.once,
        },
        "notifications": {
            "enabled": cfg.notifications.enabled,
            "events": cfg.notifications.events,
            "webhook_count": len(cfg.notifications.webhooks),
            "webhooks": [
                {
                    "name": webhook.name,
                    "platform": webhook.platform,
                    "enabled": webhook.enabled,
                    "events": webhook.events,
                }
                for webhook in cfg.notifications.webhooks
            ],
        },
    }


def _generic_payload(notification: Notification) -> dict[str, Any]:
    return {
        "event": notification.event,
        "title": notification.title,
        "message": notification.message,
        "timestamp": notification.timestamp,
        "data": notification.data,
    }


def _discord_payload(webhook: WebhookConfig, notification: Notification) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "content": _truncate(f"**{notification.title}**\n{notification.message}", 1900),
        "embeds": [
            {
                "title": _truncate(notification.title, 256),
                "description": _truncate(notification.message, 4096),
                "timestamp": notification.timestamp,
                "fields": _discord_fields(notification.data),
            }
        ],
    }
    if webhook.username:
        payload["username"] = webhook.username
    if webhook.avatar_url:
        payload["avatar_url"] = webhook.avatar_url
    return payload


def _telegram_payload(webhook: WebhookConfig, notification: Notification, chat_id: str) -> dict[str, Any]:
    text = _telegram_text(notification, webhook.parse_mode)
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": _truncate(text, 4096),
        "disable_web_page_preview": webhook.disable_web_page_preview,
    }
    if webhook.parse_mode:
        payload["parse_mode"] = webhook.parse_mode
    if webhook.message_thread_id is not None:
        payload["message_thread_id"] = webhook.message_thread_id
    return payload


def _telegram_text(notification: Notification, parse_mode: str | None) -> str:
    lines = [
        f"[{notification.event}] {notification.title}",
        notification.message,
    ]
    for key, value in _summary_items(notification.data):
        lines.append(f"{key}: {value}")
    text = "\n".join(str(line) for line in lines if line not in (None, ""))
    if parse_mode and parse_mode.upper() == "HTML":
        return html.escape(text)
    return text


def _discord_fields(data: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"name": _truncate(key, 256), "value": _truncate(str(value), 1024), "inline": False}
        for key, value in _summary_items(data)[:10]
    ]


def _summary_items(data: dict[str, Any]) -> list[tuple[str, Any]]:
    preferred = [
        "mode",
        "source",
        "repository",
        "destination",
        "action",
        "status",
        "exit_code",
        "path",
        "next_check_in_seconds",
        "error",
    ]
    items: list[tuple[str, Any]] = []
    for key in preferred:
        if key in data and data[key] not in (None, ""):
            items.append((key, _compact(data[key])))
    if not items:
        for key, value in data.items():
            if value not in (None, ""):
                items.append((key, _compact(value)))
    return items


def _compact(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return value


def _event_allowed(event: str, allowed: list[str]) -> bool:
    return "*" in allowed or event in allowed


def _required_secret(value: str | None, env: str | None, field_name: str) -> str:
    resolved = value or _env_value(env)
    if not resolved:
        raise ValueError(f"{field_name} is not configured")
    return resolved


def _env_value(env: str | None) -> str | None:
    return os.getenv(env) if env else None


def _append_query(url: str, query: dict[str, str]) -> str:
    parsed = urllib.parse.urlparse(url)
    current = dict(urllib.parse.parse_qsl(parsed.query))
    current.update(query)
    return urllib.parse.urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            urllib.parse.urlencode(current),
            parsed.fragment,
        )
    )


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 3)]}..."
