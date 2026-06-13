from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from anti_gh_ms_hysteria.config import (
    ConfigError,
    config_from_dict,
    destination_from_url,
    load_config,
    parse_cli_token,
    parse_destination_token,
)
from anti_gh_ms_hysteria.cli import build_config_from_args, build_parser
from anti_gh_ms_hysteria.destinations import build_destination
from anti_gh_ms_hysteria.destinations.github import GitHubDestination
from anti_gh_ms_hysteria.destinations.gitlab import GitLabDestination
from anti_gh_ms_hysteria.destinations.gitlab import gitlab_safe_project_path
from anti_gh_ms_hysteria.git_ops import GitMirrorManager, build_git_ssh_command, git_failure_hint
from anti_gh_ms_hysteria.http import JsonResponse
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


class LocalOnlyGit:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.clone_calls = 0
        self.marker_calls = 0

    def mirror_path(self, repo: RepoInfo) -> Path:
        return self.root / "backups" / repo.source_platform / repo.owner / f"{repo.name}.git"

    def clone_or_update(self, repo: RepoInfo, token: TokenCredential | None) -> tuple[Path, str]:
        self.clone_calls += 1
        path = self.mirror_path(repo)
        path.mkdir(parents=True)
        return path, "2026-06-13T00:00:00Z"

    def ensure_marker_commit(self, repo: RepoInfo, mirror_path: Path, downloaded_at: str) -> str:
        self.marker_calls += 1
        raise AssertionError("local mode must not create marker commits")


class FakeGitHubClient:
    def __init__(self, login: str) -> None:
        self.login = login
        self.requests: list[tuple[str, str, dict | None]] = []

    def request_json(self, method: str, path: str, body=None, **kwargs):
        self.requests.append((method, path, body))
        if method == "GET" and path == "/user":
            return JsonResponse({"login": self.login}, {}, 200)
        return JsonResponse(
            {
                "html_url": "https://github.com/dest/repo",
                "clone_url": "https://github.com/dest/repo.git",
            },
            {},
            201,
        )


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

    def test_github_destination_url_is_supported(self) -> None:
        dest = destination_from_url("https://github.com/destination-owner")
        self.assertEqual(dest.platform, "github")
        self.assertEqual(dest.owner, "destination-owner")


class TokenParsingTests(unittest.TestCase):
    def test_env_token(self) -> None:
        os.environ["AGMH_TEST_TOKEN"] = "secret"
        token = parse_cli_token("env:AGMH_TEST_TOKEN")
        self.assertEqual(token.secret, "secret")
        self.assertEqual(token.name, "AGMH_TEST_TOKEN")

    def test_username_token(self) -> None:
        platform, token = parse_destination_token("bitbucket:you@example.com:secret")
        self.assertEqual(platform, "bitbucket")
        self.assertEqual(token.username, "you@example.com")
        self.assertEqual(token.secret, "secret")


