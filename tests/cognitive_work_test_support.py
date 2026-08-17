from __future__ import annotations

from typing import Any

from shared.chromie_contracts.core_interpretation import (
    CognitiveResponsibilityProposal,
    CognitiveWorkRequest,
)


def cognitive_work_request(
    *,
    text: str,
    sid: str | None = None,
    language: str | None = None,
    context: dict[str, Any] | None = None,
    history: list[dict[str, Any]] | None = None,
    outcome: str | None = None,
    local_ref: str = "test_responsibility",
    confidence: float = 1.0,
) -> CognitiveWorkRequest:
    return CognitiveWorkRequest(
        sid=sid,
        text=text,
        language=language,
        responsibilities=[
            CognitiveResponsibilityProposal(
                local_ref=local_ref,
                outcome=outcome or text,
                confidence=confidence,
            )
        ],
        interpretation_confidence=confidence,
        context=context or {},
        history=history or [],
    )
