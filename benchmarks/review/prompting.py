from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from benchmarks.contracts import ContractError

PROMPT_PROTOCOL_VERSION = "chromie-semantic-review-v1"
_TEXT_SUFFIXES = frozenset(
    {".json", ".jsonl", ".log", ".txt", ".md", ".csv", ".tsv", ".yaml", ".yml"}
)


def _digest_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _bounded_file_text(path: Path, limit: int) -> str:
    size = path.stat().st_size
    if size <= max(4096, limit * 2):
        return _bounded_text(
            path.read_text(encoding="utf-8", errors="replace"), limit
        )
    head_size = max(1, limit * 2 // 3)
    tail_size = max(1, limit - head_size)
    with path.open("rb") as handle:
        head = handle.read(head_size)
        handle.seek(max(0, size - tail_size))
        tail = handle.read(tail_size)
    omitted = max(0, size - len(head) - len(tail))
    return (
        head.decode("utf-8", errors="replace")
        + f"\n... <approximately {omitted} bytes omitted> ...\n"
        + tail.decode("utf-8", errors="replace")
    )


def _bounded_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    head = max(1, limit * 2 // 3)
    tail = max(1, limit - head)
    omitted = len(text) - head - tail
    return f"{text[:head]}\n... <{omitted} characters omitted> ...\n{text[-tail:]}"


def _resolve_artifact(bundle_dir: Path, raw: str) -> Path | None:
    candidate = Path(raw)
    if candidate.is_absolute():
        return candidate if candidate.exists() else None
    for path in (bundle_dir / candidate, bundle_dir / "artifacts" / candidate):
        if path.exists():
            return path
    return None


def _artifact_capsule(
    bundle_dir: Path,
    inventory: list[Any],
    *,
    max_artifact_chars: int,
    remaining_chars: int,
) -> tuple[list[dict[str, Any]], int]:
    capsule: list[dict[str, Any]] = []
    remaining = remaining_chars
    for row in inventory:
        if not isinstance(row, Mapping):
            continue
        label = str(row.get("label") or row.get("included_path") or "artifact")
        included_path = row.get("included_path")
        record: dict[str, Any] = {
            "label": label,
            "status": row.get("status"),
            "included_path": included_path,
        }
        if row.get("status") != "included" or not isinstance(included_path, str):
            capsule.append(record)
            continue
        path = _resolve_artifact(bundle_dir, included_path)
        if path is None:
            record["status"] = "missing_at_review_time"
            capsule.append(record)
            continue
        if path.is_dir():
            entries: list[str] = []
            for item in path.rglob("*"):
                if item.is_file():
                    entries.append(str(item.relative_to(path)))
                if len(entries) >= 200:
                    break
            record.update({"kind": "directory", "entries": sorted(entries)})
            capsule.append(record)
            continue
        size = path.stat().st_size
        record.update(
            {
                "kind": "file",
                "size": size,
                "sha256": _digest_file(path),
            }
        )
        if path.suffix.lower() in _TEXT_SUFFIXES and remaining > 0:
            limit = min(max_artifact_chars, remaining)
            excerpt = _bounded_file_text(path, limit)
            record["text_excerpt"] = excerpt
            remaining -= len(excerpt)
        else:
            record["text_excerpt"] = None
        capsule.append(record)
    return capsule, remaining


def render_review_prompt(
    bundle: Mapping[str, Any],
    scenario_case: Mapping[str, Any],
    *,
    bundle_dir: Path,
    max_input_chars: int = 120_000,
    max_artifact_chars: int = 20_000,
) -> tuple[str, str, dict[str, Any]]:
    scenario_id = str(scenario_case.get("scenario_id") or "").strip()
    if not scenario_id:
        raise ContractError("semantic review bundle scenario requires scenario_id")
    inventory = scenario_case.get("artifact_inventory") or []
    if not inventory:
        references = scenario_case.get("artifact_references") or []
        if isinstance(references, list):
            inventory = [
                {
                    "label": Path(str(raw)).name or f"artifact-{index}",
                    "status": "included",
                    "included_path": str(raw),
                }
                for index, raw in enumerate(references)
            ]
    if not isinstance(inventory, list):
        raise ContractError(
            f"semantic review scenario {scenario_id!r} artifact_inventory "
            "must be an array"
        )
    base = {
        "prompt_protocol_version": PROMPT_PROTOCOL_VERSION,
        "run": bundle.get("run") or {},
        "scenario_id": scenario_id,
        "review_reason": scenario_case.get("review_reason"),
        "oracle_policy": scenario_case.get("oracle_policy") or {},
        "scenario": scenario_case.get("scenario") or {},
        "execution_result": scenario_case.get("execution_result") or {},
        "review_request": scenario_case.get("review_request") or {},
    }
    base_text = json.dumps(base, ensure_ascii=False, indent=2, sort_keys=True)
    remaining = max(0, max_input_chars - len(base_text) - 4000)
    artifact_capsule, _ = _artifact_capsule(
        bundle_dir,
        inventory,
        max_artifact_chars=max_artifact_chars,
        remaining_chars=remaining,
    )
    evidence = {**base, "retained_artifacts": artifact_capsule}
    evidence_text = _bounded_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True),
        max_input_chars,
    )
    system_prompt = (
        "You are an independent evaluator of Chromie benchmark scenarios. "
        "Judge only the declared semantic dimensions from retained evidence. "
        "Deterministic failures and hard-gate results are non-overridable. "
        "Do not require exact wording unless the scenario declares text as a contract. "
        "Do not infer missing evidence. Return JSON only, without markdown fences."
    )
    dimensions = (
        scenario_case.get("review_request", {}).get("semantic_dimensions", [])
        if isinstance(scenario_case.get("review_request"), Mapping)
        else []
    )
    response_shape = {
        "scenario_id": scenario_id,
        "verdict": "pass | partial | fail | insufficient_evidence",
        "rationale": "Evidence-grounded explanation",
        "evidence_refs": ["specific retained event, artifact, or field"],
        "dimensions": {
            str(dimension): {
                "verdict": "pass | partial | fail | insufficient_evidence",
                "rationale": "Dimension-specific explanation",
            }
            for dimension in dimensions
        },
        "findings": [
            {
                "severity": "low | medium | high | critical",
                "stage": "component or lifecycle stage",
                "problem": "specific observed problem",
                "evidence_refs": ["specific evidence"],
            }
        ],
        "likely_root_causes": ["bounded hypothesis, clearly identified as inference"],
    }
    user_prompt = (
        "Review this single scenario evidence capsule. Use pass only when the declared "
        "semantic behavior is supported. Use insufficient_evidence when the retained "
        "artifacts cannot support a judgment. Cite evidence_refs that exist in the "
        "capsule. Return exactly one JSON object matching this shape:\n"
        + json.dumps(response_shape, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n\nEVIDENCE CAPSULE:\n"
        + evidence_text
    )
    prompt_bytes = (system_prompt + "\n\n" + user_prompt).encode("utf-8")
    metadata = {
        "scenario_id": scenario_id,
        "prompt_protocol_version": PROMPT_PROTOCOL_VERSION,
        "prompt_sha256": _digest_bytes(prompt_bytes),
        "prompt_chars": len(system_prompt) + len(user_prompt),
        "artifact_count": len(artifact_capsule),
    }
    return system_prompt, user_prompt, metadata
