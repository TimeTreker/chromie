#!/usr/bin/env python3
"""Validate the checked-in daily-life Goal Interpretation scenario assets."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import sys
from typing import Any

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.app.cognitive_core.goal_interpreter.model_interpreter import (  # noqa: E402
    OllamaGoalInterpreter,
)
from agent.app.cognitive_core.goal_interpreter.schema import (  # noqa: E402
    GoalInterpretationRequest,
)


DATASET_ROOT = ROOT / "benchmarks" / "datasets" / "goal_interpretation_daily_life"
SCENARIO_ROOT = DATASET_ROOT / "scenarios"

TOP_LEVEL_KEYS = {
    "schema_version",
    "id",
    "dataset_id",
    "split",
    "category",
    "difficulty",
    "contrast_set",
    "input",
    "target",
    "invariants",
    "adversarial_design",
    "review",
}
FORBIDDEN_WIRE_KEYS = {
    "actions",
    "activities",
    "capability_id",
    "execution_lane",
    "goal_id",
    "information_gaps",
    "plan",
    "provider_id",
    "response_text",
    "route",
    "skill_id",
    "task_id",
    "tool_name",
    "work_items",
}


def scenario_paths(dataset_root: Path = DATASET_ROOT) -> list[Path]:
    return sorted((dataset_root / "scenarios").glob("*/*/*.json"))


def _walk_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {
            key for child in value.values() for key in _walk_keys(child)
        }
    if isinstance(value, list):
        return {key for child in value for key in _walk_keys(child)}
    return set()


def _builder(case: dict[str, Any]) -> str:
    prefix = f"gi_daily_v1_{case['category']}_"
    contrast_id = str(case["contrast_set"]["id"])
    if not contrast_id.startswith(prefix):
        raise ValueError(
            f"{case['id']}: contrast_set.id does not begin with {prefix!r}"
        )
    builder, language_slug = contrast_id[len(prefix) :].rsplit("_", 1)
    expected_slug = "zh" if case["input"]["language"] == "zh-CN" else "en"
    if language_slug != expected_slug:
        raise ValueError(
            f"{case['id']}: contrast language {language_slug!r} != {expected_slug!r}"
        )
    return builder


def _validate_case_shape(path: Path, case: dict[str, Any]) -> None:
    case_id = str(case.get("id") or "")
    if set(case) != TOP_LEVEL_KEYS:
        raise ValueError(
            f"{case_id or path}: unexpected top-level keys: "
            f"{sorted(set(case) ^ TOP_LEVEL_KEYS)}"
        )
    if case["schema_version"] != 1:
        raise ValueError(f"{case_id}: schema_version must be 1")
    if case["dataset_id"] != "chromie.goal_interpretation_daily_life.v1":
        raise ValueError(f"{case_id}: wrong dataset_id")
    if path.stem != case_id:
        raise ValueError(f"{case_id}: file stem does not match id")
    if path.parent.name != case["category"] or path.parent.parent.name != case["split"]:
        raise ValueError(f"{case_id}: path does not match split/category")
    if case["split"] not in {"train_candidate", "validation", "frozen_test"}:
        raise ValueError(f"{case_id}: unknown split")
    if case["difficulty"] not in {"medium", "hard"}:
        raise ValueError(f"{case_id}: unsupported difficulty")
    if case["input"]["language"] not in {"zh-CN", "en-US"}:
        raise ValueError(f"{case_id}: unsupported language")
    if not str(case["input"]["text"]).strip():
        raise ValueError(f"{case_id}: empty input text")
    if not isinstance(case["input"]["context"], dict):
        raise ValueError(f"{case_id}: input.context must be an object")

    review = case["review"]
    if review != {
        "origin": "assistant_authored_contrast_set",
        "reviewer_kind": "assistant_reference_model",
        "review_status": "mechanically_validated_dataset_candidate",
        "independent_semantic_review": False,
        "training_eligible": False,
        "qualification_required": "independent_human_review_and_frozen_execution",
    }:
        raise ValueError(f"{case_id}: review boundary changed without promotion")

    wire = case["target"]["reference_wire_output"]
    semantic = case["target"]["semantic_expectations"]
    responsibilities = wire["responsibilities"]
    if semantic["responsibility_count"] != len(responsibilities):
        raise ValueError(f"{case_id}: responsibility count expectation drift")
    if semantic["coordination"] != wire["coordination"]:
        raise ValueError(f"{case_id}: coordination expectation drift")
    if semantic["unresolved"] != bool(wire["unresolved"]):
        raise ValueError(f"{case_id}: unresolved expectation drift")
    if len(semantic["responsibilities"]) != len(responsibilities):
        raise ValueError(f"{case_id}: semantic Responsibility list drift")
    for reference, expectation in zip(
        responsibilities, semantic["responsibilities"], strict=True
    ):
        bindings = reference["binding_items"]
        if list(bindings) != sorted(bindings):
            raise ValueError(f"{case_id}: binding keys are not lexicographic")
        if expectation["local_ref"] != reference["local_ref"]:
            raise ValueError(f"{case_id}: local_ref expectation drift")
        if expectation["output_mode"] != reference["output_mode"]:
            raise ValueError(f"{case_id}: output_mode expectation drift")
        if expectation["required_bindings"] != bindings:
            raise ValueError(f"{case_id}: binding expectation drift")
        if not expectation["outcome_contains_any"]:
            raise ValueError(f"{case_id}: missing flexible outcome oracle")

    forbidden = _walk_keys(wire) & FORBIDDEN_WIRE_KEYS
    if forbidden:
        raise ValueError(
            f"{case_id}: reference wire output crosses downstream authority: "
            f"{sorted(forbidden)}"
        )
    invariants = case["invariants"]
    if set(invariants["must_not_emit_fields"]) != FORBIDDEN_WIRE_KEYS:
        raise ValueError(f"{case_id}: forbidden-field invariant drift")
    if not all(
        invariants[name]
        for name in (
            "one_semantic_authority_call",
            "bindings_are_sparse_and_source_or_context_grounded",
            "source_evidence_is_current_turn_only",
            "binding_keys_lexicographic",
        )
    ):
        raise ValueError(f"{case_id}: required invariant disabled")
    adversarial = case["adversarial_design"]
    if not adversarial["phenomena"] or len(adversarial["negative_hypotheses"]) < 4:
        raise ValueError(f"{case_id}: adversarial rationale is incomplete")


def validate_dataset(dataset_root: Path = DATASET_ROOT) -> dict[str, Any]:
    manifest = json.loads((dataset_root / "dataset.json").read_text(encoding="utf-8"))
    paths = scenario_paths(dataset_root)
    cases: list[dict[str, Any]] = []
    errors: list[str] = []
    interpreter = OllamaGoalInterpreter(
        ollama_url="http://dataset-validator.invalid",
        model="dataset-validator",
        timeout_ms=1000,
        num_ctx=32768,
        num_predict=2048,
    )
    host_accepted = 0
    known_host_gaps = 0

    for path in paths:
        try:
            case = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(case, dict):
                raise ValueError("scenario root must be an object")
            _validate_case_shape(path, case)
            request = GoalInterpretationRequest(
                text=case["input"]["text"],
                language=case["input"]["language"],
                context=case["input"]["context"],
            )
            wire = case["target"]["reference_wire_output"]
            schema = interpreter.build_interpretation_payload(request)["format"]
            schema_errors = list(Draft202012Validator(schema).iter_errors(wire))
            if schema_errors:
                raise ValueError(
                    "reference_wire_output schema failure: "
                    + schema_errors[0].message
                )
            host_expectation = case["target"].get(
                "host_validation_expectation", {"status": "accept"}
            )
            try:
                OllamaGoalInterpreter._validate_interpretation_content(
                    request, json.dumps(wire, ensure_ascii=False)
                )
            except Exception as exc:
                if (
                    host_expectation.get("status") == "known_contract_gap"
                    and host_expectation.get("error_contains") in str(exc)
                ):
                    known_host_gaps += 1
                else:
                    raise
            else:
                if host_expectation.get("status") != "accept":
                    raise ValueError(
                        "reference unexpectedly passed a declared Host contract gap"
                    )
                host_accepted += 1
            cases.append(case)
        except Exception as exc:  # retain all file errors for one audit pass
            errors.append(
                f"{path.relative_to(dataset_root)}: {type(exc).__name__}: {exc}"
            )

    coverage = manifest["coverage_contract"]
    if len(paths) != coverage["scenario_count"]:
        errors.append(
            f"scenario count: actual={len(paths)} declared={coverage['scenario_count']}"
        )
    if known_host_gaps != coverage.get("known_host_validation_gaps", 0):
        errors.append(
            "known Host gap count: "
            f"actual={known_host_gaps} "
            f"declared={coverage.get('known_host_validation_gaps', 0)}"
        )
    ids = [case["id"] for case in cases]
    if len(ids) != len(set(ids)):
        errors.append("scenario ids are not unique")
    inputs = [
        (
            case["input"]["language"],
            case["input"]["text"],
            json.dumps(case["input"]["context"], ensure_ascii=False, sort_keys=True),
        )
        for case in cases
    ]
    if len(inputs) != len(set(inputs)):
        errors.append("exact language/text/context inputs are not unique")

    contrast_splits: dict[str, set[str]] = defaultdict(set)
    contrast_counts: Counter[str] = Counter()
    for case in cases:
        contrast_id = case["contrast_set"]["id"]
        contrast_splits[contrast_id].add(case["split"])
        contrast_counts[contrast_id] += 1
    crossing = sorted(
        contrast_id
        for contrast_id, splits in contrast_splits.items()
        if len(splits) != 1
    )
    if crossing:
        errors.append(f"contrast sets cross splits: {crossing[:8]}")
    wrong_sizes = sorted(
        contrast_id
        for contrast_id, count in contrast_counts.items()
        if count != coverage["scenarios_per_contrast_set"]
    )
    if wrong_sizes:
        errors.append(f"contrast sets have wrong sizes: {wrong_sizes[:8]}")
    if len(contrast_counts) != coverage["contrast_set_count"]:
        errors.append(
            "contrast set count: "
            f"actual={len(contrast_counts)} declared={coverage['contrast_set_count']}"
        )

    actual_splits = Counter(case["split"] for case in cases)
    actual_languages = Counter(case["input"]["language"] for case in cases)
    actual_categories = Counter(case["category"] for case in cases)
    actual_builders = Counter(_builder(case) for case in cases)
    for label, actual, expected in (
        ("splits", actual_splits, coverage["splits"]),
        ("languages", actual_languages, coverage["languages"]),
        ("categories", actual_categories, coverage["categories"]),
        ("builders", actual_builders, coverage["builders"]),
    ):
        if dict(sorted(actual.items())) != dict(sorted(expected.items())):
            errors.append(
                f"{label} coverage drift: actual={dict(actual)} expected={expected}"
            )

    actual_dimensions: Counter[str] = Counter()
    actual_modes: Counter[str] = Counter()
    actual_relationships: Counter[str] = Counter()
    context_scenarios = 0
    unresolved_scenarios = 0
    for case in cases:
        context_scenarios += bool(case["input"]["context"])
        wire = case["target"]["reference_wire_output"]
        unresolved_scenarios += bool(wire["unresolved"])
        for responsibility in wire["responsibilities"]:
            actual_dimensions.update(responsibility["binding_items"].keys())
            actual_modes[responsibility["output_mode"]] += 1
            actual_relationships[responsibility.get("relationship", "new")] += 1
    actual_semantic_coverage = {
        "context_scenarios": context_scenarios,
        "unresolved_scenarios": unresolved_scenarios,
        "binding_dimensions": dict(sorted(actual_dimensions.items())),
        "output_modes": dict(sorted(actual_modes.items())),
        "relationships": dict(sorted(actual_relationships.items())),
    }
    if actual_semantic_coverage != coverage["semantic_coverage"]:
        errors.append(
            "semantic coverage drift: "
            f"actual={actual_semantic_coverage} "
            f"expected={coverage['semantic_coverage']}"
        )

    if errors:
        raise ValueError("\n".join(errors))
    return {
        "dataset_id": manifest["dataset_id"],
        "scenario_count": len(cases),
        "contrast_set_count": len(contrast_counts),
        "splits": dict(sorted(actual_splits.items())),
        "languages": dict(sorted(actual_languages.items())),
        "categories": dict(sorted(actual_categories.items())),
        "builders": dict(sorted(actual_builders.items())),
        "binding_dimensions": dict(sorted(actual_dimensions.items())),
        "output_modes": dict(sorted(actual_modes.items())),
        "relationships": dict(sorted(actual_relationships.items())),
        "context_scenarios": context_scenarios,
        "unresolved_scenarios": unresolved_scenarios,
        "dynamic_schema_passed": len(cases),
        "host_validation_passed": host_accepted,
        "known_host_validation_gaps": known_host_gaps,
        "independent_semantic_review": False,
        "training_eligible": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, default=DATASET_ROOT)
    args = parser.parse_args(argv)
    try:
        summary = validate_dataset(args.dataset_root.resolve())
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
