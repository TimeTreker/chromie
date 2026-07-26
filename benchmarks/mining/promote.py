from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path
from typing import Any, Mapping

from scripts.behavior_scenarios import DEFAULT_SCENARIO_ROOT, load_scenario_file, load_scenarios

from .dedupe import canonical_text, similarity
from .models import MiningError, load_json, validate_candidate, validate_review_record

_ID_RE = re.compile(r"[a-z][a-z0-9_]{2,79}")


def _candidate_primary_texts(candidate: Mapping[str, Any]) -> list[str]:
    values: list[str] = []
    input_value = candidate.get("input")
    if isinstance(input_value, Mapping) and isinstance(input_value.get("text"), str):
        values.append(str(input_value["text"]))
    turns = candidate.get("turns")
    if isinstance(turns, list):
        for turn in turns:
            if isinstance(turn, Mapping):
                value = turn.get("ask", turn.get("text"))
                if isinstance(value, str) and value.strip():
                    values.append(value.strip())
    return values


def _existing_texts(root: Path) -> list[tuple[str, str]]:
    values: list[tuple[str, str]] = []
    for scenario in load_scenarios(root):
        if scenario.turns:
            for turn in scenario.turns:
                value = turn.get("ask", turn.get("text"))
                if isinstance(value, str) and value.strip():
                    values.append((scenario.key, value.strip()))
        elif scenario.text:
            values.append((scenario.key, scenario.text))
    return values


def build_promoted_payload(
    candidate: Mapping[str, Any],
    review: Mapping[str, Any],
    *,
    target_id: str,
    suite: str,
) -> dict[str, Any]:
    if not _ID_RE.fullmatch(target_id):
        raise MiningError(f"invalid promoted scenario id: {target_id!r}")
    if review.get("decision") != "approved" or review.get("regression_promotion_allowed") is not True:
        raise MiningError("candidate review does not approve regression promotion")
    if suite != candidate.get("suite"):
        raise MiningError("promotion cannot silently change the candidate suite")
    payload = json.loads(json.dumps(candidate, ensure_ascii=False))
    payload["id"] = target_id
    payload["suite"] = suite
    payload.pop("review", None)
    payload.pop("promotion", None)
    payload.pop("candidate_contract", None)
    tags = [
        str(item)
        for item in payload.get("tags", [])
        if str(item) not in {"candidate", "pending-review"}
    ]
    for tag in ("reviewed-regression", "experience-mined"):
        if tag not in tags:
            tags.append(tag)
    payload["tags"] = tags
    payload["provenance"] = {
        "source_candidate_id": candidate["id"],
        "source_episode_id": candidate.get("review", {}).get("source_episode_id"),
        "source_evaluation_id": candidate.get("review", {}).get("source_evaluation_id"),
        "review_id": review.get("review_id"),
        "reviewer": review.get("reviewer"),
        "reviewed_at": review.get("reviewed_at"),
        "review_rationale": review.get("rationale"),
        "promotion_auto_applied": False,
    }
    return payload


def promote_candidate(
    candidate_path: Path,
    review_path: Path,
    manifest: Mapping[str, Any],
    *,
    scenario_root: Path = DEFAULT_SCENARIO_ROOT,
    target_id: str | None = None,
    suite: str | None = None,
    allow_related: bool = False,
    dry_run: bool = False,
) -> tuple[Path, dict[str, Any]]:
    candidate = load_json(candidate_path)
    validate_candidate(candidate, manifest)
    review = load_json(review_path)
    validate_review_record(review, candidate)
    target_id = target_id or str(candidate["id"]).removeprefix("candidate_")
    suite = suite or str(candidate["suite"])
    allowed = set(manifest.get("promotion", {}).get("allowed_suites", []))
    if suite not in allowed:
        raise MiningError(f"suite {suite!r} is not promotable")
    target = scenario_root / suite / f"{target_id}.json"
    if target.exists():
        raise MiningError(f"target scenario already exists: {target}")
    candidate_texts = _candidate_primary_texts(candidate)
    related: list[tuple[str, float]] = []
    for key, existing in _existing_texts(scenario_root):
        best = max((similarity(left, existing) for left in candidate_texts), default=0.0)
        if best >= 0.999999:
            raise MiningError(f"candidate duplicates committed scenario {key}")
        if best >= float(manifest.get("deduplication", {}).get("related_similarity_threshold", 0.9)):
            related.append((key, best))
    if related and not allow_related:
        detail = ", ".join(f"{key}:{score:.3f}" for key, score in sorted(related, key=lambda item: -item[1])[:5])
        raise MiningError(f"candidate is related to committed scenarios; review with --allow-related: {detail}")
    payload = build_promoted_payload(candidate, review, target_id=target_id, suite=suite)
    with tempfile.TemporaryDirectory() as tmp:
        temp = Path(tmp) / f"{target_id}.json"
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        load_scenario_file(temp)
    if not dry_run:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        load_scenario_file(target)
    return target, payload
