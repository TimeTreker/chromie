from __future__ import annotations

import hashlib
import json
from pathlib import Path
import time
from typing import Any, Mapping

from benchmarks.contracts import ContractError
from benchmarks.review.adjudicate import (
    VALID_ATTRIBUTION_CONFIDENCE,
    VALID_FAILURE_ATTRIBUTION_CATEGORIES,
    VALID_MODEL_INFERENCE_FAULT_STATES,
    VALID_VERDICTS,
)
from benchmarks.review.consensus import aggregate_semantic_reviews
from benchmarks.review.prompting import render_review_prompt
from benchmarks.review.providers import (
    ReviewerConfiguration,
    ReviewerProfile,
    invoke_reviewer,
)


def _load_bundle(path: Path) -> tuple[Path, Path, dict[str, Any]]:
    bundle_path = path / "review-bundle.json" if path.is_dir() else path
    try:
        payload = json.loads(bundle_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(
            f"cannot load semantic review bundle {bundle_path}: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise ContractError(f"{bundle_path}: expected a JSON object")
    if payload.get("kind") != "chromie_semantic_review_bundle":
        raise ContractError(f"{bundle_path}: not a Chromie semantic review bundle")
    scenarios = payload.get("scenarios")
    if not isinstance(scenarios, list):
        raise ContractError(f"{bundle_path}: scenarios must be an array")
    return bundle_path.parent, bundle_path, payload


def _extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end <= start:
            raise ContractError("semantic reviewer output contains no JSON object")
        try:
            payload = json.loads(stripped[start : end + 1])
        except json.JSONDecodeError as exc:
            raise ContractError(
                f"semantic reviewer output is invalid JSON: {exc}"
            ) from exc
    if not isinstance(payload, dict):
        raise ContractError("semantic reviewer output must be one JSON object")
    if isinstance(payload.get("reviews"), list) and len(payload["reviews"]) == 1:
        item = payload["reviews"][0]
        if isinstance(item, dict):
            return item
    return payload


def _validate_review_entry(
    raw: Mapping[str, Any], *, scenario_id: str, dimensions: tuple[str, ...]
) -> dict[str, Any]:
    actual_id = str(raw.get("scenario_id") or "").strip()
    if actual_id != scenario_id:
        raise ContractError(
            f"semantic reviewer returned scenario_id {actual_id!r}; "
            f"expected {scenario_id!r}"
        )
    verdict = str(raw.get("verdict") or "").strip()
    if verdict not in VALID_VERDICTS:
        raise ContractError(
            f"semantic reviewer {scenario_id!r} has unknown verdict {verdict!r}"
        )
    rationale = str(raw.get("rationale") or "").strip()
    if not rationale:
        raise ContractError(f"semantic reviewer {scenario_id!r} requires rationale")
    evidence_refs = raw.get("evidence_refs")
    if not isinstance(evidence_refs, list) or any(
        not isinstance(item, str) or not item.strip() for item in evidence_refs
    ):
        raise ContractError(
            f"semantic reviewer {scenario_id!r} evidence_refs must be strings"
        )
    raw_dimensions = raw.get("dimensions") or {}
    if not isinstance(raw_dimensions, Mapping):
        raise ContractError(
            f"semantic reviewer {scenario_id!r} dimensions must be an object"
        )
    normalized_dimensions: dict[str, Any] = {}
    for dimension in dimensions:
        value = raw_dimensions.get(dimension)
        if not isinstance(value, Mapping):
            raise ContractError(
                f"semantic reviewer {scenario_id!r} omitted dimension {dimension!r}"
            )
        dimension_verdict = str(value.get("verdict") or "").strip()
        dimension_rationale = str(value.get("rationale") or "").strip()
        if dimension_verdict not in VALID_VERDICTS or not dimension_rationale:
            raise ContractError(
                f"semantic reviewer {scenario_id!r} has invalid dimension {dimension!r}"
            )
        normalized_dimensions[dimension] = {
            "verdict": dimension_verdict,
            "rationale": dimension_rationale,
        }
    findings = raw.get("findings") or []
    root_causes = raw.get("likely_root_causes") or []
    if not isinstance(findings, list) or not isinstance(root_causes, list):
        raise ContractError(
            f"semantic reviewer {scenario_id!r} findings/root causes must be arrays"
        )
    attribution = raw.get("failure_attribution")
    if not isinstance(attribution, Mapping):
        raise ContractError(
            f"semantic reviewer {scenario_id!r} requires failure_attribution"
        )
    primary_category = str(attribution.get("primary_category") or "").strip()
    model_fault = str(attribution.get("model_inference_fault") or "").strip()
    attribution_confidence = str(attribution.get("confidence") or "").strip()
    attribution_rationale = str(attribution.get("rationale") or "").strip()
    attribution_evidence = attribution.get("evidence_refs")
    if primary_category not in VALID_FAILURE_ATTRIBUTION_CATEGORIES:
        raise ContractError(
            f"semantic reviewer {scenario_id!r} has invalid attribution category"
        )
    if model_fault not in VALID_MODEL_INFERENCE_FAULT_STATES:
        raise ContractError(
            f"semantic reviewer {scenario_id!r} has invalid model-inference attribution"
        )
    if attribution_confidence not in VALID_ATTRIBUTION_CONFIDENCE:
        raise ContractError(
            f"semantic reviewer {scenario_id!r} has invalid attribution confidence"
        )
    if not attribution_rationale:
        raise ContractError(
            f"semantic reviewer {scenario_id!r} requires attribution rationale"
        )
    if not isinstance(attribution_evidence, list) or any(
        not isinstance(item, str) or not item.strip() for item in attribution_evidence
    ):
        raise ContractError(
            f"semantic reviewer {scenario_id!r} attribution evidence_refs must be strings"
        )
    return {
        "scenario_id": scenario_id,
        "verdict": verdict,
        "rationale": rationale,
        "evidence_refs": [str(item) for item in evidence_refs],
        "dimensions": normalized_dimensions,
        "findings": [dict(item) for item in findings if isinstance(item, Mapping)],
        "failure_attribution": {
            "primary_category": primary_category,
            "model_inference_fault": model_fault,
            "confidence": attribution_confidence,
            "rationale": attribution_rationale,
            "evidence_refs": [str(item) for item in attribution_evidence],
        },
        "likely_root_causes": [
            str(item).strip() for item in root_causes if str(item).strip()
        ],
    }


def _run_profile(
    profile: ReviewerProfile,
    *,
    bundle_dir: Path,
    bundle: Mapping[str, Any],
    output_dir: Path,
    max_input_chars: int,
    max_artifact_chars: int,
    environment: Mapping[str, str] | None,
    bundle_sha256: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    reviewer_dir = output_dir / profile.reviewer_id
    raw_dir = reviewer_dir / "raw"
    prompt_dir = reviewer_dir / "prompts"
    raw_dir.mkdir(parents=True, exist_ok=True)
    prompt_dir.mkdir(parents=True, exist_ok=True)
    reviews: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    call_records: list[dict[str, Any]] = []
    scenarios = bundle.get("scenarios") or []
    for case in scenarios:
        if not isinstance(case, Mapping):
            errors.append(
                {
                    "scenario_id": None,
                    "error": "semantic review bundle scenario must be an object",
                }
            )
            continue
        scenario_id = str(case.get("scenario_id") or "").strip()
        safe_id = "".join(
            char if char.isalnum() or char in "-_." else "_"
            for char in scenario_id
        ) or "unknown-scenario"
        try:
            review_request = case.get("review_request") or {}
            dimensions = tuple(
                str(item)
                for item in (
                    review_request.get("semantic_dimensions")
                    if isinstance(review_request, Mapping)
                    else []
                )
                if str(item).strip()
            )
            system_prompt, user_prompt, prompt_meta = render_review_prompt(
                bundle,
                case,
                bundle_dir=bundle_dir,
                max_input_chars=max_input_chars,
                max_artifact_chars=max_artifact_chars,
            )
            (prompt_dir / f"{safe_id}.json").write_text(
                json.dumps(
                    {
                        **prompt_meta,
                        "system_prompt": system_prompt,
                        "user_prompt": user_prompt,
                    },
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            response = invoke_reviewer(
                profile,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                environment=environment,
            )
            raw_path = raw_dir / f"{safe_id}.txt"
            raw_path.write_text(response.text + "\n", encoding="utf-8")
            review = _validate_review_entry(
                _extract_json_object(response.text),
                scenario_id=scenario_id,
                dimensions=dimensions,
            )
            response_sha = hashlib.sha256(
                response.text.encode("utf-8")
            ).hexdigest()
            review["provenance"] = {
                **prompt_meta,
                "bundle_sha256": bundle_sha256,
                "response_sha256": response_sha,
                "request_id": response.request_id,
                "returned_model": response.returned_model,
                "latency_ms": response.latency_ms,
            }
            reviews.append(review)
            call_records.append(review["provenance"])
        except ContractError as exc:
            errors.append(
                {
                    "scenario_id": scenario_id or None,
                    "error": str(exc),
                }
            )
    payload = {
        "schema_version": 1,
        "reviewer": {
            "kind": "llm",
            "reviewer_id": profile.reviewer_id,
            "provider_protocol": profile.protocol,
            "model": profile.model,
            "model_family": profile.model_family,
            "base_url": profile.base_url,
            "bundle_sha256": bundle_sha256,
            "prompt_protocol_version": (
                call_records[0]["prompt_protocol_version"] if call_records else None
            ),
            "scenario_errors": errors,
        },
        "reviews": reviews,
    }
    (reviewer_dir / "reviews.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload, errors


def judge_review_bundle(
    *,
    bundle_path: Path,
    reviewer_config_path: Path,
    output_dir: Path,
    reviewer_ids: set[str] | None = None,
    max_input_chars: int = 120_000,
    max_artifact_chars: int = 20_000,
    dry_run: bool = False,
    environment: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    bundle_dir, resolved_bundle_path, bundle = _load_bundle(bundle_path)
    config = ReviewerConfiguration.from_path(reviewer_config_path)
    bundle_sha256 = hashlib.sha256(resolved_bundle_path.read_bytes()).hexdigest()
    config_sha256 = hashlib.sha256(reviewer_config_path.read_bytes()).hexdigest()
    profiles = config.selected(reviewer_ids)
    output_dir.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "schema_version": 1,
        "bundle": str(resolved_bundle_path),
        "bundle_sha256": bundle_sha256,
        "reviewer_config": str(reviewer_config_path),
        "reviewer_config_sha256": config_sha256,
        "selected_reviewers": [profile.public_metadata() for profile in profiles],
        "scenario_count": len(bundle.get("scenarios") or []),
        "dry_run": dry_run,
        "reviewers": [],
        "consensus": None,
    }
    if dry_run:
        for case in bundle.get("scenarios") or []:
            if not isinstance(case, Mapping):
                continue
            _, _, metadata = render_review_prompt(
                bundle,
                case,
                bundle_dir=bundle_dir,
                max_input_chars=max_input_chars,
                max_artifact_chars=max_artifact_chars,
            )
            report.setdefault("prompts", []).append(metadata)
        (output_dir / "judge-report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return report
    payloads: list[dict[str, Any]] = []
    for profile in profiles:
        started = time.monotonic()
        try:
            payload, scenario_errors = _run_profile(
                profile,
                bundle_dir=bundle_dir,
                bundle=bundle,
                output_dir=output_dir,
                max_input_chars=max_input_chars,
                max_artifact_chars=max_artifact_chars,
                environment=environment,
                bundle_sha256=bundle_sha256,
            )
        except ContractError as exc:
            report["reviewers"].append(
                {
                    "reviewer_id": profile.reviewer_id,
                    "status": "failed",
                    "error": str(exc),
                    "elapsed_ms": int((time.monotonic() - started) * 1000),
                }
            )
            continue
        if payload["reviews"]:
            payloads.append(payload)
        report["reviewers"].append(
            {
                "reviewer_id": profile.reviewer_id,
                "status": "partial" if scenario_errors else "passed",
                "review_count": len(payload["reviews"]),
                "error_count": len(scenario_errors),
                "scenario_errors": scenario_errors,
                "elapsed_ms": int((time.monotonic() - started) * 1000),
                "reviews_path": str(
                    output_dir / profile.reviewer_id / "reviews.json"
                ),
            }
        )
    if payloads:
        consensus = aggregate_semantic_reviews(
            payloads,
            policy=config.consensus_policy,
            minimum_reviewers=config.minimum_reviewers,
            minimum_model_families=config.minimum_model_families,
        )
        consensus_path = output_dir / "ensemble-reviews.json"
        consensus_path.write_text(
            json.dumps(consensus, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        report["consensus"] = {
            "path": str(consensus_path),
            "policy": config.consensus_policy,
            "minimum_reviewers": config.minimum_reviewers,
            "minimum_model_families": config.minimum_model_families,
            "successful_reviewers": len(payloads),
            "successful_model_families": len(
                {
                    str(payload.get("reviewer", {}).get("model_family") or "")
                    for payload in payloads
                }
            ),
        }
    reviewer_statuses = {
        str(item.get("reviewer_id")): str(item.get("status"))
        for item in report["reviewers"]
        if isinstance(item, Mapping)
    }
    report["complete"] = (
        len(payloads) >= config.minimum_reviewers
        and len(
            {
                str(payload.get("reviewer", {}).get("model_family") or "")
                for payload in payloads
            }
        )
        >= config.minimum_model_families
        and all(
            reviewer_statuses.get(profile.reviewer_id) == "passed"
            for profile in profiles
        )
    )
    (output_dir / "judge-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report
