from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

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


class FastSpeech(BaseModel):
    """A short Router-generated user-facing prelude for fast-first TTS.

    This is a process acknowledgement, not an answer, tool result, memory commit,
    or physical execution claim.
    """

    text: str = ""
    purpose: str | None = None
    language: str | None = None
    commitment: str | None = None
    must_not_claim_completion: bool = True

    @model_validator(mode="before")
    @classmethod
    def accept_bare_text(cls, value: Any) -> Any:
        """Tolerate small-router/review JSON that emits fast_speech as text.

        The prompt asks for an object, but qwen3:4b occasionally returns
        ``"fast_speech": "..."``.  Treat that as a shorthand for
        ``{"text": "..."}`` instead of rejecting an otherwise correct
        route such as weather_query.
        """

        if isinstance(value, str):
            return {"text": value}
        return value

    @model_validator(mode="after")
    def reject_contract_marker_as_spoken_text(self) -> "FastSpeech":
        """Drop enum/contract labels that a small LLM placed in text.

        Values such as ``checking_only`` are routing contract metadata, not
        playable speech.  Clearing the text lets the router repair path or the
        downstream LLM produce natural language instead of speaking the marker.
        """

        marker = "_".join(self.text.strip().casefold().replace("-", "_").split())
        if marker in {
            "checking_only",
            "prelude_only",
            "needs_confirmation",
            "acknowledge",
            "acknowledge_and_check",
            "clarify",
            "thinking",
            "safety_prelude",
        }:
            self.text = ""
        return self


class RouteItem(BaseModel):
    """One semantic route item inside a multi-route decision.

    The top-level RouteDecision.route remains for compatibility. Route items
    let the quick Router split one utterance into independently governed lanes:
    immediate speech, memory, deep thought, tools, or embodied skills.
    """

    route: RouteName
    intent: str = "unknown"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    priority: Priority = "normal"
    lane: str = "agent"
    context_profile: str = "session_compact"
    requires_mind: bool = False
    direct_to_tts: bool = False
    text: str | None = None
    fast_speech: FastSpeech | None = None
    skill_id: str | None = None
    args: dict[str, Any] = Field(default_factory=dict)
    actions: list[dict[str, Any]] = Field(default_factory=list)
    reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RouteDecision(BaseModel):
    """Structured decision consumed by host orchestrator."""

    route: RouteName
    routes: list[RouteItem] = Field(default_factory=list)
    agents: list[str] = Field(default_factory=list)
    intent: str = "unknown"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    language: str = "auto"
    priority: Priority = "normal"
    interrupt_current: bool = False
    needs_agent: bool = True
    should_speak: bool = True
    speak_first: str | None = None
    fast_speech: FastSpeech | None = None
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

    @model_validator(mode="after")
    def populate_speak_first_from_fast_speech(self) -> "RouteDecision":
        if self.speak_first:
            marker = "_".join(str(self.speak_first).strip().casefold().replace("-", "_").split())
            if marker in {
                "checking_only",
                "prelude_only",
                "needs_confirmation",
                "acknowledge",
                "acknowledge_and_check",
                "clarify",
                "thinking",
                "safety_prelude",
            }:
                self.speak_first = None
        if not self.speak_first and self.fast_speech and self.fast_speech.text.strip():
            self.speak_first = self.fast_speech.text.strip()
        return self


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
    for key in (
        "route_item_id",
        "route_item_sequence",
        "lane",
        "context_profile",
        "requires_mind",
        "direct_to_tts",
    ):
        if key in item:
            proposal.metadata[key] = item[key]
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


_ROUTE_ITEM_PRIMARY_RANK: dict[str, int] = {
    "interrupt": 0,
    "robot_action": 1,
    "deep_thought": 2,
    "tool": 3,
    "memory": 4,
    "clarify": 5,
    "chat": 6,
    "ignore": 7,
}


def _route_item_id(index: int, route: str, intent: str) -> str:
    normalized_intent = "_".join((intent or "unknown").strip().split())[:48] or "unknown"
    return f"route_item:{index}:{route}:{normalized_intent}"


