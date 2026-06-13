from __future__ import annotations

import logging
from pathlib import Path


class UI:
    def __init__(self, logger: logging.Logger, use_rich: bool = True, verbose: int = 0):
        self.logger = logger
        self.verbose = verbose
        self.console = None
        if use_rich:
            try:
                from rich.console import Console

                self.console = Console()
            except Exception:
                self.console = None

    def info(self, message: str) -> None:
        self.logger.info(message)
        self._print(message)

    def warning(self, message: str) -> None:
        self.logger.warning(message)
        self._print(f"WARNING: {message}")

    def error(self, message: str) -> None:
        self.logger.error(message)
        self._print(f"ERROR: {message}")

    def debug(self, message: str) -> None:
        self.logger.debug(message)
        if self.verbose > 0:
            self._print(f"DEBUG: {message}")

    def success(self, message: str) -> None:
        self.logger.info(message)
        self._print(message)

    def _print(self, message: str) -> None:
        if self.console:
            self.console.print(message, markup=False)
        else:
            print(message)


def setup_logging(workspace: Path, verbose: int) -> tuple[logging.Logger, Path]:
    workspace.mkdir(parents=True, exist_ok=True)
    logs_dir = workspace / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    from .utils import utc_now_iso

    log_path = logs_dir / f"run-{utc_now_iso().replace(':', '-')}.log"
    logger = logging.getLogger("agmh")
    logger.handlers.clear()
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    logger.addHandler(file_handler)

    return logger, log_path
