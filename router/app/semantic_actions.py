from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .capability_catalog import CapabilityCatalogResult
from .schema import RouteDecision, RouteRequest, finalize_decision


_SEQUENCE_SPLIT = re.compile(
    r"\s*(?:,?\s+(?:and\s+then|then|after\s+that)\s+|;+)\s*",
    re.IGNORECASE,
)
_NUMBER_WORDS = {
    "zero": 0.0,
    "one": 1.0,
    "two": 2.0,
    "three": 3.0,
    "four": 4.0,
    "five": 5.0,
    "six": 6.0,
    "seven": 7.0,
    "eight": 8.0,
    "nine": 9.0,
    "ten": 10.0,
    "eleven": 11.0,
    "twelve": 12.0,
    "fifteen": 15.0,
    "twenty": 20.0,
}


@dataclass(frozen=True)
class SemanticAction:
    capability_id: str
    args: dict[str, Any]


def _normalized(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def _candidate_map(result: CapabilityCatalogResult) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("capability_id") or ""): item
        for item in result.matches
        if item.get("available") is not False
        and item.get("interaction_executable") is True
        and item.get("capability_id")
    }


def _number(value: str | None) -> float | None:
    if not value:
        return None
    value = value.strip().lower()
    try:
        return float(value)
    except ValueError:
        return _NUMBER_WORDS.get(value)


def _duration_s(text: str) -> float | None:
    match = re.search(
        r"\bfor\s+(-?\d+(?:\.\d+)?|[a-z]+)\s*(?:seconds?|secs?|s)\b",
        text,
    )
    return _number(match.group(1)) if match else None


def _speed(text: str) -> float | None:
    patterns = (
        r"\bat\s+(-?\d+(?:\.\d+)?)\s*(?:m/?s|meters? per second|speed)?\b",
        r"\b(-?\d+(?:\.\d+)?)\s*(?:m/?s|meters? per second|speed)\b",
        r"\bspeed\s+(?:of\s+)?(-?\d+(?:\.\d+)?)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return float(match.group(1))
    return None


def _count(text: str, default: int = 2) -> int:
    if "twice" in text:
        return 2
    if "once" in text:
        return 1
    match = re.search(r"\b(\d+|one|two|three|four|five|six|seven|eight)\s+times?\b", text)
    value = _number(match.group(1)) if match else None
    return int(value) if value is not None else default


def _parse_segment(text: str, available: set[str]) -> SemanticAction | None:
    text = _normalized(text).strip(" ,.!?")
    if not text:
        return None

    if re.search(r"\b(nod|nodding)\b", text) and "soridormi.nod_yes" in available:
        return SemanticAction("soridormi.nod_yes", {"count": max(2, _count(text))})

    if re.search(r"\bshake\b.*\bhead\b", text) and "soridormi.shake_no" in available:
        return SemanticAction("soridormi.shake_no", {"count": max(2, _count(text))})

    turn_match = re.search(r"\b(?:turn|rotate)\s+(left|right)\b", text)
    if turn_match and "soridormi.turn_in_place" in available:
        yaw = -0.12 if turn_match.group(1) == "left" else 0.12
        args: dict[str, Any] = {"yaw_radps": yaw}
        duration = _duration_s(text)
        if duration is not None:
            args["duration_s"] = duration
        return SemanticAction("soridormi.turn_in_place", args)

    curve_request = bool(re.search(r"\b(curve|curved|arc|circle|circular)\b", text))
    if curve_request and "soridormi.curve_walk" in available:
        args = {}
        speed = _speed(text)
        duration = _duration_s(text)
        if speed is not None:
            args["vx_mps"] = abs(speed)
        if duration is not None:
            args["duration_s"] = duration
        turn = re.search(r"\b(left|right)\b", text)
        if turn:
            args["yaw_radps"] = -0.1 if turn.group(1) == "left" else 0.1
        return SemanticAction("soridormi.curve_walk", args)

    walk_match = re.search(
        r"\b(?:walk|move|go|travel)\b(?:\s+straight)?(?:\s+(forward|ahead|backward|back|reverse))?\b",
        text,
    )
    if walk_match and "soridormi.walk_velocity" in available:
        direction = walk_match.group(1) or "forward"
        speed = _speed(text)
        if speed is None:
            speed = 0.1
        if direction in {"backward", "back", "reverse"}:
            speed = -abs(speed)
        else:
            speed = abs(speed)
        args = {"vx_mps": speed, "vy_mps": 0.0, "yaw_radps": 0.0}
        duration = _duration_s(text)
        if duration is not None:
            args["duration_s"] = duration
        return SemanticAction("soridormi.walk_velocity", args)

    return None


def semantic_robot_decision(
    request: RouteRequest,
    result: CapabilityCatalogResult,
) -> RouteDecision | None:
    """Build an exact, ordered robot plan for clear supported commands.

    This is deliberately narrow. It handles commands whose semantics are safer
    and more reliable to parse deterministically than to infer from lexical
    catalog ranking. Unknown or ambiguous text returns None and keeps the normal
    LLM/catalog routing path intact.
    """

    candidates = _candidate_map(result)
    if not candidates:
        return None

    parts = [part for part in _SEQUENCE_SPLIT.split(request.text) if part.strip()]
    actions: list[SemanticAction] = []
    for part in parts:
        action = _parse_segment(part, set(candidates))
        if action is None:
            return None
        actions.append(action)

    if not actions:
        return None

    payload = [
        {
            "capability_id": item.capability_id,
            "args": item.args,
            "timing": "sequential",
            "sequence": index,
        }
        for index, item in enumerate(actions)
    ]
    intent = (
        f"capability:{actions[0].capability_id}"
        if len(actions) == 1
        else "compound_robot_action"
    )
    return finalize_decision(
        RouteDecision(
            route="robot_action",
            agents=["capability_agent", "safety_agent", "speaker_agent"],
            intent=intent,
            confidence=0.99,
            language=request.language or "auto",
            priority="normal",
            needs_agent=True,
            should_speak=True,
            actions=payload,
            candidate_capabilities=list(result.matches),
            reason="Deterministic semantic capability plan",
            source="catalog",
        ),
        request,
        source="catalog",
    )
