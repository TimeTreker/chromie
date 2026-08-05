from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
import logging
from typing import Any

from shared.chromie_contracts.interaction import InteractionResponse, SkillRequest


logger = logging.getLogger("chromie-orchestrator")


@dataclass(frozen=True, slots=True)
class RuntimeReadyGreetingPolicy:
    """Bounded startup-orientation policy.

    ``enabled`` remains the compatibility lifecycle switch.  Non-verbal
    orientation and startup speech are independent choices: maintained profiles
    prefer one subtle untargeted orientation and no speech.
    """

    enabled: bool
    audio_input_mode: str
    audio_output_mode: str
    timeout_ms: int
    orientation_enabled: bool = False
    orientation_timeout_ms: int = 5000
    speech_enabled: bool = False


async def execute_default_runtime_ready_orientation(
    interaction_runtime: Any,
    *,
    enable_soridormi_skills: bool,
    social_attention_mode: str,
) -> dict[str, Any]:
    """Execute one quiet, untargeted, capability-grounded wake orientation.

    Startup has no user turn and no perception evidence. Only the maintained
    neutral Social Attention capabilities below may be attempted, with
    provider-declared schemas and no target. Failure remains silent and
    fail-open; it never produces body-failure speech or an observation claim.
    """

    if not enable_soridormi_skills:
        return {"status": "skipped", "reason": "soridormi_skills_disabled"}
    if social_attention_mode != "on":
        return {"status": "skipped", "reason": "social_attention_not_on"}

    candidates = (
        (
            "soridormi.express_attention",
            {"style": "neutral", "duration_s": 1.2, "hold_fraction": 0.2},
        ),
        ("soridormi.blink_eyes", {"count": 1}),
    )
    reasons: list[str] = []
    for capability_id, args in candidates:
        try:
            await interaction_runtime.ensure_skill_definitions([capability_id])
            definition = interaction_runtime.skill_definition(capability_id)
            behavior_domains = {
                str(value).strip()
                for value in definition.metadata.get("behavior_domains", [])
                if str(value).strip()
            }
            if not definition.available:
                reasons.append(f"{capability_id}:unavailable")
                continue
            if definition.requires_confirmation:
                reasons.append(f"{capability_id}:requires_confirmation")
                continue
            if "social_attention" not in behavior_domains:
                reasons.append(f"{capability_id}:not_social_attention")
                continue

            response = InteractionResponse(
                skills=[
                    SkillRequest(
                        capability_id=capability_id,
                        args=args,
                        timing="parallel",
                        timeout_ms=min(5000, definition.timeout_ms),
                        metadata={
                            "source": "runtime_ready_orientation",
                            "startup_orientation": True,
                            "auxiliary_social_attention": True,
                            "untargeted": True,
                        },
                    )
                ],
                metadata={
                    "source": "runtime_ready_orientation",
                    "startup_orientation": True,
                    "suppress_body_failure_speech": True,
                },
            )
            execution = await interaction_runtime.execute(
                response,
                session_id=None,
            )
            return {
                "status": execution.status,
                "capability_id": capability_id,
                "reason": (
                    "completed"
                    if execution.status == "completed"
                    else "provider_result"
                ),
            }
        except Exception as exc:
            reasons.append(f"{capability_id}:{type(exc).__name__}")
            logger.info(
                "Runtime ready orientation candidate unavailable: "
                "capability_id=%s error_type=%s error=%s",
                capability_id,
                type(exc).__name__,
                exc,
            )
    return {
        "status": "skipped",
        "reason": ",".join(reasons) or "no_eligible_orientation_capability",
    }


