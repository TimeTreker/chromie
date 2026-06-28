from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Literal

from fastapi import FastAPI
from fastapi.responses import ORJSONResponse
from pydantic import BaseModel, Field

from .capability_catalog import CapabilityCatalogClient, CapabilityCatalogResult
from .config import router_mode_from_env
from .fallback import fallback_decision
from .llm_router import OllamaLLMRouter
from .rules import route_by_priority_rules
from .schema import (
    HealthResponse,
    RouteDecision,
    RouteRequest,
    annotate_pipeline_stage_outputs,
    finalize_decision,
)


class Settings(BaseModel):
    host: str = Field(default_factory=lambda: os.getenv("ROUTER_HOST", "0.0.0.0"))
    port: int = Field(default_factory=lambda: int(os.getenv("ROUTER_PORT", "8091")))
    mode: Literal["rules_only", "llm_only", "hybrid"] = Field(
        default_factory=router_mode_from_env
    )
    rules_first: bool = Field(
        default_factory=lambda: os.getenv("ROUTER_RULES_FIRST", "1").strip().lower()
        not in {"0", "false", "no", "off"}
    )
    ollama_url: str = Field(default_factory=lambda: os.getenv("ROUTER_OLLAMA_URL", "http://chromie-llm:11434"))
    model: str = Field(default_factory=lambda: os.getenv("ROUTER_MODEL", "qwen3:0.6b"))
    review_model: str = Field(default_factory=lambda: os.getenv("ROUTER_REVIEW_MODEL", "gemma4:26b"))
    timeout_ms: int = Field(default_factory=lambda: int(os.getenv("ROUTER_TIMEOUT_MS", "800")))
    llm_timeout_ms: int = Field(default_factory=lambda: int(os.getenv("ROUTER_LLM_TIMEOUT_MS", os.getenv("ROUTER_TIMEOUT_MS", "800"))))
    confidence_threshold: float = Field(
        default_factory=lambda: float(os.getenv("ROUTER_CONFIDENCE_THRESHOLD", "0.55"))
    )
    capability_catalog_url: str = Field(
        default_factory=lambda: os.getenv(
            "ROUTER_CAPABILITY_CATALOG_URL",
            "http://chromie-agent:8092",
        )
    )
    capability_catalog_timeout_ms: int = Field(
        default_factory=lambda: int(os.getenv("ROUTER_CAPABILITY_CATALOG_TIMEOUT_MS", "600"))
    )
    capability_match_limit: int = Field(
        default_factory=lambda: int(os.getenv("ROUTER_CAPABILITY_MATCH_LIMIT", "8"))
    )
    log_level: str = Field(default_factory=lambda: os.getenv("ROUTER_LOG_LEVEL", os.getenv("LOG_LEVEL", "INFO")))


settings = Settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
logger = logging.getLogger("chromie.router")

app = FastAPI(
    title="Chromie Router",
    version="0.1.0",
    default_response_class=ORJSONResponse,
)

capability_catalog = CapabilityCatalogClient(
    settings.capability_catalog_url,
    timeout_ms=settings.capability_catalog_timeout_ms,
    limit=settings.capability_match_limit,
)


llm_router = OllamaLLMRouter(
    ollama_url=settings.ollama_url,
    model=settings.model,
    review_model=settings.review_model,
    timeout_ms=settings.llm_timeout_ms,
    confidence_threshold=settings.confidence_threshold,
    prompt_path=Path(__file__).parent / "prompts" / "router_system.txt",
)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        ok=True,
        mode=settings.mode,
        model=settings.model,
        ollama_url=settings.ollama_url,
        rules_first=settings.rules_first,
    )


