from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


VisibilityMode = Literal["mirror", "public", "private", "unlisted"]
PushMode = Literal["mirror", "portable-mirror", "all", "default"]
WatchAction = Literal["full", "local", "remote"]
WorkflowMode = Literal["full", "local", "remote", "watching"]
WebhookPlatform = Literal["generic", "discord", "telegram"]


@dataclass(frozen=True)
class TokenCredential:
    secret: str
    name: str = "token"
    username: str | None = None

    @property
    def display_name(self) -> str:
        return self.name or self.username or "token"


@dataclass(frozen=True)
class RepoInfo:
    source_platform: str
    owner: str
    name: str
    full_name: str
    web_url: str
    clone_url: str
    ssh_url: str | None
    default_branch: str | None
    private: bool
    description: str | None = None
    archived: bool = False
    fork: bool = False
    visibility: str | None = None
    updated_at: str | None = None

    @property
    def key(self) -> str:
        return f"{self.source_platform}:{self.full_name}"


@dataclass
class RetryConfig:
    max_retries: int = 5
    base_delay_seconds: float = 1.5
    max_delay_seconds: float = 60.0
    request_timeout_seconds: float = 15.0
    rate_limit_sleep_seconds: int = 300
    wait_on_rate_limit: bool = True


@dataclass
class BackupConfig:
    local_dir: Path = Path("backups")
    clone_protocol: Literal["https", "ssh"] = "https"
    include_archived: bool = True
    include_forks: bool = True
    include_private_for_authenticated_user: bool = True
    lfs: bool = False
    marker_enabled: bool = True
    marker_filename: str = "agmh.txt"
    push_mode: PushMode = "mirror"


@dataclass
class GitConfig:
    author_name: str = "agmh"
    author_email: str = "agmh@localhost"
    commit_message: str = "Backuping with AGMH v{version}"
    ssh_command: str | None = None
    ssh_identity_file: Path | None = None
    ssh_identities_only: bool = True
    ssh_batch_mode: bool = False
    ssh_strict_host_key_checking: str | None = None


@dataclass
class GitHubConfig:
    api_base: str = "https://api.github.com"
    profiles_file: Path | None = None
    profiles: list[str] = field(default_factory=list)
    tokens: list[TokenCredential] = field(default_factory=list)


@dataclass
class SourceConfig:
    url: str
    platform: str | None = None
    api_base: str | None = None
    owner: str | None = None
    tokens: list[TokenCredential] = field(default_factory=list)
    watch: bool = True
    watch_interval_seconds: int | None = None
    watch_action: WatchAction | None = None


@dataclass
class WatchConfig:
    interval_seconds: int = 300
    action: WatchAction = "full"
    initial_run: bool = True
    once: bool = False


@dataclass
class WebhookConfig:
    name: str = "webhook"
    platform: WebhookPlatform = "generic"
    enabled: bool = True
    events: list[str] = field(default_factory=lambda: ["*"])
    url: str | None = None
    url_env: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    username: str | None = None
    avatar_url: str | None = None
    thread_id: str | None = None
    bot_token: str | None = None
    bot_token_env: str | None = None
    chat_id: str | None = None
    chat_id_env: str | None = None
    api_base: str = "https://api.telegram.org"
    parse_mode: str | None = None
    message_thread_id: int | None = None
    disable_web_page_preview: bool = True


@dataclass
class NotificationsConfig:
    enabled: bool = False
    events: list[str] = field(default_factory=lambda: ["*"])
    fail_silently: bool = True
    timeout_seconds: float = 10.0
    webhooks: list[WebhookConfig] = field(default_factory=list)


@dataclass
class DestinationConfig:
    url: str
    platform: str | None = None
    api_base: str | None = None
    owner: str | None = None
    tokens: list[TokenCredential] = field(default_factory=list)
    visibility: VisibilityMode = "mirror"
    push_mode: PushMode = "mirror"
    create: bool = True
    allow_existing: bool = True
    git_username: str | None = None
    push_url_template: str | None = None


@dataclass
class AppConfig:
    mode: WorkflowMode = "full"
    workspace: Path = Path(".agmh")
    dry_run: bool = False
    verbose: int = 0
    tui: bool = True
    proxy: str | None = None
    insecure_tls: bool = False
    destinations_file: Path | None = None
    sources_file: Path | None = None
    sources: list[SourceConfig] = field(default_factory=list)
    destinations: list[DestinationConfig] = field(default_factory=list)
    github: GitHubConfig = field(default_factory=GitHubConfig)
    backup: BackupConfig = field(default_factory=BackupConfig)
    retry: RetryConfig = field(default_factory=RetryConfig)
    git: GitConfig = field(default_factory=GitConfig)
    watch: WatchConfig = field(default_factory=WatchConfig)
    notifications: NotificationsConfig = field(default_factory=NotificationsConfig)
    resume: bool = True
    force: bool = False


@dataclass(frozen=True)
class DestinationRepo:
    platform: str
    owner: str
    name: str
    web_url: str
    push_url: str
    created: bool
