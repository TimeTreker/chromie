from __future__ import annotations

from collections import Counter
import copy
from typing import Any, Mapping

from benchmarks.contracts import ContractError

VALID_VERDICTS = frozenset({"pass", "partial", "fail", "insufficient_evidence"})


def _reviews_by_id(payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    if payload.get("schema_version") != 1:
        raise ContractError("semantic review payload must use schema_version 1")
    reviewer = payload.get("reviewer")
    if not isinstance(reviewer, Mapping) or not str(reviewer.get("kind") or "").strip():
        raise ContractError("semantic review payload requires reviewer.kind")
    rows = payload.get("reviews")
    if not isinstance(rows, list):
        raise ContractError("semantic review payload requires reviews array")
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise ContractError("semantic review entries must be objects")
        scenario_id = str(row.get("scenario_id") or "").strip()
        verdict = str(row.get("verdict") or "").strip()
        if not scenario_id:
            raise ContractError("semantic review entry requires scenario_id")
        if verdict not in VALID_VERDICTS:
            raise ContractError(
                f"semantic review {scenario_id!r} has unknown verdict {verdict!r}"
            )
        if scenario_id in result:
            raise ContractError(f"duplicate semantic review for {scenario_id!r}")
        result[scenario_id] = dict(row)
    return result


def apply_semantic_reviews(
    suite_report: Mapping[str, Any],
    review_payload: Mapping[str, Any],
) -> dict[str, Any]:
    if suite_report.get("schema_version") != 1 or not isinstance(
        suite_report.get("results"), list
    ):
        raise ContractError("suite report must use schema_version 1 and contain results")
    reviews = _reviews_by_id(review_payload)
    output = copy.deepcopy(dict(suite_report))
    seen: set[str] = set()
    for result in output["results"]:
        if not isinstance(result, dict):
            raise ContractError("suite report results must be objects")
        scenario_id = str(result.get("scenario_id") or "")
        review = reviews.get(scenario_id)
        if review is None:
            continue
        seen.add(scenario_id)
        evaluation = result.setdefault("evaluation", {})
        if not isinstance(evaluation, dict):
            raise ContractError(f"result {scenario_id!r} evaluation must be an object")
        if not evaluation.get("semantic_review_required"):
            raise ContractError(
                f"semantic review supplied for deterministic-only scenario {scenario_id!r}"
            )
        verdict = str(review["verdict"])
        evaluation["semantic_review"] = {
            **review,
            "reviewer": dict(review_payload.get("reviewer") or {}),
        }
        evaluation["semantic_review_status"] = verdict
        deterministic_failed = (
            evaluation.get("deterministic_status") == "fail"
            or result.get("status") == "fail"
        )
        if deterministic_failed:
            result["status"] = "fail"
            evaluation["semantic_review_effect"] = "diagnostic_only"
        elif verdict == "pass":
            result["status"] = "pass"
            evaluation["semantic_review_effect"] = "accepted"
        elif verdict == "fail":
            result["status"] = "fail"
            evaluation["semantic_review_effect"] = "accepted"
        else:
            result["status"] = "review"
            evaluation["semantic_review_effect"] = "requires_follow_up"
    unknown = sorted(set(reviews) - seen)
    if unknown:
        raise ContractError(
            "semantic review references unknown scenarios: " + ", ".join(unknown)
        )
    counts = Counter(
        str(result.get("status") or "error") for result in output["results"]
    )
    errors = output.get("errors") or []
    output["summary"] = {
        "total": len(output["results"]) + len(errors),
        "pass": counts["pass"],
        "fail": counts["fail"],
        "review": counts["review"],
        "error": len(errors),
    }
    output["semantic_review_provenance"] = {
        "reviewer": dict(review_payload.get("reviewer") or {}),
        "review_count": len(reviews),
    }
    return output
