from __future__ import annotations

import logging
from typing import Any

import aiohttp

try:
    from schemas.agent import AgentRequest, AgentResult
    from schemas.route import RouteDecision
except ImportError:  # pragma: no cover
    from orchestrator.schemas.agent import AgentRequest, AgentResult
    from orchestrator.schemas.route import RouteDecision

logger = logging.getLogger(__name__)


class AgentClient:
    def __init__(self, base_url: str, timeout_ms: int = 3000):
        self.base_url = base_url.rstrip("/")
        self.timeout_ms = max(100, int(timeout_ms))

    async def run(
        self,
        session: aiohttp.ClientSession,
        *,
        text: str,
        route_decision: RouteDecision,
        sid: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> AgentResult:
        req = AgentRequest(
            sid=sid,
            text=text,
            route_decision=route_decision,
            context=context or {},
        )
        timeout = aiohttp.ClientTimeout(total=self.timeout_ms / 1000.0)
        async with session.post(
            f"{self.base_url}/run",
            json=req.model_dump(mode="json"),
            timeout=timeout,
        ) as resp:
            body = await resp.text()
            if resp.status != 200:
                raise RuntimeError(f"Agent returned HTTP {resp.status}: {body[:500]}")
            return AgentResult.model_validate_json(body)

    async def health(self, session: aiohttp.ClientSession) -> dict[str, Any]:
        timeout = aiohttp.ClientTimeout(total=self.timeout_ms / 1000.0)
        async with session.get(f"{self.base_url}/health", timeout=timeout) as resp:
            return await resp.json()
