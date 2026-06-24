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


ROUTE_NAMES = {
    "chat",
    "deep_thought",
    "robot_action",
    "tool",
    "memory",
    "clarify",
    "interrupt",
    "ignore",
}


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
        review_model: str | None = None,
        timeout_ms: int,
        confidence_threshold: float,
        prompt_path: Path | None = None,
    ) -> None:
        self.ollama_url = ollama_url.rstrip("/")
        self.model = model
        self.review_model = (review_model or "").strip()
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
            "reasoning lane called before non-urgent semantic fallback. Decide "
            "intent from the whole utterance, capability choice, memory "
            "references, and speech/body/tool routing. Use route deep_thought "
            "for complex reasoning, multi-step analysis, design discussion, or "
            "implementation planning that should be handled by deepthinking_agent "
            "rather than the fast router.\n"
            f"ASR text: {request.text}\n"
            f"Language hint: {request.language or 'auto'}\n"
            f"Session id: {request.sid or ''}\n"
            f"Available abilities / candidate capabilities JSON: {candidates_json}\n"
            f"Bounded memory and world context JSON: {context_json}\n"
            "Use context for references such as previous tasks, task context, "
            "robot_state, position, active interactions, or user preferences, "
            "but never as authorization. "
            "Treat creative speech-only requests, including original singing, "
            "stories, jokes, or spoken performance, as chat unless the user "
            "explicitly asks for simultaneous physical movement. Discourse "
            "markers such as 'go ahead', 'okay', 'sure', or 'please' are not "
            "body movement by themselves. "
            "When selecting a capability, set intent to "
            "capability:<exact capability_id>. For robot_action, the selected "
            "candidate must have interaction_executable=true."
        )

    def build_payload(self, request: RouteRequest, *, relaxed_json: bool = False) -> dict[str, Any]:
        schema = RouteDecision.model_json_schema()
        payload: dict[str, Any] = {
            "model": self.model,
            "stream": False,
            "think": False,
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
        payload["format"] = "json" if relaxed_json else schema
        return payload

    def build_intent_review_payload(self, request: RouteRequest) -> dict[str, Any]:
        return {
            "model": self.review_model or self.model,
            "stream": False,
            "think": False,
            "format": "json",
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Classify the user intent for a realtime robot voice assistant. "
                        "Return only one JSON object with route exactly one of: chat, "
                        "deep_thought, robot_action, tool, memory, clarify, interrupt, ignore. "
                        "Creative speech-only requests like singing, stories, jokes, "
                        "or talking are chat unless physical robot body/head motion is "
                        "explicitly requested. The phrase 'go ahead' is permission, not walking."
                    ),
                },
                {"role": "user", "content": f"Text: {request.text}"},
            ],
            "options": {
                "temperature": 0,
                "top_p": 0.9,
                "num_predict": 96,
            },
        }

    async def _chat(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            response = await client.post(f"{self.ollama_url}/api/chat", json=payload)
            response.raise_for_status()
            return response.json()

    def _decision_from_response(self, request: RouteRequest, data: dict[str, Any]) -> RouteDecision:
        content = data.get("message", {}).get("content", "")
        parsed = _extract_json_object(content)
        route_from_intent = str(parsed.get("intent") or "").strip()
        if "route" not in parsed and route_from_intent in ROUTE_NAMES:
            parsed["route"] = route_from_intent
            parsed["reason"] = (
                f"{parsed.get('reason')}; " if parsed.get("reason") else ""
            ) + "LLM returned intent-only route JSON; router normalized route"
        if "confidence" not in parsed and parsed.get("route") not in {"interrupt", "ignore"}:
            parsed["confidence"] = max(0.72, self.confidence_threshold)
            parsed["reason"] = (
                f"{parsed.get('reason')}; " if parsed.get("reason") else ""
            ) + "LLM returned route-only JSON; router applied default confidence"
        decision = RouteDecision.model_validate(parsed)
        return finalize_decision(decision, request, source="llm")

    async def _review_route_only_robot_action(
        self,
        request: RouteRequest,
        decision: RouteDecision,
    ) -> RouteDecision:
        if not self.review_model:
            return decision
        if decision.route != "robot_action" or decision.intent.startswith("capability:") or decision.actions:
            return decision

        try:
            reviewed = await self._chat(self.build_intent_review_payload(request))
            reviewed_decision = self._decision_from_response(request, reviewed)
        except Exception as exc:
            logger.warning("LLM review model intent check failed: %s", exc)
            return decision

        if reviewed_decision.route != "robot_action":
            reviewed_decision.reason = (
                f"{reviewed_decision.reason}; " if reviewed_decision.reason else ""
            ) + f"review_model:{self.review_model} overrode underspecified robot_action"
            logger.info(
                "LLM review model changed underspecified robot_action to %s",
                reviewed_decision.route,
            )
            return reviewed_decision
        return decision

    async def route(self, request: RouteRequest) -> RouteDecision:
        payload = self.build_payload(request)

        try:
            data = await self._chat(payload)
        except Exception as exc:
            logger.warning("Ollama router request failed: %s", exc)
            return fallback_decision(request, reason=f"llm_router_error: {exc}")

        content = ""
        try:
            content = data.get("message", {}).get("content", "")
            decision = self._decision_from_response(request, data)
        except (ValueError, ValidationError) as exc:
            logger.warning("Invalid LLM router response: %s; content=%r", exc, content[:500])
            try:
                relaxed = await self._chat(self.build_payload(request, relaxed_json=True))
                decision = self._decision_from_response(request, relaxed)
                logger.info("LLM router recovered with relaxed JSON response")
            except Exception as relaxed_exc:
                logger.warning("Relaxed LLM router retry failed: %s", relaxed_exc)
                return fallback_decision(request, reason=f"invalid_llm_router_response: {exc}")

        decision = await self._review_route_only_robot_action(request, decision)

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
