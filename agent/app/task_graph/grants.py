from __future__ import annotations

import hashlib
import json
import secrets
import time
from dataclasses import dataclass

from .models import TaskGraph


@dataclass(frozen=True)
class ConfirmationGrant:
    graph_hash: str
    confirmed_node_ids: frozenset[str]
    expires_at: float


class ConfirmationGrantStore:
    """Issue short-lived, single-use confirmation grants bound to an exact graph."""

    def __init__(self) -> None:
        self._grants: dict[str, ConfirmationGrant] = {}

    def issue(
        self,
        graph: TaskGraph,
        confirmed_node_ids: set[str],
        *,
        ttl_s: int,
    ) -> tuple[str, ConfirmationGrant]:
        token = secrets.token_urlsafe(32)
        grant = ConfirmationGrant(
            graph_hash=self.graph_hash(graph),
            confirmed_node_ids=frozenset(confirmed_node_ids),
            expires_at=time.time() + ttl_s,
        )
        self._grants[self._token_hash(token)] = grant
        return token, grant

    def consume(self, token: str, graph: TaskGraph) -> ConfirmationGrant:
        grant = self._grants.pop(self._token_hash(token), None)
        if grant is None:
            raise ValueError("confirmation grant is invalid or already used")
        if grant.expires_at < time.time():
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
