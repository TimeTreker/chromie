from .schema import RouteDecision, RouteRequest, detect_language, finalize_decision

try:
    from chromie_contracts.reflex import DEFAULT_REFLEX_FILTER
except ImportError:  # pragma: no cover - repository development path
    from shared.chromie_contracts.reflex import DEFAULT_REFLEX_FILTER


def route_by_priority_rules(request: RouteRequest) -> RouteDecision | None:
    """Handle only safety-critical interruption and obvious non-speech noise."""

    lang = request.language or detect_language(request.text)
    outcome = DEFAULT_REFLEX_FILTER.evaluate(request.text, language=lang)
    if outcome.action == "interrupt":
        return finalize_decision(
            RouteDecision(
                route="interrupt",
                agents=[],
                intent=outcome.intent,
                confidence=outcome.confidence,
                language=outcome.language,
                priority=outcome.priority,
                interrupt_current=outcome.interrupt_current,
                needs_agent=False,
                should_speak=outcome.should_speak,
                reason=outcome.reason,
                source="rules",
                metadata={"reflex_outcome": outcome.model_dump(mode="json")},
            ),
            request,
            source="rules",
        )
    if outcome.action != "ignore":
        return None

    return finalize_decision(
        RouteDecision(
            route="ignore",
            agents=[],
            intent=outcome.intent,
            confidence=outcome.confidence,
            language=outcome.language,
            priority=outcome.priority,
            needs_agent=False,
            should_speak=outcome.should_speak,
            reason=outcome.reason,
            source="rules",
            metadata={"reflex_outcome": outcome.model_dump(mode="json")},
        ),
        request,
        source="rules",
    )
