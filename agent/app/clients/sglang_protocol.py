from __future__ import annotations

import copy
import itertools
import json
from typing import Any

from ..inference_compute import CognitionComputeClass, compute_rank

from shared.chromie_contracts.json_schema import expose_intersection_shapes


def sglang_priority(
    compute_class: CognitionComputeClass,
    *,
    step: int = 100,
) -> int:
    """Translate one provider-neutral compute class into SGLang priority."""

    if step <= 0:
        raise ValueError("SGLang priority step must be positive")
    return compute_rank(compute_class) * step


def candidate_compatible_schema(
    schema: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    """Remove only decoder hints that canonical Chromie validation re-enforces."""

    translated = copy.deepcopy(schema)
    removed: list[str] = []

    def visit(node: Any, path: str) -> None:
        if isinstance(node, dict):
            if "uniqueItems" in node:
                node.pop("uniqueItems", None)
                removed.append(f"{path}.uniqueItems")
            for key, value in node.items():
                visit(value, f"{path}.{key}")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                visit(value, f"{path}[{index}]")

    visit(translated, "$")
    return translated, removed


def _stream_decoder_constraints(node: Any) -> None:
    """Preserve the existing XGrammar streaming omissions; Host keeps authority."""
    if isinstance(node, dict):
        membership = node.get("allOf")
        if node.get("type") == "array" and isinstance(membership, list) and membership and all(
            isinstance(item, dict) and set(item) == {"contains"}
            and isinstance(item["contains"], dict)
            and len(item["contains"].get("enum", [])) == 1
            for item in membership
        ):
            # XGrammar ignores contains. Serialize mandatory members first;
            # the canonical schema still validates membership in any order.
            # This constrains generation, never fills or repairs model output.
            node["prefixItems"] = [item["contains"] for item in node.pop("allOf")]
        # XGrammar 0.2.1 miscompiles string regexes and fractional number bounds
        # (it rejected 248 of 2,232 valid values over the live catalog's ranges).
        # Integral bounds are exact (0 of 747), so the decoder keeps them: a provider
        # minimum such as count>=2 is then decoder-tight (live 2026-10-12). Everything
        # stripped remains in the original schema and deterministic validation.
        if node.get("type") == "string":
            node.pop("pattern", None)
        if node.get("type") == "number":
            for key in ("exclusiveMinimum", "exclusiveMaximum"):
                node.pop(key, None)
            for key in ("minimum", "maximum"):
                bound = node.get(key)
                if not (isinstance(bound, (int, float)) and not isinstance(bound, bool)
                        and float(bound).is_integer()):
                    node.pop(key, None)
        for value in node.values():
            _stream_decoder_constraints(value)
    elif isinstance(node, list):
        for value in node:
            _stream_decoder_constraints(value)


def _share_stream_source_spans(schema: dict[str, Any]) -> None:
    """Keep identical provenance grammars shared across Capability/state branches."""
    definitions = schema.setdefault("$defs", {})
    known: dict[str, str] = {}

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            sources = node.get("properties", {}).get("argument_sources", {})
            for name, contract in list(sources.get("properties", {}).items()):
                if not isinstance(contract, dict) or "$ref" in contract:
                    continue
                encoded = json.dumps(contract, ensure_ascii=False, separators=(",", ":"))
                if encoded not in known:
                    key = f"FastArgumentSourceSpan{len(known)}"
                    while key in definitions:
                        key += "_"
                    definitions[key] = contract
                    known[encoded] = key
                sources["properties"][name] = {"$ref": f"#/$defs/{known[encoded]}"}
            for key, value in node.items():
                if key != "$defs":
                    visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(schema)


def _share_stream_activity_branches(schema: dict[str, Any]) -> None:
    """Compile each distinct Activity branch once across decision states.

    Decision states repeat the same Capability branches; XGrammar compiles every inline
    copy, so a two-Responsibility turn's grammar took 2.7 s instead of 1.1 s. Identical
    branches become one shared definition; the decoded language is unchanged.
    """
    definitions = schema.setdefault("$defs", {})
    known: dict[str, str] = {}

    def share(branch: Any) -> Any:
        if not isinstance(branch, dict) or "$ref" in branch:
            return branch
        encoded = json.dumps(branch, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if encoded not in known:
            key = f"FastActivityBranch{len(known)}"
            while key in definitions:
                key += "_"
            definitions[key] = branch
            known[encoded] = key
        return {"$ref": f"#/$defs/{known[encoded]}"}

    for state in schema.get("oneOf") or []:
        activities = state.get("properties", {}).get("activities", {}) if isinstance(state, dict) else {}
        items = activities.get("items")
        if not isinstance(items, dict) or not isinstance(items.get("oneOf"), list):
            continue
        items["oneOf"] = [share(branch) for branch in items["oneOf"]]
        # A decided Responsibility's own Activity offers the same branches.
        prefix = activities.get("prefixItems")
        if isinstance(prefix, list):
            activities["prefixItems"] = [
                {**member, "oneOf": [share(branch) for branch in member["oneOf"]]}
                if isinstance(member, dict) and isinstance(member.get("oneOf"), list) else share(member)
                for member in prefix
            ]


def _bound_ga_ownership_rows(schema: dict[str, Any]) -> None:
    """Expose GA's existing one-owner-per-source limit to the native decoder."""
    definitions = schema.get("$defs", {})
    association_refs = (
        definitions.get("GoalAssociationModelAssociation", {})
        .get("properties", {}).get("source_responsibility_refs", {})
        .get("items", {}).get("enum")
    )
    new_goal_refs = (
        definitions.get("GoalAssociationModelGoal", {})
        .get("properties", {}).get("source_responsibility_refs", {})
        .get("items", {}).get("enum")
    )
    if not isinstance(association_refs, list) or not association_refs or association_refs != new_goal_refs:
        return
    for name in ("associations", "new_goals"):
        rows = schema.get("properties", {}).get(name)
        if isinstance(rows, dict):
            rows["maxItems"] = min(rows.get("maxItems", len(association_refs)), len(association_refs))


def _complete_ga_change_branches(schema: dict[str, Any]) -> None:
    """Give each GA change branch the whole change shape the native decoder must write.

    The decoder follows a ``oneOf`` branch and ignores the sibling ``properties``, so fields
    named only there were never decoded (live 2026-10-26, a later conversation's
    "明天早上上班要不要带伞？": a requirement change came out without its required
    ``source_responsibility_refs``; a binding change would lose its ``path`` the same way).
    """
    for name in ("GoalAssociationModelRequirementChange", "GoalAssociationModelBindingChange"):
        node = schema.get("$defs", {}).get(name, {})
        for branch in node.get("oneOf") or []:
            if not isinstance(branch.get("properties"), dict):
                continue
            branch["properties"] = {**copy.deepcopy(node.get("properties") or {}), **branch["properties"]}
            branch["required"] = list(dict.fromkeys([*(node.get("required") or []), *branch.get("required", [])]))
            branch["additionalProperties"] = False


def _disjoint_ga_goal_links(schema: dict[str, Any]) -> None:
    """Let a new Goal relate to or supersede a retained Goal, never both, in the native decoder.

    The schema states the disjointness with ``not``/``contains``, which the decoder ignores
    (live 2026-10-27, "好呀，记住吧。": a new Goal related to and superseded the same Goal and
    the DTO rejected it). Up to three candidates are offered as one branch per related subset
    whose superseded subsets come from the remaining candidates.
    """
    goal = schema.get("$defs", {}).get("GoalAssociationModelGoal", {})
    properties = goal.get("properties") or {}
    candidates = ((properties.get("related_goal_ids") or {}).get("items") or {}).get("enum")
    if not isinstance(candidates, list) or not candidates or len(candidates) > 3:
        return

    def subsets(values: list[Any]) -> list[list[Any]]:
        return [list(subset) for size in range(len(values) + 1) for subset in itertools.combinations(values, size)]

    branches = []
    for related in subsets(candidates):
        branch = {"type": "object", "additionalProperties": False, "required": list(goal.get("required") or []),
                  "properties": copy.deepcopy(properties)}
        branch["properties"]["related_goal_ids"] = {"type": "array", "enum": [related]}
        branch["properties"]["supersedes_goal_ids"] = {
            "type": "array", "enum": subsets([value for value in candidates if value not in related])}
        branches.append(branch)
    goal.pop("anyOf", None)
    goal.pop("allOf", None)
    goal["oneOf"] = branches


def _bound_ga_requirement_indices(schema: dict[str, Any]) -> None:
    """Expose GA's unique requirement indices to the native decoder, which ignores uniqueItems.

    Live 2026-10-26 (memory_plan_en): ``replace_requirement_indices`` came out as
    ``[0, 0, 0, ...]`` until the output was truncated. Up to four requirements are offered as
    their exact ordered subsets; a longer Goal is bounded by its requirement count. The DTO
    still rejects repeats.
    """
    change = schema.get("$defs", {}).get("GoalAssociationModelRequirementChange", {})
    for branch in change.get("oneOf") or []:
        indices = (branch.get("properties") or {}).get("replace_requirement_indices")
        values = ((indices or {}).get("items") or {}).get("enum") if isinstance(indices, dict) else None
        if not isinstance(values, list):
            continue
        if len(values) <= 4:
            branch["properties"]["replace_requirement_indices"] = {"type": "array", "enum": [
                list(subset) for size in range(len(values) + 1)
                for subset in itertools.combinations(values, size)]}
        else:
            indices["maxItems"] = len(values)


def _bound_ga_requirement_changes(schema: dict[str, Any]) -> None:
    """Expose GA's one-change-per-target-Goal rule to the native decoder.

    Live 2026-10-28 (child_bedtime_zh T2, "给我讲个很短的睡前故事吧。"): a modify of the one candidate
    Goal repeated the same requirement change until the output was truncated. The DTO already
    rejects repeated targets, and each change branch names one changeable Goal, so the decoder
    gets at most one change per branch.
    """
    definitions = schema.get("$defs", {})
    branches = [branch for branch in (definitions.get("GoalAssociationModelRequirementChange") or {}).get("oneOf") or []
                if branch != {"not": {}}]
    changes = ((definitions.get("GoalAssociationModelAssociation") or {}).get("properties") or {}).get(
        "requirement_changes")
    if isinstance(changes, dict) and branches:
        changes["maxItems"] = min(changes.get("maxItems", len(branches)), len(branches))


def _empty_impossible_arrays(schema: dict[str, Any]) -> None:
    """Close arrays whose items no value can satisfy, which the native decoder cannot see.

    ``{"not": {}}`` admits nothing, but the decoder ignores ``not`` and decodes any object
    (live 2026-10-27, "我刚才说要买什么来着？": with no UMI binding to copy, GA wrote a binding
    change of its own shape and the DTO rejected the turn). Such an array is decoded empty.
    """
    definitions = schema.get("$defs") or {}

    def impossible(node: Any) -> bool:
        if isinstance(node, dict) and isinstance(node.get("$ref"), str):
            node = definitions.get(node["$ref"].rsplit("/", 1)[-1])
        return isinstance(node, dict) and (node.get("not") == {} or node.get("oneOf") == [{"not": {}}])

    def close(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") == "array" and impossible(node.get("items")):
                node["maxItems"] = 0
            for value in node.values():
                close(value)
        elif isinstance(node, list):
            for value in node:
                close(value)

    close(schema)


def _ga_relationship_branches(schema: dict[str, Any]) -> None:
    """State GA's modify/clarify invariant as branches the native decoder follows.

    A modify or clarify association needs a requirement change or a resolved gap; the schema
    says so with ``if``/``then``, which the decoder ignores (live 2026-10-27, "那下班的时候呢？":
    a modify carried neither and the DTO rejected the turn). Each relationship group gets its own
    complete shape; a change or gap branch exists only when the request allows one.
    """
    definitions = schema.get("$defs") or {}
    association = definitions.get("GoalAssociationModelAssociation")
    fields = (association or {}).get("properties") or {}
    relationships = list((fields.get("relationship") or {}).get("enum") or [])
    if not relationships or "oneOf" in association:
        return
    change = definitions.get("GoalAssociationModelRequirementChange") or {}
    can_change = change.get("oneOf") != [{"not": {}}] and (fields.get("requirement_changes") or {}).get("maxItems") != 0
    gaps = (fields.get("resolved_gap_ids") or {})
    can_resolve = bool((gaps.get("items") or {}).get("enum")) and gaps.get("maxItems") != 0
    updates = [name for name in relationships if name in {"modify", "clarify"}]

    def branch(names: list[str], required_field: str | None) -> dict[str, Any]:
        shape = copy.deepcopy(fields)
        shape["relationship"] = {**shape["relationship"], "enum": names}
        if required_field:
            shape[required_field] = {**shape[required_field], "minItems": 1}
        elif "requirement_changes" in shape:
            # The DTO lets only modify/clarify change Goal requirements.
            shape["requirement_changes"] = {**shape["requirement_changes"], "maxItems": 0}
        return {"type": "object", "additionalProperties": False, "properties": shape,
                "required": [*association.get("required", []), *([required_field] if required_field else [])]}

    branches = [
        *([branch(updates, "requirement_changes")] if updates and can_change else []),
        *([branch(updates, "resolved_gap_ids")] if updates and can_resolve else []),
        branch([name for name in relationships if name not in {"modify", "clarify"}], None),
    ]
    association.pop("allOf", None)
    association.pop("anyOf", None)
    association["oneOf"] = branches


def _openai_response_format(response_format: Any) -> dict[str, Any] | None:
    if response_format == "text":
        return None
    if response_format == "json":
        return {"type": "json_object"}
    if isinstance(response_format, dict):
        schema, _ = candidate_compatible_schema(response_format)
        if schema.get("title") == "GoalAssociationModelOutput":
            _bound_ga_ownership_rows(schema)
            _complete_ga_change_branches(schema)
            _disjoint_ga_goal_links(schema)
            _bound_ga_requirement_indices(schema)
            _bound_ga_requirement_changes(schema)
            _empty_impossible_arrays(schema)
            _ga_relationship_branches(schema)
        if schema.get("title") == "FastPlannerWorkAdvanceOutput":
            _stream_decoder_constraints(schema)
        if schema.get("title") in {
            "AgentSkillSelectionModelOutput",
            "FastPlannerModelOutput", "FastPlannerMultiGoalPlanOutput",
            "FastPlannerWorkAdvanceOutput", "FastPlannerEvidenceReentryOutput",
            "SocialCognitionOutput",
        }:
            # Native intersections can hide required object/array fields. Repeat
            # their existing shape for decoding; original DTO/Host rules remain.
            expose_intersection_shapes(schema)
        if schema.get("title") == "FastPlannerWorkAdvanceOutput":
            _share_stream_source_spans(schema)
            _share_stream_activity_branches(schema)
        if schema.get("title") in {
            "GoalAssociationModelOutput", "GoalSegmentationModelOutput",
            "AgentSkillSelectionModelOutput",
            "FastPlannerModelOutput", "FastPlannerMultiGoalPlanOutput",
            "FastPlannerWorkAdvanceOutput", "FastPlannerEvidenceReentryOutput", "SocialCognitionOutput",
            "CognitiveActivationDecision",
        }:
            # Formatting belongs to this request, never to the shared model's
            # global settings. This also prevents the reproduced Planner/Skill JSON
            # whitespace loop; strings retain their exact model-authored content.
            schema["x-guidance"] = {"whitespace_flexible": False}
        if schema.get("title") == "UserMeaningInterpretationDecision":
            # Preserve flexible JSON layout while preventing structural whitespace
            # from consuming UMI's output budget. String contents are unchanged.
            schema["x-guidance"] = {"max_whitespace_cnt": 16}
        return {
            "type": "json_schema",
            "json_schema": {
                "name": "chromie_response",
                "strict": True,
                "schema": schema,
            },
        }
    raise ValueError(f"Unsupported response_format: {response_format!r}")


def build_sglang_chat_payload(
    *,
    model: str,
    messages: list[dict[str, str]],
    compute_class: CognitionComputeClass,
    options: dict[str, Any] | None,
    response_format: Any,
    stream: bool,
    priority_step: int,
) -> dict[str, Any]:
    """Build the qualified SGLang OpenAI-compatible request without semantics."""

    resolved_options = dict(options or {})
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": bool(stream),
        "temperature": float(resolved_options.get("temperature", 0.0)),
        "priority": sglang_priority(compute_class, step=priority_step),
    }
    if "qwen3" in model.casefold():
        payload["chat_template_kwargs"] = {"enable_thinking": False}
    max_tokens = int(resolved_options.get("num_predict") or 0)
    if max_tokens > 0:
        payload["max_tokens"] = max_tokens
    for source_name, wire_name in (
        ("top_p", "top_p"),
        ("seed", "seed"),
        ("frequency_penalty", "frequency_penalty"),
        ("presence_penalty", "presence_penalty"),
    ):
        value = resolved_options.get(source_name)
        if value is not None:
            payload[wire_name] = value
    stop = resolved_options.get("stop")
    if stop not in (None, "", []):
        payload["stop"] = stop
    wire_format = _openai_response_format(response_format)
    if wire_format is not None:
        payload["response_format"] = wire_format
    return payload


def _reasoning_value(mapping: dict[str, Any]) -> Any:
    for field in ("reasoning", "reasoning_content", "thinking"):
        value = mapping.get(field)
        if value not in (None, "", [], {}):
            return value
    return None


def assert_no_sglang_reasoning(payload: dict[str, Any]) -> None:
    """Fail closed if a supposedly non-thinking response exposes reasoning."""

    if _reasoning_value(payload) is not None:
        raise ValueError("SGLang response exposed reasoning output")
    choices = payload.get("choices")
    if not isinstance(choices, list):
        return
    for choice in choices:
        if not isinstance(choice, dict):
            continue
        assert_no_sglang_reasoning(choice)
        for field in ("message", "delta"):
            nested = choice.get(field)
            if isinstance(nested, dict) and _reasoning_value(nested) is not None:
                raise ValueError("SGLang response exposed reasoning output")


def sglang_completion_content(payload: dict[str, Any]) -> tuple[str, str | None]:
    assert_no_sglang_reasoning(payload)
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise ValueError("SGLang response has no completion choice")
    choice = choices[0]
    message = choice.get("message")
    if not isinstance(message, dict):
        raise ValueError("SGLang completion choice has no message")
    content = message.get("content")
    if not isinstance(content, str):
        raise ValueError("SGLang completion message has no text content")
    finish_reason = choice.get("finish_reason")
    return content, str(finish_reason) if finish_reason is not None else None


def sglang_stream_delta(payload: dict[str, Any]) -> tuple[str, str | None]:
    assert_no_sglang_reasoning(payload)
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return "", None
    choice = choices[0]
    delta = choice.get("delta")
    content = delta.get("content") if isinstance(delta, dict) else ""
    finish_reason = choice.get("finish_reason")
    return (
        content if isinstance(content, str) else "",
        str(finish_reason) if finish_reason is not None else None,
    )


def sglang_to_completion_evidence(payload: dict[str, Any]) -> dict[str, Any]:
    """Project OpenAI completion metadata into Chromie's existing budget evidence shape."""

    content, finish_reason = sglang_completion_content(payload)
    usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
    return {
        "model": payload.get("model"),
        "message": {"role": "assistant", "content": content},
        "done": finish_reason is not None,
        "done_reason": finish_reason,
        "prompt_eval_count": usage.get("prompt_tokens"),
        "eval_count": usage.get("completion_tokens"),
    }
