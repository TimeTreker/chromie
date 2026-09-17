from __future__ import annotations

from agent.app.planner_fast_validation import (
    collapse_redundant_idempotent_read_activities,
)
from shared.chromie_contracts.plan import FastPlannerAdvanceModelOutput


def _output(*activities: dict) -> FastPlannerAdvanceModelOutput:
    return FastPlannerAdvanceModelOutput.model_validate(
        {
            "disposition": "execute",
            "coverage": "complete",
            "covered_responsibility_refs": ["r1"],
            "activities": list(activities),
            "continuations": [],
            "confidence": 1.0,
            "unresolved": [],
            "reason_summary": "Use the trusted read capability.",
        }
    )


def _activity(activity_id: str, *, location: str = "Chongqing") -> dict:
    return {
        "role": "capability",
        "activity_id": activity_id,
        "capability_id": "chromie.weather.lookup",
        "args": {"location": location},
        "argument_sources": {
            "location": {
                "source_start_token_ref": "t5",
                "source_end_token_ref": "t5",
            }
        },
        "timing": "sequential",
        "source_responsibility_refs": ["r1"],
        "reason_summary": "Read weather evidence.",
    }


def _capability(*, idempotent: bool = True, side_effect_free: bool = True) -> dict:
    return {
        "capability_id": "chromie.weather.lookup",
        "idempotent": idempotent,
        "side_effect_free": side_effect_free,
    }


def test_exact_duplicate_idempotent_reads_collapse_to_one_activity() -> None:
    output = _output(*[_activity(f"weather-{index}") for index in range(5)])

    normalized, repairs = collapse_redundant_idempotent_read_activities(
        output,
        capabilities=[_capability()],
    )

    assert [item.activity_id for item in normalized.activities] == ["weather-0"]
    assert len(repairs) == 4
    assert {item["removed_activity_id"] for item in repairs} == {
        "weather-1",
        "weather-2",
        "weather-3",
        "weather-4",
    }
    assert all(
        item["normalization"] == "duplicate_idempotent_read_activity_removed"
        for item in repairs
    )


def test_same_read_capability_with_different_arguments_is_not_collapsed() -> None:
    output = _output(
        _activity("weather-cq", location="Chongqing"),
        _activity("weather-bj", location="Beijing"),
    )

    normalized, repairs = collapse_redundant_idempotent_read_activities(
        output,
        capabilities=[_capability()],
    )

    assert [item.activity_id for item in normalized.activities] == [
        "weather-cq",
        "weather-bj",
    ]
    assert repairs == []


def test_effectful_or_non_idempotent_duplicates_are_never_collapsed() -> None:
    output = _output(_activity("first"), _activity("second"))

    for capability in (
        _capability(idempotent=False, side_effect_free=True),
        _capability(idempotent=True, side_effect_free=False),
    ):
        normalized, repairs = collapse_redundant_idempotent_read_activities(
            output,
            capabilities=[capability],
        )
        assert [item.activity_id for item in normalized.activities] == [
            "first",
            "second",
        ]
        assert repairs == []
