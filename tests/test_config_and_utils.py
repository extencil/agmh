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
    parse_source_token,
    source_from_url,
)
from anti_gh_ms_hysteria.cli import build_config_from_args, build_parser
from anti_gh_ms_hysteria.destinations import build_destination
from anti_gh_ms_hysteria.destinations.github import GitHubDestination
from anti_gh_ms_hysteria.destinations.gitlab import GitLabDestination
from anti_gh_ms_hysteria.destinations.gitlab import gitlab_safe_project_path
from anti_gh_ms_hysteria.git_ops import (
    GitMirrorManager,
    build_git_ssh_command,
    git_failure_hint,
    render_commit_message,
    source_auth_username,
)
from anti_gh_ms_hysteria.http import JsonResponse
from anti_gh_ms_hysteria.models import (
    AppConfig,
    BackupConfig,
    DestinationConfig,
    GitConfig,
    GitHubConfig,
    NotificationsConfig,
    RepoInfo,
    SourceConfig,
    TokenCredential,
    WatchConfig,
    WebhookConfig,
)
from anti_gh_ms_hysteria.notifications import safe_config_snapshot
from anti_gh_ms_hysteria.runner import MirrorRunner
from anti_gh_ms_hysteria.sources import build_source
from anti_gh_ms_hysteria.sources.bitbucket import BitbucketSource
from anti_gh_ms_hysteria.sources.forgejo import ForgejoSource
from anti_gh_ms_hysteria.sources.github import GitHubSource
from anti_gh_ms_hysteria.sources.gitlab import GitLabSource
from anti_gh_ms_hysteria.sources.sourcehut import SourceHutSource
from anti_gh_ms_hysteria.state import StateStore
from anti_gh_ms_hysteria.utils import infer_platform, parse_owner_from_profile_url, safe_display_url


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


class FakeWatchSource:
    def __init__(self, source: SourceConfig) -> None:
        self.source = source
        self.key = f"{source.platform}:{source.url}"


class FakeWatchDiscovery:
    def __init__(self, source: SourceConfig, repos: list[RepoInfo]) -> None:
        self.sources = [FakeWatchSource(source)]
        self.repos = repos
        self.discovery_errors: list[tuple[str, str]] = []

    def discover_one(self, source):
        return self.repos

    def current_token(self, repo: RepoInfo) -> TokenCredential | None:
        return None

    def secrets(self) -> list[str]:
        return []


class FakeNotifier:
    def __init__(self) -> None:
        self.events: list[tuple[str, str, str, dict]] = []

    def secrets(self) -> list[str]:
        return []

    def notify(self, event: str, title: str, message: str, data=None) -> None:
        self.events.append((event, title, message, data or {}))


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

    def test_source_url_preserves_gitlab_nested_namespace(self) -> None:
        source = source_from_url("https://gitlab.com/group/subgroup")
        self.assertEqual(source.platform, "gitlab")
        self.assertEqual(source.owner, "group/subgroup")

    def test_source_url_supports_destination_platforms(self) -> None:
        self.assertEqual(source_from_url("https://codeberg.org/extencil").platform, "forgejo")
        self.assertEqual(source_from_url("https://bitbucket.org/extencil").platform, "bitbucket")
        self.assertEqual(source_from_url("https://git.sr.ht/~extencil").owner, "extencil")

    def test_safe_display_url_strips_credentials_and_sensitive_query_values(self) -> None:
        self.assertEqual(
            safe_display_url("https://user:secret@example.com/owner?token=value&visibility=public"),
            "https://example.com/owner?token=***&visibility=public",
        )
        self.assertEqual(
            safe_display_url("git@github.com:owner/repo.git"),
            "git@github.com:owner/repo.git",
        )


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

    def test_source_token_uses_same_platform_prefix_format(self) -> None:
        platform, token = parse_source_token("gitlab:oauth2:secret")
        self.assertEqual(platform, "gitlab")
        self.assertEqual(token.username, "oauth2")
        self.assertEqual(token.secret, "secret")

    def test_username_token_can_resolve_env_secret(self) -> None:
        os.environ["AGMH_BITBUCKET_APP_PASSWORD"] = "bb-secret"
        platform, token = parse_source_token("bitbucket:you@example.com:env:AGMH_BITBUCKET_APP_PASSWORD")
        self.assertEqual(platform, "bitbucket")
        self.assertEqual(token.username, "you@example.com")
        self.assertEqual(token.secret, "bb-secret")


