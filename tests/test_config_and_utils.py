from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from anti_gh_ms_hysteria.config import (
    config_from_dict,
    destination_from_url,
    parse_cli_token,
    parse_destination_token,
)
from anti_gh_ms_hysteria.destinations.gitlab import GitLabDestination
from anti_gh_ms_hysteria.destinations.gitlab import gitlab_safe_project_path
from anti_gh_ms_hysteria.git_ops import GitMirrorManager, build_git_ssh_command, git_failure_hint
from anti_gh_ms_hysteria.models import (
    AppConfig,
    BackupConfig,
    DestinationConfig,
    GitConfig,
    GitHubConfig,
    RepoInfo,
    TokenCredential,
)
from anti_gh_ms_hysteria.runner import MirrorRunner
from anti_gh_ms_hysteria.state import StateStore
from anti_gh_ms_hysteria.utils import infer_platform, parse_owner_from_profile_url


class DummyUI:
    verbose = 0

    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def info(self, message: str) -> None:
        self.messages.append(("info", message))

    def warning(self, message: str) -> None:
        self.messages.append(("warning", message))

    def error(self, message: str) -> None:
        self.messages.append(("error", message))

    def debug(self, message: str) -> None:
        self.messages.append(("debug", message))

    def success(self, message: str) -> None:
        self.messages.append(("success", message))


class RecordingGitRunner:
    def __init__(self) -> None:
        self.commands: list[tuple[list[str], bool]] = []

    def run(self, args, cwd=None, check=True, extra_env=None):
        self.commands.append((args, check))
        return subprocess.CompletedProcess(args, 0, "", "")


def repo_info(name: str = "repo") -> RepoInfo:
    return RepoInfo(
        source_platform="github",
        owner="owner",
        name=name,
        full_name=f"owner/{name}",
        web_url=f"https://github.com/owner/{name}",
        clone_url=f"https://github.com/owner/{name}.git",
        ssh_url=f"git@github.com:owner/{name}.git",
        default_branch="main",
        private=False,
    )


class UrlParsingTests(unittest.TestCase):
    def test_infers_known_platforms(self) -> None:
        self.assertEqual(infer_platform("https://github.com/extencil/"), "github")
        self.assertEqual(infer_platform("https://gitlab.com/extencil"), "gitlab")
        self.assertEqual(infer_platform("https://codeberg.org/extencil"), "forgejo")
        self.assertEqual(infer_platform("https://bitbucket.org/extencil"), "bitbucket")
        self.assertEqual(infer_platform("https://git.sr.ht/~extencil"), "sourcehut")

    def test_parses_owner(self) -> None:
        host, owner, parts = parse_owner_from_profile_url("https://git.sr.ht/~extencil")
        self.assertEqual(host, "git.sr.ht")
        self.assertEqual(owner, "extencil")
        self.assertEqual(parts, ["~extencil"])

    def test_gitlab_nested_namespace_is_preserved(self) -> None:
        dest = destination_from_url("https://gitlab.com/group/subgroup")
        self.assertEqual(dest.platform, "gitlab")
        self.assertEqual(dest.owner, "group/subgroup")


class TokenParsingTests(unittest.TestCase):
    def test_env_token(self) -> None:
        os.environ["AGHM_TEST_TOKEN"] = "secret"
        token = parse_cli_token("env:AGHM_TEST_TOKEN")
        self.assertEqual(token.secret, "secret")
        self.assertEqual(token.name, "AGHM_TEST_TOKEN")

    def test_username_token(self) -> None:
        platform, token = parse_destination_token("bitbucket:you@example.com:secret")
        self.assertEqual(platform, "bitbucket")
        self.assertEqual(token.username, "you@example.com")
        self.assertEqual(token.secret, "secret")


class ConfigTests(unittest.TestCase):
    def test_config_from_dict_resolves_paths_and_tokens(self) -> None:
        os.environ["AGHM_GH"] = "gh-secret"
        with tempfile.TemporaryDirectory() as tmp:
            cfg = config_from_dict(
                {
                    "workspace": ".state",
                    "insecure_tls": True,
                    "github": {
                        "profiles": ["https://github.com/extencil"],
                        "tokens": [{"env": "AGHM_GH", "name": "test"}],
                    },
                    "destinations": [{"url": "https://codeberg.org/extencil"}],
                },
                Path(tmp),
            )
        self.assertEqual(cfg.workspace.name, ".state")
        self.assertTrue(cfg.insecure_tls)
        self.assertEqual(cfg.github.tokens[0].secret, "gh-secret")
        self.assertEqual(cfg.destinations[0].platform, "forgejo")

    def test_config_expands_user_paths(self) -> None:
        cfg = config_from_dict({"workspace": "~/agmh-state"}, Path.cwd())
        self.assertEqual(cfg.workspace, Path.home() / "agmh-state")

    def test_marker_filename_must_not_escape_repo_root(self) -> None:
        with self.assertRaises(ValueError):
            config_from_dict({"backup": {"marker_filename": "../evil.txt"}}, Path.cwd())


