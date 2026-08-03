from __future__ import annotations

import copy
import json
import threading
from pathlib import Path
from typing import Any, Mapping

import pytest

from benchmarks.adapters.legacy_json import normalize_json_file
from benchmarks.e2e.evidence import EvidenceItem
from benchmarks.e2e.executor import E2EExecutionRecord
from benchmarks.e2e.profiles import EvidenceProfileManifest
from benchmarks.runners.models import ExecutionObservation
from benchmarks.stress.analyzer import analyze_results, compare_reports
from benchmarks.stress.profiles import (
    StressProfileError,
    StressWorkload,
    StressWorkloadManifest,
)
from benchmarks.stress.runner import StressBenchmarkRunner, StressRunProfile
from benchmarks.stress.workloads import build_sample_plan, select_workload_cases


REPO_ROOT = Path(__file__).resolve().parents[2]
STRESS_MANIFEST = REPO_ROOT / "benchmarks/manifests/stress_workloads.json"
E2E_MANIFEST = REPO_ROOT / "benchmarks/manifests/e2e_evidence_profiles.json"
SOCIAL_DATASET = REPO_ROOT / "benchmarks/datasets/social_attention/cases.json"


def _manifest() -> StressWorkloadManifest:
    return StressWorkloadManifest.from_file(STRESS_MANIFEST)


def _e2e_manifest() -> EvidenceProfileManifest:
    return EvidenceProfileManifest.from_file(E2E_MANIFEST)


def _social_cases() -> list[dict[str, Any]]:
    return normalize_json_file(
        SOCIAL_DATASET,
        repo_root=REPO_ROOT,
        layer="integration",
        datasets=("social_attention",),
        evidence_requirements=("static",),
    )


def _small_workload(**overrides: Any) -> StressWorkload:
    value: dict[str, Any] = {
        "id": "test_concurrency",
        "kind": "concurrency",
        "evidence_profile": "replay_text",
        "sample_count": 6,
        "session_count": 2,
        "concurrency": 2,
        "seed": 7,
        "selector": {
            "datasets": ["social_attention"],
            "cohorts": ["greetings_farewells"],
        },
        "sequence": {"strategy": "seeded_shuffle", "repeat_block_size": 1},
        "participants": [],
        "conditions": {"parallel_sessions": 2},
        "observations": [
            "sample_count",
            "status_distribution",
            "primary_task_success",
            "auxiliary_decision_distribution",
            "duplicate_auxiliary_rate",
            "latency_distribution",
            "evidence_completeness",
            "session_drift",
        ],
        "description": "Small deterministic test workload.",
    }
    value.update(overrides)
    return StressWorkload.from_mapping(value)


class RecordingExecutor:
    def __init__(self) -> None:
        self.metadata: list[Mapping[str, Any]] = []
        self._lock = threading.Lock()

    def execute(self, scenario, run, profile) -> E2EExecutionRecord:
        with self._lock:
            self.metadata.append(copy.deepcopy(run["metadata"]["stress"]))
        stress = run["metadata"]["stress"]
        sample_index = int(stress["sample_index"])
        auxiliary = "none" if sample_index % 2 == 0 else "acknowledgement"
        invariants = {
            name: True for name in scenario["expectations"]["invariants"]
        }
        observation = ExecutionObservation.from_dict(
            scenario["id"],
            {
                "primary_task_passed": True,
                "primary_outcome": {"sample_index": sample_index},
                "auxiliary_behavior": auxiliary,
                "behaviors": [],
                "invariant_results": invariants,
                "latency_ms": 20 + sample_index,
            },
        )
        evidence = (
            EvidenceItem(
                kind="scenario_replay",
                source="stress-test",
                correlation_id=run["correlation_id"],
                status="complete",
            ),
        )
        return E2EExecutionRecord(
            scenario_id=scenario["id"],
            correlation_id=run["correlation_id"],
            execution_state="completed",
            observation=observation,
            evidence=evidence,
            timing=({"auxiliary_started_ms": 1.0} if auxiliary != "none" else {}),
            execution_claims=("replayed_contract",),
            artifacts=(),
        )


