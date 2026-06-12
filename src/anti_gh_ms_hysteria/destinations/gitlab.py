from __future__ import annotations

import re

from ..http import ApiClient, HttpError
from ..models import AppConfig, DestinationConfig, DestinationRepo, RepoInfo
from ..ui import UI
from ..utils import encode_path, url_host
from .base import DestinationAdapter


class GitLabDestination(DestinationAdapter):
    platform = "gitlab"

    def __init__(self, dest: DestinationConfig, cfg: AppConfig, ui: UI):
        super().__init__(dest, cfg, ui)
        host = url_host(dest.url)
        api_base = dest.api_base or f"https://{host}/api/v4"
        self.client = ApiClient(
            api_base,
            self.token_pool,
            cfg.retry,
            ui,
            auth_style="gitlab",
            proxy=cfg.proxy,
            insecure_tls=cfg.insecure_tls,
        )

    def create_repository(self, repo: RepoInfo) -> DestinationRepo:
        if self.cfg.dry_run or not self.dest.create:
            return self._existing_repo(repo)
        namespace = self._namespace_id()
        destination_name = self.destination_repo_name(repo)
        body = {
            "name": destination_name,
            "path": destination_name,
            "visibility": self._gitlab_visibility(repo),
            "namespace_id": namespace,
            "initialize_with_readme": False,
        }
        if repo.description:
            body["description"] = repo.description
        try:
            response = self.client.request_json("POST", "/projects", body)
            data = response.data or {}
            return DestinationRepo(
                platform=self.platform,
                owner=self.owner,
                name=destination_name,
                web_url=data.get("web_url") or self.web_url(repo),
                push_url=data.get("http_url_to_repo") or self.default_push_url(repo),
                created=True,
            )
        except HttpError as exc:
            if self.dest.allow_existing and exc.status in {400, 409}:
                self.ui.warning(f"GitLab repository already exists or could not be created cleanly: {self.owner}/{repo.name}")
                return self._existing_repo(repo)
            raise

    def default_push_url(self, repo: RepoInfo) -> str:
        return f"https://{self.host}/{self.owner}/{self.destination_repo_name(repo)}.git"

    def destination_repo_name(self, repo: RepoInfo) -> str:
        return gitlab_safe_project_path(repo.name)

    def _namespace_id(self) -> int:
        response = self.client.request_json("GET", f"/namespaces/{encode_path(self.owner)}")
        data = response.data or {}
        return int(data["id"])

    def _gitlab_visibility(self, repo: RepoInfo) -> str:
        visibility = self.visibility_for(repo)
        return "private" if visibility == "unlisted" else visibility


def gitlab_safe_project_path(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", name.strip())
    cleaned = re.sub(r"(?i)(\.git|\.atom)$", "", cleaned)

    if name.startswith("."):
        cleaned = f"dot-{cleaned.lstrip('.-_')}"
    elif name.startswith("-"):
        cleaned = f"dash-{cleaned.lstrip('.-_')}"
    elif name.startswith("_"):
        cleaned = f"underscore-{cleaned.lstrip('.-_')}"
    else:
        cleaned = cleaned.strip(".-_")

    cleaned = cleaned.strip(".-_")
    if not cleaned:
        cleaned = "repository"
    if cleaned.lower().endswith((".git", ".atom")):
        cleaned = f"{cleaned}-repo"
    if cleaned[0] in ".-":
        cleaned = f"repo-{cleaned.lstrip('.-')}"
    return cleaned
