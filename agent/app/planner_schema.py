from __future__ import annotations

import copy
from itertools import product
from typing import Any

try:
    from chromie_contracts.core_interpretation import CognitiveResponsibilityProposal
    from chromie_contracts.interaction import (
        MEDIA_CAPABILITY_IDS,
        VOCAL_PERFORMANCE_CAPABILITY_ID,
    )
    from chromie_contracts.plan import (
        FastPlannerAdvanceModelOutput,
        FastPlannerFirstResponseModelOutput,
    )
except ImportError:  # pragma: no cover
    from shared.chromie_contracts.core_interpretation import CognitiveResponsibilityProposal
    from shared.chromie_contracts.interaction import (
        MEDIA_CAPABILITY_IDS,
        VOCAL_PERFORMANCE_CAPABILITY_ID,
    )
    from shared.chromie_contracts.plan import (
        FastPlannerAdvanceModelOutput,
        FastPlannerFirstResponseModelOutput,
    )

from .prompt_projection import bounded_json
from .planner_grounding import (
    _argument_schema_accepts_canonical_binding,
    _goal_binding_map,
    _material_values_equal,
    _normalized_entity_type,
    semantic_numeric_values,
)
from .planner_validation import requires_sequential_safety_revision
from .planner_model_contract import (
    PlannerModelOutput,
    PlannerTier,
    ResourceResponsibilityCapabilityGroundingError,
)

def canonical_resource_argument_response_schema(
    base_schema: dict[str, Any],
    *,
    authoritative_goals: list[dict[str, Any]],
) -> dict[str, Any]:
    """Make one canonical resource Goal's provider projection read-only.

    Capability selection and step ownership remain model-authored. When the turn
    has exactly one canonical resource Goal, any selected Capability branch that
    accepts complete resource/source/recipient objects receives those objects as
    decoder constants instead of a second writable semantic copy.
    """

    resource_goals = [
        goal
        for goal in authoritative_goals
        if isinstance(goal, dict)
        and isinstance(goal.get("resource_responsibility"), dict)
    ]
    if len(resource_goals) != 1 or len(authoritative_goals) != 1:
        return base_schema
    responsibility = resource_goals[0]["resource_responsibility"]
    exact_arguments = {
        name: copy.deepcopy(responsibility[name])
        for name in ("resource", "source", "recipient")
        if isinstance(responsibility.get(name), dict)
    }
    if not exact_arguments:
        return base_schema

    schema = copy.deepcopy(base_schema)
    step_schema = schema.get("$defs", {}).get("PlannerModelStep")
    branches = step_schema.get("oneOf") if isinstance(step_schema, dict) else None
    if not isinstance(branches, list):
        return base_schema

    constrained = False
    for branch in branches:
        properties = branch.get("properties") if isinstance(branch, dict) else None
        args = properties.get("args") if isinstance(properties, dict) else None
        argument_properties = args.get("properties") if isinstance(args, dict) else None
        if not isinstance(argument_properties, dict):
            continue
        required = args.setdefault("required", [])
        for name, value in exact_arguments.items():
            if name not in argument_properties:
                continue
            argument_properties[name] = {"const": value}
            if isinstance(required, list) and name not in required:
                required.append(name)
            constrained = True
    if not constrained:
        return base_schema

    parameter_resolutions = schema.get("properties", {}).get(
        "parameter_resolutions"
    )
    if isinstance(parameter_resolutions, dict):
        parameter_resolutions["maxItems"] = 0
        parameter_resolutions["description"] = (
            "Canonical resource/source/recipient arguments are deterministic "
            "read-only projections and require no Planner-authored resolutions."
        )
    return schema

def canonical_goal_binding_argument_response_schema(
    base_schema: dict[str, Any],
    *,
    authoritative_goals: list[dict[str, Any]],
) -> dict[str, Any]:
    """Project exact Goal bindings into compatible step branches.

    This is a read-only DTO projection, not semantic argument mapping. Values are
    constrained only when every current Goal using that binding name agrees and
    the Capability argument schema accepts the canonical value unchanged. A
    Capability owner may also declare ``x-chromie-entity-type`` on an argument;
    that typed owner contract maps the argument to the same canonical Goal entity
    type without relying on its arbitrary field name.
    """

    values_by_name: dict[str, list[Any]] = {}
    values_by_entity_type: dict[str, list[Any]] = {}
    for goal in authoritative_goals:
        if not isinstance(goal, dict):
            continue
        for name, binding in _goal_binding_map(goal).items():
            value = binding.get("value")
            entity_type = _normalized_entity_type(binding.get("entity_type"))
            if not isinstance(goal.get("resource_responsibility"), dict):
                if not any(
                    _material_values_equal(existing, value, list_compatible=False)
                    for existing in values_by_name.setdefault(name, [])
                ):
                    values_by_name[name].append(value)
            if entity_type and not any(
                _material_values_equal(existing, value, list_compatible=False)
                for existing in values_by_entity_type.setdefault(entity_type, [])
            ):
                values_by_entity_type[entity_type].append(value)
    exact_bindings = {
        name: values[0]
        for name, values in values_by_name.items()
        if len(values) == 1
    }
    schema = copy.deepcopy(base_schema)
    step_schema = schema.get("$defs", {}).get("PlannerModelStep")
    branches = step_schema.get("oneOf") if isinstance(step_schema, dict) else None
    if not isinstance(branches, list):
        return base_schema

    constrained = False
    for branch in branches:
        properties = branch.get("properties") if isinstance(branch, dict) else None
        args = properties.get("args") if isinstance(properties, dict) else None
        argument_properties = args.get("properties") if isinstance(args, dict) else None
        if not isinstance(argument_properties, dict):
            continue
        required = args.setdefault("required", [])
        for argument_name, argument_schema in list(argument_properties.items()):
            if not isinstance(argument_schema, dict):
                continue
            entity_type = _normalized_entity_type(
                argument_schema.pop("x-chromie-entity-type", "")
            )
            if not entity_type:
                continue
            # The Capability owner, rather than Planner or Host heuristics,
            # declares which canonical semantic dimension this argument carries.
            # If that dimension is absent, only the provider's declared default
            # may enter the Plan; a model-authored narrower scope is forbidden.
            constrained = True
            values = values_by_entity_type.get(entity_type, [])
            if len(values) == 1 and _argument_schema_accepts_canonical_binding(
                argument_schema, values[0]
            ):
                argument_properties[argument_name] = {
                    "const": copy.deepcopy(values[0])
                }
                if isinstance(required, list) and argument_name not in required:
                    required.append(argument_name)
            elif not values and "default" in argument_schema:
                argument_properties[argument_name] = {
                    "const": copy.deepcopy(argument_schema["default"])
                }
        for name, value in exact_bindings.items():
            argument_schema = argument_properties.get(name)
            if not isinstance(argument_schema, dict) or not (
                _argument_schema_accepts_canonical_binding(argument_schema, value)
            ):
                continue
            argument_properties[name] = {"const": copy.deepcopy(value)}
            if isinstance(required, list) and name not in required:
                required.append(name)
            constrained = True
    return schema if constrained else base_schema

def resource_grounding_repair_response_schema(
    base_schema: dict[str, Any],
    *,
    error: ResourceResponsibilityCapabilityGroundingError | None,
    authoritative_goals: list[dict[str, Any]],
) -> dict[str, Any]:
    """Constrain repair to validator-proven complete resource work.

    The semantic choice comes from the model-authored resource Goal and catalog
    contracts already evaluated by the grounding validator. This projection only
    prevents a bounded repair from selecting the same incomplete Capability again
    or rewriting canonical nested resource arguments.
    """

    if error is None or not error.complete_capability_ids:
        return base_schema
    goals = [goal for goal in authoritative_goals if isinstance(goal, dict)]
    goal = next(
        (
            item
            for item in goals
            if " ".join(str(item.get("goal_id") or "").strip().split())
            == error.goal_id
        ),
        None,
    )
    if goal is None:
        return base_schema
    goal_id = " ".join(str(goal.get("goal_id") or "").strip().split())
    responsibility = goal.get("resource_responsibility")
    if (
        not goal_id
        or goal_id != error.goal_id
        or not isinstance(responsibility, dict)
    ):
        return base_schema
    exact_arguments = {
        name: copy.deepcopy(responsibility[name])
        for name in ("resource", "source", "recipient")
        if isinstance(responsibility.get(name), dict)
    }
    if not exact_arguments:
        return base_schema

    schema = copy.deepcopy(base_schema)
    step_schema = schema.get("$defs", {}).get("PlannerModelStep")
    if not isinstance(step_schema, dict):
        return base_schema
    branches = step_schema.get("oneOf")
    if not isinstance(branches, list):
        return base_schema
    complete_ids = set(error.complete_capability_ids)
    retained: list[dict[str, Any]] = []
    complete_branches: list[dict[str, Any]] = []
    for branch in branches:
        if not isinstance(branch, dict):
            continue
        properties = branch.get("properties")
        if not isinstance(properties, dict):
            continue
        capability = properties.get("capability_id")
        identifiers = capability.get("enum") if isinstance(capability, dict) else None
        is_complete_capability = (
            isinstance(identifiers, list)
            and len(identifiers) == 1
            and identifiers[0] in complete_ids
        )
        if (
            not isinstance(identifiers, list)
            or len(identifiers) != 1
        ):
            continue
        if len(goals) == 1 and not is_complete_capability:
            continue
        args = properties.get("args")
        argument_properties = (
            args.get("properties") if isinstance(args, dict) else None
        )
        if not isinstance(argument_properties, dict):
            continue
        if is_complete_capability:
            required = args.setdefault("required", [])
            for name, value in exact_arguments.items():
                if name not in argument_properties:
                    continue
                argument_properties[name] = {"const": value}
                if isinstance(required, list) and name not in required:
                    required.append(name)
            complete_branches.append(branch)
        retained.append(branch)
    if not retained or not complete_branches:
        return base_schema
    step_schema["oneOf"] = retained
    capability_property = step_schema.get("properties", {}).get("capability_id")
    if isinstance(capability_property, dict):
        capability_property["enum"] = sorted(
            {
                branch["properties"]["capability_id"]["enum"][0]
                for branch in retained
            }
        )
    steps = schema.get("properties", {}).get("steps")
    if isinstance(steps, dict):
        steps["minItems"] = 1
        if len(goals) == 1:
            steps["maxItems"] = 1
        else:
            steps["contains"] = {
                "type": "object",
                "properties": {
                    "capability_id": {
                        "type": "string",
                        "enum": sorted(complete_ids),
                    },
                    "source_goal_ids": {
                        "type": "array",
                        "contains": {"const": error.goal_id},
                        "minContains": 1,
                    },
                },
                "required": ["capability_id", "source_goal_ids"],
            }
            steps["minContains"] = 1
    parameter_resolutions = schema.get("properties", {}).get(
        "parameter_resolutions"
    )
    if isinstance(parameter_resolutions, dict) and len(goals) == 1:
        parameter_resolutions["maxItems"] = 0
    return schema

