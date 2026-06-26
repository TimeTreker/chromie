from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .capability_catalog import CapabilityCatalogResult
from .schema import RouteDecision, RouteRequest, finalize_decision


_SEQUENCE_SPLIT = re.compile(
    r"\s*(?:,?\s+(?:and\s+then|then|after\s+that|and)\s+|[;；，,]|然后|接着|再)\s*",
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
    "零": 0.0,
    "一": 1.0,
    "两": 2.0,
    "二": 2.0,
    "三": 3.0,
    "四": 4.0,
    "五": 5.0,
    "六": 6.0,
    "七": 7.0,
    "八": 8.0,
    "九": 9.0,
    "十": 10.0,
}
_NOD_RE = re.compile(r"\b(?:nod|nodding|noding)\b|点头")
_BLINK_RE = re.compile(r"\b(?:blink|blinking)\b|眨眼|眨眨眼|眨一眨")
_HEAD_DIRECTION_PATTERNS = (
    re.compile(
        r"\b(?:turn|rotate|move)\s+(?:your|my|the)?\s*head\s+"
        r"(?:to\s+the\s+|to\s+|toward\s+|towards\s+)?(left|right)\b"
    ),
    re.compile(
        r"\b(?:look|face)\s+(?:to\s+the\s+|to\s+|toward\s+|towards\s+)?"
        r"(left|right)\b"
    ),
)
NORMAL_FORWARD_VX_MPS = 0.18
NORMAL_BACKWARD_VX_MPS = -0.03
WALK_VX_MIN_MPS = -0.03
WALK_VX_MAX_MPS = 0.20
SING_WHILE_MOVING_SPEECH = (
    "La la, tiny steps and circuits bright, I am walking through the light."
)


@dataclass(frozen=True)
class SemanticAction:
    capability_id: str
    args: dict[str, Any]
    metadata: dict[str, Any] | None = None


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
        r"(?:\bfor\s+)?(-?\d+(?:\.\d+)?|[a-z]+|[零一两二三四五六七八九十]+)\s*(?:seconds?|secs?|s|秒)\b",
        text,
    )
    return _number(match.group(1)) if match else None


def _clamp(value: float, *, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, float(value)))


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
    match = re.search(
        r"\b(\d+|one|two|three|four|five|six|seven|eight)\s+times?\b|"
        r"([零一两二三四五六七八九十]+)\s*(?:次|下)",
        text,
    )
    value = _number(next((group for group in match.groups() if group), "")) if match else None
    return int(value) if value is not None else default


def _natural_head_gesture_args(text: str, *, use_explicit_duration: bool = True) -> dict[str, Any]:
    count = max(2, _count(text))
    duration = _duration_s(text) if use_explicit_duration else None
    if duration is None:
        duration = round(max(1.0, min(10.0, count * 0.7)), 1)
    else:
        duration = round(_clamp(duration, minimum=1.0, maximum=10.0), 1)
    return {
        "count": count,
        "amplitude": "small",
        "duration_s": duration,
    }


def _head_direction(text: str) -> str | None:
    for pattern in _HEAD_DIRECTION_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1)
    return None


def _walk_action(text: str, available: set[str]) -> SemanticAction | None:
    walk_match = re.search(
        r"\b(?:walk|move|go|travel)\b(?:\s+straight)?(?:\s+(forward|ahead|backward|back|reverse))?\b|"
        r"(向前|往前|前进|朝前|向后|往后|后退)?(?:走|移动|行走)",
        text,
    )
    if not walk_match or "soridormi.walk_velocity" not in available:
        return None

    direction = walk_match.group(1) or walk_match.group(2) or "forward"
    if direction in {"向前", "往前", "前进", "朝前"}:
        direction = "forward"
    elif direction in {"向后", "往后", "后退"}:
        direction = "backward"
    requested_speed = _speed(text)
    speed = requested_speed
    metadata: dict[str, Any] = {}
    if speed is None:
        speed = NORMAL_BACKWARD_VX_MPS if direction in {"backward", "back", "reverse"} else NORMAL_FORWARD_VX_MPS
    if direction in {"backward", "back", "reverse"}:
        speed = -abs(speed)
        normal_speed = NORMAL_BACKWARD_VX_MPS
    else:
        speed = abs(speed)
        normal_speed = NORMAL_FORWARD_VX_MPS
    if speed < WALK_VX_MIN_MPS or speed > WALK_VX_MAX_MPS:
        metadata["speed_adjustment"] = {
            "reason": "outside_safe_range",
            "requested_vx_mps": speed,
            "normal_vx_mps": normal_speed,
            "safe_min_vx_mps": WALK_VX_MIN_MPS,
            "safe_max_vx_mps": WALK_VX_MAX_MPS,
        }
        speed = normal_speed
    args = {"vx_mps": speed, "vy_mps": 0.0, "yaw_radps": 0.0}
    duration = _duration_s(text)
    if duration is not None:
        args["duration_s"] = duration
    return SemanticAction("soridormi.walk_velocity", args, metadata or None)


