from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
import logging
from typing import Any


logger = logging.getLogger("chromie-orchestrator")


@dataclass(frozen=True, slots=True)
class RuntimeReadyGreetingPolicy:
    enabled: bool
    audio_input_mode: str
    audio_output_mode: str
    timeout_ms: int


class RuntimeReadyGreetingCoordinator:
    """Own startup greeting scheduling and playback barriers.

    Wording generation remains an injected cognitive dependency. The
    coordinator owns only the deterministic Host lifecycle: eligibility,
    scheduling, playback-start observation, bounded completion waiting, and
    fail-open microphone release.
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
    ) -> None:
        self._policy = policy
        self._generate_greeting = generate_greeting
        self._is_valid_text = is_valid_text
        self._schedule_text = schedule_text
        self._playback_start_key = playback_start_key
        self._playback_start_waiters = playback_start_waiters
        self._next_playback_order = next_playback_order

    async def announce(self) -> None:
        if not self._policy.enabled:
            logger.info("Runtime ready greeting disabled")
            return
        if (
            self._policy.audio_input_mode != "device"
            or self._policy.audio_output_mode != "device"
        ):
            logger.info(
                "Runtime ready greeting skipped: input_mode=%s output_mode=%s",
                self._policy.audio_input_mode,
                self._policy.audio_output_mode,
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
