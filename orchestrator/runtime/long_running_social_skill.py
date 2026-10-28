"""Host lifecycle of the long-running social skill (Social Attention contract).

Social Cognition chooses whether Chromie attends to a person, whom, in which posture and
when it stops (owner decisions 2026-10-25/28); Soridormi follows the person every control
frame. This owner only carries out those decisions, ends the skill on the Host's own
deterministic paths (a reflex stop, cancel, emergency or silence; a new conversation;
conversation idle), keeps its state across turns for Social Cognition, and records each
transition in the interaction ledger. It never chooses a person or a posture and never
retargets; Soridormi ends the skill itself when the person is unseen for 5 s or after
10 minutes.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable

from agent.app.tool_invocation import AsyncToolInvoker, ToolInvocationContext
from shared.chromie_contracts.social_cognition import (
    ATTEND_TO_PERSON_CAPABILITY_ID,
    SOCIAL_SKILL_CONTEXT_KEY,
    LongRunningSocialSkillDecision,
    SocialCognitionOutput,
    SocialCognitionRequest,
    social_skill_decision_error,
)

logger = logging.getLogger(__name__)

ATTEND_TO_PERSON_SKILL_ID = "attend_to_person"
TARGET_LOST_S = 5.0
MAX_DURATION_S = 600.0
STATUS_INTERVAL_S = 1.0
CATALOG_INTERVAL_S = 30.0
_BUSY_STATUSES = {"suspended", "turning"}
_ACTIVE_STATUSES = {"running", *_BUSY_STATUSES}


class LongRunningSocialSkill:
    """One Host's long-running social skill, started only by Social Cognition."""

    def __init__(
        self,
        *,
        invoker: AsyncToolInvoker | None,
        ledger: Any = None,
        idle_timeout_s: float = 180.0,
        clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], float] = time.time,
    ) -> None:
        self.invoker = invoker
        self.ledger = ledger
        self.idle_timeout_s = float(idle_timeout_s)
        self._clock = clock
        self._wall_clock = wall_clock
        self._lock = asyncio.Lock()
        self._tasks: set[asyncio.Task[None]] = set()
        self._available: bool | None = None
        self._catalog_checked_at: float | None = None
        self._status_checked_at = 0.0
        self._run: dict[str, Any] | None = None
        self._last_end: dict[str, Any] | None = None
        self._session_id = ""
        self._conversation_id: str | None = None
        self._busy_until_s = 0.0
        # Every recorded transition, bounded, for acceptance evidence across turns.
        self.events: list[dict[str, Any]] = []

    # Social Cognition's view -------------------------------------------------------

    def context(self) -> dict[str, Any]:
        """Whether Soridormi offers the skill, what runs now and how the last run ended."""

        run = self._run
        return {SOCIAL_SKILL_CONTEXT_KEY: {
            "available": self._available is True,
            "capability_id": ATTEND_TO_PERSON_CAPABILITY_ID,
            "active": run is not None,
            **({"target_ref": run["target_ref"], "posture": run["posture"], "status": run["status"]}
               if run is not None else {}),
            **({"last_end": dict(self._last_end)} if run is None and self._last_end else {}),
        }}

    # Decisions and deterministic ends ----------------------------------------------

    def schedule(
        self, decision: LongRunningSocialSkillDecision, *, context: dict[str, Any], session_id: str,
        turn_id: str = "",
    ) -> None:
        """Carry out a decision without delaying the response that carried it."""

        self._spawn(self.apply(decision, context=context, session_id=session_id, turn_id=turn_id))

    async def settle(self) -> None:
        """Wait for decisions and stops already scheduled (acceptance evidence only)."""

        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    def schedule_stop(self, reason: str) -> None:
        """Queued behind any decision still being carried out, so a start in flight is stopped too."""

        self._spawn(self.stop(reason))

    async def apply(
        self, decision: LongRunningSocialSkillDecision, *, context: dict[str, Any], session_id: str,
        turn_id: str = "",
    ) -> None:
        """One Social Cognition decision; a stale or unsupported one does not run."""

        async with self._lock:
            self._session_id = session_id or self._session_id
            error = social_skill_decision_error(decision, {**context, **self.context()})
            if error or self.invoker is None:
                self._record("social_skill_not_run", "not_run", turn_id=turn_id,
                             reason=error or "soridormi_unavailable", target_ref=decision.target_ref)
                return
            if decision.action == "keep":
                return
            if decision.action == "stop":
                await self._stop("social_cognition", turn_id=turn_id)
                return
            outcome = await self.invoker.invoke(
                "soridormi.attention.start",
                {"target_ref": decision.target_ref, "posture": decision.posture,
                 "target_lost_s": TARGET_LOST_S, "max_duration_s": MAX_DURATION_S},
                context=ToolInvocationContext(allow_side_effects=True),
            )
            output = outcome.output if outcome.status == "success" and isinstance(outcome.output, dict) else {}
            if outcome.status != "success":
                # A start that timed out may still have started: adopt what Soridormi runs.
                status = await self.invoker.invoke("soridormi.attention.status", {})
                current = status.output if status.status == "success" and isinstance(status.output, dict) else {}
                if current.get("active") is True and current.get("target_ref") == decision.target_ref:
                    output = {**current, "started": True}
            if output.get("started") is True or output.get("updated") is True:
                changed = output.get("updated") is True and self._run is not None
                # Keeping the same person in the same posture is the steady state, not a change.
                unchanged = changed and all(
                    (self._run or {}).get(key) == getattr(decision, key) for key in ("target_ref", "posture"))
                if self._run is not None and not changed:
                    self._end("switched", turn_id=turn_id)
                self._run = {
                    "attention_id": str(output.get("attention_id") or ""),
                    "target_ref": decision.target_ref, "posture": decision.posture,
                    "status": str(output.get("status") or "running"),
                    "started_wall": (self._run or {}).get("started_wall", self._wall_clock()) if changed
                    else self._wall_clock(),
                }
                self._status_checked_at = self._clock()
                if not unchanged:
                    self._record("social_skill_changed" if changed else "social_skill_started", "running",
                                 turn_id=turn_id, target_ref=decision.target_ref, posture=decision.posture)
                return
            resolution = output.get("target_resolution")
            reason = (
                str((resolution if isinstance(resolution, dict) else {}).get("status") or output.get("status") or "")
                or str(outcome.error or outcome.status)
            )
            self._record("social_skill_not_run", "not_run", turn_id=turn_id, reason=reason,
                         target_ref=decision.target_ref)

    async def stop(self, reason: str, *, turn_id: str = "") -> None:
        """The Host's deterministic ends: a reflex, a new conversation, conversation idle."""

        async with self._lock:
            if self._run is not None:
                await self._stop(reason, turn_id=turn_id)

    async def sync(self, *, last_activity_s: float | None, conversation_id: str | None) -> None:
        """Mechanical upkeep from the ambient perception loop: catalog, status and idle."""

        if self.invoker is None or self._lock.locked():
            return  # a decision or stop is being carried out; never stall the ambient loop behind it
        now = self._clock()
        async with self._lock:
            if self._catalog_checked_at is None or now - self._catalog_checked_at >= CATALOG_INTERVAL_S:
                self._catalog_checked_at = now
                await self._refresh_availability()
                await self._stop_orphan()
            if self._run is not None and self._run.get("stop_pending"):
                await self._stop(str(self._run["stop_pending"]))
                return
            if conversation_id is not None and conversation_id != self._conversation_id:
                previous, self._conversation_id = self._conversation_id, conversation_id
                if previous is not None and self._run is not None:
                    await self._stop("new_conversation")
            if self._run is None:
                return
            if now - self._status_checked_at >= STATUS_INTERVAL_S:
                self._status_checked_at = now
                outcome = await self.invoker.invoke("soridormi.attention.status", {})
                if outcome.status == "success" and isinstance(outcome.output, dict):
                    self._observe_status(outcome.output)
            # Body work that suspends attention is not idleness: idle counts from the later
            # of the last conversation activity and the last time the skill was busy.
            quiet_since = max(last_activity_s or 0.0, self._busy_until_s,
                              float((self._run or {}).get("started_wall") or 0.0))
            if self._run is not None and last_activity_s is not None and (
                self._wall_clock() - quiet_since >= self.idle_timeout_s
            ):
                await self._stop("conversation_idle")

    # Internals ---------------------------------------------------------------------

    def _spawn(self, operation: Any) -> None:
        task = asyncio.create_task(operation, name="long-running-social-skill")
        self._tasks.add(task)
        task.add_done_callback(self._task_done)

    def _task_done(self, task: asyncio.Task[None]) -> None:
        self._tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            logger.warning("long_running_social_skill_failed error=%r", task.exception())

    async def _refresh_availability(self) -> None:
        if self.invoker is None:
            return
        outcome = await self.invoker.invoke("soridormi.skill.list", {})
        skills = outcome.output.get("skills") if outcome.status == "success" and isinstance(
            outcome.output, dict) else None
        available = isinstance(skills, list) and any(
            isinstance(item, dict) and item.get("skill_id") == ATTEND_TO_PERSON_SKILL_ID
            and item.get("lifecycle") == "long_running" and item.get("available") is not False
            for item in skills
        )
        if available != self._available:
            logger.info("long_running_social_skill_available available=%s", available)
        self._available = available

    async def _stop_orphan(self) -> None:
        """A run this Host does not track (a previous Host's, or a lost one) is ended."""

        if not self._available or self.invoker is None or self._run is not None:
            return
        outcome = await self.invoker.invoke("soridormi.attention.status", {})
        if outcome.status == "success" and isinstance(outcome.output, dict) and outcome.output.get("active"):
            await self.invoker.invoke("soridormi.attention.stop", {"reason": "host_started"},
                                      context=ToolInvocationContext(allow_safety_controls=True))
            logger.info("long_running_social_skill_orphan_stopped attention_id=%s",
                        outcome.output.get("attention_id"))

    def _observe_status(self, output: dict[str, Any]) -> None:
        run = self._run
        if run is None:
            return
        if str(output.get("attention_id") or "") != run["attention_id"]:
            self._end("ended_elsewhere")
            return
        status = str(output.get("status") or "")
        if status in _BUSY_STATUSES or run["status"] in _BUSY_STATUSES:
            self._busy_until_s = self._wall_clock()
        if status == "ended" or output.get("active") is False:
            self._end(str(output.get("end_reason") or "ended"))
            return
        if status in _ACTIVE_STATUSES and status != run["status"]:
            was_suspended = run["status"] == "suspended"
            run["status"] = status
            if status == "suspended":
                self._record("social_skill_suspended", "suspended", target_ref=run["target_ref"])
            elif was_suspended:
                self._record("social_skill_resumed", status, target_ref=run["target_ref"])

    async def _stop(self, reason: str, *, turn_id: str = "") -> None:
        if self.invoker is not None:
            outcome = await self.invoker.invoke(
                "soridormi.attention.stop", {"reason": reason},
                context=ToolInvocationContext(allow_safety_controls=True),
            )
            if outcome.status != "success" and self._run is not None:
                # Keep the run so the next upkeep pass retries; never record an end that did not happen.
                logger.warning("long_running_social_skill_stop_failed reason=%s error=%s", reason, outcome.error)
                self._run["stop_pending"] = reason
                return
        self._end(reason, turn_id=turn_id)

    def _end(self, reason: str, *, turn_id: str = "") -> None:
        run = self._run
        if run is None:
            return
        self._run = None
        self._last_end = {"target_ref": run["target_ref"], "reason": reason}
        self._record("social_skill_ended", "ended", turn_id=turn_id, attention_id=run["attention_id"],
                     reason=reason, target_ref=run["target_ref"])

    def _record(
        self, event_type: Any, state: str, *, turn_id: str = "", attention_id: str | None = None,
        **metadata: Any,
    ) -> None:
        attention_id = (self._run or {}).get("attention_id", "") if attention_id is None else attention_id
        logger.info("long_running_social_skill event=%s attention_id=%s %s", event_type, attention_id,
                    " ".join(f"{key}={value}" for key, value in metadata.items()))
        self.events.append({"event_type": event_type, "state": state, "attention_id": attention_id,
                            **{key: value for key, value in metadata.items() if value is not None}})
        del self.events[:-100]
        if self.ledger is None or not self._session_id:
            return
        occurred_at = datetime.now(timezone.utc)
        self.ledger.append(
            session_id=self._session_id,
            owner="trusted_capability_runtime",
            domain="social_attention",
            event_type=event_type,
            state=state,
            subject_id=attention_id or ATTEND_TO_PERSON_CAPABILITY_ID,
            event_id=f"{event_type}:{attention_id}:{occurred_at.isoformat()}",
            turn_id=turn_id,
            capability_id=ATTEND_TO_PERSON_CAPABILITY_ID,
            occurred_at=occurred_at,
            metadata={key: value for key, value in metadata.items() if value is not None},
        )


