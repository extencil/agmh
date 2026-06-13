from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import AppConfig, RepoInfo, SourceConfig, TokenCredential
from ..tokens import TokenPool
from ..ui import UI
from ..utils import url_host


class SourceAdapter(ABC):
    platform = "unknown"

    def __init__(self, source: SourceConfig, cfg: AppConfig, ui: UI):
        self.source = source
        self.cfg = cfg
        self.ui = ui
        self.token_pool = TokenPool(source.tokens, cfg.retry, self.platform)

    @property
    def key(self) -> str:
        return f"{self.platform}:{self.source.url}"

    @property
    def owner(self) -> str:
        if not self.source.owner:
            raise ValueError(f"Source owner is missing for {self.source.url}")
        return self.source.owner

    @property
    def host(self) -> str:
        return url_host(self.source.url)

    @abstractmethod
    def discover(self) -> list[RepoInfo]:
        raise NotImplementedError

    def current_token(self) -> TokenCredential | None:
        return self.token_pool.current()

    def secrets(self) -> list[str]:
        return self.token_pool.all_secrets()

    def include(self, repo: RepoInfo) -> bool:
        if repo.archived and not self.cfg.backup.include_archived:
            return False
        if repo.fork and not self.cfg.backup.include_forks:
            return False
        return True

