from __future__ import annotations

import asyncio
import json
import logging
from typing import Callable, Awaitable, Any

import aiohttp
import websockets

logger = logging.getLogger(__name__)


class ServiceReadinessGate:
    """Waits until core services are available before opening the microphone."""

    def __init__(
        self,
        *,
        asr_url: str,
        tts_url: str,
        llm_url: str | None = None,
        ollama_model: str | None = None,
        speaker_id: str = "default",
        get_http_session: Callable[[], Awaitable[aiohttp.ClientSession]] | None = None,
        router_url: str | None = None,
        agent_url: str | None = None,
        enable_router: bool = False,
        enable_agent: bool = False,
    ):
        self.asr_url = asr_url
        self.tts_url = tts_url
        self.llm_url = llm_url
        self.ollama_model = ollama_model
        self.speaker_id = speaker_id
        self.get_http_session = get_http_session
        self.router_url = router_url.rstrip("/") if router_url else None
        self.agent_url = agent_url.rstrip("/") if agent_url else None
        self.enable_router = enable_router
        self.enable_agent = enable_agent

    async def wait_until_ready(self, interval: float = 2.0):
        while True:
            try:
                asr_ws = await self._check_asr()
                await self._check_tts()
                await self._check_optional_http()
                logger.info("All required Chromie services are ready")
                return asr_ws
            except Exception as exc:
                logger.warning("Service readiness check failed: %s", exc)
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
        logger.info("Checking TTS websocket: %s", self.tts_url)
        async with websockets.connect(self.tts_url, open_timeout=10, ping_interval=20, ping_timeout=20) as ws:
            await ws.send(json.dumps({"type": "ping", "speaker_id": self.speaker_id}))
            # Some TTS builds may not answer ping. A successful connection is enough.
            try:
                await asyncio.wait_for(ws.recv(), timeout=2.0)
            except asyncio.TimeoutError:
                pass

    async def _check_optional_http(self) -> None:
        if not self.get_http_session:
            return
        session = await self.get_http_session()
        if self.llm_url:
            # Ollama generate endpoint may not support GET; skip strict LLM check here.
            logger.info("LLM URL configured: %s model=%s", self.llm_url, self.ollama_model)
        if self.enable_router and self.router_url:
            async with session.get(f"{self.router_url}/health", timeout=aiohttp.ClientTimeout(total=3)) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"Router health HTTP {resp.status}")
        if self.enable_agent and self.agent_url:
            async with session.get(f"{self.agent_url}/health", timeout=aiohttp.ClientTimeout(total=3)) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"Agent health HTTP {resp.status}")
