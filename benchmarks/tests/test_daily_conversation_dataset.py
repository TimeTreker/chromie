from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
import sys

from benchmarks.adapters.legacy_json import normalize_json_file
from benchmarks.inventory.core import load_config
from scripts.run_daily_conversation_benchmark import _scenario_paths, run


ROOT = Path(__file__).resolve().parents[2]
DATASET_ROOT = ROOT / "benchmarks/datasets/daily_conversation"
DATASET_MANIFEST = DATASET_ROOT / "dataset.json"
SUITES_PATH = ROOT / "benchmarks/manifests/suites.json"


def _load() -> dict:
    manifest = json.loads(DATASET_MANIFEST.read_text(encoding="utf-8"))
    scenarios = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in _scenario_paths(DATASET_ROOT)
    ]
    return {**manifest, "scenarios": scenarios}


def test_daily_conversation_dataset_meets_declared_coverage() -> None:
    dataset = _load()
    scenarios = dataset["scenarios"]
    coverage = dataset["coverage_contract"]

    assert dataset["dataset_id"] == "chromie.daily_conversation.v1"
    assert len(scenarios) == coverage["expected_scenarios"] == 120
    assert len(scenarios) >= coverage["minimum_scenarios"] == 100
    assert Counter(item["metadata"]["cohort"] for item in scenarios) == coverage["cohorts"]
    assert Counter(item["metadata"]["language"] for item in scenarios) == coverage["languages"]
    assert coverage["canonical_response_strings"] == 0


def test_daily_conversation_cases_are_unique_chromie_semantic_assets() -> None:
    scenarios = _load()["scenarios"]
    ids = [item["id"] for item in scenarios]
    input_contracts = [
        json.dumps(item["inputs"], ensure_ascii=False, sort_keys=True)
        for item in scenarios
    ]

    assert len(ids) == len(set(ids))
    assert len(input_contracts) == len(set(input_contracts))
    for item in scenarios:
        assert item["context"]["authoring"]["canonical_response_provided"] is False
        assert item["context"]["authoring"]["runtime_policy_authority"] is False
        assert item["context"]["chromie_contract_basis"] == [
            "project_charter",
            "human_like_interaction_contract",
            "goal_driven_cognitive_architecture",
            "owner_approved_mind_profile",
        ]
        assert item["oracle_policy"]["mode"] == "hybrid"
        assert item["oracle_policy"]["semantic_blocking"] is True
        assert item["oracle_policy"]["semantic_dimensions"]
        assert item["review_rubric"]["judge_meaning_not_exact_wording"] is True
        assert item["review_rubric"]["chromie_specific"] is True
        assert item["primary_outcome"] == item["description"]
        assert "expected_response" not in item
        assert "exact_response" not in item
        assert "required_response" not in item


def test_daily_conversation_stores_exactly_one_scenario_per_file() -> None:
    paths = _scenario_paths(DATASET_ROOT)

    assert len(paths) == 120
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(payload, dict)
        assert payload.get("id")
        assert "scenarios" not in payload
        assert "cases" not in payload
        assert path.parent.name == payload["metadata"]["cohort"]
        assert path.stem == payload["id"].rsplit(".", 1)[-1]


def test_daily_conversation_dataset_normalizes_through_common_contract() -> None:
    normalized = []
    for path in _scenario_paths(DATASET_ROOT):
        normalized.extend(
            normalize_json_file(
                path,
                repo_root=ROOT,
                layer="integration",
                datasets=("daily_conversation",),
                evidence_requirements=("static", "live_model"),
            )
        )

    assert len(normalized) == 120
    assert all(item["datasets"] == ["daily_conversation"] for item in normalized)
    assert all(item["oracle_policy"]["mode"] == "hybrid" for item in normalized)
    assert all(item["expectations"]["primary_outcomes"] for item in normalized)
    assert all(item["review_rubric"]["dimensions"] for item in normalized)


def test_daily_conversation_source_is_registered_once() -> None:
    _, rules = load_config(SUITES_PATH)
    sources = [item for item in rules if item.name == "daily_conversation_v1"]

    assert len(sources) == 1
    source = sources[0]
    assert source.path == "benchmarks/datasets/daily_conversation"
    assert source.glob == "scenarios/**/*.json"
    assert source.layer == "integration"
    assert source.datasets == ("daily_conversation",)
    assert source.evidence_levels == ("static", "live_model")


def test_daily_conversation_runner_discovers_added_json_files(tmp_path: Path) -> None:
    (tmp_path / "scenarios/family").mkdir(parents=True)
    first = tmp_path / "scenarios/first.json"
    second = tmp_path / "scenarios/family/second.json"
    ignored = tmp_path / "scenarios/notes.md"
    first.write_text("{}", encoding="utf-8")
    second.write_text("{}", encoding="utf-8")
    ignored.write_text("not scenario data", encoding="utf-8")

    assert _scenario_paths(tmp_path) == sorted([first, second])


def test_daily_conversation_runner_retains_output_for_semantic_review(
    tmp_path: Path,
) -> None:
    adapter = tmp_path / "adapter.py"
    adapter.write_text(
        """import json, sys
request = json.load(sys.stdin)
scenario = request["scenario"]
invariants = scenario["expectations"]["invariants"]
print(json.dumps({
    "scenario_id": scenario["id"],
    "primary_outcome": "Good morning! I'm right here.",
    "invariant_results": {name: True for name in invariants},
    "evidence": [{"kind": "delivered_text", "text": "Good morning! I'm right here."}],
}))
""",
        encoding="utf-8",
    )
    output_dir = tmp_path / "result"

    status = run(
        [
            "--repo-root",
            str(ROOT),
            "--command",
            f"{sys.executable} {adapter}",
            "--model",
            "test-candidate",
            "--prompt-revision",
            "test-prompt",
            "--id",
            "daily.v1.greetings_presence.direct_morning",
            "--output-dir",
            str(output_dir),
        ]
    )

    assert status == 0
    report = json.loads((output_dir / "run.json").read_text(encoding="utf-8"))
    assert report["summary"] == {
        "total": 1,
        "pass": 0,
        "fail": 0,
        "review": 1,
        "error": 0,
    }
    bundle = json.loads(
        (output_dir / "review/review-bundle.json").read_text(encoding="utf-8")
    )
    assert bundle["scenarios"][0]["execution_result"]["observations"][
        "primary_outcome"
    ] == "Good morning! I'm right here."
    assert (output_dir / "review/review-template.json").exists()
