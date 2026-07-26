from __future__ import annotations

import difflib
import json
import re
from collections import Counter
from typing import Any, Iterable, Mapping

from .models import candidate_texts


def canonical_text(value: str) -> str:
    return " ".join(re.sub(r"[^\w\u3400-\u9fff]+", " ", value.casefold()).split())


def scenario_texts(scenario: Mapping[str, Any]) -> tuple[str, ...]:
    inputs = scenario.get("inputs")
    texts: list[str] = []
    if isinstance(inputs, Mapping):
        for key in ("text", "user_text", "utterance", "query", "request", "ask"):
            value = inputs.get(key)
            if isinstance(value, str) and value.strip():
                texts.append(value.strip())
        turns = inputs.get("turns")
        if isinstance(turns, list):
            for turn in turns:
                if isinstance(turn, Mapping):
                    value = turn.get("ask", turn.get("text"))
                    if isinstance(value, str) and value.strip():
                        texts.append(value.strip())
    if not texts:
        legacy = scenario.get("legacy_expectations")
        if isinstance(legacy, Mapping):
            text = json.dumps(legacy, ensure_ascii=False, sort_keys=True)
            if text:
                texts.append(text)
    return tuple(texts)


def similarity(left: str, right: str) -> float:
    return difflib.SequenceMatcher(a=canonical_text(left), b=canonical_text(right)).ratio()


def related_scenarios(
    candidate: Mapping[str, Any],
    scenarios: Iterable[Mapping[str, Any]],
    *,
    threshold: float,
) -> list[dict[str, Any]]:
    candidate_values = candidate_texts(candidate)
    matches: list[dict[str, Any]] = []
    for scenario in scenarios:
        best = 0.0
        for left in candidate_values:
            for right in scenario_texts(scenario):
                best = max(best, similarity(left, right))
        if best >= threshold:
            matches.append(
                {
                    "scenario_id": scenario.get("id"),
                    "similarity": round(best, 6),
                    "datasets": list(scenario.get("datasets") or []),
                    "source": scenario.get("source"),
                    "historical_regression": "historical_regression" in set(scenario.get("datasets") or []),
                }
            )
    matches.sort(key=lambda item: (-item["similarity"], str(item["scenario_id"])))
    return matches


def failure_tag_counts(candidates: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for candidate in candidates:
        tags = candidate.get("tags")
        if isinstance(tags, list):
            for tag in tags:
                value = str(tag)
                if value not in {"candidate", "experience-mined"}:
                    counter[value] += 1
    return dict(sorted(counter.items()))