class ConfigTests(unittest.TestCase):
    def test_default_generated_names_use_agmh(self) -> None:
        cfg = config_from_dict({}, Path.cwd())
        self.assertEqual(cfg.workspace, Path(".agmh"))
        self.assertTrue(cfg.backup.marker_enabled)
        self.assertEqual(cfg.backup.marker_filename, "agmh.txt")
        self.assertEqual(cfg.git.author_name, "agmh")
        self.assertEqual(cfg.git.author_email, "agmh@localhost")
        self.assertEqual(cfg.git.commit_message, "Backuping with AGMH v{version}")

    def test_backup_marker_can_be_disabled(self) -> None:
        cfg = config_from_dict({"backup": {"marker_enabled": False}}, Path.cwd())
        self.assertFalse(cfg.backup.marker_enabled)

    def test_commit_message_renders_package_version(self) -> None:
        self.assertRegex(
            render_commit_message("Backuping with AGMH v{version}"),
            r"^Backuping with AGMH v\d+\.\d+\.\d+",
        )

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
        self.assertEqual(cfg.sources[0].platform, "github")
        self.assertEqual(cfg.sources[0].tokens[0].secret, "gh-secret")
        self.assertEqual(cfg.destinations[0].platform, "forgejo")

    def test_config_from_dict_accepts_generic_sources(self) -> None:
        os.environ["AGMH_GL"] = "gl-secret"
        cfg = config_from_dict(
            {
                "sources": [
                    {
                        "url": "https://gitlab.com/group/subgroup",
                        "tokens": [{"env": "AGMH_GL"}],
                    }
                ]
            },
            Path.cwd(),
        )
        self.assertEqual(cfg.sources[0].platform, "gitlab")
        self.assertEqual(cfg.sources[0].owner, "group/subgroup")
        self.assertEqual(cfg.sources[0].tokens[0].secret, "gl-secret")

    def test_build_config_from_args_loads_generic_sources_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "sources.txt").write_text(
                "\n".join(
                    [
                        "https://github.com/extencil",
                        "https://gitlab.com/group/subgroup",
                    ]
                ),
                encoding="utf-8",
            )
            config_path = root / "agmh.config.toml"
            config_path.write_text('sources_file = "sources.txt"\n', encoding="utf-8")
            args = build_parser().parse_args(["run", "--config", str(config_path)])
            cfg = build_config_from_args(args, include_destinations=True)
        self.assertEqual([source.platform for source in cfg.sources], ["github", "gitlab"])
        self.assertEqual(cfg.sources[1].owner, "group/subgroup")

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

    def test_remote_mode_does_not_require_source_token_envs(self) -> None:
        os.environ.pop("AGMH_MISSING_SOURCE_TOKEN", None)
        cfg = config_from_dict(
            {
                "mode": "remote",
                "sources": [
                    {
                        "url": "https://gitlab.com/extencil",
                        "tokens": [{"env": "AGMH_MISSING_SOURCE_TOKEN"}],
                    }
                ],
            },
            Path.cwd(),
        )
        self.assertEqual(cfg.mode, "remote")
        self.assertEqual(cfg.sources, [])

    def test_watch_config_and_source_overrides_are_parsed(self) -> None:
        cfg = config_from_dict(
            {
                "mode": "watching",
                "watch": {
                    "interval_seconds": 30,
                    "action": "local",
                    "initial_run": False,
                    "once": True,
                },
                "sources": [
                    {
                        "url": "https://gitlab.com/group",
                        "watch": False,
                        "watch_interval_seconds": 10,
                        "watch_action": "remote",
                    }
                ],
            },
            Path.cwd(),
        )
        self.assertEqual(cfg.mode, "watching")
        self.assertEqual(cfg.watch.interval_seconds, 30)
        self.assertEqual(cfg.watch.action, "local")
        self.assertFalse(cfg.watch.initial_run)
        self.assertTrue(cfg.watch.once)
        self.assertFalse(cfg.sources[0].watch)
        self.assertEqual(cfg.sources[0].watch_interval_seconds, 10)
        self.assertEqual(cfg.sources[0].watch_action, "remote")

    def test_watch_interval_must_be_positive(self) -> None:
        with self.assertRaises(ConfigError):
            config_from_dict({"watch": {"interval_seconds": 0}}, Path.cwd())

    def test_notifications_are_disabled_by_default(self) -> None:
        cfg = config_from_dict({}, Path.cwd())
        self.assertFalse(cfg.notifications.enabled)
        self.assertEqual(cfg.notifications.webhooks, [])

    def test_config_from_dict_accepts_multiple_webhooks(self) -> None:
        cfg = config_from_dict(
            {
                "notifications": {
                    "enabled": True,
                    "events": ["start", "finish", "error"],
                    "timeout_seconds": 3,
                },
                "webhooks": [
                    {
                        "name": "ops-discord",
                        "platform": "discord",
                        "url_env": "AGMH_DISCORD_WEBHOOK",
                        "events": ["start", "error"],
                        "username": "AGMH",
                        "thread_id": "123",
                    },
                    {
                        "name": "ops-telegram",
                        "platform": "telegram",
                        "bot_token_env": "AGMH_TELEGRAM_TOKEN",
                        "chat_id": "-1001",
                        "parse_mode": "HTML",
                        "message_thread_id": 42,
                    },
                ],
            },
            Path.cwd(),
        )
        self.assertTrue(cfg.notifications.enabled)
        self.assertEqual(cfg.notifications.timeout_seconds, 3)
        self.assertEqual([webhook.platform for webhook in cfg.notifications.webhooks], ["discord", "telegram"])
        self.assertEqual(cfg.notifications.webhooks[0].url_env, "AGMH_DISCORD_WEBHOOK")
        self.assertEqual(cfg.notifications.webhooks[1].message_thread_id, 42)

    def test_safe_config_snapshot_omits_secrets(self) -> None:
        cfg = AppConfig(
            sources=[
                SourceConfig(
                    url="https://user:source-url-secret@github.com/owner?token=source-query-secret",
                    platform="github",
                    api_base="https://api-user:source-api-secret@api.github.com",
                    owner="owner",
                    tokens=[TokenCredential("source-secret")],
                )
            ],
            destinations=[
                DestinationConfig(
                    url="https://user:destination-url-secret@gitlab.com/owner?private_token=destination-query-secret",
                    platform="gitlab",
                    api_base="https://api-user:destination-api-secret@gitlab.com/api/v4",
                    owner="owner",
                    tokens=[TokenCredential("destination-secret")],
                )
            ],
            notifications=NotificationsConfig(
                enabled=True,
                webhooks=[
                    WebhookConfig(
                        name="discord",
                        platform="discord",
                        url="https://discord.com/api/webhooks/secret",
                    )
                ],
            ),
        )
        snapshot = str(safe_config_snapshot(cfg))
        self.assertNotIn("source-secret", snapshot)
        self.assertNotIn("destination-secret", snapshot)
        self.assertNotIn("source-url-secret", snapshot)
        self.assertNotIn("source-query-secret", snapshot)
        self.assertNotIn("source-api-secret", snapshot)
        self.assertNotIn("destination-url-secret", snapshot)
        self.assertNotIn("destination-query-secret", snapshot)
        self.assertNotIn("destination-api-secret", snapshot)
        self.assertNotIn("discord.com/api/webhooks/secret", snapshot)
        self.assertIn("'token_count': 1", snapshot)


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

    def test_source_clone_auth_username_depends_on_platform(self) -> None:
        self.assertEqual(source_auth_username(repo_info(), TokenCredential("secret")), "x-access-token")
        gitlab_repo = RepoInfo(**{**repo_info().__dict__, "source_platform": "gitlab"})
        self.assertEqual(source_auth_username(gitlab_repo, TokenCredential("secret")), "oauth2")
        bitbucket_repo = RepoInfo(**{**repo_info().__dict__, "source_platform": "bitbucket"})
        self.assertEqual(source_auth_username(bitbucket_repo, TokenCredential("secret")), "x-token-auth")
        self.assertEqual(
            source_auth_username(gitlab_repo, TokenCredential("secret", username="user")),
            "user",
        )


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

    def test_mirror_visibility_prefers_source_visibility(self) -> None:
        repo = RepoInfo(**{**repo_info().__dict__, "private": False, "visibility": "unlisted"})
        destination = GitLabDestination(
            DestinationConfig(url="gitlab.com/group", platform="gitlab", owner="group"),
            AppConfig(),
            DummyUI(),
        )
        self.assertEqual(destination.visibility_for(repo), "unlisted")


