from __future__ import annotations

import copy
from datetime import datetime
from itertools import combinations, product
from typing import Any

from shared.chromie_contracts.user_turn import user_turn_source_span_schema, user_turn_source_tokens
from shared.chromie_contracts.core_interpretation import CognitiveResponsibilityProposal, UserMeaningUncertainty, responsibility_binding_material_value
from shared.chromie_contracts.interaction import (
    VOCAL_MODES,
    VOCAL_PERFORMANCE_CAPABILITY_ID,
)
from shared.chromie_contracts.plan import (
    responsibility_outcome_source_tokens,
    FastPlannerAdvanceModelOutput,
    GOAL_SATISFACTION_SCORE_BANDS,
)

from .planner_validation import _capability_acquires_information
from .planner_fast_validation import fast_capability_acquires_information
from .planner_grounding import (
    _argument_realization_contract,
    _argument_schema_accepts_canonical_binding,
    _count_argument_names,
    _goal_binding_map,
    _is_count_binding,
    _material_values_equal,
    _normalized_entity_type,
    _resource_source_binding_type,
    literal_intent_argument,
    provider_resolves_required_source,
    semantic_numeric_values,
)
from .planner_model_contract import (
    ABILITY_NEED_NONE,
    ABILITY_NEEDS_MAX,
    PlannerEvidenceReentryModelOutput,
    PlannerModelOutput,
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
    retained_branches: list[dict[str, Any]] = []
    for branch in branches:
        properties = branch.get("properties") if isinstance(branch, dict) else None
        capability_ids = (properties.get("capability_id") or {}).get("enum") if isinstance(properties, dict) else None
        # A single resource-delivery Responsibility already ends in the provider's
        # safe terminal posture.  Do not offer a routine stand-idle cleanup branch
        # to the decoder.  An explicitly requested posture action is a separate
        # Responsibility/Goal and therefore does not enter this single-resource path.
        if isinstance(capability_ids, list) and capability_ids == ["soridormi.stand_idle"]:
            constrained = True
            continue
        retained_branches.append(branch)
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
    step_schema["oneOf"] = retained_branches
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
                and not any(
                    _argument_schema_accepts_canonical_binding(
                        (candidate.get("input_schema") or {}).get("properties", {}).get(parameter, {}),
                        binding["value"],
                    )
                    for candidate in capabilities or []
                    for parameter in _count_argument_names(candidate, name)
                )
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
            if entity_type == "count":
                # One compound Goal can own a counted effect and uncounted or
                # independently counted siblings. Host conserves the exact count
                # across owned steps; each branch retains its provider format.
                constrained = True
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
            if any(_is_count_binding(name, binding)
                   for goal in authoritative_goals
                   for binding_name, binding in _goal_binding_map(goal).items()
                   if binding_name == name):
                continue
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
    information_capability_ids: list[str] | None = None,
    completed_evidence_refs: list[str] | None = None,
    respond_requires_commitment: bool = False,
    held_effect_goal_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Compact decoder contract for trusted Planner Evidence re-entry.

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
                next_action["enum"] = ["respond", "clarify", "unavailable"]

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
            information_capability_ids=information_capability_ids,
        )

    # Compile the existing DTO invariants into complete native alternatives.
    # Cross-field if/then alone is not a native-decoder guarantee. Keep the
    # same semantic fields and allow mixed multi-Goal decisions.
    definitions = schema["$defs"]
    decision_base = copy.deepcopy(definitions["PlannerEvidenceReentryGoalDecision"])
    allowed_actions = decision_base["properties"]["next_action"]["enum"]

    # A respond cites only completed Evidence, which Host proves before any answer
    # (live 2026-10-12: a timed-out read was "responded" and rejected, then silence).
    # Without that list (no proof supplied) every scoped Evidence ref stays citable.
    completed = (list(evidence) if completed_evidence_refs is None
                 else [ref for ref in dict.fromkeys(completed_evidence_refs) if ref in evidence])

    # A Goal whose source Plan holds an effect (owner choice B) is settled by this
    # decision: performing the held effect, or answering that its condition does not
    # hold, covers it. Host rejects an execute below commitment for such a Goal, so the
    # decoder offers execute there only at substantial/exact (live 2026-10-13: a held
    # wave scored "partial" became a limitation the person heard as "I can't wave").
    held = [goal for goal in goals if goal in set(held_effect_goal_ids or [])]
    goal_sets = [subset for subset in ([goal for goal in goals if goal not in held], held) if subset]

    def decision_branches(actions: list[str]) -> dict[str, Any]:
        branches = []
        for subset in goal_sets:
            branches.extend(subset_branches(actions, subset, holds_effect=subset is held))
        return {"anyOf": branches}

    def subset_branches(actions: list[str], subset: list[str], *, holds_effect: bool) -> list[dict[str, Any]]:
        branches = []
        for status, (minimum, maximum) in GOAL_SATISFACTION_SCORE_BANDS.items():
            permitted = [
                action for action in actions
                if (status != "exact" or action in {"respond", "execute"})
                and (action != "respond" or completed)
                and not (holds_effect and action == "execute" and status not in {"substantial", "exact"})
            ]
            # A clarify carries the input need the person can resolve; its lifted Goal
            # outcome requires one (live 2026-10-13: after a failed fetch a clarify with
            # only a rationale passed this decoder and failed the outcome DTO).
            groups = [[action] for action in ("respond", "execute", "clarify") if action in permitted]
            if rest := [action for action in permitted if action not in {"respond", "execute", "clarify"}]:
                groups.append(rest)
            for group in groups:
                branch = copy.deepcopy(decision_base)
                fields = branch["properties"]
                if len(goal_sets) > 1:
                    fields["goal_id"]["enum"] = list(subset)
                fields["next_action"]["enum"] = group
                fields["satisfaction_status"]["enum"] = [status]
                # Keep fractional bands in full Schema validation. The serving
                # decoder's float-range compiler loses valid interior values (for
                # example 0.5 in [0.01, 0.749999]); its native range stays [0, 1].
                fields["satisfaction_score"]["allOf"] = [
                    {"minimum": minimum, "maximum": maximum}
                ]
                if group[0] in {"respond", "execute"}:
                    fields["unresolved_needs"]["maxItems"] = 0
                if group == ["clarify"]:
                    fields["unresolved_needs"]["minItems"] = 1
                if respond_requires_commitment and group == ["respond"] and status not in {"substantial", "exact"}:
                    # Outside reporting, a respond below commitment becomes a limitation at
                    # Host; that choice is unavailable's (live 2026-10-12).
                    continue
                if group == ["respond"]:
                    fields["evidence_refs"]["items"]["enum"] = completed
                    fields["evidence_refs"].update(minItems=1, maxItems=len(completed))
                    branch["required"] = [*branch["required"], "evidence_refs"]
                branches.append(branch)
        return branches

    definitions["PlannerEvidenceReentryGoalDecision"] = decision_branches(allowed_actions)
    # Without new Work nothing is adjusted or confirmed; adjusted or alternative Work is
    # confirmed. States keep that DTO rule native (live 2026-10-12: a clarify was sent
    # as a safe_adjustment with no Work and rejected).
    definitions["PlannerEvidenceReentryGoalDecisionWithoutWork"] = decision_branches(
        [action for action in allowed_actions if action != "execute"])
    states = []
    for relation, confirmation, with_work in (
        (["exact"], [False], False),
        (["exact"], [False, True], True),
        (["safe_adjustment", "alternative"], [True], True),
    ):
        if with_work and not allow_new_work:
            continue
        state = {key: copy.deepcopy(value) for key, value in schema.items()
                 if key in {"type", "properties", "required", "additionalProperties"}}
        fields = state["properties"]
        fields["plan_relation"] = {"type": "string", "enum": relation}
        fields["user_confirmation_required"] = {"type": "boolean", "enum": confirmation}
        if with_work:
            fields["new_work"]["minItems"] = 1
        else:
            fields["new_work"]["maxItems"] = 0
            fields["goal_decisions"]["items"] = {
                "$ref": "#/$defs/PlannerEvidenceReentryGoalDecisionWithoutWork"}
        states.append(state)
    schema["oneOf"] = states
    return schema


