from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from benchmarks.contracts import (
    ContractError,
    NormalizedScenario,
    OraclePolicy,
    SourceReference,
)

ID_KEYS = ("id", "scenario_id", "case_id", "test_id", "name")
INPUT_KEYS = (
    "inputs", "input", "user_input", "user_text", "text", "utterance", "query", "request",
    "messages", "turns", "conversation",
)
CONTEXT_KEYS = (
    "context", "history", "state", "profile", "mind_profile", "style", "mode",
    "available_capabilities", "capabilities", "recent_evidence", "metadata",
)
EXPECTATION_KEYS = (
    "expected", "expect", "expectations", "expected_output", "expected_result",
    "expected_plan", "assertions", "checks",
)
PRIMARY_KEYS = ("primary_outcome", "primary_expectation", "acceptable_outcomes")
AUXILIARY_KEYS = ("acceptable_auxiliary", "acceptable_auxiliary_behavior", "allowed_auxiliary")
FORBIDDEN_KEYS = ("forbidden", "forbidden_behavior", "forbidden_behaviors")
INVARIANT_KEYS = ("invariants", "required_invariants")
DISTRIBUTION_KEYS = ("distribution_observations", "distribution_expectations")
RUBRIC_KEYS = ("review_rubric", "rubric", "qualitative_review")
ORACLE_KEYS = ("oracle_policy", "oracle")



_RETIRED_SEMANTIC_EXPECTATION_KEYS = frozenset({"expected_route", "expected_intent"})
_RETIRED_NESTED_EXPECTATION_KEYS = frozenset({"route", "intent", "route_decision"})


def _reject_retired_semantic_expectations(item: Mapping[str, Any]) -> None:
    retired = sorted(_RETIRED_SEMANTIC_EXPECTATION_KEYS.intersection(item))
    expected = item.get("expected")
    if isinstance(expected, Mapping):
        retired.extend(
            f"expected.{key}"
            for key in sorted(_RETIRED_NESTED_EXPECTATION_KEYS.intersection(expected))
        )
    if retired:
        raise ContractError(
            "legacy scenario uses retired route/intent expectations: "
            + ", ".join(retired)
            + "; migrate the case to Responsibility/Goal/Plan/Capability/Evidence assertions"
        )

@dataclass(frozen=True)
class AdapterContext:
    source_path: str
    layer: str
    datasets: tuple[str, ...]
    evidence_requirements: tuple[str, ...]


