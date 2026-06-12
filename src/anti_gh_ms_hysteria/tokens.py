from __future__ import annotations

import time
from dataclasses import dataclass

from .models import RetryConfig, TokenCredential


@dataclass
class TokenLease:
    token: TokenCredential | None
    wait_seconds: float = 0


class TokenPool:
    def __init__(self, tokens: list[TokenCredential], retry: RetryConfig, label: str):
        self.tokens = tokens[:]
        self.retry = retry
        self.label = label
        self.index = 0
        self.blocked_until: dict[int, float] = {}

    def __bool__(self) -> bool:
        return bool(self.tokens)

    def all_secrets(self) -> list[str]:
        return [token.secret for token in self.tokens]

    def current(self) -> TokenCredential | None:
        lease = self.acquire()
        return lease.token

    def acquire(self) -> TokenLease:
        if not self.tokens:
            return TokenLease(None, 0)
        now = time.time()
        count = len(self.tokens)
        for offset in range(count):
            idx = (self.index + offset) % count
            if self.blocked_until.get(idx, 0) <= now:
                self.index = idx
                return TokenLease(self.tokens[idx], 0)
        earliest = min(self.blocked_until.values())
        return TokenLease(None, max(0, earliest - now))

    def rotate(self) -> None:
        if self.tokens:
            self.index = (self.index + 1) % len(self.tokens)

    def mark_limited(self, token: TokenCredential | None, reset_epoch: float | None = None) -> None:
        if token is None or token not in self.tokens:
            return
        idx = self.tokens.index(token)
        fallback = time.time() + self.retry.rate_limit_sleep_seconds
        self.blocked_until[idx] = max(reset_epoch or fallback, time.time())
        self.rotate()

    def available_tokens(self) -> list[TokenCredential]:
        now = time.time()
        return [
            token
            for idx, token in enumerate(self.tokens)
            if self.blocked_until.get(idx, 0) <= now
        ] or self.tokens[:]

