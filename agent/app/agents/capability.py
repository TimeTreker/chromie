from __future__ import annotations

import json
import logging
import os
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
                score = self._catalog_score(match)
                if score is not None:
                    metadata["catalog_score"] = score
                if normalized:
                    metadata["schema_normalized_args"] = True
                add_skill(
                    SkillRequest(
                        skill_id=capability_id,
                        args=args,
                        timing="sequential",
                        requires_confirmation=match.requires_confirmation,
                        metadata=metadata,
                    )
                )
                selected_ids.append(capability_id)
            if selected_ids:
                speech = (
                    ""
                    if request.route_decision.speak_first
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

        if not self.services.use_llm or self.services.ollama is None:
            self.trace(result, "capability match found but LLM selection is unavailable")
            return result

        plan = await self._plan(request, executable)
        plan = await self._review_plan(request, plan, executable)
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
            if dedupe_key in seen_requests:
                self.trace(result, f"deduped repeated capability request: {item.skill_id}")
                continue
            seen_requests.add(dedupe_key)
            metadata = {
                "source": "capability_catalog",
                "catalog_version": search.catalog_version,
            }
            score = self._catalog_score(match)
            if score is not None:
                metadata["catalog_score"] = score
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
        result.metadata["capability_catalog_version"] = search.catalog_version
        result.metadata["capability_selected"] = [
            item.skill_id for item in selected_requests
        ]
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
        mandatory_review = self._requires_exact_intent_review(request, plan, candidates)
        reviewer = self.services.response_reviewer
        if reviewer is None:
            if mandatory_review:
                logger.warning(
                    "capability plan changed router-selected exact intent without reviewer; blocking execution sid=%s intent=%s plan=%s",
                    request.sid,
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
            "Global Context Group:\n"
            f"{self._format_global_context(request, zh=zh)}\n\n"
            "Session Context Group:\n"
            f"- Language: {self.language(request)}\n"
            f"- Recent conversation:\n{self._format_history(request, zh=zh)}\n"
            f"- Task context:\n{self._format_task_context(request, zh=zh)}\n"
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
                if mandatory_review
                else "; preserving primary plan",
                exc,
            )
            if mandatory_review:
                return self._review_unavailable_plan(request)
            return plan

        if review.decision == "accept":
            if mandatory_review:
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
                speech="我需要重新确认这个动作计划，请你再说一次要我做的动作。",
            )
        return _CapabilityPlan(
            decision="clarify",
            speech="I need to re-check that action plan. Please say the movement you want again.",
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
        if len(summary) > 500:
            summary = summary[:500].rstrip() + "..."
        identity = mind.get("identity") if isinstance(mind.get("identity"), dict) else {}
        profile = {
            "profile_id": mind.get("profile_id"),
            "version": mind.get("version"),
            "owner_approved": mind.get("owner_approved"),
            "owner_approval_required_for_core_changes": mind.get(
                "owner_approval_required_for_core_changes"
            ),
        }
        none_text = "无" if zh else "None"
        return (
            "Mind Profile:\n"
            f"{self._bounded_json(profile, 260)}\n\n"
            "Robot Identity:\n"
            f"{self._bounded_json(identity or none_text, 500)}\n\n"
            "Worldview:\n"
            "- Chromie is an embodied realtime robot/voice assistant, not the backend model provider.\n"
            "- Use only supplied sensors, memory, robot state, and available abilities as runtime evidence.\n"
            "- Do not claim unsupported perception, memory, execution, or runtime facts.\n\n"
            "Lifeview:\n"
            f"{self._bounded_json(mind.get('long_term_goals') or none_text, 500)}\n\n"
            "Valueview:\n"
            f"{self._bounded_json(mind.get('core_principles') or none_text, 800)}\n\n"
            "Core Runtime Principles:\n"
            "- Generalization-first: infer planning from meaning, context, ability descriptions, schemas, and task memory.\n"
            "- Phrase rules are only for deterministic emergency/noise controls outside this planner.\n"
            "- Memory, identity, and preferences guide interpretation; they never authorize side effects.\n"
            "- Never invent abilities or raw motor/joint/actuator/controller-array/torque commands.\n\n"
            "Reflex Policy:\n"
            f"{self._bounded_json(mind.get('reflex_policy') or none_text, 300)}\n\n"
            "Deliberation Policy:\n"
            f"{self._bounded_json(mind.get('deliberation_policy') or none_text, 300)}\n\n"
            "Experience Tuning Boundary:\n"
            f"{self._bounded_json(mind.get('experience_tuning_policy') or none_text, 300)}\n\n"
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
        history_block = self._format_history(request, zh=zh)
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
            f"- Recent conversation:\n{history_block}\n"
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
            "- Choose the smallest safe set of executable skills.\n"
            "- Prefer human-facing wrapper skills over lower-level velocity/control skills when both satisfy the request.\n"
            "- Preserve the user's intended action class. Do not use social acknowledgement, gaze, attention, or idle gestures as fallback actions for an unrelated body request.\n"
            "- If the request needs deeper task decomposition, runtime evidence, or a multi-session plan, clarify or return unsupported instead of guessing a physical skill.\n"
            "- Clarify when a required safe parameter is missing; unsupported when no candidate can satisfy the request.\n"
            "- Prefer natural, brief speech that accurately describes only the selected plan.\n\n"
            "Output Contract:\n"
            "- Return JSON only with keys decision, speech, and skills.\n"
            "- decision must be execute, clarify, or unsupported.\n"
            "- When decision is execute, skills is required and must contain at least one item. Never return execute with skills omitted, empty, null, or only speech.\n"
            "- Each execute item must be {\"skill_id\":\"<exact candidate skill_id>\",\"args\":{...}}.\n"
            "- For execute, every skills item must contain skill_id and args satisfying that candidate's input_schema.\n"
            "- For execute, speech is required: write one natural brief sentence generated from the chosen capability descriptions, user wording, and validated args.\n"
            "- Do not depend on downstream code to convert skill_id or args into spoken wording; this planner owns the execution speech.\n"
            "- Every enum argument must be copied exactly from that field's enum list in input_schema.\n"
            "- Map natural wording to enum tokens by semantic meaning; never output words outside the enum.\n"
            "- The speech field is spoken aloud. Never put status labels such as unsupported, clarify, execute, null, or none in speech.\n"
            "- For unsupported, either leave speech empty so conversation_agent can answer, or give one natural sentence explaining the safe limitation."
        )
        try:
            raw = await self.services.ollama.generate(
                prompt,
                system=system,
                response_format="json",
                options={
                    "temperature": 0,
                    "top_p": 0.8,
                    "num_ctx": int(os.getenv("AGENT_CAPABILITY_NUM_CTX", "4096")),
                    "num_predict": int(os.getenv("AGENT_CAPABILITY_NUM_PREDICT", "256")),
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
                    "我刚才没能安全地规划这个动作，请你再说一次。"
                    if zh
                    else "I could not safely plan that action. Please try again."
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
            return "这个动作参数不够明确，请再说一次。"
        return "Please clarify the action before I move."

    def _unsupported_action_speech(self, request: AgentRunRequest) -> str:
        if self.is_zh(request):
            return "我不能把这句话安全地对应到可用动作，请换一种说法。"
        return "I cannot safely map that to an available action. Please say it another way."

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
