from __future__ import annotations

import json
from pathlib import Path

from benchmarks.adapters.legacy_json import normalize_json_file
from benchmarks.e2e.first_party import FirstPartyAdapterManifest, FirstPartyE2EExecutor
from benchmarks.e2e.runner import E2EBenchmarkRunner, E2ERunProfile
from benchmarks.e2e.profiles import EvidenceProfileManifest
from benchmarks.runners.core import select_cases
from benchmarks.social_attention.qualification import (
    build_qualification_report,
    load_manifest,
)


ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "benchmarks/datasets/social_attention/cases.json"
QUALIFICATION_MANIFEST = (
    ROOT / "benchmarks/manifests/social_attention_qualification_v1.json"
)


def _cases() -> list[dict]:
    return normalize_json_file(
        DATASET,
        repo_root=ROOT,
        layer="integration",
        datasets=("social_attention",),
        evidence_requirements=("static", "live_model"),
    )


def test_social_attention_selectors_use_contract_metadata() -> None:
    cases = _cases()
    assert len(select_cases(cases, modes={"off"})) == 8
    assert len(select_cases(cases, modes={"report_only"})) == 8
    assert len(select_cases(cases, styles={"courteous"})) == 32
    assert len(select_cases(cases, cohorts={"tool_use"})) == 8
    assert len(
        select_cases(cases, forbidden_behaviors={"user_stillness_violation"})
    ) == 10


def test_e2e_run_profile_retains_effective_runtime_identity() -> None:
    evidence_profile = EvidenceProfileManifest.from_file(
        ROOT / "benchmarks/manifests/e2e_evidence_profiles.json"
    ).get("live_service_text")
    run = E2ERunProfile(
        run_id="baseline",
        evidence_profile=evidence_profile,
        model="qwen3:4b",
        effective_model_topology={
            "fast_planner": "qwen3:4b",
            "social_attention": "qwen3:4b",
        },
        mind_profile="owner-profile-v1",
        social_interaction_style="courteous",
        social_attention_mode="on",
        semantic_authority_owner="goal_driven_cognitive_core",
        runtime_topology="launcher-effective-compact-cognition",
        sample_count=1,
    ).to_dict()
    assert run["effective_model_topology"]["fast_planner"] == "qwen3:4b"
    assert run["semantic_authority_owner"] == "goal_driven_cognitive_core"
    assert run["social_attention_mode"] == "on"


def test_e2e_run_profile_rejects_unknown_social_attention_mode() -> None:
    evidence_profile = EvidenceProfileManifest.from_file(
        ROOT / "benchmarks/manifests/e2e_evidence_profiles.json"
    ).get("live_service_text")
    try:
        E2ERunProfile(
            run_id="invalid-mode",
            evidence_profile=evidence_profile,
            social_attention_mode="mixed",
        )
    except ValueError as exc:
        assert "social_attention_mode" in str(exc)
    else:
        raise AssertionError("unknown Social Attention mode must fail closed")


def test_first_party_adapter_manifest_has_no_embedded_endpoint() -> None:
    manifest = FirstPartyAdapterManifest.from_file(
        ROOT / "benchmarks/manifests/e2e_adapters.json"
    )
    profile = manifest.get("live_service_text")
    assert profile.url_env == "CHROMIE_BENCHMARK_LIVE_SERVICE_URL"
    assert profile.callable_env == "CHROMIE_BENCHMARK_LIVE_SERVICE_CALLABLE"
    assert "http" not in profile.description.casefold()



