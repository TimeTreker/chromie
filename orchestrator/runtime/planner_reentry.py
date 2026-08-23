"""Pure Host policy for Planner re-entry from trusted runtime Evidence.

This module does not decide Goal meaning, author speech, invoke Planner, or mutate
Runtime. It projects and validates the immutable provenance that the Host must
supply when a meaningful runtime transition reactivates the existing Planner.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from shared.chromie_contracts.core_interpretation import (
    CognitiveResponsibilityProposal,
)
from shared.chromie_contracts.execution_outcome import ExecutionEvidence
from shared.chromie_contracts.interaction import InteractionResponse
from shared.chromie_contracts.plan import CanonicalPlan
from shared.chromie_contracts.tool_result import ToolResultEvidence


def _normalized_text(value: object) -> str:
    return " ".join(str(value or "").strip().split())


def execution_outcome_user_text(
    source_response: InteractionResponse,
    plan: object,
) -> str:
    """Recover the immutable originating user text for result-bound cognition."""

    metadata = (
        source_response.metadata
        if isinstance(source_response.metadata, dict)
        else {}
    )
    envelope = metadata.get("user_turn_envelope")
    normalized_input = (
        envelope.get("normalized_input")
        if isinstance(envelope, dict)
        else None
    )
    if isinstance(normalized_input, dict):
        text = str(normalized_input.get("text") or "").strip()
        if text:
            return text
    return str(getattr(plan, "goal_summary", "") or "").strip()


def terminal_evidence_relevance(
    *,
    source_response: InteractionResponse,
    evidence: ExecutionEvidence,
    goal_bindings: Sequence[Mapping[str, Any]],
) -> tuple[bool, str]:
    """Check that terminal Evidence still belongs to current open Responsibility.

    The Evidence remains valid history even when this check fails. The result only
    governs whether that historical fact may authorize a new Planner decision now.
    """

    metadata = (
        source_response.metadata
        if isinstance(source_response.metadata, dict)
        else {}
    )
    expected_plan_id = str(metadata.get("canonical_plan_id") or "").strip()
    expected_fingerprint = str(
        metadata.get("canonical_plan_fingerprint") or ""
    ).strip()
    if not expected_plan_id or not expected_fingerprint:
        return False, "source_plan_binding_missing"

    bindings = {
        str(item.get("goal_id") or "").strip(): item
        for item in goal_bindings
        if str(item.get("goal_id") or "").strip()
    }
    if not evidence.source_goal_ids:
        return False, "source_goal_binding_missing"
    for goal_id in evidence.source_goal_ids:
        binding = bindings.get(goal_id)
        if not binding or binding.get("found") is not True:
            return False, "goal_binding_missing"
        if str(binding.get("responsibility_status") or "") != "open":
            return False, "goal_responsibility_terminal"
        if str(binding.get("canonical_plan_id") or "") != expected_plan_id:
            return False, "canonical_plan_superseded"
        if (
            str(binding.get("canonical_plan_fingerprint") or "")
            != expected_fingerprint
        ):
            return False, "canonical_plan_superseded"
        request_ids = {
            str(item).strip()
            for item in binding.get("request_ids") or ()
            if str(item).strip()
        }
        if evidence.request_id not in request_ids:
            return False, "request_binding_superseded"
    return True, "current"



def provider_state_relevance(
    *,
    source_response: InteractionResponse,
    request_id: str,
    source_goal_ids: Sequence[str],
    goal_bindings: Sequence[Mapping[str, Any]],
) -> tuple[bool, str]:
    """Check that a live provider-state event still belongs to current Work.

    Provider progress is observational Runtime state, not completion Evidence.  It may
    reactivate Planner only while the originating request is still bound to the same
    open Responsibility and canonical Plan.
    """

    normalized_request_id = str(request_id or "").strip()
    normalized_goal_ids = [
        str(value).strip() for value in source_goal_ids if str(value).strip()
    ]
    if not normalized_request_id or not normalized_goal_ids:
        return False, "source_binding_missing"
    metadata = (
        source_response.metadata
        if isinstance(source_response.metadata, dict)
        else {}
    )
    expected_plan_id = str(metadata.get("canonical_plan_id") or "").strip()
    expected_fingerprint = str(
        metadata.get("canonical_plan_fingerprint") or ""
    ).strip()
    if not expected_plan_id or not expected_fingerprint:
        return False, "source_plan_binding_missing"

    bindings = {
        str(item.get("goal_id") or "").strip(): item
        for item in goal_bindings
        if str(item.get("goal_id") or "").strip()
    }
    for goal_id in normalized_goal_ids:
        binding = bindings.get(goal_id)
        if not binding or binding.get("found") is not True:
            return False, "goal_binding_missing"
        if str(binding.get("responsibility_status") or "") != "open":
            return False, "goal_responsibility_terminal"
        if str(binding.get("canonical_plan_id") or "") != expected_plan_id:
            return False, "canonical_plan_superseded"
        if (
            str(binding.get("canonical_plan_fingerprint") or "")
            != expected_fingerprint
        ):
            return False, "canonical_plan_superseded"
        request_ids = {
            str(item).strip()
            for item in binding.get("request_ids") or ()
            if str(item).strip()
        }
        if normalized_request_id not in request_ids:
            return False, "request_binding_superseded"
    return True, "current"


def meaningful_provider_state(
    progress: Mapping[str, Any],
) -> dict[str, Any]:
    """Project only provider state transitions worth waking cognition for.

    Percent/heartbeat churn is intentionally ignored.  Runtime may publish progress
    frequently; Planner should wake only for explicit state/phase changes, waiting or
    blocked conditions, degradation, or member-state changes.
    """

    if not isinstance(progress, Mapping):
        return {}
    projected: dict[str, Any] = {}
    quiet_statuses = {"", "accepted", "scheduled", "running", "in_progress"}
    for key in ("status", "state", "phase", "condition", "waiting_for"):
        value = progress.get(key)
        if value is None:
            continue
        text = _normalized_text(value)
        if not text:
            continue
        if key in {"status", "state"} and text.lower() in quiet_statuses:
            continue
        projected[key] = text
    for key in ("blocked", "degraded", "paused", "recovering"):
        if progress.get(key) is True:
            projected[key] = True
    member_status = progress.get("member_status")
    if isinstance(member_status, Mapping):
        meaningful_members = {
            str(member_id): _normalized_text(status)
            for member_id, status in member_status.items()
            if _normalized_text(status).lower() not in quiet_statuses
        }
        if meaningful_members:
            projected["member_status"] = meaningful_members
    return projected

def planner_reentry_responsibilities(
    *,
    source_response: InteractionResponse,
    goal_ids: Sequence[str],
) -> list[CognitiveResponsibilityProposal]:
    """Select the originating GI Responsibilities bound to the re-entered Goals.

    Missing provenance returns an empty list. A runtime callback must never invent a
    replacement Responsibility merely to keep cognition moving.
    """

    metadata = (
        source_response.metadata
        if isinstance(source_response.metadata, dict)
        else {}
    )
    raw_interpretation = metadata.get("goal_interpretation")
    responsibilities = (
        raw_interpretation.get("responsibilities")
        if isinstance(raw_interpretation, dict)
        else []
    )
    parsed: dict[str, CognitiveResponsibilityProposal] = {}
    for item in responsibilities if isinstance(responsibilities, list) else []:
        if not isinstance(item, dict):
            continue
        try:
            responsibility = CognitiveResponsibilityProposal.model_validate(item)
        except (TypeError, ValueError):
            continue
        parsed[responsibility.local_ref] = responsibility
    if not parsed:
        return []

    normalized_goal_ids = {
        str(goal_id).strip() for goal_id in goal_ids if str(goal_id).strip()
    }
    wanted_refs: set[str] = set()
    association = metadata.get("goal_association")
    if isinstance(association, dict):
        for item in association.get("associations") or []:
            if not isinstance(item, dict):
                continue
            target_goal_ids = {
                str(value).strip()
                for value in item.get("target_goal_ids") or []
                if str(value).strip()
            }
            if target_goal_ids.intersection(normalized_goal_ids):
                wanted_refs.update(
                    str(value).strip()
                    for value in item.get("source_responsibility_refs") or []
                    if str(value).strip()
                )
        for item in association.get("new_goals") or []:
            if not isinstance(item, dict):
                continue
            if str(item.get("goal_id") or "").strip() not in normalized_goal_ids:
                continue
            wanted_refs.update(
                str(value).strip()
                for value in item.get("source_responsibility_refs") or []
                if str(value).strip()
            )

    if wanted_refs:
        return [
            value
            for key, value in parsed.items()
            if key in wanted_refs
        ]
    if len(parsed) == 1 and len(normalized_goal_ids) == 1:
        # One Responsibility and one Goal have no association ambiguity. This is
        # identity normalization over supplied GI evidence, not new semantics.
        return list(parsed.values())
    return []


def planner_reentry_repeats_completed_activity(
    *,
    source_response: InteractionResponse,
    plan: CanonicalPlan,
    extra_context: Mapping[str, Any] | None,
    evidence: Sequence[ToolResultEvidence],
) -> bool:
    """Return true when a re-entry Plan repeats the exact terminal Activity."""

    completed_request_ids: set[str] = set()
    context = extra_context if isinstance(extra_context, Mapping) else {}
    terminal_request_id = str(context.get("terminal_request_id") or "").strip()
    if terminal_request_id and evidence and evidence[0].status == "completed":
        completed_request_ids.add(terminal_request_id)
    bundle = context.get("execution_outcome_bundle")
    if isinstance(bundle, dict):
        for item in bundle.get("evidence") or []:
            if not isinstance(item, dict) or item.get("status") != "completed":
                continue
            request_id = str(item.get("request_id") or "").strip()
            if request_id:
                completed_request_ids.add(request_id)
    if not completed_request_ids:
        return False

    completed = [
        request
        for request in source_response.capabilities
        if request.request_id in completed_request_ids
    ]
    for step in plan.steps:
        for request in completed:
            source_goal_ids = {
                str(value).strip()
                for value in request.metadata.get("source_goal_ids") or []
                if str(value).strip()
            }
            if (
                step.capability_id == request.capability_id
                and step.args == request.args
                and set(step.source_goal_ids) == source_goal_ids
            ):
                return True
    return False


def suppress_already_delivered_speech(
    response: InteractionResponse,
    delivered_texts: Iterable[str],
) -> tuple[InteractionResponse, int]:
    """Drop exact speech deltas already delivered in the same session."""

    normalized_delivered = {
        text
        for value in delivered_texts
        if (text := _normalized_text(value))
    }
    if not normalized_delivered or not response.speech:
        return response, 0
    retained_speech = [
        speech
        for speech in response.speech
        if _normalized_text(speech.text) not in normalized_delivered
    ]
    suppressed_count = len(response.speech) - len(retained_speech)
    if suppressed_count <= 0:
        return response, 0
    return response.model_copy(update={"speech": retained_speech}), suppressed_count
