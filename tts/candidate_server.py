"""WebSocket service shared by isolated TTS candidate images."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import re
import uuid
from typing import Any

import websockets

from provider import TTSAudioChunk, TTSSynthesisCompleted, TTSSynthesisRequest
from provider_impl import create_provider


logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("chromie.tts.candidate")

HOST = os.getenv("TTS_HOST", "0.0.0.0")
PORT = int(os.getenv("TTS_PORT", "5000"))
provider = create_provider()
configured_provider = str(os.getenv("TTS_PROVIDER") or "").strip().lower()
if configured_provider and configured_provider != provider.capabilities.provider_id:
    raise RuntimeError(
        "TTS_PROVIDER does not match the provider image: "
        f"{configured_provider!r} != {provider.capabilities.provider_id!r}"
    )


async def send_json(ws: Any, payload: dict[str, Any]) -> None:
    await ws.send(json.dumps(payload, ensure_ascii=False))


def normalized_request(data: dict[str, Any]) -> TTSSynthesisRequest:
    text = re.sub(r"\s+", " ", str(data.get("text") or "")).strip()
    if not text or not any(ch.isalnum() or "\u4e00" <= ch <= "\u9fff" for ch in text):
        raise ValueError("text must contain speakable content")
    speaker_id = str(data.get("speaker_id") or "default").strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", speaker_id):
        raise ValueError("invalid speaker_id")
    return TTSSynthesisRequest(
        request_id=str(data.get("request_id") or f"tts-{uuid.uuid4().hex}"),
        text=text,
        speaker_id=speaker_id,
        language_hint=(str(data.get("language_hint")).strip() or None)
        if data.get("language_hint") is not None
        else None,
    )


async def synthesize(ws: Any, request: TTSSynthesisRequest) -> None:
    capabilities = provider.capabilities
    await send_json(
        ws,
        {
            "type": "start",
            "request_id": request.request_id,
            "sample_rate": capabilities.sample_rates[0],
            "format": "pcm_s16le",
            "channels": 1,
            "provider": capabilities.as_dict(),
        },
    )
    completed: TTSSynthesisCompleted | None = None
    async for event in provider.synthesize_stream(request):
        if isinstance(event, TTSAudioChunk):
            await ws.send(event.pcm)
        elif isinstance(event, TTSSynthesisCompleted):
            completed = event
    if completed is None:
        raise RuntimeError("provider stream ended without completion metadata")
    await send_json(
        ws,
        {
            "type": "end",
            "request_id": request.request_id,
            "provider": capabilities.as_dict(),
            **dict(completed.metrics),
            "provider_metadata": dict(completed.provider_metadata),
        },
    )


async def synthesize_until_disconnect(ws: Any, request: TTSSynthesisRequest) -> bool:
    synthesis_task = asyncio.create_task(synthesize(ws, request))
    closed_task = asyncio.create_task(ws.wait_closed())
    done, _pending = await asyncio.wait(
        {synthesis_task, closed_task},
        return_when=asyncio.FIRST_COMPLETED,
    )
    if closed_task in done and synthesis_task not in done:
        synthesis_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await synthesis_task
        return False
    closed_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await closed_task
    await synthesis_task
    return True


async def handler(ws: Any) -> None:
    async for raw in ws:
        if not isinstance(raw, str):
            await send_json(ws, {"type": "error", "message": "expected JSON text"})
            continue
        try:
            data = json.loads(raw)
            msg_type = data.get("type")
            if msg_type in {"health", "ping"}:
                await send_json(
                    ws,
                    {
                        "type": "pong",
                        "service": "tts",
                        "provider_contract_version": provider.capabilities.contract_version,
                        "provider": provider.capabilities.as_dict(),
                        "provider_health": dict(await provider.health()),
                        "registered_providers": [provider.capabilities.provider_id],
                        "sample_rate": provider.capabilities.sample_rates[0],
                        "speakers": await provider.list_speakers(),
                    },
                )
            elif msg_type == "list_speakers":
                await send_json(
                    ws,
                    {"type": "speakers", "speakers": await provider.list_speakers()},
                )
            elif msg_type == "synthesize_stream":
                if not await synthesize_until_disconnect(ws, normalized_request(data)):
                    return
            else:
                await send_json(
                    ws,
                    {"type": "error", "message": f"unsupported request type: {msg_type}"},
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Candidate TTS request failed")
            if ws.state.name != "CLOSED":
                await send_json(ws, {"type": "error", "message": str(exc)})


async def main() -> None:
    await provider.start()
    logger.info(
        "Candidate TTS ready provider=%s address=ws://%s:%s",
        provider.capabilities.provider_id,
        HOST,
        PORT,
    )
    try:
        async with websockets.serve(handler, HOST, PORT, max_size=10**7):
            await asyncio.Future()
    finally:
        await provider.stop()


if __name__ == "__main__":
    asyncio.run(main())
