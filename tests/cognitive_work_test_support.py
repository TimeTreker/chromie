from __future__ import annotations

import json
from typing import Any

from shared.chromie_contracts.core_interpretation import (
    CognitiveResponsibilityProposal,
    CognitiveWorkRequest,
)


class PlannerActivationFixture:
    """Explicit model decision for episodes whose next step is Planner re-entry."""

    async def resolve_cognitive_activation(self, _session, *, request, **_kwargs):
        from shared.chromie_contracts.cognitive_activation import CognitiveActivationDecision

        decision = CognitiveActivationDecision(
            cognitive_requests=[{
                "authority": "planner", "goal_ids": request.goal_ids,
                "responsibility_refs": request.responsibility_refs,
                "source_refs": request.source_refs,
                "reason_summary": "Scripted episode requires Planner continuation.",
            }],
            confidence=1.0,
            reason_summary="Explicit Activation fixture; no native cognition claim.",
        )
        decision.validate_request(request)
        return decision


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
    """Inspect the ordinary branch; callers retain the original for wire validation.

    Native disposition-assignment branches are viewed as one shape: each field offers
    what any branch offers (the bounds the decoder lifted before the branches existed).
    """
    if "anyOf" in schema and any(name.startswith("Waiting") for name in schema.get("$defs", {})):
        schema = {**schema["anyOf"][0], "$defs": schema["$defs"]}
    if "properties" not in schema and isinstance(schema.get("oneOf"), list):
        definitions = schema.get("$defs", {})
        view = _offered_by_any(schema["oneOf"])
        for outcome in view["properties"].get("goal_outcomes", {}).get("properties", {}).values():
            if isinstance(outcome.get("oneOf"), list):
                outcome["oneOf"] = [definitions[item["$ref"].rsplit("/", 1)[-1]] if "$ref" in item else item
                                    for item in outcome["oneOf"]]
        return {**{key: value for key, value in schema.items() if key != "oneOf"}, **view}
    return schema


def plan_assignment_branches(schema):
    """The ordinary plan's native disposition-assignment branches (one when unbranched)."""
    if "anyOf" in schema and any(name.startswith("Waiting") for name in schema.get("$defs", {})):
        schema = schema["anyOf"][0]
    return schema.get("oneOf", [schema]) if "properties" not in schema else [schema]


def _offered_by_any(shapes):
    first = shapes[0]
    if not all(isinstance(shape, dict) for shape in shapes):
        return first
    view = dict(first)
    for key in {key for shape in shapes for key in shape}:
        values = [shape[key] for shape in shapes if key in shape]
        if key == "enum":
            view[key] = list(dict.fromkeys(value for item in values for value in item))
        elif key == "minItems":
            view[key] = min(values) if len(values) == len(shapes) else 0
        elif key == "maxItems":
            if len(values) == len(shapes):
                view[key] = max(values)
            else:
                view.pop(key, None)
        elif key in {"oneOf", "anyOf"}:
            unique = {json.dumps(item, sort_keys=True): item for value in values for item in value}
            view[key] = list(unique.values())
        elif key == "properties":
            names = list(dict.fromkeys(name for value in values for name in value))
            view[key] = {name: _offered_by_any([value[name] for value in values if name in value])
                         for name in names}
        else:
            view[key] = values[0]
    return view


def goal_outcome_branch(outcome, disposition=None):
    """One per-disposition native branch of a Goal outcome (the first when unspecified)."""
    branches = outcome.get("oneOf", [outcome])
    if disposition is None:
        return branches[0]
    return next(item for item in branches if item["properties"]["disposition"]["enum"] == [disposition])


def goal_outcome_dispositions(outcome):
    return [value for item in outcome.get("oneOf", [outcome]) for value in item["properties"]["disposition"]["enum"]]