class ConfigTests(unittest.TestCase):
    def test_default_generated_names_use_agmh(self) -> None:
        cfg = config_from_dict({}, Path.cwd())
        self.assertEqual(cfg.workspace, Path(".agmh"))
        self.assertEqual(cfg.backup.marker_filename, "agmh.txt")
        self.assertEqual(cfg.git.author_name, "agmh")
        self.assertEqual(cfg.git.author_email, "agmh@localhost")

    def test_init_config_default_path_uses_agmh(self) -> None:
        args = build_parser().parse_args(["init-config"])
        self.assertEqual(args.path, Path("agmh.config.toml"))

    def test_config_from_dict_resolves_paths_and_tokens(self) -> None:
        os.environ["AGMH_GH"] = "gh-secret"
        with tempfile.TemporaryDirectory() as tmp:
            cfg = config_from_dict(
                {
                    "workspace": ".state",
                    "insecure_tls": True,
                    "github": {
                        "profiles": ["https://github.com/extencil"],
                        "tokens": [{"env": "AGMH_GH", "name": "test"}],
                    },
                    "destinations": [{"url": "https://codeberg.org/extencil"}],
                },
                Path(tmp),
            )
        self.assertEqual(cfg.workspace.name, ".state")
        self.assertTrue(cfg.insecure_tls)
        self.assertEqual(cfg.github.tokens[0].secret, "gh-secret")
        self.assertEqual(cfg.destinations[0].platform, "forgejo")

    def test_github_tokens_accept_named_table(self) -> None:
        os.environ["AGMH_GH_1"] = "gh-secret-1"
        os.environ["AGMH_GH_2"] = "gh-secret-2"
        cfg = config_from_dict(
            {
                "github": {
                    "tokens": {
                        "github-primary": {"env": "AGMH_GH_1"},
                        "github-secondary": "env:AGMH_GH_2",
                    }
                }
            },
            Path.cwd(),
        )
        self.assertEqual(
            [token.name for token in cfg.github.tokens],
            ["github-primary", "github-secondary"],
        )
        self.assertEqual(
            [token.secret for token in cfg.github.tokens],
            ["gh-secret-1", "gh-secret-2"],
        )

    def test_invalid_toml_token_array_reports_helpful_config_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "agmh.config.toml"
            path.write_text(
                "\n".join(
                    [
                        "[github]",
                        "tokens = [",
                        '  { env = "GITHUB_TOKEN", name = "github-primary" }',
                        '  { env = "GITHUB_TOKEN_2", name = "github-secondary" }',
                        "]",
                    ]
                ),
                encoding="utf-8",
            )
            with self.assertRaises(ConfigError) as raised:
                load_config(path)
        message = str(raised.exception)
        self.assertIn("Invalid TOML", message)
        self.assertIn("github.tokens", message)
        self.assertIn("commas", message)

    def test_config_expands_user_paths(self) -> None:
        cfg = config_from_dict({"workspace": "~/agmh-state"}, Path.cwd())
        self.assertEqual(cfg.workspace, Path.home() / "agmh-state")

    def test_marker_filename_must_not_escape_repo_root(self) -> None:
        with self.assertRaises(ValueError):
            config_from_dict({"backup": {"marker_filename": "../evil.txt"}}, Path.cwd())

    def test_local_mode_does_not_require_destination_token_envs(self) -> None:
        os.environ.pop("AGMH_MISSING_DEST_TOKEN", None)
        cfg = config_from_dict(
            {
                "mode": "local",
                "destinations": [
                    {
                        "url": "https://gitlab.com/extencil",
                        "tokens": [{"env": "AGMH_MISSING_DEST_TOKEN"}],
                    }
                ],
            },
            Path.cwd(),
        )
        self.assertEqual(cfg.mode, "local")
        self.assertEqual(cfg.destinations, [])

    def test_remote_mode_does_not_require_github_token_envs(self) -> None:
        os.environ.pop("AGMH_MISSING_GITHUB_TOKEN", None)
        cfg = config_from_dict(
            {
                "mode": "remote",
                "github": {"tokens": [{"env": "AGMH_MISSING_GITHUB_TOKEN"}]},
            },
            Path.cwd(),
        )
        self.assertEqual(cfg.mode, "remote")
        self.assertEqual(cfg.github.tokens, [])


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

    def test_builds_github_destination(self) -> None:
        destination = build_destination(
            DestinationConfig(url="https://github.com/dest", platform="github", owner="dest"),
            AppConfig(),
            DummyUI(),
        )
        self.assertIsInstance(destination, GitHubDestination)

    def test_github_destination_push_url_and_auth(self) -> None:
        destination = GitHubDestination(
            DestinationConfig(
                url="https://github.com/dest",
                platform="github",
                owner="dest",
                tokens=[TokenCredential("secret")],
            ),
            AppConfig(),
            DummyUI(),
        )
        self.assertEqual(destination.default_push_url(repo_info()), "https://github.com/dest/repo.git")
        self.assertEqual(
            destination.push_urls(repo_info()),
            ["https://x-access-token:secret@github.com/dest/repo.git"],
        )
        self.assertEqual(destination.push_mode_for("mirror"), "portable-mirror")
        self.assertEqual(destination.push_mode_for("default"), "default")

    def test_github_destination_creates_user_repo(self) -> None:
        destination = GitHubDestination(
            DestinationConfig(url="https://github.com/dest", platform="github", owner="dest"),
            AppConfig(),
            DummyUI(),
        )
        fake_client = FakeGitHubClient("dest")
        destination.client = fake_client

        created = destination.create_repository(RepoInfo(**{**repo_info().__dict__, "private": True}))

        self.assertTrue(created.created)
        self.assertEqual(
            fake_client.requests[1],
            ("POST", "/user/repos", {"name": "repo", "private": True, "auto_init": False}),
        )

    def test_github_destination_creates_org_repo(self) -> None:
        destination = GitHubDestination(
            DestinationConfig(url="https://github.com/org", platform="github", owner="org", visibility="public"),
            AppConfig(),
            DummyUI(),
        )
        fake_client = FakeGitHubClient("user")
        destination.client = fake_client

        destination.create_repository(RepoInfo(**{**repo_info().__dict__, "private": True}))

        self.assertEqual(
            fake_client.requests[1],
            ("POST", "/orgs/org/repos", {"name": "repo", "private": False, "auto_init": False}),
        )

    def test_gitlab_hidden_repo_name_gets_legal_path(self) -> None:
        self.assertEqual(gitlab_safe_project_path(".github"), "dot-github")

    def test_gitlab_reserved_suffix_gets_legal_path(self) -> None:
        self.assertEqual(gitlab_safe_project_path("repo.git"), "repo")

    def test_hidden_ref_hint(self) -> None:
        hint = git_failure_hint("! [remote rejected] refs/pull/1/head (deny updating a hidden ref)")
        self.assertIsNotNone(hint)
        self.assertIn("portable-mirror", hint or "")

    def test_destination_visibility_override_semantics(self) -> None:
        repo = repo_info()
        private_repo = RepoInfo(**{**repo.__dict__, "private": True})
        public_repo = RepoInfo(**{**repo.__dict__, "private": False})
        destination = GitLabDestination(
            DestinationConfig(url="gitlab.com/group", platform="gitlab", owner="group"),
            AppConfig(),
            DummyUI(),
        )

        destination.dest.visibility = "mirror"
        self.assertEqual(destination.visibility_for(private_repo), "private")
        self.assertEqual(destination.visibility_for(public_repo), "public")

        destination.dest.visibility = "public"
        self.assertEqual(destination.visibility_for(private_repo), "public")

        destination.dest.visibility = "private"
        self.assertEqual(destination.visibility_for(public_repo), "private")


