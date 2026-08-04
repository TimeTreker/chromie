from __future__ import annotations

import copy
import hashlib
import json
import logging
from typing import Any

from pydantic import ValidationError

from .capabilities.catalog import CapabilityCatalog
from .capabilities.validator import validate_args_for_schema
from .clients.ollama_client import OllamaClient, llm_failure_metadata
from .agent_skills import agent_skill_prompt_section
from .cognitive_identity import (
    IDENTITY_SEMANTIC_CONTRACT,
    PERSONALITY_SEMANTIC_CONTRACT,
    bounded_identity_json,
    bounded_personality_json,
)
from .schema import AgentRunRequest

try:
    from chromie_runtime.cognitive_integrity_events import cognitive_integrity_metadata
    from chromie_runtime.runtime_trace import TraceModule, runtime_tracer
except ImportError:  # pragma: no cover
    from shared.chromie_runtime.cognitive_integrity_events import cognitive_integrity_metadata
    from shared.chromie_runtime.runtime_trace import TraceModule, runtime_tracer
from .planner_contract import (
    canonical_goal_grounding,
    canonical_plan_response_schema,
    coordinated_action_goal_ids,
    expected_goal_ids,
    is_planner_step_skill,
    materialize_goal_outcomes,
    materialize_planner_metadata,
    parallel_plan_contract_errors,
    planner_response_goal_ids,
    planner_contract_diagnostics,
    review_coordinated_action_plan_coverage,
    validate_external_response_evidence_boundary,
    validate_goal_binding_argument_grounding,
    validate_goal_responsibility_outcomes,
    validate_planner_model_output,
)

try:
    from chromie_contracts.plan import CanonicalPlan
except ImportError:  # pragma: no cover
    from shared.chromie_contracts.plan import CanonicalPlan

logger = logging.getLogger("chromie.agent.deep_planner")


