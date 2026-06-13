# AGMH

![License: Unlicense](https://img.shields.io/badge/license-Unlicense-blue.svg)
![Python](https://img.shields.io/badge/python-3.11%2B-3776ab.svg)
![CLI](https://img.shields.io/badge/interface-CLI%20%2B%20TUI-111111.svg)
![Sources](https://img.shields.io/badge/sources-GitHub%20%7C%20GitLab%20%7C%20Forgejo%20%7C%20Bitbucket%20%7C%20SourceHut-111111.svg)
![Destinations](https://img.shields.io/badge/destinations-GitHub%20%7C%20GitLab%20%7C%20Forgejo%20%7C%20Bitbucket%20%7C%20SourceHut-111111.svg)

AGMH means **ANTI GITHUB & MICROSOFT HYSTERIA**.

AGMH is a local backup and repository mirroring CLI built to help researchers,
maintainers, and software teams pull their work out of a forge quickly and push
it to another forge without losing years of history, branches, tags, or research.

It discovers repositories from supported source profiles, organizations, groups,
namespaces, or workspaces; clones them locally as mirrors; adds a small
provenance marker file; creates matching repositories on destination platforms;
and pushes the backup to GitHub, GitLab, Codeberg/Forgejo, SourceHut,
Bitbucket, or compatible Git remotes.

The primary CLI command is:

```bash
agmh
```

The legacy typo `aghm` was removed. AGMH intentionally uses `agmh` for commands,
default config files, state directories, logs, and generated marker files.

## Project Statement

This tool exists because people need a fast, practical way to remove their work
from a platform before a platform removes them.

AGMH was built in the context of a ban-wave against security researchers and the
public conflict around MSRC, the Microsoft Security Response Center, and the
researchers behind:

- https://x.com/ChaoticEclipse0
- https://x.com/xploitrsturtle2

The position of this project is explicit: when a centralized development
platform adopts policies that can be used to repress security researchers
because triagers, vendors, or corporate response teams had their egos bruised,
researchers need escape tools. If the people responsible for keeping software
secure had done their job, the ecosystem would not be in this situation.

This is not a personal fight with GitHub. It is a practical statement that
people must have the right and the ability to remove their own work from GitHub
and move it elsewhere before they lose years of research, tooling, issue
history, public contributions, branches, tags, and project continuity.

AGMH was produced by **Haltman.IO** as a peaceful protest and as a practical
tool. It was not produced by `@extencil`, but by the same group he is part of,
and it is released freely so others can protect their own work.

This tool has already been used to back up repositories from `@extencil` and
`@haltman-io` to GitLab, Codeberg, and SourceHut successfully.

This may be the last Haltman.IO project released on this shameful platform,
which in the view of this project has adopted a policy of repression against
security researchers because two of them hurt the ego of MSRC triagers.

## Public Mirrors And Accounts

AGMH was used to move the work of `@extencil` and `@haltman-io` away from
GitHub and into independent mirrors.

Extencil mirrors:

- GitLab: https://gitlab.com/extencil
- Codeberg: https://codeberg.org/extencil
- SourceHut: https://git.sr.ht/~extencil

Haltman.IO mirrors:

- GitLab: https://gitlab.com/haltman-io
- Codeberg: https://codeberg.org/haltman

Extencil also uses X, where he exposed the case around his ban:

- X profile: https://x.com/extencil
- Ban case statement: https://x.com/extencil/status/2065150696937115988

Extencil public links:

| Network | Link |
| --- | --- |
| ORCID | https://orcid.org/0009-0007-0914-3920 |
| Email | extencil@proton.thc.org, extencil@segfault.net, extencil@haltman.io, extencil@haltman.org, extencil@metasploit.io, extencil@lockbit.io, extencil@polkit.org |
| Telegram | https://t.me/extencil |
| Discord | `@extencil` |
| Signal | `@extencil.01` |
| Bluesky | https://bsky.app/profile/extencil.me |
| Mastodon | https://mastodon.social/@extencil |
| GitHub | ~~https://github.com/extencil~~ - taken down by Microslop |
| Reddit | https://reddit.com/user/extencil |
| GitLab | https://gitlab.com/extencil |
| YouTube | https://youtube.com/@extencil-thc |

## Haltman.IO

Haltman is a group of Brazilian hackers. Friends for over a decade, building
public, privacy-first infrastructure and free software.

We build, break, audit, and publish.

We do not sell platforms. We do not run franchises.

We do not ask permission.

Haltman.IO links:

- Website: https://haltman.io/
- Alternate website: https://haltman.org/
- Contact: root@haltman.io, root@haltman.org
- Join Haltman.IO: https://haltman.io/join/
- Telegram group: https://t.me/haltman_group

### Operating Values

| Doctrine | Value |
| --- | --- |
| 01 Independence | We answer to no one. No board. No investors. No sponsors. Our independence guarantees our freedom. |
| 02 Transparency | Every tool is open source. Every decision is visible. No back rooms. No hidden agendas. |
| 03 Public Output | We publish. We document. We release. Our work speaks for itself. Not our marketing. |
| 04 No Hierarchy | Flat structure. No leaders. No bosses. No titles. No org charts. Respect is earned by output. |
| 05 Mutual Aid | When one of us needs help, the others show up. No invoices. No politics. Just engineering. |
| 06 No Compromise | We do not water down our principles for comfort, profit, or acceptance. Those who trade freedom for security end up with neither. |

## What It Does

AGMH can:

- Read source profile, organization, group, namespace, or workspace URLs from a text file.
- Discover accessible public and private repositories from GitHub, GitLab, Forgejo/Gitea, Bitbucket, and SourceHut.
- Use one or more source tokens to increase API limits and access private repos.
- Rotate tokens when rate limits or authorization failures happen.
- Clone each repository locally using `git clone --mirror`.
- Run in local-only mode to download/update mirrors without pushing anywhere.
- Run in remote-only mode to push existing local mirrors to configured destinations later.
- Keep a local backup under `backups/` by default.
- Add `agmh.txt` to the default branch before mirroring.
- Create destination repositories through platform APIs.
- Preserve repository name and public/private visibility where supported.
- Push mirrors to GitHub, GitLab, Codeberg/Forgejo, SourceHut, Bitbucket, and similar Git destinations.
- Use resumable state in `.agmh/state.json`.
- Write detailed logs to `.agmh/logs/`.
- Run dry-run simulations.
- Use proxies.
- Disable TLS verification when needed for intercepting proxies.
- Use SSH keys for destinations such as SourceHut.
- Keep going when one repository fails instead of aborting the whole run.

## Supported Platforms

Source support:

| Platform | Discovery scope | Private repos | Notes |
| --- | --- | --- | --- |
| GitHub | User or organization | Yes, with token | Uses GitHub REST repositories API. GitHub Enterprise can use `api_base`. |
| GitLab | User, group, or subgroup | Yes, with token | Group discovery includes subgroups. `internal` repositories are treated as non-public when mirrored elsewhere. |
| Codeberg | User or organization | Yes, with token | Uses the Forgejo adapter. |
| Forgejo/Gitea | User or organization | Yes, with token | Works with compatible `/api/v1` instances. |
| Bitbucket | Workspace | Yes, with token | Uses Bitbucket Cloud workspaces and repository pagination. |
| SourceHut | User | Yes, with token | Uses the git.sr.ht GraphQL API. `unlisted` visibility is preserved when the destination supports it. |

Destination support:

| Platform | API create | HTTPS push | SSH push | Notes |
| --- | --- | --- | --- | --- |
| GitHub | Yes | Yes | Possible with custom URL | Use a destination token with repo creation and push permissions. GitHub Enterprise can use `api_base`. |
| GitLab | Yes | Yes | Possible with custom URL | Hidden repo names such as `.github` are mapped to valid GitLab paths such as `dot-github`. |
| Codeberg | Yes | Yes | Possible with custom URL | Uses Forgejo API. GitHub `refs/pull/*` refs are excluded in portable mirror mode because Codeberg rejects hidden refs. |
| Forgejo/Gitea | Yes | Yes | Possible with custom URL | Same adapter family as Codeberg. |
| SourceHut | Yes | Optional | Yes | API token creates repositories, SSH is recommended for Git pushes. |
| Bitbucket | Yes | Yes | Possible with custom URL | Requires Bitbucket-compatible credentials. |

## Requirements

- Python 3.11 or newer.
- Git available in `PATH`.
- Network access to source and destination forges.
- Destination accounts and tokens with enough permission to create repositories and push Git refs.
- Optional: `git-lfs` if you enable `lfs = true`.
- Optional: `ssh-agent` and SSH keys for SourceHut or SSH-based destinations.

Ubuntu system packages:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git ca-certificates openssh-client
```

Optional packages:

```bash
sudo apt install -y git-lfs curl
```

Notes:

- `git-lfs` is only required when AGMH is configured with `lfs = true`.
- `curl` is used only for the troubleshooting and proxy test commands shown in this README.
- If your Ubuntu release provides Python older than 3.11, install Python 3.11 or newer before creating the virtual environment.

## Installation

Clone the repository:

```bash
git clone https://github.com/haltman-io/agmh.git
cd agmh
```

Create a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install AGMH in editable mode:

```bash
python -m pip install -U pip
python -m pip install -e ".[tui]"
```

Check the CLI:

```bash
agmh --help
agmh run --help
```

If you do not install the package, you can run it with `PYTHONPATH`:

```bash
PYTHONPATH=src python3 -m anti_gh_ms_hysteria run --help
```

## Quick Start

Create a starter config:

```bash
cp config.example.toml agmh.config.toml
```

Create `sources.txt` from the public-safe example:

```bash
cp sources.example.txt sources.txt
$EDITOR sources.txt
```

If you prefer to keep destinations in a separate file instead of inline TOML,
start from the destination example:

```bash
cp destinations.example.txt destinations.txt
$EDITOR destinations.txt
```

Export tokens:

```bash
export GITHUB_TOKEN="github_token_here"
export GITHUB_DEST_TOKEN="github_destination_token_here"
export GITLAB_TOKEN="gitlab_token_here"
export CODEBERG_TOKEN="codeberg_token_here"
export SOURCEHUT_TOKEN="sourcehut_token_here"
```

Run a dry-run first:

```bash
agmh run --config agmh.config.toml --dry-run --verbose
```

Run the real backup:

```bash
agmh run --config agmh.config.toml --verbose
```

Check state:

```bash
agmh state --config agmh.config.toml
```

## Workflow Modes

Default full workflow:

```bash
agmh run --config agmh.config.toml --verbose
```

This discovers source repositories, clones or updates local mirrors, adds the
marker commit when `backup.marker_enabled` is true, creates destination
repositories, and pushes mirrors.

Local mirror only:

```bash
agmh local-mirror --config agmh.config.toml --verbose
```

Equivalent:

```bash
agmh run --config agmh.config.toml --mode local --verbose
```

This discovers source repositories and only clones or updates local bare mirrors
under `backup.local_dir`. It does not create marker commits and does not contact
destination forges, even if destinations are present in the config.

Remote mirror from existing local mirrors:

```bash
agmh remote-mirror --config agmh.config.toml --verbose
```

Equivalent:

```bash
agmh run --config agmh.config.toml --mode remote --verbose
```

This does not discover or clone from source forges. It reads mirrors recorded in
`.agmh/state.json`, falls back to scanning `backup.local_dir`, adds the marker
commit if enabled and needed, creates destination repositories, and pushes the
local mirrors.
When AGMH has to scan local mirrors without state metadata, repository privacy is
unknown, so it treats those repositories as private by default.

By default, remote mirror follows the source repository visibility. You can
override destination visibility for the whole remote mirror run:

```bash
agmh remote-mirror --config agmh.config.toml --destination-visibility mirror
agmh remote-mirror --config agmh.config.toml --destination-visibility public
agmh remote-mirror --config agmh.config.toml --destination-visibility private
```

`mirror` applies the same visibility recorded from the source. `public` creates
destination repositories as public regardless of source visibility. `private`
creates destination repositories as private regardless of source visibility. If
a destination repository already exists, AGMH uses the existing repository as-is.
The same override is available with `agmh run --mode remote`.

Watching mode:

```bash
agmh watching --config agmh.config.toml --verbose
```

Equivalent:

```bash
agmh run --config agmh.config.toml --mode watching --verbose
```

Watching mode runs until interrupted. It polls enabled sources, compares the
current source metadata with `.agmh/state.json`, and runs the configured action
only for first-seen or changed repositories. The default action is `full`.
The change fingerprint uses source API update fields such as GitHub `pushed_at`,
GitLab `last_activity_at`, Forgejo `updated_at`, Bitbucket `updated_on`, and
SourceHut `updated`. GitLab documents that `last_activity_at` can lag by up to
one hour, so GitLab polling is eventually consistent rather than instant.

Watching actions:

| Action | Behavior |
| --- | --- |
| `full` | Clone/update the local mirror, ensure the marker when enabled, create destinations, and push. |
| `local` | Clone/update the local mirror only. |
| `remote` | Push an existing local mirror for the changed repository. If the local mirror is missing, the action fails for that repository. |

Configure polling globally:

```toml
[watch]
interval_seconds = 300
action = "full"       # full, local, or remote
initial_run = true    # process repositories the first time they are seen
once = false          # useful for tests or supervised one-shot runs
```

Override polling per source:

```toml
[[sources]]
url = "https://gitlab.com/haltman-io"
platform = "gitlab"
tokens = [{ env = "GITLAB_SOURCE_TOKEN" }]
watch = true
watch_interval_seconds = 120
watch_action = "local"
```

CLI overrides:

```bash
agmh watching \
  --config agmh.config.toml \
  --watch-interval 120 \
  --watch-action full
```

Use `--no-watch-initial-run` when you want AGMH to record the current state
without processing existing repositories on the first polling cycle. Use
`--watch-once` to run one polling cycle and exit.

You can also set the mode in TOML:

```toml
mode = "full"   # full, local, remote, or watching
```

## Input Files

AGMH reads source profiles from a plain text file. Use one profile,
organization, group, namespace, or workspace URL per line:

```txt
https://github.com/extencil/
https://github.com/haltman-io/
https://gitlab.com/haltman-io/
https://codeberg.org/haltman/
https://bitbucket.org/example-workspace/
https://git.sr.ht/~extencil/
```

Blank lines and lines beginning with `#` are ignored.

You can also pass source profiles directly:

```bash
agmh run --source https://github.com/extencil/ --source https://github.com/haltman-io/
```

For private non-GitHub sources, prefer inline `[[sources]]` entries so each
source can declare its own `tokens` and `api_base`.

Destinations can be configured in TOML or in a plain text file:

```txt
https://gitlab.com/haltman-io
https://codeberg.org/haltman
https://git.sr.ht/~extencil
```

## Full Configuration Example

```toml
workspace = ".agmh"
mode = "full"
dry_run = false
verbose = 0
tui = true
insecure_tls = false
sources_file = "sources.txt"

[github]
tokens = [
  { env = "GITHUB_TOKEN", name = "github-primary" },
  # { env = "GITHUB_TOKEN_2", name = "github-secondary" },
]

[watch]
interval_seconds = 300
action = "full"
initial_run = true
once = false

[notifications]
enabled = false
events = ["*"]
fail_silently = true
timeout_seconds = 10

# [[webhooks]]
# name = "ops-discord"
# platform = "discord"
# url_env = "DISCORD_WEBHOOK_URL"
# events = ["start", "finish", "error", "local_saved", "remote_saved", "watch_check", "watch_update", "watch_none"]
# username = "AGMH"
#
# [[webhooks]]
# name = "ops-telegram"
# platform = "telegram"
# bot_token_env = "TELEGRAM_BOT_TOKEN"
# chat_id_env = "TELEGRAM_CHAT_ID"
# events = ["start", "finish", "error", "watch_update"]
# parse_mode = "HTML"

# Inline sources are useful when a non-GitHub source needs a token or api_base.
[[sources]]
url = "https://gitlab.com/haltman-io"
platform = "gitlab"
tokens = [{ env = "GITLAB_SOURCE_TOKEN", name = "gitlab-source" }]
watch_interval_seconds = 120
watch_action = "local"

[backup]
local_dir = "backups"
clone_protocol = "https"
include_archived = true
include_forks = true
include_private_for_authenticated_user = true
lfs = false
marker_enabled = true
push_mode = "mirror"

[retry]
max_retries = 5
base_delay_seconds = 1.5
max_delay_seconds = 60
request_timeout_seconds = 15
rate_limit_sleep_seconds = 300
wait_on_rate_limit = true

[git]
author_name = "root"
author_email = "root@haltman.io"
commit_message = "Backuping with AGMH v{version}"
# ssh_identity_file = "/home/user/.ssh/sourcehut_ed25519"
# ssh_identities_only = true
# ssh_batch_mode = false
# ssh_strict_host_key_checking = "accept-new"
# ssh_command = "ssh -i /home/user/.ssh/sourcehut_ed25519 -o IdentitiesOnly=yes"

[[destinations]]
url = "https://github.com/haltman-io-mirror"
platform = "github"
tokens = [{ env = "GITHUB_DEST_TOKEN", name = "github-destination" }]
visibility = "mirror"
push_mode = "mirror"

[[destinations]]
url = "https://gitlab.com/haltman-io"
platform = "gitlab"
tokens = [{ env = "GITLAB_TOKEN", name = "gitlab-primary" }]
visibility = "mirror"
push_mode = "mirror"

[[destinations]]
url = "https://codeberg.org/haltman"
platform = "forgejo"
tokens = [{ env = "CODEBERG_TOKEN", name = "codeberg-primary" }]
visibility = "mirror"
push_mode = "mirror"

[[destinations]]
url = "https://git.sr.ht/~extencil"
platform = "sourcehut"
tokens = [{ env = "SOURCEHUT_TOKEN", name = "sourcehut-primary" }]
visibility = "mirror"
push_mode = "mirror"
push_url_template = "git@git.sr.ht:~{owner}/{repo}"
```

## Configuration Reference

Top-level options:

| Key | Meaning |
| --- | --- |
| `mode` | Workflow mode: `full`, `local`, `remote`, or `watching`. Default: `full`. |
| `workspace` | Local state and logs directory. Default: `.agmh`. |
| `dry_run` | Plan actions without cloning, creating, or pushing. |
| `verbose` | Default verbosity level. CLI `-v` can override it. |
| `tui` | Use Rich console rendering when installed. |
| `proxy` | Optional HTTP/HTTPS proxy URL. |
| `insecure_tls` | Disable TLS certificate verification for API calls and Git HTTPS operations. |
| `resume` | Reuse `.agmh/state.json` and skip completed steps. |
| `force` | Redo steps even if state says they are complete. |
| `sources_file` | Text file containing source profile/org/group/workspace URLs. |

GitHub source shortcut options:

| Key | Meaning |
| --- | --- |
| `api_base` | GitHub API base URL. Default: `https://api.github.com`. |
| `profiles_file` | Text file containing GitHub source profile/org URLs. Prefer top-level `sources_file` for mixed providers. |
| `profiles` | Inline list of GitHub source profile/org URLs. Prefer `[[sources]]` for mixed providers. |
| `tokens` | GitHub source token entries. These are also attached to GitHub URLs read from `sources_file`. |

Source options:

| Key | Meaning |
| --- | --- |
| `url` | Source profile, org, group, namespace, or workspace URL. |
| `platform` | `github`, `gitlab`, `forgejo`, `sourcehut`, or `bitbucket`. Usually inferred from `url`. |
| `api_base` | Optional API override for self-hosted or enterprise instances. |
| `owner` | Optional owner/namespace/workspace override. |
| `tokens` | Source API and HTTPS clone tokens. Use `env` instead of hardcoding secrets. |
| `watch` | Enable or disable this source in watching mode. Default: `true`. |
| `watch_interval_seconds` | Per-source polling interval override. |
| `watch_action` | Per-source action override: `full`, `local`, or `remote`. |

Watch options:

| Key | Meaning |
| --- | --- |
| `interval_seconds` | Default polling interval for sources in watching mode. |
| `action` | Default action for changed repositories: `full`, `local`, or `remote`. |
| `initial_run` | Process repositories the first time they are seen. If `false`, AGMH records current fingerprints and waits for later changes. |
| `once` | Run one polling cycle and exit. Mainly useful for tests, cron-like runs, or supervised debugging. |

Backup options:

| Key | Meaning |
| --- | --- |
| `local_dir` | Local mirror storage directory. |
| `clone_protocol` | `https` or `ssh` for source clone URLs. |
| `include_archived` | Include archived repositories. |
| `include_forks` | Include forked repositories. |
| `include_private_for_authenticated_user` | When the token belongs to the source user, include private repositories. |
| `lfs` | Run `git lfs fetch --all` after mirror updates. |
| `marker_enabled` | Write a provenance marker commit before remote mirrors. Default: `true`. Set to `false` to avoid modifying mirrored repositories. |
| `marker_filename` | Marker file name. Default: `agmh.txt`. |
| `push_mode` | `mirror`, `portable-mirror`, `all`, or `default`. |

Retry options:

| Key | Meaning |
| --- | --- |
| `max_retries` | Maximum retry attempts for transient API and Git network failures. |
| `base_delay_seconds` | Initial retry delay. |
| `max_delay_seconds` | Maximum exponential backoff delay. |
| `request_timeout_seconds` | API request timeout. |
| `rate_limit_sleep_seconds` | Sleep interval when rate limited and no reset time is available. |
| `wait_on_rate_limit` | Wait and resume instead of failing on rate limits. |

Git options:

| Key | Meaning |
| --- | --- |
| `author_name` | Git author name for marker commits. |
| `author_email` | Git author email for marker commits. |
| `commit_message` | Commit message for the marker commit. Supports `{version}`. Default: `Backuping with AGMH v{version}`. |
| `ssh_identity_file` | Private key for Git SSH operations. |
| `ssh_command` | Full `GIT_SSH_COMMAND` override. |
| `ssh_identities_only` | Add `-o IdentitiesOnly=yes` when using `ssh_identity_file`. |
| `ssh_batch_mode` | Add `-o BatchMode=yes`, useful for non-interactive jobs. |
| `ssh_strict_host_key_checking` | `yes`, `no`, or `accept-new`. |

Destination options:

| Key | Meaning |
| --- | --- |
| `url` | Destination account, group, org, or namespace URL. |
| `platform` | `github`, `gitlab`, `forgejo`, `sourcehut`, or `bitbucket`. |
| `api_base` | Optional API override for self-hosted instances. |
| `owner` | Optional owner/namespace override. |
| `tokens` | Destination API/Git tokens. |
| `visibility` | `mirror`, `public`, `private`, or `unlisted`. |
| `push_mode` | Override push mode for that destination. |
| `create` | Create repositories through the destination API. |
| `allow_existing` | Treat existing repositories as usable. |
| `git_username` | Username for HTTPS Git push URLs. |
| `push_url_template` | Custom push URL, for example SourceHut SSH. |

Notification options:

| Key | Meaning |
| --- | --- |
| `enabled` | Enable webhook notifications. Default: `false`. |
| `events` | Global event filter. Use `["*"]` for all enabled events. |
| `fail_silently` | Log webhook delivery errors instead of failing the workflow. Default: `true`. |
| `timeout_seconds` | HTTP timeout for webhook delivery. |

Supported notification events:

| Event | When it fires |
| --- | --- |
| `start` | Workflow starts, with a sanitized config snapshot. |
| `finish` | Workflow finishes, with exit code. |
| `local_saved` | A repository mirror was cloned or updated locally. |
| `remote_saved` | A repository was pushed to a destination. |
| `watch_check` | Watching mode starts checking a source for updates. |
| `watch_update` | Watching mode found a changed or first-seen repository and includes the next action. |
| `watch_none` | Watching mode found no updates and includes the next polling interval. |
| `error` | A source discovery, clone, marker, create, push, or workflow error happened. |

Webhook options:

| Key | Meaning |
| --- | --- |
| `name` | Human-readable webhook name used in local warnings. |
| `platform` | `generic`, `discord`, or `telegram`. |
| `enabled` | Per-webhook enable switch. Default: `true`. |
| `events` | Per-webhook event filter. Use `["*"]` for all events allowed globally. |
| `url` / `url_env` | Generic or Discord webhook URL. Prefer `url_env`. |
| `headers` | Extra headers for generic webhooks. |
| `username` | Discord webhook username override. |
| `avatar_url` | Discord webhook avatar override. |
| `thread_id` | Discord forum/thread selector query parameter. |
| `bot_token` / `bot_token_env` | Telegram bot token. Prefer `bot_token_env`. |
| `chat_id` / `chat_id_env` | Telegram chat ID. |
| `api_base` | Telegram API base URL. Default: `https://api.telegram.org`. |
| `parse_mode` | Telegram parse mode, for example `HTML`. |
| `message_thread_id` | Telegram forum topic ID. |
| `disable_web_page_preview` | Telegram link preview switch. Default: `true`. |

Example webhooks:

```toml
[notifications]
enabled = true
events = ["*"]
fail_silently = true

[[webhooks]]
name = "ops-discord"
platform = "discord"
url_env = "DISCORD_WEBHOOK_URL"
events = ["start", "finish", "error", "local_saved", "remote_saved", "watch_update"]
username = "AGMH"

[[webhooks]]
name = "ops-telegram"
platform = "telegram"
bot_token_env = "TELEGRAM_BOT_TOKEN"
chat_id_env = "TELEGRAM_CHAT_ID"
events = ["error", "watch_update", "watch_none"]
parse_mode = "HTML"

[[webhooks]]
name = "ops-generic"
platform = "generic"
url_env = "AGMH_WEBHOOK_URL"
events = ["*"]
```

Webhook notifications never include token values, webhook URLs, Telegram bot
tokens, or destination push URLs containing credentials. The `start` event
includes sources, destinations, modes, counts, and other operational settings
from a sanitized config snapshot.

## Tokens

Use environment variables. Do not hardcode tokens into config files committed to
Git.

GitHub:

```bash
export GITHUB_TOKEN="..."
```

GitHub destination:

```bash
export GITHUB_DEST_TOKEN="..."
```

GitLab:

```bash
export GITLAB_TOKEN="..."
```

Codeberg:

```bash
export CODEBERG_TOKEN="..."
```

SourceHut:

```bash
export SOURCEHUT_TOKEN="..."
```

Webhooks:

```bash
export DISCORD_WEBHOOK_URL="..."
export TELEGRAM_BOT_TOKEN="..."
export TELEGRAM_CHAT_ID="..."
export AGMH_WEBHOOK_URL="..."
```

You can pass extra tokens from the CLI:

```bash
agmh run \
  --source https://github.com/haltman-io/ \
  --github-token env:GITHUB_TOKEN \
  --source-token gitlab:env:GITLAB_SOURCE_TOKEN \
  --destination https://gitlab.com/haltman-io \
  --destination-token gitlab:env:GITLAB_TOKEN
```

Use `--github-token` as a shortcut for GitHub sources. Use `--source-token platform:...`
for other source providers, for example `gitlab:env:GITLAB_TOKEN`,
`forgejo:env:CODEBERG_TOKEN`, `bitbucket:env:BITBUCKET_TOKEN`,
`bitbucket:you@example.com:env:BITBUCKET_TOKEN`, or `sourcehut:env:SOURCEHUT_TOKEN`.

Multiple tokens are allowed. AGMH rotates tokens when a token is rejected, rate
limited, or temporarily unusable.

In TOML arrays, every token entry must be separated by a comma:

```toml
[github]
tokens = [
  { env = "GITHUB_TOKEN", name = "github-primary" },
  { env = "GITHUB_TOKEN_2", name = "github-secondary" },
]
```

You can also use a named token table:

```toml
[github.tokens]
github-primary = { env = "GITHUB_TOKEN" }
github-secondary = "env:GITHUB_TOKEN_2"
```

## Marker File

By default, before pushing to destinations, AGMH writes a marker file into the
default branch of the local mirror:

```txt
agmh.txt
```

The marker contains:

```txt
source_url=https://github.com/owner/repo
downloaded_at=2026-06-12T00:00:00Z
marker_created_at=2026-06-12T00:00:01Z
```

This is intentional. It makes it clear where the backup came from and when the
backup process created the provenance marker.

Disable this repository modification with:

```toml
[backup]
marker_enabled = false
```

When `marker_enabled` is `false`, AGMH does not create or update the marker file
and does not create a marker commit before pushing to destinations.

## Push Modes

`mirror`:

Uses `git push --mirror` when the destination accepts every ref.

`portable-mirror`:

Pushes branches and tags while excluding platform-specific refs such as
GitHub pull request refs under `refs/pull/*`. This is useful for Codeberg and
Forgejo, which can reject hidden refs.

`all`:

Runs `git push --all` and then `git push --tags`.

`default`:

Pushes only the default branch.

Recommended defaults:

| Destination | Recommended push mode |
| --- | --- |
| GitHub | `mirror`, automatically translated to `portable-mirror` |
| GitLab | `mirror` |
| Codeberg/Forgejo | `mirror`, automatically translated to `portable-mirror` |
| SourceHut | `mirror` over SSH, or `portable-mirror` if hidden refs cause rejection |
| Bitbucket | `portable-mirror` |

## Proxy Usage

Use an HTTP or HTTPS proxy:

```bash
agmh run --config agmh.config.toml --proxy http://127.0.0.1:8080 --verbose
```

Use a remote proxy:

```bash
agmh run --config agmh.config.toml --proxy http://83.143.242.45:31343 --verbose
```

If the proxy intercepts TLS and you know what you are doing:

```bash
agmh run --config agmh.config.toml --proxy http://127.0.0.1:8080 --insecure --verbose
```

`--insecure` is equivalent to `-k`:

```bash
agmh run --config agmh.config.toml --proxy http://127.0.0.1:8080 -k
```

This disables certificate verification for API calls and sets
`GIT_SSL_NO_VERIFY=true` for Git HTTPS operations.

### Segfault.net Proxy Route

When GitHub API access is being rate-limited, blocked, or degraded from your
local network, you can route AGMH through a temporary HTTP proxy exposed from a
Segfault.net disposable root server.

Segfault.net is a project from The Hacker's Choice (THC). THC is an international hacker and IT security research group founded in 1995.
Segfault.net provides disposable root servers: each SSH login creates a root
server inside a virtual machine, with a public reverse TCP/UDP port option and
outbound traffic routed through upstream VPN networks. This makes it useful as a
temporary network exit path when the GitHub API is unusable from your current
IP address.

Open a Segfault.net shell:

```bash
ssh root@segfault.net
```

The public demo password is:

```text
segfault
```

Inside the Segfault.net server, request a public reverse port:

```bash
curl sf/port
```

Example output:

```text
Tip: Type cat /config/self/reverse_* for details.
Tip: Type rshell to start listening.
Tip: Type curl sf/port to assign a new port.
Your reverse Port is 83.143.242.45 31343 [83.143.242.45:31343]
```

Start an HTTP proxy listener on that assigned port:

```bash
gost -L http://:31343
```

Keep this SSH session open. The proxy exists only while the Segfault.net
environment and the `gost` process are alive. If the shell is closed or a new
Segfault.net server is created, request a new port and update the AGMH command.

On your workstation, run AGMH through the public proxy:

```bash
agmh run \
  --config agmh.config.toml \
  --verbose \
  --proxy http://83.143.242.45:31343 \
  --insecure
```

Use `--insecure` or `-k` only when TLS verification fails because of the proxy
path or interception layer. If normal certificate validation works through the
proxy, remove `--insecure`.

Before running a full migration, test the proxy path directly:

```bash
curl -I \
  --proxy http://83.143.242.45:31343 \
  https://api.github.com/users/extencil
```

Then run a short AGMH dry run with retries disabled:

```bash
agmh run \
  --config agmh.config.toml \
  --dry-run \
  --verbose \
  --proxy http://83.143.242.45:31343 \
  --insecure \
  --request-timeout 5 \
  --max-retries 0
```

This proxy path affects AGMH API calls and Git HTTPS operations. It does not
automatically proxy SSH pushes such as `git@git.sr.ht:~user/repo`, because SSH
does not use the HTTP proxy settings.

## SSH Usage

SourceHut is best used with SSH for Git pushes.

SourceHut destination:

```toml
[[destinations]]
url = "https://git.sr.ht/~extencil"
platform = "sourcehut"
tokens = [{ env = "SOURCEHUT_TOKEN", name = "sourcehut-primary" }]
visibility = "mirror"
push_mode = "mirror"
push_url_template = "git@git.sr.ht:~{owner}/{repo}"
```

If your SSH key is not a default key, configure it:

```toml
[git]
ssh_identity_file = "/home/user/.ssh/sourcehut_ed25519"
ssh_identities_only = true
ssh_strict_host_key_checking = "accept-new"
```

Or pass it at runtime:

```bash
agmh run --config agmh.config.toml \
  --ssh-key ~/.ssh/sourcehut_ed25519 \
  --ssh-strict-host-key-checking accept-new
```

If the key has a passphrase, use `ssh-agent`:

```bash
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/sourcehut_ed25519
```

Test before running AGMH:

```bash
ssh -T -i ~/.ssh/sourcehut_ed25519 -o IdentitiesOnly=yes git@git.sr.ht
```

Do not use a private key directly from a Windows-mounted path such as
`/mnt/c/Users/...` if OpenSSH reports permissive permissions. Copy it into the
Linux filesystem and lock permissions:

```bash
mkdir -p ~/.ssh
cp /mnt/c/Users/andre/.ssh/private_id_ed25519 ~/.ssh/sourcehut_ed25519
chmod 700 ~/.ssh
chmod 600 ~/.ssh/sourcehut_ed25519
```

## Dry Run

Dry-run still calls platform APIs for discovery. It does not create repos,
clone, add marker commits, or push.

```bash
agmh run --config agmh.config.toml --dry-run --verbose
```

Fail fast while debugging network/proxy issues:

```bash
agmh run --config agmh.config.toml \
  --dry-run \
  --verbose \
  --request-timeout 5 \
  --max-retries 0
```

## Resume and State

AGMH stores resumable state here:

```txt
.agmh/state.json
```

Logs are stored here:

```txt
.agmh/logs/
```

Show a state summary:

```bash
agmh state --config agmh.config.toml
```

Force completed steps to rerun:

```bash
agmh run --config agmh.config.toml --force
```

Ignore existing state:

```bash
agmh run --config agmh.config.toml --no-resume
```

## Operational Examples

Discover only:

```bash
agmh discover --sources sources.txt
```

Write discovery output to JSON:

```bash
agmh discover --sources sources.txt --output discovered-repos.json
```

Back up one GitHub org to GitLab:

```bash
export GITHUB_TOKEN="..."
export GITLAB_TOKEN="..."

agmh run \
  --source https://github.com/haltman-io/ \
  --destination https://gitlab.com/haltman-io \
  --destination-token gitlab:env:GITLAB_TOKEN \
  --github-token env:GITHUB_TOKEN \
  --verbose
```

Back up one GitLab group to GitHub:

```bash
export GITLAB_SOURCE_TOKEN="..."
export GITHUB_DEST_TOKEN="..."

agmh run \
  --source https://gitlab.com/haltman-io/ \
  --source-token gitlab:env:GITLAB_SOURCE_TOKEN \
  --destination https://github.com/haltman-io-mirror \
  --destination-token github:env:GITHUB_DEST_TOKEN \
  --verbose
```

Back up one Codeberg account to GitLab:

```bash
export CODEBERG_SOURCE_TOKEN="..."
export GITLAB_TOKEN="..."

agmh run \
  --source https://codeberg.org/haltman/ \
  --source-token forgejo:env:CODEBERG_SOURCE_TOKEN \
  --destination https://gitlab.com/haltman-codeberg-mirror \
  --destination-token gitlab:env:GITLAB_TOKEN \
  --verbose
```

Use Codeberg:

```bash
export CODEBERG_TOKEN="..."

agmh run \
  --source https://github.com/haltman-io/ \
  --destination https://codeberg.org/haltman \
  --destination-token forgejo:env:CODEBERG_TOKEN \
  --verbose
```

Use GitHub as a destination:

```bash
export GITHUB_TOKEN="..."
export GITHUB_DEST_TOKEN="..."

agmh run \
  --source https://github.com/haltman-io/ \
  --destination https://github.com/haltman-io-mirror \
  --destination-token github:env:GITHUB_DEST_TOKEN \
  --github-token env:GITHUB_TOKEN \
  --verbose
```

Watch sources and mirror updates:

```bash
agmh watching \
  --config agmh.config.toml \
  --watch-interval 300 \
  --watch-action full \
  --verbose
```

Use SourceHut over SSH:

```bash
export SOURCEHUT_TOKEN="..."

agmh run \
  --source https://github.com/haltman-io/ \
  --destination https://git.sr.ht/~extencil \
  --destination-token sourcehut:env:SOURCEHUT_TOKEN \
  --ssh-key ~/.ssh/sourcehut_ed25519 \
  --ssh-strict-host-key-checking accept-new \
  --verbose
```

Use a proxy and ignore TLS validation:

```bash
agmh run \
  --config agmh.config.toml \
  --proxy http://127.0.0.1:8080 \
  --insecure \
  --verbose
```

## Troubleshooting

### `No module named anti_gh_ms_hysteria`

You are running from a source checkout without installing the package.

Fix:

```bash
python -m pip install -e ".[tui]"
```

Or run with:

```bash
PYTHONPATH=src python3 -m anti_gh_ms_hysteria run --help
```

### It hangs on source discovery

The first source API request is waiting on network, DNS, proxy, or TLS.

Run:

```bash
agmh run --config agmh.config.toml --dry-run -v --request-timeout 5 --max-retries 0
```

Check the source API directly. For GitHub:

```bash
curl -I --max-time 10 https://api.github.com/users/extencil
```

### Proxy returns HTTP 500

Use verbose mode. AGMH prints full HTTP response details for failed HTTP
responses:

```bash
agmh run --config agmh.config.toml --proxy http://127.0.0.1:8080 --insecure --verbose --max-retries 0
```

If the response body is from the proxy, fix the proxy. If it is from the
destination, inspect the API response.

### GitLab rejects `.github`

GitLab does not allow project paths starting with a dot. AGMH maps `.github` to
`dot-github` for GitLab destinations.

If old state points to the wrong path, AGMH rechecks create when destination
path mapping changes.

### Codeberg rejects `refs/pull/*`

Codeberg/Forgejo can reject hidden GitHub pull request refs:

```txt
deny updating a hidden ref
```

AGMH maps Forgejo/Codeberg `mirror` mode to `portable-mirror`, which pushes
branches and tags without GitHub `refs/pull/*`.

### `gnutls_handshake() failed`

This is usually a transient network, proxy, or TLS interruption during Git
push. AGMH retries this class of Git network failure.

You can also reduce concurrency outside AGMH and rerun. Failed state entries are
not marked `done`, so reruns continue from the failed push.

### SourceHut says `Permission denied (publickey,keyboard-interactive)`

Your Git subprocess did not use the correct SSH key, or the key was rejected.

Test as the same user, without `sudo`:

```bash
ssh -T -i ~/.ssh/sourcehut_ed25519 -o IdentitiesOnly=yes git@git.sr.ht
```

Then run:

```bash
agmh run --config agmh.config.toml --ssh-key ~/.ssh/sourcehut_ed25519
```

### OpenSSH says `UNPROTECTED PRIVATE KEY FILE`

Private key permissions are too open. Fix:

```bash
chmod 700 ~/.ssh
chmod 600 ~/.ssh/sourcehut_ed25519
```

If the key is under `/mnt/c`, copy it to the Linux filesystem first.

### `HTTP 401`

The token is invalid, expired, missing required scopes, or belongs to the wrong
account.

Check the environment:

```bash
printenv GITHUB_TOKEN
printenv GITHUB_DEST_TOKEN
printenv GITLAB_TOKEN
printenv CODEBERG_TOKEN
printenv SOURCEHUT_TOKEN
printenv DISCORD_WEBHOOK_URL
printenv TELEGRAM_BOT_TOKEN
printenv TELEGRAM_CHAT_ID
```

Do not paste tokens into logs or issues.

### `HTTP 403` or `HTTP 429`

You hit rate limits or permission limits. AGMH rotates available tokens and, if
configured, waits for the reset window.

Use more tokens:

```toml
[github]
tokens = [
  { env = "GITHUB_TOKEN", name = "github-primary" },
  { env = "GITHUB_TOKEN_2", name = "github-secondary" },
]
```

### Repository already exists

By default, `allow_existing = true` lets AGMH continue and push into an existing
destination repository.

### Existing state skips something you want to retry

Use:

```bash
agmh run --config agmh.config.toml --force
```

or edit `.agmh/state.json` carefully.

## Security Notes

- Prefer environment variables for secrets.
- Do not commit `.agmh/`, `backups/`, `agmh.config.toml`, `sources.txt`, `destinations.txt`, or private config files.
- Logs scrub configured token secrets.
- If a token was ever printed before scrubbing existed, rotate it.
- `--insecure` is useful for debugging or intercepting proxies, but it disables TLS verification.
- SSH private keys must be readable only by your user.

## Repository Layout

```txt
src/anti_gh_ms_hysteria/
  cli.py                CLI entrypoint
  runner.py             workflow orchestration
  config.py             TOML and CLI config loading
  git_ops.py            clone, marker commit, push operations
  http.py               API client, retries, proxy, TLS handling
  state.py              resumable state file
  sources/              GitHub, GitLab, Forgejo, Bitbucket, SourceHut discovery adapters
  destinations/         GitHub, GitLab, Forgejo, Bitbucket, SourceHut adapters
tests/
  test_config_and_utils.py
```

## Development

Install:

```bash
python -m pip install -e ".[tui]"
```

Run tests:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

Compile check:

```bash
PYTHONPATH=src python -m compileall -q src tests
```

CLI smoke test:

```bash
PYTHONPATH=src python -m anti_gh_ms_hysteria run --help
```

## References

- Unlicense: https://unlicense.org/
- GitHub personal access tokens: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens
- GitHub repositories REST API: https://docs.github.com/en/rest/repos/repos
- GitHub REST API rate limits: https://docs.github.com/rest/rate-limit/rate-limit
- GitLab personal access tokens: https://docs.gitlab.com/user/profile/personal_access_tokens/
- GitLab Projects API: https://docs.gitlab.com/api/projects/
- GitLab Groups API: https://docs.gitlab.com/api/groups/
- Codeberg access tokens: https://docs.codeberg.org/advanced/access-token/
- Forgejo API usage: https://forgejo.org/docs/latest/user/api-usage/
- Bitbucket repositories API: https://developer.atlassian.com/cloud/bitbucket/rest/api-group-repositories/
- SourceHut git.sr.ht GraphQL API docs: https://docs.sourcehut.org/git.sr.ht/
- SourceHut GraphQL API docs: https://docs.sourcehut.org/
- SourceHut: https://sourcehut.org/
- Discord Webhook Resource: https://docs.discord.com/developers/resources/webhook
- Telegram Bot API: https://core.telegram.org/bots/api
- The Hacker's Choice: https://www.thc.org/
- Segfault.net disposable root servers: https://www.thc.org/segfault/
- Segfault.net service notes: https://www.thc.org/segfault/free/
- Segfault.net Server Centre source: https://github.com/hackerschoice/segfault
- ChaoticEclipse0: https://x.com/ChaoticEclipse0
- xploitrsturtle2: https://x.com/xploitrsturtle2

## License

AGMH is released under the **Unlicense**.

This means the project is dedicated to the public domain to the fullest extent
possible. See:

- https://unlicense.org/
- [LICENSE](LICENSE)

## Author

Author: **root@haltman.io**

Produced by **Haltman.IO**.