def _first(mapping: Mapping[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        if key in mapping:
            return mapping[key]
    return None


def _items(payload: Any) -> Iterable[tuple[int | None, Any]]:
    if isinstance(payload, list):
        yield from enumerate(payload)
        return
    if isinstance(payload, Mapping):
        for key in ("scenarios", "cases", "tests", "examples", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                yield from enumerate(value)
                return
    yield None, payload


def _slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9._-]+", "-", value.lower()).strip("-._")
    if not normalized:
        raise ContractError("scenario id cannot be normalized")
    return normalized


def _stable_id(context: AdapterContext, item: Any, index: int | None) -> tuple[str, str | None]:
    declared: str | None = None
    if isinstance(item, Mapping):
        raw = _first(item, ID_KEYS)
        if isinstance(raw, str) and raw.strip():
            declared = raw.strip()
    if declared:
        return _slug(declared), declared
    canonical = json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]
    stem = _slug(Path(context.source_path).stem)
    suffix = str(index) if index is not None else "single"
    return f"legacy.{stem}.{suffix}.{digest}", None


def _as_mapping(value: Any, *, fallback_key: str) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if value is None:
        return {}
    return {fallback_key: value}


def _as_strings(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            if isinstance(item, str):
                result.append(item)
            elif isinstance(item, Mapping):
                result.append(json.dumps(item, ensure_ascii=False, sort_keys=True))
            else:
                result.append(str(item))
        return result
    if isinstance(value, Mapping):
        return [json.dumps(value, ensure_ascii=False, sort_keys=True)]
    return [str(value)]


def _extract_inputs(item: Mapping[str, Any]) -> dict[str, Any]:
    explicit = item.get("inputs")
    if isinstance(explicit, Mapping) and explicit:
        return dict(explicit)
    for key in INPUT_KEYS[1:]:
        if key in item:
            return _as_mapping(item[key], fallback_key=key)
    fixture_keys = (
        "semantic_args", "provider_backend", "skill_id", "timing",
        "request_payload", "response_payload", "fixture",
    )
    if any(key in item for key in fixture_keys):
        return {"fixture": dict(item)}
    raise ContractError("legacy scenario has no recognizable input field")


def _extract_context(item: Mapping[str, Any]) -> dict[str, Any]:
    explicit = item.get("context")
    result = dict(explicit) if isinstance(explicit, Mapping) else {}
    for key in CONTEXT_KEYS:
        if key == "context" or key not in item:
            continue
        result.setdefault(key, item[key])
    return result


def _extract_legacy_expectations(item: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in EXPECTATION_KEYS:
        if key in item:
            result[key] = item[key]
    turns = item.get("turns")
    if isinstance(turns, list):
        turn_expectations: list[dict[str, Any]] = []
        for index, turn in enumerate(turns):
            if not isinstance(turn, Mapping) or "expect" not in turn:
                continue
            turn_expectations.append(
                {
                    "turn_id": turn.get("id", index),
                    "expect": turn["expect"],
                }
            )
        if turn_expectations:
            result["turn_expectations"] = turn_expectations
    return result


class LegacyJsonAdapter:
    name = "legacy_json_v1"

    def normalize(self, payload: Any, context: AdapterContext) -> list[NormalizedScenario]:
        normalized: list[NormalizedScenario] = []
        inherited_invariants: list[str] = []
        if isinstance(payload, Mapping):
            inherited_invariants = _as_strings(_first(payload, INVARIANT_KEYS))
        for index, raw_item in _items(payload):
            if not isinstance(raw_item, Mapping):
                raise ContractError(
                    f"{context.source_path}[{index}] must be an object, got {type(raw_item).__name__}"
                )
            item = dict(raw_item)
            _reject_retired_semantic_expectations(item)
            scenario_id, source_id = _stable_id(context, item, index)
            primary = _as_strings(_first(item, PRIMARY_KEYS))
            explicit_primary = bool(primary)
            auxiliary = _as_strings(_first(item, AUXILIARY_KEYS))
            forbidden = _as_strings(_first(item, FORBIDDEN_KEYS))
            invariants = _as_strings(_first(item, INVARIANT_KEYS)) or list(inherited_invariants)
            distribution = _as_strings(_first(item, DISTRIBUTION_KEYS))
            legacy = _extract_legacy_expectations(item)
            if not primary and not invariants and legacy:
                primary = ["Preserve the source scenario's declared semantic expectation"]
            capabilities = item.get("capabilities")
            if not isinstance(capabilities, (str, list, tuple)):
                capabilities = []
            rubric = _first(item, RUBRIC_KEYS)
            explicit_oracle = _first(item, ORACLE_KEYS)
            if explicit_oracle is not None and not isinstance(explicit_oracle, Mapping):
                raise ContractError(
                    f"{context.source_path}[{index}].oracle_policy must be an object"
                )
            if isinstance(explicit_oracle, Mapping):
                oracle_policy: OraclePolicy | Mapping[str, Any] = explicit_oracle
            else:
                deterministic_sources: list[str] = []
                if legacy:
                    deterministic_sources.append("legacy_expectations")
                if invariants:
                    deterministic_sources.append("invariants")
                if forbidden:
                    deterministic_sources.append("forbidden_behaviors")
                dimensions: list[str] = []
                if isinstance(rubric, Mapping):
                    dimensions = _as_strings(rubric.get("dimensions"))
                if explicit_primary and not dimensions:
                    dimensions = ["primary_outcome"]
                if deterministic_sources and dimensions:
                    mode = "hybrid"
                elif dimensions:
                    mode = "semantic_review"
                else:
                    mode = "deterministic"
                    if not deterministic_sources:
                        deterministic_sources.append("primary_task_observation")
                oracle_policy = OraclePolicy.create(
                    mode=mode,
                    deterministic_sources=deterministic_sources,
                    semantic_dimensions=dimensions,
                )
            normalized.append(
                NormalizedScenario.create(
                    id=scenario_id,
                    layer=context.layer,
                    datasets=context.datasets,
                    source=SourceReference(
                        path=context.source_path,
                        adapter=self.name,
                        source_index=index,
                        source_id=source_id,
                    ),
                    inputs=_extract_inputs(item),
                    context=_extract_context(item),
                    capabilities=capabilities,
                    primary_outcomes=primary,
                    acceptable_auxiliary=auxiliary,
                    forbidden_behaviors=forbidden,
                    invariants=invariants,
                    distribution_observations=distribution,
                    evidence_requirements=context.evidence_requirements,
                    review_rubric=rubric if isinstance(rubric, Mapping) else {},
                    legacy_expectations=legacy,
                    oracle_policy=oracle_policy,
                )
            )
        return normalized


def normalize_payload(
    payload: Any,
    *,
    source_path: str,
    layer: str,
    datasets: Iterable[str],
    evidence_requirements: Iterable[str] = ("static",),
) -> list[dict[str, Any]]:
    context = AdapterContext(
        source_path=source_path,
        layer=layer,
        datasets=tuple(datasets),
        evidence_requirements=tuple(evidence_requirements),
    )
    return [item.to_dict() for item in LegacyJsonAdapter().normalize(payload, context)]


def normalize_json_file(
    path: Path,
    *,
    repo_root: Path,
    layer: str,
    datasets: Iterable[str],
    evidence_requirements: Iterable[str] = ("static",),
) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot load {path}: {exc}") from exc
    try:
        source_path = path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError as exc:
        raise ContractError(f"source path is outside repository: {path}") from exc
    return normalize_payload(
        payload,
        source_path=source_path,
        layer=layer,
        datasets=datasets,
        evidence_requirements=evidence_requirements,
    )
