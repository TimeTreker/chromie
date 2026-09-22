from __future__ import annotations

import copy
from datetime import datetime
from itertools import product
from typing import Any

try:
    from chromie_contracts.core_interpretation import CognitiveResponsibilityProposal, UserMeaningUncertainty
    from chromie_contracts.interaction import (
        MEDIA_CAPABILITY_IDS,
        VOCAL_MODES,
        VOCAL_PERFORMANCE_CAPABILITY_ID,
    )
    from chromie_contracts.plan import (
        FastPlannerAdvanceModelOutput,
        GOAL_SATISFACTION_SCORE_BANDS,
    )
except ImportError:  # pragma: no cover
    from shared.chromie_contracts.core_interpretation import CognitiveResponsibilityProposal, UserMeaningUncertainty
    from shared.chromie_contracts.interaction import (
        MEDIA_CAPABILITY_IDS,
        VOCAL_MODES,
        VOCAL_PERFORMANCE_CAPABILITY_ID,
    )
    from shared.chromie_contracts.plan import (
        FastPlannerAdvanceModelOutput,
        GOAL_SATISFACTION_SCORE_BANDS,
    )

from .prompt_projection import bounded_json
from .planner_validation import _capability_acquires_information
from .planner_grounding import (
    _argument_realization_contract,
    _argument_schema_accepts_canonical_binding,
    _count_argument_names,
    _goal_binding_map,
    _is_count_binding,
    _material_values_equal,
    _normalized_entity_type,
    literal_intent_argument,
    semantic_numeric_values,
)
from .planner_model_contract import (
    PlannerEvidenceReentryModelOutput,
    PlannerModelOutput,
    PlannerTier,
)


def work_change_response_schema(
    schema: dict[str, Any], *, context: dict[str, Any]
) -> dict[str, Any]:
    """Expose exact supplied cancellation identities in every native object branch."""

    result = copy.deepcopy(schema)
    identities = sorted({
        str(item["activity_id"])
        for item in context.get("existing_work_activities") or []
        if isinstance(item, dict) and item.get("activity_id")
    })
    cancellation = {
        "type": "array",
        "items": {"type": "string", **({"enum": identities} if identities else {})},
        "maxItems": len(identities),
        "uniqueItems": True,
        "description": "Explicitly cancel these supplied Activities. Omitted Work stays unchanged.",
    }

    def constrain(node: Any) -> None:
        if not isinstance(node, dict):
            return
        properties = node.get("properties")
        if isinstance(properties, dict) and "steps" in properties and node.get("type") == "object":
            properties["cancel_activity_ids"] = copy.deepcopy(cancellation)
            required = node.setdefault("required", [])
            if identities and "cancel_activity_ids" not in required:
                required.append("cancel_activity_ids")
        if isinstance(properties, dict) and "reuse_activity_id" in properties:
            properties["reuse_activity_id"] = {
                "type": "string", "enum": ["", *identities],
                "description": "Empty for new Work; otherwise an exact supplied Activity identity.",
            }
        for value in node.values():
            if isinstance(value, dict):
                constrain(value)
            elif isinstance(value, list):
                for item in value:
                    constrain(item)

    constrain(result)
    return result


def _canonical_binding_argument_value(argument_schema: dict[str, Any], value: Any) -> Any:
    """Return the exact JSON value required by one provider argument schema.

    Canonical Goal bindings preserve source surfaces such as ``"4"``.  Once a
    Capability owner declares that the corresponding argument is an integer or
    number, the decoder contract must expose the provider's JSON type rather
    than force the model to emit a string that Host code later has to repair.
    This conversion changes representation only; range and integrality have
    already been checked by ``_argument_schema_accepts_canonical_binding``.
    """

    value_type = argument_schema.get("type")
    if value_type not in {"integer", "number"}:
        return copy.deepcopy(value)
    numbers = semantic_numeric_values(value)
    if len(numbers) != 1:
        return copy.deepcopy(value)
    number = next(iter(numbers))
    if value_type == "integer":
        return int(number)
    return int(number) if number == number.to_integral_value() else float(number)


def _constrain_auxiliary_activity_schema(
    schema: dict[str, Any],
    candidates: list[dict[str, Any]] | None,
) -> None:
    """Bind optional decoration to the exact eligible live-catalog surface."""

    properties = schema.get("properties", {})
    activities = properties.get("auxiliary_activities")
    if not isinstance(activities, dict):
        return
    candidate_rows = [
        item
        for item in (candidates or [])
        if isinstance(item, dict)
        and str(item.get("capability_id") or "").strip()
        and isinstance(item.get("input_schema"), dict)
    ]
    activities["maxItems"] = min(3, len(candidate_rows)) if candidate_rows else 0
    activities["description"] = (
        "Optional non-Goal social decorations authored in this same primary Planner "
        "result. Empty is normal and preferred unless one candidate materially improves "
        "the anchored primary Activity."
    )
    definition = schema.get("$defs", {}).get("AuxiliaryPlanActivity")
    if not isinstance(definition, dict):
        return
    base_properties = definition.get("properties")
    if not isinstance(base_properties, dict):
        return
    # ``reason_summary`` has an empty Pydantic default. Keeping it in this
    # latency-critical projection taught small models to leak it into the
    # primary presentation Activity, where it is forbidden. Planner still owns
    # every material decoration field; trusted code restores only the default.
    base_properties.pop("reason_summary", None)
    required = [name for name in (definition.get("required") or []) if name != "reason_summary"]
    for field_name in (
        "auxiliary_activity_id",
        "anchor_kind",
        "anchor_id",
        "capability_id",
        "args",
        "execution_role",
        "timing",
        "social_function",
        "target",
    ):
        if field_name not in required:
            required.append(field_name)
    definition["required"] = required
    definition.setdefault("allOf", []).append(
        {
            "if": {
                "properties": {"anchor_kind": {"const": "plan_response"}},
                "required": ["anchor_kind"],
            },
            "then": {
                "properties": {"anchor_id": {"const": "response"}},
                "required": ["anchor_id"],
            },
        }
    )
    if not candidate_rows:
        return
    # The generic capability constraint is applied before this role-specific
    # one. Replace its primary-capability enum too, so an eligible auxiliary
    # capability does not also have to be a Goal step.
    base_properties["capability_id"] = {
        "type": "string",
        "enum": [str(item["capability_id"]) for item in candidate_rows],
    }
    branches: list[dict[str, Any]] = []
    for candidate in candidate_rows:
        branch_properties = copy.deepcopy(base_properties)
        branch_properties["capability_id"] = {
            "type": "string",
            "enum": [str(candidate["capability_id"])],
        }
        branch_properties["args"] = copy.deepcopy(candidate["input_schema"])
        branches.append(
            {
                "type": "object",
                "properties": branch_properties,
                "required": required,
                "additionalProperties": False,
            }
        )
    definition["oneOf"] = branches


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
        if isinstance(goal, dict) and isinstance(goal.get("resource_responsibility"), dict)
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

    parameter_resolutions = schema.get("properties", {}).get("parameter_resolutions")
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
    capabilities: list[dict[str, Any]] | None = None,
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
        name: values[0] for name, values in values_by_name.items() if len(values) == 1
    }
    schema = copy.deepcopy(base_schema)
    step_schema = schema.get("$defs", {}).get("PlannerModelStep")
    branches = step_schema.get("oneOf") if isinstance(step_schema, dict) else None
    if not isinstance(branches, list):
        return base_schema

    constrained = False
    capabilities_by_id = {
        str(item.get("capability_id") or ""): item for item in capabilities or []
    }
    retained_branches = []
    for branch in branches:
        properties = branch.get("properties") if isinstance(branch, dict) else None
        args = properties.get("args") if isinstance(properties, dict) else None
        argument_properties = args.get("properties") if isinstance(args, dict) else None
        if not isinstance(argument_properties, dict):
            retained_branches.append(branch)
            continue
        capability_ids = (properties.get("capability_id") or {}).get("enum") or []
        capability = capabilities_by_id.get(str(capability_ids[0])) if capability_ids else None
        capability = capability or {"input_schema": args}
        unsupported_goal_ids = {
            str(goal.get("goal_id") or "") for goal in authoritative_goals
            if not isinstance(goal.get("resource_responsibility"), dict)
            and not _capability_acquires_information(capability)
            and any(
                _is_count_binding(name, binding)
                and not _count_argument_names(capability, name)
                for name, binding in _goal_binding_map(goal).items()
            )
        }
        ownership = properties.get("source_goal_ids") or {}
        allowed = (ownership.get("items") or {}).get("enum")
        if isinstance(allowed, list) and unsupported_goal_ids.intersection(allowed):
            constrained = True
            allowed = [goal_id for goal_id in allowed if goal_id not in unsupported_goal_ids]
            if not allowed:
                continue
            ownership["items"]["enum"] = allowed
        retained_branches.append(branch)
        required = args.setdefault("required", [])
        for argument_name, argument_schema in list(argument_properties.items()):
            if not isinstance(argument_schema, dict):
                continue
            entity_type = _normalized_entity_type(argument_schema.pop("x-chromie-entity-type", ""))
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
                    "const": _canonical_binding_argument_value(argument_schema, values[0])
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
            argument_properties[name] = {
                "const": _canonical_binding_argument_value(argument_schema, value)
            }
            if isinstance(required, list) and name not in required:
                required.append(name)
            constrained = True
    if retained_branches:
        step_schema["oneOf"] = retained_branches
    elif constrained:
        # Keep a valid, nonempty definition for providers that compile all $defs;
        # no executable step is representable for this authoritative Goal set.
        schema["properties"]["steps"]["maxItems"] = 0
    time_conditions = schema.get("properties", {}).get("time_conditions")
    time_condition_definition = schema.get("$defs", {}).get("PlannerModelTimeCondition")
    ready_conditions: list[tuple[str, int]] = []
    for goal in authoritative_goals:
        if not isinstance(goal, dict):
            continue
        goal_id = str(goal.get("goal_id") or "").strip()
        binding = _goal_binding_map(goal).get("ready_at")
        value = binding.get("value") if isinstance(binding, dict) else None
        if not goal_id or not isinstance(value, str):
            continue
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            continue
        if parsed.tzinfo is None:
            continue
        ready_conditions.append((goal_id, int(parsed.timestamp() * 1000)))
    if (
        ready_conditions
        and isinstance(time_conditions, dict)
        and isinstance(time_condition_definition, dict)
    ):
        branches = []
        for goal_id, due_at_ms in ready_conditions:
            branch = copy.deepcopy(time_condition_definition)
            branch_properties = branch.setdefault("properties", {})
            branch_properties["goal_id"] = {"const": goal_id}
            branch_properties["due_at_ms"] = {"const": due_at_ms}
            branches.append(branch)
        time_conditions["items"] = {"oneOf": branches}
        time_conditions["maxItems"] = len(ready_conditions)
        constrained = True
    return schema if constrained else base_schema


