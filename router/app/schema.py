from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

try:
    from chromie_contracts.task_proposal import TaskProposal
except ImportError:  # pragma: no cover - repository development path
    from shared.chromie_contracts.task_proposal import TaskProposal


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
    "robot_action": ["capability_agent", "safety_agent", "speaker_agent"],
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
    "post_interrupt_review": 1,
    "quick_intent": 2,
    "deep_thought": 3,
}
ROUTE_MERGE_SCHEMA_VERSION = 1


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


def _is_effectful_task_type(task_type: str) -> bool:
    return (
        task_type in {
            "body.stop_motion",
            "task.cancel_current_action",
            "task.execute_robot_action",
            "task.execute_skill",
            "task.execute_task_graph",
            "task.use_tool",
        }
        or task_type.startswith("body.")
        or task_type.startswith("task.execute")
    )


def _task_proposal_for_item(item: dict[str, Any]) -> dict[str, Any]:
    task_type = str(item.get("task_type") or "unknown").strip() or "unknown"
    source_stage = str(item.get("source_stage") or "router").strip() or "router"
    capability_id = str(item.get("capability_id") or "").strip()
    proposal = TaskProposal(
        id=str(item.get("id") or f"{source_stage}:{task_type}"),
        source=source_stage,
        proposal_kind=str(item.get("kind") or "task"),
        task_type=task_type,
        state="advisory",
        reason="router proposal awaiting Orchestrator merge and commit",
        effectful=_is_effectful_task_type(task_type),
        priority=str(item.get("priority") or "normal"),
        sequence=_safe_int(item.get("merged_sequence"), _safe_int(item.get("sequence"), 0)),
        skill_id=capability_id or None,
        metadata={
            "route": str(item.get("route") or ""),
            "intent": str(item.get("intent") or ""),
            "requires_validation": bool(item.get("requires_validation", True)),
        },
    )
    confidence = item.get("confidence")
    if isinstance(confidence, (int, float)) and not isinstance(confidence, bool):
        proposal.metadata["confidence"] = max(0.0, min(1.0, float(confidence)))
    return proposal.model_dump(mode="json", exclude_none=True)


def _task_proposals_for_items(task_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_task_proposal_for_item(item) for item in task_list if isinstance(item, dict)]


def _desired_ability_items(decision: RouteDecision) -> list[dict[str, Any]]:
    metadata = decision.metadata if isinstance(decision.metadata, dict) else {}
    raw = metadata.get("desired_abilities")
    if raw is None:
        raw = metadata.get("ability_proposals")
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def _state_for_desired_ability_status(status: str) -> str:
    normalized = "_".join(status.strip().lower().split())
    if normalized in {"missing_ability", "known_missing", "not_executable", "unsupported"}:
        return "missing_ability"
    if normalized in {"forbidden", "unsafe", "refused"}:
        return "refused"
    return "advisory"


def _desired_ability_proposals(
    decision: RouteDecision,
    *,
    source_stage: str,
) -> list[dict[str, Any]]:
    proposals: list[dict[str, Any]] = []
    for index, item in enumerate(_desired_ability_items(decision)):
        ability_id = str(
            item.get("ability_id")
            or item.get("desired_ability")
            or item.get("intent")
            or ""
        ).strip()
        if not ability_id:
            continue
        status = str(item.get("status") or "missing_ability")
        confidence = item.get("confidence")
        metadata: dict[str, Any] = {
            "route": decision.route,
            "intent": str(item.get("intent") or decision.intent or ""),
            "status": status,
        }
        matched_skill_id = str(item.get("matched_skill_id") or item.get("skill_id") or "").strip()
        if matched_skill_id:
            metadata["matched_skill_id"] = matched_skill_id
        if isinstance(confidence, (int, float)) and not isinstance(confidence, bool):
            metadata["confidence"] = max(0.0, min(1.0, float(confidence)))
        proposal = TaskProposal(
            id=str(item.get("id") or f"{source_stage}:ability:{index}:{ability_id}"),
            source=source_stage,
            proposal_kind="ability",
            task_type=str(item.get("task_type") or "ability.requested"),
            state=_state_for_desired_ability_status(status),  # type: ignore[arg-type]
            reason=str(
                item.get("reason")
                or "desired ability is understood but not executable from the current catalog"
            ),
            effectful=False,
            priority=str(item.get("priority") or decision.priority or "normal"),
            sequence=_safe_int(item.get("sequence"), index),
            ability_id=ability_id,
            skill_id=matched_skill_id or None,
            metadata=metadata,
        )
        proposals.append(proposal.model_dump(mode="json", exclude_none=True))
    return proposals


