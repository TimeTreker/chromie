from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


RouteName = Literal[
    "chat",
    "deep_thought",
    "robot_action",
    "tool",
    "memory",
    "clarify",
    "interrupt",
    "ignore",
]

Priority = Literal["low", "normal", "high", "urgent"]
DecisionSource = Literal["rules", "llm", "catalog", "fallback"]


DEFAULT_AGENTS: dict[str, list[str]] = {
    "chat": ["conversation_agent", "speaker_agent"],
    "deep_thought": ["deepthinking_agent", "speaker_agent"],
    "robot_action": ["robot_pose_controller_agent", "safety_agent", "speaker_agent"],
    "tool": ["tool_agent", "speaker_agent"],
    "memory": ["memory_agent", "speaker_agent"],
    "clarify": ["speaker_agent"],
    "interrupt": [],
    "ignore": [],
}


class RouteRequest(BaseModel):
    """Request from host orchestrator after ASR final text."""

    sid: str | None = None
    text: str = Field(min_length=0, description="ASR final text")
    language: str | None = Field(default=None, description="Optional BCP-47 language hint")
    context: dict[str, Any] = Field(default_factory=dict)

    @field_validator("text")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return (value or "").strip()


class RouteDecision(BaseModel):
    """Structured decision consumed by host orchestrator."""

    route: RouteName
    agents: list[str] = Field(default_factory=list)
    intent: str = "unknown"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    language: str = "auto"
    priority: Priority = "normal"
    interrupt_current: bool = False
    needs_agent: bool = True
    should_speak: bool = True
    speak_first: str | None = None
    actions: list[dict[str, Any]] = Field(default_factory=list)
    candidate_capabilities: list[dict[str, Any]] = Field(default_factory=list)
    reason: str | None = None
    source: DecisionSource = "fallback"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("agents")
    @classmethod
    def normalize_agents(cls, value: list[str]) -> list[str]:
        seen: set[str] = set()
        normalized: list[str] = []
        for agent in value or []:
            agent = str(agent).strip()
            if not agent or agent in seen:
                continue
            seen.add(agent)
            normalized.append(agent)
        return normalized


class HealthResponse(BaseModel):
    ok: bool = True
    service: str = "chromie-router"
    mode: str
    model: str | None = None
    ollama_url: str | None = None
    rules_first: bool = True


STAGE_ORDER: dict[str, int] = {
    "emergency_filter": 0,
    "quick_intent": 1,
    "deep_thought": 2,
}


def default_agents_for_route(route: str) -> list[str]:
    return list(DEFAULT_AGENTS.get(route, ["conversation_agent", "speaker_agent"]))


def _priority_rank(priority: str) -> int:
    return {"urgent": 0, "high": 1, "normal": 2, "low": 3}.get(priority, 2)


def _route_task_type(route: str) -> str:
    return {
        "chat": "speech.answer",
        "deep_thought": "cognition.deep_think",
        "robot_action": "task.execute_robot_action",
        "tool": "task.use_tool",
        "memory": "memory.remember_session_context",
        "clarify": "speech.ask_clarification",
        "interrupt": "task.cancel_current_action",
        "ignore": "state.ignore_input",
    }.get(route, "route.handle_request")


