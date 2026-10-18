from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
import logging
import re
from typing import Any
import uuid

from shared.chromie_contracts.interaction import InteractionResponse, CapabilityRequest
from shared.chromie_contracts.social_cognition import SocialStartupGreetingRequest


logger = logging.getLogger("chromie-orchestrator")


def _fit_startup_args_to_capability_schema(
    args: Mapping[str, Any],
    input_schema: Mapping[str, Any],
) -> dict[str, Any]:
    """Clamp bounded numeric startup preferences to the provider contract.

    Startup may prefer a subtle duration, but the provider owns the legal input
    range. Reading the already-resolved CapabilityDefinition avoids duplicating
    provider minima in Host code or tests.
    """

    fitted = dict(args)
    properties = input_schema.get("properties")
    if not isinstance(properties, Mapping):
        return fitted
    for name, value in list(fitted.items()):
        schema = properties.get(name)
        if not isinstance(schema, Mapping) or isinstance(value, bool):
            continue
        if not isinstance(value, (int, float)):
            continue
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if isinstance(minimum, (int, float)) and not isinstance(minimum, bool):
            value = max(value, minimum)
        if isinstance(maximum, (int, float)) and not isinstance(maximum, bool):
            value = min(value, maximum)
        fitted[name] = value
    return fitted


