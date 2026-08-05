from __future__ import annotations

from .schema import RouteDecision, RouteRequest, detect_language, finalize_decision


class InterpretationUnavailableError(RuntimeError):
    """Raised when semantic interpretation did not produce a valid result."""

    def __init__(self, reason: str) -> None:
        self.reason = " ".join(str(reason or "interpretation unavailable").split())
        super().__init__(self.reason)



def fallback_decision(request: RouteRequest, *, reason: str | None = None) -> RouteDecision:
    """Handle empty input or report that semantic interpretation is unavailable.

    Non-empty input must never be assigned a plausible semantic lane merely
    because model inference, validation, or catalog grounding failed.
    """

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

    raise InterpretationUnavailableError(
        reason or "Goal Interpreter did not produce a valid semantic result"
    )
