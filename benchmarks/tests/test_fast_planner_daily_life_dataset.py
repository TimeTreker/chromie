from __future__ import annotations

import asyncio
import json

import pytest

from benchmarks.datasets.fast_planner_daily_life.qualification import (
    DATASET_ROOT,
    PRODUCTION_TRANSACTION_FILES,
    adjudicate_batch,
    canonical_primary_result_accepted,
    load_cases,
    production_source_identity,
    scenario_paths,
    validate_dataset,
)
from shared.chromie_contracts.plan import CanonicalPlan


def test_fast_planner_daily_life_corpus_is_current_production_shaped() -> None:
    assert len(scenario_paths()) == 204
    cases = load_cases()
    assert len(cases) == 204
    assert {case["input"]["language"] for case in cases} == {"en-US", "zh-CN"}
    assert {case["input"]["runtime_variant"] for case in cases} == {
        "canonical_primary",
        "canonical_reentry",
        "streaming_advance",
    }

    summary = validate_dataset()
    assert summary["validated"] == 204
    assert summary["contrast_set_count"] == 51


def test_fast_planner_daily_life_stores_one_scenario_per_file() -> None:
    paths = scenario_paths()

    assert len(paths) == 204
    assert len({path.resolve() for path in paths}) == 204
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert path.stem == payload["id"]
        assert path.parent.name == payload["category"]
        assert path.parent.parent.name == payload["split"]
        assert "target" not in payload["input"]
        assert payload["review"]["review_status"] == (
            "mechanically_validated_dataset_candidate"
        )
        assert payload["review"]["author_model"] == "gpt-5.6-sol"
        assert payload["review"]["training_eligible"] is False
        assert payload["review"]["independent_semantic_review"] is False


def test_fast_planner_daily_life_manifest_matches_file_tree() -> None:
    manifest = json.loads((DATASET_ROOT / "dataset.json").read_text(encoding="utf-8"))

    assert manifest["coverage_contract"]["scenario_count"] == len(scenario_paths())
    assert manifest["dataset_id"] == "chromie.fast_planner_daily_life.v2"
    assert manifest["coverage_contract"]["contrast_set_count"] == 51
    assert manifest["coverage_contract"]["scenarios_per_contrast_set"] == 4
    assert manifest["asset_contract"]["path_pattern"] == (
        "scenarios/<split>/<category>/<scenario-id>.json"
    )
    assert manifest["coverage_contract"]["training_eligible"] is False
    assert manifest["coverage_contract"]["independent_semantic_review"] is False
    assert manifest["authoring"]["production_shape_valid"] is True
    assert manifest["authoring"]["qualification_prepare_allowed"] is True
    assert manifest["historical_invalidated_coverage_assessment"]["status"] == (
        "superseded_by_v2_design_capacity_corpus"
    )
    assert manifest["coverage_matrix"]["planner_required_capacities"] == 17
    assert manifest["coverage_matrix"]["capacity_cells"] == 51
    assert manifest["coverage_matrix"]["daily_life_families"] == 15
    assert "ability_classes" not in manifest["coverage_matrix"]
    assert manifest["historical_invalidated_coverage_assessment"]["observed_biases"] == {
        "frozen_catalog_capability_count": 5,
        "scenarios_with_no_required_capability": 832,
        "required_capability_mentions": {
            "chromie.reminder.create": 404,
            "chromie.weather.lookup": 206,
            "soridormi.look_at_person": 96,
            "soridormi.blink_eyes": 66,
            "soridormi.walk_forward": 60,
        },
        "responsibilities_without_material_bindings": 1328,
        "responsibility_count": 1984,
    }
    replacement = manifest["replacement_state_space_draft"]
    assert replacement["status"] == "authored_frozen_and_mechanically_validated"
    assert replacement["qualification_scope"] == (
        "fast_planner_first_then_deep_extension"
    )
    assert replacement["primary_coverage_unit"] == "planner_required_capacity"
    authority = replacement["authority_statement"]
    assert "Planner owns HOW" in authority["planner_owns"]
    assert "does not reinterpret provider-neutral WHAT" in authority[
        "planner_does_not_own"
    ]
    assert "docs/LLM_PROMPT_QUALIFICATION_METHOD.md section 7" in authority[
        "design_authorities"
    ]
    assert {
        item["owner"] for item in replacement["non_planner_responsibilities"]
    } == {
        "Goal Interpretation",
        "Goal Association",
        "Host and Cognitive Runtime",
        "Trusted Capability Runtime and providers",
        "Host deterministic control",
        "Soridormi",
        "Vocal and playback runtime",
    }
    entry_contracts = {
        item["id"]: item for item in replacement["entry_variant_contracts"]
    }
    assert set(entry_contracts) == {
        "streaming_advance",
        "canonical_primary",
        "canonical_reentry",
    }
    assert "canonical Goal identity" in entry_contracts["streaming_advance"][
        "not_representable_at_this_boundary"
    ]
    assert "Evidence admission or correlation" in entry_contracts[
        "canonical_reentry"
    ]["not_representable_at_this_boundary"]
    capacity_ids = {
        item["id"] for item in replacement["planner_required_capacities"]
    }
    assert capacity_ids == {
        "authoritative_scope_coverage_and_satisfaction",
        "direct_communicative_planning",
        "capability_grounding_and_non_substitution",
        "parameter_resolution_and_provenance",
        "work_topology_and_coordination",
        "per_goal_disposition_and_mixed_outcomes",
        "planner_uncertainty_and_limit_outcomes",
        "plan_relation_and_confirmation_proposal",
        "truthful_response_staging_and_deduplication",
        "retained_work_revision_and_no_replay",
        "evidence_reentry_interpretation",
        "temporal_readiness_planning",
        "fast_completion_or_how_escalation",
        "resource_contract_composition",
        "outcome_mode_fidelity",
        "optional_social_decoration",
        "atomic_plan_integrity_and_safe_alternatives",
    }
    for capacity in replacement["planner_required_capacities"]:
        assert capacity["applies_to"]
        assert capacity["obligation"]
        assert capacity["boundary_not_owned"]
        assert len(capacity["authority_refs"]) >= 3
    assert {
        item["id"] for item in replacement["deferred_deep_extension_capacities"]
    } == {
        "complex_multi_step_and_agent_skill_composition",
        "material_alternative_generation",
        "degraded_failed_or_unsafe_revision",
        "no_change_or_no_safe_plan",
    }
    coverage_gate = replacement["coverage_claim_gate"]
    assert len(coverage_gate["required_before_freeze"]) == 8
    assert len(coverage_gate["required_after_inference"]) == 4
    assert "target-blind" in coverage_gate["required_after_inference"][0]
    contrast_design = replacement["planned_minimum_contrast_design"]
    assert contrast_design["status"] == (
        "authored_frozen_same_model_semantic_review_pending"
    )
    assert contrast_design["case_count_floor"] == 204
    assert contrast_design["case_count_is_final_target"] is False
    contrast_rows = contrast_design["capacity_cells"]
    assert {row["capacity_id"] for row in contrast_rows} == capacity_ids
    assert len(contrast_rows) == len(capacity_ids) == 17
    for row in contrast_rows:
        assert row["changed_axis"]
        assert len(row["cells"]) == 3
        assert len({cell["daily_life_family"] for cell in row["cells"]}) == 3
        assert all(
            cell["entry_variant"] in entry_contracts for cell in row["cells"]
        )
    family_counts = {
        family: sum(
            cell["daily_life_family"] == family
            for row in contrast_rows
            for cell in row["cells"]
        )
        for family in replacement["daily_life_families"]
    }
    assert set(family_counts.values()).issubset({3, 4})
    assert sum(family_counts.values()) == 51
    assert len(replacement["daily_life_families"]) == 15
    assert set(replacement["planner_entry_variants"]) == {
        "streaming_advance",
        "canonical_primary",
        "canonical_reentry",
    }
    assert "missing_material_binding" in replacement["grounding_states"]
    assert "partial_support_without_partial_leakage" in replacement[
        "coordination_states"
    ]


