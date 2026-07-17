from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from pydantic import ValidationError

from .capabilities.catalog import CapabilityCatalog
from .clients.ollama_client import OllamaClient, llm_failure_metadata
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
from .schema import AgentRunRequest

try:
    from chromie_contracts.plan import CanonicalPlan
except ImportError:  # pragma: no cover
    from shared.chromie_contracts.plan import CanonicalPlan

logger = logging.getLogger("chromie.agent.fast_planner")


class FastPlannerResolver:
    """Low-latency semantic planner over the executable common catalog only."""

    def __init__(
        self,
        ollama: OllamaClient,
        catalog: CapabilityCatalog,
        *,
        min_confidence: float = 0.8,
        num_ctx: int = 4096,
        num_predict: int = 512,
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
        plan_id = self._plan_id(request)
        capabilities = await self.catalog.prompt_entries(scope="common", refresh=False)
        executable = [
            item
            for item in capabilities
            if item.available
            and item.interaction_executable
            and is_planner_step_skill(item.capability_id)
        ]
        capability_payload = [
            {
                "capability_id": item.capability_id,
                "description": item.description,
                "input_schema": item.input_schema,
                "requires_confirmation": item.requires_confirmation,
                "can_run_parallel": item.can_run_parallel,
                "exclusive_group": item.exclusive_group,
            }
            for item in executable[: self.max_capabilities]
        ]
        context = request.context if isinstance(request.context, dict) else {}
        expected_goal_ids_for_turn = expected_goal_ids(context)
        response_schema = canonical_plan_response_schema(
            planner_tier="fast",
            expected_goal_ids=expected_goal_ids_for_turn,
            allowed_skill_ids=[item["capability_id"] for item in capability_payload],
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
                    response_format=response_schema,
                )
                if not isinstance(raw, dict):
                    raise ValueError("fast planner response is not a JSON object")
                normalized = self._normalize(
                    raw,
                    request=request,
                    plan_id=plan_id,
                    expected_goal_ids_for_turn=expected_goal_ids_for_turn,
                )
                plan = CanonicalPlan.model_validate(normalized)
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
                        "fast_planner_contract_repair_start sid=%s validation_errors=%s raw_output=%s",
                        request.sid,
                        initial_validation_errors,
                        self._bounded(initial_raw_output, 4000),
                    )
                    continue
                return self._escalation(
                    plan_id,
                    request,
                    "fast_planner_model_contract_failed"
                    if contract_repair_attempted
                    else "fast_planner_unavailable",
                    error=exc,
                    metadata={
                        "contract_schema": "FastPlannerModelOutput",
                        "canonical_contract": "CanonicalPlan",
                        "contract_repair_attempted": contract_repair_attempted,
                        "contract_repair_succeeded": False,
                        "initial_validation_errors": initial_validation_errors,
                        "initial_raw_output": self._bounded(initial_raw_output, 4000)
                        if initial_raw_output is not None
                        else "",
                        "repair_raw_output": self._bounded(raw, 4000)
                        if contract_repair_attempted and raw is not None
                        else "",
                    },
                )

            validated = self._validate(
                plan,
                capability_payload=capability_payload,
                request=request,
                expected_goal_ids_for_turn=expected_goal_ids_for_turn,
            )
            if contract_repair_attempted:
                metadata = dict(validated.metadata)
                metadata.update(
                    {
                        "contract_schema": "FastPlannerModelOutput",
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
        association = context.get("goal_association_resolution") or {}
        route = request.route_decision
        advisory = {
            "route": route.route,
            "intent": route.intent,
            "confidence": route.confidence,
        }
        grounding = canonical_goal_grounding(context)
        return (
            f"Goal association advisory JSON:\n{self._bounded(association, 3000)}\n\n"
            f"Router advisory JSON:\n{self._bounded(advisory, 900)}\n\n"
            f"Executable common capability catalog JSON:\n{self._bounded(capabilities, 9000)}\n\n"
            f"Previous Fast Planner output when doing a semantic replan:\n{self._bounded(previous_raw, 3500) if previous_raw is not None else 'null'}\n\n"
            f"Exact contract validation errors when revising:\n{validation_errors or '[]'}\n\n"
            "When validation errors are present and the previous output is null, regenerate one fresh complete object from the authoritative turn, goals, catalog, and every listed defect. Do not patch, quote, splice, annotate, or embed JSON fragments inside rationale or response strings. "
            "Decide whether the executable common catalog completely covers every independent responsibility in the current user turn. "
            "Finding one matching skill is not complete coverage. If any responsibility, parameter, ordering, concurrency relation, or capability is unresolved, return disposition=escalate, coverage=partial or uncertain, a non-empty escalation_reason, and zero steps. "
            "Fast Planner must not emit mixed outcomes; escalate so Deep Planner can account for them. For complete direct execution, use exact supplied skill IDs and schema-valid args. "
            "User-facing speech is owned by Response Composer, not a plan step. Represent a conversational answer as disposition=respond with response_text; if it is independent of an executable goal, escalate for a Deep Planner mixed execute/respond outcome. "
            "Every executable step must use source_goal_ids copied from the canonical goals. Do not use capability_id, parameters, action, input_schema, route, or step_type as plan-step fields. "
            "goal_satisfaction measures prospective plan adequacy: planned steps count as satisfying their goals if successful, so pending execution alone is never an unmet requirement. A score from 0.95 through 1.0 requires status=exact; score=1.0 must never use substantial. If steps are present, top-level disposition cannot be respond. "
            "For every complete multi-goal execute or respond result, goal_outcomes must be keyed exactly once by every supplied canonical goal ID. "
            "Use plan_relation=exact for an exact plan. A safe_adjustment or alternative must set user_confirmation_required=true so the host holds execution for approval. "
            "The Ollama decoder enforces the exact flat FastPlannerModelOutput schema out-of-band. "
            "The host adds plan identity, planner tier, and the authoritative top-level canonical goal IDs; do not emit those envelope fields. "
            "Return JSON only. The final grounding below is authoritative and overrides previous output or advisory text.\n\n"
            f"FINAL AUTHORITATIVE USER TURN:\n{request.text}\n\n"
            f"FINAL CANONICAL GOALS JSON:\n{self._bounded(grounding, 4500)}\n\n"
            f"FINAL ALLOWED EXECUTABLE SKILL IDS JSON:\n{self._bounded([item['capability_id'] for item in capabilities], 2500)}"
        )

    @staticmethod
    def _system_prompt() -> str:
        return (
            "You are Chromie's Fast Planner. Plan only the final authoritative user turn and canonical goals at the end of the prompt. "
            "Produce a complete simple response or complete common-skill plan only when every responsibility is covered; otherwise escalate. "
            "Do not execute, authorize, or claim completion. Return JSON only."
        )

    @staticmethod
    def _repair_system_prompt() -> str:
        return (
            "You regenerate one fresh Fast Planner output using the supplied authoritative goals, executable capability catalog, complete validation errors, and schema-constrained decoder. "
            "Rebuild every required field instead of editing or splicing the invalid JSON. Regenerate the flat FastPlannerModelOutput without local aliases, annotations, or field mappings. Return JSON only."
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
            planner_tier="fast",
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
        if expected_goal_ids_for_turn and set(plan.goal_ids) != set(expected_goal_ids_for_turn):
            return self._escalation(
                plan.plan_id,
                request,
                "goal_ids_do_not_match_goal_association",
                metadata={
                    "expected_goal_ids": expected_goal_ids_for_turn,
                    "actual_goal_ids": list(plan.goal_ids),
                },
            )
        if plan.coverage != "complete" or plan.confidence < self.min_confidence:
            return self._escalation(
                plan.plan_id,
                request,
                "coverage_not_complete",
                unresolved=plan.unresolved,
                metadata={
                    "proposed_coverage": plan.coverage,
                    "proposed_confidence": plan.confidence,
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
                    )
                },
            )
        for step in plan.steps:
            capability = allowed.get(step.skill_id)
            if capability is None:
                return self._escalation(
                    plan.plan_id,
                    request,
                    "step_not_in_executable_common_catalog",
                    unresolved=[step.skill_id],
                )
        metadata = dict(plan.metadata)
        metadata.update(
            {
                "resolver": "fast_planner",
                "status": "complete",
                "authority": "advisory",
                "common_capability_count": len(capability_payload),
                "min_confidence": self.min_confidence,
                "contract_schema": "FastPlannerModelOutput",
                "canonical_contract": "CanonicalPlan",
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
    ) -> CanonicalPlan:
        detail = dict(metadata or {})
        detail.update(
            {
                "resolver": "fast_planner",
                "status": "escalate",
                "authority": "advisory",
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
