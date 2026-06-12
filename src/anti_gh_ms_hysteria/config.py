from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

from .models import (
    AppConfig,
    BackupConfig,
    DestinationConfig,
    GitConfig,
    GitHubConfig,
    RetryConfig,
    TokenCredential,
)
from .utils import infer_platform, parse_owner_from_profile_url, read_lines_file, resolve_secret


def load_config(path: Path | None) -> AppConfig:
    if path is None:
        return AppConfig()
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    base_dir = path.parent
    return config_from_dict(data, base_dir)


def config_from_dict(data: dict[str, Any], base_dir: Path | None = None) -> AppConfig:
    base_dir = base_dir or Path.cwd()
    cfg = AppConfig()
    cfg.workspace = _path(data.get("workspace"), base_dir, cfg.workspace)
    cfg.dry_run = bool(data.get("dry_run", cfg.dry_run))
    cfg.verbose = int(data.get("verbose", cfg.verbose))
    cfg.tui = bool(data.get("tui", cfg.tui))
    cfg.proxy = data.get("proxy", cfg.proxy)
    cfg.insecure_tls = bool(data.get("insecure_tls", data.get("insecure", cfg.insecure_tls)))
    cfg.resume = bool(data.get("resume", cfg.resume))
    cfg.force = bool(data.get("force", cfg.force))
    cfg.destinations_file = _optional_path(data.get("destinations_file"), base_dir)

    github = data.get("github", {})
    cfg.github = GitHubConfig(
        api_base=str(github.get("api_base", cfg.github.api_base)),
        profiles_file=_optional_path(github.get("profiles_file"), base_dir),
        profiles=list(github.get("profiles", cfg.github.profiles)),
        tokens=_token_list(github.get("tokens", [])),
    )

    if not cfg.github.tokens:
        cfg.github.tokens = _default_env_tokens(
            [("GITHUB_TOKEN", "GITHUB_TOKEN"), ("GH_TOKEN", "GH_TOKEN")]
        )

    backup = data.get("backup", {})
    cfg.backup = BackupConfig(
        local_dir=_path(backup.get("local_dir"), base_dir, cfg.backup.local_dir),
        clone_protocol=str(backup.get("clone_protocol", cfg.backup.clone_protocol)),
        include_archived=bool(backup.get("include_archived", cfg.backup.include_archived)),
        include_forks=bool(backup.get("include_forks", cfg.backup.include_forks)),
        include_private_for_authenticated_user=bool(
            backup.get(
                "include_private_for_authenticated_user",
                cfg.backup.include_private_for_authenticated_user,
            )
        ),
        lfs=bool(backup.get("lfs", cfg.backup.lfs)),
        marker_filename=_marker_filename(backup.get("marker_filename", cfg.backup.marker_filename)),
        push_mode=str(backup.get("push_mode", cfg.backup.push_mode)),
    )

    retry = data.get("retry", {})
    cfg.retry = RetryConfig(
        max_retries=int(retry.get("max_retries", cfg.retry.max_retries)),
        base_delay_seconds=float(retry.get("base_delay_seconds", cfg.retry.base_delay_seconds)),
        max_delay_seconds=float(retry.get("max_delay_seconds", cfg.retry.max_delay_seconds)),
        request_timeout_seconds=float(
            retry.get("request_timeout_seconds", cfg.retry.request_timeout_seconds)
        ),
        rate_limit_sleep_seconds=int(
            retry.get("rate_limit_sleep_seconds", cfg.retry.rate_limit_sleep_seconds)
        ),
        wait_on_rate_limit=bool(retry.get("wait_on_rate_limit", cfg.retry.wait_on_rate_limit)),
    )

    git = data.get("git", {})
    cfg.git = GitConfig(
        author_name=str(git.get("author_name", cfg.git.author_name)),
        author_email=str(git.get("author_email", cfg.git.author_email)),
        commit_message=str(git.get("commit_message", cfg.git.commit_message)),
        ssh_command=git.get("ssh_command", cfg.git.ssh_command),
        ssh_identity_file=_optional_path(git.get("ssh_identity_file"), base_dir),
        ssh_identities_only=bool(git.get("ssh_identities_only", cfg.git.ssh_identities_only)),
        ssh_batch_mode=bool(git.get("ssh_batch_mode", cfg.git.ssh_batch_mode)),
        ssh_strict_host_key_checking=git.get(
            "ssh_strict_host_key_checking",
            cfg.git.ssh_strict_host_key_checking,
        ),
    )

    cfg.destinations = [
        _destination_from_dict(raw) for raw in data.get("destinations", [])
    ]

    return cfg