class SourceMappingTests(unittest.TestCase):
    def test_builds_source_adapters(self) -> None:
        cases = [
            (
                SourceConfig(url="https://github.com/extencil", platform="github", owner="extencil"),
                GitHubSource,
            ),
            (
                SourceConfig(url="https://gitlab.com/extencil", platform="gitlab", owner="extencil"),
                GitLabSource,
            ),
            (
                SourceConfig(url="https://codeberg.org/extencil", platform="forgejo", owner="extencil"),
                ForgejoSource,
            ),
            (
                SourceConfig(url="https://bitbucket.org/extencil", platform="bitbucket", owner="extencil"),
                BitbucketSource,
            ),
            (
                SourceConfig(url="https://git.sr.ht/~extencil", platform="sourcehut", owner="extencil"),
                SourceHutSource,
            ),
        ]
        for config, expected_type in cases:
            self.assertIsInstance(build_source(config, AppConfig(), DummyUI()), expected_type)

    def test_gitlab_repo_response_maps_to_repo_info(self) -> None:
        source = GitLabSource(
            SourceConfig(url="https://gitlab.com/group", platform="gitlab", owner="group"),
            AppConfig(),
            DummyUI(),
        )
        repo = source._repo_from_api(
            {
                "path": "repo",
                "path_with_namespace": "group/subgroup/repo",
                "web_url": "https://gitlab.com/group/subgroup/repo",
                "http_url_to_repo": "https://gitlab.com/group/subgroup/repo.git",
                "ssh_url_to_repo": "git@gitlab.com:group/subgroup/repo.git",
                "default_branch": "main",
                "visibility": "internal",
                "archived": True,
                "forked_from_project": {"id": 1},
            }
        )
        self.assertEqual(repo.source_platform, "gitlab")
        self.assertEqual(repo.owner, "group/subgroup")
        self.assertTrue(repo.private)
        self.assertTrue(repo.archived)
        self.assertTrue(repo.fork)

    def test_forgejo_repo_response_maps_to_repo_info(self) -> None:
        source = ForgejoSource(
            SourceConfig(url="https://codeberg.org/extencil", platform="forgejo", owner="extencil"),
            AppConfig(),
            DummyUI(),
        )
        repo = source._repo_from_api(
            {
                "name": "repo",
                "full_name": "extencil/repo",
                "owner": {"login": "extencil"},
                "html_url": "https://codeberg.org/extencil/repo",
                "clone_url": "https://codeberg.org/extencil/repo.git",
                "ssh_url": "git@codeberg.org:extencil/repo.git",
                "default_branch": "main",
                "private": True,
                "fork": False,
            }
        )
        self.assertEqual(repo.source_platform, "forgejo")
        self.assertEqual(repo.visibility, "private")
        self.assertTrue(repo.private)

    def test_bitbucket_repo_response_maps_to_repo_info(self) -> None:
        source = BitbucketSource(
            SourceConfig(url="https://bitbucket.org/workspace", platform="bitbucket", owner="workspace"),
            AppConfig(),
            DummyUI(),
        )
        repo = source._repo_from_api(
            {
                "full_name": "workspace/repo",
                "name": "Repo",
                "links": {
                    "html": {"href": "https://bitbucket.org/workspace/repo"},
                    "clone": [
                        {"name": "ssh", "href": "git@bitbucket.org:workspace/repo.git"},
                        {"name": "https", "href": "https://bitbucket.org/workspace/repo.git"},
                    ],
                },
                "mainbranch": {"name": "main"},
                "is_private": False,
            }
        )
        self.assertEqual(repo.clone_url, "https://bitbucket.org/workspace/repo.git")
        self.assertEqual(repo.ssh_url, "git@bitbucket.org:workspace/repo.git")
        self.assertFalse(repo.private)

    def test_sourcehut_repo_response_maps_to_repo_info(self) -> None:
        source = SourceHutSource(
            SourceConfig(url="https://git.sr.ht/~extencil", platform="sourcehut", owner="extencil"),
            AppConfig(),
            DummyUI(),
        )
        repo = source._repo_from_api(
            {
                "name": "repo",
                "repoPath": "~extencil/repo",
                "visibility": "UNLISTED",
                "HEAD": {"name": "refs/heads/trunk"},
            }
        )
        self.assertEqual(repo.full_name, "extencil/repo")
        self.assertEqual(repo.web_url, "https://git.sr.ht/~extencil/repo")
        self.assertEqual(repo.default_branch, "trunk")
        self.assertEqual(repo.visibility, "unlisted")