def _safe_int(value: Any, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default


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
            extra: dict[str, Any] = {
                "sequence": _safe_int(action.get("sequence"), index)
            }
            if capability_id:
                extra["capability_id"] = capability_id
                extra["args"] = args
                timing = str(action.get("timing") or "").strip()
                if timing:
                    extra["timing"] = timing
                reason = str(action.get("reason") or "").strip()
                if reason:
                    extra["reason"] = reason
            if action_type:
                extra["action_type"] = action_type
                params = action.get("params")
                if isinstance(params, dict):
                    extra["params"] = params
            confidence = action.get("confidence")
            if isinstance(confidence, (int, float)) and not isinstance(confidence, bool):
                extra["confidence"] = max(0.0, min(1.0, float(confidence)))
            task_type = "task.execute_robot_action"
            kind = "action"
            requires_validation = True
            if capability_id:
                task_type = "speech.speak" if capability_id == "chromie.speak" else "task.execute_skill"
                kind = "speech" if capability_id == "chromie.speak" else "action"
                requires_validation = capability_id != "chromie.speak"
            elif action_type:
                task_type = action_type
            tasks.append(
                _task_item(
                    source_stage=source_stage,
                    kind=kind,
                    task_type=task_type,
                    route=route,
                    intent=intent,
                    priority=priority,
                    index=index,
                    requires_validation=requires_validation,
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
    include_desired_abilities: bool = False,
) -> dict[str, Any]:
    task_items = tasks if tasks is not None else _tasks_for_decision(decision, source_stage=stage)
    task_proposals = _task_proposals_for_items(task_items)
    if tasks is None or include_desired_abilities:
        task_proposals.extend(_desired_ability_proposals(decision, source_stage=stage))
    return {
        "stage": stage,
        "status": status,
        "route": decision.route,
        "intent": decision.intent,
        "confidence": decision.confidence,
        "source": decision.source,
        "tasks": task_items,
        "task_proposals": task_proposals,
        "actions": [item for item in task_items if item.get("kind") == "action"],
    }


def passed_stage_output(stage: str) -> dict[str, Any]:
    return {
        "stage": stage,
        "status": "passed",
        "tasks": [],
        "task_proposals": [],
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


def _stage_names(outputs: list[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    for output in outputs:
        if not isinstance(output, dict):
            continue
        stage = str(output.get("stage") or "").strip()
        if stage:
            names.append(stage)
    return names


def _infer_selected_stage(decision: RouteDecision, outputs: list[dict[str, Any]]) -> str | None:
    for output in reversed(outputs):
        if not isinstance(output, dict):
            continue
        if output.get("status") == "passed":
            continue
        if output.get("route") == decision.route:
            return str(output.get("stage") or "") or None
    for output in outputs:
        if not isinstance(output, dict):
            continue
        if output.get("status") != "passed":
            return str(output.get("stage") or "") or None
    return None


def _route_merge_summary(
    decision: RouteDecision,
    outputs: list[dict[str, Any]],
    task_list: list[dict[str, Any]],
    task_proposals: list[dict[str, Any]],
    *,
    strategy: str,
    selected_stage: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "schema_version": ROUTE_MERGE_SCHEMA_VERSION,
        "strategy": strategy,
        "final_route": decision.route,
        "final_intent": decision.intent,
        "final_source": decision.source,
        "selected_stage": selected_stage or _infer_selected_stage(decision, outputs),
        "proposal_count": len([item for item in outputs if isinstance(item, dict)]),
        "task_count": len(task_list),
        "task_proposal_count": len(task_proposals),
        "stages": _stage_names(outputs),
        "task_source_stages": sorted(
            {
                str(item.get("source_stage") or "")
                for item in task_list
                if str(item.get("source_stage") or "").strip()
            },
            key=lambda stage: STAGE_ORDER.get(stage, 99),
        ),
    }
    if reason:
        summary["reason"] = reason
    return summary


def _additional_stage_task_proposals(
    outputs: list[dict[str, Any]],
    generated_task_proposals: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    existing_ids = {
        str(item.get("id") or "").strip()
        for item in generated_task_proposals
        if isinstance(item, dict)
    }
    additional: list[dict[str, Any]] = []
    for stage_output in outputs:
        if not isinstance(stage_output, dict):
            continue
        raw = stage_output.get("task_proposals")
        if not isinstance(raw, list):
            continue
        for proposal in raw:
            if not isinstance(proposal, dict):
                continue
            proposal_id = str(proposal.get("id") or "").strip()
            if not proposal_id or proposal_id in existing_ids:
                continue
            additional.append(proposal)
            existing_ids.add(proposal_id)
    return additional


def annotate_stage_outputs(
    decision: RouteDecision,
    outputs: list[dict[str, Any]],
    *,
    merge_strategy: str = "stage_priority",
    merge_reason: str | None = None,
    selected_stage: str | None = None,
) -> RouteDecision:
    task_list = merge_stage_task_list(outputs)
    task_proposals = _task_proposals_for_items(task_list)
    task_proposals.extend(_additional_stage_task_proposals(outputs, task_proposals))
    decision.metadata = {
        **(decision.metadata or {}),
        "route_stage_outputs": outputs,
        "task_list": task_list,
        "task_proposals": task_proposals,
        "route_merge": _route_merge_summary(
            decision,
            outputs,
            task_list,
            task_proposals,
            strategy=merge_strategy,
            selected_stage=selected_stage,
            reason=merge_reason,
        ),
    }
    return decision


def annotate_default_stage_output(decision: RouteDecision) -> RouteDecision:
    if (decision.metadata or {}).get("route_stage_outputs"):
        return annotate_stage_outputs(
            decision,
            decision.metadata["route_stage_outputs"],
            merge_strategy=str(
                (decision.metadata.get("route_merge") or {}).get("strategy")
                or "preserve_existing_stage_outputs"
            ),
            selected_stage=(decision.metadata.get("route_merge") or {}).get("selected_stage"),
        )
    stage = (
        "emergency_filter"
        if decision.route in {"interrupt", "ignore"} and decision.source == "rules"
        else "deep_thought"
        if decision.route == "deep_thought"
        else "quick_intent"
    )
    return annotate_stage_outputs(
        decision,
        [route_stage_output(decision, stage=stage)],
        merge_strategy="single_stage",
    )


def annotate_pipeline_stage_outputs(
    decision: RouteDecision,
    *,
    emergency_matched: bool = False,
) -> RouteDecision:
    existing_outputs = (decision.metadata or {}).get("route_stage_outputs")
    existing_stages = [
        str(item.get("stage") or "")
        for item in existing_outputs
        if isinstance(item, dict)
    ] if isinstance(existing_outputs, list) else []
    if (
        isinstance(existing_outputs, list)
        and existing_stages
        and existing_stages[0] == "emergency_filter"
        and (emergency_matched or len(existing_stages) > 1)
    ):
        existing_merge = decision.metadata.get("route_merge") or {}
        is_plain_interrupt = emergency_matched and len(existing_stages) == 1
        return annotate_stage_outputs(
            decision,
            existing_outputs,
            merge_strategy=str(
                "safety_interrupt"
                if is_plain_interrupt
                else existing_merge.get("strategy")
                or "preserve_existing_pipeline_outputs"
            ),
            selected_stage=(
                "emergency_filter"
                if is_plain_interrupt
                else existing_merge.get("selected_stage")
            ),
        )

    if emergency_matched:
        return annotate_stage_outputs(
            decision,
            [route_stage_output(decision, stage="emergency_filter", status="triggered")],
            merge_strategy="safety_interrupt",
            selected_stage="emergency_filter",
        )

    outputs: list[dict[str, Any]] = [passed_stage_output("emergency_filter")]
    if decision.route == "deep_thought":
        thinking_ack_allowed = (decision.metadata or {}).get("thinking_ack_allowed") is not False
        deep_thought_tasks = [
            _task_item(
                source_stage="deep_thought",
                kind="task",
                task_type="cognition.deep_think",
                route=decision.route,
                intent=decision.intent,
                priority=decision.priority,
                index=1 if thinking_ack_allowed else 0,
                extra={"candidate_count": len(decision.candidate_capabilities)},
            ),
        ]
        if thinking_ack_allowed:
            deep_thought_tasks.insert(
                0,
                _task_item(
                    source_stage="deep_thought",
                    kind="action",
                    task_type="speech.thinking_ack",
                    route=decision.route,
                    intent=decision.intent,
                    priority=decision.priority,
                    index=0,
                    requires_validation=False,
                    extra={"text": decision.speak_first} if decision.speak_first else None,
                ),
            )
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
                tasks=deep_thought_tasks,
                include_desired_abilities=True,
            )
        )
    else:
        outputs.append(route_stage_output(decision, stage="quick_intent"))
    return annotate_stage_outputs(
        decision,
        outputs,
        merge_strategy=(
            "safety_filter_then_deep_thought"
            if decision.route == "deep_thought"
            else "safety_filter_then_quick_intent"
        ),
    )


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
