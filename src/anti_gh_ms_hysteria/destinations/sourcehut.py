from __future__ import annotations

from typing import Any

from ..http import ApiClient, HttpError
from ..models import AppConfig, DestinationConfig, DestinationRepo, RepoInfo, TokenCredential
from ..ui import UI
from ..utils import url_host
from .base import DestinationAdapter


class SourceHutDestination(DestinationAdapter):
    platform = "sourcehut"

    def __init__(self, dest: DestinationConfig, cfg: AppConfig, ui: UI):
        super().__init__(dest, cfg, ui)
        host = url_host(dest.url)
        api_base = dest.api_base or f"https://{host if host == 'git.sr.ht' else 'git.sr.ht'}"
        self.client = ApiClient(
            api_base,
            self.token_pool,
            cfg.retry,
            ui,
            auth_style="bearer",
            proxy=cfg.proxy,
            insecure_tls=cfg.insecure_tls,
        )

    def create_repository(self, repo: RepoInfo) -> DestinationRepo:
        if self.cfg.dry_run or not self.dest.create:
            return self._existing_repo(repo)
        mutation = """
        mutation createRepository($name: String!, $visibility: Visibility!, $description: String) {
          createRepository(name: $name, visibility: $visibility, description: $description) {
            id
            name
            visibility
            repoPath
          }
        }
        """
        variables = {
            "name": repo.name,
            "visibility": self._visibility(repo),
            "description": repo.description,
        }
        try:
            data = self._graphql(mutation, variables)
            created = (data or {}).get("createRepository") or {}
            repo_path = created.get("repoPath")
            return DestinationRepo(
                platform=self.platform,
                owner=self.owner,
                name=repo.name,
                web_url=f"https://git.sr.ht/{repo_path}" if repo_path else self.web_url(repo),
                push_url=self.default_push_url(repo),
                created=True,
            )
        except HttpError as exc:
            if self.dest.allow_existing and exc.status in {400, 409}:
                self.ui.warning(f"SourceHut repository already exists or could not be created cleanly: ~{self.owner}/{repo.name}")
                return self._existing_repo(repo)
            raise

    def default_push_url(self, repo: RepoInfo) -> str:
        if self.dest.push_url_template:
            return self.dest.push_url_template.format(owner=self.owner, repo=repo.name, name=repo.name)
        return f"git@git.sr.ht:~{self.owner}/{repo.name}"

    def web_url(self, repo: RepoInfo) -> str:
        return f"https://git.sr.ht/~{self.owner}/{repo.name}"

    def _auth_url(self, url: str, token: TokenCredential, repo: RepoInfo) -> str:
        if not url.startswith("http"):
            return url
        from ..git_ops import with_basic_auth

        username = token.username or self.dest.git_username or "oauth2"
        return with_basic_auth(url, username, token.secret)

    def _graphql(self, query: str, variables: dict[str, Any]) -> Any:
        response = self.client.request_json(
            "POST",
            "/query",
            {"query": query, "variables": variables},
        )
        data = response.data or {}
        if data.get("errors"):
            message = "; ".join(str(error.get("message") or error) for error in data["errors"])
            status = 409 if "exist" in message.lower() else 400
            raise HttpError(status, f"SourceHut GraphQL error: {message}", str(data))
        return data.get("data")

    def _visibility(self, repo: RepoInfo) -> str:
        visibility = self.visibility_for(repo)
        if visibility == "unlisted":
            return "UNLISTED"
        return "PRIVATE" if visibility == "private" else "PUBLIC"
