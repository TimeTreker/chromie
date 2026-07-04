from __future__ import annotations

import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI
from fastapi.responses import ORJSONResponse
from pydantic import BaseModel, Field

from .capability_catalog import CapabilityCatalogClient, CapabilityCatalogResult
from .config import router_mode_from_env
from .fallback import fallback_decision
from .llm_router import OllamaLLMRouter, _is_placeholder_capability_intent
from .rules import route_by_priority_rules
from .schema import (
    HealthResponse,
    RouteDecision,
    RouteRequest,
    annotate_pipeline_stage_outputs,
    annotate_stage_outputs,
    finalize_decision,
    route_stage_output,
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
    review_model: str = Field(default_factory=lambda: os.getenv("ROUTER_REVIEW_MODEL", "gemma4:e2b"))
    timeout_ms: int = Field(default_factory=lambda: int(os.getenv("ROUTER_TIMEOUT_MS", "2200")))
    llm_timeout_ms: int = Field(default_factory=lambda: int(os.getenv("ROUTER_LLM_TIMEOUT_MS", os.getenv("ROUTER_TIMEOUT_MS", "2200"))))
    llm_num_predict: int = Field(default_factory=lambda: int(os.getenv("ROUTER_LLM_NUM_PREDICT", "192")))
    review_timeout_ms: int = Field(
        default_factory=lambda: int(
            os.getenv("ROUTER_REVIEW_TIMEOUT_MS", "800")
        )
    )
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
    capability_catalog_cache_ttl_ms: int = Field(
        default_factory=lambda: int(os.getenv("ROUTER_CAPABILITY_CATALOG_CACHE_TTL_MS", "5000"))
    )
    capability_match_limit: int = Field(
        default_factory=lambda: int(os.getenv("ROUTER_CAPABILITY_MATCH_LIMIT", "8"))
    )
    post_interrupt_review_enabled: bool = Field(
        default_factory=lambda: os.getenv("ROUTER_POST_INTERRUPT_REVIEW_ENABLED", "0").strip().lower()
        not in {"0", "false", "no", "off"}
    )
    slow_review_recovery_enabled: bool = Field(
        default_factory=lambda: os.getenv("ROUTER_SLOW_REVIEW_RECOVERY_ENABLED", "0").strip().lower()
        not in {"0", "false", "no", "off"}
    )
    log_level: str = Field(default_factory=lambda: os.getenv("ROUTER_LOG_LEVEL", os.getenv("LOG_LEVEL", "INFO")))


settings = Settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
logger = logging.getLogger("chromie.router")
PROMPT_CATALOG_COMMON_LIMIT = 48
PROMPT_CATALOG_ALL_LIMIT = 96

app = FastAPI(
    title="Chromie Router",
    version="0.1.0",
    default_response_class=ORJSONResponse,
)

capability_catalog = CapabilityCatalogClient(
    settings.capability_catalog_url,
    timeout_ms=settings.capability_catalog_timeout_ms,
    limit=settings.capability_match_limit,
    snapshot_cache_ttl_ms=settings.capability_catalog_cache_ttl_ms,
)


llm_router = OllamaLLMRouter(
    ollama_url=settings.ollama_url,
    model=settings.model,
    review_model=settings.review_model,
    timeout_ms=settings.llm_timeout_ms,
    review_timeout_ms=settings.review_timeout_ms,
    confidence_threshold=settings.confidence_threshold,
    slow_review_recovery_enabled=settings.slow_review_recovery_enabled,
    num_predict=settings.llm_num_predict,
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
                "id": "post_interrupt_review",
                "description": "Optional semantic review after an interrupt has already been applied, used only to confirm or correct likely stop/cancel mishearing.",
                "routes": ["chat", "deep_thought", "robot_action", "tool", "memory", "clarify", "interrupt", "ignore"],
                "llm": settings.mode in {"hybrid", "llm_only"} and settings.post_interrupt_review_enabled,
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


def _unique_capabilities(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    ordered: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        capability_id = _capability_id(item)
        if not capability_id:
            continue
        if capability_id not in merged:
            ordered.append(capability_id)
            merged[capability_id] = dict(item)
            continue
        merged[capability_id] = {**merged[capability_id], **dict(item)}
    return [merged[capability_id] for capability_id in ordered]


def _prompt_catalog_capabilities(
    snapshot: dict[str, Any],
    *,
    scope: Literal["common", "all"],
) -> list[dict[str, Any]]:
    raw = snapshot.get("capabilities") if isinstance(snapshot, dict) else None
    if not isinstance(raw, list):
        return []
    items: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        if item.get("available") is False:
            continue
        tier = str(item.get("prompt_tier") or "rare")
        if scope == "common" and tier != "common":
            continue
        items.append(dict(item))
    items.sort(
        key=lambda item: (
            str(item.get("prompt_tier") or "rare") != "common",
            item.get("interaction_executable") is not True,
            str(item.get("route") or ""),
            _capability_id(item),
        )
    )
    limit = PROMPT_CATALOG_COMMON_LIMIT if scope == "common" else PROMPT_CATALOG_ALL_LIMIT
    return items[:limit]


def _intent_capability_id(intent: str) -> str:
    prefix = "capability:"
    normalized = (intent or "").strip()
    if not normalized.startswith(prefix):
        return ""
    return normalized[len(prefix) :].strip()


def _unique_capability_suffix_match(raw_intent: str, by_id: dict[str, dict[str, Any]]) -> str:
    normalized = (raw_intent or "").strip()
    if not normalized:
        return ""
    aliases = {
        normalized.casefold(),
        normalized.casefold().replace(" ", "_").replace("-", "_"),
    }
    matches = [
        capability_id
        for capability_id in by_id
        if capability_id.rsplit(".", 1)[-1].casefold() in aliases
    ]
    return matches[0] if len(matches) == 1 else ""


def _capability_available(item: dict) -> bool:
    return item.get("available") is not False


def _capability_executable(item: dict) -> bool:
    return _capability_available(item) and bool(item.get("interaction_executable"))


def _capability_allowed_in_quick_action(item: dict) -> bool:
    capability_id = _capability_id(item)
    if capability_id == "chromie.speak":
        return _capability_available(item)
    return _capability_executable(item)


def _interaction_executable_candidates(result: CapabilityCatalogResult) -> list[dict]:
    return [item for item in result.matches if _capability_executable(item)]


def _action_sequence(action: Any, fallback: int) -> int:
    if not isinstance(action, dict):
        return fallback
    value = action.get("sequence")
    if isinstance(value, bool):
        return fallback
    if isinstance(value, int):
        return value
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return fallback


def _action_confidence(action: dict[str, Any], fallback: float) -> float | None:
    value = action.get("confidence")
    if value is None:
        return max(0.0, min(1.0, float(fallback)))
    if isinstance(value, bool):
        return None
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return None


def _default_thinking_speak_first(language: str) -> str:
    if (language or "").startswith("zh"):
        return "给我一点时间想清楚。"
    return "Give me a moment to think that through."


def _safe_thinking_speak_first(text: str | None, *, language: str) -> str | None:
    cleaned = " ".join((text or "").strip().split())
    if not cleaned:
        return None
    if len(cleaned) > 120:
        cleaned = cleaned[:120].rstrip()
    normalized = cleaned.casefold()
    action_claim_terms = (
        "done",
        "completed",
        "executing",
        "moving",
        "walking",
        "turning",
        "blinking",
        "nodding",
        "i did",
        "i will do it",
        "doing it now",
        "已",
        "已经",
        "完成",
        "执行",
        "正在",
        "开始",
        "走",
        "移动",
        "眨",
        "点头",
        "转",
    )
    if any(term in normalized for term in action_claim_terms):
        return None
    return cleaned


def _thinking_ack_allowed_from_decision(decision: RouteDecision) -> bool:
    return bool(
        _safe_thinking_speak_first(
            decision.speak_first,
            language=decision.language or "auto",
        )
    )


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
    prompt_capabilities = request.context.get("prompt_capabilities_common")
    if not isinstance(prompt_capabilities, list):
        prompt_capabilities = []
    candidates = _unique_capabilities([*list(result.matches or []), *prompt_capabilities])
    decision.candidate_capabilities = candidates
    by_id = {_capability_id(item): item for item in candidates if _capability_id(item)}
    selected_id = _intent_capability_id(decision.intent)
    raw_intent = (decision.intent or "").strip()
    normalized_reason = "validator normalized catalog capability intent"
    if not selected_id:
        if raw_intent in by_id:
            selected_id = raw_intent
            normalized_reason = "validator normalized exact capability intent"
        else:
            selected_id = _unique_capability_suffix_match(raw_intent, by_id)
    if selected_id and raw_intent != f"capability:{selected_id}":
        decision.intent = f"capability:{selected_id}"
        decision.reason = (
            f"{decision.reason}; " if decision.reason else ""
        ) + normalized_reason

    if decision.route == "robot_action":
        if decision.actions:
            normalized_actions: list[dict[str, Any]] = []
            invalid_reasons: list[str] = []
            low_confidence_reasons: list[str] = []
            ordered_actions = sorted(
                enumerate(decision.actions),
                key=lambda pair: (_action_sequence(pair[1], pair[0]), pair[0]),
            )
            for normalized_index, (index, action) in enumerate(ordered_actions):
                if not isinstance(action, dict):
                    invalid_reasons.append(f"action[{index}] is not an object")
                    continue
                capability_id = str(action.get("capability_id") or "").strip()
                if not capability_id:
                    invalid_reasons.append(f"action[{index}] missing capability_id")
                    continue
                selected = by_id.get(capability_id)
                if selected is None:
                    invalid_reasons.append(f"action[{index}] unknown capability_id {capability_id!r}")
                    continue
                if not _capability_allowed_in_quick_action(selected):
                    invalid_reasons.append(f"action[{index}] capability is unavailable or not quick-action executable")
                    continue
                args = action.get("args") if isinstance(action.get("args"), dict) else {}
                if capability_id == "chromie.speak" and not str(args.get("text") or "").strip():
                    invalid_reasons.append(f"action[{index}] chromie.speak missing args.text")
                    continue
                action_confidence = _action_confidence(action, decision.confidence)
                if action_confidence is None:
                    invalid_reasons.append(f"action[{index}] has invalid confidence")
                    continue
                if action_confidence < settings.confidence_threshold:
                    low_confidence_reasons.append(
                        f"action[{index}] confidence {action_confidence:.2f} "
                        f"below threshold {settings.confidence_threshold:.2f}"
                    )
                    continue
                timing = str(action.get("timing") or "").strip()
                normalized: dict[str, Any] = {
                    "capability_id": capability_id,
                    "args": args,
                    "sequence": normalized_index,
                    "confidence": round(action_confidence, 4),
                }
                if timing in {"parallel", "sequential"}:
                    normalized["timing"] = timing
                reason = str(action.get("reason") or "").strip()
                if reason:
                    normalized["reason"] = reason[:160]
                normalized_actions.append(normalized)
            if invalid_reasons or low_confidence_reasons or not normalized_actions:
                if low_confidence_reasons and not _safe_thinking_speak_first(
                    decision.speak_first,
                    language=decision.language or request.language or "auto",
                ):
                    decision.speak_first = _default_thinking_speak_first(
                        decision.language or request.language or "auto"
                    )
                    decision.metadata = {
                        **(decision.metadata or {}),
                        "validator_default_thinking_ack": True,
                    }
                return _deep_thought_from_low_confidence(
                    request,
                    decision,
                    reason_prefix=(
                        "quick router compound action list needs deep_thought review: "
                        + "; ".join([*invalid_reasons, *low_confidence_reasons][:4])
                    ),
                )
            decision.actions = normalized_actions
            if not decision.intent or decision.intent in {"unknown", "robot_action"} or _is_placeholder_capability_intent(raw_intent):
                decision.intent = "compound_common_catalog_task"
                if _is_placeholder_capability_intent(raw_intent):
                    decision.reason = (
                        f"{decision.reason}; " if decision.reason else ""
                    ) + "validator normalized placeholder intent for valid compound actions"
            decision.metadata = {
                **(decision.metadata or {}),
                "quick_router_action_count": len(normalized_actions),
                "quick_router_compound_tasks": len(normalized_actions) > 1,
                "quick_router_action_min_confidence": min(
                    float(item["confidence"]) for item in normalized_actions
                ),
            }
            required_agents = ["capability_agent", "safety_agent"]
            if decision.should_speak:
                required_agents.append("speaker_agent")
            decision.agents = list(dict.fromkeys([*decision.agents, *required_agents]))
            return finalize_decision(decision, request, source="llm")

        if _is_placeholder_capability_intent(raw_intent):
            return fallback_decision(
                request,
                reason=(
                    "llm_robot_action_placeholder_capability_intent: "
                    f"{raw_intent or '<empty>'}"
                ),
            )
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

    if decision.route == "deep_thought":
        safe_speak_first = _safe_thinking_speak_first(
            decision.speak_first,
            language=decision.language or request.language or "auto",
        )
        decision.speak_first = safe_speak_first
        decision.metadata = {
            **(decision.metadata or {}),
            "thinking_ack_allowed": bool(safe_speak_first),
            "thinking_ack_source": "quick_llm_speak_first" if safe_speak_first else "none",
        }

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
    thinking_ack_allowed = _thinking_ack_allowed_from_decision(decision)
    if (decision.metadata or {}).get("validator_default_thinking_ack") is True:
        thinking_ack_source = "quick_validator_default_speak_first"
    elif thinking_ack_allowed:
        thinking_ack_source = "quick_llm_speak_first"
    else:
        thinking_ack_source = "none"
    quick_stage = route_stage_output(
        decision,
        stage="quick_intent",
        status="needs_deep_review",
    )
    quick_review_request = {
        "schema_version": 1,
        "review_status": "needs_review",
        "execution_state": "not_committed",
        "reason": reason_parts[0],
        "quick_route": decision.route,
        "quick_intent": decision.intent,
        "quick_confidence": decision.confidence,
        "quick_actions": list(decision.actions),
        "quick_task_list": quick_stage.get("tasks", []),
        "quick_task_proposals": quick_stage.get("task_proposals", []),
    }
    return finalize_decision(
        RouteDecision(
            route="deep_thought",
            agents=["deepthinking_agent", "speaker_agent"],
            intent="deep_thought_low_confidence",
            confidence=decision.confidence,
            language=decision.language or request.language or "auto",
            priority=decision.priority,
            speak_first=_safe_thinking_speak_first(
                decision.speak_first,
                language=decision.language or request.language or "auto",
            ),
            needs_agent=True,
            should_speak=True,
            candidate_capabilities=candidates,
            reason="; ".join(reason_parts),
            source="llm",
            metadata={
                **(decision.metadata or {}),
                "thinking_ack_allowed": thinking_ack_allowed,
                "thinking_ack_source": thinking_ack_source,
                "quick_router_review_request": quick_review_request,
            },
        ),
        request,
        source="llm",
    )


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
    prompt_capabilities_common: list[dict[str, Any]] | None = None,
    prompt_capabilities_all: list[dict[str, Any]] | None = None,
) -> None:
    previous = request.context.get("router_stage_context")
    # Preserve low-score context-fill candidates for semantic recovery. A
    # lexical catalog miss can still provide the correct ability surface for
    # multilingual or ASR-noisy requests; only catalog-owned fallback execution
    # is gated on ``matched``.
    candidate_capabilities = list(catalog_result.matches or [])
    common = _unique_capabilities(list(prompt_capabilities_common or []))
    full = _unique_capabilities(list(prompt_capabilities_all or []))
    request.context = {
        **request.context,
        "candidate_capabilities": candidate_capabilities,
        "prompt_capabilities_common": common,
        "prompt_capabilities_all": full,
        "prompt_catalog_scope": "common",
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


def _decision_summary(decision: RouteDecision) -> dict:
    return {
        "route": decision.route,
        "agents": list(decision.agents),
        "intent": decision.intent,
        "confidence": decision.confidence,
        "language": decision.language,
        "priority": decision.priority,
        "interrupt_current": decision.interrupt_current,
        "needs_agent": decision.needs_agent,
        "should_speak": decision.should_speak,
        "speak_first": decision.speak_first,
        "actions": list(decision.actions),
        "candidate_capabilities": list(decision.candidate_capabilities),
        "reason": decision.reason,
        "source": decision.source,
        "metadata": {
            key: value
            for key, value in (decision.metadata or {}).items()
            if key not in {"route_stage_outputs", "task_list", "task_proposals", "route_merge"}
        },
    }


def _attach_post_interrupt_review(
    interrupt_decision: RouteDecision,
    advisory: RouteDecision | None,
    *,
    status: str,
    reason: str | None = None,
) -> RouteDecision:
    outputs = [
        route_stage_output(
            interrupt_decision,
            stage="emergency_filter",
            status="triggered",
        )
    ]
    review: dict = {"status": status}
    if reason:
        review["reason"] = reason

    if advisory is not None:
        review["decision"] = _decision_summary(advisory)
        if status == "corrected":
            outputs.append(
                route_stage_output(
                    advisory,
                    stage="post_interrupt_review",
                    status="corrected_after_interrupt",
                )
            )
            review["post_interrupt_decision"] = _decision_summary(advisory)
        else:
            outputs.append(
                route_stage_output(
                    advisory,
                    stage="post_interrupt_review",
                    status=status,
                    tasks=[],
                )
            )

    interrupt_decision.metadata = {
        **(interrupt_decision.metadata or {}),
        "post_interrupt_review": review,
    }
    if status == "corrected" and advisory is not None:
        interrupt_decision.metadata["post_interrupt_decision"] = _decision_summary(advisory)
    return annotate_stage_outputs(
        interrupt_decision,
        outputs,
        merge_strategy="safety_interrupt_then_semantic_review",
        merge_reason=reason,
        selected_stage="emergency_filter",
    )


async def _review_priority_interrupt(
    request: RouteRequest,
    interrupt_decision: RouteDecision,
) -> RouteDecision:
    if not settings.post_interrupt_review_enabled:
        return interrupt_decision
    if settings.mode not in {"hybrid", "llm_only"}:
        return interrupt_decision
    if interrupt_decision.route != "interrupt":
        return interrupt_decision

    try:
        catalog_result = await capability_catalog.search(
            text=request.text,
            language=request.language,
        )
    except Exception as exc:
        logger.warning("post-interrupt catalog context failed: %s", exc)
        return _attach_post_interrupt_review(
            interrupt_decision,
            None,
            status="unavailable",
            reason=f"catalog_error:{type(exc).__name__}",
        )

    _attach_stage_context(
        request,
        emergency_matched=True,
        catalog_result=catalog_result,
    )
    interrupt_decision.candidate_capabilities = list(catalog_result.matches or [])

    try:
        advisory = await llm_router.review_after_priority_interrupt(
            request,
            interrupt_decision,
        )
    except Exception as exc:
        logger.warning("post-interrupt semantic review failed: %s", exc)
        return _attach_post_interrupt_review(
            interrupt_decision,
            None,
            status="unavailable",
            reason=f"review_error:{type(exc).__name__}",
        )

    if advisory.route in {"interrupt", "ignore"}:
        return _attach_post_interrupt_review(
            interrupt_decision,
            advisory,
            status="confirmed" if advisory.route == "interrupt" else "ignored",
        )
    if advisory.confidence < settings.confidence_threshold:
        return _attach_post_interrupt_review(
            interrupt_decision,
            advisory,
            status="uncertain",
            reason=(
                f"confidence {advisory.confidence:.2f} below threshold "
                f"{settings.confidence_threshold:.2f}"
            ),
        )
    return _attach_post_interrupt_review(
        interrupt_decision,
        advisory,
        status="corrected",
    )


def _deep_thought_router_unavailable_decision(
    request: RouteRequest,
    result: CapabilityCatalogResult,
    *,
    llm_decision: RouteDecision,
) -> RouteDecision | None:
    reason_parts = [
        "LLM router unavailable; delegating to deep_thought instead of deterministic semantic routing",
        f"catalog_version={result.catalog_version}",
    ]
    if llm_decision.reason:
        reason_parts.append(f"llm_fallback_reason={llm_decision.reason}")
    return finalize_decision(
        RouteDecision(
            route="deep_thought",
            agents=[
                "deepthinking_agent",
                "speaker_agent",
            ],
            intent="deep_thought_router_unavailable",
            confidence=0.50,
            language=request.language or "auto",
            priority="normal",
            needs_agent=True,
            should_speak=True,
            candidate_capabilities=result.matches,
            reason="; ".join(reason_parts),
            source="fallback",
            metadata={"thinking_ack_allowed": False},
        ),
        request,
        source="fallback",
    )


@app.post("/route", response_model=RouteDecision)
async def route(request: RouteRequest) -> RouteDecision:
    start = time.perf_counter()
    request.text = request.text.strip()

    decision: RouteDecision | None = None
    emergency_matched = False
    priority = route_by_priority_rules(request)
    if priority is not None:
        decision = await _review_priority_interrupt(request, priority)
        emergency_matched = True

    if decision is None:
        catalog_result_task = asyncio.create_task(capability_catalog.search(
            text=request.text,
            language=request.language,
        ))
        snapshot_method = getattr(capability_catalog, "snapshot", None)
        catalog_snapshot_task = (
            asyncio.create_task(snapshot_method()) if callable(snapshot_method) else None
        )
        catalog_result = await catalog_result_task
        if catalog_snapshot_task is not None:
            try:
                catalog_snapshot = await catalog_snapshot_task
            except Exception as exc:
                logger.warning("capability catalog prompt snapshot failed: %s", exc)
                catalog_snapshot = {}
        else:
            catalog_snapshot = {}
        prompt_capabilities_common = _prompt_catalog_capabilities(
            catalog_snapshot,
            scope="common",
        )
        prompt_capabilities_all = _prompt_catalog_capabilities(
            catalog_snapshot,
            scope="all",
        )
        if not prompt_capabilities_common:
            prompt_capabilities_common = list(catalog_result.matches or [])
        if not prompt_capabilities_all:
            prompt_capabilities_all = _unique_capabilities(
                [*prompt_capabilities_common, *list(catalog_result.matches or [])]
            )
        _attach_stage_context(
            request,
            emergency_matched=False,
            catalog_result=catalog_result,
            prompt_capabilities_common=prompt_capabilities_common,
            prompt_capabilities_all=prompt_capabilities_all,
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
                    decision = _deep_thought_from_low_confidence(request, llm_decision)
                else:
                    decision = _validate_llm_capability_decision(
                        request,
                        llm_decision,
                        catalog_result,
                    )
            elif llm_decision.source == "fallback":
                decision = _deep_thought_router_unavailable_decision(
                    request,
                    catalog_result,
                    llm_decision=llm_decision,
                )
                if decision is None:
                    decision = llm_decision

        if decision is None:
            reason = (
                "llm_no_route"
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
