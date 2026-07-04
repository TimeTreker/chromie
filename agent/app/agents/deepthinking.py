from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Literal, cast

from pydantic import BaseModel, Field, ValidationError

try:
    from chromie_contracts.interaction import SkillRequest
    from chromie_contracts.task_proposal import TaskProposal
except ImportError:  # pragma: no cover - repository development path
    from shared.chromie_contracts.interaction import SkillRequest
    from shared.chromie_contracts.task_proposal import TaskProposal

from ..capabilities.validator import normalize_args_for_schema, validate_args_for_schema
from ..schema import AgentResult, AgentRunRequest
from .base import BaseAgent

logger = logging.getLogger("chromie.agent.deepthinking")


class _DeepThinkingSpeechTask(BaseModel):
    text: str = ""
    timing: Literal["immediate", "parallel", "sequential", "after_skills"] = "immediate"
    style: str = "brief"
    priority: str = "normal"


class _DeepThinkingTask(BaseModel):
    skill_id: str
    args: dict[str, Any] = Field(default_factory=dict)
    timing: Literal["immediate", "parallel", "sequential", "after_skills"] = "sequential"
    timeout_ms: int | None = Field(default=None, ge=1, le=120000)
    cancellable: bool = True
    requires_confirmation: bool | None = None
    reason: str = ""


class _DeepThinkingActionTask(BaseModel):
    skill_id: str
    args: dict[str, Any] = Field(default_factory=dict)
    timing: Literal["parallel", "sequential"] = "sequential"
    timeout_ms: int | None = Field(default=None, ge=1, le=120000)
    cancellable: bool = True
    requires_confirmation: bool | None = None
    reason: str = ""


class _DeepThinkingQuickReview(BaseModel):
    decision: Literal["none", "accept", "revise", "supersede"] = "none"
    reason: str = ""
    superseded_task_ids: list[str] = Field(default_factory=list)


class _DeepThinkingTaskProposal(BaseModel):
    ability_id: str
    intent: str = ""
    status: Literal["missing_ability", "known_missing", "not_executable", "planned", "forbidden", "advisory"] = "missing_ability"
    matched_skill_id: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    reason: str = ""


class _DeepThinkingPlan(BaseModel):
    tasks: list[_DeepThinkingTask] = Field(default_factory=list)
    task_proposals: list[_DeepThinkingTaskProposal] = Field(default_factory=list)
    spoken_response: str = ""
    speech_tasks: list[_DeepThinkingSpeechTask] = Field(default_factory=list)
    action_tasks: list[_DeepThinkingActionTask] = Field(default_factory=list)
    quick_review: _DeepThinkingQuickReview = Field(default_factory=_DeepThinkingQuickReview)
    reason: str = ""


