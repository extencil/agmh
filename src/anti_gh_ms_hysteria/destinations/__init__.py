from __future__ import annotations

from .base import DestinationAdapter
from .bitbucket import BitbucketDestination
from .forgejo import ForgejoDestination
from .github import GitHubDestination
from .gitlab import GitLabDestination
from .sourcehut import SourceHutDestination


def build_destination(adapter_config, app_config, ui) -> DestinationAdapter:
    platform = (adapter_config.platform or "").lower()
    if platform == "github":
        return GitHubDestination(adapter_config, app_config, ui)
    if platform == "gitlab":
        return GitLabDestination(adapter_config, app_config, ui)
    if platform in {"forgejo", "codeberg", "gitea"}:
        return ForgejoDestination(adapter_config, app_config, ui)
    if platform == "bitbucket":
        return BitbucketDestination(adapter_config, app_config, ui)
    if platform in {"sourcehut", "srht"}:
        return SourceHutDestination(adapter_config, app_config, ui)
    raise ValueError(f"Unsupported destination platform: {adapter_config.platform}")


__all__ = ["DestinationAdapter", "build_destination"]