def canonical_plan_response_schema(
    *,
    planner_tier: PlannerTier,
    expected_goal_ids: list[str],
    allowed_capability_ids: list[str],
    capability_input_schemas: dict[str, dict[str, Any]] | None = None,
    response_only: bool = False,
    requires_execution: bool = False,
    response_goal_ids: list[str] | None = None,
    provider_vocal_goal_ids: list[str] | None = None,
    provider_media_goal_operations: dict[str, str] | None = None,
    unavailable_information_goal_ids: list[str] | None = None,
    single_step_goal_ids: list[str] | None = None,
    required_numeric_goal_values: dict[str, list[int | float]] | None = None,
) -> dict[str, Any]:
    """Return one flat, constrained model-output schema for a planner request.

    This schema deliberately excludes the host-owned CanonicalPlan envelope.
    The host supplies its plan identity, tier, schema version, and exact Goal
    Association IDs after validating this semantic DTO. Cross-field invariants
    remain enforced by ``PlannerModelOutput`` and ``CanonicalPlan``. A planner
    may regenerate once only when this DTO is mechanically malformed; semantic
    rejection is not a same-tier repair trigger. Fast Planner uses the same decoder-tight
    per-goal shape for one or many goals so the schema never instructs the model
    to omit fields that deterministic validation requires.
    """

    if planner_tier == "fast":
        schema = fast_multi_goal_response_schema(
            expected_goal_ids=expected_goal_ids,
            allowed_capability_ids=allowed_capability_ids,
            capability_input_schemas=capability_input_schemas,
            response_only=response_only,
            requires_execution=requires_execution,
            response_goal_ids=response_goal_ids,
        )
        schema["title"] = "FastPlannerModelOutput"
        return schema

    schema = copy.deepcopy(PlannerModelOutput.model_json_schema())
    schema["title"] = (
        "FastPlannerModelOutput" if planner_tier == "fast" else "DeepPlannerModelOutput"
    )
    properties = schema.setdefault("properties", {})
    required = schema.setdefault("required", [])
    for field_name in (
        "disposition",
        "coverage",
        "confidence",
        "goal_summary",
        "response_text",
        "steps",
        "escalation_reason",
        "unresolved",
        "parameter_resolutions",
        "goal_outcomes",
        "goal_satisfaction",
        "plan_relation",
        "user_confirmation_required",
    ):
        if field_name not in required:
            required.append(field_name)

    disposition = properties.get("disposition")
    if isinstance(disposition, dict):
        if response_only:
            disposition["enum"] = [
                "respond",
                "clarify",
                "unavailable",
                "refused",
            ]
        elif requires_execution:
            disposition["enum"] = (
                ["execute", "mixed", "clarify", "unavailable", "refused"]
                if response_goal_ids
                else ["execute", "clarify", "unavailable", "refused"]
            )
        else:
            disposition["enum"] = [
                "respond",
                "execute",
                "mixed",
                "clarify",
                "unavailable",
                "refused",
            ]

    planner_response_text = properties.get("response_text")
    if isinstance(planner_response_text, dict) and requires_execution:
        planner_response_text["description"] = (
            "Optional prospective conversational delta for executable work. Use "
            "Interaction Context to avoid repeating already delivered or pending "
            "speech. This field never satisfies the effectful Goal and never proves "
            "execution or an external result."
        )

    allowed_goals = list(dict.fromkeys(expected_goal_ids))
    allowed_capabilities = list(dict.fromkeys(allowed_capability_ids))
    response_goal_set = set(response_goal_ids or []).intersection(allowed_goals)
    single_step_goal_set = set(single_step_goal_ids or []).intersection(
        allowed_goals
    )
    unavailable_information_goal_set = set(
        unavailable_information_goal_ids or []
    ).intersection(allowed_goals)
    if (
        planner_tier == "deep"
        and unavailable_information_goal_set
        and unavailable_information_goal_set == set(allowed_goals)
        and isinstance(disposition, dict)
    ):
        disposition["enum"] = ["unavailable", "refused"]
    provider_vocal_goal_set = set(provider_vocal_goal_ids or []).intersection(
        allowed_goals
    )
    provider_media_goal_operations = {
        goal_id: operation
        for goal_id, operation in (provider_media_goal_operations or {}).items()
        if goal_id in allowed_goals and operation in MEDIA_CAPABILITY_IDS
    }
    vocal_capability_available = VOCAL_PERFORMANCE_CAPABILITY_ID in allowed_capabilities
    unavailable_provider_vocal_goal_set = (
        provider_vocal_goal_set if not vocal_capability_available else set()
    )
    unavailable_provider_media_goal_set = {
        goal_id
        for goal_id, operation in provider_media_goal_operations.items()
        if MEDIA_CAPABILITY_IDS[operation] not in allowed_capabilities
    }
    executable_source_goal_ids = [
        goal_id
        for goal_id in allowed_goals
        if goal_id
        not in (
            unavailable_provider_vocal_goal_set
            | unavailable_provider_media_goal_set
            | unavailable_information_goal_set
        )
    ]
    known_unavailable_goal_set = (
        unavailable_provider_vocal_goal_set
        | unavailable_provider_media_goal_set
        | unavailable_information_goal_set
    )
    if (
        requires_execution
        and executable_source_goal_ids
        and known_unavailable_goal_set
        and isinstance(disposition, dict)
    ):
        # A request can contain independently executable work alongside a Goal
        # whose typed provider contract is deterministically unavailable.  The
        # complete aggregate result is then ``mixed`` even when no Goal is a
        # conversational-response Goal.  Keep that valid result representable
        # at the decoder boundary; the per-Goal schemas and semantic validator
        # still decide which remaining Goals are actually executable.
        disposition["enum"] = [
            "execute",
            "mixed",
            "clarify",
            "unavailable",
            "refused",
        ]

    if unavailable_provider_vocal_goal_set:
        planner_response_text = properties.get("response_text")
        if isinstance(planner_response_text, dict):
            planner_response_text.pop("maxLength", None)
            planner_response_text["minLength"] = 1
            planner_response_text["description"] = (
                "Required natural aggregate limitation: explicitly state that the "
                "provider-required vocal performance cannot be performed with the "
                "available capabilities. Never claim, promise, or imply that the "
                "unavailable vocal work will happen. Independent executable work may "
                "still be described prospectively."
            )

    if requires_execution and not response_goal_set:
        planner_response_text = properties.get("response_text")
        if isinstance(planner_response_text, dict):
            planner_response_text.pop("maxLength", None)
            planner_response_text["description"] = (
                "Use an empty string only for pure executable work. A terminal "
                "clarify, unavailable, or refused result must contain the exact "
                "natural Planner-owned limitation or question for the user."
            )

    # Both tiers must emit the multi-goal outcome envelope.  Deep Planner always
    # emits a complete map.  Fast Planner uses one flat decoder-compatible shape:
    # either an empty map for semantic escalation or a complete terminal map.
    if len(allowed_goals) > 1 and "goal_outcomes" not in required:
        required.append("goal_outcomes")

    goal_outcomes = properties.get("goal_outcomes")
    if isinstance(goal_outcomes, dict):
        if planner_tier == "fast" and len(allowed_goals) <= 1:
            # A single-goal fast plan already has one unambiguous semantic owner
            # for the top-level response/step fields. Hiding the redundant nested
            # map avoids an Ollama decoder failure mode where it emits a partial
            # $ref object that necessarily fails PlannerModelGoalOutcome.
            goal_outcomes.clear()
            goal_outcomes.update(
                {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                    "maxProperties": 0,
                }
            )
        else:
            outcome_properties = {
                goal_id: {
                    "$ref": "#/$defs/PlannerModelGoalOutcome",
                    "description": (
                        "Outcome for this exact canonical goal. Decide only this "
                        "goal's disposition, coverage, response, and owned step IDs."
                    ),
                }
                for goal_id in allowed_goals
            }
            goal_outcomes.clear()
            goal_outcomes.update(
                {
                    "type": "object",
                    "properties": outcome_properties,
                    "additionalProperties": False,
                    "maxProperties": len(allowed_goals),
                }
            )
            if allowed_goals and planner_tier == "deep":
                goal_outcomes.update(
                    {
                        "required": allowed_goals,
                        "minProperties": len(allowed_goals),
                    }
                )
            elif allowed_goals and planner_tier == "fast":
                goal_outcomes["minProperties"] = 0

    outcome_schema = schema.get("$defs", {}).get("PlannerModelGoalOutcome")
    if isinstance(outcome_schema, dict):
        # The runtime validator distinguishes an intentionally empty field from
        # one the decoder silently omitted.  Keep the decoder contract aligned
        # with that validator: every outcome must make its ownership and
        # terminal judgment explicit, even when a disposition requires an
        # empty string/list or a null satisfaction value.
        outcome_required = outcome_schema.setdefault("required", [])
        for field_name in (
            "disposition",
            "coverage",
            "response_text",
            "unresolved",
            "step_ids",
            "satisfaction",
            "rationale",
        ):
            if field_name not in outcome_required:
                outcome_required.append(field_name)
        outcome_disposition = outcome_schema.get("properties", {}).get("disposition")
        if isinstance(outcome_disposition, dict):
            if response_only:
                outcome_disposition["enum"] = (
                    ["respond"]
                    if planner_tier == "fast"
                    else ["respond", "clarify", "unavailable", "refused"]
                )
            elif planner_tier == "fast":
                outcome_disposition["enum"] = ["respond", "execute"]
            else:
                outcome_disposition["enum"] = [
                    "respond",
                    "execute",
                    "clarify",
                    "unavailable",
                    "refused",
                ]

        outcome_properties = outcome_schema.get("properties", {})
        base_branches: list[dict[str, Any]] = []
        allowed_outcomes = (
            (
                ["respond"]
                if planner_tier == "fast"
                else ["respond", "clarify", "unavailable", "refused"]
            )
            if response_only
            else (
                ["respond", "execute"]
                if planner_tier == "fast"
                else [
                    "respond",
                    "execute",
                    "clarify",
                    "unavailable",
                    "refused",
                ]
            )
        )
        for outcome_name in allowed_outcomes:
            branch: dict[str, Any] = {"properties": {"disposition": {"enum": [outcome_name]}}}
            branch_props = branch["properties"]
            if outcome_name == "execute":
                branch_props["coverage"] = {"enum": ["complete"]}
                branch_props["step_ids"] = {"minItems": 1}
            elif outcome_name == "respond":
                branch_props["coverage"] = {"enum": ["complete"]}
                branch_props["response_text"] = {"minLength": 1}
                branch_props["step_ids"] = {"maxItems": 0}
            elif outcome_name == "clarify":
                branch_props["coverage"] = {"enum": ["partial", "uncertain"]}
                branch_props["step_ids"] = {"maxItems": 0}
            else:
                branch_props["step_ids"] = {"maxItems": 0}
            base_branches.append(branch)
        if base_branches and planner_tier == "fast":
            outcome_schema["oneOf"] = base_branches

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
                capability_id = node_properties.get("capability_id")
                if isinstance(capability_id, dict) and allowed_capabilities:
                    capability_id["enum"] = allowed_capabilities
                for field_name in goal_list_fields:
                    field = node_properties.get(field_name)
                    if isinstance(field, dict) and allowed_goals:
                        field["items"] = {
                            "type": "string",
                            "enum": (
                                executable_source_goal_ids
                                if field_name == "source_goal_ids"
                                else allowed_goals
                            ),
                        }
                        field["uniqueItems"] = True
                        if field_name == "source_goal_ids":
                            field["minItems"] = 1
            for value in node.values():
                constrain(value)
        elif isinstance(node, list):
            for value in node:
                constrain(value)

    constrain(schema)
    _constrain_plan_relation_confirmation(schema)

    # Ollama's structured decoder does not reliably apply nested ``required``
    # constraints through a dynamic object property that contains only a $ref.
    # Inline each Deep Planner goal outcome and its satisfaction object so the
    # decoder sees every required semantic field at the exact goal key.
    if planner_tier == "deep":
        satisfaction_schema = schema.get("$defs", {}).get("PlannerGoalSatisfaction")
        if isinstance(satisfaction_schema, dict):
            satisfaction_required = satisfaction_schema.setdefault("required", [])
            for field_name in (
                "score",
                "status",
                "satisfied_goal_ids",
                "unmet_goal_ids",
                "unmet_requirements",
                "rationale",
            ):
                if field_name not in satisfaction_required:
                    satisfaction_required.append(field_name)
            top_satisfaction = properties.get("goal_satisfaction")
            if isinstance(top_satisfaction, dict):
                top_satisfaction.clear()
                top_satisfaction.update(copy.deepcopy(satisfaction_schema))
                top_satisfaction["description"] = (
                    "Required prospective adequacy judgment for the complete "
                    "Deep Planner result, including clarify/unavailable/refused."
                )

        if isinstance(goal_outcomes, dict) and isinstance(outcome_schema, dict):
            outcome_properties = goal_outcomes.get("properties", {})
            for goal_id in allowed_goals:
                goal_property = outcome_properties.get(goal_id)
                if not isinstance(goal_property, dict):
                    continue
                specialized = copy.deepcopy(outcome_schema)
                specialized_properties = specialized.get("properties", {})
                if isinstance(satisfaction_schema, dict):
                    specialized_satisfaction = copy.deepcopy(satisfaction_schema)
                    satisfaction_properties = specialized_satisfaction.get("properties", {})
                    for field_name in (
                        "satisfied_goal_ids",
                        "unmet_goal_ids",
                    ):
                        field = satisfaction_properties.get(field_name)
                        if isinstance(field, dict):
                            field["items"] = {
                                "type": "string",
                                "enum": [goal_id],
                            }
                            field["uniqueItems"] = True
                            field["maxItems"] = 1
                    specialized_properties["satisfaction"] = specialized_satisfaction
                if requires_execution and goal_id not in response_goal_set:
                    disposition_field = specialized_properties.get("disposition")
                    if isinstance(disposition_field, dict):
                        disposition_field["enum"] = [
                            "execute",
                            "clarify",
                            "unavailable",
                            "refused",
                        ]
                    response_text_field = specialized_properties.get("response_text")
                    if isinstance(response_text_field, dict):
                        response_text_field.pop("maxLength", None)
                        response_text_field["description"] = (
                            "Use an empty string for an executable outcome. A terminal "
                            "clarify, unavailable, or refused outcome must contain its "
                            "exact natural Planner-owned limitation or question."
                        )
                    specialized.setdefault("allOf", []).append(
                        {
                            "anyOf": [
                                {
                                    "properties": {
                                        "disposition": {"enum": ["execute"]},
                                        "response_text": {"maxLength": 0},
                                    },
                                    "required": ["disposition", "response_text"],
                                },
                                {
                                    "properties": {
                                        "disposition": {
                                            "enum": [
                                                "clarify",
                                                "unavailable",
                                                "refused",
                                            ]
                                        },
                                        "response_text": {"minLength": 1},
                                    },
                                    "required": ["disposition", "response_text"],
                                },
                            ]
                        }
                    )
                    branches = specialized.get("oneOf")
                    if isinstance(branches, list):
                        specialized["oneOf"] = [
                            branch
                            for branch in branches
                            if (
                                branch.get("properties", {}).get("disposition", {}).get("enum")
                                != ["respond"]
                            )
                        ]
                if goal_id in response_goal_set:
                    disposition_field = specialized_properties.get("disposition")
                    if isinstance(disposition_field, dict):
                        disposition_field["enum"] = ["respond"]
                    response_text_field = specialized_properties.get("response_text")
                    if isinstance(response_text_field, dict):
                        response_text_field.pop("maxLength", None)
                        response_text_field["minLength"] = 1
                        response_text_field["description"] = (
                            "Required direct response that completes this "
                            "Goal Association-authored spoken responsibility."
                        )
                    step_ids_field = specialized_properties.get("step_ids")
                    if isinstance(step_ids_field, dict):
                        step_ids_field["maxItems"] = 0
                    branches = specialized.get("oneOf")
                    if isinstance(branches, list):
                        specialized["oneOf"] = [
                            branch
                            for branch in branches
                            if (
                                branch.get("properties", {}).get("disposition", {}).get("enum")
                                == ["respond"]
                            )
                        ]
                if goal_id in single_step_goal_set:
                    step_ids_field = specialized_properties.get("step_ids")
                    if isinstance(step_ids_field, dict):
                        step_ids_field["maxItems"] = 1
                        step_ids_field["description"] = (
                            "This non-resource Goal represents one independently "
                            "observable effect and may own at most one executable "
                            "step. Optional or decorative effects require their own "
                            "authoritative Goal."
                        )
                if goal_id in provider_vocal_goal_set:
                    disposition_field = specialized_properties.get("disposition")
                    if isinstance(disposition_field, dict):
                        disposition_field["enum"] = (
                            [
                                "execute",
                                "clarify",
                                "unavailable",
                                "refused",
                            ]
                            if vocal_capability_available
                            else [
                                "clarify",
                                "unavailable",
                                "refused",
                            ]
                        )
                    response_text_field = specialized_properties.get("response_text")
                    if isinstance(response_text_field, dict):
                        response_text_field["maxLength"] = 800
                        if vocal_capability_available:
                            response_text_field.pop("minLength", None)
                            response_text_field["description"] = (
                                "Optional conversational delta; it never substitutes "
                                "for the provider-required vocal performance."
                            )
                        else:
                            response_text_field["minLength"] = 1
                            response_text_field["description"] = (
                                "Required natural limitation for this exact vocal Goal: "
                                "state that the requested performance cannot be performed "
                                "with the available capabilities. Never claim or promise "
                                "that it will happen."
                            )
                    step_ids_field = specialized_properties.get("step_ids")
                    if isinstance(step_ids_field, dict) and not vocal_capability_available:
                        step_ids_field["maxItems"] = 0
                    branches = specialized.get("oneOf")
                    if isinstance(branches, list):
                        specialized["oneOf"] = [
                            branch
                            for branch in branches
                            if (
                                branch.get("properties", {}).get("disposition", {}).get("enum")
                                != ["respond"]
                            )
                            and (
                                vocal_capability_available
                                or (
                                    branch.get("properties", {}).get("disposition", {}).get("enum")
                                    != ["execute"]
                                )
                            )
                        ]
                if goal_id in provider_media_goal_operations:
                    exact_media_capability = MEDIA_CAPABILITY_IDS[
                        provider_media_goal_operations[goal_id]
                    ]
                    media_capability_available = exact_media_capability in allowed_capabilities
                    disposition_field = specialized_properties.get("disposition")
                    if isinstance(disposition_field, dict):
                        disposition_field["enum"] = (
                            ["execute", "clarify", "unavailable", "refused"]
                            if media_capability_available
                            else ["clarify", "unavailable", "refused"]
                        )
                    response_text_field = specialized_properties.get("response_text")
                    if isinstance(response_text_field, dict):
                        response_text_field.pop("minLength", None)
                        response_text_field["maxLength"] = 800
                        response_text_field["description"] = (
                            "Optional conversational delta; it never substitutes for "
                            "the provider-required media operation."
                        )
                    step_ids_field = specialized_properties.get("step_ids")
                    if isinstance(step_ids_field, dict) and not media_capability_available:
                        step_ids_field["maxItems"] = 0
                    branches = specialized.get("oneOf")
                    if isinstance(branches, list):
                        specialized["oneOf"] = [
                            branch
                            for branch in branches
                            if (
                                branch.get("properties", {}).get("disposition", {}).get("enum")
                                != ["respond"]
                            )
                            and (
                                media_capability_available
                                or (
                                    branch.get("properties", {}).get("disposition", {}).get("enum")
                                    != ["execute"]
                                )
                            )
                        ]
                if goal_id in unavailable_information_goal_set:
                    disposition_field = specialized_properties.get("disposition")
                    if isinstance(disposition_field, dict):
                        disposition_field["enum"] = ["unavailable", "refused"]
                        disposition_field["description"] = (
                            "The typed information domain has no matching declared "
                            "provider in this turn's qualified catalog."
                        )
                    response_text_field = specialized_properties.get("response_text")
                    if isinstance(response_text_field, dict):
                        response_text_field.pop("maxLength", None)
                        response_text_field["minLength"] = 1
                        response_text_field["description"] = (
                            "Required natural, truthful limitation in the user's language; "
                            "do not ask for details that cannot create the missing provider."
                        )
                    step_ids_field = specialized_properties.get("step_ids")
                    if isinstance(step_ids_field, dict):
                        step_ids_field["maxItems"] = 0
                deep_outcome_disposition = specialized_properties.get("disposition")
                allowed_deep_outcomes = set(
                    deep_outcome_disposition.get("enum") or []
                    if isinstance(deep_outcome_disposition, dict)
                    else []
                )
                deep_outcome_branches = [
                    copy.deepcopy(branch)
                    for branch in base_branches
                    if set(
                        branch.get("properties", {})
                        .get("disposition", {})
                        .get("enum", [])
                    ).intersection(allowed_deep_outcomes)
                ]
                if deep_outcome_branches:
                    # Deep outcomes are inlined because the deployed decoder does
                    # not reliably apply nested requirements through a dynamic
                    # $ref.  Keep its semantic choice open, but expose the DTO
                    # invariant that execute owns at least one step ID and all
                    # non-executing outcomes own none.
                    specialized.setdefault("allOf", []).append(
                        {"anyOf": deep_outcome_branches}
                    )
                goal_property.clear()
                goal_property.update(specialized)
                goal_property["description"] = (
                    "Complete model-authored Deep Planner outcome for "
                    f"authoritative goal {goal_id!r}."
                )

    if planner_tier == "deep":
        max_deep_steps = max(4, len(allowed_goals) * 4)
        steps_schema = properties.get("steps")
        if isinstance(steps_schema, dict):
            steps_schema["maxItems"] = max_deep_steps
            steps_schema["description"] = (
                "A bounded compositional plan with at most four executable "
                "steps per authoritative Goal. Repeated motions belong in a "
                "capability count argument; never duplicate a step."
            )
        parameter_resolution_schema = properties.get("parameter_resolutions")
        if isinstance(parameter_resolution_schema, dict):
            parameter_resolution_schema["maxItems"] = max_deep_steps * 2
        unresolved_schema = properties.get("unresolved")
        if isinstance(unresolved_schema, dict):
            unresolved_schema["maxItems"] = max(4, len(allowed_goals) * 2)

        def bound_deep_text(
            owner: dict[str, Any], field_name: str, maximum: int
        ) -> None:
            field = owner.get(field_name)
            if isinstance(field, dict):
                current = field.get("maxLength")
                field["maxLength"] = (
                    min(int(current), maximum)
                    if isinstance(current, int)
                    else maximum
                )

        bound_deep_text(properties, "goal_summary", 240)
        bound_deep_text(properties, "response_text", 800)
        bound_deep_text(properties, "escalation_reason", 240)
        step_model = schema.get("$defs", {}).get("PlannerModelStep")
        if isinstance(step_model, dict):
            bound_deep_text(step_model.get("properties", {}), "reason_summary", 240)
        resolution_model = schema.get("$defs", {}).get("PlanParameterResolution")
        if isinstance(resolution_model, dict):
            bound_deep_text(resolution_model.get("properties", {}), "rationale", 240)
        satisfaction_model = schema.get("$defs", {}).get("PlannerGoalSatisfaction")
        if isinstance(satisfaction_model, dict):
            bound_deep_text(satisfaction_model.get("properties", {}), "rationale", 320)
        outcome_model = schema.get("$defs", {}).get("PlannerModelGoalOutcome")
        if isinstance(outcome_model, dict):
            bound_deep_text(outcome_model.get("properties", {}), "rationale", 320)

        def bound_deep_prose(node: Any) -> None:
            if isinstance(node, dict):
                node_properties = node.get("properties")
                if isinstance(node_properties, dict):
                    bound_deep_text(node_properties, "reason_summary", 240)
                    bound_deep_text(node_properties, "rationale", 320)
                for nested in node.values():
                    bound_deep_prose(nested)
            elif isinstance(node, list):
                for nested in node:
                    bound_deep_prose(nested)

        bound_deep_prose(schema)

    if response_only:
        steps_schema = properties.get("steps")
        if isinstance(steps_schema, dict):
            steps_schema["maxItems"] = 0
            steps_schema["description"] = (
                "The canonical Goals are provider-free direct speech responsibilities; "
                "return no executable plan steps."
            )

    step_schema = schema.get("$defs", {}).get("PlannerModelStep")
    if isinstance(step_schema, dict):
        step_required = step_schema.setdefault("required", [])
        for field_name in (
            "step_id",
            "capability_id",
            "args",
            "timing",
            "source_goal_ids",
            "reason_summary",
        ):
            if field_name not in step_required:
                step_required.append(field_name)
        _constrain_planner_step_args(
            step_schema,
            allowed_capabilities=allowed_capabilities,
            capability_input_schemas=capability_input_schemas,
        )
    if planner_tier == "deep" and requires_execution and not response_goal_set:
        schema.setdefault("allOf", []).append(
            {
                "anyOf": [
                    {
                        "properties": {
                            "disposition": {"enum": ["execute"]},
                            "response_text": {"maxLength": 0},
                            "steps": {"minItems": 1},
                        },
                        "required": ["disposition", "response_text", "steps"],
                    },
                    {
                        "properties": {
                            "disposition": {"enum": ["mixed"]},
                            "response_text": {"minLength": 1},
                            "steps": {"minItems": 1},
                        },
                        "required": ["disposition", "response_text", "steps"],
                    },
                    {
                        "properties": {
                            "disposition": {
                                "enum": ["clarify", "unavailable", "refused"]
                            },
                            "response_text": {"minLength": 1},
                            "steps": {"maxItems": 0},
                        },
                        "required": ["disposition", "response_text", "steps"],
                    },
                ]
            }
        )
    # ``required_numeric_goal_values`` remains accepted for API compatibility,
    # but duplicate provenance is projected after the model authors the exact
    # Capability argument and Goal ownership. Requiring the model to restate the
    # same value in this decoder schema created a second, failure-prone authority.
    del required_numeric_goal_values
    _constrain_terminal_unresolved(schema)
    return schema

