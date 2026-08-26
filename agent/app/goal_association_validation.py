from __future__ import annotations

"""Deterministic Goal Association normalization, grounding, conflict, and coverage checks.

This module does not invoke a model or commit Goal continuity.
"""

import copy
import json
from typing import Any, Literal

from pydantic import ValidationError

from .prompt_projection import bounded_json
from .goal_association_contract import (
    GoalAssociationModelGoal,
    GoalAssociationModelOutput,
    GoalResponsibilityCoverageCertificate,
    GoalSegmentationModelOutput,
    _validate_model_resource_quantity,
)

try:
    from chromie_contracts.core_interpretation import CognitiveWorkRequest
except ImportError:  # pragma: no cover
    from shared.chromie_contracts.core_interpretation import CognitiveWorkRequest


def _normalized_binding_name(value: Any) -> str:
    return "_".join(
        str(value).strip().casefold().replace("-", "_").split()
    )


def _canonical_source_binding_value(name: Any, value: Any) -> str:
    normalized_name = _normalized_binding_name(name)
    normalized_value = " ".join(str(value).strip().casefold().split())
    if normalized_name == "speed":
        return {
            "slowly": "slow",
            "quickly": "quick",
        }.get(normalized_value, normalized_value)
    if value is True:
        return "true"
    if value is False:
        return "false"
    return normalized_value


def _ordinary_source_binding_pairs(
    request: CognitiveWorkRequest,
) -> dict[str, set[tuple[str, str]]]:
    return {
        responsibility.local_ref: {
            (
                _normalized_binding_name(name),
                _canonical_source_binding_value(name, value),
            )
            for name, value in responsibility.bindings.items()
            if isinstance(value, (str, int, float, bool))
            and _normalized_binding_name(name)
            not in {"action", "activity", "effect", "outcome"}
        }
        for responsibility in request.responsibilities
    }


class _CoverageSourceExcerptViolation(ValueError):
    """Coverage audit cited text outside the authoritative user turn."""