class StateTests(unittest.TestCase):
    def test_state_persists_steps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            state = StateStore(path)
            state.mark_step("github:owner/repo", "clone", "done", path="repo.git")
            loaded = StateStore(path)
            self.assertTrue(loaded.is_done("github:owner/repo", "clone"))
            self.assertEqual(
                loaded.repo("github:owner/repo")["steps"]["clone"]["path"],
                "repo.git",
            )


class GitSshTests(unittest.TestCase):
    def test_builds_git_ssh_command_from_identity_file(self) -> None:
        cfg = AppConfig(
            git=GitConfig(
                ssh_identity_file=Path("/home/user/.ssh/sourcehut_ed25519"),
                ssh_strict_host_key_checking="accept-new",
            )
        )
        command = build_git_ssh_command(cfg)
        self.assertIsNotNone(command)
        self.assertTrue(command.startswith("ssh -i "))
        self.assertIn("sourcehut_ed25519", command)
        self.assertIn("-o IdentitiesOnly=yes", command)
        self.assertIn("-o StrictHostKeyChecking=accept-new", command)

    def test_ssh_permission_denied_hint(self) -> None:
        hint = git_failure_hint("git@git.sr.ht: Permission denied (publickey,keyboard-interactive).")
        self.assertIsNotNone(hint)
        self.assertIn("--ssh-key", hint or "")


class GitMirrorTests(unittest.TestCase):
    def test_lfs_fetch_runs_before_origin_url_is_scrubbed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = AppConfig(
                backup=BackupConfig(
                    local_dir=Path(tmp) / "backups",
                    lfs=True,
                )
            )
            runner = RecordingGitRunner()
            manager = GitMirrorManager(cfg, DummyUI(), runner)
            repo = repo_info()
            mirror_path = manager.mirror_path(repo)
            mirror_path.mkdir(parents=True)

            manager.clone_or_update(repo, TokenCredential("secret", name="github"))

        self.assertEqual(runner.commands[0][0][3:6], ["remote", "set-url", "origin"])
        self.assertIn("x-access-token", runner.commands[0][0][-1])
        self.assertEqual(runner.commands[2][0][3:], ["lfs", "fetch", "--all"])
        self.assertEqual(runner.commands[3][0][3:6], ["remote", "set-url", "origin"])
        self.assertEqual(runner.commands[3][0][-1], repo.clone_url)


class DestinationMappingTests(unittest.TestCase):
    def test_destination_default_push_url_accepts_url_without_scheme(self) -> None:
        destination = GitLabDestination(
            DestinationConfig(url="gitlab.com/group", platform="gitlab", owner="group"),
            AppConfig(),
            DummyUI(),
        )
        self.assertEqual(
            destination.default_push_url(repo_info()),
            "https://gitlab.com/group/repo.git",
        )

    def test_gitlab_hidden_repo_name_gets_legal_path(self) -> None:
        self.assertEqual(gitlab_safe_project_path(".github"), "dot-github")

    def test_gitlab_reserved_suffix_gets_legal_path(self) -> None:
        self.assertEqual(gitlab_safe_project_path("repo.git"), "repo")

    def test_hidden_ref_hint(self) -> None:
        hint = git_failure_hint("! [remote rejected] refs/pull/1/head (deny updating a hidden ref)")
        self.assertIsNotNone(hint)
        self.assertIn("portable-mirror", hint or "")


class RunnerTests(unittest.TestCase):
    def test_run_fails_when_source_discovery_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = AppConfig(
                workspace=Path(tmp) / ".aghm",
                github=GitHubConfig(profiles=["https://gitlab.com/not-github"]),
            )
            result = MirrorRunner(cfg, DummyUI()).run()
        self.assertEqual(result, 1)


if __name__ == "__main__":
    unittest.main()
