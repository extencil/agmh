from __future__ import annotations

from urllib.parse import urlencode

from ..http import ApiClient, HttpError
from ..models import AppConfig, RepoInfo, SourceConfig
from ..ui import UI
from .base import SourceAdapter


class GitHubSource(SourceAdapter):
    platform = "github"

    def __init__(self, source: SourceConfig, cfg: AppConfig, ui: UI):
        super().__init__(source, cfg, ui)
        self.client = ApiClient(
            source.api_base or cfg.github.api_base,
            self.token_pool,
            cfg.retry,
            ui,
            auth_style="github",
            proxy=cfg.proxy,
            insecure_tls=cfg.insecure_tls,
        )

    def discover(self) -> list[RepoInfo]:
        self.ui.info(f"Discovering GitHub repositories for {self.owner}")
        repos = self._discover_owner(self.owner)
        return sorted(repos, key=lambda item: item.full_name.lower())

    def _discover_owner(self, owner: str) -> list[RepoInfo]:
        account_type = self._account_type(owner)
        repos: list[RepoInfo] = []
        if account_type == "Organization":
            repos.extend(self._list_paginated(f"/orgs/{owner}/repos", {"type": "all"}))
        else:
            repos.extend(self._list_paginated(f"/users/{owner}/repos", {"type": "all"}))
            if self.cfg.backup.include_private_for_authenticated_user and self.token_pool:
                repos.extend(self._authenticated_owner_repos(owner))
        return [repo for repo in repos if self.include(repo)]

    def _account_type(self, owner: str) -> str:
        response = self.client.request_json("GET", f"/users/{owner}")
        return str((response.data or {}).get("type") or "User")

    def _authenticated_owner_repos(self, owner: str) -> list[RepoInfo]:
        try:
            me = self.client.request_json("GET", "/user").data or {}
            login = str(me.get("login") or "")
            if login.lower() != owner.lower():
                return []
            return self._list_paginated(
                "/user/repos",
                {
                    "visibility": "all",
                    "affiliation": "owner,collaborator,organization_member",
                    "sort": "full_name",
                },
                owner_filter=owner,
            )
        except HttpError as exc:
            self.ui.warning(f"Could not list authenticated private repositories for {owner}: {exc}")
            return []

    def _list_paginated(
        self,
        path: str,
        params: dict[str, str],
        owner_filter: str | None = None,
    ) -> list[RepoInfo]:
        page = 1
        found: list[RepoInfo] = []
        while True:
            query = {**params, "per_page": "100", "page": str(page)}
            response = self.client.request_json("GET", f"{path}?{urlencode(query)}")
            items = response.data or []
            if not isinstance(items, list):
                raise ValueError(f"Unexpected GitHub response for {path}")
            for raw in items:
                repo = self._repo_from_api(raw)
                if owner_filter and repo.owner.lower() != owner_filter.lower():
                    continue
                found.append(repo)
            if len(items) < 100:
                break
            page += 1
        return found

    def _repo_from_api(self, raw: dict) -> RepoInfo:
        owner = raw.get("owner") or {}
        visibility = "private" if raw.get("private", False) else "public"
        return RepoInfo(
            source_platform=self.platform,
            owner=str(owner.get("login") or raw.get("full_name", "").split("/")[0]),
            name=str(raw["name"]),
            full_name=str(raw["full_name"]),
            web_url=str(raw["html_url"]),
            clone_url=str(raw["clone_url"]),
            ssh_url=raw.get("ssh_url"),
            default_branch=raw.get("default_branch"),
            private=bool(raw.get("private", False)),
            description=raw.get("description"),
            archived=bool(raw.get("archived", False)),
            fork=bool(raw.get("fork", False)),
            visibility=visibility,
            updated_at=raw.get("pushed_at") or raw.get("updated_at"),
        )