def social_skill_of(runtime: Any) -> LongRunningSocialSkill | None:
    skill = getattr(runtime, "long_running_social_skill", None)
    return skill if isinstance(skill, LongRunningSocialSkill) else None


def with_social_skill_context(runtime: Any, context: dict[str, Any]) -> dict[str, Any]:
    """The Social Cognition context with the skill's offer and state, when the Host has one."""

    skill = social_skill_of(runtime)
    return {**context, **skill.context()} if skill is not None else dict(context)


def apply_social_skill_decision(
    runtime: Any, result: SocialCognitionOutput, *, request: SocialCognitionRequest, session_id: str,
) -> None:
    skill = social_skill_of(runtime)
    if skill is not None and result.social_skill is not None:
        skill.schedule(result.social_skill, context=request.context, session_id=session_id,
                       turn_id=str(request.source_turn.get("turn_id") or ""))


async def sync_social_skill(host: Any) -> None:
    """One upkeep pass; a failed Soridormi read leaves the skill's state as it was."""

    skill = social_skill_of(getattr(host, "interaction_runtime", None))
    conversation = getattr(host, "conversation_state", None)
    if skill is None:
        return
    last_activity_ms = getattr(conversation, "last_activity_ms", None)
    try:
        await skill.sync(
            last_activity_s=float(last_activity_ms) / 1000.0 if last_activity_ms else None,
            conversation_id=getattr(conversation, "conversation_id", None),
        )
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning("long_running_social_skill_sync_failed error_type=%s error=%s",
                       type(exc).__name__, str(exc)[:240])
