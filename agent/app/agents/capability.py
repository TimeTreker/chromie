from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, model_validator

try:
    from chromie_contracts.interaction import SkillRequest
except ImportError:  # pragma: no cover - repository development path
    from shared.chromie_contracts.interaction import SkillRequest

from ..capabilities.validator import normalize_args_for_schema, validate_args_for_schema
from ..schema import AgentResult, AgentRunRequest
from .base import BaseAgent

logger = logging.getLogger("chromie.agent.capability")


class _PlannedSkill(BaseModel):
    skill_id: str
    args: dict[str, Any] = Field(default_factory=dict)


class _CapabilityPlan(BaseModel):
    decision: Literal["execute", "clarify", "unsupported"]
    speech: str = ""
    skills: list[_PlannedSkill] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_skills_for_execute(self) -> "_CapabilityPlan":
        if self.decision != "execute":
            return self
        if not self.skills:
            raise ValueError("decision=execute requires at least one skill")
        speech = _natural_speech_or_empty(self.speech)
        if not speech:
            raise ValueError("decision=execute requires natural speech")
        self.speech = speech
        return self


class _CapabilityPlanReview(BaseModel):
    decision: Literal["accept", "revise", "clarify", "unsupported"]
    reason: str = ""
    speech: str = ""
    skills: list[_PlannedSkill] = Field(default_factory=list)


def _natural_speech_or_empty(value: str) -> str:
    text = " ".join((value or "").strip().split())
    if not text:
        return ""
    label = text.strip(" .!?:;，。！？：；").lower().replace("-", "_")
    if label in {"unsupported", "not_supported", "clarify", "execute", "none", "null", "n/a", "na"}:
        return ""
    return text


