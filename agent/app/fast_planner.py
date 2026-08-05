from __future__ import annotations

import copy
import hashlib
import json
import logging
from typing import Any

from pydantic import ValidationError

from .capabilities.catalog import CapabilityCatalog
from .clients.ollama_client import OllamaClient, llm_failure_metadata
from .agent_skills import agent_skill_prompt_section
from .cognitive_identity import (
    IDENTITY_SEMANTIC_CONTRACT,
    PERSONALITY_SEMANTIC_CONTRACT,
    bounded_identity_json,
    bounded_personality_json,
)
from .planner_contract import (
    canonical_goal_grounding,
    canonical_plan_response_schema,
    goal_association_prompt_projection,
    coordinated_action_goal_ids,
    evidence_bound_dialogue,
    expected_goal_ids,
    fast_multi_goal_response_schema,
    is_planner_step_skill,
    materialize_goal_outcomes,
    materialize_planner_metadata,
    parallel_plan_contract_errors,
    planner_response_goal_ids,
    planner_contract_diagnostics,
    review_coordinated_action_plan_coverage,
    validate_explicit_numeric_parameter_grounding,
    validate_external_response_evidence_boundary,
    validate_goal_binding_argument_grounding,
    validate_goal_responsibility_outcomes,
    validate_planner_model_output,
)
from .schema import AgentRunRequest

try:
    from chromie_runtime.cognitive_integrity_events import cognitive_integrity_metadata
    from chromie_runtime.llm_diagnostics import cognition_text_reference
    from chromie_runtime.runtime_trace import TraceModule, runtime_tracer
except ImportError:  # pragma: no cover
    from shared.chromie_runtime.cognitive_integrity_events import cognitive_integrity_metadata
    from shared.chromie_runtime.llm_diagnostics import cognition_text_reference
    from shared.chromie_runtime.runtime_trace import TraceModule, runtime_tracer

try:
    from chromie_contracts.plan import CanonicalPlan
except ImportError:  # pragma: no cover
    from shared.chromie_contracts.plan import CanonicalPlan

logger = logging.getLogger("chromie.agent.fast_planner")


