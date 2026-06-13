from __future__ import annotations

from .base import SourceAdapter
from .bitbucket import BitbucketSource
from .forgejo import ForgejoSource
from .github import GitHubSource
from .gitlab import GitLabSource
from .sourcehut import SourceHutSource
from ..models import AppConfig, RepoInfo, SourceConfig, TokenCredential
from ..ui import UI


def build_source(source_config: SourceConfig, app_config: AppConfig, ui: UI) -> SourceAdapter:
    platform = (source_config.platform or "").lower()
    if platform == "github":
        return GitHubSource(source_config, app_config, ui)
    if platform == "gitlab":
        return GitLabSource(source_config, app_config, ui)
    if platform in {"forgejo", "codeberg", "gitea"}:
        return ForgejoSource(source_config, app_config, ui)
    if platform == "bitbucket":
        return BitbucketSource(source_config, app_config, ui)
    if platform in {"sourcehut", "srht"}:
        return SourceHutSource(source_config, app_config, ui)
    raise ValueError(f"Unsupported source platform: {source_config.platform}")


class SourceDiscovery:
    def __init__(self, cfg: AppConfig, ui: UI):
        self.cfg = cfg
        self.ui = ui
        self.sources = [build_source(source, cfg, ui) for source in cfg.sources]
        self.discovery_errors: list[tuple[str, str]] = []
        self.repo_sources: dict[str, SourceAdapter] = {}

    def discover(self) -> list[RepoInfo]:
        self.discovery_errors = []
        self.repo_sources = {}
        repos: dict[str, RepoInfo] = {}
        for source in self.sources:
            for repo in self.discover_one(source):
                repos[repo.key.lower()] = repo
        return sorted(repos.values(), key=lambda item: (item.source_platform, item.full_name.lower()))

    def discover_one(self, source: SourceAdapter) -> list[RepoInfo]:
        try:
            repos = source.discover()
        except Exception as exc:
            self.discovery_errors.append((source.source.url, str(exc)))
            self.ui.error(f"Failed to discover {source.source.url}: {exc}")
            return []
        for repo in repos:
            self.repo_sources[repo.key.lower()] = source
        return repos

    def current_token(self, repo: RepoInfo) -> TokenCredential | None:
        source = self.repo_sources.get(repo.key.lower())
        return source.current_token() if source else None

    def secrets(self) -> list[str]:
        secrets: list[str] = []
        for source in self.sources:
            secrets.extend(source.secrets())
        return secrets


__all__ = ["SourceAdapter", "SourceDiscovery", "build_source"]

