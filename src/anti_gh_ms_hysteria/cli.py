from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .models import AppConfig
from .config import (
    apply_destinations_file,
    apply_profile_file,
    destination_from_url,
    load_config,
    parse_cli_token,
    parse_destination_token,
)
from .runner import MirrorRunner
from .ui import UI, setup_logging


SAMPLE_CONFIG = """workspace = ".aghm"
dry_run = false
verbose = 0
tui = true

[github]
profiles_file = "targets.txt"
tokens = [{ env = "GITHUB_TOKEN", name = "github-primary" }]

[backup]
local_dir = "backups"
clone_protocol = "https"
include_archived = true
include_forks = true
include_private_for_authenticated_user = true
lfs = false
push_mode = "mirror"

[[destinations]]
url = "https://gitlab.com/example"
platform = "gitlab"
tokens = [{ env = "GITLAB_TOKEN", name = "gitlab-primary" }]
visibility = "mirror"
push_mode = "mirror"

[git]
# ssh_identity_file = "/home/user/.ssh/sourcehut_ed25519"
# ssh_strict_host_key_checking = "accept-new"
"""


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    raw = list(sys.argv[1:] if argv is None else argv)
    commands = {"run", "discover", "init-config", "state", "-h", "--help"}
    if not raw or raw[0] not in commands:
        raw = ["run", *raw]
    args = parser.parse_args(raw)
    return args.handler(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agmh",
        description="Local GitHub backup and repository mirroring CLI.",
    )
    sub = parser.add_subparsers(dest="command")

    run = sub.add_parser("run", help="discover, back up, annotate, and mirror repositories")
    add_runtime_args(run)
    run.set_defaults(handler=run_command)

    discover = sub.add_parser("discover", help="list accessible GitHub repositories")
    add_runtime_args(discover, destinations=False)
    discover.add_argument("--output", type=Path, help="write JSON discovery output to this file")
    discover.set_defaults(handler=discover_command)

    init = sub.add_parser("init-config", help="write a starter TOML config")
    init.add_argument("--path", type=Path, default=Path("aghm.config.toml"))
    init.add_argument("--force", action="store_true")
    init.set_defaults(handler=init_config_command)

    state = sub.add_parser("state", help="show a summary of the local resume state")
    state.add_argument("--config", type=Path)
    state.add_argument("--workspace", type=Path)
    state.set_defaults(handler=state_command)
    return parser


def add_runtime_args(parser: argparse.ArgumentParser, destinations: bool = True) -> None:
    parser.add_argument("--config", type=Path, help="TOML config file")
    parser.add_argument("--sources", type=Path, help="text file with one GitHub profile URL per line")
    parser.add_argument("--source", action="append", default=[], help="GitHub profile URL; repeatable")
    parser.add_argument("--github-token", action="append", default=[], help="GitHub token value or env:NAME; repeatable")
    parser.add_argument("--workspace", type=Path, help="state/log workspace directory")
    parser.add_argument("--local-dir", type=Path, help="local bare mirror directory")
    parser.add_argument("--clone-protocol", choices=["https", "ssh"], help="source clone protocol")
    parser.add_argument(
        "--push-mode",
        choices=["mirror", "portable-mirror", "all", "default"],
        help="destination Git push mode",
    )
    parser.add_argument("--proxy", help="HTTP/HTTPS proxy URL for API and git commands")
    parser.add_argument("-k", "--insecure", action="store_true", help="disable TLS certificate verification")
    parser.add_argument("--ssh-key", type=Path, help="SSH private key file used by git clone/push")
    parser.add_argument("--ssh-command", help="full GIT_SSH_COMMAND override used by git clone/push")
    parser.add_argument(
        "--ssh-strict-host-key-checking",
        choices=["yes", "no", "accept-new"],
        help="SSH StrictHostKeyChecking value used by git clone/push",
    )
    parser.add_argument("--ssh-batch-mode", action="store_true", help="make SSH fail instead of prompting")
    parser.add_argument("--request-timeout", type=float, help="API request timeout in seconds")
    parser.add_argument("--max-retries", type=int, help="maximum API retries after transient network failures")
    parser.add_argument("--dry-run", action="store_true", help="plan actions without creating, cloning, or pushing")
    parser.add_argument("--no-tui", action="store_true", help="disable optional Rich console rendering")
    parser.add_argument("--no-resume", action="store_true", help="ignore completed state entries")
    parser.add_argument("--force", action="store_true", help="redo steps even if state says they are done")
    parser.add_argument("--lfs", action="store_true", help="run git lfs fetch --all after mirror updates")
    parser.add_argument("-v", "--verbose", action="count", default=0, help="increase log verbosity")
    parser.add_argument("--exclude-archived", action="store_true", help="skip archived GitHub repositories")
    parser.add_argument("--exclude-forks", action="store_true", help="skip forked GitHub repositories")
    if destinations:
        parser.add_argument("--destinations", type=Path, help="text file with one destination profile URL per line")
        parser.add_argument("--destination", action="append", default=[], help="destination profile URL; repeatable")
        parser.add_argument(
            "--destination-token",
            action="append",
            default=[],
            help="destination token as platform:token, platform:env:NAME, or platform:username:token",
        )


