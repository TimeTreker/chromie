from __future__ import annotations

import json
import logging
import os

import websockets

logger = logging.getLogger(__name__)


class ASRClient:
    """Tiny helper for the current Chromie ASR websocket protocol.

    The existing ASR service accepts raw PCM16 mono audio bytes and returns a JSON
    final message such as {"type": "final", "text": "..."}.
    """

    def __init__(self, url: str, timeout_ms: int | None = None):
        self.url = url
        resolved_timeout_ms = (
            int(os.getenv("ORCH_ASR_TIMEOUT_MS", "30000"))
            if timeout_ms is None
            else timeout_ms
        )
        self.timeout_s = max(0.001, resolved_timeout_ms / 1000.0)
        self.ws = None

    async def connect(self):
        self.ws = await websockets.connect(
            self.url,
            max_size=10**7,
            open_timeout=10,
            ping_interval=20,
            ping_timeout=20,
        )
        return self.ws

    async def ensure_connected(self):
        if self.ws is None or getattr(self.ws, "close_code", None) is not None:
            await self.connect()
        return self.ws

    async def transcribe(self, audio: bytes, timeout: float | None = None) -> dict:
        import asyncio

        ws = await self.ensure_connected()
        await ws.send(audio)
        raw = await asyncio.wait_for(
            ws.recv(),
            timeout=self.timeout_s if timeout is None else timeout,
        )
        return json.loads(raw)

    async def close(self):
        if self.ws is not None:
            await self.ws.close()
            self.ws = None
