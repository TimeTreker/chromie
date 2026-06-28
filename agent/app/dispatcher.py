from __future__ import annotations

from .schema import AgentRunRequest


DEFAULT_AGENT_ORDER: dict[str, list[str]] = {
    "chat": ["conversation_agent", "speaker_agent"],
    "deep_thought": ["deepthinking_agent", "speaker_agent"],
    "robot_action": ["capability_agent", "safety_agent", "speaker_agent"],
    "tool": ["tool_agent", "speaker_agent"],
    "memory": ["memory_agent", "speaker_agent"],
    "clarify": ["conversation_agent", "speaker_agent"],
    "interrupt": [],
    "ignore": [],
}

# Safety should validate after planners, and speaker should run last so it can
# summarize the final action set.
TAIL_ORDER = ["safety_agent", "speaker_agent"]


def selected_agents(request: AgentRunRequest) -> list[str]:
    requested = list(request.route_decision.agents or [])
    if not requested:
        requested = list(DEFAULT_AGENT_ORDER.get(request.route_decision.route, ["conversation_agent", "speaker_agent"]))

    if request.route_decision.route == "robot_action":
        for agent in ["capability_agent", "safety_agent", "speaker_agent"]:
            if agent not in requested:
                requested.append(agent)

    if request.route_decision.route == "deep_thought":
        requested = [agent for agent in requested if agent != "conversation_agent"]
        if "deepthinking_agent" not in requested:
            requested.insert(0, "deepthinking_agent")
    if request.route_decision.route == "chat" and "conversation_agent" not in requested:
        requested.insert(0, "conversation_agent")
    if request.route_decision.should_speak and "speaker_agent" not in requested and request.route_decision.route not in {"ignore", "interrupt"}:
        requested.append("speaker_agent")

    seen: set[str] = set()
    head: list[str] = []
    tail: list[str] = []
    for agent in requested:
        if agent in seen:
            continue
        seen.add(agent)
        if agent in TAIL_ORDER:
            tail.append(agent)
        else:
            head.append(agent)

    tail.sort(key=TAIL_ORDER.index)
    return head + tail
