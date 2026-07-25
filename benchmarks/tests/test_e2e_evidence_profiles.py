from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

from benchmarks.adapters.normalize import normalize_inventory
from benchmarks.inventory.core import build_inventory
from benchmarks.e2e.evidence import (
    EvidenceItem,
    validate_claims,
    validate_timing,
)
from benchmarks.e2e.executor import CommandE2EExecutor, ReplayE2EExecutor
from benchmarks.e2e.profiles import (
    EvidenceProfile,
    EvidenceProfileError,
    EvidenceProfileManifest,
)
from benchmarks.e2e.runner import E2EBenchmarkRunner, E2ERunProfile


REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / "benchmarks/manifests/e2e_evidence_profiles.json"


def _scenario() -> dict:
    return {
        "schema_version": 1,
        "id": "sa.v1.test.e2e",
        "layer": "integration",
        "datasets": ["social_attention"],
        "source": {
            "path": "benchmarks/datasets/social_attention/cases.json",
            "adapter": "legacy_json_v1",
            "source_index": 0,
            "source_id": "sa.v1.test.e2e",
        },
        "inputs": {"text": "Hello there."},
        "context": {},
        "capabilities": ["social_attention.acknowledgement"],
        "expectations": {
            "primary_outcomes": ["Acknowledge naturally"],
            "acceptable_auxiliary": ["none", "one bounded cue"],
            "forbidden_behaviors": ["locomotion"],
            "invariants": [],
            "distribution_observations": ["auxiliary_selection"],
        },
        "evidence_requirements": ["live_service"],
        "review_rubric": {},
        "legacy_expectations": {},
    }


def _manifest() -> EvidenceProfileManifest:
    return EvidenceProfileManifest.from_file(MANIFEST_PATH)


def test_manifest_declares_distinct_evidence_profiles() -> None:
    manifest = _manifest()
    assert [item.id for item in manifest.profiles] == [
        "replay_text",
        "live_model_text",
        "live_service_text",
        "live_service_virtual_audio",
        "simulated_mujoco",
        "physical_supervised",
    ]
    physical = manifest.get("physical_supervised")
    assert physical.evidence_level == "physical"
    assert physical.supervision == "operator_required"
    assert physical.human_approval_required is True
    assert physical.requires_safe_idle is True


def test_physical_profile_cannot_be_unsupervised() -> None:
    value = _manifest().get("physical_supervised").to_dict()
    value["supervision"] = "automatic"
    with pytest.raises(EvidenceProfileError, match="operator supervision"):
        EvidenceProfile.from_mapping(value)


def test_execution_claims_cannot_exceed_profile() -> None:
    profile = _manifest().get("live_service_text")
    result = validate_claims(profile, ["physical_provider_execution"])
    assert result["valid"] is False
    assert result["forbidden"] == ["physical_provider_execution"]


def test_auxiliary_timing_is_observed_not_prescribed() -> None:
    profile = _manifest().get("live_service_text")
    timing = validate_timing(
        profile,
        {
            "input_received_ms": 0,
            "primary_response_started_ms": 100,
            "auxiliary_started_ms": 120,
            "terminal_ms": 400,
        },
        auxiliary_behavior="one bounded cue",
    )
    assert timing["complete"] is True
    assert timing["derived"]["auxiliary_offset_from_primary_response_ms"] == 20
    assert "auxiliary_started_ms" in timing["required"]


def _write_success_adapter(path: Path) -> None:
    path.write_text(
        """
import json
import sys
from pathlib import Path
request = json.load(sys.stdin)
correlation_id = request["run"]["correlation_id"]
partial = Path(request["partial_evidence_path"])
partial.write_text(json.dumps({
    "kind": "cognitive_gateway_turn",
    "source": "gateway",
    "correlation_id": correlation_id,
    "status": "observed"
}) + "\\n", encoding="utf-8")
evidence = []
for kind, source in [
    ("cognitive_core_result", "agent"),
    ("primary_response", "orchestrator"),
    ("correlated_trace", "runtime_trace"),
]:
    evidence.append({
        "kind": kind,
        "source": source,
        "correlation_id": correlation_id,
        "status": "complete"
    })
print(json.dumps({
    "schema_version": 1,
    "scenario_id": request["scenario"]["id"],
    "correlation_id": correlation_id,
    "execution_state": "completed",
    "execution_claims": ["deployed_service_execution"],
    "timing": {
        "input_received_ms": 0,
        "primary_response_started_ms": 100,
        "terminal_ms": 250
    },
    "evidence": evidence,
    "observation": {
        "primary_task_passed": True,
        "primary_outcome": {"response": "hello"},
        "auxiliary_behavior": "none",
        "behaviors": [],
        "invariant_results": {}
    }
}))
""".strip()
        + "\n",
        encoding="utf-8",
    )


def test_command_e2e_run_retains_correlated_evidence(tmp_path: Path) -> None:
    adapter = tmp_path / "adapter.py"
    _write_success_adapter(adapter)
    scenario = _scenario()
    original = copy.deepcopy(scenario)
    profile = _manifest().get("live_service_text")
    report = E2EBenchmarkRunner(
        CommandE2EExecutor(
            [sys.executable, str(adapter)],
            timeout_s=5,
            artifact_root=tmp_path / "artifacts",
        ),
        E2ERunProfile(run_id="run-1", evidence_profile=profile),
    ).run([scenario])
    assert scenario == original
    assert report["summary"]["pass"] == 1
    assert report["summary"]["evidence_complete"] == 1
    assert report["qualification"]["release_qualified"] is False
    assert report["qualification"]["state"] == "human_review_required"
    result = report["results"][0]
    assert result["observations"]["partial_evidence_retained"] is True
    assert result["qualification"]["evidence_state"] == "complete"
    assert result["run"]["correlation_id"] == "run-1:sa.v1.test.e2e"
    assert {item["kind"] for item in result["observations"]["evidence"]} == {
        "cognitive_gateway_turn",
        "cognitive_core_result",
        "primary_response",
        "correlated_trace",
    }


