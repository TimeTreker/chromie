from __future__ import annotations

import asyncio
import json
import logging

import websockets

logger = logging.getLogger(__name__)


class ASRClient:
    """Tiny helper for the current Chromie ASR websocket protocol.

    The ASR service accepts raw PCM16 mono audio bytes and returns a JSON final
    message such as {"type": "final", "sequence": 1, "text": "..."}. The
    sequence numbers the utterances sent on one connection.
    """

    def __init__(self, url: str, timeout_ms: int = 30000):
        self.url = url
        self.timeout_s = max(0.001, timeout_ms / 1000.0)
        self.ws = None
        self._sequence = 0

    async def connect(self):
        self.ws = await websockets.connect(
            self.url,
            max_size=10**7,
            open_timeout=10,
            ping_interval=20,
            ping_timeout=20,
        )
        self._sequence = 0
        return self.ws

    async def ensure_connected(self):
        if self.ws is None or getattr(self.ws, "close_code", None) is not None:
            await self.connect()
        return self.ws

    async def transcribe(self, audio: bytes, timeout: float | None = None) -> dict:
        ws = await self.ensure_connected()
        self._sequence += 1
        expected = self._sequence
        completed = False
        try:
            await ws.send(audio)
            raw = await asyncio.wait_for(
                ws.recv(),
                timeout=self.timeout_s if timeout is None else timeout,
            )
            result = json.loads(raw)
            if result.get("sequence") != expected:
                raise RuntimeError(
                    f"ASR reply sequence {result.get('sequence')!r} "
                    f"does not match utterance {expected}"
                )
            completed = True
        finally:
            if not completed:
                # A timed-out or mismatched reply may still arrive later; never
                # read it as the answer to the next utterance.
                await self.close()
        return result

    async def close(self):
        ws, self.ws = self.ws, None
        if ws is not None:
            await ws.close()