@app.get("/routes")
async def routes() -> dict:
    return {
        "routes": ["chat", "deep_thought", "robot_action", "tool", "memory", "clarify", "interrupt", "ignore"],
        "lanes": [
            {
                "id": "emergency_filter",
                "description": "Deterministic stop, cancel, silence, emergency, and unusable-audio handling before model routing.",
                "routes": ["interrupt", "ignore"],
                "llm": False,
            },
            {
                "id": "quick_intent",
                "description": "Capability-catalog bounded quick intent and meaning routing with the small Router model.",
                "routes": ["chat", "deep_thought", "robot_action", "tool", "memory", "clarify"],
                "llm": settings.mode in {"hybrid", "llm_only"},
            },
            {
                "id": "route_validation",
                "description": "Deterministic validators correct capability-contract, availability, and safety impossibilities without answering the user.",
                "routes": ["chat", "deep_thought", "robot_action", "tool", "memory", "clarify"],
                "llm": False,
            },
            {
                "id": "deep_thought",
                "description": "Delegated planning/reasoning when the quick router is low confidence or explicitly chooses deep_thought.",
                "routes": ["deep_thought"],
                "llm": False,
            },
        ],
        "mode": settings.mode,
        "agents": [
            "capability_agent",
            "conversation_agent",
            "deepthinking_agent",
            "speaker_agent",
            "safety_agent",
            "tool_agent",
            "memory_agent",
            "vision_agent",
        ],
    }


def _capability_id(item: dict) -> str:
    return str(item.get("capability_id") or "").strip()


def _intent_capability_id(intent: str) -> str:
    prefix = "capability:"
    normalized = (intent or "").strip()
    if not normalized.startswith(prefix):
        return ""
    return normalized[len(prefix) :].strip()


def _capability_available(item: dict) -> bool:
    return item.get("available") is not False


def _capability_executable(item: dict) -> bool:
    return _capability_available(item) and bool(item.get("interaction_executable"))


def _interaction_executable_candidates(result: CapabilityCatalogResult) -> list[dict]:
    return [item for item in result.matches if _capability_executable(item)]


def _clarify_capability_decision(
    request: RouteRequest,
    result: CapabilityCatalogResult,
    *,
    reason: str,
) -> RouteDecision:
    language = request.language or "auto"
    speak_first = (
        "你希望我现在执行动作，还是只创建动作计划？"
        if language.startswith("zh")
        else "Should I execute the motion now, or only create a motion plan?"
    )
    return finalize_decision(
        RouteDecision(
            route="clarify",
            agents=["speaker_agent"],
            intent="clarify_capability_selection",
            confidence=0.0,
            language=language,
            needs_agent=True,
            should_speak=True,
            speak_first=speak_first,
            candidate_capabilities=list(result.matches),
            reason=reason,
            source="llm",
        ),
        request,
        source="llm",
    )


def _validate_llm_capability_decision(
    request: RouteRequest,
    decision: RouteDecision,
    result: CapabilityCatalogResult,
) -> RouteDecision:
    candidates = list(result.matches)
    decision.candidate_capabilities = candidates
    by_id = {_capability_id(item): item for item in candidates if _capability_id(item)}
    selected_id = _intent_capability_id(decision.intent)

    if decision.route == "robot_action":
        selected = by_id.get(selected_id)
        if selected_id and (selected is None or not _capability_executable(selected)):
            executable = _interaction_executable_candidates(result)
            if not executable:
                return _clarify_capability_decision(
                    request,
                    result,
                    reason="no interaction-executable capability is available",
                )
            decision.intent = "robot_action"
            decision.reason = (
                f"{decision.reason}; " if decision.reason else ""
            ) + "validator cleared invalid capability selection for Agent planning"

        elif not selected_id:
            executable = _interaction_executable_candidates(result)
            if not executable:
                return _clarify_capability_decision(
                    request,
                    result,
                    reason="no interaction-executable capability is available",
                )
            if not decision.intent or decision.intent in {"unknown", "interrupt", "ignore"}:
                decision.intent = "robot_action"

        required_agents = ["capability_agent", "safety_agent"]
        if decision.should_speak:
            required_agents.append("speaker_agent")
        decision.agents = list(dict.fromkeys([*decision.agents, *required_agents]))
        return finalize_decision(decision, request, source="llm")

    if decision.route == "chat":
        if not decision.intent or decision.intent == "unknown":
            decision.intent = "general_conversation"
        decision.agents = list(dict.fromkeys([*decision.agents, "conversation_agent", "speaker_agent"]))
        return finalize_decision(decision, request, source="llm")

    if selected_id:
        selected = by_id.get(selected_id)
        if selected is None or not _capability_available(selected):
            decision.intent = "unknown"
        elif decision.route in {"tool", "memory"}:
            required_agent = "capability_agent" if _capability_executable(selected) else "tool_agent"
            decision.agents = list(dict.fromkeys([*decision.agents, required_agent]))
        else:
            decision.intent = "unknown"

    return finalize_decision(decision, request, source="llm")


