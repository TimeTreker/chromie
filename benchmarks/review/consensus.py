from __future__ import annotations

from collections import Counter
import hashlib
import json
from typing import Any, Iterable, Mapping

from benchmarks.contracts import ContractError
from benchmarks.review.adjudicate import VALID_VERDICTS, _reviews_by_id

VALID_CONSENSUS_POLICIES = frozenset({"majority", "unanimous", "conservative"})


def _reviewer_identity(payload: Mapping[str, Any]) -> str:
    reviewer = payload.get("reviewer")
    if not isinstance(reviewer, Mapping):
        raise ContractError("semantic review payload requires reviewer")
    identity = str(
        reviewer.get("reviewer_id")
        or reviewer.get("model")
        or reviewer.get("kind")
        or ""
    ).strip()
    if not identity:
        raise ContractError("semantic review reviewer identity must not be empty")
    return identity


def _consensus_verdict(
    votes: list[str],
    *,
    policy: str,
    minimum: int,
    family_count: int,
    minimum_families: int,
) -> str:
    if len(votes) < minimum or family_count < minimum_families:
        return "insufficient_evidence"
    if policy == "unanimous":
        return votes[0] if len(set(votes)) == 1 else "insufficient_evidence"
    if policy == "conservative":
        for verdict in ("fail", "partial", "insufficient_evidence", "pass"):
            if verdict in votes:
                return verdict
        raise ContractError("empty semantic verdict set")
    counts = Counter(votes)
    verdict, count = counts.most_common(1)[0]
    if count > len(votes) / 2:
        return verdict
    return "insufficient_evidence"


