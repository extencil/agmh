from __future__ import annotations

from urllib.parse import urlencode

from ..http import ApiClient
from ..models import AppConfig, RepoInfo, SourceConfig
from ..ui import UI
from ..utils import encode_path
from .base import SourceAdapter


class GitLabSource(SourceAdapter):
    platform = "gitlab"

    def __init__(self, source: SourceConfig, cfg: AppConfig, ui: UI):
        super().__init__(source, cfg, ui)
        self.client = ApiClient(
            source.api_base or f"https://{self.host}/api/v4",
            self.token_pool,
            cfg.retry,
            ui,
            auth_style="gitlab",
            proxy=cfg.proxy,
            insecure_tls=cfg.insecure_tls,
        )

    def discover(self) -> list[RepoInfo]:
        self.ui.info(f"Discovering GitLab repositories for {self.owner}")
        repos = self._discover_group(self.owner)
        if not repos and "/" not in self.owner:
            repos = self._discover_user(self.owner)
        return sorted((repo for repo in repos if self.include(repo)), key=lambda item: item.full_name.lower())

    def _discover_group(self, owner: str) -> list[RepoInfo]:
        group = self.client.request_json("GET", f"/groups/{encode_path(owner)}", allow_not_found=True)
        if group.status == 404:
            return []
        return self._list_paginated(
            f"/groups/{encode_path(owner)}/projects",
            {"include_subgroups": "true", "with_shared": "false"},
        )

    def _discover_user(self, username: str) -> list[RepoInfo]:
        users = self.client.request_json(
            "GET",
            f"/users?{urlencode({'username': username, 'per_page': '1'})}",
        ).data or []
        if not users:
            return []
        user_id = str(users[0].get("id") or username)
        return self._list_paginated(
            f"/users/{encode_path(user_id)}/projects",
            {"with_shared": "false"},
        )

    def _list_paginated(self, path: str, params: dict[str, str]) -> list[RepoInfo]:
        page = 1
        found: list[RepoInfo] = []
        while True:
            query = {**params, "per_page": "100", "page": str(page)}
            response = self.client.request_json("GET", f"{path}?{urlencode(query)}")
            items = response.data or []
            if not isinstance(items, list):
                raise ValueError(f"Unexpected GitLab response for {path}")
            found.extend(self._repo_from_api(raw) for raw in items)
            if len(items) < 100:
                break
            page += 1
        return found

    def _repo_from_api(self, raw: dict) -> RepoInfo:
        full_name = str(raw.get("path_with_namespace") or "")
        if not full_name:
            namespace = raw.get("namespace") or {}
            owner = str(namespace.get("full_path") or namespace.get("path") or self.owner)
            full_name = f"{owner}/{raw.get('path') or raw.get('name')}"
        owner = full_name.rsplit("/", 1)[0]
        visibility = str(raw.get("visibility") or "private").lower()
        return RepoInfo(
            source_platform=self.platform,
            owner=owner,
            name=str(raw.get("path") or raw["name"]),
            full_name=full_name,
            web_url=str(raw.get("web_url") or f"https://{self.host}/{full_name}"),
            clone_url=str(raw.get("http_url_to_repo") or f"https://{self.host}/{full_name}.git"),
            ssh_url=raw.get("ssh_url_to_repo"),
            default_branch=raw.get("default_branch"),
            private=visibility != "public",
            description=raw.get("description"),
            archived=bool(raw.get("archived", False)),
            fork=bool(raw.get("forked_from_project")),
            visibility=visibility,
            updated_at=raw.get("last_activity_at") or raw.get("updated_at"),
        )
