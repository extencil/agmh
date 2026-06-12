from __future__ import annotations

import json
import time
from pathlib import Path

from .destinations import build_destination
from .destinations.base import DestinationAdapter
from .git_ops import GitCommandError, GitMirrorManager, GitRunner
from .models import AppConfig, RepoInfo
from .sources.github import GitHubSource
from .state import StateStore
from .ui import UI
from .utils import scrub_secret, utc_now_iso


class MirrorRunner:
    def __init__(self, cfg: AppConfig, ui: UI):
        self.cfg = cfg
        self.ui = ui
        self.source = GitHubSource(cfg, ui)
        self.destinations = [build_destination(dest, cfg, ui) for dest in cfg.destinations]
        secrets = self.source.secrets()
        for dest in self.destinations:
            secrets.extend(dest.token_pool.all_secrets())
        self.git_runner = GitRunner(cfg, ui, secrets)
        self.git = GitMirrorManager(cfg, ui, self.git_runner)
        self.state = StateStore(cfg.workspace / "state.json")
        self.secrets = secrets

    def discover(self) -> list[RepoInfo]:
        return self.source.discover()

    def run(self) -> int:
        repos = self.discover()
        self.ui.info(f"Discovered {len(repos)} GitHub repositories")
        discovery_failures = len(self.source.discovery_errors)
        failures = discovery_failures
        for repo in repos:
            ok = self._process_repo(repo)
            if not ok:
                failures += 1
        if failures:
            if discovery_failures:
                self.ui.warning(f"Discovery failed for {discovery_failures} source profile(s)")
            repository_failures = failures - discovery_failures
            if repository_failures:
                self.ui.warning(f"Completed with {repository_failures} repository-level failures")
            return 1
        self.ui.success("Completed all repository workflows")
        return 0

    def write_discovery_json(self, path: Path | None = None) -> list[RepoInfo]:
        repos = self.discover()
        payload = [
            {
                "full_name": repo.full_name,
                "private": repo.private,
                "clone_url": repo.clone_url,
                "ssh_url": repo.ssh_url,
                "default_branch": repo.default_branch,
                "web_url": repo.web_url,
            }
            for repo in repos
        ]
        text = json.dumps(payload, indent=2, sort_keys=True)
        if path:
            path.write_text(text + "\n", encoding="utf-8")
            self.ui.info(f"Wrote discovery output to {path}")
        else:
            print(text)
        return repos

    def _process_repo(self, repo: RepoInfo) -> bool:
        key = repo.key
        self.state.mark_repo_metadata(
            key,
            source_url=repo.web_url,
            full_name=repo.full_name,
            private=repo.private,
            default_branch=repo.default_branch,
        )
        mirror_path = self.git.mirror_path(repo)
        downloaded_at = utc_now_iso()
        branch = repo.default_branch or "main"

        try:
            if self._should_skip_step(key, "clone") and mirror_path.exists():
                self.ui.info(f"Skipping clone for {repo.full_name}; state already marks it done")
                clone_step = self.state.repo(key).get("steps", {}).get("clone", {})
                downloaded_at = clone_step.get("downloaded_at", downloaded_at)
            else:
                token = self.source.current_token()
                mirror_path, downloaded_at = self.git.clone_or_update(repo, token)
                self._mark_step(key, "clone", "done", path=str(mirror_path), downloaded_at=downloaded_at)
        except Exception as exc:
            self._mark_step(key, "clone", "failed", error=str(exc))
            self.ui.error(f"Clone/update failed for {repo.full_name}: {exc}")
            return False

        try:
            if self._should_skip_step(key, "marker"):
                self.ui.info(f"Skipping marker for {repo.full_name}; state already marks it done")
                marker_step = self.state.repo(key).get("steps", {}).get("marker", {})
                branch = marker_step.get("branch", branch)
            else:
                branch = self.git.ensure_marker_commit(repo, mirror_path, downloaded_at)
                self._mark_step(key, "marker", "done", branch=branch)
        except Exception as exc:
            self._mark_step(key, "marker", "failed", error=str(exc))
            self.ui.error(f"Marker commit failed for {repo.full_name}: {exc}")
            return False

        destination_failures = 0
        for destination in self.destinations:
            if not self._process_destination(repo, mirror_path, branch, destination):
                destination_failures += 1
        return destination_failures == 0

    def _process_destination(
        self,
        repo: RepoInfo,
        mirror_path: Path,
        branch: str,
        destination: DestinationAdapter,
    ) -> bool:
        key = repo.key
        dest_key = destination.key
        try:
            if self._should_skip_destination(key, dest_key, "create"):
                create_step = self.state.repo(key).get("destinations", {}).get(dest_key, {}).get("create", {})
                expected_web_url = destination.web_url(repo)
                if create_step.get("web_url") != expected_web_url:
                    self.ui.info(
                        f"Rechecking create for {repo.full_name} on {dest_key}; destination path mapping changed"
                    )
                    created = destination.create_repository(repo)
                    self._mark_destination(
                        key,
                        dest_key,
                        "create",
                        "done",
                        web_url=created.web_url,
                        created=created.created,
                    )
                else:
                    self.ui.info(f"Skipping create for {repo.full_name} on {dest_key}; state already marks it done")
            else:
                created = destination.create_repository(repo)
                self._mark_destination(
                    key,
                    dest_key,
                    "create",
                    "done",
                    web_url=created.web_url,
                    created=created.created,
                )
        except Exception as exc:
            self._mark_destination(key, dest_key, "create", "failed", error=str(exc))
            self.ui.error(f"Create failed for {repo.full_name} on {dest_key}: {exc}")
            return False

        try:
            if self._should_skip_destination(key, dest_key, "push"):
                self.ui.info(f"Skipping push for {repo.full_name} to {dest_key}; state already marks it done")
            else:
                self._push_with_rotation(repo, mirror_path, branch, destination)
                self._mark_destination(key, dest_key, "push", "done")
        except Exception as exc:
            self._mark_destination(key, dest_key, "push", "failed", error=str(exc))
            self.ui.error(f"Push failed for {repo.full_name} to {dest_key}: {exc}")
            return False
        return True

    def _push_with_rotation(
        self,
        repo: RepoInfo,
        mirror_path: Path,
        branch: str,
        destination: DestinationAdapter,
    ) -> None:
        push_urls = destination.push_urls(repo)
        if not push_urls:
            raise RuntimeError(f"No push URL available for destination {destination.key}")
        last_error: Exception | None = None
        attempt = 0
        while True:
            for push_url in push_urls:
                try:
                    self.ui.info(f"Pushing {repo.full_name} to {destination.key}")
                    requested_mode = destination.dest.push_mode or self.cfg.backup.push_mode
                    destination_mode = destination.push_mode_for(requested_mode)
                    self.git.push(mirror_path, push_url, destination_mode, branch)
                    return
                except GitCommandError as exc:
                    last_error = exc
                    text = f"{exc.stdout}\n{exc.stderr}".lower()
                    self.ui.warning(
                        "Git push failed; trying next credential if available: "
                        + scrub_secret(exc.stderr.strip() or str(exc), self.secrets)
                    )
                    if _looks_like_git_rate_limit(text) and self.cfg.retry.wait_on_rate_limit:
                        wait = self.cfg.retry.rate_limit_sleep_seconds
                        self.ui.warning(f"Git push appears rate limited; waiting {wait}s before retry")
                        time.sleep(wait)
                        break
                    if _looks_like_transient_git_network_error(text) and attempt < self.cfg.retry.max_retries:
                        attempt += 1
                        wait = min(
                            self.cfg.retry.max_delay_seconds,
                            self.cfg.retry.base_delay_seconds * (2 ** (attempt - 1)),
                        )
                        self.ui.warning(f"Git push network error; retrying in {wait:.1f}s")
                        time.sleep(wait)
                        break
            else:
                if last_error:
                    raise last_error
                raise RuntimeError(f"Push failed for {repo.full_name} to {destination.key}")

    def _should_skip_step(self, key: str, step: str) -> bool:
        return self.cfg.resume and not self.cfg.force and self.state.is_done(key, step)

    def _should_skip_destination(self, key: str, destination_key: str, step: str) -> bool:
        return (
            self.cfg.resume
            and not self.cfg.force
            and self.state.destination_status(key, destination_key, step) == "done"
        )

    def _mark_step(self, key: str, step: str, status: str, **extra) -> None:
        if self.cfg.dry_run and status == "done":
            status = "planned"
        self.state.mark_step(key, step, status, **extra)

    def _mark_destination(self, key: str, destination_key: str, step: str, status: str, **extra) -> None:
        if self.cfg.dry_run and status == "done":
            status = "planned"
        self.state.mark_destination(key, destination_key, step, status, **extra)


def _looks_like_git_rate_limit(text: str) -> bool:
    return "rate limit" in text or "too many requests" in text or "http 429" in text


def _looks_like_transient_git_network_error(text: str) -> bool:
    patterns = [
        "gnutls_handshake() failed",
        "tls connection was non-properly terminated",
        "connection reset",
        "connection timed out",
        "operation timed out",
        "the remote end hung up unexpectedly",
        "http/2 stream",
        "curl 18",
        "curl 28",
        "curl 35",
        "curl 56",
    ]
    return any(pattern in text for pattern in patterns)