class RuntimeReadyGreetingCoordinator:
    """Own startup orientation and optional greeting lifecycle.

    The coordinator does not interpret a room, select a target, or claim an
    observation.  It may invoke one injected, already-bounded untargeted
    orientation callback.  Speech remains an explicit operator opt-in and keeps
    the existing playback-start/completion barrier when enabled.
    """

    def __init__(
        self,
        *,
        policy: RuntimeReadyGreetingPolicy,
        generate_greeting: Callable[[], Awaitable[tuple[str, str]]],
        is_valid_text: Callable[[str], bool],
        schedule_text: Callable[[str], Awaitable[Mapping[str, Any]]],
        playback_start_key: Callable[[int, int, str | None], tuple[int, int, str | None]],
        playback_start_waiters: Mapping[
            tuple[int, int, str | None],
            asyncio.Future[bool],
        ],
        next_playback_order: Callable[[], int],
        execute_orientation: Callable[[], Awaitable[Mapping[str, Any]]] | None = None,
    ) -> None:
        self._policy = policy
        self._generate_greeting = generate_greeting
        self._is_valid_text = is_valid_text
        self._schedule_text = schedule_text
        self._playback_start_key = playback_start_key
        self._playback_start_waiters = playback_start_waiters
        self._next_playback_order = next_playback_order
        self._execute_orientation = execute_orientation

    async def _orient(self) -> None:
        if not self._policy.orientation_enabled or self._execute_orientation is None:
            logger.info("Runtime ready non-verbal orientation disabled")
            return
        timeout_s = max(0.001, self._policy.orientation_timeout_ms / 1000.0)
        try:
            result = await asyncio.wait_for(
                self._execute_orientation(),
                timeout=timeout_s,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "Runtime ready orientation timed out after timeout_ms=%s; "
                "opening the microphone anyway",
                self._policy.orientation_timeout_ms,
            )
            return
        except Exception as exc:
            logger.warning(
                "Runtime ready orientation failed open: error_type=%s error=%s",
                type(exc).__name__,
                exc,
            )
            return
        logger.info(
            "Runtime ready orientation finished: status=%s capability_id=%s reason=%s",
            result.get("status") or "unknown",
            result.get("capability_id") or "none",
            result.get("reason") or "none",
        )

    async def announce(self) -> None:
        if not self._policy.enabled:
            logger.info("Runtime ready orientation disabled")
            return
        if (
            self._policy.audio_input_mode != "device"
            or self._policy.audio_output_mode != "device"
        ):
            logger.info(
                "Runtime ready orientation skipped: input_mode=%s output_mode=%s",
                self._policy.audio_input_mode,
                self._policy.audio_output_mode,
            )
            return

        await self._orient()

        if not self._policy.speech_enabled:
            logger.info(
                "Runtime ready orientation is silent; live microphone turns are enabled"
            )
            return

        text, source = await self._generate_greeting()
        if not self._is_valid_text(text):
            logger.warning(
                "Runtime ready greeting skipped because no valid text was produced"
            )
            return

        logger.info(
            "Runtime ready greeting scheduled: source=%s text=%r",
            source,
            text,
        )
        scheduled = await self._schedule_text(text)
        if scheduled.get("scheduled") is not True:
            logger.warning(
                "Runtime ready greeting could not be scheduled: reason=%s",
                scheduled.get("reason") or "unknown",
            )
            return

        generation = int(scheduled["generation"])
        first_order = int(scheduled["order"])
        last_order = int(scheduled.get("last_order", first_order))
        first_key = self._playback_start_key(generation, first_order, None)
        first_waiter = self._playback_start_waiters.get(first_key)
        timeout_s = self._policy.timeout_ms / 1000.0
        deadline = asyncio.get_running_loop().time() + timeout_s

        if first_waiter is None:
            logger.warning("Runtime ready greeting lost its playback-start waiter")
            return

        try:
            started = await asyncio.wait_for(
                asyncio.shield(first_waiter),
                timeout=timeout_s,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "Runtime ready greeting did not begin playback within timeout_ms=%s; "
                "opening the microphone anyway",
                self._policy.timeout_ms,
            )
            return

        if not started:
            logger.warning(
                "Runtime ready greeting synthesis completed without starting playback; "
                "opening the microphone anyway"
            )
            return

        while self._next_playback_order() <= last_order:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                logger.warning(
                    "Runtime ready greeting playback did not finish within timeout_ms=%s; "
                    "opening the microphone anyway",
                    self._policy.timeout_ms,
                )
                return
            await asyncio.sleep(min(0.05, remaining))

        logger.info(
            "Runtime ready greeting completed; live microphone turns are enabled"
        )
