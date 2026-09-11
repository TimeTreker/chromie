from __future__ import annotations

"""Deterministic Goal Association normalization, grounding, and conservation checks.

This module does not invoke a model or commit Goal continuity.
"""

import copy
import json
from typing import Any

from pydantic import ValidationError

from .prompt_projection import required_json
from .goal_association_contract import (
    GoalAssociationModelGoal,
    GoalAssociationModelOutput,
    GoalSegmentationModelOutput,
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


def normalize_resource_binding_branches(
    raw: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Normalize model content from a resource Goal's inactive binding branch.

    Resource Goals have one semantic owner: ``resource_responsibility``. Some
    structured-output models nevertheless populate the mutually exclusive top-
    level ``bindings`` branch. Move nonduplicate model-authored bindings into the
    discriminated resource owner before clearing the inactive branch. This is
    mechanical DTO normalization: no value is inferred or rewritten, and trusted
    source-grounded conservation validation still checks that every material fact
    belongs to the primary Responsibility result.
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
            # Do not erase a malformed branch before the DTO can reject it.
            continue
        resource = goal.get("resource_responsibility")
        if not isinstance(resource, dict):
            continue
        kind = str(resource.get("kind") or "").strip()
        if kind not in {"information", "physical_object"}:
            continue
        if kind == "information":
            binding_owner = resource
            binding_key = "query_scope"
            target = resource.get("query_scope")
        else:
            source = resource.get("source")
            binding_owner = source if isinstance(source, dict) else None
            binding_key = "acquisition_bindings"
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
            raise ValueError(
                f"new_goals[{index}] inactive physical source contains authored bindings"
            )
        if not top_level:
            continue
        if binding_owner is None:
            raise ValueError(f"new_goals[{index}] has no resource binding destination")
        if binding_key in binding_owner and not isinstance(target, list):
            raise ValueError(f"new_goals[{index}] has a malformed active resource binding branch")
        if target is None:
            target = []
            binding_owner[binding_key] = target
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


def inherited_goal_outcomes(goal: GoalAssociationModelGoal, request: CognitiveWorkRequest) -> list[str]:
    """Read WHAT from the exact admitted Responsibility references, never GA prose."""
    by_ref = {item.local_ref: item.outcome for item in request.responsibilities}
    refs = goal.source_responsibility_refs
    if not refs or len(refs) != len(set(refs)) or any(ref not in by_ref for ref in refs):
        raise ValueError("new Goal requires exact unique GI Responsibility references")
    return [by_ref[ref] for ref in refs]


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
                    if source_name
                    in {
                        "date",
                        "period",
                        "time",
                        "time_period",
                        "time_scope",
                        "temporal_period",
                        "temporal_scope",
                    }
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
                    and name
                    in {
                        "date",
                        "period",
                        "time",
                        "time_period",
                        "time_scope",
                        "temporal_period",
                        "temporal_scope",
                    }
                    and entity_type
                    in {
                        "date",
                        "period",
                        "time",
                        "time_period",
                        "time_scope",
                        "temporal_period",
                    }
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


def source_grounded_binding_conservation_conflicts(
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
    Numeric/boolean GI scalars are already typed authoritative values; conserve
    them even when their original surface was a word (for example, "twice").
    Context-normalized strings absent from the literal turn remain governed by
    their dedicated temporal/referent contracts.
    """

    authoritative_turn = " ".join(request.text.strip().casefold().split())
    expected_by_ref: dict[str, set[tuple[str, str]]] = {}

    def scalar_values(value: Any) -> set[str]:
        if isinstance(value, (int, float, bool)):
            return {_canonical_source_binding_value("", value)}
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
            if isinstance(raw_value, (int, float, bool))
            or value in authoritative_turn
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
                "; ".join(inherited_goal_outcomes(goal, request)).strip().casefold().split()
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
                "; ".join(inherited_goal_outcomes(goal, request)).strip().casefold().split()
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
                    "entity",
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


def is_mechanical_contract_failure(exc: ValidationError) -> bool:
    """Only recognized shape errors may enter the one DTO regeneration.

    Semantic validators also raise ValidationError. Missing meaning, invalid
    values, and mixed failures must not authorize another semantic decision.
    Unknown error types fail closed rather than expanding repair eligibility.
    """
    errors = exc.errors(include_url=False)
    return bool(errors) and all(
        error["type"] in {"list_type", "dict_type"}
        for error in errors
    )


def validation_error_json(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        payload: Any = exc.errors(include_url=False)
    else:
        payload = [{"type": type(exc).__name__, "message": str(exc)[:1000]}]
    return required_json(payload, 6000, label="GA mechanical validation errors")


def mechanical_repair_projection(raw: dict[str, Any], exc: ValidationError) -> dict[str, Any]:
    """Project only unambiguous container corrections, preserving every value.

    Unknown fields, missing meaning and null/scalar containers are not removable
    noise. The caller validates this complete projection before a repair call.
    """
    if not is_mechanical_contract_failure(exc):
        raise ValueError("GA primary errors do not permit mechanical repair")
    projected = copy.deepcopy(raw)
    for error in exc.errors(include_url=False):
        path = error["loc"]
        parent: Any = projected
        if not path:
            raise ValueError("GA mechanical repair has no concrete field path")
        for part in path[:-1]:
            if isinstance(parent, dict) and part in parent:
                parent = parent[part]
            elif isinstance(parent, list) and isinstance(part, int) and 0 <= part < len(parent):
                parent = parent[part]
            else:
                raise ValueError("GA mechanical repair path is not recoverable")
        key = path[-1]
        if not isinstance(parent, dict) or key not in parent:
            raise ValueError("GA mechanical repair requires one existing container field")
        value = parent[key]
        if error["type"] == "list_type" and isinstance(value, dict):
            parent[key] = [value]
        elif error["type"] == "dict_type" and isinstance(value, list) and len(value) == 1 and isinstance(value[0], dict):
            parent[key] = value[0]
        else:
            raise ValueError("GA malformed container has no lossless representation")
    return projected


def require_repair_semantic_preservation(expected: dict[str, Any], actual: dict[str, Any]) -> None:
    """Compare parsed content, not semantic equivalence or model assurances.

    Object key order is immaterial. Values, explicit fields, array order and
    cardinality remain exact, including information in optional fields.
    """
    def encode(value: dict[str, Any]) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)

    if encode(expected) != encode(actual):
        raise ValueError("GA repair semantic_preservation failed: authored content changed")
