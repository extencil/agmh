from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from .destinations import build_destination
from .destinations.base import DestinationAdapter
from .git_ops import GitCommandError, GitMirrorManager, GitRunner
from .models import AppConfig, RepoInfo
from .sources import SourceDiscovery
from .state import StateStore
from .ui import UI
from .utils import scrub_secret, utc_now_iso


@dataclass(frozen=True)
class LocalMirror:
    repo: RepoInfo
    path: Path
    downloaded_at: str
    privacy_known: bool = True


class MirrorRunner:
    def __init__(self, cfg: AppConfig, ui: UI):
        self.cfg = cfg
        self.ui = ui
        self.source = SourceDiscovery(cfg, ui)
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
        if self.cfg.mode == "remote":
            return self._run_remote_mirror()
        if self.cfg.mode == "watching":
            return self._run_watching()

        repos = self.discover()
        self.ui.info(f"Discovered {len(repos)} source repositories")
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
        if self.cfg.mode == "local":
            self.ui.success("Completed local mirror workflow")
        else:
            self.ui.success("Completed all repository workflows")
        return 0

    def _run_remote_mirror(self) -> int:
        mirrors = self._local_mirrors()
        self.ui.info(f"Loaded {len(mirrors)} local mirrors")
        if not mirrors:
            self.ui.error(
                f"No local mirrors found in state or under {self.cfg.backup.local_dir}. "
                "Run local-mirror first or set backup.local_dir to the mirror directory."
            )
            return 1

        failures = 0
        for mirror in mirrors:
            if not self._process_local_mirror(mirror):
                failures += 1
        if failures:
            self.ui.warning(f"Completed with {failures} local mirror push failure(s)")
            return 1
        self.ui.success("Completed remote mirror workflow")
        return 0

    def _run_watching(self) -> int:
        enabled_sources = [source for source in self.source.sources if source.source.watch]
        if not enabled_sources:
            self.ui.error("Watching mode has no enabled sources")
            return 1

        self.ui.info(
            f"Starting watching workflow for {len(enabled_sources)} source(s); "
            f"default interval is {self.cfg.watch.interval_seconds}s"
        )
        next_poll = {source.key: 0.0 for source in enabled_sources}
        failures = 0
        try:
            while True:
                now = time.monotonic()
                polled = False
                for source in enabled_sources:
                    if now < next_poll[source.key]:
                        continue
                    polled = True
                    failures += self._watch_source(source)
                    next_poll[source.key] = time.monotonic() + _source_watch_interval(
                        source.source.watch_interval_seconds,
                        self.cfg.watch.interval_seconds,
                    )
                if self.cfg.watch.once:
                    return 1 if failures else 0
                sleep_for = _watch_sleep_seconds(next_poll)
                if polled:
                    self.ui.debug(f"Watching idle for {sleep_for:.1f}s")
                time.sleep(sleep_for)
        except KeyboardInterrupt:
            self.ui.warning("Watching workflow stopped by keyboard interrupt")
            return 130

    def _watch_source(self, source) -> int:
        action = source.source.watch_action or self.cfg.watch.action
        interval = _source_watch_interval(source.source.watch_interval_seconds, self.cfg.watch.interval_seconds)
        self.ui.info(f"Polling {source.key}; action={action}, interval={interval}s")
        failures = 0
        discovery_errors_before = len(self.source.discovery_errors)
        repos = self.source.discover_one(source)
        if len(self.source.discovery_errors) > discovery_errors_before:
            failures += 1
        for repo in repos:
            should_process, reason, fingerprint = self._watch_decision(repo)
            if not should_process:
                continue
            self.ui.info(f"Watching detected {reason} for {repo.full_name}; running {action} workflow")
            ok = self._process_watched_repo(repo, action)
            if ok:
                self.state.mark_watch(
                    repo.key,
                    "processed",
                    fingerprint=fingerprint,
                    source_updated_at=repo.updated_at,
                    action=action,
                    reason=reason,
                    last_processed_at=utc_now_iso(),
                )
            else:
                failures += 1
                self.state.mark_watch(
                    repo.key,
                    "failed",
                    pending_fingerprint=fingerprint,
                    source_updated_at=repo.updated_at,
                    action=action,
                    reason=reason,
                )
        return failures

    def _watch_decision(self, repo: RepoInfo) -> tuple[bool, str, str]:
        fingerprint = _watch_fingerprint(repo)
        entry = self.state.repo(repo.key)
        watch = entry.get("watch", {})
        previous = watch.get("fingerprint")
        if not previous:
            if self.cfg.watch.initial_run:
                return True, "first-seen repository", fingerprint
            self.state.mark_watch(
                repo.key,
                "seen",
                fingerprint=fingerprint,
                source_updated_at=repo.updated_at,
                last_seen_at=utc_now_iso(),
                action="none",
                reason="initial-run-disabled",
            )
            return False, "unchanged", fingerprint
        if previous != fingerprint:
            return True, "source update", fingerprint
        self.state.mark_watch(
            repo.key,
            "unchanged",
            fingerprint=fingerprint,
            source_updated_at=repo.updated_at,
            last_seen_at=utc_now_iso(),
        )
        return False, "unchanged", fingerprint

    def _process_watched_repo(self, repo: RepoInfo, action: str) -> bool:
        if action in {"full", "local"}:
            return self._process_repo(repo, force_workflow=True, workflow_mode=action)
        mirror_path = self.git.mirror_path(repo)
        if not mirror_path.exists():
            self.ui.error(f"Remote watch action needs an existing local mirror for {repo.full_name}: {mirror_path}")
            return False
        mirror = LocalMirror(repo=repo, path=mirror_path, downloaded_at=utc_now_iso())
        return self._process_local_mirror(mirror, force_workflow=True)

    def write_discovery_json(self, path: Path | None = None) -> list[RepoInfo]:
        repos = self.discover()
        payload = [
            {
                "full_name": repo.full_name,
                "source_platform": repo.source_platform,
                "private": repo.private,
                "visibility": repo.visibility,
                "clone_url": repo.clone_url,
                "ssh_url": repo.ssh_url,
                "default_branch": repo.default_branch,
                "web_url": repo.web_url,
                "updated_at": repo.updated_at,
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

    def _process_repo(
        self,
        repo: RepoInfo,
        force_workflow: bool = False,
        workflow_mode: str | None = None,
    ) -> bool:
        workflow_mode = workflow_mode or self.cfg.mode
        key = repo.key
        self.state.mark_repo_metadata(
            key,
            source_url=repo.web_url,
            full_name=repo.full_name,
            private=repo.private,
            default_branch=repo.default_branch,
            visibility=repo.visibility,
            source_updated_at=repo.updated_at,
        )
        mirror_path = self.git.mirror_path(repo)
        downloaded_at = utc_now_iso()
        branch = repo.default_branch or "main"

        try:
            if self._should_skip_step(key, "clone", force_workflow) and mirror_path.exists():
                self.ui.info(f"Skipping clone for {repo.full_name}; state already marks it done")
                clone_step = self.state.repo(key).get("steps", {}).get("clone", {})
                downloaded_at = clone_step.get("downloaded_at", downloaded_at)
            else:
                token = self.source.current_token(repo)
                mirror_path, downloaded_at = self.git.clone_or_update(repo, token)
                self._mark_step(key, "clone", "done", path=str(mirror_path), downloaded_at=downloaded_at)
        except Exception as exc:
            self._mark_step(key, "clone", "failed", error=str(exc))
            self.ui.error(f"Clone/update failed for {repo.full_name}: {exc}")
            return False

        if workflow_mode == "local":
            self.ui.info(f"Local mirror mode: skipping marker and destinations for {repo.full_name}")
            return True

        return self._finish_repo_workflow(repo, mirror_path, downloaded_at, branch, force_workflow)

    def _process_local_mirror(self, mirror: LocalMirror, force_workflow: bool = False) -> bool:
        repo = mirror.repo
        key = repo.key
        mirror_path = mirror.path
        branch = repo.default_branch or "main"
        self.state.mark_repo_metadata(
            key,
            source_url=repo.web_url,
            full_name=repo.full_name,
            private=repo.private,
            default_branch=repo.default_branch,
            visibility=repo.visibility,
            source_updated_at=repo.updated_at,
            privacy_known=mirror.privacy_known,
        )
        if not self.state.is_done(key, "clone"):
            self._mark_step(key, "clone", "done", path=str(mirror_path), downloaded_at=mirror.downloaded_at)
        if not mirror_path.exists():
            self._mark_step(key, "remote-mirror", "failed", error=f"Local mirror does not exist: {mirror_path}")
            self.ui.error(f"Local mirror does not exist for {repo.full_name}: {mirror_path}")
            return False
        if not mirror.privacy_known:
            self.ui.warning(
                f"Privacy is unknown for scanned local mirror {repo.full_name}; treating it as private"
            )
        return self._finish_repo_workflow(repo, mirror_path, mirror.downloaded_at, branch, force_workflow)

    def _finish_repo_workflow(
        self,
        repo: RepoInfo,
        mirror_path: Path,
        downloaded_at: str,
        branch: str,
        force_workflow: bool = False,
    ) -> bool:
        key = repo.key
        try:
            if self._should_skip_step(key, "marker", force_workflow):
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
            if not self._process_destination(repo, mirror_path, branch, destination, force_workflow):
                destination_failures += 1
        return destination_failures == 0

    def _local_mirrors(self) -> list[LocalMirror]:
        mirrors_by_key: dict[str, LocalMirror] = {}
        for mirror in self._local_mirrors_from_state():
            mirrors_by_key[mirror.repo.key] = mirror
        for mirror in self._local_mirrors_from_disk():
            mirrors_by_key.setdefault(mirror.repo.key, mirror)
        return sorted(mirrors_by_key.values(), key=lambda item: item.repo.full_name.lower())

    def _local_mirrors_from_state(self) -> list[LocalMirror]:
        mirrors: list[LocalMirror] = []
        for key, entry in self.state.data.get("repos", {}).items():
            clone_step = entry.get("steps", {}).get("clone", {})
            if clone_step.get("status") != "done":
                continue
            full_name = str(entry.get("full_name") or _full_name_from_key(key))
            owner, name = _split_full_name(full_name)
            source_platform = key.split(":", 1)[0] if ":" in key else "github"
            repo = RepoInfo(
                source_platform=source_platform,
                owner=owner,
                name=name,
                full_name=full_name,
                web_url=str(entry.get("source_url") or _default_web_url(source_platform, full_name)),
                clone_url="",
                ssh_url=None,
                default_branch=entry.get("default_branch") or None,
                private=bool(entry.get("private", False)),
                visibility=entry.get("visibility") or None,
                updated_at=entry.get("source_updated_at") or None,
            )
            path = Path(str(clone_step.get("path") or self.git.mirror_path(repo)))
            downloaded_at = str(clone_step.get("downloaded_at") or entry.get("updated_at") or utc_now_iso())
            mirrors.append(LocalMirror(repo=repo, path=path, downloaded_at=downloaded_at))
        return mirrors

    def _local_mirrors_from_disk(self) -> list[LocalMirror]:
        base = self.cfg.backup.local_dir
        if not base.exists():
            return []
        mirrors: list[LocalMirror] = []
        for source_dir in sorted(path for path in base.iterdir() if path.is_dir()):
            for owner_dir in sorted(path for path in source_dir.iterdir() if path.is_dir()):
                for mirror_path in sorted(owner_dir.glob("*.git")):
                    if not _looks_like_local_mirror(mirror_path):
                        continue
                    source = source_dir.name
                    owner = owner_dir.name
                    name = mirror_path.name.removesuffix(".git")
                    full_name = f"{owner}/{name}"
                    repo = RepoInfo(
                        source_platform=source,
                        owner=owner,
                        name=name,
                        full_name=full_name,
                        web_url=_default_web_url(source, full_name),
                        clone_url="",
                        ssh_url=None,
                        default_branch=_default_branch_from_head(mirror_path),
                        private=True,
                        visibility="private",
                        updated_at=None,
                    )
                    mirrors.append(
                        LocalMirror(
                            repo=repo,
                            path=mirror_path,
                            downloaded_at=utc_now_iso(),
                            privacy_known=False,
                        )
                    )
        return mirrors

    def _process_destination(
        self,
        repo: RepoInfo,
        mirror_path: Path,
        branch: str,
        destination: DestinationAdapter,
        force_workflow: bool = False,
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
            if self._should_skip_destination(key, dest_key, "push", force_workflow):
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

    def _should_skip_step(self, key: str, step: str, force_workflow: bool = False) -> bool:
        return self.cfg.resume and not self.cfg.force and not force_workflow and self.state.is_done(key, step)

    def _should_skip_destination(
        self,
        key: str,
        destination_key: str,
        step: str,
        force_workflow: bool = False,
    ) -> bool:
        return (
            self.cfg.resume
            and not self.cfg.force
            and not force_workflow
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


def _watch_fingerprint(repo: RepoInfo) -> str:
    payload = {
        "clone_url": repo.clone_url,
        "default_branch": repo.default_branch,
        "private": repo.private,
        "ssh_url": repo.ssh_url,
        "updated_at": repo.updated_at,
        "visibility": repo.visibility,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _source_watch_interval(source_interval: int | None, default_interval: int) -> int:
    return max(1, int(source_interval or default_interval))


def _watch_sleep_seconds(next_poll: dict[str, float]) -> float:
    if not next_poll:
        return 1.0
    return max(1.0, min(next_poll.values()) - time.monotonic())


def _full_name_from_key(key: str) -> str:
    return key.split(":", 1)[1] if ":" in key else key


def _split_full_name(full_name: str) -> tuple[str, str]:
    owner, _, name = full_name.rpartition("/")
    if not owner or not name:
        raise ValueError(f"Invalid repository full name in state: {full_name}")
    return owner, name


def _default_web_url(source_platform: str, full_name: str) -> str:
    if source_platform == "github":
        return f"https://github.com/{full_name}"
    if source_platform == "gitlab":
        return f"https://gitlab.com/{full_name}"
    if source_platform in {"forgejo", "codeberg", "gitea"}:
        return f"https://codeberg.org/{full_name}"
    if source_platform == "bitbucket":
        return f"https://bitbucket.org/{full_name}"
    if source_platform == "sourcehut":
        owner, _, name = full_name.rpartition("/")
        return f"https://git.sr.ht/~{owner}/{name}" if owner and name else full_name
    return full_name


def _looks_like_local_mirror(path: Path) -> bool:
    return path.is_dir() and (path / "HEAD").is_file()


def _default_branch_from_head(path: Path) -> str | None:
    try:
        text = (path / "HEAD").read_text(encoding="utf-8").strip()
    except OSError:
        return None
    prefix = "ref: refs/heads/"
    if text.startswith(prefix):
        return text.removeprefix(prefix)
    return None
