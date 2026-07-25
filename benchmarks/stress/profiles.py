from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping


class StressProfileError(ValueError):
    """Raised when a stress-workload manifest is malformed or policy-like."""


WORKLOAD_KINDS = frozenset(
    {
        "long_session",
        "repetition_cooldown",
        "interruption",
        "concurrency",
        "provider_degradation",
        "multi_user",
    }
)
SEQUENCE_STRATEGIES = frozenset({"round_robin", "seeded_shuffle", "repeat_each"})
OBSERVATION_DIMENSIONS = frozenset(
    {
        "sample_count",
        "status_distribution",
        "primary_task_success",
        "auxiliary_decision_distribution",
        "semantic_behavior_distribution",
        "duplicate_auxiliary_rate",
        "cooldown_violation_rate",
        "stillness_violation_rate",
        "safety_violation_rate",
        "execution_leakage_rate",
        "participant_isolation_violation_rate",
        "latency_distribution",
        "evidence_completeness",
        "session_drift",
    }
)
COMPARISON_DIMENSIONS = frozenset(
    {
        "model",
        "prompt_revision",
        "mind_profile",
        "provider_revision",
        "code_revision",
        "evidence_profile",
    }
)
_PROHIBITED_POLICY_KEYS = frozenset(
    {
        "runtime_policy",
        "runtime_behavior_rule",
        "prompt_override",
        "scenario_prompt",
        "action_schedule",
        "gesture_quota",
        "required_gesture_rate",
        "target_auxiliary_rate",
        "required_auxiliary_rate",
        "forced_action",
        "turn_count_behavior",
        "cooldown_action_rule",
        "release_pass_threshold",
        "automatic_release_gate",
    }
)


def _string_tuple(value: Any, *, field_name: str, allow_empty: bool = True) -> tuple[str, ...]:
    if value is None and allow_empty:
        return ()
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise StressProfileError(f"{field_name} must be an array of non-empty strings")
    if not allow_empty and not value:
        raise StressProfileError(f"{field_name} must not be empty")
    if len(set(value)) != len(value):
        raise StressProfileError(f"{field_name} contains duplicates")
    return tuple(value)


def _walk_keys(value: Any) -> Iterable[str]:
    if isinstance(value, Mapping):
        for key, item in value.items():
            yield str(key)
            yield from _walk_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_keys(item)


def _validate_no_runtime_policy(value: Any, *, scope: str) -> None:
    for key in _walk_keys(value):
        normalized = key.strip().casefold()
        if normalized in _PROHIBITED_POLICY_KEYS:
            raise StressProfileError(
                f"{scope} contains prohibited runtime-policy field {key!r}"
            )
        if normalized.endswith("_quota") or normalized.endswith("_target_rate"):
            raise StressProfileError(
                f"{scope} contains policy-like quota/rate field {key!r}"
            )


@dataclass(frozen=True)
class ScenarioSelector:
    datasets: tuple[str, ...]
    ids: tuple[str, ...] = ()
    cohorts: tuple[str, ...] = ()
    styles: tuple[str, ...] = ()
    modes: tuple[str, ...] = ()
    languages: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ScenarioSelector":
        selector = cls(
            datasets=_string_tuple(
                value.get("datasets"), field_name="selector.datasets", allow_empty=False
            ),
            ids=_string_tuple(value.get("ids", []), field_name="selector.ids"),
            cohorts=_string_tuple(
                value.get("cohorts", []), field_name="selector.cohorts"
            ),
            styles=_string_tuple(value.get("styles", []), field_name="selector.styles"),
            modes=_string_tuple(value.get("modes", []), field_name="selector.modes"),
            languages=_string_tuple(
                value.get("languages", []), field_name="selector.languages"
            ),
        )
        known = {"datasets", "ids", "cohorts", "styles", "modes", "languages"}
        unknown = sorted(set(value) - known)
        if unknown:
            raise StressProfileError(f"selector contains unknown fields: {unknown}")
        return selector

    def to_dict(self) -> dict[str, Any]:
        return {
            "datasets": list(self.datasets),
            "ids": list(self.ids),
            "cohorts": list(self.cohorts),
            "styles": list(self.styles),
            "modes": list(self.modes),
            "languages": list(self.languages),
        }