def canonical_plan_response_schema(
    *,
    expected_goal_ids: list[str],
    allowed_capability_ids: list[str],
    capability_input_schemas: dict[str, dict[str, Any]] | None = None,
    response_only: bool = False,
    requires_execution: bool = False,
    response_goal_ids: list[str] | None = None,
    nonfulfilling_response_goal_ids: list[str] | None = None,
    effectful_goal_ids: list[str] | None = None,
    confirmation_required_capability_ids: list[str] | None = None,
    unavailable_goal_ids: list[str] | None = None,
    information_capability_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Return one flat, constrained model-output schema for a planner request.

    This schema deliberately excludes the host-owned CanonicalPlan envelope.
    The host supplies its plan identity, tier, schema version, and exact Goal
    Association IDs after validating this semantic DTO. Cross-field invariants
    remain enforced by ``PlannerModelOutput`` and ``CanonicalPlan``. A malformed
    or semantically rejected result fails closed; it is never regenerated by the
    same Planner. The decoder-tight per-goal shape is used for one or many goals
    so the schema never instructs the model to omit fields that deterministic
    validation requires.
    """

    schema = fast_multi_goal_response_schema(
        expected_goal_ids=expected_goal_ids,
        allowed_capability_ids=allowed_capability_ids,
        capability_input_schemas=capability_input_schemas,
        response_only=response_only,
        requires_execution=requires_execution,
        response_goal_ids=response_goal_ids,
        nonfulfilling_response_goal_ids=nonfulfilling_response_goal_ids,
        # As for several Goals: an effectful Goal is never answered with words alone,
        # which Host rejects (live 2026-10-15: "Yes, please." for water was planned as
        # respond and then reached the waiting shape to get past the decoder).
        effectful_goal_ids=effectful_goal_ids,
        confirmation_required_capability_ids=(confirmation_required_capability_ids),
        unavailable_goal_ids=unavailable_goal_ids,
        information_capability_ids=information_capability_ids,
    )
    schema["title"] = "FastPlannerModelOutput"
    return schema


def readiness_first_response_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """The Planner states any future readiness before it writes the Goal outcomes.

    Waiting was chosen implicitly by the outcome the model wrote first, so a Goal the
    model meant to acknowledge reached the waiting shape and was given an invented
    condition ("Yes, please.", "Do it again!"; live 2026-10-13/15). With time_conditions
    after ability_needs, an empty list closes waiting before any outcome. Order only.
    """
    def visit(node: Any) -> None:
        if isinstance(node, dict):
            properties = node.get("properties")
            if isinstance(properties, dict) and "time_conditions" in properties and "goal_outcomes" in properties:
                first = [name for name in ("ability_needs", "time_conditions") if name in properties]
                node["properties"] = {**{name: properties[name] for name in first},
                                      **{name: value for name, value in properties.items() if name not in first}}
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(schema)
    return schema


def native_goal_outcome_branches(schema: dict[str, Any]) -> dict[str, Any]:
    """Final decoder pass: each Goal outcome becomes per-disposition native branches.

    Applied after every canonical schema refinement, so each branch carries the final
    per-Goal enums and bounds. Validation semantics are unchanged. Every exposed shape
    is covered, however deeply nested: the decoder follows a nested alternative and
    ignores its siblings (live 2026-10-13: the readiness wrapper's inner waiting shapes
    still offered a partial respond, which the outcome DTO rejects).
    """
    result = copy.deepcopy(schema)

    def exposed(node: dict[str, Any]) -> list[dict[str, Any]]:
        return [node, *[shape for key in ("oneOf", "anyOf") for item in node.get(key) or []
                        if isinstance(item, dict) for shape in exposed(item)]]

    for shape in exposed(result):
        outcomes = (shape.get("properties") or {}).get("goal_outcomes")
        goals = outcomes.get("properties") if isinstance(outcomes, dict) else None
        if not isinstance(goals, dict):
            continue
        for goal_id, outcome in list(goals.items()):
            if isinstance(outcome, dict) and isinstance(outcome.get("properties"), dict):
                description = outcome.get("description")
                goals[goal_id] = _goal_outcome_disposition_branches(outcome)
                if description:
                    goals[goal_id]["description"] = description
    return result


def _goal_outcome_disposition_branches(outcome: dict[str, Any]) -> dict[str, Any]:
    """Expose one Goal outcome's per-disposition shape natively (``validate_outcome_shape``).

    Native decoders ignore the conditional ``allOf``; live 2026-10-11 an execute outcome
    carried communication ordering and failed the DTO. Each branch fixes the disposition
    and the fields that disposition allows; the model still chooses the disposition.
    """
    properties = outcome.get("properties")
    disposition = properties.get("disposition") if isinstance(properties, dict) else None
    choices = disposition.get("enum") if isinstance(disposition, dict) else None
    if not isinstance(choices, list) or not choices:
        return outcome
    base = {key: value for key, value in outcome.items() if key not in {"allOf", "oneOf", "anyOf"}}
    branches = []
    for choice in choices:
        branch = copy.deepcopy(base)
        fields = branch["properties"]
        fields["disposition"] = {"type": "string", "enum": [choice]}
        terminal = choice in {"execute", "respond"}
        fields["coverage"] = {"type": "string", "enum": ["complete"] if terminal else ["partial", "uncertain"]}
        if isinstance(fields.get("step_ids"), dict):
            if choice == "execute":
                fields["step_ids"]["minItems"] = max(1, int(fields["step_ids"].get("minItems", 0)))
            else:
                fields["step_ids"]["maxItems"] = 0
        if isinstance(fields.get("unresolved"), dict):
            if terminal:
                fields["unresolved"]["maxItems"] = 0
            elif choice == "clarify":
                fields["unresolved"]["minItems"] = 1
        if choice != "respond":
            for name in ("precedes_step_ids", "follows_step_ids"):
                if isinstance(fields.get(name), dict):
                    fields[name]["maxItems"] = 0
        branches.append(branch)
    return {"oneOf": branches} if len(branches) > 1 else branches[0]


def fast_multi_goal_response_schema(
    *,
    expected_goal_ids: list[str],
    allowed_capability_ids: list[str],
    capability_input_schemas: dict[str, dict[str, Any]] | None = None,
    response_only: bool = False,
    requires_execution: bool = False,
    response_goal_ids: list[str] | None = None,
    nonfulfilling_response_goal_ids: list[str] | None = None,
    effectful_goal_ids: list[str] | None = None,
    confirmation_required_capability_ids: list[str] | None = None,
    unavailable_goal_ids: list[str] | None = None,
    information_capability_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Return a decoder-tight, model-authored multi-goal plan schema.

    The Planner model authors the semantic plan itself: aggregate
    disposition and coverage, executable steps, exact step ownership,
    per-goal outcomes, limitation judgments, and prospective satisfaction. It
    authors no wording: Social Cognition owns every user-facing word.  The host adds only envelope identity fields after validation.

    Every field needed by deterministic validation is required at the JSON
    decoder boundary.  A limitation is represented by model-authored per-goal
    ``unavailable`` outcomes rather than an empty host-interpreted map.
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
            (["respond", "mixed", "clarify", "unavailable"] if len(expected_goal_ids) > 1 else ["respond", "clarify", "unavailable"])
            if response_only
            else ["execute", "mixed", "clarify", "unavailable"]
            if requires_execution and response_goal_ids
            else ["execute", "clarify", "unavailable"]
            if requires_execution
            else ["respond", "execute", "mixed", "clarify", "unavailable"]
        )

    if isinstance(disposition, dict) and len(set(expected_goal_ids)) < 2:
        disposition["enum"] = [value for value in disposition["enum"] if value != "mixed"]

    allowed_goals = list(dict.fromkeys(expected_goal_ids))
    allowed_capabilities = list(dict.fromkeys(allowed_capability_ids))
    response_goal_set = set(response_goal_ids or []).intersection(allowed_goals)
    cancellation_goal_set = set(nonfulfilling_response_goal_ids or []).intersection(allowed_goals)
    effectful_goal_set = set(effectful_goal_ids or []).intersection(allowed_goals)
    # Goals whose information or resource provider is absent from the supplied contracts
    # can only be an honest limitation (the former Deep decoder guarantee).
    unavailable_goal_set = set(unavailable_goal_ids or []).intersection(allowed_goals)

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
    if requires_execution:
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
    # judgment, including an unsatisfied/partial judgment for a limitation.
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
        bound_text(outcome_properties, "rationale", 200)
        outcome_unresolved = outcome_properties.get("unresolved")
        if isinstance(outcome_unresolved, dict):
            outcome_unresolved["maxItems"] = 4
            if isinstance(outcome_unresolved.get("items"), dict):
                outcome_unresolved["items"]["maxLength"] = 240
        outcome_disposition = outcome_properties.get("disposition")
        if isinstance(outcome_disposition, dict):
            outcome_disposition["enum"] = (
                ["respond", "clarify", "unavailable"]
                if response_only
                else ["execute", "clarify", "unavailable"]
                if requires_execution
                else ["respond", "execute", "clarify", "unavailable"]
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
            "depends_on",
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
            information_capability_ids=information_capability_ids,
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
                    disposition_field["enum"] = ["execute", "clarify", "unavailable"]
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
                        "unavailable",
                    ]
                branches = specialized_outcome.get("oneOf")
                if isinstance(branches, list):
                    specialized_outcome["oneOf"] = [
                        branch
                        for branch in branches
                        if (
                            branch.get("properties", {}).get("disposition", {}).get("enum")
                            in (["respond"], ["clarify"], ["unavailable"])
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
                            "disposition": {"enum": ["unavailable"]},
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
                    "empty list for respond/clarify/unavailable."
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
            "clarify when all clarify, and unavailable when all are unavailable."
        )

    # Encode the aggregate invariant in the decoder grammar.  The model still
    # chooses each goal's semantic disposition; this cross-field constraint
    # only makes the redundant top-level aggregate and executable-step count
    # consistent with those model-authored choices.  Enumerating the small
    # execute/respond assignment space avoids a host-side semantic compiler.
    # Larger turns keep the normal validator path rather than exploding the
    # response schema.
    assignment_branches: list[dict[str, Any]] = []
    if 1 <= len(allowed_goals) <= 6:
        # One Goal may be unavailable while its siblings execute or are answered (the one
        # Planner keeps the former Deep mixed outcome); bounded so the space stays small.
        per_goal_limitation = ("unavailable",) if len(allowed_goals) <= 4 else ()
        assignment_choices = [
            ("unavailable",)
            if goal_id in unavailable_goal_set
            else (("respond", "clarify")
                  if goal_id in response_goal_set
                  else ("execute",)
                  if goal_id in effectful_goal_set
                  else (("execute",) if requires_execution else ("execute", "respond")))
            + per_goal_limitation
            for goal_id in allowed_goals
        ]
        assignments = list(product(*assignment_choices))
        assignments.append(tuple("clarify" for _ in allowed_goals))
        assignments.append(tuple("unavailable" for _ in allowed_goals))
        for assignment in dict.fromkeys(assignments):
            assignment_set = set(assignment)
            if any(goal_id in unavailable_goal_set and disposition != "unavailable"
                   for goal_id, disposition in zip(allowed_goals, assignment, strict=True)):
                continue
            if "clarify" in assignment_set and "execute" in assignment_set:
                continue
            if "clarify" in assignment_set and "unavailable" in assignment_set:
                continue
            if requires_execution and assignment_set == {"respond"}:
                continue
            if assignment_set == {"execute"}:
                aggregate = "execute"
            elif assignment_set == {"respond"}:
                aggregate = "respond"
            elif assignment_set == {"clarify"}:
                aggregate = "clarify"
            elif assignment_set == {"unavailable"}:
                aggregate = "unavailable"
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
                    "goal_outcomes",
                ],
            }
            if not execute_count:
                # No executable Goal: nothing to confirm (PlannerModelOutput rejects it too).
                branch["properties"]["user_confirmation_required"] = {"type": "boolean", "const": False}
                branch["required"].append("user_confirmation_required")
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
        # or a limitation owns none and cannot claim exact satisfaction.
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
                            "disposition": {"enum": ["clarify", "unavailable"]},
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
            for field_name in ("disposition", "coverage", "steps"):
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
    information_capability_ids: list[str] | None = None,
) -> None:
    """Bind each model-selected capability to its exact provider arg schema.

    With ``information_capability_ids`` the step purpose is also the provider's:
    only an information-acquiring Capability may be ``acquire_information``, and
    then with the expected Evidence the step contract requires (live 2026-10-12:
    a re-entry wave decided as a read failed DTO validation).
    """

    if not capability_input_schemas:
        return
    base_properties = step_schema.get("properties")
    if not isinstance(base_properties, dict):
        return
    required = [str(item) for item in step_schema.get("required", []) if str(item).strip()]
    readers = None if information_capability_ids is None else set(information_capability_ids)
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
        purposes = (
            [None] if readers is None
            else ["achieve_effect", "acquire_information"] if capability_id in readers
            else ["achieve_effect"]
        )
        for purpose in purposes:
            branch_properties = copy.deepcopy(properties)
            branch_required = list(required)
            if purpose is not None and "step_purpose" in branch_properties:
                branch_properties["step_purpose"] = {"type": "string", "enum": [purpose]}
            if purpose == "acquire_information" and "expected_outcome" in branch_properties:
                # An omitted purpose is achieve_effect, so a read states both fields.
                branch_properties["expected_outcome"] = {
                    **branch_properties["expected_outcome"], "minLength": 1,
                }
                branch_required += [name for name in ("step_purpose", "expected_outcome")
                                    if name not in branch_required]
            branches.append(
                {
                    "type": "object",
                    "properties": branch_properties,
                    "required": branch_required,
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


# Planner pass-specific constrained-decoder schemas. These functions
# project an already-owned Planner contract; they do not invoke a model or choose HOW.




def _fast_terminal_activity_contract() -> dict[str, Any]:
    """Require real Work, or for mixed any answered or clarified Responsibility.

    Mixed follows from the Responsibility decisions; Host adds each unavailable
    Activity, so "answer one, cannot do the other" is mixed with only a response
    (live 2026-10-13: "你会后空翻吗？翻一个给我看看！" was rejected here).
    """

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
                    "activities": {"anyOf": [
                        contains_role("complete_response"),
                        contains_role("clarification"),
                    ]},
                }},
            ],
        },
    }


_UNRESOLVED_PROVIDER_SOURCE_STATUSES = ("unknown", "provider_resolved")


def _provider_source_status_branches(
    branch: dict[str, Any], *, situation_source_refs: list[str],
) -> list[dict[str, Any]]:
    """Express the Host's provider-source invariant as decoder-enforceable branches.

    The provider resolves the source itself, so the Planner never retypes a location
    into it. A bare unresolved status cites nothing. A known source is its status
    plus cited evidence of where: the span where the person said it, or the current
    Situation observation that saw it; trusted code keeps the cited surface. Native
    structured decoders do not apply ``if``/``then``, so each choice is a branch.
    """

    source_schema = branch["properties"]["args"]["properties"]["source"]
    if set(source_schema.get("required", [])) - {"status"}:
        return [branch]
    statuses = list(((source_schema.get("properties") or {}).get("status") or {}).get("enum") or [])

    def status_only(current: dict[str, Any], allowed: list[str]) -> dict[str, Any]:
        current["properties"]["args"]["properties"]["source"] = {
            "type": "object",
            "properties": {"status": {"type": "string", "enum": allowed}},
            "required": ["status"],
            "additionalProperties": False,
        }
        return current["properties"].get("argument_sources")

    variants = []
    unresolved = [status for status in statuses if status in _UNRESOLVED_PROVIDER_SOURCE_STATUSES]
    if unresolved:
        current = copy.deepcopy(branch)
        spans = status_only(current, unresolved)
        if isinstance(spans, dict):
            spans.get("properties", {}).pop("source", None)
            if "source" in spans.get("required", []):
                spans["required"].remove("source")
        variants.append(current)
    # Host treats a bare provider_resolved as unresolved; cited evidence makes it known.
    cited = ["known"] if "known" in statuses else []
    spans = branch["properties"].get("argument_sources")
    evidence = []
    if isinstance(spans, dict) and "source" in spans.get("properties", {}):
        evidence.append(spans["properties"]["source"])
    if situation_source_refs:
        evidence.append({
            "type": "object",
            "properties": {"situation_interpretation_ref": {
                "type": "string", "enum": list(situation_source_refs),
            }},
            "required": ["situation_interpretation_ref"],
            "additionalProperties": False,
        })
    if cited and evidence:
        current = copy.deepcopy(branch)
        current_spans = status_only(current, cited)
        current_spans.setdefault("properties", {})["source"] = (
            copy.deepcopy(evidence[0]) if len(evidence) == 1 else {"oneOf": copy.deepcopy(evidence)}
        )
        if "source" not in current_spans.setdefault("required", []):
            current_spans["required"].append("source")
        if "source" not in current["properties"]["args"].setdefault("required", []):
            current["properties"]["args"]["required"].append("source")
        if "argument_sources" not in current["required"]:
            current["required"].append("argument_sources")
        variants.append(current)
    return variants or [branch]


def _fast_enum_source_branches(
    branch: dict[str, Any], *, capability: dict[str, Any],
    grounded_parameters: set[str], owning_outcomes: list[str],
    original_user_text: str,
) -> list[dict[str, Any]]:
    """Project the Host's literal-copy exception for each selected enum value.

    A translated WHO is not the immutable source. Keep literal copies available
    only when the same value occurs on both authoritative surfaces; all other
    required enum values keep the existing Planner source-span obligation.
    Complete object alternatives survive the native streaming grammar projection.
    """
    args = branch["properties"]["args"]
    variants = [branch]
    for name in args.get("required") or []:
        contract = args.get("properties", {}).get(name)
        if (name in grounded_parameters or provider_resolves_required_source(capability, name)
                or not isinstance(contract, dict) or contract.get("type") != "string"
                or not isinstance(contract.get("enum"), list)):
            continue
        literal_values = [value for value in contract["enum"]
                          if any(literal_intent_argument(value, outcome=outcome,
                                     source_text=original_user_text) for outcome in owning_outcomes)]
        mapped_values = [value for value in contract["enum"] if value not in literal_values]
        expanded = []
        for variant in variants:
            for values, needs_source in ((literal_values, False), (mapped_values, True)):
                if not values:
                    continue
                current = copy.deepcopy(variant)
                properties = current["properties"]
                properties["args"]["properties"][name]["enum"] = values
                if needs_source:
                    source_required = properties["argument_sources"].setdefault("required", [])
                    if name not in source_required:
                        source_required.append(name)
                    if "argument_sources" not in current["required"]:
                        current["required"].append("argument_sources")
                expanded.append(current)
        variants = expanded
    return variants


def fast_advance_response_schema(
    responsibility_refs: list[str],
    *,
    responsibilities: list[CognitiveResponsibilityProposal] | None = None,
    capabilities: list[dict[str, Any]] | None = None,
    meaning_uncertainties: list[UserMeaningUncertainty] | None = None,
    source_token_refs: list[str] | None = None,
    original_user_text: str = "",
    situation_source_refs: list[str] | None = None,
    committed_communicative: bool = False,
    suppress_new_communicative: bool = False,
    suppress_new_progress: bool = False,
    trusted_target_ref: str = "",
) -> dict[str, Any]:
    """Constrain Fast Activities to authoritative WHAT and the live catalog.

    Work/evidence readiness is a Planner decision, not a UMI field. The decoder
    therefore keeps response, execution, clarification, limitation, and silence-
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
            "unavailable",
        ]
        if unresolved_meaning:
            disposition["enum"] = ["mixed", "clarify", "unavailable"]
            disposition["description"] = (
                "Terminal work must preserve every UMI unresolved meaning in an "
                "exact unresolved_meaning InformationGap citation. Mixed work "
                "may execute only independent Responsibilities not blocked by "
                "a clarification. Unavailable authorizes no Capability work."
            )
    activities_schema = top_properties.get("activities")
    # One complete intent may require several Activities. Preserve the DTO bound;
    # Responsibility count is not an execution-step budget.
    schema.setdefault("allOf", []).extend(
        [
            {
                "if": {
                    "properties": {"disposition": {"const": "unavailable"}},
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
                    }
                },
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
    # An information question that current established perception already answers ("is there
    # water?" with a bottle in view) is answered from the cited observation; with no answer
    # path the Planner fetched the water to "confirm" it (live 2026-10-16).
    perceived_answer_refs = {
        item.local_ref for item in responsibility_items if item.output_mode == "information"
    } if situation_source_refs else set()
    # Both ends of a typed requested concurrency; a Capability that cannot run in
    # parallel cannot realize them, so the decoder leaves a limitation instead.
    concurrent_refs: set[str] = set()
    for item in responsibility_items:
        targets = item.bindings.get("parallel_with", [])
        for target in targets if isinstance(targets, list) else [targets]:
            if str(target).strip() in refs:
                concurrent_refs.update({item.local_ref, str(target).strip()})
    vocal_modes = {item.local_ref: item.output_mode for item in responsibility_items
                   if item.output_mode in set(VOCAL_MODES) - {"speech"}}
    covered = schema.get("properties", {}).get("covered_responsibility_refs")
    if isinstance(covered, dict):
        covered["items"] = {"type": "string", "enum": refs}
        covered["minItems"] = len(refs)
        covered["maxItems"] = len(refs)
        covered["uniqueItems"] = True
    definitions = schema.get("$defs", {})
    provider_owned_inputs_complete = False
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
                def binding_realizes_input(
                    capability: dict[str, Any],
                    item: CognitiveResponsibilityProposal,
                    name: str,
                ) -> bool:
                    if provider_resolves_required_source(capability, name):
                        return True
                    if name in item.bindings:
                        return True
                    return any(
                        isinstance(contract := _argument_realization_contract(
                            capability, binding_name
                        ), dict)
                        and name in (contract.get("arguments") or [])
                        for binding_name in item.bindings
                    )

                def provider_owns_ready_inputs(capability: dict[str, Any]) -> bool:
                    hints = capability.get("hints") or {}
                    resource_contract = hints.get("resource_contract") or {}
                    owned = set(resource_contract.get("provider_owns") or [])
                    if not {"source_resolution", "navigation", "perception"} <= owned:
                        return False
                    input_schema = capability.get("input_schema") or {}
                    required = input_schema.get("required") or []
                    return bool(responsibility_items) and all(
                        all(
                            binding_realizes_input(capability, item, str(name))
                            for name in required
                        )
                        for item in responsibility_items
                    )

                gap_properties["source_kind"] = {
                    "const": "execution_input",
                    "type": "string",
                }
                applicable_capability_ids = [
                    str(item.get("capability_id") or "").strip()
                    for item in (capabilities or [])
                    if isinstance(item, dict)
                    and str(item.get("capability_id") or "").strip()
                    and not provider_owns_ready_inputs(item)
                ]
                provider_owned_inputs_complete = bool(capabilities) and not applicable_capability_ids
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
                        if capability_id not in applicable_capability_ids:
                            continue
                        input_schema = capability.get("input_schema")
                        if not capability_id or not isinstance(input_schema, dict):
                            continue
                        input_properties = input_schema.get("properties") or {}
                        required_inputs = [
                            str(name)
                            for name in input_schema.get("required") or []
                            if isinstance(input_properties.get(str(name)), dict)
                            and "default" not in input_properties[str(name)]
                            and not provider_resolves_required_source(capability, str(name))
                            # A typed semantic binding may realize a structured
                            # provider argument through argument_realization.
                            # Neither form is a missing user input.
                            and not (responsibility_items and all(
                                binding_realizes_input(capability, item, str(name))
                                for item in responsibility_items
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
            elif unresolved_meaning:
                # Host admits only the exact UMI uncertainty wording as an unresolved_meaning
                # source (live 2026-10-16: a gap cited "u1" and the clarification failed).
                meaning_gap = copy.deepcopy(information_gap_contract)
                meaning_gap["properties"]["source_kind"] = {"type": "string", "const": "unresolved_meaning"}
                meaning_gap["properties"]["source_reference"] = {
                    "type": "string", "enum": sorted(unresolved_meaning)}
                input_gap = copy.deepcopy(information_gap_contract)
                input_gap["properties"]["source_kind"] = {"type": "string", "const": "execution_input"}
                information_gap_contract["oneOf"] = [meaning_gap, input_gap]
            # Expose PlannerInformationGap's existing membership invariants.
            # Source order remains irrelevant to the canonical contract.
            source_variants = []
            for gap in information_gap_contract.pop("oneOf", []) or [copy.deepcopy(information_gap_contract)]:
                kind_schema = gap["properties"]["source_kind"]
                kinds = [kind_schema["const"]] if "const" in kind_schema else kind_schema["enum"]
                for kind in kinds:
                    variant = copy.deepcopy(gap)
                    variant["properties"]["source_kind"] = {"type": "string", "const": kind}
                    required_sources = ["authoritative_context"]
                    if kind == "execution_input":
                        required_sources.append("capability_schema")
                    sources = variant["properties"]["resolution_sources_considered"]
                    sources["allOf"] = [{"contains": {"type": "string", "const": name}} for name in required_sources]
                    sources["minItems"] = len(required_sources)
                    source_variants.append(variant)
            information_gap_contract["oneOf"] = source_variants
    clarification_contract = definitions.get("FastPlannerInputNeed")
    if isinstance(clarification_contract, dict):
        gaps = clarification_contract.get("properties", {}).get("information_gaps")
        if isinstance(gaps, dict):
            # One Responsibility may retain several independent UMI gaps. Stay
            # within the canonical DTO bound instead of forcing silent omission.
            gaps["maxItems"] = min(
                int(gaps.get("maxItems", 8)), max(1, len(unresolved_meaning))
            )
    unavailable_contract = definitions.get("FastPlannerUnavailableNeed")
    if isinstance(unavailable_contract, dict):
        missing = unavailable_contract.get("properties", {}).get("missing")
        if isinstance(missing, dict):
            missing["items"] = {"type": "string", "minLength": 1, "maxLength": 240}
            missing["description"] = (
                "What Chromie lacks for this Responsibility now, such as a Capability that the "
                "loaded and library contracts do not provide. Facts, never wording."
            )
    for contract_name in (
        "FastPlannerResponseNeed",
        "FastPlannerInputNeed",
        "FastPlannerCapabilityActivity",
        "FastPlannerUnavailableNeed",
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
        if contract_name == "FastPlannerResponseNeed":
            # Host writes a perceived answer's citations from the decision's observed_refs.
            contract_properties.pop("situation_interpretation_refs", None)
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
        # A limitation is a Responsibility decision (responsibility_decisions), not an Activity.
        allowed_activity_contracts = [
            "FastPlannerCapabilityActivity",
        ]
        if not provider_owned_inputs_complete:
            allowed_activity_contracts.append("FastPlannerInputNeed")
        elif isinstance(disposition, dict):
            disposition["enum"] = [
                value for value in disposition.get("enum", []) if value != "clarify"
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
    decisions_schema = top_properties.get("responsibility_decisions")
    if isinstance(decisions_schema, dict):
        offered = (
            {item.get("$ref", "").rsplit("/", 1)[-1] for item in activity_items.get("oneOf", [])}
            if isinstance(activity_items, dict) and responsibility_items else
            {"FastPlannerCapabilityActivity", "FastPlannerResponseNeed", "FastPlannerInputNeed"}
        )
        has_capabilities = bool([item for item in (capabilities or []) if isinstance(item, dict)])
        limitation = {
            "type": "object", "additionalProperties": False, "required": ["decision", "missing"],
            "properties": {
                "decision": {"type": "string", "enum": ["unavailable"]},
                "missing": {"type": "array", "minItems": 1, "maxItems": 4,
                            "items": {"type": "string", "minLength": 1, "maxLength": 240}},
            },
        }
        per_ref: dict[str, Any] = {}
        for ref in refs:
            choices = []
            if "FastPlannerCapabilityActivity" in offered and has_capabilities and ref in capability_refs:
                choices.append("work")
            if "FastPlannerResponseNeed" in offered and (not responsibility_items or ref in ordinary_speech_refs):
                choices.append("answer")
            if "FastPlannerInputNeed" in offered:
                choices.append("clarify")
            answered = {
                "type": "object", "additionalProperties": False, "required": ["decision", "missing"],
                "properties": {"decision": {"type": "string", "enum": choices},
                               "missing": {"type": "array", "maxItems": 0}},
            }
            # Ordinary speech needs no Capability: SC can always say what Chromie knows,
            # does not know, or will not say (live 2026-10-12: a joke was "unavailable").
            branches = ([answered] if ref in speech_only and "answer" in choices
                        else [limitation] if not choices else [answered, limitation])
            if ref in perceived_answer_refs and not (committed_communicative or suppress_new_communicative):
                # Name the observations first; only a cited one opens answer_from_perception.
                observed = {
                    "type": "object", "additionalProperties": False,
                    "required": ["observed_refs", "decision", "missing"],
                    "properties": {
                        "observed_refs": {"type": "array", "minItems": 1, "uniqueItems": True,
                                          "maxItems": min(8, len(situation_source_refs or [])),
                                          "items": {"type": "string", "enum": list(situation_source_refs or [])}},
                        "decision": {"type": "string", "enum": ["answer_from_perception"]},
                        "missing": {"type": "array", "maxItems": 0},
                    },
                }
                for branch in branches:
                    branch["properties"] = {"observed_refs": {"type": "array", "maxItems": 0},
                                            **branch["properties"]}
                    branch["required"] = ["observed_refs", *branch["required"]]
                branches = [*branches, observed]
            per_ref[ref] = copy.deepcopy(branches[0]) if len(branches) == 1 else {"oneOf": copy.deepcopy(branches)}
        decisions_schema.clear()
        decisions_schema.update({
            "type": "object", "additionalProperties": False, "properties": per_ref, "required": list(refs),
            "description": "Decide every Responsibility first: work, answer, clarify, or unavailable "
                           "with the facts it is missing. Activities then realize these decisions.",
        })
        if "responsibility_decisions" not in schema.setdefault("required", []):
            schema["required"].insert(schema["required"].index("activities")
                                      if "activities" in schema["required"] else 0, "responsibility_decisions")
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
            for field_name in ("args", "depends_on"):
                if field_name not in capability_required:
                    capability_required.append(field_name)
            capability_contract["required"] = capability_required
            branches: list[dict[str, Any]] = []
            offers_acquisition = any(fast_capability_acquires_information(item) for item in allowed_capabilities)
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
                # Host accepts a target argument only as the exact current trusted target.
                target_property = (branch_properties["args"].get("properties") or {}).get("target_ref")
                if trusted_target_ref and isinstance(target_property, dict):
                    branch_properties["args"]["properties"]["target_ref"] = {
                        "type": "string", "const": trusted_target_ref,
                    }
                # This purpose is fixed by the provider, not by Goal terminality.
                branch_properties["step_purpose"] = {
                    "type": "string", "enum": [
                        "acquire_information" if fast_capability_acquires_information(capability) else "achieve_effect"
                    ],
                }
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
                    # Order and concurrency are WorkDAG dependencies (depends_on), not a
                    # per-Activity label; Host checks UMI before/after/parallel_with on them.
                    compatible_refs = tuple(ref for ref in capability_refs
                        if (ref not in vocal_modes or vocal_modes[ref] == mode)
                        and not (ref in concurrent_refs and capability.get("can_run_parallel") is False))
                    for compatible in ([compatible_refs] if compatible_refs else []):
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
                        source_schema = properties["args"].get("properties", {}).get("source")
                        source_bindings_schema = (
                            source_schema.get("properties", {}).get("bindings")
                            if isinstance(source_schema, dict) else None
                        )
                        if isinstance(source_bindings_schema, dict):
                            exact_source_bindings: dict[str, Any] = {}
                            for item in responsibility_items:
                                if item.local_ref not in compatible:
                                    continue
                                for binding_name, raw_value in item.bindings.items():
                                    source_type = _resource_source_binding_type(capability, binding_name)
                                    realization = _argument_realization_contract(capability, binding_name)
                                    if source_type == "distance" and isinstance(realization, dict) and "source" in realization.get("arguments", []):
                                        exact_source_bindings[source_type] = responsibility_binding_material_value(raw_value)
                            if exact_source_bindings:
                                source_bindings_schema["properties"] = {
                                    name: {"const": value}
                                    for name, value in sorted(exact_source_bindings.items())
                                }
                                source_bindings_schema["required"] = sorted(exact_source_bindings)
                                source_schema["required"] = sorted(set(source_schema.get("required", [])) | {"bindings"})
                        grounded_parameters = trusted_grounded_parameters | bound_parameters | realized_parameters
                        source_grounded_parameters = grounded_parameters - _count_argument_names(capability)
                        input_properties = input_schema.get("properties")
                        if isinstance(input_properties, dict):
                            required_inputs = {
                                str(name) for name in input_schema.get("required") or []
                            }
                            # An information query's free-text inputs (a place to look up)
                            # come from the person's words. Host admits them only as an
                            # exact literal or with a span, and the decoder cannot enforce
                            # literalness, so they must cite a span (a translated city stays
                            # provable). Authored text and enum strings keep their own paths.
                            acquires_information = fast_capability_acquires_information(capability)
                            required_source_inputs = sorted(
                                name
                                for name in required_inputs
                                if name not in grounded_parameters
                                and not provider_resolves_required_source(capability, name)
                                and isinstance(input_properties.get(name), dict)
                                and (
                                    input_properties[name].get("type")
                                    in ("number", "integer", "boolean", "object", "array")
                                    or (acquires_information
                                        and input_properties[name].get("type") == "string"
                                        and not input_properties[name].get("enum"))
                                )
                            )
                            span_contract = {"oneOf": [
                                user_turn_source_span_schema(source_token_refs),
                                *[
                                    {**branch, "properties": {
                                        **branch["properties"],
                                        "source_responsibility_ref": {"const": item.local_ref, "type": "string"},
                                    }, "required": [*branch["required"], "source_responsibility_ref"]}
                                    for item in responsibility_items if item.local_ref in compatible
                                    for branch in user_turn_source_span_schema(
                                        [token["ref"] for token in responsibility_outcome_source_tokens(
                                            item.local_ref, item.outcome)]
                                    )["oneOf"]
                                ],
                            ]}
                            properties["argument_sources"] = {
                                "type": "object",
                                "properties": {
                                    str(name): copy.deepcopy(span_contract)
                                    for name in sorted(input_properties)
                                    if name not in index_grounded_parameters
                                    and name not in source_grounded_parameters
                                },
                                "required": required_source_inputs,
                                "additionalProperties": False,
                            }
                            if required_source_inputs and "argument_sources" not in required:
                                required.append("argument_sources")
                        if mode is not None:
                            properties["args"]["properties"]["mode"] = {**mode_contract, "enum": [mode]}
                        properties["depends_on"] = {
                            "type": "array",
                            "items": {"type": "string", "minLength": 1, "maxLength": 160},
                            "maxItems": 8,
                        }
                        if "depends_on" not in required:
                            required.append("depends_on")
                        properties["source_responsibility_refs"]["items"] = {"type": "string", "enum": list(compatible)}
                        properties["source_responsibility_refs"]["maxItems"] = len(compatible)
                        if fast_capability_acquires_information(capability):
                            # A read for a non-information outcome always leaves a decision for
                            # the re-entry (for example a conditional action); state it typed.
                            properties["deferred_requirement"] = {
                                "type": "string", "minLength": 1, "maxLength": 240,
                            }
                            if any(item.output_mode != "information" for item in responsibility_items
                                   if item.local_ref in compatible) and "deferred_requirement" not in required:
                                required.append("deferred_requirement")
                            properties.pop("deferred", None)
                        else:
                            properties.pop("deferred_requirement", None)
                            # With a read on offer, every effect states whether it waits on
                            # that read's result (owner choice B); without one it cannot.
                            if offers_acquisition:
                                properties["deferred"] = {"type": "boolean"}
                                if "deferred" not in required:
                                    required.append("deferred")
                            else:
                                properties.pop("deferred", None)
                        branch = {
                            "type": "object",
                            "properties": properties,
                            "required": required,
                            "additionalProperties": False,
                        }
                        variants = [branch]
                        if (provider_resolves_required_source(capability, "source")
                                and "source" not in source_grounded_parameters):
                            # Host also checks this cross-field invariant; the decoder
                            # must offer only its legal combinations.
                            variants = _provider_source_status_branches(
                                branch, situation_source_refs=situation_source_refs or [],
                            )
                        for variant in variants:
                            branches.extend(_fast_enum_source_branches(
                                variant, capability=capability,
                                grounded_parameters=grounded_parameters,
                                owning_outcomes=[item.outcome for item in responsibility_items
                                                 if item.local_ref in compatible],
                                original_user_text=original_user_text,
                            ))
            if branches:
                capability_contract["oneOf"] = branches
            elif isinstance(activity_items, dict):
                # Contradictory source relations or incompatible providers leave
                # clarification/limitation available, never executable leakage.
                activity_items["oneOf"] = [branch for branch in activity_items.get("oneOf", [])
                    if branch.get("$ref") != "#/$defs/FastPlannerCapabilityActivity"]
    elif vocal_modes and isinstance(activity_items, dict):
        # No catalog provider cannot become an invented vocal provider.
        activity_items["oneOf"] = [branch for branch in activity_items.get("oneOf", [])
            if branch.get("$ref") != "#/$defs/FastPlannerCapabilityActivity"]
    # Decide every Responsibility, then its local Work, before the redundant aggregate.
    properties = schema["properties"]
    first = [name for name in ("responsibility_decisions", "activities") if name in properties]
    schema["properties"] = {
        **{name: properties[name] for name in first},
        **{key: value for key, value in properties.items() if key not in first},
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
    meaning_uncertainties: list[UserMeaningUncertainty] | None = None,
    language: str = "",
    source_token_refs: list[str] | None = None,
    original_user_text: str = "",
    situation_source_refs: list[str] | None = None,
    trusted_target_ref: str = "",
) -> dict[str, Any]:
    """One complete Work result; independent SC owns communication latency."""
    schema = fast_advance_response_schema(
        responsibility_refs, responsibilities=responsibilities, capabilities=capabilities,
        meaning_uncertainties=meaning_uncertainties, source_token_refs=source_token_refs,
        original_user_text=original_user_text, situation_source_refs=situation_source_refs,
        trusted_target_ref=trusted_target_ref,
    )
    compiled = _ollama_streaming_schema(schema, retain_value_constraints=True)
    compiled["title"] = "FastPlannerWorkAdvanceOutput"
    # Streaming Fast is the latency-critical provisional Work pass. One
    # Responsibility may need up to four executable Activities plus one terminal
    # communication/clarification Activity. A larger composition is a limitation;
    # do not let native constrained decoding spend its whole deadline filling the
    # DTO's broad retained compatibility bound.
    activities = compiled.get("properties", {}).get("activities")
    if isinstance(activities, dict):
        retained_bound = int(activities.get("maxItems", 24))
        fast_bound = max(1, len(responsibility_refs)) * 5
        activities["maxItems"] = min(retained_bound, fast_bound)
        compiled["properties"] = {
            **{name: value for name, value in compiled["properties"].items() if name != "activities"
               and name not in _AFTER_ACTIVITIES},
            "activity_count": {"type": "integer", "minimum": 0, "maximum": activities["maxItems"]},
            "activities": activities,
            **{name: value for name, value in compiled["properties"].items() if name in _AFTER_ACTIVITIES},
        }
        compiled["required"] = [*compiled.get("required", []), "activity_count"]
    # Native decoders do not enforce the conditional allOf contract. Keep that
    # full validation and expose the same execution/limitation states as unions.
    states = []
    for disposition in compiled["properties"]["disposition"]["enum"]:
        state = copy.deepcopy(compiled)
        state.pop("allOf", None)
        properties = state["properties"]
        properties["disposition"] = {"type": "string", "enum": [disposition]}
        if disposition in {"execute", "mixed", "respond"}:
            properties["coverage"] = {"type": "string", "enum": ["complete"]}
            # Every Work state carries at least one Activity (limitations are decisions).
            properties["activities"]["minItems"] = 1
        if disposition == "clarify":
            # Host binds no clarification from a bare decision: its information_gaps are authored
            # (live 2026-10-16: "把那个拿给我" decided clarify with zero Activities and failed).
            properties["activities"]["minItems"] = 1
        if disposition == "unavailable":
            # Every Responsibility is a limitation: its facts live in its decision.
            properties["coverage"] = {"type": "string", "enum": ["partial", "uncertain"]}
            properties["activities"]["maxItems"] = 0
        if not _restrict_state_decisions(properties, disposition, responsibility_refs):
            continue
        if disposition == "mixed":
            states.extend(_mixed_limitation_states(state, responsibility_refs))
            continue
        # A uniform decision is realized only by its own roles (live 2026-10-12: a single
        # work decision also authored a clarification and Host rejected the turn).
        decided = _STATE_DECISION.get(disposition)
        roles = set().union(*(_DECISION_ROLES[item] for item in decided)) if decided else None
        items = properties["activities"]["items"]
        if roles is not None and isinstance(items, dict) and isinstance(items.get("oneOf"), list):
            kept = [item for item in items["oneOf"]
                    if (item.get("properties", {}).get("role", {}).get("enum") or [""])[0] in roles]
            # Host writes an answer from perception, so such a state may have no Activity.
            activity_free = _state_decisions(properties) <= _ACTIVITY_FREE_DECISIONS
            if not kept and properties["activities"].get("minItems") and not activity_free:
                continue
            if kept:
                items["oneOf"] = kept
            else:
                properties["activities"]["maxItems"] = 0
                properties["activities"].pop("minItems", None)
        states.append(state)
    compiled["oneOf"] = _exact_activity_count_states(states)
    _responsibility_refs_first(compiled)
    return compiled


def _responsibility_refs_first(node: Any) -> None:
    """Each Activity names the Responsibilities it serves before its Capability and args.

    The model then writes a shared read for every Responsibility it serves instead of
    binding it to the one whose words it was writing (live 2026-10-15: one weather read
    for "will it rain" and "should I take an umbrella" was bound to the first only, and
    Host rejected the turn). Order only; the offered values are unchanged.
    """
    if isinstance(node, dict):
        properties = node.get("properties")
        if isinstance(properties, dict) and "role" in properties and "source_responsibility_refs" in properties:
            first = ("role", "source_responsibility_refs")
            node["properties"] = {**{name: properties[name] for name in first},
                                  **{name: value for name, value in properties.items() if name not in first}}
        for value in node.values():
            _responsibility_refs_first(value)
    elif isinstance(node, list):
        for value in node:
            _responsibility_refs_first(value)


_AFTER_ACTIVITIES = frozenset({
    "disposition", "coverage", "covered_responsibility_refs", "confidence", "unresolved", "reason_summary",
})


def _exact_activity_count_states(states: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The Planner states how many Activities it writes before writing them.

    Without it the decision to write another Activity rode on a fused value-closing
    token such as ``."},`` or ``"]},``, chosen as a way to end a string, after which
    the decoder had to open another Activity and the model copied the previous one
    (live 2026-10-13/14: two or five identical deliveries). With the count first, the
    array has exactly that length, so no closing token can open an extra Activity.
    """
    exact = []
    for state in states:
        properties = state["properties"]
        activities = properties["activities"]
        low = int(activities.get("minItems", 0))
        high = int(activities.get("maxItems", low))
        for count in range(low, high + 1):
            ordered: dict[str, Any] = {}
            for name, value in properties.items():
                if name == "activities":
                    ordered["activity_count"] = {"type": "integer", "enum": [count]}
                    value = {**value, "minItems": count, "maxItems": count}
                ordered[name] = value
            required = list(state.get("required", []))
            refs = list((properties.get("responsibility_decisions") or {}).get("properties", {}))
            if count == 1 and len(refs) > 1 and properties["disposition"].get("enum") == ["execute"]:
                # Every Responsibility was decided work and one Activity realizes them: it
                # serves each of them (live 2026-10-15: one weather read for "will it rain"
                # and "should I take an umbrella" cited the first only; Host rejected it).
                ordered["activities"] = {**ordered["activities"],
                                         "items": _serving_every_responsibility(ordered["activities"]["items"], refs)}
            exact.append({**state, "properties": ordered,
                          "required": required if "activity_count" in required else [*required, "activity_count"]})
    return exact


def _serving_every_responsibility(items: Any, refs: list[str]) -> Any:
    """The same Activity alternatives, each citing exactly every given Responsibility."""
    items = copy.deepcopy(items)
    for branch in items.get("oneOf", [items]) if isinstance(items, dict) else []:
        properties = branch.get("properties") if isinstance(branch, dict) else None
        if isinstance(properties, dict) and "source_responsibility_refs" in properties:
            properties["source_responsibility_refs"] = {
                "type": "array", "prefixItems": [{"type": "string", "const": ref} for ref in refs],
                "items": {"type": "string", "enum": refs}, "minItems": len(refs), "maxItems": len(refs),
            }
    return items


_STATE_DECISION = {"execute": {"work"}, "respond": {"answer", "answer_from_perception"},
                   "clarify": {"clarify"}, "unavailable": {"unavailable"}}


def _restrict_state_decisions(
    properties: dict[str, Any], disposition: str, responsibility_refs: list[str],
) -> bool:
    """A uniform disposition state admits only that decision for every Responsibility.

    The decisions precede the disposition, so the decoder keeps only states their
    choices allow; ``mixed`` needs two Responsibilities. Returns False for a state no
    decision space can reach. Host validation still rejects any remaining mismatch.
    """
    decisions = properties.get("responsibility_decisions")
    per_ref = decisions.get("properties") if isinstance(decisions, dict) else None
    if not isinstance(per_ref, dict):
        return True
    if disposition == "mixed":
        return len(responsibility_refs) > 1
    wanted = _STATE_DECISION.get(disposition)
    for ref, choice in list(per_ref.items()):
        kept = []
        for branch in choice.get("oneOf", [choice]):
            allowed = branch.get("properties", {}).get("decision", {}).get("enum") or []
            if wanted & set(allowed):
                narrowed = copy.deepcopy(branch)
                narrowed["properties"]["decision"] = {
                    "type": "string", "enum": [value for value in allowed if value in wanted]}
                kept.append(narrowed)
        if not kept:
            return False
        per_ref[ref] = kept[0]
    return True


MIXED_DECISION_STATE_MAX_REFS = 2
MIXED_LIMITATION_STATE_MAX_REFS = 3
_ACTIVITY_FREE_DECISIONS = frozenset({"answer_from_perception", "unavailable"})


def _state_decisions(properties: dict[str, Any]) -> set[str]:
    """Every decision a state still offers any Responsibility."""
    per_ref = properties.get("responsibility_decisions", {}).get("properties", {})
    found: set[str] = set()
    for choice in per_ref.values():
        for branch in choice.get("oneOf", [choice]):
            found.update(branch.get("properties", {}).get("decision", {}).get("enum") or [])
    return found


_DECISION_ROLES = {"work": {"capability", "complete_response"}, "answer": {"complete_response"},
                   "answer_from_perception": set(),
                   "clarify": {"clarification"}, "unavailable": set()}


def _mixed_limitation_states(state: dict[str, Any], responsibility_refs: list[str]) -> list[dict[str, Any]]:
    """A mixed decision is made before Activities, which then serve only what it decided.

    With two Responsibilities each state fixes both decisions, and an Activity role is
    offered only for the Responsibility whose decision it realizes; with three, one
    state per set of ``unavailable`` Responsibilities keeps Activities off them. Live
    2026-10-12 (wave + coffee): coffee was decided unavailable, then given a
    clarification, and Host rejected the whole turn. Larger turns keep one mixed state
    and Host keeps the same checks.
    """
    per_ref = state["properties"].get("responsibility_decisions", {}).get("properties", {})
    if len(responsibility_refs) > MIXED_LIMITATION_STATE_MAX_REFS or not per_ref:
        return [state]

    def offered(ref: str) -> dict[str, dict[str, Any]]:
        by_decision: dict[str, dict[str, Any]] = {}
        choice = per_ref[ref]
        for branch in choice.get("oneOf", [choice]):
            for decision in branch.get("properties", {}).get("decision", {}).get("enum") or []:
                narrowed = copy.deepcopy(branch)
                narrowed["properties"]["decision"] = {"type": "string", "enum": [decision]}
                by_decision[decision] = narrowed
        return by_decision

    choices = {ref: offered(ref) for ref in responsibility_refs}
    if len(responsibility_refs) <= MIXED_DECISION_STATE_MAX_REFS:
        assignments = [dict(zip(responsibility_refs, picked))
                       for picked in product(*(list(choices[ref]) for ref in responsibility_refs))
                       if len(set(picked)) > 1]
    else:
        assignments = [{ref: ("unavailable" if ref in limited else None) for ref in responsibility_refs}
                       for size in range(len(responsibility_refs))
                       for limited in combinations(responsibility_refs, size)]

    states = []
    for assignment in assignments:
        decided = {}
        for ref, decision in assignment.items():
            options = ({decision: choices[ref][decision]} if decision in choices[ref] else {}) if decision else {
                key: value for key, value in choices[ref].items() if key != "unavailable"}
            if not options:
                break
            values = list(options.values())
            decided[ref] = values[0] if len(values) == 1 else {"oneOf": values}
        else:
            stage = copy.deepcopy(state)
            stage["properties"]["responsibility_decisions"]["properties"] = decided
            items = stage["properties"]["activities"]["items"]
            kept_items = []
            for item in items.get("oneOf", [items]):
                role = (item.get("properties", {}).get("role", {}).get("enum") or [""])[0]
                refs = item.get("properties", {}).get("source_responsibility_refs", {}).get("items", {})
                allowed = [ref for ref in refs.get("enum", responsibility_refs)
                           if assignment[ref] != "unavailable"
                           and (assignment[ref] is None or role in _DECISION_ROLES[assignment[ref]])]
                if not allowed:
                    continue
                if "enum" in refs:
                    refs["enum"] = allowed
                    item["properties"]["source_responsibility_refs"]["maxItems"] = len(allowed)
                kept_items.append(item)
            if kept_items:
                stage["properties"]["activities"]["items"] = {"oneOf": kept_items}
                states.append(stage)
            elif all(assignment[ref] in _ACTIVITY_FREE_DECISIONS for ref in responsibility_refs):
                stage["properties"]["activities"]["maxItems"] = 0
                stage["properties"]["activities"].pop("minItems", None)
                states.append(stage)
    return states


def need_first_response_schema(schema: dict[str, Any], loaded_capability_ids: list[str]) -> dict[str, Any]:
    """Require ability_needs before Work in the object and in every exposed shape.

    Native decoders follow the exposed oneOf/anyOf shapes, so each shape carries the
    field first. closest_loaded names only Capabilities loaded for this decision.
    """
    needs = {
        "type": "array", "maxItems": ABILITY_NEEDS_MAX,
        "items": {
            "type": "object", "additionalProperties": False,
            "required": ["need", "closest_loaded", "closest_loaded_does", "fits"],
            "properties": {
                "need": {"type": "string", "minLength": 3, "maxLength": 100},
                "closest_loaded": {"type": "string", "enum": [*dict.fromkeys(loaded_capability_ids), ABILITY_NEED_NONE]},
                "closest_loaded_does": {"type": "string", "minLength": 3, "maxLength": 80},
                "fits": {"type": "boolean"},
            },
        },
    }
    result = copy.deepcopy(schema)

    def attach(node: Any, *, root: bool = False) -> None:
        if isinstance(node, list):
            for item in node:
                attach(item)
            return
        if not isinstance(node, dict):
            return
        closed = isinstance(node.get("properties"), dict) and node.get("additionalProperties") is False
        if root or closed:
            node["properties"] = {"ability_needs": copy.deepcopy(needs), **node.get("properties", {})}
            node["required"] = ["ability_needs", *[name for name in node.get("required", []) if name != "ability_needs"]]
        # Exposed Work shapes live only under combinators, never inside property schemas.
        for key in ("oneOf", "anyOf", "allOf", "then", "else"):
            if key in node:
                attach(node[key])

    attach(result, root=True)
    return result



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
    # Keep the primary contract's decoder profile through readiness and the
    # subsequent capability-lookup wrapper. Losing it bypasses native array
    # defaults, shape exposure and bounded JSON formatting on the real call.
    return {**({"title": schema["title"]} if "title" in schema else {}),
            "$defs": definitions, "anyOf": [
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
