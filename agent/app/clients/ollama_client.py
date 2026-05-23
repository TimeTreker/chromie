from __future__ import annotations

import json
import logging
from typing import Any

import httpx

logger = logging.getLogger("chromie.agent.ollama")


class OllamaClient:
    """Tiny async Ollama client.

    The agent service remains CPU-only and delegates model work to chromie-llm.
    """

    def __init__(self, base_url: str, model: str, timeout_ms: int = 2500) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = httpx.Timeout(timeout_ms / 1000.0)

    async def generate_text(
        self,
        prompt: str,
        *,
        system: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": options or {"temperature": 0.2, "num_predict": 80},
        }
        if system:
            payload["system"] = system

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(f"{self.base_url}/api/generate", json=payload)
                response.raise_for_status()
                data = response.json()
                return str(data.get("response") or "").strip()
        except Exception as exc:  # noqa: BLE001 - fallback behavior belongs in agents
            logger.warning("Ollama generate_text failed: %s", exc)
            raise

    async def generate_json(
        self,
        prompt: str,
        *,
        system: str | None = None,
        schema: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": schema or "json",
            "options": options or {"temperature": 0.1, "num_predict": 160},
        }
        if system:
            payload["system"] = system

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(f"{self.base_url}/api/generate", json=payload)
                response.raise_for_status()
                data = response.json()
                raw = data.get("response") or "{}"
                if isinstance(raw, dict):
                    return raw
                return json.loads(str(raw))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Ollama generate_json failed: %s", exc)
            raise