def _deep_thought_from_low_confidence(
    request: RouteRequest,
    decision: RouteDecision,
    *,
    reason_prefix: str | None = None,
) -> RouteDecision:
    candidates = decision.candidate_capabilities
    if not candidates:
        raw_candidates = request.context.get("candidate_capabilities", [])
        candidates = raw_candidates if isinstance(raw_candidates, list) else []
    reason_parts = [
        reason_prefix
        or f"quick router confidence {decision.confidence:.2f} below threshold {settings.confidence_threshold:.2f}",
        f"quick_route={decision.route}",
        f"quick_intent={decision.intent}",
    ]
    if decision.reason:
        reason_parts.append(f"quick_reason={decision.reason}")
    return finalize_decision(
        RouteDecision(
            route="deep_thought",
            agents=["deepthinking_agent", "speaker_agent"],
            intent="deep_thought_low_confidence",
            confidence=decision.confidence,
            language=decision.language or request.language or "auto",
            priority=decision.priority,
            needs_agent=True,
            should_speak=True,
            candidate_capabilities=candidates,
            reason="; ".join(reason_parts),
            source="llm",
            metadata={
                **(decision.metadata or {}),
                "thinking_ack_allowed": False,
            },
        ),
        request,
        source="llm",
    )


def _catalog_recovery_from_low_confidence(
    request: RouteRequest,
    decision: RouteDecision,
    result: CapabilityCatalogResult,
) -> RouteDecision | None:
    recovered = _catalog_decision(request, result)
    if recovered is None or recovered.route != "robot_action":
        return None
    recovered.reason = (
        "quick router low confidence, recovered executable catalog robot_action; "
        f"quick_route={decision.route}; quick_intent={decision.intent}"
    )
    recovered.metadata = {
        **(decision.metadata or {}),
        **(recovered.metadata or {}),
    }
    return recovered


def _recover_invalid_operational_llm_decision(
    request: RouteRequest,
    decision: RouteDecision,
    result: CapabilityCatalogResult,
) -> RouteDecision:
    del result
    return fallback_decision(
        request,
        reason=(
            f"quick router returned deterministic-only route {decision.route}; "
            "emergency filter did not match"
        ),
    )


def _attach_stage_context(
    request: RouteRequest,
    *,
    emergency_matched: bool,
    catalog_result: CapabilityCatalogResult,
) -> None:
    previous = request.context.get("router_stage_context")
    request.context = {
        **request.context,
        "candidate_capabilities": catalog_result.matches,
        "capability_catalog_version": catalog_result.catalog_version,
        "router_stage_context": {
            **(previous if isinstance(previous, dict) else {}),
            "emergency_filter": {
                "matched": emergency_matched,
                "routes": ["interrupt", "ignore"],
            },
            "quick_intent": {
                "model": settings.model,
                "confidence_threshold": settings.confidence_threshold,
            },
        },
    }