def aggregate_semantic_reviews(
    review_payloads: Iterable[Mapping[str, Any]],
    *,
    policy: str = "majority",
    minimum_reviewers: int = 2,
    minimum_model_families: int = 1,
) -> dict[str, Any]:
    if policy not in VALID_CONSENSUS_POLICIES:
        raise ContractError(f"unknown semantic consensus policy: {policy}")
    if minimum_reviewers <= 0:
        raise ContractError("minimum_reviewers must be positive")
    if minimum_model_families <= 0:
        raise ContractError("minimum_model_families must be positive")
    if minimum_model_families > minimum_reviewers:
        raise ContractError(
            "minimum_model_families cannot exceed minimum_reviewers"
        )
    payloads = [dict(payload) for payload in review_payloads]
    if not payloads:
        raise ContractError("at least one semantic review payload is required")
    identities = [_reviewer_identity(payload) for payload in payloads]
    families: list[str] = []
    for identity, payload in zip(identities, payloads, strict=True):
        reviewer = payload.get("reviewer")
        family = (
            str(reviewer.get("model_family") or "").strip()
            if isinstance(reviewer, Mapping)
            else ""
        )
        if not family and minimum_model_families > 1:
            raise ContractError(
                f"semantic reviewer {identity!r} requires model_family when "
                "minimum_model_families is greater than one"
            )
        families.append(family or identity)
    duplicates = sorted({item for item in identities if identities.count(item) > 1})
    if duplicates:
        raise ContractError(
            "duplicate semantic reviewer identities: " + ", ".join(duplicates)
        )
    review_maps = [_reviews_by_id(payload) for payload in payloads]
    scenario_ids = sorted(set().union(*(set(rows) for rows in review_maps)))
    reviews: list[dict[str, Any]] = []
    for scenario_id in scenario_ids:
        vote_rows: list[dict[str, Any]] = []
        for index, (identity, rows) in enumerate(
            zip(identities, review_maps, strict=True)
        ):
            row = rows.get(scenario_id)
            if row is None:
                continue
            vote_rows.append(
                {
                    "reviewer_id": identity,
                    "model_family": families[index],
                    "verdict": str(row["verdict"]),
                    "rationale": str(row.get("rationale") or ""),
                    "evidence_refs": list(row.get("evidence_refs") or []),
                }
            )
        verdicts = [str(row["verdict"]) for row in vote_rows]
        vote_families = {
            families[index]
            for index, rows in enumerate(review_maps)
            if scenario_id in rows
        }
        verdict = _consensus_verdict(
            verdicts,
            policy=policy,
            minimum=minimum_reviewers,
            family_count=len(vote_families),
            minimum_families=minimum_model_families,
        )
        counts = Counter(verdicts)
        evidence_refs = sorted(
            {
                str(ref)
                for rows in review_maps
                for ref in (rows.get(scenario_id, {}).get("evidence_refs") or [])
                if str(ref).strip()
            }
        )
        dimensions: dict[str, Any] = {}
        dimension_names = sorted(
            {
                str(name)
                for rows in review_maps
                for name in (
                    rows.get(scenario_id, {}).get("dimensions") or {}
                )
                if str(name).strip()
            }
        )
        for dimension in dimension_names:
            dimension_votes: list[str] = []
            for rows in review_maps:
                raw_dimensions = rows.get(scenario_id, {}).get("dimensions") or {}
                if not isinstance(raw_dimensions, Mapping):
                    continue
                value = raw_dimensions.get(dimension)
                if not isinstance(value, Mapping):
                    continue
                candidate = str(value.get("verdict") or "")
                if candidate in VALID_VERDICTS:
                    dimension_votes.append(candidate)
            dimension_families: set[str] = set()
            for index, rows in enumerate(review_maps):
                raw_dimensions = rows.get(scenario_id, {}).get("dimensions") or {}
                if not isinstance(raw_dimensions, Mapping):
                    continue
                value = raw_dimensions.get(dimension)
                if isinstance(value, Mapping) and str(
                    value.get("verdict") or ""
                ) in VALID_VERDICTS:
                    dimension_families.add(families[index])
            dimension_verdict = _consensus_verdict(
                dimension_votes,
                policy=policy,
                minimum=minimum_reviewers,
                family_count=len(dimension_families),
                minimum_families=minimum_model_families,
            )
            dimensions[dimension] = {
                "verdict": dimension_verdict,
                "rationale": (
                    f"{policy} consensus from {len(dimension_votes)} reviewers: "
                    + ", ".join(
                        f"{name}={count}"
                        for name, count in sorted(Counter(dimension_votes).items())
                    )
                ),
                "votes": dimension_votes,
            }
        findings: list[dict[str, Any]] = []
        root_causes: list[str] = []
        for index, (identity, rows) in enumerate(
            zip(identities, review_maps, strict=True)
        ):
            row = rows.get(scenario_id)
            if row is None:
                continue
            for finding in row.get("findings") or []:
                if isinstance(finding, Mapping):
                    findings.append({"reviewer_id": identity, **dict(finding)})
            for cause in row.get("likely_root_causes") or []:
                text = str(cause).strip()
                if text and text not in root_causes:
                    root_causes.append(text)
        agreement_count = max(counts.values(), default=0)
        reviews.append(
            {
                "scenario_id": scenario_id,
                "verdict": verdict,
                "rationale": (
                    f"{policy} semantic consensus: "
                    + ", ".join(
                        f"{name}={count}" for name, count in sorted(counts.items())
                    )
                    + f"; minimum_reviewers={minimum_reviewers}; "
                    + f"minimum_model_families={minimum_model_families}."
                ),
                "evidence_refs": evidence_refs,
                "dimensions": dimensions,
                "findings": findings,
                "likely_root_causes": root_causes,
                "judge_votes": vote_rows,
                "agreement": {
                    "policy": policy,
                    "reviewer_count": len(vote_rows),
                    "minimum_reviewers": minimum_reviewers,
                    "minimum_model_families": minimum_model_families,
                    "model_family_count": len(vote_families),
                    "model_families": sorted(vote_families),
                    "agreement_count": agreement_count,
                    "agreement_ratio": (
                        agreement_count / len(vote_rows) if vote_rows else 0.0
                    ),
                    "counts": dict(sorted(counts.items())),
                },
            }
        )
    member_metadata = [dict(payload.get("reviewer") or {}) for payload in payloads]
    ensemble_material = json.dumps(
        member_metadata, ensure_ascii=False, sort_keys=True
    ).encode("utf-8")
    return {
        "schema_version": 1,
        "reviewer": {
            "kind": "llm_ensemble",
            "reviewer_id": (
                "ensemble-" + hashlib.sha256(ensemble_material).hexdigest()[:12]
            ),
            "policy": policy,
            "minimum_reviewers": minimum_reviewers,
            "minimum_model_families": minimum_model_families,
            "members": member_metadata,
        },
        "reviews": reviews,
    }