def scoped_reporting_response_schema(
    schema: dict[str, Any], *, goal_ids: set[str], expected_goal_ids: list[str],
    future_goal_times: dict[str, int | None] | None = None,
) -> dict[str, Any]:
    """Bound control/waiting reports separately from effect fulfillment and Work."""
    if not goal_ids:
        return schema
    result = copy.deepcopy(schema)
    future_goal_times = future_goal_times or {}
    for variant in [result, *result.get("anyOf", [])]:
        properties = variant["properties"]
        if goal_ids == set(expected_goal_ids):
            for name in ("steps", "time_conditions", "cancel_activity_ids"):
                if name in properties:
                    properties[name]["maxItems"] = 0
            properties["user_confirmation_required"]["enum"] = [False]
        if future_goal_times:
            conditions = properties["time_conditions"]
            conditions.pop("maxItems", None)
            conditions["minItems"] = len(future_goal_times)
            conditions.setdefault("allOf", []).extend({"contains": {
                "type": "object", "properties": {"goal_id": {"const": goal_id},
                    "due_at_ms": {"const": due_ms} if due_ms is not None else {"type": "integer", "minimum": 1},
                    **({"source_quote": {"type": "string", "minLength": 1}} if due_ms is None else {})},
                    "required": ["goal_id", "due_at_ms", *(["source_quote"] if due_ms is None else [])],
            }} for goal_id, due_ms in future_goal_times.items())
            if goal_ids == set(expected_goal_ids):
                conditions["maxItems"] = len(future_goal_times)
                properties["disposition"]["enum"] = ["respond"]
        outcomes = properties["goal_outcomes"]["properties"]
        assessments = [(properties["goal_satisfaction"], goal_ids)]
        for goal_id in goal_ids:
            fields = outcomes[goal_id]["properties"]
            fields["step_ids"]["maxItems"] = 0
            if goal_id in future_goal_times:
                fields["disposition"]["enum"] = ["respond"]
            assessments.append((fields["satisfaction"], {goal_id}))
        for assessment, unmet_ids in assessments:
            bands = assessment.get("anyOf", [assessment])
            bands = [band for band in bands
                     if band.get("properties", {}).get("status", {}).get("enum") != ["exact"]]
            if "anyOf" in assessment:
                assessment["anyOf"] = bands
            for band in bands:
                fields = band["properties"]
                fields["score"]["exclusiveMaximum"] = 0.95
                fields["status"]["enum"] = [
                    value for value in fields["status"]["enum"] if value != "exact"
                ]
                fields["unmet_requirements"]["minItems"] = 1
                fields["unmet_goal_ids"].setdefault("allOf", []).extend(
                    {"contains": {"const": goal_id}} for goal_id in sorted(unmet_ids)
                )
                fields["satisfied_goal_ids"]["items"]["enum"] = [
                    goal_id for goal_id in expected_goal_ids if goal_id not in unmet_ids
                ]
                if not fields["satisfied_goal_ids"]["items"]["enum"]:
                    fields["satisfied_goal_ids"]["maxItems"] = 0
                    fields["satisfied_goal_ids"]["items"].pop("enum")
    return result



def fast_evidence_reentry_response_schema(
    *,
    expected_goal_ids: list[str],
    evidence_refs: list[str],
    allowed_capability_ids: list[str],
    capability_input_schemas: dict[str, dict[str, Any]] | None = None,
    allow_new_work: bool = True,
) -> dict[str, Any]:
    """Compact decoder contract for trusted Fast Planner Evidence re-entry.

    The model decides only post-execution next action and genuinely new Work. Host
    materializes the redundant Planner/CanonicalPlan envelope afterwards. Keeping this
    schema disjoint from ``goal_outcomes``/``steps`` prevents historical Plan/Runtime
    evidence from becoming an accidental answer template.
    """

    schema = copy.deepcopy(PlannerEvidenceReentryModelOutput.model_json_schema())
    schema["title"] = "FastPlannerEvidenceReentryOutput"
    properties = schema.setdefault("properties", {})
    required = schema.setdefault("required", [])
    for field_name in (
        "goal_decisions",
        "new_work",
        "confidence",
        "plan_relation",
        "user_confirmation_required",
        "escalation_reason",
    ):
        if field_name not in required:
            required.append(field_name)

    goals = list(dict.fromkeys(str(item).strip() for item in expected_goal_ids if str(item).strip()))
    evidence = list(dict.fromkeys(str(item).strip() for item in evidence_refs if str(item).strip()))
    decisions = properties.get("goal_decisions")
    if isinstance(decisions, dict):
        decisions["minItems"] = len(goals)
        decisions["maxItems"] = len(goals)
    decision_schema = schema.get("$defs", {}).get("PlannerEvidenceReentryGoalDecision")
    if isinstance(decision_schema, dict):
        decision_properties = decision_schema.get("properties", {})
        goal_id = decision_properties.get("goal_id")
        if isinstance(goal_id, dict):
            goal_id["enum"] = goals
        evidence_field = decision_properties.get("evidence_refs")
        if isinstance(evidence_field, dict):
            evidence_field["items"] = {"type": "string", "enum": evidence}
            evidence_field["maxItems"] = len(evidence)
            evidence_field["uniqueItems"] = True
        if not allow_new_work:
            next_action = decision_properties.get("next_action")
            if isinstance(next_action, dict):
                next_action["enum"] = [
                    "respond", "clarify", "unavailable", "refused", "escalate"
                ]

    new_work = properties.get("new_work")
    if isinstance(new_work, dict):
        new_work["maxItems"] = (max(1, len(goals)) * 4) if allow_new_work else 0
    step_schema = schema.get("$defs", {}).get("PlannerModelStep")
    allowed_capabilities = list(dict.fromkeys(allowed_capability_ids))
    if isinstance(step_schema, dict):
        step_properties = step_schema.get("properties", {})
        source_goals = step_properties.get("source_goal_ids")
        if isinstance(source_goals, dict):
            source_goals["items"] = {"type": "string", "enum": goals}
            source_goals["uniqueItems"] = True
            source_goals["maxItems"] = len(goals)
        capability_id = step_properties.get("capability_id")
        if isinstance(capability_id, dict):
            capability_id["enum"] = allowed_capabilities
        _constrain_planner_step_args(
            step_schema,
            allowed_capabilities=allowed_capabilities,
            capability_input_schemas=capability_input_schemas,
        )

    # Compile the existing DTO invariants into complete native alternatives.
    # Cross-field if/then alone is not a native-decoder guarantee. Keep the
    # same semantic fields and allow mixed multi-Goal decisions, including a
    # single unresolved Goal requesting depth alongside resolved siblings.
    definitions = schema["$defs"]
    decision_base = copy.deepcopy(definitions["PlannerEvidenceReentryGoalDecision"])
    allowed_actions = decision_base["properties"]["next_action"]["enum"]

    def decision_branches(actions: list[str]) -> dict[str, Any]:
        branches = []
        for status, (minimum, maximum) in GOAL_SATISFACTION_SCORE_BANDS.items():
            permitted = [
                action for action in actions
                if status != "exact" or action in {"respond", "execute"}
            ]
            if not permitted:
                continue
            branch = copy.deepcopy(decision_base)
            fields = branch["properties"]
            fields["next_action"]["enum"] = permitted
            fields["satisfaction_status"]["enum"] = [status]
            # Keep fractional bands in full Schema validation. The serving
            # decoder's float-range compiler loses valid interior values (for
            # example 0.5 in [0.01, 0.749999]); its native range stays [0, 1].
            fields["satisfaction_score"]["allOf"] = [
                {"minimum": minimum, "maximum": maximum}
            ]
            branches.append(branch)
        return {"anyOf": branches}

    definitions["PlannerEvidenceReentryGoalDecision"] = decision_branches(allowed_actions)
    definitions["NonEscalatingReentryDecision"] = decision_branches(
        [action for action in allowed_actions if action != "escalate"]
    )
    definitions["EscalatingReentryDecision"] = decision_branches(["escalate"])
    base = {key: copy.deepcopy(value) for key, value in schema.items() if key != "$defs"}
    normal = copy.deepcopy(base)
    normal["properties"]["goal_decisions"]["items"] = {
        "$ref": "#/$defs/NonEscalatingReentryDecision"
    }
    normal["properties"]["escalation_reason"] = {"type": "string", "const": ""}
    alternatives = [normal]
    for index in range(len(goals)):
        branch = copy.deepcopy(base)
        fields = branch["properties"]
        fields["new_work"]["maxItems"] = 0
        fields["escalation_reason"].update(minLength=1, pattern=r"\S")
        # Witness an actual escalation at any array position without changing
        # Goal order or forcing all sibling Goals to escalate.
        fields["goal_decisions"]["prefixItems"] = [
            {"$ref": "#/$defs/PlannerEvidenceReentryGoalDecision"}
            for _ in range(index)
        ] + [{"$ref": "#/$defs/EscalatingReentryDecision"}]
        alternatives.append(branch)
    schema["anyOf"] = alternatives

    return schema