def _route_items_from_metadata(decision: RouteDecision) -> list[RouteItem]:
    metadata = decision.metadata if isinstance(decision.metadata, dict) else {}
    raw = metadata.get("route_items")
    if raw is None:
        raw = metadata.get("routes")
    if not isinstance(raw, list):
        return []
    items: list[RouteItem] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            items.append(RouteItem.model_validate(item))
        except Exception:
            continue
    return items


def _default_route_item(decision: RouteDecision) -> RouteItem:
    lane = "agent"
    context_profile = "session_compact"
    requires_mind = False
    direct_to_tts = False
    if decision.route == "chat":
        lane = "immediate_speech" if decision.speak_first else "conversation"
        context_profile = "fast_minimal"
        direct_to_tts = bool(decision.speak_first)
    elif decision.route == "deep_thought":
        lane = "deepthought"
        context_profile = "full_mind"
        requires_mind = True
    elif decision.route == "robot_action":
        lane = "skill_runtime"
        context_profile = "capability_safety"
    elif decision.route == "memory":
        lane = "post_turn"
        context_profile = "session_compact"
    elif decision.route == "tool":
        lane = "tool"
        context_profile = "session_compact"
    elif decision.route == "interrupt":
        lane = "deterministic_control"
        context_profile = "none"
    elif decision.route == "ignore":
        lane = "none"
        context_profile = "none"
    return RouteItem(
        route=decision.route,
        intent=decision.intent,
        confidence=decision.confidence,
        priority=decision.priority,
        lane=lane,
        context_profile=context_profile,
        requires_mind=requires_mind,
        direct_to_tts=direct_to_tts,
        text=decision.speak_first if direct_to_tts else None,
        fast_speech=decision.fast_speech,
        actions=list(decision.actions or []),
        reason=decision.reason,
    )


def _normalized_route_items(decision: RouteDecision) -> list[RouteItem]:
    items = list(decision.routes or [])
    if not items:
        items = _route_items_from_metadata(decision)
    if not items:
        items = [_default_route_item(decision)]

    normalized: list[RouteItem] = []
    for index, item in enumerate(items):
        metadata = dict(item.metadata or {})
        metadata.setdefault("route_item_id", _route_item_id(index, item.route, item.intent))
        if item.route == "deep_thought" and not item.requires_mind:
            item = item.model_copy(update={"requires_mind": item.context_profile == "full_mind"})
        normalized.append(item.model_copy(update={"metadata": metadata}))
    return normalized


def _dominant_route(route_items: list[RouteItem], fallback: str) -> str:
    if not route_items:
        return fallback
    return min(
        [item.route for item in route_items],
        key=lambda route: _ROUTE_ITEM_PRIMARY_RANK.get(route, 99),
    )


def normalize_route_items(decision: RouteDecision) -> RouteDecision:
    route_items = _normalized_route_items(decision)
    dominant = _dominant_route(route_items, decision.route)
    if dominant != decision.route:
        decision.route = dominant  # type: ignore[assignment]
        decision.reason = (
            f"{decision.reason}; " if decision.reason else ""
        ) + "validator selected dominant compatibility route from route_items"
    route_item_dicts = [
        item.model_dump(mode="json", exclude_none=True)
        for item in route_items
    ]
    decision.routes = route_items
    decision.metadata = {
        **(decision.metadata or {}),
        "route_items": route_item_dicts,
        "route_item_count": len(route_item_dicts),
    }
    return decision


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


def _route_item_extra(item: RouteItem, index: int) -> dict[str, Any]:
    route_item_id = str(item.metadata.get("route_item_id") or _route_item_id(index, item.route, item.intent))
    extra: dict[str, Any] = {
        "route_item_id": route_item_id,
        "lane": item.lane,
        "context_profile": item.context_profile,
        "requires_mind": item.requires_mind,
        "direct_to_tts": item.direct_to_tts,
    }
    if item.text:
        extra["text"] = item.text
    if item.fast_speech:
        extra["fast_speech"] = item.fast_speech.model_dump(mode="json", exclude_none=True)
    if item.skill_id:
        extra["capability_id"] = item.skill_id
        extra["args"] = item.args
    if item.reason:
        extra["reason"] = item.reason
    if item.metadata:
        extra["route_item_metadata"] = item.metadata
    return extra


