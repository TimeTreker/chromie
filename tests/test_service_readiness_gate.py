"""Readiness means a service can serve the turn, not that it accepts a connection."""
from __future__ import annotations

import json

import pytest
import websockets

from orchestrator.readiness import ServiceReadinessGate


async def _serve_tts(health_reports):
    """Fake TTS: each health request answers with the next provider_health report."""
    reports = list(health_reports)

    async def handler(ws):
        async for message in ws:
            assert json.loads(message)["type"] == "health"
            health = reports.pop(0) if len(reports) > 1 else reports[0]
            await ws.send(json.dumps({"type": "pong", "service": "tts", "provider_health": health}))

    server = await websockets.serve(handler, "127.0.0.1", 0)
    return server, f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}"


@pytest.mark.asyncio
async def test_interaction_waits_for_the_tts_provider_to_report_ready():
    """Live 2026-10-12: TTS accepted the connection while its first audio took 7.7 s.
    The provider owns readiness (warm workers); the Host waits for it, never warms it."""
    warming = {"ready": False, "worker_process_alive": True, "worker_warmed": False}
    warm = {"ready": True, "worker_process_alive": True, "worker_warmed": True,
            "worker": {"warmed": True, "warmup_seconds": {"chromie_en": 2.1}}}
    server, url = await _serve_tts([warming, warming, warm])
    try:
        gate = ServiceReadinessGate(asr_url="unused", tts_url=url)
        await gate.wait_until_ready(interval=0.01, require_asr=False, deadline_s=10.0)
        assert gate.tts_provider_health == warm
    finally:
        server.close()

    server, url = await _serve_tts([warming])
    try:
        with pytest.raises(RuntimeError, match="did not become ready"):
            await ServiceReadinessGate(asr_url="unused", tts_url=url).wait_until_ready(
                interval=0.01, require_asr=False, deadline_s=0.3)
    finally:
        server.close()


@pytest.mark.asyncio
async def test_a_provider_without_a_ready_report_needs_a_live_worker():
    server, url = await _serve_tts([{"worker_process_alive": False}])
    try:
        with pytest.raises(RuntimeError, match="did not become ready"):
            await ServiceReadinessGate(asr_url="unused", tts_url=url).wait_until_ready(
                interval=0.01, require_asr=False, deadline_s=0.3)
    finally:
        server.close()
    server, url = await _serve_tts([{"worker_process_alive": True}])
    try:
        await ServiceReadinessGate(asr_url="unused", tts_url=url).wait_until_ready(
            interval=0.01, require_asr=False, deadline_s=5.0)
    finally:
        server.close()
