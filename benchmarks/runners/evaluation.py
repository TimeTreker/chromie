from __future__ import annotations

from typing import Any, Mapping

from benchmarks.runners.models import ExecutionObservation, RunProfile
from benchmarks.runners.oracles import oracle_policy_for_scenario


def evaluate_boundaries(
    scenario: Mapping[str, Any], observation: ExecutionObservation, profile: RunProfile
) -> dict[str, Any]:
    """Evaluate only explicit machine-checkable boundaries.

    This function deliberately does not infer intent, naturalness, empathy, or
    style quality from user text. Those remain model-quality review dimensions.
    """

    expectations = scenario.get("expectations", {})
    oracle_policy = oracle_policy_for_scenario(scenario)
    required_invariants = tuple(expectations.get("invariants", []))
    reported = {item.name: item for item in observation.invariant_results}
    invariant_results: list[dict[str, Any]] = []
    for name in required_invariants:
        item = reported.get(name)
        if item is None:
            invariant_results.append(
                {"name": name, "passed": False, "detail": "executor did not report invariant"}
            )
        else:
            invariant_results.append(item.to_dict())

    forbidden = set(expectations.get("forbidden_behaviors", []))
    observed_behaviors = set(observation.behaviors)
    forbidden_hits = sorted(forbidden & observed_behaviors)
    for behavior in forbidden_hits:
        invariant_results.append(
            {
                "name": f"forbidden_behavior:{behavior}",
                "passed": False,
                "detail": "executor reported a forbidden behavior label",
            }
        )

    hard_failure = any(not item["passed"] for item in invariant_results)
    semantic_review_required = oracle_policy.mode in {"semantic_review", "hybrid"}
    if observation.primary_task_passed is False:
        hard_failure = True

    if hard_failure:
        status = "fail"
    elif semantic_review_required:
        status = "review"
    else:
        status = "pass"

    return {
        "schema_version": 1,
        "scenario_id": scenario["id"],
        "status": status,
        "run": profile.to_dict(),
        "observations": {
            "primary_task_passed": observation.primary_task_passed,
            "primary_outcome": observation.primary_outcome,
            "auxiliary_behavior": observation.auxiliary_behavior,
            "behaviors": list(observation.behaviors),
            "latency_ms": observation.latency_ms,
            "social_attention_lifecycle": dict(observation.social_attention_lifecycle),
            "evidence": list(observation.evidence),
        },
        "evaluation": {
            "semantic_review_required": semantic_review_required,
            "forbidden_behavior_hits": forbidden_hits,
            "oracle_policy": oracle_policy.to_dict(),
            "deterministic_status": "fail" if hard_failure else "pass",
            "semantic_review_status": (
                "pending" if semantic_review_required else "not_required"
            ),
        },
        "invariant_results": invariant_results,
        "artifacts": list(observation.artifacts),
    }
