from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

from .dedupe import failure_tag_counts, related_scenarios, similarity
from .models import (
    MiningError,
    candidate_fingerprint,
    candidate_texts,
    load_json,
    validate_candidate,
)


def load_normalized(path: Path) -> list[dict[str, Any]]:
    payload = load_json(path)
    cases = payload.get("cases")
    if payload.get("schema_version") != 1 or not isinstance(cases, list):
        raise MiningError("normalized scenario file must contain schema_version 1 and cases")
    if not all(isinstance(item, dict) for item in cases):
        raise MiningError("normalized scenario cases must be objects")
    return cases


def discover_candidates(roots: Iterable[Path], manifest: Mapping[str, Any]) -> list[tuple[Path, dict[str, Any]]]:
    candidates: list[tuple[Path, dict[str, Any]]] = []
    seen_fingerprints: set[str] = set()
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.json")):
            try:
                candidate = load_json(path)
            except MiningError:
                continue
            candidate_like = all(key in candidate for key in ("id", "review", "promotion"))
            if not candidate_like:
                continue
            validate_candidate(candidate, manifest)
            fingerprint = candidate_fingerprint(candidate)
            if fingerprint in seen_fingerprints:
                continue
            seen_fingerprints.add(fingerprint)
            candidates.append((path, candidate))
    return candidates


def build_candidate_catalog(
    candidates: list[tuple[Path, dict[str, Any]]],
    normalized_scenarios: list[dict[str, Any]],
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    dedupe = manifest.get("deduplication", {})
    related_threshold = float(dedupe.get("related_similarity_threshold", 0.9))
    near_threshold = float(dedupe.get("near_duplicate_similarity_threshold", 0.96))
    entries: list[dict[str, Any]] = []
    clusters: dict[str, list[str]] = defaultdict(list)
    exact_pairs: list[dict[str, Any]] = []
    similarity_edges: list[tuple[str, str, float]] = []
    for left_index, (_, left) in enumerate(candidates):
        for _, right in candidates[left_index + 1 :]:
            score = max(
                (similarity(left_text, right_text)
                 for left_text in candidate_texts(left)
                 for right_text in candidate_texts(right)),
                default=0.0,
            )
            if score >= related_threshold:
                similarity_edges.append((str(left["id"]), str(right["id"]), score))
    parent: dict[str, str] = {str(candidate["id"]): str(candidate["id"]) for _, candidate in candidates}

    def find(value: str) -> str:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(left: str, right: str) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[max(left_root, right_root)] = min(left_root, right_root)

    for left, right, _ in similarity_edges:
        union(left, right)

    for path, candidate in candidates:
        related = related_scenarios(candidate, normalized_scenarios, threshold=related_threshold)
        near = [item for item in related if item["similarity"] >= near_threshold]
        exact = [item for item in related if item["similarity"] >= 0.999999]
        if exact:
            exact_pairs.extend(
                {"candidate_id": candidate["id"], **item} for item in exact
            )
        cluster_key = "+".join(sorted(str(tag) for tag in candidate.get("tags", []) if tag not in {"candidate", "experience-mined"})) or "unclassified"
        clusters[cluster_key].append(str(candidate["id"]))
        entries.append(
            {
                "candidate_id": candidate["id"],
                "path": str(path),
                "fingerprint": candidate_fingerprint(candidate),
                "suite": candidate.get("suite"),
                "source_episode_id": candidate.get("review", {}).get("source_episode_id"),
                "source_evaluation_id": candidate.get("review", {}).get("source_evaluation_id"),
                "related_committed": related[:10],
                "near_duplicate_count": len(near),
                "historical_regression_recurrence": any(item["historical_regression"] for item in related),
                "review_status": candidate.get("review", {}).get("status"),
                "promotion_allowed": False,
            }
        )
    similarity_clusters: dict[str, list[str]] = defaultdict(list)
    for candidate_id in parent:
        similarity_clusters[find(candidate_id)].append(candidate_id)
    failure_counts = failure_tag_counts(candidate for _, candidate in candidates)
    committed_text = json.dumps(normalized_scenarios, ensure_ascii=False, sort_keys=True).casefold()
    coverage_gaps = sorted(tag for tag in failure_counts if tag.casefold() not in committed_text)
    return {
        "schema_version": 1,
        "manifest_id": manifest["manifest_id"],
        "candidate_count": len(entries),
        "committed_scenario_count": len(normalized_scenarios),
        "candidates": entries,
        "failure_tag_clusters": {key: sorted(values) for key, values in sorted(clusters.items())},
        "similarity_clusters": [
            sorted(values)
            for _, values in sorted(similarity_clusters.items())
            if len(values) > 1
        ],
        "candidate_similarity_edges": [
            {"left": left, "right": right, "similarity": round(score, 6)}
            for left, right, score in sorted(similarity_edges)
        ],
        "failure_tag_counts": failure_counts,
        "coverage_gaps": coverage_gaps,
        "exact_committed_duplicates": exact_pairs,
        "review_required": True,
        "automatic_promotion_performed": False,
        "runtime_policy_authority": False,
    }
