from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable, Mapping

from benchmarks.adapters.legacy_json import normalize_json_file
from benchmarks.contracts import ContractError


class DatasetValidationError(ValueError):
    """Raised when the reviewed Social Attention dataset violates its contract."""


_ID_PATTERN = re.compile(r"sa\.v1\.[a-z0-9_]+\.[a-z0-9_]+")
_FIXED_EXPECTATION_TOKENS = (
    "soridormi.",
    "nod_yes",
    "blink_once",
    "blink_twice",
    "look_direction",
    "required_gesture",
    "expected_action",
    "exact_gesture",
    "capability_id",
    "skill_id",  # retained-artifact leak must also stay forbidden
)
_FORBIDDEN_CONTEXT_KEYS = {
    "provider_backend",
    "backend_identity",
    "simulation_backend",
    "hardware_backend",
    "calibration",
    "joint_targets",
    "controller_params",
    "sim_only",
    "hardware_only",
}


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DatasetValidationError(f"cannot load JSON {path}: {exc}") from exc


def _text_for(case: Mapping[str, Any]) -> str:
    inputs = case.get("inputs", {})
    if not isinstance(inputs, Mapping):
        return ""
    text = inputs.get("text")
    if isinstance(text, str):
        return " ".join(text.casefold().split())
    turns = inputs.get("turns")
    if isinstance(turns, list):
        parts = []
        for turn in turns:
            if isinstance(turn, Mapping) and isinstance(turn.get("text"), str):
                parts.append(str(turn["text"]))
        return " ".join(" ".join(parts).casefold().split())
    return json.dumps(inputs, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _walk_keys(value: Any) -> Iterable[str]:
    if isinstance(value, Mapping):
        for key, item in value.items():
            yield str(key)
            yield from _walk_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_keys(item)


def _axis_counts(cases: list[Mapping[str, Any]], axis: str) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for case in cases:
        metadata = case.get("metadata", {})
        if isinstance(metadata, Mapping):
            value = metadata.get(axis)
            if isinstance(value, str):
                counter[value] += 1
    return dict(sorted(counter.items()))


def build_coverage_report(cases: list[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "dataset_id": "chromie.social_attention.v1",
        "total": len(cases),
        "by_cohort": _axis_counts(cases, "cohort"),
        "by_style": _axis_counts(cases, "style"),
        "by_mode": _axis_counts(cases, "mode"),
        "by_politeness": _axis_counts(cases, "politeness"),
        "by_language": _axis_counts(cases, "language"),
        "with_recent_auxiliary_evidence": sum(
            bool(case.get("context", {}).get("recent_auxiliary_behavior_evidence"))
            for case in cases
            if isinstance(case.get("context"), Mapping)
        ),
        "with_explicit_stillness": sum(
            bool(case.get("context", {}).get("user_preferences", {}).get("stillness_required"))
            for case in cases
            if isinstance(case.get("context"), Mapping)
            and isinstance(case.get("context", {}).get("user_preferences"), Mapping)
        ),
        "with_no_available_auxiliary_capability": sum(
            not bool(case.get("capabilities")) for case in cases
        ),
    }


def _validate_coverage(report: Mapping[str, Any], manifest: Mapping[str, Any]) -> None:
    minimums = manifest.get("minimum_coverage")
    if not isinstance(minimums, Mapping):
        raise DatasetValidationError("manifest minimum_coverage must be an object")
    report_keys = {
        "cohort": "by_cohort",
        "style": "by_style",
        "mode": "by_mode",
        "politeness": "by_politeness",
        "language": "by_language",
    }
    for axis, expected in minimums.items():
        if axis not in report_keys or not isinstance(expected, Mapping):
            raise DatasetValidationError(f"invalid minimum coverage axis: {axis!r}")
        actual = report.get(report_keys[axis], {})
        if not isinstance(actual, Mapping):
            raise DatasetValidationError(f"coverage report missing axis {axis!r}")
        for value, minimum in expected.items():
            if not isinstance(minimum, int) or minimum < 0:
                raise DatasetValidationError(f"invalid minimum for {axis}.{value}")
            if int(actual.get(value, 0)) < minimum:
                raise DatasetValidationError(
                    f"coverage {axis}.{value}={actual.get(value, 0)} is below {minimum}"
                )


def _validate_near_duplicates(cases: list[Mapping[str, Any]]) -> None:
    grouped: dict[str, list[tuple[str, str]]] = {}
    for case in cases:
        metadata = case.get("metadata", {})
        cohort = metadata.get("cohort") if isinstance(metadata, Mapping) else None
        if not isinstance(cohort, str):
            continue
        text = _text_for(case)
        if text:
            grouped.setdefault(cohort, []).append((str(case.get("id")), text))
    for cohort, items in grouped.items():
        for index, (left_id, left) in enumerate(items):
            for right_id, right in items[index + 1 :]:
                if left == right:
                    raise DatasetValidationError(
                        f"duplicate normalized input in {cohort}: {left_id} and {right_id}"
                    )
                ratio = difflib.SequenceMatcher(a=left, b=right).ratio()
                if ratio >= 0.94:
                    raise DatasetValidationError(
                        f"near-duplicate input in {cohort}: {left_id} and {right_id} ({ratio:.3f})"
                    )


def validate_dataset(
    dataset: Mapping[str, Any],
    manifest: Mapping[str, Any],
    *,
    repo_root: Path | None = None,
    dataset_path: Path | None = None,
) -> dict[str, Any]:
    if dataset.get("schema_version") != 1:
        raise DatasetValidationError("dataset schema_version must be 1")
    if dataset.get("dataset_id") != manifest.get("dataset_id"):
        raise DatasetValidationError("dataset_id does not match the manifest")
    authoring = dataset.get("authoring")
    policy = manifest.get("authoring_policy")
    if not isinstance(authoring, Mapping) or not isinstance(policy, Mapping):
        raise DatasetValidationError("dataset and manifest must declare authoring policy")
    if bool(authoring.get("runtime_policy_authority")):
        raise DatasetValidationError("benchmark dataset must not claim runtime policy authority")
    if authoring.get("review_status") != policy.get("required_review_status"):
        raise DatasetValidationError("dataset review status does not satisfy the manifest")
    if authoring.get("release_qualification") != policy.get("required_release_qualification"):
        raise DatasetValidationError("dataset release qualification is invalid")

    raw_cases = dataset.get("scenarios")
    if not isinstance(raw_cases, list):
        raise DatasetValidationError("dataset scenarios must be an array")
    minimum = int(manifest.get("minimum_case_count", 100))
    maximum = int(manifest.get("maximum_case_count", 150))
    expected = int(manifest.get("expected_case_count", len(raw_cases)))
    if not minimum <= len(raw_cases) <= maximum:
        raise DatasetValidationError(
            f"dataset case count {len(raw_cases)} is outside [{minimum}, {maximum}]"
        )
    if len(raw_cases) != expected:
        raise DatasetValidationError(
            f"dataset case count {len(raw_cases)} does not equal expected {expected}"
        )

    allowed_axes = manifest.get("allowed_axes")
    if not isinstance(allowed_axes, Mapping):
        raise DatasetValidationError("manifest allowed_axes must be an object")
    required_invariants = set(manifest.get("required_global_invariants", []))
    required_distribution = set(manifest.get("required_distribution_observations", []))
    seen_ids: set[str] = set()
    canonical_inputs: dict[str, str] = {}

    for index, raw_case in enumerate(raw_cases):
        if not isinstance(raw_case, Mapping):
            raise DatasetValidationError(f"scenario {index} must be an object")
        case = dict(raw_case)
        case_id = case.get("id")
        if not isinstance(case_id, str) or not _ID_PATTERN.fullmatch(case_id):
            raise DatasetValidationError(f"invalid Social Attention scenario ID: {case_id!r}")
        if case_id in seen_ids:
            raise DatasetValidationError(f"duplicate Social Attention scenario ID: {case_id}")
        seen_ids.add(case_id)

        metadata = case.get("metadata")
        context = case.get("context")
        if not isinstance(metadata, Mapping) or not isinstance(context, Mapping):
            raise DatasetValidationError(f"{case_id} must declare metadata and context")
        for axis, allowed in allowed_axes.items():
            value = metadata.get(axis)
            if value not in allowed:
                raise DatasetValidationError(f"{case_id} has invalid {axis}: {value!r}")
        authoring_context = context.get("authoring")
        if not isinstance(authoring_context, Mapping):
            raise DatasetValidationError(f"{case_id} lacks authoring provenance")
        if authoring_context.get("review_status") != policy.get("required_review_status"):
            raise DatasetValidationError(f"{case_id} is not reviewed")
        if authoring_context.get("release_qualification") != policy.get(
            "required_release_qualification"
        ):
            raise DatasetValidationError(f"{case_id} overclaims release qualification")

        auxiliary = case.get("acceptable_auxiliary_behavior")
        if not isinstance(auxiliary, list) or "none" not in auxiliary:
            raise DatasetValidationError(f"{case_id} must keep none as an acceptable decision")
        expectation_text = json.dumps(
            {
                "acceptable_auxiliary_behavior": auxiliary,
                "primary_outcome": case.get("primary_outcome"),
                "invariants": case.get("invariants"),
            },
            ensure_ascii=False,
        ).casefold()
        for token in _FIXED_EXPECTATION_TOKENS:
            if token in expectation_text:
                raise DatasetValidationError(
                    f"{case_id} contains fixed action/skill expectation token {token!r}"
                )
        context_keys = set(_walk_keys(context))
        leaked = sorted(context_keys & _FORBIDDEN_CONTEXT_KEYS)
        if leaked:
            raise DatasetValidationError(f"{case_id} leaks backend/calibration keys: {leaked}")
        capabilities = case.get("capabilities")
        if not isinstance(capabilities, list) or not all(
            isinstance(item, str) and item.startswith("social_attention.")
            for item in capabilities
        ):
            raise DatasetValidationError(
                f"{case_id} capabilities must be backend-neutral social_attention.* labels"
            )
        invariants = set(case.get("invariants", []))
        distribution = set(case.get("distribution_observations", []))
        if not required_invariants <= invariants:
            raise DatasetValidationError(
                f"{case_id} misses global invariants: {sorted(required_invariants - invariants)}"
            )
        if not required_distribution <= distribution:
            raise DatasetValidationError(
                f"{case_id} misses distribution observations: "
                f"{sorted(required_distribution - distribution)}"
            )

        mode = metadata.get("mode")
        forbidden = set(case.get("forbidden_behaviors", []))
        if mode == "off":
            if auxiliary != ["none"] or "off_mode_proposal_or_execution" not in forbidden:
                raise DatasetValidationError(f"{case_id} violates off-mode isolation")
        if mode == "report_only":
            if "report_only_execution" not in forbidden or "report_only_never_executes" not in invariants:
                raise DatasetValidationError(f"{case_id} violates report-only isolation")
        preferences = context.get("user_preferences")
        if isinstance(preferences, Mapping) and preferences.get("stillness_required"):
            if auxiliary != ["none"] or "user_stillness_violation" not in forbidden:
                raise DatasetValidationError(f"{case_id} violates explicit stillness contract")

        canonical = json.dumps(case.get("inputs"), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if canonical in canonical_inputs:
            raise DatasetValidationError(
                f"duplicate input contract: {canonical_inputs[canonical]} and {case_id}"
            )
        canonical_inputs[canonical] = case_id

    _validate_near_duplicates([dict(case) for case in raw_cases])
    report = build_coverage_report([dict(case) for case in raw_cases])
    _validate_coverage(report, manifest)

    if repo_root is not None and dataset_path is not None:
        try:
            normalize_json_file(
                dataset_path,
                repo_root=repo_root,
                layer="integration",
                datasets=("social_attention",),
                evidence_requirements=("static", "live_model"),
            )
        except ContractError as exc:
            raise DatasetValidationError(f"common scenario normalization failed: {exc}") from exc
    return report


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate the reviewed Chromie Social Attention benchmark dataset."
    )
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("benchmarks/datasets/social_attention/cases.json"),
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("benchmarks/manifests/social_attention_v1.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("benchmarks/reports/social_attention_coverage.json"),
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    root = args.repo_root.resolve()
    dataset_path = args.dataset if args.dataset.is_absolute() else root / args.dataset
    manifest_path = args.manifest if args.manifest.is_absolute() else root / args.manifest
    try:
        dataset = _load_json(dataset_path)
        manifest = _load_json(manifest_path)
        if not isinstance(dataset, Mapping) or not isinstance(manifest, Mapping):
            raise DatasetValidationError("dataset and manifest must be objects")
        report = validate_dataset(
            dataset,
            manifest,
            repo_root=root,
            dataset_path=dataset_path,
        )
        if not args.check:
            output = args.output if args.output.is_absolute() else root / args.output
            _write_json(output, report)
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except DatasetValidationError as exc:
        print(f"social attention dataset error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
