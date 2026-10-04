"""Constrained-decoder schema construction for Goal Association model DTOs.

This module has no model client, Goal state, or continuity decision lifecycle.
"""

from __future__ import annotations

import copy
from typing import Any

from .goal_association_contract import (
    GoalAssociationModelOutput,
    GoalSegmentationModelOutput,
)


try:
    from chromie_contracts.json_schema import expose_intersection_shapes as _expose_intersection_shapes
except ImportError:  # pragma: no cover - repository development path
    from shared.chromie_contracts.json_schema import expose_intersection_shapes as _expose_intersection_shapes


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
    responsibility_continuity_scopes: dict[str, str] | None = None,
    responsibility_information_refs: set[str] | None = None,
    responsibility_bindings: dict[str, dict[str, Any]] | None = None,
    meaning_uncertainty_refs: list[str] | None = None,
    association_min_confidence: float = 0.0,
) -> dict[str, Any]:
    schema = copy.deepcopy(output_type.model_json_schema())
    association_min_confidence = max(
        0.0, min(1.0, float(association_min_confidence))
    )
    active_ids = [
        " ".join(str(item.get("goal_id") or "").strip().split())
        for item in candidate_goals
        if " ".join(str(item.get("goal_id") or "").strip().split())
    ]
    open_goal_ids = [
        " ".join(str(item.get("goal_id") or "").strip().split())
        for item in candidate_goals
        if " ".join(str(item.get("goal_id") or "").strip().split())
        and str(item.get("responsibility_status") or "open").strip() == "open"
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
    responsibility_continuity_scopes = dict(responsibility_continuity_scopes or {})
    responsibility_information_refs = set(
        responsibility_information_refs or set()
    )
    responsibility_bindings = {
        str(source_ref): dict(bindings)
        for source_ref, bindings in (responsibility_bindings or {}).items()
    }
    meaning_uncertainty_refs = [
        " ".join(str(item or "").strip().split())
        for item in (meaning_uncertainty_refs or [])
        if " ".join(str(item or "").strip().split())
    ]
    properties = schema.get("properties", {})
    activation_schema = schema.get("$defs", {}).get("CognitiveActivationRequest")
    if isinstance(activation_schema, dict):
        activation_properties = activation_schema.get("properties", {})
        if isinstance(activation_properties, dict):
            authority = activation_properties.get("authority")
            if isinstance(authority, dict):
                authority["enum"] = ["planner", "social_cognition"]
            refs = activation_properties.get("responsibility_refs")
            if isinstance(refs, dict):
                refs["items"] = {"type": "string", "enum": responsibility_refs}
                refs["uniqueItems"] = True
    # GA supplies Goal identity/relationships only; Host inherits all WHAT from UMI.
    associations = properties.get("associations")
    if isinstance(associations, dict) and not open_goal_ids:
        # Retained terminal Goals remain available below as related historical
        # context for a new Goal, but they cannot own a current Responsibility.
        # Make this structural for native decoders rather than relying on if/then.
        associations["maxItems"] = 0
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
                        # otherwise correct continuity decision. Expose the
                        # configured admission threshold to the constrained
                        # decoder so a semantic "no match" is represented as
                        # unassociated rather than as a confidence-zero
                        # association that later conflicts with unassociated.
                        required_fields = list(node.get("required") or [])
                        for field in ("target_goal_ids", "confidence"):
                            if field not in required_fields:
                                required_fields.append(field)
                        confidence = node_properties.get("confidence")
                        if isinstance(confidence, dict):
                            confidence["minimum"] = association_min_confidence
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
                    # Associations are continuity operations over live Goal identity.
                    # Terminal Goals are immutable historical context: a fresh
                    # Responsibility may cite them through new_goals.related_goal_ids
                    # but must not be attached to them as its canonical owner.
                    target_ids["items"] = {
                        "type": "string",
                        "enum": open_goal_ids,
                    }
                    target_ids["uniqueItems"] = True
                    if "relationship" in node_properties and open_goal_ids:
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
                resolved_uncertainties = node_properties.get(
                    "resolved_meaning_uncertainty_refs"
                )
                if isinstance(resolved_uncertainties, dict):
                    if meaning_uncertainty_refs:
                        resolved_uncertainties["items"] = {
                            "type": "string",
                            "enum": meaning_uncertainty_refs,
                        }
                        resolved_uncertainties["uniqueItems"] = True
                    else:
                        resolved_uncertainties["maxItems"] = 0
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
    change_schema = schema.get("$defs", {}).get("GoalAssociationModelRequirementChange")
    if isinstance(change_schema, dict):
        change_schema["oneOf"] = [
            {
                "properties": {
                    "target_goal_id": {"const": str(snapshot["goal_id"])},
                    "replace_requirement_indices": {
                        "type": "array", "uniqueItems": True,
                        "items": {"type": "integer", "enum": list(range(len(
                            (snapshot.get("goal") or {}).get("success_criteria")
                            or [(snapshot.get("goal") or {}).get("description")]
                        )))},
                    },
                },
                "required": ["target_goal_id", "replace_requirement_indices"],
            }
            for snapshot in candidate_goals
        ]
    binding_change = schema.get("$defs", {}).get("GoalAssociationModelBindingChange")
    if isinstance(binding_change, dict):
        binding_change["oneOf"] = [
            {"properties": {
                "source_responsibility_ref": {"const": source_ref},
                "source_binding": {"enum": list(bindings)},
            }, "required": ["source_responsibility_ref", "source_binding"]}
            for source_ref, bindings in responsibility_bindings.items() if bindings
        ] or [{"not": {}}]
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
                                "requirement_changes": {
                                    "type": "array",
                                    "minItems": 1,
                                }
                            },
                            "required": ["requirement_changes"],
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
    properties = schema.setdefault("properties", {})
    required = list(schema.get("required") or [])
    # Host materializes WHAT; GA owns the primary identity/relationship choice.
    properties.pop("decision", None)
    associations = properties.get("associations")
    if isinstance(associations, dict) and not open_goal_ids:
        associations["maxItems"] = 0

    ordered_required = [
        *( ["associations"] if "associations" in properties else [] ),
        "new_goals",
        "referent_updates",
        "resolved_references",
        "cognitive_requests",
        "confidence",
        "reason_summary",
    ]

    if responsibility_refs:
        def source_ref_item(source_ref: str) -> dict[str, Any]:
            return {
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
            }

        def association_contains(source_ref: str) -> dict[str, Any]:
            return {
                "contains": source_ref_item(source_ref),
                "minContains": 1,
                "maxContains": 1,
            }

        def association_excludes(source_ref: str) -> dict[str, Any]:
            return {"not": {"contains": source_ref_item(source_ref)}}

        for source_ref in responsibility_refs:
            if "associations" not in properties or not open_goal_ids:
                schema.setdefault("allOf", []).append({
                    "properties": {
                        "new_goals": association_contains(source_ref),
                    },
                    "required": ["new_goals"],
                })
                continue
            schema.setdefault("allOf", []).append({
                "oneOf": [
                    {
                        "properties": {
                            "associations": association_contains(source_ref),
                            "new_goals": association_excludes(source_ref),
                        },
                        "required": ["associations", "new_goals"],
                    },
                    {
                        "properties": {
                            "associations": association_excludes(source_ref),
                            "new_goals": association_contains(source_ref),
                        },
                        "required": ["associations", "new_goals"],
                    },
                ]
            })

    schema["required"] = [name for name in dict.fromkeys([*ordered_required, *required]) if name in properties]
    schema.pop("oneOf", None)
    schema.pop("anyOf", None)
    schema = resource_semantic_contract_response_schema(schema)
    # GA owns identity and continuity. Complete intent is inherited by Host;
    # no classification, resource decomposition or parameter extraction is needed.
    schema["$defs"]["GoalAssociationModelGoal"] = {
        "type": "object", "additionalProperties": False,
        "properties": {
            "source_responsibility_refs": {
                "type": "array", "items": {"type": "string", "enum": responsibility_refs},
                "minItems": 1, "maxItems": 1, "uniqueItems": True,
            },
            **{name: {"type": "array", "items": {"type": "string", "enum": ids},
                      "maxItems": len(ids), "uniqueItems": True}
               for name, ids in (("related_goal_ids", active_ids),
                                 ("supersedes_goal_ids", open_goal_ids))},
        },
        "required": ["source_responsibility_refs", "related_goal_ids", "supersedes_goal_ids"],
    }
    # Complete the shared item before specializing prefixItems. JSON Schema
    # applies `items` only after the prefix, so later changes to its $ref cannot
    # protect copied terminal-history items.
    if open_goal_ids:
        schema["$defs"]["GoalAssociationModelGoal"]["allOf"] = [
            {"not": {"properties": {
                "related_goal_ids": {"contains": {"const": goal_id}},
                "supersedes_goal_ids": {"contains": {"const": goal_id}},
            }, "required": ["related_goal_ids", "supersedes_goal_ids"]}}
            for goal_id in open_goal_ids
        ]
    # Without an open target, every accepted Responsibility needs its own
    # identity row. Fix transport order and exact refs for constrained decoders;
    # retained terminal Goals remain historical context through related_goal_ids.
    if not open_goal_ids and responsibility_refs:
        compact_goal = schema["$defs"]["GoalAssociationModelGoal"]
        fixed_items: list[dict[str, Any]] = []
        for source_ref in responsibility_refs:
            fixed = copy.deepcopy(compact_goal)
            source_refs = fixed["properties"]["source_responsibility_refs"]
            source_refs["items"] = {
                "type": "string",
                "enum": [source_ref],
            }
            fixed_items.append(fixed)
        new_goal_array = schema.get("properties", {}).get("new_goals")
        if isinstance(new_goal_array, dict):
            new_goal_array["minItems"] = len(fixed_items)
            new_goal_array["maxItems"] = len(fixed_items)
            new_goal_array["prefixItems"] = fixed_items
            # Keep the existing schema-valued suffix surface. maxItems makes a
            # suffix impossible, while the retained $ref keeps the canonical Goal
            # definition reachable for decoder/validator consumers.
    if active_ids:
        # A retained Goal has one continuity fate in a single GA transaction.
        # Host materialization already rejects a Goal that is both retained by an
        # association and retired by a new Goal; expose the same invariant to the
        # constrained decoder so the primary model cannot author that impossible
        # state and then fail after generation.
        for goal_id in active_ids:
            associated = {
                "properties": {
                    "associations": {
                        "contains": {
                            "type": "object",
                            "properties": {
                                "target_goal_ids": {
                                    "contains": {"const": goal_id},
                                    "minContains": 1,
                                }
                            },
                            "required": ["target_goal_ids"],
                        },
                        "minContains": 1,
                    }
                },
                "required": ["associations"],
            }
            superseded = {
                "properties": {
                    "new_goals": {
                        "contains": {
                            "type": "object",
                            "properties": {
                                "supersedes_goal_ids": {
                                    "contains": {"const": goal_id},
                                    "minContains": 1,
                                }
                            },
                            "required": ["supersedes_goal_ids"],
                        },
                        "minContains": 1,
                    }
                },
                "required": ["new_goals"],
            }
            schema.setdefault("allOf", []).append(
                {"not": {"allOf": [associated, superseded]}}
            )
    _expose_intersection_shapes(schema)
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