def normalize_optional_referent_updates(
    raw: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Drop only semantically unusable optional referent-index updates.

    Referent focus changes, retirements, and introductions with actual entity
    content remain contract-authoritative and still fail closed. A correction
    without any supplied target referent cannot update the discourse index; the
    canonical Goal association and coverage audit remain responsible for the
    actual correction meaning.
    A model-added ``introduce`` item with neither an entity type nor canonical
    value cannot ground any Goal binding and must not discard otherwise valid
    Goals.
    """

    normalized = copy.deepcopy(raw)
    updates = normalized.get("referent_updates")
    if not isinstance(updates, list):
        return normalized, []
    kept: list[Any] = []
    dropped: list[dict[str, Any]] = []
    for index, item in enumerate(updates):
        if not isinstance(item, dict):
            kept.append(item)
            continue
        operation = str(item.get("operation") or "").strip()
        entity_type = str(item.get("entity_type") or "").strip()
        canonical_value = str(item.get("canonical_value") or "").strip()
        target_referent_ids = item.get("target_referent_ids") or []
        target_goal_ids = item.get("target_goal_ids") or []
        if (
            operation == "introduce"
            and not entity_type
            and not canonical_value
            and not target_referent_ids
            and not target_goal_ids
        ):
            dropped.append(
                {
                    "path": f"referent_updates[{index}]",
                    "operation": "introduce",
                    "reason": "missing_entity_type_and_canonical_value",
                }
            )
            continue
        if operation == "correct" and not target_referent_ids:
            dropped.append(
                {
                    "path": f"referent_updates[{index}]",
                    "operation": "correct",
                    "reason": "missing_target_referent_ids",
                }
            )
            continue
        kept.append(item)
    normalized["referent_updates"] = kept
    return normalized, dropped


def normalize_resource_binding_branches(
    raw: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Normalize model content from a resource Goal's inactive binding branch.

    Resource Goals have one semantic owner: ``resource_responsibility``. Some
    structured-output models nevertheless populate the mutually exclusive top-
    level ``bindings`` branch. Move nonduplicate model-authored bindings into the
    discriminated resource owner before clearing the inactive branch. This is
    mechanical DTO normalization: no value is inferred or rewritten, and the
    independent source-grounded coverage certificate still decides whether each
    migrated fact belongs to the Responsibility.
    """

    normalized = copy.deepcopy(raw)
    goals = normalized.get("new_goals")
    if not isinstance(goals, list):
        return normalized, []

    dropped: list[dict[str, Any]] = []
    for index, goal in enumerate(goals):
        if not isinstance(goal, dict):
            continue
        top_level = goal.get("bindings")
        if not isinstance(top_level, list):
            top_level = []
        resource = goal.get("resource_responsibility")
        if not isinstance(resource, dict):
            continue
        kind = str(resource.get("kind") or "").strip()
        if kind not in {"information", "physical_object"}:
            continue
        if kind == "information":
            target = resource.get("query_scope")
        else:
            source = resource.get("source")
            target = (
                source.get("acquisition_bindings")
                if isinstance(source, dict)
                else None
            )
        physical_source_unknown = bool(
            kind == "physical_object"
            and isinstance(resource.get("source"), dict)
            and resource["source"].get("status") != "known"
        )
        has_inactive_physical_grounding = bool(
            physical_source_unknown
            and isinstance(target, list)
            and target
        )
        if physical_source_unknown and (top_level or has_inactive_physical_grounding):
            # `status` is the discriminant: unknown/provider-resolved sources
            # cannot own acquisition grounding. Clear model content from that
            # inactive branch so the independent semantic coverage audit can
            # decide whether the entire resource wrapper was justified. Never
            # flip unknown to known or reinterpret body-motion parameters as an
            # object-acquisition location.
            source = resource["source"]
            existing = source.pop("acquisition_bindings", [])
            goal["bindings"] = []
            dropped.append(
                {
                    "path": f"new_goals[{index}].bindings",
                    "resource_kind": kind,
                    "binding_count": len(top_level),
                    "migrated_count": 0,
                    "inactive_acquisition_binding_count": (
                        len(existing) if isinstance(existing, list) else 0
                    ),
                    "reason": "unknown_physical_source_has_no_grounding_branch",
                }
            )
            continue
        if not top_level:
            continue
        if not isinstance(target, list):
            target = []
            if kind == "information":
                resource["query_scope"] = target
            elif isinstance(resource.get("source"), dict):
                resource["source"]["acquisition_bindings"] = target
        fingerprints = {
            json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            for item in target
        }
        migrated_count = 0
        for binding in top_level:
            fingerprint = json.dumps(
                binding,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            if fingerprint in fingerprints:
                continue
            target.append(copy.deepcopy(binding))
            fingerprints.add(fingerprint)
            migrated_count += 1
        goal["bindings"] = []
        dropped.append(
            {
                "path": f"new_goals[{index}].bindings",
                "resource_kind": kind,
                "binding_count": len(top_level),
                "migrated_count": migrated_count,
                "reason": "normalized_into_active_resource_binding_branch",
            }
        )
    return normalized, dropped


def normalize_optional_resource_quantity(
    raw: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Drop only malformed optional quantity scalars before validation.

    No replacement quantity is inferred. Responsibility coverage still proves
    conservation of any source-grounded quantity, so removing decoder noise
    cannot silently erase a quantity the human actually supplied.
    """

    normalized = copy.deepcopy(raw)
    goals = normalized.get("new_goals")
    if not isinstance(goals, list):
        return normalized, []
    dropped: list[dict[str, Any]] = []
    for index, goal in enumerate(goals):
        if not isinstance(goal, dict):
            continue
        resource = goal.get("resource_responsibility")
        if not isinstance(resource, dict) or "quantity" not in resource:
            continue
        value = resource.get("quantity")
        if value is None or value == "":
            continue
        try:
            if not isinstance(value, str):
                raise ValueError("quantity is not a string")
            _validate_model_resource_quantity(value.strip())
        except (TypeError, ValueError):
            resource.pop("quantity", None)
            dropped.append(
                {
                    "path": (
                        f"new_goals[{index}].resource_responsibility.quantity"
                    ),
                    "reason": "invalid_optional_quantity_scalar",
                    "input_type": type(value).__name__,
                }
            )
    return normalized, dropped


def restore_missing_goal_descriptions(
    raw: dict[str, Any],
    *,
    request: CognitiveWorkRequest,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Restore a mechanically omitted description from its exact source outcome.

    The source Responsibility remains the semantic authority.  Recovery is
    permitted only when the candidate names exactly one admitted local_ref and
    its description is absent or blank; no wording is generated or inferred.
    Responsibility/output-mode conservation and the independent coverage audit
    still validate the resulting Goal.
    """

    normalized = copy.deepcopy(raw)
    outcomes = {
        item.local_ref: item.outcome
        for item in request.responsibilities
        if item.local_ref and item.outcome
    }
    recovered: list[dict[str, Any]] = []
    goals = normalized.get("new_goals")
    if not isinstance(goals, list):
        return normalized, recovered
    for index, goal in enumerate(goals):
        if not isinstance(goal, dict):
            continue
        if str(goal.get("description") or "").strip():
            continue
        source_refs = goal.get("source_responsibility_refs")
        if not isinstance(source_refs, list) or len(source_refs) != 1:
            continue
        source_ref = str(source_refs[0] or "").strip()
        outcome = outcomes.get(source_ref)
        if not outcome:
            continue
        goal["description"] = outcome
        recovered.append(
            {
                "path": f"new_goals[{index}].description",
                "source_responsibility_ref": source_ref,
                "semantic_value_unchanged": True,
            }
        )
    return normalized, recovered


def drop_ungrounded_resource_query_locations(
    raw: dict[str, Any],
    *,
    request: CognitiveWorkRequest,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Drop an invented optional query location without choosing a replacement.

    This restores Responsibility conservation before validation.  Coverage
    remains responsible for rejecting the Goal when location was actually
    material, so the normalization cannot silently satisfy missing meaning.
    """

    normalized = copy.deepcopy(raw)
    authoritative_turn = " ".join(request.text.strip().split()).casefold()
    grounded_values = {
        " ".join(str(value).strip().split()).casefold()
        for responsibility in request.responsibilities
        for value in responsibility.bindings.values()
        if str(value).strip()
    }
    resolved_values = {
        " ".join(str(item.get("resolved_value") or "").strip().split()).casefold()
        for item in normalized.get("resolved_references") or []
        if isinstance(item, dict)
        and str(item.get("resolved_value") or "").strip()
    }
    location_types = {
        "address",
        "city",
        "country",
        "county",
        "location",
        "place",
        "region",
    }
    dropped: list[dict[str, Any]] = []
    goals = normalized.get("new_goals")
    if not isinstance(goals, list):
        return normalized, dropped
    for goal_index, goal in enumerate(goals):
        if not isinstance(goal, dict):
            continue
        resource = goal.get("resource_responsibility")
        if not isinstance(resource, dict) or resource.get("kind") != "information":
            continue
        query_scope = resource.get("query_scope")
        if not isinstance(query_scope, list):
            continue
        kept: list[Any] = []
        for binding_index, binding in enumerate(query_scope):
            if not isinstance(binding, dict):
                kept.append(binding)
                continue
            name = "_".join(
                str(binding.get("name") or "")
                .strip()
                .casefold()
                .replace("-", "_")
                .split()
            )
            entity_type = "_".join(
                str(binding.get("entity_type") or "")
                .strip()
                .casefold()
                .replace("-", "_")
                .split()
            )
            value = " ".join(
                str(binding.get("value") or "").strip().split()
            ).casefold()
            is_location = name == "location" or entity_type in location_types
            grounded = bool(
                value
                and (
                    value in authoritative_turn
                    or value in grounded_values
                    or value in resolved_values
                )
            )
            if (
                not is_location
                or str(binding.get("referent_id") or "").strip()
                or grounded
            ):
                kept.append(binding)
                continue
            dropped.append(
                {
                    "path": (
                        f"new_goals[{goal_index}].resource_responsibility."
                        f"query_scope[{binding_index}]"
                    ),
                    "name": str(binding.get("name") or ""),
                    "entity_type": str(binding.get("entity_type") or ""),
                    "value": str(binding.get("value") or ""),
                    "reason": "not_entailed_by_turn_responsibility_or_referent",
                }
            )
        resource["query_scope"] = kept
    return normalized, dropped


def normalize_grounded_binding_types(
    raw: dict[str, Any],
    *,
    request: CognitiveWorkRequest,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Canonicalize only source-grounded spatial/temporal DTO type labels.

    The model already owns the semantic field name and exact value. This adapter
    changes neither; this replaces only a mechanically non-canonical type/name
    pair after the value is proven by the authoritative turn, GI bindings, or an
    admitted resolved reference. Provider-facing temporal realization remains a
    Planner responsibility.
    """

    normalized = copy.deepcopy(raw)
    authoritative_turn = " ".join(request.text.strip().split()).casefold()
    grounded_values = {
        " ".join(str(value).strip().split()).casefold()
        for responsibility in request.responsibilities
        for value in responsibility.bindings.values()
        if str(value).strip()
    }
    grounded_values.update(
        " ".join(str(item.get("resolved_value") or "").strip().split()).casefold()
        for item in normalized.get("resolved_references") or []
        if isinstance(item, dict)
        and str(item.get("resolved_value") or "").strip()
    )
    ordinary_pairs_by_ref = _ordinary_source_binding_pairs(request)
    generic_types = {"entity", "string", "text"}
    repaired: list[dict[str, Any]] = []
    goals = normalized.get("new_goals")
    if not isinstance(goals, list):
        return normalized, repaired
    for goal_index, goal in enumerate(goals):
        if not isinstance(goal, dict):
            continue
        goal_source_refs = {
            str(source_ref)
            for source_ref in goal.get("source_responsibility_refs") or []
        }
        expected_ordinary_pairs = {
            pair
            for source_ref in goal_source_refs
            for pair in ordinary_pairs_by_ref.get(source_ref, set())
        }
        source_names_by_value: dict[str, set[str]] = {}
        for source_name, source_value in expected_ordinary_pairs:
            source_names_by_value.setdefault(source_value, set()).add(source_name)
        surfaces: list[tuple[str, Any]] = [("bindings", goal.get("bindings"))]
        resource = goal.get("resource_responsibility")
        if isinstance(resource, dict):
            if resource.get("kind") == "information":
                surfaces.append(("resource.query_scope", resource.get("query_scope")))
            source = resource.get("source")
            if isinstance(source, dict):
                surfaces.append(
                    (
                        "resource.source.acquisition_bindings",
                        source.get("acquisition_bindings"),
                    )
                )
        for surface_name, bindings in surfaces:
            if not isinstance(bindings, list):
                continue
            for binding_index, binding in enumerate(bindings):
                if not isinstance(binding, dict):
                    continue
                name = "_".join(
                    str(binding.get("name") or "")
                    .strip()
                    .casefold()
                    .replace("-", "_")
                    .split()
                )
                entity_type = "_".join(
                    str(binding.get("entity_type") or "")
                    .strip()
                    .casefold()
                    .replace("-", "_")
                    .split()
                )
                value = " ".join(
                    str(binding.get("value") or "").strip().split()
                ).casefold()
                grounded = bool(
                    value
                    and (
                        value in authoritative_turn
                        or value in grounded_values
                    )
                )
                source_pair_grounded = (
                    name,
                    value,
                ) in expected_ordinary_pairs
                source_names_for_value = source_names_by_value.get(value, set())
                if (
                    surface_name == "resource.query_scope"
                    and name == "location"
                    and len(source_names_for_value) == 1
                    and "location" not in source_names_for_value
                ):
                    # The provider preserved one exact authoritative GI value but
                    # attached the wrong query-scope label. Project the unique
                    # source binding name; no source-language meaning is inferred.
                    source_name = next(iter(source_names_for_value))
                    canonical_type = (
                        "temporal_scope"
                        if source_name in {"date", "time", "temporal_scope"}
                        else source_name
                    )
                    binding["name"] = source_name
                    binding["entity_type"] = canonical_type
                    repaired.append(
                        {
                            "path": (
                                f"new_goals[{goal_index}].{surface_name}"
                                f"[{binding_index}]"
                            ),
                            "from": f"{name}/{entity_type}",
                            "to": f"{source_name}/{canonical_type}",
                            "value_unchanged": True,
                            "source_pair_grounded": True,
                        }
                    )
                    continue
                if surface_name == "bindings" and source_pair_grounded:
                    canonical_type: str | None = None
                    if name == "direction" and entity_type in {
                        "spatial_direction",
                        *generic_types,
                    }:
                        canonical_type = "direction"
                    elif name in {"duration", "duration_seconds"} and entity_type in {
                        "integer",
                        "number",
                        "temporal_scope",
                        "time_duration",
                        *generic_types,
                    }:
                        canonical_type = "duration"
                    elif name == "speed" and entity_type in {
                        "manner",
                        *generic_types,
                    }:
                        canonical_type = "speed"
                    elif name in {
                        "amount",
                        "count",
                        "item_count",
                        "quantity",
                        "quantity_binding",
                        "resource_count",
                        "resource_quantity",
                    } and entity_type in {"integer", "number", *generic_types}:
                        canonical_type = name
                    if canonical_type is not None:
                        binding["entity_type"] = canonical_type
                        repaired.append(
                            {
                                "path": (
                                    f"new_goals[{goal_index}].{surface_name}"
                                    f"[{binding_index}].entity_type"
                                ),
                                "from": entity_type,
                                "to": canonical_type,
                                "value_unchanged": True,
                                "source_pair_grounded": True,
                            }
                        )
                        continue
                if (
                    surface_name == "resource.query_scope"
                    and name in {"date", "time", "temporal_scope"}
                    and entity_type in {"date", "period", "time"}
                    and grounded
                ):
                    binding["entity_type"] = "temporal_scope"
                    repaired.append(
                        {
                            "path": (
                                f"new_goals[{goal_index}].{surface_name}"
                                f"[{binding_index}].entity_type"
                            ),
                            "from": entity_type,
                            "to": "temporal_scope",
                            "value_unchanged": True,
                        }
                    )
                    continue
                if (
                    name == "location_relative"
                    and entity_type == "location_relative"
                    and grounded
                ):
                    binding["name"] = "location"
                    binding["entity_type"] = "relative_location"
                    repaired.append(
                        {
                            "path": (
                                f"new_goals[{goal_index}].{surface_name}"
                                f"[{binding_index}]"
                            ),
                            "from": "location_relative/location_relative",
                            "to": "location/relative_location",
                            "value_unchanged": True,
                        }
                    )
                    continue
                if (
                    name != "location"
                    or entity_type not in generic_types
                    or not grounded
                ):
                    continue
                binding["entity_type"] = "place"
                repaired.append(
                    {
                        "path": (
                            f"new_goals[{goal_index}].{surface_name}"
                            f"[{binding_index}].entity_type"
                        ),
                        "from": entity_type,
                        "to": "place",
                        "value_unchanged": True,
                    }
                )
    return normalized, repaired


def action_collection_bindings(
    model_output: GoalAssociationModelOutput | GoalSegmentationModelOutput,
) -> list[str]:
    rejected: list[str] = []
    for goal_index, goal in enumerate(model_output.new_goals):
        for binding in goal.semantic_bindings:
            entity_type = "_".join(
                binding.entity_type.strip().casefold().replace("-", "_").split()
            )
            if "action" in entity_type and (
                "list" in entity_type
                or "set" in entity_type
                or "group" in entity_type
                or "collection" in entity_type
            ):
                rejected.append(
                    f"new_goals[{goal_index}].bindings[{binding.name}]="
                    f"{binding.entity_type}"
                )
    return rejected


def responsibility_output_mode_conflicts(
    model_output: GoalAssociationModelOutput | GoalSegmentationModelOutput,
    *,
    request: CognitiveWorkRequest,
) -> list[str]:
    expected = {
        item.local_ref: item.output_mode
        for item in request.responsibilities
        if item.output_mode != "unspecified"
    }
    conflicts: list[str] = []
    for goal_index, goal in enumerate(model_output.new_goals):
        for source_ref in goal.source_responsibility_refs:
            required = expected.get(source_ref)
            if required is None or goal.output_mode == required:
                continue
            conflicts.append(
                f"new_goals[{goal_index}] source_ref={source_ref} "
                f"expected={required} actual={goal.output_mode}"
            )
    return conflicts


def binding_semantic_contract_conflicts(
    model_output: GoalAssociationModelOutput | GoalSegmentationModelOutput,
) -> list[str]:
    """Reject contradictions between model-authored canonical binding fields.

    This does not infer a parameter from user wording. It only prevents a DTO
    from calling the same binding a different or non-canonical parameter kind,
    such as ``name=distance`` with ``entity_type=quantity`` or the generic
    ``measurement`` label. The decoder already exposes this exact invariant;
    runtime validation keeps it fail-closed when a provider ignores the clause.
    """

    categories = {
        "distance": {"distance"},
        "direction": {"direction"},
        "duration": {"duration", "duration_seconds"},
        "quantity": {
            "amount",
            "count",
            "item_count",
            "quantity",
            "quantity_binding",
            "resource_count",
            "resource_quantity",
        },
        "speed": {"speed"},
    }
    category_by_token = {
        token: category
        for category, tokens in categories.items()
        for token in tokens
    }
    conflicts: list[str] = []
    for goal_index, goal in enumerate(model_output.new_goals):
        for binding_index, binding in enumerate(goal.semantic_bindings):
            name = "_".join(
                binding.name.strip().casefold().replace("-", "_").split()
            )
            entity_type = "_".join(
                binding.entity_type.strip()
                .casefold()
                .replace("-", "_")
                .split()
            )
            name_category = category_by_token.get(name)
            type_category = category_by_token.get(entity_type)
            if name_category is not None and type_category != name_category:
                conflicts.append(
                    f"new_goals[{goal_index}].bindings[{binding_index}]="
                    f"{binding.name}/{binding.entity_type}"
                )
    return conflicts


def resource_source_binding_contract_conflicts(
    model_output: GoalAssociationModelOutput | GoalSegmentationModelOutput,
) -> list[str]:
    """Report invalid model-declared links from a resource to source evidence.

    This is a typed integrity check over fields the model already authored. It
    does not infer a source, binding, parameter, or value from user wording.
    It prevents the resource's identity, requested amount, recipient, or delivery
    mode from being relabelled as the place/source from which that resource should
    be acquired. A focused model revision remains responsible for semantic repair.
    """

    non_source_names = {
        "amount",
        "count",
        "delivery_mode",
        "delivery_recipient",
        "desired_item",
        "item",
        "item_count",
        "object",
        "quantity",
        "recipient",
        "resource",
        "resource_count",
        "resource_description",
        "resource_identity",
        "resource_kind",
        "resource_quantity",
        "target_item",
    }
    identity_or_quantity_types = {
        "amount",
        "count",
        "item",
        "object",
        "physical_object",
        "quantity",
        "resource",
        "resource_identity",
        "resource_kind",
    }
    explicit_source_names = {
        "direction",
        "distance",
        "location",
        "origin",
        "path",
        "place",
        "provider",
        "route",
        "source",
        "source_location",
        "source_provider",
        "spatial_offset",
    }
    spatial_source_types = {
        "direction",
        "distance",
        "location",
        "place",
        "relative_location",
        "route",
    }

    conflicts: list[str] = []
    for goal_index, goal in enumerate(model_output.new_goals):
        resource = goal.resource_responsibility
        if resource is None:
            continue
        if resource.kind != "physical_object":
            continue
        for binding in resource.source.acquisition_bindings:
            source_name = binding.name
            normalized_name = "_".join(
                binding.name.strip().casefold().replace("-", "_").split()
            )
            normalized_type = "_".join(
                binding.entity_type.strip()
                .casefold()
                .replace("-", "_")
                .split()
            )
            if (
                normalized_name in non_source_names
                or normalized_name not in explicit_source_names
                or normalized_type not in spatial_source_types
                or (
                    normalized_type in identity_or_quantity_types
                    and normalized_name not in explicit_source_names
                )
            ):
                conflicts.append(
                    f"new_goals[{goal_index}].resource_responsibility."
                    f"source.acquisition_bindings[{source_name}]="
                    f"non_source_semantics({binding.name}/{binding.entity_type})"
                )
    return conflicts


def source_grounded_binding_coverage_conflicts(
    model_output: (
        GoalAssociationModelOutput
        | GoalSegmentationModelOutput
        | list[GoalAssociationModelGoal]
    ),
    *,
    request: CognitiveWorkRequest,
) -> list[str]:
    """Conserve direct GI material values on their one typed Goal surface.

    Goal Interpretation already owns whether a value is material WHAT. This
    check does not infer a parameter kind from the utterance; it follows the
    model-authored source_responsibility_refs and verifies that directly
    source-grounded values did not disappear. The Goal description is the
    authoritative owner of the action/effect itself, while bindings own its
    material parameters; an exact source action retained in that description
    therefore does not need a redundant ``action`` binding.
    Context-normalized values absent from the literal turn remain governed by
    their dedicated temporal/referent contracts.
    """

    authoritative_turn = " ".join(request.text.strip().casefold().split())
    expected_by_ref: dict[str, set[tuple[str, str]]] = {}

    def scalar_values(value: Any) -> set[str]:
        if isinstance(value, str):
            normalized = " ".join(value.strip().casefold().split())
            return {normalized} if normalized else set()
        if isinstance(value, dict):
            return {
                item
                for nested in value.values()
                for item in scalar_values(nested)
            }
        if isinstance(value, (list, tuple)):
            return {
                item
                for nested in value
                for item in scalar_values(nested)
            }
        return set()

    for responsibility in request.responsibilities:
        expected_by_ref[responsibility.local_ref] = {
            (
                _normalized_binding_name(name),
                value,
            )
            for name, raw_value in responsibility.bindings.items()
            for value in scalar_values(raw_value)
            if value in authoritative_turn
        }

    conflicts: list[str] = []
    goals = model_output if isinstance(model_output, list) else model_output.new_goals
    for goal_index, goal in enumerate(goals):
        expected_pairs = {
            pair
            for source_ref in goal.source_responsibility_refs
            for pair in expected_by_ref.get(source_ref, set())
        }
        if not expected_pairs:
            continue
        resource = goal.resource_responsibility
        if resource is None:
            ordinary_expected_pairs = {
                (name, _canonical_source_binding_value(name, value))
                for name, value in expected_pairs
            }
            actual_pairs = {
                (
                    _normalized_binding_name(binding.name),
                    " ".join(binding.value.strip().casefold().split()),
                )
                for binding in goal.semantic_bindings
            }
            normalized_description = " ".join(
                goal.description.strip().casefold().split()
            )
            actual_pairs.update(
                (name, value)
                for name, value in ordinary_expected_pairs
                if name in {"action", "activity", "effect", "outcome"}
                and value in normalized_description
            )
            missing_pairs = ordinary_expected_pairs - actual_pairs
        elif resource.kind == "information":
            actual = {
                " ".join(binding.value.strip().casefold().split())
                for binding in resource.query_scope
            }
            actual.update(
                scalar_values(resource.quantity)
            )
            actual.update(scalar_values(resource.recipient.description))
            if resource.source.status == "known":
                actual.update(scalar_values(resource.source.source_name))
            missing_pairs = {
                pair for pair in expected_pairs if pair[1] not in actual
            }
        else:
            actual = {
                " ".join(binding.value.strip().casefold().split())
                for binding in resource.source.acquisition_bindings
            }
            normalized_description = " ".join(
                goal.description.strip().casefold().split()
            )
            normalized_resource_description = " ".join(
                resource.description.strip().casefold().split()
            )
            actual.update(
                value
                for name, value in expected_pairs
                if name in {"action", "activity", "effect", "outcome"}
                and value in normalized_description
            )
            actual.update(
                value
                for name, value in expected_pairs
                if name
                in {
                    "desired_item",
                    "item",
                    "object",
                    "resource",
                    "resource_identity",
                    "target_item",
                }
                and value in normalized_resource_description
            )
            actual.update(
                value
                for name, value in expected_pairs
                if name in {"amount", "count", "quantity", "resource_quantity"}
                and value in scalar_values(resource.quantity)
            )
            actual.update(
                value
                for name, value in expected_pairs
                if name in {"recipient", "delivery_recipient"}
                and value in scalar_values(resource.recipient.description)
            )
            missing_pairs = {
                pair for pair in expected_pairs if pair[1] not in actual
            }
        for _, missing in sorted(missing_pairs):
            conflicts.append(
                f"new_goals[{goal_index}] source_refs="
                f"{','.join(goal.source_responsibility_refs)} missing={missing!r}"
            )
    return conflicts


def non_verbatim_explicit_location_bindings(
    model_output: GoalAssociationModelOutput | GoalSegmentationModelOutput,
    *,
    request: CognitiveWorkRequest,
) -> list[str]:
    """Reject ungrounded rewrites of directly named locations.

    Indirect references keep their resolved canonical value and provenance.
    A new location without referent provenance, however, came from the current
    explicit user turn and must remain source-grounded user language after
    whitespace normalization.  This prevents a model translation or
    transliteration from silently changing which real place a provider sees.
    """

    authoritative_turn = " ".join(request.text.strip().split()).casefold()
    resolved_values = {
        (item.entity_type.casefold(), item.resolved_value.casefold())
        for item in model_output.resolved_references
    }
    rejected: list[str] = []
    canonical_location_types = {
        "address",
        "city",
        "country",
        "county",
        "geographic",
        "location",
        "place",
        "relative_location",
        "region",
    }
    for goal_index, goal in enumerate(model_output.new_goals):
        for binding in goal.semantic_bindings:
            name = "_".join(
                binding.name.strip().casefold().replace("-", "_").split()
            )
            entity_type = "_".join(
                binding.entity_type.strip().casefold().replace("-", "_").split()
            )
            if name != "location" and entity_type not in {
                "address",
                "city",
                "country",
                "county",
                "geographic",
                "location",
                "place",
                "region",
            }:
                continue
            if name == "location" and entity_type not in canonical_location_types:
                rejected.append(
                    f"new_goals[{goal_index}].bindings[{binding.name}]="
                    f"non_location_semantics({binding.entity_type!r})"
                )
                continue
            if binding.referent_id or (
                binding.entity_type.casefold(),
                binding.value.casefold(),
            ) in resolved_values:
                continue
            value = " ".join(binding.value.strip().split()).casefold()
            if value not in authoritative_turn:
                rejected.append(
                    f"new_goals[{goal_index}].bindings[{binding.name}]="
                    f"{binding.value!r}"
                )
    return rejected


def validation_error_json(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        payload: Any = exc.errors(include_url=False)
    else:
        payload = [{"type": type(exc).__name__, "message": str(exc)[:1000]}]
    return bounded_json(payload, 6000)


def responsibility_coverage_required(
    model_output: GoalAssociationModelOutput | GoalSegmentationModelOutput,
    *,
    request: CognitiveWorkRequest,
) -> bool:
    """Audit every newly proposed Goal set and no association-only branch.

    This is a structural transition, not a Host semantic risk heuristic.
    Association-only results have no candidate new-Goal set for this certificate
    to prove.
    """

    del request
    return bool(model_output.new_goals)


def coverage_verdict(
    certificate: GoalResponsibilityCoverageCertificate,
    *,
    goal_count: int,
) -> tuple[Literal["accept", "reject"], list[str]]:
    problems: list[str] = []
    responsibility_owner_counts: dict[int, int] = {}
    positively_owned: set[int] = set()
    for item in certificate.items:
        if item.role in {"responsibility", "constraint"} and item.coverage not in {
            "covered",
            "clarification_required",
        }:
            problems.append(
                f"{item.coverage}:{item.role}:{item.source_excerpt}"
            )
            # Preserve the auditor's typed semantic proof as feedback for the
            # one already-authorized fresh interpretation.  The Host does not
            # infer these facts from user wording; it only forwards fields the
            # GA-owned coverage model explicitly declared.
            if item.required_goal_shape != "ordinary":
                problems.append(
                    "required_goal_shape:"
                    + item.required_goal_shape
                    + f":{item.role}:{item.source_excerpt}"
                )
            if item.required_information_domain != "none":
                problems.append(
                    "required_information_domain:"
                    + item.required_information_domain
                    + f":{item.role}:{item.source_excerpt}"
                )
            if item.required_output_mode != "none":
                problems.append(
                    "required_output_mode:"
                    + item.required_output_mode
                    + f":{item.role}:{item.source_excerpt}"
                )
        if item.role != "responsibility" or item.coverage not in {
            "covered",
            "clarification_required",
        }:
            continue
        for goal_index in item.candidate_goal_indices:
            positively_owned.add(goal_index)
            if item.independently_satisfiable:
                responsibility_owner_counts[goal_index] = (
                    responsibility_owner_counts.get(goal_index, 0) + 1
                )
    for goal_index, count in sorted(responsibility_owner_counts.items()):
        if count > 1:
            problems.append(
                f"overmerged_independent_responsibilities:goal[{goal_index}]"
            )
    unjustified = sorted(set(range(max(0, goal_count))) - positively_owned)
    if unjustified:
        problems.append(
            "unjustified_goal_indices:"
            + ",".join(str(index) for index in unjustified)
        )
    return ("reject", problems) if problems else ("accept", [])
