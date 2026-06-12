from __future__ import annotations

from ..http import ApiClient, HttpError
from ..models import AppConfig, DestinationConfig, DestinationRepo, RepoInfo, TokenCredential
from ..ui import UI
from ..utils import url_host
from .base import DestinationAdapter


class ForgejoDestination(DestinationAdapter):
    platform = "forgejo"

    def __init__(self, dest: DestinationConfig, cfg: AppConfig, ui: UI):
        super().__init__(dest, cfg, ui)
        host = url_host(dest.url)
        api_base = dest.api_base or f"https://{host}/api/v1"
        self.client = ApiClient(
            api_base,
            self.token_pool,
            cfg.retry,
            ui,
            auth_style="forgejo",
            proxy=cfg.proxy,
            insecure_tls=cfg.insecure_tls,
        )

    def create_repository(self, repo: RepoInfo) -> DestinationRepo:
        if self.cfg.dry_run or not self.dest.create:
            return self._existing_repo(repo)
        body = {
            "name": repo.name,
            "private": self.private_for(repo),
            "auto_init": False,
        }
        if repo.description:
            body["description"] = repo.description

        endpoint = self._create_endpoint()
        try:
            response = self.client.request_json("POST", endpoint, body)
            data = response.data or {}
            return DestinationRepo(
                platform=self.platform,
                owner=self.owner,
                name=repo.name,
                web_url=data.get("html_url") or self.web_url(repo),
                push_url=data.get("clone_url") or self.default_push_url(repo),
                created=True,
            )
        except HttpError as exc:
            if self.dest.allow_existing and exc.status in {400, 409, 422}:
                self.ui.warning(f"Forgejo repository already exists or could not be created cleanly: {self.owner}/{repo.name}")
                return self._existing_repo(repo)
            raise

    def default_push_url(self, repo: RepoInfo) -> str:
        return f"https://{self.host}/{self.owner}/{repo.name}.git"

    def push_mode_for(self, requested_mode: str) -> str:
        if requested_mode == "mirror":
            return "portable-mirror"
        return requested_mode

    def _auth_url(self, url: str, token: TokenCredential, repo: RepoInfo) -> str:
        username = token.username or self.dest.git_username or self.owner
        from ..git_ops import with_basic_auth

        return with_basic_auth(url, username, token.secret)

    def _create_endpoint(self) -> str:
        me = self.client.request_json("GET", "/user", allow_not_found=True).data or {}
        login = str(me.get("login") or me.get("username") or "")
        if login.lower() == self.owner.lower():
            return "/user/repos"
        org = self.client.request_json("GET", f"/orgs/{self.owner}", allow_not_found=True)
        if org.status != 404:
            return f"/orgs/{self.owner}/repos"
        raise ValueError(
            f"Forgejo destination owner {self.owner} is not the authenticated user and was not found as an organization"
        )
