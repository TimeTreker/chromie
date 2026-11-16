"""Export only hash-bound, reviewed and redacted production transactions."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
from pathlib import Path
from typing import Any

from .common import Rejected, digest, loads, privacy_check, private_dir, redact, source_identity, write_json
from .contracts import receipt_packet, replay, schema_order_hash


def receipts(paths: list[Path]) -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    for path in paths:
        with path.open() as stream:
            for line in stream:
                if "llm_call_evidence " in line:
                    line = line.split("llm_call_evidence ", 1)[1]
                elif not line.lstrip().startswith("{"):
                    continue
                value = loads(line)
                if value.get("event") != "chromie.llm_call_evidence":
                    continue
                found[digest(value)] = value
    if not found:
        raise Rejected("no_complete_llm_receipts")
    return found


def trace_index(paths: list[Path]) -> dict[str, tuple[str, dict[str, Any]]]:
    result = {}
    for path in paths:
        payload = loads(path.read_text())
        trace = payload.get("trace", payload)
        if trace.get("schema_version") != 1 or not trace.get("trace_id"):
            raise Rejected("unsupported_runtime_trace")
        result[trace["trace_id"]] = (digest(payload), trace)
    return result


def sanitized_case(review: dict[str, Any], sources: dict[str, Any],
                   replacements: list[dict[str, str]]) -> dict[str, Any]:
    case = redact({"transaction": review["transaction"],
                   "calls": [receipt_packet(sources[key]) for key in review["receipt_sha256"]]}, replacements)
    for call in case["calls"]:
        call["schema_order_sha256"] = schema_order_hash(call["schema"])
    privacy_check(case)
    return case


def prepare(review: dict[str, Any], sources: dict[str, Any], traces: dict[str, Any],
            replacements: list[dict[str, str]], salt: bytes) -> dict[str, Any]:
    if len(salt) < 32:
        raise Rejected("salt_at_least_32_bytes_required")
    if (review.get("status") != "approved" or review.get("privacy_approved") is not True
            or review.get("semantic_approved") is not True or not review.get("reviewer")):
        raise Rejected("explicit_privacy_and_semantic_review_required")
    if review.get("split") not in {"train", "validation", "frozen_test"}:
        raise Rejected("explicit_split_required")
    if review["split"] == "train" and review.get("training_eligible") is not True:
        raise Rejected("holdout_not_training_eligible")
    ids = review["receipt_sha256"]
    if not ids or len(ids) != len(set(ids)):
        raise Rejected("unique_ordered_receipts_required")
    selected = [sources[key] for key in ids]
    # Ordinary Runtime Trace contains timing and correlation, never enough prompt
    # or output text to invent an SFT pair. Join only a complete matching receipt.
    trace_refs = []
    for record in selected:
        trace_id = record.get("correlations", {}).get("trace_id")
        if not trace_id and record.get("correlations", {}).get("turn_id"):
            turn_id = record["correlations"]["turn_id"]
            matches = [key for key, (_, trace) in traces.items()
                       if turn_id in [trace.get("correlations", {}).get(field)
                                      for field in ("session_id", "turn_id", "interaction_id")]]
            if len(matches) > 1:
                raise Rejected("ambiguous_trace_correlation")
            trace_id = matches[0] if matches else None
        if trace_id:
            if trace_id not in traces or traces[trace_id][1].get("state") != "complete":
                raise Rejected("missing_or_incomplete_correlated_trace")
            trace_refs.append(traces[trace_id][0])
    if sorted(set(trace_refs)) != sorted(set(review.get("trace_sha256", []))):
        raise Rejected("trace_review_identity_mismatch")
    case = sanitized_case(review, sources, replacements)
    # Review binds the entire sanitized packet, source DTO and Capability snapshots.
    # Editing a redaction, label, target, or input invalidates the review.
    if digest(case) != review.get("sanitized_sha256"):
        raise Rejected("sanitized_review_identity_mismatch")
    asyncio.run(replay(case))
    group = review.get("conversation_group")
    contrast = review.get("contrast_group")
    if not isinstance(group, str) or not group or not isinstance(contrast, str) or not contrast:
        raise Rejected("conversation_and_contrast_groups_required")
    def pseudonym(text: str) -> str:
        return hmac.new(salt, text.encode(), hashlib.sha256).hexdigest()
    case.update(id=digest(case), split=review["split"], training_eligible=review.get("training_eligible") is True,
                language=review["language"], category=review["category"],
                groups=[pseudonym("conversation:" + group), pseudonym("contrast:" + contrast)],
                source_receipt_sha256=ids, trace_sha256=sorted(set(trace_refs)),
                trace_coverage="correlated" if trace_refs else "unavailable",
                review_sha256=digest(review), privacy="reviewed_redacted_local_only")
    privacy_check(case)
    return case


def export_cases(cases: list[dict[str, Any]], output: Path) -> dict[str, Any]:
    if not cases or len({case["id"] for case in cases}) != len(cases):
        raise Rejected("empty_or_duplicate_transactions")
    partitions: dict[str, str] = {}
    samples = []
    for case in cases:
        # Whole conversations, contrast families, identical inputs and duplicate
        # targets stay in one split. Different labels for one input fail closed.
        keys = [*case["groups"], *case["source_receipt_sha256"]]
        keys += [digest(call["messages"]) for call in case["calls"]]
        for key in keys:
            if key in partitions and partitions[key] != case["split"]:
                raise Rejected("cross_split_leakage")
            partitions[key] = case["split"]
        for call in case["calls"]:
            samples.append({"case_id": case["id"], "split": case["split"],
                            "role": case["transaction"]["role"], "stage": call["stage"],
                            "language": case["language"], "category": case["category"],
                            "messages": call["messages"], "completion": call["completion"],
                            "schema_sha256": digest(call["schema"])})
    # Deduplicate within each split without removing case-level evaluation truth.
    samples = list({digest({k: row[k] for k in ("split", "messages", "completion")}): row
                    for row in samples}.values())
    private_dir(output)
    (output / "cases").mkdir(mode=0o700)
    for case in cases:
        write_json(output / "cases" / (case["id"] + ".json"), case)
    for split in ("train", "validation", "frozen_test"):
        from .common import encoded
        path = output / (split + ".jsonl")
        import os
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            for row in samples:
                if row["split"] == split:
                    stream.write(encoded(row) + b"\n")
    manifest = {"schema_version": 1, "source": source_identity(),
                "cases": {case["id"]: digest(case) for case in cases},
                "counts": {split: sum(row["split"] == split for row in samples)
                           for split in ("train", "validation", "frozen_test")},
                "training_eligible": False, "automatic_promotion": False}
    from .common import file_digest
    manifest["files"] = {split + ".jsonl": file_digest(output / (split + ".jsonl"))
                         for split in ("train", "validation", "frozen_test")}
    write_json(output / "manifest.json", manifest)
    return manifest


def load_dataset(root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    from .common import file_digest
    manifest = loads((root / "manifest.json").read_text())
    if any(file_digest(root / name) != sha for name, sha in manifest["files"].items()):
        raise Rejected("dataset_file_identity_mismatch")
    cases = [loads(path.read_text()) for path in sorted((root / "cases").glob("*.json"))]
    if {case["id"]: digest(case) for case in cases} != manifest["cases"]:
        raise Rejected("frozen_case_identity_mismatch")
    return manifest, cases
