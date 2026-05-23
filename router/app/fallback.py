from __future__ import annotations

from .schema import RouteDecision, RouteRequest, detect_language, finalize_decision


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
