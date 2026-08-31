"""Constrained-decoder schema construction for Goal Association model DTOs.

This module has no model client, Goal state, or continuity decision lifecycle.
"""

from __future__ import annotations

import copy
from typing import Any, Literal

from .goal_association_contract import (
    GoalAssociationModelGoal,
    GoalAssociationModelOutput,
    GoalSegmentationModelOutput,
)


def _decoder_binding_value(name: Any, value: Any) -> str:
    """Project an already-typed GI value into the Goal binding vocabulary."""

    normalized_name = "_".join(
        str(name).strip().casefold().replace("-", "_").split()
    )
    normalized_value = " ".join(str(value).strip().casefold().split())
    if normalized_name == "speed":
        canonical_speed = {
            "slowly": "slow",
            "quickly": "quick",
        }.get(normalized_value)
        if canonical_speed is not None:
            return canonical_speed
    if value is True:
        return "true"
    if value is False:
        return "false"
    return str(value)


def _prune_unreferenced_definitions(schema: dict[str, Any]) -> dict[str, Any]:
    """Remove decoder definitions unreachable from the active schema graph."""

    result = copy.deepcopy(schema)
    definitions = result.get("$defs")
    if not isinstance(definitions, dict):
        return result

    def referenced_definitions(node: Any) -> set[str]:
        references: set[str] = set()
        if isinstance(node, dict):
            ref = node.get("$ref")
            prefix = "#/$defs/"
            if isinstance(ref, str) and ref.startswith(prefix):
                references.add(ref[len(prefix) :].split("/", 1)[0])
            for key, value in node.items():
                if key != "$defs":
                    references.update(referenced_definitions(value))
        elif isinstance(node, list):
            for value in node:
                references.update(referenced_definitions(value))
        return references

    reachable = referenced_definitions(
        {key: value for key, value in result.items() if key != "$defs"}
    )
    pending = list(reachable)
    while pending:
        name = pending.pop()
        nested = referenced_definitions(definitions.get(name))
        for referenced_name in nested - reachable:
            reachable.add(referenced_name)
            pending.append(referenced_name)
    result["$defs"] = {
        name: definition
        for name, definition in definitions.items()
        if name in reachable
    }
    return result


