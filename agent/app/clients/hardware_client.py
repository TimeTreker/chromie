from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger("chromie.agent.hardware")


class HardwareClient:
    """Optional client for a host hardware daemon.

    The agent service does not execute hardware by default. The host orchestrator
    should normally execute returned actions. This client is kept for future
    diagnostics or dry-run validation endpoints.
    """

    def __init__(self, base_url: str, timeout_ms: int = 1000) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = httpx.Timeout(timeout_ms / 1000.0)

    async def health(self) -> dict[str, Any] | None:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.base_url}/health")
                response.raise_for_status()
                return response.json()
        except Exception as exc:  # noqa: BLE001
            logger.debug("hardware health unavailable: %s", exc)
            return None