def _goal_resource_branches_are_closed(goal_schema: dict[str, Any]) -> bool:
    """Whether every branch already implies the three resource conditionals."""
    branches = goal_schema.get("oneOf")
    if not isinstance(branches, list) or not branches:
        return False
    for branch in branches:
        properties = branch.get("properties", {})
        required = set(branch.get("required", []))
        if not {"resource_responsibility", "bindings", "output_mode"} <= required:
            return False
        resource = properties.get("resource_responsibility", {})
        if resource.get("type") == "null":
            continue
        resource_kind = resource.get("properties", {}).get("kind", {})
        kind = resource_kind.get("const")
        if kind is None and len(resource_kind.get("enum", [])) == 1:
            kind = resource_kind["enum"][0]
        expected_mode = {
            "physical_object": "body_action", "information": "information"
        }.get(kind)
        if (
            resource.get("type") != "object"
            or "kind" not in resource.get("required", [])
            or expected_mode is None
            or properties.get("output_mode") != {"const": expected_mode}
            or properties.get("bindings", {}).get("maxItems") != 0
        ):
            return False
    return True


def resource_semantic_contract_response_schema(
    response_schema: dict[str, Any],
) -> dict[str, Any]:
    """Expose single-owner resource kinds and completion modes to decoding."""

    schema = copy.deepcopy(response_schema)
    definitions = schema.get("$defs", {})
    goal_schema = definitions.get("GoalAssociationModelGoal")
    if isinstance(goal_schema, dict):
        clauses = goal_schema.setdefault("allOf", [])
        resource_clauses = []
        for resource_kind, output_mode in (
            ("physical_object", "body_action"),
            ("information", "information"),
        ):
            resource_clauses.append(
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
        clauses.extend(resource_clauses)
        if _goal_resource_branches_are_closed(goal_schema):
            # Remove only the known implications. Candidate-ID exclusion and
            # any other independent clauses must remain intact.
            redundant = [
                {
                    "if": {
                        "properties": {
                            "resource_responsibility": {"not": {"type": "null"}}
                        },
                        "required": ["resource_responsibility"],
                    },
                    "then": {"properties": {"bindings": {"maxItems": 0}}},
                },
                *resource_clauses,
            ]
            remaining = [clause for clause in clauses if clause not in redundant]
            if remaining:
                goal_schema["allOf"] = remaining
            else:
                goal_schema.pop("allOf", None)

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
        # Native decoding does not enforce the former if/then dependency.
        # Compile the existing DTO invariant into complete, disjoint objects;
        # never turn an invented source such as "none" into an absent source.
        branches = []
        for status in information_source["properties"]["status"]["enum"]:
            branch = copy.deepcopy(information_source)
            properties = branch["properties"]
            properties["status"] = {"type": "string", "const": status}
            if status == "known":
                properties["source_name"]["minLength"] = 1
                branch["required"] = list(dict.fromkeys([
                    *branch["required"], "source_name",
                ]))
            else:
                properties["source_name"] = {"type": "string", "const": ""}
                properties["referent_id"] = {"type": "string", "const": ""}
            branches.append(branch)
        definitions["GoalAssociationModelInformationSource"] = {
            "title": information_source.get("title"), "oneOf": branches,
        }
    return schema