class DeepPlannerResolver:
    """Full-catalog semantic planner with one bounded same-tier revision."""

    TRACE_MODULE = TraceModule(
        name="agent.deep_planner",
        component_type="planner",
        implementation="DeepPlannerResolver",
        schema_version=1,
    )

    def __init__(self, ollama: OllamaClient, catalog: CapabilityCatalog, *, min_confidence: float = 0.65,
                 num_ctx: int = 8192, num_predict: int = 1024, max_capabilities: int = 96,
                 max_replans: int = 2, min_goal_satisfaction: float = 0.75) -> None:
        self.ollama = ollama
        self.catalog = catalog
        self.min_confidence = max(0.0, min(1.0, float(min_confidence)))
        self.num_ctx = max(4096, int(num_ctx))
        self.num_predict = max(256, int(num_predict))
        self.max_capabilities = max(1, min(256, int(max_capabilities)))
        self.max_replans = max(0, min(2, int(max_replans)))
        self.min_goal_satisfaction = max(0.0, min(1.0, float(min_goal_satisfaction)))

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
                        "max_replans": self.max_replans,
                    },
                ) as span:
                    result = await self._resolve(request)
                    span.set_attribute("disposition", result.disposition)
                    span.set_attribute("coverage", result.coverage)
                    span.set_attribute("step_count", len(result.steps))
                    span.set_attribute("goal_count", len(result.goal_ids))
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
        capabilities = await self.catalog.prompt_entries(scope="all", refresh=False)
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
        payload = [self._capability_payload(item) for item in executable[: self.max_capabilities]]
        expected_goal_ids_for_turn = expected_goal_ids(
            request.context if isinstance(request.context, dict) else {}
        )
        authoritative_goals = canonical_goal_grounding(request.context)
        response_schema = self._response_schema(
            expected_goal_ids_for_turn,
            allowed_skill_ids=[item["capability_id"] for item in payload],
            response_only=response_only,
            requires_execution=requires_execution,
            response_goal_ids=sorted(planner_response_goal_ids(authoritative_goals)),
        )
        generation_options = {
            "temperature": 0,
            "top_p": 0.9,
            "num_ctx": self.num_ctx,
            "num_predict": self.num_predict,
        }
        persistent_safety_feedback = self._initial_safety_feedback(
            request.context if isinstance(request.context, dict) else {}
        )
        feedback: list[dict[str, Any]] = list(persistent_safety_feedback)
        previous_raw: Any = None
        initial_raw_output: Any = None
        contract_repair_attempted = False
        initial_validation_errors = ""
        for attempt in range(self.max_replans + 1):
            raw: Any = None
            try:
                active_response_schema = (
                    self._safety_revision_response_schema(
                        response_schema,
                        feedback=feedback,
                    )
                    if self._requires_safety_revision(feedback)
                    else response_schema
                )
                raw = await self.ollama.generate(
                    self._prompt(
                        request,
                        payload,
                        feedback=feedback,
                        response_schema=active_response_schema,
                        previous_raw=previous_raw,
                        expected_goal_ids=expected_goal_ids_for_turn,
                    ),
                    system=(
                        self._revision_system_prompt()
                        if feedback
                        else self._system_prompt()
                    ),
                    options=generation_options,
                    response_format=active_response_schema,
                )
                if not isinstance(raw, dict):
                    raise ValueError("deep planner response is not a JSON object")
                self._validate_parallel_timing_preservation(
                    raw,
                    context=request.context,
                )
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
                    feedback = self._merge_feedback(
                        persistent_safety_feedback,
                        [{
                            "type": "canonical_plan_contract_validation_failure",
                            "error_type": type(exc).__name__,
                            "validation_errors": initial_validation_errors,
                        }],
                    )
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
                plan,
                payload,
                expected_goal_ids=expected_goal_ids_for_turn,
                request=request,
            )
            errors = [
                *self._safety_revision_contract_errors(plan, feedback),
                *errors,
            ]
            if not errors:
                coverage_review_metadata: dict[str, Any] = {}
                coordinated_goal_ids = coordinated_action_goal_ids(
                    canonical_goal_grounding(request.context)
                )
                if (
                    coordinated_goal_ids.intersection(plan.goal_ids)
                    and plan.disposition in {"execute", "mixed"}
                    and plan.steps
                ):
                    try:
                        coverage_review = (
                            await review_coordinated_action_plan_coverage(
                                self.ollama,
                                request_text=request.text,
                                language=str(request.language or "und"),
                                authoritative_goals=canonical_goal_grounding(
                                    request.context
                                ),
                                plan=plan,
                                capabilities=payload,
                                num_ctx=self.num_ctx,
                            )
                        )
                    except Exception as exc:
                        logger.warning(
                            "deep_planner_coverage_review_unavailable sid=%s "
                            "error_type=%s error=%s",
                            request.sid,
                            type(exc).__name__,
                            exc,
                        )
                        return self._clarify(
                            plan_id,
                            request,
                            "coordinated_action_coverage_review_unavailable",
                            unresolved=["coordinated_action_coverage"],
                            error=exc,
                            attempts=attempt + 1,
                            metadata={
                                "coordinated_goal_ids": sorted(
                                    coordinated_goal_ids
                                ),
                                "execution_allowed": False,
                            },
                        )
                    if coverage_review.decision != "accept":
                        review_error = {
                            "type": "coordinated_action_coverage_incomplete",
                            "uncovered_requirements": list(
                                coverage_review.uncovered_requirements
                            ),
                            "reason": coverage_review.reason,
                            "confidence": coverage_review.confidence,
                        }
                        logger.warning(
                            "deep_planner_coverage_review_rejected sid=%s "
                            "attempt=%s uncovered=%s reason=%s",
                            request.sid,
                            attempt + 1,
                            coverage_review.uncovered_requirements,
                            coverage_review.reason,
                        )
                        if attempt < self.max_replans:
                            feedback = self._merge_feedback(
                                persistent_safety_feedback,
                                [review_error],
                            )
                            previous_raw = raw
                            continue
                        return self._clarify(
                            plan_id,
                            request,
                            "coordinated_action_coverage_incomplete",
                            unresolved=coverage_review.uncovered_requirements,
                            metadata={
                                "validation_feedback": [review_error],
                                "coordinated_goal_ids": sorted(
                                    coordinated_goal_ids
                                ),
                                "execution_allowed": False,
                            },
                            attempts=attempt + 1,
                        )
                    coverage_review_metadata["coverage_review"] = {
                        "status": "accepted",
                        "confidence": coverage_review.confidence,
                        "reason": coverage_review.reason,
                        "execution_authority": "none",
                    }
                metadata = dict(plan.metadata)
                metadata.update({"resolver": "deep_planner", "status": "complete" if plan.coverage == "complete" else plan.disposition,
                                 "authority": "advisory", "attempt_count": attempt + 1,
                                 "full_capability_count": len(payload), "max_replans": self.max_replans, "min_goal_satisfaction": self.min_goal_satisfaction,
                                 "contract_schema": "DeepPlannerModelOutput",
                                 "canonical_contract": "CanonicalPlan",
                                 "contract_repair_attempted": contract_repair_attempted,
                                 "contract_repair_succeeded": contract_repair_attempted})
                metadata.update(coverage_review_metadata)
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
                feedback = self._merge_feedback(
                    persistent_safety_feedback,
                    errors,
                )
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
            "hints": dict(item.hints),
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
        response_only: bool = False,
        requires_execution: bool = False,
        response_goal_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        return canonical_plan_response_schema(
            planner_tier="deep",
            expected_goal_ids=expected_goal_ids,
            allowed_skill_ids=list(allowed_skill_ids or []),
            response_only=response_only,
            requires_execution=requires_execution,
            response_goal_ids=response_goal_ids,
        )

    @staticmethod
    def _requires_safety_revision(feedback: list[dict[str, Any]]) -> bool:
        safety_types = {
            "parallel_capability_not_declared_safe",
            "parallel_exclusive_group_conflict",
            "parallel_resource_claim_conflict",
            "coordinated_action_coverage_incomplete",
            "safety_revision_contract_not_satisfied",
        }
        return any(
            isinstance(item, dict) and item.get("type") in safety_types
            for item in feedback
        )

    @staticmethod
    def _requires_sequential_safety_revision(
        feedback: list[dict[str, Any]],
    ) -> bool:
        concurrency_types = {
            "parallel_capability_not_declared_safe",
            "parallel_exclusive_group_conflict",
            "parallel_resource_claim_conflict",
        }
        return any(
            isinstance(item, dict) and item.get("type") in concurrency_types
            for item in feedback
        )

    @classmethod
    def _initial_safety_feedback(
        cls,
        context: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Carry upstream deterministic safety findings into Deep attempt one."""

        candidates: list[dict[str, Any]] = []
        fast_plan = context.get("fast_plan_resolution") or context.get(
            "fast_planner_resolution"
        )
        if isinstance(fast_plan, dict):
            metadata = fast_plan.get("metadata")
            if isinstance(metadata, dict):
                parallel_errors = metadata.get("parallel_contract_errors")
                # A lone step labeled parallel has no overlap relation to
                # revise.  Carry this finding only when Fast actually proposed
                # a multi-step concurrency plan; otherwise Deep may safely
                # regenerate the single step as sequential.
                if (
                    isinstance(parallel_errors, list)
                    and int(metadata.get("executable_step_count") or 0) > 1
                ):
                    candidates.extend(
                        item for item in parallel_errors if isinstance(item, dict)
                    )
        runtime_feedback = context.get("runtime_validator_feedback")
        if isinstance(runtime_feedback, list):
            candidates.extend(
                item for item in runtime_feedback if isinstance(item, dict)
            )
        return [
            dict(item)
            for item in cls._merge_feedback(candidates)
            if cls._requires_safety_revision([item])
        ]

    @staticmethod
    def _merge_feedback(
        *groups: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = []
        seen: set[str] = set()
        for group in groups:
            for item in group:
                if not isinstance(item, dict):
                    continue
                key = json.dumps(
                    item,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    default=str,
                )
                if key in seen:
                    continue
                seen.add(key)
                merged.append(item)
        return merged

    @classmethod
    def _safety_revision_response_schema(
        cls,
        base_schema: dict[str, Any],
        *,
        feedback: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Forbid exact execution after deterministic concurrency rejection."""

        schema = copy.deepcopy(base_schema)
        if cls._requires_sequential_safety_revision(list(feedback or [])):
            # The deployed structured decoder does not reliably enforce a
            # nested step constraint added only through a top-level allOf.
            # Specialize the referenced step DTO itself so a concurrency
            # rejection cannot be relabeled as a safe adjustment while the
            # rejected parallel timing remains unchanged.  This conservative
            # revision may still clarify or propose a confirmation-bound
            # sequential alternative; it cannot authorize overlap.
            step_schema = schema.get("$defs", {}).get("PlannerModelStep")
            if isinstance(step_schema, dict):
                timing = step_schema.get("properties", {}).get("timing")
                if isinstance(timing, dict):
                    timing["enum"] = ["sequential"]
                    timing["default"] = "sequential"
                    timing["description"] = (
                        "Concurrency was rejected by deterministic provider/resource "
                        "validation; retained executable steps must be sequential."
                    )
        schema.setdefault("allOf", []).append(
            {
                "anyOf": [
                    {
                        "properties": {
                            "disposition": {
                                "type": "string",
                                "enum": ["execute", "mixed"],
                            },
                            "plan_relation": {
                                "type": "string",
                                "enum": ["safe_adjustment", "alternative"],
                            },
                            "user_confirmation_required": {
                                "type": "boolean",
                                "enum": [True],
                            },
                            "response_text": {
                                "type": "string",
                                "minLength": 1,
                            },
                        }
                    },
                    {
                        "properties": {
                            "disposition": {
                                "type": "string",
                                "enum": ["clarify", "unavailable", "refused"],
                            },
                            "steps": {
                                "type": "array",
                                "maxItems": 0,
                            },
                            "plan_relation": {
                                "type": "string",
                                "enum": ["exact"],
                            },
                            "user_confirmation_required": {
                                "type": "boolean",
                                "enum": [False],
                            },
                        }
                    },
                ]
            }
        )
        return schema

    @classmethod
    def _safety_revision_contract_errors(
        cls,
        plan: CanonicalPlan,
        feedback: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Enforce the decoder's safety-revision grammar at runtime too."""

        if not cls._requires_safety_revision(feedback):
            return []
        if plan.disposition in {"clarify", "unavailable", "refused"}:
            return [] if not plan.steps else [
                {
                    "type": "safety_revision_contract_not_satisfied",
                    "reason": "non-executable safety revision retained plan steps",
                }
            ]
        relation = str(plan.metadata.get("plan_relation") or "exact")
        confirmation = plan.metadata.get("user_confirmation_required") is True
        retained_parallel_steps = [
            step.step_id for step in plan.steps if step.timing == "parallel"
        ]
        if (
            cls._requires_sequential_safety_revision(feedback)
            and retained_parallel_steps
        ):
            return [
                {
                    "type": "safety_revision_contract_not_satisfied",
                    "plan_relation": relation,
                    "parallel_step_ids": retained_parallel_steps,
                    "reason": (
                        "concurrency was rejected, so a safe revision cannot "
                        "retain parallel step timing"
                    ),
                }
            ]
        if (
            plan.disposition in {"execute", "mixed"}
            and relation in {"safe_adjustment", "alternative"}
            and confirmation
            and bool(plan.response_text.strip())
        ):
            return []
        return [
            {
                "type": "safety_revision_contract_not_satisfied",
                "disposition": plan.disposition,
                "plan_relation": relation,
                "user_confirmation_required": confirmation,
                "response_text_present": bool(plan.response_text.strip()),
                "reason": (
                    "after concurrency safety rejection, execution requires an "
                    "explicit safe_adjustment or alternative, explanatory "
                    "response_text, and user confirmation"
                ),
            }
        ]

    @staticmethod
    def _validate_parallel_timing_preservation(
        raw: dict[str, Any],
        *,
        context: dict[str, Any] | None,
    ) -> None:
        """Reject a silent loss of Fast Planner concurrency.

        The Host does not infer concurrency from user phrases. It only preserves
        the preceding model-authored Fast plan as semantic evidence. Deep Planner
        may keep parallel timing or explicitly revise it using validator feedback,
        but omitting timing must never fall through to the DTO's sequential
        compatibility default.
        """

        if not isinstance(context, dict):
            return
        advisory = context.get("fast_plan_resolution") or context.get(
            "fast_planner_resolution"
        )
        if not isinstance(advisory, dict):
            return
        fast_steps = advisory.get("steps")
        raw_steps = raw.get("steps")
        if not isinstance(fast_steps, list) or not isinstance(raw_steps, list):
            return
        parallel_fast = [
            item
            for item in fast_steps
            if isinstance(item, dict)
            and str(item.get("timing") or "").strip() == "parallel"
        ]
        if len(parallel_fast) < 2:
            return
        expected_skills = sorted(
            str(item.get("capability_id") or item.get("skill_id") or "").strip()
            for item in parallel_fast
            if str(item.get("capability_id") or item.get("skill_id") or "").strip()
        )
        actual_skills = sorted(
            str(item.get("capability_id") or item.get("skill_id") or "").strip()
            for item in raw_steps
            if isinstance(item, dict)
            and str(item.get("capability_id") or item.get("skill_id") or "").strip()
        )
        if expected_skills != actual_skills:
            return
        missing = [
            index
            for index, item in enumerate(raw_steps)
            if isinstance(item, dict) and "timing" not in item
        ]
        if missing:
            raise ValueError(
                "deep planner omitted timing while revising a parallel Fast plan; "
                "explicitly preserve parallel timing or author an explicit reviewed alternative"
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
        identity_json = bounded_identity_json(context)
        personality_json = bounded_personality_json(context)
        skill_section = agent_skill_prompt_section(
            context,
            agent_role="deep_planner",
        )
        fast_plan = context.get("fast_plan_resolution") or context.get("fast_planner_resolution") or {}
        goals = context.get("active_goal_snapshots") or []
        association = context.get("goal_association_resolution") or {}
        grounding = canonical_goal_grounding(context)
        runtime_feedback = context.get("runtime_validator_feedback") or []
        combined_feedback = [*feedback, *(runtime_feedback if isinstance(runtime_feedback, list) else [])]
        feedback_section = self._bounded(combined_feedback, 5000) if combined_feedback else "[]"
        previous_section = self._bounded(previous_raw, 5000) if previous_raw is not None else "null"
        source_route = str(request.route_decision.route or "").strip()
        route_effect_contract = (
            "The authoritative source route is chat. This turn is response-only: "
            "do not select or invent executable skills, physical effects, or plan "
            "steps. Use respond, clarify, unavailable, or refused outcomes only. "
            if source_route == "chat"
            else (
                "The authoritative source route is tool. This fresh external-information "
                "turn must contain at least one executable supplied tool step, or return "
                "clarify/unavailable/refused when no valid tool plan is possible. Do not "
                "terminate the whole turn as respond from model memory or loosely related "
                "evidence. Every top-level and per-goal response_text must be empty on this "
                "tool route: do not greet, self-introduce, narrate the lookup, or predict "
                "its result. Response Composer owns optional pre-execution speech and "
                "trusted post-execution interpretation owns the answer. A completed-evidence "
                "follow-up that needs no execution belongs on a chat route upstream. "
                if source_route == "tool"
                else ""
            )
        )
        return (
            f"Fast-plan advisory JSON:\n{self._bounded(fast_plan, 1800)}\n\n"
            f"Goal association advisory JSON:\n{self._bounded(association, 3200)}\n\n"
            f"Active goals JSON:\n{self._bounded(goals, 3200)}\n\n"
            f"Owner-approved Chromie identity JSON:\n{identity_json}\n\n"
            f"Owner-approved Personality Expression JSON:\n{personality_json}\n\n"
            f"{skill_section}"
            f"Executable capability catalog JSON:\n{self._bounded(capabilities, 16000)}\n\n"
            f"Verified tool-memory index JSON (provenance and bound arguments only; no result contents):\n{self._bounded(context.get('verified_tool_memory_index') or [], 6000)}\n\n"
            f"Active and recoverable task bindings JSON:\n{self._bounded(context.get('active_task_snapshots') or [], 6000)}\n\n"
            f"Previous Deep Planner model output JSON, when doing a semantic runtime replan:\n{previous_section}\n\n"
            f"Deterministic validation feedback from the previous deep-plan or trusted host-runtime attempt:\n{feedback_section}\n\n"
            "When validation feedback is present but the previous output is null, regenerate one fresh complete object from the authoritative turn, goals, catalog, and all listed defects. Do not patch, quote, splice, annotate, or embed JSON fragments inside rationale or response strings. "
            "When validation feedback says parallel execution is not affirmatively safe, never silently change parallel steps to an exact sequential plan. Either author plan_relation=safe_adjustment or alternative with user_confirmation_required=true and response_text explaining the timing change, or return a zero-step clarification/unavailable result. "
            "Produce the final DeepPlannerModelOutput for the complete user goal. Deep planning is terminal: never return to the Fast Planner. The FINAL AUTHORITATIVE USER TURN owns the current communicative act. Retained Goals and delivered evidence may support a response, but must not replace the latest reaction, feeling, acknowledgement, evaluation, or practical decision. Answer that current act directly; replay or re-explain a prior task only when the latest turn asks for it. The verified tool-memory index contains no answer facts. If one exact fresh index entry matches the authoritative Goal bindings, execute chromie.memory.retrieve_verified_tool_result with its evidence_id, original tool_id, and the exact material arguments. If no such entry exists, execute the fresh read capability. Never answer directly from index metadata, never reinterpret an unresolved reference from old memory, and never use another task's result. When a scheduled, running, or recoverable safe read has no matching completed memory entry, resume or retry its bound capability with the exact arguments. "
            f"{route_effect_contract}"
            f"{IDENTITY_SEMANTIC_CONTRACT}"
            f"{PERSONALITY_SEMANTIC_CONTRACT}"
            "Use the full catalog, preserve all independent responsibilities, constraints, conditions, ordering, concurrency, temporal scope, comparison period, and requested answer shape. Never silently rewrite simultaneous independent actions as before/after actions. Every executable step must explicitly include timing; omission is invalid because it would erase the model's ordering or concurrency decision. When the user requests compatible actions to happen together, assign timing=parallel only when each selected capability explicitly declares parallel_metadata_declared=true and can_run_parallel=true and their exclusive/resource claims are compatible. Never invent an unstated feature of a capability in a reason or outcome; a physical action cannot satisfy a conversational or spoken-performance Goal unless its supplied semantics explicitly say so. Use a respond outcome for speech authored by Response Composer. Never satisfy a prohibition, negation, or hold-state constraint by invoking the positive action it forbids; if the catalog has no capability whose semantic scope actually enforces that negative state, clarify or report it unavailable. If safe parallel execution is unavailable or uncertain, clarify or propose an explicit safe adjustment rather than silently serializing the request. For a Goal with resource_responsibility, treat the entire acquire-and-deliver outcome as one semantic responsibility. Select only an exact registered Capability whose declared semantic_scope covers that resource kind, acquisition, and delivery. Never substitute a partial primitive such as walking for physical fetch-and-deliver, or generic conversation for external information retrieval. Provider-internal stages such as navigation, search, grasp, carry, evidence retrieval, evaluation, and final delivery are not separate Goals or planner steps unless the selected Capability contract explicitly exposes them as independently authoritative outcomes. The Goal is provider-neutral: choose from the catalog by exact supported semantics, never from a hardcoded provider rule. When resource_responsibility.source.status=unknown and the selected capability cannot resolve the source itself, return a specific context request and zero executable steps. Capability semantic_scope metadata is authoritative applicability evidence. Never silently narrow a canonical goal to fit a capability or its enum defaults. If a goal is outside every available capability scope, clarify or report unavailable with zero steps. Resolve low-consequence "
            "parameters semantically when justified; otherwise return a specific natural clarification. Canonical Goal object.bindings are authoritative resolved parameters from Goal Association. Every material step argument, including location, date, target, person, and entity identity, must equal the matching binding; do not replace a binding with a value from older memory or re-resolve the original reference. For chromie.weather.lookup, keep args.location exactly equal to the canonical location binding. When the user or discourse context clearly supplies a hierarchical place, you may also provide location_context with locality, admin1, country, and aliases for that same place; never use it to select a different place. For chromie.memory.retrieve_verified_tool_result, resolved Goal bindings such as location and date belong inside the single material_args object. They are not missing direct step arguments, so do not emit separate location or date parameter_resolutions. If a resolution for that nested object is useful, its parameter must be material_args and its value must equal the complete step.args.material_args object. When independent goals have different terminal needs, use disposition=mixed, coverage=complete, and goal_outcomes so executable goals can proceed while only affected goals wait for clarification. Scope every blocking parameter resolution with source_goal_ids. Exact, safe-adjusted, or alternative executable plans "
            "must use coverage=complete and disposition=execute or mixed as appropriate. Every executable step must include source_goal_ids identifying exactly the goals it serves. Use plan_relation=exact for an exact plan. A safe_adjustment or material alternative must use the corresponding plan_relation, be described in response_text, set user_confirmation_required=true, and require "
            "confirmation downstream. For every missing parameter, return parameter_resolutions with a semantic strategy, concrete value when resolved, confidence, and rationale. Use safe_default only for low-consequence reversible values inside schema bounds. Use ask_user for material or risky values. Also return goal_satisfaction as prospective plan adequacy: planned steps count as satisfying their goals if successful, and pending execution alone is never an unmet requirement. An exact complete plan therefore uses status=exact with score at least 0.95 and lists the goals it is designed to satisfy. If essential information remains missing, use coverage=partial or uncertain with disposition=clarify and zero steps. "
            "If unavailable or refused, use zero steps. Use exact supplied capability IDs and schema-valid args. "
            "User-facing speech is owned by Response Composer and is never an executable plan step. A conversational answer, joke, explanation, greeting, or spoken performance uses a respond outcome with non-empty response_text and zero step_ids. When a Goal has responsibility_kind=spoken_response, response_text is the completion surface itself: include the requested authored content now, such as the actual answer, joke, or song verse, rather than willingness, a promise to perform later, a title alone, or a stage direction. Combine that outcome with physical execution as disposition=mixed; do not create a speech transport step. Greeting wording and length are ordinary model-authored conversational choices governed by the supplied scene, relationship context, and owner-approved personality. "
            "A plan step may contain only step_id, capability_id, args, timing, source_goal_ids, and reason_summary. "
            "Use capability_id as the executable identity. Do not copy catalog-only fields such as input_schema, parameters, route, step_type, or effects into a plan step. "
            "Use exactly the supplied canonical goal IDs. Do not create goals for internal status checks, safety checks, capability lookups, or implementation preconditions; represent any justified internal operation only as a step owned by an existing user goal. "
            "Keep the plan minimal: do not add neutral-position, reset, transition, cleanup, or presentation steps unless the user explicitly requested them or a supplied capability execution constraint explicitly requires them. "
            "goal_outcomes is a JSON object keyed by every supplied canonical goal ID exactly once, never a list; every Deep Planner result must include it. Every outcome must explicitly author disposition, coverage, response_text, unresolved, step_ids, satisfaction, and rationale. Each value describes only that key's goal and must not repeat goal_id inside the value. Per-goal outcome invariants are mandatory: execute requires coverage=complete and at least one real plan step_id copied exactly from steps; respond requires coverage=complete, the actual answer text now (not a promise that it will be supplied later), and zero step_ids; clarify requires coverage=partial or uncertain, an unresolved need or response_text, and zero step_ids; unavailable and refused require zero step_ids. Top-level and per-goal satisfaction are always non-null model judgments with score, status, satisfied_goal_ids, unmet_goal_ids, unmet_requirements, and rationale. A satisfaction score from 0.95 through 1.0 requires status=exact; score=1.0 must never use substantial. Do not assign a physical skill to a conversational answer merely because it is the nearest remaining capability. "
            "Top-level disposition is the aggregate of per-goal dispositions: use mixed only when at least two different per-goal disposition values are present. Multiple goals that are all execute use top-level execute; multiple goals that are all respond use top-level respond. "
            "Every outcome step_id must name a real plan step, every plan step must be referenced by an execute outcome when goal_outcomes are present, and each step source_goal_ids must exactly match the execute outcomes that reference it. "
            "The Ollama decoder enforces the exact flat DeepPlannerModelOutput JSON Schema supplied out-of-band. The host adds plan identity, planner tier, and the authoritative top-level canonical goal IDs; do not emit those envelope fields. Populate only fields allowed by the model schema and return JSON only. "
            "The following final grounding block is authoritative and must override unrelated content in previous model output or advisory context.\n\n"
            f"FINAL AUTHORITATIVE USER TURN:\n{request.text}\n\n"
            f"FINAL CANONICAL GOALS JSON (copy goal IDs exactly and satisfy these meanings only):\n{self._bounded(grounding, 5000)}\n\n"
            f"FINAL ALLOWED EXECUTABLE CAPABILITY IDS JSON:\n{self._bounded([item['capability_id'] for item in capabilities], 4000)}"
        )

    @staticmethod
    def _system_prompt() -> str:
        return (
            "You are Chromie's Deep Planner. Plan only the final authoritative user turn and canonical goals supplied at the end of the prompt. "
            "You may revise once from structured validator feedback, but you never call or return to the Fast Planner. "
            "Capabilities are plan leaves, not planner ownership boundaries. Do not execute, authorize, or claim completion. Return JSON only."
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
        validate_goal_responsibility_outcomes(
            model_output,
            authoritative_goals=canonical_goal_grounding(request.context),
            context=request.context,
        )
        validate_goal_binding_argument_grounding(
            model_output,
            authoritative_goals=canonical_goal_grounding(request.context),
        )
        validate_external_response_evidence_boundary(
            model_output,
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
        request: AgentRunRequest,
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
        if (
            str(request.route_decision.route or "").strip() == "tool"
            and plan.disposition not in {"clarify", "unavailable", "refused"}
            and not plan.steps
        ):
            errors.append(
                {
                    "type": "tool_route_requires_executable_step",
                    "disposition": plan.disposition,
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
                # The complete aggregate satisfaction object and exact keyed
                # outcome map already express prospective adequacy. Per-outcome
                # satisfaction is useful when the model supplies it, but is not
                # a second mandatory copy of the same judgment. Treat a supplied
                # low score as authoritative without failing solely on omission.
                if (
                    outcome.satisfaction is not None
                    and outcome.satisfaction.score < self.min_goal_satisfaction
                ):
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
            capability = allowed.get(step.capability_id)
            if capability is None:
                errors.append({"type": "unknown_capability", "step_id": step.step_id, "capability_id": step.capability_id})
                continue
            if not capability.get("available") or not capability.get("interaction_executable"):
                errors.append({"type": "capability_not_executable", "step_id": step.step_id,
                               "capability_id": step.capability_id})
                continue
            schema_errors = validate_args_for_schema(step.args, capability.get("input_schema") or {})
            if schema_errors:
                errors.append({"type": "invalid_args", "step_id": step.step_id, "capability_id": step.capability_id,
                               "errors": schema_errors[:8]})
        errors.extend(parallel_plan_contract_errors(plan, capabilities))
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
