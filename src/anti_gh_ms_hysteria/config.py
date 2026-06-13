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
    SourceConfig,
    TokenCredential,
)
from .utils import infer_platform, parse_owner_from_profile_url, read_lines_file, resolve_secret


class ConfigError(ValueError):
    pass


def load_config(path: Path | None, mode_override: str | None = None) -> AppConfig:
    if path is None:
        cfg = AppConfig()
        if mode_override:
            cfg.mode = _workflow_mode(mode_override)
        return cfg
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"Cannot read config file {path}: {exc}") from exc

    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Invalid TOML in {path}: {exc}{_toml_error_hint(text)}") from exc

    base_dir = path.parent
    try:
        return config_from_dict(data, base_dir, mode_override=mode_override)
    except ConfigError:
        raise
    except ValueError as exc:
        raise ConfigError(f"Invalid config in {path}: {exc}") from exc


def config_from_dict(
    data: dict[str, Any],
    base_dir: Path | None = None,
    mode_override: str | None = None,
) -> AppConfig:
    base_dir = base_dir or Path.cwd()
    cfg = AppConfig()
    cfg.mode = _workflow_mode(mode_override or data.get("mode", cfg.mode))
    cfg.workspace = _path(data.get("workspace"), base_dir, cfg.workspace)
    cfg.dry_run = bool(data.get("dry_run", cfg.dry_run))
    cfg.verbose = int(data.get("verbose", cfg.verbose))
    cfg.tui = bool(data.get("tui", cfg.tui))
    cfg.proxy = data.get("proxy", cfg.proxy)
    cfg.insecure_tls = bool(data.get("insecure_tls", data.get("insecure", cfg.insecure_tls)))
    cfg.resume = bool(data.get("resume", cfg.resume))
    cfg.force = bool(data.get("force", cfg.force))
    cfg.destinations_file = _optional_path(data.get("destinations_file"), base_dir)
    cfg.sources_file = _optional_path(data.get("sources_file"), base_dir)

    github = data.get("github", {})
    cfg.github = GitHubConfig(
        api_base=str(github.get("api_base", cfg.github.api_base)),
        profiles_file=_optional_path(github.get("profiles_file"), base_dir),
        profiles=list(github.get("profiles", cfg.github.profiles)),
        tokens=[] if cfg.mode == "remote" else _token_list(github.get("tokens", []), "github.tokens"),
    )

    if cfg.mode != "remote" and not cfg.github.tokens:
        cfg.github.tokens = _default_env_tokens(
            [("GITHUB_TOKEN", "GITHUB_TOKEN"), ("GH_TOKEN", "GH_TOKEN")]
        )

    if cfg.mode != "remote":
        cfg.sources = [
            _source_from_dict(raw, parse_tokens=True) for raw in data.get("sources", [])
        ]
        cfg.sources.extend(
            source_from_url(
                profile,
                tokens=cfg.github.tokens,
                api_base=cfg.github.api_base,
            )
            for profile in cfg.github.profiles
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

    if cfg.mode != "local":
        cfg.destinations = [
            _destination_from_dict(raw) for raw in data.get("destinations", [])
        ]

    return cfg


def apply_profile_file(cfg: AppConfig, path: Path | None) -> None:
    if path:
        cfg.sources_file = path
    if cfg.sources_file:
        cfg.sources.extend(sources_from_file(cfg.sources_file, github_tokens=cfg.github.tokens))
    if cfg.github.profiles_file:
        profiles = read_lines_file(cfg.github.profiles_file)
        cfg.github.profiles.extend(profiles)
        cfg.sources.extend(
            source_from_url(profile, tokens=cfg.github.tokens, api_base=cfg.github.api_base)
            for profile in profiles
        )


def apply_destinations_file(cfg: AppConfig, path: Path | None) -> None:
    if path:
        cfg.destinations_file = path
    if cfg.destinations_file:
        cfg.destinations.extend(destinations_from_file(cfg.destinations_file))


def destinations_from_file(path: Path) -> list[DestinationConfig]:
    return [destination_from_url(line) for line in read_lines_file(path)]


def sources_from_file(
    path: Path,
    github_tokens: list[TokenCredential] | None = None,
) -> list[SourceConfig]:
    return [
        source_from_url(line, tokens=github_tokens if _looks_like_github(line) else None)
        for line in read_lines_file(path)
    ]


def source_from_url(
    url: str,
    tokens: list[TokenCredential] | None = None,
    api_base: str | None = None,
) -> SourceConfig:
    platform = infer_platform(url)
    _, owner, parts = parse_owner_from_profile_url(url)
    if platform == "gitlab" and parts:
        owner = "/".join(parts)
    return SourceConfig(
        url=url,
        platform=platform,
        owner=owner,
        api_base=api_base if platform == "github" else None,
        tokens=list(tokens or []) if platform == "github" else [],
    )


def destination_from_url(url: str) -> DestinationConfig:
    platform = infer_platform(url)
    _, owner, parts = parse_owner_from_profile_url(url)
    if platform == "gitlab" and parts:
        owner = "/".join(parts)
    return DestinationConfig(url=url, platform=platform, owner=owner)


def _source_from_dict(raw: dict[str, Any], parse_tokens: bool = True) -> SourceConfig:
    url = str(raw["url"])
    platform = str(raw.get("platform") or infer_platform(url))
    _, owner, parts = parse_owner_from_profile_url(url)
    if platform == "gitlab" and parts:
        owner = "/".join(parts)
    owner = str(raw.get("owner") or owner)
    return SourceConfig(
        url=url,
        platform=platform,
        api_base=raw.get("api_base"),
        owner=owner,
        tokens=_token_list(raw.get("tokens", []), f"source {url} tokens") if parse_tokens else [],
    )


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
        tokens=_token_list(raw.get("tokens", []), f"destination {url} tokens"),
        visibility=str(raw.get("visibility", "mirror")),
        push_mode=str(raw.get("push_mode", "mirror")),
        create=bool(raw.get("create", True)),
        allow_existing=bool(raw.get("allow_existing", True)),
        git_username=raw.get("git_username"),
        push_url_template=raw.get("push_url_template"),
    )


