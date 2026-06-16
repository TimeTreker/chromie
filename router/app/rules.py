from __future__ import annotations

import re

from .schema import RouteDecision, RouteRequest, detect_language, finalize_decision


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


INTERRUPT_PATTERNS = [
    r"^(stop|cancel|quiet|shut up|be quiet|enough|pause|hold on)(?:\s+(?:now|please))?[.!?]*$",
    r"(stop talking|stop speaking|don't speak|do not speak)",
    r"^(停|停下|停止|闭嘴|别说了|不要说了|安静|暂停|打住)[。！!？?]*$",
]

IGNORE_PATTERNS = [
    r"^$",
    r"^[\W_]+$",
    r"^(um+|uh+|er+|hmm+|mm+|嗯+|呃+|啊+|额+)[。.!?？]*$",
]

EMOTIONAL_CUE_PATTERNS = [
    r"^(sigh|叹气|唉|哎|哎呀|唉呀)[。.!?？]*$",
]

LOOK_AT_USER_PATTERNS = [
    r"(look at me|face me|turn .*towards me|look this way)",
    r"(看着我|看向我|转过来看我|面对我|朝我看)",
]

TURN_LEFT_PATTERNS = [
    r"(turn left|look left|face left)",
    r"(左转|往左|向左|看左边|转向左边)",
]

TURN_RIGHT_PATTERNS = [
    r"(turn right|look right|face right)",
    r"(右转|往右|向右|看右边|转向右边)",
]

NOD_PATTERNS = [
    r"(nod|nodding)",
    r"(点头|点一下头)",
]

SHAKE_HEAD_PATTERNS = [
    r"(shake your head)",
    r"(摇头|摇一下头)",
]

COME_HERE_PATTERNS = [
    r"(come here|come closer|move closer|come to me)",
    r"(过来|靠近我|走过来|到我这边)",
]

WEATHER_PATTERNS = [
    r"(weather|temperature|hot outside|cold outside|rain)",
    r"(天气|气温|热不热|冷不冷|下雨|外面热|外面冷)",
]

MEMORY_PATTERNS = [
    r"(remember that|remember this|don't forget)",
    r"(记住|帮我记住|不要忘了)",
]


