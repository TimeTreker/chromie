from __future__ import annotations

import json
import logging
import os
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, model_validator

try:
    from chromie_contracts.perception import live_perception_dependency_from_metadata
    from chromie_contracts.interaction import SkillRequest
    from chromie_contracts.semantic_authority import semantic_authority_from_context
    from chromie_contracts.semantic_task import InformationGap
except ImportError:  # pragma: no cover - repository development path
    from shared.chromie_contracts.perception import live_perception_dependency_from_metadata
    from shared.chromie_contracts.interaction import SkillRequest
    from shared.chromie_contracts.semantic_authority import semantic_authority_from_context
    from shared.chromie_contracts.semantic_task import InformationGap

from ..capabilities.validator import (
    normalize_args_for_schema,
    validate_args_for_schema,
)
from ..schema import AgentResult, AgentRunRequest
from .base import BaseAgent

logger = logging.getLogger("chromie.agent.capability")


class _PlannedSkill(BaseModel):
    skill_id: str
    args: dict[str, Any] = Field(default_factory=dict)
    proposed_args: dict[str, Any] = Field(default_factory=dict)
    semantic_intent: dict[str, Any] = Field(default_factory=dict)
    parameter_grounding: dict[str, Any] = Field(default_factory=dict)
    unmapped_intent: list[Any] = Field(default_factory=list)
    timing: Literal["parallel", "sequential"] = "sequential"
    step_id: str = ""
    reason: str = ""


class _CapabilityPlan(BaseModel):
    decision: Literal["execute", "propose_alternative", "clarify", "unsupported"]
    speech: str = ""
    skills: list[_PlannedSkill] = Field(default_factory=list)
    information_gaps: list[InformationGap] = Field(default_factory=list)
    plan_relation: Literal["exact", "safe_adjustment", "alternative", "partial", "none"] = "none"
    user_confirmation_required: bool = False
    original_goal_summary: str = ""
    assessment: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_plan_shape(self) -> "_CapabilityPlan":
        if self.decision in {"execute", "propose_alternative"}:
            if not self.skills:
                raise ValueError(f"decision={self.decision} requires at least one skill")
            speech = _natural_speech_or_empty(self.speech)
            if not speech:
                raise ValueError(f"decision={self.decision} requires natural speech")
            self.speech = speech
        if self.decision == "propose_alternative":
            self.user_confirmation_required = True
            if self.plan_relation == "none":
                self.plan_relation = "alternative"

        seen_steps: dict[tuple[str, str], set[str]] = {}
        for item in self.skills:
            args = item.proposed_args if item.proposed_args else item.args
            duplicate_key = (
                item.skill_id,
                json.dumps(
                    args,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    default=str,
                ),
            )
            step_id = item.step_id.strip()
            prior_step_ids = seen_steps.get(duplicate_key)
            if prior_step_ids is not None and (
                not step_id or "" in prior_step_ids or step_id in prior_step_ids
            ):
                raise ValueError(
                    "intentional repeated skills with identical arguments require "
                    "distinct non-empty step_id values"
                )
            seen_steps.setdefault(duplicate_key, set()).add(step_id)
        return self