class RunnerTests(unittest.TestCase):
    def test_run_fails_when_source_discovery_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = AppConfig(workspace=Path(tmp) / ".agmh")
            runner = MirrorRunner(cfg, DummyUI())

            class FailingDiscovery:
                discovery_errors = [("https://example.invalid/source", "boom")]

                def discover(self):
                    return []

            runner.source = FailingDiscovery()
            result = runner.run()
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
            notifier = FakeNotifier()
            runner.notifier = notifier

            result = runner._process_repo(repo_info())

        self.assertTrue(result)
        self.assertEqual(local_git.clone_calls, 1)
        self.assertEqual(local_git.marker_calls, 0)
        self.assertIn("local_saved", [event[0] for event in notifier.events])

    def test_marker_disabled_skips_marker_commit_in_full_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = AppConfig(
                mode="full",
                workspace=Path(tmp) / ".agmh",
                backup=BackupConfig(local_dir=Path(tmp) / "backups", marker_enabled=False),
            )
            runner = MirrorRunner(cfg, DummyUI())
            local_git = LocalOnlyGit(Path(tmp))
            runner.git = local_git
            notifier = FakeNotifier()
            runner.notifier = notifier

            result = runner._process_repo(repo_info())
            marker_step = runner.state.repo("github:owner/repo").get("steps", {}).get("marker", {})

        self.assertTrue(result)
        self.assertEqual(local_git.clone_calls, 1)
        self.assertEqual(local_git.marker_calls, 0)
        self.assertEqual(marker_step.get("status"), "skipped")

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
            notifier = FakeNotifier()
            runner.notifier = notifier
            pushes = []

            def record_push(path: Path, push_url: str, push_mode: str, default_branch: str | None) -> None:
                pushes.append((path, push_url, push_mode, default_branch))

            runner.git.push = record_push
            result = runner.run()

        self.assertEqual(result, 0)
        self.assertEqual(pushes, [(mirror_path, "https://gitlab.com/owner/repo.git", "mirror", "main")])
        self.assertIn("remote_saved", [event[0] for event in notifier.events])

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

    def test_watching_processes_first_seen_repo_with_source_action_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = SourceConfig(
                url="https://github.com/owner",
                platform="github",
                owner="owner",
                watch_action="local",
                watch_interval_seconds=7,
            )
            repo = RepoInfo(**{**repo_info().__dict__, "updated_at": "2026-06-13T10:00:00Z"})
            cfg = AppConfig(
                mode="watching",
                workspace=Path(tmp) / ".agmh",
                watch=WatchConfig(once=True, action="full", interval_seconds=60),
            )
            runner = MirrorRunner(cfg, DummyUI())
            notifier = FakeNotifier()
            runner.notifier = notifier
            runner.source = FakeWatchDiscovery(source, [repo])
            processed = []

            def record_process(repo: RepoInfo, force_workflow: bool = False, workflow_mode: str | None = None):
                processed.append((repo.key, force_workflow, workflow_mode))
                return True

            runner._process_repo = record_process
            result = runner.run()

        self.assertEqual(result, 0)
        self.assertEqual(processed, [("github:owner/repo", True, "local")])
        self.assertIn("watch_check", [event[0] for event in notifier.events])
        self.assertIn("watch_update", [event[0] for event in notifier.events])

    def test_watching_initial_run_false_marks_without_processing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = SourceConfig(url="https://github.com/owner", platform="github", owner="owner")
            repo = RepoInfo(**{**repo_info().__dict__, "updated_at": "2026-06-13T10:00:00Z"})
            cfg = AppConfig(
                mode="watching",
                workspace=Path(tmp) / ".agmh",
                watch=WatchConfig(once=True, initial_run=False),
            )
            runner = MirrorRunner(cfg, DummyUI())
            runner.source = FakeWatchDiscovery(source, [repo])
            processed = []

            def record_process(repo: RepoInfo, force_workflow: bool = False, workflow_mode: str | None = None):
                processed.append(repo.key)
                return True

            runner._process_repo = record_process
            result = runner.run()
            watch_state = runner.state.repo(repo.key)["watch"]

        self.assertEqual(result, 0)
        self.assertEqual(processed, [])
        self.assertEqual(watch_state["status"], "seen")

    def test_watching_skips_unchanged_repo_after_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = SourceConfig(url="https://github.com/owner", platform="github", owner="owner")
            repo = RepoInfo(**{**repo_info().__dict__, "updated_at": "2026-06-13T10:00:00Z"})
            cfg = AppConfig(
                mode="watching",
                workspace=Path(tmp) / ".agmh",
                watch=WatchConfig(once=True, action="local"),
            )
            runner = MirrorRunner(cfg, DummyUI())
            notifier = FakeNotifier()
            runner.notifier = notifier
            fake_source = FakeWatchDiscovery(source, [repo])
            runner.source = fake_source
            processed = []

            def record_process(repo: RepoInfo, force_workflow: bool = False, workflow_mode: str | None = None):
                processed.append(repo.updated_at)
                return True

            runner._process_repo = record_process
            first = runner.run()
            processed.clear()
            second = runner.run()

        self.assertEqual(first, 0)
        self.assertEqual(second, 0)
        self.assertEqual(processed, [])
        self.assertIn("watch_none", [event[0] for event in notifier.events])

    def test_watching_processes_repo_when_fingerprint_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = SourceConfig(url="https://github.com/owner", platform="github", owner="owner")
            first_repo = RepoInfo(**{**repo_info().__dict__, "updated_at": "2026-06-13T10:00:00Z"})
            second_repo = RepoInfo(**{**repo_info().__dict__, "updated_at": "2026-06-13T10:05:00Z"})
            cfg = AppConfig(
                mode="watching",
                workspace=Path(tmp) / ".agmh",
                watch=WatchConfig(once=True, action="local"),
            )
            runner = MirrorRunner(cfg, DummyUI())
            fake_source = FakeWatchDiscovery(source, [first_repo])
            runner.source = fake_source
            processed = []

            def record_process(repo: RepoInfo, force_workflow: bool = False, workflow_mode: str | None = None):
                processed.append(repo.updated_at)
                return True

            runner._process_repo = record_process
            runner.run()
            fake_source.repos = [second_repo]
            runner.run()

        self.assertEqual(processed, ["2026-06-13T10:00:00Z", "2026-06-13T10:05:00Z"])


if __name__ == "__main__":
    unittest.main()