def _token_list(raw_tokens: Any, field_name: str) -> list[TokenCredential]:
    tokens: list[TokenCredential] = []
    if raw_tokens in (None, ""):
        return tokens

    if isinstance(raw_tokens, dict):
        if "env" in raw_tokens or "value" in raw_tokens:
            return [_token_from_entry(raw_tokens, field_name, 0, None)]
        return [
            _token_from_entry(raw, field_name, idx, str(name))
            for idx, (name, raw) in enumerate(raw_tokens.items())
        ]

    if not isinstance(raw_tokens, list):
        raise ConfigError(f"{field_name} must be a list, a token table, or a named token table")

    for idx, raw in enumerate(raw_tokens):
        tokens.append(_token_from_entry(raw, field_name, idx, None))
    return tokens


def _token_from_entry(raw: Any, field_name: str, idx: int, default_name: str | None) -> TokenCredential:
    fallback_name = default_name or f"token-{idx + 1}"
    if isinstance(raw, str):
        if raw.startswith("env:"):
            env = raw.removeprefix("env:")
            return TokenCredential(resolve_secret(env=env), name=default_name or env)
        return TokenCredential(raw, name=fallback_name)
    if not isinstance(raw, dict):
        raise ConfigError(f"Invalid {field_name} entry: {raw!r}")

    secret = resolve_secret(raw.get("value"), raw.get("env"))
    name = str(raw.get("name") or default_name or raw.get("env") or f"token-{idx + 1}")
    username = raw.get("username")
    return TokenCredential(secret=secret, name=name, username=username)


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
            name = maybe_user
            if maybe_token.startswith("env:"):
                token_value = resolve_secret(env=maybe_token.removeprefix("env:"))
            else:
                token_value = maybe_token
    return TokenCredential(token_value, name=name, username=username)


def parse_destination_token(value: str) -> tuple[str, TokenCredential]:
    if ":" not in value:
        raise ValueError("Destination tokens must use platform:token, platform:env:NAME, or platform:username:env:NAME")
    platform, raw = value.split(":", 1)
    return platform.lower(), parse_cli_token(raw)


def parse_source_token(value: str) -> tuple[str, TokenCredential]:
    if ":" not in value:
        raise ValueError("Source tokens must use platform:token, platform:env:NAME, or platform:username:env:NAME")
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


def _workflow_mode(value: Any) -> str:
    mode = str(value or "full").strip().lower()
    aliases = {
        "default": "full",
        "all": "full",
        "local-only": "local",
        "local_mirror": "local",
        "local-mirror": "local",
        "remote-only": "remote",
        "remote_mirror": "remote",
        "remote-mirror": "remote",
    }
    mode = aliases.get(mode, mode)
    if mode not in {"full", "local", "remote"}:
        raise ConfigError("mode must be one of: full, local, remote")
    return mode


def _looks_like_github(url: str) -> bool:
    try:
        return infer_platform(url) == "github"
    except ValueError:
        return False


def _toml_error_hint(text: str) -> str:
    if "tokens" not in text:
        return ""
    return (
        "\n\nFor multiple github.tokens entries, use commas between array items:\n"
        'tokens = [\n'
        '  { env = "GITHUB_TOKEN", name = "github-primary" },\n'
        '  { env = "GITHUB_TOKEN_2", name = "github-secondary" },\n'
        ']\n\n'
        "You can also use a named token table:\n"
        "[github.tokens]\n"
        'github-primary = { env = "GITHUB_TOKEN" }\n'
        'github-secondary = { env = "GITHUB_TOKEN_2" }'
    )