@dataclass(frozen=True, slots=True)
class RuntimeReadyGreetingPolicy:
    """Bounded startup-orientation policy.

    Non-verbal startup orientation and optional startup speech are independent
    lifecycle choices. Startup orientation is baseline Activity/liveliness, not
    Social Attention, because no social interaction anchor exists yet.
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
    enable_soridormi_capabilities: bool,
) -> dict[str, Any]:
    """Execute one quiet, untargeted, capability-grounded startup orientation.

    Startup has no user turn and no social interaction anchor, so this is
    baseline lifecycle Activity rather than Social Attention. Only subtle,
    untargeted expression/orientation capabilities may be attempted. Failure
    remains silent and fail-open; it never produces body-failure speech or an
    observation claim.
    """

    if not enable_soridormi_capabilities:
        return {"status": "skipped", "reason": "soridormi_capabilities_disabled"}

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
            await interaction_runtime.ensure_capability_definitions([capability_id])
            definition = interaction_runtime.capability_definition(capability_id)
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
            if not behavior_domains.intersection(
                {"facial_expression", "posture_expression", "orientation"}
            ):
                reasons.append(f"{capability_id}:not_startup_orientation")
                continue

            fitted_args = _fit_startup_args_to_capability_schema(
                args,
                definition.input_schema,
            )
            response = InteractionResponse(
                capabilities=[
                    CapabilityRequest(
                        capability_id=capability_id,
                        args=fitted_args,
                        timing="parallel",
                        timeout_ms=min(5000, definition.timeout_ms),
                        metadata={
                            "source": "runtime_ready_orientation",
                            "startup_orientation": True,
                            "execution_lane": "activity",
                            "execution_role": "startup_orientation",
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
            dispatch = await interaction_runtime.submit_response(
                response,
                session_id=None,
            )
            execution = await interaction_runtime.wait_dispatch(dispatch)
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


def runtime_ready_greeting_time_context(
    local_now: datetime | None = None,
) -> dict[str, str]:
    observed = local_now or datetime.now().astimezone()
    if observed.tzinfo is None:
        observed = observed.astimezone()
    hour = observed.hour
    if 5 <= hour < 11:
        local_period = "morning"
    elif 11 <= hour < 14:
        local_period = "midday"
    elif 14 <= hour < 18:
        local_period = "afternoon"
    elif 18 <= hour < 23:
        local_period = "evening"
    else:
        local_period = "late_night"
    offset = observed.strftime("%z")
    if len(offset) == 5:
        offset = f"{offset[:3]}:{offset[3:]}"
    return {
        "local_iso": observed.isoformat(timespec="minutes"),
        "local_period": local_period,
        "timezone": str(observed.tzname() or "local"),
        "utc_offset": offset,
        "weekday": observed.strftime("%A"),
    }


def validate_runtime_ready_greeting_completion(text: str) -> str:
    if not re.search(r"[。！？!?]$", str(text or "").strip()):
        raise RuntimeError(
            "runtime ready greeting is not a complete punctuated sentence"
        )
    return text


async def generate_runtime_ready_greeting(host: Any) -> tuple[str, str]:
    """Return the startup line and its source; Social Cognition authors any words.

    The Host is not a response author: it supplies trusted clock facts and the
    owner-approved Mind, then only validates delivery bounds. An owner-configured
    text is the owner's own wording and is played as given.
    """
    language = host.runtime_ready_greeting_language
    try:
        configured = host._validate_spoken_text_contract(
            host.runtime_ready_greeting_text,
            purpose="configured runtime ready greeting",
            max_chars=24,
            one_sentence=True,
            language=language,
        )
    except RuntimeError:
        configured = ""
    if configured:
        return configured, "configured"

    try:
        if not host.enable_agent:
            raise RuntimeError("Social Cognition is unavailable without the Agent")
        request = SocialStartupGreetingRequest(
            request_id=f"startup-greeting:{uuid.uuid4().hex}",
            language=language,
            max_chars=24,
            local_time=runtime_ready_greeting_time_context(),
            context={"mind": host.mind.context()},
        )
        session = await host.get_http_session()
        resolution = await host.agent_client.resolve_startup_greeting(
            session,
            request=request,
            timeout_ms=host.runtime_ready_greeting_generation_timeout_ms,
        )
        if resolution.disposition == "silence":
            logger.info(
                "Runtime ready greeting: Social Cognition chose silence: %s",
                resolution.reason_summary,
            )
            return "", "social_cognition:silence"
        generated = host._validate_spoken_text_contract(
            resolution.text,
            purpose="runtime ready greeting",
            max_chars=24,
            one_sentence=True,
            language=language,
        )
        validate_runtime_ready_greeting_completion(generated)
        return generated, "social_cognition"
    except Exception as exc:
        logger.warning("Runtime ready greeting from Social Cognition failed: %s", exc)
    try:
        fallback = host._validate_spoken_text_contract(
            host.runtime_ready_greeting_fallback_text,
            purpose="runtime ready greeting fallback",
            max_chars=24,
            one_sentence=True,
            language=language,
        )
    except RuntimeError as fallback_exc:
        logger.warning("Runtime ready greeting fallback rejected: %s", fallback_exc)
        return "", "unavailable"
    return fallback, "fallback"


def build_runtime_ready_greeting_coordinator(
    host: Any,
) -> RuntimeReadyGreetingCoordinator:
    async def schedule_text(text: str) -> dict[str, Any]:
        return await host.schedule_tts_text(text, session_id=None)

    orientation_enabled = bool(
        getattr(host, "enable_soridormi_capabilities", False)
    )

    async def execute_orientation() -> dict[str, Any]:
        return await execute_default_runtime_ready_orientation(
            host.interaction_runtime,
            enable_soridormi_capabilities=getattr(
                host, "enable_soridormi_capabilities", False
            ),
        )

    return RuntimeReadyGreetingCoordinator(
        policy=RuntimeReadyGreetingPolicy(
            enabled=host.runtime_ready_greeting_enabled,
            audio_input_mode=host.audio_input_mode,
            audio_output_mode=host.audio_output_mode,
            timeout_ms=host.runtime_ready_greeting_timeout_ms,
            orientation_enabled=orientation_enabled,
            orientation_timeout_ms=min(
                5000, host.runtime_ready_greeting_timeout_ms
            ),
            speech_enabled=bool(
                getattr(
                    getattr(
                        getattr(host, "host_settings", None),
                        "playback",
                        None,
                    ),
                    "ready_greeting_speech_enabled",
                    getattr(
                        host,
                        "runtime_ready_greeting_speech_enabled",
                        False,
                    ),
                )
            ),
        ),
        generate_greeting=host._generate_runtime_ready_greeting,
        is_valid_text=host.is_valid_tts_text,
        schedule_text=schedule_text,
        playback_start_key=host.playback_start_key,
        playback_start_waiters=host.playback_delivery.playback_start_waiters,
        next_playback_order=lambda: host.playback_delivery.next_playback_order,
        execute_orientation=execute_orientation,
    )