def _head_gesture_action(
    text: str,
    available: set[str],
    *,
    use_explicit_duration: bool = True,
) -> SemanticAction | None:
    if _NOD_RE.search(text) and "soridormi.nod_yes" in available:
        return SemanticAction(
            "soridormi.nod_yes",
            _natural_head_gesture_args(text, use_explicit_duration=use_explicit_duration),
        )

    if re.search(r"\bshake\b.*\bhead\b", text) and "soridormi.shake_no" in available:
        return SemanticAction(
            "soridormi.shake_no",
            _natural_head_gesture_args(text, use_explicit_duration=use_explicit_duration),
        )

    return None


def _blink_action(text: str, available: set[str]) -> SemanticAction | None:
    if not _BLINK_RE.search(text) or "soridormi.blink_eyes" not in available:
        return None
    count = max(1, min(6, _count(text, default=2)))
    return SemanticAction("soridormi.blink_eyes", {"count": count})


def _look_direction_action(text: str, available: set[str]) -> SemanticAction | None:
    direction = _head_direction(text)
    if direction is None or "soridormi.look_direction" not in available:
        return None

    args: dict[str, Any] = {
        "head_yaw_rad": -0.35 if direction == "left" else 0.35,
        "head_pitch_rad": 0.0,
    }
    duration = _duration_s(text)
    if duration is not None:
        args["duration_s"] = round(_clamp(duration, minimum=0.2, maximum=3.0), 1)
    return SemanticAction("soridormi.look_direction", args)


def _parse_atomic_segment(text: str, available: set[str]) -> SemanticAction | None:
    text = _normalized(text).strip(" ,.!?")
    if not text:
        return None

    blink = _blink_action(text, available)
    if blink is not None:
        return blink

    head_gesture = _head_gesture_action(text, available)
    if head_gesture is not None:
        return head_gesture

    look_direction = _look_direction_action(text, available)
    if look_direction is not None:
        return look_direction

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

    walk = _walk_action(text, available)
    if walk is not None:
        return walk

    return None


def _parse_segment(text: str, available: set[str]) -> list[SemanticAction] | None:
    normalized = _normalized(text).strip(" ,.!?")
    if not normalized:
        return None

    if re.search(r"\b(?:with|while|whilst)\b", normalized):
        walk = _walk_action(normalized, available)
        if walk is not None:
            gesture = _head_gesture_action(
                normalized,
                available,
                use_explicit_duration=False,
            )
            if gesture is not None:
                return [walk, gesture]

    action = _parse_atomic_segment(normalized, available)
    return [action] if action is not None else None


def _speak_first(text: str, actions: list[SemanticAction]) -> str | None:
    normalized = _normalized(text)
    speech_parts: list[str] = []
    for action in actions:
        metadata = action.metadata or {}
        if metadata.get("speed_adjustment"):
            speech_parts.append(
                "Too fast. Walking normally."
            )
            break
    if re.search(r"\b(?:sing|song)\b", normalized) and any(
        action.capability_id == "soridormi.walk_velocity" for action in actions
    ):
        speech_parts.append(SING_WHILE_MOVING_SPEECH)
    if re.search(r"\b(?:say|tell|greet)\s+(?:hello|hi|hey)\b", normalized):
        speech_parts.append("Hello.")
    return " ".join(speech_parts) if speech_parts else None


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
        segment_actions = _parse_segment(part, set(candidates))
        if segment_actions is None:
            return None
        actions.extend(segment_actions)

    if not actions:
        return None

    payload = [
        {
            "capability_id": item.capability_id,
            "args": item.args,
            "timing": "sequential",
            "sequence": index,
            **({"metadata": item.metadata} if item.metadata else {}),
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
            speak_first=_speak_first(request.text, actions),
            actions=payload,
            candidate_capabilities=list(result.matches),
            reason="Deterministic semantic capability plan",
            source="catalog",
        ),
        request,
        source="catalog",
    )