@dataclass(frozen=True)
class SequenceProfile:
    strategy: str
    repeat_block_size: int = 1

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "SequenceProfile":
        strategy = value.get("strategy")
        if strategy not in SEQUENCE_STRATEGIES:
            raise StressProfileError(f"invalid sequence strategy: {strategy!r}")
        repeat_block_size = value.get("repeat_block_size", 1)
        if not isinstance(repeat_block_size, int) or repeat_block_size < 1:
            raise StressProfileError("sequence.repeat_block_size must be a positive integer")
        if strategy != "repeat_each" and repeat_block_size != 1:
            raise StressProfileError(
                "sequence.repeat_block_size is only valid for repeat_each"
            )
        return cls(strategy=strategy, repeat_block_size=repeat_block_size)

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "repeat_block_size": self.repeat_block_size,
        }


@dataclass(frozen=True)
class StressWorkload:
    id: str
    kind: str
    evidence_profile: str
    sample_count: int
    session_count: int
    concurrency: int
    seed: int
    selector: ScenarioSelector
    sequence: SequenceProfile
    participants: tuple[str, ...]
    conditions: Mapping[str, Any]
    observations: tuple[str, ...]
    description: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "StressWorkload":
        known_fields = {
            "id",
            "kind",
            "evidence_profile",
            "sample_count",
            "session_count",
            "concurrency",
            "seed",
            "selector",
            "sequence",
            "participants",
            "conditions",
            "observations",
            "description",
        }
        unknown_fields = sorted(set(value) - known_fields)
        if unknown_fields:
            raise StressProfileError(
                f"stress workload contains unknown fields: {unknown_fields}"
            )
        workload_id = value.get("id")
        if not isinstance(workload_id, str) or not workload_id.strip():
            raise StressProfileError("stress workload id must be a non-empty string")
        kind = value.get("kind")
        if kind not in WORKLOAD_KINDS:
            raise StressProfileError(f"workload {workload_id!r} has invalid kind")
        evidence_profile = value.get("evidence_profile")
        if not isinstance(evidence_profile, str) or not evidence_profile.strip():
            raise StressProfileError(
                f"workload {workload_id!r} evidence_profile must be non-empty"
            )

        def positive_int(name: str, maximum: int = 10000) -> int:
            raw = value.get(name)
            if not isinstance(raw, int) or not 1 <= raw <= maximum:
                raise StressProfileError(
                    f"workload {workload_id!r} {name} must be in [1, {maximum}]"
                )
            return raw

        sample_count = positive_int("sample_count")
        session_count = positive_int("session_count")
        concurrency = positive_int("concurrency", maximum=256)
        if session_count > sample_count:
            raise StressProfileError(
                f"workload {workload_id!r} session_count exceeds sample_count"
            )
        if concurrency > sample_count:
            raise StressProfileError(
                f"workload {workload_id!r} concurrency exceeds sample_count"
            )
        if kind in {"long_session", "repetition_cooldown", "interruption"} and concurrency != 1:
            raise StressProfileError(
                f"workload {workload_id!r} requires concurrency=1 to preserve turn order"
            )
        seed = value.get("seed")
        if not isinstance(seed, int) or seed < 0:
            raise StressProfileError(f"workload {workload_id!r} seed must be non-negative")
        selector_value = value.get("selector")
        sequence_value = value.get("sequence")
        if not isinstance(selector_value, Mapping) or not isinstance(sequence_value, Mapping):
            raise StressProfileError(
                f"workload {workload_id!r} requires selector and sequence objects"
            )
        participants = _string_tuple(
            value.get("participants", []), field_name=f"workload {workload_id}.participants"
        )
        if kind == "multi_user" and len(participants) < 2:
            raise StressProfileError(
                f"multi_user workload {workload_id!r} requires at least two participants"
            )
        if kind != "multi_user" and participants:
            raise StressProfileError(
                f"participants are only valid for multi_user workload {workload_id!r}"
            )
        conditions = value.get("conditions", {})
        if not isinstance(conditions, Mapping):
            raise StressProfileError(
                f"workload {workload_id!r} conditions must be an object"
            )
        _validate_no_runtime_policy(conditions, scope=f"workload {workload_id!r}")
        observations = _string_tuple(
            value.get("observations"),
            field_name=f"workload {workload_id}.observations",
            allow_empty=False,
        )
        unknown_observations = sorted(set(observations) - OBSERVATION_DIMENSIONS)
        if unknown_observations:
            raise StressProfileError(
                f"workload {workload_id!r} has unknown observations: {unknown_observations}"
            )
        description = value.get("description")
        if not isinstance(description, str) or not description.strip():
            raise StressProfileError(
                f"workload {workload_id!r} description must be non-empty"
            )
        return cls(
            id=workload_id,
            kind=kind,
            evidence_profile=evidence_profile,
            sample_count=sample_count,
            session_count=session_count,
            concurrency=concurrency,
            seed=seed,
            selector=ScenarioSelector.from_mapping(selector_value),
            sequence=SequenceProfile.from_mapping(sequence_value),
            participants=participants,
            conditions=dict(conditions),
            observations=observations,
            description=description,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "evidence_profile": self.evidence_profile,
            "sample_count": self.sample_count,
            "session_count": self.session_count,
            "concurrency": self.concurrency,
            "seed": self.seed,
            "selector": self.selector.to_dict(),
            "sequence": self.sequence.to_dict(),
            "participants": list(self.participants),
            "conditions": dict(self.conditions),
            "observations": list(self.observations),
            "description": self.description,
        }