def test_first_party_callable_executes_unchanged_e2e_contract(
    tmp_path: Path, monkeypatch
) -> None:
    module = tmp_path / "qualification_harness.py"
    module.write_text(
        """
def invoke(request):
    scenario_id = request["scenario"]["id"]
    correlation_id = request["run"]["correlation_id"]
    evidence = [
        {"kind": kind, "source": "harness", "correlation_id": correlation_id, "status": "complete"}
        for kind in ("model_identity", "prompt_revision", "model_output")
    ]
    return {
        "schema_version": 1,
        "scenario_id": scenario_id,
        "correlation_id": correlation_id,
        "execution_state": "completed",
        "execution_claims": ["model_output"],
        "timing": {
            "input_received_ms": 0,
            "primary_response_started_ms": 10,
            "terminal_ms": 20
        },
        "evidence": evidence,
        "observation": {
            "primary_task_passed": True,
            "auxiliary_behavior": "none",
            "behaviors": [],
            "invariant_results": {
                name: True
                for name in request["scenario"]["expectations"]["invariants"]
            },
            "social_attention_lifecycle": {
                "proposal_state": "none",
                "materialization_state": "not_applicable",
                "provider_acceptance_state": "not_applicable",
                "provider_completion_state": "not_applicable",
                "safe_idle_state": "not_applicable"
            }
        }
    }
""",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    adapter_profile = FirstPartyAdapterManifest.from_file(
        ROOT / "benchmarks/manifests/e2e_adapters.json"
    ).get("live_model_text")
    evidence_profile = EvidenceProfileManifest.from_file(
        ROOT / "benchmarks/manifests/e2e_evidence_profiles.json"
    ).get("live_model_text")
    executor = FirstPartyE2EExecutor.from_environment(
        adapter_profile,
        timeout_s=5,
        artifact_root=tmp_path / "artifacts",
        environment={
            "CHROMIE_BENCHMARK_LIVE_MODEL_CALLABLE": "qualification_harness:invoke"
        },
    )
    case = _cases()[0]
    report = E2EBenchmarkRunner(
        executor,
        E2ERunProfile(run_id="callable", evidence_profile=evidence_profile),
    ).run([case])
    assert report["summary"]["review"] == 1
    assert report["results"][0]["evaluation"]["deterministic_status"] == "pass"
    assert report["results"][0]["evaluation"]["semantic_review_status"] == "pending"
    assert report["summary"]["evidence_complete"] == 1
    assert report["summary"]["social_attention_lifecycle"]["proposal_state"] == {
        "none": 1
    }

def _passing_e2e_reports(cases: list[dict]) -> list[dict]:
    grouped: dict[tuple[str, str], list[dict]] = {}
    for case in cases:
        metadata = case["context"]["metadata"]
        grouped.setdefault((metadata["mode"], metadata["style"]), []).append(case)

    reports = []
    for (mode, style), scoped_cases in sorted(grouped.items()):
        results = []
        for case in scoped_cases:
            forbidden = set(case["expectations"]["forbidden_behaviors"])
            if mode == "off":
                lifecycle = {
                    "proposal_state": "none",
                    "materialization_state": "not_applicable",
                    "provider_acceptance_state": "not_applicable",
                    "provider_completion_state": "not_applicable",
                    "safe_idle_state": "not_applicable",
                }
            elif mode == "report_only" or "user_stillness_violation" in forbidden:
                lifecycle = {
                    "proposal_state": "proposed" if mode == "report_only" else "none",
                    "materialization_state": "rejected",
                    "provider_acceptance_state": "not_applicable",
                    "provider_completion_state": "not_applicable",
                    "safe_idle_state": "not_applicable",
                }
            else:
                lifecycle = {
                    "proposal_state": "proposed",
                    "materialization_state": "accepted",
                    "provider_acceptance_state": "accepted",
                    "provider_completion_state": "completed",
                    "safe_idle_state": "not_applicable",
                }
            results.append(
                {
                    "scenario_id": case["id"],
                    "status": "pass",
                    "evaluation": {"forbidden_behavior_hits": []},
                    "invariant_results": [
                        {"name": name, "passed": True, "detail": None}
                        for name in case["expectations"]["invariants"]
                    ],
                    "observations": {"social_attention_lifecycle": lifecycle},
                }
            )
        reports.append(
            {
                "schema_version": 1,
                "run": {
                    "run_id": f"baseline-{mode}-{style}",
                    "evidence_profile": "live_service_text",
                    "model": "qwen3:4b",
                    "code_revision": "deadbeef",
                    "prompt_revision": "planner-activity-prompt-v1",
                    "provider_revision": "provider-v1",
                    "hardware_profile": "rtx5090",
                    "effective_model_topology": {"fast_planner": "qwen3:4b"},
                    "mind_profile": f"owner-profile-{style}-v1",
                    "social_interaction_style": style,
                    "social_attention_mode": mode,
                    "semantic_authority_owner": "goal_driven_cognitive_core",
                    "runtime_topology": "launcher-effective-compact-cognition",
                    "sample_count": 1,
                },
                "results": results,
            }
        )
    return reports


def test_complete_contract_evidence_passes_deterministic_hard_gates() -> None:
    cases = _cases()
    reports = _passing_e2e_reports(cases)
    report = build_qualification_report(
        manifest=load_manifest(QUALIFICATION_MANIFEST),
        cases=cases,
        e2e_reports=reports,
    )
    assert report["summary"]["social_case_count"] == 128
    assert report["summary"]["reported_result_count"] == 128
    assert report["summary"]["run_count"] == 11
    assert report["summary"]["hard_gates_failed"] == 0
    assert report["identity_validation"]["complete"] is True
    assert report["scope_validation"]["complete"] is True
    assert report["coverage_validation"]["complete"] is True
    assert report["qualification"]["deterministic_hard_gates_passed"] is True
    assert report["qualification"]["release_qualified"] is False
    assert report["qualification"]["state"] == "human_review_required"


def test_missing_off_mode_lifecycle_fails_closed() -> None:
    cases = _cases()
    reports = _passing_e2e_reports(cases)
    target = next(
        item
        for report in reports
        for item in report["results"]
        if item["scenario_id"] == "sa.v1.modes.off_greeting"
    )
    target["observations"]["social_attention_lifecycle"] = {}
    report = build_qualification_report(
        manifest=load_manifest(QUALIFICATION_MANIFEST),
        cases=cases,
        e2e_reports=reports,
    )
    gate = next(item for item in report["hard_gates"] if item["id"] == "off_mode_isolation")
    assert gate["passed"] is False
    assert report["qualification"]["state"] == "not_eligible"


def test_mixed_mode_or_style_report_is_rejected_as_scope_drift() -> None:
    cases = _cases()
    reports = _passing_e2e_reports(cases)
    reports[0]["run"]["social_attention_mode"] = "on"
    report = build_qualification_report(
        manifest=load_manifest(QUALIFICATION_MANIFEST),
        cases=cases,
        e2e_reports=reports,
    )
    assert report["scope_validation"]["complete"] is False
    assert any(error.startswith("mode_mismatch:") for error in report["scope_validation"]["errors"])
    assert report["qualification"]["state"] == "not_eligible"


def test_missing_slice_fails_complete_baseline_coverage() -> None:
    cases = _cases()
    reports = _passing_e2e_reports(cases)[:-1]
    report = build_qualification_report(
        manifest=load_manifest(QUALIFICATION_MANIFEST),
        cases=cases,
        e2e_reports=reports,
    )
    assert report["coverage_validation"]["complete"] is False
    assert report["coverage_validation"]["missing_scenario_results"]
    assert report["qualification"]["state"] == "not_eligible"