def goal_association_response_schema(
    output_type: (
        type[GoalAssociationModelOutput] | type[GoalSegmentationModelOutput]
    ),
    candidate_goals: list[dict[str, Any]],
    discourse_referents: list[dict[str, Any]],
    *,
    responsibility_count: int | None = None,
    responsibility_refs: list[str] | None = None,
    responsibility_output_modes: dict[str, str] | None = None,
    responsibility_information_refs: set[str] | None = None,
    responsibility_bindings: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    schema = copy.deepcopy(output_type.model_json_schema())
    active_ids = [
        " ".join(str(item.get("goal_id") or "").strip().split())
        for item in candidate_goals
        if " ".join(str(item.get("goal_id") or "").strip().split())
    ]
    referent_ids = [
        " ".join(str(item.get("referent_id") or "").strip().split())
        for item in discourse_referents
        if " ".join(str(item.get("referent_id") or "").strip().split())
    ]
    gap_ids = [
        " ".join(str(gap.get("gap_id") or "").strip().split())
        for goal in candidate_goals
        for gap in (goal.get("open_information_gaps") or [])
        if isinstance(gap, dict)
        and " ".join(str(gap.get("gap_id") or "").strip().split())
    ]
    responsibility_refs = list(responsibility_refs or [])
    responsibility_output_modes = dict(responsibility_output_modes or {})
    responsibility_information_refs = set(
        responsibility_information_refs or set()
    )
    responsibility_bindings = {
        str(source_ref): dict(bindings)
        for source_ref, bindings in (responsibility_bindings or {}).items()
    }
    properties = schema.get("properties", {})
    new_goals = properties.get("new_goals")
    if isinstance(new_goals, dict):
        new_goals["maxItems"] = (
            8
            if responsibility_count is None
            else min(8, max(0, int(responsibility_count)))
        )
    if not referent_ids:
        resolved_references = properties.get("resolved_references")
        if isinstance(resolved_references, dict):
            resolved_references["maxItems"] = 0

    def constrain(node: Any) -> None:
        if isinstance(node, dict):
            node_properties = node.get("properties")
            if isinstance(node_properties, dict):
                source_refs = node_properties.get("source_responsibility_refs")
                if isinstance(source_refs, dict):
                    required_fields = list(node.get("required") or [])
                    if "source_responsibility_refs" not in required_fields:
                        required_fields.append("source_responsibility_refs")
                    node["required"] = required_fields
                    source_refs["items"] = {
                        "type": "string",
                        "enum": responsibility_refs,
                    }
                    source_refs["uniqueItems"] = True
                    if responsibility_refs:
                        source_refs["minItems"] = 1
                    if "relationship" in node_properties:
                        # Association confidence is model evidence used by the
                        # fail-closed commit threshold. A DTO default of 0.0 is
                        # not evidence and must never silently discard an
                        # otherwise correct continuity decision.
                        required_fields = list(node.get("required") or [])
                        for field in ("target_goal_ids", "confidence"):
                            if field not in required_fields:
                                required_fields.append(field)
                        node["required"] = required_fields
                related_field = node_properties.get("related_goal_ids")
                if isinstance(related_field, dict):
                    items = related_field.get("items")
                    if isinstance(items, dict):
                        if active_ids:
                            items["type"] = "string"
                            items["enum"] = active_ids
                        else:
                            related_field["maxItems"] = 0
                target_ids = node_properties.get("target_goal_ids")
                if isinstance(target_ids, dict):
                    target_ids["items"] = {
                        "type": "string",
                        "enum": active_ids,
                    }
                    target_ids["uniqueItems"] = True
                    if "relationship" in node_properties and active_ids:
                        # Every association addresses retained Goal state.
                        # An empty array can never satisfy the DTO, so expose
                        # that mechanical fact to the structured decoder.
                        target_ids["minItems"] = 1
                target_referents = node_properties.get("target_referent_ids")
                if isinstance(target_referents, dict):
                    target_referents["items"] = {
                        "type": "string",
                        "enum": referent_ids,
                    }
                    target_referents["uniqueItems"] = True
                resolved_gaps = node_properties.get("resolved_gap_ids")
                if isinstance(resolved_gaps, dict):
                    if gap_ids:
                        resolved_gaps["items"] = {
                            "type": "string",
                            "enum": gap_ids,
                        }
                        resolved_gaps["uniqueItems"] = True
                    else:
                        resolved_gaps["maxItems"] = 0
                referent_id = node_properties.get("referent_id")
                if isinstance(referent_id, dict):
                    referent_id["type"] = "string"
                    referent_id["enum"] = ["", *referent_ids]
            if node.get("type") == "object":
                node["additionalProperties"] = False
            for value in node.values():
                constrain(value)
        elif isinstance(node, list):
            for value in node:
                constrain(value)

    constrain(schema)
    association_schema = schema.get("$defs", {}).get(
        "GoalAssociationModelAssociation"
    )
    if isinstance(association_schema, dict):
        # Pydantic rejects a modify/clarify association whose semantic update
        # exists only in reason_summary, but the generated decoder schema used
        # to permit exactly that shape.  Expose the existing DTO invariant at
        # the earliest structured-output boundary so the primary invocation
        # must author the update instead of relying on a semantic repair call.
        association_schema.setdefault("allOf", []).append(
            {
                "if": {
                    "properties": {
                        "relationship": {
                            "enum": ["modify", "clarify"],
                        }
                    },
                    "required": ["relationship"],
                },
                "then": {
                    "anyOf": [
                        {
                            "properties": {
                                "updated_description": {
                                    "type": "string",
                                    "minLength": 1,
                                }
                            },
                            "required": ["updated_description"],
                        },
                        {
                            "properties": {
                                "resolved_gap_ids": {
                                    "type": "array",
                                    "minItems": 1,
                                }
                            },
                            "required": ["resolved_gap_ids"],
                        },
                    ]
                },
            }
        )
    recipient_schema = schema.get("$defs", {}).get(
        "GoalAssociationModelResourceRecipient"
    )
    if isinstance(recipient_schema, dict):
        recipient_properties = recipient_schema.setdefault("properties", {})
        recipient_properties["referent_id"] = (
            {
                "anyOf": [
                    {"type": "string", "enum": referent_ids},
                    {"type": "null"},
                ]
            }
            if referent_ids
            else {"type": "null"}
        )
        recipient_properties["description"] = {
            "type": "string",
            "minLength": 1,
            "description": (
                "Human-facing recipient meaning. Copy an explicit current-turn "
                "recipient surface exactly; use requester only when no explicit "
                "recipient or supplied discourse referent exists."
            ),
        }
    # Apply the canonical binding clauses before copying the binding schema into
    # Responsibility-specific oneOf branches.  Applying them only to ``$defs``
    # after those copies are built leaves the active constrained-decoder branch
    # without the same name/type invariant enforced by runtime validation.
    schema = binding_semantic_contract_response_schema(schema)
    goal_schema = schema.get("$defs", {}).get("GoalAssociationModelGoal")
    if isinstance(goal_schema, dict) and responsibility_refs:
        # Every writable Goal-semantic surface must be explicit in the
        # constrained model output. Defaults on these fields are Python DTO
        # conveniences, not permission for the model to drop GI-grounded
        # bindings or silently avoid deciding the resource branch.
        goal_required = list(
            dict.fromkeys(
                [
                    "source_responsibility_refs",
                    "output_mode",
                    "resource_kind",
                    "description",
                    "bindings",
                    "resource_responsibility",
                    *(goal_schema.get("required") or []),
                ]
            )
        )
        goal_schema["required"] = goal_required
        source_refs_schema = goal_schema.get("properties", {}).get(
            "source_responsibility_refs"
        )
        if isinstance(source_refs_schema, dict):
            source_refs_schema["minItems"] = 1
            source_refs_schema["maxItems"] = 1
        goal_properties = goal_schema.get("properties")
        branch_goal_properties = (
            copy.deepcopy(goal_properties)
            if isinstance(goal_properties, dict)
            else {}
        )

        def expected_source_bindings(source_ref: str) -> list[tuple[str, str]]:
            return [
                (
                    " ".join(str(name).strip().split()),
                    _decoder_binding_value(name, value),
                )
                for name, value in responsibility_bindings.get(
                    source_ref, {}
                ).items()
                if " ".join(str(name).strip().split())
                and "_".join(
                    str(name).strip().casefold().replace("-", "_").split()
                )
                not in {"action", "activity", "effect", "outcome"}
            ]

        def exact_binding_array_schema(
            base: dict[str, Any],
            expected_bindings: list[tuple[str, str]],
            *,
            entity_type_by_name: dict[str, str] | None = None,
        ) -> dict[str, Any]:
            constrained = copy.deepcopy(base)
            constrained["minItems"] = len(expected_bindings)
            constrained["maxItems"] = len(expected_bindings)
            binding_item_template = copy.deepcopy(
                schema.get("$defs", {}).get("GoalAssociationModelBinding") or {}
            )
            binding_branches: list[dict[str, Any]] = []
            for name, value in expected_bindings:
                binding_branch = copy.deepcopy(binding_item_template)
                binding_properties = binding_branch.setdefault("properties", {})
                binding_properties["name"] = {"const": name}
                binding_properties["value"] = {"const": value}
                normalized_name = "_".join(
                    name.strip().casefold().replace("-", "_").split()
                )
                canonical_entity_type = {
                    "after": "sequence_ref",
                    "before": "sequence_ref",
                    "count": "count",
                    "direction": "direction",
                    "distance": "distance",
                    "duration": "duration",
                    "parallel_with": "sequence_ref",
                    "quantity": "quantity",
                    "speed": "speed",
                    **(entity_type_by_name or {}),
                }.get(normalized_name)
                if canonical_entity_type is not None:
                    binding_properties["entity_type"] = {
                        "const": canonical_entity_type
                    }
                binding_branch["required"] = list(
                    dict.fromkeys(
                        [
                            *(binding_branch.get("required") or []),
                            "name",
                            "value",
                            "entity_type",
                            "confidence",
                        ]
                    )
                )
                binding_branches.append(binding_branch)
            # Each expected source binding is already ordered by the accepted
            # Responsibility DTO.  A free oneOf item grammar plus ``contains``
            # allowed the deployed structured decoder to repeat one legal row
            # and omit another (for example two ``name`` rows and no ``value``
            # row).  Positional branches make the complete closed projection
            # visible at the decoder boundary; no semantic value or type is
            # invented here.  Keep ``items`` schema-valued even though
            # ``maxItems`` prevents a suffix: Ollama 0.32's guided parser does
            # not accept the JSON Schema boolean form ``items: false``.
            constrained["prefixItems"] = binding_branches
            constrained["items"] = (
                {"oneOf": copy.deepcopy(binding_branches)}
                if binding_branches
                else copy.deepcopy(binding_item_template)
            )
            constrained["uniqueItems"] = True
            constrained["allOf"] = [
                {
                    "contains": {
                        "type": "object",
                        "properties": {
                            "name": {"const": name},
                            "value": {"const": value},
                        },
                        "required": ["name", "value"],
                    },
                    "minContains": 1,
                }
                for name, value in expected_bindings
            ]
            return constrained

        def branch_properties(
            source_ref: str,
            *,
            resource_variant: Literal[
                "ordinary", "physical_object", "information", "unbounded"
            ],
        ) -> dict[str, Any]:
            """Return the complete, output-mode-compatible Goal surface.

            ``resource_responsibility`` is required so the decoder must make
            the resource decision explicitly, but Pydantic's default schema
            lists the object union before ``null``.  Ollama's constrained
            decoder consequently biased ordinary effects toward fabricated
            resources.  Keep semantic selection model-owned while removing
            impossible resource kinds and putting the ordinary ``null`` branch
            first.  ``body_action`` remains free to select a real physical
            acquisition, and ``information`` remains free to select a real
            information responsibility.
            """

            properties = copy.deepcopy(branch_goal_properties)
            output_mode = responsibility_output_modes.get(source_ref)
            properties["resource_kind"] = {
                "const": (
                    "none" if resource_variant == "ordinary" else resource_variant
                ),
                "description": (
                    "Choose the semantic resource shape before authoring its payload. "
                    "none means the outcome is not resource acquisition or delivery."
                ),
            }
            if resource_variant == "ordinary":
                properties["resource_responsibility"] = {
                    "type": "null",
                    "description": (
                        "The requested outcome is not acquisition-and-delivery of a "
                        "resource. Select this null branch for Chromie's own locomotion, "
                        "posture, gaze, gesture, turning, or other body motion."
                    ),
                }
                expected_bindings = expected_source_bindings(source_ref)
                if expected_bindings:
                    properties["bindings"] = exact_binding_array_schema(
                        properties.get("bindings") or {},
                        expected_bindings,
                        entity_type_by_name={"location": "location"},
                    )
            elif resource_variant == "physical_object":
                physical_schema = copy.deepcopy(
                    schema.get("$defs", {}).get(
                        "GoalAssociationModelPhysicalResourceResponsibility"
                    )
                    or {}
                )
                physical_schema["description"] = (
                    "Select only when acquiring a distinct concrete object independent "
                    "of Chromie's body and physically handing it to a recipient is the "
                    "requested outcome. Never select for Chromie's own locomotion, "
                    "posture, gaze, gesture, turning, or body motion."
                )
                spatial_names = {
                    "location",
                    "relative_location",
                    "distance",
                    "direction",
                    "route",
                }
                expected_spatial_bindings = [
                    (name, value)
                    for name, value in expected_source_bindings(source_ref)
                    if "_".join(
                        name.strip().casefold().replace("-", "_").split()
                    )
                    in spatial_names
                ]
                physical_properties = physical_schema.get("properties")
                if isinstance(physical_properties, dict):
                    expected_bindings = expected_source_bindings(source_ref)
                    identity_names = {
                        "desired_item",
                        "entity",
                        "item",
                        "object",
                        "resource",
                        "resource_identity",
                        "target_item",
                    }
                    recipient_names = {"delivery_recipient", "recipient"}
                    identity_values = [
                        value
                        for name, value in expected_bindings
                        if "_".join(
                            name.strip().casefold().replace("-", "_").split()
                        )
                        in identity_names
                    ]
                    recipient_values = [
                        value
                        for name, value in expected_bindings
                        if "_".join(
                            name.strip().casefold().replace("-", "_").split()
                        )
                        in recipient_names
                    ]
                    if len(set(identity_values)) == 1:
                        physical_properties["description"] = {
                            "const": identity_values[0]
                        }
                    if len(set(recipient_values)) == 1:
                        resource_recipient = copy.deepcopy(
                            schema.get("$defs", {}).get(
                                "GoalAssociationModelResourceRecipient"
                            )
                            or {}
                        )
                        resource_recipient_properties = (
                            resource_recipient.setdefault("properties", {})
                        )
                        resource_recipient_properties["description"] = {
                            "const": recipient_values[0]
                        }
                        resource_recipient["required"] = list(
                            dict.fromkeys(
                                [
                                    *(resource_recipient.get("required") or []),
                                    "description",
                                ]
                            )
                        )
                        physical_properties["recipient"] = resource_recipient
                if expected_spatial_bindings and isinstance(
                    physical_properties, dict
                ):
                    source_schema = copy.deepcopy(
                        schema.get("$defs", {}).get(
                            "GoalAssociationModelPhysicalSource"
                        )
                        or {}
                    )
                    source_properties = source_schema.get("properties")
                    if isinstance(source_properties, dict):
                        source_properties["status"] = {"const": "known"}
                        source_properties["acquisition_bindings"] = (
                            exact_binding_array_schema(
                                source_properties.get("acquisition_bindings") or {},
                                expected_spatial_bindings,
                                entity_type_by_name={
                                    "location": "relative_location",
                                    "relative_location": "relative_location",
                                    "distance": "distance",
                                    "direction": "direction",
                                    "route": "route",
                                },
                            )
                        )
                        source_schema["required"] = list(
                            dict.fromkeys(
                                [
                                    *(source_schema.get("required") or []),
                                    "status",
                                    "acquisition_bindings",
                                ]
                            )
                        )
                        physical_properties["source"] = source_schema
                properties["resource_responsibility"] = physical_schema
                properties["bindings"] = {
                    **copy.deepcopy(properties.get("bindings") or {}),
                    "maxItems": 0,
                }
            elif resource_variant == "information":
                information_schema = copy.deepcopy(
                    schema.get("$defs", {}).get(
                        "GoalAssociationModelInformationResourceResponsibility"
                    )
                    or {}
                )
                expected_bindings = expected_source_bindings(source_ref)
                information_properties = information_schema.get("properties")
                if expected_bindings and isinstance(information_properties, dict):
                    information_properties["query_scope"] = (
                        exact_binding_array_schema(
                            information_properties.get("query_scope") or {},
                            expected_bindings,
                        )
                    )
                properties["resource_responsibility"] = information_schema
                properties["bindings"] = {
                    **copy.deepcopy(properties.get("bindings") or {}),
                    "maxItems": 0,
                }

            if resource_variant == "unbounded":
                properties["resource_kind"] = copy.deepcopy(
                    branch_goal_properties.get("resource_kind") or {}
                )

            properties["source_responsibility_refs"] = {
                "const": [source_ref]
            }
            if output_mode is not None:
                properties["output_mode"] = {"const": output_mode}
            # JSON property order is observable to the constrained decoder.  Put
            # the explicit semantic discriminator before either payload branch so
            # the model chooses resource shape before the easier empty-bindings
            # production can select a physical-resource branch on its behalf.
            discriminator_first = (
                "source_responsibility_refs",
                "output_mode",
                "resource_kind",
                "description",
                "bindings",
                "resource_responsibility",
            )
            return {
                **{
                    name: properties[name]
                    for name in discriminator_first
                    if name in properties
                },
                **{
                    name: value
                    for name, value in properties.items()
                    if name not in discriminator_first
                },
            }

        def resource_variants(source_ref: str) -> list[str]:
            output_mode = responsibility_output_modes.get(source_ref)
            if source_ref in responsibility_information_refs:
                # GI authored only the human-level information WHAT. At the
                # canonical Goal boundary that category projects to the existing
                # provider-neutral information-resource representation. This is
                # a deterministic representation projection, not GI choosing a
                # Capability, provider, or executable work item.
                return ["information"]
            if output_mode == "body_action":
                return ["ordinary", "physical_object"]
            if output_mode == "information":
                return ["information"]
            if output_mode == "stateful_effect":
                return ["ordinary"]
            if output_mode is not None:
                return ["ordinary"]
            return ["unbounded"]

        goal_schema["oneOf"] = []
        for source_ref in responsibility_refs:
            for resource_variant in resource_variants(source_ref):
                goal_schema["oneOf"].append(
                    {
                        # Ollama's constrained decoder treats the selected
                        # oneOf object branch as the active production surface.
                        # Repeat the complete writable Goal surface here, not
                        # only the discriminants, so branch-local required
                        # fields can actually be generated. Resource-capable
                        # modes use complete cross-product branches so an
                        # ordinary Goal cannot also populate a resource object.
                        "properties": branch_properties(
                            source_ref,
                            resource_variant=resource_variant,
                        ),
                        # Some constrained decoders treat a nested oneOf branch
                        # as the active object production surface rather than
                        # combining its required list with the parent object.
                        "required": list(
                            dict.fromkeys(
                                [
                                    *goal_required,
                                    "source_responsibility_refs",
                                    *(
                                        ["output_mode"]
                                        if source_ref
                                        in responsibility_output_modes
                                        else []
                                    ),
                                ]
                            )
                        ),
                    }
                )
    properties = schema.setdefault("properties", {})
    required = list(schema.get("required") or [])
    if output_type is GoalSegmentationModelOutput:
        properties["decision"] = {
            "type": "string",
            "enum": ["create_goals"],
        }
        ordered_required = [
            "decision",
            "new_goals",
            "referent_updates",
            "resolved_references",
            "confidence",
            "reason_summary",
        ]
    else:
        properties["decision"] = {
            "type": "string",
            "enum": ["associate", "create_goals"],
        }
        ordered_required = [
            "decision",
            "associations",
            "new_goals",
            "referent_updates",
            "resolved_references",
            "confidence",
            "reason_summary",
        ]
    if responsibility_refs:
        def contains_source_ref(source_ref: str) -> dict[str, Any]:
            return {
                "contains": {
                    "type": "object",
                    "properties": {
                        "source_responsibility_refs": {
                            "type": "array",
                            "contains": {"const": source_ref},
                            "minContains": 1,
                            "maxContains": 1,
                        }
                    },
                    "required": ["source_responsibility_refs"],
                },
                "minContains": 1,
                "maxContains": 1,
            }

        new_goal_conservation = {
            "minItems": len(responsibility_refs),
            "maxItems": len(responsibility_refs),
            "allOf": [
                contains_source_ref(source_ref)
                for source_ref in responsibility_refs
            ],
        }
        if output_type is GoalSegmentationModelOutput:
            # With no retained Goal candidate, every GI Responsibility must
            # become exactly one new Goal. Encode the already-enforced Host
            # invariant in the decoder so contract repair cannot emit r1,r1
            # for an r1,r2 turn. This is identity conservation, not semantic
            # reassociation.
            properties["new_goals"].update(new_goal_conservation)
        else:
            # Goal Association owns the branch choice. Once it chooses
            # create_goals, associations are inactive and every Responsibility
            # necessarily belongs to the new-goal branch. Conversely, an
            # association branch must conserve each supplied ref exactly once.
            schema.setdefault("allOf", []).append(
                {
                    "if": {
                        "properties": {"decision": {"const": "create_goals"}},
                        "required": ["decision"],
                    },
                    "then": {
                        "properties": {
                            "associations": {"maxItems": 0},
                            "new_goals": new_goal_conservation,
                        }
                    },
                    "else": {
                        "properties": {
                            "new_goals": {"maxItems": 0},
                            "associations": {
                                "minItems": 1,
                                "allOf": [
                                    contains_source_ref(source_ref)
                                    for source_ref in responsibility_refs
                                ],
                            },
                        }
                    },
                }
            )

    schema["required"] = list(dict.fromkeys([*ordered_required, *required]))
    schema.pop("oneOf", None)
    schema.pop("anyOf", None)
    schema = resource_semantic_contract_response_schema(schema)
    # The complete oneOf branches above duplicate the Pydantic parent Goal
    # surface so constrained decoders can generate branch-local required fields.
    # Keeping the same properties on the parent makes the decoder compile two
    # equivalent object surfaces and keeps definitions for impossible resource
    # variants alive.  Retain exactly one complete surface per branch.
    compact_goal_schema = schema.get("$defs", {}).get(
        "GoalAssociationModelGoal"
    )
    if isinstance(compact_goal_schema, dict) and compact_goal_schema.get("oneOf"):
        compact_goal_schema.pop("properties", None)
        compact_goal_schema.pop("required", None)
        compact_goal_schema.pop("additionalProperties", None)
        for branch in compact_goal_schema["oneOf"]:
            if isinstance(branch, dict):
                branch["type"] = "object"
                branch["additionalProperties"] = False
    return _prune_unreferenced_definitions(schema)


def binding_semantic_contract_response_schema(
    response_schema: dict[str, Any],
) -> dict[str, Any]:
    """Expose the existing canonical binding invariant to constrained decoding."""

    schema = copy.deepcopy(response_schema)
    binding_schema = schema.get("$defs", {}).get(
        "GoalAssociationModelBinding"
    )
    if not isinstance(binding_schema, dict):
        return schema
    categories = {
        "distance": ["distance"],
        "direction": ["direction"],
        "duration": ["duration", "duration_seconds"],
        "quantity": [
            "amount",
            "count",
            "item_count",
            "quantity",
            "quantity_binding",
            "resource_count",
            "resource_quantity",
        ],
        "speed": ["speed"],
    }
    clauses = binding_schema.setdefault("allOf", [])
    for names in categories.values():
        clauses.append(
            {
                "if": {
                    "properties": {"name": {"enum": names}},
                    "required": ["name"],
                },
                "then": {
                    "properties": {"entity_type": {"enum": names}},
                    "required": ["entity_type"],
                },
            }
        )
    clauses.append(
        {
            "if": {
                "properties": {"entity_type": {"const": "speed"}},
                "required": ["entity_type"],
            },
            "then": {
                "properties": {
                    "value": {
                        "anyOf": [
                            {"enum": ["slow", "normal", "quick"]},
                            {"pattern": r".*[0-9].*"},
                        ]
                    }
                },
                "required": ["value"],
            },
        }
    )
    return schema
def resource_semantic_contract_response_schema(
    response_schema: dict[str, Any],
) -> dict[str, Any]:
    """Expose single-owner resource kinds and completion modes to decoding."""

    schema = copy.deepcopy(response_schema)
    definitions = schema.get("$defs", {})
    goal_schema = definitions.get("GoalAssociationModelGoal")
    if isinstance(goal_schema, dict):
        clauses = goal_schema.setdefault("allOf", [])
        for resource_kind, output_mode in (
            ("physical_object", "body_action"),
            ("information", "information"),
        ):
            clauses.append(
                {
                    "if": {
                        "properties": {
                            "resource_responsibility": {
                                "type": "object",
                                "properties": {"kind": {"enum": [resource_kind]}},
                                "required": ["kind"],
                            }
                        },
                        "required": ["resource_responsibility"],
                    },
                    "then": {
                        "properties": {"output_mode": {"enum": [output_mode]}},
                        "required": ["output_mode"],
                    },
                }
            )

    physical_source = definitions.get("GoalAssociationModelPhysicalSource")
    if isinstance(physical_source, dict):
        physical_source.setdefault("allOf", []).append(
            {
                "if": {
                    "properties": {"status": {"enum": ["known"]}},
                    "required": ["status"],
                },
                "then": {
                    "properties": {"acquisition_bindings": {"minItems": 1}}
                },
            }
        )

    information_source = definitions.get("GoalAssociationModelInformationSource")
    if isinstance(information_source, dict):
        information_source.setdefault("allOf", []).extend(
            [
                {
                    "if": {
                        "properties": {"status": {"enum": ["known"]}},
                        "required": ["status"],
                    },
                    "then": {
                        "properties": {"source_name": {"minLength": 1}}
                    },
                },
                {
                    "if": {
                        "properties": {
                            "status": {"enum": ["unknown", "provider_resolved"]}
                        },
                        "required": ["status"],
                    },
                    "then": {
                        "properties": {"source_name": {"maxLength": 0}}
                    },
                },
            ]
        )
    return schema