def _catalog_decision(
    request: RouteRequest,
    result: CapabilityCatalogResult,
) -> RouteDecision | None:
    if not result.matched or not result.matches:
        return None
    route = result.suggested_route
    if route not in {"chat", "robot_action", "tool", "memory"}:
        route = "tool"
    if route == "chat":
        return finalize_decision(
            RouteDecision(
                route="chat",
                agents=["conversation_agent", "speaker_agent"],
                intent="general_conversation",
                confidence=max(0.56, min(0.99, float(result.matches[0].get("score") or 0.0))),
                language=request.language or "auto",
                priority="normal",
                needs_agent=True,
                should_speak=True,
                candidate_capabilities=result.matches,
                reason=f"Catalog indicated conversational handling v{result.catalog_version}",
                source="catalog",
            ),
            request,
            source="catalog",
        )
    top = result.matches[0]
    if route == "robot_action":
        top = next(
            (item for item in result.matches if _capability_executable(item)),
            None,
        )
        if top is None:
            return None
    selected_id = _capability_id(top)
    if not selected_id:
        return None
    score = float(top.get("score") or 0.0)
    agents = list(result.suggested_agents or ["capability_agent", "speaker_agent"])
    return finalize_decision(
        RouteDecision(
            route=route,
            agents=agents,
            intent=f"capability:{selected_id}",
            confidence=max(0.56, min(0.99, score)),
            language=request.language or "auto",
            priority="normal",
            needs_agent=True,
            should_speak=True,
            candidate_capabilities=result.matches,
            reason=f"Matched shared capability catalog v{result.catalog_version}",
            source="catalog",
        ),
        request,
        source="catalog",
    )


@app.post("/route", response_model=RouteDecision)
async def route(request: RouteRequest) -> RouteDecision:
    start = time.perf_counter()
    request.text = request.text.strip()

    decision: RouteDecision | None = None
    emergency_matched = False
    priority = route_by_priority_rules(request)
    if priority is not None:
        decision = priority
        emergency_matched = True

    if decision is None:
        catalog_result = await capability_catalog.search(
            text=request.text,
            language=request.language,
        )
        _attach_stage_context(
            request,
            emergency_matched=False,
            catalog_result=catalog_result,
        )

        if settings.mode in ("llm_only", "hybrid"):
            llm_decision = await llm_router.route(request)
            if llm_decision.source == "llm":
                if llm_decision.route in {"interrupt", "ignore"}:
                    decision = _recover_invalid_operational_llm_decision(
                        request,
                        llm_decision,
                        catalog_result,
                    )
                elif (
                    llm_decision.confidence < settings.confidence_threshold
                    and llm_decision.route not in {"chat", "deep_thought"}
                ):
                    decision = _catalog_recovery_from_low_confidence(
                        request,
                        llm_decision,
                        catalog_result,
                    )
                    if decision is None:
                        decision = _deep_thought_from_low_confidence(request, llm_decision)
                elif llm_decision.route == "deep_thought":
                    decision = _validate_llm_capability_decision(
                        request,
                        llm_decision,
                        catalog_result,
                    )
                else:
                    decision = _validate_llm_capability_decision(
                        request,
                        llm_decision,
                        catalog_result,
                    )
            elif llm_decision.source == "fallback":
                decision = llm_decision
        if decision is None and settings.mode == "rules_only":
            decision = _catalog_decision(request, catalog_result)

        if decision is None:
            decision = _catalog_decision(request, catalog_result)
        if decision is None:
            reason = (
                "catalog_rules_and_llm_no_match"
                if settings.mode in ("llm_only", "hybrid")
                else "catalog_and_rules_no_match"
            )
            decision = fallback_decision(request, reason=reason)

    decision = finalize_decision(decision, request, source=decision.source)
    decision = annotate_pipeline_stage_outputs(
        decision,
        emergency_matched=emergency_matched,
    )
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    logger.info(
        "route sid=%s source=%s route=%s intent=%s confidence=%.2f capabilities=%d ms=%.1f",
        request.sid,
        decision.source,
        decision.route,
        decision.intent,
        decision.confidence,
        len(decision.candidate_capabilities),
        elapsed_ms,
    )
    return decision


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=False)
