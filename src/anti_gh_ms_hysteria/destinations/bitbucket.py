from __future__ import annotations

from ..http import ApiClient, HttpError
from ..models import AppConfig, DestinationConfig, DestinationRepo, RepoInfo, TokenCredential
from ..ui import UI
from .base import DestinationAdapter


class BitbucketDestination(DestinationAdapter):
    platform = "bitbucket"

    def __init__(self, dest: DestinationConfig, cfg: AppConfig, ui: UI):
        super().__init__(dest, cfg, ui)
        api_base = dest.api_base or "https://api.bitbucket.org/2.0"
        self.client = ApiClient(
            api_base,
            self.token_pool,
            cfg.retry,
            ui,
            auth_style="basic",
            proxy=cfg.proxy,
            insecure_tls=cfg.insecure_tls,
        )

    def create_repository(self, repo: RepoInfo) -> DestinationRepo:
        if self.cfg.dry_run or not self.dest.create:
            return self._existing_repo(repo)
        body = {
            "scm": "git",
            "is_private": self.private_for(repo),
        }
        if repo.description:
            body["description"] = repo.description
        endpoint = f"/repositories/{self.owner}/{repo.name}"
        try:
            response = self.client.request_json("POST", endpoint, body)
            data = response.data or {}
            links = data.get("links") or {}
            html = (links.get("html") or {}).get("href")
            return DestinationRepo(
                platform=self.platform,
                owner=self.owner,
                name=repo.name,
                web_url=html or self.web_url(repo),
                push_url=self.default_push_url(repo),
                created=True,
            )
        except HttpError as exc:
            if self.dest.allow_existing and exc.status in {400, 409}:
                self.ui.warning(f"Bitbucket repository already exists or could not be created cleanly: {self.owner}/{repo.name}")
                return self._existing_repo(repo)
            raise

    def default_push_url(self, repo: RepoInfo) -> str:
        return f"https://bitbucket.org/{self.owner}/{repo.name}.git"

    def push_mode_for(self, requested_mode: str) -> str:
        if requested_mode == "mirror":
            return "portable-mirror"
        return requested_mode

    def _auth_url(self, url: str, token: TokenCredential, repo: RepoInfo) -> str:
        username = token.username or self.dest.git_username or "x-token-auth"
        from ..git_ops import with_basic_auth

        return with_basic_auth(url, username, token.secret)