def test_manifest_contains_all_workload_families_and_no_runtime_authority() -> None:
    manifest = _manifest()
    assert manifest.runtime_policy_authority is False
    assert manifest.metrics_are_observational is True
    assert {item.kind for item in manifest.workloads} == {
        "long_session",
        "repetition_cooldown",
        "interruption",
        "concurrency",
        "provider_degradation",
        "multi_user",
    }
    e2e = _e2e_manifest()
    for workload in manifest.workloads:
        assert e2e.get(workload.evidence_profile).id == workload.evidence_profile


def test_workload_manifest_rejects_policy_like_rate_targets() -> None:
    payload = json.loads(STRESS_MANIFEST.read_text(encoding="utf-8"))
    payload["workloads"][0]["conditions"]["target_auxiliary_rate"] = 0.2
    with pytest.raises(StressProfileError, match="prohibited runtime-policy field"):
        StressWorkloadManifest.from_mapping(payload)


def test_every_maintained_workload_selects_reviewed_cases() -> None:
    cases = _social_cases()
    for workload in _manifest().workloads:
        selected = select_workload_cases(cases, workload)
        assert selected, workload.id
        assert all("social_attention" in case["datasets"] for case in selected)


def test_seeded_sample_plan_is_deterministic_and_session_bounded() -> None:
    workload = _small_workload()
    first = build_sample_plan(_social_cases(), workload)
    second = build_sample_plan(_social_cases(), workload)
    assert [item.source_scenario_id for item in first] == [
        item.source_scenario_id for item in second
    ]
    assert len(first) == 6
    assert {item.session_id for item in first} == {
        "test_concurrency.session-001",
        "test_concurrency.session-002",
    }
    assert [item.index for item in first] == list(range(6))


def test_repeat_each_sequence_builds_contiguous_pressure_blocks() -> None:
    workload = _small_workload(
        id="test_repetition",
        kind="repetition_cooldown",
        sample_count=9,
        session_count=1,
        concurrency=1,
        sequence={"strategy": "repeat_each", "repeat_block_size": 3},
    )
    plan = build_sample_plan(_social_cases(), workload)
    assert len({item.source_scenario_id for item in plan[:3]}) == 1
    assert len({item.source_scenario_id for item in plan[3:6]}) == 1
    assert plan[0].source_scenario_id != plan[3].source_scenario_id


def test_multi_user_plan_alternates_synthetic_participants() -> None:
    workload = _small_workload(
        id="test_multi_user",
        kind="multi_user",
        sample_count=6,
        session_count=2,
        concurrency=2,
        participants=["speaker_a", "speaker_b"],
    )
    plan = build_sample_plan(_social_cases(), workload)
    assert [item.participant_id for item in plan] == [
        "speaker_a",
        "speaker_b",
        "speaker_a",
        "speaker_b",
        "speaker_a",
        "speaker_b",
    ]


def test_stress_runner_preserves_order_and_passes_harness_metadata() -> None:
    workload = _small_workload()
    executor = RecordingExecutor()
    report = StressBenchmarkRunner(
        lambda sample: executor,
        StressRunProfile(
            run_id="stress-test",
            model="model-a",
            prompt_revision="prompt-a",
            mind_profile="courteous",
        ),
        workload,
        _e2e_manifest().get("replay_text"),
    ).run(_social_cases())
    assert report["summary"]["samples"] == 6
    assert report["summary"]["review"] == 6
    assert [item["sample"]["index"] for item in report["results"]] == list(range(6))
    assert report["qualification"]["release_qualified"] is False
    assert report["qualification"]["runtime_policy_authority"] is False
    assert report["distribution"]["sample_count"] == 6
    assert {item["workload_id"] for item in executor.metadata} == {"test_concurrency"}
    assert all(item["runtime_policy_authority"] is False for item in executor.metadata)


