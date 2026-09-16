from __future__ import annotations

from scripts.qualification.generalization_relations import evaluate_generalization_spec
from shared.chromie_contracts.semantic_capability import realize_semantic_capability_args
from tests.test_semantic_capability_facade import PROVIDER_SCHEMA, SEMANTIC_FACADE


def test_relation_checker_distinguishes_semantic_invariance_from_provider_realization() -> None:
    reversed_facade = {
        **SEMANTIC_FACADE,
        "provider_realizations": {
            "yaw_radps": {
                **SEMANTIC_FACADE["provider_realizations"]["yaw_radps"],
                "positive_direction": "right",
                "negative_direction": "left",
            }
        },
    }
    semantic_plan = {
        "capability_id": "soridormi.turn_in_place",
        "args": {"direction": "left", "duration_s": 2.0},
    }
    default_provider = realize_semantic_capability_args(
        semantic_plan["args"],
        facade=SEMANTIC_FACADE,
        provider_input_schema=PROVIDER_SCHEMA,
        capability_id="default-frame",
    )
    reversed_provider = realize_semantic_capability_args(
        semantic_plan["args"],
        facade=reversed_facade,
        provider_input_schema=PROVIDER_SCHEMA,
        capability_id="reversed-frame",
    )
    report = evaluate_generalization_spec({
        "observations": {
            "default": {"plan": semantic_plan, "provider": default_provider},
            "reversed": {"plan": semantic_plan, "provider": reversed_provider},
        },
        "relations": [{
            "id": "provider-frame-invariance",
            "left": "default",
            "right": "reversed",
            "transformation": "reverse provider yaw sign convention",
            "invariants": ["plan"],
            "deltas": ["provider.yaw_radps"],
        }],
    })
    assert report["passed"] is True


def test_relation_checker_allows_paraphrase_source_span_change_but_requires_semantics() -> None:
    report = evaluate_generalization_spec({
        "observations": {
            "en-a": {
                "responsibility": {"outcome": "turn left", "output_mode": "body_action"},
                "source": {"start": "t1", "end": "t2"},
            },
            "en-b": {
                "responsibility": {"outcome": "turn left", "output_mode": "body_action"},
                "source": {"start": "t4", "end": "t6"},
            },
        },
        "relations": [{
            "id": "paraphrase-meaning",
            "left": "en-a",
            "right": "en-b",
            "transformation": "paraphrase with a different immutable source span",
            "invariants": ["responsibility"],
            "deltas": ["source"],
        }],
    })
    assert report["passed"] is True


def test_relation_checker_requires_controlled_semantic_delta() -> None:
    report = evaluate_generalization_spec({
        "observations": {
            "left": {"plan": {"capability": "turn", "direction": "left"}},
            "right": {"plan": {"capability": "turn", "direction": "right"}},
        },
        "relations": [{
            "id": "direction-mutation",
            "left": "left",
            "right": "right",
            "transformation": "left -> right",
            "invariants": ["plan.capability"],
            "deltas": ["plan.direction"],
            "left_assertions": {"plan.direction": "left"},
            "right_assertions": {"plan.direction": "right"},
        }],
    })
    assert report["passed"] is True


def test_relation_checker_fails_independent_drift_even_if_both_cases_exist() -> None:
    report = evaluate_generalization_spec({
        "observations": {
            "a": {"plan": {"capability": "turn", "direction": "left"}},
            "b": {"plan": {"capability": "walk", "direction": "right"}},
        },
        "relations": [{
            "id": "bad-direction-mutation",
            "left": "a",
            "right": "b",
            "invariants": ["plan.capability"],
            "deltas": ["plan.direction"],
        }],
    })
    assert report["passed"] is False
    assert report["failed_relation_ids"] == ["bad-direction-mutation"]