def run_command(args: argparse.Namespace) -> int:
    cfg = build_config_from_args(args, include_destinations=True)
    if not cfg.github.profiles:
        print("No GitHub source profiles were provided.", file=sys.stderr)
        return 2
    logger, log_path = setup_logging(cfg.workspace, cfg.verbose)
    ui = UI(logger, use_rich=cfg.tui, verbose=cfg.verbose)
    ui.info(f"Log file: {log_path}")
    return MirrorRunner(cfg, ui).run()


def discover_command(args: argparse.Namespace) -> int:
    cfg = build_config_from_args(args, include_destinations=False)
    if not cfg.github.profiles:
        print("No GitHub source profiles were provided.", file=sys.stderr)
        return 2
    logger, log_path = setup_logging(cfg.workspace, cfg.verbose)
    ui = UI(logger, use_rich=cfg.tui, verbose=cfg.verbose)
    ui.info(f"Log file: {log_path}")
    runner = MirrorRunner(cfg, ui)
    runner.write_discovery_json(args.output)
    return 1 if runner.source.discovery_errors else 0


def init_config_command(args: argparse.Namespace) -> int:
    if args.path.exists() and not args.force:
        print(f"Refusing to overwrite existing config: {args.path}", file=sys.stderr)
        return 2
    args.path.write_text(SAMPLE_CONFIG, encoding="utf-8")
    print(f"Wrote {args.path}")
    return 0


def state_command(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    if args.workspace:
        cfg.workspace = args.workspace
    state_path = cfg.workspace / "state.json"
    if not state_path.exists():
        print(f"No state file found at {state_path}")
        return 0
    data = json.loads(state_path.read_text(encoding="utf-8"))
    repos = data.get("repos", {})
    print(f"State: {state_path}")
    print(f"Repositories tracked: {len(repos)}")
    done_pushes = 0
    failed = 0
    for entry in repos.values():
        for step in entry.get("steps", {}).values():
            failed += 1 if step.get("status") == "failed" else 0
        for dest in entry.get("destinations", {}).values():
            done_pushes += 1 if dest.get("push", {}).get("status") == "done" else 0
            for step in dest.values():
                failed += 1 if isinstance(step, dict) and step.get("status") == "failed" else 0
    print(f"Completed destination pushes: {done_pushes}")
    print(f"Failed steps: {failed}")
    return 0


def build_config_from_args(args: argparse.Namespace, include_destinations: bool) -> AppConfig:
    cfg = load_config(args.config)
    if args.workspace:
        cfg.workspace = args.workspace
    if args.local_dir:
        cfg.backup.local_dir = args.local_dir
    if args.clone_protocol:
        cfg.backup.clone_protocol = args.clone_protocol
    if args.push_mode:
        cfg.backup.push_mode = args.push_mode
    if args.proxy:
        cfg.proxy = args.proxy
    if args.insecure:
        cfg.insecure_tls = True
    if args.ssh_key:
        cfg.git.ssh_identity_file = args.ssh_key
    if args.ssh_command:
        cfg.git.ssh_command = args.ssh_command
    if args.ssh_strict_host_key_checking:
        cfg.git.ssh_strict_host_key_checking = args.ssh_strict_host_key_checking
    if args.ssh_batch_mode:
        cfg.git.ssh_batch_mode = True
    if args.request_timeout:
        cfg.retry.request_timeout_seconds = args.request_timeout
    if args.max_retries is not None:
        cfg.retry.max_retries = args.max_retries
    if args.dry_run:
        cfg.dry_run = True
    if args.no_tui:
        cfg.tui = False
    if args.no_resume:
        cfg.resume = False
    if args.force:
        cfg.force = True
    if args.lfs:
        cfg.backup.lfs = True
    if args.verbose:
        cfg.verbose = max(cfg.verbose, args.verbose)
    if args.exclude_archived:
        cfg.backup.include_archived = False
    if args.exclude_forks:
        cfg.backup.include_forks = False

    apply_profile_file(cfg, args.sources)
    cfg.github.profiles.extend(args.source)
    cfg.github.tokens.extend(parse_cli_token(token) for token in args.github_token)

    if include_destinations:
        apply_destinations_file(cfg, args.destinations)
        cfg.destinations.extend(destination_from_url(url) for url in args.destination)
        destination_tokens = [parse_destination_token(value) for value in args.destination_token]
        for platform, token in destination_tokens:
            matched = False
            for dest in cfg.destinations:
                if (dest.platform or "").lower() == platform:
                    dest.tokens.append(token)
                    matched = True
            if not matched:
                print(f"WARNING: no destination matched token platform {platform}", file=sys.stderr)
    return cfg
