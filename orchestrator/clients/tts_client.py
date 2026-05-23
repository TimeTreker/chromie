from __future__ import annotations

import json
import logging

import websockets

logger = logging.getLogger(__name__)


class TTSClient:
    """One-shot client for Chromie's TTS websocket protocol."""

    def __init__(self, url: str, default_sample_rate: int = 44100):
        self.url = url
        self.default_sample_rate = default_sample_rate

    async def synthesize(self, *, text: str, speaker_id: str, request_id: str) -> tuple[bytes, int]:
        async with websockets.connect(
            self.url,
            max_size=10**7,
            open_timeout=10,
            ping_interval=20,
            ping_timeout=20,
        ) as ws:
            await ws.send(
                json.dumps(
                    {
                        "type": "synthesize_stream",
                        "text": text,
                        "speaker_id": speaker_id,
                        "request_id": request_id,
                    },
                    ensure_ascii=False,
                )
            )
            audio = bytearray()
            sample_rate = self.default_sample_rate
            async for msg in ws:
                if isinstance(msg, bytes):
                    audio.extend(msg)
                    continue
                data = json.loads(msg)
                msg_type = data.get("type")
                if msg_type == "start":
                    sample_rate = int(data.get("sample_rate") or sample_rate)
                elif msg_type == "error":
                    raise RuntimeError(data.get("message") or "TTS error")
                elif msg_type == "end":
                    return bytes(audio), sample_rate
            raise RuntimeError("TTS websocket closed before end message")
