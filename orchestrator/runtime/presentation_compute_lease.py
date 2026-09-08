"""Host-owned accelerator lease for real speech presentation."""

from __future__ import annotations

import asyncio
import inspect
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

import aiohttp

logger = logging.getLogger(__name__)

SpeechScheduler = Callable[[dict[str, Any]], dict[str, Any] | Awaitable[dict[str, Any]]]


class PresentationComputeLeaseError(RuntimeError):
    """The configured compute provider could not honor a Host resource decision."""


@dataclass(frozen=True)
class PresentationComputeLeaseToken:
    epoch: int


class PresentationComputeLease:
    """Pause/resume provider compute around Vocal delivery without owning semantics.

    The epoch makes revocation race-safe.  Once a new foreground input revokes a
    lease, the old speech task may finish later but its stale token cannot resume
    or release a newer lease.
    """

    def __init__(
        self,
        *,
        enabled: bool,
        control_url: str,
        mode: str = "in_place",
        timeout_ms: int = 2000,
    ) -> None:
        self.enabled = bool(enabled)
        self.control_url = control_url.rstrip("/")
        self.mode = str(mode or "in_place").strip()
        self.timeout_ms = max(100, int(timeout_ms))
        self._lock = asyncio.Lock()
        self._epoch = 0
        self._active_epoch: int | None = None
        self._holders = 0
        if self.enabled and not self.control_url:
            raise ValueError("presentation compute lease requires control_url")
        if self.mode != "in_place":
            raise ValueError(f"unsupported presentation compute lease mode: {self.mode!r}")

    @property
    def active(self) -> bool:
        return self._active_epoch is not None

    async def _post_control(self, action: str, payload: dict[str, Any]) -> None:
        timeout = aiohttp.ClientTimeout(total=self.timeout_ms / 1000.0)
        async with aiohttp.ClientSession(timeout=timeout, trust_env=False) as session:
            async with session.post(
                f"{self.control_url}/{action}",
                json=payload,
            ) as response:
                body = await response.json(content_type=None)
                if response.status >= 400 or not isinstance(body, dict) or body.get("status") != "ok":
                    raise PresentationComputeLeaseError(
                        f"{action} failed status={response.status} body={body!r}"
                    )

    async def acquire(self, *, reason: str) -> PresentationComputeLeaseToken | None:
        if not self.enabled:
            return None
        async with self._lock:
            if self._active_epoch is None:
                await self._post_control(
                    "pause_generation",
                    {"mode": self.mode},
                )
                self._epoch += 1
                self._active_epoch = self._epoch
                self._holders = 0
                logger.info(
                    "presentation_compute_lease_acquired epoch=%s reason=%s",
                    self._active_epoch,
                    reason,
                )
            self._holders += 1
            return PresentationComputeLeaseToken(epoch=self._active_epoch)

    async def release(
        self,
        token: PresentationComputeLeaseToken | None,
        *,
        reason: str,
    ) -> bool:
        if not self.enabled or token is None:
            return False
        async with self._lock:
            if token.epoch != self._active_epoch:
                return False
            self._holders = max(0, self._holders - 1)
            if self._holders:
                return False
            await self._post_control(
                "continue_generation",
                {"torch_empty_cache": False},
            )
            released_epoch = self._active_epoch
            self._active_epoch = None
            logger.info(
                "presentation_compute_lease_released epoch=%s reason=%s",
                released_epoch,
                reason,
            )
            return True

    async def revoke(self, *, reason: str) -> bool:
        """Resume provider compute before a newly admitted foreground turn runs."""

        if not self.enabled:
            return False
        async with self._lock:
            if self._active_epoch is None:
                return False
            await self._post_control(
                "continue_generation",
                {"torch_empty_cache": False},
            )
            revoked_epoch = self._active_epoch
            self._active_epoch = None
            self._holders = 0
            self._epoch += 1
            logger.info(
                "presentation_compute_lease_revoked epoch=%s reason=%s",
                revoked_epoch,
                reason,
            )
            return True

    def wrap_speech_scheduler(self, scheduler: SpeechScheduler) -> SpeechScheduler:
        if not self.enabled:
            return scheduler

        async def schedule(args: dict[str, Any]) -> dict[str, Any]:
            leased_args = dict(args)
            metadata = dict(leased_args.get("metadata") or {})
            # Hold the conservative first production lease through voice release.
            # Barge-in revocation makes this non-blocking for new foreground input.
            metadata["wait_for_voice_release"] = True
            metadata["presentation_compute_lease"] = "sglang_engine"
            leased_args["metadata"] = metadata
            token = await self.acquire(reason="vocal_delivery")
            try:
                result = scheduler(leased_args)
                if inspect.isawaitable(result):
                    result = await result
                if not isinstance(result, dict):
                    raise TypeError("speech scheduler must return a dictionary")
                return result
            finally:
                await self.release(token, reason="vocal_delivery_terminal")

        return schedule