def apply_profile_file(cfg: AppConfig, path: Path | None) -> None:
    if path:
        cfg.github.profiles_file = path
    if cfg.github.profiles_file:
        cfg.github.profiles.extend(read_lines_file(cfg.github.profiles_file))


def apply_destinations_file(cfg: AppConfig, path: Path | None) -> None:
    if path:
        cfg.destinations_file = path
    if cfg.destinations_file:
        cfg.destinations.extend(destinations_from_file(cfg.destinations_file))


def destinations_from_file(path: Path) -> list[DestinationConfig]:
    return [destination_from_url(line) for line in read_lines_file(path)]


def destination_from_url(url: str) -> DestinationConfig:
    platform = infer_platform(url)
    _, owner, parts = parse_owner_from_profile_url(url)
    if platform == "gitlab" and parts:
        owner = "/".join(parts)
    return DestinationConfig(url=url, platform=platform, owner=owner)


def _destination_from_dict(raw: dict[str, Any]) -> DestinationConfig:
    url = str(raw["url"])
    platform = str(raw.get("platform") or infer_platform(url))
    _, owner, parts = parse_owner_from_profile_url(url)
    if platform == "gitlab" and parts:
        owner = "/".join(parts)
    owner = str(raw.get("owner") or owner)
    return DestinationConfig(
        url=url,
        platform=platform,
        api_base=raw.get("api_base"),
        owner=owner,
        tokens=_token_list(raw.get("tokens", [])),
        visibility=str(raw.get("visibility", "mirror")),
        push_mode=str(raw.get("push_mode", "mirror")),
        create=bool(raw.get("create", True)),
        allow_existing=bool(raw.get("allow_existing", True)),
        git_username=raw.get("git_username"),
        push_url_template=raw.get("push_url_template"),
    )


def _token_list(raw_tokens: Any) -> list[TokenCredential]:
    tokens: list[TokenCredential] = []
    for idx, raw in enumerate(raw_tokens or []):
        if isinstance(raw, str):
            if raw.startswith("env:"):
                env = raw.removeprefix("env:")
                tokens.append(TokenCredential(resolve_secret(env=env), name=env))
            else:
                tokens.append(TokenCredential(raw, name=f"token-{idx + 1}"))
            continue
        if not isinstance(raw, dict):
            raise ValueError(f"Invalid token entry: {raw!r}")
        secret = resolve_secret(raw.get("value"), raw.get("env"))
        name = str(raw.get("name") or raw.get("env") or f"token-{idx + 1}")
        username = raw.get("username")
        tokens.append(TokenCredential(secret=secret, name=name, username=username))
    return tokens


def _default_env_tokens(envs: list[tuple[str, str]]) -> list[TokenCredential]:
    tokens: list[TokenCredential] = []
    for env, name in envs:
        value = os.getenv(env)
        if value:
            tokens.append(TokenCredential(value, name=name))
    return tokens


def parse_cli_token(value: str) -> TokenCredential:
    username = None
    token_value = value
    name = "cli-token"
    if value.startswith("env:"):
        env = value.removeprefix("env:")
        token_value = resolve_secret(env=env)
        name = env
    elif "=" in value and value.split("=", 1)[0].isidentifier():
        env, _ = value.split("=", 1)
        token_value = resolve_secret(value=value.split("=", 1)[1])
        name = env
    if ":" in token_value and not token_value.startswith(("ghp_", "github_pat_")):
        maybe_user, maybe_token = token_value.split(":", 1)
        if maybe_user and maybe_token:
            username = maybe_user
            token_value = maybe_token
            name = maybe_user
    return TokenCredential(token_value, name=name, username=username)


def parse_destination_token(value: str) -> tuple[str, TokenCredential]:
    if ":" not in value:
        raise ValueError("Destination tokens must use platform:token or platform:env:NAME")
    platform, raw = value.split(":", 1)
    return platform.lower(), parse_cli_token(raw)


def _optional_path(value: Any, base_dir: Path) -> Path | None:
    if value in (None, ""):
        return None
    return _path(value, base_dir, Path("."))


def _path(value: Any, base_dir: Path, default: Path) -> Path:
    if value in (None, ""):
        return default
    path = Path(str(value)).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return path


def _marker_filename(value: Any) -> str:
    marker = str(value or "").strip()
    path = Path(marker)
    if (
        not marker
        or path.is_absolute()
        or path.name != marker
        or marker in {".", ".."}
        or ".." in path.parts
    ):
        raise ValueError("backup.marker_filename must be a plain filename, not a path")
    return marker
