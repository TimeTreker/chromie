from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Callable, Awaitable, Any

import aiohttp
import websockets

logger = logging.getLogger(__name__)


class ServiceReadinessGate:
    """Waits until core services can actually serve a turn before Chromie interacts.

    Reachable is not ready: a cold TTS engine accepted the connection but needed 7.7 s for
    its first audio, so the first reply was not played (live 2026-10-12). Each service owns
    its readiness; TTS reports ``provider_health.ready`` once its workers are warm.
    """

    def __init__(
        self,
        *,
        asr_url: str,
        tts_url: str,
        speaker_id: str = "default",
        get_http_session: Callable[[], Awaitable[aiohttp.ClientSession]] | None = None,
        agent_url: str | None = None,
        enable_agent: bool = False,
    ):
        self.asr_url = asr_url
        self.tts_url = tts_url
        self.speaker_id = speaker_id
        self.get_http_session = get_http_session
        self.agent_url = agent_url.rstrip("/") if agent_url else None
        self.enable_agent = enable_agent
        self.tts_provider_health: dict[str, Any] = {}
        self.asr_ws: Any = None

    async def wait_until_ready(
        self, interval: float = 2.0, *, require_asr: bool = True, deadline_s: float | None = None,
    ):
        """Return once every required service is ready; text hosts pass require_asr=False."""
        deadline = None if deadline_s is None else time.monotonic() + deadline_s
        while True:
            try:
                asr_ws = await self._check_asr() if require_asr else None
                await self._check_tts()
                await self._check_optional_http()
                logger.info("All required Chromie services are ready")
                return asr_ws
            except Exception as exc:
                logger.warning("Service readiness check failed: %s", exc)
                if deadline is not None and time.monotonic() >= deadline:
                    raise RuntimeError(f"Chromie services did not become ready: {exc}") from exc
                await asyncio.sleep(interval)

    async def _check_asr(self):
        logger.info("Checking ASR websocket: %s", self.asr_url)
        return await websockets.connect(
            self.asr_url,
            max_size=10**7,
            open_timeout=10,
            ping_interval=20,
            ping_timeout=20,
        )

    async def _check_tts(self) -> None:
        logger.info("Checking TTS readiness: %s", self.tts_url)
        async with websockets.connect(
            self.tts_url, open_timeout=10, ping_interval=20, ping_timeout=20,
        ) as ws:
            await ws.send(json.dumps({"type": "health"}))
            payload = json.loads(await asyncio.wait_for(ws.recv(), timeout=5.0))
        health = payload.get("provider_health") if isinstance(payload, dict) else None
        if not isinstance(health, dict) or payload.get("type") != "pong":
            raise RuntimeError("TTS provider health is missing")
        # The provider owns readiness; without that report a live worker is the floor.
        ready = health["ready"] if "ready" in health else health.get("worker_process_alive")
        if ready is not True:
            raise RuntimeError("TTS provider is not ready")
        self.tts_provider_health = health

    async def _check_optional_http(self) -> None:
        if not self.get_http_session:
            return
        session = await self.get_http_session()
        if self.enable_agent and self.agent_url:
            async with session.get(f"{self.agent_url}/health", timeout=aiohttp.ClientTimeout(total=3)) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"Agent health HTTP {resp.status}")
