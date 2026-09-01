#!/usr/bin/env python3
"""Validate the frozen Goal Association corpus against production contracts."""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.app.goal_association import GoalAssociationResolver  # noqa: E402
from agent.app.goal_association_contract import (  # noqa: E402
    GoalAssociationModelOutput,
    GoalSegmentationModelOutput,
)
from agent.app.goal_association_prompt import discourse_referents  # noqa: E402
from agent.app.goal_association_schema import goal_association_response_schema  # noqa: E402
from shared.chromie_contracts.core_interpretation import CognitiveWorkRequest  # noqa: E402


DATASET_ROOT = ROOT / "benchmarks" / "datasets" / "goal_association_daily_life"
SCENARIO_ROOT = DATASET_ROOT / "scenarios"
MANIFEST_PATH = DATASET_ROOT / "dataset.json"
DATASET_ID = "chromie.goal_association_daily_life.v1"
SCENARIO_COUNT = 1_500
FAMILIES = (
    "create_without_candidates",
    "continue_active",
    "modify_active",
    "clarify_open_gap",
    "confirm_pending",
    "reject_pending",
    "cancel_active",
    "pause_running",
    "resume_paused",
    "reference_terminal",
    "supersede_existing",
    "unrelated_new_goal",
    "merge_existing_goals",
    "split_existing_goal",
    "mixed_continue_and_new_contract_gap",
)


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
FORBIDDEN_OUTPUT_KEYS = {
    "activities",
    "capability_id",
    "execution_lane",
    "plan",
    "provider_id",
    "requires_replan",
    "response_text",
    "skill_id",
    "tool_name",
    "work_items",
}


class _ReferenceModel:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.calls = 0

    async def generate(self, prompt: Any, **kwargs: Any) -> dict[str, Any]:
        self.calls += 1
        return self.payload


def scenario_paths(dataset_root: Path = DATASET_ROOT) -> list[Path]:
    return sorted((dataset_root / "scenarios").glob("*/*/*.json"))


def load_cases(dataset_root: Path = DATASET_ROOT) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for path in scenario_paths(dataset_root):
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError(f"{path}: scenario must be an object")
        case_id = str(value.get("id") or "")
        if path.stem != case_id:
            raise ValueError(f"{path}: file stem does not match scenario id")
        if path.parent.name != value.get("category"):
            raise ValueError(f"{path}: category directory does not match scenario")
        if path.parent.parent.name != value.get("split"):
            raise ValueError(f"{path}: split directory does not match scenario")
        cases.append(value)
    return cases


