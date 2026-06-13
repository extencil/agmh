from __future__ import annotations

from urllib.parse import urlencode

from ..http import ApiClient
from ..models import AppConfig, RepoInfo, SourceConfig
from ..ui import UI
from .base import SourceAdapter


class BitbucketSource(SourceAdapter):
    platform = "bitbucket"

    def __init__(self, source: SourceConfig, cfg: AppConfig, ui: UI):
        super().__init__(source, cfg, ui)
        self.client = ApiClient(
            source.api_base or "https://api.bitbucket.org/2.0",
            self.token_pool,
            cfg.retry,
            ui,
            auth_style="basic",
            proxy=cfg.proxy,
            insecure_tls=cfg.insecure_tls,
        )

    def discover(self) -> list[RepoInfo]:
        self.ui.info(f"Discovering Bitbucket repositories for {self.owner}")
        repos = self._list_workspace(self.owner)
        return sorted((repo for repo in repos if self.include(repo)), key=lambda item: item.full_name.lower())

    def _list_workspace(self, workspace: str) -> list[RepoInfo]:
        path_or_url = f"/repositories/{workspace}?{urlencode({'pagelen': '100'})}"
        found: list[RepoInfo] = []
        while path_or_url:
            response = self.client.request_json("GET", path_or_url)
            data = response.data or {}
            items = data.get("values") or []
            if not isinstance(items, list):
                raise ValueError(f"Unexpected Bitbucket response for {workspace}")
            found.extend(self._repo_from_api(raw) for raw in items)
            path_or_url = data.get("next")
        return found

    def _repo_from_api(self, raw: dict) -> RepoInfo:
        full_name = str(raw["full_name"])
        owner, _, slug = full_name.partition("/")
        links = raw.get("links") or {}
        clone_url, ssh_url = _clone_urls(links.get("clone") or [])
        web_url = str((links.get("html") or {}).get("href") or f"https://bitbucket.org/{full_name}")
        default_branch = raw.get("mainbranch") or {}
        visibility = "private" if raw.get("is_private", False) else "public"
        return RepoInfo(
            source_platform=self.platform,
            owner=owner,
            name=slug or str(raw.get("slug") or raw["name"]),
            full_name=full_name,
            web_url=web_url,
            clone_url=clone_url or f"https://bitbucket.org/{full_name}.git",
            ssh_url=ssh_url,
            default_branch=default_branch.get("name") if isinstance(default_branch, dict) else None,
            private=bool(raw.get("is_private", False)),
            description=raw.get("description"),
            archived=bool(raw.get("archived", False)),
            fork=bool(raw.get("parent")),
            visibility=visibility,
        )


def _clone_urls(clones: list[dict]) -> tuple[str | None, str | None]:
    https_url = None
    ssh_url = None
    for clone in clones:
        name = str(clone.get("name") or "").lower()
        href = clone.get("href")
        if name == "https" and href:
            https_url = str(href)
        elif name == "ssh" and href:
            ssh_url = str(href)
    return https_url, ssh_url

