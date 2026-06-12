from __future__ import annotations

from urllib.parse import urlencode

from ..http import ApiClient, HttpError
from ..models import AppConfig, RepoInfo
from ..tokens import TokenPool
from ..ui import UI
from ..utils import parse_owner_from_profile_url


class GitHubSource:
    def __init__(self, cfg: AppConfig, ui: UI):
        self.cfg = cfg
        self.ui = ui
        self.token_pool = TokenPool(cfg.github.tokens, cfg.retry, "GitHub")
        self.client = ApiClient(
            cfg.github.api_base,
            self.token_pool,
            cfg.retry,
            ui,
            auth_style="github",
            proxy=cfg.proxy,
            insecure_tls=cfg.insecure_tls,
        )
        self.discovery_errors: list[tuple[str, str]] = []

    def discover(self) -> list[RepoInfo]:
        self.discovery_errors = []
        repos: dict[str, RepoInfo] = {}
        for profile in self.cfg.github.profiles:
            try:
                owner = self._profile_owner(profile)
                self.ui.info(f"Discovering GitHub repositories for {owner}")
                for repo in self._discover_owner(owner):
                    repos[repo.full_name.lower()] = repo
            except Exception as exc:
                self.discovery_errors.append((profile, str(exc)))
                self.ui.error(f"Failed to discover {profile}: {exc}")
        return sorted(repos.values(), key=lambda item: item.full_name.lower())

    def current_token(self):
        return self.token_pool.current()

    def secrets(self) -> list[str]:
        return self.token_pool.all_secrets()

    def _profile_owner(self, profile: str) -> str:
        host, owner, _ = parse_owner_from_profile_url(profile)
        if host != "github.com":
            raise ValueError(f"GitHub source profiles must use github.com: {profile}")
        return owner

    def _discover_owner(self, owner: str) -> list[RepoInfo]:
        account_type = self._account_type(owner)
        repos: list[RepoInfo] = []
        if account_type == "Organization":
            repos.extend(self._list_paginated(f"/orgs/{owner}/repos", {"type": "all"}))
        else:
            repos.extend(self._list_paginated(f"/users/{owner}/repos", {"type": "all"}))
            if self.cfg.backup.include_private_for_authenticated_user and self.token_pool:
                repos.extend(self._authenticated_owner_repos(owner))
        return [repo for repo in repos if self._include(repo)]

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
        return RepoInfo(
            source_platform="github",
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
        )

    def _include(self, repo: RepoInfo) -> bool:
        if repo.archived and not self.cfg.backup.include_archived:
            return False
        if repo.fork and not self.cfg.backup.include_forks:
            return False
        return True
