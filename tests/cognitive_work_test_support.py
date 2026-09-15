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


def word_free_model_fixture(raw: dict[str, Any]) -> dict[str, Any]:
    """Separate legacy test wording from a Work-only model reply, before inference.

    This is fixture authoring only. Production decoders never strip forbidden fields.
    Tests explicitly supply their separate SC words to social_fixture_resolution.
    """
    import copy
    result = copy.deepcopy(raw)
    result.pop("response_text", None)
    result.pop("auxiliary_activities", None)
    result.pop("communicative_acts", None)
    outcomes = result.get("goal_outcomes") or {}
    for outcome in outcomes.values() if isinstance(outcomes, dict) else outcomes:
        outcome.pop("response_text", None)
        if outcome.get("disposition") == "respond":
            outcome.setdefault("precedes_step_ids", [])
            outcome.setdefault("follows_step_ids", [])
    return result


def social_fixture_resolution(request, text="Fixture response."):
    from shared.chromie_contracts.social_cognition import SocialCognitionResolution
    acts = [{"activity_id": "fixture-act-" + str(index), "text": text,
             "function": "ask" if need.kind in {"confirmation", "input"} else "respond",
             "truth_stage": "context_grounded", "delivery_phase": need.delivery_phase or "immediate",
             "source_goal_ids": need.source_goal_ids,
             "source_responsibility_refs": need.source_responsibility_refs,
             "addressed_need_ids": [need.need_id]}
            for index, need in enumerate(request.communication_needs)]
    return SocialCognitionResolution(request_id=request.request_id,
        snapshot_digest=request.snapshot_digest(), disposition="communicate" if acts else "silence",
        activities=acts, need_outcomes={need.need_id: "covered" for need in request.communication_needs},
        reason_summary="Explicit SC fixture, independent of the Work reply.", model_call_count=1)


async def social_fixture_response(adapter, *, plan, session_id, language, context=None, text="Fixture response."):
    from shared.chromie_contracts.social_cognition import SocialCognitionRequest
    request = SocialCognitionRequest(request_id="fixture:" + plan.plan_id, trigger="work_state",
        source_refs=[plan.plan_id], goal_ids=plan.goal_ids, language=language,
        communication_needs=plan.communication_needs, context={**(context or {}), "canonical_plan_resolution": plan.prompt_projection()})
    return await adapter.build_social_cognition_response(plan=plan, request=request,
        resolution=social_fixture_resolution(request, text), session_id=session_id,
        language=language, context=context)


def ordinary_plan_schema(schema):
    """Inspect the ordinary branch; callers retain the original for wire validation."""
    if "anyOf" in schema and any(name.startswith("Waiting") for name in schema.get("$defs", {})):
        return {**schema["anyOf"][0], "$defs": schema["$defs"]}
    return schema
