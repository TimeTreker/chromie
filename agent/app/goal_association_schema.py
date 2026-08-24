from __future__ import annotations

"""Constrained-decoder schema construction for Goal Association model DTOs.

This module has no model client, Goal state, or continuity decision lifecycle.
"""

import copy
from typing import Any, Literal

from .goal_association_contract import (
    GoalAssociationModelGoal,
    GoalAssociationModelOutput,
    GoalResponsibilityCoverageCertificate,
    GoalSegmentationModelOutput,
)


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
    goal_schema = schema.get("$defs", {}).get("GoalAssociationModelGoal")
    if isinstance(goal_schema, dict) and responsibility_refs:
        # Every writable Goal-semantic surface must be explicit in the
        # constrained model output. Defaults on these fields are Python DTO
        # conveniences, not permission for the model to drop GI-grounded
        # bindings or silently avoid deciding the resource branch.
        goal_required = list(
            dict.fromkeys(
                [
                    *(goal_schema.get("required") or []),
                    "source_responsibility_refs",
                    "description",
                    "output_mode",
                    "bindings",
                    "resource_responsibility",
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
            acquisition, and ``capability_work`` remains free to select a real
            information responsibility.
            """

            properties = copy.deepcopy(branch_goal_properties)
            output_mode = responsibility_output_modes.get(source_ref)
            if resource_variant == "ordinary":
                properties["resource_responsibility"] = {"type": "null"}
                expected_bindings = [
                    (" ".join(str(name).strip().split()), str(value))
                    for name, value in responsibility_bindings.get(
                        source_ref, {}
                    ).items()
                    if " ".join(str(name).strip().split())
                    and "_".join(
                        str(name)
                        .strip()
                        .casefold()
                        .replace("-", "_")
                        .split()
                    )
                    not in {"action", "activity", "effect", "outcome"}
                ]
                if expected_bindings:
                    bindings_schema = copy.deepcopy(
                        properties.get("bindings") or {}
                    )
                    bindings_schema["minItems"] = len(expected_bindings)
                    bindings_schema["maxItems"] = len(expected_bindings)
                    binding_item_template = copy.deepcopy(
                        schema.get("$defs", {}).get(
                            "GoalAssociationModelBinding"
                        )
                        or {}
                    )
                    binding_branches: list[dict[str, Any]] = []
                    for name, value in expected_bindings:
                        binding_branch = copy.deepcopy(binding_item_template)
                        binding_properties = binding_branch.setdefault(
                            "properties", {}
                        )
                        binding_properties["name"] = {"const": name}
                        binding_properties["value"] = {"const": value}
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
                    bindings_schema["items"] = {"oneOf": binding_branches}
                    bindings_schema["allOf"] = [
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
                    properties["bindings"] = bindings_schema
            elif resource_variant == "physical_object":
                properties["resource_responsibility"] = {
                    "$ref": (
                        "#/$defs/"
                        "GoalAssociationModelPhysicalResourceResponsibility"
                    )
                }
                properties["bindings"] = {
                    **copy.deepcopy(properties.get("bindings") or {}),
                    "maxItems": 0,
                }
            elif resource_variant == "information":
                properties["resource_responsibility"] = {
                    "$ref": (
                        "#/$defs/"
                        "GoalAssociationModelInformationResourceResponsibility"
                    )
                }
                properties["bindings"] = {
                    **copy.deepcopy(properties.get("bindings") or {}),
                    "maxItems": 0,
                }

            properties["source_responsibility_refs"] = {
                "const": [source_ref]
            }
            if output_mode is not None:
                properties["output_mode"] = {"const": output_mode}
            return properties

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
            if output_mode == "capability_work":
                return ["ordinary", "information"]
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
    return resource_semantic_contract_response_schema(
        binding_semantic_contract_response_schema(
            schema
        )
    )


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
        "quantity": [
            "amount",
            "count",
            "item_count",
            "quantity",
            "quantity_binding",
            "resource_count",
            "resource_quantity",
        ],
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
            ("information", "capability_work"),
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


def coverage_certificate_response_schema(
    candidate_goals: list[GoalAssociationModelGoal],
    *,
    authoritative_turn: str = "",
) -> dict[str, Any]:
    goal_count = len(candidate_goals)
    schema = copy.deepcopy(
        GoalResponsibilityCoverageCertificate.model_json_schema()
    )
    item_schema = schema.get("$defs", {}).get(
        "GoalResponsibilityCoverageItem"
    )
    if isinstance(item_schema, dict):
        item_schema["required"] = [
            "source_excerpt",
            "role",
            "coverage",
            "independently_satisfiable",
            "candidate_goal_indices",
            "required_goal_shape",
            "required_information_domain",
            "required_output_mode",
        ]
        indices = item_schema.get("properties", {}).get(
            "candidate_goal_indices"
        )
        surface = " ".join(str(authoritative_turn or "").strip().split())
        if surface and len(surface) <= 40:
            exact_surfaces = sorted(
                {
                    surface[start:end]
                    for start in range(len(surface))
                    for end in range(start + 1, len(surface) + 1)
                },
                key=lambda value: (len(value), value),
            )
            source_excerpt = item_schema.get("properties", {}).get(
                "source_excerpt"
            )
            if isinstance(source_excerpt, dict):
                source_excerpt["enum"] = exact_surfaces
                source_excerpt["description"] = (
                    "Copy one exact non-empty contiguous source slice; the decoder "
                    "cannot translate, inflect, combine, or rewrite particles."
                )
        if isinstance(indices, dict):
            indices["uniqueItems"] = True
            index_items = indices.get("items")
            if isinstance(index_items, dict):
                index_items["type"] = "integer"
                index_items["enum"] = list(range(max(0, goal_count)))
        item_schema.setdefault("allOf", []).extend(
            [
                {
                    "if": {
                        "properties": {
                            "role": {"enum": ["context", "framing"]}
                        },
                        "required": ["role"],
                    },
                    "then": {
                        "properties": {
                            "coverage": {
                                "enum": ["covered", "clarification_required"]
                            },
                            "independently_satisfiable": {"enum": [False]},
                            "candidate_goal_indices": {"maxItems": 0},
                            "required_goal_shape": {"const": "ordinary"},
                            "required_information_domain": {"const": "none"},
                            "required_output_mode": {"const": "none"},
                        }
                    },
                },
                {
                    "if": {
                        "properties": {
                            "role": {"enum": ["constraint"]}
                        },
                        "required": ["role"],
                    },
                    "then": {
                        "properties": {
                            "independently_satisfiable": {"enum": [False]},
                            "required_goal_shape": {"const": "ordinary"},
                            "required_information_domain": {"const": "none"},
                            "required_output_mode": {"const": "none"},
                        }
                    },
                },
                {
                    "if": {
                        "properties": {
                            "role": {"enum": ["responsibility"]},
                            "required_goal_shape": {
                                "enum": ["information_resource"]
                            },
                        },
                        "required": ["role", "required_goal_shape"],
                    },
                    "then": {
                        "properties": {
                            "required_information_domain": {
                                "enum": [
                                    "local_clock",
                                    "weather_forecast",
                                    "external_grounded_information",
                                    "direct_environment_perception",
                                    "private_runtime_information",
                                ]
                            },
                            "required_output_mode": {"const": "capability_work"},
                        }
                    },
                },
                {
                    "if": {
                        "properties": {
                            "required_goal_shape": {
                                "enum": [
                                    "ordinary",
                                    "physical_resource",
                                    "persistent_effect",
                                ]
                            }
                        },
                        "required": ["required_goal_shape"],
                    },
                    "then": {
                        "properties": {
                            "required_information_domain": {"const": "none"}
                        }
                    },
                },
                {
                    "if": {
                        "properties": {
                            "required_goal_shape": {
                                "enum": ["physical_resource"]
                            }
                        },
                        "required": ["required_goal_shape"],
                    },
                    "then": {
                        "properties": {
                            "required_output_mode": {"const": "body_action"}
                        }
                    },
                },
                {
                    "if": {
                        "properties": {
                            "required_goal_shape": {
                                "enum": ["persistent_effect"]
                            }
                        },
                        "required": ["required_goal_shape"],
                    },
                    "then": {
                        "properties": {
                            "required_output_mode": {"const": "capability_work"}
                        }
                    },
                },
                {
                    "if": {
                        "properties": {
                            "role": {
                                "enum": ["responsibility", "constraint"]
                            },
                            "coverage": {
                                "enum": ["covered", "clarification_required"]
                            },
                        },
                        "required": ["role", "coverage"],
                    },
                    "then": {
                        "properties": {
                            "candidate_goal_indices": {"minItems": 1}
                        }
                    },
                },
                {
                    "if": {
                        "properties": {
                            "role": {"enum": ["responsibility"]},
                            "coverage": {"enum": ["covered"]},
                        },
                        "required": ["role", "coverage"],
                    },
                    "then": {
                        "properties": {
                            "candidate_goal_indices": {
                                "minItems": 1,
                                "maxItems": 1,
                            }
                        }
                    },
                },
                {
                    "if": {
                        "properties": {
                            "coverage": {"enum": ["representation_mismatch"]}
                        },
                        "required": ["coverage"],
                    },
                    "then": {
                        "properties": {
                            "candidate_goal_indices": {"minItems": 1}
                        }
                    },
                },
                {
                    "if": {
                        "properties": {
                            "role": {"enum": ["responsibility"]},
                            "coverage": {"enum": ["representation_mismatch"]},
                        },
                        "required": ["role", "coverage"],
                    },
                    "then": {
                        "properties": {
                            "candidate_goal_indices": {
                                "minItems": 1,
                                "maxItems": 1,
                            }
                        }
                    },
                },
                {
                    "if": {
                        "properties": {
                            "coverage": {
                                "enum": ["missing"]
                            }
                        },
                        "required": ["coverage"],
                    },
                    "then": {
                        "properties": {
                            "candidate_goal_indices": {"maxItems": 0}
                        }
                    },
                },
            ]
        )
        properties = schema.get("properties", {})
        responsibility_items = properties.get("responsibility_items")
        supporting_items = properties.get("supporting_items")
        if isinstance(responsibility_items, dict):
            responsibility_item = copy.deepcopy(item_schema)
            responsibility_item_properties = responsibility_item["properties"]
            responsibility_required = list(responsibility_item["required"])

            def candidate_shape(
                candidate: GoalAssociationModelGoal,
            ) -> tuple[str, str, str]:
                resource = candidate.resource_responsibility
                if resource is not None and resource.kind == "information":
                    return (
                        "information_resource",
                        resource.information_domain,
                        candidate.output_mode,
                    )
                if resource is not None and resource.kind == "physical_object":
                    return ("physical_resource", "none", candidate.output_mode)
                if candidate.output_mode == "capability_work":
                    return ("persistent_effect", "none", candidate.output_mode)
                return ("ordinary", "none", candidate.output_mode)

            def responsibility_branch(
                *,
                coverage: str,
                candidate_index: int | None,
                constrain_to_candidate: bool,
            ) -> dict[str, Any]:
                branch_properties = copy.deepcopy(
                    responsibility_item_properties
                )
                branch_properties["role"] = {"const": "responsibility"}
                branch_properties["coverage"] = {"const": coverage}
                branch_properties["candidate_goal_indices"] = {
                    "const": (
                        []
                        if candidate_index is None
                        else [candidate_index]
                    )
                }
                if constrain_to_candidate and candidate_index is not None:
                    shape, information_domain, output_mode = candidate_shape(
                        candidate_goals[candidate_index]
                    )
                    branch_properties["required_goal_shape"] = {
                        "const": shape
                    }
                    branch_properties["required_information_domain"] = {
                        "const": information_domain
                    }
                    branch_properties["required_output_mode"] = {
                        "const": output_mode
                    }
                return {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": branch_properties,
                    "required": responsibility_required,
                }

            responsibility_branches: list[dict[str, Any]] = []
            for candidate_index in range(goal_count):
                responsibility_branches.extend(
                    [
                        responsibility_branch(
                            coverage="covered",
                            candidate_index=candidate_index,
                            constrain_to_candidate=True,
                        ),
                        responsibility_branch(
                            coverage="clarification_required",
                            candidate_index=candidate_index,
                            constrain_to_candidate=True,
                        ),
                        responsibility_branch(
                            coverage="representation_mismatch",
                            candidate_index=candidate_index,
                            constrain_to_candidate=False,
                        ),
                    ]
                )
            responsibility_branches.append(
                responsibility_branch(
                    coverage="missing",
                    candidate_index=None,
                    constrain_to_candidate=False,
                )
            )
            responsibility_items["items"] = {
                "oneOf": responsibility_branches
            }
        if isinstance(supporting_items, dict):
            supporting_item = copy.deepcopy(item_schema)
            supporting_item["properties"]["role"] = {
                "type": "string",
                "enum": ["constraint", "context", "framing"],
            }
            supporting_items["items"] = supporting_item
    schema["required"] = [
        "responsibility_items",
        "supporting_items",
        "reason_summary",
    ]
    schema["additionalProperties"] = False
    return schema
