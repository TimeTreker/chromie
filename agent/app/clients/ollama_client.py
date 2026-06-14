from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any, Literal

import httpx


logger = logging.getLogger("chromie.agent.ollama")

ResponseFormat = Literal["text", "json"]


class OllamaClient:
    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        *,
        timeout_ms: int | None = None,
    ):
        self.base_url = (
            base_url
            or os.getenv("AGENT_OLLAMA_URL")
            or os.getenv("OLLAMA_URL")
            or "http://chromie-llm:11434"
        ).rstrip("/")

        self.model = (
            model
            or os.getenv("AGENT_MODEL")
            or os.getenv("OLLAMA_MODEL")
            or "qwen3:4b"
        )

        self.timeout_ms = int(
            timeout_ms
            or os.getenv("AGENT_TIMEOUT_MS")
            or os.getenv("OLLAMA_TIMEOUT_MS")
            or "3000"
        )

        logger.info(
            "ollama_client_init base_url=%s model=%s timeout_ms=%s",
            self.base_url,
            self.model,
            self.timeout_ms,
        )

    async def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        options: dict[str, Any] | None = None,
        response_format: ResponseFormat = "text",
    ) -> str | dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "think": False,
        }

        if system:
            payload["system"] = system

        if options:
            payload["options"] = options

        if response_format == "json":
            payload["format"] = "json"

        url = f"{self.base_url}/api/generate"
        timeout = httpx.Timeout(self.timeout_ms / 1000.0)

        prompt_preview = " ".join(prompt.split())[:160]

        logger.info(
            "ollama_generate_start url=%s model=%s response_format=%s prompt_chars=%s prompt_preview=%r",
            url,
            self.model,
            response_format,
            len(prompt),
            prompt_preview,
        )

        started = time.perf_counter()

        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                trust_env=False,
            ) as client:
                response = await client.post(url, json=payload)

            elapsed_ms = (time.perf_counter() - started) * 1000.0

            logger.info(
                "ollama_generate_http_done status_code=%s elapsed_ms=%.1f",
                response.status_code,
                elapsed_ms,
            )

            response.raise_for_status()
            logger.info(
                "ollama_generate_raw_body body=%s",
                response.text[:2000],
            )
            data = response.json()

            text = str(data.get("response") or "").strip()

            logger.info(
                "ollama_generate_done response_chars=%s response_preview=%r",
                len(text),
                " ".join(text.split())[:160],
            )

        except Exception as exc:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            logger.exception(
                "ollama_generate_failed elapsed_ms=%.1f error_type=%s error=%s",
                elapsed_ms,
                type(exc).__name__,
                exc,
            )
            raise

        if response_format == "text":
            return text

        if response_format == "json":
            parsed = self._parse_json(text)
            logger.info("ollama_generate_json_parsed keys=%s", list(parsed.keys()))
            return parsed

        raise ValueError(f"Unsupported response_format: {response_format}")

    def _parse_json(self, text: str) -> dict[str, Any]:
        cleaned = self._strip_code_fence(text)

        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
            if not match:
                raise
            parsed = json.loads(match.group(0))

        if not isinstance(parsed, dict):
            raise ValueError("Ollama JSON response is not an object")

        return parsed

    def _strip_code_fence(self, text: str) -> str:
        text = text.strip()

        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
            text = re.sub(r"\s*```$", "", text)

        return text.strip()
