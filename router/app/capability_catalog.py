from __future__ import annotations

import logging
from typing import Any

import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger("chromie.router.capability_catalog")


class CapabilityCatalogResult(BaseModel):
    query: str = ""
    matched: bool = False
    suggested_route: str = "chat"
    suggested_agents: list[str] = Field(default_factory=list)
    matches: list[dict[str, Any]] = Field(default_factory=list)
    catalog_version: int = 0
    live_refresh_error: str | None = None


class CapabilityCatalogClient:
    def __init__(self, base_url: str, *, timeout_ms: int = 600, limit: int = 8) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_s = max(0.05, int(timeout_ms) / 1000.0)
        self.limit = max(1, min(int(limit), 32))

    async def search(self, *, text: str, language: str | None = None) -> CapabilityCatalogResult:
        if not self.base_url:
            return CapabilityCatalogResult(query=text)
        try:
            async with httpx.AsyncClient(timeout=self.timeout_s, trust_env=False) as client:
                response = await client.post(
                    f"{self.base_url}/capabilities/search",
                    json={
                        "text": text,
                        "language": language or "auto",
                        "limit": self.limit,
                        "prefer_interaction_executable": True,
                    },
                )
                response.raise_for_status()
                return CapabilityCatalogResult.model_validate(response.json())
        except Exception as exc:
            logger.warning("capability catalog request failed: %s", exc)
            return CapabilityCatalogResult(
                query=text,
                live_refresh_error=f"{type(exc).__name__}: {exc}",
            )

    async def snapshot(self, *, refresh: bool = False) -> dict[str, Any]:
        if not self.base_url:
            return {}
        try:
            async with httpx.AsyncClient(timeout=self.timeout_s, trust_env=False) as client:
                response = await client.get(
                    f"{self.base_url}/capabilities/catalog",
                    params={"refresh": "true" if refresh else "false"},
                )
                response.raise_for_status()
                data = response.json()
                return data if isinstance(data, dict) else {}
        except Exception as exc:
            logger.warning("capability catalog snapshot request failed: %s", exc)
            return {"live_refresh_error": f"{type(exc).__name__}: {exc}"}