def test_fast_planner_source_identity_covers_the_production_transaction() -> None:
    identity = production_source_identity()

    assert len(identity["production_files"]) == len(PRODUCTION_TRANSACTION_FILES)
    assert len(identity["production_files_sha256"]) == 64
    assert len(identity["production_tracked_diff_sha256"]) == 64
    assert identity["git_revision"]


def test_canonical_adjudication_distinguishes_advisory_result_from_fallback() -> None:
    terminal = CanonicalPlan(
        plan_id="plan-terminal",
        planner_tier="fast",
        disposition="respond",
        coverage="complete",
        confidence=1.0,
        response_text="Hello.",
        metadata={
            "authority": "advisory",
            "resolver": "fast_planner",
            "path_classification": "terminal",
        },
    )
    escalation = CanonicalPlan(
        plan_id="plan-escalation",
        planner_tier="fast",
        disposition="escalate",
        coverage="uncertain",
        confidence=0.5,
        escalation_reason="The common tier cannot cover the complete Goal.",
        metadata={
            "authority": "advisory",
            "resolver": "fast_planner",
            "path_classification": "semantic_escalation",
        },
    )
    rejected = escalation.model_copy(
        update={
            "metadata": {
                **escalation.metadata,
                "failure_class": "model_contract_invalid",
                "error_type": "PlannerDTOContractError",
            }
        }
    )

    assert canonical_primary_result_accepted(
        terminal, {"disposition": "respond"}
    )
    assert canonical_primary_result_accepted(
        escalation, {"disposition": "escalate"}
    )
    assert not canonical_primary_result_accepted(
        escalation, {"disposition": "execute"}
    )
    assert not canonical_primary_result_accepted(
        rejected, {"disposition": "escalate"}
    )


def test_adjudication_rejects_any_failed_candidate_process(tmp_path) -> None:
    (tmp_path / "batch-identity.json").write_text(
        json.dumps({"scenario_count": 2}),
        encoding="utf-8",
    )
    (tmp_path / "source-stability.json").write_text(
        json.dumps(
            {
                "stable": True,
                "completed_calls": 2,
                "successful_processes": 1,
                "timeouts": 0,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="batch is incomplete"):
        asyncio.run(adjudicate_batch(tmp_path))
