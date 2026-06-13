from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .utils import utc_now_iso


class StateStore:
    def __init__(self, path: Path):
        self.path = path
        self.data: dict[str, Any] = {"version": 1, "repos": {}}
        self.load()

    def load(self) -> None:
        if self.path.exists():
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        self.data.setdefault("version", 1)
        self.data.setdefault("repos", {})

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(self.data, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self.path)

    def repo(self, key: str) -> dict[str, Any]:
        repos = self.data.setdefault("repos", {})
        return repos.setdefault(key, {"steps": {}, "destinations": {}})

    def is_done(self, key: str, step: str) -> bool:
        return self.repo(key).get("steps", {}).get(step, {}).get("status") == "done"

    def mark_step(self, key: str, step: str, status: str, **extra: Any) -> None:
        entry = self.repo(key)
        steps = entry.setdefault("steps", {})
        steps[step] = {"status": status, "updated_at": utc_now_iso(), **extra}
        self.save()

    def mark_repo_metadata(self, key: str, **metadata: Any) -> None:
        entry = self.repo(key)
        entry.update(metadata)
        entry["updated_at"] = utc_now_iso()
        self.save()

    def mark_watch(self, key: str, status: str, **extra: Any) -> None:
        entry = self.repo(key)
        watch = entry.setdefault("watch", {})
        watch.update({"status": status, "updated_at": utc_now_iso(), **extra})
        self.save()

    def destination_status(self, key: str, destination_key: str, step: str) -> str | None:
        dest = self.repo(key).setdefault("destinations", {}).get(destination_key, {})
        return dest.get(step, {}).get("status")

    def mark_destination(
        self,
        key: str,
        destination_key: str,
        step: str,
        status: str,
        **extra: Any,
    ) -> None:
        dests = self.repo(key).setdefault("destinations", {})
        dest = dests.setdefault(destination_key, {})
        dest[step] = {"status": status, "updated_at": utc_now_iso(), **extra}
        self.save()

