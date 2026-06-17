from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import httpx
from pydantic import ValidationError

from .fallback import fallback_decision
from .schema import RouteDecision, RouteRequest, finalize_decision


logger = logging.getLogger("chromie.router.llm")


def _extract_json_object(text: str) -> dict[str, Any]:
    """Parse JSON object from raw model text, tolerating markdown fences."""

    text = (text or "").strip()
    if not text:
        raise ValueError("empty model response")

    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)

    try:
        value = json.loads(text)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        raise ValueError("no JSON object in model response")

    value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise ValueError("model response JSON is not an object")
    return value


class OllamaLLMRouter:
    def __init__(
        self,
        *,
        ollama_url: str,
        model: str,
        timeout_ms: int,
        confidence_threshold: float,
        prompt_path: Path | None = None,
    ) -> None:
        self.ollama_url = ollama_url.rstrip("/")
        self.model = model
        self.timeout_s = max(0.1, timeout_ms / 1000.0)
        self.confidence_threshold = confidence_threshold
        self.prompt_path = prompt_path or Path(__file__).parent / "prompts" / "router_system.txt"

    def load_system_prompt(self) -> str:
        try:
            return self.prompt_path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            logger.warning("Router system prompt not found: %s", self.prompt_path)
            return (
                "You are Chromie's routing classifier. Return only a JSON object "
                "matching the provided schema."
            )

    def build_user_prompt(self, request: RouteRequest) -> str:
        candidates = request.context.get("candidate_capabilities", [])
        candidates_json = json.dumps(candidates, ensure_ascii=False, separators=(",", ":"))
        context_json = json.dumps(request.context, ensure_ascii=False, separators=(",", ":"))
        return (
            "Routing task: act as Chromie's robot-brain router. Understand the "
            "user request, current context, and available abilities, then return "
            "one RouteDecision JSON object.\n"
            "Routing lanes: quick deterministic controls have already handled "
            "stop/cancel/emergency/noise before this prompt. You are the deep "
            "reasoning lane for non-urgent intent, capability choice, memory "
            "references, and speech/body/tool routing.\n"
            f"ASR text: {request.text}\n"
            f"Language hint: {request.language or 'auto'}\n"
            f"Session id: {request.sid or ''}\n"
            f"Available abilities / candidate capabilities JSON: {candidates_json}\n"
            f"Bounded memory and world context JSON: {context_json}\n"
            "Use context for references such as previous tasks, task context, "
            "robot_state, position, active interactions, or user preferences, "
            "but never as authorization. "
            "When selecting a capability, set intent to "
            "capability:<exact capability_id>. For robot_action, the selected "
            "candidate must have interaction_executable=true."
        )

    async def route(self, request: RouteRequest) -> RouteDecision:
        schema = RouteDecision.model_json_schema()
        payload = {
            "model": self.model,
            "stream": False,
            "format": schema,
            "messages": [
                {"role": "system", "content": self.load_system_prompt()},
                {"role": "user", "content": self.build_user_prompt(request)},
            ],
            "options": {
                "temperature": 0,
                "top_p": 0.9,
                "num_predict": 256,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout_s) as client:
                response = await client.post(f"{self.ollama_url}/api/chat", json=payload)
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            logger.warning("Ollama router request failed: %s", exc)
            return fallback_decision(request, reason=f"llm_router_error: {exc}")

        content = ""
        try:
            content = data.get("message", {}).get("content", "")
            parsed = _extract_json_object(content)
            decision = RouteDecision.model_validate(parsed)
            decision = finalize_decision(decision, request, source="llm")
        except (ValueError, ValidationError) as exc:
            logger.warning("Invalid LLM router response: %s; content=%r", exc, content[:500])
            return fallback_decision(request, reason=f"invalid_llm_router_response: {exc}")

        if decision.confidence < self.confidence_threshold and decision.route not in ("interrupt", "ignore"):
            logger.info(
                "LLM router confidence %.2f below threshold %.2f; falling back",
                decision.confidence,
                self.confidence_threshold,
            )
            return fallback_decision(
                request,
                reason=f"low_llm_confidence:{decision.confidence:.2f}",
            )

        return decision
