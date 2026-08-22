from __future__ import annotations

import copy
from dataclasses import dataclass, field
import json
from decimal import Decimal, InvalidOperation
import re
from typing import Any

from pydantic import ValidationError

try:
    from chromie_contracts.core_interpretation import CognitiveResponsibilityProposal
    from chromie_contracts.interaction import MEDIA_CAPABILITY_IDS, VOCAL_MODES, VOCAL_PERFORMANCE_CAPABILITY_ID
    from chromie_contracts.plan import CanonicalPlan, FastPlannerAdvanceModelOutput, FastPlannerProgressAct, GoalSatisfactionStatus, PlanParameterResolution
except ImportError:  # pragma: no cover
    from shared.chromie_contracts.core_interpretation import CognitiveResponsibilityProposal
    from shared.chromie_contracts.interaction import MEDIA_CAPABILITY_IDS, VOCAL_MODES, VOCAL_PERFORMANCE_CAPABILITY_ID
    from shared.chromie_contracts.plan import CanonicalPlan, FastPlannerAdvanceModelOutput, FastPlannerProgressAct, GoalSatisfactionStatus, PlanParameterResolution

from .capabilities.validator import validate_args_for_schema
from .planner_context import (
    _goal_execution_metadata,
    evidence_bound_dialogue,
    goal_association_prompt_projection,
    goal_cancellation_evidence_reentry_goal_ids,
    planner_effectful_goal_ids,
    planner_goal_execution_requirements,
    planner_provider_media_goal_operations,
    planner_provider_vocal_goal_ids,
    planner_response_goal_ids,
    result_evidence_reentry_goal_ids,
    first_response_phase_decided,
)
from .planner_grounding import (
    _argument_realization_contract,
    _argument_schema_accepts_canonical_binding,
    _goal_binding_map,
    _material_values_equal,
    _normalized_entity_type,
    semantic_numeric_values,
)
from .planner_model_contract import (
    PlannerDTOContractError,
    PlannerModelOutput,
    PlannerTier,
    ResourceResponsibilityCapabilityGroundingError,
    ResourceResponsibilityCapabilityUnavailableError,
    ResourceResponsibilityRequiresCompositionError,
)

_NUMERIC_LITERAL_RE = re.compile(
    r"(?<![A-Za-z0-9_.])[-+]?(?:\d+(?:\.\d+)?|\.\d+)(?![\d.])"
)
_LIST_ENTITY_TYPES = frozenset({"list", "action_list"})
_INFORMATION_TEMPORAL_ENTITY_TYPES = frozenset(
    {
        "day_part", "date", "date_range", "time", "time_frame",
        "time_period", "temporal_period", "temporal_scope",
    }
)

def validate_goal_responsibility_outcomes(
    output: PlannerModelOutput,
    *,
    authoritative_goals: list[dict[str, Any]],
    context: dict[str, Any] | None = None,
) -> None:
    """Keep planner outcomes aligned with typed Goal completion contracts."""

    response_goal_ids = planner_response_goal_ids(authoritative_goals)
    provider_vocal_goal_ids = planner_provider_vocal_goal_ids(authoritative_goals)
    provider_media_goal_operations = planner_provider_media_goal_operations(authoritative_goals)
    speaking_goal_ids = response_goal_ids | provider_vocal_goal_ids
    capability_goal_ids: set[str] = set()
    for goal in authoritative_goals:
        if not isinstance(goal, dict):
            continue
        goal_id = " ".join(str(goal.get("goal_id") or "").strip().split())
        metadata = goal.get("metadata")
        if (
            goal_id
            and isinstance(metadata, dict)
            and metadata.get("responsibility_kind") == "capability_dependent"
        ):
            capability_goal_ids.add(goal_id)
    evidence_goal_ids = {
        source_goal_id
        for item in evidence_bound_dialogue(context)
        for source_goal_id in item.get("source_goal_ids") or []
    }
    evidence_goal_ids.update(result_evidence_reentry_goal_ids(context))
    evidence_goal_ids.update(goal_cancellation_evidence_reentry_goal_ids(context))
    valid_vocal_step_ids: set[str] = set()
    valid_media_step_ids: set[str] = set()
    for goal_id in sorted(response_goal_ids):
        outcome = output.goal_outcomes.get(goal_id)
        if outcome is None:
            raise ValueError(f"vocal_output goal requires an explicit outcome: {goal_id}")
        if outcome.disposition != "respond":
            raise ValueError(
                "vocal_output goal must use disposition=respond and no "
                f"executable step: {goal_id}"
            )
    for goal_id in sorted(provider_vocal_goal_ids):
        outcome = output.goal_outcomes.get(goal_id)
        if outcome is None:
            raise ValueError(
                f"provider-required vocal goal requires an explicit outcome: {goal_id}"
            )
        if outcome.disposition == "respond":
            raise ValueError(
                "provider-required vocal goal cannot be completed by response_text, "
                "ordinary TTS, media playback, or a body step: "
                f"{goal_id}"
            )
        owned_steps = [step for step in output.steps if goal_id in step.source_goal_ids]
        if outcome.disposition == "execute":
            expected_mode = next(
                (
                    _goal_execution_metadata(goal)[1]
                    for goal in authoritative_goals
                    if str(goal.get("goal_id") or "").strip() == goal_id
                ),
                "",
            )
            if len(owned_steps) != 1:
                raise ValueError(
                    "provider-required vocal execute outcome requires exactly one "
                    f"owned {VOCAL_PERFORMANCE_CAPABILITY_ID} step: {goal_id}"
                )
            step = owned_steps[0]
            if step.capability_id != VOCAL_PERFORMANCE_CAPABILITY_ID:
                raise ValueError(
                    "provider-required vocal goal requires exact capability_id "
                    f"{VOCAL_PERFORMANCE_CAPABILITY_ID}: {goal_id}"
                )
            if str(step.args.get("mode") or "").strip() != expected_mode:
                raise ValueError(
                    "vocal capability mode must exactly match authoritative Goal "
                    f"output_mode={expected_mode!r}: {goal_id}"
                )
            if not str(step.args.get("text") or "").strip():
                raise ValueError(
                    f"vocal capability request requires authored text/content: {goal_id}"
                )
            valid_vocal_step_ids.add(step.step_id)
        elif owned_steps:
            raise ValueError(
                f"non-executing provider-required vocal outcome cannot own plan steps: {goal_id}"
            )
    for goal_id, operation in sorted(provider_media_goal_operations.items()):
        outcome = output.goal_outcomes.get(goal_id)
        if outcome is None:
            raise ValueError(
                f"provider-required media Goal requires an explicit outcome: {goal_id}"
            )
        if outcome.disposition == "respond":
            raise ValueError(
                "media playback Goal cannot be completed by response text, ordinary "
                f"TTS, or vocal performance: {goal_id}"
            )
        owned_steps = [step for step in output.steps if goal_id in step.source_goal_ids]
        if outcome.disposition == "execute":
            expected_capability = MEDIA_CAPABILITY_IDS[operation]
            if len(owned_steps) != 1:
                raise ValueError(
                    "provider-required media execute outcome requires exactly one "
                    f"owned {expected_capability} step: {goal_id}"
                )
            step = owned_steps[0]
            if step.capability_id != expected_capability:
                raise ValueError(
                    "provider-required media Goal requires exact capability_id "
                    f"{expected_capability}: {goal_id}"
                )
            valid_media_step_ids.add(step.step_id)
        elif owned_steps:
            raise ValueError(
                f"non-executing provider-required media outcome cannot own plan steps: {goal_id}"
            )
    invalid_steps = [
        step.step_id
        for step in output.steps
        if speaking_goal_ids.intersection(step.source_goal_ids)
        and step.step_id not in valid_vocal_step_ids
    ]
    if invalid_steps:
        raise ValueError(
            "Vocal goals can own only an exact qualified vocal Capability step: "
            + ",".join(invalid_steps)
        )
    invalid_media_steps = [
        step.step_id
        for step in output.steps
        if set(provider_media_goal_operations).intersection(step.source_goal_ids)
        and step.step_id not in valid_media_step_ids
    ]
    if invalid_media_steps:
        raise ValueError(
            "Media playback Goals can own only their exact chromie.media.* "
            "Capability step: " + ",".join(invalid_media_steps)
        )
    for goal_id in sorted(capability_goal_ids):
        outcome = output.goal_outcomes.get(goal_id)
        responds_without_capability = (
            outcome is not None and outcome.disposition == "respond"
        ) or (
            len(authoritative_goals) == 1
            and not output.goal_outcomes
            and output.disposition == "respond"
        )
        if responds_without_capability and goal_id not in evidence_goal_ids:
            raise ValueError(
                "capability_dependent goal cannot use disposition=respond "
                "without capability or delivered evidence-bound dialogue: " + goal_id
            )
    # Keep this broad invariant last so narrower responsibility contracts retain
    # their more actionable diagnostics.  It contains every remaining typed
    # effectful Goal without inferring effect from user wording.
    terminal_block_dispositions = {
        "clarify",
        "escalate",
        "unavailable",
        "refused",
    }
    for goal_id in sorted(planner_effectful_goal_ids(authoritative_goals)):
        outcome = output.goal_outcomes.get(goal_id)
        disposition = outcome.disposition if outcome is not None else output.disposition
        owned_steps = [step for step in output.steps if goal_id in step.source_goal_ids]
        if disposition == "execute" and owned_steps:
            continue
        if disposition in terminal_block_dispositions:
            continue
        if disposition == "respond" and goal_id in evidence_goal_ids:
            continue
        raise ValueError(
            "unresolved effectful goal requires an executable step or explicit "
            "clarify/escalate/unavailable/refused evidence: " + goal_id
        )

