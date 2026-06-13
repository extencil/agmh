from __future__ import annotations

from abc import ABC, abstractmethod

from ..git_ops import with_basic_auth
from ..models import AppConfig, DestinationConfig, DestinationRepo, RepoInfo, TokenCredential
from ..tokens import TokenPool
from ..ui import UI
from ..utils import url_host


class DestinationAdapter(ABC):
    platform = "unknown"

    def __init__(self, dest: DestinationConfig, cfg: AppConfig, ui: UI):
        self.dest = dest
        self.cfg = cfg
        self.ui = ui
        self.token_pool = TokenPool(dest.tokens, cfg.retry, self.platform)

    @property
    def key(self) -> str:
        return f"{self.platform}:{self.dest.url}"

    @abstractmethod
    def create_repository(self, repo: RepoInfo) -> DestinationRepo:
        raise NotImplementedError

    def destination_repo_name(self, repo: RepoInfo) -> str:
        return repo.name

    def push_mode_for(self, requested_mode: str) -> str:
        return requested_mode

    def push_urls(self, repo: RepoInfo) -> list[str]:
        if self.dest.push_url_template:
            url = self.dest.push_url_template.format(
                owner=self.owner,
                repo=self.destination_repo_name(repo),
                name=self.destination_repo_name(repo),
                platform=self.platform,
            )
            return self._authenticate_urls(url, repo)
        return self._authenticate_urls(self.default_push_url(repo), repo)

    @abstractmethod
    def default_push_url(self, repo: RepoInfo) -> str:
        raise NotImplementedError

    @property
    def owner(self) -> str:
        if not self.dest.owner:
            raise ValueError(f"Destination owner is missing for {self.dest.url}")
        return self.dest.owner

    @property
    def host(self) -> str:
        return url_host(self.dest.url)

    def private_for(self, repo: RepoInfo) -> bool:
        if self.dest.visibility == "private":
            return True
        if self.dest.visibility in {"public", "unlisted"}:
            return False
        return repo.private

    def visibility_for(self, repo: RepoInfo) -> str:
        if self.dest.visibility == "public":
            return "public"
        if self.dest.visibility == "private":
            return "private"
        if self.dest.visibility == "unlisted":
            return "unlisted"
        source_visibility = (repo.visibility or "").lower()
        if source_visibility in {"public", "private", "unlisted"}:
            return source_visibility
        return "private" if repo.private else "public"

    def _authenticate_urls(self, url: str, repo: RepoInfo) -> list[str]:
        if not url.startswith("http"):
            return [url]
        tokens = self.token_pool.available_tokens()
        if not tokens:
            return [url]
        return [self._auth_url(url, token, repo) for token in tokens]

    def _auth_url(self, url: str, token: TokenCredential, repo: RepoInfo) -> str:
        username = token.username or self.dest.git_username or self.owner
        return with_basic_auth(url, username, token.secret)

    def _existing_repo(self, repo: RepoInfo) -> DestinationRepo:
        return DestinationRepo(
            platform=self.platform,
            owner=self.owner,
            name=self.destination_repo_name(repo),
            web_url=self.web_url(repo),
            push_url=self.default_push_url(repo),
            created=False,
        )

    def web_url(self, repo: RepoInfo) -> str:
        return self.default_push_url(repo).removesuffix(".git")
