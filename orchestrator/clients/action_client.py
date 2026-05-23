from __future__ import annotations

import logging

import aiohttp

try:
    from schemas.action import ActionCommand, ActionResult
except ImportError:  # pragma: no cover
    from orchestrator.schemas.action import ActionCommand, ActionResult

logger = logging.getLogger(__name__)


class ActionClient:
    def __init__(self, base_url: str, timeout_ms: int = 5000):
        self.base_url = base_url.rstrip("/")
        self.timeout_ms = max(100, int(timeout_ms))

    async def execute(self, session: aiohttp.ClientSession, action: ActionCommand) -> ActionResult:
        timeout = aiohttp.ClientTimeout(total=(action.timeout_ms or self.timeout_ms) / 1000.0)
        async with session.post(
            f"{self.base_url}/actions",
            json=action.model_dump(mode="json"),
            timeout=timeout,
        ) as resp:
            body = await resp.text()
            if resp.status != 200:
                return ActionResult(
                    id=action.id,
                    target=action.target,
                    type=action.type,
                    status="failed",
                    message=f"HTTP {resp.status}: {body[:500]}",
                )
            return ActionResult.model_validate_json(body)

    async def health(self, session: aiohttp.ClientSession) -> dict:
        timeout = aiohttp.ClientTimeout(total=self.timeout_ms / 1000.0)
        async with session.get(f"{self.base_url}/health", timeout=timeout) as resp:
            return await resp.json()
