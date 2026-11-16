"""Frozen, target-blind resolver inference and strict paired non-regression checks."""
from __future__ import annotations

import asyncio
import logging
import math
import time
from pathlib import Path
from typing import Any

from .common import Rejected, digest, local_url, loads, private_dir, source_identity, write_json
from .contracts import replay
from .dataset import load_dataset

_SERVER_POLICY = ("version", "dtype", "kv_cache_dtype", "quantization", "context_length",
                  "max_total_tokens", "max_running_requests", "chunked_prefill_size", "schedule_policy",
                  "enable_priority_scheduling", "reasoning_parser", "tool_call_parser", "grammar_backend")


def server_identity(url: str) -> dict[str, Any]:
    import httpx
    with httpx.Client(trust_env=False, follow_redirects=False, timeout=10) as client:
        response = client.get(url.removesuffix("/v1") + "/get_server_info")
        response.raise_for_status()
        payload = response.json()
    args = payload.get("server_args", payload)
    keys = (*_SERVER_POLICY, "model_path", "revision", "served_model_name", "random_seed")
    # Some SGLang releases expose credentials in server_info. Never retain its
    # unrestricted dictionary, even in a private evaluation artifact.
    return {key: args.get(key, payload.get(key)) for key in keys}


def evaluate(*, dataset: Path, output: Path, split: str, url: str | None = None,
             model: str | None = None) -> dict[str, Any]:
    from .model import offline
    offline()
    manifest, cases = load_dataset(dataset)
    source = source_identity()
    if manifest["source"] != source:
        raise Rejected("evaluation_source_differs_from_dataset")
    if split not in {"validation", "frozen_test"}:
        raise Rejected("held_out_split_required")
    selected = [case for case in cases if case["split"] == split]
    if not selected:
        raise Rejected("empty_evaluation_cohort")
    candidate = None
    identity = None
    transport_records: list[Any] = []
    class PrivateEvidence(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            text = record.getMessage()
            if text.startswith("llm_call_evidence "):
                transport_records.append(loads(text.split(" ", 1)[1]))
    if url is not None:
        import httpx
        from agent.app.clients.sglang_client import SGLangClient
        if not model:
            raise Rejected("explicit_candidate_model_required")
        url = local_url(url)
        with httpx.Client(trust_env=False, follow_redirects=False, timeout=10) as client:
            response = client.get(url + "/models")
            response.raise_for_status()
            if model not in {item["id"] for item in response.json()["data"]}:
                raise Rejected("candidate_served_model_missing")
        identity = server_identity(url)
        candidate = SGLangClient(url, model, timeout_ms=600_000, purpose="offline_qualification")
    elif model:
        raise Rejected("candidate_url_required")
    # Production resolver failures may log private payloads. Retain them only in
    # the private report, never in console or a telemetry sink.
    for name in ("chromie.agent", "chromie.runtime"):
        logging.getLogger(name).setLevel(logging.CRITICAL)
    if candidate is not None:
        # The maintained client already records complete requests/raw responses,
        # including malformed outputs, cancellation and HTTP failures. Keep those
        # records in this private artifact rather than losing failures to parsing.
        logger = logging.getLogger("chromie.agent.sglang")
        logger.handlers = [PrivateEvidence()]
        logger.propagate = False
        logger.setLevel(logging.INFO)
        logging.disable(logging.NOTSET)
    private_dir(output)
    results = []
    server_unchanged = True
    for case in selected:
        transport_records.clear()
        started = time.perf_counter()
        try:
            if candidate is not None and server_identity(url) != identity:
                server_unchanged = False
                raise Rejected("serving_identity_changed")
            result = asyncio.run(replay(case, candidate))
        except Exception as exc:
            result = {"verdict": "hard_failure", "error_type": type(exc).__name__,
                      "error_code": str(exc) if isinstance(exc, Rejected) else "resolver_rejected"}
        result.update(case_id=case["id"], role=case["transaction"]["role"],
                      variant=case["transaction"]["variant"], language=case["language"], category=case["category"],
                      elapsed_ms=(time.perf_counter() - started) * 1000)
        result["transport_records"] = list(transport_records)
        write_json(output / (case["id"] + ".json"), result)
        results.append(result)
        if result["verdict"] != "pass":
            break  # A hard failure makes the batch incomplete, never an aggregate pass.
    source_unchanged = source_identity() == source
    if candidate is not None:
        try:
            server_unchanged = server_unchanged and server_identity(url) == identity
        except Exception:
            server_unchanged = False
    summary = {"schema_version": 1, "kind": "chromie.offline_adaptation_evaluation",
               "source": source, "source_unchanged": source_unchanged, "server_unchanged": server_unchanged,
               "dataset_sha256": digest(manifest), "split": split,
               "mode": "native_candidate" if candidate else "reference_replay",
               "model": model, "server_identity": identity, "url": url,
               "expected_cases": [case["id"] for case in selected],
               "results": results, "complete": len(results) == len(selected) and source_unchanged and server_unchanged,
               "passed": len(results) == len(selected) and source_unchanged and server_unchanged and all(row["verdict"] == "pass" for row in results),
               "promotion_allowed": False, "physical_evidence": False}
    write_json(output / "summary.json", summary)
    return summary


def compare(baseline: dict[str, Any], candidate: dict[str, Any], review: dict[str, Any],
            *, latency_ratio: float = 1.2) -> dict[str, Any]:
    if not math.isfinite(latency_ratio) or latency_ratio < 1:
        raise Rejected("invalid_latency_gate")
    for report in (baseline, candidate):
        if (report.get("mode") != "native_candidate" or report.get("passed") is not True
                or report.get("complete") is not True or report.get("source_unchanged") is not True
                or report.get("server_unchanged") is not True):
            raise Rejected("two_complete_native_cohorts_required")
    for key in ("source", "dataset_sha256", "split", "expected_cases"):
        if baseline[key] != candidate[key]:
            raise Rejected("paired_cohort_identity_mismatch")
    for key in _SERVER_POLICY:
        if baseline["server_identity"].get(key) != candidate["server_identity"].get(key):
            raise Rejected("serving_policy_changed:" + key)
    if review.get("baseline_sha256") != digest(baseline) or review.get("candidate_sha256") != digest(candidate):
        raise Rejected("semantic_review_identity_mismatch")
    if not review.get("reviewer") or review.get("independent") is not True:
        raise Rejected("independent_semantic_review_required")
    left = {row["case_id"]: row for row in baseline["results"]}
    right = {row["case_id"]: row for row in candidate["results"]}
    expected = set(candidate["expected_cases"])
    if not expected or set(left) != expected or set(right) != expected or set(review["cases"]) != expected:
        raise Rejected("missing_or_extra_case_adjudication")
    failures = []
    slices: dict[str, list[str]] = {}
    for key in sorted(expected):
        before, after = left[key], right[key]
        judgment = review["cases"][key]
        for report in (before, after):
            if report["verdict"] != "pass":
                failures.append({"case_id": key, "reason": "hard_failure"})
        if judgment.get("candidate_acceptable") is not True or judgment.get("regressed") is not False:
            failures.append({"case_id": key, "reason": "semantic_failure_or_regression"})
        if after["elapsed_ms"] > max(before["elapsed_ms"] * latency_ratio, before["elapsed_ms"] + 50):
            failures.append({"case_id": key, "reason": "latency_regression"})
        for dimension in ("role", "variant", "language", "category"):
            if before[dimension] != after[dimension]:
                raise Rejected("case_slice_changed")
            slices.setdefault(dimension + ":" + after[dimension], []).append(key)
    return {"passed": not failures, "failures": failures,
            "slices": {key: {"count": len(ids), "failures": sum(row["case_id"] in ids for row in failures)}
                       for key, ids in slices.items()},
            "baseline_sha256": digest(baseline), "candidate_sha256": digest(candidate),
            "review_sha256": digest(review), "promotion_allowed": False,
            "remaining_gates": ["canonical_local", "all_role_native_workflow", "everyday_complete_cohort",
                                "supervised_voice", "default_target_evidence"]}
