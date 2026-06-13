from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from pathlib import Path
from urllib.parse import quote, urlparse, urlunparse

from .models import AppConfig, RepoInfo, TokenCredential
from .ui import UI
from .utils import ensure_within, safe_path_part, scrub_secret, utc_now_iso


class GitCommandError(RuntimeError):
    def __init__(
        self,
        command: list[str],
        returncode: int,
        stdout: str,
        stderr: str,
        command_display: str | None = None,
    ):
        super().__init__(f"git command failed with exit code {returncode}: {command_display or ' '.join(command)}")
        self.command = command
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.command_display = command_display or " ".join(command)


class GitRunner:
    def __init__(self, cfg: AppConfig, ui: UI, secrets: list[str]):
        self.cfg = cfg
        self.ui = ui
        self.secrets = secrets

    def run(
        self,
        args: list[str],
        cwd: Path | None = None,
        check: bool = True,
        extra_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        if self.cfg.proxy:
            env["HTTP_PROXY"] = self.cfg.proxy
            env["HTTPS_PROXY"] = self.cfg.proxy
        if self.cfg.insecure_tls:
            env["GIT_SSL_NO_VERIFY"] = "true"
        git_ssh_command = build_git_ssh_command(self.cfg)
        if git_ssh_command:
            env["GIT_SSH_COMMAND"] = git_ssh_command
            self.ui.debug(f"GIT_SSH_COMMAND={git_ssh_command}")
        if extra_env:
            env.update(extra_env)

        printable = scrub_secret(" ".join(args), self.secrets)
        self.ui.debug(f"Running: {printable}")
        if self.cfg.dry_run:
            self.ui.info(f"DRY-RUN git: {printable}")
            return subprocess.CompletedProcess(args, 0, "", "")

        proc = subprocess.run(
            args,
            cwd=str(cwd) if cwd else None,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if proc.stdout:
            self.ui.debug(scrub_secret(proc.stdout.strip(), self.secrets))
        if proc.stderr:
            self.ui.debug(scrub_secret(proc.stderr.strip(), self.secrets))
        if check and proc.returncode != 0:
            stderr = scrub_secret(proc.stderr, self.secrets)
            hint = git_failure_hint(stderr)
            if hint:
                stderr = f"{stderr.rstrip()}\n\n{hint}\n"
            raise GitCommandError(
                args,
                proc.returncode,
                scrub_secret(proc.stdout, self.secrets),
                stderr,
                command_display=printable,
            )
        return proc


class GitMirrorManager:
    def __init__(self, cfg: AppConfig, ui: UI, runner: GitRunner):
        self.cfg = cfg
        self.ui = ui
        self.runner = runner

    def mirror_path(self, repo: RepoInfo) -> Path:
        return (
            self.cfg.backup.local_dir
            / safe_path_part(repo.source_platform)
            / safe_path_part(repo.owner)
            / f"{safe_path_part(repo.name)}.git"
        )

    def clone_or_update(self, repo: RepoInfo, token: TokenCredential | None) -> tuple[Path, str]:
        mirror_path = self.mirror_path(repo)
        mirror_path.parent.mkdir(parents=True, exist_ok=True)
        downloaded_at = utc_now_iso()
        remote_url = self._source_clone_url(repo, token)
        clean_url = self._clean_source_clone_url(repo)

        try:
            if mirror_path.exists():
                self.ui.info(f"Updating local mirror for {repo.full_name}")
                self.runner.run(["git", "-C", str(mirror_path), "remote", "set-url", "origin", remote_url])
                self.runner.run(["git", "-C", str(mirror_path), "remote", "update", "--prune"])
            else:
                self.ui.info(f"Cloning local mirror for {repo.full_name}")
                self.runner.run(["git", "clone", "--mirror", remote_url, str(mirror_path)])
            if self.cfg.backup.lfs:
                self.runner.run(["git", "-C", str(mirror_path), "lfs", "fetch", "--all"], check=False)
        finally:
            if mirror_path.exists():
                self.runner.run(
                    ["git", "-C", str(mirror_path), "remote", "set-url", "origin", clean_url],
                    check=False,
                )

        return mirror_path, downloaded_at

    def ensure_marker_commit(self, repo: RepoInfo, mirror_path: Path, downloaded_at: str) -> str:
        branch = repo.default_branch or "main"
        if self.cfg.dry_run:
            self.ui.info(
                f"DRY-RUN marker: would create {self.cfg.backup.marker_filename} on {repo.full_name}:{branch}"
            )
            return branch

        tmp_root = self.cfg.workspace / "tmp"
        workdir = tmp_root / f"{safe_path_part(repo.owner)}-{safe_path_part(repo.name)}"
        ensure_within(tmp_root, workdir)
        if workdir.exists():
            shutil.rmtree(workdir)
        tmp_root.mkdir(parents=True, exist_ok=True)

        self.ui.info(f"Ensuring marker file on {repo.full_name}:{branch}")
        self.runner.run(["git", "clone", str(mirror_path), str(workdir)])

        has_default = (
            self.runner.run(
                ["git", "-C", str(workdir), "rev-parse", "--verify", f"origin/{branch}"],
                check=False,
            ).returncode
            == 0
        )
        if has_default:
            self.runner.run(["git", "-C", str(workdir), "checkout", "-B", branch, f"origin/{branch}"])
        else:
            self.runner.run(["git", "-C", str(workdir), "checkout", "--orphan", branch])

        marker_path = workdir / self.cfg.backup.marker_filename
        ensure_within(workdir, marker_path)
        if not marker_path.exists():
            marker_created_at = utc_now_iso()
            marker_path.write_text(
                "\n".join(
                    [
                        f"source_url={repo.web_url}",
                        f"downloaded_at={downloaded_at}",
                        f"marker_created_at={marker_created_at}",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            self.runner.run(["git", "-C", str(workdir), "add", self.cfg.backup.marker_filename])
            status = self.runner.run(["git", "-C", str(workdir), "status", "--porcelain"]).stdout.strip()
            if status:
                self.runner.run(
                    [
                        "git",
                        "-C",
                        str(workdir),
                        "-c",
                        f"user.name={self.cfg.git.author_name}",
                        "-c",
                        f"user.email={self.cfg.git.author_email}",
                        "commit",
                        "-m",
                        self.cfg.git.commit_message,
                    ]
                )
                self.runner.run(["git", "-C", str(workdir), "push", "origin", f"HEAD:refs/heads/{branch}"])
        else:
            self.ui.info(f"Marker file already exists for {repo.full_name}; leaving it unchanged")

        if not self.cfg.dry_run:
            shutil.rmtree(workdir)
        return branch

    def push(self, mirror_path: Path, push_url: str, push_mode: str, default_branch: str | None) -> None:
        if push_mode == "all":
            self.runner.run(["git", "-C", str(mirror_path), "push", "--all", push_url])
            self.runner.run(["git", "-C", str(mirror_path), "push", "--tags", push_url])
        elif push_mode == "default":
            branch = default_branch or "main"
            self.runner.run(
                ["git", "-C", str(mirror_path), "push", push_url, f"refs/heads/{branch}:refs/heads/{branch}"]
            )
        elif push_mode == "portable-mirror":
            self.runner.run(
                [
                    "git",
                    "-C",
                    str(mirror_path),
                    "push",
                    "--prune",
                    push_url,
                    "+refs/heads/*:refs/heads/*",
                ]
            )
            self.runner.run(["git", "-C", str(mirror_path), "push", "--tags", push_url])
        else:
            self.runner.run(["git", "-C", str(mirror_path), "push", "--mirror", push_url])

    def _source_clone_url(self, repo: RepoInfo, token: TokenCredential | None) -> str:
        if self.cfg.backup.clone_protocol == "ssh" and repo.ssh_url:
            return repo.ssh_url
        if token and repo.clone_url.startswith("https://"):
            return with_basic_auth(repo.clone_url, source_auth_username(repo, token), token.secret)
        return repo.clone_url

    def _clean_source_clone_url(self, repo: RepoInfo) -> str:
        if self.cfg.backup.clone_protocol == "ssh" and repo.ssh_url:
            return repo.ssh_url
        return repo.clone_url


def with_basic_auth(url: str, username: str, secret: str) -> str:
    parsed = urlparse(url)
    username_q = quote(username, safe="")
    secret_q = quote(secret, safe="")
    netloc = f"{username_q}:{secret_q}@{parsed.netloc}"
    return urlunparse((parsed.scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))


def source_auth_username(repo: RepoInfo, token: TokenCredential) -> str:
    if token.username:
        return token.username
    if repo.source_platform == "github":
        return "x-access-token"
    if repo.source_platform in {"gitlab", "sourcehut"}:
        return "oauth2"
    if repo.source_platform == "bitbucket":
        return "x-token-auth"
    return repo.owner


def build_git_ssh_command(cfg: AppConfig) -> str | None:
    if cfg.git.ssh_command:
        return cfg.git.ssh_command

    has_ssh_settings = any(
        [
            cfg.git.ssh_identity_file,
            cfg.git.ssh_batch_mode,
            cfg.git.ssh_strict_host_key_checking,
        ]
    )
    if not has_ssh_settings:
        return None

    parts = ["ssh"]
    if cfg.git.ssh_identity_file:
        parts.extend(["-i", str(cfg.git.ssh_identity_file)])
        if cfg.git.ssh_identities_only:
            parts.extend(["-o", "IdentitiesOnly=yes"])
    if cfg.git.ssh_batch_mode:
        parts.extend(["-o", "BatchMode=yes"])
    if cfg.git.ssh_strict_host_key_checking:
        parts.extend(["-o", f"StrictHostKeyChecking={cfg.git.ssh_strict_host_key_checking}"])
    return shlex.join(parts)


def git_failure_hint(stderr: str) -> str | None:
    text = stderr.lower()
    if "permission denied (publickey" in text:
        return (
            "SSH authentication failed. If this destination needs a non-default key, set "
            "[git].ssh_identity_file in the config or pass --ssh-key. Verify the same command "
            "as the same user without sudo: ssh -T -i <key> git@git.sr.ht. If the key is under "
            "/mnt/c and SSH reports permissive permissions, copy it to ~/.ssh and chmod it to 600."
        )
    if "unprotected private key file" in text or "bad permissions" in text:
        return (
            "SSH rejected the private key permissions. Put the private key on a Linux filesystem, "
            "for example ~/.ssh/sourcehut_ed25519, then run chmod 700 ~/.ssh and chmod 600 on the key."
        )
    if "deny updating a hidden ref" in text or "refs/pull/" in text:
        return (
            "The destination rejected GitHub pull-request refs. Use portable-mirror push mode for this "
            "destination so only branches and tags are mirrored."
        )
    return None
