from __future__ import annotations

from typing import Any, Mapping

from benchmarks.contracts import ContractError, OraclePolicy


def oracle_policy_for_scenario(scenario: Mapping[str, Any]) -> OraclePolicy:
    """Return the explicit or backwards-compatible oracle policy.

    Existing normalized scenarios remain runnable. New normalization emits an
    explicit policy so deterministic fixtures and semantic review are not
    conflated.
    """

    raw = scenario.get("oracle_policy")
    if raw is not None:
        if not isinstance(raw, Mapping):
            raise ContractError("scenario.oracle_policy must be an object")
        return OraclePolicy.from_mapping(raw)

    expectations = scenario.get("expectations")
    if not isinstance(expectations, Mapping):
        expectations = {}
    review_rubric = scenario.get("review_rubric")
    if not isinstance(review_rubric, Mapping):
        review_rubric = {}
    legacy = scenario.get("legacy_expectations")
    if not isinstance(legacy, Mapping):
        legacy = {}
    return OraclePolicy.derive(
        primary_outcomes=tuple(expectations.get("primary_outcomes") or ()),
        forbidden_behaviors=tuple(expectations.get("forbidden_behaviors") or ()),
        invariants=tuple(expectations.get("invariants") or ()),
        review_rubric=review_rubric,
        legacy_expectations=legacy,
    )