def _task_items_for_route_item(
    item: RouteItem,
    *,
    source_stage: str,
    index: int,
) -> list[dict[str, Any]]:
    route = item.route
    priority = item.priority
    intent = item.intent
    base_extra = _route_item_extra(item, index)
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
                extra=base_extra,
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
                extra=base_extra,
            )
        )
        return tasks

    actions = list(item.actions or [])
    if not actions and item.skill_id:
        actions = [
            {
                "capability_id": item.skill_id,
                "args": item.args,
                "sequence": index,
                "confidence": item.confidence,
            }
        ]

    if route == "robot_action" and actions:
        for action_index, action in enumerate(actions):
            capability_id = str(action.get("capability_id") or "").strip()
            action_type = str(action.get("type") or "").strip()
            args = action.get("args") if isinstance(action.get("args"), dict) else {}
            extra: dict[str, Any] = {
                **base_extra,
                "sequence": _safe_int(action.get("sequence"), action_index),
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
                    index=action_index,
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
                extra={
                    **base_extra,
                    **({"capability_id": capability_id} if capability_id else {}),
                },
            )
        )
        return tasks

    if route == "chat" and item.lane in {"immediate_speech", "fast_tts"} and item.text:
        tasks.append(
            _task_item(
                source_stage=source_stage,
                kind="speech",
                task_type="speech.fast_reply",
                route=route,
                intent=intent,
                priority=priority,
                index=index,
                requires_validation=False,
                extra=base_extra,
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
            extra=base_extra,
        )
    )
    return tasks


def _tasks_for_route_items(
    route_items: list[RouteItem],
    *,
    source_stage: str,
) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for index, item in enumerate(route_items):
        for task in _task_items_for_route_item(
            item,
            source_stage=source_stage,
            index=index,
        ):
            task["route_item_sequence"] = index
            tasks.append(task)
    return tasks


def _tasks_for_decision(decision: RouteDecision, *, source_stage: str) -> list[dict[str, Any]]:
    return _tasks_for_route_items(
        _normalized_route_items(decision),
        source_stage=source_stage,
    )


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
    route_items = [
        item.model_dump(mode="json", exclude_none=True)
        for item in _normalized_route_items(decision)
    ]
    return {
        "stage": stage,
        "status": status,
        "route": decision.route,
        "intent": decision.intent,
        "confidence": decision.confidence,
        "source": decision.source,
        "route_items": route_items,
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
        route_items = _normalized_route_items(decision)
        quick_route_items = [item for item in route_items if item.route != "deep_thought"]
        deep_route_items = [item for item in route_items if item.route == "deep_thought"]
        has_immediate_speech = any(
            item.route == "chat"
            and item.lane in {"immediate_speech", "fast_tts"}
            and item.direct_to_tts
            and bool(item.text)
            for item in quick_route_items
        )
        thinking_ack_allowed = (
            (decision.metadata or {}).get("thinking_ack_allowed") is not False
            and not has_immediate_speech
        )
        if not deep_route_items:
            deep_route_items = [_default_route_item(decision)]
        quick_tasks = _tasks_for_route_items(
            quick_route_items,
            source_stage="quick_intent",
        )
        quick_tasks.append(
            _task_item(
                source_stage="quick_intent",
                kind="task",
                task_type="cognition.delegate_deep_thought",
                route=decision.route,
                intent=decision.intent,
                priority=decision.priority,
                index=len(quick_tasks),
                extra={
                    "quick_confidence": decision.confidence,
                    "reason": decision.reason,
                },
            )
        )
        deep_thought_tasks = [
            {
                **task,
                "candidate_count": len(decision.candidate_capabilities),
            }
            for task in _tasks_for_route_items(
                deep_route_items,
                source_stage="deep_thought",
            )
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
                tasks=quick_tasks,
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

    decision = normalize_route_items(decision)

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
        if decision.metadata.get("llm_clarification_required") is True:
            decision.speak_first = None
            decision.fast_speech = None
            decision.agents = ["conversation_agent", "speaker_agent"]
        elif not decision.speak_first:
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
