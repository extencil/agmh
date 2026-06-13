from __future__ import annotations

from typing import Any

from ..http import ApiClient, HttpError
from ..models import AppConfig, RepoInfo, SourceConfig
from ..ui import UI
from .base import SourceAdapter


class SourceHutSource(SourceAdapter):
    platform = "sourcehut"

    def __init__(self, source: SourceConfig, cfg: AppConfig, ui: UI):
        super().__init__(source, cfg, ui)
        self.client = ApiClient(
            source.api_base or "https://git.sr.ht",
            self.token_pool,
            cfg.retry,
            ui,
            auth_style="bearer",
            proxy=cfg.proxy,
            insecure_tls=cfg.insecure_tls,
        )

    def discover(self) -> list[RepoInfo]:
        self.ui.info(f"Discovering SourceHut repositories for ~{self.owner}")
        repos = self._list_user(self.owner)
        return sorted((repo for repo in repos if self.include(repo)), key=lambda item: item.full_name.lower())

    def _list_user(self, username: str) -> list[RepoInfo]:
        query = """
        query userRepos($username: String!, $cursor: Cursor) {
          user(username: $username) {
            repositories(cursor: $cursor) {
              results {
                name
                description
                visibility
                updated
                repoPath
                HEAD {
                  name
                }
              }
              cursor
            }
          }
        }
        """
        cursor = None
        found: list[RepoInfo] = []
        while True:
            data = self._graphql(query, {"username": username, "cursor": cursor})
            user = (data or {}).get("user") or {}
            repositories = user.get("repositories") or {}
            items = repositories.get("results") or []
            if not isinstance(items, list):
                raise ValueError(f"Unexpected SourceHut response for ~{username}")
            found.extend(self._repo_from_api(raw) for raw in items)
            cursor = repositories.get("cursor")
            if not cursor:
                break
        return found

    def _repo_from_api(self, raw: dict) -> RepoInfo:
        name = str(raw["name"])
        repo_path = str(raw.get("repoPath") or f"~{self.owner}/{name}")
        owner = repo_path.strip("/").split("/", 1)[0].removeprefix("~")
        visibility = str(raw.get("visibility") or "PRIVATE").lower()
        return RepoInfo(
            source_platform=self.platform,
            owner=owner,
            name=name,
            full_name=f"{owner}/{name}",
            web_url=f"https://git.sr.ht/{repo_path}",
            clone_url=f"https://git.sr.ht/{repo_path}",
            ssh_url=f"git@git.sr.ht:{repo_path}",
            default_branch=_branch_name(raw.get("HEAD")),
            private=visibility == "private",
            description=raw.get("description"),
            archived=False,
            fork=False,
            visibility=visibility,
            updated_at=raw.get("updated"),
        )

    def _graphql(self, query: str, variables: dict[str, Any]) -> Any:
        response = self.client.request_json(
            "POST",
            "/query",
            {"query": query, "variables": variables},
        )
        data = response.data or {}
        if data.get("errors"):
            message = "; ".join(str(error.get("message") or error) for error in data["errors"])
            raise HttpError(400, f"SourceHut GraphQL error: {message}", str(data))
        return data.get("data")


def _branch_name(head: Any) -> str | None:
    if not isinstance(head, dict):
        return None
    name = head.get("name")
    if not name:
        return None
    text = str(name)
    return text.removeprefix("refs/heads/")
