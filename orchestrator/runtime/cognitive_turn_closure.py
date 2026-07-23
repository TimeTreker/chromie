from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from shared.chromie_contracts.execution_outcome import (
    ExecutionOutcomeBundle,
    ProviderPostconditionEvidence,
)
from shared.chromie_contracts.interaction import (
    InteractionResponse,
    output_schema_sha256,
    validate_output_schema_declaration,
)
from shared.chromie_contracts.plan import CanonicalPlan
from shared.chromie_contracts.response_composition import (
    canonical_plan_fingerprint,
)

from .outcome_reconciliation import ExecutionOutcomeReconciler
from .skill_runtime import SkillRuntimeResult


class CognitiveTurnClosure:
    """Build trusted execution evidence for one effectful cognitive turn.

    This class owns no speech, goal meaning, retry, or recovery policy. It
    validates the immutable plan/request boundary, constructs bounded provider
    observations, and delegates exact status aggregation to the deterministic
    outcome reconciler.
    """

    def __init__(
        self,
        interaction_runtime: Any,
        *,
        reconciler: ExecutionOutcomeReconciler | None = None,
    ) -> None:
        self.interaction_runtime = interaction_runtime
        self.reconciler = reconciler or ExecutionOutcomeReconciler()

    @staticmethod
    def canonical_plan(
        response: InteractionResponse,
    ) -> CanonicalPlan | None:
        metadata = response.metadata
        if metadata.get("cognitive_runtime_apply") is not True:
            return None
        raw_plan = metadata.get("canonical_plan")
        if not isinstance(raw_plan, dict):
            return None
        plan = CanonicalPlan.model_validate(raw_plan)
        if not plan.steps:
            return None
        declared_plan_id = str(
            metadata.get("canonical_plan_id") or ""
        ).strip()
        if declared_plan_id and declared_plan_id != plan.plan_id:
            raise ValueError(
                "cognitive response canonical_plan_id does not match plan"
            )
        declared_fingerprint = str(
            metadata.get("canonical_plan_fingerprint") or ""
        ).strip()
        expected_fingerprint = canonical_plan_fingerprint(plan)
        if (
            declared_fingerprint
            and declared_fingerprint != expected_fingerprint
        ):
            raise ValueError(
                "cognitive response canonical plan fingerprint is stale"
            )
        return plan

    def build(
        self,
        *,
        response: InteractionResponse,
        execution: SkillRuntimeResult,
        session_id: str | None,
        provider_status: dict[str, Any] | None = None,
    ) -> ExecutionOutcomeBundle | None:
        plan = self.canonical_plan(response)
        if plan is None:
            return None
        if execution.interaction_id != response.interaction_id:
            raise ValueError(
                "SkillRuntimeResult interaction_id does not match "
                "InteractionResponse"
            )
        turn_id = self._turn_id(response, session_id=session_id)
        output_schemas, schema_gate_reasons = self._output_schemas(response)
        speech_result_bindings = self._speech_result_bindings(response)
        postconditions = self._provider_postconditions(
            plan,
            provider_status=provider_status,
        )
        bundle = self.reconciler.build(
            turn_id=turn_id,
            plan=plan,
            interaction_id=response.interaction_id,
            requests=response.skills,
            results=execution.results,
            output_schemas=output_schemas,
            committed_auxiliary_result_skills=speech_result_bindings,
            traces=execution.traces,
            provider_postconditions=postconditions,
        )
        return self._record_schema_gate_reasons(
            bundle,
            schema_gate_reasons=schema_gate_reasons,
        )

    @staticmethod
    def _speech_result_bindings(
        response: InteractionResponse,
    ) -> dict[str, str]:
        bindings: dict[str, str] = {}
        for speech in response.speech:
            speech_id = str(speech.id or "").strip()
            if not speech_id:
                raise ValueError(
                    "InteractionSpeech id is required for result correlation"
                )
            if speech_id in bindings:
                raise ValueError(
                    "multiple InteractionSpeech values use one result id"
                )
            bindings[speech_id] = "chromie.speak"
        return bindings

    @staticmethod
    def _turn_id(
        response: InteractionResponse,
        *,
        session_id: str | None,
    ) -> str:
        metadata = response.metadata
        turn_id = str(metadata.get("turn_id") or "").strip()
        envelope = metadata.get("user_turn_envelope")
        if not turn_id and isinstance(envelope, dict):
            turn_id = str(envelope.get("turn_id") or "").strip()
        if not turn_id:
            # Compatibility responses created before UserTurnEnvelope dual
            # emission retain the host session correlation. New cognitive
            # responses always carry the canonical turn_id.
            turn_id = str(session_id or "").strip()
        if not turn_id:
            raise ValueError("effectful cognitive response has no turn_id")
        return turn_id

    def _output_schemas(
        self,
        response: InteractionResponse,
    ) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
        schemas: dict[str, dict[str, Any]] = {}
        reasons: dict[str, str] = {}
        for request in response.skills:
            if request.metadata.get("source") != "goal_driven_canonical_plan":
                continue
            committed_digest = request.committed_output_schema_sha256
            if committed_digest is None:
                schemas[request.request_id] = {}
                reasons[request.request_id] = (
                    "committed_output_schema_digest_missing"
                )
                continue
            try:
                definition = self.interaction_runtime.skill_definition(
                    request.skill_id
                )
            except Exception:
                schemas[request.request_id] = {}
                reasons[request.request_id] = (
                    "current_skill_definition_unavailable"
                )
                continue
            schema = getattr(definition, "output_schema", None)
            try:
                validate_output_schema_declaration(schema)
                current_digest = output_schema_sha256(schema)
            except (TypeError, ValueError):
                schemas[request.request_id] = {}
                reasons[request.request_id] = (
                    "current_output_schema_invalid"
                )
                continue
            if current_digest != committed_digest:
                schemas[request.request_id] = {}
                reasons[request.request_id] = (
                    "committed_output_schema_digest_mismatch"
                )
                continue
            schemas[request.request_id] = dict(schema)
        return schemas, reasons

    @staticmethod
    def _record_schema_gate_reasons(
        bundle: ExecutionOutcomeBundle,
        *,
        schema_gate_reasons: dict[str, str],
    ) -> ExecutionOutcomeBundle:
        if not schema_gate_reasons:
            return bundle
        raw = bundle.model_dump(mode="json")
        for evidence in raw["evidence"]:
            reason = schema_gate_reasons.get(evidence["request_id"])
            observation = evidence.get("observation")
            if (
                reason is None
                or not isinstance(observation, dict)
                or observation.get("status") != "schema_unavailable"
            ):
                continue
            bounded_reason = reason[:160]
            observation["validation_errors"] = [bounded_reason]
            evidence["metadata"] = {
                **evidence.get("metadata", {}),
                "output_schema_gate_reason": bounded_reason,
            }
        return ExecutionOutcomeBundle.model_validate(raw)

    def _provider_postconditions(
        self,
        plan: CanonicalPlan,
        *,
        provider_status: dict[str, Any] | None,
    ) -> list[ProviderPostconditionEvidence]:
        if not isinstance(provider_status, dict) or not provider_status:
            return []
        body_goal_set = {
            goal_id
            for step in plan.steps
            if step.skill_id.startswith("soridormi.")
            for goal_id in step.source_goal_ids
        }
        body_goal_ids = [
            goal_id for goal_id in plan.goal_ids if goal_id in body_goal_set
        ]
        if not body_goal_ids:
            return []
        projection: dict[str, Any] = {}
        properties: dict[str, dict[str, str]] = {}
        for key in ("mode", "backend"):
            value = provider_status.get(key)
            if isinstance(value, str):
                projection[key] = value
                properties[key] = {"type": "string"}
        for key in ("safe_idle", "emergency_stop", "fallen"):
            value = provider_status.get(key)
            if isinstance(value, bool):
                projection[key] = value
                properties[key] = {"type": "boolean"}
        projection["active_task_present"] = (
            provider_status.get("active_task") is not None
        )
        properties["active_task_present"] = {"type": "boolean"}
        schema = {
            "type": "object",
            "properties": properties,
            "required": sorted(projection),
            "additionalProperties": False,
        }
        observation = self.reconciler.build_model_observation(
            projection,
            output_schema=schema,
        )
        canonical = json.dumps(
            projection,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        evidence_id = "postcondition_" + hashlib.sha256(
            (
                f"{plan.plan_id}|{canonical_plan_fingerprint(plan)}|"
                f"{canonical}"
            ).encode("utf-8")
        ).hexdigest()[:20]
        return [
            ProviderPostconditionEvidence(
                evidence_id=evidence_id,
                provider_id="soridormi.mcp",
                condition="post_execution_robot_status",
                observation=observation,
                source_goal_ids=body_goal_ids,
                observed_at=datetime.now(timezone.utc),
                metadata={
                    "supports_goal_completion": False,
                    "supports_safety_claims_only_when_explicit": True,
                },
            )
        ]


__all__ = ["CognitiveTurnClosure"]