def test_command_failure_retains_partial_evidence(tmp_path: Path) -> None:
    adapter = tmp_path / "failed_adapter.py"
    adapter.write_text(
        """
import json
import sys
from pathlib import Path
request = json.load(sys.stdin)
Path(request["partial_evidence_path"]).write_text(json.dumps({
    "kind": "cognitive_gateway_turn",
    "source": "gateway",
    "correlation_id": request["run"]["correlation_id"],
    "status": "observed"
}) + "\\n", encoding="utf-8")
raise SystemExit(7)
""".strip()
        + "\n",
        encoding="utf-8",
    )
    profile = _manifest().get("live_service_text")
    report = E2EBenchmarkRunner(
        CommandE2EExecutor(
            [sys.executable, str(adapter)],
            timeout_s=5,
            artifact_root=tmp_path / "artifacts",
        ),
        E2ERunProfile(run_id="run-failed", evidence_profile=profile),
    ).run([_scenario()])
    result = report["results"][0]
    assert result["status"] == "error"
    assert result["observations"]["partial_evidence_retained"] is True
    assert result["qualification"]["evidence_state"] == "partial"
    assert result["observations"]["evidence"][0]["kind"] == "cognitive_gateway_turn"



def test_timeout_retains_checkpoint_evidence(tmp_path: Path) -> None:
    adapter = tmp_path / "timeout_adapter.py"
    adapter.write_text(
        """
import json
import sys
import time
from pathlib import Path
request = json.load(sys.stdin)
Path(request["partial_evidence_path"]).write_text(json.dumps({
    "kind": "cognitive_gateway_turn",
    "source": "gateway",
    "correlation_id": request["run"]["correlation_id"],
    "status": "observed"
}) + "\\n", encoding="utf-8")
time.sleep(2)
""".strip()
        + "\n",
        encoding="utf-8",
    )
    profile = _manifest().get("live_service_text")
    report = E2EBenchmarkRunner(
        CommandE2EExecutor(
            [sys.executable, str(adapter)],
            timeout_s=0.8,
            artifact_root=tmp_path / "artifacts",
        ),
        E2ERunProfile(run_id="run-timeout", evidence_profile=profile),
    ).run([_scenario()])
    result = report["results"][0]
    assert result["status"] == "error"
    assert result["observations"]["execution_state"] == "timeout"
    assert result["observations"]["partial_evidence_retained"] is True
    assert result["observations"]["evidence"][0]["kind"] == "cognitive_gateway_turn"


def test_replay_cannot_claim_physical_execution(tmp_path: Path) -> None:
    scenario = _scenario()
    replay = tmp_path / "replay.json"
    replay.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "observations": {
                    scenario["id"]: {
                        "schema_version": 1,
                        "scenario_id": scenario["id"],
                        "execution_state": "completed",
                        "execution_claims": ["physical_provider_execution"],
                        "timing": {},
                        "evidence": [
                            {
                                "kind": "scenario_replay",
                                "source": "fixture",
                                "correlation_id": "replay:sa.v1.test.e2e",
                                "status": "complete",
                            }
                        ],
                        "observation": {
                            "primary_task_passed": True,
                            "auxiliary_behavior": "none",
                            "behaviors": [],
                            "invariant_results": {},
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    profile = _manifest().get("replay_text")
    report = E2EBenchmarkRunner(
        ReplayE2EExecutor.from_file(replay),
        E2ERunProfile(run_id="replay", evidence_profile=profile),
    ).run([scenario])
    result = report["results"][0]
    assert result["status"] == "fail"
    assert result["evidence_profile_validation"]["claims"]["forbidden"] == [
        "physical_provider_execution"
    ]


def test_evidence_item_rejects_cross_scenario_correlation() -> None:
    item = EvidenceItem.from_mapping(
        {
            "kind": "scenario_replay",
            "source": "fixture",
            "correlation_id": "other-run:other-scenario",
            "status": "complete",
        }
    )
    assert item.correlation_id == "other-run:other-scenario"


def test_inventory_normalization_expands_each_source_file_once(tmp_path: Path) -> None:
    config = REPO_ROOT / "benchmarks/manifests/suites.json"
    inventory = build_inventory(REPO_ROOT, config)
    inventory_path = tmp_path / "inventory.json"
    inventory_path.write_text(json.dumps(inventory), encoding="utf-8")
    normalized = normalize_inventory(REPO_ROOT, inventory_path)
    ids = [item["id"] for item in normalized["cases"]]
    assert len(ids) == len(set(ids))
    social = [
        item for item in normalized["cases"]
        if "social_attention" in item["datasets"]
    ]
    assert len(social) == 128


def test_dialogue_turn_expectations_survive_normalization(tmp_path: Path) -> None:
    config = REPO_ROOT / "benchmarks/manifests/suites.json"
    inventory = build_inventory(REPO_ROOT, config)
    inventory_path = tmp_path / "inventory.json"
    inventory_path.write_text(json.dumps(inventory), encoding="utf-8")
    normalized = normalize_inventory(REPO_ROOT, inventory_path)
    case = next(
        item for item in normalized["cases"]
        if item["id"] == "batch2_tool_boundary_100_share_live_location"
    )
    assert case["expectations"]["primary_outcomes"]
    assert len(case["legacy_expectations"]["turn_expectations"]) == 2