class RunnerTests(unittest.TestCase):
    def test_run_fails_when_source_discovery_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = AppConfig(
                workspace=Path(tmp) / ".agmh",
                github=GitHubConfig(profiles=["https://gitlab.com/not-github"]),
            )
            result = MirrorRunner(cfg, DummyUI()).run()
        self.assertEqual(result, 1)

    def test_local_mode_clones_without_marker_or_destinations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = AppConfig(
                mode="local",
                workspace=Path(tmp) / ".agmh",
                backup=BackupConfig(local_dir=Path(tmp) / "backups"),
                github=GitHubConfig(profiles=["https://github.com/owner"]),
            )
            runner = MirrorRunner(cfg, DummyUI())
            local_git = LocalOnlyGit(Path(tmp))
            runner.git = local_git

            result = runner._process_repo(repo_info())

        self.assertTrue(result)
        self.assertEqual(local_git.clone_calls, 1)
        self.assertEqual(local_git.marker_calls, 0)

    def test_remote_mode_pushes_existing_state_mirror(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mirror_path = Path(tmp) / "backups" / "github" / "owner" / "repo.git"
            mirror_path.mkdir(parents=True)
            (mirror_path / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
            cfg = AppConfig(
                mode="remote",
                workspace=Path(tmp) / ".agmh",
                backup=BackupConfig(local_dir=Path(tmp) / "backups"),
                destinations=[
                    DestinationConfig(
                        url="https://gitlab.com/owner",
                        platform="gitlab",
                        owner="owner",
                        create=False,
                    )
                ],
            )
            state = StateStore(cfg.workspace / "state.json")
            state.mark_repo_metadata(
                "github:owner/repo",
                source_url="https://github.com/owner/repo",
                full_name="owner/repo",
                private=True,
                default_branch="main",
            )
            state.mark_step(
                "github:owner/repo",
                "clone",
                "done",
                path=str(mirror_path),
                downloaded_at="2026-06-13T00:00:00Z",
            )
            state.mark_step("github:owner/repo", "marker", "done", branch="main")

            runner = MirrorRunner(cfg, DummyUI())
            pushes = []

            def record_push(path: Path, push_url: str, push_mode: str, default_branch: str | None) -> None:
                pushes.append((path, push_url, push_mode, default_branch))

            runner.git.push = record_push
            result = runner.run()

        self.assertEqual(result, 0)
        self.assertEqual(pushes, [(mirror_path, "https://gitlab.com/owner/repo.git", "mirror", "main")])

    def test_remote_visibility_flag_overrides_destination_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "agmh.config.toml"
            config_path.write_text(
                "\n".join(
                    [
                        'mode = "remote"',
                        "[[destinations]]",
                        'url = "https://gitlab.com/owner"',
                        'platform = "gitlab"',
                        'visibility = "private"',
                    ]
                ),
                encoding="utf-8",
            )
            args = build_parser().parse_args(
                [
                    "remote-mirror",
                    "--config",
                    str(config_path),
                    "--destination-visibility",
                    "public",
                ]
            )
            cfg = build_config_from_args(args, include_destinations=True)

        self.assertEqual(cfg.mode, "remote")
        self.assertEqual([dest.visibility for dest in cfg.destinations], ["public"])

    def test_destination_visibility_flag_requires_remote_mode(self) -> None:
        args = build_parser().parse_args(["run", "--destination-visibility", "public"])
        with self.assertRaises(ConfigError):
            build_config_from_args(args, include_destinations=True)


if __name__ == "__main__":
    unittest.main()
