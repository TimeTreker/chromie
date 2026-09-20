from __future__ import annotations

from shared.chromie_contracts.cognitive_activation import CognitiveActivationDecision


def activation_decision(request, *authorities: str) -> CognitiveActivationDecision:
    return CognitiveActivationDecision(
        cognitive_requests=[
            {
                "authority": authority,
                "goal_ids": list(request.goal_ids),
                "responsibility_refs": list(request.responsibility_refs),
                "source_refs": list(request.source_refs),
                "reason_summary": "Fixture explicitly requests this cognitive owner.",
            }
            for authority in authorities
        ],
        confidence=1.0,
        reason_summary="Fixture activation decision.",
    ).validate_request(request)


async def allow_activation(_session, *, request, timeout_ms=None):
    del timeout_ms
    return activation_decision(request, *request.allowed_authorities)


async def suppress_activation(_session, *, request, timeout_ms=None):
    del timeout_ms
    return activation_decision(request)