@dataclass(frozen=True)
class StressWorkloadManifest:
    schema_version: int
    runtime_policy_authority: bool
    metrics_are_observational: bool
    release_qualification: str
    comparison_dimensions: tuple[str, ...]
    workloads: tuple[StressWorkload, ...]

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "StressWorkloadManifest":
        if value.get("schema_version") != 1:
            raise StressProfileError("stress workload manifest must use schema_version 1")
        _validate_no_runtime_policy(value, scope="stress workload manifest")
        runtime_policy_authority = value.get("runtime_policy_authority")
        metrics_are_observational = value.get("metrics_are_observational")
        if runtime_policy_authority is not False:
            raise StressProfileError("stress workloads must not claim runtime policy authority")
        if metrics_are_observational is not True:
            raise StressProfileError("stress metrics must be declared observational")
        release_qualification = value.get("release_qualification")
        if release_qualification != "human_approval_required":
            raise StressProfileError(
                "stress workload manifest must retain human approval for release qualification"
            )
        comparison_dimensions = _string_tuple(
            value.get("comparison_dimensions"),
            field_name="comparison_dimensions",
            allow_empty=False,
        )
        unknown_dimensions = sorted(
            set(comparison_dimensions) - COMPARISON_DIMENSIONS
        )
        if unknown_dimensions:
            raise StressProfileError(
                f"unknown comparison dimensions: {unknown_dimensions}"
            )
        raw_workloads = value.get("workloads")
        if not isinstance(raw_workloads, list) or not raw_workloads:
            raise StressProfileError("stress workload manifest must contain workloads")
        workloads = tuple(
            StressWorkload.from_mapping(item)
            for item in raw_workloads
            if isinstance(item, Mapping)
        )
        if len(workloads) != len(raw_workloads):
            raise StressProfileError("every stress workload must be an object")
        ids = [item.id for item in workloads]
        if len(set(ids)) != len(ids):
            raise StressProfileError("stress workload IDs must be unique")
        kinds = {item.kind for item in workloads}
        missing_kinds = sorted(WORKLOAD_KINDS - kinds)
        if missing_kinds:
            raise StressProfileError(
                f"stress workload manifest is missing kinds: {missing_kinds}"
            )
        return cls(
            schema_version=1,
            runtime_policy_authority=False,
            metrics_are_observational=True,
            release_qualification=release_qualification,
            comparison_dimensions=comparison_dimensions,
            workloads=workloads,
        )

    @classmethod
    def from_file(cls, path: Path) -> "StressWorkloadManifest":
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise StressProfileError(f"cannot load stress workload manifest {path}: {exc}") from exc
        if not isinstance(payload, Mapping):
            raise StressProfileError("stress workload manifest must be an object")
        return cls.from_mapping(payload)

    def get(self, workload_id: str) -> StressWorkload:
        for workload in self.workloads:
            if workload.id == workload_id:
                return workload
        choices = ", ".join(item.id for item in self.workloads)
        raise StressProfileError(
            f"unknown stress workload {workload_id!r}; choose one of: {choices}"
        )