def scenario_tree_digest(dataset_root: Path = DATASET_ROOT) -> str:
    digest = hashlib.sha256()
    for path in scenario_paths(dataset_root):
        digest.update(path.relative_to(dataset_root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _walk_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {key for item in value.values() for key in _walk_keys(item)}
    if isinstance(value, list):
        return {key for item in value for key in _walk_keys(item)}
    return set()


def _request_schema(request: CognitiveWorkRequest) -> tuple[type[Any], dict[str, Any], list[dict[str, Any]]]:
    resolver = GoalAssociationResolver(_ReferenceModel({}))
    candidates = resolver._candidate_goals(request)
    output_type: type[Any] = GoalAssociationModelOutput if candidates else GoalSegmentationModelOutput
    schema = goal_association_response_schema(
        output_type,
        candidates,
        discourse_referents(request),
        responsibility_count=len(request.responsibilities),
        responsibility_refs=[item.local_ref for item in request.responsibilities],
        responsibility_output_modes={
            item.local_ref: item.output_mode
            for item in request.responsibilities
            if item.output_mode != "unspecified"
        },
        responsibility_information_refs={
            item.local_ref
            for item in request.responsibilities
            if item.output_mode == "information"
        },
        responsibility_bindings={
            item.local_ref: {
                str(name): value
                for name, value in item.bindings.items()
                if isinstance(value, (str, int, float, bool))
            }
            for item in request.responsibilities
        },
    )
    return output_type, schema, candidates


def _responsibility_map(reference: dict[str, Any]) -> list[dict[str, Any]]:
    mapped: list[dict[str, Any]] = []
    for association in reference.get("associations", []):
        for source_ref in association["source_responsibility_refs"]:
            mapped.append({
                "source_ref": source_ref,
                "operation": "association",
                "relationship": association["relationship"],
                "target_goal_ids": association["target_goal_ids"],
            })
    for goal in reference.get("new_goals", []):
        for source_ref in goal["source_responsibility_refs"]:
            mapped.append({
                "source_ref": source_ref,
                "operation": "new_goal",
                "relationship": "new",
                "target_goal_ids": [],
                "output_mode": goal["output_mode"],
                "supersedes_goal_ids": goal["supersedes_goal_ids"],
            })
    return sorted(mapped, key=lambda item: item["source_ref"])


async def _validate_cases(cases: list[dict[str, Any]]) -> tuple[list[str], dict[str, int]]:
    errors: list[str] = []
    counts = Counter()
    seen_ids: set[str] = set()
    seen_requests: set[str] = set()
    contrast_members: dict[str, set[str]] = defaultdict(set)

    for case in cases:
        case_id = str(case.get("id") or "")
        try:
            if set(case) != TOP_LEVEL_KEYS:
                raise ValueError(f"unexpected top-level keys: {sorted(set(case) ^ TOP_LEVEL_KEYS)}")
            if case["schema_version"] != 1 or case["dataset_id"] != DATASET_ID:
                raise ValueError("dataset/schema identity mismatch")
            if not case_id or case_id in seen_ids:
                raise ValueError("missing or duplicate scenario id")
            seen_ids.add(case_id)
            if case["category"] not in FAMILIES:
                raise ValueError(f"unknown category {case['category']!r}")
            if case["split"] not in {"train_candidate", "validation", "frozen_test"}:
                raise ValueError(f"unknown split {case['split']!r}")
            if case["input"]["language"] not in {"en-US", "zh-CN"}:
                raise ValueError("unsupported language")
            request = CognitiveWorkRequest.model_validate(case["input"]["request"])
            if request.language != case["input"]["language"]:
                raise ValueError("request language drift")
            request_key = json.dumps(request.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
            if request_key in seen_requests:
                raise ValueError("duplicate complete GA request")
            seen_requests.add(request_key)

            contrast = case["contrast_set"]
            contrast_members[str(contrast["id"])].add(str(contrast["member"]))
            if contrast["member"] != case["category"]:
                raise ValueError("contrast member/category drift")

            target = case["target"]
            reference = target["reference_model_output"]
            forbidden = _walk_keys(reference) & FORBIDDEN_OUTPUT_KEYS
            if forbidden:
                raise ValueError(f"reference crosses authority boundary: {sorted(forbidden)}")
            expected_map = target["semantic_expectations"]["responsibility_map"]
            if _responsibility_map(reference) != expected_map:
                raise ValueError("semantic responsibility map drift")
            source_refs = sorted(item.local_ref for item in request.responsibilities)
            mapped_refs = sorted(item["source_ref"] for item in expected_map)
            if source_refs != mapped_refs:
                raise ValueError(f"Responsibility conservation drift: {source_refs} != {mapped_refs}")

            output_type, schema, candidates = _request_schema(request)
            declared_candidates = target["semantic_expectations"]["candidate_goal_ids"]
            if [item["goal_id"] for item in candidates] != declared_candidates:
                raise ValueError("candidate Goal projection drift")
            schema_errors = list(Draft202012Validator(schema).iter_errors(reference))
            expectation = target["schema_expectation"]
            if expectation == "accept":
                if target["contract_gap"] is not None:
                    raise ValueError("accepted reference must not declare a contract gap")
                if schema_errors:
                    raise ValueError(f"reference schema failure: {schema_errors[0].message}")
                output_type.model_validate(reference)
                model = _ReferenceModel(reference)
                resolution = await GoalAssociationResolver(model).resolve(request)
                if resolution.resolution_status != "resolved" or model.calls != 1:
                    raise ValueError(
                        f"production resolver reference failed: status={resolution.resolution_status} calls={model.calls}"
                    )
                counts["host_accepted"] += 1
            else:
                raise ValueError(f"unknown schema expectation {expectation!r}")

            if case["review"] != {
                "origin": "assistant_authored_contrast_matrix",
                "reviewer_kind": "assistant_reference_model",
                "review_status": "mechanically_validated_dataset_candidate",
                "independent_semantic_review": False,
                "training_eligible": False,
                "qualification_required": "owner_review_and_frozen_one_batch_execution",
            }:
                raise ValueError("review/qualification boundary changed")
            counts["validated"] += 1
        except Exception as exc:
            errors.append(f"{case_id or '<unknown>'}: {type(exc).__name__}: {exc}")

    required_members = set(FAMILIES)
    for contrast_id, members in contrast_members.items():
        if members != required_members:
            errors.append(f"{contrast_id}: contrast membership drift: {sorted(members ^ required_members)}")
    if len(contrast_members) != 100:
        errors.append(f"contrast set count: actual={len(contrast_members)} expected=100")
    return errors, dict(counts)


def validate_dataset() -> dict[str, Any]:
    cases = load_cases()
    errors, runtime_counts = asyncio.run(_validate_cases(cases))
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if len(cases) != SCENARIO_COUNT:
        errors.append(f"scenario count: actual={len(cases)} expected={SCENARIO_COUNT}")
    actual_digest = scenario_tree_digest()
    declared_digest = manifest.get("asset_contract", {}).get("scenario_tree_sha256")
    if actual_digest != declared_digest:
        errors.append(f"scenario tree digest mismatch: actual={actual_digest} declared={declared_digest}")
    actual_coverage = {
        "categories": dict(sorted(Counter(case["category"] for case in cases).items())),
        "independent_semantic_review": False,
        "languages": dict(sorted(Counter(case["input"]["language"] for case in cases).items())),
        "scenario_count": len(cases),
        "schema_expectations": dict(sorted(Counter(case["target"]["schema_expectation"] for case in cases).items())),
        "splits": dict(sorted(Counter(case["split"] for case in cases).items())),
        "training_eligible": False,
    }
    if manifest.get("coverage_contract") != actual_coverage:
        errors.append("dataset manifest coverage does not match discovered scenario files")
    summary = {
        "dataset_id": DATASET_ID,
        "scenario_count": len(cases),
        "languages": dict(sorted(Counter(case["input"]["language"] for case in cases).items())),
        "splits": dict(sorted(Counter(case["split"] for case in cases).items())),
        "categories": dict(sorted(Counter(case["category"] for case in cases).items())),
        "runtime": runtime_counts,
        "errors": errors,
    }
    if errors:
        raise ValueError("\n".join(errors[:50]))
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print the summary as JSON")
    args = parser.parse_args()
    try:
        summary = validate_dataset()
    except Exception as exc:
        print(f"Goal Association dataset validation failed:\n{exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            "Goal Association dataset validation passed: "
            f"{summary['scenario_count']} scenarios; "
            f"Host accepted {summary['runtime'].get('host_accepted', 0)}; "
            f"known contract gaps {summary['runtime'].get('known_contract_gaps', 0)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
