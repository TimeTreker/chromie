"""Final Planner decoder pass: the native shape a constrained decoder actually follows.

Native decoders ignore ``allOf`` and conditional constraints, so every validation rule
the DTO enforces on dispositions is also exposed here as native ``oneOf`` branches.
"""
from __future__ import annotations

import copy
import json
from typing import Any


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
        _native_disposition_assignment_branches(shape)
    _shared_goal_outcome_definitions(result)
    return result


def _shared_goal_outcome_definitions(schema: dict[str, Any]) -> None:
    """Define each repeated native Goal outcome once; every assignment branch refers to it.

    Inline copies per assignment multiplied the grammar the decoder compiles (2 Goals:
    2.4x the XGrammar rules of the unbranched shape; shared: 1.4x).
    """
    definitions = schema.setdefault("$defs", {})
    names: dict[str, str] = {}
    uses: dict[str, int] = {}

    def count(outcome: Any) -> Any:
        if isinstance(outcome, dict) and isinstance(outcome.get("properties"), dict):
            key = json.dumps(outcome, sort_keys=True)
            uses[key] = uses.get(key, 0) + 1
        return outcome

    def share(outcome: Any) -> Any:
        if not isinstance(outcome, dict) or not isinstance(outcome.get("properties"), dict):
            return outcome
        key = json.dumps(outcome, sort_keys=True)
        if uses.get(key, 0) < 2:
            return outcome
        if key not in names:
            names[key] = f"NativeGoalOutcome{len(names) + 1}"
            definitions[names[key]] = outcome
        return {"$ref": f"#/$defs/{names[key]}"}

    def visit(node: Any, apply: Any) -> None:
        if not isinstance(node, dict):
            return
        goals = ((node.get("properties") or {}).get("goal_outcomes") or {}).get("properties")
        for outcome in (goals or {}).values():
            if isinstance(outcome, dict) and isinstance(outcome.get("oneOf"), list):
                outcome["oneOf"] = [apply(item) for item in outcome["oneOf"]]
        for key in ("oneOf", "anyOf"):
            for item in node.get(key) or []:
                visit(item, apply)

    visit(schema, count)
    visit(schema, share)


# Mixed assignments grow with the product of per-Goal choices; above this count they
# share one branch whose bounds cover them all (the validator still decides the rest).


_NATIVE_MIXED_ASSIGNMENT_MAX = 8


def _native_disposition_assignment_branches(shape: dict[str, Any]) -> None:
    """Expose the aggregate disposition/step assignment natively (``validate_semantic_shape``).

    The assignment lives in ``allOf``, which native decoders ignore, so the visible
    shape offered a clarify, respond or unavailable Plan with steps, and execute without
    one; Host rejected them (open after live run 16, 2026-10-15). Each branch is one
    permitted assignment narrowed into the already-native shape; the model still authors
    every Goal outcome and the aggregate.
    """
    assignments = next((
        item["anyOf"] for item in shape.get("allOf") or []
        if isinstance(item, dict) and isinstance(item.get("anyOf"), list) and item["anyOf"]
        and all(_assignment_disposition(branch) is not None for branch in item["anyOf"])
    ), None)
    if (assignments is None or not isinstance(shape.get("properties"), dict)
            or "oneOf" in shape or "anyOf" in shape):
        return
    mixed = [branch for branch in assignments if _assignment_disposition(branch) == "mixed"]
    constraints = [branch for branch in assignments if _assignment_disposition(branch) != "mixed"]
    constraints += mixed if len(mixed) <= _NATIVE_MIXED_ASSIGNMENT_MAX else [_merged_constraint(mixed)]
    # Cross-field validation stays once on the enclosing shape (it applies to every branch).
    kept = {"title", "$defs", "description", "allOf"}
    base = {key: value for key, value in shape.items() if key not in kept | {"oneOf", "anyOf"}}
    branches = []
    for constraint in constraints:
        branch = copy.deepcopy(base)
        _narrow(branch, constraint)
        branches.append(branch)
    for key in list(shape):
        if key not in kept:
            del shape[key]
    shape["oneOf"] = branches


def _assignment_disposition(branch: Any) -> str | None:
    properties = branch.get("properties") if isinstance(branch, dict) else None
    if not isinstance(properties, dict) or "steps" not in properties:
        return None
    choices = (properties.get("disposition") or {}).get("enum")
    return choices[0] if isinstance(choices, list) and len(choices) == 1 else None


def _merged_constraint(constraints: list[dict[str, Any]]) -> dict[str, Any]:
    """The weakest bounds every constraint satisfies (enum union, widest item counts)."""
    merged: dict[str, Any] = {}
    if all("enum" in item for item in constraints):
        merged["enum"] = list(dict.fromkeys(value for item in constraints for value in item["enum"]))
    if all("minItems" in item for item in constraints):
        merged["minItems"] = min(item["minItems"] for item in constraints)
    if all("maxItems" in item for item in constraints):
        merged["maxItems"] = max(item["maxItems"] for item in constraints)
    constants = {repr(item.get("const")) for item in constraints}
    if all("const" in item for item in constraints) and len(constants) == 1:
        merged["const"] = constraints[0]["const"]
    if all(isinstance(item.get("properties"), dict) for item in constraints):
        names = set.intersection(*(set(item["properties"]) for item in constraints))
        merged["properties"] = {
            name: _merged_constraint([item["properties"][name] for item in constraints])
            for name in constraints[0]["properties"] if name in names
        }
    return merged


def _compatible(branch: dict[str, Any], constraint: dict[str, Any]) -> bool:
    properties = branch.get("properties") or {}
    for name, bound in (constraint.get("properties") or {}).items():
        offered = (properties.get(name) or {}).get("enum") if isinstance(properties.get(name), dict) else None
        if isinstance(bound, dict) and "enum" in bound and isinstance(offered, list):
            if not set(map(repr, offered)) & set(map(repr, bound["enum"])):
                return False
    return True


def _narrow(target: dict[str, Any], constraint: dict[str, Any]) -> None:
    """Intersect a native shape with one assignment constraint (enums, item counts, const)."""
    alternatives = [key for key in ("oneOf", "anyOf") if isinstance(target.get(key), list)]
    if alternatives and not isinstance(target.get("properties"), dict):
        for key in alternatives:
            target[key] = [item for item in target[key] if isinstance(item, dict) and _compatible(item, constraint)]
            for item in target[key]:
                _narrow(item, constraint)
        return
    for name, bound in (constraint.get("properties") or {}).items():
        if isinstance(bound, dict) and isinstance((target.get("properties") or {}).get(name), dict):
            _narrow(target["properties"][name], bound)
    if "enum" in constraint:
        allowed = [value for value in target.get("enum", constraint["enum"]) if value in constraint["enum"]]
        target["enum"] = allowed
    if "const" in constraint:
        target["const"] = constraint["const"]
    if "minItems" in constraint:
        target["minItems"] = max(target.get("minItems", 0), constraint["minItems"])
    if "maxItems" in constraint:
        target["maxItems"] = min(target.get("maxItems", constraint["maxItems"]), constraint["maxItems"])


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