class CapabilityAgent(BaseAgent):
    """Select exact executable capabilities from the shared catalog."""

    name = "capability_agent"

    async def run(self, request: AgentRunRequest, result: AgentResult) -> AgentResult:
        catalog = self.services.capability_catalog
        add_skill = getattr(result, "add_skill", None)
        if catalog is None or not callable(add_skill):
            return result

        search_text = self._capability_search_text(request)
        search = await catalog.search(
            search_text,
            language=self.language(request),
            limit=self.services.capability_match_limit,
            min_score=0.0,
            prefer_interaction_executable=True,
        )
        request.route_decision.candidate_capabilities = [
            match.model_dump(mode="json") for match in search.matches
        ]
        matched_executable = [
            match for match in search.matches if match.interaction_executable
        ]
        executable = self._available_executable_capabilities(catalog, matched_executable)
        request.route_decision.candidate_capabilities = [
            self._capability_payload(match) for match in executable
        ]
        direct_actions = list(request.route_decision.actions or [])
        if direct_actions:
            allowed = {match.capability_id: match for match in executable}
            selected_ids: list[str] = []
            for action in sorted(
                direct_actions,
                key=lambda item: int(item.get("sequence", 0)),
            ):
                capability_id = str(action.get("capability_id") or "").strip()
                match = allowed.get(capability_id)
                if match is None:
                    result.metadata["capability_handled"] = True
                    result.metadata["capability_decision"] = "blocked"
                    result.metadata["invalid_selected_capability_id"] = capability_id
                    self.trace(
                        result,
                        f"router action capability is unavailable or non-executable: {capability_id}",
                    )
                    return result
                args = action.get("args")
                if not isinstance(args, dict):
                    args = {}
                args, normalized = normalize_args_for_schema(args, match.input_schema)
                arg_errors = validate_args_for_schema(args, match.input_schema)
                if arg_errors:
                    result.add_speak_immediate(
                        self._invalid_args_speech(request),
                        style="brief",
                    )
                    result.metadata["capability_handled"] = True
                    result.metadata["capability_decision"] = "clarify"
                    result.metadata["invalid_capability_args"] = {
                        "skill_id": capability_id,
                        "errors": arg_errors,
                    }
                    self.trace(
                        result,
                        f"router action args failed schema validation for {capability_id}: {arg_errors}",
                    )
                    return result
                metadata = {
                    "source": "router_actions",
                    "catalog_version": search.catalog_version,
                    "sequence": int(action.get("sequence", len(selected_ids))),
                }
                action_confidence = action.get("confidence")
                if isinstance(action_confidence, (int, float)) and not isinstance(action_confidence, bool):
                    metadata["router_action_confidence"] = max(
                        0.0,
                        min(1.0, float(action_confidence)),
                    )
                timing = str(action.get("timing") or "").strip()
                if timing not in {"parallel", "sequential"}:
                    timing = "sequential"
                metadata["router_action_timing"] = timing
                score = self._catalog_score(match)
                if score is not None:
                    metadata["catalog_score"] = score
                if normalized:
                    metadata["schema_normalized_args"] = True
                add_skill(
                    SkillRequest(
                        skill_id=capability_id,
                        args=args,
                        timing=timing,  # type: ignore[arg-type]
                        requires_confirmation=match.requires_confirmation,
                        metadata=metadata,
                    )
                )
                selected_ids.append(capability_id)
            if selected_ids:
                speech = (
                    ""
                    if request.route_decision.speak_first or "chromie.speak" in selected_ids
                    else self._direct_action_ack_speech(request, len(selected_ids))
                )
                if speech:
                    result.add_speak_immediate(speech, style="brief")
                result.metadata["capability_handled"] = True
                result.metadata["capability_decision"] = "execute"
                result.metadata["capability_catalog_version"] = search.catalog_version
                result.metadata["capability_selected"] = selected_ids
                self.trace(result, f"accepted {len(selected_ids)} router capability action(s)")
                return result

        selected_id = ""
        intent = (request.route_decision.intent or "").strip()
        if intent.startswith("capability:"):
            selected_id = intent[len("capability:") :].strip()
        if selected_id:
            selected = [
                match for match in executable if match.capability_id == selected_id
            ]
            if not selected:
                result.metadata["capability_handled"] = True
                result.metadata["capability_decision"] = "blocked"
                result.metadata["invalid_selected_capability_id"] = selected_id
                self.trace(
                    result,
                    f"router-selected capability is unavailable or non-executable: {selected_id}",
                )
                return result
            self.trace(result, f"router-selected capability is available: {selected_id}")
        if not executable:
            result.metadata["capability_search"] = search.model_dump(mode="json")
            self.trace(result, "no interaction-executable capability matched")
            return result

        batched_count_metadata: dict[str, Any] | None = None
        fast_path_metadata: dict[str, Any] | None = None
        fast_path = self._fast_router_task_plan(request, executable)
        if fast_path is not None:
            plan, fast_path_metadata = fast_path
            if fast_path_metadata.get("source") == "exact_routed_count_batch_recovery":
                batched_count_metadata = {
                    key: fast_path_metadata[key]
                    for key in (
                        "skill_id",
                        "requested_count",
                        "max_per_call",
                        "batch_count",
                        "batches",
                        "source",
                    )
                    if key in fast_path_metadata
                }
        else:
            if not self.services.use_llm or self.services.ollama is None:
                self.trace(result, "capability match found but LLM selection is unavailable")
                return result

            plan = await self._plan(request, executable)
            plan = await self._review_plan(request, plan, executable)
            plan = self._normalize_plan_for_routed_surface(request, plan, executable)
            batched_recovery = self._recover_batched_over_limit_count_plan(
                request,
                plan,
                executable,
            )
            if batched_recovery is not None:
                plan, batched_count_metadata = batched_recovery
        allowed = {match.capability_id: match for match in executable}
        if plan.decision != "execute":
            speech = self._natural_plan_speech(plan.speech)
            if speech:
                result.add_speak_immediate(speech, style="brief")
                result.metadata["capability_handled"] = True
            elif plan.decision == "unsupported" and "conversation_agent" in request.route_decision.agents:
                result.metadata["capability_handled"] = False
            else:
                result.add_speak_immediate(
                    self._unsupported_action_speech(request),
                    style="brief",
                )
                result.metadata["capability_handled"] = True
            result.metadata["capability_decision"] = plan.decision
            self.trace(result, f"capability decision={plan.decision}")
            return result

        selected = 0
        selected_requests: list[SkillRequest] = []
        seen_requests: set[tuple[str, str]] = set()
        for item in plan.skills:
            match = allowed.get(item.skill_id)
            if match is None:
                logger.warning("LLM selected capability outside candidate set: %s", item.skill_id)
                continue
            args, normalized = normalize_args_for_schema(item.args, match.input_schema)
            arg_errors = validate_args_for_schema(args, match.input_schema)
            if arg_errors:
                logger.warning("LLM selected invalid args for %s: %s", item.skill_id, arg_errors)
                result.add_speak_immediate(
                    self._invalid_args_speech(request),
                    style="brief",
                )
                result.metadata["capability_handled"] = True
                result.metadata["capability_decision"] = "clarify"
                result.metadata["invalid_capability_args"] = {
                    "skill_id": item.skill_id,
                    "errors": arg_errors,
                }
                self.trace(
                    result,
                    f"LLM capability args failed schema validation for {item.skill_id}: {arg_errors}",
                )
                return result
            dedupe_key = (item.skill_id, self._canonical_args_key(args))
            if batched_count_metadata is None and dedupe_key in seen_requests:
                self.trace(result, f"deduped repeated capability request: {item.skill_id}")
                continue
            seen_requests.add(dedupe_key)
            metadata = {
                "source": "capability_catalog",
                "catalog_version": search.catalog_version,
            }
            if fast_path_metadata is not None:
                metadata["source"] = str(
                    fast_path_metadata.get("source") or "router_task_list_fast_path"
                )
                for key in (
                    "route_task_id",
                    "route_task_source_stage",
                    "route_confidence",
                    "router_source",
                    "fast_path_reason",
                ):
                    if key in fast_path_metadata:
                        metadata[key] = fast_path_metadata[key]
            score = self._catalog_score(match)
            if score is not None:
                metadata["catalog_score"] = score
            if batched_count_metadata is not None:
                metadata.update(
                    {
                        "batched_over_limit": True,
                        "batch_index": selected + 1,
                        "batch_count": batched_count_metadata["batch_count"],
                        "requested_count": batched_count_metadata["requested_count"],
                        "max_per_call": batched_count_metadata["max_per_call"],
                    }
                )
            if normalized:
                metadata["schema_normalized_args"] = True
            request_item = SkillRequest(
                skill_id=item.skill_id,
                args=args,
                timing="sequential",
                requires_confirmation=match.requires_confirmation,
                metadata=metadata,
            )
            add_skill(request_item)
            selected_requests.append(request_item)
            selected += 1

        if selected == 0:
            self.trace(result, "LLM produced no valid capability selection")
            return result

        speech = self._natural_plan_speech(plan.speech)
        if speech:
            result.add_speak_immediate(speech, style="brief")
        result.metadata["capability_handled"] = True
        result.metadata["capability_decision"] = "execute"
        result.metadata["capability_catalog_version"] = search.catalog_version
        result.metadata["capability_selected"] = [
            item.skill_id for item in selected_requests
        ]
        if batched_count_metadata is not None:
            result.metadata["capability_batched_over_limit"] = batched_count_metadata
        if fast_path_metadata is not None:
            result.metadata["capability_fast_path"] = fast_path_metadata
        self.trace(result, f"selected {selected} catalog capability request(s)")
        return result

    async def _review_plan(
        self,
        request: AgentRunRequest,
        plan: _CapabilityPlan,
        candidates: list[Any],
    ) -> _CapabilityPlan:
        if plan.decision != "execute":
            return plan
        mandatory_review = self._requires_robot_action_review(request, plan)
        exact_intent_substitution = self._requires_exact_intent_review(
            request,
            plan,
            candidates,
        )
        reviewer = self.services.response_reviewer
        if reviewer is None:
            if mandatory_review:
                logger.warning(
                    "capability plan review is required but unavailable; blocking execution sid=%s route=%s intent=%s plan=%s",
                    request.sid,
                    request.route_decision.route,
                    request.route_decision.intent,
                    [item.skill_id for item in plan.skills],
                )
                return self._review_unavailable_plan(request)
            return plan

        zh = self.is_zh(request)
        candidate_payload = [self._capability_payload(match) for match in candidates]
        selected_id = self._router_selected_capability_id(request)
        selected_line = (
            f"- Router-selected exact skill_id: {selected_id}\n"
            if selected_id
            else "- Router-selected exact skill_id: none\n"
        )
        review_prompt = (
            "Session Context Group:\n"
            f"- Language: {self.language(request)}\n"
            f"- Extracted memory:\n{self._bounded_text(self._format_memory_context(request, zh=zh), 900)}\n"
            f"- Task context:\n{self._bounded_text(self._format_task_context(request, zh=zh), 900)}\n"
            f"- Router decision context JSON: {self._format_route_context(request)}\n\n"
            "Current Job:\n"
            "- You are Chromie's semantic capability-plan reviewer.\n"
            "- Judge whether the proposed skill sequence directly preserves and satisfies the user's intended physical/tool action.\n"
            "- Generalize from meaning, context, capability descriptions, schemas, and task memory; do not use keyword or phrase rules.\n"
            "- If the user request is complex enough to need deeper planning, or if a safe executable plan is not clear, revise to clarify or unsupported with no skills.\n\n"
            "Task Context Group:\n"
            f"- Latest user input: {request.text}\n"
            f"{selected_line}"
            f"- Available capability API surface: {json.dumps(candidate_payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))}\n"
            f"- Proposed capability plan JSON: {plan.model_dump_json()}\n\n"
            "Cost Function:\n"
            "- Accept only when every selected skill is semantically necessary for the user's request and its arguments fit the schema.\n"
            "- If the Router selected an exact skill_id and the proposed plan replaced it, do not use decision=accept. Revise to an executable plan that preserves the routed intent, or return clarify/unsupported with no skills.\n"
            "- Reject or revise plans that substitute a different behavior class for the user's intent, such as social acknowledgement, gaze, or attention when the user requested locomotion or another body task.\n"
            "- Prefer a clarification over executing a skill that merely seems generally robot-like but does not satisfy the request.\n"
            "- Preserve the no-raw-motor boundary and never invent skills outside the supplied API surface.\n\n"
            "Output Contract:\n"
            "- Return JSON only with keys decision, reason, speech, and skills.\n"
            "- decision=accept keeps the original plan; use empty speech and skills.\n"
            "- decision=revise replaces the original plan and must include natural speech plus one or more exact candidate skills with schema-valid args.\n"
            "- decision=clarify or unsupported blocks execution; include natural speech and no skills.\n"
            "- Spoken speech must be brief and must not expose internal skill IDs."
        )
        system = (
            "You are Chromie's semantic safety reviewer for capability plans. "
            "Preserve intent by meaning, not phrase rules. Return compact JSON only. "
            "Do not authorize raw motor, joint, actuator, controller-array, position-array, or torque commands."
        )
        try:
            raw = await reviewer.generate(
                review_prompt,
                system=system,
                response_format="json",
                options={
                    "temperature": 0,
                    "top_p": 0.8,
                    "num_predict": int(os.getenv("AGENT_CAPABILITY_REVIEW_NUM_PREDICT", "160")),
                },
            )
        except Exception as exc:
            logger.warning(
                "capability plan review failed%s: error_type=%s error=%s",
                "; blocking exact-intent substitution"
                if exact_intent_substitution
                else "; blocking required robot action review"
                if mandatory_review
                else "; preserving primary plan",
                type(exc).__name__,
                exc,
            )
            if mandatory_review:
                return self._review_unavailable_plan(request)
            return plan
        try:
            review = _CapabilityPlanReview.model_validate(raw)
        except ValidationError as exc:
            logger.warning(
                "invalid capability plan review%s: %s",
                "; blocking exact-intent substitution"
                if exact_intent_substitution
                else "; blocking required robot action review"
                if mandatory_review
                else "; preserving primary plan",
                exc,
            )
            if mandatory_review:
                return self._review_unavailable_plan(request)
            return plan

        if review.decision == "accept":
            if exact_intent_substitution:
                logger.warning(
                    "capability plan reviewer accepted an exact-intent substitution; blocking execution sid=%s intent=%s plan=%s reason=%r",
                    request.sid,
                    request.route_decision.intent,
                    [item.skill_id for item in plan.skills],
                    review.reason[:200],
                )
                return self._review_unavailable_plan(request)
            return plan

        speech = self._natural_plan_speech(review.speech)
        if review.decision == "revise":
            try:
                return _CapabilityPlan(
                    decision="execute",
                    speech=speech,
                    skills=review.skills,
                )
            except ValidationError as exc:
                logger.warning("capability plan review produced invalid revision: %s", exc)
                return _CapabilityPlan(
                    decision="clarify",
                    speech=(
                        "请再说明一下你希望我做什么。"
                        if zh
                        else "Please clarify what action you want me to perform."
                    ),
                )

        if not speech:
            speech = (
                "这个动作需要再确认一下，请你更具体地说。"
                if zh
                else "Please clarify the action before I move."
            )
        return _CapabilityPlan(decision=review.decision, speech=speech)

    def _requires_robot_action_review(
        self,
        request: AgentRunRequest,
        plan: _CapabilityPlan,
    ) -> bool:
        if not self.services.require_capability_plan_review:
            return False
        if request.route_decision.route != "robot_action":
            return False
        return plan.decision == "execute" and bool(plan.skills)

    def _router_selected_capability_id(self, request: AgentRunRequest) -> str:
        intent = (request.route_decision.intent or "").strip()
        if not intent.startswith("capability:"):
            return ""
        return intent[len("capability:") :].strip()

    def _requires_exact_intent_review(
        self,
        request: AgentRunRequest,
        plan: _CapabilityPlan,
        candidates: list[Any],
    ) -> bool:
        if not self.services.require_capability_plan_review:
            return False
        if request.route_decision.route != "robot_action":
            return False
        selected_id = self._router_selected_capability_id(request)
        if not selected_id:
            return False
        candidate_ids = {str(getattr(match, "capability_id", "")) for match in candidates}
        if selected_id not in candidate_ids:
            return False
        planned_ids = {item.skill_id for item in plan.skills}
        return bool(planned_ids) and selected_id not in planned_ids

    def _review_unavailable_plan(self, request: AgentRunRequest) -> _CapabilityPlan:
        if self.is_zh(request):
            return _CapabilityPlan(
                decision="clarify",
                speech="这个动作计划没有可靠的复核结果，所以我不会移动。",
            )
        return _CapabilityPlan(
            decision="clarify",
            speech="That motion plan did not get a reliable review result, so I will not move.",
        )

    def _direct_action_ack_speech(self, request: AgentRunRequest, action_count: int) -> str:
        if action_count <= 0:
            return ""
        if self.is_zh(request):
            return "我会按顺序执行这些动作。" if action_count > 1 else "我会执行这个动作。"
        return (
            "I will run the selected actions in order."
            if action_count > 1
            else "I will run that action."
        )

    def _format_session_context(self, request: AgentRunRequest) -> str:
        context = dict(request.context or {})
        context.pop("mind", None)
        context.pop("candidate_capabilities", None)
        context.pop("history", None)
        context.pop("conversation", None)
        memory = context.get("session_memory")
        if isinstance(memory, dict):
            context["session_memory"] = {
                key: value
                for key, value in memory.items()
                if key not in {"recent_user_request", "recent_assistant_response"}
            }
        return self._bounded_json(context, 1000)

    def _format_route_context(self, request: AgentRunRequest) -> str:
        route = request.route_decision
        payload = {
            "route": route.route,
            "intent": route.intent,
            "confidence": route.confidence,
            "language": route.language,
            "source": route.source,
            "reason": route.reason,
            "metadata": route.metadata,
            "actions": route.actions,
        }
        return self._bounded_json(payload, 800)

    def _format_global_context(self, request: AgentRunRequest, *, zh: bool) -> str:
        mind = self.mind_context(request)
        summary = " ".join(str(mind.get("prompt_summary") or "").split()) if mind else ""
        if len(summary) > 220:
            summary = summary[:220].rstrip() + "..."
        identity = mind.get("identity") if isinstance(mind.get("identity"), dict) else {}
        profile = {
            "profile_id": mind.get("profile_id"),
            "version": mind.get("version"),
            "owner_approved": mind.get("owner_approved"),
        }
        none_text = "无" if zh else "None"
        return (
            "Mind Profile:\n"
            f"{self._bounded_json(profile, 180)}\n\n"
            "Robot Identity:\n"
            f"{self._bounded_json(identity or none_text, 220)}\n\n"
            "Worldview:\n"
            "- Chromie is an embodied realtime robot. Use only supplied runtime context and abilities as evidence.\n"
            "- Never claim unsupported perception, memory, execution, or runtime facts.\n\n"
            "Lifeview:\n"
            f"{self._bounded_json(mind.get('long_term_goals') or none_text, 180)}\n\n"
            "Valueview:\n"
            f"{self._bounded_json(mind.get('core_principles') or none_text, 260)}\n\n"
            "Core Runtime Principles:\n"
            "- Plan by meaning, context, ability descriptions, and schemas; phrase rules are only for emergency/noise controls outside this planner.\n"
            "- Memory, identity, and preferences guide interpretation but never authorize side effects.\n"
            "- Never invent abilities or raw motor/joint/actuator/controller-array/torque commands.\n\n"
            "Owner-Approved Mind Summary:\n"
            f"{summary or none_text}"
        )

    async def _plan(self, request: AgentRunRequest, candidates: list[Any]) -> _CapabilityPlan:
        assert self.services.ollama is not None
        zh = self.is_zh(request)
        global_context_block = self._format_global_context(request, zh=zh)
        session_context_block = self._format_session_context(request)
        route_context_block = self._format_route_context(request)
        task_context_block = self._format_task_context(request, zh=zh)
        memory_block = self._format_memory_context(request, zh=zh)
        candidate_payload = [self._capability_payload(match) for match in candidates]
        selected_id = ""
        intent = (request.route_decision.intent or "").strip()
        if intent.startswith("capability:"):
            selected_id = intent[len("capability:") :].strip()
        selected_line = (
            f"Router-selected exact skill_id: {selected_id}\n"
            if selected_id
            else "Router-selected exact skill_id: none\n"
        )
        system = (
            "You are Chromie's capability selection agent. The prompt is organized as Global Context Group, Session Context Group, Current Job, Task Context Group, Cost Function, and Output Contract. "
            "Read the upper context first, then solve the current job, then return only the contract. "
            "Generalization-first principle: infer the user's desired physical/tool action from meaning, context, capability descriptions, and input_schema; do not turn prompt wording into phrase rules. "
            "Select only exact skill_id values from the provided candidates. Never invent a skill. "
            "Never output raw joint, motor, actuator, controller-array, position-array, or torque controls. "
            "Schema obedience is more important than copying the user's words. "
            "Return compact JSON only."
        )
        prompt = (
            "Global Context Group:\n"
            f"{global_context_block}\n\n"
            "Additional Robot Worldview:\n"
            "- Do not claim a physical action is happening unless you output an executable skill request that downstream runtime can validate.\n"
            "- Do not claim perception, memory, or execution evidence absent from context.\n\n"
            "Session Context Group:\n"
            f"- Language: {'zh-CN' if zh else 'en-US'}\n"
            f"- Session id: {request.sid or ''}\n"
            f"- Extracted memory:\n{memory_block}\n"
            f"- Task context:\n{task_context_block}\n"
            f"- Router decision context JSON: {route_context_block}\n"
            f"- Bounded session/runtime context JSON: {session_context_block}\n\n"
            "Current Job:\n"
            "- You are now acting as Chromie's capability planner.\n"
            "- Use the upper context as background; output execute, clarify, or unsupported.\n"
            "- Do not answer unrelated chat here; return unsupported with no skills when no physical/tool skill should run.\n\n"
            "Task Context Group:\n"
            f"- Latest user input: {request.text}\n"
            f"- {selected_line.rstrip()}\n"
            f"- Available capability API surface: {json.dumps(candidate_payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))}\n"
            "- Ability interpretation: choose only from the provided skill_id values and satisfy that candidate's input_schema.\n"
            "- If Router-selected exact skill_id is best, use it; if another candidate better satisfies the action/schema, choose that candidate.\n"
            "- Polite ability-shaped requests can be action requests when they ask Chromie to perform a listed physical action now.\n"
            "- For questions, identity/status, greetings, jokes, stories, songs, or other speech-only conversation, return unsupported with no skills.\n"
            "- Never combine an unrelated spoken answer with a body skill.\n"
            "- Use recent conversation/task context for follow-ups; distinguish gaze/attention/orientation from locomotion by meaning and descriptions.\n\n"
            "Cost Function:\n"
            "- Choose the smallest validated set of executable skills.\n"
            "- Prefer human-facing wrapper skills over lower-level velocity/control skills when both satisfy the request.\n"
            "- Preserve the user's intended action class. Do not use social acknowledgement, gaze, attention, or idle gestures as fallback actions for an unrelated body request.\n"
            "- If the request needs deeper task decomposition, runtime evidence, or a multi-session plan, clarify or return unsupported instead of guessing a physical skill.\n"
            "- Clarify when a required parameter is missing; unsupported when no candidate can satisfy the request.\n"
            "- Prefer natural, brief speech that accurately describes only the selected plan.\n\n"
            "Output Contract:\n"
            "- Return JSON only with keys decision, speech, and skills.\n"
            "- decision must be execute, clarify, or unsupported.\n"
            "- When decision is execute, skills is required and must contain at least one item. Never return execute with skills omitted, empty, null, or only speech.\n"
            "- Each execute item must be {\"skill_id\":\"<exact candidate skill_id>\",\"args\":{...}}.\n"
            "- For execute, every skills item must contain skill_id and args satisfying that candidate's input_schema.\n"
            "- For execute, speech is required: write one natural brief sentence generated from the chosen capability descriptions, user wording, and validated args.\n"
            "- Execution speech must be a short acknowledgement, not an implementation explanation; do not include Task Split, Key Risk, Next Step, internal skill IDs, schema field names, or raw args.\n"
            "- Do not depend on downstream code to convert skill_id or args into spoken wording; this planner owns the execution speech.\n"
            "- Every enum argument must be copied exactly from that field's enum list in input_schema.\n"
            "- Map natural wording to enum tokens by semantic meaning; never output words outside the enum.\n"
            "- The speech field is spoken aloud. Never put status labels such as unsupported, clarify, execute, null, or none in speech.\n"
            "- For unsupported, either leave speech empty so conversation_agent can answer, or give one natural sentence explaining the runtime limitation."
        )
        try:
            raw = await self.services.ollama.generate(
                prompt,
                system=system,
                response_format="json",
                options={
                    "temperature": 0,
                    "top_p": 0.8,
                    "num_ctx": int(os.getenv("AGENT_CAPABILITY_NUM_CTX", "24576")),
                    "num_predict": int(os.getenv("AGENT_CAPABILITY_NUM_PREDICT", "512")),
                },
            )
        except Exception as exc:
            logger.warning(
                "capability planner LLM failed; returning clarification: error_type=%s error=%s",
                type(exc).__name__,
                exc,
            )
            return _CapabilityPlan(
                decision="clarify",
                speech=(
                    "我听到了这个动作请求，但没有生成有效的动作指令，所以我不会移动。"
                    if zh
                    else "I heard the movement request, but I could not produce a valid motion command, so I will not move."
                ),
            )
        try:
            return _CapabilityPlan.model_validate(raw)
        except ValidationError as exc:
            logger.warning("invalid capability plan: %s", exc)
            return _CapabilityPlan(
                decision="clarify",
                speech=(
                    "请再说明一下你希望我做什么。"
                    if zh
                    else "Please clarify what action you want me to perform."
                ),
            )

    def _available_executable_capabilities(self, catalog: Any, matched: list[Any]) -> list[Any]:
        by_id: dict[str, Any] = {}
        for match in matched:
            by_id[str(match.capability_id)] = match
        entries = catalog.entries() if hasattr(catalog, "entries") else []
        for entry in entries:
            if not getattr(entry, "available", False):
                continue
            if not getattr(entry, "interaction_executable", False):
                continue
            by_id.setdefault(str(entry.capability_id), entry)
        return sorted(
            by_id.values(),
            key=lambda item: (
                self._catalog_score(item) or 0.0,
                str(getattr(item, "capability_id", "")),
            ),
            reverse=True,
        )

    def _normalize_plan_for_routed_surface(
        self,
        request: AgentRunRequest,
        plan: _CapabilityPlan,
        candidates: list[Any],
    ) -> _CapabilityPlan:
        if plan.decision != "execute" or not plan.skills:
            return plan
        candidate_by_id = {
            str(getattr(match, "capability_id", "") or ""): match
            for match in candidates
        }
        if "soridormi.look_at_person" not in candidate_by_id:
            return plan
        context_candidates = request.context.get("capability_candidates")
        if not isinstance(context_candidates, list):
            context_candidates = []
        routed_candidate_ids = {
            str(item.get("capability_id") or "")
            for item in context_candidates
            if isinstance(item, dict)
        }
        routed_candidate_ids.update(
            str(item.get("capability_id") or "")
            for item in request.route_decision.candidate_capabilities
            if isinstance(item, dict)
        )
        if "soridormi.look_at_person" not in routed_candidate_ids:
            return plan

        changed = False
        normalized_skills: list[_PlannedSkill] = []
        for item in plan.skills:
            if item.skill_id != "soridormi.look_direction":
                normalized_skills.append(item)
                continue
            args = self._look_direction_args_to_person_target_args(
                item.args,
                candidate_by_id["soridormi.look_at_person"],
            )
            normalized_skills.append(
                _PlannedSkill(skill_id="soridormi.look_at_person", args=args)
            )
            changed = True
        if not changed:
            return plan
        try:
            return _CapabilityPlan(
                decision=plan.decision,
                speech=plan.speech,
                skills=normalized_skills,
            )
        except ValidationError:
            return plan

    def _look_direction_args_to_person_target_args(
        self,
        args: dict[str, Any],
        target: Any,
    ) -> dict[str, Any]:
        schema = getattr(target, "input_schema", {}) or {}
        properties = schema.get("properties") if isinstance(schema, dict) else {}
        if not isinstance(properties, dict):
            properties = {}
        out: dict[str, Any] = {}
        yaw = args.get("head_yaw_rad", args.get("yaw_rad", args.get("target_yaw_rad")))
        if isinstance(yaw, (int, float)) and not isinstance(yaw, bool):
            out["target_yaw_rad"] = self._clamp_number_for_schema(
                float(yaw),
                properties.get("target_yaw_rad"),
            )
        pitch = args.get("head_pitch_rad", args.get("pitch_rad", args.get("target_pitch_rad")))
        if isinstance(pitch, (int, float)) and not isinstance(pitch, bool):
            out["target_pitch_rad"] = self._clamp_number_for_schema(
                float(pitch),
                properties.get("target_pitch_rad"),
            )
        duration = args.get("duration_s")
        if isinstance(duration, (int, float)) and not isinstance(duration, bool):
            out["duration_s"] = self._clamp_number_for_schema(
                float(duration),
                properties.get("duration_s"),
            )
        return out

    @staticmethod
    def _clamp_number_for_schema(value: float, schema: Any) -> float:
        if not isinstance(schema, dict):
            return value
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if isinstance(minimum, (int, float)) and not isinstance(minimum, bool):
            value = max(float(minimum), value)
        if isinstance(maximum, (int, float)) and not isinstance(maximum, bool):
            value = min(float(maximum), value)
        return value

    def _fast_router_task_plan(
        self,
        request: AgentRunRequest,
        candidates: list[Any],
    ) -> tuple[_CapabilityPlan, dict[str, Any]] | None:
        if request.route_decision.route != "robot_action":
            return None
        selected_id = self._router_selected_capability_id(request)
        if not selected_id:
            return None
        route_task = self._route_task_list_item_for_skill(request, selected_id)
        if route_task is None:
            return None
        if request.route_decision.confidence < self._fast_tasklist_confidence_threshold():
            return None
        target = next(
            (
                match
                for match in candidates
                if str(getattr(match, "capability_id", "") or "") == selected_id
            ),
            None,
        )
        if target is None or not self._can_fast_execute_router_skill(target):
            return None

        over_limit = self._fast_over_limit_count_plan(request, target, route_task)
        if over_limit is not None:
            return over_limit

        args = self._fast_router_args(request, target)
        if args is None:
            return None
        args, _normalized = normalize_args_for_schema(args, getattr(target, "input_schema", {}) or {})
        if validate_args_for_schema(args, getattr(target, "input_schema", {}) or {}):
            return None
        speech = self._fast_router_speech(request, target, args)
        try:
            plan = _CapabilityPlan(
                decision="execute",
                speech=speech,
                skills=[_PlannedSkill(skill_id=selected_id, args=args)],
            )
        except ValidationError:
            return None
        return plan, self._route_task_metadata(
            request,
            route_task,
            selected_id,
            source="router_task_list_fast_path",
            fast_path_reason="exact low-risk router task with deterministic schema args",
        )

    def _fast_over_limit_count_plan(
        self,
        request: AgentRunRequest,
        target: Any,
        route_task: dict[str, Any],
    ) -> tuple[_CapabilityPlan, dict[str, Any]] | None:
        if not self._can_batch_over_limit_count_skill(target):
            return None
        selected_id = str(getattr(target, "capability_id", "") or "")
        schema = getattr(target, "input_schema", {}) or {}
        properties = schema.get("properties") if isinstance(schema, dict) else {}
        count_schema = properties.get("count") if isinstance(properties, dict) else None
        if not isinstance(count_schema, dict):
            return None
        maximum = count_schema.get("maximum")
        if not isinstance(maximum, (int, float)) or isinstance(maximum, bool):
            return None
        max_count = int(maximum)
        if max_count <= 0:
            return None
        requested_count = self._extract_requested_count(request.text)
        if requested_count is None or requested_count <= max_count:
            return None
        minimum = count_schema.get("minimum")
        min_count = (
            int(minimum)
            if isinstance(minimum, (int, float)) and not isinstance(minimum, bool)
            else 1
        )
        if min_count <= 0:
            min_count = 1
        chunks = self._split_count_into_schema_batches(
            requested_count,
            min_count=min_count,
            max_count=max_count,
        )
        if chunks is None:
            return None
        speech = self._batched_count_speech(
            request,
            target,
            requested_count=requested_count,
            max_count=max_count,
            batch_count=len(chunks),
        )
        try:
            plan = _CapabilityPlan(
                decision="execute",
                speech=speech,
                skills=[
                    _PlannedSkill(skill_id=selected_id, args={"count": chunk})
                    for chunk in chunks
                ],
            )
        except ValidationError:
            return None
        metadata = self._route_task_metadata(
            request,
            route_task,
            selected_id,
            source="exact_routed_count_batch_recovery",
            fast_path_reason="exact router task count exceeds schema maximum and is batchable",
        )
        metadata.update(
            {
                "requested_count": requested_count,
                "max_per_call": max_count,
                "batch_count": len(chunks),
                "batches": chunks,
            }
        )
        return plan, metadata

    def _fast_router_args(self, request: AgentRunRequest, target: Any) -> dict[str, Any] | None:
        schema = getattr(target, "input_schema", {}) or {}
        if not isinstance(schema, dict):
            return None
        properties = schema.get("properties")
        if not isinstance(properties, dict):
            properties = {}
        required = schema.get("required")
        required_fields = {str(item) for item in required} if isinstance(required, list) else set()
        if not required_fields.issubset({"count"}):
            return None
        if not self._optional_fast_fields_are_omittable(properties, required_fields):
            return None
        count_schema = properties.get("count")
        if not isinstance(count_schema, dict):
            return {} if not required_fields else None
        requested_count = self._extract_requested_count(request.text)
        if requested_count is None:
            default_count = self._positive_int(count_schema.get("default"))
            requested_count = default_count
        if requested_count is None:
            return None if "count" in required_fields else {}
        minimum = count_schema.get("minimum")
        if isinstance(minimum, (int, float)) and not isinstance(minimum, bool):
            if requested_count < int(minimum):
                return None
        maximum = count_schema.get("maximum")
        if isinstance(maximum, (int, float)) and not isinstance(maximum, bool):
            if requested_count > int(maximum):
                return None
        return {"count": requested_count}

    def _can_fast_execute_router_skill(self, match: Any) -> bool:
        if bool(getattr(match, "requires_confirmation", False)):
            return False
        safety_class = str(getattr(match, "safety_class", "") or "").lower()
        if safety_class in {"physical_motion", "safety_critical", "restricted"}:
            return False
        effects = {
            str(item).strip().lower()
            for item in (getattr(match, "effects", []) or [])
            if str(item).strip()
        }
        if effects.intersection(
            {
                "physical_motion",
                "safety_control",
                "tool_write",
                "external_side_effect",
                "memory_write",
            }
        ):
            return False
        schema = getattr(match, "input_schema", {}) or {}
        if not isinstance(schema, dict):
            return False
        properties = schema.get("properties")
        if not isinstance(properties, dict):
            properties = {}
        required = schema.get("required")
        required_fields = {str(item) for item in required} if isinstance(required, list) else set()
        if not required_fields.issubset({"count"}):
            return False
        if not self._optional_fast_fields_are_omittable(properties, required_fields):
            return False
        capability_id = str(getattr(match, "capability_id", "") or "").lower()
        description = str(getattr(match, "description", "") or "").lower()
        gesture_terms = ("blink", "nod", "shake")
        return any(term in capability_id or term in description for term in gesture_terms)

    @staticmethod
    def _optional_fast_fields_are_omittable(
        properties: dict[str, Any],
        required_fields: set[str],
    ) -> bool:
        for name, prop in properties.items():
            field = str(name)
            if field == "count":
                continue
            if field in required_fields:
                return False
            if not isinstance(prop, dict) or "default" not in prop:
                return False
        return True

    def _route_task_list_item_for_skill(
        self,
        request: AgentRunRequest,
        capability_id: str,
    ) -> dict[str, Any] | None:
        tasks = request.route_decision.metadata.get("task_list")
        if not isinstance(tasks, list):
            return None
        for item in tasks:
            if not isinstance(item, dict):
                continue
            if str(item.get("task_type") or "") != "task.execute_skill":
                continue
            if str(item.get("capability_id") or "").strip() != capability_id:
                continue
            if str(item.get("status") or "proposed") not in {"proposed", "validated"}:
                continue
            return item
        return None

    def _route_task_metadata(
        self,
        request: AgentRunRequest,
        route_task: dict[str, Any],
        skill_id: str,
        *,
        source: str,
        fast_path_reason: str,
    ) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "source": source,
            "skill_id": skill_id,
            "route_confidence": request.route_decision.confidence,
            "router_source": request.route_decision.source,
            "fast_path_reason": fast_path_reason,
        }
        task_id = str(route_task.get("id") or "").strip()
        if task_id:
            metadata["route_task_id"] = task_id
        source_stage = str(route_task.get("source_stage") or "").strip()
        if source_stage:
            metadata["route_task_source_stage"] = source_stage
        return metadata

    def _fast_router_speech(
        self,
        request: AgentRunRequest,
        match: Any,
        args: dict[str, Any],
    ) -> str:
        capability_id = str(getattr(match, "capability_id", "") or "").lower()
        description = str(getattr(match, "description", "") or "").lower()
        count = self._positive_int(args.get("count"))
        if self.is_zh(request):
            if "blink" in capability_id or "blink" in description:
                return f"好的，我会眨眼{count}次。" if count else "好的，我会眨眼。"
            if "nod" in capability_id or "nod" in description:
                return f"好的，我会点头{count}次。" if count else "好的，我会点头。"
            if "shake" in capability_id or "shake" in description:
                return f"好的，我会摇头{count}次。" if count else "好的，我会摇头。"
            return "好的，我会执行这个动作。"
        if "blink" in capability_id or "blink" in description:
            return f"Okay, I'll blink my eyes {count} times." if count else "Okay, I'll blink my eyes."
        if "nod" in capability_id or "nod" in description:
            return f"Okay, I'll nod {count} times." if count else "Okay, I'll nod."
        if "shake" in capability_id or "shake" in description:
            return (
                f"Okay, I'll shake my head {count} times."
                if count
                else "Okay, I'll shake my head."
            )
        return "Okay, I'll do that."

    @staticmethod
    def _fast_tasklist_confidence_threshold() -> float:
        raw = os.getenv("AGENT_CAPABILITY_FAST_TASKLIST_MIN_CONFIDENCE", "0.55")
        try:
            value = float(raw)
        except ValueError:
            return 0.55
        return max(0.0, min(1.0, value))

    def _recover_batched_over_limit_count_plan(
        self,
        request: AgentRunRequest,
        plan: _CapabilityPlan,
        candidates: list[Any],
    ) -> tuple[_CapabilityPlan, dict[str, Any]] | None:
        selected_id = self._router_selected_capability_id(request)
        if not selected_id:
            return None
        target = next(
            (
                match
                for match in candidates
                if str(getattr(match, "capability_id", "") or "") == selected_id
            ),
            None,
        )
        if target is None or not self._can_batch_over_limit_count_skill(target):
            return None

        schema = getattr(target, "input_schema", {}) or {}
        properties = schema.get("properties") if isinstance(schema, dict) else {}
        count_schema = properties.get("count") if isinstance(properties, dict) else None
        if not isinstance(count_schema, dict):
            return None
        maximum = count_schema.get("maximum")
        if not isinstance(maximum, (int, float)) or isinstance(maximum, bool):
            return None
        max_count = int(maximum)
        if max_count <= 0:
            return None
        minimum = count_schema.get("minimum")
        min_count = (
            int(minimum)
            if isinstance(minimum, (int, float)) and not isinstance(minimum, bool)
            else 1
        )
        if min_count <= 0:
            min_count = 1

        requested_count: int | None = None
        if plan.decision == "execute":
            if len(plan.skills) != 1:
                return None
            item = plan.skills[0]
            if item.skill_id != selected_id:
                return None
            planned_count = self._positive_int(item.args.get("count"))
            text_count = self._extract_requested_count(request.text)
            if (
                text_count is not None
                and text_count > max_count
                and (planned_count is None or planned_count <= max_count)
            ):
                requested_count = text_count
            else:
                requested_count = planned_count
        elif plan.decision in {"clarify", "unsupported"}:
            requested_count = self._extract_requested_count(request.text)
        if requested_count is None or requested_count <= max_count:
            return None

        chunks = self._split_count_into_schema_batches(
            requested_count,
            min_count=min_count,
            max_count=max_count,
        )
        if chunks is None:
            return None

        speech = self._batched_count_speech(
            request,
            target,
            requested_count=requested_count,
            max_count=max_count,
            batch_count=len(chunks),
        )
        try:
            recovered = _CapabilityPlan(
                decision="execute",
                speech=speech,
                skills=[
                    _PlannedSkill(skill_id=selected_id, args={"count": chunk})
                    for chunk in chunks
                ],
            )
        except ValidationError:
            return None
        return recovered, {
            "skill_id": selected_id,
            "requested_count": requested_count,
            "max_per_call": max_count,
            "batch_count": len(chunks),
            "batches": chunks,
            "source": "exact_routed_count_batch_recovery",
        }

    def _can_batch_over_limit_count_skill(self, match: Any) -> bool:
        if bool(getattr(match, "requires_confirmation", False)):
            return False
        safety_class = str(getattr(match, "safety_class", "") or "").lower()
        if safety_class in {"physical_motion", "safety_critical", "restricted"}:
            return False
        effects = {
            str(item).strip().lower()
            for item in (getattr(match, "effects", []) or [])
            if str(item).strip()
        }
        if "physical_motion" in effects or "safety_control" in effects:
            return False
        schema = getattr(match, "input_schema", {}) or {}
        if not isinstance(schema, dict):
            return False
        properties = schema.get("properties")
        if not isinstance(properties, dict):
            return False
        count_schema = properties.get("count")
        if not isinstance(count_schema, dict):
            return False
        type_value = count_schema.get("type")
        if isinstance(type_value, str):
            types = {str(type_value)}
        elif isinstance(type_value, list):
            types = {str(item) for item in type_value}
        else:
            types = set()
        if types and not types.intersection({"integer", "number"}):
            return False
        if "maximum" not in count_schema:
            return False
        required = schema.get("required")
        if isinstance(required, list):
            required_fields = {str(item) for item in required}
            if not required_fields.issubset({"count"}):
                return False
        return True

    def _split_count_into_schema_batches(
        self,
        requested_count: int,
        *,
        min_count: int,
        max_count: int,
    ) -> list[int] | None:
        max_batches = 6
        chunks: list[int] = []
        remaining = requested_count
        while remaining > 0:
            chunk = min(max_count, remaining)
            remainder = remaining - chunk
            if 0 < remainder < min_count:
                needed = min_count - remainder
                chunk -= needed
                remainder += needed
            if chunk < min_count or chunk > max_count:
                return None
            chunks.append(chunk)
            remaining = remainder
            if len(chunks) > max_batches:
                return None
        return chunks if chunks else None

    def _batched_count_speech(
        self,
        request: AgentRunRequest,
        match: Any,
        *,
        requested_count: int,
        max_count: int,
        batch_count: int,
    ) -> str:
        action = "do that"
        capability_id = str(getattr(match, "capability_id", "") or "")
        description = str(getattr(match, "description", "") or "").lower()
        if "blink" in capability_id or "blink" in description:
            action = "blink"
        elif "nod" in capability_id or "nod" in description:
            action = "nod"
        elif "shake" in capability_id or "shake" in description:
            action = "shake my head"
        if self.is_zh(request):
            if action == "blink":
                zh_action = "眨眼"
            elif action == "nod":
                zh_action = "点头"
            elif action == "shake my head":
                zh_action = "摇头"
            else:
                zh_action = "执行这个动作"
            return f"单次最多{max_count}次，所以我会分{batch_count}批{zh_action}{requested_count}次。"
        return (
            f"I can {action} up to {max_count} times per batch, "
            f"so I will {action} {requested_count} times in {batch_count} batches."
        )

    @staticmethod
    def _positive_int(value: Any) -> int | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value if value > 0 else None
        if isinstance(value, float) and value.is_integer():
            number = int(value)
            return number if number > 0 else None
        if isinstance(value, str) and re.fullmatch(r"\s*\d{1,4}\s*", value):
            number = int(value.strip())
            return number if number > 0 else None
        return None

    @classmethod
    def _extract_requested_count(cls, text: str) -> int | None:
        match = re.search(r"(?<![\d.])(\d{1,4})(?![\d.])", text or "")
        if match:
            number = int(match.group(1))
            return number if number > 0 else None
        chinese_match = re.search(r"([一二两三四五六七八九十]{1,3})\s*(?:下|次|遍|回|个)?", text or "")
        if chinese_match:
            number = cls._chinese_number_to_int(chinese_match.group(1))
            if number is not None and number > 0:
                return number
        words = re.findall(r"[a-zA-Z]+", (text or "").lower())
        for index, word in enumerate(words):
            if word in {"once", "a"}:
                return 1
            if word == "twice":
                return 2
            if word == "thrice":
                return 3
            number = cls._number_word_to_int(word)
            if number is not None:
                if index + 1 < len(words):
                    next_number = cls._number_word_to_int(words[index + 1])
                    if number >= 20 and next_number is not None and 0 < next_number < 10:
                        number += next_number
                return number if number > 0 else None
        return None

    @staticmethod
    def _chinese_number_to_int(value: str) -> int | None:
        digits = {
            "零": 0,
            "一": 1,
            "二": 2,
            "两": 2,
            "三": 3,
            "四": 4,
            "五": 5,
            "六": 6,
            "七": 7,
            "八": 8,
            "九": 9,
        }
        value = (value or "").strip()
        if not value:
            return None
        if value in digits:
            return digits[value]
        if value == "十":
            return 10
        if "十" in value:
            left, _, right = value.partition("十")
            tens = 1 if not left else digits.get(left)
            ones = 0 if not right else digits.get(right)
            if tens is None or ones is None:
                return None
            return tens * 10 + ones
        if len(value) == 2 and all(ch in digits for ch in value):
            return digits[value[0]] * 10 + digits[value[1]]
        return None

    @staticmethod
    def _number_word_to_int(word: str) -> int | None:
        return {
            "zero": 0,
            "one": 1,
            "two": 2,
            "three": 3,
            "four": 4,
            "five": 5,
            "six": 6,
            "seven": 7,
            "eight": 8,
            "nine": 9,
            "ten": 10,
            "eleven": 11,
            "twelve": 12,
            "thirteen": 13,
            "fourteen": 14,
            "fifteen": 15,
            "sixteen": 16,
            "seventeen": 17,
            "eighteen": 18,
            "nineteen": 19,
            "twenty": 20,
            "thirty": 30,
            "forty": 40,
            "fifty": 50,
            "sixty": 60,
        }.get(word)

    def _capability_payload(self, match: Any) -> dict[str, Any]:
        description = " ".join(str(getattr(match, "description", "") or "").split())
        if len(description) > 140:
            description = description[:140].rstrip() + "..."
        payload: dict[str, Any] = {
            "skill_id": str(getattr(match, "capability_id", "")),
            "description": description,
            "input_schema": self._compact_input_schema(getattr(match, "input_schema", {}) or {}),
            "effects": list(getattr(match, "effects", []) or []),
            "requires_confirmation": bool(getattr(match, "requires_confirmation", False)),
        }
        score = self._catalog_score(match)
        if score is not None:
            payload["score"] = score
        return payload

    def _compact_input_schema(self, schema: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(schema, dict):
            return {}
        compact: dict[str, Any] = {}
        for key in ("type", "required", "additionalProperties"):
            if key in schema:
                compact[key] = schema[key]
        properties = schema.get("properties")
        if isinstance(properties, dict):
            compact_properties: dict[str, Any] = {}
            for name, prop in properties.items():
                if not isinstance(prop, dict):
                    continue
                compact_prop: dict[str, Any] = {}
                for key in ("type", "enum", "minimum", "maximum", "default"):
                    if key in prop:
                        compact_prop[key] = prop[key]
                if compact_prop:
                    compact_properties[str(name)] = compact_prop
            compact["properties"] = compact_properties
        return compact

    @staticmethod
    def _catalog_score(match: Any) -> float | None:
        score = getattr(match, "score", None)
        if isinstance(score, (int, float)) and not isinstance(score, bool):
            return float(score)
        return None

    @staticmethod
    def _canonical_args_key(args: dict[str, Any]) -> str:
        try:
            return json.dumps(
                args,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        except TypeError:
            return repr(sorted(args.items()))

    def _invalid_args_speech(self, request: AgentRunRequest) -> str:
        if self.is_zh(request):
            return "这个动作缺少必要参数，所以我还不能移动。"
        return "Please clarify the action before I move."

    def _unsupported_action_speech(self, request: AgentRunRequest) -> str:
        if self.is_zh(request):
            return "我没有找到能对应这句话的可用动作，所以我不会移动。"
        return "I cannot map that to an available action, so I will not move."

    @staticmethod
    def _natural_plan_speech(value: str) -> str:
        return _natural_speech_or_empty(value)

    def _capability_search_text(self, request: AgentRunRequest) -> str:
        parts = [" ".join((request.text or "").split())]
        task_context = self._task_context_from_request(request)
        if isinstance(task_context, dict):
            for key in ("goal", "last_meaningful_user_turn", "last_assistant_response"):
                value = " ".join(str(task_context.get(key) or "").split())
                if value:
                    parts.append(value)
            for claim in task_context.get("important_claims") or []:
                value = " ".join(str(claim or "").split())
                if value:
                    parts.append(value)
        return " ".join(part for part in parts if part)

    def _task_context_from_request(self, request: AgentRunRequest) -> dict[str, Any] | None:
        context = request.context or {}
        current = context.get("current_task_context")
        if isinstance(current, dict):
            return current
        memory = context.get("session_memory")
        if isinstance(memory, dict):
            current = memory.get("current_task_context")
            if isinstance(current, dict):
                return current
        conversation = context.get("conversation")
        if isinstance(conversation, dict):
            current = conversation.get("current_task_context")
            if isinstance(current, dict):
                return current
        return None

    def _format_task_context(self, request: AgentRunRequest, *, zh: bool) -> str:
        task_context = self._task_context_from_request(request)
        if not task_context:
            return "无" if zh else "None"
        compact = json.dumps(task_context, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if len(compact) > 1200:
            compact = compact[:1200].rstrip() + "..."
        return compact

    def _session_memory_from_request(self, request: AgentRunRequest) -> dict[str, Any]:
        context = request.context or {}
        memory = context.get("session_memory")
        if isinstance(memory, dict):
            return memory
        conversation = context.get("conversation")
        if isinstance(conversation, dict):
            memory = conversation.get("session_memory")
            if isinstance(memory, dict):
                return memory
        return {}

    def _format_memory_context(self, request: AgentRunRequest, *, zh: bool) -> str:
        memory = self._session_memory_from_request(request)
        if not memory:
            return "无" if zh else "None"
        lines: list[str] = []
        summary = str(memory.get("memory_summary") or "").strip()
        if summary and summary.lower() != "none":
            for item in summary.splitlines()[:8]:
                text = item.strip().lstrip("-").strip()
                if text:
                    lines.append(f"- {self._bounded_text(text, 220)}")
        entries = memory.get("extracted_memory")
        if isinstance(entries, list) and not lines:
            for item in entries[-6:]:
                if not isinstance(item, dict):
                    continue
                text = " ".join(str(item.get("text") or "").split())
                if text:
                    lines.append(f"- {self._bounded_text(text, 220)}")
        current_task = memory.get("current_task")
        if isinstance(current_task, dict):
            status = " ".join(str(current_task.get("status") or "").split())
            summary_text = " ".join(str(current_task.get("summary") or "").split())
            parts = []
            if status:
                parts.append(f"status={status}")
            if summary_text:
                parts.append(f"summary={self._bounded_text(summary_text, 180)}")
            if parts:
                label = "当前任务" if zh else "current_task"
                lines.append(f"- {label}: {'; '.join(parts)}")
        return "\n".join(lines) if lines else ("无" if zh else "None")

    def _history_from_request(self, request: AgentRunRequest) -> list[dict[str, Any]]:
        if request.history:
            return [turn for turn in request.history if isinstance(turn, dict)]
        context = request.context or {}
        history = context.get("history")
        if isinstance(history, list):
            return [turn for turn in history if isinstance(turn, dict)]
        conversation = context.get("conversation")
        if isinstance(conversation, dict):
            history = conversation.get("history")
            if isinstance(history, list):
                return [turn for turn in history if isinstance(turn, dict)]
        return []

    def _format_history(self, request: AgentRunRequest, *, zh: bool) -> str:
        history = self._history_from_request(request)
        if not history:
            return "无" if zh else "None"
        lines: list[str] = []
        for turn in history[-6:]:
            role = str(turn.get("role") or "unknown").lower()
            text = " ".join(str(turn.get("text") or "").split())
            if not text:
                continue
            if len(text) > 180:
                text = text[:180].rstrip() + "..."
            if zh:
                label = "用户" if role == "user" else "Chromie" if role == "assistant" else role
            else:
                label = "User" if role == "user" else "Chromie" if role == "assistant" else role
            lines.append(f"{label}: {text}")
        return "\n".join(lines) if lines else ("无" if zh else "None")

    def _format_recent_turn_fallback(self, request: AgentRunRequest, *, zh: bool) -> str:
        history = self._history_from_request(request)
        if not history:
            return "无" if zh else "None"
        lines: list[str] = []
        for turn in history[-2:]:
            role = str(turn.get("role") or "unknown").lower()
            text = " ".join(str(turn.get("text") or "").split())
            if not text:
                continue
            if len(text) > 160:
                text = text[:160].rstrip() + "..."
            if zh:
                label = "用户" if role == "user" else "Chromie" if role == "assistant" else role
            else:
                label = "User" if role == "user" else "Chromie" if role == "assistant" else role
            lines.append(f"{label}: {text}")
        return "\n".join(lines) if lines else ("无" if zh else "None")
