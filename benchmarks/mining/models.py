from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


class MiningError(ValueError):
    """Raised when candidate mining or review metadata violates its contract."""


_ID_RE = re.compile(r"[a-z][a-z0-9_]{2,79}")


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MiningError(f"cannot load JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise MiningError(f"{path} must contain one JSON object")
    return value


def validate_mining_manifest(payload: Mapping[str, Any]) -> None:
    if payload.get("schema_version") != 1:
        raise MiningError("mining manifest schema_version must be 1")
    if payload.get("manifest_id") != "chromie.scenario_mining.v1":
        raise MiningError("unexpected mining manifest id")
    forbidden_true = (
        "runtime_policy_authority",
        "auto_promotion_allowed",
        "authoritative_prompt_mutation_allowed",
    )
    for key in forbidden_true:
        if payload.get(key) is not False:
            raise MiningError(f"mining manifest must keep {key}=false")
    promotion = payload.get("promotion")
    if not isinstance(promotion, Mapping):
        raise MiningError("mining manifest promotion must be an object")
    for key in ("auto_commit", "auto_prompt_edit", "auto_runtime_policy_edit"):
        if promotion.get(key) is not False:
            raise MiningError(f"promotion must keep {key}=false")
    axes = payload.get("variation_axes")
    if not isinstance(axes, Mapping) or not axes:
        raise MiningError("mining manifest must declare controlled variation axes")


def candidate_fingerprint(candidate: Mapping[str, Any]) -> str:
    canonical = json.dumps(candidate, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_candidate(candidate: Mapping[str, Any], manifest: Mapping[str, Any]) -> None:
    if candidate.get("schema_version") != 1:
        raise MiningError("candidate schema_version must be 1")
    candidate_id = candidate.get("id")
    if not isinstance(candidate_id, str) or not _ID_RE.fullmatch(candidate_id):
        raise MiningError(f"invalid candidate id: {candidate_id!r}")
    allowed_suites = set(manifest.get("promotion", {}).get("allowed_suites", []))
    suite = candidate.get("suite")
    if suite not in allowed_suites:
        raise MiningError(f"unsupported candidate suite: {suite!r}")
    review = candidate.get("review")
    promotion = candidate.get("promotion")
    if not isinstance(review, Mapping) or not isinstance(promotion, Mapping):
        raise MiningError("candidate must contain review and promotion objects")
    if review.get("requires_human_review") is not True:
        raise MiningError("candidate must require human review")
    if review.get("status") != "pending_human_review":
        raise MiningError("immutable mined candidate must remain pending_human_review")
    if promotion.get("auto_promotion_allowed") is not False:
        raise MiningError("candidate cannot allow automatic promotion")
    if promotion.get("regression_allowed") is not False:
        raise MiningError("unreviewed candidate cannot allow regression promotion")
    if promotion.get("training_allowed") is not False:
        raise MiningError("unreviewed candidate cannot allow training promotion")
    if not review.get("source_episode_id") or not review.get("source_evaluation_id"):
        raise MiningError("candidate must preserve episode and evaluation provenance")
    if not candidate_texts(candidate):
        raise MiningError("candidate must contain at least one user input")


def candidate_texts(candidate: Mapping[str, Any]) -> tuple[str, ...]:
    texts: list[str] = []
    input_value = candidate.get("input")
    if isinstance(input_value, Mapping) and isinstance(input_value.get("text"), str):
        text = str(input_value["text"]).strip()
        if text:
            texts.append(text)
    turns = candidate.get("turns")
    if isinstance(turns, list):
        for turn in turns:
            if not isinstance(turn, Mapping):
                continue
            value = turn.get("ask", turn.get("text"))
            if isinstance(value, str) and value.strip():
                texts.append(value.strip())
    return tuple(texts)


def create_review_record(
    candidate: Mapping[str, Any],
    *,
    decision: str,
    reviewer: str,
    rationale: str,
    reviewed_at: str | None = None,
) -> dict[str, Any]:
    reviewer = reviewer.strip()
    rationale = rationale.strip()
    if decision not in {"approved", "rejected"}:
        raise MiningError("review decision must be approved or rejected")
    if not reviewer or not rationale:
        raise MiningError("reviewer and rationale must not be empty")
    reviewed_at = reviewed_at or datetime.now(timezone.utc).isoformat()
    review_id = "review_" + hashlib.sha256(
        f"{candidate.get('id')}|{candidate_fingerprint(candidate)}|{decision}|{reviewer}".encode("utf-8")
    ).hexdigest()[:16]
    return {
        "schema_version": 1,
        "review_id": review_id,
        "candidate_id": candidate["id"],
        "candidate_fingerprint": candidate_fingerprint(candidate),
        "decision": decision,
        "reviewer": reviewer,
        "reviewed_at": reviewed_at,
        "rationale": rationale,
        "regression_promotion_allowed": decision == "approved",
        "training_promotion_allowed": False,
        "auto_apply": False,
        "runtime_policy_authority": False,
    }


def validate_review_record(review: Mapping[str, Any], candidate: Mapping[str, Any]) -> None:
    if review.get("schema_version") != 1:
        raise MiningError("review record schema_version must be 1")
    if review.get("candidate_id") != candidate.get("id"):
        raise MiningError("review record candidate_id does not match candidate")
    if review.get("candidate_fingerprint") != candidate_fingerprint(candidate):
        raise MiningError("review record does not match immutable candidate fingerprint")
    if review.get("decision") not in {"approved", "rejected"}:
        raise MiningError("invalid review decision")
    for key in ("reviewer", "reviewed_at", "rationale"):
        if not isinstance(review.get(key), str) or not str(review[key]).strip():
            raise MiningError(f"review record missing {key}")
    if review.get("auto_apply") is not False or review.get("runtime_policy_authority") is not False:
        raise MiningError("review record cannot auto-apply or own Runtime policy")
    allowed = review.get("decision") == "approved"
    if review.get("regression_promotion_allowed") is not allowed:
        raise MiningError("review promotion permission does not match decision")