def _result(
    index: int,
    auxiliary: str,
    *,
    primary: bool = True,
    forbidden: list[str] | None = None,
    invariant_failed: str | None = None,
    latency: float = 100,
) -> dict[str, Any]:
    invariant_results = []
    if invariant_failed:
        invariant_results.append(
            {"name": invariant_failed, "passed": False, "detail": "observed"}
        )
    return {
        "status": "pass" if primary and not invariant_failed and not forbidden else "fail",
        "sample": {
            "index": index,
            "session_id": "session-1",
            "sequence_position": index + 1,
        },
        "observations": {
            "primary_task_passed": primary,
            "auxiliary_behavior": auxiliary,
            "behaviors": [],
            "latency_ms": latency,
            "derived_timing": {"input_to_primary_response_ms": latency - 10},
        },
        "evaluation": {"forbidden_behavior_hits": forbidden or []},
        "invariant_results": invariant_results,
        "qualification": {"evidence_state": "complete"},
    }


def test_distribution_analyzer_reports_duplicates_drift_and_intervals() -> None:
    report = analyze_results(
        [
            _result(0, "none", latency=90),
            _result(1, "acknowledgement", latency=100),
            _result(
                2,
                "acknowledgement",
                forbidden=["repeated_auxiliary_behavior"],
                invariant_failed="forbidden_behavior:repeated_auxiliary_behavior",
                latency=110,
            ),
            _result(3, "friendly_expression", primary=False, latency=120),
        ]
    )
    assert report["sample_count"] == 4
    assert report["primary_task"]["success_rate"] == 0.75
    assert report["auxiliary_decisions"]["none_selection_rate"] == 0.25
    assert report["duplicate_auxiliary"]["count"] == 1
    assert report["duplicate_auxiliary"]["eligible_non_none_transitions"] == 2
    assert report["duplicate_auxiliary"]["rate"] == 0.5
    assert report["violations"]["families"]["cooldown"]["sample_count"] == 1
    assert report["session_drift"]["sessions"][0]["auxiliary_rate_delta"] == 0.5
    assert report["latency_ms"]["observation"]["p50"] == 105
    assert report["latency_ms"]["observation"]["p95"] == pytest.approx(118.5)
    assert report["confidence_intervals_95"]["any_auxiliary"]["sample_count"] == 4


def _stress_report(run_id: str, model: str, auxiliary: list[str]) -> dict[str, Any]:
    distribution = analyze_results(
        [_result(index, value) for index, value in enumerate(auxiliary)]
    )
    return {
        "schema_version": 1,
        "run": {"run_id": run_id, "model": model, "prompt_revision": "p1"},
        "workload": {"id": "same-workload"},
        "evidence_profile": {"id": "replay_text"},
        "distribution": distribution,
    }


def test_model_comparison_reports_deltas_without_selecting_winner() -> None:
    comparison = compare_reports(
        [
            _stress_report("a", "model-a", ["none", "none", "ack"]),
            _stress_report("b", "model-b", ["ack", "ack", "ack"]),
        ]
    )
    assert comparison["baseline_run_id"] == "a"
    assert comparison["ranking_or_winner_selected"] is False
    assert comparison["comparisons"][1]["delta_from_baseline"][
        "any_auxiliary_rate"
    ] == pytest.approx(2 / 3)


def test_model_comparison_rejects_mismatched_workloads() -> None:
    first = _stress_report("a", "model-a", ["none"])
    second = _stress_report("b", "model-b", ["none"])
    second["workload"] = {"id": "other-workload"}
    with pytest.raises(StressProfileError, match="one workload"):
        compare_reports([first, second])


def test_stress_contract_schemas_are_valid_json_and_non_qualifying() -> None:
    workload_schema = json.loads(
        (REPO_ROOT / "benchmarks/contracts/stress-workload.schema.json").read_text(
            encoding="utf-8"
        )
    )
    result_schema = json.loads(
        (REPO_ROOT / "benchmarks/contracts/stress-suite-result.schema.json").read_text(
            encoding="utf-8"
        )
    )
    assert workload_schema["properties"]["runtime_policy_authority"]["const"] is False
    qualification = result_schema["properties"]["qualification"]["properties"]
    assert qualification["release_qualified"]["const"] is False
    assert qualification["runtime_policy_authority"]["const"] is False
