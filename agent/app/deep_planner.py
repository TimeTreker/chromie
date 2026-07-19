from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from pydantic import ValidationError

from .capabilities.catalog import CapabilityCatalog
from .capabilities.validator import validate_args_for_schema
from .clients.ollama_client import OllamaClient, llm_failure_metadata
from .schema import AgentRunRequest

try:
    from chromie_runtime.cognitive_integrity_events import cognitive_integrity_metadata
except ImportError:  # pragma: no cover
    from shared.chromie_runtime.cognitive_integrity_events import cognitive_integrity_metadata
from .planner_contract import (
    canonical_goal_grounding,
    canonical_plan_response_schema,
    expected_goal_ids,
    is_planner_step_skill,
    materialize_goal_outcomes,
    materialize_planner_metadata,
    planner_contract_diagnostics,
    validate_planner_model_output,
)

try:
    from chromie_contracts.plan import CanonicalPlan
except ImportError:  # pragma: no cover
    from shared.chromie_contracts.plan import CanonicalPlan

logger = logging.getLogger("chromie.agent.deep_planner")


class DeepPlannerResolver:
    """Full-catalog semantic planner with one bounded same-tier revision."""

    def __init__(self, ollama: OllamaClient, catalog: CapabilityCatalog, *, min_confidence: float = 0.65,
                 num_ctx: int = 8192, num_predict: int = 1024, max_capabilities: int = 96,
                 max_replans: int = 1, min_goal_satisfaction: float = 0.75) -> None:
        self.ollama = ollama
        self.catalog = catalog
        self.min_confidence = max(0.0, min(1.0, float(min_confidence)))
        self.num_ctx = max(4096, int(num_ctx))
        self.num_predict = max(256, int(num_predict))
        self.max_capabilities = max(1, min(256, int(max_capabilities)))
        self.max_replans = max(0, min(2, int(max_replans)))
        self.min_goal_satisfaction = max(0.0, min(1.0, float(min_goal_satisfaction)))

    async def resolve(self, request: AgentRunRequest) -> CanonicalPlan:
        plan_id = self._plan_id(request)
        capabilities = await self.catalog.prompt_entries(scope="all", refresh=False)
        executable = [
            item
            for item in capabilities
            if item.available
            and item.interaction_executable
            and is_planner_step_skill(item.capability_id)
        ]
        payload = [self._capability_payload(item) for item in executable[: self.max_capabilities]]
        expected_goal_ids_for_turn = expected_goal_ids(
            request.context if isinstance(request.context, dict) else {}
        )
        response_schema = self._response_schema(
            expected_goal_ids_for_turn,
            allowed_skill_ids=[item["capability_id"] for item in payload],
        )
        generation_options = {
            "temperature": 0,
            "top_p": 0.9,
            "num_ctx": self.num_ctx,
            "num_predict": self.num_predict,
        }
        feedback: list[dict[str, Any]] = []
        previous_raw: Any = None
        initial_raw_output: Any = None
        contract_repair_attempted = False
        initial_validation_errors = ""
        for attempt in range(self.max_replans + 1):
            raw: Any = None
            try:
                raw = await self.ollama.generate(
                    self._prompt(
                        request,
                        payload,
                        feedback=feedback,
                        response_schema=response_schema,
                        previous_raw=previous_raw,
                        expected_goal_ids=expected_goal_ids_for_turn,
                    ),
                    system=(
                        self._revision_system_prompt()
                        if feedback
                        else self._system_prompt()
                    ),
                    options=generation_options,
                    response_format=response_schema,
                )
                if not isinstance(raw, dict):
                    raise ValueError("deep planner response is not a JSON object")
                plan = CanonicalPlan.model_validate(
                    self._normalize(
                        raw,
                        request=request,
                        plan_id=plan_id,
                        expected_goal_ids_for_turn=expected_goal_ids_for_turn,
                    )
                )
            except Exception as exc:
                failure = llm_failure_metadata(exc)
                logger.warning(
                    "deep_planner_inference_failed sid=%s attempt=%s error_type=%s error=%s "
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
                semantic_replan = self._is_semantic_replan_error(exc)
                if attempt < self.max_replans and semantic_replan:
                    contract_repair_attempted = True
                    initial_raw_output = raw
                    # Contract repair is a fresh schema-constrained regeneration,
                    # not an in-place JSON edit.  Supplying the invalid object as
                    # copy text encouraged deployed models to splice validator
                    # fragments into rationale strings instead of rebuilding the
                    # missing fields.
                    previous_raw = None
                    initial_validation_errors = self._validation_error_json(
                        exc,
                        raw=raw,
                        expected_goal_ids_for_turn=expected_goal_ids_for_turn,
                    )
                    logger.warning(
                        "deep_planner_contract_repair_start sid=%s attempt=%s "
                        "validation_errors=%s raw_output=%s",
                        request.sid,
                        attempt + 1,
                        initial_validation_errors,
                        self._bounded(initial_raw_output, 5000),
                    )
                    feedback = [
                        {
                            "type": "canonical_plan_contract_validation_failure",
                            "error_type": type(exc).__name__,
                            "validation_errors": initial_validation_errors,
                        }
                    ]
                    continue
                integrity_metadata = cognitive_integrity_metadata(stage="deep_planner", exc=exc, request=request)
                return self._clarify(
                    plan_id,
                    request,
                    "deep_planner_model_contract_failed"
                    if contract_repair_attempted or semantic_replan
                    else "deep_planner_unavailable",
                    error=exc,
                    attempts=attempt + 1,
                    metadata={
                        "contract_schema": "DeepPlannerModelOutput",
                        "canonical_contract": "CanonicalPlan",
                        "contract_repair_attempted": contract_repair_attempted,
                        "contract_repair_succeeded": False,
                        "initial_validation_errors": initial_validation_errors,
                        "initial_raw_output": self._bounded(initial_raw_output, 5000)
                        if initial_raw_output is not None
                        else "",
                        "repair_raw_output": self._bounded(raw, 5000)
                        if contract_repair_attempted and raw is not None
                        else "",
                        **integrity_metadata,
                    },
                )
            errors = self._validation_errors(
                plan, payload, expected_goal_ids=expected_goal_ids_for_turn
            )
            if not errors:
                metadata = dict(plan.metadata)
                metadata.update({"resolver": "deep_planner", "status": "complete" if plan.coverage == "complete" else plan.disposition,
                                 "authority": "advisory", "attempt_count": attempt + 1,
                                 "full_capability_count": len(payload), "max_replans": self.max_replans, "min_goal_satisfaction": self.min_goal_satisfaction,
                                 "contract_schema": "DeepPlannerModelOutput",
                                 "canonical_contract": "CanonicalPlan",
                                 "contract_repair_attempted": contract_repair_attempted,
                                 "contract_repair_succeeded": contract_repair_attempted})
                if contract_repair_attempted:
                    metadata["contract_repair"] = {
                        "attempted": True,
                        "succeeded": True,
                        "strategy": "schema_constrained_model_revision",
                        "attempt_count": 1,
                    }
                    logger.info(
                        "deep_planner_contract_repair_done sid=%s status=success",
                        request.sid,
                    )
                return plan.model_copy(update={"metadata": metadata})
            if attempt < self.max_replans:
                feedback = errors
                previous_raw = raw
                continue
            return self._clarify(
                plan_id,
                request,
                "validation_rejected_after_replan",
                unresolved=[
                    item.get("step_id") or item.get("skill_id") or item["type"]
                    for item in errors
                ],
                metadata={
                    "validation_feedback": errors,
                    "contract_schema": "DeepPlannerModelOutput",
                    "canonical_contract": "CanonicalPlan",
                    "initial_raw_output": self._bounded(previous_raw, 5000)
                    if previous_raw is not None
                    else "",
                    "repair_raw_output": self._bounded(raw, 5000)
                    if raw is not None
                    else "",
                },
                attempts=attempt + 1,
            )
        raise AssertionError("unreachable")

    @staticmethod
    def _is_semantic_replan_error(exc: Exception) -> bool:
        """Return true only when another model answer can repair the failure.

        Transport, timeout, context-window, and output-budget failures are not
        semantic plan defects and must not consume the bounded same-tier replan.
        """

        return isinstance(exc, (json.JSONDecodeError, ValidationError, ValueError))

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
                planner_tier="deep",
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
        )[:12000]

    @staticmethod
    def _capability_payload(item: Any) -> dict[str, Any]:
        return {
            "capability_id": item.capability_id, "description": item.description,
            "input_schema": item.input_schema, "route": item.route, "available": item.available,
            "interaction_executable": item.interaction_executable,
            "requires_confirmation": item.requires_confirmation, "effects": item.effects,
            "safety_class": item.safety_class, "can_run_parallel": item.can_run_parallel,
            "parallel_metadata_declared": item.parallel_metadata_declared,
            "exclusive_group": item.exclusive_group, "resource_claims": item.resource_claims,
            "execution_constraints": item.execution_constraints,
        }

    @staticmethod
    def _plan_id(request: AgentRunRequest) -> str:
        digest = hashlib.sha256(f"{request.sid or 'turn'}|deep|{request.text}".encode()).hexdigest()[:20]
        return f"plan_{digest}"

    @classmethod
    def _response_schema(
        cls,
        expected_goal_ids: list[str],
        *,
        allowed_skill_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        return canonical_plan_response_schema(
            planner_tier="deep",
            expected_goal_ids=expected_goal_ids,
            allowed_skill_ids=list(allowed_skill_ids or []),
        )

    @staticmethod
    def _bounded(value: Any, limit: int) -> str:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
        return text if len(text) <= limit else text[:limit].rstrip() + "..."

    def _prompt(
        self,
        request: AgentRunRequest,
        capabilities: list[dict[str, Any]],
        *,
        feedback: list[dict[str, Any]],
        response_schema: dict[str, Any],
        previous_raw: Any = None,
        expected_goal_ids: list[str],
    ) -> str:
        context = request.context if isinstance(request.context, dict) else {}
        fast_plan = context.get("fast_plan_resolution") or context.get("fast_planner_resolution") or {}
        goals = context.get("active_goal_snapshots") or []
        association = context.get("goal_association_resolution") or {}
        grounding = canonical_goal_grounding(context)
        runtime_feedback = context.get("runtime_validator_feedback") or []
        combined_feedback = [*feedback, *(runtime_feedback if isinstance(runtime_feedback, list) else [])]
        feedback_section = self._bounded(combined_feedback, 5000) if combined_feedback else "[]"
        previous_section = self._bounded(previous_raw, 5000) if previous_raw is not None else "null"
        return (
            f"Fast-plan advisory JSON:\n{self._bounded(fast_plan, 1800)}\n\n"
            f"Goal association advisory JSON:\n{self._bounded(association, 3200)}\n\n"
            f"Active goals JSON:\n{self._bounded(goals, 3200)}\n\n"
            f"Executable capability catalog JSON:\n{self._bounded(capabilities, 16000)}\n\n"
            f"Previous Deep Planner model output JSON, when doing a semantic runtime replan:\n{previous_section}\n\n"
            f"Deterministic validation feedback from the previous deep-plan or trusted host-runtime attempt:\n{feedback_section}\n\n"
            "When validation feedback is present but the previous output is null, regenerate one fresh complete object from the authoritative turn, goals, catalog, and all listed defects. Do not patch, quote, splice, annotate, or embed JSON fragments inside rationale or response strings. "
            "Produce the final DeepPlannerModelOutput for the complete user goal. Deep planning is terminal: never return to the Fast Planner. "
            "Use the full catalog, preserve all independent responsibilities, constraints, conditions, ordering, and concurrency. Resolve low-consequence "
            "parameters semantically when justified; otherwise return a specific natural clarification. When independent goals have different terminal needs, use disposition=mixed, coverage=complete, and goal_outcomes so executable goals can proceed while only affected goals wait for clarification. Scope every blocking parameter resolution with source_goal_ids. Exact, safe-adjusted, or alternative executable plans "
            "must use coverage=complete and disposition=execute or mixed as appropriate. Every executable step must include source_goal_ids identifying exactly the goals it serves. Use plan_relation=exact for an exact plan. A safe_adjustment or material alternative must use the corresponding plan_relation, be described in response_text, set user_confirmation_required=true, and require "
            "confirmation downstream. For every missing parameter, return parameter_resolutions with a semantic strategy, concrete value when resolved, confidence, and rationale. Use safe_default only for low-consequence reversible values inside schema bounds. Use ask_user for material or risky values. Also return goal_satisfaction as prospective plan adequacy: planned steps count as satisfying their goals if successful, and pending execution alone is never an unmet requirement. An exact complete plan therefore uses status=exact with score at least 0.95 and lists the goals it is designed to satisfy. If essential information remains missing, use coverage=partial or uncertain with disposition=clarify and zero steps. "
            "If unavailable or refused, use zero steps. Use exact supplied capability IDs and schema-valid args. "
            "User-facing speech is owned by Response Composer and is never an executable plan step. A conversational answer, joke, explanation, or greeting uses a respond outcome with non-empty response_text and zero step_ids. Combine that outcome with physical execution as disposition=mixed; do not create a speech transport step. "
            "A plan step may contain only step_id, skill_id, args, timing, source_goal_ids, and reason_summary. "
            "Do not copy catalog field names such as capability_id, input_schema, parameters, route, step_type, or effects into a plan step. "
            "Use exactly the supplied canonical goal IDs. Do not create goals for internal status checks, safety checks, capability lookups, or implementation preconditions; represent any justified internal operation only as a step owned by an existing user goal. "
            "Keep the plan minimal: do not add neutral-position, reset, transition, cleanup, or presentation steps unless the user explicitly requested them or a supplied capability execution constraint explicitly requires them. "
            "goal_outcomes is a JSON object keyed by every supplied canonical goal ID exactly once, never a list; every complete multi-goal execute, respond, or mixed result must include it. Each value describes only that key's goal and must not repeat goal_id inside the value. Per-goal outcome invariants are mandatory: execute requires coverage=complete and at least one real plan step_id copied exactly from steps; respond requires coverage=complete, the actual answer text now (not a promise that it will be supplied later), and zero step_ids; clarify requires coverage=partial or uncertain, an unresolved need or response_text, and zero step_ids; unavailable and refused require zero step_ids. In a mixed plan, every execute or respond outcome also requires its own prospective satisfaction assessment. A satisfaction score from 0.95 through 1.0 requires status=exact; score=1.0 must never use substantial. Do not assign a physical skill to a conversational answer merely because it is the nearest remaining capability. "
            "Top-level disposition is the aggregate of per-goal dispositions: use mixed only when at least two different per-goal disposition values are present. Multiple goals that are all execute use top-level execute; multiple goals that are all respond use top-level respond. "
            "Every outcome step_id must name a real plan step, every plan step must be referenced by an execute outcome when goal_outcomes are present, and each step source_goal_ids must exactly match the execute outcomes that reference it. "
            "The Ollama decoder enforces the exact flat DeepPlannerModelOutput JSON Schema supplied out-of-band. The host adds plan identity, planner tier, and the authoritative top-level canonical goal IDs; do not emit those envelope fields. Populate only fields allowed by the model schema and return JSON only. "
            "The following final grounding block is authoritative and must override unrelated content in previous model output or advisory context.\n\n"
            f"FINAL AUTHORITATIVE USER TURN:\n{request.text}\n\n"
            f"FINAL CANONICAL GOALS JSON (copy goal IDs exactly and satisfy these meanings only):\n{self._bounded(grounding, 5000)}\n\n"
            f"FINAL ALLOWED EXECUTABLE SKILL IDS JSON:\n{self._bounded([item['capability_id'] for item in capabilities], 4000)}"
        )

    @staticmethod
    def _system_prompt() -> str:
        return (
            "You are Chromie's Deep Planner. Plan only the final authoritative user turn and canonical goals supplied at the end of the prompt. "
            "You may revise once from structured validator feedback, but you never call or return to the Fast Planner. "
            "Skills are plan leaves, not planner ownership boundaries. Do not execute, authorize, or claim completion. Return JSON only."
        )

    @staticmethod
    def _revision_system_prompt() -> str:
        return (
            "You regenerate one fresh Deep Planner output using semantic reasoning, complete deterministic validator feedback, and the supplied exact flat DeepPlannerModelOutput JSON Schema. "
            "Rebuild every required field from the authoritative user turn, goals, and capabilities; do not edit or splice the invalid JSON. "
            "Return only the corrected DeepPlannerModelOutput JSON object. Do not add commentary, markdown, annotations, local field mappings, or hidden reasoning."
        )

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
            planner_tier="deep",
            expected_goal_ids_for_turn=expected_goal_ids_for_turn,
        )
        out = model_output.model_dump(mode="python")
        out.pop("plan_relation", None)
        out.pop("user_confirmation_required", None)
        out["goal_outcomes"] = materialize_goal_outcomes(
            model_output,
            expected_goal_ids_for_turn=expected_goal_ids_for_turn,
        )
        out["plan_id"] = plan_id
        out["planner_tier"] = "deep"
        out["goal_ids"] = list(expected_goal_ids_for_turn)
        steps = out.get("steps")
        if isinstance(steps, dict):
            steps = [steps]
        if not isinstance(steps, list):
            steps = []
        normalized = []
        for index, item in enumerate(steps):
            if not isinstance(item, dict):
                continue
            step = dict(item)
            if not step.get("step_id"):
                step["step_id"] = f"{plan_id}:step:{index}"
            step.setdefault("timing", "sequential")
            normalized.append(step)
        out["steps"] = normalized
        out.setdefault("coverage", "uncertain")
        out.setdefault("disposition", "clarify")
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

    def _validation_errors(
        self,
        plan: CanonicalPlan,
        capabilities: list[dict[str, Any]],
        *,
        expected_goal_ids: list[str],
    ) -> list[dict[str, Any]]:
        allowed = {item["capability_id"]: item for item in capabilities}
        errors: list[dict[str, Any]] = []
        if expected_goal_ids and set(plan.goal_ids) != set(expected_goal_ids):
            errors.append(
                {
                    "type": "goal_ids_do_not_match_goal_association",
                    "expected_goal_ids": expected_goal_ids,
                    "actual_goal_ids": list(plan.goal_ids),
                }
            )
        if plan.coverage == "complete" and plan.confidence < self.min_confidence:
            errors.append({"type": "confidence_below_threshold", "confidence": plan.confidence,
                           "required": self.min_confidence})
        if plan.coverage == "complete":
            if plan.goal_satisfaction is None:
                errors.append({"type": "missing_goal_satisfaction"})
            elif (
                plan.disposition != "mixed"
                and plan.goal_satisfaction.score < self.min_goal_satisfaction
            ):
                errors.append({"type": "goal_satisfaction_below_threshold", "score": plan.goal_satisfaction.score, "required": self.min_goal_satisfaction})
        if plan.disposition == "mixed":
            for outcome in plan.goal_outcomes:
                if outcome.disposition not in {"execute", "respond"}:
                    continue
                if outcome.satisfaction is None:
                    errors.append(
                        {
                            "type": "missing_goal_outcome_satisfaction",
                            "goal_id": outcome.goal_id,
                            "disposition": outcome.disposition,
                        }
                    )
                elif outcome.satisfaction.score < self.min_goal_satisfaction:
                    errors.append(
                        {
                            "type": "goal_outcome_satisfaction_below_threshold",
                            "goal_id": outcome.goal_id,
                            "score": outcome.satisfaction.score,
                            "required": self.min_goal_satisfaction,
                        }
                    )
        step_ids = {step.step_id for step in plan.steps}
        for resolution in plan.parameter_resolutions:
            if resolution.step_id not in step_ids and not resolution.blocking:
                errors.append({"type": "parameter_resolution_unknown_step", "step_id": resolution.step_id, "parameter": resolution.parameter})
            if resolution.blocking and plan.disposition == "execute":
                errors.append({"type": "blocking_parameter_resolution", "step_id": resolution.step_id, "parameter": resolution.parameter})
        for step in plan.steps:
            capability = allowed.get(step.skill_id)
            if capability is None:
                errors.append({"type": "unknown_capability", "step_id": step.step_id, "skill_id": step.skill_id})
                continue
            if not capability.get("available") or not capability.get("interaction_executable"):
                errors.append({"type": "capability_not_executable", "step_id": step.step_id,
                               "skill_id": step.skill_id})
                continue
            schema_errors = validate_args_for_schema(step.args, capability.get("input_schema") or {})
            if schema_errors:
                errors.append({"type": "invalid_args", "step_id": step.step_id, "skill_id": step.skill_id,
                               "errors": schema_errors[:8]})
        return errors

    def _clarify(self, plan_id: str, request: AgentRunRequest, reason: str, *, unresolved: list[str] | None = None,
                 metadata: dict[str, Any] | None = None, error: Exception | None = None,
                 attempts: int = 1) -> CanonicalPlan:
        detail = dict(metadata or {})
        detail.update({"resolver": "deep_planner", "status": "clarify", "authority": "advisory",
                       "attempt_count": attempts, "max_replans": self.max_replans, "reason": reason})
        if error is not None:
            detail.update(
                {
                    "error_type": type(error).__name__,
                    "error": str(error)[:300],
                    **llm_failure_metadata(error),
                }
            )
        context = request.context if isinstance(request.context, dict) else {}
        return CanonicalPlan(plan_id=plan_id, planner_tier="deep", disposition="clarify",
                             coverage="uncertain", confidence=0.0, goal_summary=request.text,
                             goal_ids=expected_goal_ids(context),
                             response_text="", steps=[], unresolved=list(unresolved or []), metadata=detail)
