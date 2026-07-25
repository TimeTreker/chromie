from __future__ import annotations

import math
import random
from dataclasses import dataclass
from itertools import cycle, islice
from typing import Any, Iterable, Mapping

from .profiles import StressProfileError, StressWorkload


@dataclass(frozen=True)
class StressSample:
    index: int
    sample_id: str
    session_id: str
    sequence_position: int
    participant_id: str | None
    source_scenario_id: str
    scenario: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "sample_id": self.sample_id,
            "session_id": self.session_id,
            "sequence_position": self.sequence_position,
            "participant_id": self.participant_id,
            "source_scenario_id": self.source_scenario_id,
        }


def _case_metadata(case: Mapping[str, Any]) -> Mapping[str, Any]:
    direct = case.get("metadata")
    if isinstance(direct, Mapping):
        return direct
    context = case.get("context")
    if isinstance(context, Mapping):
        nested = context.get("metadata")
        if isinstance(nested, Mapping):
            return nested
    return {}


def select_workload_cases(
    cases: Iterable[Mapping[str, Any]], workload: StressWorkload
) -> list[dict[str, Any]]:
    selector = workload.selector
    selected: list[dict[str, Any]] = []
    for source in cases:
        case_id = source.get("id")
        datasets = source.get("datasets", [])
        if not isinstance(case_id, str) or not isinstance(datasets, list):
            continue
        if not set(selector.datasets).intersection(datasets):
            continue
        if selector.ids and case_id not in selector.ids:
            continue
        metadata = _case_metadata(source)
        filters = (
            ("cohort", selector.cohorts),
            ("style", selector.styles),
            ("mode", selector.modes),
            ("language", selector.languages),
        )
        if any(
            allowed and metadata.get(field_name) not in allowed
            for field_name, allowed in filters
        ):
            continue
        selected.append(dict(source))
    selected.sort(key=lambda item: item["id"])
    if not selected:
        raise StressProfileError(
            f"workload {workload.id!r} selector matched no normalized scenarios"
        )
    return selected


def _scenario_sequence(
    selected: list[dict[str, Any]], workload: StressWorkload
) -> list[dict[str, Any]]:
    strategy = workload.sequence.strategy
    if strategy == "round_robin":
        return list(islice(cycle(selected), workload.sample_count))
    if strategy == "repeat_each":
        expanded = [
            case
            for case in selected
            for _ in range(workload.sequence.repeat_block_size)
        ]
        return list(islice(cycle(expanded), workload.sample_count))
    if strategy == "seeded_shuffle":
        rng = random.Random(workload.seed)
        result: list[dict[str, Any]] = []
        while len(result) < workload.sample_count:
            batch = list(selected)
            rng.shuffle(batch)
            result.extend(batch)
        return result[: workload.sample_count]
    raise StressProfileError(f"unsupported sequence strategy: {strategy}")


def build_sample_plan(
    cases: Iterable[Mapping[str, Any]], workload: StressWorkload
) -> list[StressSample]:
    selected = select_workload_cases(cases, workload)
    sequence = _scenario_sequence(selected, workload)
    samples_per_session = math.ceil(workload.sample_count / workload.session_count)
    positions: dict[str, int] = {}
    result: list[StressSample] = []
    for index, scenario in enumerate(sequence):
        session_index = min(index // samples_per_session, workload.session_count - 1)
        session_id = f"{workload.id}.session-{session_index + 1:03d}"
        position = positions.get(session_id, 0) + 1
        positions[session_id] = position
        participant = None
        if workload.participants:
            participant = workload.participants[index % len(workload.participants)]
        result.append(
            StressSample(
                index=index,
                sample_id=f"{workload.id}.sample-{index + 1:05d}",
                session_id=session_id,
                sequence_position=position,
                participant_id=participant,
                source_scenario_id=str(scenario["id"]),
                scenario=scenario,
            )
        )
    return result