def qualify_capability_catalog_for_output_modes(
    capabilities: list[dict[str, Any]],
    *,
    authoritative_goals: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Remove capabilities whose typed lane cannot serve any current Goal.

    Goal Association already owns each Goal's provider-neutral output mode. The
    catalog owns executable typed semantic-scope and effect metadata. Intersecting
    those declarations prevents an information tool from becoming decorative body work,
    or a body action from standing in for an exact vocal/media provider, without
    inferring intent from user phrases or capability names.
    """

    output_modes = {
        " ".join(
            str((goal.get("metadata") or {}).get("output_mode") or "")
            .strip()
            .split()
        )
        for goal in authoritative_goals
        if isinstance(goal, dict) and isinstance(goal.get("metadata"), dict)
    }
    output_modes.discard("")
    if not output_modes or "other" in output_modes:
        return list(capabilities)

    has_body = "body_action" in output_modes
    has_information = "capability_work" in output_modes
    has_media = "media_playback" in output_modes
    has_provider_vocal = bool(
        output_modes.intersection(set(VOCAL_MODES) - {"speech"})
    )
    qualified: list[dict[str, Any]] = []
    for capability in capabilities:
        if not isinstance(capability, dict):
            continue
        capability_id = " ".join(
            str(capability.get("capability_id") or "").strip().split()
        )
        effects = {
            " ".join(str(item or "").strip().split()).casefold()
            for item in capability.get("effects") or []
            if str(item or "").strip()
        }
        hints = capability.get("hints")
        hints = hints if isinstance(hints, dict) else {}
        scope = capability.get("semantic_scope")
        if not isinstance(scope, dict) or not scope:
            scope = hints.get("semantic_scope")
        scope = scope if isinstance(scope, dict) else {}
        responsibility_type = " ".join(
            str(scope.get("responsibility_type") or "").strip().split()
        )
        resource_kinds = {
            " ".join(str(item or "").strip().split())
            for item in scope.get("resource_kinds") or []
        }
        is_information = (
            responsibility_type == "acquire_and_deliver_resource"
            and "information" in resource_kinds
        )
        is_body = bool(
            effects.intersection(
                {
                    "physical_motion",
                    "visual_expression",
                    "object_manipulation",
                    "resource_delivery",
                    "body_activity_execution",
                    "embodied_task_request",
                }
            )
        ) or (
            responsibility_type == "acquire_and_deliver_resource"
            and "physical_object" in resource_kinds
        )
        is_vocal = capability_id == VOCAL_PERFORMANCE_CAPABILITY_ID
        is_media = capability_id in set(MEDIA_CAPABILITY_IDS.values())
        if is_vocal:
            if has_provider_vocal:
                qualified.append(capability)
            continue
        if is_media:
            if has_media:
                qualified.append(capability)
            continue
        if is_information:
            if has_information:
                qualified.append(capability)
            continue
        if is_body:
            if has_body:
                qualified.append(capability)
            continue
        # Untyped capabilities are not made semantically applicable by their
        # transport/provider shape. Providers must declare the semantic scope or
        # effect that makes the capability relevant to the Goal.
    return qualified

def qualify_capability_catalog_for_information_domains(
    capabilities: list[dict[str, Any]],
    *,
    authoritative_goals: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Remove explicitly wrong-domain information providers before planning.

    Goal Association has already authored the information domain. A Capability
    that explicitly declares a different domain is therefore inapplicable, not
    an alternative for the Planner to consider. Capabilities without a declared
    domain remain visible because another typed contract or the Planner may still
    establish their applicability. With multiple information Goals, a Capability
    is retained when its domain matches at least one of them; per-Goal ownership
    remains subject to the normal resource-grounding validator.
    """

    required_domains: set[str] = set()
    for goal in authoritative_goals:
        if not isinstance(goal, dict):
            continue
        responsibility = goal.get("resource_responsibility")
        responsibility = responsibility if isinstance(responsibility, dict) else {}
        resource = responsibility.get("resource")
        resource = resource if isinstance(resource, dict) else {}
        if " ".join(str(resource.get("kind") or "").strip().split()) != "information":
            continue
        attributes = resource.get("attributes")
        attributes = attributes if isinstance(attributes, dict) else {}
        domain = attributes.get("information_domain")
        domain = domain if isinstance(domain, dict) else {}
        value = " ".join(str(domain.get("value") or "").strip().split())
        if value:
            required_domains.add(value)

    if not required_domains:
        return list(capabilities)

    qualified: list[dict[str, Any]] = []
    for capability in capabilities:
        if not isinstance(capability, dict):
            continue
        hints = capability.get("hints")
        metadata = capability.get("metadata")
        hints = hints if isinstance(hints, dict) else {}
        metadata = metadata if isinstance(metadata, dict) else {}
        scope = capability.get("semantic_scope")
        if not isinstance(scope, dict) or not scope:
            scope = hints.get("semantic_scope")
        if not isinstance(scope, dict) or not scope:
            scope = metadata.get("semantic_scope")
        scope = scope if isinstance(scope, dict) else {}
        domain = " ".join(str(scope.get("domain") or "").strip().split())
        if domain and domain not in required_domains:
            continue
        qualified.append(capability)
    return qualified

def information_goal_ids_without_declared_provider(
    capabilities: list[dict[str, Any]],
    *,
    authoritative_goals: list[dict[str, Any]],
) -> set[str]:
    """Return typed information Goals with no matching declared provider.

    This is a contract lookup, not semantic intent inference: the information
    domain, responsibility type, and resource kind were already authored by Goal
    Association, and provider applicability comes only from Capability metadata.
    """

    declared_scopes: list[dict[str, Any]] = []
    for capability in capabilities:
        if not isinstance(capability, dict):
            continue
        hints = capability.get("hints")
        metadata = capability.get("metadata")
        hints = hints if isinstance(hints, dict) else {}
        metadata = metadata if isinstance(metadata, dict) else {}
        scope = capability.get("semantic_scope")
        if not isinstance(scope, dict) or not scope:
            scope = hints.get("semantic_scope")
        if not isinstance(scope, dict) or not scope:
            scope = metadata.get("semantic_scope")
        if isinstance(scope, dict) and scope:
            declared_scopes.append(scope)

    unavailable: set[str] = set()
    for goal in authoritative_goals:
        if not isinstance(goal, dict):
            continue
        goal_id = " ".join(str(goal.get("goal_id") or "").strip().split())
        responsibility = goal.get("resource_responsibility")
        responsibility = responsibility if isinstance(responsibility, dict) else {}
        resource = responsibility.get("resource")
        resource = resource if isinstance(resource, dict) else {}
        kind = " ".join(str(resource.get("kind") or "").strip().split())
        attributes = resource.get("attributes")
        attributes = attributes if isinstance(attributes, dict) else {}
        binding = attributes.get("information_domain")
        binding = binding if isinstance(binding, dict) else {}
        domain = " ".join(str(binding.get("value") or "").strip().split())
        responsibility_type = " ".join(
            str(responsibility.get("responsibility_type") or "").strip().split()
        )
        if not goal_id or kind != "information" or not domain:
            continue
        matching_provider = any(
            " ".join(str(scope.get("domain") or "").strip().split()) == domain
            and " ".join(
                str(scope.get("responsibility_type") or "").strip().split()
            )
            == responsibility_type
            and kind
            in {
                " ".join(str(value or "").strip().split())
                for value in (
                    scope.get("resource_kinds")
                    if isinstance(scope.get("resource_kinds"), list)
                    else []
                )
            }
            for scope in declared_scopes
        )
        if not matching_provider:
            unavailable.add(goal_id)
    return unavailable

def validate_resource_responsibility_capability_grounding(
    output: PlannerModelOutput,
    *,
    authoritative_goals: list[dict[str, Any]],
    capabilities: list[dict[str, Any]],
) -> None:
    """Validate resource Goals against the current plan-level capability boundary.

    Goal Association owns the provider-neutral responsibility. The Planner owns
    selection and composition across the *advertised* catalog. Providers own any
    decomposition hidden inside one selected capability. This validator makes no
    semantic choices; it mechanically verifies that selected capability contracts
    form an ordered resource-state chain and that their combined promises cover
    the already-authored Goal.

    ``resource_contract.plan_requires`` and ``plan_provides`` are public
    planning facts. ``completion_requires`` remains provider-result evidence
    for the exact Capability. Every maintained provider must declare its public
    plan coverage explicitly; Planner does not infer missing provider contracts.
    """

    capability_by_id = {
        " ".join(str(item.get("capability_id") or "").strip().split()): item
        for item in capabilities
        if isinstance(item, dict)
        and " ".join(str(item.get("capability_id") or "").strip().split())
    }

    def normalized_values(value: Any) -> set[str]:
        values = value if isinstance(value, list) else []
        return {
            " ".join(str(item or "").strip().split())
            for item in values
            if " ".join(str(item or "").strip().split())
        }

    def capability_contract(candidate: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        hints = candidate.get("hints")
        metadata = candidate.get("metadata")
        hints = hints if isinstance(hints, dict) else {}
        metadata = metadata if isinstance(metadata, dict) else {}
        scope = hints.get("semantic_scope")
        if not isinstance(scope, dict) or not scope:
            scope = metadata.get("semantic_scope")
        contract = hints.get("resource_contract")
        if not isinstance(contract, dict) or not contract:
            contract = metadata.get("resource_contract")
        return (scope if isinstance(scope, dict) else {}, contract if isinstance(contract, dict) else {})

    def contract_projection(
        candidate: dict[str, Any],
        *,
        expected_type: str,
        expected_kind: str,
        expected_delivery: str,
        expected_information_domain: str,
    ) -> tuple[list[str], set[str], set[str], set[str], str]:
        scope, contract = capability_contract(candidate)
        errors: list[str] = []
        if not contract:
            errors.append("missing resource_contract")
        if scope.get("responsibility_type") != expected_type:
            errors.append(
                "semantic_scope.responsibility_type does not match "
                f"{expected_type!r}"
            )
        kinds = normalized_values(scope.get("resource_kinds"))
        if expected_kind not in kinds:
            errors.append(
                "semantic_scope.resource_kinds does not include "
                f"{expected_kind!r}"
            )
        capability_domain = " ".join(
            str(scope.get("domain") or "").strip().split()
        )
        if (
            expected_kind == "information"
            and expected_information_domain
            and capability_domain
            and capability_domain != expected_information_domain
        ):
            errors.append(
                "semantic_scope.domain does not match canonical information domain "
                f"{expected_information_domain!r}"
            )
        raw_delivery_modes = scope.get("delivery_modes")
        delivery_modes = {
            " ".join(str(value or "").strip().split())
            for value in (
                raw_delivery_modes
                if isinstance(raw_delivery_modes, list)
                else [scope.get("delivery")]
            )
            if " ".join(str(value or "").strip().split())
        }
        requires = normalized_values(contract.get("plan_requires"))
        provides = normalized_values(contract.get("plan_provides"))
        completion_requires = normalized_values(contract.get("completion_requires"))
        if not provides and completion_requires:
            # Existing complete providers already express the states their own
            # successful result must prove. Those states are also valid public
            # plan coverage when no explicit plan_provides exists.
            provides = set(completion_requires)
        final_delivery_owner = " ".join(
            str(contract.get("final_delivery_owner") or "").strip().split()
        )
        if "resource_delivered" in provides and expected_delivery not in delivery_modes:
            errors.append(
                "capability providing resource_delivered must declare "
                f"delivery mode {expected_delivery!r}"
            )
        if (
            final_delivery_owner == "planner_communicative_activity"
            and expected_delivery not in delivery_modes
        ):
            errors.append(
                "Planner-delivery Capability must declare "
                f"delivery mode {expected_delivery!r}"
            )
        if not provides and final_delivery_owner != "planner_communicative_activity":
            errors.append("resource_contract.plan_provides is empty")
        return errors, requires, provides, delivery_modes, final_delivery_owner

    for goal in authoritative_goals:
        if not isinstance(goal, dict):
            continue
        goal_id = " ".join(str(goal.get("goal_id") or "").strip().split())
        responsibility = goal.get("resource_responsibility")
        if not goal_id or not isinstance(responsibility, dict) or not responsibility:
            continue

        owned_steps = [step for step in output.steps if goal_id in step.source_goal_ids]
        if not owned_steps:
            continue

        resource = responsibility.get("resource")
        resource = resource if isinstance(resource, dict) else {}
        responsibility_args = {
            name: responsibility.get(name)
            for name in ("resource", "source", "recipient")
            if isinstance(responsibility.get(name), dict)
        }
        expected_type = " ".join(
            str(responsibility.get("responsibility_type") or "").strip().split()
        )
        expected_kind = " ".join(str(resource.get("kind") or "").strip().split())
        resource_attributes = resource.get("attributes")
        resource_attributes = (
            resource_attributes if isinstance(resource_attributes, dict) else {}
        )
        domain_binding = resource_attributes.get("information_domain")
        domain_binding = domain_binding if isinstance(domain_binding, dict) else {}
        expected_information_domain = " ".join(
            str(domain_binding.get("value") or "").strip().split()
        )
        expected_delivery = " ".join(
            str(responsibility.get("delivery_mode") or "").strip().split()
        )
        required_terminal_states = {"resource_acquired"}
        if expected_kind == "physical_object":
            required_terminal_states.add("resource_delivered")

        def catalog_coverage(
            initial_state: set[str],
        ) -> tuple[set[str], bool, list[str], list[str]]:
            """Return reachable resource state from currently advertised contracts."""

            reachable = set(initial_state)
            response_delivery = False
            projections: list[tuple[str, set[str], set[str], str]] = []
            complete_capability_ids: list[str] = []
            for capability_id, candidate in capability_by_id.items():
                errors, requires, provides, _modes, final_delivery_owner = (
                    contract_projection(
                        candidate,
                        expected_type=expected_type,
                        expected_kind=expected_kind,
                        expected_delivery=expected_delivery,
                        expected_information_domain=expected_information_domain,
                    )
                )
                if errors:
                    continue
                projections.append(
                    (capability_id, requires, provides, final_delivery_owner)
                )
                individually_complete = (
                    not requires
                    and required_terminal_states <= provides
                    and (
                        expected_kind == "physical_object"
                        or "resource_delivered" in provides
                        or final_delivery_owner == "planner_communicative_activity"
                    )
                )
                if individually_complete:
                    complete_capability_ids.append(capability_id)

            used: list[str] = []
            remaining = list(projections)
            while remaining:
                progressed = False
                next_remaining: list[tuple[str, set[str], set[str], str]] = []
                for capability_id, requires, provides, final_delivery_owner in remaining:
                    if not requires <= reachable:
                        next_remaining.append(
                            (capability_id, requires, provides, final_delivery_owner)
                        )
                        continue
                    reachable.update(provides)
                    response_delivery = response_delivery or (
                        final_delivery_owner == "planner_communicative_activity"
                    )
                    used.append(capability_id)
                    progressed = True
                if not progressed:
                    break
                remaining = next_remaining
            return (
                reachable,
                response_delivery,
                sorted(set(used)),
                sorted(set(complete_capability_ids)),
            )

        def coverage_complete(state: set[str], response_delivery: bool) -> bool:
            if not required_terminal_states <= state:
                return False
            if expected_kind == "physical_object":
                return True
            return "resource_delivered" in state or response_delivery

        resource_state: set[str] = set()
        response_layer_delivery = False
        selected_ids: list[str] = []

        for step in owned_steps:
            capability = capability_by_id.get(step.capability_id)
            if capability is None:
                raise ValueError(
                    "resource responsibility step uses a Capability absent from the "
                    f"authoritative catalog: goal_id={goal_id}, "
                    f"capability_id={step.capability_id}"
                )
            errors, requires, provides, _delivery_modes, final_delivery_owner = (
                contract_projection(
                    capability,
                    expected_type=expected_type,
                    expected_kind=expected_kind,
                    expected_delivery=expected_delivery,
                    expected_information_domain=expected_information_domain,
                )
            )
            if errors:
                reachable, response_delivery, composition_ids, complete_ids = (
                    catalog_coverage(set())
                )
                message = (
                    "resource responsibility Capability contract mismatch: "
                    f"goal_id={goal_id}, capability_id={step.capability_id}: "
                    + "; ".join(errors)
                )
                if complete_ids:
                    raise ResourceResponsibilityCapabilityGroundingError(
                        message
                        + "; complete_capability_ids="
                        + ",".join(complete_ids),
                        goal_id=goal_id,
                        complete_capability_ids=complete_ids,
                    )
                if coverage_complete(reachable, response_delivery):
                    raise ResourceResponsibilityRequiresCompositionError(
                        message
                        + "; composable_capability_ids="
                        + ",".join(composition_ids)
                    )
                raise ResourceResponsibilityCapabilityUnavailableError(
                    message
                    + "; no supplied Capability set declares the required contract"
                )
            for argument_name, expected_value in responsibility_args.items():
                if argument_name not in step.args:
                    continue
                if not _material_values_equal(
                    step.args[argument_name],
                    expected_value,
                    list_compatible=False,
                ):
                    raise ResourceResponsibilityCapabilityGroundingError(
                        "resource responsibility step argument contradicts the "
                        "canonical Goal responsibility: "
                        f"goal_id={goal_id}, capability_id={step.capability_id}, "
                        f"argument={argument_name!r}",
                        goal_id=goal_id,
                        complete_capability_ids=(
                            [step.capability_id]
                            if len(owned_steps) == 1
                            and not requires
                            and required_terminal_states <= provides
                            and (
                                expected_kind == "physical_object"
                                or "resource_delivered" in provides
                                or final_delivery_owner
                                == "planner_communicative_activity"
                            )
                            else []
                        ),
                    )
            missing_preconditions = sorted(requires - resource_state)
            if missing_preconditions:
                raise ResourceResponsibilityCapabilityGroundingError(
                    "resource responsibility capability chain has unsatisfied "
                    f"plan_requires for goal_id={goal_id}, "
                    f"capability_id={step.capability_id}: "
                    + ",".join(missing_preconditions)
                )
            if requires and step.timing == "parallel":
                raise ResourceResponsibilityCapabilityGroundingError(
                    "resource responsibility capability with plan_requires must be "
                    f"sequential: goal_id={goal_id}, capability_id={step.capability_id}"
                )
            resource_state.update(provides)
            response_layer_delivery = response_layer_delivery or (
                final_delivery_owner == "planner_communicative_activity"
            )
            selected_ids.append(step.capability_id)

        missing_terminal_states = sorted(required_terminal_states - resource_state)
        delivery_missing = (
            expected_kind != "physical_object"
            and "resource_delivered" not in resource_state
            and not response_layer_delivery
        )
        if not missing_terminal_states and not delivery_missing:
            continue

        reachable, response_delivery, composition_ids, complete_ids = catalog_coverage(
            resource_state
        )

        details = [*missing_terminal_states]
        if delivery_missing:
            details.append("user_delivery")
        message = (
            "resource responsibility plan does not cover the complete Goal: "
            f"goal_id={goal_id}, selected_capability_ids={','.join(selected_ids)}, "
            f"missing={','.join(details)}"
        )
        if complete_ids:
            raise ResourceResponsibilityCapabilityGroundingError(
                message
                + "; complete_capability_ids="
                + ",".join(complete_ids),
                goal_id=goal_id,
                complete_capability_ids=complete_ids,
            )
        if coverage_complete(reachable, response_delivery):
            additional_ids = [
                capability_id
                for capability_id in composition_ids
                if capability_id not in selected_ids
            ]
            raise ResourceResponsibilityRequiresCompositionError(
                message
                + "; additional_capability_ids="
                + ",".join(additional_ids)
            )
        raise ResourceResponsibilityCapabilityUnavailableError(
            message + "; no supplied Capability set declares the missing resource coverage"
        )

def coordinated_action_goal_ids(
    authoritative_goals: list[dict[str, Any]],
) -> set[str]:
    """Return model-authored provider Goals requiring semantic coverage audit.

    Goal Association, rather than the Host, declares ``responsibility_kind`` and
    authors any ``action_list`` binding or sibling Goal split. The Host uses only
    those typed facts to require an independent model completeness audit; it does
    not infer actions, parse user wording, or select Capabilities. Auditing every
    executable-action and capability-dependent Goal prevents a generic movement
    step from being accepted as object handling and prevents a domain-specific
    read Capability from being broadened into unrelated external retrieval.
    """

    goal_ids: set[str] = set()
    source_groups: dict[str, set[str]] = {}
    for goal in authoritative_goals:
        if not isinstance(goal, dict):
            continue
        goal_id = " ".join(str(goal.get("goal_id") or "").strip().split())
        if not goal_id:
            continue
        source_text = " ".join(str(goal.get("source_text") or "").strip().split())
        if source_text:
            source_groups.setdefault(source_text, set()).add(goal_id)
        metadata = goal.get("metadata")
        if isinstance(metadata, dict) and str(
            metadata.get("responsibility_kind") or ""
        ).strip() in {"executable_action", "capability_dependent"}:
            goal_ids.add(goal_id)
        resource_responsibility = goal.get("resource_responsibility")
        if isinstance(resource_responsibility, dict) and resource_responsibility:
            goal_ids.add(goal_id)
        goal_object = goal.get("object")
        if not isinstance(goal_object, dict):
            continue
        bindings = goal_object.get("bindings")
        if not isinstance(bindings, dict):
            continue
        if any(
            isinstance(binding, dict)
            and "_".join(
                str(binding.get("entity_type") or "").strip().casefold().replace("-", "_").split()
            )
            == "action_list"
            for binding in bindings.values()
        ):
            goal_ids.add(goal_id)
    for grouped_ids in source_groups.values():
        # Three or more independently observable responsibilities from one
        # model-segmented utterance cross the bounded-complexity threshold even
        # when no one Goal owns an action_list binding. Two ordinary sibling
        # Goals remain on the normal per-goal contract path.
        if len(grouped_ids) >= 3:
            goal_ids.update(grouped_ids)
    return goal_ids

def parallel_plan_contract_errors(
    plan: CanonicalPlan,
    capabilities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Validate declared capability/resource evidence for parallel Plan steps.

    This validator never chooses timing. It only rejects model-authored parallel
    timing when the supplied provider catalog does not affirm that timing or
    when declared exclusive/resource claims conflict. The planner may then
    author an explicit safe adjustment, alternative, or clarification.
    """

    by_id = {
        str(item.get("capability_id") or ""): item
        for item in capabilities
        if str(item.get("capability_id") or "").strip()
    }
    parallel_steps = [step for step in plan.steps if step.timing == "parallel"]
    errors: list[dict[str, Any]] = []
    usable: list[tuple[Any, dict[str, Any]]] = []
    for step in parallel_steps:
        capability = by_id.get(step.capability_id)
        if capability is None:
            continue
        if (
            capability.get("parallel_metadata_declared") is not True
            or capability.get("can_run_parallel") is not True
        ):
            errors.append(
                {
                    "type": "parallel_capability_not_declared_safe",
                    "step_id": step.step_id,
                    "capability_id": step.capability_id,
                    "parallel_step_count": len(parallel_steps),
                    "parallel_metadata_declared": capability.get("parallel_metadata_declared"),
                    "can_run_parallel": capability.get("can_run_parallel"),
                }
            )
            continue
        usable.append((step, capability))

    for index, (left_step, left) in enumerate(usable):
        left_group = str(left.get("exclusive_group") or "").strip()
        left_resources = {
            str(item).strip() for item in left.get("resource_claims") or [] if str(item).strip()
        }
        for right_step, right in usable[index + 1 :]:
            right_group = str(right.get("exclusive_group") or "").strip()
            if left_group and left_group == right_group:
                errors.append(
                    {
                        "type": "parallel_exclusive_group_conflict",
                        "step_ids": [left_step.step_id, right_step.step_id],
                        "exclusive_group": left_group,
                    }
                )
            right_resources = {
                str(item).strip()
                for item in right.get("resource_claims") or []
                if str(item).strip()
            }
            conflicts = sorted(left_resources.intersection(right_resources))
            if conflicts:
                errors.append(
                    {
                        "type": "parallel_resource_claim_conflict",
                        "step_ids": [left_step.step_id, right_step.step_id],
                        "resource_claims": conflicts,
                    }
                )
    return errors

def retained_evidence_response_review_required(
    context: dict[str, Any] | None,
    plan: CanonicalPlan,
) -> bool:
    """Identify typed retained-Goal responses that need semantic turn review.

    Goal Association, not Host wording rules, decides whether the latest turn
    continues or otherwise refers to an existing Goal. The review is required
    only when trusted delivered evidence is also available and the terminal
    Plan proposes a conversational response with no executable effects.
    """

    if plan.disposition != "respond" or plan.steps:
        return False
    responding_goal_ids = {
        item.goal_id for item in plan.goal_outcomes if item.disposition == "respond"
    } or set(plan.goal_ids)
    if not responding_goal_ids or not evidence_bound_dialogue(context):
        return False
    association = goal_association_prompt_projection(context)
    return any(
        isinstance(item, dict)
        and str(item.get("relationship") or "").strip() != "new"
        and responding_goal_ids.intersection(
            str(goal_id).strip()
            for goal_id in item.get("target_goal_ids") or []
            if str(goal_id).strip()
        )
        for item in association.get("associations") or []
    )

def validate_goal_binding_argument_grounding(
    output: PlannerModelOutput,
    *,
    authoritative_goals: list[dict[str, Any]],
    capabilities: list[dict[str, Any]] | None = None,
) -> None:
    """Keep executable arguments aligned with Goal Association bindings.

    Goal Association remains the LLM semantic authority that resolves references
    and binds entities.  This validator does not infer what ``那边`` means and it
    contains no location, weather, or phrase rules.  It only rejects a Planner
    step when an argument with the same semantic binding name contradicts the
    immutable Goal value that the step claims to satisfy.

    Verified-memory retrieval is additionally required to carry every material
    binding in ``material_args``.  This prevents a generic "latest result" lookup
    from crossing task or discourse scopes after the Goal has been resolved.
    """

    if output.disposition not in {"execute", "mixed"}:
        return

    capabilities_by_id = {
        str(item.get("capability_id") or ""): item
        for item in (capabilities or [])
        if isinstance(item, dict) and str(item.get("capability_id") or "")
    }
    resolutions_by_step_parameter = {
        (resolution.step_id, resolution.parameter): resolution
        for resolution in output.parameter_resolutions
        if not resolution.blocking
    }

    bindings_by_goal: dict[str, dict[str, dict[str, Any]]] = {}
    information_goal_ids: set[str] = set()
    for goal in authoritative_goals:
        if not isinstance(goal, dict):
            continue
        goal_id = " ".join(str(goal.get("goal_id") or "").strip().split())
        if goal_id:
            bindings_by_goal[goal_id] = _goal_binding_map(goal)
            responsibility = goal.get("resource_responsibility")
            resource = (
                responsibility.get("resource")
                if isinstance(responsibility, dict)
                else None
            )
            if isinstance(resource, dict) and resource.get("kind") == "information":
                information_goal_ids.add(goal_id)

    def nested_values(value: Any) -> list[Any]:
        if isinstance(value, dict):
            return [item for child in value.values() for item in nested_values(child)]
        if isinstance(value, list):
            return [item for child in value for item in nested_values(child)]
        return [value]

    for step in output.steps:
        claimed_goal_ids = [
            goal_id for goal_id in step.source_goal_ids if goal_id in bindings_by_goal
        ]
        if not claimed_goal_ids:
            continue

        required: dict[str, dict[str, Any]] = {}
        for goal_id in claimed_goal_ids:
            for name, binding in bindings_by_goal[goal_id].items():
                if name in required and not _material_values_equal(
                    required[name]["value"],
                    binding["value"],
                    list_compatible=(
                        required[name]["entity_type"] in _LIST_ENTITY_TYPES
                        or binding["entity_type"] in _LIST_ENTITY_TYPES
                    ),
                ):
                    raise ValueError(
                        "one executable step cannot satisfy conflicting authoritative "
                        f"Goal bindings for {name!r}"
                    )
                required[name] = binding

        for name, binding in required.items():
            capability = capabilities_by_id.get(step.capability_id) or {}
            input_schema = capability.get("input_schema")
            argument_schema = (
                (input_schema.get("properties") or {}).get(name)
                if isinstance(input_schema, dict)
                else None
            )
            if name not in step.args:
                if isinstance(argument_schema, dict) and (
                    _argument_schema_accepts_canonical_binding(
                        argument_schema,
                        binding["value"],
                    )
                ):
                    raise PlannerDTOContractError(
                        "planner step omitted same-name authoritative Goal binding: "
                        f"{step.step_id}.{name}={binding['value']!r}"
                    )
                continue
            actual = step.args[name]
            expected = binding["value"]
            if not _material_values_equal(
                actual,
                expected,
                list_compatible=(binding["entity_type"] in _LIST_ENTITY_TYPES),
            ):
                raise ValueError(
                    "planner step argument contradicts authoritative Goal binding: "
                    f"{step.step_id}.{name}={actual!r}, expected={expected!r}"
                )

        capability = capabilities_by_id.get(step.capability_id) or {}
        input_schema = capability.get("input_schema")
        argument_properties = (
            input_schema.get("properties")
            if isinstance(input_schema, dict)
            else None
        )
        if isinstance(argument_properties, dict):
            values_by_entity_type: dict[str, list[Any]] = {}
            for binding in required.values():
                entity_type = _normalized_entity_type(binding.get("entity_type"))
                value = binding.get("value")
                if entity_type and not any(
                    _material_values_equal(
                        existing,
                        value,
                        list_compatible=False,
                    )
                    for existing in values_by_entity_type.setdefault(
                        entity_type, []
                    )
                ):
                    values_by_entity_type[entity_type].append(value)
            for argument_name, argument_schema in argument_properties.items():
                if not isinstance(argument_schema, dict):
                    continue
                entity_type = _normalized_entity_type(
                    argument_schema.get("x-chromie-entity-type")
                )
                if not entity_type:
                    continue
                values = values_by_entity_type.get(entity_type, [])
                if len(values) > 1:
                    raise ValueError(
                        "one executable step cannot satisfy conflicting authoritative "
                        f"Goal entity type {entity_type!r}"
                    )
                if len(values) == 1:
                    if argument_name not in step.args:
                        raise PlannerDTOContractError(
                            "planner step omitted authoritative typed Goal binding: "
                            f"{step.step_id}.{argument_name}={values[0]!r} "
                            f"for entity_type={entity_type!r}"
                        )
                    if not _material_values_equal(
                        step.args[argument_name],
                        values[0],
                        list_compatible=False,
                    ):
                        raise ValueError(
                            "planner step argument contradicts authoritative typed Goal "
                            f"binding: {step.step_id}.{argument_name}="
                            f"{step.args[argument_name]!r}, expected={values[0]!r} "
                            f"for entity_type={entity_type!r}"
                        )
                elif (
                    argument_name in step.args
                    and "default" in argument_schema
                    and not _material_values_equal(
                        step.args[argument_name],
                        argument_schema["default"],
                        list_compatible=False,
                    )
                ):
                    raise ValueError(
                        "planner step invented unsupported semantic scope instead of "
                        "the Capability default: "
                        f"{step.step_id}.{argument_name}="
                        f"{step.args[argument_name]!r}, default="
                        f"{argument_schema['default']!r}, "
                        f"entity_type={entity_type!r}"
                    )

        argument_values = nested_values(step.args)
        for goal_id in claimed_goal_ids:
            if goal_id not in information_goal_ids:
                continue
            for name, binding in bindings_by_goal[goal_id].items():
                if binding["entity_type"] not in _INFORMATION_TEMPORAL_ENTITY_TYPES:
                    continue
                expected = binding["value"]
                if any(
                    _material_values_equal(actual, expected, list_compatible=False)
                    for actual in argument_values
                ):
                    continue
                capability = capabilities_by_id.get(step.capability_id) or {}
                realization = _argument_realization_contract(
                    capability, binding["entity_type"]
                )
                if realization is not None:
                    declared_arguments = [
                        str(name)
                        for name in realization.get("arguments") or []
                        if str(name)
                    ]
                    minimum_arguments = max(
                        1, int(realization.get("minimum_arguments") or 1)
                    )
                    realized_arguments = [
                        name for name in declared_arguments if name in step.args
                    ]
                    if len(realized_arguments) < minimum_arguments:
                        raise PlannerDTOContractError(
                            "planner step did not realize authoritative semantic scope "
                            "through the selected Capability contract: "
                            f"goal_id={goal_id!r}, binding={name!r}, "
                            f"entity_type={binding['entity_type']!r}, "
                            f"capability_id={step.capability_id!r}"
                        )
                    for argument_name in realized_arguments:
                        resolution = resolutions_by_step_parameter.get(
                            (step.step_id, argument_name)
                        )
                        if (
                            resolution is None
                            or resolution.strategy != "semantic_realization"
                            or goal_id not in resolution.source_goal_ids
                            or not _material_values_equal(
                                resolution.value,
                                step.args[argument_name],
                                list_compatible=False,
                            )
                        ):
                            raise PlannerDTOContractError(
                                "Capability semantic realization requires explicit "
                                "Planner provenance: "
                                f"step_id={step.step_id!r}, parameter={argument_name!r}, "
                                f"goal_id={goal_id!r}"
                            )
                    continue
                semantic_scope = (
                    (capability.get("hints") or {}).get("semantic_scope") or {}
                )
                fixed_scope = semantic_scope.get("fixed_temporal_scope") or {}
                fixed_entity_types = {
                    str(value).casefold()
                    for value in fixed_scope.get("entity_types") or []
                }
                fixed_values = list(fixed_scope.get("values") or [])
                if (
                    binding["entity_type"] in fixed_entity_types
                    and any(
                        _material_values_equal(
                            declared,
                            expected,
                            list_compatible=False,
                        )
                        for declared in fixed_values
                    )
                ):
                    continue
                raise PlannerDTOContractError(
                    "information capability step omits authoritative temporal scope: "
                    f"goal_id={goal_id!r}, binding={name!r}, value={expected!r}"
                )

        if step.capability_id == "chromie.memory.retrieve_verified_tool_result":
            material_args = step.args.get("material_args")
            if not isinstance(material_args, dict):
                raise ValueError(
                    "verified-memory retrieval requires material_args containing "
                    "the authoritative Goal bindings"
                )
            for name, binding in required.items():
                if name not in material_args:
                    raise ValueError(
                        f"verified-memory retrieval omitted authoritative Goal binding: {name!r}"
                    )
                actual = material_args[name]
                expected = binding["value"]
                if not _material_values_equal(
                    actual,
                    expected,
                    list_compatible=(binding["entity_type"] in _LIST_ENTITY_TYPES),
                ):
                    raise ValueError(
                        "verified-memory retrieval contradicts authoritative Goal "
                        f"binding: material_args.{name}={actual!r}, "
                        f"expected={expected!r}"
                    )

def validate_user_supplied_parameter_provenance(
    output: PlannerModelOutput,
    *,
    authoritative_goals: list[dict[str, Any]],
) -> None:
    """Require non-numeric ``user_supplied`` values to exist in typed Goals.

    A Planner may map a Goal binding to a differently named Capability argument,
    but it cannot manufacture a material string/entity value and label it as user
    supplied. Numeric provenance retains its older dedicated validator because it
    also accounts for explicit numeric literals during the binding migration.
    """

    if output.disposition not in {"execute", "mixed"}:
        return

    bindings_by_goal: dict[str, dict[str, dict[str, Any]]] = {}
    for goal in authoritative_goals:
        if not isinstance(goal, dict):
            continue
        goal_id = " ".join(str(goal.get("goal_id") or "").strip().split())
        if goal_id:
            bindings_by_goal[goal_id] = _goal_binding_map(goal)

    for resolution in output.parameter_resolutions:
        if resolution.strategy != "user_supplied":
            continue
        value = resolution.value
        if (
            not isinstance(value, bool)
            and isinstance(value, (int, float, Decimal))
        ) or (
            isinstance(value, str)
            and _NUMERIC_LITERAL_RE.fullmatch(value.strip()) is not None
        ):
            # The dedicated numeric provenance validator also supports legacy
            # Goals whose numeric binding migration is still in progress.
            continue

        source_goal_ids = [
            goal_id
            for goal_id in resolution.source_goal_ids
            if goal_id in bindings_by_goal
        ]
        if not source_goal_ids:
            raise ValueError(
                "non-numeric user_supplied parameter resolution requires "
                f"authoritative source_goal_ids: {resolution.step_id}."
                f"{resolution.parameter}"
            )

        cited_bindings: dict[str, list[dict[str, Any]]] = {}
        for goal_id in source_goal_ids:
            for name, binding in bindings_by_goal[goal_id].items():
                cited_bindings.setdefault(name, []).append(binding)

        if isinstance(value, dict) and resolution.parameter == "material_args":
            unmatched = []
            for name, actual in value.items():
                candidates = cited_bindings.get(str(name), [])
                if not candidates or not any(
                    _material_values_equal(
                        actual,
                        binding["value"],
                        list_compatible=(binding["entity_type"] in _LIST_ENTITY_TYPES),
                    )
                    for binding in candidates
                ):
                    unmatched.append(str(name))
            if not unmatched:
                continue
        else:
            preferred = cited_bindings.get(resolution.parameter, [])
            candidates = preferred or [
                binding
                for bindings in cited_bindings.values()
                for binding in bindings
            ]
            if any(
                _material_values_equal(
                    value,
                    binding["value"],
                    list_compatible=(binding["entity_type"] in _LIST_ENTITY_TYPES),
                )
                for binding in candidates
            ):
                continue

        raise ValueError(
            "user_supplied parameter resolution is not present in authoritative "
            f"typed Goal bindings: {resolution.step_id}."
            f"{resolution.parameter}={value!r}"
        )

def validate_external_response_evidence_boundary(
    output: PlannerModelOutput,
    *,
    context: dict[str, Any] | None,
) -> None:
    """Reject factual responses for unresolved external-read Goals.

    Active Goal snapshots may record that a trusted safe-read Capability was
    planned but has not produced completed evidence.  A planner may retry that
    read, retrieve an exact verified result, clarify, or report a limitation.
    It may not turn the unresolved execution binding into a direct factual
    response.  This validator reads typed lifecycle evidence only; it does not
    inspect user wording or choose a Capability.
    """

    context = context or {}
    snapshots = context.get("active_goal_snapshots")
    if not isinstance(snapshots, list):
        snapshots = []

    unresolved_external_goal_ids: set[str] = set()
    completed_statuses = {"completed", "done", "success", "succeeded"}
    external_safety_classes = {"safe_read", "read_only", "external_read"}
    for snapshot in snapshots:
        if not isinstance(snapshot, dict):
            continue
        goal_id = " ".join(str(snapshot.get("goal_id") or "").strip().split())
        if not goal_id:
            continue
        metadata = snapshot.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        binding = metadata.get("execution_binding")
        if not isinstance(binding, dict):
            continue
        outcome_status = " ".join(
            str(binding.get("execution_outcome_status") or "").strip().split()
        ).casefold()
        if outcome_status in completed_statuses:
            continue
        planned = binding.get("planned_capabilities")
        if not isinstance(planned, list):
            planned = []
        has_external_read = bool(binding.get("retryable_safe_read"))
        for item in planned:
            if not isinstance(item, dict):
                continue
            safety_class = " ".join(str(item.get("safety_class") or "").strip().split()).casefold()
            if safety_class in external_safety_classes or item.get("retryable_safe_read") is True:
                has_external_read = True
                break
        if has_external_read:
            unresolved_external_goal_ids.add(goal_id)

    responding_goal_ids: set[str] = set()
    if output.goal_outcomes:
        responding_goal_ids = {
            goal_id
            for goal_id, outcome in output.goal_outcomes.items()
            if outcome.disposition == "respond"
        }
    elif output.disposition == "respond":
        responding_goal_ids = set(unresolved_external_goal_ids)

    unsupported = responding_goal_ids & unresolved_external_goal_ids
    unsupported -= result_evidence_reentry_goal_ids(context)
    unsupported -= goal_cancellation_evidence_reentry_goal_ids(context)
    if unsupported:
        raise ValueError(
            "external_read_response_requires_completed_or_verified_evidence: "
            + ",".join(sorted(unsupported))
        )

    verified_goal_ids: set[str] = set()
    verified_index = context.get("verified_tool_memory_index")
    if isinstance(verified_index, list):
        for item in verified_index:
            if not isinstance(item, dict):
                continue
            verified_goal_ids.update(
                normalized
                for value in item.get("goal_ids") or []
                if (normalized := " ".join(str(value or "").strip().split()))
            )
    dialogue_goal_ids = {
        goal_id
        for item in evidence_bound_dialogue(context)
        for goal_id in item.get("source_goal_ids") or []
    }
    index_only_goal_ids = responding_goal_ids & verified_goal_ids - dialogue_goal_ids
    index_only_goal_ids -= result_evidence_reentry_goal_ids(context)
    index_only_goal_ids -= goal_cancellation_evidence_reentry_goal_ids(context)
    if index_only_goal_ids:
        raise ValueError(
            "external_read_response_requires_evidence_bound_dialogue_or_retrieval: "
            + ",".join(sorted(index_only_goal_ids))
        )

def validate_explicit_numeric_parameter_grounding(
    output: PlannerModelOutput,
    *,
    authoritative_goals: list[dict[str, Any]],
) -> None:
    """Verify numeric user-supplied arguments against immutable goal text.

    The planner remains the semantic authority for mapping a user value to a
    skill parameter.  This check only enforces provenance after that judgment:
    a value labelled ``user_supplied`` must agree with its executable step and
    identify an authoritative source Goal containing that value, and every
    numeric literal in an executable goal must be accounted for.  It therefore
    catches silent default substitution without introducing phrase-to-action
    or parameter-name rules.  Stable Goal IDs carry provenance; requiring the
    model to copy a second free-text citation adds no evidence and is not part
    of this contract.
    """

    if output.disposition not in {"execute", "mixed"}:
        return

    def numeric(value: Any) -> Decimal | None:
        if isinstance(value, bool) or not isinstance(value, (int, float, Decimal, str)):
            return None
        if isinstance(value, str) and _NUMERIC_LITERAL_RE.fullmatch(value.strip()) is None:
            return None
        try:
            return Decimal(str(value).strip())
        except InvalidOperation:
            return None

    def literals(value: str) -> list[Decimal]:
        found: list[Decimal] = []
        for match in _NUMERIC_LITERAL_RE.finditer(value):
            try:
                number = Decimal(match.group(0))
            except InvalidOperation:
                continue
            if number not in found:
                found.append(number)
        return found

    def resolution_location(resolution: PlanParameterResolution) -> str:
        """Render an unambiguous typed location for model repair feedback."""

        return f"step_id={resolution.step_id!r}, parameter={resolution.parameter!r}"

    def numerically_equal(left: Decimal, right: Decimal) -> bool:
        """Ignore only representation-scale floating-point roundoff."""

        scale = max(abs(left), abs(right), Decimal(1))
        return abs(left - right) <= Decimal("1e-12") * scale

    goal_text: dict[str, str] = {}
    resource_arguments_by_goal: dict[str, dict[str, Any]] = {}
    for goal in authoritative_goals:
        if not isinstance(goal, dict):
            continue
        goal_id = " ".join(str(goal.get("goal_id") or "").strip().split())
        if not goal_id:
            continue
        parts: list[str] = []
        description = str(goal.get("description") or "").strip()
        if description:
            parts.append(description)
        criteria = goal.get("success_criteria")
        if isinstance(criteria, list):
            parts.extend(str(item).strip() for item in criteria if str(item).strip())
        source_text = str(goal.get("source_text") or "").strip()
        if not parts and source_text:
            parts.append(source_text)
        bindings = _goal_binding_map(goal)
        parts.extend(
            str(binding.get("value")).strip()
            for binding in bindings.values()
            if binding.get("value") is not None
            and str(binding.get("value")).strip()
        )
        responsibility = goal.get("resource_responsibility")
        if isinstance(responsibility, dict):
            resource_arguments_by_goal[goal_id] = {
                name: responsibility.get(name)
                for name in ("resource", "source", "recipient")
                if isinstance(responsibility.get(name), dict)
            }
        goal_text[goal_id] = " ".join(dict.fromkeys(parts))

    steps = {step.step_id: step for step in output.steps}
    structured_numeric_grounding: dict[str, set[Decimal]] = {}

    def nested_numbers(value: Any) -> set[Decimal]:
        if isinstance(value, dict):
            return {
                number
                for item in value.values()
                for number in nested_numbers(item)
            }
        if isinstance(value, list):
            return {
                number
                for item in value
                for number in nested_numbers(item)
            }
        if isinstance(value, str):
            return set(literals(value))
        number = numeric(value)
        return {number} if number is not None else set()

    for step in output.steps:
        for goal_id in step.source_goal_ids:
            expected_arguments = resource_arguments_by_goal.get(goal_id, {})
            for parameter, expected in expected_arguments.items():
                actual = step.args.get(parameter)
                if actual is None or not _material_values_equal(
                    actual,
                    expected,
                    list_compatible=False,
                ):
                    continue
                structured_numeric_grounding.setdefault(goal_id, set()).update(
                    nested_numbers(actual)
                )
    user_numeric_resolutions: list[tuple[PlanParameterResolution, Decimal]] = []
    unsupported_user_numeric_resolutions: list[
        tuple[PlanParameterResolution, Decimal, list[str]]
    ] = []
    for resolution in output.parameter_resolutions:
        if resolution.blocking:
            continue
        step = steps.get(resolution.step_id)
        if step is None:
            raise PlannerDTOContractError(
                "parameter resolution references unknown executable step "
                f"({resolution_location(resolution)})"
            )
        if resolution.parameter not in step.args:
            raise PlannerDTOContractError(
                "parameter resolution references an argument absent from its step: "
                f"{resolution_location(resolution)}"
            )
        resolved_number = numeric(resolution.value)
        argument_number = numeric(step.args[resolution.parameter])
        if resolved_number is not None and argument_number is not None:
            if not numerically_equal(resolved_number, argument_number):
                raise PlannerDTOContractError(
                    "parameter resolution value must equal the executable step argument: "
                    f"{resolution_location(resolution)} has "
                    f"resolution={resolution.value!r}, step={step.args[resolution.parameter]!r}"
                )
        elif not _material_values_equal(
            resolution.value,
            step.args[resolution.parameter],
            list_compatible=(
                isinstance(resolution.value, list)
                or isinstance(step.args[resolution.parameter], list)
            ),
        ):
            raise PlannerDTOContractError(
                "parameter resolution value must equal the executable step argument: "
                f"{resolution_location(resolution)}"
            )

        if resolution.strategy != "user_supplied" or resolved_number is None:
            continue
        source_goal_ids = list(dict.fromkeys(resolution.source_goal_ids))
        if not source_goal_ids:
            raise PlannerDTOContractError(
                "numeric user_supplied parameter resolution requires source_goal_ids: "
                f"{resolution_location(resolution)}"
            )
        unsupported_goal_ids = [
            goal_id
            for goal_id in source_goal_ids
            if resolved_number not in literals(goal_text.get(goal_id, ""))
        ]
        if unsupported_goal_ids:
            unsupported_user_numeric_resolutions.append(
                (resolution, resolved_number, unsupported_goal_ids)
            )
        user_numeric_resolutions.append((resolution, resolved_number))

    executable_goal_ids = {
        goal_id
        for goal_id, outcome in output.goal_outcomes.items()
        if outcome.disposition == "execute"
    }
    if not executable_goal_ids:
        executable_goal_ids = {goal_id for step in output.steps for goal_id in step.source_goal_ids}
    missing_numeric_grounding: list[tuple[str, Decimal]] = []
    for goal_id in sorted(executable_goal_ids):
        for literal in literals(goal_text.get(goal_id, "")):
            if not any(
                literal == value and goal_id in resolution.source_goal_ids
                for resolution, value in user_numeric_resolutions
            ) and literal not in structured_numeric_grounding.get(goal_id, set()):
                missing_numeric_grounding.append((goal_id, literal))
    if missing_numeric_grounding:
        missing = "; ".join(
            f"goal_id={goal_id!r}, value={literal}"
            for goal_id, literal in missing_numeric_grounding
        )
        raise ValueError(
            "explicit numeric goal value has no matching user_supplied "
            f"parameter resolution: {missing}"
        )
    if unsupported_user_numeric_resolutions:
        unsupported = "; ".join(
            f"{resolution_location(resolution)}, value={value}, "
            f"source_goal_ids={goal_ids!r}"
            for resolution, value, goal_ids in unsupported_user_numeric_resolutions
        )
        raise ValueError(
            "numeric user_supplied parameter resolution is not present in "
            f"its authoritative source Goal: {unsupported}"
        )

def explicit_numeric_goal_values(
    authoritative_goals: list[dict[str, Any]],
    *,
    include_resource_goals: bool = False,
) -> dict[str, list[int | float]]:
    """Project explicit Goal numbers for decoder-side provenance obligations.

    This is the same immutable Goal surface consumed by the runtime validator;
    it does not decide which Capability parameter a number means. Resource Goals
    are excluded by default because an exact structured resource argument carries
    its own nested numeric grounding without a flat parameter resolution.
    """

    projected: dict[str, list[int | float]] = {}
    for goal in authoritative_goals:
        if not isinstance(goal, dict):
            continue
        goal_id = " ".join(str(goal.get("goal_id") or "").strip().split())
        if not goal_id:
            continue
        if (
            not include_resource_goals
            and isinstance(goal.get("resource_responsibility"), dict)
        ):
            continue
        parts: list[str] = []
        description = str(goal.get("description") or "").strip()
        if description:
            parts.append(description)
        criteria = goal.get("success_criteria")
        if isinstance(criteria, list):
            parts.extend(
                str(item).strip() for item in criteria if str(item).strip()
            )
        source_text = str(goal.get("source_text") or "").strip()
        if not parts and source_text:
            parts.append(source_text)
        parts.extend(
            str(binding.get("value")).strip()
            for binding in _goal_binding_map(goal).values()
            if binding.get("value") is not None
            and str(binding.get("value")).strip()
        )
        values: list[int | float] = []
        for match in _NUMERIC_LITERAL_RE.finditer(" ".join(dict.fromkeys(parts))):
            try:
                decimal_value = Decimal(match.group(0))
            except InvalidOperation:
                continue
            json_value: int | float = (
                int(decimal_value)
                if decimal_value == decimal_value.to_integral_value()
                else float(decimal_value)
            )
            if json_value not in values:
                values.append(json_value)
        if values:
            projected[goal_id] = values
    return projected

def normalize_missing_numeric_parameter_provenance(
    raw: dict[str, Any],
    *,
    authoritative_goals: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Add only mechanically provable duplicate provenance for Goal numbers.

    Capability choice, step ownership, argument name, and argument value must
    already exist in the model-authored DTO. A row is added only when one exact
    Goal number occurs in exactly one argument of exactly one step owned by that
    Goal. No executable or communicative field is changed.
    """

    steps = raw.get("steps")
    if not isinstance(steps, list):
        return raw, []
    outcomes = raw.get("goal_outcomes")
    outcomes = outcomes if isinstance(outcomes, dict) else {}
    resolutions = raw.get("parameter_resolutions")
    resolutions = resolutions if isinstance(resolutions, list) else []

    def numeric(value: Any) -> Decimal | None:
        if isinstance(value, bool) or not isinstance(
            value, (int, float, Decimal, str)
        ):
            return None
        if (
            isinstance(value, str)
            and _NUMERIC_LITERAL_RE.fullmatch(value.strip()) is None
        ):
            return None
        try:
            return Decimal(str(value).strip())
        except InvalidOperation:
            return None

    def equal(left: Decimal, right: Decimal) -> bool:
        scale = max(abs(left), abs(right), Decimal(1))
        return abs(left - right) <= Decimal("1e-12") * scale

    repairs: list[dict[str, Any]] = []
    for goal_id, values in explicit_numeric_goal_values(
        authoritative_goals
    ).items():
        outcome = outcomes.get(goal_id)
        if isinstance(outcome, dict) and outcome.get("disposition") != "execute":
            continue
        for value in values:
            expected = Decimal(str(value))
            candidates: list[tuple[str, str]] = []
            for step in steps:
                if not isinstance(step, dict) or goal_id not in (
                    step.get("source_goal_ids") or []
                ):
                    continue
                step_id = " ".join(str(step.get("step_id") or "").strip().split())
                args = step.get("args")
                if not step_id or not isinstance(args, dict):
                    continue
                for parameter, argument in args.items():
                    actual = numeric(argument)
                    if actual is not None and equal(actual, expected):
                        candidates.append((step_id, str(parameter)))
            if len(candidates) != 1:
                continue
            step_id, parameter = candidates[0]
            # This adapter fills an absent duplicate-provenance row only. An
            # existing row for the same argument remains model-authored input,
            # including when its value or Goal ownership is wrong, so normal
            # contract validation can reject it instead of masking the defect
            # with a second mechanically generated row.
            if any(
                isinstance(resolution, dict)
                and str(resolution.get("step_id") or "").strip() == step_id
                and str(resolution.get("parameter") or "").strip() == parameter
                for resolution in resolutions
            ):
                continue
            repairs.append(
                {
                    "step_id": step_id,
                    "parameter": parameter,
                    "strategy": "user_supplied",
                    "value": value,
                    "confidence": 1.0,
                    "blocking": False,
                    "rationale": (
                        "Exact duplicate provenance for a Goal numeric value "
                        "already present in one owned step argument."
                    ),
                    "source_goal_ids": [goal_id],
                }
            )
    if not repairs:
        return raw, []
    normalized = copy.deepcopy(raw)
    target = normalized.setdefault("parameter_resolutions", [])
    if not isinstance(target, list):
        return raw, []
    target.extend(copy.deepcopy(repairs))
    return normalized, repairs

def normalize_schema_default_parameter_provenance(
    raw: dict[str, Any],
    *,
    authoritative_goals: list[dict[str, Any]],
    capability_payload: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Correct a mechanically provable schema-default provenance label.

    The planner still owns capability, argument, and Goal/step selection. This
    adapter changes only ``user_supplied`` provenance when the numeric value is
    absent from every cited Goal and exactly equals the selected capability's
    declared default for the same argument. It never changes an argument value
    or repairs values without authoritative catalog-default evidence.
    """

    def numeric(value: Any) -> Decimal | None:
        if isinstance(value, bool) or not isinstance(
            value,
            (int, float, Decimal, str),
        ):
            return None
        if (
            isinstance(value, str)
            and _NUMERIC_LITERAL_RE.fullmatch(value.strip()) is None
        ):
            return None
        try:
            return Decimal(str(value).strip())
        except InvalidOperation:
            return None

    goal_numbers: dict[str, set[Decimal]] = {}
    for goal in authoritative_goals:
        if not isinstance(goal, dict):
            continue
        goal_id = " ".join(str(goal.get("goal_id") or "").strip().split())
        if not goal_id:
            continue
        values: set[Decimal] = set()
        for text in [
            goal.get("description"),
            *(goal.get("success_criteria") or []),
        ]:
            for match in _NUMERIC_LITERAL_RE.finditer(str(text or "")):
                parsed = numeric(match.group(0))
                if parsed is not None:
                    values.add(parsed)
        for binding in _goal_binding_map(goal).values():
            parsed = numeric(binding.get("value"))
            if parsed is not None:
                values.add(parsed)
        goal_numbers[goal_id] = values

    schemas = {
        str(item.get("capability_id") or "").strip(): item.get("input_schema") or {}
        for item in capability_payload
        if isinstance(item, dict)
    }
    normalized = copy.deepcopy(raw)
    steps = {
        str(item.get("step_id") or "").strip(): item
        for item in normalized.get("steps") or []
        if isinstance(item, dict) and str(item.get("step_id") or "").strip()
    }
    repairs: list[dict[str, Any]] = []
    for resolution in normalized.get("parameter_resolutions") or []:
        if not isinstance(resolution, dict):
            continue
        if str(resolution.get("strategy") or "") != "user_supplied":
            continue
        resolved_number = numeric(resolution.get("value"))
        if resolved_number is None:
            continue
        source_goal_ids = [
            " ".join(str(value or "").strip().split())
            for value in resolution.get("source_goal_ids") or []
        ]
        if any(
            resolved_number in goal_numbers.get(goal_id, set())
            for goal_id in source_goal_ids
        ):
            continue
        step_id = str(resolution.get("step_id") or "").strip()
        parameter = str(resolution.get("parameter") or "").strip()
        step = steps.get(step_id)
        if not isinstance(step, dict):
            continue
        args = step.get("args") if isinstance(step.get("args"), dict) else {}
        argument_number = numeric(args.get(parameter))
        capability_id = str(step.get("capability_id") or "").strip()
        parameter_schema = (
            schemas.get(capability_id, {}).get("properties", {}).get(parameter, {})
        )
        schema_default = (
            parameter_schema.get("default")
            if isinstance(parameter_schema, dict)
            else None
        )
        default_number = numeric(schema_default)
        if (
            argument_number is None
            or default_number is None
            or resolved_number != argument_number
            or resolved_number != default_number
        ):
            continue
        resolution["strategy"] = "schema_default"
        resolution["source_goal_ids"] = []
        repairs.append(
            {
                "step_id": step_id,
                "capability_id": capability_id,
                "parameter": parameter,
                "value": resolution.get("value"),
                "from_strategy": "user_supplied",
                "to_strategy": "schema_default",
                "reason": "exact_declared_catalog_default_absent_from_cited_goals",
            }
        )
    return normalized, repairs

def normalize_detached_parameter_resolutions(
    raw: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Remove only non-blocking resolution records with no step argument.

    A ``PlanParameterResolution`` is provenance for one exact executable argument;
    it does not own the argument or any Goal meaning.  When a model attaches a
    non-blocking resolution to a parameter absent from the referenced step while
    the exact resolved value is already carried by another top-level argument, that
    record cannot ground additional execution meaning and is mechanically detached.
    Dropping it does not rewrite the selected Capability, step arguments, Goal
    ownership, timing, or disposition.  All remaining authoritative binding and
    numeric-grounding checks still run, so a missing or differently nested material
    argument continues through the normal repair/fail-closed path.

    Blocking resolutions are deliberately retained because they describe an
    unresolved parameter that may not yet exist in executable ``args``.
    """

    normalized = copy.deepcopy(raw)
    steps = {
        str(item.get("step_id") or "").strip(): item
        for item in normalized.get("steps") or []
        if isinstance(item, dict) and str(item.get("step_id") or "").strip()
    }
    resolutions = normalized.get("parameter_resolutions")
    if not isinstance(resolutions, list):
        return normalized, []

    retained: list[Any] = []
    repairs: list[dict[str, Any]] = []
    for resolution in resolutions:
        if not isinstance(resolution, dict) or resolution.get("blocking") is True:
            retained.append(resolution)
            continue
        step_id = str(resolution.get("step_id") or "").strip()
        parameter = str(resolution.get("parameter") or "").strip()
        step = steps.get(step_id)
        args = step.get("args") if isinstance(step, dict) else None
        if (
            not step_id
            or not parameter
            or not isinstance(args, dict)
            or parameter in args
        ):
            retained.append(resolution)
            continue
        equivalent_arguments = sorted(
            str(name)
            for name, value in args.items()
            if _material_values_equal(
                resolution.get("value"),
                value,
                list_compatible=(
                    isinstance(resolution.get("value"), list)
                    or isinstance(value, list)
                ),
            )
        )
        if not equivalent_arguments:
            retained.append(resolution)
            continue
        repairs.append(
            {
                "normalization": "detached_parameter_resolution_removed",
                "step_id": step_id,
                "parameter": parameter,
                "step_argument_keys": sorted(str(key) for key in args),
                "equivalent_step_argument_keys": equivalent_arguments,
            }
        )

    normalized["parameter_resolutions"] = retained
    return normalized, repairs

def planner_contract_diagnostics(
    raw: Any,
    *,
    planner_tier: PlannerTier,
    expected_goal_ids_for_turn: list[str],
) -> list[dict[str, Any]]:
    """Collect independent planner-contract defects without short-circuiting.

    Pydantic intentionally validates nested values before parent model validators.
    That means one invalid nested satisfaction object can hide a missing
    ``step_ids`` or ``response_text`` defect in the same goal outcome.  The
    planners allow only one mechanical DTO regeneration, so validation feedback must
    expose all independently observable structural defects from the original
    model output rather than only the first validation layer that failed.

    This function is diagnostic only.  It never rewrites model-authored meaning
    or fills missing ownership/response fields.
    """

    if not isinstance(raw, dict):
        return []

    diagnostics: list[dict[str, Any]] = []

    def add(
        loc: list[str | int],
        msg: str,
        *,
        value: Any = None,
        error_type: str = "value_error",
    ) -> None:
        diagnostics.append(
            {
                "type": error_type,
                "loc": loc,
                "msg": msg,
                "input": value,
                "source": "planner_contract_diagnostics",
            }
        )

    def satisfaction_status_for_score(score: float) -> GoalSatisfactionStatus:
        if score >= 0.95:
            return "exact"
        if score >= 0.75:
            return "substantial"
        if score > 0.0:
            return "partial"
        return "unsatisfied"

    def inspect_satisfaction(value: Any, loc: list[str | int]) -> None:
        if not isinstance(value, dict):
            return
        score = value.get("score")
        status = value.get("status")
        if not isinstance(score, (int, float)) or isinstance(score, bool):
            return
        if not isinstance(status, str):
            return
        if not 0.0 <= float(score) <= 1.0:
            return
        expected = satisfaction_status_for_score(float(score))
        if status != expected:
            add(
                loc,
                (
                    "goal satisfaction score is inconsistent with status; "
                    f"score={float(score):g} requires status={expected!r}"
                ),
                value=value,
            )

    steps = raw.get("steps")
    if not isinstance(steps, list):
        steps = []
    step_ids: set[str] = set()
    step_sources: dict[str, set[str]] = {}
    for index, item in enumerate(steps):
        if not isinstance(item, dict):
            continue
        step_id = " ".join(str(item.get("step_id") or "").strip().split())
        if step_id:
            step_ids.add(step_id)
            source_goal_ids = item.get("source_goal_ids")
            if isinstance(source_goal_ids, str):
                source_goal_ids = [source_goal_ids]
            if isinstance(source_goal_ids, list):
                for source_goal_id in source_goal_ids:
                    goal_id = " ".join(str(source_goal_id or "").strip().split())
                    if goal_id:
                        step_sources.setdefault(step_id, set()).add(goal_id)
        elif item.get("capability_id"):
            add(
                ["steps", index, "step_id"],
                "executable planner step requires step_id",
                value=item,
                error_type="missing",
            )

    disposition = raw.get("disposition")
    coverage = raw.get("coverage")
    response_text = str(raw.get("response_text") or "").strip()
    if coverage != "complete" and steps:
        add(
            ["steps"],
            "non-complete planner output must not carry executable steps",
            value=steps,
        )
    if disposition == "execute" and not steps:
        add(
            ["steps"],
            "execute planner output requires at least one step",
            value=steps,
        )
    if disposition == "mixed" and not steps:
        add(
            ["steps"],
            "mixed planner output requires steps and goal_outcomes",
            value=steps,
        )
    if disposition == "respond" and not response_text:
        add(
            ["response_text"],
            "respond planner output requires response_text",
            value=raw.get("response_text"),
        )
    if disposition not in {"execute", "mixed"} and steps:
        add(
            ["steps"],
            f"{disposition} planner output must not carry executable steps",
            value=steps,
        )
    if disposition in {"execute", "respond", "mixed"} and coverage != "complete":
        add(
            ["coverage"],
            "execute, respond, and mixed planner output requires complete coverage",
            value=coverage,
        )
    if disposition in {"execute", "respond", "mixed"} and not isinstance(
        raw.get("goal_satisfaction"), dict
    ):
        add(
            ["goal_satisfaction"],
            "complete executable or response output requires goal_satisfaction",
            value=raw.get("goal_satisfaction"),
        )
    inspect_satisfaction(raw.get("goal_satisfaction"), ["goal_satisfaction"])

    outcomes = raw.get("goal_outcomes")
    expected_goal_ids = list(dict.fromkeys(expected_goal_ids_for_turn))
    expected_goal_set = set(expected_goal_ids)
    multi_goal_fast = planner_tier == "fast" and len(expected_goal_set) > 1
    fast_escalation = planner_tier == "fast" and disposition == "escalate"

    if multi_goal_fast and "goal_outcomes" not in raw:
        add(
            ["goal_outcomes"],
            "multi-goal fast planner output requires an explicit goal_outcomes object",
            value=None,
            error_type="missing",
        )
    if fast_escalation:
        if coverage not in {"partial", "uncertain"}:
            add(
                ["coverage"],
                "fast semantic escalation requires partial or uncertain coverage",
                value=coverage,
            )
        if multi_goal_fast:
            satisfaction = raw.get("goal_satisfaction")
            if not isinstance(satisfaction, dict):
                add(
                    ["goal_satisfaction"],
                    "multi-goal fast escalation requires model-authored goal_satisfaction",
                    value=satisfaction,
                )
            elif satisfaction.get("status") == "exact":
                add(
                    ["goal_satisfaction", "status"],
                    "fast semantic escalation cannot claim exact goal satisfaction",
                    value=satisfaction.get("status"),
                )
        else:
            if isinstance(outcomes, dict) and outcomes:
                add(
                    ["goal_outcomes"],
                    "single-goal fast semantic escalation requires goal_outcomes={}",
                    value=outcomes,
                )
            if raw.get("goal_satisfaction") is not None:
                add(
                    ["goal_satisfaction"],
                    "single-goal fast semantic escalation requires goal_satisfaction=null",
                    value=raw.get("goal_satisfaction"),
                )
    if isinstance(outcomes, dict):
        outcome_goal_set = set(outcomes)
        require_complete_outcome_map = not fast_escalation or multi_goal_fast
        if require_complete_outcome_map and outcome_goal_set != expected_goal_set:
            add(
                ["goal_outcomes"],
                ("goal_outcomes keys must cover exactly the authoritative Goal Association IDs"),
                value={
                    "expected": expected_goal_ids,
                    "actual": list(outcomes),
                },
            )

        outcome_dispositions: set[str] = set()
        referenced_steps: set[str] = set()
        executable_owners_by_step: dict[str, set[str]] = {}
        for goal_id, outcome in outcomes.items():
            if not isinstance(outcome, dict):
                continue
            outcome_disposition = outcome.get("disposition")
            outcome_coverage = outcome.get("coverage")
            outcome_response = str(outcome.get("response_text") or "").strip()
            outcome_step_ids = outcome.get("step_ids")
            if isinstance(outcome_step_ids, str):
                outcome_step_ids = [outcome_step_ids]
            if not isinstance(outcome_step_ids, list):
                outcome_step_ids = []
            normalized_outcome_step_ids = [
                " ".join(str(item or "").strip().split())
                for item in outcome_step_ids
                if " ".join(str(item or "").strip().split())
            ]
            outcome_dispositions.add(str(outcome_disposition or ""))
            allowed_outcome_dispositions = (
                {"execute", "respond", "clarify", "escalate"}
                if planner_tier == "fast"
                else {
                    "execute",
                    "respond",
                    "clarify",
                    "unavailable",
                    "refused",
                }
            )
            if outcome_disposition not in allowed_outcome_dispositions:
                add(
                    ["goal_outcomes", goal_id, "disposition"],
                    f"{planner_tier} goal outcome requires one legal explicit disposition",
                    value=outcome_disposition,
                )
            inspect_satisfaction(
                outcome.get("satisfaction"),
                ["goal_outcomes", goal_id, "satisfaction"],
            )

            if outcome_disposition == "execute":
                if outcome_coverage != "complete" or not normalized_outcome_step_ids:
                    add(
                        ["goal_outcomes", goal_id],
                        "execute goal outcome requires complete coverage and step_ids",
                        value=outcome,
                    )
                for step_id in normalized_outcome_step_ids:
                    referenced_steps.add(step_id)
                    executable_owners_by_step.setdefault(step_id, set()).add(goal_id)
            elif outcome_disposition == "respond":
                if outcome_coverage != "complete" or not outcome_response:
                    add(
                        ["goal_outcomes", goal_id],
                        "respond goal outcome requires complete coverage and response_text",
                        value=outcome,
                    )
                if normalized_outcome_step_ids:
                    add(
                        ["goal_outcomes", goal_id, "step_ids"],
                        "respond goal outcome must not reference steps",
                        value=normalized_outcome_step_ids,
                    )
            elif outcome_disposition == "escalate":
                if outcome_coverage not in {"partial", "uncertain"}:
                    add(
                        ["goal_outcomes", goal_id, "coverage"],
                        "escalate goal outcome requires partial or uncertain coverage",
                        value=outcome_coverage,
                    )
                if normalized_outcome_step_ids:
                    add(
                        ["goal_outcomes", goal_id, "step_ids"],
                        "escalate goal outcome must not reference steps",
                        value=normalized_outcome_step_ids,
                    )
                if outcome_response:
                    add(
                        ["goal_outcomes", goal_id, "response_text"],
                        "escalate goal outcome must not claim a conversational answer",
                        value=outcome_response,
                    )
                if (
                    not outcome.get("unresolved")
                    and not str(outcome.get("rationale") or "").strip()
                ):
                    add(
                        ["goal_outcomes", goal_id],
                        "escalate goal outcome requires an unresolved need or rationale",
                        value=outcome,
                    )
            elif outcome_disposition == "clarify":
                if outcome_coverage not in {"partial", "uncertain"}:
                    add(
                        ["goal_outcomes", goal_id, "coverage"],
                        "clarify goal outcome requires partial or uncertain coverage",
                        value=outcome_coverage,
                    )
                if normalized_outcome_step_ids:
                    add(
                        ["goal_outcomes", goal_id, "step_ids"],
                        "clarify goal outcome must not reference steps",
                        value=normalized_outcome_step_ids,
                    )
                unresolved = outcome.get("unresolved")
                if not outcome_response and not unresolved:
                    add(
                        ["goal_outcomes", goal_id],
                        "clarify goal outcome requires an unresolved need or response_text",
                        value=outcome,
                    )
            elif outcome_disposition in {"unavailable", "refused"} and normalized_outcome_step_ids:
                add(
                    ["goal_outcomes", goal_id, "step_ids"],
                    "unavailable and refused goal outcomes must not reference steps",
                    value=normalized_outcome_step_ids,
                )

            unknown_steps = set(normalized_outcome_step_ids) - step_ids
            if unknown_steps:
                add(
                    ["goal_outcomes", goal_id, "step_ids"],
                    "goal outcome references unknown step IDs: " + ",".join(sorted(unknown_steps)),
                    value=normalized_outcome_step_ids,
                )

        normalized_dispositions = {item for item in outcome_dispositions if item}
        if normalized_dispositions:
            expected_disposition = (
                "mixed" if len(normalized_dispositions) > 1 else next(iter(normalized_dispositions))
            )
            if disposition != expected_disposition:
                add(
                    ["disposition"],
                    "top-level disposition must match per-goal outcome dispositions",
                    value={
                        "actual": disposition,
                        "expected": expected_disposition,
                        "outcome_dispositions": sorted(normalized_dispositions),
                    },
                )

        if step_ids and referenced_steps != step_ids:
            add(
                ["goal_outcomes"],
                "every executable step must belong to at least one goal outcome: "
                + ",".join(sorted(step_ids - referenced_steps)),
                value=outcomes,
            )
        for step_id, sources in step_sources.items():
            expected_sources = executable_owners_by_step.get(step_id, set())
            if expected_sources and sources != expected_sources:
                add(
                    ["steps", step_id, "source_goal_ids"],
                    (
                        f"step {step_id!r} source_goal_ids must exactly match the "
                        "executable goal outcomes that reference it"
                    ),
                    value={
                        "actual": sorted(sources),
                        "expected": sorted(expected_sources),
                    },
                )
    elif len(expected_goal_set) > 1 and disposition in {"execute", "respond", "mixed"}:
        add(
            ["goal_outcomes"],
            (
                "complete multi-goal planner output requires goal_outcomes keyed by "
                "every authoritative Goal Association ID"
            ),
            value=outcomes,
        )

    if planner_tier == "deep" and disposition == "escalate":
        add(
            ["disposition"],
            "deep plans cannot return to the fast planner",
            value=disposition,
        )

    unique: list[dict[str, Any]] = []
    seen: set[tuple[str, tuple[str | int, ...]]] = set()
    for item in diagnostics:
        key = (str(item.get("msg") or ""), tuple(item.get("loc") or []))
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique

def _normalize_redundant_planner_response_fields(
    raw: dict[str, Any],
    *,
    expected_goal_ids_for_turn: list[str],
) -> dict[str, Any]:
    """Normalize transport redundancy without inventing planning semantics.

    ``steps[].source_goal_ids`` is the model's semantic ownership judgment.
    ``goal_outcomes.*.step_ids`` and the top-level disposition repeat that same
    judgment as cross-reference and aggregate transport fields. Models regularly
    produce stale or nonexistent step references even when capability choice,
    arguments, and source ownership are otherwise coherent. Rebuild only those
    redundant fields from the model-authored step ownership; never choose a
    capability, add a step, or assign an unowned Goal. An execute outcome with no
    owned step therefore remains invalid and must be repaired by the model.
    """

    normalized = copy.deepcopy(raw)
    outcomes = normalized.get("goal_outcomes")
    if not isinstance(outcomes, dict):
        return normalized

    expected = list(dict.fromkeys(expected_goal_ids_for_turn))
    expected_set = set(expected)
    owned_step_ids: dict[str, list[str]] = {goal_id: [] for goal_id in expected}
    steps = normalized.get("steps")
    ownership_is_usable = isinstance(steps, list)
    seen_step_ids: set[str] = set()
    if ownership_is_usable:
        for item in steps:
            if not isinstance(item, dict):
                ownership_is_usable = False
                break
            step_id = " ".join(str(item.get("step_id") or "").strip().split())
            source_goal_ids = item.get("source_goal_ids")
            if not step_id or step_id in seen_step_ids or not isinstance(source_goal_ids, list):
                ownership_is_usable = False
                break
            seen_step_ids.add(step_id)
            for raw_goal_id in source_goal_ids:
                goal_id = " ".join(str(raw_goal_id or "").strip().split())
                if goal_id in expected_set and step_id not in owned_step_ids[goal_id]:
                    owned_step_ids[goal_id].append(step_id)

    normalized_outcomes: dict[str, Any] = {}
    for raw_goal_id, value in outcomes.items():
        goal_id = str(raw_goal_id)
        if not isinstance(value, dict):
            normalized_outcomes[goal_id] = value
            continue
        outcome = copy.deepcopy(value)
        response_text = str(outcome.get("response_text") or "").strip()
        owned = owned_step_ids.get(goal_id, []) if ownership_is_usable else []
        if not outcome.get("disposition"):
            if owned:
                outcome["disposition"] = "execute"
            elif response_text:
                outcome["disposition"] = "respond"
        if (
            not outcome.get("coverage")
            and normalized.get("coverage") == "complete"
            and outcome.get("disposition") in {"execute", "respond"}
        ):
            outcome["coverage"] = "complete"
        if ownership_is_usable and outcome.get("disposition") == "execute":
            outcome["step_ids"] = list(owned)
        elif outcome.get("disposition") == "respond":
            outcome["step_ids"] = []
        normalized_outcomes[goal_id] = outcome
    normalized["goal_outcomes"] = normalized_outcomes

    if set(normalized_outcomes) == expected_set and expected_set:
        dispositions = {
            str(item.get("disposition") or "")
            for item in normalized_outcomes.values()
            if isinstance(item, dict)
        }
        if "" not in dispositions:
            aggregate = (
                "mixed"
                if dispositions == {"execute", "respond"}
                else next(iter(dispositions))
                if len(dispositions) == 1
                else ""
            )
            if aggregate:
                normalized["disposition"] = aggregate

    if (
        normalized.get("disposition") == "respond"
        and not str(normalized.get("response_text") or "").strip()
        and len(expected) == 1
    ):
        sole = normalized_outcomes.get(expected[0])
        if isinstance(sole, dict):
            response_text = str(sole.get("response_text") or "").strip()
            if response_text:
                normalized["response_text"] = response_text
    return normalized

def validate_planner_model_output(
    raw: dict[str, Any],
    *,
    planner_tier: PlannerTier,
    expected_goal_ids_for_turn: list[str],
) -> PlannerModelOutput:
    """Validate the semantic DTO and reject conflicting legacy goal echoes."""

    model_raw = _normalize_redundant_planner_response_fields(
        dict(raw),
        expected_goal_ids_for_turn=expected_goal_ids_for_turn,
    )
    echoed_goal_ids = model_raw.pop("goal_ids", None)
    for field_name in ("schema_version", "plan_id", "planner_tier"):
        model_raw.pop(field_name, None)

    if echoed_goal_ids is not None:
        if isinstance(echoed_goal_ids, str):
            echoed_goal_ids = [echoed_goal_ids]
        if not isinstance(echoed_goal_ids, list):
            raise ValueError("planner goal_ids echo must be a list when present")
        normalized_echo = list(
            dict.fromkeys(
                " ".join(str(item or "").strip().split())
                for item in echoed_goal_ids
                if " ".join(str(item or "").strip().split())
            )
        )
        if expected_goal_ids_for_turn and set(normalized_echo) != set(expected_goal_ids_for_turn):
            raise ValueError(
                "goal_ids_do_not_match_goal_association: planner echo conflicts "
                "with authoritative Goal Association IDs"
            )

    raw_steps = model_raw.get("steps")
    output = PlannerModelOutput.model_validate(model_raw)

    if isinstance(raw_steps, list):
        for index, item in enumerate(raw_steps):
            if not isinstance(item, dict):
                continue
            missing_authority_fields = [
                field_name
                for field_name in ("step_id", "timing", "source_goal_ids")
                if field_name not in item
            ]
            if missing_authority_fields:
                raise ValueError(
                    f"planner step {index} requires explicit model-authored authority fields: "
                    + ",".join(missing_authority_fields)
                )
    allowed_dispositions = (
        {"respond", "execute", "mixed", "clarify", "escalate"}
        if planner_tier == "fast"
        else {"respond", "execute", "mixed", "clarify", "unavailable", "refused"}
    )
    if output.disposition not in allowed_dispositions:
        raise ValueError(
            f"disposition={output.disposition!r} is not valid for planner_tier={planner_tier}"
        )
    goal_outcomes_were_supplied = "goal_outcomes" in model_raw
    outcome_goal_ids = set(output.goal_outcomes)
    expected_goal_id_set = set(expected_goal_ids_for_turn)
    if planner_tier == "fast" and len(expected_goal_id_set) > 1:
        missing_envelope_fields = [
            field_name
            for field_name in ("steps", "goal_outcomes", "goal_satisfaction")
            if field_name not in model_raw
        ]
        if missing_envelope_fields:
            raise ValueError(
                "multi-goal fast planner output requires explicit fields: "
                + ",".join(missing_envelope_fields)
            )
    if planner_tier == "fast" and len(expected_goal_id_set) > 1 and not goal_outcomes_were_supplied:
        raise ValueError("multi-goal fast planner output requires an explicit goal_outcomes object")
    if planner_tier == "fast" and output.disposition == "escalate":
        if output.coverage not in {"partial", "uncertain"}:
            raise ValueError("fast semantic escalation requires partial or uncertain coverage")
        if len(expected_goal_id_set) <= 1:
            if output.goal_outcomes:
                raise ValueError("single-goal fast semantic escalation requires goal_outcomes={}")
            if output.goal_satisfaction is not None:
                raise ValueError(
                    "single-goal fast semantic escalation requires goal_satisfaction=null"
                )
    if (
        len(expected_goal_id_set) > 1
        and output.disposition in {"execute", "respond", "mixed"}
        and not output.goal_outcomes
    ):
        raise ValueError(
            "complete multi-goal planner output requires goal_outcomes keyed by "
            "every authoritative Goal Association ID"
        )
    if (
        goal_outcomes_were_supplied
        and len(expected_goal_id_set) > 1
        and outcome_goal_ids != expected_goal_id_set
    ):
        raise ValueError(
            "goal_outcomes keys must cover exactly the authoritative Goal Association IDs"
        )
    if planner_tier == "fast" and output.goal_outcomes:
        outcome_dispositions = {outcome.disposition for outcome in output.goal_outcomes.values()}
        unsupported = outcome_dispositions - {"execute", "respond", "clarify", "escalate"}
        if unsupported:
            raise ValueError(
                "fast goal outcomes may only execute, respond, clarify, or escalate: "
                + ",".join(sorted(unsupported))
            )
        if "clarify" in outcome_dispositions:
            if outcome_dispositions != {"clarify"}:
                raise ValueError(
                    "fast clarification must not mix clarify outcomes with "
                    "execute or respond outcomes"
                )
            if output.disposition != "clarify":
                raise ValueError("all-clarify goal outcomes require top-level disposition=clarify")
            if output.steps:
                raise ValueError("fast clarification must not carry steps")
        elif "escalate" in outcome_dispositions:
            if outcome_dispositions != {"escalate"}:
                raise ValueError(
                    "fast semantic escalation must not mix escalate outcomes "
                    "with execute or respond outcomes"
                )
            if output.disposition != "escalate":
                raise ValueError(
                    "all-escalate goal outcomes require top-level disposition=escalate"
                )
            if output.steps:
                raise ValueError("fast semantic escalation must not carry steps")
            if output.goal_satisfaction is None:
                raise ValueError(
                    "multi-goal fast semantic escalation requires model-authored goal_satisfaction"
                )
            if output.goal_satisfaction.status == "exact":
                raise ValueError("fast semantic escalation cannot claim exact goal satisfaction")
        elif output.disposition == "escalate":
            raise ValueError("multi-goal fast escalation requires one escalate outcome per goal")
        if output.disposition == "mixed" and outcome_dispositions != {
            "execute",
            "respond",
        }:
            raise ValueError("fast mixed output requires at least one execute and one respond goal")
    for goal_id, outcome in output.goal_outcomes.items():
        if planner_tier == "fast" and len(expected_goal_id_set) > 1:
            if outcome.satisfaction is None:
                raise ValueError("multi-goal fast outcomes require model-authored satisfaction")
        referenced_goal_ids = {
            *(outcome.satisfaction.satisfied_goal_ids if outcome.satisfaction else []),
            *(outcome.satisfaction.unmet_goal_ids if outcome.satisfaction else []),
        }
        foreign_goal_ids = referenced_goal_ids - {goal_id}
        if foreign_goal_ids:
            raise ValueError(
                "per-goal outcome satisfaction may reference only its enclosing "
                f"authoritative goal ID {goal_id!r}; found " + ",".join(sorted(foreign_goal_ids))
            )
    if planner_tier == "fast" and len(expected_goal_id_set) > 1:
        if output.goal_satisfaction is None:
            raise ValueError("multi-goal fast output requires model-authored goal_satisfaction")
    if output.goal_satisfaction is not None:
        referenced_goal_ids = {
            *output.goal_satisfaction.satisfied_goal_ids,
            *output.goal_satisfaction.unmet_goal_ids,
        }
        foreign_goal_ids = referenced_goal_ids - expected_goal_id_set
        if foreign_goal_ids:
            raise ValueError(
                "top-level goal satisfaction references non-authoritative goal IDs: "
                + ",".join(sorted(foreign_goal_ids))
            )
    return output


def requires_safety_revision(feedback: list[dict[str, Any]]) -> bool:
    safety_types = {
        "parallel_capability_not_declared_safe",
        "parallel_exclusive_group_conflict",
        "parallel_resource_claim_conflict",
        "safety_revision_contract_not_satisfied",
    }
    return any(
        isinstance(item, dict)
        and item.get("type") in safety_types
        and not (
            item.get("type") == "parallel_capability_not_declared_safe"
            and item.get("parallel_step_count") == 1
        )
        for item in feedback
    )

def requires_sequential_safety_revision(
    feedback: list[dict[str, Any]],
) -> bool:
    concurrency_types = {
        "parallel_capability_not_declared_safe",
        "parallel_exclusive_group_conflict",
        "parallel_resource_claim_conflict",
    }
    return any(
        isinstance(item, dict)
        and item.get("type") in concurrency_types
        and not (
            item.get("type") == "parallel_capability_not_declared_safe"
            and item.get("parallel_step_count") == 1
        )
        for item in feedback
    )

class CapabilityArgumentValidationError(PlannerDTOContractError):
    def __init__(self, feedback: list[dict[str, Any]]) -> None:
        self.feedback = [dict(item) for item in feedback]
        super().__init__(
            json.dumps(
                self.feedback,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        )


class AuthoritativeGroundingValidationError(ValueError):
    """Fast output contradicts or bypasses immutable Goal grounding."""


def planner_validation_error_items(
    exc: Exception,
    *,
    raw: Any,
    planner_tier: PlannerTier,
    expected_goal_ids_for_turn: list[str],
) -> list[dict[str, Any]]:
    if isinstance(exc, CapabilityArgumentValidationError):
        feedback = [dict(item) for item in exc.feedback]
    elif isinstance(exc, ValidationError):
        feedback = list(exc.errors(include_url=False))
    else:
        feedback = [{"type": type(exc).__name__, "message": str(exc)[:1000]}]
    feedback.extend(
        planner_contract_diagnostics(
            raw,
            planner_tier=planner_tier,
            expected_goal_ids_for_turn=expected_goal_ids_for_turn,
        )
    )
    unique: list[dict[str, Any]] = []
    seen: set[tuple[str, tuple[Any, ...]]] = set()
    for item in feedback:
        key = (
            str(item.get("msg") or item.get("message") or ""),
            tuple(item.get("loc") or []),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def planner_validation_error_json(
    exc: Exception,
    *,
    raw: Any,
    planner_tier: PlannerTier,
    expected_goal_ids_for_turn: list[str],
    limit: int = 10000,
) -> str:
    from .prompt_projection import bounded_json

    return bounded_json(
        planner_validation_error_items(
            exc,
            raw=raw,
            planner_tier=planner_tier,
            expected_goal_ids_for_turn=expected_goal_ids_for_turn,
        ),
        limit,
    )


@dataclass(frozen=True)
class FastPlanQualification:
    accepted: bool
    plan: CanonicalPlan
    reason: str = ""
    unresolved: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    path_classification: str = "semantic_escalation"


def qualify_fast_canonical_plan(
    plan: CanonicalPlan,
    *,
    capability_payload: list[dict[str, Any]],
    expected_goal_ids_for_turn: list[str],
    authoritative_goals: list[dict[str, Any]],
    evidence_reentry_goal_ids: set[str],
    min_confidence: float,
) -> FastPlanQualification:
    allowed = {item["capability_id"]: item for item in capability_payload}
    contract_schema = (
        "FastPlannerMultiGoalPlanOutput"
        if len(expected_goal_ids_for_turn) > 1
        else "FastPlannerModelOutput"
    )
    counts = {
        "authoritative_goal_count": len(expected_goal_ids_for_turn),
        "goal_outcome_count": len(plan.goal_outcomes),
        "executable_step_count": len(plan.steps),
    }

    def reject(
        reason: str,
        *,
        unresolved: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> FastPlanQualification:
        return FastPlanQualification(
            accepted=False,
            plan=plan,
            reason=reason,
            unresolved=tuple(unresolved or []),
            metadata={**(metadata or {}), **counts},
        )

    if expected_goal_ids_for_turn and set(plan.goal_ids) != set(expected_goal_ids_for_turn):
        return reject(
            "goal_ids_do_not_match_goal_association",
            metadata={
                "expected_goal_ids": expected_goal_ids_for_turn,
                "actual_goal_ids": list(plan.goal_ids),
            },
        )
    _, requires_execution = planner_goal_execution_requirements(authoritative_goals)
    if evidence_reentry_goal_ids == set(expected_goal_ids_for_turn):
        requires_execution = False
    if (
        requires_execution
        and plan.disposition not in {"escalate", "clarify", "unavailable", "refused"}
        and not plan.steps
    ):
        return reject(
            "canonical_goal_requires_executable_step",
            metadata={"proposed_disposition": plan.disposition},
        )
    if plan.disposition == "escalate":
        metadata = dict(plan.metadata)
        metadata.update(
            {
                "resolver": "fast_planner",
                "status": "escalate",
                "authority": "advisory",
                "path_classification": "semantic_escalation",
                "common_capability_count": len(capability_payload),
                "min_confidence": min_confidence,
                "contract_schema": contract_schema,
                "canonical_contract": "CanonicalPlan",
                **counts,
            }
        )
        return FastPlanQualification(True, plan.model_copy(update={"metadata": metadata}))
    if plan.coverage != "complete" or plan.confidence < min_confidence:
        return reject(
            "coverage_not_complete",
            unresolved=list(plan.unresolved),
            metadata={
                "proposed_coverage": plan.coverage,
                "proposed_confidence": plan.confidence,
            },
        )
    if plan.goal_satisfaction is None or plan.goal_satisfaction.score < 0.95:
        return reject(
            "goal_satisfaction_not_exact",
            unresolved=list(plan.unresolved),
            metadata={
                "proposed_goal_satisfaction": (
                    plan.goal_satisfaction.model_dump(mode="json")
                    if plan.goal_satisfaction
                    else None
                )
            },
        )
    incomplete_outcomes = [
        outcome.goal_id
        for outcome in plan.goal_outcomes
        if outcome.satisfaction is None or outcome.satisfaction.score < 0.95
    ]
    if incomplete_outcomes:
        return reject(
            "per_goal_satisfaction_not_exact",
            unresolved=incomplete_outcomes,
        )
    for step in plan.steps:
        if allowed.get(step.capability_id) is None:
            return reject(
                "step_not_in_executable_common_catalog",
                unresolved=[step.capability_id],
            )
    parallel_errors = parallel_plan_contract_errors(plan, capability_payload)
    if parallel_errors:
        return reject(
            "parallel_execution_contract_unavailable",
            unresolved=[str(item["type"]) for item in parallel_errors],
            metadata={
                "parallel_contract_errors": parallel_errors,
                "execution_allowed": False,
            },
        )
    metadata = dict(plan.metadata)
    metadata.update(
        {
            "resolver": "fast_planner",
            "status": "complete",
            "authority": "advisory",
            "common_capability_count": len(capability_payload),
            "min_confidence": min_confidence,
            "contract_schema": contract_schema,
            "canonical_contract": "CanonicalPlan",
            "path_classification": "terminal",
            **counts,
        }
    )
    return FastPlanQualification(True, plan.model_copy(update={"metadata": metadata}))


def restore_required_capability_args_from_responsibilities(
    raw: dict[str, Any],
    *,
    responsibilities: list[CognitiveResponsibilityProposal],
    capabilities: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Restore omitted required args when GI already owns the exact value.

    The model still owns Capability selection. Once it selects a Capability,
    copying an identically named required input from every cited Responsibility
    is mechanical provenance preservation, not a new HOW decision. Conflicting,
    partial, transformed, optional, or defaulted inputs remain model-owned and
    fail through the normal contract boundary.
    """

    activities = raw.get("activities")
    if not isinstance(activities, list):
        return raw, []
    by_ref = {item.local_ref: item for item in responsibilities}
    by_capability = {
        str(item.get("capability_id") or ""): item
        for item in capabilities
        if isinstance(item, dict) and str(item.get("capability_id") or "")
    }
    normalized = copy.deepcopy(raw)
    normalized_activities = normalized.get("activities")
    if not isinstance(normalized_activities, list):
        return raw, []
    repairs: list[dict[str, Any]] = []
    for activity_index, activity in enumerate(normalized_activities):
        if not isinstance(activity, dict) or activity.get("role") != "capability":
            continue
        capability_id = str(activity.get("capability_id") or "")
        definition = by_capability.get(capability_id)
        if not isinstance(definition, dict):
            continue
        input_schema = definition.get("input_schema")
        if not isinstance(input_schema, dict):
            continue
        properties = input_schema.get("properties")
        if not isinstance(properties, dict):
            properties = {}
        required = [str(item) for item in input_schema.get("required") or []]
        source_refs = [
            str(item)
            for item in activity.get("source_responsibility_refs") or []
            if str(item) in by_ref
        ]
        if not source_refs:
            continue
        args = activity.get("args")
        if not isinstance(args, dict):
            args = {}
        else:
            args = dict(args)
        changed = False
        for parameter in required:
            if parameter in args:
                continue
            parameter_schema = properties.get(parameter)
            if isinstance(parameter_schema, dict) and "default" in parameter_schema:
                continue
            if not all(
                parameter in by_ref[source_ref].bindings
                for source_ref in source_refs
            ):
                continue
            values = [
                by_ref[source_ref].bindings[parameter]
                for source_ref in source_refs
            ]
            first = values[0]
            if any(value != first for value in values[1:]):
                continue
            args[parameter] = copy.deepcopy(first)
            changed = True
            repairs.append(
                {
                    "activity_index": activity_index,
                    "activity_id": str(activity.get("activity_id") or ""),
                    "capability_id": capability_id,
                    "parameter": parameter,
                    "source_responsibility_refs": source_refs,
                    "recovery": "restored_required_arg_from_authoritative_responsibility",
                }
            )
        if changed:
            activity["args"] = args
    return (normalized if repairs else raw), repairs


def validate_fast_advance_output(
    output: FastPlannerAdvanceModelOutput,
    *,
    request: CognitiveWorkRequest,
    responsibilities: list[CognitiveResponsibilityProposal],
    capabilities: list[dict[str, Any]],
) -> None:
    responsibility_refs = [item.local_ref for item in responsibilities]
    if set(output.covered_responsibility_refs) != set(responsibility_refs):
        raise PlannerDTOContractError(
            "Fast Planner must cover exactly the authoritative Responsibility refs"
        )
    by_ref = {item.local_ref: item for item in responsibilities}
    allowed = {item["capability_id"]: item for item in capabilities}
    unresolved_meaning = {
        " ".join(str(item or "").strip().split())
        for item in request.interpretation_unresolved
        if " ".join(str(item or "").strip().split())
    }
    clarification_activities = [
        item for item in output.activities if item.role == "clarification"
    ]
    capability_activities = [
        item for item in output.activities if item.role == "capability"
    ]
    complete_response_activities = [
        item for item in output.activities if item.role == "complete_response"
    ]
    numeric_args_by_ref: dict[str, set[Decimal]] = {
        ref: set() for ref in responsibility_refs
    }
    for activity in capability_activities:
        activity_numbers = semantic_numeric_values(activity.args)
        for source_ref in activity.source_responsibility_refs:
            if source_ref in numeric_args_by_ref:
                numeric_args_by_ref[source_ref].update(activity_numbers)
    for source_ref, source in by_ref.items():
        required_numbers = semantic_numeric_values(source.bindings)
        missing_numbers = sorted(
            required_numbers - numeric_args_by_ref.get(source_ref, set())
        )
        if missing_numbers and any(
            source_ref in activity.source_responsibility_refs
            for activity in capability_activities
        ):
            raise PlannerDTOContractError(
                "Fast Planner Capability args omitted explicit numeric "
                f"Responsibility bindings for {source_ref}: "
                + ",".join(str(value) for value in missing_numbers)
            )
    if output.disposition in {"execute", "respond", "clarify", "mixed"}:
        terminal_roles = {"capability", "complete_response", "clarification"}
        terminal_refs = {
            source_ref
            for activity in output.activities
            if activity.role in terminal_roles
            for source_ref in activity.source_responsibility_refs
        }
        missing_terminal_refs = set(responsibility_refs) - terminal_refs
        if missing_terminal_refs:
            raise PlannerDTOContractError(
                "Fast Planner must supply one terminal Activity for every "
                "authoritative Responsibility before claiming a terminal "
                "disposition; missing="
                + ",".join(sorted(missing_terminal_refs))
            )
    if all(item.completion_requires_fresh_evidence for item in responsibilities) and not (
        clarification_activities
        or complete_response_activities
        or any(item.role == "progress" for item in output.activities)
        or first_response_phase_decided(request)
    ):
        raise PlannerDTOContractError(
            "fresh-evidence Fast work requires a Communicative Main Activity"
        )
    if clarification_activities:
        expected_disposition = "mixed" if capability_activities else "clarify"
        if output.disposition != expected_disposition:
            raise PlannerDTOContractError(
                "clarification disposition must be clarify when it is the only "
                "terminal work, or mixed when independent Capability work proceeds"
            )
        if complete_response_activities and not capability_activities:
            raise PlannerDTOContractError(
                "the current Fast contract cannot combine only response and "
                "clarification outcomes without executable Work"
            )
    all_gap_ids = [
        gap.gap_id
        for activity in clarification_activities
        for gap in activity.information_gaps
    ]
    if len(all_gap_ids) != len(set(all_gap_ids)):
        raise PlannerDTOContractError(
            "Planner InformationGap IDs must be unique across the Activity Plan"
        )
    for activity in output.activities:
        unknown_refs = set(activity.source_responsibility_refs) - set(by_ref)
        if unknown_refs:
            raise PlannerDTOContractError(
                "Fast Planner Activity references unknown Responsibilities: "
                + ",".join(sorted(unknown_refs))
            )
        if activity.role == "complete_response" and any(
            by_ref[ref].completion_requires_fresh_evidence
            for ref in activity.source_responsibility_refs
        ):
            raise PlannerDTOContractError(
                "Fast Planner cannot complete a fresh-evidence Responsibility "
                "before trusted evidence"
            )
        if activity.role == "clarification":
            if output.disposition not in {"clarify", "mixed"}:
                raise PlannerDTOContractError(
                    "a clarification Activity requires disposition=clarify or mixed"
                )
            for gap in activity.information_gaps:
                if gap.source_kind == "unresolved_meaning":
                    if gap.source_reference not in unresolved_meaning:
                        raise PlannerDTOContractError(
                            "semantic clarification must cite exact GI unresolved "
                            f"meaning: {gap.source_reference!r}"
                        )
                    continue
                definition = allowed.get(gap.source_reference)
                if definition is None:
                    raise PlannerDTOContractError(
                        "execution-input clarification must cite an available "
                        f"Capability ID: {gap.source_reference!r}"
                    )
                input_schema = definition.get("input_schema") or {}
                properties = input_schema.get("properties") or {}
                required = set(input_schema.get("required") or [])
                bound_names = {
                    str(name)
                    for ref in activity.source_responsibility_refs
                    for name in by_ref[ref].bindings
                }
                for parameter in gap.required_for:
                    parameter_schema = properties.get(parameter)
                    if parameter not in required or not isinstance(
                        parameter_schema, dict
                    ):
                        raise PlannerDTOContractError(
                            "execution-input clarification may name only required "
                            f"Capability inputs: {gap.source_reference}.{parameter}"
                        )
                    if "default" in parameter_schema:
                        raise PlannerDTOContractError(
                            "Planner cannot ask for an input with a Capability "
                            f"schema default: {gap.source_reference}.{parameter}"
                        )
                    if parameter in bound_names:
                        raise PlannerDTOContractError(
                            "Planner cannot ask for an already-bound input: "
                            f"{parameter}"
                        )
        if activity.role != "capability":
            continue
        definition = allowed.get(activity.capability_id)
        if definition is None:
            raise PlannerDTOContractError(
                f"unknown or unavailable Capability {activity.capability_id!r}"
            )
        for source_ref in activity.source_responsibility_refs:
            source = by_ref[source_ref]
            if source.output_mode not in set(VOCAL_MODES) - {"speech"}:
                continue
            if (
                activity.capability_id != VOCAL_PERFORMANCE_CAPABILITY_ID
                or activity.args.get("mode") != source.output_mode
            ):
                raise PlannerDTOContractError(
                    "Fast Planner must preserve a mode-specific vocal "
                    "Responsibility through the exact qualified vocal provider; "
                    f"source_ref={source_ref} expected_capability="
                    f"{VOCAL_PERFORMANCE_CAPABILITY_ID} expected_mode="
                    f"{source.output_mode} actual_capability="
                    f"{activity.capability_id} actual_mode="
                    f"{activity.args.get('mode')!r}. Ordinary speech, media, and "
                    "body Activities are not completion evidence for that mode."
                )
        schema_errors = validate_args_for_schema(
            activity.args,
            definition.get("input_schema") or {},
        )
        if schema_errors:
            raise PlannerDTOContractError(
                json.dumps(
                    {
                        "activity_id": activity.activity_id,
                        "capability_id": activity.capability_id,
                        "invalid_args": schema_errors[:8],
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
        input_schema = definition.get("input_schema") or {}
        properties = input_schema.get("properties") or {}
        required_inputs = set(input_schema.get("required") or [])
        authoritative_bindings = {
            str(name): value
            for ref in activity.source_responsibility_refs
            for name, value in by_ref[ref].bindings.items()
        }
        for parameter in sorted(required_inputs):
            parameter_schema = properties.get(parameter)
            if not isinstance(parameter_schema, dict):
                continue
            if "default" in parameter_schema:
                continue
            if parameter not in authoritative_bindings:
                raise AuthoritativeGroundingValidationError(
                    "Fast Planner cannot invent an unbound required Capability "
                    f"input before canonical Goal grounding: "
                    f"{activity.capability_id}.{parameter}"
                )
            actual = activity.args.get(parameter)
            expected = authoritative_bindings[parameter]
            if actual != expected and str(actual).strip() != str(expected).strip():
                raise AuthoritativeGroundingValidationError(
                    "Fast Planner required Capability input contradicts GI "
                    f"binding: {activity.capability_id}.{parameter}"
                )


def capability_argument_errors(
    plan: CanonicalPlan,
    capability_payload: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    allowed = {item["capability_id"]: item for item in capability_payload}
    errors: list[dict[str, Any]] = []
    for step in plan.steps:
        capability = allowed.get(step.capability_id)
        if capability is None:
            continue
        schema_errors = validate_args_for_schema(
            step.args,
            capability.get("input_schema") or {},
        )
        if schema_errors:
            errors.append(
                {
                    "type": "invalid_args",
                    "step_id": step.step_id,
                    "capability_id": step.capability_id,
                    "errors": schema_errors[:8],
                }
            )
    return errors


def validate_work_reuse_selection(
    output: Any,
    *,
    context: dict[str, Any] | None,
) -> None:
    """Validate explicit Planner reuse references without choosing reuse.

    Fast Planner owns the semantic decision by either citing a supplied
    provisional Activity ID or omitting it. This check is deliberately
    mechanical: cited IDs must exist and the selected step must preserve
    the Activity's immutable Capability, arguments, and timing. The Host
    later validates canonical Goal ownership and live runtime state.
    """

    raw_activities = (context or {}).get(
        "existing_work_activities"
    )
    activities = (
        [item for item in raw_activities if isinstance(item, dict)]
        if isinstance(raw_activities, list)
        else []
    )
    by_id = {
        str(item.get("activity_id") or "").strip(): item
        for item in activities
        if str(item.get("activity_id") or "").strip()
    }
    cited: set[str] = set()
    for step in output.steps:
        activity_id = str(step.reuse_activity_id or "").strip()
        if not activity_id:
            continue
        if activity_id in cited:
            raise PlannerDTOContractError(
                f"reuse_activity_id is duplicated: {activity_id}"
            )
        cited.add(activity_id)
        activity = by_id.get(activity_id)
        if activity is None:
            raise PlannerDTOContractError(
                f"reuse_activity_id was not supplied by Runtime: {activity_id}"
            )
        if step.capability_id != str(activity.get("capability_id") or ""):
            raise PlannerDTOContractError(
                f"reuse_activity_id {activity_id} changes capability_id"
            )
        if step.args != dict(activity.get("args") or {}):
            raise PlannerDTOContractError(
                f"reuse_activity_id {activity_id} changes immutable args"
            )
        if step.timing != str(activity.get("timing") or "sequential"):
            raise PlannerDTOContractError(
                f"reuse_activity_id {activity_id} changes timing"
            )

    # The supplied reconciliation projection is one bounded snapshot.
    # Reusing any member currently requires selecting every member; extra
    # newly planned steps remain legal and execute beside the reused set.
    if cited and cited != set(by_id):
        raise PlannerDTOContractError(
            "Work reuse must select the complete supplied "
            "Activity set"
        )
    if cited and any(
        by_id[activity_id].get("origin") == "retained_runtime"
        for activity_id in cited
    ) and len(output.steps) != len(cited):
        raise PlannerDTOContractError(
            "retained Runtime Work reuse cannot add steps to the "
            "reconciliation-only Plan"
        )


def merge_planner_feedback(
    *groups: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for group in groups:
        for item in group:
            if not isinstance(item, dict):
                continue
            key = json.dumps(
                item,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            )
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
    return merged


def initial_safety_feedback(
    context: dict[str, Any],
) -> list[dict[str, Any]]:
    """Carry upstream deterministic safety findings into Deep attempt one."""

    candidates: list[dict[str, Any]] = []
    fast_plan = context.get("fast_plan_resolution") or context.get("fast_planner_resolution")
    if isinstance(fast_plan, dict):
        metadata = fast_plan.get("metadata")
        if isinstance(metadata, dict):
            parallel_errors = metadata.get("parallel_contract_errors")
            # A lone step labeled parallel has no overlap relation to
            # revise.  Carry this finding only when Fast actually proposed
            # a multi-step concurrency plan; otherwise Deep may safely
            # regenerate the single step as sequential.
            if (
                isinstance(parallel_errors, list)
                and int(metadata.get("executable_step_count") or 0) > 1
            ):
                candidates.extend(item for item in parallel_errors if isinstance(item, dict))
    runtime_feedback = context.get("runtime_validator_feedback")
    if isinstance(runtime_feedback, list):
        candidates.extend(item for item in runtime_feedback if isinstance(item, dict))
    return [
        dict(item)
        for item in merge_planner_feedback(candidates)
        if requires_safety_revision([item])
    ]


def normalize_mixed_goal_outcome_accounting(
    raw: dict[str, Any],
    *,
    expected_goal_ids: list[str],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Normalize only redundant aggregate fields in an explicit mixed plan.

    Per-Goal outcomes are the semantic authority. When they cover every
    canonical Goal, contain at least two terminal dispositions, and explicitly
    leave some Goals non-executing, top-level ``coverage`` means accounting
    coverage and is therefore mechanically ``complete``. A step that no execute
    outcome references is contradictory DTO residue and cannot be executed; it
    is removed without changing any Goal outcome or inventing replacement work.
    """

    normalized = copy.deepcopy(raw)
    outcomes = normalized.get("goal_outcomes")
    expected = set(expected_goal_ids)
    if not isinstance(outcomes, dict) or set(outcomes) != expected or not expected:
        return normalized, []
    dispositions = {
        str(item.get("disposition") or "").strip()
        for item in outcomes.values()
        if isinstance(item, dict)
    }
    if len(dispositions) < 2 or not dispositions.issubset(
        {"execute", "respond", "clarify", "unavailable", "refused"}
    ):
        return normalized, []
    repairs: list[dict[str, Any]] = []
    if normalized.get("disposition") != "mixed":
        repairs.append(
            {
                "path": "disposition",
                "from": normalized.get("disposition"),
                "to": "mixed",
                "basis": "explicit per-Goal terminal dispositions differ",
            }
        )
        normalized["disposition"] = "mixed"
    if normalized.get("coverage") != "complete":
        repairs.append(
            {
                "path": "coverage",
                "from": normalized.get("coverage"),
                "to": "complete",
                "basis": "every canonical Goal has an explicit terminal outcome",
            }
        )
        normalized["coverage"] = "complete"

    for goal_id, outcome in outcomes.items():
        if not isinstance(outcome, dict):
            continue
        satisfaction = outcome.get("satisfaction")
        if not isinstance(satisfaction, dict) or satisfaction.get("status") != "exact":
            continue
        satisfied = {
            str(item).strip()
            for item in satisfaction.get("satisfied_goal_ids") or []
            if str(item).strip()
        }
        unmet = list(satisfaction.get("unmet_goal_ids") or [])
        retained_unmet = [
            item for item in unmet if str(item).strip() not in satisfied
        ]
        if retained_unmet != unmet:
            repairs.append(
                {
                    "path": f"goal_outcomes.{goal_id}.satisfaction.unmet_goal_ids",
                    "from": unmet,
                    "to": retained_unmet,
                    "basis": "the same Goal cannot be both satisfied and unmet",
                }
            )
            satisfaction["unmet_goal_ids"] = retained_unmet
        unmet_requirements = list(
            satisfaction.get("unmet_requirements") or []
        )
        if unmet_requirements:
            repairs.append(
                {
                    "path": (
                        f"goal_outcomes.{goal_id}.satisfaction."
                        "unmet_requirements"
                    ),
                    "from": unmet_requirements,
                    "to": [],
                    "basis": (
                        "status=exact is the explicit prospective adequacy "
                        "judgment and cannot also carry unmet requirements"
                    ),
                }
            )
            satisfaction["unmet_requirements"] = []

    per_goal_satisfaction = [
        outcome.get("satisfaction")
        for outcome in outcomes.values()
        if isinstance(outcome, dict)
        and isinstance(outcome.get("satisfaction"), dict)
    ]
    aggregate_satisfaction = normalized.get("goal_satisfaction")
    if (
        len(per_goal_satisfaction) == len(expected)
        and isinstance(aggregate_satisfaction, dict)
    ):
        scores = [item.get("score") for item in per_goal_satisfaction]
        if all(
            isinstance(score, (int, float)) and not isinstance(score, bool)
            for score in scores
        ):
            aggregate_score = sum(float(score) for score in scores) / len(scores)
            aggregate_satisfied = list(
                dict.fromkeys(
                    str(goal_id).strip()
                    for item in per_goal_satisfaction
                    for goal_id in item.get("satisfied_goal_ids") or []
                    if str(goal_id).strip()
                )
            )
            aggregate_unmet = list(
                dict.fromkeys(
                    str(goal_id).strip()
                    for item in per_goal_satisfaction
                    for goal_id in item.get("unmet_goal_ids") or []
                    if str(goal_id).strip()
                )
            )
            aggregate_requirements = list(
                dict.fromkeys(
                    " ".join(str(requirement or "").strip().split())
                    for item in per_goal_satisfaction
                    for requirement in item.get("unmet_requirements") or []
                    if " ".join(str(requirement or "").strip().split())
                )
            )
            aggregate_status = (
                "exact"
                if aggregate_score >= 0.95 and not aggregate_unmet and not aggregate_requirements
                else "substantial"
                if aggregate_score >= 0.75
                else "partial"
                if aggregate_score > 0.0
                else "unsatisfied"
            )
            aggregate_projection = {
                "score": aggregate_score,
                "status": aggregate_status,
                "satisfied_goal_ids": aggregate_satisfied,
                "unmet_goal_ids": aggregate_unmet,
                "unmet_requirements": aggregate_requirements,
            }
            changed_fields = {
                field_name: {
                    "from": aggregate_satisfaction.get(field_name),
                    "to": value,
                }
                for field_name, value in aggregate_projection.items()
                if aggregate_satisfaction.get(field_name) != value
            }
            if changed_fields:
                repairs.append(
                    {
                        "path": "goal_satisfaction",
                        "fields": changed_fields,
                        "basis": "deterministic aggregate of explicit per-Goal judgments",
                    }
                )
                aggregate_satisfaction.update(aggregate_projection)

    referenced_execute_steps = {
        str(step_id).strip()
        for outcome in outcomes.values()
        if isinstance(outcome, dict)
        and outcome.get("disposition") == "execute"
        for step_id in outcome.get("step_ids") or []
        if str(step_id).strip()
    }
    execute_owners_by_step: dict[str, list[str]] = {}
    for goal_id, outcome in outcomes.items():
        if not isinstance(outcome, dict) or outcome.get("disposition") != "execute":
            continue
        for step_id in outcome.get("step_ids") or []:
            normalized_step_id = str(step_id).strip()
            if normalized_step_id:
                execute_owners_by_step.setdefault(normalized_step_id, []).append(
                    str(goal_id)
                )
    steps = normalized.get("steps")
    if not isinstance(steps, list):
        return normalized, repairs
    retained: list[Any] = []
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            retained.append(step)
            continue
        step_id = str(step.get("step_id") or "").strip()
        if not step_id or step_id in referenced_execute_steps:
            expected_owners = execute_owners_by_step.get(step_id, [])
            actual_owners = list(step.get("source_goal_ids") or [])
            if step_id and expected_owners and actual_owners != expected_owners:
                repaired_step = dict(step)
                repaired_step["source_goal_ids"] = expected_owners
                repairs.append(
                    {
                        "path": f"steps[{index}].source_goal_ids",
                        "step_id": step_id,
                        "from": actual_owners,
                        "to": expected_owners,
                        "basis": "execute outcomes are the per-Goal ownership authority",
                    }
                )
                retained.append(repaired_step)
                continue
            retained.append(step)
            continue
        repairs.append(
            {
                "path": f"steps[{index}]",
                "step_id": step_id,
                "reason": "not_referenced_by_any_execute_outcome",
            }
        )
    normalized["steps"] = retained
    return normalized, repairs


def validate_mechanical_numeric_revision_preserved(
    candidate: dict[str, Any],
    *,
    baseline: dict[str, Any],
) -> None:
    """Reject any semantic rewrite during a provenance-only DTO repair."""

    changed = sorted(
        field_name
        for field_name in set(candidate).union(baseline)
        if field_name != "parameter_resolutions"
        and candidate.get(field_name) != baseline.get(field_name)
    )
    if changed:
        raise PlannerDTOContractError(
            "mechanical numeric provenance repair changed semantic plan fields: "
            + ",".join(changed)
        )


def safety_revision_contract_errors(
    plan: CanonicalPlan,
    feedback: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Enforce the decoder's safety-revision grammar at runtime too."""

    if not requires_safety_revision(feedback):
        return []
    if plan.disposition in {"clarify", "unavailable", "refused"}:
        return (
            []
            if not plan.steps
            else [
                {
                    "type": "safety_revision_contract_not_satisfied",
                    "reason": "non-executable safety revision retained plan steps",
                }
            ]
        )
    relation = str(plan.metadata.get("plan_relation") or "exact")
    confirmation = plan.metadata.get("user_confirmation_required") is True
    retained_parallel_steps = [step.step_id for step in plan.steps if step.timing == "parallel"]
    if requires_sequential_safety_revision(feedback) and retained_parallel_steps:
        return [
            {
                "type": "safety_revision_contract_not_satisfied",
                "plan_relation": relation,
                "parallel_step_ids": retained_parallel_steps,
                "reason": (
                    "concurrency was rejected, so a safe revision cannot "
                    "retain parallel step timing"
                ),
            }
        ]
    if (
        plan.disposition in {"execute", "mixed"}
        and relation in {"safe_adjustment", "alternative"}
        and confirmation
        and bool(plan.response_text.strip())
    ):
        return []
    return [
        {
            "type": "safety_revision_contract_not_satisfied",
            "disposition": plan.disposition,
            "plan_relation": relation,
            "user_confirmation_required": confirmation,
            "response_text_present": bool(plan.response_text.strip()),
            "reason": (
                "after concurrency safety rejection, execution requires an "
                "explicit safe_adjustment or alternative, explanatory "
                "response_text, and user confirmation"
            ),
        }
    ]



def detached_numeric_provenance_obligations(
    raw: Any,
    *,
    authoritative_goals: list[dict[str, Any]],
    error: Exception,
) -> list[dict[str, Any]]:
    """Identify only unambiguous missing duplicate numeric provenance rows."""

    if (
        "explicit numeric goal value has no matching user_supplied "
        "parameter resolution" not in str(error)
        or not isinstance(raw, dict)
    ):
        return []
    numeric_by_goal = explicit_numeric_goal_values(authoritative_goals)
    outcomes = raw.get("goal_outcomes")
    steps = raw.get("steps")
    resolutions = raw.get("parameter_resolutions")
    if not isinstance(steps, list):
        return []
    outcomes = outcomes if isinstance(outcomes, dict) else {}
    resolutions = resolutions if isinstance(resolutions, list) else []
    step_owned_goal_ids = {
        str(goal_id)
        for step in steps
        if isinstance(step, dict)
        for goal_id in step.get("source_goal_ids") or []
        if str(goal_id).strip()
    }

    def numeric(value: Any) -> float | None:
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            return None
        try:
            return float(str(value).strip())
        except ValueError:
            return None

    obligations: list[dict[str, Any]] = []
    for goal_id, values in numeric_by_goal.items():
        outcome = outcomes.get(goal_id)
        if isinstance(outcome, dict):
            if outcome.get("disposition") != "execute":
                continue
        elif goal_id not in step_owned_goal_ids:
            continue
        for value in values:
            candidates: list[tuple[str, str]] = []
            for step in steps:
                if not isinstance(step, dict) or goal_id not in (
                    step.get("source_goal_ids") or []
                ):
                    continue
                step_id = " ".join(str(step.get("step_id") or "").strip().split())
                args = step.get("args")
                if not step_id or not isinstance(args, dict):
                    continue
                for parameter, argument in args.items():
                    argument_number = numeric(argument)
                    if argument_number is None:
                        continue
                    scale = max(abs(float(value)), abs(argument_number), 1.0)
                    if abs(float(value) - argument_number) <= 1e-12 * scale:
                        candidates.append((step_id, str(parameter)))
            if len(candidates) != 1:
                return []
            step_id, parameter = candidates[0]
            already_present = any(
                isinstance(resolution, dict)
                and str(resolution.get("strategy") or "") == "user_supplied"
                and str(resolution.get("step_id") or "").strip() == step_id
                and str(resolution.get("parameter") or "").strip() == parameter
                and resolution.get("source_goal_ids") == [goal_id]
                and numeric(resolution.get("value")) is not None
                and abs(
                    float(value)
                    - float(numeric(resolution.get("value")) or 0.0)
                )
                <= 1e-12 * max(abs(float(value)), 1.0)
                for resolution in resolutions
            )
            if already_present:
                continue
            obligations.append(
                {
                    "step_id": step_id,
                    "parameter": parameter,
                    "value": value,
                    "source_goal_ids": [goal_id],
                }
            )
    return obligations


def deep_validation_error_items(
    exc: Exception,
    *,
    raw: Any,
    expected_goal_ids_for_turn: list[str],
    capability_payload: list[dict[str, Any]] | None = None,
    authoritative_goals: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if isinstance(exc, ValidationError):
        feedback = list(exc.errors(include_url=False))
    else:
        feedback = [
            {
                "type": "canonical_plan_contract_validation_failure",
                "error_type": type(exc).__name__,
                "message": str(exc)[:1000],
            }
        ]
    feedback.extend(
        planner_contract_diagnostics(
            raw,
            planner_tier="deep",
            expected_goal_ids_for_turn=expected_goal_ids_for_turn,
        )
    )
    if isinstance(raw, dict):
        schemas = {
            str(item.get("capability_id") or ""): item.get("input_schema") or {}
            for item in list(capability_payload or [])
        }
        steps = {
            str(item.get("step_id") or ""): item
            for item in raw.get("steps") or []
            if isinstance(item, dict) and str(item.get("step_id") or "").strip()
        }
        for resolution in raw.get("parameter_resolutions") or []:
            if not isinstance(resolution, dict):
                continue
            step_id = str(resolution.get("step_id") or "").strip()
            parameter = str(resolution.get("parameter") or "").strip()
            step = steps.get(step_id)
            if not parameter or not isinstance(step, dict):
                continue
            args = step.get("args") if isinstance(step.get("args"), dict) else {}
            if parameter in args:
                continue
            capability_id = str(step.get("capability_id") or "").strip()
            feedback.append(
                {
                    "type": "parameter_resolution_argument_mismatch",
                    "step_id": step_id,
                    "capability_id": capability_id,
                    "parameter": parameter,
                    "resolution_value": resolution.get("value"),
                    "resolution_strategy": resolution.get("strategy"),
                    "source_goal_ids": list(resolution.get("source_goal_ids") or []),
                    "actual_arg_keys": sorted(args),
                    "capability_input_schema": schemas.get(capability_id, {}),
                    "corrective_contract": (
                        "A nonblocking parameter_resolution must name an argument "
                        "present in the referenced step args with the same value. "
                        "If the value came from an authoritative Goal, use strategy "
                        "user_supplied. Regenerate a schema-valid consistent step "
                        "and resolution or return a non-executable clarification; "
                        "do not describe an absent argument only in prose."
                    ),
                }
            )
        if "no matching user_supplied parameter resolution" in str(exc):
            for resolution in raw.get("parameter_resolutions") or []:
                if not isinstance(resolution, dict):
                    continue
                if str(resolution.get("strategy") or "") == "user_supplied":
                    continue
                value = resolution.get("value")
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    continue
                step_id = str(resolution.get("step_id") or "").strip()
                step = steps.get(step_id)
                if not isinstance(step, dict):
                    continue
                feedback.append(
                    {
                        "type": "explicit_numeric_resolution_strategy_mismatch",
                        "step_id": step_id,
                        "capability_id": str(
                            step.get("capability_id") or ""
                        ).strip(),
                        "parameter": str(
                            resolution.get("parameter") or ""
                        ).strip(),
                        "resolution_value": value,
                        "actual_strategy": resolution.get("strategy"),
                        "source_goal_ids": list(
                            resolution.get("source_goal_ids") or []
                        ),
                        "corrective_contract": (
                            "A numeric value copied from an authoritative Goal "
                            "must use strategy user_supplied, equal the referenced "
                            "step argument, and cite that Goal in source_goal_ids."
                        ),
                    }
                )
        if "numeric user_supplied parameter resolution is not present" in str(exc):
            for resolution in raw.get("parameter_resolutions") or []:
                if not isinstance(resolution, dict):
                    continue
                if str(resolution.get("strategy") or "") != "user_supplied":
                    continue
                step_id = str(resolution.get("step_id") or "").strip()
                step = steps.get(step_id)
                if not isinstance(step, dict):
                    continue
                capability_id = str(step.get("capability_id") or "").strip()
                parameter = str(resolution.get("parameter") or "").strip()
                parameter_schema = (
                    schemas.get(capability_id, {})
                    .get("properties", {})
                    .get(parameter, {})
                )
                feedback.append(
                    {
                        "type": "unsupported_user_supplied_provenance",
                        "step_id": step_id,
                        "capability_id": capability_id,
                        "parameter": parameter,
                        "resolution_value": resolution.get("value"),
                        "source_goal_ids": list(
                            resolution.get("source_goal_ids") or []
                        ),
                        "catalog_parameter_schema": parameter_schema,
                        "corrective_contract": (
                            "This value is absent from every cited owning Goal. "
                            "Never borrow a sibling Goal's quantity. If the owning "
                            "Goal omitted this optional parameter, omit the argument "
                            "and resolution, or use the exact catalog default with "
                            "strategy schema_default and no source_goal_ids."
                        ),
                    }
                )
        for obligation in detached_numeric_provenance_obligations(
            raw,
            authoritative_goals=list(authoritative_goals or []),
            error=exc,
        ):
            feedback.append(
                {
                    "type": "missing_user_supplied_parameter_resolution",
                    **obligation,
                    "corrective_contract": (
                        "The semantic mapping already exists in exactly one owned "
                        "step argument. Preserve the plan meaning and add one "
                        "nonblocking parameter_resolution with this exact step_id, "
                        "parameter, numeric value, strategy=user_supplied, and sole "
                        "source Goal. Do not add, remove, or substitute work."
                    ),
                }
            )
    unique: list[dict[str, Any]] = []
    seen: set[tuple[str, tuple[Any, ...]]] = set()
    for item in feedback:
        message = str(item.get("msg") or item.get("message") or "")
        location = tuple(item.get("loc") or [])
        key = (
            message
            or json.dumps(
                item,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ),
            location,
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def deep_plan_validation_errors(
    plan: CanonicalPlan,
    capabilities: list[dict[str, Any]],
    *,
    expected_goal_ids: list[str],
    authoritative_goals: list[dict[str, Any]],
    min_confidence: float,
    min_goal_satisfaction: float,
) -> list[dict[str, Any]]:
    allowed = {item["capability_id"]: item for item in capabilities}
    errors: list[dict[str, Any]] = []
    if expected_goal_ids and set(plan.goal_ids) != set(expected_goal_ids):
        errors.append(
            {
                "type": "goal_ids_do_not_match_goal_association",
                "expected_goal_ids": expected_goal_ids,
                "actual_goal_ids": list(plan.goal_ids),
            }
        )
    _, requires_execution = planner_goal_execution_requirements(
        authoritative_goals
    )
    if (
        requires_execution
        and plan.disposition not in {"clarify", "unavailable", "refused"}
        and not plan.steps
    ):
        errors.append(
            {
                "type": "canonical_goal_requires_executable_step",
                "disposition": plan.disposition,
            }
        )
    if plan.coverage == "complete" and plan.confidence < min_confidence:
        errors.append(
            {
                "type": "confidence_below_threshold",
                "confidence": plan.confidence,
                "required": min_confidence,
            }
        )
    if plan.coverage == "complete":
        if plan.goal_satisfaction is None:
            errors.append({"type": "missing_goal_satisfaction"})
        elif (
            plan.disposition != "mixed"
            and plan.goal_satisfaction.score < min_goal_satisfaction
        ):
            errors.append(
                {
                    "type": "goal_satisfaction_below_threshold",
                    "score": plan.goal_satisfaction.score,
                    "required": min_goal_satisfaction,
                }
            )
    if plan.disposition == "mixed":
        for outcome in plan.goal_outcomes:
            if outcome.disposition not in {"execute", "respond"}:
                continue
            # The complete aggregate satisfaction object and exact keyed
            # outcome map already express prospective adequacy. Per-outcome
            # satisfaction is useful when the model supplies it, but is not
            # a second mandatory copy of the same judgment. Treat a supplied
            # low score as authoritative without failing solely on omission.
            if (
                outcome.satisfaction is not None
                and outcome.satisfaction.score < min_goal_satisfaction
            ):
                errors.append(
                    {
                        "type": "goal_outcome_satisfaction_below_threshold",
                        "goal_id": outcome.goal_id,
                        "score": outcome.satisfaction.score,
                        "required": min_goal_satisfaction,
                    }
                )
    step_ids = {step.step_id for step in plan.steps}
    for resolution in plan.parameter_resolutions:
        if resolution.step_id not in step_ids and not resolution.blocking:
            errors.append(
                {
                    "type": "parameter_resolution_unknown_step",
                    "step_id": resolution.step_id,
                    "parameter": resolution.parameter,
                }
            )
        if resolution.blocking and plan.disposition == "execute":
            errors.append(
                {
                    "type": "blocking_parameter_resolution",
                    "step_id": resolution.step_id,
                    "parameter": resolution.parameter,
                }
            )
    for step in plan.steps:
        capability = allowed.get(step.capability_id)
        if capability is None:
            errors.append(
                {
                    "type": "unknown_capability",
                    "step_id": step.step_id,
                    "capability_id": step.capability_id,
                }
            )
            continue
        if not capability.get("available") or not capability.get("interaction_executable"):
            errors.append(
                {
                    "type": "capability_not_executable",
                    "step_id": step.step_id,
                    "capability_id": step.capability_id,
                }
            )
            continue
        schema_errors = validate_args_for_schema(
            step.args, capability.get("input_schema") or {}
        )
        if schema_errors:
            errors.append(
                {
                    "type": "invalid_args",
                    "step_id": step.step_id,
                    "capability_id": step.capability_id,
                    "errors": schema_errors[:8],
                }
            )
    errors.extend(parallel_plan_contract_errors(plan, capabilities))
    return errors

def validated_fail_safe_progress(
    raw_output: Any,
    *,
    responsibility_refs: list[str],
) -> list[FastPlannerProgressAct]:
    """Retain independently valid, non-terminal progress from an invalid Plan.

    Progress carries no result, completion, Capability, or execution claim.  The
    invalid Plan wrapper and every terminal Activity remain discarded.  Exact
    duplicates are collapsed so one malformed model response cannot schedule
    repeated audible acknowledgements.
    """

    if not isinstance(raw_output, dict):
        return []
    allowed_refs = set(responsibility_refs)
    retained: list[FastPlannerProgressAct] = []
    seen: set[tuple[Any, ...]] = set()
    for candidate in raw_output.get("activities") or []:
        if not isinstance(candidate, dict) or candidate.get("role") != "progress":
            continue
        try:
            activity = FastPlannerProgressAct.model_validate(candidate)
        except ValidationError:
            continue
        refs = set(activity.source_responsibility_refs)
        if not refs or not refs.issubset(allowed_refs):
            continue
        key = (
            activity.progress_kind,
            activity.speech_act,
            activity.text,
            activity.timing,
            tuple(sorted(refs)),
        )
        if key in seen:
            continue
        seen.add(key)
        retained.append(activity)
    return retained