def _matches(text: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def _robot_decision(
    request: RouteRequest,
    *,
    intent: str,
    reason: str,
    confidence: float = 0.95,
    agents: list[str] | None = None,
    actions: list[dict] | None = None,
) -> RouteDecision:
    lang = request.language or detect_language(request.text)
    return finalize_decision(
        RouteDecision(
            route="robot_action",
            agents=agents or ["robot_pose_controller_agent", "safety_agent", "speaker_agent"],
            intent=intent,
            confidence=confidence,
            language=lang,
            priority="normal",
            interrupt_current=False,
            needs_agent=True,
            should_speak=True,
            actions=actions or [],
            reason=reason,
            source="rules",
        ),
        request,
        source="rules",
    )


def route_by_priority_rules(request: RouteRequest) -> RouteDecision | None:
    """Handle only safety-critical interruption and obvious non-speech noise."""

    text = _norm(request.text)
    lang = request.language or detect_language(request.text)
    if _matches(text, INTERRUPT_PATTERNS):
        return finalize_decision(
            RouteDecision(
                route="interrupt",
                agents=[],
                intent="stop_current_output",
                confidence=0.99,
                language=lang,
                priority="urgent",
                interrupt_current=True,
                needs_agent=False,
                should_speak=False,
                reason="Matched interrupt safety rule",
                source="rules",
            ),
            request,
            source="rules",
        )
    if _matches(text, IGNORE_PATTERNS):
        return finalize_decision(
            RouteDecision(
                route="ignore",
                agents=[],
                intent="noise_or_filler",
                confidence=0.90,
                language=lang,
                priority="low",
                needs_agent=False,
                should_speak=False,
                reason="Matched ignore/noise rule",
                source="rules",
            ),
            request,
            source="rules",
        )
    return None


def route_by_rules(request: RouteRequest) -> RouteDecision | None:
    """Return a high-confidence route using cheap deterministic rules.

    Return None when the text is not obvious and the LLM router should decide.
    """

    text = _norm(request.text)
    lang = request.language or detect_language(request.text)

    if _matches(text, INTERRUPT_PATTERNS):
        return finalize_decision(
            RouteDecision(
                route="interrupt",
                agents=[],
                intent="stop_current_output",
                confidence=0.99,
                language=lang,
                priority="urgent",
                interrupt_current=True,
                needs_agent=False,
                should_speak=False,
                reason="Matched interrupt rule",
                source="rules",
            ),
            request,
            source="rules",
        )

    if _matches(text, IGNORE_PATTERNS):
        return finalize_decision(
            RouteDecision(
                route="ignore",
                agents=[],
                intent="noise_or_filler",
                confidence=0.90,
                language=lang,
                priority="low",
                needs_agent=False,
                should_speak=False,
                reason="Matched ignore/noise rule",
                source="rules",
            ),
            request,
            source="rules",
        )

    if _matches(text, EMOTIONAL_CUE_PATTERNS):
        return finalize_decision(
            RouteDecision(
                route="chat",
                agents=["conversation_agent", "speaker_agent"],
                intent="emotional_cue",
                confidence=0.80,
                language=lang,
                priority="normal",
                needs_agent=True,
                should_speak=True,
                speak_first="怎么了？" if lang.startswith("zh") else "What happened?",
                reason="Matched emotional cue rule",
                source="rules",
            ),
            request,
            source="rules",
        )

    if _matches(text, LOOK_AT_USER_PATTERNS):
        return _robot_decision(
            request,
            intent="look_at_user",
            reason="Matched look-at-user robot pose rule",
            actions=[
                {
                    "target": "robot_pose_controller",
                    "type": "head.look_at_user",
                    "params": {"duration_ms": 3000},
                    "blocking": False,
                }
            ],
        )

    if _matches(text, TURN_LEFT_PATTERNS):
        return _robot_decision(
            request,
            intent="turn_left",
            reason="Matched turn-left robot pose rule",
            actions=[
                {
                    "target": "robot_pose_controller",
                    "type": "head.turn",
                    "params": {"yaw_degrees": -20, "duration_ms": 600},
                    "blocking": False,
                }
            ],
        )

    if _matches(text, TURN_RIGHT_PATTERNS):
        return _robot_decision(
            request,
            intent="turn_right",
            reason="Matched turn-right robot pose rule",
            actions=[
                {
                    "target": "robot_pose_controller",
                    "type": "head.turn",
                    "params": {"yaw_degrees": 20, "duration_ms": 600},
                    "blocking": False,
                }
            ],
        )

    if _matches(text, NOD_PATTERNS):
        return _robot_decision(
            request,
            intent="nod",
            reason="Matched nod robot pose rule",
            actions=[
                {
                    "target": "robot_pose_controller",
                    "type": "head.nod",
                    "params": {"times": 1, "duration_ms": 800},
                    "blocking": False,
                }
            ],
        )

    if _matches(text, SHAKE_HEAD_PATTERNS):
        return _robot_decision(
            request,
            intent="shake_head",
            reason="Matched shake-head robot pose rule",
            actions=[
                {
                    "target": "robot_pose_controller",
                    "type": "head.shake",
                    "params": {"times": 1, "duration_ms": 900},
                    "blocking": False,
                }
            ],
        )

    if _matches(text, COME_HERE_PATTERNS):
        return _robot_decision(
            request,
            intent="move_closer_to_user",
            reason="Matched motion planning rule",
            agents=["motion_planner_agent", "safety_agent", "speaker_agent"],
            confidence=0.90,
            actions=[
                {
                    "target": "motion_controller",
                    "type": "navigate.to_user",
                    "params": {
                        "stop_distance_m": 0.8,
                        "max_speed_mps": 0.25,
                        "avoid_obstacles": True,
                    },
                    "blocking": True,
                }
            ],
        )

    if _matches(text, WEATHER_PATTERNS):
        return finalize_decision(
            RouteDecision(
                route="tool",
                agents=["tool_agent", "speaker_agent"],
                intent="weather_query",
                confidence=0.88,
                language=lang,
                priority="normal",
                needs_agent=True,
                should_speak=True,
                reason="Matched weather/tool rule",
                source="rules",
            ),
            request,
            source="rules",
        )

    if _matches(text, MEMORY_PATTERNS):
        return finalize_decision(
            RouteDecision(
                route="memory",
                agents=["memory_agent", "speaker_agent"],
                intent="remember_user_fact",
                confidence=0.86,
                language=lang,
                priority="normal",
                needs_agent=True,
                should_speak=True,
                reason="Matched memory rule",
                source="rules",
            ),
            request,
            source="rules",
        )

    return None