class FastPlannerResolver:
    """Low-latency semantic planner over the executable common catalog only."""

    TRACE_MODULE = TraceModule(
        name="agent.fast_planner",
        component_type="planner",
        implementation="FastPlannerResolver",
        schema_version=1,
    )

    def __init__(
        self,
        ollama: OllamaClient,
        catalog: CapabilityCatalog,
        *,
        min_confidence: float = 0.8,
        num_ctx: int = 8192,
        num_predict: int = 2048,
        max_capabilities: int = 24,
        max_contract_repairs: int = 1,
    ) -> None:
        self.ollama = ollama
        self.catalog = catalog
        self.min_confidence = max(0.0, min(1.0, float(min_confidence)))
        self.num_ctx = max(2048, int(num_ctx))
        self.num_predict = max(128, int(num_predict))
        self.max_capabilities = max(1, min(64, int(max_capabilities)))
        self.max_contract_repairs = max(0, min(1, int(max_contract_repairs)))

    async def resolve(self, request: AgentRunRequest) -> CanonicalPlan:
        trace_scope = runtime_tracer.continue_from_context(request.context)
        if not trace_scope.enabled:
            return await self._resolve(request)
        try:
            async with trace_scope:
                async with runtime_tracer.span(
                    module=self.TRACE_MODULE,
                    operation="resolve",
                    attributes={
                        "num_ctx": self.num_ctx,
                        "num_predict": self.num_predict,
                        "max_capabilities": self.max_capabilities,
                    },
                ) as span:
                    result = await self._resolve(request)
                    span.set_attribute("disposition", result.disposition)
                    span.set_attribute("coverage", result.coverage)
                    span.set_attribute("step_count", len(result.steps))
                    span.set_attribute("goal_count", len(result.goal_ids))
                    path = str(result.metadata.get("path_classification") or "")
                    if path:
                        span.set_attribute("path_classification", path)
                    if result.metadata.get("failure_class"):
                        span.set_status("error")
        except BaseException:
            trace_scope.finish(state="abandoned")
            raise
        trace_scope.finish(state="complete")
        runtime_tracer.attach_fragment(result.metadata, trace_scope)
        return result

    async def _resolve(self, request: AgentRunRequest) -> CanonicalPlan:
        plan_id = self._plan_id(request)
        capabilities = await self.catalog.prompt_entries(scope="common", refresh=False)
        executable = [
            item
            for item in capabilities
            if item.available
            and item.interaction_executable
            and is_planner_step_skill(item.capability_id)
        ]
        source_route = str(request.route_decision.route or "").strip()
        response_only = source_route == "chat"
        requires_execution = source_route == "tool"
        if response_only:
            executable = []
        elif requires_execution:
            # Cognitive Core already established the effect envelope. A tool
            # lane may choose among tool capabilities, but it must never drift
            # into a body gesture merely because that capability is common.
            executable = [
                item for item in executable if str(item.route) == "tool"
            ]
        capability_payload = [
            {
                "capability_id": item.capability_id,
                "description": item.description,
                "input_schema": item.input_schema,
                "requires_confirmation": item.requires_confirmation,
                "can_run_parallel": item.can_run_parallel,
                "parallel_metadata_declared": item.parallel_metadata_declared,
                "exclusive_group": item.exclusive_group,
                "resource_claims": list(item.resource_claims),
                "effects": list(item.effects),
                "safety_class": item.safety_class,
                "hints": dict(item.hints),
            }
            for item in executable[: self.max_capabilities]
        ]
        context = request.context if isinstance(request.context, dict) else {}
        expected_goal_ids_for_turn = expected_goal_ids(context)
        authoritative_goals = canonical_goal_grounding(context)
        response_goal_ids = sorted(planner_response_goal_ids(authoritative_goals))
        multi_goal_contract = len(expected_goal_ids_for_turn) > 1
        contract_schema = (
            "FastPlannerMultiGoalPlanOutput"
            if multi_goal_contract
            else "FastPlannerModelOutput"
        )
        response_schema = (
            fast_multi_goal_response_schema(
                expected_goal_ids=expected_goal_ids_for_turn,
                allowed_skill_ids=[
                    item["capability_id"] for item in capability_payload
                ],
                response_only=response_only,
                requires_execution=requires_execution,
                response_goal_ids=response_goal_ids,
            )
            if multi_goal_contract
            else canonical_plan_response_schema(
                planner_tier="fast",
                expected_goal_ids=expected_goal_ids_for_turn,
                allowed_skill_ids=[
                    item["capability_id"] for item in capability_payload
                ],
                response_only=response_only,
                requires_execution=requires_execution,
                response_goal_ids=response_goal_ids,
            )
        )
        options = {
            "temperature": 0,
            "top_p": 0.9,
            "num_ctx": self.num_ctx,
            "num_predict": self.num_predict,
        }
        previous_raw: Any = None
        initial_raw_output: Any = None
        initial_validation_errors = ""
        contract_repair_attempted = False

        for attempt in range(self.max_contract_repairs + 1):
            raw: Any = None
            try:
                active_response_schema = (
                    self._repair_response_schema(
                        response_schema,
                        initial_raw_output,
                        expected_goal_ids_for_turn=expected_goal_ids_for_turn,
                    )
                    if contract_repair_attempted
                    else response_schema
                )
                raw = await self.ollama.generate(
                    self._prompt(
                        request,
                        capability_payload,
                        response_schema=response_schema,
                        previous_raw=previous_raw,
                        validation_errors=initial_validation_errors,
                    ),
                    system=(
                        self._repair_system_prompt()
                        if contract_repair_attempted
                        else self._system_prompt()
                    ),
                    options=options,
                    response_format=active_response_schema,
                    prompt_family=(
                        "fast_planner.repair"
                        if contract_repair_attempted
                        else "fast_planner.primary"
                    ),
                    turn_id=request.sid,
                    attempt=attempt + 1,
                )
                if not isinstance(raw, dict):
                    raise ValueError("fast planner response is not a JSON object")
                normalized = (
                    self._normalize_multi_goal(
                        raw,
                        request=request,
                        plan_id=plan_id,
                        expected_goal_ids_for_turn=expected_goal_ids_for_turn,
                    )
                    if multi_goal_contract
                    else self._normalize(
                        raw,
                        request=request,
                        plan_id=plan_id,
                        expected_goal_ids_for_turn=expected_goal_ids_for_turn,
                    )
                )
                plan = CanonicalPlan.model_validate(normalized)
                validated_model_output = validate_planner_model_output(
                    raw,
                    planner_tier="fast",
                    expected_goal_ids_for_turn=expected_goal_ids_for_turn,
                )
                authoritative_goals = canonical_goal_grounding(request.context)
                validate_explicit_numeric_parameter_grounding(
                    validated_model_output,
                    authoritative_goals=authoritative_goals,
                )
                validate_goal_binding_argument_grounding(
                    validated_model_output,
                    authoritative_goals=authoritative_goals,
                )
                validate_external_response_evidence_boundary(
                    validated_model_output,
                    context=request.context,
                )
            except Exception as exc:
                failure = llm_failure_metadata(exc)
                logger.warning(
                    "fast_planner_inference_failed sid=%s attempt=%s error_type=%s error=%s "
                    "failure_class=%s failure_domain=%s architecture_attribution=%s retryable=%s",
                    request.sid,
                    attempt + 1,
                    type(exc).__name__,
                    exc,
                    failure["failure_class"],
                    failure["failure_domain"],
                    failure["architecture_attribution"],
                    failure["retryable"],
                )
                if (
                    attempt < self.max_contract_repairs
                    and isinstance(exc, (ValidationError, json.JSONDecodeError, ValueError))
                ):
                    contract_repair_attempted = True
                    initial_raw_output = raw
                    # Regenerate from authoritative grounding instead of asking
                    # the model to edit invalid JSON in place.  In live runs,
                    # copy-editing caused validator text to be embedded inside
                    # rationale strings while required fields stayed missing.
                    previous_raw = None
                    initial_validation_errors = self._validation_error_json(
                        exc,
                        raw=raw,
                        expected_goal_ids_for_turn=expected_goal_ids_for_turn,
                    )
                    logger.warning(
                        "fast_planner_contract_repair_start sid=%s validation_errors=%s "
                        "raw_output_ref=%s raw_output=%s",
                        request.sid,
                        initial_validation_errors,
                        cognition_text_reference(initial_raw_output),
                        self._bounded(initial_raw_output, 4000),
                    )
                    continue
                logger.warning(
                    "fast_planner_contract_failure_evidence sid=%s "
                    "initial_raw_output_ref=%s repair_raw_output_ref=%s "
                    "initial_raw_output=%s repair_raw_output=%s",
                    request.sid,
                    cognition_text_reference(initial_raw_output),
                    cognition_text_reference(
                        raw if contract_repair_attempted else None
                    ),
                    self._bounded(initial_raw_output, 4000)
                    if initial_raw_output is not None
                    else "",
                    self._bounded(raw, 4000)
                    if contract_repair_attempted and raw is not None
                    else "",
                )
                integrity_metadata = cognitive_integrity_metadata(stage="fast_planner", exc=exc, request=request)
                return self._escalation(
                    plan_id,
                    request,
                    "fast_planner_model_contract_failed"
                    if contract_repair_attempted
                    else "fast_planner_unavailable",
                    error=exc,
                    path_classification="contract_failure",
                    metadata={
                        "contract_schema": contract_schema,
                        "canonical_contract": "CanonicalPlan",
                        "contract_repair_attempted": contract_repair_attempted,
                        "contract_repair_succeeded": False,
                        "initial_validation_errors": initial_validation_errors,
                        "initial_raw_output_ref": cognition_text_reference(
                            initial_raw_output
                        ),
                        "repair_raw_output_ref": cognition_text_reference(
                            raw if contract_repair_attempted else None
                        ),
                        **integrity_metadata,
                    },
                )

            validated = self._validate(
                plan,
                capability_payload=capability_payload,
                request=request,
                expected_goal_ids_for_turn=expected_goal_ids_for_turn,
            )
            coordinated_goal_ids = coordinated_action_goal_ids(
                canonical_goal_grounding(request.context)
            )
            if (
                coordinated_goal_ids.intersection(validated.goal_ids)
                and validated.disposition in {"execute", "mixed"}
                and validated.steps
            ):
                try:
                    coverage_review = await review_coordinated_action_plan_coverage(
                        self.ollama,
                        request_text=request.text,
                        language=str(request.language or "und"),
                        authoritative_goals=canonical_goal_grounding(request.context),
                        plan=validated,
                        capabilities=capability_payload,
                        num_ctx=self.num_ctx,
                    )
                except Exception as exc:
                    logger.warning(
                        "fast_planner_coverage_review_unavailable sid=%s "
                        "error_type=%s error=%s",
                        request.sid,
                        type(exc).__name__,
                        exc,
                    )
                    return self._escalation(
                        plan_id,
                        request,
                        "coordinated_action_coverage_review_unavailable",
                        error=exc,
                        path_classification="coverage_review_failure",
                        metadata={
                            "coordinated_goal_ids": sorted(coordinated_goal_ids),
                            "execution_allowed": False,
                        },
                    )
                if coverage_review.decision != "accept":
                    logger.warning(
                        "fast_planner_coverage_review_rejected sid=%s "
                        "uncovered=%s reason=%s",
                        request.sid,
                        coverage_review.uncovered_requirements,
                        coverage_review.reason,
                    )
                    return self._escalation(
                        plan_id,
                        request,
                        "coordinated_action_coverage_incomplete",
                        unresolved=coverage_review.uncovered_requirements,
                        path_classification="semantic_escalation",
                        metadata={
                            "coordinated_goal_ids": sorted(coordinated_goal_ids),
                            "coverage_review": coverage_review.model_dump(mode="json"),
                            "execution_allowed": False,
                        },
                    )
                metadata = dict(validated.metadata)
                metadata["coverage_review"] = {
                    "status": "accepted",
                    "confidence": coverage_review.confidence,
                    "reason": coverage_review.reason,
                    "execution_authority": "none",
                }
                validated = validated.model_copy(update={"metadata": metadata})
            if contract_repair_attempted:
                metadata = dict(validated.metadata)
                metadata.update(
                    {
                        "contract_schema": contract_schema,
                        "canonical_contract": "CanonicalPlan",
                        "contract_repair_attempted": True,
                        "contract_repair_succeeded": True,
                        "contract_repair": {
                            "attempted": True,
                            "succeeded": True,
                            "strategy": "schema_constrained_model_revision",
                            "attempt_count": 1,
                        },
                    }
                )
                validated = validated.model_copy(update={"metadata": metadata})
                logger.info("fast_planner_contract_repair_done sid=%s status=success", request.sid)
            return validated
        raise AssertionError("unreachable")

    @staticmethod
    def _repair_response_schema(
        schema: dict[str, Any],
        initial_raw_output: Any,
        *,
        expected_goal_ids_for_turn: list[str],
    ) -> dict[str, Any]:
        """Narrow a redundant aggregate to the model's own goal judgments.

        The initial model output remains the semantic authority for every
        per-goal disposition.  When that complete outcome map is valid but its
        redundant top-level aggregate is inconsistent, the bounded repair
        grammar permits only the mechanically consistent aggregate.  The host
        never examines user wording or chooses a goal outcome, step, or skill.
        """

        if not isinstance(initial_raw_output, dict):
            return schema
        outcomes = initial_raw_output.get("goal_outcomes")
        expected = list(expected_goal_ids_for_turn)
        if not isinstance(outcomes, dict) or set(outcomes) != set(expected):
            return schema
        dispositions: list[str] = []
        for goal_id in expected:
            outcome = outcomes.get(goal_id)
            if not isinstance(outcome, dict):
                return schema
            disposition = outcome.get("disposition")
            if disposition not in {"execute", "respond", "clarify", "escalate"}:
                return schema
            dispositions.append(disposition)
        disposition_set = set(dispositions)
        if disposition_set == {"execute"}:
            aggregate = "execute"
        elif disposition_set == {"respond"}:
            aggregate = "respond"
        elif disposition_set == {"execute", "respond"}:
            aggregate = "mixed"
        elif disposition_set == {"clarify"}:
            aggregate = "clarify"
        elif disposition_set == {"escalate"}:
            aggregate = "escalate"
        else:
            return schema
        narrowed = copy.deepcopy(schema)
        disposition_schema = narrowed.get("properties", {}).get("disposition")
        if not isinstance(disposition_schema, dict):
            return schema
        disposition_schema["enum"] = [aggregate]
        disposition_schema["description"] = (
            "Bounded contract repair: this is the sole aggregate consistent "
            "with the initial model-authored per-goal dispositions."
        )
        return narrowed

    @staticmethod
    def _validation_error_json(
        exc: Exception,
        *,
        raw: Any,
        expected_goal_ids_for_turn: list[str],
    ) -> str:
        if isinstance(exc, ValidationError):
            feedback = list(exc.errors(include_url=False))
        else:
            feedback = [
                {"type": type(exc).__name__, "message": str(exc)[:1000]}
            ]
        feedback.extend(
            planner_contract_diagnostics(
                raw,
                planner_tier="fast",
                expected_goal_ids_for_turn=expected_goal_ids_for_turn,
            )
        )
        unique: list[dict[str, Any]] = []
        seen: set[tuple[str, tuple[Any, ...]]] = set()
        for item in feedback:
            key = (
                str(item.get("msg") or item.get("message") or ""),
                tuple(item.get("loc") or []),
            )
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)
        return json.dumps(
            unique,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )[:10000]

    @staticmethod
    def _plan_id(request: AgentRunRequest) -> str:
        digest = hashlib.sha256(
            f"{request.sid or 'turn'}|fast|{request.text}".encode()
        ).hexdigest()[:20]
        return f"plan_{digest}"

    @staticmethod
    def _bounded(value: Any, limit: int) -> str:
        text = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return text if len(text) <= limit else text[:limit].rstrip() + "..."

    def _prompt(
        self,
        request: AgentRunRequest,
        capabilities: list[dict[str, Any]],
        *,
        response_schema: dict[str, Any],
        previous_raw: Any = None,
        validation_errors: str = "",
    ) -> str:
        context = request.context if isinstance(request.context, dict) else {}
        skill_section = agent_skill_prompt_section(
            context,
            agent_role="fast_planner",
        )
        identity_json = bounded_identity_json(context)
        personality_json = bounded_personality_json(context)
        association = goal_association_prompt_projection(context)
        route = request.route_decision
        advisory = {
            "route": route.route,
            "intent": route.intent,
            "confidence": route.confidence,
        }
        grounding = canonical_goal_grounding(context)
        argument_grounding_contract = (
            "Treat an explicit numeric value in an authoritative goal as a "
            "user-supplied candidate for the matching catalog argument. When "
            "the value and units are unambiguous and the value is within the "
            "catalog schema, copy it exactly; never silently replace it with "
            "a schema default. Catalog defaults are only for parameters the "
            "user did not supply. If the units, argument mapping, or validity "
            "are uncertain, escalate instead of claiming exact coverage. A "
            "material adjustment must use a non-exact plan_relation, require "
            "confirmation, and explain the change. "
            "For each numeric literal in an executable authoritative goal, "
            "include a user_supplied parameter_resolution tied to the owned "
            "step and goal. The parameter field must be the exact bare key in "
            "that step's args object, never a step- or capability-qualified "
            "name. Its value must equal the step argument and its "
            "source_goal_ids must identify the authoritative Goal containing "
            "that same number. Use those stable Goal IDs as provenance; do not "
            "copy, paraphrase, or annotate Goal text into another field. "
            "For chromie.memory.retrieve_verified_tool_result, resolved Goal "
            "bindings such as location and date belong inside the single "
            "material_args object. They are not missing direct step arguments, "
            "so do not emit separate location or date parameter_resolutions. "
            "If a resolution for that nested object is useful, its parameter "
            "must be material_args and its value must equal the complete "
            "step.args.material_args object. "
        )
        source_route = str(request.route_decision.route or "").strip()
        route_effect_contract = (
            "The authoritative source route is chat. This turn is response-only: "
            "do not select or invent executable skills, physical effects, or plan "
            "steps. Answer conversational goals with respond outcomes; escalate "
            "only when semantic reasoning is genuinely insufficient. "
            if source_route == "chat"
            else (
                "The authoritative source route is tool. This fresh external-information "
                "turn must contain at least one executable supplied tool step, or use a "
                "model-authored semantic escalation when no valid tool plan is possible. "
                "Do not terminate the whole turn as respond from model memory or loosely "
                "related evidence. A completed-evidence follow-up that needs no execution "
                "belongs on a chat route upstream. "
                if source_route == "tool"
                else ""
            )
        )
        semantic_scope_contract = (
            "For a Goal with resource_responsibility, treat the entire acquire-and-deliver outcome as one semantic responsibility. Select only an exact registered Capability whose declared semantic_scope covers that resource kind, acquisition, and delivery. Never substitute a partial primitive such as walking for physical fetch-and-deliver, or generic conversation for external information retrieval. Provider-internal stages such as navigation, search, grasp, carry, evidence retrieval, evaluation, and final delivery are not separate Goals or planner steps unless the selected Capability contract explicitly exposes them as independently authoritative outcomes. The Goal is provider-neutral: choose from the catalog by exact supported semantics, never from a hardcoded provider rule. When resource_responsibility.source.status=unknown and the selected capability cannot resolve the source itself, return a specific context request and zero executable steps. Capability semantic_scope metadata is authoritative applicability evidence. Canonical Goal object.bindings are authoritative resolved parameters from Goal Association. Every material tool argument, especially location, date, target, and entity identity, must equal the corresponding binding; never reinterpret an original pronoun or replace a binding with an older memory entry. For chromie.weather.lookup, keep args.location exactly equal to the canonical location binding. When the user or discourse context clearly supplies a hierarchical place, you may also provide location_context with locality, admin1, country, and aliases for that same place; never use it to select a different place. Preserve every canonical-goal qualifier, including temporal scope, comparison period, answer shape, ordering, and concurrency. Never silently rewrite simultaneous independent actions as before/after actions. Every executable step must explicitly include timing; omission is invalid because it would erase the model's ordering or concurrency decision. When the user requests compatible actions to happen together, assign timing=parallel only when each selected capability explicitly declares parallel_metadata_declared=true and can_run_parallel=true and their exclusive/resource claims are compatible. Never invent an unstated feature of a capability in a reason or outcome; in particular, a physical action cannot satisfy a conversational or spoken-performance Goal unless its supplied semantics explicitly say so. Use a respond outcome for speech authored by Response Composer. A user-requested spoken response or performance may still be simultaneous with an Activity-lane step. Preserve that relation without inventing a chromie.speak plan step: keep the spoken Goal as a respond outcome, set each participating Activity step to timing=parallel only when its provider declares safe parallel execution, and leave cross-lane speaking/activity coordination to Response Composer. Never satisfy a prohibition, negation, or hold-state constraint by invoking the positive action it forbids; if the catalog has no capability whose semantic scope actually enforces that negative state, clarify or report it unavailable. If safe parallel execution is unavailable or uncertain, escalate or propose an explicit safe adjustment rather than silently serializing the request. Never silently narrow a goal to fit a capability or its enum defaults. If the goal falls outside a capability's supported scope, escalate for clarification, another capability, or an honest unavailable result with zero steps. "
        )
        current_turn_communication_contract = (
            "The FINAL AUTHORITATIVE USER TURN owns the current communicative act. "
            "Retained Goals, delivered evidence-bound dialogue, and verified memory "
            "may support the response, but they must not replace what the person just "
            "meant. For a reaction, feeling, acknowledgement, evaluation, or practical "
            "decision, answer that latest act directly and naturally. Do not replay the "
            "previous task answer unless the latest turn actually asks for repetition, "
            "verification, explanation, comparison, or another answer from it. "
        )
        concise_output_contract = (
            "Keep goal summaries, step reasons, satisfaction rationales, and "
            "outcome rationales concise: one short sentence each. Do not "
            "repeat the user goal, catalog description, arguments, or the same "
            "justification across multiple fields. "
        )
        if len(expected_goal_ids(context)) > 1:
            return (
                f"Goal association advisory JSON:\n{self._bounded(association, 3000)}\n\n"
                f"Goal Interpretation advisory JSON:\n{self._bounded(advisory, 900)}\n\n"
                f"Owner-approved Chromie identity JSON:\n{identity_json}\n\n"
                f"Owner-approved Personality Expression JSON:\n{personality_json}\n\n"
                f"{skill_section}"
                f"Executable common capability catalog JSON:\n{self._bounded(capabilities, 9000)}\n\n"
                f"Verified tool-memory index JSON (provenance and bound arguments only; no result contents):\n{self._bounded(context.get('verified_tool_memory_index') or [], 5000)}\n\n"
                f"Delivered evidence-bound dialogue JSON (trusted spoken projection, not the full provider result):\n{self._bounded(evidence_bound_dialogue(context, fallback_history=request.history), 3600)}\n\n"
                f"Active and recoverable task bindings JSON:\n{self._bounded(context.get('active_task_snapshots') or [], 5000)}\n\n"
                f"Previous Fast Planner output when doing a semantic replan:\n{self._bounded(previous_raw, 3500) if previous_raw is not None else 'null'}\n\n"
                "When validation errors are present, regenerate one fresh complete model-authored plan object from the authoritative goals and catalog. Author the semantic plan directly. Do not classify text with lexical rules and do not expect the host to choose a capability, arguments, ordering, ownership, response, disposition, coverage, or satisfaction for you. "
                "Every top-level field and every nested field in FastPlannerMultiGoalPlanOutput is required. Use exact catalog capability IDs and schema-valid args. The verified tool-memory index contains no answer facts. When an exact fresh index entry matches every authoritative Goal binding, execute chromie.memory.retrieve_verified_tool_result with that evidence_id, original tool_id, and the same material arguments; never use a respond outcome directly from the index. If no exact fresh entry exists, execute the supplied fresh read capability. For a scheduled, running, or recoverable safe-read goal, reuse the bound capability and exact arguments and execute or retry it; never answer from another task's result. On a tool route, every top-level and per-goal response_text must be empty: do not greet, acknowledge, self-introduce, narrate a lookup, or predict the result. Response Composer owns optional pre-execution speech, and post-execution speech is produced only from evidence returned by an executed retrieval or external read. "
                f"{argument_grounding_contract}"
                f"{semantic_scope_contract}"
                f"{current_turn_communication_contract}"
                f"{IDENTITY_SEMANTIC_CONTRACT}"
                f"{PERSONALITY_SEMANTIC_CONTRACT}"
                f"{route_effect_contract}"
                f"{concise_output_contract}"
                "Author stable non-empty step_id values, exact source_goal_ids, and matching outcome step_ids yourself. "
                "This is prospective planning: no action has executed yet. A planned step or response counts as satisfying its goal if it would succeed. For each keyed goal outcome, judge only that one goal; never put sibling goals or pending execution in unmet_goal_ids or unmet_requirements. Complete terminal outcomes use exact satisfaction with both unmet lists empty. "
                "Fast terminal scope permits at most one executable step per goal. A count argument performs repetition inside one skill call; never duplicate a step to implement repeated blinks, nods, or similar motions. Respond goals have no executable step. "
                "For a terminal plan, every per-goal outcome is execute or respond, coverage is complete, and the top-level disposition exactly aggregates the outcome dispositions. A respond outcome contains the actual answer now and references no steps. An execute outcome references every and only the model-authored steps owned by that goal. "
                "For semantic escalation, author disposition=escalate, coverage=partial or uncertain, steps=[], a non-empty top-level escalation_reason, and one escalate outcome for every canonical goal. Each escalate outcome must explain its own unresolved need, reference no steps, carry no response_text, and include a non-exact prospective satisfaction judgment. Do not mix escalation outcomes with executable or response outcomes. "
                "goal_satisfaction and every per-goal satisfaction are model judgments about prospective plan adequacy. A score from 0.95 through 1.0 requires status=exact. Escalation cannot claim exact satisfaction. "
                "Response Composer owns transport speech, so chromie.speak is never a plan step. Do not replace a conversational answer with a gesture or attention action. "
                "Use plan_relation=exact unless the plan materially changes the request; safe_adjustment or alternative requires user_confirmation_required=true and explanatory response_text. "
                "The host adds only plan_id, planner_tier, schema_version, and the authoritative top-level goal_ids after validating your output. It does not compile semantic decisions or generate step ownership. Return JSON only.\n\n"
                f"FINAL AUTHORITATIVE USER TURN:\n{request.text}\n\n"
                f"FINAL CANONICAL GOALS JSON:\n{self._bounded(grounding, 4500)}\n\n"
                f"FINAL ALLOWED EXECUTABLE CAPABILITY IDS JSON:\n{self._bounded([item['capability_id'] for item in capabilities], 2500)}\n\n"
                "FINAL AUTHORITATIVE CONTRACT REPAIR ERRORS JSON:\n"
                f"{validation_errors or '[]'}\n"
                "When this list is non-empty, correct every listed defect in the fresh object. If an error reports an expected aggregate disposition, author exactly that disposition unless you also revise the underlying per-goal outcomes consistently."
            )
        return (
            f"Goal association advisory JSON:\n{self._bounded(association, 3000)}\n\n"
            f"Goal Interpretation advisory JSON:\n{self._bounded(advisory, 900)}\n\n"
            f"Owner-approved Chromie identity JSON:\n{identity_json}\n\n"
            f"Owner-approved Personality Expression JSON:\n{personality_json}\n\n"
            f"{skill_section}"
            f"Executable common capability catalog JSON:\n{self._bounded(capabilities, 9000)}\n\n"
            f"Verified tool-memory index JSON (provenance and bound arguments only; no result contents):\n{self._bounded(context.get('verified_tool_memory_index') or [], 5000)}\n\n"
            f"Delivered evidence-bound dialogue JSON (trusted spoken projection, not the full provider result):\n{self._bounded(evidence_bound_dialogue(context, fallback_history=request.history), 3600)}\n\n"
            f"Active and recoverable task bindings JSON:\n{self._bounded(context.get('active_task_snapshots') or [], 5000)}\n\n"
            f"Previous Fast Planner output when doing a semantic replan:\n{self._bounded(previous_raw, 3500) if previous_raw is not None else 'null'}\n\n"
            "When validation errors are present and the previous output is null, regenerate one fresh complete object from the authoritative turn, goals, catalog, and every listed defect. Do not patch, quote, splice, annotate, or embed JSON fragments inside rationale or response strings. "
            "Decide whether the executable common catalog completely covers every independent responsibility in the current user turn. A verified tool-memory index entry is only metadata that an exact prior result may be retrievable; it is never answer evidence. After Goal Association has fixed all material bindings, select chromie.memory.retrieve_verified_tool_result only when one index entry exactly matches the required tool_id and material arguments and is fresh enough for the user request. Otherwise select the fresh read capability. A status follow-up for a scheduled, running, or recoverable safe read must resume or retry the bound skill with its exact arguments when no matching completed memory entry exists. Never invent weather, temperature, status, price, schedule, or another external result from model memory or from index metadata. "
            "There are exactly two legal output shapes for one or many goals. A terminal plan uses coverage=complete, a goal_outcomes entry keyed exactly once by every canonical Goal ID, and non-null prospective satisfaction. A semantic escalation uses disposition=escalate, coverage=partial or uncertain, steps=[], one escalate outcome for every canonical Goal ID, non-exact prospective satisfaction, and a specific non-empty escalation_reason. "
            "Finding one matching capability is not complete coverage. If any responsibility, parameter, ordering, concurrency relation, safety judgment, or capability is unresolved, use the complete model-authored semantic-escalation shape; never return an empty outcome map or null satisfaction. "
            "Fast Planner may emit disposition=mixed only for a completely covered simple combination of common unlocked execute goals and direct conversational respond goals. A mixed plan requires at least one execute outcome, at least one respond outcome, complete per-goal satisfaction, and exact step ownership. "
            "For complete direct execution, use exact supplied capability IDs and schema-valid args. "
            f"{argument_grounding_contract}"
            f"{semantic_scope_contract}"
            f"{current_turn_communication_contract}"
            f"{IDENTITY_SEMANTIC_CONTRACT}"
            f"{PERSONALITY_SEMANTIC_CONTRACT}"
            f"{route_effect_contract}"
            f"{concise_output_contract}"
            "User-facing speech is owned by Response Composer, not a plan step. Represent each conversational responsibility with disposition=respond and an actual response_text now; never substitute chromie.speak or a body gesture. Greeting wording and length are ordinary model-authored conversational choices governed by the supplied scene, relationship context, and owner-approved personality. "
            "Every executable step must use capability_id plus source_goal_ids copied from the canonical goals. Do not use catalog-only parameters, action, input_schema, route, or step_type fields. "
            "goal_satisfaction measures prospective plan adequacy: planned steps count as satisfying their goals if successful, so pending execution alone is never an unmet requirement. A score from 0.95 through 1.0 requires status=exact; score=1.0 must never use substantial. If steps are present, top-level disposition cannot be respond. "
            "For every terminal or escalation result, goal_outcomes must be keyed exactly once by every supplied canonical Goal ID. Each execute outcome needs its real step_ids; each respond outcome needs non-empty response_text and step_ids=[]; each escalation outcome needs its unresolved reason and non-exact satisfaction. "
            "Valid examples: execute uses owned steps and execute outcomes; mixed uses owned steps plus respond outcomes; escalation uses steps=[], one escalate outcome per Goal, and non-null non-exact goal_satisfaction. "
            "Use plan_relation=exact for an exact plan. A safe_adjustment or alternative must set user_confirmation_required=true so the host holds execution for approval. "
            "The Ollama decoder enforces the exact flat FastPlannerModelOutput schema out-of-band. "
            "The host adds plan identity, planner tier, and the authoritative top-level canonical goal IDs; do not emit those envelope fields. "
            "Return JSON only. The final grounding below is authoritative and overrides previous output or advisory text.\n\n"
            f"FINAL AUTHORITATIVE USER TURN:\n{request.text}\n\n"
            f"FINAL CANONICAL GOALS JSON:\n{self._bounded(grounding, 4500)}\n\n"
            f"FINAL ALLOWED EXECUTABLE CAPABILITY IDS JSON:\n{self._bounded([item['capability_id'] for item in capabilities], 2500)}\n\n"
            "FINAL AUTHORITATIVE CONTRACT REPAIR ERRORS JSON:\n"
            f"{validation_errors or '[]'}\n"
            "When this list is non-empty, correct every listed defect in the fresh object. If an error reports an expected aggregate disposition, author exactly that disposition unless you also revise the underlying per-goal outcomes consistently."
        )

    @staticmethod
    def _system_prompt() -> str:
        return (
            "You are Chromie's Fast Planner. Plan only the final authoritative user turn and canonical goals at the end of the prompt. "
            "Author the semantic plan from the goals and executable catalog; never use phrase-to-action rules and never delegate semantic planning to the host. "
            "A verified-memory index is provenance only, never answer evidence. For a retained completed external-result Goal, a direct response may use only supplied delivered evidence-bound dialogue: preserve every measurement and condition exactly and omit unsupported embellishment. If that dialogue is absent, retrieve matching verified evidence, perform a fresh read, or escalate. "
            "Produce a complete simple response, common-skill plan, or simple execute-plus-respond mixed plan only when every responsibility is covered; otherwise author a complete per-goal semantic escalation. "
            "Do not execute, authorize, or claim completion. Return JSON only."
        )

    @staticmethod
    def _repair_system_prompt() -> str:
        return (
            "You regenerate one fresh Fast Planner output using the supplied authoritative goals, executable capability catalog, complete validation errors, and schema-constrained decoder. "
            "Validation errors describe defects in the prior plan object; they are not evidence that execution occurred, that the user request became uncertain, or that a catalog capability needs confirmation. Preserve the authoritative user meaning and catalog facts while correcting every defect. "
            "Rebuild every required model-authored plan field instead of editing or splicing invalid JSON. Do not rely on host-generated steps, ownership, outcomes, disposition, or satisfaction. Return JSON only."
        )

    def _normalize_multi_goal(
        self,
        raw: dict[str, Any],
        *,
        request: AgentRunRequest,
        plan_id: str,
        expected_goal_ids_for_turn: list[str],
    ) -> dict[str, Any]:
        """Add only host-owned envelope fields to a model-authored plan."""

        model_output = validate_planner_model_output(
            raw,
            planner_tier="fast",
            expected_goal_ids_for_turn=expected_goal_ids_for_turn,
        )
        validate_goal_responsibility_outcomes(
            model_output,
            authoritative_goals=canonical_goal_grounding(request.context),
            context=request.context,
        )
        out = model_output.model_dump(mode="python")
        out.pop("plan_relation", None)
        out.pop("user_confirmation_required", None)
        out["goal_outcomes"] = materialize_goal_outcomes(
            model_output,
            expected_goal_ids_for_turn=expected_goal_ids_for_turn,
        )
        out["plan_id"] = plan_id
        out["planner_tier"] = "fast"
        out["goal_ids"] = list(expected_goal_ids_for_turn)
        metadata = materialize_planner_metadata(model_output)
        metadata.update(
            {
                "model_contract": "FastPlannerMultiGoalPlanOutput",
                "semantic_authority": "fast_planner_model",
                "model_authored_steps": True,
                "model_authored_step_ids": True,
                "model_authored_step_ownership": True,
                "model_authored_goal_outcomes": True,
                "model_authored_goal_satisfaction": True,
                "host_semantic_compilation": False,
            }
        )
        out["metadata"] = metadata
        return out

    def _normalize(
        self,
        raw: dict[str, Any],
        *,
        request: AgentRunRequest,
        plan_id: str,
        expected_goal_ids_for_turn: list[str],
    ) -> dict[str, Any]:
        model_output = validate_planner_model_output(
            raw,
            planner_tier="fast",
            expected_goal_ids_for_turn=expected_goal_ids_for_turn,
        )
        validate_goal_responsibility_outcomes(
            model_output,
            authoritative_goals=canonical_goal_grounding(request.context),
            context=request.context,
        )
        out = model_output.model_dump(mode="python")
        out.pop("plan_relation", None)
        out.pop("user_confirmation_required", None)
        out["goal_outcomes"] = materialize_goal_outcomes(
            model_output,
            expected_goal_ids_for_turn=expected_goal_ids_for_turn,
        )
        out["plan_id"] = plan_id
        out["planner_tier"] = "fast"
        out["goal_ids"] = list(expected_goal_ids_for_turn)
        steps = out.get("steps")
        if isinstance(steps, dict):
            steps = [steps]
        if not isinstance(steps, list):
            steps = []
        normalized_steps = []
        for index, item in enumerate(steps):
            if not isinstance(item, dict):
                continue
            step = dict(item)
            if not step.get("step_id"):
                step["step_id"] = f"{plan_id}:step:{index}"
            step.setdefault("timing", "sequential")
            normalized_steps.append(step)
        out["steps"] = normalized_steps
        out.setdefault("coverage", "uncertain")
        out.setdefault("disposition", "escalate")
        out.setdefault("confidence", 0.0)
        out.setdefault("goal_summary", request.text)
        out.setdefault("response_text", "")
        out.setdefault("escalation_reason", "")
        out.setdefault("unresolved", [])
        out.setdefault("parameter_resolutions", [])
        out.setdefault("goal_outcomes", [])
        out.setdefault("goal_satisfaction", None)
        out["metadata"] = materialize_planner_metadata(model_output)
        return out

    def _validate(
        self,
        plan: CanonicalPlan,
        *,
        capability_payload: list[dict[str, Any]],
        request: AgentRunRequest,
        expected_goal_ids_for_turn: list[str],
    ) -> CanonicalPlan:
        allowed = {item["capability_id"]: item for item in capability_payload}
        contract_schema = (
            "FastPlannerMultiGoalPlanOutput"
            if len(expected_goal_ids_for_turn) > 1
            else "FastPlannerModelOutput"
        )
        counts = {
            "authoritative_goal_count": len(expected_goal_ids_for_turn),
            "goal_outcome_count": len(plan.goal_outcomes),
            "executable_step_count": len(plan.steps),
        }
        if expected_goal_ids_for_turn and set(plan.goal_ids) != set(expected_goal_ids_for_turn):
            return self._escalation(
                plan.plan_id,
                request,
                "goal_ids_do_not_match_goal_association",
                metadata={
                    "expected_goal_ids": expected_goal_ids_for_turn,
                    "actual_goal_ids": list(plan.goal_ids),
                    **counts,
                },
            )
        if (
            str(request.route_decision.route or "").strip() == "tool"
            and plan.disposition != "escalate"
            and not plan.steps
        ):
            return self._escalation(
                plan.plan_id,
                request,
                "tool_route_requires_executable_step",
                metadata={
                    "proposed_disposition": plan.disposition,
                    **counts,
                },
            )
        if plan.disposition == "escalate":
            metadata = dict(plan.metadata)
            metadata.update(
                {
                    "resolver": "fast_planner",
                    "status": "escalate",
                    "authority": "advisory",
                    "path_classification": "semantic_escalation",
                    "common_capability_count": len(capability_payload),
                    "min_confidence": self.min_confidence,
                    "contract_schema": contract_schema,
                    "canonical_contract": "CanonicalPlan",
                    **counts,
                }
            )
            return plan.model_copy(update={"metadata": metadata})
        if plan.coverage != "complete" or plan.confidence < self.min_confidence:
            return self._escalation(
                plan.plan_id,
                request,
                "coverage_not_complete",
                unresolved=plan.unresolved,
                metadata={
                    "proposed_coverage": plan.coverage,
                    "proposed_confidence": plan.confidence,
                    **counts,
                },
            )
        if plan.goal_satisfaction is None or plan.goal_satisfaction.score < 0.95:
            return self._escalation(
                plan.plan_id,
                request,
                "goal_satisfaction_not_exact",
                unresolved=plan.unresolved,
                metadata={
                    "proposed_goal_satisfaction": (
                        plan.goal_satisfaction.model_dump(mode="json")
                        if plan.goal_satisfaction
                        else None
                    ),
                    **counts,
                },
            )
        incomplete_outcomes = [
            outcome.goal_id
            for outcome in plan.goal_outcomes
            if outcome.satisfaction is None or outcome.satisfaction.score < 0.95
        ]
        if incomplete_outcomes:
            return self._escalation(
                plan.plan_id,
                request,
                "per_goal_satisfaction_not_exact",
                unresolved=incomplete_outcomes,
                metadata={**counts},
            )
        for step in plan.steps:
            capability = allowed.get(step.capability_id)
            if capability is None:
                return self._escalation(
                    plan.plan_id,
                    request,
                    "step_not_in_executable_common_catalog",
                    unresolved=[step.capability_id],
                    metadata={**counts},
                )
        parallel_errors = parallel_plan_contract_errors(
            plan,
            capability_payload,
        )
        if parallel_errors:
            return self._escalation(
                plan.plan_id,
                request,
                "parallel_execution_contract_unavailable",
                unresolved=[str(item["type"]) for item in parallel_errors],
                metadata={
                    "parallel_contract_errors": parallel_errors,
                    "execution_allowed": False,
                    **counts,
                },
            )
        metadata = dict(plan.metadata)
        metadata.update(
            {
                "resolver": "fast_planner",
                "status": "complete",
                "authority": "advisory",
                "common_capability_count": len(capability_payload),
                "min_confidence": self.min_confidence,
                "contract_schema": contract_schema,
                "canonical_contract": "CanonicalPlan",
                "path_classification": "terminal",
                **counts,
            }
        )
        return plan.model_copy(update={"metadata": metadata})

    def _escalation(
        self,
        plan_id: str,
        request: AgentRunRequest,
        reason: str,
        *,
        unresolved: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        error: Exception | None = None,
        path_classification: str = "semantic_escalation",
    ) -> CanonicalPlan:
        detail = dict(metadata or {})
        detail.update(
            {
                "resolver": "fast_planner",
                "status": "escalate",
                "authority": "advisory",
                "path_classification": path_classification,
            }
        )
        if error is not None:
            detail.update(
                {
                    "error_type": type(error).__name__,
                    "error": str(error)[:300],
                    **llm_failure_metadata(error),
                }
            )
        context = request.context if isinstance(request.context, dict) else {}
        return CanonicalPlan(
            plan_id=plan_id,
            planner_tier="fast",
            disposition="escalate",
            coverage="uncertain",
            confidence=0.0,
            goal_ids=expected_goal_ids(context),
            goal_summary=request.text,
            steps=[],
            escalation_reason=reason,
            unresolved=list(unresolved or []),
            metadata=detail,
        )
