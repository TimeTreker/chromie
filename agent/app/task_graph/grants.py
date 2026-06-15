from __future__ import annotations

import hashlib
import json
import secrets
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass

from .models import TaskGraph


@dataclass(frozen=True)
class ConfirmationGrant:
    graph_hash: str
    confirmed_node_ids: frozenset[str]
    expires_at: float


class ConfirmationGrantStore:
    """Issue short-lived, single-use confirmation grants bound to an exact graph."""

    def __init__(
        self,
        *,
        max_entries: int = 128,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be at least 1")
        self.max_entries = max_entries
        self._clock = clock
        self._grants: OrderedDict[str, ConfirmationGrant] = OrderedDict()

    def issue(
        self,
        graph: TaskGraph,
        confirmed_node_ids: set[str],
        *,
        ttl_s: int,
    ) -> tuple[str, ConfirmationGrant]:
        now = self._now()
        self._purge_expired(now)
        token = secrets.token_urlsafe(32)
        grant = ConfirmationGrant(
            graph_hash=self.graph_hash(graph),
            confirmed_node_ids=frozenset(confirmed_node_ids),
            expires_at=now + ttl_s,
        )
        while len(self._grants) >= self.max_entries:
            self._grants.popitem(last=False)
        self._grants[self._token_hash(token)] = grant
        return token, grant

    def consume(self, token: str, graph: TaskGraph) -> ConfirmationGrant:
        grant = self._grants.pop(self._token_hash(token), None)
        if grant is None:
            self._purge_expired()
            raise ValueError("confirmation grant is invalid or already used")
        now = self._now()
        self._purge_expired(now)
        if grant.expires_at < now:
            raise ValueError("confirmation grant has expired")
        if not secrets.compare_digest(grant.graph_hash, self.graph_hash(graph)):
            raise ValueError("confirmation grant does not match this TaskGraph")
        return grant

    def graph_hash(self, graph: TaskGraph) -> str:
        payload = json.dumps(
            graph.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def _token_hash(self, token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _purge_expired(self, now: float | None = None) -> None:
        now = self._now() if now is None else now
        expired = [
            token_hash
            for token_hash, grant in self._grants.items()
            if grant.expires_at < now
        ]
        for token_hash in expired:
            self._grants.pop(token_hash, None)

    def __len__(self) -> int:
        self._purge_expired()
        return len(self._grants)

    def _now(self) -> float:
        return self._clock() if self._clock is not None else time.time()
