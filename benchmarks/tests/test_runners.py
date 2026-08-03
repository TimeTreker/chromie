from __future__ import annotations

import json
import sys
from pathlib import Path

from benchmarks.runners.core import BenchmarkRunner, select_cases
from benchmarks.runners.executors import CommandExecutor, ReplayExecutor
from benchmarks.runners.models import RunProfile


def _scenario(*, oracle_policy=None, **expectation_overrides):
    expectations = {
        "primary_outcomes": ["complete the requested task"],
        "acceptable_auxiliary": ["none"],
        "forbidden_behaviors": ["locomotion"],
        "invariants": ["explicit action has priority"],
        "distribution_observations": [],
    }
    expectations.update(expectation_overrides)
    return {
        "schema_version": 1,
        "id": "case.001",
        "layer": "module",
        "datasets": ["goal_interpretation"],
        "source": {"path": "case.json", "adapter": "test"},
        "inputs": {"user_text": "example"},
        "context": {},
        "capabilities": [],
        "expectations": expectations,
        "evidence_requirements": ["replay"],
        "review_rubric": {},
        "legacy_expectations": {},
        "oracle_policy": oracle_policy
        or {
            "mode": "deterministic",
            "deterministic_sources": ["replay_fixture", "invariants"],
            "semantic_dimensions": [],
            "semantic_blocking": True,
        },
    }


def test_replay_runner_passes_reported_boundaries() -> None:
    executor = ReplayExecutor(
        {
            "case.001": {
                "primary_task_passed": True,
                "behaviors": [],
                "invariant_results": {"explicit action has priority": True},
            }
        }
    )
    report = BenchmarkRunner(executor, RunProfile("replay", "replay")).run([_scenario()])
    assert report["summary"] == {"total": 1, "pass": 1, "fail": 0, "review": 0, "error": 0}


def test_missing_invariant_fails_closed() -> None:
    report = BenchmarkRunner(
        ReplayExecutor({"case.001": {"primary_task_passed": True}}),
        RunProfile("replay", "replay"),
    ).run([_scenario()])
    assert report["results"][0]["status"] == "fail"
    assert report["results"][0]["invariant_results"][0]["detail"] == "executor did not report invariant"


def test_forbidden_behavior_uses_declared_labels_not_user_text() -> None:
    report = BenchmarkRunner(
        ReplayExecutor(
            {
                "case.001": {
                    "primary_task_passed": True,
                    "behaviors": ["locomotion"],
                    "invariant_results": {"explicit action has priority": True},
                }
            }
        ),
        RunProfile("replay", "replay"),
    ).run([_scenario()])
    assert report["results"][0]["evaluation"]["forbidden_behavior_hits"] == ["locomotion"]
    assert report["results"][0]["status"] == "fail"


def test_subjective_primary_outcome_enters_review() -> None:
    report = BenchmarkRunner(
        ReplayExecutor(
            {
                "case.001": {
                    "invariant_results": {"explicit action has priority": True},
                }
            }
        ),
        RunProfile("replay", "replay"),
    ).run(
        [
            _scenario(
                oracle_policy={
                    "mode": "hybrid",
                    "deterministic_sources": ["invariants"],
                    "semantic_dimensions": ["primary_outcome", "naturalness"],
                    "semantic_blocking": True,
                }
            )
        ]
    )
    assert report["results"][0]["status"] == "review"
    assert report["results"][0]["evaluation"]["semantic_review_required"] is True


def test_semantic_oracle_cannot_be_short_circuited_by_executor_pass_flag() -> None:
    report = BenchmarkRunner(
        ReplayExecutor(
            {
                "case.001": {
                    "primary_task_passed": True,
                    "invariant_results": {"explicit action has priority": True},
                }
            }
        ),
        RunProfile("replay", "replay"),
    ).run(
        [
            _scenario(
                oracle_policy={
                    "mode": "hybrid",
                    "deterministic_sources": ["invariants"],
                    "semantic_dimensions": ["intent_understanding"],
                    "semantic_blocking": True,
                }
            )
        ]
    )
    assert report["results"][0]["status"] == "review"
    assert report["results"][0]["evaluation"]["deterministic_status"] == "pass"
    assert report["results"][0]["evaluation"]["semantic_review_status"] == "pending"


def test_command_executor_uses_json_boundary(tmp_path: Path) -> None:
    adapter = tmp_path / "adapter.py"
    adapter.write_text(
        """import json, sys\nrequest = json.load(sys.stdin)\nprint(json.dumps({\"scenario_id\": request[\"scenario\"][\"id\"], \"primary_task_passed\": True, \"invariant_results\": {\"explicit action has priority\": True}}))\n""",
        encoding="utf-8",
    )
    observation = CommandExecutor([sys.executable, str(adapter)]).execute(
        _scenario(), RunProfile("live_model", "live_model", model="test")
    )
    assert observation.scenario_id == "case.001"
    assert observation.primary_task_passed is True


def test_select_cases_filters_without_duplicating_scenarios() -> None:
    cases = [_scenario(), {**_scenario(), "id": "case.002", "layer": "integration", "datasets": ["interaction"]}]
    assert [item["id"] for item in select_cases(cases, layers={"integration"})] == ["case.002"]
    assert [item["id"] for item in select_cases(cases, datasets={"goal_interpretation"})] == ["case.001"]


def test_replay_file_contract(tmp_path: Path) -> None:
    path = tmp_path / "replay.json"
    path.write_text(json.dumps({"schema_version": 1, "observations": {"case.001": {}}}), encoding="utf-8")
    assert isinstance(ReplayExecutor.from_file(path), ReplayExecutor)
