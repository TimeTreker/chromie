from __future__ import annotations

import logging
from typing import Any, Callable

from shared.chromie_contracts.interaction import InteractionResponse
from shared.chromie_contracts.user_turn import UserTurnEnvelope
from orchestrator.runtime.capability_runtime import CapabilityRuntimeResult
from orchestrator.runtime.cognitive_runtime import CognitiveRuntimeResolution

logger = logging.getLogger(__name__)


def record_execution_experience_safely(
    *,
    response: InteractionResponse,
    execution: CapabilityRuntimeResult | None,
    session_id: str | None,
    confirmed_request_ids: set[str] | None,
    prepare_response: Callable[..., InteractionResponse],
    record_experience: Callable[..., None],
    session_log: Callable[..., None],
    errors: list[str] | None = None,
) -> None:
    """Keep observability preparation/write failures outside interaction semantics."""

    try:
        prepared = prepare_response(
            response,
            session_id=session_id,
            confirmed_request_ids=confirmed_request_ids,
        )
        record_kwargs: dict[str, Any] = {
            "response": prepared,
            "execution": execution,
            "session_id": session_id,
        }
        effective_errors = list(errors or ())
        metadata = prepared.metadata if isinstance(prepared.metadata, dict) else {}
        if metadata.get("semantic_status") == "failed":
            stage = str(metadata.get("semantic_failure_stage") or "cognition")
            failure_class = str(
                metadata.get("semantic_failure_class") or "semantic_failure"
            )
            failure_error = str(metadata.get("semantic_failure_error") or "").strip()
            semantic_error = f"{stage}:{failure_class}"
            if failure_error:
                semantic_error += f": {failure_error}"
            if semantic_error not in effective_errors:
                effective_errors.append(semantic_error)
        if effective_errors:
            record_kwargs["errors"] = effective_errors
        record_experience(**record_kwargs)
    except Exception as exc:  # pragma: no cover - defensive containment
        logger.warning(
            "Execution experience preparation failed: %s",
            exc,
            exc_info=True,
        )
        session_log(
            session_id,
            "experience_prepare_failed: error_type=%s error=%s",
            type(exc).__name__,
            exc,
        )


def record_cognitive_runtime_evidence(
    recorder: Any,
    resolution: CognitiveRuntimeResolution,
    *,
    session_id: str,
    user_text: str,
    session_log: Callable[..., None],
) -> None:
    """Record bounded cognitive runtime evidence without affecting semantics."""

    try:
        recorder.record(
            resolution,
            sid=session_id,
            text=user_text,
        )
    except Exception as exc:
        logger.warning("Cognitive runtime evidence write failed: %s", exc, exc_info=True)
        session_log(
            session_id,
            "cognitive_runtime_evidence_failed: error_type=%s error=%s",
            type(exc).__name__,
            exc,
        )


def record_cognitive_gateway_evidence(
    recorder: Any,
    turn_envelope: UserTurnEnvelope,
    *,
    user_text: str,
    session_log: Callable[..., None],
    context_snapshot: Any | None = None,
    attention_review: Any | None = None,
) -> None:
    """Record Gateway evidence fail-softly after the admission decision exists."""

    try:
        recorder.record_gateway(
            turn_envelope,
            text=user_text,
            context_snapshot=context_snapshot,
            attention_review=attention_review,
        )
    except Exception as exc:
        logger.warning("Cognitive Gateway evidence write failed: %s", exc, exc_info=True)
        session_log(
            turn_envelope.session_id,
            "cognitive_gateway_evidence_failed: error_type=%s error=%s",
            type(exc).__name__,
            exc,
        )
