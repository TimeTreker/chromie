"""Canonical Plan to Capability Runtime adapter for the goal-driven runtime.

``CanonicalPlanRuntimeAdapter`` validates a canonical Plan against the live
Capability Registry, prepares auxiliary and social responses and builds the
InteractionResponse that the Capability Runtime executes.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections import deque
from datetime import datetime, timezone
from typing import Any, Callable

from agent.app.capabilities.validator import validate_args_for_schema
from pydantic import ValidationError

from shared.chromie_contracts.execution_outcome import (
    claim_qualification_policy_sha256,
)
from shared.chromie_contracts.interaction import (
    InteractionResponse,
    InteractionSpeech,
    MEDIA_CAPABILITY_IDS,
    CapabilityRequest,
    VOCAL_PERFORMANCE_CAPABILITY_ID,
    output_schema_sha256,
    validate_output_schema_declaration,
)
from shared.chromie_contracts.social_cognition import SocialCognitionRequest, SocialCognitionResolution
from shared.chromie_contracts.plan import (
    AuxiliaryPlanActivity,
    CanonicalPlan,
    fast_planner_activity_request_id,
    validate_communicative_activity_identity,
    canonical_plan_fingerprint,
)
from shared.chromie_contracts.planner_response import PlannerResponseProjection
from shared.chromie_contracts.semantic_task import ResponsePlan, ResponseStage
from shared.chromie_contracts.user_turn import (
    user_turn_prohibits_speech,
)
from shared.chromie_runtime.runtime_trace import TraceModule, runtime_tracer

from orchestrator.runtime.cognitive_runtime import (
    _lineage_context,
    _plan_semantic_lineage,
    _semantic_lineage_from_context,
    _social_semantic_lineage,
)

logger = logging.getLogger(__name__)


class CanonicalPlanRuntimeAdapter:
    """Translate validated canonical planning into the existing trusted runtime."""

    TRACE_MODULE = TraceModule(
        name="orchestrator.canonical_plan_adapter",
        component_type="runtime_adapter",
        implementation="CanonicalPlanRuntimeAdapter",
        schema_version=1,
    )

    def __init__(
        self,
        interaction_runtime: Any,
        *,
        recent_auxiliary_evidence_limit: int = 12,
    ) -> None:
        self.interaction_runtime = interaction_runtime
        self._recent_auxiliary_behavior_evidence: deque[dict[str, Any]] = deque(
            maxlen=max(1, int(recent_auxiliary_evidence_limit))
        )

    def recent_auxiliary_behavior_evidence(
        self,
        session_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return bounded host evidence without implying provider completion."""

        evidence = [dict(item) for item in self._recent_auxiliary_behavior_evidence]
        if session_id is None:
            return evidence
        return [item for item in evidence if item.get("session_id") == session_id]

    def _record_auxiliary_behavior_request(
        self,
        request: CapabilityRequest,
        *,
        session_id: str,
    ) -> None:
        if not request.metadata.get("auxiliary_plan_activity"):
            return
        if any(
            item.get("request_id") == request.request_id
            for item in self._recent_auxiliary_behavior_evidence
        ):
            return
        self._recent_auxiliary_behavior_evidence.append(
            {
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "session_id": session_id,
                "evidence_kind": "host_accepted_auxiliary_request",
                "execution_claim": "not_observed",
                "request_id": request.request_id,
                "capability_id": request.capability_id,
                "semantic_args": dict(request.args),
                "social_function": request.metadata.get("social_function"),
                "turn_id": request.metadata.get("turn_id"),
                "anchor_kind": request.metadata.get("anchor_kind"),
                "anchor_id": request.metadata.get("anchor_id"),
                "auxiliary_activity_id": request.metadata.get(
                    "auxiliary_activity_id"
                ),
                "primary_activity_goal_ids": list(
                    request.metadata.get("primary_activity_goal_ids") or []
                ),
                "primary_activity_execution_lanes": list(
                    request.metadata.get("primary_activity_execution_lanes") or []
                ),
                "primary_activity_vocal_modes": list(
                    request.metadata.get("primary_activity_vocal_modes") or []
                ),
                "canonical_plan_id": request.metadata.get("canonical_plan_id"),
                "social_cognition_request_id": request.metadata.get("social_cognition_request_id"),
            }
        )


    async def validation_errors(self, plan: CanonicalPlan) -> list[dict[str, Any]]:
        async with runtime_tracer.span(
            module=self.TRACE_MODULE,
            operation="validate_plan",
            attributes={
                "plan_disposition": plan.disposition,
                "step_count": len(plan.steps),
                "planner_tier": plan.planner_tier,
            },
        ) as span:
            errors = await self._validation_errors(plan)
            span.set_attribute("error_count", len(errors))
            if errors:
                span.set_status("error")
            return errors

    async def _validation_errors(self, plan: CanonicalPlan) -> list[dict[str, Any]]:
        errors: list[dict[str, Any]] = []
        if plan.disposition not in {"execute", "mixed"}:
            if plan.steps:
                errors.append({"type": "non_execute_plan_has_steps"})
            return errors
        capability_ids = [step.capability_id for step in plan.steps]
        try:
            await self.interaction_runtime.ensure_capability_definitions(capability_ids)
        except Exception as exc:
            return [
                {
                    "type": "runtime_catalog_error",
                    "error_type": type(exc).__name__,
                    "message": str(exc)[:400],
                }
            ]

        definitions: dict[str, Any] = {}
        for step in plan.steps:
            try:
                definition = self.interaction_runtime.capability_definition(step.capability_id)
            except Exception as exc:
                errors.append(
                    {
                        "type": "unknown_runtime_capability",
                        "step_id": step.step_id,
                        "capability_id": step.capability_id,
                        "message": str(exc)[:300],
                    }
                )
                continue
            definitions[step.step_id] = definition
            if not definition.available:
                errors.append(
                    {
                        "type": "runtime_capability_unavailable",
                        "step_id": step.step_id,
                        "capability_id": step.capability_id,
                        "reason": definition.unavailable_reason,
                    }
                )
                continue
            try:
                validate_output_schema_declaration(definition.output_schema)
                output_schema_sha256(definition.output_schema)
            except (TypeError, ValueError) as exc:
                errors.append(
                    {
                        "type": "runtime_invalid_output_schema",
                        "step_id": step.step_id,
                        "capability_id": step.capability_id,
                        "message": str(exc)[:160],
                    }
                )
            schema_errors = validate_args_for_schema(step.args, definition.input_schema)
            if schema_errors:
                errors.append(
                    {
                        "type": "runtime_invalid_args",
                        "step_id": step.step_id,
                        "capability_id": step.capability_id,
                        "errors": schema_errors[:8],
                    }
                )

        parallel_batch: list[Any] = []
        for step in plan.steps:
            # Adjacent Fast execution groups stay separate (no key: one contiguous batch).
            if step.timing == "parallel" and (
                not parallel_batch
                or (step.metadata or {}).get("execution_group")
                == (parallel_batch[0].metadata or {}).get("execution_group")
            ):
                parallel_batch.append(step)
                continue
            errors.extend(
                self._parallel_errors(
                    parallel_batch,
                    definitions,
                    plan_step_count=len(plan.steps),
                )
            )
            parallel_batch = [step] if step.timing == "parallel" else []
        errors.extend(
            self._parallel_errors(
                parallel_batch,
                definitions,
                plan_step_count=len(plan.steps),
            )
        )
        return errors

    @staticmethod
    def _parallel_errors(
        steps: list[Any],
        definitions: dict[str, Any],
        *,
        plan_step_count: int,
    ) -> list[dict[str, Any]]:
        if not steps:
            return []
        if len(steps) == 1 and plan_step_count > 1:
            step = steps[0]
            return [
                {
                    "type": "runtime_parallel_singleton_group",
                    "step_id": step.step_id,
                    "capability_id": step.capability_id,
                }
            ]
        errors: list[dict[str, Any]] = []
        for index, step in enumerate(steps):
            definition = definitions.get(step.step_id)
            if definition is None:
                continue
            if not definition.can_run_parallel:
                errors.append(
                    {
                        "type": "runtime_parallel_not_supported",
                        "step_id": step.step_id,
                        "capability_id": step.capability_id,
                    }
                )
            left_group = str(definition.exclusive_group or "")
            left_resources = {
                str(item) for item in definition.metadata.get("resource_claims", []) if str(item)
            }
            for other in steps[index + 1 :]:
                other_definition = definitions.get(other.step_id)
                if other_definition is None:
                    continue
                right_group = str(other_definition.exclusive_group or "")
                right_resources = {
                    str(item)
                    for item in other_definition.metadata.get("resource_claims", [])
                    if str(item)
                }
                if left_group and right_group and left_group == right_group:
                    errors.append(
                        {
                            "type": "runtime_parallel_exclusive_group_conflict",
                            "step_ids": [step.step_id, other.step_id],
                            "exclusive_group": left_group,
                        }
                    )
                overlap = sorted(left_resources.intersection(right_resources))
                if overlap:
                    errors.append(
                        {
                            "type": "runtime_parallel_resource_conflict",
                            "step_ids": [step.step_id, other.step_id],
                            "resources": overlap,
                        }
                    )
        return errors

    @staticmethod
    def _current_auxiliary_target_evidence(
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Project current trusted target semantics without selecting a target."""

        for key in (
            "auxiliary_social_target",
            "social_attention_target",
            "active_user_target",
            "perceived_user_target",
        ):
            value = context.get(key)
            if not isinstance(value, dict) or not value:
                continue
            explicit_source = str(value.get("source") or "").strip()
            source = (
                explicit_source
                if explicit_source in {"live_perception", "conversation_context"}
                else "live_perception"
                if "perception" in key or "perceived" in key
                else "conversation_context"
            )
            raw_target = value.get("target")
            target = dict(raw_target) if isinstance(raw_target, dict) else dict(value)
            return {
                "available": True,
                "source": source,
                "target": {
                    name: target[name]
                    for name in (
                        "target_ref",
                        "relative_direction",
                        "confidence",
                        "evidence_refs",
                    )
                    if name in target
                },
            }
        return {"available": False}

    @staticmethod
    def _attention_target_error(
        attention: AuxiliaryPlanActivity,
        context: dict[str, Any],
    ) -> str | None:
        target = attention.target
        if target.source == "none":
            return None
        evidence = CanonicalPlanRuntimeAdapter._current_auxiliary_target_evidence(
            context
        )
        if not isinstance(evidence, dict) or not evidence.get("available"):
            return "attention_target_not_available"
        if str(evidence.get("source") or "") != target.source:
            return "attention_target_source_mismatch"
        evidence_target = evidence.get("target")
        if not isinstance(evidence_target, dict):
            return "attention_target_not_available"
        expected_ref = str(evidence_target.get("target_ref") or "").strip()
        if expected_ref and expected_ref != target.target_ref:
            return "attention_target_ref_mismatch"
        expected_direction = str(evidence_target.get("relative_direction") or "").strip()
        claimed_direction = str(target.relative_direction or "").strip()
        if expected_direction and claimed_direction and expected_direction != claimed_direction:
            return "attention_target_direction_mismatch"
        return None

    @staticmethod
    def _attention_target_args_error(
        args: dict[str, Any],
        schema: dict[str, Any],
        context: dict[str, Any],
    ) -> str | None:
        semantic_keys = {"direction", "relative_direction", "target_ref"}
        if not semantic_keys.intersection(args):
            return None
        evidence = CanonicalPlanRuntimeAdapter._current_auxiliary_target_evidence(
            context
        )
        if not isinstance(evidence, dict) or not evidence.get("available"):
            return "targeted_behavior_requires_semantic_evidence"
        target = evidence.get("target")
        if not isinstance(target, dict):
            return "targeted_behavior_requires_semantic_evidence"
        expected_direction = str(target.get("relative_direction") or "").strip()
        actual_direction = str(
            args.get("relative_direction") or args.get("direction") or ""
        ).strip()
        if expected_direction and actual_direction and expected_direction != actual_direction:
            return "direction_mismatch"
        expected_ref = str(target.get("target_ref") or "").strip()
        actual_ref = str(args.get("target_ref") or "").strip()
        if expected_ref and actual_ref and expected_ref != actual_ref:
            return "target_ref_mismatch"
        return None

    @staticmethod
    def _attention_conflicts_with_primary(
        social_definition: Any,
        timing: str,
        primary_definitions: dict[str, Any],
    ) -> bool:
        if not primary_definitions:
            return False
        if timing != "parallel" or not social_definition.can_run_parallel:
            return True
        if social_definition.metadata.get("parallel_metadata_declared") is not True:
            return True
        social_group = str(social_definition.exclusive_group or "")
        social_resources = {
            str(item) for item in social_definition.metadata.get("resource_claims", []) if str(item)
        }
        for definition in primary_definitions.values():
            if not definition.can_run_parallel:
                return True
            if definition.metadata.get("parallel_metadata_declared") is not True:
                return True
            primary_group = str(definition.exclusive_group or "")
            if social_group and primary_group and social_group == primary_group:
                return True
            primary_resources = {
                str(item) for item in definition.metadata.get("resource_claims", []) if str(item)
            }
            if social_resources.intersection(primary_resources):
                return True
        return False

    async def prepare_auxiliary_response(
        self,
        *,
        social_cognition: SocialCognitionResolution,
        session_id: str,
        turn_id: str,
        interaction: InteractionResponse | None,
        primary_plan: CanonicalPlan | None = None,
        context: dict[str, Any] | None = None,
        snapshot_is_current: Callable[[], bool] | None = None,
    ) -> InteractionResponse | dict[str, Any]:
        """Validate and execute SC-owned optional social expression.

        Runtime may accept or suppress the exact proposal. It never reselects the
        Capability, target, arguments, social function, or primary anchor. The
        resulting Activity has no Goal-completion or cognition-reentry authority.
        """

        if snapshot_is_current is not None and not snapshot_is_current():
            return {"status": "suppressed", "materialized_count": 0, "reasons": ["stale_social_snapshot"]}
        auxiliary_activities = [
            item for act in social_cognition.activities for item in act.auxiliary_activities
        ]
        primary_steps = list(interaction.capabilities) if interaction is not None else []
        materialized_ids = {str(ref) for speech in (interaction.speech if interaction else [])
                            for ref in speech.metadata.get("communicative_activity_ids", [])}
        communicative_ids = {act.activity_id for act in social_cognition.activities
                             if act.function == "nonverbal" or act.activity_id in materialized_ids}
        step_ids = set()
        has_plan_response = False
        planner_source_id = social_cognition.request_id
        planner_source_metadata = {
            "social_cognition_request_id": social_cognition.request_id,
            "social_cognition_snapshot_digest": social_cognition.snapshot_digest,
            "semantic_owner": "social_cognition",
        }
        auxiliary_source = "social_cognition_auxiliary_activity"
        if not auxiliary_activities:
            return {
                "status": "not_executed",
                "materialized_count": 0,
            }
        if interaction is None:
            return {
                "status": "rejected",
                "materialized_count": 0,
                "reasons": ["primary_interaction_not_materialized"],
            }
        runtime_context = dict(context or {})
        requests: list[CapabilityRequest] = []
        reasons: list[str] = []
        primary_capability_ids = {
            step.capability_id for step in primary_steps
        }
        if primary_plan is not None:
            # Independent SC packets contain no task Work. Consult the committed
            # Plan for containment without copying its steps into this dispatch.
            primary_capability_ids.update(step.capability_id for step in primary_plan.steps)
        primary_definitions: dict[str, Any] = {}
        unresolved_embodied_primary_ids: set[str] = set()
        for capability_id in sorted(primary_capability_ids):
            try:
                await self.interaction_runtime.ensure_capability_definitions([capability_id])
                primary_definition = self.interaction_runtime.capability_definition(capability_id)
            except (TypeError, ValueError, ValidationError, RuntimeError):
                if capability_id.startswith("soridormi."):
                    unresolved_embodied_primary_ids.add(capability_id)
                continue
            primary_metadata = (
                primary_definition.metadata
                if isinstance(primary_definition.metadata, dict)
                else {}
            )
            primary_effects = {
                str(item).strip().lower()
                for item in primary_metadata.get("effects", [])
                if str(item).strip()
            }
            if capability_id.startswith("soridormi.") or primary_effects.intersection(
                {"physical_motion", "visual_expression", "social_expression"}
            ):
                primary_definitions[capability_id] = primary_definition
        seen: set[str] = set()
        for index, behavior in enumerate(auxiliary_activities):
            try:
                anchor_valid = (
                    behavior.anchor_id in step_ids
                    if behavior.anchor_kind == "plan_step"
                    else behavior.anchor_id in communicative_ids
                    if behavior.anchor_kind == "communicative_act"
                    else behavior.anchor_id == "response" and has_plan_response
                )
                if not anchor_valid:
                    reasons.append(
                        f"stale_or_invalid_anchor:{behavior.auxiliary_activity_id}"
                    )
                    continue
                target_error = self._attention_target_error(behavior, runtime_context)
                if target_error:
                    reasons.append(
                        f"target_error:{behavior.capability_id}:{target_error}"
                    )
                    continue
                if unresolved_embodied_primary_ids:
                    reasons.extend(
                        f"primary_definition_unavailable:{capability_id}"
                        for capability_id in sorted(unresolved_embodied_primary_ids)
                    )
                    continue
                await self.interaction_runtime.ensure_capability_definitions([behavior.capability_id])
                definition = self.interaction_runtime.capability_definition(behavior.capability_id)
                metadata = definition.metadata if isinstance(definition.metadata, dict) else {}
                domains = {
                    str(item).strip().lower()
                    for item in metadata.get("behavior_domains", [])
                    if str(item).strip()
                }
                if "social_attention" not in domains:
                    reasons.append(f"not_social_attention:{behavior.capability_id}")
                    continue
                if behavior.capability_id in seen:
                    reasons.append(f"duplicate_auxiliary_capability:{behavior.capability_id}")
                    continue
                if any(
                    item.get("session_id") == session_id
                    and item.get("turn_id") == turn_id
                    and item.get("anchor_id") == behavior.anchor_id
                    and item.get("capability_id") == behavior.capability_id
                    for item in self._recent_auxiliary_behavior_evidence
                ):
                    reasons.append(
                        f"duplicate_auxiliary_dispatch:{behavior.capability_id}"
                    )
                    continue
                if not definition.available:
                    reasons.append(f"unavailable:{behavior.capability_id}")
                    continue
                if definition.requires_confirmation:
                    reasons.append(f"confirmation_required:{behavior.capability_id}")
                    continue
                if behavior.timing != "parallel":
                    reasons.append(f"auxiliary_must_be_parallel:{behavior.capability_id}")
                    continue
                if not definition.can_run_parallel:
                    reasons.append(f"parallel_not_supported:{behavior.capability_id}")
                    continue
                if (
                    behavior.capability_id.startswith("soridormi.")
                    and metadata.get("parallel_metadata_declared") is not True
                ):
                    reasons.append(f"parallel_metadata_missing:{behavior.capability_id}")
                    continue
                if self._attention_conflicts_with_primary(
                    definition,
                    behavior.timing,
                    primary_definitions,
                ):
                    reasons.append(f"resource_conflict:{behavior.capability_id}")
                    continue
                schema_errors = validate_args_for_schema(behavior.args, definition.input_schema)
                if schema_errors:
                    reasons.append(f"invalid_args:{behavior.capability_id}")
                    continue
                target_args_error = self._attention_target_args_error(
                    behavior.args,
                    definition.input_schema,
                    runtime_context,
                )
                if target_args_error:
                    reasons.append(
                        f"target_error:{behavior.capability_id}:{target_args_error}"
                    )
                    continue
                schema_digest = output_schema_sha256(definition.output_schema)
                digest = hashlib.sha256(
                    f"{turn_id}|{planner_source_id}|{behavior.auxiliary_activity_id}|{index}|{behavior.capability_id}".encode("utf-8")
                ).hexdigest()[:20]
                request = CapabilityRequest(
                    request_id=f"aux_{digest}",
                    capability_id=behavior.capability_id,
                    capability_version=definition.version,
                    args=dict(behavior.args),
                    timing="parallel",
                    timeout_ms=definition.timeout_ms,
                    cancellable=definition.interruptible,
                    requires_confirmation=False,
                    idempotency_key=(
                        f"{turn_id}:aux:{planner_source_id}:{behavior.auxiliary_activity_id}"
                    ),
                    committed_output_schema_sha256=schema_digest,
                    committed_completion_evidence_sha256=(
                        claim_qualification_policy_sha256(
                            definition.completion_evidence_policy
                        )
                        if definition.completion_evidence_policy is not None
                        else None
                    ),
                    metadata={
                        "source": auxiliary_source,
                        "auxiliary_plan_activity": True,
                        "behavior_domain": "social_attention",
                        "interaction_role": "auxiliary_expression",
                        "social_function": behavior.social_function,
                        "target": behavior.target.model_dump(
                            mode="json", exclude_none=True
                        ),
                        "reason": behavior.reason_summary,
                        "execution_lane": "activity",
                        "execution_role": "social_decoration",
                        "source_goal_ids": [],
                        "turn_id": turn_id,
                        **planner_source_metadata,
                        "auxiliary_activity_id": behavior.auxiliary_activity_id,
                        "anchor_kind": behavior.anchor_kind,
                        "anchor_id": behavior.anchor_id,
                        "primary_activity_goal_ids": [],
                    },
                )
                requests.append(request)
                seen.add(behavior.capability_id)
            except (TypeError, ValueError, ValidationError, RuntimeError) as exc:
                reasons.append(f"invalid:{behavior.capability_id}:{type(exc).__name__}")

        if snapshot_is_current is not None and not snapshot_is_current():
            return {"status": "suppressed", "materialized_count": 0, "reasons": ["stale_social_snapshot"]}
        if not requests:
            return {
                "status": "rejected" if reasons else "not_executed",
                "materialized_count": 0,
                "reasons": reasons,
            }
        interaction_id = f"aux_{turn_id}_{hashlib.sha256(planner_source_id.encode('utf-8')).hexdigest()[:10]}"
        response_metadata: dict[str, Any] = {
            "source": auxiliary_source + "s",
            "auxiliary_plan_activity": True,
            "turn_id": turn_id,
            "session_id": session_id,
            **planner_source_metadata,
            "source_goal_ids": [],
            "cognitive_reentry_eligible": False,
        }
        envelope = runtime_context.get("user_turn_envelope")
        if isinstance(envelope, dict):
            response_metadata["user_turn_envelope"] = dict(envelope)
        response = InteractionResponse(
            interaction_id=interaction_id,
            status="ok",
            capabilities=requests,
            metadata=response_metadata,
        )
        response.metadata["auxiliary_reasons"] = reasons
        return response

    async def execute_auxiliary_activities(
        self, *, social_cognition: SocialCognitionResolution, session_id: str,
        turn_id: str, interaction: InteractionResponse | None,
        context: dict[str, Any] | None = None,
        snapshot_is_current: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        response = await self.prepare_auxiliary_response(social_cognition=social_cognition,
            session_id=session_id, turn_id=turn_id, interaction=interaction,
            context=context, snapshot_is_current=snapshot_is_current)
        if not isinstance(response, InteractionResponse):
            return response
        requests = response.capabilities
        reasons = response.metadata.get("auxiliary_reasons", [])
        for request in requests:
            self._record_auxiliary_behavior_request(request, session_id=session_id)
        dispatch = await self.interaction_runtime.submit_response(
            response,
            session_id=session_id,
        )
        execution = await self.interaction_runtime.wait_dispatch(dispatch)
        if execution.status != "completed":
            raise RuntimeError(f"social_expression_delivery_failed: status={execution.status}")
        return {
            "status": execution.status,
            "materialized_count": len(requests),
            "request_ids": [item.request_id for item in requests],
            "reasons": reasons,
        }


    async def prepare_social_response(
        self, response: InteractionResponse, *, social_cognition: SocialCognitionResolution,
        session_id: str, turn_id: str, context: dict[str, Any] | None = None,
        snapshot_is_current: Callable[[], bool] | None = None,
        primary_plan: CanonicalPlan | None = None,
    ) -> InteractionResponse:
        """Materialize exact SC anchors before either modality enters Runtime."""
        if response.metadata.get("social_expression_materialized") is True:
            return response
        auxiliary = await self.prepare_auxiliary_response(social_cognition=social_cognition,
            session_id=session_id, turn_id=turn_id, interaction=response,
            context=context, snapshot_is_current=snapshot_is_current, primary_plan=primary_plan)
        response = response.model_copy(deep=True)
        response.metadata["social_expression_materialized"] = True
        response.metadata.update({"session_id": session_id, "turn_id": turn_id})
        if not isinstance(auxiliary, InteractionResponse):
            response.metadata["social_expression_admission"] = auxiliary
            return response
        for request in auxiliary.capabilities:
            anchor = request.metadata.get("anchor_id")
            speeches = [speech for speech in response.speech
                        if anchor in speech.metadata.get("communicative_activity_ids", [])]
            if len(speeches) == 1:
                speech = speeches[0]
                identity = "sc:" + hashlib.sha256(f"{social_cognition.request_id}|{anchor}".encode()).hexdigest()[:24]
                shared = {"coordination_id": identity, "lane_start_policy": "prepared_start"}
                request.metadata.update(shared)
                speech.metadata.update({**shared, "execution_lane": "vocal"})
            self._record_auxiliary_behavior_request(request, session_id=session_id)
        response.capabilities.extend(auxiliary.capabilities)
        return response

    async def build_execution_only_response(
        self,
        *,
        plan: CanonicalPlan,
        session_id: str,
        language: str,
        context: dict[str, Any] | None = None,
    ) -> InteractionResponse:
        """Release validated Work without optional communication as a barrier."""

        fingerprint = canonical_plan_fingerprint(plan)
        planner_response = PlannerResponseProjection(
            projection_id=f"execution_only_{fingerprint[:20]}",
            canonical_plan_id=plan.plan_id,
            canonical_plan_fingerprint=fingerprint,
            canonical_plan=plan,
            response_plan=ResponsePlan(),
            lane_coordination=[],
            confidence=1.0,
            rationale="Work without a required communication need can proceed independently of SC.",
            metadata={
                "authority": "advisory",
                "resolver": "readiness_execution",
                "task_plan_immutable": True,
                "safe_read_speech_optional": True,
            },
        )
        return await self.build_response(
            plan=plan,
            planner_response=planner_response,
            session_id=session_id,
            language=language,
            context=context,
        )

    async def build_social_cognition_response(
        self, *, plan: CanonicalPlan, request: SocialCognitionRequest,
        resolution: SocialCognitionResolution, session_id: str, language: str,
        context: dict[str, Any] | None = None,
    ) -> InteractionResponse:
        """Join exact SC acts to immutable Work; never copy speech into the Plan."""
        resolution.validate_request(request)
        for act in resolution.activities:
            validate_communicative_activity_identity(
                activity_id=act.activity_id, text=act.text,
                interaction_context=(context or request.context).get("interaction_context"),
                repair_of_activity_ids=act.repair_of_activity_ids,
            )
        needs = {need.need_id: need for need in plan.communication_needs}
        responding_goals = {item.goal_id for item in plan.goal_outcomes if item.disposition == "respond"}
        stages = []
        for act in resolution.activities:
            if not act.text.strip():
                continue
            addressed = [needs[key] for key in act.addressed_need_ids]
            kinds = {need.kind for need in addressed}
            completion_goals = sorted({
                goal_id for need in addressed
                if need.kind == "answer" and resolution.need_outcomes[need.need_id] == "covered"
                for goal_id in need.source_goal_ids if goal_id in responding_goals
            })
            confirmation = "confirmation" in kinds
            waiting = confirmation or "input" in kinds
            completion = bool(completion_goals) and not set(act.source_goal_ids).intersection(plan.executable_goal_ids())
            stages.append(ResponseStage(
                text=act.text, delivery_phase=act.delivery_phase,
                speech_act="ask_confirmation" if confirmation else "ask_clarification" if waiting else act.function,
                commitment_state="waiting_for_user" if waiting else "completed" if completion else "none",
                must_not_claim_completion=not (completion and not waiting),
                covers_goal_ids=list(act.source_goal_ids), metadata={
                    "wording_owner": "social_cognition",
                    "communicative_activity_ids": [act.activity_id],
                    "truth_stages": [act.truth_stage],
                    "evidence_refs": list(act.evidence_refs),
                    "addressed_need_ids": list(act.addressed_need_ids),
                    "source_responsibility_refs": list(act.source_responsibility_refs),
                    "communication_completion_goal_ids": completion_goals,
                    "required_before_work": confirmation or any(need.delivery_phase == "pre_action" or need.before_step_ids for need in addressed),
                    "communication_before_step_ids": sorted({key for need in addressed for key in need.before_step_ids}),
                    "communication_after_step_ids": sorted({key for need in addressed for key in need.after_step_ids}),
                },
            ))
        fingerprint = canonical_plan_fingerprint(plan)
        projection = PlannerResponseProjection(
            projection_id=f"sc_{resolution.snapshot_digest[:20]}",
            canonical_plan_id=plan.plan_id, canonical_plan_fingerprint=fingerprint,
            canonical_plan=plan, response_plan=ResponsePlan(activities=stages),
            social_cognition_request=request, social_cognition=resolution,
            metadata={"authority": "social_cognition", "task_plan_immutable": True},
        )
        social_context = _lineage_context(
            dict(context or request.context),
            _social_semantic_lineage(request.semantic_artifact_lineage, resolution),
        )
        response = await self.build_response(
            plan=plan, planner_response=projection, session_id=session_id,
            language=language, context=social_context,
        )
        response.metadata["pending_communication_need_ids"] = [
            key for key, value in resolution.need_outcomes.items() if value == "pending"
        ]
        response.metadata["social_cognition_resolution"] = resolution.model_dump(mode="json")
        if any(act.auxiliary_activities for act in resolution.activities):
            response = await self.prepare_social_response(response, social_cognition=resolution,
                session_id=session_id, turn_id=str(request.source_turn.get("turn_id") or request.request_id),
                context=social_context)
        return response


    async def build_response(
        self,
        *,
        plan: CanonicalPlan,
        planner_response: PlannerResponseProjection,
        session_id: str,
        language: str,
        context: dict[str, Any] | None = None,
    ) -> InteractionResponse:
        async with runtime_tracer.span(
            module=self.TRACE_MODULE,
            operation="build_response",
            attributes={
                "plan_disposition": plan.disposition,
                "step_count": len(plan.steps),
                "speech_stage_count": sum(
                    1
                    for item in (
                        planner_response.response_plan.immediate,
                        planner_response.response_plan.pre_action,
                        planner_response.response_plan.final,
                    )
                    if item is not None
                )
                + len(planner_response.response_plan.progress)
                + len(planner_response.response_plan.activities),
            },
        ) as span:
            response = await self._build_response(
                plan=plan,
                planner_response=planner_response,
                session_id=session_id,
                language=language,
                context=context,
            )
            span.set_attribute("response_status", response.status)
            span.set_attribute("speech_count", len(response.speech))
            span.set_attribute("capability_count", len(response.capabilities))
            if response.status == "error":
                span.set_status("error")
            return response

    async def _build_response(
        self,
        *,
        plan: CanonicalPlan,
        planner_response: PlannerResponseProjection,
        session_id: str,
        language: str,
        context: dict[str, Any] | None = None,
    ) -> InteractionResponse:
        if planner_response.canonical_plan_id != plan.plan_id:
            raise ValueError("planner response projection references a different canonical plan")
        if planner_response.canonical_plan_fingerprint != canonical_plan_fingerprint(plan):
            raise ValueError("planner response projection canonical-plan fingerprint mismatch")
        errors = await self.validation_errors(plan)
        if errors:
            raise ValueError(
                "runtime canonical-plan validation failed: "
                + json.dumps(errors, ensure_ascii=False)
            )

        fingerprint = canonical_plan_fingerprint(plan)
        runtime_context = context if isinstance(context, dict) else {}
        runtime_lineage = _plan_semantic_lineage(
            _semantic_lineage_from_context(runtime_context), plan,
        )
        runtime_context = _lineage_context(runtime_context, runtime_lineage)
        lineage_payload = runtime_lineage.model_dump(mode="json")
        envelope = runtime_context.get("user_turn_envelope")
        turn_id = (
            str(envelope.get("turn_id") or session_id)
            if isinstance(envelope, dict)
            else session_id
        )
        reflex = envelope.get("reflex") if isinstance(envelope, dict) else None
        deterministic_interrupt = bool(
            isinstance(envelope, dict)
            and envelope.get("admission") == "reflex_and_admit"
            and isinstance(reflex, dict)
            and reflex.get("action") == "interrupt"
        )
        speech_prohibited = user_turn_prohibits_speech(envelope)
        residual_effects_permitted = bool(
            deterministic_interrupt
            and reflex.get("cancellation_scope") == "output_only"
            and isinstance(reflex.get("metadata"), dict)
            and reflex["metadata"].get("residual_semantic_input") is True
        )
        alternative = str(plan.metadata.get("plan_relation") or "") in {
            "alternative",
            "safe_adjustment",
        } or bool(plan.metadata.get("user_confirmation_required"))
        executable_goal_ids = set(plan.executable_goal_ids())
        confirmation_goal_ids = set(executable_goal_ids) if alternative else set()
        if not alternative:
            for step in plan.steps:
                definition = self.interaction_runtime.capability_definition(step.capability_id)
                if step.metadata.get("value_withheld"):
                    continue
                if definition.requires_confirmation or step.metadata.get("value_confirmation_required"):
                    confirmation_goal_ids.update(step.source_goal_ids)

        response_plan = planner_response.response_plan
        lane_coordination_by_id = {
            item.coordination_id: item for item in planner_response.lane_coordination
        }
        activity_coordination_by_step_id = {
            step_id: item
            for item in planner_response.lane_coordination
            for step_id in item.activity_step_ids
        }
        vocal_coordination_by_step_id = {
            step_id: item
            for item in planner_response.lane_coordination
            for step_id in item.vocal_step_ids
        }
        plan_steps_by_id = {step.step_id: step for step in plan.steps}
        media_mixer_by_coordination_id: dict[str, dict[str, Any]] = {}
        for coordination in planner_response.lane_coordination:
            if "vocal" not in coordination.lanes:
                continue
            media_step_ids = [
                step_id
                for step_id in coordination.activity_step_ids
                if plan_steps_by_id[step_id].capability_id in MEDIA_CAPABILITY_IDS.values()
            ]
            if not media_step_ids:
                continue
            mixer_contracts: list[dict[str, Any]] = []
            for step_id in media_step_ids:
                definition = self.interaction_runtime.capability_definition(
                    plan_steps_by_id[step_id].capability_id
                )
                if definition.metadata.get("mixer_policy") != ("duck_media_during_vocal"):
                    raise ValueError(
                        "speech-over-media coordination requires the declared "
                        "duck_media_during_vocal mixer policy: " + step_id
                    )
                try:
                    mixer_contracts.append(
                        {
                            "media_mixer_policy": "duck_media_during_vocal",
                            "media_ducking_gain_db": float(definition.metadata["ducking_gain_db"]),
                            "media_duck_attack_ms": int(definition.metadata["duck_attack_ms"]),
                            "media_duck_release_ms": int(definition.metadata["duck_release_ms"]),
                        }
                    )
                except (KeyError, TypeError, ValueError) as exc:
                    raise ValueError(
                        "speech-over-media coordination requires a complete "
                        "ducking gain and timing contract: " + step_id
                    ) from exc
            mixer_contract = mixer_contracts[0]
            if any(item != mixer_contract for item in mixer_contracts[1:]):
                raise ValueError(
                    "speech-over-media coordination requires one unambiguous mixer contract"
                )
            media_mixer_by_coordination_id[coordination.coordination_id] = {
                **mixer_contract,
                "media_ducking_required": True,
                "coordinated_media_step_ids": media_step_ids,
            }
        stage_items = PlannerResponseProjection._stages(response_plan)
        social_response = planner_response.social_cognition is not None
        effectful_pre_execution = plan.disposition in {"execute", "mixed"} and bool(plan.steps)
        executable_definitions = (
            [self.interaction_runtime.capability_definition(step.capability_id) for step in plan.steps]
            if effectful_pre_execution
            else []
        )
        read_only_plan = bool(executable_definitions) and all(
            str((definition.metadata or {}).get("safety_class") or "") == "safe_read"
            for definition in executable_definitions
        )
        safe_read_parallel = (
            effectful_pre_execution and read_only_plan and not confirmation_goal_ids
        )
        safe_read_speech_optional = (
            safe_read_parallel
            and plan.disposition == "execute"
            and executable_goal_ids == set(plan.goal_ids)
        )
        pure_execution_speech_optional = (
            effectful_pre_execution
            and plan.disposition == "execute"
            and executable_goal_ids == set(plan.goal_ids)
            and not confirmation_goal_ids
            and response_plan.immediate is None
            and response_plan.pre_action is None
        )
        reusable_turn_speech: dict[str, dict[str, Any]] = {}
        if isinstance(context, dict):
            # A speech-event identity selects the Communicative Act. Text is
            # checked later only as payload integrity, never as de-duplication
            # identity. Prefer playback-qualified evidence when both projections
            # contain the same event.
            for key in ("scheduled_turn_speech", "delivered_turn_speech"):
                values = context.get(key)
                if not isinstance(values, list):
                    continue
                for item in values:
                    if not isinstance(item, dict):
                        continue
                    event_id = " ".join(
                        str(item.get("event_id") or item.get("speech_event_id") or "")
                        .strip()
                        .split()
                    )
                    status = str(item.get("status") or "").strip()
                    if event_id and status in {
                        "scheduled",
                        "playback_started",
                        "playback_completed",
                    }:
                        reusable_turn_speech[event_id] = dict(item)
        omitted_pre_execution_speech_phases: list[str] = []
        projected_speech_stages: list[dict[str, Any]] = []
        if effectful_pre_execution:
            immediate_item = (
                ("immediate", response_plan.immediate)
                if response_plan.immediate is not None
                else None
            )
            pre_action_item = (
                ("pre_action", response_plan.pre_action)
                if response_plan.pre_action is not None
                else None
            )
            available_pre_execution = [
                item for item in (immediate_item, pre_action_item) if item is not None
            ]
            final_items = (
                [("final", response_plan.final)]
                if response_plan.final is not None
                else []
            )
            covered_pre_execution = {
                goal_id for _, stage in available_pre_execution for goal_id in stage.covers_goal_ids
            }
            required_pre_execution_goal_ids = set(covered_pre_execution)

            # A safe, read-only lookup may start immediately without any spoken
            # acknowledgement. If the response model supplied a tiny natural
            # acknowledgement, it is optional and runs in parallel with the lookup.
            # Effectful or confirmation-gated pre-action speech retains the
            # delivery barrier. A Planner-authored final phase remains after Work
            # and is never forced to claim ownership of executable Goals.
            if safe_read_parallel:
                if pre_action_item is not None and required_pre_execution_goal_ids.issubset(
                    set(pre_action_item[1].covers_goal_ids)
                ):
                    selected_pre_execution = [pre_action_item]
                elif immediate_item is not None and required_pre_execution_goal_ids.issubset(
                    set(immediate_item[1].covers_goal_ids)
                ):
                    selected_pre_execution = [immediate_item]
                else:
                    selected_pre_execution = list(available_pre_execution)
            else:
                if pure_execution_speech_optional:
                    selected_pre_execution = []
                elif pre_action_item is not None and required_pre_execution_goal_ids.issubset(
                    set(pre_action_item[1].covers_goal_ids)
                ):
                    selected_pre_execution = [pre_action_item]
                elif immediate_item is not None and required_pre_execution_goal_ids.issubset(
                    set(immediate_item[1].covers_goal_ids)
                ):
                    selected_pre_execution = [immediate_item]
                else:
                    selected_pre_execution = list(available_pre_execution)

            stage_items = (PlannerResponseProjection._stages(response_plan) if social_response
                           else [*selected_pre_execution, *final_items])

            selected_keys = {(phase, id(stage)) for phase, stage in stage_items}
            omitted_pre_execution_speech_phases = [
                phase
                for phase, stage in (
                    ("immediate", response_plan.immediate),
                    ("pre_action", response_plan.pre_action),
                    *[("progress", item) for item in response_plan.progress],
                    ("final", response_plan.final),
                )
                if stage is not None and (phase, id(stage)) not in selected_keys
            ]

            confirmation_stages = [
                stage
                for _, stage in stage_items
                if stage is not None
                and stage.speech_act.casefold() == "ask_confirmation"
                and stage.commitment_state == "waiting_for_user"
            ]
            confirmation_stage_goal_ids = {
                goal_id for stage in confirmation_stages for goal_id in stage.covers_goal_ids
            }
            if confirmation_goal_ids and not confirmation_goal_ids.issubset(
                confirmation_stage_goal_ids
            ):
                raise ValueError(
                    "confirmation-bound execution requires model-authored "
                    "ask_confirmation speech covering every confirmation goal"
                )
            if (
                not confirmation_goal_ids
                and plan.disposition == "execute"
                and any(
                    stage is not None
                    and (
                        stage.speech_act.casefold() == "ask_confirmation"
                        or stage.commitment_state == "waiting_for_user"
                    )
                    for _, stage in stage_items
                )
            ):
                raise ValueError(
                    "execution response requests confirmation without a runtime "
                    "confirmation requirement"
                )

            if safe_read_parallel:
                projected_speech_stages = [
                    {
                        "phase": phase,
                        "text": stage.text,
                        "speech_act": stage.speech_act,
                        "commitment_state": stage.commitment_state,
                        "must_not_claim_completion": (
                            True if phase != "final" else stage.must_not_claim_completion
                        ),
                        "covers_goal_ids": list(stage.covers_goal_ids),
                        "claims": stage.claims,
                        "source": "planner_communicative_activity",
                        "operational_text_source": "planner_wording_runtime_validated",
                        "runtime_confirmation_required": False,
                        "safe_read_micro_ack": (
                            safe_read_speech_optional and phase != "final"
                        ),
                        "coordination_id": stage.coordination_id,
                        "delivery_role": stage.delivery_role,
                        "reuse_current_turn_speech": (stage.reuse_current_turn_speech),
                        "reused_speech_event_id": stage.reused_speech_event_id,
                        "communicative_activity_ids": list(
                            (stage.metadata or {}).get("communicative_activity_ids") or []
                        ),
                        "truth_stages": list(
                            (stage.metadata or {}).get("truth_stages") or []
                        ),
                    }
                    for phase, stage in stage_items
                    if stage is not None
                ]
            else:
                projected_speech_stages = [
                    {
                        "phase": phase,
                        "text": stage.text,
                        "speech_act": stage.speech_act,
                        "commitment_state": stage.commitment_state,
                        "must_not_claim_completion": (stage.must_not_claim_completion),
                        "covers_goal_ids": list(stage.covers_goal_ids),
                        "claims": list(stage.claims),
                        "source": "planner_communicative_activity",
                        "operational_text_source": ("planner_wording_runtime_validated"),
                        "runtime_confirmation_required": (
                            bool(confirmation_goal_ids) and stage in confirmation_stages
                        ),
                        "coordination_id": stage.coordination_id,
                        "delivery_role": stage.delivery_role,
                        "reuse_current_turn_speech": (stage.reuse_current_turn_speech),
                        "reused_speech_event_id": stage.reused_speech_event_id,
                        "communicative_activity_ids": list(
                            (stage.metadata or {}).get("communicative_activity_ids") or []
                        ),
                        "truth_stages": list(
                            (stage.metadata or {}).get("truth_stages") or []
                        ),
                    }
                    for phase, stage in stage_items
                    if stage is not None
                ]
        else:
            projected_speech_stages = [
                {
                    "phase": phase,
                    "text": stage.text,
                    "speech_act": stage.speech_act,
                    "commitment_state": stage.commitment_state,
                    "must_not_claim_completion": stage.must_not_claim_completion,
                    "covers_goal_ids": stage.covers_goal_ids,
                    "claims": stage.claims,
                    "source": "planner_communicative_activity",
                    "coordination_id": stage.coordination_id,
                    "delivery_role": stage.delivery_role,
                    "reuse_current_turn_speech": (stage.reuse_current_turn_speech),
                    "reused_speech_event_id": stage.reused_speech_event_id,
                    "communicative_activity_ids": list(
                        (stage.metadata or {}).get("communicative_activity_ids") or []
                    ),
                    "truth_stages": list(
                        (stage.metadata or {}).get("truth_stages") or []
                    ),
                }
                for phase, stage in stage_items
                if stage is not None
            ]

        if social_response:
            for projected, (_, stage) in zip(projected_speech_stages, stage_items):
                projected.update({
                    "source": "social_cognition", "wording_owner": "social_cognition",
                    "operational_text_source": "social_cognition_wording_runtime_validated",
                    **{key: stage.metadata[key] for key in (
                        "addressed_need_ids", "source_responsibility_refs", "evidence_refs",
                        "communication_completion_goal_ids", "required_before_work",
                        "communication_before_step_ids", "communication_after_step_ids",
                    )},
                })

        if speech_prohibited:
            projected_speech_stages = []

        speech: list[InteractionSpeech] = []
        for projected in projected_speech_stages:
            phase = str(projected["phase"])
            stage_safe_read_parallel = safe_read_parallel and phase != "final"
            coordination_id = str(projected.get("coordination_id") or "").strip()
            coordination = lane_coordination_by_id.get(coordination_id)
            coordinated_speech = bool(coordination is not None and "vocal" in coordination.lanes)
            playback_barrier = (
                projected.get("reuse_current_turn_speech") is True
                or (
                    (phase != "final" or not effectful_pre_execution)
                    and not stage_safe_read_parallel
                    and not coordinated_speech
                )
            )
            if social_response:
                playback_barrier = projected.get("required_before_work") is True or not effectful_pre_execution
            speech_metadata = {
                "source": projected["source"],
                "session_id": session_id,
                "turn_id": turn_id,
                "phase": phase,
                "speech_act": projected["speech_act"],
                "commitment_state": projected["commitment_state"],
                "must_not_claim_completion": projected["must_not_claim_completion"],
                "covers_goal_ids": projected["covers_goal_ids"],
                "source_goal_ids": projected["covers_goal_ids"],
                "canonical_plan_id": plan.plan_id,
                "canonical_plan_fingerprint": fingerprint,
                "claims": projected["claims"],
                "execution_lane": "vocal",
                "delivery_role": projected.get("delivery_role", "response"),
                "communicative_activity_ids": list(
                    projected.get("communicative_activity_ids") or []
                ),
                "truth_stages": list(projected.get("truth_stages") or []),
                "wait_for_playback_start": playback_barrier,
                "playback_start_required_for_delivery": playback_barrier,
            }
            if social_response:
                speech_metadata.update({key: projected[key] for key in (
                    "wording_owner", "addressed_need_ids", "source_responsibility_refs",
                    "evidence_refs", "communication_completion_goal_ids",
                    "communication_before_step_ids", "communication_after_step_ids",
                )})
            if social_response and (
                projected.get("required_before_work") is True
                or projected.get("communication_before_step_ids")
                or projected.get("communication_after_step_ids")
            ):
                speech_metadata["wait_for_voice_release"] = True
            ordered_context_grounded_after_work = (
                phase == "final"
                and set(speech_metadata["truth_stages"]) == {"context_grounded"}
                and not set(projected.get("covers_goal_ids") or []).intersection(
                    executable_goal_ids
                )
            )
            if ordered_context_grounded_after_work:
                speech_metadata["ordered_context_grounded_after_work"] = True
            if projected.get("reuse_current_turn_speech") is True:
                reused_event_id = " ".join(
                    str(projected.get("reused_speech_event_id") or "").strip().split()
                )
                reused = reusable_turn_speech.get(reused_event_id)
                if reused is None:
                    raise ValueError(
                        "response stage requested current-turn speech reuse but "
                        "no exact scheduled or delivered speech event exists"
                    )
                normalized_text = " ".join(str(projected.get("text") or "").strip().split())
                reused_text = " ".join(str(reused.get("text") or "").strip().split())
                if normalized_text != reused_text:
                    raise ValueError(
                        "response stage text does not match the referenced "
                        "current-turn speech event"
                    )
                reused_goal_ids = {
                    normalized
                    for item in reused.get("source_goal_ids") or []
                    if (normalized := " ".join(str(item or "").strip().split()))
                }
                reassigned_goal_ids = (
                    set(projected.get("covers_goal_ids") or []) - reused_goal_ids
                )
                if reused_goal_ids and reassigned_goal_ids:
                    raise ValueError(
                        "Goal-bound current-turn speech cannot be reassigned to "
                        "unrelated canonical Goals: "
                        + ", ".join(sorted(reassigned_goal_ids))
                    )
                reused_plan_id = " ".join(
                    str(reused.get("canonical_plan_id") or "").strip().split()
                )
                if reused_plan_id and reused_plan_id != plan.plan_id:
                    raise ValueError(
                        "reused current-turn speech references a different "
                        "canonical plan"
                    )
                reused_plan_fingerprint = " ".join(
                    str(reused.get("canonical_plan_fingerprint") or "")
                    .strip()
                    .split()
                )
                if reused_plan_fingerprint and reused_plan_fingerprint != fingerprint:
                    raise ValueError(
                        "reused current-turn speech canonical-plan fingerprint "
                        "mismatch"
                    )
                raw_orders = reused.get("orders")
                if not isinstance(raw_orders, list):
                    raw_orders = []
                speech_metadata.update(
                    {
                        "reuse_current_turn_speech": True,
                        "reused_speech_event_id": reused_event_id,
                        "reused_speech_status": reused.get("status"),
                        "reused_speech_generation": reused.get("generation"),
                        "reused_speech_orders": [
                            int(item) for item in raw_orders if isinstance(item, int)
                        ],
                    }
                )
            if coordinated_speech and coordination is not None:
                speech_metadata.update(
                    {
                        "coordination_id": coordination.coordination_id,
                        "lane_coordination_relation": coordination.relation,
                        "lane_start_policy": coordination.start_policy,
                        "lane_failure_policy": coordination.failure_policy,
                        "parallel_with_activity": "activity" in coordination.lanes,
                        "playback_start_required_for_effects": False,
                    }
                )
                mixer_contract = media_mixer_by_coordination_id.get(coordination.coordination_id)
                if mixer_contract is not None:
                    speech_metadata.update(mixer_contract)
            elif stage_safe_read_parallel:
                speech_metadata.update(
                    {
                        "safe_read_micro_ack": safe_read_speech_optional,
                        "parallel_with_safe_read": True,
                        "playback_start_required_for_effects": False,
                    }
                )
            elif effectful_pre_execution:
                speech_metadata["playback_start_required_for_effects"] = (
                    projected.get("required_before_work") is True if social_response else True
                )
            for key in (
                "operational_text_source",
                "runtime_confirmation_required",
            ):
                if key in projected:
                    speech_metadata[key] = projected[key]
            speech.append(
                InteractionSpeech(
                    text=str(projected["text"]),
                    timing=(
                        "after_capabilities"
                        if phase == "final" and effectful_pre_execution
                        else "parallel"
                        if stage_safe_read_parallel or coordinated_speech or (
                            social_response and effectful_pre_execution and not projected.get("required_before_work")
                        )
                        else "immediate"
                        if phase == "immediate"
                        else "sequential"
                    ),
                    style="brief",
                    metadata=speech_metadata,
                )
            )

        capabilities: list[CapabilityRequest] = []
        for step in plan.steps:
            if deterministic_interrupt and not residual_effects_permitted:
                # The control itself is already applied by the Gateway. Semantic
                # admission exists only to reconcile retained Goal state; it may
                # never materialize replacement work for the interrupting turn.
                continue
            if (step.metadata or {}).get("retained_work_reused") is True:
                # The exact live request remains owned by its original Runtime
                # submission. Planner selected it explicitly and Host validated
                # its identity above, so this canonical revision must not
                # dispatch a duplicate request.
                continue
            definition = self.interaction_runtime.capability_definition(step.capability_id)
            execution_lane = str(definition.metadata.get("execution_lane") or "activity").strip()
            if speech_prohibited and execution_lane == "vocal":
                raise ValueError("protective silence forbids a vocal Capability in this turn")
            if execution_lane not in {"vocal", "activity"}:
                raise ValueError(
                    "canonical plan capability has unsupported execution lane: "
                    f"{step.capability_id}={execution_lane!r}"
                )
            if (
                step.capability_id == VOCAL_PERFORMANCE_CAPABILITY_ID
                and execution_lane != "vocal"
            ):
                raise ValueError(
                    "exact vocal performance capability must remain in the vocal lane"
                )
            if step.capability_id in MEDIA_CAPABILITY_IDS.values() and execution_lane != "activity":
                raise ValueError(
                    "exact media playback capabilities must remain in the activity lane"
                )
            coordination = (
                vocal_coordination_by_step_id.get(step.step_id)
                if execution_lane == "vocal"
                else activity_coordination_by_step_id.get(step.step_id)
            )
            wrong_lane_coordination = (
                activity_coordination_by_step_id.get(step.step_id)
                if execution_lane == "vocal"
                else vocal_coordination_by_step_id.get(step.step_id)
            )
            if wrong_lane_coordination is not None:
                raise ValueError(
                    "lane coordination step membership contradicts trusted "
                    f"capability execution_lane={execution_lane}: {step.step_id}"
                )
            if coordination is not None:
                if not definition.can_run_parallel:
                    raise ValueError("cross-lane capability is not parallel-safe: " + step.capability_id)
                if definition.metadata.get("parallel_metadata_declared") is not True:
                    raise ValueError(
                        "cross-lane capability lacks explicit parallel metadata: " + step.capability_id
                    )
            coordination_metadata = (
                {
                    "coordination_id": coordination.coordination_id,
                    "lane_coordination_relation": coordination.relation,
                    "lane_start_policy": coordination.start_policy,
                    "lane_failure_policy": coordination.failure_policy,
                    "parallel_with_vocal": (
                        execution_lane != "vocal" and "vocal" in coordination.lanes
                    ),
                    "parallel_with_activity": (
                        execution_lane != "activity" and "activity" in coordination.lanes
                    ),
                }
                if coordination is not None
                else {}
            )
            media_mixer_metadata: dict[str, Any] = {}
            if (
                coordination is not None
                and step.capability_id in MEDIA_CAPABILITY_IDS.values()
                and "vocal" in coordination.lanes
            ):
                media_mixer_metadata = dict(
                    media_mixer_by_coordination_id[coordination.coordination_id]
                )
            fast_activity_id = str(
                (step.metadata or {}).get("fast_activity_id") or ""
            ).strip()
            digest = hashlib.sha256(f"{fingerprint}|{step.step_id}".encode("utf-8")).hexdigest()[
                :20
            ]
            request_id = (
                fast_planner_activity_request_id(turn_id, fast_activity_id)
                if fast_activity_id
                else f"cogreq_{digest}"
            )
            capabilities.append(
                CapabilityRequest(
                    request_id=request_id,
                    capability_id=step.capability_id,
                    capability_version=definition.version,
                    args=step.args,
                    timing="parallel" if safe_read_parallel else step.timing,
                    timeout_ms=definition.timeout_ms,
                    cancellable=definition.interruptible,
                    # A value-withheld effect is refused before start, never offered for confirmation.
                    requires_confirmation=not step.metadata.get("value_withheld") and (
                        bool(definition.requires_confirmation) or alternative
                        or bool(step.metadata.get("value_confirmation_required"))),
                    idempotency_key=f"{plan.plan_id}:{step.step_id}:{fingerprint[:16]}",
                    committed_output_schema_sha256=output_schema_sha256(definition.output_schema),
                    committed_completion_evidence_sha256=(
                        claim_qualification_policy_sha256(
                            definition.completion_evidence_policy
                        )
                        if definition.completion_evidence_policy is not None
                        else None
                    ),
                    metadata={
                        **step.metadata,
                        "source": "goal_driven_canonical_plan",
                        "canonical_plan_id": plan.plan_id,
                        "canonical_plan_fingerprint": fingerprint,
                        "planner_tier": plan.planner_tier,
                        "step_id": step.step_id,
                        "source_goal_ids": step.source_goal_ids,
                        "reason_summary": step.reason_summary,
                        "language": language,
                        "effects": list(definition.metadata.get("effects") or []),
                        "safety_class": str(definition.metadata.get("safety_class") or ""),
                        "effectful": str(definition.metadata.get("safety_class") or "")
                        not in {"safe_read", "planning_only"},
                        "retryable_safe_read": safe_read_parallel,
                        "execution_lane": execution_lane,
                        "parallel_with_vocal": (
                            safe_read_parallel
                            or bool(coordination_metadata.get("parallel_with_vocal"))
                        ),
                        **coordination_metadata,
                        **media_mixer_metadata,
                        "canonical_timing": step.timing,
                        "effective_timing": ("parallel" if safe_read_parallel else step.timing),
                        "task_list_revision": int(
                            plan.metadata.get("task_list_revision") or 1
                        ),
                        "runtime_timing_adjustment": (
                            "safe_read_parallel"
                            if safe_read_parallel and step.timing != "parallel"
                            else "none"
                        ),
                        "semantic_artifact_lineage": lineage_payload,
                    },
                )
            )

        status_map = {
            "respond": "ok",
            "execute": "ok",
            "mixed": "ok",
            "clarify": "clarify",
            "unavailable": "refused",
            "refused": "refused",
        }
        primary_effectful_count = sum(
            1 for request in capabilities if request.metadata.get("effectful") is True
        )
        metadata = {
            "source": "goal_driven_cognitive_runtime",
            "cognitive_runtime_apply": True,
            "language": language,
            "canonical_plan": plan.model_dump(mode="json", exclude_none=True),
            "canonical_plan_id": plan.plan_id,
            "canonical_plan_fingerprint": fingerprint,
            "planner_response_projection": planner_response.model_dump(mode="json", exclude_none=True),
            "execution_lanes": {
                "vocal": (
                    "response_delivery_and_provider_work"
                    if any(
                        request.metadata.get("execution_lane") == "vocal" for request in capabilities
                    )
                    else "response_delivery"
                ),
                "activity": (
                    "provider_work"
                    if any(
                        request.metadata.get("execution_lane") == "activity"
                        for request in capabilities
                    )
                    else "idle"
                ),
            },
            "lane_coordination_groups": [
                item.model_dump(mode="json", exclude_none=True)
                for item in planner_response.lane_coordination
            ],
            "planning_result": (
                "composed_plan" if plan.disposition in {"execute", "mixed"} else plan.disposition
            ),
            "capability_decision": plan.disposition,
            "goal_ids": plan.goal_ids,
            "planner_tier": plan.planner_tier,
            "goal_satisfaction": (
                plan.goal_satisfaction.model_dump(mode="json")
                if plan.goal_satisfaction is not None
                else None
            ),
            "omitted_pre_execution_speech_phases": (omitted_pre_execution_speech_phases),
            "operational_speech_authority": (
                "social_cognition_runtime_validated" if social_response else
                "llm_optional_micro_ack"
                if safe_read_speech_optional
                else "planner_selected_silence"
                if pure_execution_speech_optional
                else "llm_parallel_speech"
                if safe_read_parallel
                else "planner_wording_runtime_validated"
                if effectful_pre_execution
                else "not_applicable"
            ),
            "safe_read_parallel_execution": safe_read_parallel,
            "safe_read_speech_optional": safe_read_speech_optional,
            "retained_work_reconciliation_only": (
                plan.metadata.get("retained_work_reconciliation_only") is True
            ),
            "deterministic_interrupt_speech_prohibited": speech_prohibited,
            "deterministic_interrupt_residual_effects_permitted": (
                residual_effects_permitted
            ),
            "semantic_artifact_lineage": lineage_payload,
        }
        if isinstance(runtime_context.get("user_turn_envelope"), dict):
            metadata["user_turn_envelope"] = runtime_context["user_turn_envelope"]
        mind_context = runtime_context.get("mind")
        if isinstance(mind_context, dict) and isinstance(
            mind_context.get("personality_expression"), dict
        ):
            metadata["personality_expression"] = mind_context["personality_expression"]
        if alternative:
            metadata["material_plan_change_requires_confirmation"] = True
        confirmation_prompt = next(
            (
                item.text
                for item in speech
                if item.metadata.get("runtime_confirmation_required") is True
            ),
            "",
        )
        if confirmation_prompt:
            metadata["confirmation_prompt"] = confirmation_prompt
            metadata["confirmation_prompt_source"] = (
                "social_cognition_runtime_validated" if social_response else "planner_wording_runtime_validated"
            )
        response = InteractionResponse(
            interaction_id=f"cognitive_{session_id}_{fingerprint[:20]}",
            status=status_map.get(plan.disposition, "error"),
            speech=speech,
            capabilities=capabilities,
            requires_confirmation=any(item.requires_confirmation for item in capabilities),
            reason=(
                str(plan.metadata.get("reason") or "") or None
                if plan.disposition in {"unavailable", "refused"} else None
            ),
            metadata=metadata,
        )
        return response
