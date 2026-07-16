from __future__ import annotations

import copy
from typing import Any, Literal

try:
    from chromie_contracts.plan import CanonicalPlan
except ImportError:  # pragma: no cover
    from shared.chromie_contracts.plan import CanonicalPlan

PlannerTier = Literal["fast", "deep"]


def expected_goal_ids(context: dict[str, Any] | None) -> list[str]:
    """Return the ordered canonical goal IDs accepted by Goal Association."""

    association = (context or {}).get("goal_association_resolution")
    if not isinstance(association, dict):
        return []

    ordered: list[str] = []
    seen: set[str] = set()

    def add(value: Any) -> None:
        text = " ".join(str(value or "").strip().split())
        if text and text not in seen:
            seen.add(text)
            ordered.append(text)

    for item in association.get("associations") or []:
        if not isinstance(item, dict):
            continue
        for goal_id in item.get("target_goal_ids") or []:
            add(goal_id)
    for item in association.get("new_goals") or []:
        if isinstance(item, dict):
            add(item.get("goal_id"))
    return ordered


def canonical_goal_grounding(context: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Build a compact immutable grounding block for planner prompts.

    Goal Association owns which goals exist. Planners receive only those IDs and
    their human-facing semantics; internal implementation concepts are omitted.
    """

    context = context or {}
    association = context.get("goal_association_resolution")
    active = context.get("active_goal_snapshots") or []
    active_by_id: dict[str, dict[str, Any]] = {}
    for item in active:
        if not isinstance(item, dict):
            continue
        goal_id = " ".join(str(item.get("goal_id") or "").strip().split())
        goal = item.get("goal") if isinstance(item.get("goal"), dict) else {}
        if goal_id:
            active_by_id[goal_id] = {
                "goal_id": goal_id,
                "description": goal.get("description") or item.get("last_user_update") or "",
                "source_text": goal.get("source_text") or item.get("last_user_update") or "",
                "constraints": goal.get("constraints") or {},
                "success_criteria": goal.get("success_criteria") or [],
            }

    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    if isinstance(association, dict):
        for item in association.get("associations") or []:
            if not isinstance(item, dict):
                continue
            for raw_id in item.get("target_goal_ids") or []:
                goal_id = " ".join(str(raw_id or "").strip().split())
                if goal_id and goal_id not in seen:
                    seen.add(goal_id)
                    result.append(active_by_id.get(goal_id, {"goal_id": goal_id}))
        for item in association.get("new_goals") or []:
            if not isinstance(item, dict):
                continue
            goal_id = " ".join(str(item.get("goal_id") or "").strip().split())
            if not goal_id or goal_id in seen:
                continue
            seen.add(goal_id)
            result.append(
                {
                    "goal_id": goal_id,
                    "description": item.get("description") or "",
                    "source_text": item.get("source_text") or "",
                    "constraints": item.get("constraints") or {},
                    "success_criteria": item.get("success_criteria") or [],
                }
            )
    return result


def canonical_plan_response_schema(
    *,
    planner_tier: PlannerTier,
    expected_goal_ids: list[str],
    allowed_skill_ids: list[str],
) -> dict[str, Any]:
    """Return a constrained CanonicalPlan schema for one planner request.

    This is a structural contract, not semantic rewriting. It limits generated
    IDs to the authoritative Goal Association result and limits leaves to the
    supplied executable capability catalog. Cross-field disposition invariants
    are represented in the decoder schema so invalid empty execute plans cannot
    be generated as valid structured output.
    """

    schema = copy.deepcopy(CanonicalPlan.model_json_schema())
    properties = schema.setdefault("properties", {})

    tier = properties.get("planner_tier")
    if isinstance(tier, dict):
        tier.clear()
        tier.update({"type": "string", "const": planner_tier})

    allowed_goals = list(dict.fromkeys(expected_goal_ids))
    allowed_skills = list(dict.fromkeys(allowed_skill_ids))

    top_goal_ids = properties.get("goal_ids")
    if isinstance(top_goal_ids, dict) and allowed_goals:
        top_goal_ids["items"] = {"type": "string", "enum": allowed_goals}
        top_goal_ids["minItems"] = len(allowed_goals)
        top_goal_ids["maxItems"] = len(allowed_goals)
        top_goal_ids["uniqueItems"] = True

    goal_list_fields = {
        "goal_ids",
        "source_goal_ids",
        "satisfied_goal_ids",
        "unmet_goal_ids",
    }

    def constrain(node: Any) -> None:
        if isinstance(node, dict):
            node_properties = node.get("properties")
            if isinstance(node_properties, dict):
                goal_id = node_properties.get("goal_id")
                if isinstance(goal_id, dict) and allowed_goals:
                    goal_id["enum"] = allowed_goals
                skill_id = node_properties.get("skill_id")
                if isinstance(skill_id, dict) and allowed_skills:
                    skill_id["enum"] = allowed_skills
                for field_name in goal_list_fields:
                    field = node_properties.get(field_name)
                    if isinstance(field, dict) and allowed_goals:
                        field["items"] = {"type": "string", "enum": allowed_goals}
                        field["uniqueItems"] = True
                        if field_name == "source_goal_ids":
                            field["minItems"] = 1
            for value in node.values():
                constrain(value)
        elif isinstance(node, list):
            for value in node:
                constrain(value)

    constrain(schema)

    variants: list[dict[str, Any]] = []

    def variant(disposition: str, *, coverage: Any, step_min: int | None = None,
                step_max: int | None = None, response_min: int | None = None,
                escalation_min: int | None = None, outcomes_min: int | None = None) -> dict[str, Any]:
        props: dict[str, Any] = {
            "planner_tier": {"const": planner_tier},
            "disposition": {"const": disposition},
            "coverage": coverage,
        }
        if step_min is not None or step_max is not None:
            value: dict[str, Any] = {"type": "array"}
            if step_min is not None:
                value["minItems"] = step_min
            if step_max is not None:
                value["maxItems"] = step_max
            props["steps"] = value
        if response_min is not None:
            props["response_text"] = {"type": "string", "minLength": response_min}
        if escalation_min is not None:
            props["escalation_reason"] = {"type": "string", "minLength": escalation_min}
        if outcomes_min is not None:
            props["goal_outcomes"] = {"type": "array", "minItems": outcomes_min}
        return {
            "type": "object",
            "properties": props,
            "required": ["planner_tier", "disposition", "coverage", "steps"],
        }

    variants.extend(
        [
            variant("execute", coverage={"const": "complete"}, step_min=1),
            variant("respond", coverage={"const": "complete"}, step_max=0, response_min=1),
        ]
    )
    if planner_tier == "fast":
        variants.append(
            variant(
                "escalate",
                coverage={"enum": ["partial", "uncertain"]},
                step_max=0,
                escalation_min=1,
            )
        )
    else:
        variants.extend(
            [
                variant("mixed", coverage={"const": "complete"}, step_min=1, outcomes_min=2),
                variant("clarify", coverage={"enum": ["partial", "uncertain"]}, step_max=0),
                variant("unavailable", coverage={"enum": ["complete", "partial", "uncertain"]}, step_max=0),
                variant("refused", coverage={"enum": ["complete", "partial", "uncertain"]}, step_max=0),
            ]
        )
    schema["oneOf"] = variants
    return schema