def canonical_plan_response_schema(
    *,
    planner_tier: PlannerTier,
    expected_goal_ids: list[str],
    allowed_capability_ids: list[str],
    capability_input_schemas: dict[str, dict[str, Any]] | None = None,
    auxiliary_social_capabilities: list[dict[str, Any]] | None = None,
    response_only: bool = False,
    requires_execution: bool = False,
    response_goal_ids: list[str] | None = None,
    nonfulfilling_response_goal_ids: list[str] | None = None,
    provider_vocal_goal_ids: list[str] | None = None,
    provider_media_goal_operations: dict[str, str] | None = None,
    unavailable_information_goal_ids: list[str] | None = None,
    unavailable_resource_goal_ids: list[str] | None = None,
    single_step_goal_ids: list[str] | None = None,
    required_numeric_goal_values: dict[str, list[int | float]] | None = None,
    confirmation_required_capability_ids: list[str] | None = None,
    nonparallel_capability_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Return one flat, constrained model-output schema for a planner request.

    This schema deliberately excludes the host-owned CanonicalPlan envelope.
    The host supplies its plan identity, tier, schema version, and exact Goal
    Association IDs after validating this semantic DTO. Cross-field invariants
    remain enforced by ``PlannerModelOutput`` and ``CanonicalPlan``. A malformed
    or semantically rejected result fails closed; it is never regenerated by the
    same Planner depth. Fast Planner uses the same decoder-tight per-goal shape
    for one or many goals so the schema never instructs the model to omit fields
    that deterministic validation requires.
    """

    if planner_tier == "fast":
        schema = fast_multi_goal_response_schema(
            expected_goal_ids=expected_goal_ids,
            allowed_capability_ids=allowed_capability_ids,
            capability_input_schemas=capability_input_schemas,
            auxiliary_social_capabilities=auxiliary_social_capabilities,
            response_only=response_only,
            requires_execution=requires_execution,
            response_goal_ids=response_goal_ids,
            nonfulfilling_response_goal_ids=nonfulfilling_response_goal_ids,
            confirmation_required_capability_ids=(confirmation_required_capability_ids),
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
        "steps",
        "escalation_reason",
        "unresolved",
        "parameter_resolutions",
        "time_conditions",
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
                *(["mixed"] if len(set(expected_goal_ids)) > 1 else []),
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
    single_step_goal_set = set(single_step_goal_ids or []).intersection(allowed_goals)
    unavailable_information_goal_set = set(unavailable_information_goal_ids or []).intersection(
        allowed_goals
    )
    unavailable_resource_goal_set = set(unavailable_resource_goal_ids or []).intersection(
        allowed_goals
    )
    if (
        planner_tier == "deep"
        and (unavailable_information_goal_set | unavailable_resource_goal_set) == set(allowed_goals)
        and isinstance(disposition, dict)
    ):
        disposition["enum"] = ["unavailable", "refused"]
    provider_vocal_goal_set = set(provider_vocal_goal_ids or []).intersection(allowed_goals)
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
            | unavailable_resource_goal_set
        )
    ]
    known_unavailable_goal_set = (
        unavailable_provider_vocal_goal_set
        | unavailable_provider_media_goal_set
        | unavailable_information_goal_set
        | unavailable_resource_goal_set
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

    if isinstance(disposition, dict) and len(set(expected_goal_ids)) < 2:
        # Mixed is an aggregate of distinct per-Goal dispositions, never a
        # different way to label one Goal's clarification or executable result.
        disposition["enum"] = [value for value in disposition["enum"] if value != "mixed"]

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
                branch["required"] = ["precedes_step_ids", "follows_step_ids"]
                branch_props["step_ids"] = {"maxItems": 0}
            elif outcome_name == "clarify":
                branch_props["coverage"] = {"enum": ["partial", "uncertain"]}
                branch_props["step_ids"] = {"maxItems": 0}
            elif outcome_name == "escalate":
                branch_props["coverage"] = {"enum": ["partial", "uncertain"]}
                pass
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
    _constrain_auxiliary_activity_schema(schema, auxiliary_social_capabilities)
    _constrain_plan_relation_confirmation(schema)
    _constrain_capability_confirmation(
        schema,
        confirmation_required_capability_ids or [],
    )

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
                                        },
                                    "required": ["disposition", ],
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
                                        },
                                    "required": ["disposition", ],
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
                        disposition_field["enum"] = ["respond", "clarify", "unavailable", "refused"]
                    response_text_field = specialized_properties.get("response_text")
                    if isinstance(response_text_field, dict):
                        response_text_field.pop("maxLength", None)
                        response_text_field["minLength"] = 1
                        response_text_field["description"] = (
                            "Required direct response or truthful clarification, "
                            "unavailability, or refusal for this speech Goal."
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
                                in (["respond"], ["clarify"], ["unavailable"], ["refused"])
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
                if goal_id in (unavailable_information_goal_set | unavailable_resource_goal_set):
                    disposition_field = specialized_properties.get("disposition")
                    if isinstance(disposition_field, dict):
                        disposition_field["enum"] = ["unavailable", "refused"]
                        disposition_field["description"] = (
                            "The typed resource responsibility has no complete declared "
                            "provider or composable provider chain in this turn's catalog."
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
                        branch.get("properties", {}).get("disposition", {}).get("enum", [])
                    ).intersection(allowed_deep_outcomes)
                ]
                if deep_outcome_branches:
                    # Deep outcomes are inlined because the deployed decoder does
                    # not reliably apply nested requirements through a dynamic
                    # $ref.  Keep its semantic choice open, but expose the DTO
                    # invariant that execute owns at least one step ID and all
                    # non-executing outcomes own none.
                    specialized.setdefault("allOf", []).append({"anyOf": deep_outcome_branches})
                    # Native decoders may omit intersections. Complete object
                    # alternatives retain the same DTO invariant during decoding.
                    native_outcomes = []
                    for constraint in deep_outcome_branches:
                        variant = copy.deepcopy(specialized)
                        variant.pop("allOf", None)
                        variant.pop("oneOf", None)
                        for name, bounds in constraint["properties"].items():
                            variant["properties"][name].update(bounds)
                        variant["required"] = list(dict.fromkeys([*variant.get("required", []), *constraint.get("required", [])]))
                        native_outcomes.append(variant)
                    specialized["oneOf"] = native_outcomes
                limitation_condition = {
                    "properties": {"disposition": {"enum": ["clarify", "unavailable", "refused"]}},
                    "required": ["disposition"],
                }
                specialized.setdefault("allOf", []).append(
                    {
                        "if": limitation_condition,
                        "then": {
                            "properties": {
                                "satisfaction": {
                                    "properties": {
                                        "status": {"enum": ["substantial", "partial", "unsatisfied"]},
                                        "satisfied_goal_ids": {"maxItems": 0},
                                        "unmet_goal_ids": {"minItems": 1},
                                    }
                                }
                            }
                        },
                    }
                )
                schema.setdefault("allOf", []).append(
                    {
                        "if": {"properties": {"goal_outcomes": {"properties": {goal_id: limitation_condition}}}},
                        "then": {
                            "properties": {
                                "goal_satisfaction": {
                                    "properties": {
                                        "status": {"enum": ["substantial", "partial", "unsatisfied"]},
                                        "unmet_goal_ids": {"contains": {"const": goal_id}},
                                        "satisfied_goal_ids": {"not": {"contains": {"const": goal_id}}},
                                    }
                                }
                            }
                        },
                    }
                )
                # Put optional ordering obligations before required assessment;
                # a response after Work must not disappear at object closure.
                order = ("disposition", "coverage", "step_ids", "precedes_step_ids", "follows_step_ids")
                for variant in [specialized, *specialized.get("oneOf", [])]:
                    fields = variant["properties"]
                    variant["properties"] = {
                        **{key: fields[key] for key in order if key in fields},
                        **{key: value for key, value in fields.items() if key not in order},
                    }
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

        def bound_deep_text(owner: dict[str, Any], field_name: str, maximum: int) -> None:
            field = owner.get(field_name)
            if isinstance(field, dict):
                current = field.get("maxLength")
                field["maxLength"] = (
                    min(int(current), maximum) if isinstance(current, int) else maximum
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
            for branch in resolution_model.get("anyOf", []):
                branch_properties = branch.get("properties", {})
                bound_deep_text(branch_properties, "rationale", 240)
                # Unresolved strategies already require blocking. CanonicalPlan
                # also requires their exact Goal ownership; expose that in each
                # complete decoder branch, without Host filling missing IDs.
                if branch_properties.get("blocking", {}).get("const") is True:
                    branch_required = branch.setdefault("required", [])
                    if "source_goal_ids" not in branch_required:
                        branch_required.append("source_goal_ids")
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
            nonparallel_capability_ids=nonparallel_capability_ids,
        )
    if planner_tier == "deep" and requires_execution and not response_goal_set:
        schema.setdefault("allOf", []).append(
            {
                "anyOf": [
                    {
                        "properties": {
                            "disposition": {"enum": ["execute"]},
                            "steps": {"minItems": 1},
                        },
                        "required": ["disposition", "steps"],
                    },
                    {
                        "properties": {
                            "disposition": {"enum": ["mixed"]},
                            "steps": {"minItems": 1},
                        },
                        "required": ["disposition", "steps"],
                    },
                    {
                        "properties": {
                            "disposition": {"enum": ["clarify", "unavailable", "refused"]},
                            "steps": {"maxItems": 0},
                        },
                        "required": ["disposition", "steps"],
                    },
                ]
            }
        )
    # ``required_numeric_goal_values`` remains accepted for API compatibility,
    # but duplicate provenance is projected after the model authors the exact
    # Capability argument and Goal ownership. Requiring the model to restate the
    # same value in this decoder schema created a second, failure-prone authority.
    del required_numeric_goal_values
    if planner_tier == "deep" and response_only:
        # Match the existing Host aggregate without enumerating 4**N outcome
        # assignments. A mixed speech result needs two distinct witnesses:
        # an independently completed response and an unresolved limitation.
        speech_dispositions = ["respond", "clarify", "unavailable", "refused"]
        aggregate_branches: list[dict[str, Any]] = []
        for aggregate in speech_dispositions:
            aggregate_branches.append(
                {
                    "properties": {
                        "disposition": {"enum": [aggregate]},
                        "goal_outcomes": {
                            "properties": {
                                goal_id: {"properties": {"disposition": {"enum": [aggregate]}}}
                                for goal_id in allowed_goals
                            }
                        },
                    }
                }
            )
        if len(allowed_goals) > 1:
            aggregate_branches.append(
                {
                    "properties": {
                        "disposition": {"enum": ["mixed"]},
                        "coverage": {"enum": ["complete"]},
                        "goal_outcomes": {
                            "anyOf": [
                                {
                                    "properties": {
                                        response_id: {"properties": {"disposition": {"enum": ["respond"]}}},
                                        limitation_id: {"properties": {"disposition": {"enum": speech_dispositions[1:]}}},
                                    }
                                }
                                for response_id in allowed_goals
                                for limitation_id in allowed_goals
                                if response_id != limitation_id
                            ]
                        },
                    }
                }
            )
        schema.setdefault("allOf", []).append({"anyOf": aggregate_branches})
        properties["user_confirmation_required"] = {"type": "boolean", "const": False}
        properties["plan_relation"] = {"type": "string", "enum": ["exact"]}
        properties["time_conditions"]["maxItems"] = 0
        # The deployed llama.cpp converter reads properties before allOf.
        # Supply complete union branches so native decoding sees the same
        # aggregate restriction. Keep the original schema as an independent
        # intersection for full JSON Schema validation and other consumers.
        base = copy.deepcopy(schema)
        base.pop("$defs", None)
        native_branches: list[dict[str, Any]] = []
        for aggregate_branch in aggregate_branches:
            variant = copy.deepcopy(base)
            variant_properties = variant["properties"]
            aggregate_properties = aggregate_branch["properties"]
            variant_properties["disposition"] = aggregate_properties["disposition"]
            if "coverage" in aggregate_properties:
                variant_properties["coverage"] = aggregate_properties["coverage"]
            outcome_constraint = aggregate_properties["goal_outcomes"]
            outcome_branches = []
            for witness in outcome_constraint.get("anyOf", [outcome_constraint]):
                outcomes = copy.deepcopy(properties["goal_outcomes"])
                for goal_id, constraint in witness["properties"].items():
                    outcomes["properties"][goal_id]["properties"]["disposition"] = (
                        constraint["properties"]["disposition"]
                    )
                    if "respond" not in constraint["properties"]["disposition"]["enum"]:
                        satisfaction_fields = outcomes["properties"][goal_id]["properties"]["satisfaction"]["properties"]
                        satisfaction_fields["status"] = {"type": "string", "enum": ["substantial", "partial", "unsatisfied"]}
                        satisfaction_fields["satisfied_goal_ids"]["maxItems"] = 0
                        satisfaction_fields["unmet_goal_ids"]["minItems"] = 1
                outcome_branches.append(outcomes)
            variant_properties["goal_outcomes"] = (
                outcome_branches[0]
                if len(outcome_branches) == 1
                else {"anyOf": outcome_branches}
            )
            if aggregate_properties["disposition"]["enum"] != ["respond"]:
                aggregate_satisfaction = variant_properties["goal_satisfaction"]["properties"]
                aggregate_satisfaction["status"] = {"type": "string", "enum": ["substantial", "partial", "unsatisfied"]}
                aggregate_satisfaction["unmet_goal_ids"]["minItems"] = 1
            # Author the individual results before committing their redundant
            # aggregate. Native object decoding follows this property order.
            variant["properties"] = {
                "goal_outcomes": variant_properties["goal_outcomes"],
                **{key: value for key, value in variant_properties.items() if key != "goal_outcomes"},
            }
            native_branches.append(variant)
        schema["anyOf"] = native_branches
    # Every step must belong to an outcome and IDs must be unique. Project
    # those existing per-Goal bounds into the aggregate array as well.
    if allowed_goals and isinstance(goal_outcomes, dict):
        capacity = sum(
            goal_outcomes["properties"][goal_id]["properties"]["step_ids"].get("maxItems", 4)
            for goal_id in allowed_goals
        )
        properties["steps"]["maxItems"] = min(properties["steps"].get("maxItems", capacity), capacity)
    _constrain_terminal_unresolved(schema)
    preferred = ("goal_summary", "goal_outcomes", "steps", "goal_satisfaction")
    schema["properties"] = {
        **{key: properties[key] for key in preferred if key in properties},
        **{key: value for key, value in properties.items() if key not in preferred},
    }
    return schema


def fast_multi_goal_response_schema(
    *,
    expected_goal_ids: list[str],
    allowed_capability_ids: list[str],
    capability_input_schemas: dict[str, dict[str, Any]] | None = None,
    auxiliary_social_capabilities: list[dict[str, Any]] | None = None,
    response_only: bool = False,
    requires_execution: bool = False,
    response_goal_ids: list[str] | None = None,
    nonfulfilling_response_goal_ids: list[str] | None = None,
    effectful_goal_ids: list[str] | None = None,
    confirmation_required_capability_ids: list[str] | None = None,
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
        "steps",
        "escalation_reason",
        "unresolved",
        "parameter_resolutions",
        "time_conditions",
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
            (["respond", "mixed", "clarify", "escalate"] if len(expected_goal_ids) > 1 else ["respond", "clarify", "escalate"])
            if response_only
            else ["execute", "mixed", "clarify", "escalate"]
            if requires_execution and response_goal_ids
            else ["execute", "clarify", "escalate"]
            if requires_execution
            else ["respond", "execute", "mixed", "clarify", "escalate"]
        )

    if isinstance(disposition, dict) and len(set(expected_goal_ids)) < 2:
        disposition["enum"] = [value for value in disposition["enum"] if value != "mixed"]

    allowed_goals = list(dict.fromkeys(expected_goal_ids))
    allowed_capabilities = list(dict.fromkeys(allowed_capability_ids))
    response_goal_set = set(response_goal_ids or []).intersection(allowed_goals)
    cancellation_goal_set = set(nonfulfilling_response_goal_ids or []).intersection(allowed_goals)
    effectful_goal_set = set(effectful_goal_ids or []).intersection(allowed_goals)

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
        800,
    )
    if requires_execution:
        response_text_field = properties.get("response_text")
        if isinstance(response_text_field, dict):
            response_text_field["description"] = (
                "Planner speech is empty for exact execution-only work without "
                "confirmation. When user_confirmation_required=true, author the "
                "exact confirmation question here, including for an exact Plan. A "
                "safe-adjusted or alternative Plan must explain its material "
                "change here, and a mixed Plan may carry the direct-response "
                "Goal delta."
            )
        if not response_goal_set:
            schema.setdefault("allOf", []).append(
                {
                    "if": {
                        "properties": {
                            "plan_relation": {"const": "exact"},
                            "user_confirmation_required": {"const": False},
                        },
                        "required": ["plan_relation", "user_confirmation_required"],
                    },
                    "then": {
                        "properties": {},
                        "required": [],
                    },
                }
            )
    schema.setdefault("allOf", []).append(
        {
            "if": {
                "properties": {"user_confirmation_required": {"const": True}},
                "required": ["user_confirmation_required"],
            },
            "then": {
                "properties": {},
                "required": [],
            },
        }
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
        # One complete intent may require several Activities. Bound composition
        # independently of UMI segmentation; repetitions still use count arguments.
        steps["maxItems"] = len(allowed_goals) * 4
        steps["description"] = (
            "At most four executable steps per authoritative goal. A skill's "
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
        for branch in resolution_schema.get("anyOf", []):
            branch["required"] = list(resolution_required)
            for name, contract in resolution_properties.items():
                if name not in {"strategy", "blocking", "value"}:
                    branch["properties"][name] = copy.deepcopy(contract)
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
        for status_value, (minimum, maximum) in GOAL_SATISFACTION_SCORE_BANDS.items():
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
                    disposition_field["enum"] = [
                        "respond",
                        "clarify",
                        "escalate",
                    ]
                response_text_field = specialized_outcome_properties.get("response_text")
                if isinstance(response_text_field, dict):
                    response_text_field.pop("maxLength", None)
                    response_text_field.pop("minLength", None)
                    response_text_field["description"] = (
                        "Author the exact direct response for disposition=respond, "
                        "or an empty string when the whole Fast plan escalates."
                    )
                branches = specialized_outcome.get("oneOf")
                if isinstance(branches, list):
                    specialized_outcome["oneOf"] = [
                        branch
                        for branch in branches
                        if (
                            branch.get("properties", {}).get("disposition", {}).get("enum")
                            in (["respond"], ["clarify"], ["escalate"])
                        )
                    ]
            specialized_outcome_properties["satisfaction"] = strict_satisfaction_schema(
                specialized_satisfaction,
                exact_satisfied_count=1,
            )
            specialized_outcome.setdefault("allOf", []).append(
                {
                    "if": {
                        "properties": {
                            "disposition": {"enum": ["escalate"]},
                        },
                        "required": ["disposition"],
                    },
                    "then": {
                        "properties": {
                            "step_ids": {"maxItems": 0},
                        },
                        "required": ["step_ids"],
                    },
                }
            )
            step_ids = specialized_outcome_properties.get("step_ids")
            if isinstance(step_ids, dict):
                step_ids["maxItems"] = 0 if goal_id in response_goal_set else 4
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
            "respond are both present or independent respond and clarify outcomes coexist, "
            "clarify when all clarify, and escalate when all escalate."
        )

    # Encode the aggregate invariant in the decoder grammar.  The model still
    # chooses each goal's semantic disposition; this cross-field constraint
    # only makes the redundant top-level aggregate and executable-step count
    # consistent with those model-authored choices.  Enumerating the small
    # execute/respond assignment space avoids a host-side semantic compiler.
    # Larger turns are outside the Fast terminal surface and retain the normal
    # validator/Deep Planner path rather than exploding the response schema.
    assignment_branches: list[dict[str, Any]] = []
    if 1 <= len(allowed_goals) <= 6:
        assignment_choices = [
            ("respond", "clarify")
            if goal_id in response_goal_set
            else ("execute",)
            if goal_id in effectful_goal_set
            else (("execute",) if requires_execution else ("execute", "respond"))
            for goal_id in allowed_goals
        ]
        assignments = list(product(*assignment_choices))
        assignments.append(tuple("clarify" for _ in allowed_goals))
        assignments.append(tuple("escalate" for _ in allowed_goals))
        for assignment in dict.fromkeys(assignments):
            assignment_set = set(assignment)
            if "clarify" in assignment_set and "execute" in assignment_set:
                continue
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
            terminal_assignment = assignment_set.issubset({"execute", "respond"})
            nonexact_statuses = ["substantial", "partial", "unsatisfied"]
            outcome_properties: dict[str, Any] = {}
            for goal_id, goal_disposition in zip(allowed_goals, assignment, strict=True):
                terminal_outcome = goal_disposition in {"execute", "respond"}
                outcome_properties[goal_id] = {
                    "type": "object",
                    "properties": {
                        "disposition": {
                            "type": "string",
                            "enum": [goal_disposition],
                        },
                        "coverage": {
                            "type": "string",
                            "enum": (
                                ["complete"] if terminal_outcome else ["partial", "uncertain"]
                            ),
                        },
                        "step_ids": (
                            {"type": "array", "minItems": 1, "maxItems": 4}
                            if goal_disposition == "execute"
                            else {"type": "array", "maxItems": 0}
                        ),
                        "satisfaction": {
                            "type": "object",
                            "properties": {
                                "status": {
                                    "type": "string",
                                    "enum": (
                                        nonexact_statuses
                                        if goal_id in cancellation_goal_set and goal_disposition == "respond"
                                        else ["exact", "substantial", "partial"]
                                        if goal_disposition == "execute"
                                        else ["exact", "substantial"]
                                        if terminal_outcome
                                        else nonexact_statuses
                                    ),
                                }
                            },
                            "required": ["status"],
                        },
                    },
                    "required": [
                        "disposition",
                        "coverage",
                        "step_ids",
                        "satisfaction",
                    ],
                }
            branch: dict[str, Any] = {
                "properties": {
                    "disposition": {"type": "string", "enum": [aggregate]},
                    "coverage": {
                        "type": "string",
                        "enum": (["complete"] if terminal_assignment or aggregate == "mixed" else ["partial", "uncertain"]),
                    },
                    "steps": {
                        "type": "array",
                        "minItems": execute_count,
                        "maxItems": execute_count * 4,
                    },
                    "goal_satisfaction": {
                        "type": "object",
                        "properties": {
                            "status": {
                                "type": "string",
                                "enum": (
                                    nonexact_statuses
                                    if cancellation_goal_set
                                    else ["exact", "substantial", "partial"]
                                    if terminal_assignment and execute_count
                                    else ["exact", "substantial"]
                                    if terminal_assignment
                                    else nonexact_statuses
                                ),
                            }
                        },
                        "required": ["status"],
                    },
                    "escalation_reason": (
                        {"type": "string", "minLength": 1}
                        if aggregate == "escalate"
                        else {"type": "string", "maxLength": 0}
                    ),
                    **(
                        {}
                        if aggregate == "respond"
                        else {}
                    ),
                    "goal_outcomes": {
                        "type": "object",
                        "properties": outcome_properties,
                    },
                },
                "required": [
                    "disposition",
                    "coverage",
                    "steps",
                    "goal_satisfaction",
                    "escalation_reason",
                    "goal_outcomes",
                ],
            }
            assignment_branches.append(branch)
        schema.setdefault("allOf", []).append({"anyOf": assignment_branches})
        # Native decoders may ignore the cross-field intersection. Lift bounds
        # shared by every already-valid assignment into the visible fields.
        # This cannot select an assignment: every permitted judgment remains.
        constraints = [branch["properties"] for branch in assignment_branches]
        properties["disposition"]["enum"] = list(dict.fromkeys(
            value for row in constraints for value in row["disposition"]["enum"]))
        properties["steps"]["minItems"] = max(properties["steps"].get("minItems", 0), min(row["steps"]["minItems"] for row in constraints))
        properties["steps"]["maxItems"] = min(properties["steps"].get("maxItems", 6), max(row["steps"]["maxItems"] for row in constraints))
        for goal_id in allowed_goals:
            fields = properties["goal_outcomes"]["properties"][goal_id]["properties"]
            choices = [row["goal_outcomes"]["properties"][goal_id]["properties"] for row in constraints]
            fields["disposition"]["enum"] = list(dict.fromkeys(
                value for choice in choices for value in choice["disposition"]["enum"]))
            fields["step_ids"]["minItems"] = min(choice["step_ids"].get("minItems", 0) for choice in choices)
            fields["step_ids"]["maxItems"] = max(choice["step_ids"]["maxItems"] for choice in choices)
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
                                "properties": {"status": {"enum": ["exact", "substantial", "partial"]}}
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
    nonexact_goal_outcomes = {
        goal_id: {
            "properties": {
                "satisfaction": {
                    "properties": {"status": {"enum": ["substantial"]}},
                    "required": ["status"],
                }
            }
        }
        for goal_id in allowed_goals
    }
    schema.setdefault("allOf", []).append(
        {
            "if": {
                "properties": {"plan_relation": {"enum": ["safe_adjustment", "alternative"]}},
                "required": ["plan_relation"],
            },
            "then": {
                "properties": {
                    "goal_satisfaction": {
                        "properties": {"status": {"enum": ["substantial"]}},
                        "required": ["status"],
                    },
                    "goal_outcomes": {
                        "properties": nonexact_goal_outcomes,
                    },
                },
                "required": ["goal_satisfaction", "goal_outcomes"],
            },
        }
    )
    _constrain_capability_confirmation(
        schema,
        confirmation_required_capability_ids or [],
    )

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
        "escalation_reason",
        "unresolved",
        "parameter_resolutions",
        "time_conditions",
        "plan_relation",
        "user_confirmation_required",
    )
    schema["properties"] = {
        key: properties[key] for key in preferred_property_order if key in properties
    }
    _constrain_terminal_unresolved(schema)
    _constrain_auxiliary_activity_schema(schema, auxiliary_social_capabilities)
    if response_only and assignment_branches:
        # Native object decoding ignores root allOf once properties is present.
        # Materialize the existing speech assignments as complete alternatives;
        # the unchanged outer schema still validates their full intersection.
        native_base = copy.deepcopy(schema)
        native_base.pop("$defs", None)
        native_base.pop("allOf", None)
        native_speech_branches: list[dict[str, Any]] = []
        for assignment_branch in assignment_branches:
            constraints = assignment_branch["properties"]
            if constraints["steps"]["maxItems"] != 0:
                continue
            native_variant = copy.deepcopy(native_base)
            native_properties = native_variant["properties"]
            for field_name in ("disposition", "coverage", "steps", "escalation_reason"):
                native_properties[field_name].update(constraints[field_name])
            satisfaction_restrictions = [(
                native_properties["goal_satisfaction"],
                constraints["goal_satisfaction"]["properties"]["status"]["enum"],
            )]
            for goal_id, goal_constraint in constraints["goal_outcomes"]["properties"].items():
                goal_fields = native_properties["goal_outcomes"]["properties"][goal_id]["properties"]
                constrained_fields = goal_constraint["properties"]
                for field_name in ("disposition", "coverage", "step_ids"):
                    goal_fields[field_name].update(constrained_fields[field_name])
                satisfaction_restrictions.append((
                    goal_fields["satisfaction"],
                    constrained_fields["satisfaction"]["properties"]["status"]["enum"],
                ))
            for satisfaction_field, allowed_statuses in satisfaction_restrictions:
                satisfaction_field["anyOf"] = [
                    band for band in satisfaction_field["anyOf"]
                    if set(band["properties"]["status"]["enum"]).issubset(allowed_statuses)
                ]
            native_variant["properties"] = {
                "goal_outcomes": native_properties["goal_outcomes"],
                **{key: value for key, value in native_properties.items() if key != "goal_outcomes"},
            }
            native_speech_branches.append(native_variant)
        schema["anyOf"] = native_speech_branches
    return schema


def _constrain_planner_step_args(
    step_schema: dict[str, Any],
    *,
    allowed_capabilities: list[str],
    capability_input_schemas: dict[str, dict[str, Any]] | None,
    nonparallel_capability_ids: list[str] | None = None,
) -> None:
    """Bind each model-selected capability to its exact provider arg schema."""

    if not capability_input_schemas:
        return
    base_properties = step_schema.get("properties")
    if not isinstance(base_properties, dict):
        return
    required = [str(item) for item in step_schema.get("required", []) if str(item).strip()]
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
        if capability_id in set(nonparallel_capability_ids or []):
            timing = properties.get("timing")
            if isinstance(timing, dict):
                timing["enum"] = ["sequential"]
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
                        }
                },
            ]
        }
    )
    schema.setdefault("allOf", []).append(
        {
            "if": {
                "properties": {
                    "disposition": {
                        "enum": [
                            "respond",
                            "clarify",
                            "unavailable",
                            "refused",
                            "escalate",
                        ]
                    }
                },
                "required": ["disposition"],
            },
            "then": {
                "properties": {
                    "user_confirmation_required": {
                        "type": "boolean",
                        "enum": [False],
                    }
                },
                "required": ["user_confirmation_required"],
            },
        }
    )


def _constrain_capability_confirmation(schema: dict[str, Any], capability_ids: list[str]) -> None:
    """Require a Planner confirmation proposal for provider-gated Work.

    Provider metadata determines whether authorization needs confirmation;
    Planner still authors the proposal bit in its one semantic result, and Host
    later owns the actual confirmation state and authorization decision.
    """

    required_ids = sorted({item for item in capability_ids if item})
    if not required_ids:
        return
    schema.setdefault("allOf", []).append(
        {
            "if": {
                "properties": {
                    "steps": {
                        "contains": {
                            "type": "object",
                            "properties": {"capability_id": {"enum": required_ids}},
                            "required": ["capability_id"],
                        }
                    }
                },
                "required": ["steps"],
            },
            "then": {
                "properties": {
                    "user_confirmation_required": {
                        "type": "boolean",
                        "enum": [True],
                    }
                },
                "required": ["user_confirmation_required"],
            },
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
                            "properties": {"disposition": {"enum": ["execute", "respond"]}},
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




def _fast_terminal_activity_contract() -> dict[str, Any]:
    """Require real Work or a complete response alongside a clarification."""

    def contains_role(role: str) -> dict[str, Any]:
        return {
            "contains": {
                "type": "object",
                "properties": {"role": {"const": role}},
                "required": ["role"],
            },
            "minContains": 1,
        }

    return {
        "if": {
            "properties": {"disposition": {"enum": ["execute", "mixed"]}},
            "required": ["disposition"],
        },
        "then": {
            "properties": {"coverage": {"const": "complete"}},
            "anyOf": [
                {"properties": {"activities": contains_role("capability")}},
                {"properties": {
                    "disposition": {"const": "mixed"},
                    "activities": {"allOf": [
                        contains_role("complete_response"),
                        contains_role("clarification"),
                    ]},
                }},
            ],
        },
    }


def _fast_source_span_contract(
    source_token_refs: list[str] | None,
) -> dict[str, Any]:
    token_ref = (
        {"type": "string", "enum": list(source_token_refs)}
        if source_token_refs
        else {"type": "string", "minLength": 1, "maxLength": 24}
    )
    return {
        "type": "object",
        "properties": {
            "source_start_token_ref": copy.deepcopy(token_ref),
            "source_end_token_ref": copy.deepcopy(token_ref),
        },
        "required": ["source_start_token_ref", "source_end_token_ref"],
        "additionalProperties": False,
    }

def fast_advance_response_schema(
    responsibility_refs: list[str],
    *,
    responsibilities: list[CognitiveResponsibilityProposal] | None = None,
    capabilities: list[dict[str, Any]] | None = None,
    auxiliary_social_capabilities: list[dict[str, Any]] | None = None,
    meaning_uncertainties: list[UserMeaningUncertainty] | None = None,
    source_token_refs: list[str] | None = None,
    committed_communicative: bool = False,
    suppress_new_communicative: bool = False,
    suppress_new_progress: bool = False,
) -> dict[str, Any]:
    """Constrain Fast Activities to authoritative WHAT and the live catalog.

    Work/evidence readiness is a Planner decision, not a UMI field. The decoder
    therefore keeps response, execution, clarification, escalation, and silence-
    preserving branches available subject only to already-committed communication
    and concrete Capability contracts.
    """

    schema = copy.deepcopy(FastPlannerAdvanceModelOutput.model_json_schema())
    unresolved_meaning = {
        " ".join(item.description.strip().split())
        for item in (meaning_uncertainties or [])
        if " ".join(item.description.strip().split())
    }
    top_properties = schema.get("properties", {})
    disposition = top_properties.get("disposition")
    if isinstance(disposition, dict):
        disposition["enum"] = [
            "respond",
            "execute",
            "mixed",
            "clarify",
            "escalate",
        ]
        if unresolved_meaning:
            disposition["enum"] = ["mixed", "clarify", "escalate"]
            disposition["description"] = (
                "Terminal work must preserve every UMI unresolved meaning in an "
                "exact unresolved_meaning InformationGap citation. Mixed work "
                "may execute only independent Responsibilities not blocked by "
                "a clarification. Escalation authorizes no Capability work."
            )
    activities_schema = top_properties.get("activities")
    # One complete intent may require several Activities. Preserve the DTO bound;
    # Responsibility count is not an execution-step budget.
    schema.setdefault("allOf", []).extend(
        [
            {
                "if": {
                    "properties": {"disposition": {"const": "escalate"}},
                    "required": ["disposition"],
                },
                "then": {
                    "properties": {
                        "coverage": {"enum": ["partial", "uncertain"]},
                        "activities": {
                            "not": {
                                "contains": {
                                    "type": "object",
                                    "properties": {"role": {"const": "capability"}},
                                    "required": ["role"],
                                }
                            }
                        },
                        "continuations": {
                            "items": {"const": "deep_planner"},
                            "minItems": 1,
                            "maxItems": 1,
                        },
                    }
                },
                "else": {"properties": {"continuations": {"maxItems": 0}}},
            },
            _fast_terminal_activity_contract(),
        ]
    )
    reason_summary = top_properties.get("reason_summary")
    if isinstance(reason_summary, dict):
        reason_summary["maxLength"] = 160
    top_properties["activities"]["maxItems"] = 24
    refs = list(dict.fromkeys(responsibility_refs))
    responsibility_items = list(responsibilities or [])
    ordinary_speech_refs = {
        item.local_ref for item in responsibility_items if item.output_mode in {"speech", "other"}
    }
    speech_only = {item.local_ref for item in responsibility_items if item.output_mode == "speech"}
    capability_refs = [ref for ref in refs if ref not in speech_only]
    vocal_modes = {item.local_ref: item.output_mode for item in responsibility_items
                   if item.output_mode in set(VOCAL_MODES) - {"speech"}}
    # Project already-authored UMI timing onto both ends of each relation.
    # Host validation enforces the same invariant; the decoder must not offer
    # a contradictory label and rely on rejection after primary inference.
    timing_choices = {ref: {"sequential", "parallel"} for ref in refs}
    for item in responsibility_items:
        for relation in ("before", "precedes", "after", "follows", "parallel_with"):
            targets = item.bindings.get(relation, [])
            targets = targets if isinstance(targets, list) else [targets]
            for target in targets:
                target = str(target).strip()
                if item.local_ref in timing_choices and target in timing_choices:
                    allowed = {"parallel" if relation == "parallel_with" else "sequential"}
                    timing_choices[item.local_ref] &= allowed
                    timing_choices[target] &= allowed
    covered = schema.get("properties", {}).get("covered_responsibility_refs")
    if isinstance(covered, dict):
        covered["items"] = {"type": "string", "enum": refs}
        covered["minItems"] = len(refs)
        covered["maxItems"] = len(refs)
        covered["uniqueItems"] = True
    definitions = schema.get("$defs", {})
    information_gap_contract = definitions.get("PlannerInformationGap")
    if isinstance(information_gap_contract, dict):
        gap_required = information_gap_contract.setdefault("required", [])
        if "required_for" not in gap_required:
            gap_required.append("required_for")
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
            if meaning_uncertainties == []:
                gap_properties["source_kind"] = {
                    "const": "execution_input",
                    "type": "string",
                }
                applicable_capability_ids = [
                    str(item.get("capability_id") or "").strip()
                    for item in (capabilities or [])
                    if isinstance(item, dict) and str(item.get("capability_id") or "").strip()
                ]
                if applicable_capability_ids:
                    gap_properties["source_reference"] = {
                        "type": "string",
                        "enum": applicable_capability_ids,
                    }
                    execution_input_branches: list[dict[str, Any]] = []
                    for capability in capabilities or []:
                        if not isinstance(capability, dict):
                            continue
                        capability_id = str(capability.get("capability_id") or "").strip()
                        input_schema = capability.get("input_schema")
                        if not capability_id or not isinstance(input_schema, dict):
                            continue
                        input_properties = input_schema.get("properties") or {}
                        required_inputs = [
                            str(name)
                            for name in input_schema.get("required") or []
                            if isinstance(input_properties.get(str(name)), dict)
                            and "default" not in input_properties[str(name)]
                            # This is the same direct-binding exclusion enforced
                            # by Host. Across several Responsibilities, exclude
                            # only names bound in every possible source owner.
                            and not (responsibility_items and all(
                                str(name) in item.bindings for item in responsibility_items
                            ))
                        ]
                        if not required_inputs:
                            continue
                        execution_input_branches.append(
                            {
                                "properties": {
                                    "source_reference": {
                                        "const": capability_id,
                                        "type": "string",
                                    },
                                    "required_for": {
                                        "type": "array",
                                        "items": {
                                            "type": "string",
                                            "enum": required_inputs,
                                        },
                                        "minItems": 1,
                                        "maxItems": len(required_inputs),
                                        "uniqueItems": True,
                                    },
                                },
                                "required": [
                                    "source_reference",
                                    "required_for",
                                ],
                            }
                        )
                    if execution_input_branches:
                        information_gap_contract.setdefault("allOf", []).append(
                            {"anyOf": execution_input_branches}
                        )
                        native_gaps = []
                        for constraint in execution_input_branches:
                            variant = copy.deepcopy(information_gap_contract)
                            variant.pop("allOf", None)
                            variant["properties"].update(constraint["properties"])
                            native_gaps.append(variant)
                        information_gap_contract["oneOf"] = native_gaps
    clarification_contract = definitions.get("FastPlannerInputNeed")
    if isinstance(clarification_contract, dict):
        gaps = clarification_contract.get("properties", {}).get("information_gaps")
        if isinstance(gaps, dict):
            # One Responsibility may retain several independent UMI gaps. Stay
            # within the canonical DTO bound instead of forcing silent omission.
            gaps["maxItems"] = min(
                int(gaps.get("maxItems", 8)), max(1, len(unresolved_meaning))
            )
    for contract_name in (
        "FastPlannerResponseNeed",
        "FastPlannerInputNeed",
        "FastPlannerCapabilityActivity",
    ):
        contract = definitions.get(contract_name)
        if not isinstance(contract, dict):
            continue
        contract_properties = contract.get("properties", {})
        source_refs = contract_properties.get("source_responsibility_refs")
        if isinstance(source_refs, dict):
            allowed_refs = (
                capability_refs
                if contract_name == "FastPlannerCapabilityActivity"
                else (
                    [ref for ref in refs if ref in ordinary_speech_refs]
                    if (contract_name == "FastPlannerResponseNeed" and responsibility_items)
                    else refs
                )
            )
            source_refs["items"] = {"type": "string", "enum": allowed_refs}
            source_refs["uniqueItems"] = True
            source_refs["maxItems"] = len(allowed_refs)
        role = contract_properties.get("role")
        if isinstance(role, dict):
            # Put the discriminating semantic choice before the branch payload.
            # Otherwise constrained decoding can commit to the first, easiest
            # union branch before it reaches ``role`` and coerce intended
            # Capability Activities into Communicative Acts.
            contract["properties"] = {
                "role": role,
                **{name: value for name, value in contract_properties.items() if name != "role"},
            }
    activity_items = activities_schema.get("items") if isinstance(activities_schema, dict) else None
    if isinstance(activity_items, dict) and responsibility_items:
        allowed_activity_contracts = [
            "FastPlannerCapabilityActivity",
            "FastPlannerInputNeed",
        ]
        if ordinary_speech_refs and not (committed_communicative or suppress_new_communicative):
            allowed_activity_contracts.insert(1, "FastPlannerResponseNeed")
        activity_items["oneOf"] = [
            {"$ref": f"#/$defs/{contract_name}"} for contract_name in allowed_activity_contracts
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
    allowed_capabilities = [
        item
        for item in (capabilities or [])
        if isinstance(item, dict) and item.get("capability_id")
    ]
    if isinstance(capability_contract, dict) and allowed_capabilities:
        capability_id = capability_contract.get("properties", {}).get("capability_id")
        if isinstance(capability_id, dict):
            capability_id["enum"] = [str(item["capability_id"]) for item in allowed_capabilities]
        capability_contract.pop("allOf", None)
        capability_properties = capability_contract.get("properties")
        if isinstance(capability_properties, dict):
            capability_required = list(capability_contract.get("required", []))
            for field_name in ("args", "timing"):
                if field_name not in capability_required:
                    capability_required.append(field_name)
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
                branch_properties["args"] = _ordered_capability_arguments(input_schema)
                hints = capability.get("hints")
                derivation_targets: set[str] = set()
                if isinstance(hints, dict):
                    raw_derivations = hints.get("argument_derivation")
                    if isinstance(raw_derivations, dict):
                        derivation_targets = {
                            str(name) for name in raw_derivations
                        }
                trusted_grounded_parameters = {"target_ref"} | derivation_targets
                index_grounded_parameters = (
                    {"evidence_id", "tool_id", "material_args"}
                    if capability_id_value == "chromie.memory.retrieve_verified_tool_result"
                    else set()
                )
                trusted_grounded_parameters |= index_grounded_parameters
                if capability_id_value == VOCAL_PERFORMANCE_CAPABILITY_ID:
                    trusted_grounded_parameters.add("mode")
                # Match the Host's existing exact vocal-provider/mode invariant.
                # UMI has already authored the mode; this does not infer it from words.
                modes: list[str | None] = [None]
                if vocal_modes and capability_id_value == VOCAL_PERFORMANCE_CAPABILITY_ID:
                    mode_contract = input_schema.get("properties", {}).get("mode", {})
                    modes = list(mode_contract.get("enum", [mode_contract["const"]]
                                 if "const" in mode_contract else VOCAL_MODES))
                for mode in modes:
                    timings_by_refs: dict[tuple[str, ...], list[str]] = {}
                    for timing in ("sequential", "parallel"):
                        if timing == "parallel" and capability.get("can_run_parallel") is False:
                            continue
                        compatible = tuple(ref for ref in capability_refs
                            if timing in timing_choices[ref] and (ref not in vocal_modes or vocal_modes[ref] == mode))
                        if compatible:
                            timings_by_refs.setdefault(compatible, []).append(timing)
                    for compatible, timings in timings_by_refs.items():
                        properties = copy.deepcopy(branch_properties)
                        required = list(capability_required)
                        bound_parameters = {
                            str(name)
                            for item in responsibility_items
                            if item.local_ref in compatible
                            for name in item.bindings
                        }
                        realized_parameters: set[str] = set()
                        for binding_name in bound_parameters:
                            realization = _argument_realization_contract(capability, binding_name)
                            if isinstance(realization, dict):
                                realized_parameters.update(
                                    str(name)
                                    for name in realization.get("arguments") or []
                                )
                        grounded_parameters = trusted_grounded_parameters | bound_parameters | realized_parameters
                        input_properties = input_schema.get("properties")
                        if isinstance(input_properties, dict):
                            owning_outcomes = [item.outcome for item in responsibility_items if item.local_ref in compatible]
                            # Host permits a literal string copy only when it occurs
                            # in the owning intent AND immutable input. Test whether
                            # even an exact source copy could match an owning intent,
                            # including Host's case-only representation allowance.
                            # If not, no real source could satisfy that exception.
                            # Require the Planner's span; never infer an enum mapping.
                            mapped_enum_inputs = {
                                name for name, contract in input_properties.items()
                                if isinstance(contract, dict) and contract.get("type") == "string"
                                and contract.get("enum") and len(owning_outcomes) == len(compatible)
                                and not any(literal_intent_argument(value, outcome=outcome, source_text=value)
                                    for value in contract["enum"] for outcome in owning_outcomes)
                            }
                            required_inputs = {
                                str(name) for name in input_schema.get("required") or []
                            }
                            required_source_inputs = sorted(
                                name
                                for name in required_inputs
                                if name not in grounded_parameters
                                and isinstance(input_properties.get(name), dict)
                                and (input_properties[name].get("type")
                                     in ("number", "integer", "boolean", "object", "array")
                                     or name in mapped_enum_inputs)
                            )
                            span_contract = _fast_source_span_contract(source_token_refs)
                            properties["argument_sources"] = {
                                "type": "object",
                                "properties": {
                                    str(name): copy.deepcopy(span_contract)
                                    for name in sorted(input_properties)
                                    if name not in index_grounded_parameters
                                },
                                "required": required_source_inputs,
                                "additionalProperties": False,
                            }
                            if required_source_inputs and "argument_sources" not in required:
                                required.append("argument_sources")
                        if mode is not None:
                            properties["args"]["properties"]["mode"] = {**mode_contract, "enum": [mode]}
                        properties["timing"] = {"type": "string", "enum": timings}
                        properties["source_responsibility_refs"]["items"] = {"type": "string", "enum": list(compatible)}
                        properties["source_responsibility_refs"]["maxItems"] = len(compatible)
                        branches.append({
                            "type": "object",
                            "properties": properties,
                            "required": required,
                            "additionalProperties": False,
                        })
            if branches:
                capability_contract["oneOf"] = branches
            elif isinstance(activity_items, dict):
                # Contradictory source relations or incompatible providers leave
                # clarification/escalation available, never executable leakage.
                activity_items["oneOf"] = [branch for branch in activity_items.get("oneOf", [])
                    if branch.get("$ref") != "#/$defs/FastPlannerCapabilityActivity"]
    elif vocal_modes and isinstance(activity_items, dict):
        # No catalog provider cannot become an invented vocal provider.
        activity_items["oneOf"] = [branch for branch in activity_items.get("oneOf", [])
            if branch.get("$ref") != "#/$defs/FastPlannerCapabilityActivity"]
    # Decide local Work before its redundant aggregate disposition.
    properties = schema["properties"]
    schema["properties"] = {
        "activities": properties["activities"],
        **{key: value for key, value in properties.items() if key != "activities"},
    }
    return schema




def _ollama_streaming_schema(
    schema: dict[str, Any],
    *,
    retain_value_constraints: bool = False,
) -> dict[str, Any]:
    """Compile the Fast stream contract to Ollama's reliable GBNF subset.

    Ollama converts ``format`` JSON Schema to a grammar. Nested Pydantic refs,
    an object carrying both base properties and a branch union, and annotation
    keywords have produced silently unconstrained output in supported Ollama
    releases. Runtime still validates the full Pydantic contract after decode;
    this projection preserves the structural choices needed during generation.
    """

    definitions = schema.get("$defs", {})
    if not isinstance(definitions, dict):
        definitions = {}
    annotations = {
        "$defs",
        "$schema",
        "default",
        "description",
        "discriminator",
        "examples",
        "exclusiveMaximum",
        "exclusiveMinimum",
        "format",
        "maxItems",
        "maxLength",
        "maximum",
        "minItems",
        "minLength",
        "minimum",
        "multipleOf",
        "pattern",
        "title",
        "uniqueItems",
    }
    if retain_value_constraints:
        annotations.difference_update(
            {
                "exclusiveMaximum",
                "exclusiveMinimum",
                "maxItems",
                "maxLength",
                "maximum",
                "minItems",
                "minLength",
                "minimum",
                "multipleOf",
                "pattern",
                "uniqueItems",
            }
        )

    def compile_node(node: Any, stack: tuple[str, ...] = ()) -> Any:
        if isinstance(node, list):
            return [compile_node(item, stack) for item in node]
        if not isinstance(node, dict):
            return node
        if node.get("type") == "array" and node.get("maxItems") == 0:
            return {"type": "array", "enum": [[]]}
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/$defs/"):
            name = ref.rsplit("/", 1)[-1]
            if name in stack or name not in definitions:
                raise ValueError(f"invalid recursive or missing streaming schema ref: {ref}")
            compiled = compile_node(definitions[name], (*stack, name))
            siblings = {key: value for key, value in node.items() if key != "$ref"}
            if siblings:
                if not isinstance(compiled, dict):
                    raise ValueError(f"streaming schema ref cannot accept siblings: {ref}")
                compiled = {**compiled, **compile_node(siblings, stack)}
            return compiled

        # Capability and auxiliary definitions first carry their generic object
        # shape and then exact per-capability object branches. The branch objects
        # already contain the complete shape, so avoid an ambiguous conjunction.
        branches = node.get("oneOf")
        if (
            node.get("type") == "object"
            and "properties" in node
            and isinstance(branches, list)
            and branches
        ):
            node = {"oneOf": branches}

        compiled_node: dict[str, Any] = {}
        for key, value in node.items():
            if key in annotations:
                continue
            if key == "const":
                compiled_node["enum"] = [compile_node(value, stack)]
            elif key == "properties" and isinstance(value, dict):
                # Property names such as ``description`` or ``default`` are
                # application fields, not schema annotations.
                compiled_node[key] = {
                    property_name: compile_node(property_schema, stack)
                    for property_name, property_schema in value.items()
                }
            else:
                compiled_node[key] = compile_node(value, stack)
        union = compiled_node.get("oneOf")
        if isinstance(union, list):
            flattened: list[Any] = []
            for branch in union:
                if isinstance(branch, dict) and set(branch) == {"oneOf"}:
                    nested = branch.get("oneOf")
                    if isinstance(nested, list):
                        flattened.extend(nested)
                        continue
                flattened.append(branch)
            if len(flattened) == 1:
                only_branch = flattened[0]
                if isinstance(only_branch, dict):
                    return only_branch
            compiled_node["oneOf"] = flattened
        return compiled_node

    compiled_schema = compile_node(copy.deepcopy(schema))
    if not isinstance(compiled_schema, dict):
        raise ValueError("compiled streaming response schema must remain an object")
    return compiled_schema


def _ordered_capability_arguments(schema: dict[str, Any]) -> dict[str, Any]:
    """Match the catalog's lexicographic JSON order without changing its values.

    Constrained object decoding cannot return to an earlier optional property.
    Keep argument objects aligned with the sorted catalog seen by the model;
    decision/discriminator order outside arguments remains owned by the role.
    """
    result = copy.deepcopy(schema)

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            if isinstance(node.get("properties"), dict):
                node["properties"] = dict(sorted(node["properties"].items()))
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(result)
    return result


def fast_streaming_advance_response_schema(
    responsibility_refs: list[str], *,
    responsibilities: list[CognitiveResponsibilityProposal] | None = None,
    capabilities: list[dict[str, Any]] | None = None,
    auxiliary_social_capabilities: list[dict[str, Any]] | None = None,
    meaning_uncertainties: list[UserMeaningUncertainty] | None = None,
    language: str = "",
    source_token_refs: list[str] | None = None,
) -> dict[str, Any]:
    """One complete Work result; independent SC owns communication latency."""
    schema = fast_advance_response_schema(
        responsibility_refs, responsibilities=responsibilities, capabilities=capabilities,
        meaning_uncertainties=meaning_uncertainties, source_token_refs=source_token_refs,
    )
    compiled = _ollama_streaming_schema(schema, retain_value_constraints=True)
    compiled["title"] = "FastPlannerWorkAdvanceOutput"
    # Streaming Fast is the latency-critical provisional Work pass. One
    # Responsibility may need up to four executable Activities plus one terminal
    # communication/clarification Activity. Larger compositions belong to Deep;
    # do not let native constrained decoding spend its whole deadline filling the
    # DTO's broad retained compatibility bound.
    activities = compiled.get("properties", {}).get("activities")
    if isinstance(activities, dict):
        retained_bound = int(activities.get("maxItems", 24))
        fast_bound = max(1, len(responsibility_refs)) * 5
        activities["maxItems"] = min(retained_bound, fast_bound)
    # Native decoders do not enforce the conditional allOf contract. Keep that
    # full validation and expose the same execution/delegation states as unions.
    states = []
    for disposition in compiled["properties"]["disposition"]["enum"]:
        state = copy.deepcopy(compiled)
        state.pop("allOf", None)
        properties = state["properties"]
        properties["disposition"] = {"type": "string", "enum": [disposition]}
        if disposition in {"execute", "mixed", "respond"}:
            properties["coverage"] = {"type": "string", "enum": ["complete"]}
        if disposition == "escalate":
            properties["coverage"] = {"type": "string", "enum": ["partial", "uncertain"]}
            properties["continuations"] = {"type": "array", "items": {"enum": ["deep_planner"]},
                                            "minItems": 1, "maxItems": 1}
            items = properties["activities"]["items"]
            alternatives = [item for item in items.get("oneOf", [items])
                if item.get("properties", {}).get("role", {}).get("enum") != ["capability"]]
            if alternatives:
                properties["activities"]["items"] = {"oneOf": alternatives}
            else:
                properties["activities"]["maxItems"] = 0
        else:
            properties["continuations"] = {"type": "array", "enum": [[]]}
        states.append(state)
    compiled["oneOf"] = states
    return compiled


def deep_plan_response_schema(
    expected_goal_ids: list[str],
    *,
    allowed_capability_ids: list[str] | None = None,
    capability_input_schemas: dict[str, dict[str, Any]] | None = None,
    auxiliary_social_capabilities: list[dict[str, Any]] | None = None,
    response_only: bool = False,
    requires_execution: bool = False,
    response_goal_ids: list[str] | None = None,
    provider_vocal_goal_ids: list[str] | None = None,
    provider_media_goal_operations: dict[str, str] | None = None,
    unavailable_information_goal_ids: list[str] | None = None,
    unavailable_resource_goal_ids: list[str] | None = None,
    single_step_goal_ids: list[str] | None = None,
    required_numeric_goal_values: dict[str, list[int | float]] | None = None,
    confirmation_required_capability_ids: list[str] | None = None,
    nonparallel_capability_ids: list[str] | None = None,
) -> dict[str, Any]:
    return canonical_plan_response_schema(
        planner_tier="deep",
        expected_goal_ids=expected_goal_ids,
        allowed_capability_ids=list(allowed_capability_ids or []),
        capability_input_schemas=capability_input_schemas,
        auxiliary_social_capabilities=auxiliary_social_capabilities,
        response_only=response_only,
        requires_execution=requires_execution,
        response_goal_ids=response_goal_ids,
        provider_vocal_goal_ids=(provider_vocal_goal_ids),
        provider_media_goal_operations=(provider_media_goal_operations),
        unavailable_information_goal_ids=unavailable_information_goal_ids,
        unavailable_resource_goal_ids=unavailable_resource_goal_ids,
        single_step_goal_ids=single_step_goal_ids,
        required_numeric_goal_values=required_numeric_goal_values,
        confirmation_required_capability_ids=(confirmation_required_capability_ids),
        nonparallel_capability_ids=nonparallel_capability_ids,
    )


def capability_lookup_response_schema(schema: dict[str, Any], entries: list[Any]) -> dict[str, Any]:
    """One read-only request or one complete Plan; never both."""
    ids = [item.capability_id for item in entries]
    if not ids:
        return schema
    definitions = schema.get("$defs", {})
    plan = {key: value for key, value in schema.items() if key != "$defs"}
    lookup = {
        "type": "object", "additionalProperties": False,
        "required": ["requested_capability_ids"],
        "properties": {"requested_capability_ids": {
            "type": "array", "items": {"type": "string", "enum": ids},
            "minItems": 1, "maxItems": 8, "uniqueItems": True,
            "description": (
                "Request full contracts for indexed abilities needed to realize accepted "
                "Responsibilities. Use this branch instead of substituting an unrelated "
                "already-loaded Capability."
            ),
        }},
    }
    # Put lookup first. Native constrained decoders may commit to a oneOf branch from
    # the first emitted member; plan-first ordering previously trapped semantically
    # correct indexed-ability reasoning inside the loaded-capability enum.
    return {"$defs": definitions, "oneOf": [lookup, plan]}



def planner_readiness_response_schema(
    schema: dict[str, Any], goal_ids: list[str], *,
    confirmation_required_capability_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Allow source-bound waiting without letting a response fulfill an effect.

    Each waiting Goal has an unmet outcome and a cited future condition. Other
    Goals may retain their independent ready Work. Runtime validates provenance,
    prohibits early Work and holds waiting Goals open until their due wake.
    """
    if not goal_ids:
        return schema
    waiting = fast_multi_goal_response_schema(
        expected_goal_ids=goal_ids, allowed_capability_ids=[], response_only=True,
        response_goal_ids=goal_ids, nonfulfilling_response_goal_ids=goal_ids,
    )
    waiting = scoped_reporting_response_schema(
        waiting, goal_ids=set(goal_ids), expected_goal_ids=goal_ids,
        future_goal_times={goal_id: None for goal_id in goal_ids},
    )
    for variant in [waiting, *waiting.get("anyOf", [])]:
        variant["properties"]["cancel_activity_ids"] = {
            "type": "array", "items": {"type": "string"}, "maxItems": 0,
        }
    if len(goal_ids) > 1:
        waiting = _mixed_readiness_schema(
            schema, goal_ids, confirmation_required_capability_ids or [],
        )
    # Keep independently specialized definitions distinct between the two shapes.
    def rename(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: rename(item) for key, item in value.items()}
        if isinstance(value, list):
            return [rename(item) for item in value]
        if isinstance(value, str) and value.startswith("#/$defs/"):
            return value.replace("#/$defs/", "#/$defs/Waiting", 1)
        return value
    definitions = {**schema.get("$defs", {}), **{
        "Waiting" + name: rename(value) for name, value in waiting.pop("$defs", {}).items()
    }}
    return {"$defs": definitions, "anyOf": [
        {key: value for key, value in schema.items() if key != "$defs"}, rename(waiting),
    ]}


def _mixed_readiness_schema(
    schema: dict[str, Any], goal_ids: list[str], confirmation_ids: list[str],
) -> dict[str, Any]:
    """Preserve the ordinary step contract while allowing independently timed Goals.

    Conditions are linear in Goal count; do not enumerate future/ready subsets.
    The Host repeats these constraints for decoders without cross-field support.
    """
    step = schema["$defs"]["PlannerModelStep"]
    mixed = fast_multi_goal_response_schema(
        expected_goal_ids=goal_ids,
        allowed_capability_ids=step["properties"]["capability_id"].get("enum", []),
        nonfulfilling_response_goal_ids=goal_ids,
        confirmation_required_capability_ids=confirmation_ids,
    )
    # Retain all catalog, typed-binding, resource and Work-reuse restrictions
    # already compiled by the ordinary entrypoint. Waiting grants no new Work.
    mixed["$defs"]["PlannerModelStep"] = copy.deepcopy(step)
    fields = mixed["properties"]
    ordinary = schema["properties"]
    for name in ("steps", "cancel_activity_ids", "user_confirmation_required"):
        fields[name] = copy.deepcopy(ordinary[name])
    fields["steps"]["minItems"] = 0
    fields["time_conditions"].update(minItems=1, maxItems=len(goal_ids), uniqueItems=True)
    for goal_id in goal_ids:
        timer = {"contains": {"type": "object", "properties": {
            "goal_id": {"const": goal_id}, "source_quote": {"type": "string", "minLength": 1}},
            "required": ["goal_id", "source_quote"]}, "minContains": 1, "maxContains": 1}
        scoped = scoped_reporting_response_schema(
            mixed, goal_ids={goal_id}, expected_goal_ids=goal_ids,
            future_goal_times={goal_id: None},
        )["properties"]
        mixed.setdefault("allOf", []).append({
            "if": {"properties": {"time_conditions": timer}},
            "then": {"properties": {
                "goal_outcomes": {"properties": {goal_id: scoped["goal_outcomes"]["properties"][goal_id]}},
                "goal_satisfaction": scoped["goal_satisfaction"],
                "steps": {"items": {"properties": {"source_goal_ids": {
                    "not": {"contains": {"const": goal_id}}}}}},
            }},
        })
        # An effect cannot turn into an untimed response through this alternative.
        dispositions = ordinary["goal_outcomes"]["properties"][goal_id]["properties"]["disposition"]["enum"]
        if "respond" not in dispositions:
            mixed["allOf"].append({
                "if": {"properties": {"goal_outcomes": {"properties": {goal_id: {
                    "properties": {"disposition": {"const": "respond"}}}}}}},
                "then": {"properties": {"time_conditions": timer}},
            })
    return mixed
