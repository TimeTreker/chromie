"""Deferred delivery for completed outcomes from overlapping ordinary turns.

The coordinator owns only runtime delivery eligibility and waiting.  It does not
infer user intent, Goal relationships, or response wording.  Those remain with
the Goal-driven Core and Planner-owned Communicative Activities.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Iterable, Literal

DeliveryWindowStatus = Literal[
    "ready",
    "goal_invalidated",
    "timeout",
]


@dataclass(frozen=True)
class DeliveryWindowResult:
    status: DeliveryWindowStatus
    waited_for_session_ids: tuple[str, ...] = ()

def goals_deliverable_from_snapshot(
    snapshot: dict[str, Any],
    goal_ids: tuple[str, ...],
) -> bool:
    """Reject only explicit cancellation or supersession of queued result speech."""

    if not goal_ids:
        return True
    contexts = snapshot.get("task_contexts")
    if not isinstance(contexts, list):
        return True
    invalid = {"cancelled", "canceled", "superseded"}
    by_goal: dict[str, str] = {}
    for item in contexts:
        if not isinstance(item, dict):
            continue
        semantic_goal = item.get("semantic_goal")
        if not isinstance(semantic_goal, dict):
            continue
        goal_id = str(semantic_goal.get("goal_id") or "").strip()
        if goal_id:
            by_goal[goal_id] = str(item.get("status") or "").strip().casefold()
    return not any(by_goal.get(goal_id) in invalid for goal_id in goal_ids)


class OutcomeDeliveryCoordinator:
    """Wait for a non-interrupting output window for an earlier completed Goal."""

    def __init__(
        self,
        *,
        current_session_id: Callable[[], str | None],
        session_done: Callable[[str], bool],
        output_idle: Callable[[], bool],
        goals_deliverable: Callable[[tuple[str, ...]], bool],
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        poll_interval_s: float = 0.05,
    ) -> None:
        self._current_session_id = current_session_id
        self._session_done = session_done
        self._output_idle = output_idle
        self._goals_deliverable = goals_deliverable
        self._sleep = sleep
        self._poll_interval_s = max(0.001, float(poll_interval_s))

    @staticmethod
    def is_ordinary_overlap(
        *,
        origin_session_id: str | None,
        current_session_id: str | None,
        generation_changed: bool,
        execution_status: str,
        aggregate_status: str,
    ) -> bool:
        """Return whether staleness came from a newer ordinary turn.

        A generation change alone can represent explicit output invalidation or
        cancellation, so it is not enough.  The earlier execution and aggregate
        outcome must also be complete, and a distinct current session must exist.
        """

        return bool(
            generation_changed
            and origin_session_id
            and current_session_id
            and origin_session_id != current_session_id
            and execution_status == "completed"
            and aggregate_status == "completed"
        )

    async def wait_for_window(
        self,
        *,
        origin_session_id: str,
        source_goal_ids: Iterable[str],
        timeout_s: float,
    ) -> DeliveryWindowResult:
        goal_ids = tuple(dict.fromkeys(str(item).strip() for item in source_goal_ids if str(item).strip()))
        deadline = asyncio.get_running_loop().time() + max(0.001, float(timeout_s))
        waited: list[str] = []

        while True:
            if not self._goals_deliverable(goal_ids):
                return DeliveryWindowResult(
                    status="goal_invalidated",
                    waited_for_session_ids=tuple(waited),
                )

            current = self._current_session_id()
            foreground_busy = bool(
                current
                and current != origin_session_id
                and not self._session_done(current)
            )
            if foreground_busy:
                if current not in waited:
                    waited.append(current)
            elif self._output_idle():
                return DeliveryWindowResult(
                    status="ready",
                    waited_for_session_ids=tuple(waited),
                )

            now = asyncio.get_running_loop().time()
            if now >= deadline:
                return DeliveryWindowResult(
                    status="timeout",
                    waited_for_session_ids=tuple(waited),
                )
            await self._sleep(min(self._poll_interval_s, deadline - now))

def build_host_outcome_delivery(host: Any) -> OutcomeDeliveryCoordinator:
    """Bind the coordinator to the Host's existing lifecycle owners."""

    return OutcomeDeliveryCoordinator(
        current_session_id=lambda: host.session_id,
        session_done=lambda sid: bool(
            (state := host.sessions.state.get(str(sid or ""))) is None
            or state.get("done_logged") is True
        ),
        output_idle=lambda: bool(
            not host.is_playing_audio
            and host.playback_queue.empty()
            and not host.active_synthesis_tasks
        ),
        goals_deliverable=lambda goal_ids: goals_deliverable_from_snapshot(
            host.conversation_state.snapshot(),
            goal_ids,
        ),
    )


__all__ = [
    "DeliveryWindowResult",
    "OutcomeDeliveryCoordinator",
    "build_host_outcome_delivery",
    "goals_deliverable_from_snapshot",
]
