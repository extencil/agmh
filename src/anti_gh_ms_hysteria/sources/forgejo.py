from __future__ import annotations

from urllib.parse import urlencode

from ..http import ApiClient, HttpError
from ..models import AppConfig, RepoInfo, SourceConfig
from ..ui import UI
from .base import SourceAdapter


class ForgejoSource(SourceAdapter):
    platform = "forgejo"

    def __init__(self, source: SourceConfig, cfg: AppConfig, ui: UI):
        super().__init__(source, cfg, ui)
        self.client = ApiClient(
            source.api_base or f"https://{self.host}/api/v1",
            self.token_pool,
            cfg.retry,
            ui,
            auth_style="forgejo",
            proxy=cfg.proxy,
            insecure_tls=cfg.insecure_tls,
        )

    def discover(self) -> list[RepoInfo]:
        self.ui.info(f"Discovering Forgejo repositories for {self.owner}")
        repos: dict[str, RepoInfo] = {}
        for repo in self._authenticated_owner_repos(self.owner):
            repos[repo.key.lower()] = repo
        for endpoint in (f"/users/{self.owner}/repos", f"/orgs/{self.owner}/repos"):
            for repo in self._list_paginated(endpoint):
                repos[repo.key.lower()] = repo
        return sorted(
            (repo for repo in repos.values() if self.include(repo)),
            key=lambda item: item.full_name.lower(),
        )

    def _authenticated_owner_repos(self, owner: str) -> list[RepoInfo]:
        try:
            me = self.client.request_json("GET", "/user", allow_not_found=True)
        except HttpError as exc:
            if exc.status == 401:
                return []
            raise
        if me.status == 404:
            return []
        data = me.data or {}
        login = str(data.get("login") or data.get("username") or "")
        if login.lower() != owner.lower():
            return []
        return [
            repo
            for repo in self._list_paginated("/user/repos")
            if repo.owner.lower() == owner.lower()
        ]

    def _list_paginated(self, path: str) -> list[RepoInfo]:
        page = 1
        found: list[RepoInfo] = []
        while True:
            query = {"limit": "100", "page": str(page)}
            response = self.client.request_json(
                "GET",
                f"{path}?{urlencode(query)}",
                allow_not_found=True,
            )
            if response.status == 404:
                return found
            items = response.data or []
            if not isinstance(items, list):
                raise ValueError(f"Unexpected Forgejo response for {path}")
            found.extend(self._repo_from_api(raw) for raw in items)
            if len(items) < 100:
                break
            page += 1
        return found

    def _repo_from_api(self, raw: dict) -> RepoInfo:
        owner = raw.get("owner") or {}
        owner_name = str(owner.get("login") or owner.get("username") or self.owner)
        full_name = str(raw.get("full_name") or f"{owner_name}/{raw['name']}")
        visibility = "private" if raw.get("private", False) else "public"
        web_url = str(raw.get("html_url") or f"https://{self.host}/{full_name}")
        clone_url = str(raw.get("clone_url") or f"{web_url}.git")
        return RepoInfo(
            source_platform=self.platform,
            owner=owner_name,
            name=str(raw["name"]),
            full_name=full_name,
            web_url=web_url,
            clone_url=clone_url,
            ssh_url=raw.get("ssh_url"),
            default_branch=raw.get("default_branch"),
            private=bool(raw.get("private", False)),
            description=raw.get("description"),
            archived=bool(raw.get("archived", False)),
            fork=bool(raw.get("fork", False)),
            visibility=visibility,
            updated_at=raw.get("updated_at"),
        )
