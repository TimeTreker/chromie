from __future__ import annotations

import re

from .schema import RouteDecision, RouteRequest, detect_language, finalize_decision


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _semantic_fallback_decision(
    request: RouteRequest,
    *,
    lang: str,
    reason: str | None,
) -> RouteDecision | None:
    text = _norm(request.text)
    if not text:
        return None

    if _looks_like_memory_request(text):
        return finalize_decision(
            RouteDecision(
                route="memory",
                agents=["memory_agent", "speaker_agent"],
                intent="remember_user_preference",
                confidence=0.62,
                language=lang,
                priority="normal",
                needs_agent=True,
                should_speak=True,
                reason=reason or "Fallback semantic memory request",
                source="fallback",
            ),
            request,
            source="fallback",
        )

    if _looks_like_weather_or_lookup_request(text):
        return finalize_decision(
            RouteDecision(
                route="tool",
                agents=["tool_agent", "speaker_agent"],
                intent="weather_query",
                confidence=0.60,
                language=lang,
                priority="normal",
                needs_agent=True,
                should_speak=True,
                reason=reason or "Fallback semantic tool request",
                source="fallback",
            ),
            request,
            source="fallback",
        )

    if _looks_like_deep_thought_request(text):
        return finalize_decision(
            RouteDecision(
                route="deep_thought",
                agents=["deepthinking_agent", "speaker_agent"],
                intent="deep_thought_planning",
                confidence=0.61,
                language=lang,
                priority="normal",
                needs_agent=True,
                should_speak=True,
                reason=reason or "Fallback semantic deep-thought request",
                source="fallback",
                metadata={"thinking_ack_allowed": False},
            ),
            request,
            source="fallback",
        )

    return None


def _looks_like_memory_request(text: str) -> bool:
    if re.search(r"\b(?:remember|memorize|note|save|store)\s+(?:that\s+)?\b", text):
        return True
    if re.search(r"\b(?:make|take)\s+(?:a\s+)?note\b", text):
        return True
    if re.search(r"\b(?:my|our)\s+(?:favorite|preferred|preference)\b", text):
        return True
    return bool(re.search(r"(记住|记下|记一下|保存|偏好|喜欢)", text))


def _looks_like_weather_or_lookup_request(text: str) -> bool:
    if re.search(r"\b(?:weather|forecast|rain|raining|temperature)\b", text):
        return bool(
            re.search(r"\b(?:check|look\s+up|search|find|tell|will|is|does|today|tomorrow)\b", text)
            or "?" in text
        )
    return bool(re.search(r"(天气|下雨|降雨|气温|预报|查询|查一下)", text))


def _looks_like_deep_thought_request(text: str) -> bool:
    planning_terms = (
        "think carefully",
        "split the work",
        "break down",
        "step by step",
        "architecture",
        "implementation plan",
        "design the",
    )
    if any(term in text for term in planning_terms):
        return True
    return bool(
        re.search(r"\b(?:plan|design|implement|build|add)\b", text)
        and re.search(r"\b(?:long[- ]term memory|memory architecture|task session|multi[- ]step)\b", text)
    )


def fallback_decision(request: RouteRequest, *, reason: str | None = None) -> RouteDecision:
    """Safe default when rules and LLM routing cannot produce a valid route."""

    lang = request.language or detect_language(request.text)

    if not request.text.strip():
        route = RouteDecision(
            route="ignore",
            agents=[],
            intent="empty_input",
            confidence=0.80,
            language=lang,
            priority="low",
            needs_agent=False,
            should_speak=False,
            reason=reason or "Empty input",
            source="fallback",
        )
        return finalize_decision(route, request, source="fallback")

    semantic = _semantic_fallback_decision(request, lang=lang, reason=reason)
    if semantic is not None:
        return semantic

    route = RouteDecision(
        route="chat",
        agents=["conversation_agent", "speaker_agent"],
        intent="general_conversation",
        confidence=0.45,
        language=lang,
        priority="normal",
        needs_agent=True,
        should_speak=True,
        reason=reason or "Fallback to general chat",
        source="fallback",
    )
    return finalize_decision(route, request, source="fallback")
