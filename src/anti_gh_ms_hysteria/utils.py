from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlparse


SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_lines_file(path: Path) -> list[str]:
    lines: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        lines.append(line)
    return lines


def safe_path_part(value: str) -> str:
    cleaned = SAFE_NAME_RE.sub("-", value.strip())
    return cleaned.strip(".-") or "unnamed"


def parse_owner_from_profile_url(url: str) -> tuple[str, str, list[str]]:
    parsed = urlparse(url if "://" in url else f"https://{url}")
    host = parsed.netloc.lower()
    parts = [part for part in parsed.path.split("/") if part]
    if not host or not parts:
        raise ValueError(f"Invalid profile URL: {url}")
    return host, parts[-1].removeprefix("~"), parts


def infer_platform(url: str) -> str:
    host, _, _ = parse_owner_from_profile_url(url)
    if host == "github.com" or host.endswith(".github.com"):
        return "github"
    if "gitlab" in host:
        return "gitlab"
    if host == "codeberg.org" or "forgejo" in host or "gitea" in host:
        return "forgejo"
    if host == "bitbucket.org":
        return "bitbucket"
    if host in {"git.sr.ht", "sr.ht", "sourcehut.org"} or host.endswith(".sr.ht"):
        return "sourcehut"
    raise ValueError(f"Cannot infer platform from URL: {url}")


def url_host(url: str) -> str:
    parsed = urlparse(url if "://" in url else f"https://{url}")
    if not parsed.netloc:
        raise ValueError(f"Invalid URL: {url}")
    return parsed.netloc.lower()


def join_url(base: str, path: str) -> str:
    return f"{base.rstrip('/')}/{path.lstrip('/')}"


def encode_path(path: str) -> str:
    return quote(path.strip("/"), safe="")


def resolve_secret(value: str | None = None, env: str | None = None) -> str:
    if value:
        return value
    if env:
        secret = os.getenv(env)
        if not secret:
            raise ValueError(f"Environment variable {env} is not set")
        return secret
    raise ValueError("Token must define either value or env")


def scrub_secret(text: str, secrets: list[str]) -> str:
    scrubbed = text
    for secret in secrets:
        if secret:
            scrubbed = scrubbed.replace(secret, "***")
            scrubbed = scrubbed.replace(quote(secret, safe=""), "***")
    return scrubbed


def ensure_within(parent: Path, child: Path) -> None:
    parent_resolved = parent.resolve()
    child_resolved = child.resolve()
    if parent_resolved != child_resolved and parent_resolved not in child_resolved.parents:
        raise ValueError(f"Refusing path outside workspace: {child_resolved}")