def fast_multi_goal_response_schema(
    *,
    expected_goal_ids: list[str],
    allowed_capability_ids: list[str],
    capability_input_schemas: dict[str, dict[str, Any]] | None = None,
    response_only: bool = False,
    requires_execution: bool = False,
    response_goal_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Return a decoder-tight, model-authored multi-goal plan schema.

    The Fast Planner model authors the semantic plan itself: aggregate
    disposition and coverage, executable steps, exact step ownership,
    per-goal outcomes, response text, escalation judgments, and prospective
    satisfaction.  The host adds only envelope identity fields after validation.

    Every field needed by deterministic validation is required at the JSON
    decoder boundary.  Semantic escalation is represented by model-authored
    per-goal ``escalate`` outcomes rather than an empty host-interpreted map.
    This avoids phrase-to-action rules and avoids the previous gap where the
    decoder accepted an object that the planner contract necessarily rejected.
    """

    schema = copy.deepcopy(PlannerModelOutput.model_json_schema())
    schema["title"] = "FastPlannerMultiGoalPlanOutput"
    properties = schema.setdefault("properties", {})
    required = schema.setdefault("required", [])
    for field_name in (
        "disposition",
        "coverage",
        "confidence",
        "goal_summary",
        "response_text",
        "steps",
        "escalation_reason",
        "unresolved",
        "parameter_resolutions",
        "goal_outcomes",
        "goal_satisfaction",
        "plan_relation",
        "user_confirmation_required",
    ):
        if field_name not in required:
            required.append(field_name)

    disposition = properties.get("disposition")
    if isinstance(disposition, dict):
        disposition["enum"] = (
            ["respond", "clarify", "escalate"]
            if response_only
            else ["execute", "mixed", "clarify", "escalate"]
            if requires_execution and response_goal_ids
            else ["execute", "clarify", "escalate"]
            if requires_execution
            else ["respond", "execute", "mixed", "clarify", "escalate"]
        )

    allowed_goals = list(dict.fromkeys(expected_goal_ids))
    allowed_capabilities = list(dict.fromkeys(allowed_capability_ids))
    response_goal_set = set(response_goal_ids or []).intersection(allowed_goals)

    def bound_text(
        owner: dict[str, Any],
        field_name: str,
        maximum: int,
    ) -> None:
        field = owner.get(field_name)
        if isinstance(field, dict):
            field["maxLength"] = maximum

    # Repeated prose in several semantically redundant fields previously made
    # otherwise simple plans consume most of the decoder budget.  Keep the
    # semantic judgments model-authored while bounding their representation.
    bound_text(properties, "goal_summary", 240)
    bound_text(
        properties,
        "response_text",
        0 if requires_execution and not response_goal_set else 800,
    )
    if requires_execution:
        response_text_field = properties.get("response_text")
        if isinstance(response_text_field, dict):
            response_text_field["description"] = (
                "Planner speech is empty for execution-only work; a separate "
                "response owner handles communication. Mixed plans may carry only "
                "the direct-response Goal delta."
            )
    bound_text(properties, "escalation_reason", 240)
    top_unresolved = properties.get("unresolved")
    if isinstance(top_unresolved, dict):
        top_unresolved["maxItems"] = max(4, len(allowed_goals))
        if isinstance(top_unresolved.get("items"), dict):
            top_unresolved["items"]["maxLength"] = 240
    parameter_resolutions = properties.get("parameter_resolutions")
    if isinstance(parameter_resolutions, dict):
        parameter_resolutions["maxItems"] = max(4, len(allowed_goals) * 4)

    steps = properties.get("steps")
    if isinstance(steps, dict):
        # Fast multi-goal terminal scope is deliberately limited to simple
        # goals: at most one executable step per authoritative goal.  Besides
        # documenting that boundary, the decoder limit prevents a malformed
        # model response from repeating one physical step until num_predict is
        # exhausted.  A goal that needs multiple capabilities belongs in Deep
        # Planning through a model-authored semantic escalation.
        steps["maxItems"] = len(allowed_goals)
        steps["description"] = (
            "At most one executable step per authoritative goal. A skill's "
            "count argument represents repeated motions; never duplicate a "
            "step to implement count. Conversational respond goals have no step."
        )

    if response_only:
        response_only_steps = properties.get("steps")
        if isinstance(response_only_steps, dict):
            response_only_steps["maxItems"] = 0
            response_only_steps["description"] = (
                "The canonical Goals are provider-free direct speech responsibilities; "
                "return no executable plan steps."
            )

    goal_outcomes = properties.get("goal_outcomes")
    if isinstance(goal_outcomes, dict):
        goal_outcomes.clear()
        goal_outcomes.update(
            {
                "type": "object",
                "properties": {
                    goal_id: {
                        "$ref": "#/$defs/PlannerModelGoalOutcome",
                        "description": (
                            "The Fast Planner's complete semantic outcome for "
                            "this exact authoritative goal."
                        ),
                    }
                    for goal_id in allowed_goals
                },
                "required": allowed_goals,
                "additionalProperties": False,
                "minProperties": len(allowed_goals),
                "maxProperties": len(allowed_goals),
            }
        )

    # Fast multi-goal output always carries a model-authored satisfaction
    # judgment, including an unsatisfied/partial judgment when escalating.
    goal_satisfaction = properties.get("goal_satisfaction")
    if isinstance(goal_satisfaction, dict):
        goal_satisfaction.clear()
        goal_satisfaction.update({"$ref": "#/$defs/PlannerGoalSatisfaction"})

    outcome_schema = schema.get("$defs", {}).get("PlannerModelGoalOutcome")
    if isinstance(outcome_schema, dict):
        outcome_required = outcome_schema.setdefault("required", [])
        for field_name in (
            "disposition",
            "coverage",
            "response_text",
            "unresolved",
            "step_ids",
            "satisfaction",
            "rationale",
        ):
            if field_name not in outcome_required:
                outcome_required.append(field_name)
        outcome_properties = outcome_schema.get("properties", {})
        bound_text(
            outcome_properties,
            "response_text",
            0 if requires_execution and not response_goal_set else 800,
        )
        bound_text(outcome_properties, "rationale", 200)
        outcome_unresolved = outcome_properties.get("unresolved")
        if isinstance(outcome_unresolved, dict):
            outcome_unresolved["maxItems"] = 4
            if isinstance(outcome_unresolved.get("items"), dict):
                outcome_unresolved["items"]["maxLength"] = 240
        outcome_disposition = outcome_properties.get("disposition")
        if isinstance(outcome_disposition, dict):
            outcome_disposition["enum"] = (
                ["respond", "clarify", "escalate"]
                if response_only
                else ["execute", "clarify", "escalate"]
                if requires_execution
                else ["respond", "execute", "clarify", "escalate"]
            )
        if response_only:
            step_ids = outcome_properties.get("step_ids")
            if isinstance(step_ids, dict):
                step_ids["maxItems"] = 0
        satisfaction = outcome_properties.get("satisfaction")
        if isinstance(satisfaction, dict):
            satisfaction.clear()
            satisfaction.update({"$ref": "#/$defs/PlannerGoalSatisfaction"})

    satisfaction_schema = schema.get("$defs", {}).get("PlannerGoalSatisfaction")
    if isinstance(satisfaction_schema, dict):
        satisfaction_required = satisfaction_schema.setdefault("required", [])
        for field_name in (
            "score",
            "status",
            "satisfied_goal_ids",
            "unmet_goal_ids",
            "unmet_requirements",
            "rationale",
        ):
            if field_name not in satisfaction_required:
                satisfaction_required.append(field_name)
        satisfaction_properties = satisfaction_schema.get("properties", {})
        bound_text(satisfaction_properties, "rationale", 200)
        unmet_requirements = satisfaction_properties.get("unmet_requirements")
        if isinstance(unmet_requirements, dict):
            unmet_requirements["maxItems"] = 4
            if isinstance(unmet_requirements.get("items"), dict):
                unmet_requirements["items"]["maxLength"] = 240
            unmet_requirements["description"] = (
                "Actual planning gaps only. Pending execution, the text of a "
                "covered goal, and sibling goals are not unmet requirements. "
                "This must be empty when status is exact."
            )

    step_schema = schema.get("$defs", {}).get("PlannerModelStep")
    if isinstance(step_schema, dict):
        step_required = step_schema.setdefault("required", [])
        for field_name in (
            "step_id",
            "capability_id",
            "args",
            "timing",
            "source_goal_ids",
            "reason_summary",
        ):
            if field_name not in step_required:
                step_required.append(field_name)
        step_id = step_schema.get("properties", {}).get("step_id")
        if isinstance(step_id, dict):
            step_id["minLength"] = 1
        bound_text(step_schema.get("properties", {}), "reason_summary", 160)
    resolution_schema = schema.get("$defs", {}).get("PlanParameterResolution")
    if isinstance(resolution_schema, dict):
        resolution_required = resolution_schema.setdefault("required", [])
        for field_name in (
            "step_id",
            "parameter",
            "strategy",
            "value",
            "confidence",
            "blocking",
            "rationale",
            "source_goal_ids",
        ):
            if field_name not in resolution_required:
                resolution_required.append(field_name)
        resolution_properties = resolution_schema.get("properties", {})
        bound_text(resolution_properties, "rationale", 160)
        parameter = resolution_properties.get("parameter")
        if isinstance(parameter, dict):
            parameter["description"] = (
                "Copy exactly one argument key from the referenced step's args "
                "object, such as speed_mps or duration_s. Do not prefix it "
                "with a step ID or capability ID."
            )
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
                capability_id = node_properties.get("capability_id")
                if isinstance(capability_id, dict) and allowed_capabilities:
                    capability_id["enum"] = allowed_capabilities
                for field_name in goal_list_fields:
                    field = node_properties.get(field_name)
                    if isinstance(field, dict) and allowed_goals:
                        field["items"] = {
                            "type": "string",
                            "enum": allowed_goals,
                        }
                        field["uniqueItems"] = True
                        if field_name == "source_goal_ids":
                            field["minItems"] = 1
            for value in node.values():
                constrain(value)
        elif isinstance(node, list):
            for value in node:
                constrain(value)

    constrain(schema)
    if isinstance(step_schema, dict):
        _constrain_planner_step_args(
            step_schema,
            allowed_capabilities=allowed_capabilities,
            capability_input_schemas=capability_input_schemas,
        )

    def strict_satisfaction_schema(
        base: dict[str, Any],
        *,
        exact_satisfied_count: int,
    ) -> dict[str, Any]:
        """Align decoder branches with the satisfaction validator bands."""

        branches: list[dict[str, Any]] = []
        bands = (
            ("exact", 0.95, 1.0),
            ("substantial", 0.75, 0.949999),
            ("partial", 0.01, 0.749999),
            ("unsatisfied", 0.0, 0.0),
        )
        for status_value, minimum, maximum in bands:
            branch = copy.deepcopy(base)
            branch_properties = branch.setdefault("properties", {})
            status = branch_properties.setdefault("status", {})
            status.clear()
            status.update({"type": "string", "enum": [status_value]})
            score = branch_properties.setdefault("score", {})
            score["minimum"] = minimum
            score["maximum"] = maximum
            if status_value == "exact":
                for field_name in ("unmet_goal_ids", "unmet_requirements"):
                    field_schema = branch_properties.get(field_name)
                    if isinstance(field_schema, dict):
                        field_schema["maxItems"] = 0
                satisfied = branch_properties.get("satisfied_goal_ids")
                if isinstance(satisfied, dict):
                    satisfied["minItems"] = exact_satisfied_count
                    satisfied["maxItems"] = exact_satisfied_count
            branches.append(branch)
        return {
            "anyOf": branches,
            "description": (
                "Prospective plan adequacy. The selected status branch enforces "
                "its score band; exact satisfaction requires all planned goals "
                "in satisfied_goal_ids and both unmet lists empty."
            ),
        }

    if isinstance(goal_satisfaction, dict) and isinstance(satisfaction_schema, dict):
        goal_satisfaction.clear()
        goal_satisfaction.update(
            strict_satisfaction_schema(
                satisfaction_schema,
                exact_satisfied_count=len(allowed_goals),
            )
        )

    # A goal_outcomes key already identifies the one goal being judged.  The
    # generic model schema cannot express that a nested satisfaction object may
    # reference only its enclosing key, so specialize each decoder property.
    # This is contract/schema alignment, not semantic compilation: the model
    # still authors the disposition, step link, score, status, and rationale.
    # It simply cannot mislabel unrelated sibling goals as unmet inside a
    # goal-specific judgment and then fail the deterministic validator.
    if (
        isinstance(goal_outcomes, dict)
        and isinstance(outcome_schema, dict)
        and isinstance(satisfaction_schema, dict)
    ):
        outcome_properties = goal_outcomes.get("properties", {})
        for goal_id in allowed_goals:
            goal_property = outcome_properties.get(goal_id)
            if not isinstance(goal_property, dict):
                continue
            specialized_outcome = copy.deepcopy(outcome_schema)
            specialized_satisfaction = copy.deepcopy(satisfaction_schema)
            specialized_satisfaction_properties = specialized_satisfaction.get("properties", {})
            for field_name in ("satisfied_goal_ids", "unmet_goal_ids"):
                field_schema = specialized_satisfaction_properties.get(field_name)
                if isinstance(field_schema, dict):
                    field_schema["items"] = {"type": "string", "enum": [goal_id]}
                    field_schema["uniqueItems"] = True
                    field_schema["maxItems"] = 1
            satisfied = specialized_satisfaction_properties.get("satisfied_goal_ids")
            if isinstance(satisfied, dict):
                satisfied["description"] = (
                    f"Only {goal_id!r} may appear here. Include it when this "
                    "goal's proposed step or response would satisfy it."
                )
            unmet = specialized_satisfaction_properties.get("unmet_goal_ids")
            if isinstance(unmet, dict):
                unmet["description"] = (
                    f"Only {goal_id!r} may appear here, and only for an actual "
                    "planning gap. Pending execution and sibling goals do not "
                    "belong here; exact satisfaction requires an empty list."
                )
            specialized_outcome_properties = specialized_outcome.get("properties", {})
            if requires_execution and goal_id not in response_goal_set:
                disposition_field = specialized_outcome_properties.get("disposition")
                if isinstance(disposition_field, dict):
                    disposition_field["enum"] = ["execute", "clarify", "escalate"]
                response_text_field = specialized_outcome_properties.get("response_text")
                if isinstance(response_text_field, dict):
                    response_text_field["maxLength"] = 0
                    response_text_field["description"] = (
                        "Execution Goals do not author speech; communication is "
                        "owned by the response layer."
                    )
                branches = specialized_outcome.get("oneOf")
                if isinstance(branches, list):
                    specialized_outcome["oneOf"] = [
                        branch
                        for branch in branches
                        if (
                            branch.get("properties", {}).get("disposition", {}).get("enum")
                            != ["respond"]
                        )
                    ]
            if goal_id in response_goal_set:
                disposition_field = specialized_outcome_properties.get("disposition")
                if isinstance(disposition_field, dict):
                    disposition_field["enum"] = ["respond"]
                response_text_field = specialized_outcome_properties.get("response_text")
                if isinstance(response_text_field, dict):
                    response_text_field.pop("maxLength", None)
                    response_text_field["minLength"] = 1
                    response_text_field["description"] = (
                        "Required direct response that completes this Goal "
                        "Association-authored spoken responsibility."
                    )
                branches = specialized_outcome.get("oneOf")
                if isinstance(branches, list):
                    specialized_outcome["oneOf"] = [
                        branch
                        for branch in branches
                        if (
                            branch.get("properties", {}).get("disposition", {}).get("enum")
                            == ["respond"]
                        )
                    ]
            specialized_outcome_properties["satisfaction"] = strict_satisfaction_schema(
                specialized_satisfaction,
                exact_satisfied_count=1,
            )
            step_ids = specialized_outcome_properties.get("step_ids")
            if isinstance(step_ids, dict):
                step_ids["maxItems"] = 0 if goal_id in response_goal_set else 1
                step_ids["uniqueItems"] = True
                step_ids["description"] = (
                    "No executable step may be owned by this direct-response Goal."
                    if goal_id in response_goal_set
                    else "The one simple Fast Planner step owned by this goal, or an "
                    "empty list for respond/clarify/escalate."
                )
            goal_property.clear()
            goal_property.update(specialized_outcome)
            goal_property["description"] = (
                "The complete model-authored outcome for authoritative goal "
                f"{goal_id!r}. Satisfaction evaluates this goal only."
            )

    disposition = properties.get("disposition")
    if isinstance(disposition, dict):
        disposition["description"] = (
            "Aggregate the already-authored goal_outcomes: execute when all "
            "outcomes execute, respond when all respond, mixed when execute and "
            "respond are both present, clarify when all clarify, and escalate when all escalate."
        )

    # Encode the aggregate invariant in the decoder grammar.  The model still
    # chooses each goal's semantic disposition; this cross-field constraint
    # only makes the redundant top-level aggregate and executable-step count
    # consistent with those model-authored choices.  Enumerating the small
    # execute/respond assignment space avoids a host-side semantic compiler.
    # Larger turns are outside the Fast terminal surface and retain the normal
    # validator/Deep Planner path rather than exploding the response schema.
    if 1 < len(allowed_goals) <= 6:
        assignment_branches: list[dict[str, Any]] = []
        assignment_choices = [
            ("respond",)
            if goal_id in response_goal_set
            else (("execute",) if requires_execution else ("execute", "respond"))
            for goal_id in allowed_goals
        ]
        assignments = list(product(*assignment_choices))
        assignments.append(tuple("clarify" for _ in allowed_goals))
        assignments.append(tuple("escalate" for _ in allowed_goals))
        for assignment in assignments:
            assignment_set = set(assignment)
            if requires_execution and assignment_set == {"respond"}:
                continue
            if assignment_set == {"execute"}:
                aggregate = "execute"
            elif assignment_set == {"respond"}:
                aggregate = "respond"
            elif assignment_set == {"clarify"}:
                aggregate = "clarify"
            elif assignment_set == {"escalate"}:
                aggregate = "escalate"
            else:
                aggregate = "mixed"
            execute_count = sum(item == "execute" for item in assignment)
            branch: dict[str, Any] = {
                "properties": {
                    "disposition": {"type": "string", "enum": [aggregate]},
                    "steps": {
                        "type": "array",
                        "minItems": execute_count,
                        "maxItems": execute_count,
                    },
                    "goal_outcomes": {
                        "type": "object",
                        "properties": {
                            goal_id: {
                                "type": "object",
                                "properties": {
                                    "disposition": {
                                        "type": "string",
                                        "enum": [goal_disposition],
                                    }
                                },
                            }
                            for goal_id, goal_disposition in zip(
                                allowed_goals, assignment, strict=True
                            )
                        },
                    },
                }
            }
            assignment_branches.append(branch)
        schema.setdefault("allOf", []).append({"anyOf": assignment_branches})
    elif len(allowed_goals) == 1 and requires_execution:
        # The single-Goal fast schema has no nested outcome map from which to
        # derive its aggregate.  Encode the same mechanical invariant directly:
        # an executable result owns exactly one simple step, while clarification
        # or semantic escalation owns none and cannot claim exact satisfaction.
        schema.setdefault("allOf", []).append(
            {
                "anyOf": [
                    {
                        "properties": {
                            "disposition": {"enum": ["execute"]},
                            "steps": {"minItems": 1, "maxItems": 1},
                            "goal_satisfaction": {
                                "properties": {"status": {"enum": ["exact"]}}
                            },
                        },
                        "required": [
                            "disposition",
                            "steps",
                            "goal_satisfaction",
                        ],
                    },
                    {
                        "properties": {
                            "disposition": {"enum": ["clarify", "escalate"]},
                            "steps": {"maxItems": 0},
                            "goal_satisfaction": {
                                "properties": {
                                    "status": {
                                        "enum": [
                                            "substantial",
                                            "partial",
                                            "unsatisfied",
                                        ]
                                    }
                                }
                            },
                        },
                        "required": [
                            "disposition",
                            "steps",
                            "goal_satisfaction",
                        ],
                    },
                ]
            }
        )

    _constrain_plan_relation_confirmation(schema)

    # The structured decoder normally emits object fields in schema order.
    # Place per-goal outcomes before steps and aggregate disposition so the
    # model authors goal meaning first; the generic cross-field grammar can
    # then bound the number of simple executable steps and aggregate it.
    preferred_property_order = (
        "goal_summary",
        "goal_outcomes",
        "steps",
        "goal_satisfaction",
        "disposition",
        "coverage",
        "confidence",
        "response_text",
        "escalation_reason",
        "unresolved",
        "parameter_resolutions",
        "plan_relation",
        "user_confirmation_required",
    )
    schema["properties"] = {
        key: properties[key] for key in preferred_property_order if key in properties
    }
    _constrain_terminal_unresolved(schema)
    return schema

def _constrain_planner_step_args(
    step_schema: dict[str, Any],
    *,
    allowed_capabilities: list[str],
    capability_input_schemas: dict[str, dict[str, Any]] | None,
) -> None:
    """Bind each model-selected capability to its exact provider arg schema."""

    if not capability_input_schemas:
        return
    base_properties = step_schema.get("properties")
    if not isinstance(base_properties, dict):
        return
    required = [
        str(item) for item in step_schema.get("required", []) if str(item).strip()
    ]
    branches: list[dict[str, Any]] = []
    for capability_id in allowed_capabilities:
        input_schema = capability_input_schemas.get(capability_id)
        if not isinstance(input_schema, dict):
            continue
        properties = copy.deepcopy(base_properties)
        properties["capability_id"] = {
            "type": "string",
            "enum": [capability_id],
        }
        properties["args"] = copy.deepcopy(input_schema)
        branches.append(
            {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            }
        )
    if branches:
        step_schema["oneOf"] = branches

def _constrain_plan_relation_confirmation(schema: dict[str, Any]) -> None:
    """Align material plan changes with decoder-enforced confirmation."""

    schema.setdefault("allOf", []).append(
        {
            "anyOf": [
                {
                    "properties": {
                        "plan_relation": {
                            "type": "string",
                            "enum": ["exact"],
                        },
                        "user_confirmation_required": {
                            "type": "boolean",
                            "enum": [False],
                        },
                    }
                },
                {
                    "properties": {
                        "plan_relation": {
                            "type": "string",
                            "enum": ["safe_adjustment", "alternative"],
                        },
                        "user_confirmation_required": {
                            "type": "boolean",
                            "enum": [True],
                        },
                        "response_text": {
                            "type": "string",
                            "minLength": 1,
                        },
                    }
                },
            ]
        }
    )

def _constrain_terminal_unresolved(schema: dict[str, Any]) -> None:
    """Align decoder branches with terminal unresolved-work validators."""

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            properties = node.get("properties")
            if (
                isinstance(properties, dict)
                and isinstance(properties.get("disposition"), dict)
                and isinstance(properties.get("unresolved"), dict)
            ):
                node.setdefault("allOf", []).append(
                    {
                        "if": {
                            "properties": {
                                "disposition": {"enum": ["execute", "respond"]}
                            },
                            "required": ["disposition"],
                        },
                        "then": {
                            "properties": {"unresolved": {"maxItems": 0}},
                            "required": ["unresolved"],
                        },
                    }
                )
            for value in list(node.values()):
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(schema)


# Fast/Deep Planner pass-specific constrained-decoder schemas. These functions
# project an already-owned Planner contract; they do not invoke a model or choose HOW.

def fast_first_response_response_schema(
    responsibility_refs: list[str],
    *,
    responsibilities: list[CognitiveResponsibilityProposal] | None = None,
    language: str = "",
) -> dict[str, Any]:
    """Expose Fast Planner's 0..1 first-communication decision to decoding.

    The decoder may choose a complete response only when every supplied
    Responsibility is already conversational speech WHAT. Information,
    body/media/vocal, and other observable/stateful Responsibilities still need
    Planner work before they can be completed, so their pre-Evidence first-response
    schema exposes only prospective progress or silence. This keeps the decoder
    from treating a text-only progress acknowledgement as a complete response just
    because the compact DTO intentionally omits the mechanical ``role`` tag.
    """

    schema = copy.deepcopy(FastPlannerFirstResponseModelOutput.model_json_schema())
    definitions = schema.get("$defs", {})
    activity_schema = schema.get("properties", {}).get("activity")
    if isinstance(activity_schema, dict):
        # Keep the model-facing DTO semantic and tiny. Runtime restores the
        # discriminating role after decoding from the presence/absence of
        # progress_kind, so the LLM does not spend tokens on a mechanical tag.
        activity_schema.clear()
        supplied_responsibilities = list(responsibilities or [])
        direct_conversation = supplied_responsibilities and all(
            item.output_mode == "speech" for item in supplied_responsibilities
        )
        activity_choices: list[dict[str, Any]] = [
            {
                "$ref": (
                    "#/$defs/FastPlannerCompleteResponseAct"
                    if direct_conversation
                    else "#/$defs/FastPlannerProgressAct"
                )
            },
        ]
        activity_choices.append({"type": "null"})
        activity_schema.update(
            {
                "anyOf": activity_choices,
                "default": None,
            }
        )
    for contract_name in (
        "FastPlannerProgressAct",
        "FastPlannerCompleteResponseAct",
    ):
        contract = definitions.get(contract_name)
        if not isinstance(contract, dict):
            continue
        properties = contract.get("properties")
        if not isinstance(properties, dict):
            continue
        for field_name in (
            "evidence_refs",
            "timing",
            "speech_act",
            "truth_stage",
            "activity_id",
            "role",
        ):
            properties.pop(field_name, None)
        text_contract = properties.get("text")
        if isinstance(text_contract, dict):
            text_contract["maxLength"] = (
                32 if str(language).casefold().startswith("zh") else 72
            )
            if contract_name == "FastPlannerCompleteResponseAct":
                prior_utterances = {
                    str(item.bindings.get("prior_assistant_utterance") or "")
                    for item in (responsibilities or [])
                    if str(
                        item.bindings.get("prior_assistant_utterance") or ""
                    )
                }
                if len(prior_utterances) == 1:
                    # The user asked for an exact repeat of already accepted
                    # delivered speech. Projecting that immutable dialogue
                    # value is not Host-authored wording; it prevents the model
                    # from substituting the current question or adding a prefix.
                    prior_utterance = next(iter(prior_utterances))
                    text_contract["const"] = prior_utterance
                    text_contract["maxLength"] = max(
                        int(text_contract["maxLength"]),
                        len(prior_utterance),
                    )
            if contract_name == "FastPlannerProgressAct":
                semantic_contract = [
                    {
                        "relationship": item.relationship,
                        "outcome": item.outcome,
                        "target_goal_ids": list(item.target_goal_ids),
                    }
                    for item in (responsibilities or [])
                ]
                text_contract["pattern"] = r"^[^?？]*$"
                text_contract["description"] = (
                    "Exact short speech before any work or Evidence exists. "
                    "It may acknowledge and prospectively say what Chromie will "
                    "check/do, but must not name an instrument, source, sensor, "
                    "screen, or implementation method because no Capability has "
                    "been selected in this phase. It must not answer the request "
                    "or imply execution, a result, or completion already happened. "
                    "For relationship=continue, preserve continuation/resumption "
                    "of the concrete resolved outcome and never use an onset or "
                    "progressive predicate before Runtime commitment. Semantic "
                    "Responsibility context: "
                    + bounded_json(semantic_contract, 1200)
                )
        source_refs = properties.get("source_responsibility_refs")
        if isinstance(source_refs, dict):
            source_refs["items"] = {
                "type": "string",
                "enum": list(dict.fromkeys(responsibility_refs)),
            }
            source_refs["uniqueItems"] = True
            if len(set(responsibility_refs)) == 1:
                properties.pop("source_responsibility_refs", None)
        if contract_name == "FastPlannerProgressAct":
            progress_kind = properties.get("progress_kind")
            if isinstance(progress_kind, dict):
                progress_kind["description"] = (
                    "Select check_information for information acquisition, "
                    "perform_action for an embodied/media/vocal/state-changing "
                    "effect, or acknowledge_work for other prospective work."
                )
                enum_values = progress_kind.get("enum")
                if isinstance(enum_values, list):
                    progress_kind["enum"] = [
                        value for value in enum_values if value != "think"
                    ]
        if contract_name == "FastPlannerProgressAct":
            ordered: dict[str, Any] = {}
            for field_name in ("progress_kind", "text"):
                if field_name in properties:
                    ordered[field_name] = properties[field_name]
            for field_name, field_schema in properties.items():
                if field_name not in ordered:
                    ordered[field_name] = field_schema
            contract["properties"] = properties = ordered
        required = contract.get("required")
        if isinstance(required, list):
            required_names = set(required).intersection(properties)
            if len(set(responsibility_refs)) == 1:
                required_names.discard("source_responsibility_refs")
            contract["required"] = [
                name
                for name in (
                    "role",
                    "progress_kind",
                    "source_responsibility_refs",
                    "text",
                )
                if name in required_names
            ] + sorted(
                required_names
                - {
                    "role",
                    "progress_kind",
                    "source_responsibility_refs",
                    "text",
                }
            )
    return schema


def fast_advance_revision_response_schema(
    schema: dict[str, Any],
    initial_raw: Any,
    *,
    committed_communicative: bool,
    capabilities: list[dict[str, Any]],
    responsibilities: list[CognitiveResponsibilityProposal],
) -> dict[str, Any]:
    """Constrain one DTO revision to the model's initial disposition.

    A malformed Activity list must not make the permitted same-stage repair
    reconsider user meaning. In particular, an initial ``execute`` decision
    already commits the model to Capability work; when the first Communicative
    Activity was independently committed, the repaired list can contain only
    Capability Activities. The model still owns which available Capability and
    arguments satisfy the Responsibility.
    """

    if not isinstance(initial_raw, dict):
        return schema
    disposition_value = initial_raw.get("disposition")
    allowed_contracts_by_disposition = {
        "execute": ["FastPlannerCapabilityActivity"],
        "respond": ["FastPlannerCompleteResponseAct"],
        "clarify": ["FastPlannerClarificationAct"],
    }
    allowed_contracts = allowed_contracts_by_disposition.get(disposition_value)
    if allowed_contracts is None:
        return schema
    initial_activities = initial_raw.get("activities")
    initial_selected_progress = any(
        isinstance(item, dict) and item.get("role") == "progress"
        for item in (
            initial_activities if isinstance(initial_activities, list) else []
        )
    )
    if (
        disposition_value == "execute"
        and not committed_communicative
        and initial_selected_progress
    ):
        allowed_contracts.append("FastPlannerProgressAct")

    narrowed = copy.deepcopy(schema)
    properties = narrowed.get("properties", {})
    disposition = properties.get("disposition")
    if isinstance(disposition, dict):
        disposition["enum"] = [disposition_value]
        disposition["description"] = (
            "Mechanical DTO revision: preserve the initial model-authored "
            "disposition exactly."
        )
    activities = properties.get("activities")
    activity_items = activities.get("items") if isinstance(activities, dict) else None
    if not isinstance(activity_items, dict):
        return narrowed
    activity_items["oneOf"] = [
        {"$ref": f"#/$defs/{contract_name}"}
        for contract_name in allowed_contracts
    ]
    discriminator = activity_items.get("discriminator")
    if isinstance(discriminator, dict):
        mapping = discriminator.get("mapping")
        if isinstance(mapping, dict):
            discriminator["mapping"] = {
                role: ref
                for role, ref in mapping.items()
                if ref.rsplit("/", 1)[-1] in allowed_contracts
            }
    if isinstance(activities, dict):
        activities["minItems"] = 1
    if disposition_value == "execute":
        definitions = narrowed.get("$defs", {})
        capability_contract = definitions.get("FastPlannerCapabilityActivity")
        capability_properties = (
            capability_contract.get("properties")
            if isinstance(capability_contract, dict)
            else None
        )
        capability_required = (
            list(capability_contract.get("required", []))
            if isinstance(capability_contract, dict)
            else []
        )
        if "args" not in capability_required:
            capability_required.append("args")
        branches: list[dict[str, Any]] = []
        explicit_numbers = sorted(
            {
                number
                for responsibility in responsibilities
                for number in semantic_numeric_values(
                    responsibility.bindings
                )
            }
        )
        if isinstance(capability_properties, dict):
            for capability in capabilities:
                capability_id = str(capability.get("capability_id") or "")
                input_schema = capability.get("input_schema")
                if not capability_id or not isinstance(input_schema, dict):
                    continue
                branch_properties = copy.deepcopy(capability_properties)
                branch_properties["capability_id"] = {
                    "type": "string",
                    "enum": [capability_id],
                }
                explicit_input_schema = copy.deepcopy(input_schema)
                explicit_required = list(
                    explicit_input_schema.get("required", [])
                )
                input_properties = explicit_input_schema.get("properties")
                if isinstance(input_properties, dict):
                    numeric_parameter_names = [
                        parameter_name
                        for parameter_name, parameter_schema in input_properties.items()
                        if isinstance(parameter_schema, dict)
                        and parameter_schema.get("type") in {"integer", "number"}
                    ]
                    for parameter_name, parameter_schema in input_properties.items():
                        if (
                            isinstance(parameter_schema, dict)
                            and "default" in parameter_schema
                            and parameter_name not in explicit_required
                        ):
                            # A mechanical revision materializes schema defaults
                            # explicitly. This keeps the model-selected scope in
                            # the DTO instead of making downstream Runtime guess
                            # whether an omitted optional temporal/behavior field
                            # was intentional.
                            explicit_required.append(parameter_name)
                    if (
                        len(explicit_numbers) == 1
                        and len(numeric_parameter_names) == 1
                    ):
                        numeric_name = numeric_parameter_names[0]
                        numeric_schema = input_properties.get(numeric_name)
                        explicit_number = explicit_numbers[0]
                        if isinstance(numeric_schema, dict) and (
                            numeric_schema.get("type") == "number"
                            or explicit_number == explicit_number.to_integral_value()
                        ):
                            numeric_schema["enum"] = [
                                int(explicit_number)
                                if numeric_schema.get("type") == "integer"
                                else float(explicit_number)
                            ]
                if explicit_required:
                    explicit_input_schema["required"] = explicit_required
                branch_properties["args"] = explicit_input_schema
                branches.append(
                    {
                        "type": "object",
                        "properties": branch_properties,
                        "required": capability_required,
                        "additionalProperties": False,
                    }
                )
        if isinstance(capability_contract, dict) and branches:
            capability_contract["oneOf"] = branches
    return narrowed

def fast_advance_response_schema(
    responsibility_refs: list[str],
    *,
    responsibilities: list[CognitiveResponsibilityProposal] | None = None,
    capabilities: list[dict[str, Any]] | None = None,
    interpretation_unresolved: list[str] | None = None,
    committed_communicative: bool = False,
    suppress_new_communicative: bool = False,
    suppress_new_progress: bool = False,
) -> dict[str, Any]:
    """Constrain Fast Activities to authoritative WHAT and the live catalog.

    Work/evidence readiness is a Planner decision, not a GI field. The decoder
    therefore keeps response, execution, clarification, escalation, and silence-
    preserving branches available subject only to already-committed communication
    and concrete Capability contracts.
    """

    schema = copy.deepcopy(FastPlannerAdvanceModelOutput.model_json_schema())
    top_properties = schema.get("properties", {})
    activities_schema = top_properties.get("activities")
    if isinstance(activities_schema, dict):
        activities_schema["maxItems"] = max(
            1,
            len(responsibility_refs)
            if committed_communicative or suppress_new_communicative
            else len(responsibility_refs) * 2,
        )
    schema.setdefault("allOf", []).extend(
        [
            {
                "if": {
                    "properties": {"disposition": {"const": "escalate"}},
                    "required": ["disposition"],
                },
                "then": {
                    "properties": {
                        "continuations": {
                            "items": {"const": "deep_planner"},
                            "minItems": 1,
                            "maxItems": 1,
                        }
                    }
                },
                "else": {
                    "properties": {"continuations": {"maxItems": 0}}
                },
            },
            {
                "if": {
                    "properties": {
                        "disposition": {"enum": ["execute", "mixed"]}
                    },
                    "required": ["disposition"],
                },
                "then": {
                    "properties": {
                        "activities": {
                            "contains": {
                                "type": "object",
                                "properties": {"role": {"const": "capability"}},
                                "required": ["role"],
                            },
                            "minContains": 1,
                        }
                    }
                },
            },
        ]
    )
    reason_summary = top_properties.get("reason_summary")
    if isinstance(reason_summary, dict):
        reason_summary["maxLength"] = 100
    refs = list(dict.fromkeys(responsibility_refs))
    responsibility_items = list(responsibilities or [])
    ordinary_speech_refs = {
        item.local_ref
        for item in responsibility_items
        if item.output_mode == "speech"
    }
    capability_refs = [ref for ref in refs if ref not in ordinary_speech_refs]
    covered = schema.get("properties", {}).get(
        "covered_responsibility_refs"
    )
    if isinstance(covered, dict):
        covered["items"] = {"type": "string", "enum": refs}
        covered["minItems"] = len(refs)
        covered["maxItems"] = len(refs)
        covered["uniqueItems"] = True
    definitions = schema.get("$defs", {})
    information_gap_contract = definitions.get("PlannerInformationGap")
    if isinstance(information_gap_contract, dict):
        gap_properties = information_gap_contract.get("properties")
        if isinstance(gap_properties, dict):
            # PlannerInformationGap appears only inside a clarification Act in
            # this decoder contract.  Encode the Act invariant directly so the
            # model's one mechanical revision receives the deeper input-schema
            # error instead of failing first on a duplicate Pydantic invariant.
            gap_properties["preferred_resolution"] = {
                "const": "ask_user",
                "type": "string",
            }
            gap_properties["blocking"] = {
                "const": True,
                "default": True,
                "type": "boolean",
            }
            gap_properties["resolved"] = {
                "const": False,
                "default": False,
                "type": "boolean",
            }
            required_for = gap_properties.get("required_for")
            if isinstance(required_for, dict):
                required_for["minItems"] = 1
            if interpretation_unresolved == []:
                gap_properties["source_kind"] = {
                    "const": "execution_input",
                    "type": "string",
                }
                applicable_capability_ids = [
                    str(item.get("capability_id") or "").strip()
                    for item in (capabilities or [])
                    if isinstance(item, dict)
                    and str(item.get("capability_id") or "").strip()
                ]
                if applicable_capability_ids:
                    gap_properties["source_reference"] = {
                        "type": "string",
                        "enum": applicable_capability_ids,
                    }
    clarification_contract = definitions.get("FastPlannerClarificationAct")
    if isinstance(clarification_contract, dict):
        gaps = clarification_contract.get("properties", {}).get(
            "information_gaps"
        )
        if isinstance(gaps, dict):
            gaps["maxItems"] = 1
    if committed_communicative or suppress_new_communicative:
        # The first-response phase already made its one communication decision.
        # Full Fast planning may still discover a real clarification need, but it
        # must not manufacture substitute progress/completion speech merely because
        # execution planning is continuing.
        activities = top_properties.get("activities")
        activity_items = (
            activities.get("items") if isinstance(activities, dict) else None
        )
        allowed_activity_contracts = [
            "FastPlannerCapabilityActivity",
            "FastPlannerClarificationAct",
        ]
        if isinstance(activity_items, dict):
            activity_items["oneOf"] = [
                {"$ref": f"#/$defs/{contract_name}"}
                for contract_name in allowed_activity_contracts
            ]
            discriminator = activity_items.get("discriminator")
            if isinstance(discriminator, dict):
                mapping = discriminator.get("mapping")
                if isinstance(mapping, dict):
                    discriminator["mapping"] = {
                        role: ref
                        for role, ref in mapping.items()
                        if ref.rsplit("/", 1)[-1] in allowed_activity_contracts
                    }
    for contract_name in (
        "FastPlannerCompleteResponseAct",
        "FastPlannerClarificationAct",
        "FastPlannerProgressAct",
        "FastPlannerCapabilityActivity",
    ):
        contract = definitions.get(contract_name)
        if not isinstance(contract, dict):
            continue
        contract_properties = contract.get("properties", {})
        source_refs = contract_properties.get(
            "source_responsibility_refs"
        )
        if isinstance(source_refs, dict):
            allowed_refs = (
                capability_refs
                if contract_name == "FastPlannerCapabilityActivity"
                else (
                    [ref for ref in refs if ref in ordinary_speech_refs]
                    if (
                        contract_name == "FastPlannerCompleteResponseAct"
                        and responsibility_items
                    )
                    else refs
                )
            )
            source_refs["items"] = {"type": "string", "enum": allowed_refs}
            source_refs["uniqueItems"] = True
        role = contract_properties.get("role")
        if isinstance(role, dict):
            # Put the discriminating semantic choice before the branch payload.
            # Otherwise constrained decoding can commit to the first, easiest
            # union branch before it reaches ``role`` and coerce intended
            # Capability Activities into Communicative Acts.
            contract["properties"] = {
                "role": role,
                **{
                    name: value
                    for name, value in contract_properties.items()
                    if name != "role"
                },
            }
    activity_items = (
        activities_schema.get("items")
        if isinstance(activities_schema, dict)
        else None
    )
    if isinstance(activity_items, dict) and responsibility_items:
        allowed_activity_contracts = [
            "FastPlannerCapabilityActivity",
            "FastPlannerClarificationAct",
        ]
        if not (
            committed_communicative
            or suppress_new_communicative
            or suppress_new_progress
        ):
            allowed_activity_contracts.append("FastPlannerProgressAct")
        if ordinary_speech_refs and not (
            committed_communicative or suppress_new_communicative
        ):
            allowed_activity_contracts.insert(1, "FastPlannerCompleteResponseAct")
        activity_items["oneOf"] = [
            {"$ref": f"#/$defs/{contract_name}"}
            for contract_name in allowed_activity_contracts
        ]
        discriminator = activity_items.get("discriminator")
        if isinstance(discriminator, dict):
            mapping = discriminator.get("mapping")
            if isinstance(mapping, dict):
                discriminator["mapping"] = {
                    role_name: ref
                    for role_name, ref in mapping.items()
                    if ref.rsplit("/", 1)[-1] in allowed_activity_contracts
                }
    capability_contract = definitions.get("FastPlannerCapabilityActivity")
    progress_contract = definitions.get("FastPlannerProgressAct")
    if isinstance(progress_contract, dict):
        # These values are fixed by the selected progress_kind contract and
        # Pydantic validation. Omitting their duplicate decoder properties
        # keeps the low-latency response schema small without moving wording
        # or semantic-function ownership out of Fast Planner.
        progress_contract.pop("allOf", None)
        progress_properties = progress_contract.get("properties")
        if isinstance(progress_properties, dict):
            for field_name in (
                "evidence_refs",
                "speech_act",
                "timing",
                "truth_stage",
            ):
                progress_properties.pop(field_name, None)
    allowed_capabilities = [
        item
        for item in (capabilities or [])
        if isinstance(item, dict) and item.get("capability_id")
    ]
    if isinstance(capability_contract, dict) and allowed_capabilities:
        capability_id = capability_contract.get("properties", {}).get(
            "capability_id"
        )
        if isinstance(capability_id, dict):
            capability_id["enum"] = [
                str(item["capability_id"])
                for item in allowed_capabilities
            ]
        capability_contract.pop("allOf", None)
        capability_properties = capability_contract.get("properties")
        if isinstance(capability_properties, dict):
            capability_properties.pop("reason_summary", None)
            capability_required = list(capability_contract.get("required", []))
            if "args" not in capability_required:
                capability_required.append("args")
            capability_contract["required"] = capability_required
            branches: list[dict[str, Any]] = []
            for capability in allowed_capabilities:
                capability_id_value = str(capability.get("capability_id") or "")
                input_schema = capability.get("input_schema")
                if not capability_id_value or not isinstance(input_schema, dict):
                    continue
                branch_properties = copy.deepcopy(capability_properties)
                branch_properties["capability_id"] = {
                    "type": "string",
                    "enum": [capability_id_value],
                }
                branch_properties["args"] = copy.deepcopy(input_schema)
                branches.append(
                    {
                        "type": "object",
                        "properties": branch_properties,
                        "required": capability_required,
                        "additionalProperties": False,
                    }
                )
            if branches:
                capability_contract["oneOf"] = branches
    return schema

def fast_repair_response_schema(
    schema: dict[str, Any],
    initial_raw_output: Any,
    *,
    expected_goal_ids_for_turn: list[str],
) -> dict[str, Any]:
    """Narrow a redundant aggregate to the model's own goal judgments.

    The initial model output remains the semantic authority for every
    per-goal disposition.  When that complete outcome map is valid but its
    redundant top-level aggregate is inconsistent, the bounded repair
    grammar permits only the mechanically consistent aggregate.  The host
    never examines user wording or chooses a goal outcome, step, or skill.
    """

    if not isinstance(initial_raw_output, dict):
        return schema
    outcomes = initial_raw_output.get("goal_outcomes")
    expected = list(expected_goal_ids_for_turn)
    if not isinstance(outcomes, dict) or set(outcomes) != set(expected):
        return schema
    dispositions: list[str] = []
    for goal_id in expected:
        outcome = outcomes.get(goal_id)
        if not isinstance(outcome, dict):
            return schema
        disposition = outcome.get("disposition")
        if disposition not in {"execute", "respond", "clarify", "escalate"}:
            return schema
        dispositions.append(disposition)
    disposition_set = set(dispositions)
    if disposition_set == {"execute"}:
        aggregate = "execute"
    elif disposition_set == {"respond"}:
        aggregate = "respond"
    elif disposition_set == {"execute", "respond"}:
        aggregate = "mixed"
    elif disposition_set == {"clarify"}:
        aggregate = "clarify"
    elif disposition_set == {"escalate"}:
        aggregate = "escalate"
    else:
        return schema
    narrowed = copy.deepcopy(schema)
    disposition_schema = narrowed.get("properties", {}).get("disposition")
    if not isinstance(disposition_schema, dict):
        return schema
    disposition_schema["enum"] = [aggregate]
    disposition_schema["description"] = (
        "Bounded contract repair: this is the sole aggregate consistent "
        "with the initial model-authored per-goal dispositions."
    )
    narrowed_outcomes = narrowed.get("properties", {}).get("goal_outcomes")
    outcome_properties = (
        narrowed_outcomes.get("properties")
        if isinstance(narrowed_outcomes, dict)
        else None
    )
    if isinstance(outcome_properties, dict):
        for goal_id, initial_disposition in zip(expected, dispositions, strict=True):
            goal_schema = outcome_properties.get(goal_id)
            if not isinstance(goal_schema, dict):
                continue
            # Retain the shared outcome contract while freezing the
            # model-authored semantic disposition. A DTO repair may correct
            # redundant fields but cannot change escalate into execute. An
            # escalated outcome also has mechanically empty response/step
            # surfaces: otherwise the repair grammar permits the exact nested
            # contradiction that caused the original contract rejection.
            goal_properties = goal_schema.setdefault("properties", {})
            goal_properties["disposition"] = {
                "type": "string",
                "enum": [initial_disposition],
                "description": (
                    "Bounded DTO repair: preserve the initial model-authored "
                    "per-Goal semantic disposition exactly."
                ),
            }
            if initial_disposition == "escalate":
                goal_properties["response_text"] = {
                    "type": "string",
                    "maxLength": 0,
                }
                goal_properties["step_ids"] = {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 0,
                }
                goal_schema["required"] = list(
                    dict.fromkeys(
                        [
                            *(goal_schema.get("required") or []),
                            "disposition",
                            "response_text",
                            "step_ids",
                        ]
                    )
                )
    if aggregate == "escalate":
        properties = narrowed.get("properties", {})
        coverage = properties.get("coverage")
        if isinstance(coverage, dict):
            coverage["enum"] = ["partial"]
        steps = properties.get("steps")
        if isinstance(steps, dict):
            steps["maxItems"] = 0
        response_text = properties.get("response_text")
        if isinstance(response_text, dict):
            response_text["maxLength"] = 0
    return narrowed

def deep_plan_response_schema(
    expected_goal_ids: list[str],
    *,
    allowed_capability_ids: list[str] | None = None,
    capability_input_schemas: dict[str, dict[str, Any]] | None = None,
    response_only: bool = False,
    requires_execution: bool = False,
    response_goal_ids: list[str] | None = None,
    provider_vocal_goal_ids: list[str] | None = None,
    provider_media_goal_operations: dict[str, str] | None = None,
    unavailable_information_goal_ids: list[str] | None = None,
    single_step_goal_ids: list[str] | None = None,
    required_numeric_goal_values: dict[str, list[int | float]] | None = None,
) -> dict[str, Any]:
    return canonical_plan_response_schema(
        planner_tier="deep",
        expected_goal_ids=expected_goal_ids,
        allowed_capability_ids=list(allowed_capability_ids or []),
        capability_input_schemas=capability_input_schemas,
        response_only=response_only,
        requires_execution=requires_execution,
        response_goal_ids=response_goal_ids,
        provider_vocal_goal_ids=(provider_vocal_goal_ids),
        provider_media_goal_operations=(provider_media_goal_operations),
        unavailable_information_goal_ids=unavailable_information_goal_ids,
        single_step_goal_ids=single_step_goal_ids,
        required_numeric_goal_values=required_numeric_goal_values,
    )

def deep_safety_revision_response_schema(
    base_schema: dict[str, Any],
    *,
    feedback: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Forbid exact execution after deterministic concurrency rejection."""

    schema = copy.deepcopy(base_schema)
    response_text = schema.get("properties", {}).get("response_text")
    if isinstance(response_text, dict):
        response_text.pop("maxLength", None)
    if requires_sequential_safety_revision(list(feedback or [])):
        # The deployed structured decoder does not reliably enforce a
        # nested step constraint added only through a top-level allOf.
        # Specialize the referenced step DTO itself so a concurrency
        # rejection cannot be relabeled as a safe adjustment while the
        # rejected parallel timing remains unchanged.  This conservative
        # revision may still clarify or propose a confirmation-bound
        # sequential alternative; it cannot authorize overlap.
        step_schema = schema.get("$defs", {}).get("PlannerModelStep")
        if isinstance(step_schema, dict):
            timing = step_schema.get("properties", {}).get("timing")
            if isinstance(timing, dict):
                timing["enum"] = ["sequential"]
                timing["default"] = "sequential"
                timing["description"] = (
                    "Concurrency was rejected by deterministic provider/resource "
                    "validation; retained executable steps must be sequential."
                )
    schema.setdefault("allOf", []).append(
        {
            "anyOf": [
                {
                    "properties": {
                        "disposition": {
                            "type": "string",
                            "enum": ["execute", "mixed"],
                        },
                        "plan_relation": {
                            "type": "string",
                            "enum": ["safe_adjustment", "alternative"],
                        },
                        "user_confirmation_required": {
                            "type": "boolean",
                            "enum": [True],
                        },
                        "response_text": {
                            "type": "string",
                            "minLength": 1,
                        },
                    }
                },
                {
                    "properties": {
                        "disposition": {
                            "type": "string",
                            "enum": ["clarify", "unavailable", "refused"],
                        },
                        "steps": {
                            "type": "array",
                            "maxItems": 0,
                        },
                        "plan_relation": {
                            "type": "string",
                            "enum": ["exact"],
                        },
                        "user_confirmation_required": {
                            "type": "boolean",
                            "enum": [False],
                        },
                    }
                },
            ]
        }
    )
    return schema

def deep_contract_revision_response_schema(
    base_schema: dict[str, Any],
    *,
    feedback: list[dict[str, Any]] | None = None,
    semantic_baseline: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Tighten rejected pairs without allowing a mechanical repair to replan."""

    mismatches = [
        item
        for item in list(feedback or [])
        if isinstance(item, dict)
        and item.get("type") == "parameter_resolution_argument_mismatch"
        and str(item.get("capability_id") or "").strip()
        and str(item.get("parameter") or "").strip()
    ]
    missing_numeric = [
        item
        for item in list(feedback or [])
        if isinstance(item, dict)
        and item.get("type")
        == "missing_user_supplied_parameter_resolution"
        and str(item.get("step_id") or "").strip()
        and str(item.get("parameter") or "").strip()
        and list(item.get("source_goal_ids") or [])
    ]
    if not mismatches and not missing_numeric:
        return base_schema
    schema = copy.deepcopy(base_schema)
    branches = (
        schema.get("$defs", {})
        .get("PlannerModelStep", {})
        .get("oneOf", [])
    )
    if not isinstance(branches, list):
        return schema
    for mismatch in mismatches:
        capability_id = str(mismatch["capability_id"]).strip()
        parameter = str(mismatch["parameter"]).strip()
        for branch in branches:
            if not isinstance(branch, dict):
                continue
            properties = branch.get("properties")
            if not isinstance(properties, dict):
                continue
            capability_property = properties.get("capability_id")
            if not isinstance(capability_property, dict) or capability_property.get(
                "enum"
            ) != [capability_id]:
                continue
            args = properties.get("args")
            if not isinstance(args, dict) or parameter not in (
                args.get("properties") or {}
            ):
                continue
            required = args.setdefault("required", [])
            if parameter not in required:
                required.append(parameter)
    if missing_numeric:
        if isinstance(semantic_baseline, dict):
            properties = schema.get("properties")
            if isinstance(properties, dict):
                for field_name, field_value in semantic_baseline.items():
                    if field_name == "parameter_resolutions":
                        continue
                    properties[field_name] = {
                        "const": copy.deepcopy(field_value)
                    }
        resolution_array = schema.get("properties", {}).get(
            "parameter_resolutions"
        )
        resolution_model = schema.get("$defs", {}).get(
            "PlanParameterResolution"
        )
        if isinstance(resolution_array, dict) and isinstance(
            resolution_model, dict
        ):
            resolution_branches: list[dict[str, Any]] = []
            for obligation in missing_numeric:
                branch = copy.deepcopy(resolution_model)
                branch_properties = branch.setdefault("properties", {})
                branch_properties["step_id"] = {
                    "const": str(obligation["step_id"])
                }
                branch_properties["parameter"] = {
                    "const": str(obligation["parameter"])
                }
                branch_properties["strategy"] = {"const": "user_supplied"}
                branch_properties["value"] = {"const": obligation["value"]}
                branch_properties["blocking"] = {"const": False}
                branch_properties["source_goal_ids"] = {
                    "const": list(obligation["source_goal_ids"])
                }
                required = branch.setdefault("required", [])
                for field_name in (
                    "step_id",
                    "parameter",
                    "strategy",
                    "value",
                    "confidence",
                    "blocking",
                    "rationale",
                    "source_goal_ids",
                ):
                    if field_name not in required:
                        required.append(field_name)
                resolution_branches.append(branch)
            resolution_array["items"] = (
                resolution_branches[0]
                if len(resolution_branches) == 1
                else {"oneOf": resolution_branches}
            )
            resolution_array["minItems"] = len(resolution_branches)
    return schema