class _CapabilityPlanReview(BaseModel):
    decision: Literal["accept", "revise", "propose_alternative", "clarify", "unsupported"]
    reason: str = ""
    speech: str = ""
    skills: list[_PlannedSkill] = Field(default_factory=list)
    plan_relation: Literal["exact", "safe_adjustment", "alternative", "partial", "none"] = "none"
    user_confirmation_required: bool = False
    assessment: dict[str, Any] = Field(default_factory=dict)


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
        # Exact Router actions are already-selected adapter input, not a second
        # semantic plan. Materialize them deterministically even when an LLM is
        # available; the CapabilityAgent must not reinterpret the utterance.
        if direct_actions:
            allowed = {match.capability_id: match for match in executable}
            selected_ids: list[str] = []
            selected_requests: list[SkillRequest] = []
            ordered_direct_actions = sorted(
                direct_actions,
                key=lambda item: int(item.get("sequence", 0)),
            )
            route_stage = self._selected_route_stage(request)
            for router_action_index, action in enumerate(ordered_direct_actions):
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
                    information_gaps = self._schema_information_gaps(
                        capability_id,
                        args,
                        match.input_schema,
                    )
                    result.add_speak_immediate(
                        self._information_gap_fallback_speech(
                            request,
                            information_gaps,
                        ),
                        style="brief",
                    )
                    result.metadata["capability_handled"] = True
                    result.metadata["capability_decision"] = "clarify"
                    result.metadata["planning_result"] = "needs_clarification"
                    result.metadata["information_gaps"] = [
                        gap.model_dump(mode="json", exclude_none=True)
                        for gap in information_gaps
                    ]
                    self._attach_task_planning_identity(request, result.metadata)
                    result.metadata["invalid_capability_args"] = {
                        "skill_id": capability_id,
                        "errors": arg_errors,
                    }
                    self.trace(
                        result,
                        f"router action args failed schema validation for {capability_id}: {arg_errors}",
                    )
                    return result
                sequence = int(action.get("sequence", len(selected_ids)))
                metadata = {
                    "source": "router_actions",
                    "source_component": "agent.capability",
                    "execution_mode": "proposed",
                    "execution_semantics": "proposal_from_route2",
                    "requires_runtime_validation": True,
                    "catalog_version": search.catalog_version,
                    "sequence": sequence,
                    "route_stage": route_stage,
                    "route_source": request.route_decision.source,
                    "route_intent": request.route_decision.intent,
                    "route_confidence": request.route_decision.confidence,
                    "router_action_index": router_action_index,
                    "router_action_count": len(ordered_direct_actions),
                    "router_compound_action_plan": len(ordered_direct_actions) > 1,
                    "router_action_sequence": sequence,
                    "capability_safety_class": match.safety_class,
                    "capability_effects": list(match.effects or []),
                    "capability_requires_confirmation": match.requires_confirmation,
                    "capability_invocation_kind": match.invocation_kind,
                    "capability_source": match.source,
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
                reason = str(action.get("reason") or "").strip()
                if reason:
                    metadata["router_action_reason"] = reason[:200]
                perception_dependency = live_perception_dependency_from_metadata(
                    action,
                    match.metadata,
                    match.hints,
                )
                if perception_dependency is not None:
                    metadata.update(perception_dependency)
                if normalized:
                    metadata["schema_normalized_args"] = True
                selected_requests.append(
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
                for request_item in selected_requests:
                    add_skill(request_item)
                speech = (
                    ""
                    if request.route_decision.speak_first or "chromie.speak" in selected_ids
                    else self._direct_action_ack_speech(request, len(selected_ids))
                )
                if speech:
                    result.add_speak_immediate(speech, style="brief")
                result.metadata["capability_handled"] = True
                result.metadata["capability_decision"] = "execute"
                result.metadata["semantic_authority_owner"] = "router_action_adapter"
                result.metadata["semantic_authority_role"] = "adapter"
                result.metadata["planning_result"] = (
                    "direct_skill" if len(selected_ids) == 1 else "composed_plan"
                )
                result.metadata["planned_skills"] = [
                    {
                        "skill_id": str(action.get("capability_id") or ""),
                        "args": dict(action.get("args") or {}),
                    }
                    for action in ordered_direct_actions
                    if isinstance(action, dict)
                ]
                self._attach_task_planning_identity(request, result.metadata)
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
        if not self.services.use_llm or self.services.ollama is None:
            self.trace(result, "capability match found but semantic LLM planning is unavailable")
            return result

        authority = None
        try:
            authority = semantic_authority_from_context(request.context)
        except ValidationError as exc:
            result.metadata["semantic_authority_rejected"] = {
                "reason": "invalid_claim",
                "error": str(exc)[:500],
            }
        legacy_authorized = (
            self.services.legacy_capability_fallback_enabled
            and authority is not None
            and authority.owner == "legacy_capability_fallback"
            and authority.role == "authoritative"
            and authority.emergency_fallback
        )
        if not legacy_authorized:
            result.add_speak_immediate(
                self._legacy_planner_disabled_speech(request),
                style="warning",
            )
            result.metadata.update(
                {
                    "capability_handled": True,
                    "capability_decision": "clarify",
                    "planning_result": "legacy_semantic_planner_disabled",
                    "semantic_authority_owner": (
                        authority.owner if authority is not None else "none"
                    ),
                    "semantic_authority_role": (
                        authority.role if authority is not None else "none"
                    ),
                    "legacy_capability_fallback_enabled": (
                        self.services.legacy_capability_fallback_enabled
                    ),
                }
            )
            self.trace(
                result,
                "semantic LLM planning rejected; CapabilityAgent is adapter-only "
                "without an explicit emergency fallback claim",
            )
            return result

        result.metadata["semantic_authority_owner"] = authority.owner
        result.metadata["semantic_authority_role"] = authority.role
        result.metadata["legacy_emergency_fallback"] = True
        plan = await self._plan(request, executable)
        plan = await self._repair_unstructured_clarification(
            request,
            plan,
            executable,
        )
        plan = self._normalize_plan_for_routed_surface(request, plan, executable)
        plan = await self._repair_parameter_plan_if_needed(
            request,
            plan,
            executable,
        )
        plan = await self._review_plan(request, plan, executable)
        plan = self._normalize_plan_for_routed_surface(request, plan, executable)
        plan = await self._repair_parameter_plan_if_needed(
            request,
            plan,
            executable,
        )
        allowed = {match.capability_id: match for match in executable}
        if plan.decision not in {"execute", "propose_alternative"}:
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
            result.metadata["planning_result"] = (
                "needs_clarification" if plan.decision == "clarify" else "unavailable"
            )
            if plan.information_gaps:
                result.metadata["information_gaps"] = [
                    gap.model_dump(mode="json", exclude_none=True)
                    for gap in plan.information_gaps
                ]
            if plan.assessment:
                result.metadata["semantic_plan_assessment"] = self._bounded_metadata_value(
                    plan.assessment,
                    max_chars=1600,
                )
                if plan.assessment.get("atomic_plan_rejected") is True:
                    result.metadata["atomic_plan_rejected"] = True
                issues = plan.assessment.get("parameter_issues")
                if isinstance(issues, list) and issues:
                    first_issue = issues[0] if isinstance(issues[0], dict) else {}
                    result.metadata["invalid_capability_args"] = {
                        "skill_id": str(first_issue.get("skill_id") or ""),
                        "errors": [
                            str(item)
                            for item in (first_issue.get("errors") or [])
                        ],
                    }
            self._attach_task_planning_identity(request, result.metadata)
            self.trace(result, f"capability decision={plan.decision}")
            return result

        # Validate the complete model-authored plan before committing any skill.
        # This is structural atomicity: deterministic code validates schemas and
        # catalog membership, but it never decides which user goal to omit or how
        # to replace it.
        selected_requests: list[SkillRequest] = []
        seen_requests: set[tuple[str, str, str]] = set()
        any_adjustment = False
        for item in plan.skills:
            match = allowed.get(item.skill_id)
            if match is None:
                logger.warning("LLM selected capability outside candidate set: %s", item.skill_id)
                result.add_speak_immediate(
                    self._information_gap_fallback_speech(
                        request,
                        [
                            InformationGap(
                                gap_id="capability-plan:available-skill",
                                description="the intended action using an available capability",
                                blocking=True,
                                required_for=["capability_plan"],
                                preferred_resolution="ask_user",
                            )
                        ],
                    ),
                    style="brief",
                )
                result.metadata.update(
                    {
                        "capability_handled": True,
                        "capability_decision": "clarify",
                        "planning_result": "needs_clarification",
                        "invalid_selected_capability_id": item.skill_id,
                        "atomic_plan_rejected": True,
                    }
                )
                self._attach_task_planning_identity(request, result.metadata)
                return result

            proposal_args = self._skill_proposal_args(item)
            args, normalized = normalize_args_for_schema(proposal_args, match.input_schema)
            adjudication_status = "executable"
            proposal_adjustments: list[dict[str, Any]] = []
            arg_errors = validate_args_for_schema(args, match.input_schema)
            if arg_errors:
                adjusted_args, proposal_adjustments = self._schema_bounded_adjustment(
                    args,
                    match.input_schema,
                )
                if proposal_adjustments:
                    adjusted_args, adjusted_normalized = normalize_args_for_schema(
                        adjusted_args,
                        match.input_schema,
                    )
                    adjusted_errors = validate_args_for_schema(
                        adjusted_args,
                        match.input_schema,
                    )
                    if not adjusted_errors:
                        args = adjusted_args
                        normalized = normalized or adjusted_normalized or adjusted_args != proposal_args
                        arg_errors = []
                        adjudication_status = "adjusted_needs_confirmation"
                        any_adjustment = True

            if arg_errors:
                logger.warning("LLM selected invalid args for %s: %s", item.skill_id, arg_errors)
                information_gaps = self._schema_information_gaps(
                    item.skill_id,
                    args,
                    match.input_schema,
                    validation_errors=arg_errors,
                )
                result.add_speak_immediate(
                    self._information_gap_fallback_speech(request, information_gaps),
                    style="brief",
                )
                result.metadata.update(
                    {
                        "capability_handled": True,
                        "capability_decision": "clarify",
                        "planning_result": "needs_clarification",
                        "information_gaps": [
                            gap.model_dump(mode="json", exclude_none=True)
                            for gap in information_gaps
                        ],
                        "invalid_capability_args": {
                            "skill_id": item.skill_id,
                            "errors": arg_errors,
                        },
                        "atomic_plan_rejected": True,
                    }
                )
                self._attach_task_planning_identity(request, result.metadata)
                self.trace(
                    result,
                    f"LLM capability args failed schema validation for {item.skill_id}: {arg_errors}",
                )
                return result

            dedupe_key = (
                item.skill_id,
                self._canonical_args_key(args),
                item.step_id.strip(),
            )
            if not item.step_id.strip() and dedupe_key in seen_requests:
                self.trace(result, f"deduped repeated capability request: {item.skill_id}")
                continue
            seen_requests.add(dedupe_key)
            metadata = {
                "source": "capability_catalog",
                "source_component": "agent.capability",
                "execution_mode": "proposed",
                "execution_semantics": "proposal_from_capability_agent",
                "requires_runtime_validation": True,
                "catalog_version": search.catalog_version,
                "semantic_plan_decision": plan.decision,
                "semantic_plan_relation": plan.plan_relation,
            }
            if item.step_id.strip():
                metadata["semantic_plan_step_id"] = item.step_id.strip()[:120]
            metadata.update(
                self._skill_proposal_metadata(
                    item,
                    proposal_args=proposal_args,
                    accepted_args=args,
                    adjudication_status=adjudication_status,
                    adjustments=proposal_adjustments,
                )
            )
            score = self._catalog_score(match)
            if score is not None:
                metadata["catalog_score"] = score
            if batched_count_metadata is not None:
                metadata.update(
                    {
                        "batched_over_limit": True,
                        "batch_index": len(selected_requests) + 1,
                        "batch_count": batched_count_metadata["batch_count"],
                        "requested_count": batched_count_metadata["requested_count"],
                        "max_per_call": batched_count_metadata["max_per_call"],
                    }
                )
            perception_dependency = live_perception_dependency_from_metadata(
                match.metadata,
                match.hints,
            )
            if perception_dependency is not None:
                metadata.update(perception_dependency)
            if normalized:
                metadata["schema_normalized_args"] = True
            selected_requests.append(
                SkillRequest(
                    skill_id=item.skill_id,
                    args=args,
                    timing=item.timing,
                    requires_confirmation=bool(match.requires_confirmation),
                    metadata=metadata,
                )
            )

        if not selected_requests:
            self.trace(result, "LLM produced no valid capability selection")
            return result

        semantic_confirmation = (
            plan.decision == "propose_alternative"
            or plan.user_confirmation_required
            or any_adjustment
        )
        if semantic_confirmation:
            selected_requests = [
                request_item.model_copy(
                    deep=True,
                    update={
                        "requires_confirmation": True,
                        "metadata": {
                            **request_item.metadata,
                            "semantic_plan_confirmation_required": True,
                        },
                    },
                )
                for request_item in selected_requests
            ]

        for request_item in selected_requests:
            add_skill(request_item)

        speech = self._natural_plan_speech(plan.speech)
        if speech and not semantic_confirmation:
            result.add_speak_immediate(speech, style="brief")
        result.metadata["capability_handled"] = True
        result.metadata["capability_decision"] = plan.decision
        result.metadata["planning_result"] = (
            "alternative_plan"
            if plan.decision == "propose_alternative"
            else "safe_adjustment"
            if plan.plan_relation == "safe_adjustment"
            else "direct_skill"
            if len(selected_requests) == 1
            else "composed_plan"
        )
        result.metadata["semantic_plan_relation"] = plan.plan_relation
        result.metadata["semantic_plan_assessment"] = self._bounded_metadata_value(
            plan.assessment,
            max_chars=1600,
        )
        if plan.original_goal_summary:
            result.metadata["original_goal_summary"] = plan.original_goal_summary[:600]
        if semantic_confirmation:
            result.metadata.update(
                {
                    "disable_body_auto_confirm": True,
                    "semantic_plan_confirmation_required": True,
                    "confirmation_prompt": speech,
                }
            )
        result.metadata["planned_skills"] = [
            {
                "skill_id": item.skill_id,
                "args": dict(item.args),
                "timing": item.timing,
                **(
                    {"step_id": str(item.metadata["semantic_plan_step_id"])}
                    if item.metadata.get("semantic_plan_step_id")
                    else {}
                ),
            }
            for item in selected_requests
        ]
        self._attach_task_planning_identity(request, result.metadata)
        result.metadata["capability_catalog_version"] = search.catalog_version
        result.metadata["capability_selected"] = [
            item.skill_id for item in selected_requests
        ]
        if batched_count_metadata is not None:
            result.metadata["capability_batched_over_limit"] = batched_count_metadata
        self.trace(result, f"selected {len(selected_requests)} catalog capability request(s)")
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
            "- Reconstruct the complete requested outcome and verify that every material component is represented.\n"
            "- Use provider/resource constraints as evidence for timing compatibility. Do not infer concurrency from skill names.\n"
            "- Review unresolved parameters semantically. A low-consequence bounded field may use an explicit schema default or a conservative ordinary value; a materially safety- or outcome-sensitive field must be asked of the user.\n"
            "- Clarification speech must ask for the exact missing fact rather than saying only that parameters are missing or movement is impossible.\n"
            "- If the proposed plan materially changes, omits, or serializes a requested component, return propose_alternative with a complete replacement plan and a natural confirmation question.\n"
            "- If a safe executable or alternative plan is not clear, revise to clarify or unsupported with no skills.\n\n"
            "Task Context Group:\n"
            f"- Latest user input: {request.text}\n"
            f"{selected_line}"
            f"- Available capability API surface: {json.dumps(candidate_payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))}\n"
            f"- Proposed capability plan JSON: {plan.model_dump_json()}\n\n"
            "Cost Function:\n"
            "- Accept only when the plan is complete, every selected skill is semantically necessary, its arguments fit the schema, and requested timing is compatible with supplied provider/resource evidence.\n"
            "- If the Router selected an exact skill_id and the proposed plan replaced it, do not use decision=accept. Revise to an executable plan that preserves the routed intent, or return clarify/unsupported with no skills.\n"
            "- Reject or revise plans that substitute a different behavior class for the user's intent, such as social acknowledgement, gaze, or attention when the user requested locomotion or another body task.\n"
            "- Prefer a clarification over executing a skill that merely seems generally robot-like but does not satisfy the request.\n"
            "- Preserve the no-raw-motor boundary and never invent skills outside the supplied API surface.\n\n"
            "Output Contract:\n"
            "- Return JSON only with keys decision, reason, speech, skills, plan_relation, user_confirmation_required, and assessment.\n"
            "- decision=accept keeps the original plan; use empty speech and skills.\n"
            "- decision=revise replaces the original exact plan and must include natural speech plus one or more exact candidate skills with schema-valid args.\n"
            "- decision=propose_alternative replaces the plan with a materially changed complete alternative, must include natural speech asking for confirmation, and must set user_confirmation_required=true.\n"
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
        if review.decision in {"revise", "propose_alternative"}:
            try:
                return _CapabilityPlan(
                    decision=(
                        "propose_alternative"
                        if review.decision == "propose_alternative"
                        else "execute"
                    ),
                    speech=speech,
                    skills=review.skills,
                    plan_relation=review.plan_relation,
                    user_confirmation_required=(
                        review.user_confirmation_required
                        or review.decision == "propose_alternative"
                    ),
                    original_goal_summary=plan.original_goal_summary,
                    assessment=review.assessment,
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

    async def _repair_unstructured_clarification(
        self,
        request: AgentRunRequest,
        plan: _CapabilityPlan,
        candidates: list[Any],
    ) -> _CapabilityPlan:
        """Ask a semantic reviewer to replace an unstructured clarification.

        A clarification without structured information gaps cannot be resumed
        reliably on a later turn. The repair model receives the complete goal
        and capability surface and may return an exact plan, an alternative, or
        a specific question. Deterministic code does not infer the missing fact.
        """

        if plan.decision != "clarify" or plan.information_gaps:
            return plan

        planners: list[Any] = []
        for candidate in (self.services.response_reviewer, self.services.ollama):
            if candidate is not None and all(candidate is not item for item in planners):
                planners.append(candidate)
        if not planners:
            return plan

        zh = self.is_zh(request)
        candidate_payload = [self._capability_payload(match) for match in candidates]
        prompt = (
            "Global Context Group:\n"
            f"{self._format_global_context(request, zh=zh)}\n\n"
            "Current Job:\n"
            "- Reconstruct the complete requested outcome from the original user utterance.\n"
            "- Replace the unstructured clarification with one of: an exact executable plan, a complete alternative proposal, or a specific structured information request.\n"
            "- Preserve every requested action and timing relation. Do not silently drop a component.\n"
            "- Resolve low-consequence missing fields semantically from schema defaults or a conservative bounded ordinary value.\n"
            "- Ask the user only for a fact that materially affects safety, authorization, target, cost, irreversible effects, or experienced action scope.\n"
            "- Do not use phrase rules and do not expose internal schema or validation terminology in speech.\n\n"
            "Task Context Group:\n"
            f"- Latest user input: {request.text}\n"
            f"- Available capability API surface: {json.dumps(candidate_payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))}\n"
            f"- Previous clarification JSON: {plan.model_dump_json()}\n\n"
            "Output Contract:\n"
            "- Return JSON only with keys decision, speech, skills, information_gaps, plan_relation, user_confirmation_required, original_goal_summary, and assessment.\n"
            "- decision is execute, propose_alternative, clarify, or unsupported.\n"
            "- clarify requires natural speech and at least one specific information_gaps item.\n"
            "- execute/propose_alternative requires the complete plan with schema-valid concrete arguments.\n"
            "- proposed alternatives that materially change timing or omit/replace a requested method require user_confirmation_required=true."
        )
        system = (
            "You are Chromie's semantic capability-plan recovery reviewer. "
            "Reason from the complete utterance and supplied capability evidence, not phrase rules. "
            "Return compact JSON only."
        )
        for planner in planners:
            try:
                raw = await planner.generate(
                    prompt,
                    system=system,
                    response_format="json",
                    options={
                        "temperature": 0,
                        "top_p": 0.8,
                        "num_ctx": int(os.getenv("AGENT_CAPABILITY_NUM_CTX", "24576")),
                        "num_predict": int(os.getenv("AGENT_CAPABILITY_PARAMETER_REPAIR_NUM_PREDICT", "384")),
                    },
                )
                repaired = _CapabilityPlan.model_validate(raw)
            except Exception as exc:
                logger.warning(
                    "capability clarification repair failed: planner=%s error_type=%s error=%s",
                    type(planner).__name__,
                    type(exc).__name__,
                    exc,
                )
                continue
            if repaired.decision == "clarify" and (
                not repaired.information_gaps
                or not self._natural_plan_speech(repaired.speech)
            ):
                continue
            assessment = dict(repaired.assessment or {})
            assessment["unstructured_clarification_repaired"] = True
            return repaired.model_copy(update={"assessment": assessment})
        return plan

    async def _repair_parameter_plan_if_needed(
        self,
        request: AgentRunRequest,
        plan: _CapabilityPlan,
        candidates: list[Any],
    ) -> _CapabilityPlan:
        """Give the semantic planner one chance to resolve concrete parameter gaps.

        The deterministic layer only identifies schema/provider mismatches.  It
        does not decide whether a missing value is harmless, materially changes
        the requested outcome, or should be asked of the user.  That decision is
        made by the LLM from the complete utterance, safety class, effects,
        schema defaults/bounds, provider constraints, and current task context.
        """

        issues = self._parameter_validation_issues(plan, candidates)
        if not issues:
            return plan

        planners: list[Any] = []
        for planner_candidate in (self.services.ollama, self.services.response_reviewer):
            if planner_candidate is not None and all(
                planner_candidate is not item for item in planners
            ):
                planners.append(planner_candidate)
        if not planners:
            return self._parameter_clarification_fallback(request, issues, candidates)

        zh = self.is_zh(request)
        candidate_payload = [self._capability_payload(match) for match in candidates]
        prompt = (
            "Global Context Group:\n"
            f"{self._format_global_context(request, zh=zh)}\n\n"
            "Session Context Group:\n"
            f"- Language: {self.language(request)}\n"
            f"- Task context: {self._bounded_text(self._format_task_context(request, zh=zh), 900)}\n"
            f"- Memory context: {self._bounded_text(self._format_memory_context(request, zh=zh), 700)}\n\n"
            "Current Job:\n"
            "- Repair the capability plan's unresolved or invalid parameters by semantic judgment.\n"
            "- Decide independently for each parameter whether to use a safe ordinary default, obtain context, or ask the user.\n"
            "- Base that decision on the supplied field description, explicit schema default, bounds, safety class, effects, provider constraints, and how materially the value changes the user's requested outcome.\n"
            "- Prefer an explicit schema default when it is suitable. If no explicit default exists, a low-consequence cosmetic or easily reversible field may use a conservative ordinary value inside the schema bounds.\n"
            "- A value that materially affects safety, destination/target, authorization, external cost, irreversible effects, or the experienced scope of a physical action must not be guessed. Ask the user for the exact missing fact instead.\n"
            "- Do not use keywords or phrase rules. Do not silently discard any requested action.\n"
            "- Never say only that parameters are missing or that Chromie cannot move. A clarification must name the exact fact needed and, when useful, offer bounded candidate choices.\n\n"
            "Task Context Group:\n"
            f"- Latest user input: {request.text}\n"
            f"- Available capability API surface: {json.dumps(candidate_payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))}\n"
            f"- Current plan JSON: {plan.model_dump_json()}\n"
            f"- Structural parameter issues JSON: {json.dumps(issues, ensure_ascii=False, sort_keys=True, separators=(',', ':'))}\n\n"
            "Output Contract:\n"
            "- Return JSON only with keys decision, speech, skills, information_gaps, plan_relation, user_confirmation_required, original_goal_summary, and assessment.\n"
            "- decision is execute, propose_alternative, clarify, or unsupported.\n"
            "- For execute/propose_alternative, output the complete plan, not just the repaired step. Every required field must be concrete and schema-valid.\n"
            "- Record how each inferred value was grounded in parameter_grounding. Use resolution values such as schema_default, use_safe_default, user_supplied, observed_context, or trusted_service, with a short rationale.\n"
            "- For clarify, output no skills. speech must ask a specific natural question. information_gaps must identify each exact missing field, why it matters, preferred_resolution, and candidate_values when the schema supplies them.\n"
            "- Do not expose skill IDs, schema field names, or internal validation errors in spoken speech."
        )
        system = (
            "You are Chromie's semantic parameter-resolution planner. "
            "Use the supplied capability contracts and consequence evidence, not phrase rules. "
            "Return compact JSON only and never authorize raw motor or joint controls."
        )
        last_issues = issues
        for planner in planners:
            try:
                raw = await planner.generate(
                    prompt,
                    system=system,
                    response_format="json",
                    options={
                        "temperature": 0,
                        "top_p": 0.8,
                        "num_ctx": int(os.getenv("AGENT_CAPABILITY_NUM_CTX", "24576")),
                        "num_predict": int(os.getenv("AGENT_CAPABILITY_PARAMETER_REPAIR_NUM_PREDICT", "384")),
                    },
                )
                repaired = _CapabilityPlan.model_validate(raw)
            except Exception as exc:
                logger.warning(
                    "capability parameter repair failed: planner=%s error_type=%s error=%s",
                    type(planner).__name__,
                    type(exc).__name__,
                    exc,
                )
                continue

            remaining = self._parameter_validation_issues(repaired, candidates)
            if repaired.decision in {"execute", "propose_alternative"} and remaining:
                logger.warning(
                    "capability parameter repair remained schema-invalid: planner=%s issues=%s",
                    type(planner).__name__,
                    remaining,
                )
                last_issues = remaining
                continue
            if repaired.decision == "clarify" and (
                not repaired.information_gaps
                or not self._natural_plan_speech(repaired.speech)
            ):
                continue
            assessment = dict(repaired.assessment or {})
            assessment["semantic_parameter_repair"] = True
            return repaired.model_copy(update={"assessment": assessment})

        return self._parameter_clarification_fallback(request, last_issues, candidates)

    def _parameter_validation_issues(
        self,
        plan: _CapabilityPlan,
        candidates: list[Any],
    ) -> list[dict[str, Any]]:
        if plan.decision not in {"execute", "propose_alternative"}:
            return []
        allowed = {
            str(getattr(match, "capability_id", "") or ""): match
            for match in candidates
        }
        issues: list[dict[str, Any]] = []
        for item in plan.skills:
            match = allowed.get(item.skill_id)
            if match is None:
                issues.append(
                    {
                        "skill_id": item.skill_id,
                        "errors": ["skill is not present in the supplied capability surface"],
                    }
                )
                continue
            proposal_args = self._skill_proposal_args(item)
            normalized_args, _ = normalize_args_for_schema(
                proposal_args,
                match.input_schema,
            )
            errors = validate_args_for_schema(normalized_args, match.input_schema)
            if errors:
                adjusted_args, adjustments = self._schema_bounded_adjustment(
                    normalized_args,
                    match.input_schema,
                )
                if adjustments:
                    adjusted_args, _ = normalize_args_for_schema(
                        adjusted_args,
                        match.input_schema,
                    )
                    if not validate_args_for_schema(adjusted_args, match.input_schema):
                        # The normal atomic validation path will apply and audit
                        # this bounded adjustment. It is not a missing-parameter
                        # question and does not need a second semantic model call.
                        continue
            if not errors:
                continue
            issues.append(
                {
                    "skill_id": item.skill_id,
                    "proposed_args": proposal_args,
                    "normalized_args": normalized_args,
                    "errors": errors,
                    "input_schema": self._compact_input_schema(match.input_schema),
                    "safety_class": str(getattr(match, "safety_class", "") or ""),
                    "effects": list(getattr(match, "effects", []) or []),
                    "requires_confirmation": bool(getattr(match, "requires_confirmation", False)),
                    "execution_constraints": dict(
                        getattr(match, "execution_constraints", {}) or {}
                    ),
                }
            )
        return issues

    def _parameter_clarification_fallback(
        self,
        request: AgentRunRequest,
        issues: list[dict[str, Any]],
        candidates: list[Any],
    ) -> _CapabilityPlan:
        by_id = {
            str(getattr(match, "capability_id", "") or ""): match
            for match in candidates
        }
        gaps: list[InformationGap] = []
        for issue in issues:
            skill_id = str(issue.get("skill_id") or "").strip()
            match = by_id.get(skill_id)
            if match is None:
                continue
            gaps.extend(
                self._schema_information_gaps(
                    skill_id,
                    issue.get("normalized_args") if isinstance(issue.get("normalized_args"), dict) else {},
                    match.input_schema,
                    validation_errors=(
                        [str(item) for item in issue.get("errors", [])]
                        if isinstance(issue.get("errors"), list)
                        else []
                    ),
                )
            )
        if not gaps:
            gaps = [
                InformationGap(
                    gap_id="capability-plan:required-detail",
                    description=(
                        "需要你补充确认的动作细节"
                        if self.is_zh(request)
                        else "the action detail that still needs confirmation"
                    ),
                    blocking=True,
                    required_for=["capability_plan"],
                    preferred_resolution="ask_user",
                )
            ]
        return _CapabilityPlan(
            decision="clarify",
            speech=self._information_gap_fallback_speech(request, gaps),
            information_gaps=gaps,
            plan_relation="none",
            assessment={
                "atomic_plan_rejected": True,
                "parameter_repair_fallback": True,
                "parameter_issues": issues[:6],
            },
        )

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

    def _selected_route_stage(self, request: AgentRunRequest) -> str:
        metadata = request.route_decision.metadata or {}
        route_merge = metadata.get("route_merge")
        if isinstance(route_merge, dict):
            selected_stage = str(route_merge.get("selected_stage") or "").strip()
            if selected_stage:
                return selected_stage
        route_stage_outputs = metadata.get("route_stage_outputs")
        if isinstance(route_stage_outputs, list):
            for output in reversed(route_stage_outputs):
                if not isinstance(output, dict):
                    continue
                status = str(output.get("status") or "").strip()
                if status == "passed":
                    continue
                stage = str(output.get("stage") or "").strip()
                if stage:
                    return stage
        return "quick_intent"

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

    @staticmethod
    def _skill_proposal_args(item: _PlannedSkill) -> dict[str, Any]:
        """Return the LLM's proposed executable args for schema adjudication.

        ``args`` remains the backward-compatible contract. ``proposed_args`` is
        the preferred proposal form because it makes the LLM/skill-agent split
        explicit: the LLM proposes semantic parameters, and this CapabilityAgent
        adjudicates them against the concrete skill schema before creating a
        trusted SkillRequest.
        """

        if isinstance(item.proposed_args, dict) and item.proposed_args:
            return dict(item.proposed_args)
        return dict(item.args or {})

    def _skill_proposal_metadata(
        self,
        item: _PlannedSkill,
        *,
        proposal_args: dict[str, Any],
        accepted_args: dict[str, Any],
        adjudication_status: str,
        adjustments: list[dict[str, Any]],
    ) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "proposal_adjudication_status": adjudication_status,
        }
        if proposal_args != accepted_args:
            metadata["proposal_requested_args"] = dict(proposal_args)
            metadata["proposal_accepted_args"] = dict(accepted_args)
        if item.semantic_intent:
            metadata["proposal_semantic_intent"] = self._bounded_metadata_value(
                item.semantic_intent,
                max_chars=900,
            )
        if item.parameter_grounding:
            metadata["proposal_parameter_grounding"] = self._bounded_metadata_value(
                item.parameter_grounding,
                max_chars=1200,
            )
        if item.unmapped_intent:
            metadata["proposal_unmapped_intent"] = self._bounded_metadata_value(
                item.unmapped_intent,
                max_chars=700,
            )
        if adjustments:
            metadata["proposal_adjustments"] = adjustments
            metadata["proposal_adjusted_requires_confirmation"] = True
        return metadata

    @staticmethod
    def _bounded_metadata_value(value: Any, *, max_chars: int) -> Any:
        try:
            text = json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        except TypeError:
            text = repr(value)
        if len(text) <= max_chars:
            return value
        return {
            "truncated": True,
            "summary_json": text[:max_chars].rstrip() + "...",
        }

    def _schema_bounded_adjustment(
        self,
        args: dict[str, Any],
        schema: dict[str, Any],
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Bound numeric proposal fields to schema limits when that is enough.

        This is the generic skill-agent adjudication step. It does not infer
        human language. The LLM may propose ``duration_s=15`` or a velocity that
        is too high; this function only asks whether the concrete skill schema
        can accept a safer bounded version. Any adjustment is marked for user
        confirmation by the caller.
        """

        if not isinstance(args, dict) or not isinstance(schema, dict):
            return dict(args or {}), []
        properties = schema.get("properties")
        if not isinstance(properties, dict):
            return dict(args), []

        adjusted = dict(args)
        adjustments: list[dict[str, Any]] = []
        for field, prop in properties.items():
            if field not in adjusted or not isinstance(prop, dict):
                continue
            value = adjusted[field]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            bounded = float(value)
            reason = ""
            maximum = prop.get("maximum")
            minimum = prop.get("minimum")
            if isinstance(maximum, (int, float)) and not isinstance(maximum, bool) and bounded > float(maximum):
                bounded = float(maximum)
                reason = "bounded_to_schema_maximum"
            if isinstance(minimum, (int, float)) and not isinstance(minimum, bool) and bounded < float(minimum):
                bounded = float(minimum)
                reason = "bounded_to_schema_minimum"
            if reason and bounded != float(value):
                adjusted[field] = int(bounded) if isinstance(value, int) and bounded.is_integer() else bounded
                adjustments.append(
                    {
                        "field": str(field),
                        "requested": value,
                        "adjusted": adjusted[field],
                        "reason": reason,
                    }
                )
        return adjusted, adjustments

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
            "Self Model:\n"
            f"{self._bounded_json(mind.get('self_model') or identity or none_text, 420)}\n\n"
            "Worldview:\n"
            "- Chromie is the speaking and acting entity described by the supplied self model. Use only supplied runtime context and abilities as evidence.\n"
            "- Spoken planning text should be natural and foreground the current goal, not volunteer system category, embodiment category, age label, or internal architecture.\n"
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
            "You generate semantic skill proposals with schema-grounded proposed_args, semantic_intent, parameter_grounding, and unmapped_intent; downstream runtime and Soridormi may accept, adjust, require confirmation, or refuse them. "
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
            "- Use the upper context as background; output execute, propose_alternative, clarify, or unsupported.\n"
            "- First reconstruct the complete requested outcome, including every requested action, relation, timing, and constraint.\n"
            "- For execute, produce a complete semantic plan that preserves the requested outcome.\n"
            "- Use propose_alternative when available capabilities, schemas, provider constraints, or safety context require a material change such as omitting a requested action, changing concurrency to sequence, or substituting a different method.\n"
            "- A proposed alternative must not execute until the user confirms it.\n"
            "- Do not answer unrelated chat here; return unsupported with no skills when no physical/tool skill should run.\n\n"
            "Task Context Group:\n"
            f"- Latest user input: {request.text}\n"
            f"- {selected_line.rstrip()}\n"
            f"- Available capability API surface: {json.dumps(candidate_payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))}\n"
            "- Ability interpretation: choose only from the provided skill_id values and satisfy that candidate's input_schema.\n"
            "- Treat can_run_parallel, exclusive_group, resource_claims, and execution_constraints as provider/runtime evidence about whether skills may overlap.\n"
            "- Do not infer concurrency from a skill name. If the evidence does not support overlap, do not claim simultaneous execution.\n"
            "- If Router-selected exact skill_id is best, use it; if another candidate better satisfies the action/schema, choose that candidate.\n"
            "- Treat modifiers such as direction, duration, distance, count, speed, urgency, target, and object references as semantic parameter intent. Ground them to schema fields when the schema exposes a compatible field.\n"
            "- If the schema does not expose a field for a user modifier, do not invent that field; place the unsupported modifier in unmapped_intent and explain briefly in speech when it matters.\n"
            "- Polite ability-shaped requests can be action requests when they ask Chromie to perform a listed physical action now.\n"
            "- For questions, identity/status, greetings, jokes, stories, songs, or other speech-only conversation, return unsupported with no skills.\n"
            "- Never combine an unrelated spoken answer with a body skill.\n"
            "- Use recent conversation/task context for follow-ups; distinguish gaze/attention/orientation from locomotion by meaning and descriptions.\n\n"
            "Cost Function:\n"
            "- Choose the smallest complete validated set of executable skills. Completeness means every material part of the reconstructed user goal is either satisfied or explicitly represented in an alternative proposal.\n"
            "- Prefer human-facing wrapper skills over lower-level velocity/control skills when both satisfy the request.\n"
            "- Preserve the user's intended action class. Do not use social acknowledgement, gaze, attention, or idle gestures as fallback actions for an unrelated body request.\n"
            "- Convert human modifiers into schema-grounded proposal args, but let schema and runtime bound the final executable parameters.\n"
            "- Resolve missing parameters semantically before giving up: inspect the field description, schema default, bounds, safety class, effects, provider constraints, and how materially the value changes the user's outcome.\n"
            "- For a low-consequence, easily reversible parameter, prefer an explicit schema default; when no explicit default exists, you may choose a conservative ordinary value inside the supplied bounds and record that choice in parameter_grounding as use_safe_default.\n"
            "- Do not guess a parameter whose value materially affects safety, target/direction, authorization, external cost, irreversible effects, or the experienced scope of a physical action. Ask the user for that exact fact.\n"
            "- A clarification must name the exact missing fact and, where useful, offer bounded choices. Never answer only that parameters are missing or that Chromie cannot move.\n"
            "- If a safe adjustment preserves the user's outcome without removing a requested component, you may return execute with plan_relation=safe_adjustment and explain it briefly. Set user_confirmation_required=true when the adjustment materially changes what the user will experience.\n"
            "- If a requested component cannot be included, or requested parallel timing cannot be honored, return propose_alternative rather than silently dropping or serializing it.\n"
            "- If the request needs deeper task decomposition, runtime evidence, or a multi-session plan, clarify or return unsupported instead of guessing a physical skill.\n"
            "- Clarify when a required parameter is missing; unsupported when no candidate can satisfy the request.\n"
            "- For clarify, information_gaps should describe the missing semantic facts, why they block planning, and whether they should be resolved by ask_user, observe_environment, query_trusted_service, use_owner_approved_preference, use_safe_default, or unresolvable.\n"
            "- Do not ask the user for a world fact Chromie can observe or query from a trusted service.\n"
            "- Prefer natural, brief speech that accurately describes only the selected plan.\n\n"
            "Output Contract:\n"
            "- Return JSON only with keys decision, speech, skills, information_gaps, plan_relation, user_confirmation_required, original_goal_summary, and assessment.\n"
            "- decision must be execute, propose_alternative, clarify, or unsupported.\n"
            "- plan_relation must be exact, safe_adjustment, alternative, partial, or none.\n"
            "- original_goal_summary must briefly capture the complete requested outcome.\n"
            "- assessment should explain goal coverage, provider/resource compatibility, safety considerations, and any changed or omitted requirement in structured fields.\n"
            "- When decision is execute, skills is required and must contain at least one item. Never return execute with skills omitted, empty, null, or only speech.\n"
            "- Each execute or propose_alternative item must include skill_id and may include args or proposed_args. skill_id must be an exact candidate skill_id.\n"
            "- Each skill item may include timing=parallel or sequential and an optional stable step_id. Use distinct step_id values when the complete plan intentionally repeats the same skill with identical args. Use parallel only when explicit supplied provider/resource evidence permits overlap; absent or undeclared parallel metadata is not proof of compatibility.\n"
            "- Prefer proposed_args when you are translating human intent into concrete parameters; args remains accepted for backward compatibility.\n"
            "- Optional proposal fields are semantic_intent, parameter_grounding, and unmapped_intent. Use them to explain how user intent maps to schema fields.\n"
            "- For each inferred parameter, parameter_grounding should state a resolution such as schema_default, use_safe_default, user_supplied, observed_context, or trusted_service, plus a brief rationale.\n"
            "- proposed_args/args must use only fields from that candidate's input_schema. Do not invent fields for unsupported modifiers.\n"
            "- For execute, every skills item must contain schema-grounded proposed_args or args that the capability layer can validate or safely bound.\n"
            "- For execute, speech is required: write one natural brief sentence generated from the chosen capability descriptions, user wording, and validated args.\n"
            "- For propose_alternative, speech is required and must naturally explain the material change and ask whether the user accepts that complete alternative.\n"
            "- Do not return a partial executable plan under decision=execute.\n"
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
                _PlannedSkill(
                    skill_id="soridormi.look_at_person",
                    args=args,
                    timing=item.timing,
                    step_id=item.step_id,
                    reason=item.reason,
                    semantic_intent=item.semantic_intent,
                    parameter_grounding=item.parameter_grounding,
                    unmapped_intent=item.unmapped_intent,
                )
            )
            changed = True
        if not changed:
            return plan
        try:
            return _CapabilityPlan(
                decision=plan.decision,
                speech=plan.speech,
                skills=normalized_skills,
                information_gaps=plan.information_gaps,
                plan_relation=plan.plan_relation,
                user_confirmation_required=plan.user_confirmation_required,
                original_goal_summary=plan.original_goal_summary,
                assessment=plan.assessment,
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

    def _capability_payload(self, match: Any) -> dict[str, Any]:
        description = " ".join(str(getattr(match, "description", "") or "").split())
        if len(description) > 140:
            description = description[:140].rstrip() + "..."
        payload: dict[str, Any] = {
            "skill_id": str(getattr(match, "capability_id", "")),
            "description": description,
            "input_schema": self._compact_input_schema(getattr(match, "input_schema", {}) or {}),
            "effects": list(getattr(match, "effects", []) or []),
            "safety_class": str(getattr(match, "safety_class", "") or ""),
            "requires_confirmation": bool(getattr(match, "requires_confirmation", False)),
            "available": bool(getattr(match, "available", False)),
            "can_run_parallel": getattr(match, "can_run_parallel", None),
            "parallel_metadata_declared": bool(
                getattr(match, "parallel_metadata_declared", False)
            ),
            "exclusive_group": getattr(match, "exclusive_group", None),
            "resource_claims": list(getattr(match, "resource_claims", []) or []),
            "execution_constraints": dict(
                getattr(match, "execution_constraints", {}) or {}
            ),
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
                for key in (
                    "type",
                    "enum",
                    "minimum",
                    "maximum",
                    "exclusiveMinimum",
                    "exclusiveMaximum",
                    "default",
                    "unit",
                    "units",
                    "description",
                    "examples",
                    "x-chromie-resolution",
                    "x-chromie-default-policy",
                ):
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

    @staticmethod
    def _schema_information_gaps(
        skill_id: str,
        args: dict[str, Any],
        schema: dict[str, Any],
        *,
        validation_errors: list[str] | None = None,
    ) -> list[InformationGap]:
        required = schema.get("required") if isinstance(schema, dict) else []
        properties = schema.get("properties") if isinstance(schema, dict) else {}
        if not isinstance(required, list):
            required = []
        if not isinstance(properties, dict):
            properties = {}
        gaps: list[InformationGap] = []
        invalid_fields: set[str] = set()
        for error in validation_errors or []:
            for field_name in properties:
                if f"args.{field_name}" in error or repr(field_name) in error:
                    invalid_fields.add(str(field_name))
        for field_name in required:
            name = str(field_name)
            if name in args and name not in invalid_fields:
                continue
            field_schema = properties.get(name)
            if not isinstance(field_schema, dict):
                field_schema = {}
            description = " ".join(
                str(
                    field_schema.get("description")
                    or field_schema.get("title")
                    or f"Required value for {name}"
                ).strip().split()
            )
            resolution = str(
                field_schema.get("x-chromie-resolution")
                or field_schema.get("resolution")
                or "ask_user"
            )
            if resolution not in {
                "ask_user",
                "observe_environment",
                "query_trusted_service",
                "use_owner_approved_preference",
                "use_safe_default",
                "unresolvable",
            }:
                resolution = "ask_user"
            enum = field_schema.get("enum")
            candidate_values = list(enum) if isinstance(enum, list) else []
            gaps.append(
                InformationGap(
                    gap_id=f"{skill_id}:{name}",
                    description=description,
                    blocking=True,
                    required_for=[skill_id],
                    preferred_resolution=resolution,  # type: ignore[arg-type]
                    candidate_values=candidate_values,
                    metadata={"schema_field": name, "skill_id": skill_id},
                )
            )
        for name in sorted(invalid_fields):
            if any(gap.metadata.get("schema_field") == name for gap in gaps):
                continue
            field_schema = properties.get(name)
            if not isinstance(field_schema, dict):
                field_schema = {}
            description = " ".join(
                str(
                    field_schema.get("description")
                    or field_schema.get("title")
                    or f"a valid value for {name}"
                ).strip().split()
            )
            enum = field_schema.get("enum")
            candidate_values = list(enum) if isinstance(enum, list) else []
            gaps.append(
                InformationGap(
                    gap_id=f"{skill_id}:{name}",
                    description=description,
                    blocking=True,
                    required_for=[skill_id],
                    preferred_resolution="ask_user",
                    candidate_values=candidate_values,
                    metadata={
                        "schema_field": name,
                        "skill_id": skill_id,
                        "validation_errors": [
                            error
                            for error in (validation_errors or [])
                            if f"args.{name}" in error or repr(name) in error
                        ][:4],
                    },
                )
            )
        return gaps

    def _attach_task_planning_identity(
        self,
        request: AgentRunRequest,
        metadata: dict[str, Any],
    ) -> None:
        task_context = self._task_context_from_request(request)
        if not isinstance(task_context, dict):
            return
        task_id = str(task_context.get("task_id") or "").strip()
        if task_id:
            metadata["task_id"] = task_id
        try:
            goal_version = int(task_context.get("goal_version") or 1)
        except (TypeError, ValueError):
            goal_version = 1
        metadata["goal_version"] = max(1, goal_version)

    def _information_gap_fallback_speech(
        self,
        request: AgentRunRequest,
        gaps: list[InformationGap],
    ) -> str:
        descriptions = [
            " ".join(gap.description.strip().split())
            for gap in gaps
            if gap.blocking and gap.description.strip()
        ][:3]
        if not descriptions:
            return (
                "请告诉我完成这个动作所需的具体信息。"
                if self.is_zh(request)
                else "Please tell me the specific information needed for this action."
            )
        if self.is_zh(request):
            return "请告诉我：" + "；".join(descriptions) + "。"
        return "Please tell me: " + "; ".join(descriptions) + "."

    def _legacy_planner_disabled_speech(self, request: AgentRunRequest) -> str:
        if self.is_zh(request):
            return (
                "这次没有经过统一目标规划，我不会启动旧的动作规划器。"
                "请稍后重试，或由运维显式启用应急回退。"
            )
        return (
            "This turn did not pass through the unified goal planner, so I will "
            "not start the legacy action planner. Please retry or use an "
            "explicit operator-enabled emergency fallback."
        )

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
