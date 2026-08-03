from __future__ import annotations

import json
from pathlib import Path
import shutil
import tarfile
from typing import Any, Iterable, Mapping

from benchmarks.contracts import ContractError
from benchmarks.runners.oracles import oracle_policy_for_scenario


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot load JSON {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ContractError(f"{path}: expected a JSON object")
    return payload


def _safe_name(value: str) -> str:
    return "".join(char if char.isalnum() or char in "-_." else "_" for char in value)


def _copy_artifact(
    source: Path,
    *,
    destination_root: Path,
    label: str,
) -> dict[str, Any]:
    record: dict[str, Any] = {"source": str(source), "label": label}
    if not source.exists():
        record.update({"status": "missing", "included_path": None})
        return record
    destination = destination_root / _safe_name(label)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(source, destination)
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    record.update(
        {
            "status": "included",
            "included_path": destination.relative_to(destination_root.parent).as_posix(),
            "kind": "directory" if source.is_dir() else "file",
        }
    )
    return record


def build_review_bundle(
    normalized_payload: Mapping[str, Any],
    suite_report: Mapping[str, Any],
    *,
    artifact_root: Path | None = None,
) -> dict[str, Any]:
    cases = normalized_payload.get("cases")
    if normalized_payload.get("schema_version") != 1 or not isinstance(cases, list):
        raise ContractError(
            "normalized scenario payload must use schema_version 1 and contain cases"
        )
    results = suite_report.get("results")
    if suite_report.get("schema_version") != 1 or not isinstance(results, list):
        raise ContractError("suite report must use schema_version 1 and contain results")
    cases_by_id = {
        str(case.get("id")): case
        for case in cases
        if isinstance(case, Mapping) and isinstance(case.get("id"), str)
    }
    review_cases: list[dict[str, Any]] = []
    for result in results:
        if not isinstance(result, Mapping):
            raise ContractError("suite report results must be objects")
        scenario_id = str(result.get("scenario_id") or "")
        scenario = cases_by_id.get(scenario_id)
        if scenario is None:
            raise ContractError(f"suite result references unknown scenario {scenario_id!r}")
        evaluation = result.get("evaluation")
        if not isinstance(evaluation, Mapping):
            evaluation = {}
        policy = oracle_policy_for_scenario(scenario)
        if not bool(evaluation.get("semantic_review_required")) and policy.mode == "deterministic":
            continue
        if result.get("status") == "fail":
            # Keep deterministic failures available for root-cause review without
            # allowing a semantic reviewer to override them.
            review_reason = "deterministic_failure_diagnostic"
        else:
            review_reason = "semantic_adjudication"
        expectations = scenario.get("expectations")
        if not isinstance(expectations, Mapping):
            expectations = {}
        review_cases.append(
            {
                "scenario_id": scenario_id,
                "review_reason": review_reason,
                "oracle_policy": policy.to_dict(),
                "scenario": scenario,
                "execution_result": result,
                "review_request": {
                    "semantic_dimensions": list(policy.semantic_dimensions),
                    "primary_outcomes": list(expectations.get("primary_outcomes") or []),
                    "acceptable_auxiliary": list(
                        expectations.get("acceptable_auxiliary") or []
                    ),
                    "forbidden_behaviors": list(
                        expectations.get("forbidden_behaviors") or []
                    ),
                    "review_rubric": dict(scenario.get("review_rubric") or {}),
                    "deterministic_boundaries_are_non_overridable": True,
                    "judge_meaning_not_exact_wording": True,
                },
                "artifact_references": list(result.get("artifacts") or []),
            }
        )
    return {
        "schema_version": 1,
        "kind": "chromie_semantic_review_bundle",
        "run": dict(suite_report.get("run") or {}),
        "suite_summary": dict(suite_report.get("summary") or {}),
        "review_instructions": [
            "Use deterministic results as non-overridable boundary evidence.",
            "Judge only declared semantic dimensions and acceptable behavior regions.",
            "Do not require one exact wording when multiple responses are reasonable.",
            "Cite retained evidence or mark insufficient_evidence.",
            "Return pass, partial, fail, or insufficient_evidence for every scenario.",
        ],
        "artifact_root": str(artifact_root) if artifact_root else None,
        "scenarios": review_cases,
    }


def write_review_bundle(
    *,
    normalized_path: Path,
    report_path: Path,
    output_dir: Path,
    artifact_root: Path | None = None,
    includes: Iterable[Path] = (),
    archive_path: Path | None = None,
) -> dict[str, Any]:
    normalized = _load_json(normalized_path)
    report = _load_json(report_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    bundle = build_review_bundle(normalized, report, artifact_root=artifact_root)

    artifact_records: list[dict[str, Any]] = []
    if artifact_root is not None:
        artifact_root = artifact_root.resolve()
        artifacts_dir = output_dir / "artifacts"
        for case in bundle["scenarios"]:
            scenario_id = str(case["scenario_id"])
            copied: list[dict[str, Any]] = []
            for index, raw in enumerate(case["artifact_references"]):
                source = Path(str(raw))
                if not source.is_absolute():
                    source = artifact_root / source
                source = source.resolve()
                try:
                    source.relative_to(artifact_root)
                except ValueError as exc:
                    raise ContractError(
                        f"artifact path escapes artifact root: {source}"
                    ) from exc
                copied.append(
                    _copy_artifact(
                        source,
                        destination_root=artifacts_dir / _safe_name(scenario_id),
                        label=f"{index:03d}-{source.name or 'artifact'}",
                    )
                )
            case["artifact_inventory"] = copied
            artifact_records.extend(copied)

    attachment_dir = output_dir / "attachments"
    attachment_records: list[dict[str, Any]] = []
    for index, include in enumerate(includes):
        source = include.resolve()
        attachment_records.append(
            _copy_artifact(
                source,
                destination_root=attachment_dir,
                label=f"{index:03d}-{source.name or 'attachment'}",
            )
        )

    bundle["artifact_inventory"] = artifact_records
    bundle["attachment_inventory"] = attachment_records
    bundle_path = output_dir / "review-bundle.json"
    bundle_path.write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    review_template = {
        "schema_version": 1,
        "reviewer": {
            "kind": "llm",
            "model": None,
            "model_family": None,
            "reviewer_id": None,
        },
        "reviews": [
            {
                "scenario_id": case["scenario_id"],
                "verdict": "insufficient_evidence",
                "rationale": "Replace with an evidence-grounded semantic judgment.",
                "evidence_refs": [],
                "dimensions": {
                    dimension: {
                        "verdict": "insufficient_evidence",
                        "rationale": "Review retained evidence for this dimension.",
                    }
                    for dimension in case["review_request"]["semantic_dimensions"]
                },
                "findings": [],
                "likely_root_causes": [],
            }
            for case in bundle["scenarios"]
        ],
    }
    (output_dir / "review-template.json").write_text(
        json.dumps(review_template, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    (output_dir / "REVIEW_INSTRUCTIONS.txt").write_text(
        "Review review-bundle.json using only retained evidence.\n"
        "Fill review-template.json with pass, partial, fail, or "
        "insufficient_evidence.\n"
        "Do not override deterministic failures or require exact conversational "
        "wording.\n"
        "For independent API judges, run: python -m benchmarks.review judge "
        "--bundle . --reviewers <config.json> --output-dir judgments\n"
        "For separately produced reviews, run: python -m benchmarks.review "
        "aggregate --reviews <one.json> --reviews <two.json> "
        "--minimum-model-families 2 --output "
        "ensemble-reviews.json\n",
        encoding="utf-8",
    )
    if archive_path is not None:
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive_path, "w:gz") as archive:
            archive.add(output_dir, arcname=output_dir.name)
    return bundle