def _task_item(
    *,
    source_stage: str,
    kind: str,
    task_type: str,
    route: str,
    intent: str,
    priority: str,
    index: int,
    status: str = "proposed",
    requires_validation: bool = True,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    item = {
        "id": f"{source_stage}:{index}:{task_type}",
        "source_stage": source_stage,
        "kind": kind,
        "task_type": task_type,
        "route": route,
        "intent": intent,
        "priority": priority,
        "status": status,
        "requires_validation": requires_validation,
    }
    if extra:
        item.update(extra)
    return item


def _tasks_for_decision(decision: RouteDecision, *, source_stage: str) -> list[dict[str, Any]]:
    route = decision.route
    priority = decision.priority
    intent = decision.intent
    tasks: list[dict[str, Any]] = []

    if route == "interrupt":
        tasks.append(
            _task_item(
                source_stage=source_stage,
                kind="action",
                task_type="task.cancel_current_action",
                route=route,
                intent=intent,
                priority="urgent",
                index=0,
                requires_validation=False,
            )
        )
        tasks.append(
            _task_item(
                source_stage=source_stage,
                kind="action",
                task_type="body.stop_motion",
                route=route,
                intent=intent,
                priority="urgent",
                index=1,
                requires_validation=True,
            )
        )
        return tasks

    if route == "robot_action" and decision.actions:
        for index, action in enumerate(decision.actions):
            capability_id = str(action.get("capability_id") or "").strip()
            action_type = str(action.get("type") or "").strip()
            args = action.get("args") if isinstance(action.get("args"), dict) else {}
            extra: dict[str, Any] = {"sequence": index}
            if capability_id:
                extra["capability_id"] = capability_id
                extra["args"] = args
            if action_type:
                extra["action_type"] = action_type
                params = action.get("params")
                if isinstance(params, dict):
                    extra["params"] = params
            tasks.append(
                _task_item(
                    source_stage=source_stage,
                    kind="action",
                    task_type="task.execute_skill" if capability_id else action_type or "task.execute_robot_action",
                    route=route,
                    intent=intent,
                    priority=priority,
                    index=index,
                    extra=extra,
                )
            )
        return tasks

    capability_prefix = "capability:"
    if route == "robot_action" and intent.startswith(capability_prefix):
        capability_id = intent[len(capability_prefix) :].strip()
        tasks.append(
            _task_item(
                source_stage=source_stage,
                kind="action",
                task_type="task.execute_skill",
                route=route,
                intent=intent,
                priority=priority,
                index=0,
                extra={"capability_id": capability_id} if capability_id else None,
            )
        )
        return tasks

    tasks.append(
        _task_item(
            source_stage=source_stage,
            kind="task" if route not in {"ignore"} else "state",
            task_type=_route_task_type(route),
            route=route,
            intent=intent,
            priority=priority,
            index=0,
            requires_validation=route not in {"ignore"},
        )
    )
    return tasks


def route_stage_output(
    decision: RouteDecision,
    *,
    stage: str,
    status: str = "proposed",
    tasks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    task_items = tasks if tasks is not None else _tasks_for_decision(decision, source_stage=stage)
    return {
        "stage": stage,
        "status": status,
        "route": decision.route,
        "intent": decision.intent,
        "confidence": decision.confidence,
        "source": decision.source,
        "tasks": task_items,
        "actions": [item for item in task_items if item.get("kind") == "action"],
    }


def passed_stage_output(stage: str) -> dict[str, Any]:
    return {
        "stage": stage,
        "status": "passed",
        "tasks": [],
        "actions": [],
    }


def merge_stage_task_list(outputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for stage_output in outputs:
        if not isinstance(stage_output, dict):
            continue
        stage = str(stage_output.get("stage") or "unknown")
        tasks = stage_output.get("tasks") or []
        if not isinstance(tasks, list):
            continue
        for task in tasks:
            if not isinstance(task, dict):
                continue
            merged.append(
                {
                    **task,
                    "source_stage": str(task.get("source_stage") or stage),
                }
            )
    merged.sort(
        key=lambda item: (
            _priority_rank(str(item.get("priority") or "normal")),
            STAGE_ORDER.get(str(item.get("source_stage") or ""), 99),
            int(item.get("sequence", len(merged))) if isinstance(item.get("sequence", 0), int) else 0,
        )
    )
    return [
        {
            **item,
            "merged_sequence": index,
        }
        for index, item in enumerate(merged)
    ]


def annotate_stage_outputs(
    decision: RouteDecision,
    outputs: list[dict[str, Any]],
) -> RouteDecision:
    decision.metadata = {
        **(decision.metadata or {}),
        "route_stage_outputs": outputs,
        "task_list": merge_stage_task_list(outputs),
    }
    return decision


def annotate_default_stage_output(decision: RouteDecision) -> RouteDecision:
    if (decision.metadata or {}).get("route_stage_outputs"):
        decision.metadata = {
            **decision.metadata,
            "task_list": merge_stage_task_list(decision.metadata["route_stage_outputs"]),
        }
        return decision
    stage = (
        "emergency_filter"
        if decision.route in {"interrupt", "ignore"} and decision.source == "rules"
        else "deep_thought"
        if decision.route == "deep_thought"
        else "quick_intent"
    )
    return annotate_stage_outputs(decision, [route_stage_output(decision, stage=stage)])


def annotate_pipeline_stage_outputs(
    decision: RouteDecision,
    *,
    emergency_matched: bool = False,
) -> RouteDecision:
    if emergency_matched:
        return annotate_stage_outputs(
            decision,
            [route_stage_output(decision, stage="emergency_filter", status="triggered")],
        )

    outputs: list[dict[str, Any]] = [passed_stage_output("emergency_filter")]
    if decision.route == "deep_thought":
        outputs.append(
            route_stage_output(
                decision,
                stage="quick_intent",
                status="delegated",
                tasks=[
                    _task_item(
                        source_stage="quick_intent",
                        kind="task",
                        task_type="cognition.delegate_deep_thought",
                        route=decision.route,
                        intent=decision.intent,
                        priority=decision.priority,
                        index=0,
                        extra={
                            "quick_confidence": decision.confidence,
                            "reason": decision.reason,
                        },
                    )
                ],
            )
        )
        outputs.append(
            route_stage_output(
                decision,
                stage="deep_thought",
                status="proposed",
                tasks=[
                    _task_item(
                        source_stage="deep_thought",
                        kind="action",
                        task_type="speech.thinking_ack",
                        route=decision.route,
                        intent=decision.intent,
                        priority=decision.priority,
                        index=0,
                        requires_validation=False,
                    ),
                    _task_item(
                        source_stage="deep_thought",
                        kind="task",
                        task_type="cognition.deep_think",
                        route=decision.route,
                        intent=decision.intent,
                        priority=decision.priority,
                        index=1,
                        extra={"candidate_count": len(decision.candidate_capabilities)},
                    ),
                ],
            )
        )
    else:
        outputs.append(route_stage_output(decision, stage="quick_intent"))
    return annotate_stage_outputs(decision, outputs)


def finalize_decision(
    decision: RouteDecision,
    request: RouteRequest | None = None,
    *,
    source: DecisionSource | None = None,
) -> RouteDecision:
    """Fill safe defaults and normalize route flags."""

    if source is not None:
        decision.source = source

    if request is not None and decision.language in ("", "auto", "unknown"):
        decision.language = request.language or detect_language(request.text)

    if not decision.agents:
        decision.agents = default_agents_for_route(decision.route)

    if decision.route == "interrupt":
        decision.priority = "urgent"
        decision.interrupt_current = True
        decision.needs_agent = False
        decision.should_speak = False
        decision.agents = []

    elif decision.route == "ignore":
        decision.needs_agent = False
        decision.should_speak = False
        decision.agents = []

    elif decision.route == "clarify":
        decision.needs_agent = True
        decision.should_speak = True
        if not decision.speak_first:
            decision.speak_first = "你是指什么？" if decision.language.startswith("zh") else "What do you mean?"

    elif decision.route == "deep_thought":
        decision.needs_agent = True
        decision.should_speak = True
        decision.agents = [agent for agent in decision.agents if agent != "conversation_agent"]
        if "deepthinking_agent" not in decision.agents:
            decision.agents.insert(0, "deepthinking_agent")
        if "speaker_agent" not in decision.agents:
            decision.agents.append("speaker_agent")

    else:
        decision.needs_agent = True

    return annotate_default_stage_output(decision)


def detect_language(text: str) -> str:
    text = text or ""
    if any("一" <= ch <= "鿿" for ch in text):
        return "zh-CN"
    if any("Ѐ" <= ch <= "ӿ" for ch in text):
        return "ru-RU"
    return "en-US"
