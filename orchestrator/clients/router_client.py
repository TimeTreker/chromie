from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

try:
    from schemas.route import RouteDecision, RouteRequest
except ImportError:  # pragma: no cover
    from orchestrator.schemas.route import RouteDecision, RouteRequest

logger = logging.getLogger(__name__)


class RouterClient:
    def __init__(self, base_url: str, timeout_ms: int = 2000):
        self.base_url = base_url.rstrip("/")
        self.timeout_ms = max(50, int(timeout_ms))

    async def route(
        self,
        session: aiohttp.ClientSession,
        *,
        text: str,
        sid: str | None = None,
        language: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> RouteDecision:
        req = RouteRequest(sid=sid, text=text, language=language, context=context or {})
        timeout = aiohttp.ClientTimeout(total=self.timeout_ms / 1000.0)
        url = f"{self.base_url}/route"
        async with session.post(url, json=req.model_dump(mode="json"), timeout=timeout) as resp:
            body = await resp.text()
            if resp.status != 200:
                raise RuntimeError(f"Router returned HTTP {resp.status}: {body[:500]}")
            return RouteDecision.model_validate_json(body)

    async def health(self, session: aiohttp.ClientSession) -> dict[str, Any]:
        timeout = aiohttp.ClientTimeout(total=self.timeout_ms / 1000.0)
        async with session.get(f"{self.base_url}/health", timeout=timeout) as resp:
            return await resp.json()