class DeepThinkingAgent(BaseAgent):
    name = "deepthinking_agent"

    async def run(self, request: AgentRunRequest, result: AgentResult) -> AgentResult:
        started = time.perf_counter()
        logger.info(
            "deepthinking_agent_start sid=%s route=%s intent=%s agents=%s text_chars=%s text=%r use_llm=%s ollama_present=%s history_turns=%s pending_tasks=%s conversation_id=%s",
            request.sid,
            request.route_decision.route,
            request.route_decision.intent,
            request.route_decision.agents,
            len(request.text or ""),
            request.text,
            self.services.use_llm,
            self.services.ollama is not None,
            len(self._history_from_request(request)),
            len(self._pending_tasks_from_request(request)),
            self._conversation_id(request),
        )

        if getattr(result, "metadata", {}).get("capability_handled"):
            result.trace.append("deepthinking_agent: skipped because capability agent handled the request")
            return result

        if request.route_decision.route != "deep_thought" and self.name not in request.route_decision.agents:
            logger.info(
                "deepthinking_agent_skip sid=%s reason=route_not_handled route=%s agents=%s",
                request.sid,
                request.route_decision.route,
                request.route_decision.agents,
            )
            return result

        text = request.text.strip()
        if not text:
            result.status = "ignored"
            result.reason = "empty_text"
            self.trace(result, "ignored empty text")
            return result

        if not self.services.use_llm:
            logger.warning("deepthinking_agent_fallback sid=%s reason=llm_disabled", request.sid)
            result.trace.append("deepthinking_agent: llm disabled")
        elif self.services.ollama is None:
            logger.warning("deepthinking_agent_fallback sid=%s reason=ollama_client_missing", request.sid)
            result.trace.append("deepthinking_agent: ollama client missing")
        else:
            try:
                logger.info(
                    "deepthinking_agent_llm_start sid=%s model_call_expected=True text=%r history_turns=%s pending_tasks=%s conversation_id=%s",
                    request.sid,
                    request.text,
                    len(self._history_from_request(request)),
                    len(self._pending_tasks_from_request(request)),
                    self._conversation_id(request),
                )
                plan = await self._llm_plan(request)
                response_json = plan.model_dump_json()
                logger.info(
                    "deepthinking_agent_llm_done sid=%s plan_chars=%s plan=%r elapsed_ms=%.1f",
                    request.sid,
                    len(response_json),
                    response_json,
                    (time.perf_counter() - started) * 1000.0,
                )
                self._apply_plan(request, result, plan)
                self.trace(result, "generated deep-thinking task plan with session memory")
                return result
            except Exception as exc:
                logger.exception(
                    "deepthinking_agent_llm_failed sid=%s error_type=%s error=%s elapsed_ms=%.1f",
                    request.sid,
                    type(exc).__name__,
                    exc,
                    (time.perf_counter() - started) * 1000.0,
                )
                result.trace.append(f"deepthinking_agent: llm failed: {type(exc).__name__}: {exc}")

        fallback = self._fallback_reply(request)
        result.add_speak_immediate(fallback, style="brief")
        self.trace(result, "used fallback reply")
        return result

    async def _llm_plan(self, request: AgentRunRequest) -> _DeepThinkingPlan:
        assert self.services.ollama is not None
        zh = self.is_zh(request)
        language = self.language(request)
        extracted_context_block = self._format_extracted_conversation_context(request, zh=False)
        pending_block = self._format_pending_tasks(request, zh=False)
        session_memory_block = self._format_session_memory(request, zh=False)
        task_context_block = self._format_task_context(request, zh=False)
        mind_block = self.format_mind_context(request, zh=False)
        conversation_id = self._conversation_id(request)
        capability_context = self._capability_context(request, zh=False)
        route_context = self._route_context(request, zh=False)
        output_contract = self._output_contract()

        system = (
            "Priority Rule 1: For physical robot action requests, output ONLY a short spoken acknowledgement or routing sentence. "
            "Absolutely NO Task Split, Key Risk, Next Step, internal skill IDs, schema fields, or raw execution arguments in the spoken response. "
            "Do not claim movement is executing unless you also emit a matching validated action task. "
            "You are Chromie's deepthinking agent, not the normal conversation agent. "
            "Your job is to split complex requests into clear tasks and use session working memory for architecture, debugging, planning, decisions, and candidate action requests. "
            "Generalization-first is a core principle: reason from meaning, context, capability descriptions, and task memory. Do not turn examples into keyword rules or replace understanding with rule tables. "
            "Example - Bad keyword-rule: User says 'turn on light' -> think 'keyword=light, action=on'. Good generalization: User wants illumination; check the supplied capabilities and context before planning or answering. "
            "Treat Chromie's mind principles, long-term goals, and experience-tuning boundaries as upper constraints for deliberation; core principles can change only through human owner approval. "
            "All spoken output must be in the target language specified in the User Prompt's 'Target spoken language' field. "
            "If the user asks about identity, name, or age, answer from the owner-approved identity in the mind profile; Chromie is the robot, not the backend language model or provider model. "
            "Answer naturally in Chromie's first-person robot persona; do not use backend-model stock phrases such as 'as an AI' or 'I do not have personal opinions'. "
            "Reason privately and output only the final answer, never the hidden chain of thought. "
            "When the request benefits from task decomposition, give an ordered, concise task split, key risks, and the next step. "
            "When voicing a cognitive task plan, weave the task split, key risk, and next step into one fluid first-person spoken paragraph. Never output bullet points, labels, or numbered lists in the final TTS output. "
            "For short follow-ups, resolve references from task context before asking for more context. "
            "If more tools, code changes, or robot actions are needed, describe the plan or ask for confirmation; do not invent results. "
            "For direct physical robot action requests, do not narrate Task Split, Key Risk, Next Step, internal skill IDs, or execution arguments in chromie.speak text. "
            "For physical action, emit skill tasks: one chromie.speak acknowledgement task when speech is useful, plus exact candidate skill tasks for embodied/tool work. "
            "Do not pretend to remember anything outside the supplied context, and do not invent tool results. "
            "For common factual questions, answer directly and correct obvious false premises. "
            "If the user says 'do you think', 'in my opinion', or 'do you agree' about an objective fact, treat it as a factual question, not a personal-opinion question. "
            "Do not answer that you lack personal opinions when the question has an objective factual answer. "
            "Normally do not repeat, quote, or paraphrase the user's current words; do that only when confirmation, clarification, or an explicit read-back is needed. "
            "When the user phrases a harmless creative speech request as a capability question, such as asking whether you can, could, or would tell a joke, tell a story, sing, write a poem, or create something, interpret it as a request to do it now. Do not answer only with ability, willingness, or readiness. "
            "When a greeting and a request appear together, acknowledge the greeting briefly and still complete the request in the same reply. "
            "If recent context shows Chromie already promised a joke, story, song, poem, or other creative content and the user says they are waiting, asks you to continue, says go ahead, or asks again, deliver the promised content now. "
            "For joke, short-story, singing, or songwriting requests, create brief original harmless content instead of only saying you can do it. "
            "Understand the user's intent broadly before applying the current capability catalog. The catalog constrains executable tasks, not meaning. "
            "The capability catalog describes executable abilities and schemas, not authorization; never invent executable capabilities, low-level motor commands, or raw joint actions. "
            "If you understand a desired human-like ability but no supplied executable skill safely matches it, emit a task_proposals item with status missing_ability and emit only truthful chromie.speak text; do not fake the action. "
            "Speech is not a special final text channel; it is the chromie.speak skill. "
            "If upstream routing context includes quick_router_review_request, review the quick Router's proposals as an adult safety reviewer. "
            "Set quick_review.decision to accept when the quick plan is correct, revise when it is partly right but needs changed tasks/arguments/order, or supersede when it misunderstood the user. "
            "When revising or superseding, emit the replacement tasks you think are correct. If the quick proposal was not committed, do not apologize merely for revising it; if context shows a wrong action already ran or was visibly started, include a brief chromie.speak apology/correction. "
            "Return compact JSON only with keys tasks, task_proposals, quick_review, and reason. "
            "tasks is a unified ordered list of robot skill tasks. Each task has skill_id, args, timing, timeout_ms, cancellable, requires_confirmation, and reason. "
            "task_proposals is an optional ordered list of understood desired abilities that are not executable now; each item has ability_id, intent, status, matched_skill_id, confidence, and reason. "
            "Use skill_id chromie.speak with args {\"text\":\"...\",\"style\":\"brief\",\"priority\":\"normal\"} for anything Chromie should say. "
            "Every non-speech task skill_id must be copied exactly from the supplied Capability catalog and its args must satisfy that candidate input_schema. "
            "Never output raw joint, motor, actuator, controller-array, position-array, or torque fields anywhere. "
            "reason is a short audit note, not chain-of-thought."
        )
        prompt = (
            f"conversation_id: {conversation_id}\n"
            f"Target spoken language: {language}\n\n"
            f"Session working memory:\n{session_memory_block}\n\n"
            f"Extracted conversation context (no raw transcript turns):\n{extracted_context_block}\n\n"
            f"Pending tasks:\n{pending_block}\n\n"
            f"Task context:\n{task_context_block}\n\n"
            f"Mind principles, long-term goals, and experience boundaries:\n{mind_block}\n\n"
            f"Capability catalog:\n{capability_context}\n\n"
            f"Upstream routing context:\n{route_context}\n\n"
            f"Output Contract:\n{output_contract}\n\n"
            f"Current user said: {request.text}\n"
            f"Current intent: {request.route_decision.intent}\n"
            "Apply the Priority Rules strictly. First understand the user's desired ability broadly, then compare it with the supplied executable catalog. "
            "Emit only the tasks Chromie should perform now. "
            "For cognitive tasks, this is usually one chromie.speak task with a concise natural-spoken plan. "
            "For physical actions, include a short chromie.speak acknowledgement only if useful, and include candidate executable skill tasks for the actual work. "
            "If no supplied capability safely matches, emit only a brief chromie.speak clarification or limitation plus a task_proposals missing_ability item. "
            "Output the JSON contract and nothing else."
        )

        options = {
            "temperature": 0.25,
            "top_p": 0.9,
            "num_ctx": int(os.getenv("AGENT_DEEPTHINKING_NUM_CTX", "8192")),
            "num_predict": int(os.getenv("AGENT_DEEPTHINKING_NUM_PREDICT", "384")),
            "stop": ["\nUser:", "\nAssistant:", "\n用户：", "\n助手："],
        }
        raw = await self.services.ollama.generate(
            prompt,
            system=system,
            response_format="json",
            options=options,
        )
        plan = self._plan_from_raw(raw)
        return await self._review_plan_speech(
            request,
            plan,
            prompt=prompt,
            system=system,
            zh=zh,
            options=options,
        )

    def _output_contract(self) -> str:
        return (
            "Return JSON only. Top-level keys: tasks, task_proposals, quick_review, reason only.\n"
            "Do not output spoken_response, speech_tasks, action_tasks, markdown, prose, or labels.\n"
            "JSON skeleton:\n"
            "{\"tasks\":[{\"skill_id\":\"chromie.speak\",\"args\":{\"text\":\"...\",\"style\":\"brief\",\"priority\":\"normal\"},\"timing\":\"immediate\",\"timeout_ms\":null,\"cancellable\":true,\"requires_confirmation\":null,\"reason\":\"short audit note\"}],\"task_proposals\":[{\"ability_id\":\"social.blink_eyes\",\"intent\":\"blink eyes\",\"status\":\"missing_ability\",\"matched_skill_id\":null,\"confidence\":0.9,\"reason\":\"no executable eye-blink skill was supplied\"}],\"quick_review\":{\"decision\":\"none|accept|revise|supersede\",\"reason\":\"short review note\",\"superseded_task_ids\":[]},\"reason\":\"short audit note\"}\n"
            "Task field rules:\n"
            "- skill_id: use chromie.speak for speech, otherwise copy one exact skill_id from Capability catalog.\n"
            "- args: object matching the selected skill schema. For chromie.speak use text, style, and priority.\n"
            "- timing: immediate, parallel, sequential, or after_skills. Non-speech tasks should normally use sequential or parallel.\n"
            "- timeout_ms: integer milliseconds or null.\n"
            "- cancellable: boolean.\n"
            "- requires_confirmation: boolean or null; null means defer to the candidate capability definition.\n"
            "- reason: short audit note, not hidden chain-of-thought.\n"
            "Task proposal rules:\n"
            "- Use task_proposals for desired human-like abilities that you understand but cannot execute with the supplied catalog.\n"
            "- status should be missing_ability when no executable skill is supplied, forbidden when the request is unsafe, or planned/advisory only for non-executing roadmap notes.\n"
            "- matched_skill_id is null unless a supplied catalog skill is relevant but not executable.\n"
            "- task_proposals never execute; executable work must appear in tasks with exact catalog skill_ids.\n"
            "For cognitive answers, usually emit exactly one chromie.speak task.\n"
            "For physical/tool actions, emit a chromie.speak acknowledgement only if useful, plus the exact executable candidate skill task.\n"
            "If no supplied capability safely matches, emit one chromie.speak clarification or limitation plus a task_proposals missing_ability item.\n"
            "When Upstream routing context includes quick_router_review_request, fill quick_review. Use accept only when the quick proposal is semantically correct. Use revise or supersede when replacing it, and include superseded_task_ids from the supplied quick_task_proposals when known.\n"
            "Do not copy placeholder values from the skeleton."
        )

    def _plan_from_raw(self, raw: Any) -> _DeepThinkingPlan:
        if isinstance(raw, dict):
            try:
                return _DeepThinkingPlan.model_validate(raw)
            except ValidationError as exc:
                logger.warning("invalid deepthinking JSON plan dict: %s", exc)
                return _DeepThinkingPlan(spoken_response="")
        text = str(cast(Any, raw) or "").strip()
        if not text:
            return _DeepThinkingPlan(spoken_response="")
        if text.startswith("{"):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    return _DeepThinkingPlan.model_validate(parsed)
            except (json.JSONDecodeError, ValidationError) as exc:
                logger.warning("invalid deepthinking JSON plan text: %s", exc)
        return _DeepThinkingPlan(spoken_response=text)

    async def _review_plan_speech(
        self,
        request: AgentRunRequest,
        plan: _DeepThinkingPlan,
        *,
        prompt: str,
        system: str,
        zh: bool,
        options: dict[str, Any],
    ) -> _DeepThinkingPlan:
        response = plan.spoken_response
        first_task_speech_index = self._first_speech_task_index(plan)
        first_legacy_speech_index = 0 if plan.speech_tasks else None
        if not response and first_task_speech_index is not None:
            response = self._speech_task_text(plan.tasks[first_task_speech_index])
        if not response and first_legacy_speech_index is not None:
            response = plan.speech_tasks[first_legacy_speech_index].text
        if not response and self._effect_tasks(plan):
            response = "好的。" if zh else "Okay."
        response = await self.review_spoken_response(
            request,
            prompt=prompt,
            system=system,
            response=response,
            zh=zh,
            options=options,
        )
        response = self._clean_response(response, zh=zh)
        if not self.is_playable_spoken_response(response, zh=zh):
            logger.warning(
                "deepthinking_agent_invalid_spoken_response sid=%s response=%r",
                request.sid,
                response,
            )
            response = self.invalid_spoken_response_fallback(zh=zh)
        if first_task_speech_index is not None:
            tasks = list(plan.tasks)
            task = tasks[first_task_speech_index]
            args = dict(task.args)
            args["text"] = response
            tasks[first_task_speech_index] = task.model_copy(update={"args": args})
            return plan.model_copy(update={"spoken_response": response, "tasks": tasks})
        if first_legacy_speech_index is not None:
            speech_tasks = list(plan.speech_tasks)
            speech_tasks[first_legacy_speech_index] = speech_tasks[first_legacy_speech_index].model_copy(
                update={"text": response}
            )
            return plan.model_copy(update={"spoken_response": response, "speech_tasks": speech_tasks})
        return plan.model_copy(update={"spoken_response": response})

    def _response_review_prompt(
        self,
        request: AgentRunRequest,
        *,
        agent_prompt: str,
        agent_system: str,
        response: str,
        target_language: str,
    ) -> str:
        del agent_system
        task_context = self._bounded_text(self._format_task_context(request, zh=False), 1200)
        extracted_context = self._bounded_text(
            self._format_extracted_conversation_context(request, zh=False),
            1400,
        )
        capabilities = self._bounded_json(
            {
                "candidate_capabilities": request.route_decision.candidate_capabilities,
                "capability_candidates": request.context.get("capability_candidates"),
            },
            1600,
        )
        route_context = self._bounded_json(
            {
                "route": request.route_decision.route,
                "intent": request.route_decision.intent,
                "source": request.route_decision.source,
                "agents": request.route_decision.agents,
                "actions": request.route_decision.actions,
            },
            1000,
        )
        original_prompt = agent_prompt[:1800]
        return (
            f"Target spoken language: {target_language}\n"
            "Use an explicit user-requested output language when the current input or extracted context asks for one; otherwise use the target spoken language.\n"
            f"Current user input: {request.text}\n"
            f"Route context: {route_context}\n"
            f"Extracted conversation context: {extracted_context}\n"
            f"Task context: {task_context}\n"
            f"Capability context: {capabilities}\n"
            f"Original agent prompt excerpt: {original_prompt}\n"
            f"Candidate spoken response: {response}\n\n"
            "Decide whether the candidate can be spoken now. "
            "A one-word fragment such as only 'I' is not speakable and must be revised. "
            "If the current user input or extracted context asks for a joke, story, song, poem, or other creative content, "
            "including capability-style wording such as whether Chromie can, could, or would do it, the candidate must include the actual content. Example: user asks for a joke and candidate says "
            "'I can tell you a joke.' => revise with a brief original joke. "
            "If extracted context shows Chromie already promised the content and the user says they are waiting, asks to continue, says go ahead, or asks again, the candidate must deliver it now. "
            "If the candidate says Chromie lacks a body/tool ability that appears available in Capability context or the original prompt excerpt, revise it to acknowledge the available ability instead of falsely refusing. "
            "If Route context is chat or clarify and the candidate promises, confirms, or implies that Chromie will now execute a physical body action, movement, or tool side effect, revise it to a safe clarification that the action must be routed through the robot action planner before execution. "
            "Do not let a speech-only response claim that a movement or tool action is being performed when no robot_action route or skill request is present. "
            "Normally Chromie should not repeat, quote, or paraphrase the user's current words; allow that only for confirmation, clarification, or an explicit read-back request. "
            "Return JSON: {\"decision\":\"accept|revise\",\"reason\":\"short reason\","
            "\"spoken_response\":\"empty when accepted; final corrected spoken answer when revised\"}."
        )

    def _add_spoken_response(self, result: AgentResult, response: str) -> None:
        for chunk in self._split_spoken_response(response):
            result.add_speak_immediate(chunk, style="brief")

    def _apply_plan(
        self,
        request: AgentRunRequest,
        result: AgentResult,
        plan: _DeepThinkingPlan,
    ) -> None:
        metadata = getattr(result, "metadata", None)
        tasks = self._normalized_tasks(plan)
        rejected_tasks: list[dict[str, Any]] = []
        task_proposals: list[dict[str, Any]] = []
        valid_task_count = 0
        proposed_effect_count = 0
        valid_effect_count = 0
        add_skill = getattr(result, "add_skill", None)
        candidates = self._candidate_capabilities(request)

        for index, task in enumerate(tasks):
            if self._is_speech_task(task):
                self._add_speech_skill_task(result, task)
                task_proposals.append(
                    self._task_proposal(
                        task,
                        index=index,
                        state="committed",
                        reason=task.reason or plan.reason or "deepthinking speech task",
                        committed_by="deepthinking_speech_task",
                    )
                )
                valid_task_count += 1
                continue
            proposed_effect_count += 1
            if callable(add_skill):
                candidate = self._candidate_for_task(task, candidates)
                if candidate is None:
                    task_proposals.append(
                        self._task_proposal(
                            task,
                            index=index,
                            state="rejected",
                            reason="not_available_interaction_executable_candidate",
                        )
                    )
                    rejected_tasks.append(
                        {
                            "skill_id": task.skill_id,
                            "reason": "not_available_interaction_executable_candidate",
                        }
                    )
                    continue
                schema = candidate.get("input_schema") if isinstance(candidate, dict) else {}
                if not isinstance(schema, dict):
                    schema = {}
                args, normalized = normalize_args_for_schema(task.args, schema)
                arg_errors = validate_args_for_schema(args, schema)
                if arg_errors:
                    task_proposals.append(
                        self._task_proposal(
                            task,
                            index=index,
                            state="rejected",
                            reason="schema_validation_failed",
                        )
                    )
                    rejected_tasks.append(
                        {
                            "skill_id": task.skill_id,
                            "reason": "schema_validation_failed",
                            "errors": arg_errors,
                        }
                    )
                    continue
                requires_confirmation = (
                    bool(candidate.get("requires_confirmation"))
                    if task.requires_confirmation is None
                    else bool(task.requires_confirmation)
                )
                skill_id = self._candidate_skill_id(candidate) or task.skill_id
                skill = SkillRequest(
                    skill_id=skill_id,
                    args=args,
                    timing=self._skill_timing(task),
                    timeout_ms=task.timeout_ms,
                    cancellable=task.cancellable,
                    requires_confirmation=requires_confirmation,
                    metadata={
                        "source": "deepthinking_skill_task",
                        "reason": self._bounded_text(task.reason or plan.reason, 240),
                        "schema_normalized_args": normalized,
                    },
                )
                add_skill(skill)
                task_proposals.append(
                    self._task_proposal(
                        task,
                        index=index,
                        state="advisory",
                        reason=task.reason or plan.reason or "deepthinking skill task",
                        skill_id=skill_id,
                    )
                )
                valid_task_count += 1
                valid_effect_count += 1
                continue
            task_proposals.append(
                self._task_proposal(
                    task,
                    index=index,
                    state="rejected",
                    reason="result_surface_has_no_skill_lane",
                )
            )
            rejected_tasks.append(
                {
                    "skill_id": task.skill_id,
                    "reason": "result_surface_has_no_skill_lane",
                }
            )

        proposal_offset = len(task_proposals)
        for index, proposal in enumerate(plan.task_proposals):
            task_proposals.append(
                self._desired_ability_task_proposal(
                    proposal,
                    index=proposal_offset + index,
                    fallback_reason=plan.reason,
                )
            )

        if isinstance(metadata, dict):
            metadata["deepthinking_output_mode"] = "skill_tasks"
            metadata["deepthinking_proposed_task_count"] = len(tasks)
            metadata["deepthinking_desired_ability_proposal_count"] = len(plan.task_proposals)
            metadata["deepthinking_valid_task_count"] = valid_task_count
            metadata["deepthinking_proposed_effect_task_count"] = proposed_effect_count
            metadata["deepthinking_valid_effect_task_count"] = valid_effect_count
            metadata["deepthinking_proposed_action_count"] = proposed_effect_count
            metadata["deepthinking_valid_action_count"] = valid_effect_count
            if plan.reason:
                metadata["deepthinking_reason"] = self._bounded_text(plan.reason, 300)
            if plan.quick_review.decision != "none":
                metadata["quick_router_review_decision"] = plan.quick_review.decision
                if plan.quick_review.reason:
                    metadata["quick_router_review_reason"] = self._bounded_text(
                        plan.quick_review.reason,
                        300,
                    )
                if plan.quick_review.superseded_task_ids:
                    metadata["quick_router_review_superseded_task_ids"] = list(
                        plan.quick_review.superseded_task_ids[:12]
                    )
            metadata["language"] = self.language(request)
            if task_proposals:
                metadata["deepthinking_task_proposals"] = task_proposals[:12]
            superseded = self._superseded_quick_proposals(
                request,
                plan=plan,
                replacement_proposals=task_proposals,
            )
            if superseded:
                metadata["superseded_task_proposals"] = superseded[:12]
            if rejected_tasks:
                metadata["deepthinking_rejected_tasks"] = rejected_tasks[:6]
                metadata["deepthinking_rejected_actions"] = rejected_tasks[:6]

    def _superseded_quick_proposals(
        self,
        request: AgentRunRequest,
        *,
        plan: _DeepThinkingPlan,
        replacement_proposals: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if plan.quick_review.decision not in {"revise", "supersede"}:
            return []
        review_request = (request.route_decision.metadata or {}).get("quick_router_review_request")
        if not isinstance(review_request, dict):
            return []
        raw_proposals = review_request.get("quick_task_proposals")
        if not isinstance(raw_proposals, list):
            return []
        requested_ids = {
            str(item).strip()
            for item in plan.quick_review.superseded_task_ids
            if str(item).strip()
        }
        replacement_id = ""
        for proposal in replacement_proposals:
            replacement_id = str(proposal.get("id") or "").strip()
            if replacement_id:
                break
        if not replacement_id:
            replacement_id = "deepthinking:review"
        reason = (
            plan.quick_review.reason
            or plan.reason
            or "deepthinking reviewed and replaced quick router proposal"
        )
        superseded: list[dict[str, Any]] = []
        for index, proposal in enumerate(raw_proposals[:12]):
            if not isinstance(proposal, dict):
                continue
            proposal_id = str(proposal.get("id") or "").strip()
            if requested_ids and proposal_id not in requested_ids:
                continue
            task_type = str(proposal.get("task_type") or "unknown").strip() or "unknown"
            item: dict[str, Any] = {
                "id": f"{proposal_id or f'quick:{index}:{task_type}'}:superseded",
                "source": str(proposal.get("source") or "quick_intent"),
                "proposal_kind": str(proposal.get("proposal_kind") or "task"),
                "task_type": task_type,
                "state": "superseded",
                "reason": self._bounded_text(reason, 240),
                "effectful": bool(proposal.get("effectful", False)),
                "priority": str(proposal.get("priority") or "normal"),
                "sequence": self._safe_sequence(proposal.get("sequence"), index),
                "superseded_by": replacement_id,
            }
            skill_id = str(proposal.get("skill_id") or "").strip()
            if skill_id:
                item["skill_id"] = skill_id
            superseded.append(item)
        return superseded

    @staticmethod
    def _safe_sequence(value: Any, default: int) -> int:
        if isinstance(value, bool):
            return default
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return default

    def _task_proposal(
        self,
        task: _DeepThinkingTask,
        *,
        index: int,
        state: str,
        reason: str,
        skill_id: str | None = None,
        committed_by: str | None = None,
    ) -> dict[str, Any]:
        normalized_skill_id = skill_id or task.skill_id.strip()
        task_type = self._task_type_for_skill(normalized_skill_id)
        proposal = TaskProposal(
            id=f"deepthinking:{index}:{task_type}",
            source="deepthinking",
            proposal_kind="speech" if self._is_speech_task(task) else "skill",
            task_type=task_type,
            state=state,  # type: ignore[arg-type]
            reason=self._bounded_text(reason, 240),
            effectful=self._is_effectful_skill_id(normalized_skill_id),
            priority="normal",
            sequence=index,
            skill_id=normalized_skill_id,
            committed_by=committed_by,
            timing=task.timing,
            requires_confirmation=task.requires_confirmation,
            metadata={
                "has_args": bool(task.args),
                "timeout_ms": task.timeout_ms,
                "cancellable": task.cancellable,
            },
        )
        return proposal.model_dump(mode="json", exclude_none=True)

    def _desired_ability_task_proposal(
        self,
        proposal: _DeepThinkingTaskProposal,
        *,
        index: int,
        fallback_reason: str,
    ) -> dict[str, Any]:
        status = "_".join(proposal.status.strip().lower().split())
        state = "missing_ability"
        if status == "forbidden":
            state = "refused"
        elif status in {"planned", "advisory"}:
            state = "advisory"
        metadata: dict[str, Any] = {
            "intent": self._bounded_text(proposal.intent, 160),
            "status": proposal.status,
        }
        if proposal.matched_skill_id:
            metadata["matched_skill_id"] = proposal.matched_skill_id
        if proposal.confidence is not None:
            metadata["confidence"] = proposal.confidence
        item = TaskProposal(
            id=f"deepthinking:{index}:ability.requested",
            source="deepthinking",
            proposal_kind="ability",
            task_type="ability.requested",
            state=state,  # type: ignore[arg-type]
            reason=self._bounded_text(
                proposal.reason
                or fallback_reason
                or "desired ability is not executable from the supplied catalog",
                240,
            ),
            effectful=False,
            priority="normal",
            sequence=index,
            ability_id=proposal.ability_id,
            skill_id=proposal.matched_skill_id,
            metadata=metadata,
        )
        return item.model_dump(mode="json", exclude_none=True)

    @staticmethod
    def _task_type_for_skill(skill_id: str) -> str:
        if skill_id == "chromie.speak":
            return "speech.speak"
        if skill_id == "session.interrupt":
            return "task.cancel_current_action"
        if skill_id == "chromie.task_graph.execute":
            return "task.execute_task_graph"
        return "task.execute_skill"

    @staticmethod
    def _is_effectful_skill_id(skill_id: str) -> bool:
        return (
            skill_id.startswith("soridormi.")
            or skill_id == "session.interrupt"
            or skill_id == "chromie.task_graph.execute"
            or (
                skill_id.startswith("chromie.")
                and skill_id != "chromie.speak"
            )
        )

    def _normalized_tasks(self, plan: _DeepThinkingPlan) -> list[_DeepThinkingTask]:
        tasks = list(plan.tasks)
        has_speech_task = any(self._is_speech_task(task) for task in tasks)
        if plan.speech_tasks:
            tasks.extend(
                _DeepThinkingTask(
                    skill_id="chromie.speak",
                    args={
                        "text": task.text,
                        "style": task.style,
                        "priority": task.priority,
                    },
                    timing=task.timing,
                    reason=plan.reason,
                )
                for task in plan.speech_tasks
            )
            has_speech_task = True
        if plan.spoken_response and not has_speech_task:
            tasks.insert(
                0,
                _DeepThinkingTask(
                    skill_id="chromie.speak",
                    args={
                        "text": plan.spoken_response,
                        "style": "brief",
                        "priority": "normal",
                    },
                    timing="immediate",
                    reason=plan.reason,
                ),
            )
        tasks.extend(
            _DeepThinkingTask(
                skill_id=task.skill_id,
                args=task.args,
                timing=task.timing,
                timeout_ms=task.timeout_ms,
                cancellable=task.cancellable,
                requires_confirmation=task.requires_confirmation,
                reason=task.reason,
            )
            for task in plan.action_tasks
        )
        return tasks

    def _effect_tasks(self, plan: _DeepThinkingPlan) -> list[_DeepThinkingTask]:
        return [task for task in self._normalized_tasks(plan) if not self._is_speech_task(task)]

    def _first_speech_task_index(self, plan: _DeepThinkingPlan) -> int | None:
        for index, task in enumerate(plan.tasks):
            if self._is_speech_task(task):
                return index
        return None

    @staticmethod
    def _is_speech_task(task: _DeepThinkingTask) -> bool:
        return task.skill_id.strip() == "chromie.speak"

    @staticmethod
    def _speech_task_text(task: _DeepThinkingTask) -> str:
        text = task.args.get("text")
        if text is None:
            text = task.args.get("message")
        return str(text or "").strip()

    def _add_speech_skill_task(self, result: AgentResult, task: _DeepThinkingTask) -> None:
        text = self._speech_task_text(task)
        style = str(task.args.get("style") or "brief")
        priority = str(task.args.get("priority") or "normal")
        self._add_speech_task(
            result,
            _DeepThinkingSpeechTask(
                text=text,
                timing=task.timing,
                style=style,
                priority=priority,
            ),
        )

    def _add_speech_task(self, result: AgentResult, task: _DeepThinkingSpeechTask) -> None:
        text = task.text or ""
        for chunk in self._split_spoken_response(text):
            if task.timing == "after_skills":
                result.add_speak_after(
                    chunk,
                    style=task.style,
                    priority=task.priority,  # type: ignore[arg-type]
                )
                continue
            try:
                result.add_speak_immediate(
                    chunk,
                    style=task.style,
                    priority=task.priority,  # type: ignore[arg-type]
                    timing=task.timing,  # type: ignore[call-arg]
                    metadata={"source": "deepthinking_speech_task"},
                )
            except TypeError:
                result.add_speak_immediate(
                    chunk,
                    style=task.style,
                    priority=task.priority,  # type: ignore[arg-type]
                )

    def _candidate_capabilities(self, request: AgentRunRequest) -> list[dict[str, Any]]:
        candidates = request.route_decision.candidate_capabilities
        if not candidates:
            candidates = request.context.get("capability_candidates") or []
        if not isinstance(candidates, list):
            return []
        return [item for item in candidates if isinstance(item, dict)]

    def _candidate_for_task(
        self,
        task: _DeepThinkingTask,
        candidates: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        requested = task.skill_id.strip()
        if not requested:
            return None
        for candidate in candidates:
            ids = {
                str(candidate.get("capability_id") or "").strip(),
                str(candidate.get("skill_id") or "").strip(),
            }
            ids.discard("")
            if requested not in ids:
                continue
            if candidate.get("available") is False:
                return None
            if candidate.get("interaction_executable") is not True:
                return None
            return candidate
        return None

    def _candidate_skill_id(self, candidate: dict[str, Any]) -> str:
        return str(candidate.get("capability_id") or candidate.get("skill_id") or "").strip()

    @staticmethod
    def _skill_timing(task: _DeepThinkingTask) -> Literal["parallel", "sequential"]:
        return "parallel" if task.timing in {"parallel", "immediate"} else "sequential"

    def _split_spoken_response(self, response: str) -> list[str]:
        text = " ".join((response or "").strip().split())
        if not text:
            return []
        max_chars = max(1, self.services.max_speak_chars)
        max_total = max_chars * 4
        if len(text) > max_total:
            text = text[:max_total].rstrip("，,。.!！?？ ")
            text += "。" if any("\u4e00" <= ch <= "\u9fff" for ch in text) else "."
        if len(text) <= max_chars:
            return [text]

        chunks: list[str] = []
        current = ""
        for word in text.split(" "):
            candidate = f"{current} {word}".strip() if current else word
            if len(candidate) <= max_chars:
                current = candidate
                continue
            if current:
                chunks.append(current.rstrip("，,。.!！?？ "))
            if len(word) <= max_chars:
                current = word
                continue
            for offset in range(0, len(word), max_chars):
                piece = word[offset : offset + max_chars]
                if len(piece) == max_chars:
                    chunks.append(piece)
                else:
                    current = piece
        if current:
            chunks.append(current.rstrip("，,。.!！?？ "))
        return [chunk for chunk in chunks if chunk]

    def _conversation_id(self, request: AgentRunRequest) -> str | None:
        context = request.context or {}
        cid = context.get("conversation_id")
        if cid:
            return str(cid)
        conversation = context.get("conversation")
        if isinstance(conversation, dict) and conversation.get("conversation_id"):
            return str(conversation.get("conversation_id"))
        return None

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

    def _pending_tasks_from_request(self, request: AgentRunRequest) -> list[dict[str, Any]]:
        context = request.context or {}
        if "active_pending_tasks" in context:
            tasks = context.get("active_pending_tasks")
        else:
            tasks = context.get("pending_tasks")
        if not isinstance(tasks, list):
            conversation = context.get("conversation")
            if isinstance(conversation, dict):
                if "active_pending_tasks" in conversation:
                    tasks = conversation.get("active_pending_tasks")
                else:
                    tasks = conversation.get("pending_tasks")
        if not isinstance(tasks, list):
            return []
        return [task for task in tasks if isinstance(task, dict)]

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

    def _format_session_memory(self, request: AgentRunRequest, *, zh: bool) -> str:
        del zh
        memory = self._session_memory_from_request(request)
        if not memory:
            return "None"
        lines: list[str] = []
        kind = str(memory.get("kind") or "").strip()
        if kind:
            lines.append(f"- kind: {kind}")
        conversation_id = str(memory.get("conversation_id") or "").strip()
        if conversation_id:
            lines.append(f"- conversation_id: {conversation_id}")
        memory_summary = str(memory.get("memory_summary") or "").strip()
        if memory_summary and memory_summary.lower() != "none":
            for item in memory_summary.splitlines()[:8]:
                text = item.strip().lstrip("-").strip()
                if text:
                    lines.append(f"- memory: {self._bounded_text(text, 220)}")
        current_task = memory.get("current_task")
        if isinstance(current_task, dict):
            status = str(current_task.get("status") or "").strip()
            summary = " ".join(str(current_task.get("summary") or "").split())
            parts = []
            if status:
                parts.append(f"status={status}")
            if summary:
                parts.append(f"summary={self._bounded_text(summary, 220)}")
            if parts:
                lines.append(f"- current_task: {'; '.join(parts)}")
        active_tasks = memory.get("active_pending_tasks")
        if isinstance(active_tasks, list) and active_tasks:
            lines.append("- active_pending_tasks:")
            for task in active_tasks[-4:]:
                if not isinstance(task, dict):
                    continue
                task_type = " ".join(str(task.get("type") or "task").split())
                status = " ".join(str(task.get("status") or "pending").split())
                summary = " ".join(str(task.get("summary") or task_type).split())
                lines.append(
                    f"  - {task_type}: status={status}; summary={self._bounded_text(summary, 180)}"
                )
        forgetting_policy = memory.get("forgetting_policy")
        if isinstance(forgetting_policy, dict):
            policy = {
                key: forgetting_policy.get(key)
                for key in (
                    "explicit_reset_clears_history_and_tasks",
                    "hard_idle_timeout_sec",
                    "soft_idle_new_topic_timeout_sec",
                    "completed_task_retention_sec",
                    "last_split_reason",
                )
                if key in forgetting_policy
            }
            if policy:
                lines.append(
                    "- forgetting_policy: "
                    + self._bounded_text(
                        json.dumps(policy, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                        360,
                    )
                )
        return "\n".join(lines) if lines else "None"

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
        del zh
        task_context = self._task_context_from_request(request)
        if not task_context:
            return "None"
        summary = self._task_context_summary(task_context)
        return "\n".join(summary) if summary else "None"

    def _format_extracted_conversation_context(self, request: AgentRunRequest, *, zh: bool) -> str:
        del zh
        lines: list[str] = []
        conversation_id = self._conversation_id(request)
        if conversation_id:
            lines.append(f"- conversation_id: {conversation_id}")

        memory = self._session_memory_from_request(request)
        extracted_memory = memory.get("extracted_memory") if isinstance(memory, dict) else None
        if isinstance(extracted_memory, list):
            for item in extracted_memory[-6:]:
                if not isinstance(item, dict):
                    continue
                text = " ".join(str(item.get("text") or "").split())
                kind = " ".join(str(item.get("kind") or "memory").split())
                if text:
                    lines.append(f"- memory.{kind}: {self._bounded_text(text, 220)}")
        current_task = memory.get("current_task") if isinstance(memory, dict) else None
        if isinstance(current_task, dict):
            summary = " ".join(str(current_task.get("summary") or "").split())
            status = " ".join(str(current_task.get("status") or "").split())
            if summary or status:
                parts = []
                if status:
                    parts.append(f"status={status}")
                if summary:
                    parts.append(f"summary={self._bounded_text(summary, 220)}")
                lines.append(f"- current_task: {'; '.join(parts)}")

        task_context = self._task_context_from_request(request)
        if isinstance(task_context, dict):
            summary = self._task_context_summary(task_context)
            if summary:
                lines.extend(summary)

        active_contexts = memory.get("active_task_contexts") if isinstance(memory, dict) else None
        if isinstance(active_contexts, list):
            for item in active_contexts[-3:]:
                if not isinstance(item, dict) or item is task_context:
                    continue
                summary = self._task_context_summary(item, prefix="related_task")
                if summary:
                    lines.extend(summary[:2])

        pending_tasks = self._pending_tasks_from_request(request)
        if pending_tasks:
            lines.append("- active_pending_tasks:")
            for task in pending_tasks[-4:]:
                if not isinstance(task, dict):
                    continue
                task_type = " ".join(str(task.get("type") or "task").split())
                status = " ".join(str(task.get("status") or "pending").split())
                summary = " ".join(str(task.get("summary") or task_type).split())
                lines.append(
                    f"  - {task_type}: status={status}; summary={self._bounded_text(summary, 180)}"
                )

        forgetting_policy = memory.get("forgetting_policy") if isinstance(memory, dict) else None
        if isinstance(forgetting_policy, dict):
            split_reason = str(forgetting_policy.get("last_split_reason") or "").strip()
            if split_reason:
                lines.append(f"- context_boundary: last_split_reason={split_reason}")

        if not lines:
            return "None"
        return "\n".join(lines)

    def _task_context_summary(
        self,
        task_context: dict[str, Any],
        *,
        prefix: str = "task_context",
    ) -> list[str]:
        lines: list[str] = []
        header_parts: list[str] = []
        raw_like_values = {
            " ".join(str(task_context.get(key) or "").split()).casefold()
            for key in ("last_meaningful_user_turn", "last_assistant_response")
        }
        raw_like_values.discard("")
        for key in ("task_id", "status", "task_relation", "task_type", "goal"):
            value = " ".join(str(task_context.get(key) or "").split())
            if value:
                if key == "goal" and value.casefold() in raw_like_values:
                    continue
                header_parts.append(f"{key}={self._bounded_text(value, 180)}")
        if header_parts:
            lines.append(f"- {prefix}: {'; '.join(header_parts)}")

        for key in ("important_claims", "entities", "pending_questions"):
            values = self._string_items(task_context.get(key), max_items=5)
            if values:
                lines.append(f"- {prefix}.{key}: {', '.join(values)}")

        constraints = task_context.get("constraints")
        if isinstance(constraints, dict) and constraints:
            compact = json.dumps(constraints, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            lines.append(f"- {prefix}.constraints: {self._bounded_text(compact, 240)}")

        metadata = task_context.get("metadata")
        if isinstance(metadata, dict):
            route = str(metadata.get("last_route") or "").strip()
            intent = str(metadata.get("last_intent") or "").strip()
            if route or intent:
                parts = []
                if route:
                    parts.append(f"last_route={route}")
                if intent:
                    parts.append(f"last_intent={intent}")
                lines.append(f"- {prefix}.routing: {'; '.join(parts)}")
        return lines

    def _string_items(self, value: Any, *, max_items: int = 5) -> list[str]:
        if isinstance(value, str):
            candidates = [value]
        elif isinstance(value, list):
            candidates = [item for item in value if isinstance(item, str)]
        else:
            return []
        items: list[str] = []
        seen: set[str] = set()
        for item in candidates:
            text = " ".join(item.split())
            if not text:
                continue
            key = text.casefold()
            if key in seen:
                continue
            seen.add(key)
            items.append(self._bounded_text(text, 180))
            if len(items) >= max_items:
                break
        return items

    def _format_history(self, request: AgentRunRequest, *, zh: bool) -> str:
        history = self._history_from_request(request)
        if not history:
            return "无" if zh else "None"
        lines: list[str] = []
        for turn in history[-8:]:
            role = str(turn.get("role") or "unknown").lower()
            text = " ".join(str(turn.get("text") or "").split())
            if not text:
                continue
            if len(text) > 220:
                text = text[:220].rstrip() + "..."
            if zh:
                label = "用户" if role == "user" else "助手" if role == "assistant" else role
            else:
                label = "User" if role == "user" else "Assistant" if role == "assistant" else role.title()
            intent = turn.get("intent")
            suffix = f" ({intent})" if intent and role == "user" else ""
            lines.append(f"{label}{suffix}: {text}")
        return "\n".join(lines) if lines else ("无" if zh else "None")

    def _format_pending_tasks(self, request: AgentRunRequest, *, zh: bool) -> str:
        tasks = self._pending_tasks_from_request(request)
        if not tasks:
            return "无" if zh else "None"
        lines: list[str] = []
        for task in tasks[-4:]:
            task_type = str(task.get("type") or "task")
            status = str(task.get("status") or "pending")
            summary = " ".join(str(task.get("summary") or task_type).split())
            lines.append(f"- {task_type}: {status}; {summary}")
        return "\n".join(lines) if lines else ("无" if zh else "None")

    def _capability_context(self, request: AgentRunRequest, *, zh: bool) -> str:
        candidates = request.route_decision.candidate_capabilities
        if not candidates:
            candidates = request.context.get("capability_candidates") or []
        if not isinstance(candidates, list) or not candidates:
            return "无匹配能力" if zh else "No matching capabilities were supplied."
        lines: list[str] = []
        for item in candidates[:8]:
            if not isinstance(item, dict):
                continue
            capability_id = str(item.get("capability_id") or item.get("skill_id") or "")
            description = str(item.get("description") or "")
            api = json.dumps(
                item.get("input_schema") or {},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            if len(api) > 360:
                api = api[:360].rstrip() + "..."
            executable = bool(item.get("interaction_executable"))
            label = "可执行" if zh and executable else "仅供规划" if zh else "executable" if executable else "planning only"
            lines.append(f"- {capability_id}: {description} [{label}; api={api}]")
        return "\n".join(lines) if lines else ("无匹配能力" if zh else "No matching capabilities were supplied.")

    def _route_context(self, request: AgentRunRequest, *, zh: bool) -> str:
        decision = request.route_decision
        parts = [
            f"route={decision.route}",
            f"intent={decision.intent}",
            f"confidence={decision.confidence:.2f}",
            f"source={decision.source}",
        ]
        if decision.reason:
            parts.append(f"reason={decision.reason}")
        if decision.speak_first:
            parts.append(f"speak_first={decision.speak_first}")
        review_request = (decision.metadata or {}).get("quick_router_review_request")
        if isinstance(review_request, dict):
            parts.append(
                "quick_router_review_request="
                + self._bounded_json_for_prompt(review_request, max_chars=2600)
            )
        return "；".join(parts) if zh else "; ".join(parts)

    @staticmethod
    def _bounded_json_for_prompt(value: Any, *, max_chars: int) -> str:
        try:
            text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        except TypeError:
            text = json.dumps(str(value), ensure_ascii=False)
        text = " ".join(text.split())
        if len(text) > max_chars:
            return text[:max_chars].rstrip() + "..."
        return text

    def _fallback_reply(self, request: AgentRunRequest) -> str:
        if self.is_zh(request):
            return "我可以把这个复杂任务拆开，但我现在没连上深度思考模型。"
        return "I can split this into a plan, but my deep-thinking model is not responding."

    def _clean_response(self, response: str, *, zh: bool) -> str:
        response = " ".join((response or "").strip().strip('"').split())
        if not response:
            return "我没太听清，你能再说一遍吗？" if zh else "I did not catch that. Could you say it again?"

        bad_prefixes = [
            "assistant:",
            "chromie:",
            "response:",
            "spoken response:",
            "助手：",
            "回答：",
        ]
        lowered = response.lower()
        for prefix in bad_prefixes:
            if lowered.startswith(prefix):
                response = response[len(prefix) :].strip()
                break

        return response
