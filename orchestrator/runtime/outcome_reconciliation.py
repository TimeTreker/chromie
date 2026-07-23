from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from typing import Any

from agent.app.capabilities.validator import validate_value_for_schema

from shared.chromie_contracts.execution_outcome import (
    ExecutionEvidence,
    ExecutionEvidenceStatus,
    ExecutionOutcomeBundle,
    GoalExecutionOutcome,
    ModelObservation,
    ProviderPostconditionEvidence,
    aggregate_execution_status,
)
from shared.chromie_contracts.interaction import (
    SkillRequest,
    SkillResult,
    SkillTrace,
)
from shared.chromie_contracts.plan import CanonicalPlan
from shared.chromie_contracts.response_composition import (
    canonical_plan_fingerprint,
)


_PRIMARY_PLAN_SOURCE = "goal_driven_canonical_plan"
_SUPPORTED_SCHEMA_TYPES = frozenset(
    {
        "array",
        "boolean",
        "integer",
        "null",
        "number",
        "object",
        "string",
    }
)
_SENSITIVE_OUTPUT_KEY_TERMS = frozenset(
    {
        "authorization",
        "cookie",
        "credential",
        "passcode",
        "passphrase",
        "passwd",
        "password",
        "secret",
        "token",
    }
)
_SENSITIVE_OUTPUT_KEY_COMPACTS = frozenset(
    {
        "accesskey",
        "apikey",
        "authorizationheader",
        "authheader",
        "privatekey",
        "signingkey",
    }
)
_SENSITIVE_KEY_QUALIFIERS = frozenset(
    {
        "access",
        "api",
        "encryption",
        "private",
        "signing",
    }
)
_CAMEL_CASE_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_OUTPUT_KEY_SEPARATOR = re.compile(r"[^a-z0-9]+")


def _stable_id(prefix: str, *parts: str) -> str:
    payload = "|".join(parts)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]
    return f"{prefix}_{digest}"


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _is_sensitive_output_key(value: Any) -> bool:
    expanded = _CAMEL_CASE_BOUNDARY.sub(" ", str(value).strip())
    parts = tuple(
        part
        for part in _OUTPUT_KEY_SEPARATOR.split(expanded.casefold())
        if part
    )
    if not parts:
        return False
    part_set = set(parts)
    if _SENSITIVE_OUTPUT_KEY_TERMS.intersection(part_set):
        return True
    if "key" in part_set and _SENSITIVE_KEY_QUALIFIERS.intersection(part_set):
        return True
    return "".join(parts) in _SENSITIVE_OUTPUT_KEY_COMPACTS


def _sensitive_output_path(value: Any, *, path: str = "$") -> str | None:
    if isinstance(value, dict):
        for key, item in value.items():
            child_path = f"{path}.{key}"
            if _is_sensitive_output_key(key):
                return child_path
            found = _sensitive_output_path(item, path=child_path)
            if found is not None:
                return found
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            found = _sensitive_output_path(item, path=f"{path}[{index}]")
            if found is not None:
                return found
    return None


def _model_output_schema_error(
    schema: Any,
    *,
    path: str = "$",
) -> str | None:
    """Reject schemas that could pass undeclared provider output to a model."""

    if not isinstance(schema, dict):
        return f"{path} is not an object schema"
    if "$ref" in schema or any(
        key in schema for key in ("allOf", "anyOf", "oneOf")
    ):
        return f"{path} uses unsupported schema indirection or composition"
    schema_type = schema.get("type")
    if isinstance(schema_type, str):
        schema_types = {schema_type}
    elif isinstance(schema_type, list) and schema_type and all(
        isinstance(item, str) for item in schema_type
    ):
        schema_types = set(schema_type)
    elif schema_type is None:
        schema_types = set()
    else:
        return f"{path} has an invalid type declaration"
    unsupported_types = sorted(schema_types - _SUPPORTED_SCHEMA_TYPES)
    if unsupported_types:
        return f"{path} uses unsupported types: {unsupported_types}"
    enum = schema.get("enum")
    if "enum" in schema and (not isinstance(enum, list) or not enum):
        return f"{path} enum must be a non-empty list"
    properties = schema.get("properties")
    if path == "$" and schema_type != "object":
        return "output schema root must have type=object"
    if path != "$" and not schema_types and "enum" not in schema:
        return f"{path} must declare a type or enum"
    if properties is not None and "object" not in schema_types:
        return f"{path} declares properties without type=object"
    if "object" in schema_types:
        if not isinstance(properties, dict) or not properties:
            return f"{path} must declare non-empty properties"
        if schema.get("additionalProperties") is not False:
            return f"{path} must set additionalProperties=false"
        for key, child in properties.items():
            error = _model_output_schema_error(
                child,
                path=f"{path}.properties.{key}",
            )
            if error is not None:
                return error
    if "items" in schema and "array" not in schema_types:
        return f"{path} declares items without type=array"
    if "array" in schema_types:
        items = schema.get("items")
        if not isinstance(items, dict):
            return f"{path} array must declare an item schema"
        return _model_output_schema_error(items, path=f"{path}.items")
    return None


class ExecutionOutcomeReconciler:
    """Join an immutable plan, committed requests, and trusted runtime results.

    This stage performs correlation and terminal-state aggregation only. It
    does not infer semantic success from speech, select a retry, or compose a
    user-facing response.
    """

    def __init__(
        self,
        *,
        max_observation_bytes: int = 8192,
        max_total_observation_bytes: int = 32768,
    ) -> None:
        if max_observation_bytes < 1:
            raise ValueError("max_observation_bytes must be positive")
        if max_total_observation_bytes < 1:
            raise ValueError("max_total_observation_bytes must be positive")
        self.max_observation_bytes = int(max_observation_bytes)
        self.max_total_observation_bytes = int(
            max_total_observation_bytes
        )

    def build(
        self,
        *,
        turn_id: str,
        plan: CanonicalPlan,
        interaction_id: str,
        requests: Iterable[SkillRequest],
        results: Iterable[SkillResult],
        output_schemas: Mapping[str, dict[str, Any]] | None = None,
        committed_auxiliary_result_skills: Mapping[str, str] | None = None,
        traces: Iterable[SkillTrace] = (),
        provider_postconditions: Iterable[
            ProviderPostconditionEvidence
        ] = (),
    ) -> ExecutionOutcomeBundle:
        normalized_turn_id = " ".join(str(turn_id or "").strip().split())
        normalized_interaction_id = " ".join(
            str(interaction_id or "").strip().split()
        )
        if not normalized_turn_id:
            raise ValueError("turn_id is required")
        if not normalized_interaction_id:
            raise ValueError("interaction_id is required")

        fingerprint = canonical_plan_fingerprint(plan)
        outcome_id = _stable_id(
            "outcome",
            normalized_turn_id,
            normalized_interaction_id,
            plan.plan_id,
            fingerprint,
        )
        (
            planned_requests,
            auxiliary_requests,
            ignored_request_count,
        ) = self._planned_requests(
            plan,
            fingerprint=fingerprint,
            requests=list(requests),
        )
        planned_request_ids = {
            request.request_id for request in planned_requests.values()
        }
        results_by_request, ignored_result_count = self._results_by_request(
            list(results),
            planned_request_ids=planned_request_ids,
            auxiliary_requests=auxiliary_requests,
            committed_auxiliary_result_skills=(
                committed_auxiliary_result_skills or {}
            ),
        )
        traces_by_request = self._traces_by_request(
            list(traces),
            planned_request_ids=planned_request_ids,
        )
        # Closure binds schemas to committed request IDs. The skill-ID fallback
        # preserves the lower-level builder API used by direct contract tests.
        schemas = output_schemas or {}

        evidence: list[ExecutionEvidence] = []
        observation_bytes_used = 0
        for step in plan.steps:
            request = planned_requests[step.step_id]
            result = results_by_request.get(request.request_id)
            trace = traces_by_request.get(request.request_id)
            evidence_id = _stable_id(
                "evidence",
                outcome_id,
                step.step_id,
                request.request_id,
            )
            if result is None:
                evidence.append(
                    ExecutionEvidence(
                        evidence_id=evidence_id,
                        request_id=request.request_id,
                        step_id=step.step_id,
                        skill_id=step.skill_id,
                        source_goal_ids=step.source_goal_ids,
                        status="not_run",
                        reason_code="missing_skill_result",
                        message=(
                            "No terminal SkillResult was returned for the "
                            "committed request."
                        ),
                        missing_result=True,
                        metadata={
                            "correlation": "plan_step_and_committed_request",
                        },
                    )
                )
                continue
            if result.skill_id != request.skill_id:
                raise ValueError(
                    "SkillResult skill_id does not match committed request"
                )
            if (
                result.skill_version
                and request.skill_version
                and result.skill_version != request.skill_version
            ):
                raise ValueError(
                    "SkillResult skill_version does not match committed "
                    "request"
                )

            status, normalization_reason = self._result_status(result.status)
            reason_code = result.reason_code or normalization_reason
            observation = self.build_model_observation(
                result.output,
                output_schema=schemas.get(
                    request.request_id,
                    schemas.get(step.skill_id),
                ),
                remaining_total_bytes=max(
                    0,
                    self.max_total_observation_bytes
                    - observation_bytes_used,
                ),
            )
            if observation.status == "available":
                observation_bytes_used += observation.output_size_bytes

            started_at = result.started_at
            finished_at = result.finished_at
            trace_id = result.trace_id
            provider_id = result.provider_id
            if trace is not None:
                if trace.interaction_id != normalized_interaction_id:
                    raise ValueError(
                        "SkillTrace interaction_id does not match outcome "
                        "interaction"
                    )
                if trace.skill_id != step.skill_id:
                    raise ValueError(
                        "SkillTrace skill_id does not match planned step"
                    )
                if trace.status != result.status:
                    raise ValueError(
                        "SkillTrace status does not match SkillResult"
                    )
                if provider_id and provider_id != trace.provider_id:
                    raise ValueError(
                        "SkillTrace provider_id does not match SkillResult"
                    )
                if trace_id and trace_id != trace.trace_id:
                    raise ValueError(
                        "SkillResult trace_id does not match SkillTrace"
                    )
                provider_id = provider_id or trace.provider_id
                trace_id = trace_id or trace.trace_id
                started_at = started_at or trace.started_at
                finished_at = finished_at or trace.finished_at

            evidence.append(
                ExecutionEvidence(
                    evidence_id=evidence_id,
                    request_id=request.request_id,
                    step_id=step.step_id,
                    skill_id=step.skill_id,
                    source_goal_ids=step.source_goal_ids,
                    status=status,
                    reported_status=result.status,
                    provider_id=provider_id,
                    observation=observation,
                    reason_code=reason_code,
                    message=result.message,
                    trace_id=trace_id,
                    started_at=started_at,
                    finished_at=finished_at,
                    missing_result=False,
                    metadata={
                        "correlation": "plan_step_request_and_skill_result",
                    },
                )
            )

        evidence_by_step = {item.step_id: item for item in evidence}
        executable_goal_ids = {
            goal_id
            for step in plan.steps
            for goal_id in step.source_goal_ids
        }
        expected_executable_goal_ids = set(plan.executable_goal_ids())
        if executable_goal_ids != expected_executable_goal_ids:
            raise ValueError(
                "canonical executable goal ownership does not match plan steps"
            )

        goal_outcomes: list[GoalExecutionOutcome] = []
        for goal_id in plan.goal_ids:
            if goal_id not in executable_goal_ids:
                continue
            goal_steps = [
                step
                for step in plan.steps
                if goal_id in step.source_goal_ids
            ]
            goal_evidence = [
                evidence_by_step[step.step_id] for step in goal_steps
            ]
            status = aggregate_execution_status(
                [item.status for item in goal_evidence]
            )
            completed_step_ids = [
                item.step_id
                for item in goal_evidence
                if item.status == "completed"
            ]
            unresolved_step_ids = [
                item.step_id
                for item in goal_evidence
                if item.status != "completed"
            ]
            reason_codes = [
                item.reason_code or item.status
                for item in goal_evidence
                if item.status != "completed"
            ]
            goal_outcomes.append(
                GoalExecutionOutcome(
                    goal_id=goal_id,
                    status=status,
                    step_ids=[step.step_id for step in goal_steps],
                    evidence_ids=[
                        item.evidence_id for item in goal_evidence
                    ],
                    completed_step_ids=completed_step_ids,
                    unresolved_step_ids=unresolved_step_ids,
                    reason_codes=reason_codes,
                    metadata={
                        "source": "deterministic_execution_reconciliation",
                    },
                )
            )

        non_execution_goal_ids = [
            goal_id
            for goal_id in plan.goal_ids
            if goal_id not in executable_goal_ids
        ]
        aggregate_status = aggregate_execution_status(
            [item.status for item in goal_outcomes]
        )
        return ExecutionOutcomeBundle(
            outcome_id=outcome_id,
            turn_id=normalized_turn_id,
            interaction_id=normalized_interaction_id,
            canonical_plan_id=plan.plan_id,
            canonical_plan_fingerprint=fingerprint,
            canonical_goal_ids=plan.goal_ids,
            non_execution_goal_ids=non_execution_goal_ids,
            aggregate_status=aggregate_status,
            evidence=evidence,
            goal_outcomes=goal_outcomes,
            provider_postconditions=list(provider_postconditions),
            metadata={
                "builder": "ExecutionOutcomeReconciler",
                "observation_max_bytes": self.max_observation_bytes,
                "observation_total_max_bytes": (
                    self.max_total_observation_bytes
                ),
                "observation_bytes_exposed": observation_bytes_used,
                "ignored_non_plan_request_count": ignored_request_count,
                "ignored_non_plan_result_count": ignored_result_count,
            },
        )

    def build_model_observation(
        self,
        output: dict[str, Any],
        *,
        output_schema: dict[str, Any] | None,
        remaining_total_bytes: int | None = None,
    ) -> ModelObservation:
        """Return provider output only when it passes every exposure gate."""

        try:
            encoded = _canonical_json_bytes(output)
        except (TypeError, ValueError) as exc:
            fallback = repr(output).encode("utf-8", errors="replace")
            return ModelObservation(
                status="schema_invalid",
                output_sha256=hashlib.sha256(fallback).hexdigest(),
                output_size_bytes=len(fallback),
                validation_errors=[
                    f"output is not JSON serializable: {type(exc).__name__}"
                ],
            )

        digest = hashlib.sha256(encoded).hexdigest()
        size = len(encoded)
        if not isinstance(output_schema, dict) or not output_schema:
            return ModelObservation(
                status="schema_unavailable",
                output_sha256=digest,
                output_size_bytes=size,
                validation_errors=["no trusted output schema is available"],
            )
        schema_error = _model_output_schema_error(output_schema)
        if schema_error is not None:
            return ModelObservation(
                status="schema_unavailable",
                output_sha256=digest,
                output_size_bytes=size,
                validation_errors=[
                    "output schema is not closed for model exposure: "
                    + schema_error
                ],
            )

        validation_errors = validate_value_for_schema(
            output,
            output_schema,
            path="output",
        )
        if validation_errors:
            return ModelObservation(
                status="schema_invalid",
                output_sha256=digest,
                output_size_bytes=size,
                validation_errors=validation_errors[:8],
            )

        sensitive_path = _sensitive_output_path(output)
        if sensitive_path is not None:
            return ModelObservation(
                status="sensitive",
                schema_validated=True,
                output_sha256=digest,
                output_size_bytes=size,
                validation_errors=[
                    f"sensitive output field is not model-visible: {sensitive_path}"
                ],
            )

        total_limit = (
            self.max_total_observation_bytes
            if remaining_total_bytes is None
            else max(0, int(remaining_total_bytes))
        )
        if size > self.max_observation_bytes or size > total_limit:
            return ModelObservation(
                status="too_large",
                schema_validated=True,
                output_sha256=digest,
                output_size_bytes=size,
                validation_errors=[
                    "schema-valid output exceeded the model observation bound"
                ],
            )

        return ModelObservation(
            status="available",
            data=output,
            schema_validated=True,
            output_sha256=digest,
            output_size_bytes=size,
        )

    @staticmethod
    def _planned_requests(
        plan: CanonicalPlan,
        *,
        fingerprint: str,
        requests: list[SkillRequest],
    ) -> tuple[
        dict[str, SkillRequest],
        dict[str, SkillRequest],
        int,
    ]:
        by_step: dict[str, SkillRequest] = {}
        auxiliary_by_request: dict[str, SkillRequest] = {}
        seen_request_ids: set[str] = set()
        ignored = 0
        known_steps = {step.step_id: step for step in plan.steps}
        for request in requests:
            if request.request_id in seen_request_ids:
                raise ValueError(
                    "multiple committed SkillRequest values use one request_id"
                )
            seen_request_ids.add(request.request_id)
            metadata = request.metadata
            source = str(metadata.get("source") or "").strip()
            declared_plan_id = str(
                metadata.get("canonical_plan_id") or ""
            ).strip()
            declared_step_id = str(metadata.get("step_id") or "").strip()
            if metadata.get("auxiliary_social_attention") is True:
                if source != "social_attention_plan":
                    raise ValueError(
                        "auxiliary request has an invalid source"
                    )
                if declared_plan_id != plan.plan_id:
                    raise ValueError(
                        "auxiliary request references a different plan"
                    )
                auxiliary_by_request[request.request_id] = request
                ignored += 1
                continue
            is_plan_request = bool(
                source == _PRIMARY_PLAN_SOURCE
                or declared_plan_id
                or declared_step_id
            )
            if not is_plan_request:
                ignored += 1
                continue
            if source != _PRIMARY_PLAN_SOURCE:
                raise ValueError(
                    "canonical step request has an invalid source"
                )
            if declared_plan_id != plan.plan_id:
                raise ValueError(
                    "canonical step request references a different plan"
                )
            declared_fingerprint = str(
                metadata.get("canonical_plan_fingerprint") or ""
            ).strip()
            if declared_fingerprint != fingerprint:
                raise ValueError(
                    "canonical step request fingerprint is stale or missing"
                )
            step = known_steps.get(declared_step_id)
            if step is None:
                raise ValueError(
                    "canonical step request references an unknown step"
                )
            if request.skill_id != step.skill_id:
                raise ValueError(
                    "canonical step request skill_id does not match plan"
                )
            if request.args != step.args:
                raise ValueError(
                    "canonical step request args do not match plan"
                )
            if request.timing != step.timing:
                raise ValueError(
                    "canonical step request timing does not match plan"
                )
            raw_request_goal_ids = metadata.get("source_goal_ids", [])
            if isinstance(raw_request_goal_ids, str):
                raw_request_goal_ids = [raw_request_goal_ids]
            if not isinstance(raw_request_goal_ids, list):
                raise ValueError(
                    "canonical step request source_goal_ids must be a list"
                )
            request_goal_ids = {
                str(item).strip()
                for item in raw_request_goal_ids
                if str(item).strip()
            }
            if request_goal_ids != set(step.source_goal_ids):
                raise ValueError(
                    "canonical step request source_goal_ids do not match plan"
                )
            if declared_step_id in by_step:
                raise ValueError(
                    "multiple committed requests reference one canonical step"
                )
            by_step[declared_step_id] = request

        missing = [
            step.step_id for step in plan.steps if step.step_id not in by_step
        ]
        if missing:
            raise ValueError(
                "canonical plan steps have no committed SkillRequest: "
                + ",".join(missing)
            )
        return by_step, auxiliary_by_request, ignored

    @staticmethod
    def _results_by_request(
        results: list[SkillResult],
        *,
        planned_request_ids: set[str],
        auxiliary_requests: Mapping[str, SkillRequest],
        committed_auxiliary_result_skills: Mapping[str, str],
    ) -> tuple[dict[str, SkillResult], int]:
        by_request: dict[str, SkillResult] = {}
        ignored_request_ids: set[str] = set()
        auxiliary_result_skills = {
            request_id: request.skill_id
            for request_id, request in auxiliary_requests.items()
        }
        for raw_request_id, raw_skill_id in (
            committed_auxiliary_result_skills.items()
        ):
            request_id = str(raw_request_id or "").strip()
            skill_id = str(raw_skill_id or "").strip()
            if not request_id or not skill_id:
                raise ValueError(
                    "committed auxiliary result binding requires request_id "
                    "and skill_id"
                )
            if (
                request_id in planned_request_ids
                or request_id in auxiliary_result_skills
            ):
                raise ValueError(
                    "committed auxiliary result binding collides with a "
                    "SkillRequest"
                )
            auxiliary_result_skills[request_id] = skill_id
        ignored = 0
        for result in results:
            if result.request_id not in planned_request_ids:
                auxiliary = auxiliary_requests.get(result.request_id)
                expected_skill_id = auxiliary_result_skills.get(
                    result.request_id
                )
                if expected_skill_id is None:
                    raise ValueError(
                        "SkillResult has no committed canonical or auxiliary "
                        f"SkillRequest: {result.request_id}"
                    )
                if result.request_id in ignored_request_ids:
                    raise ValueError(
                        "multiple SkillResult values reference one auxiliary "
                        "request"
                    )
                if result.skill_id != expected_skill_id:
                    raise ValueError(
                        "auxiliary SkillResult skill_id does not match "
                        "committed request"
                    )
                if (
                    auxiliary is not None
                    and result.skill_version
                    and auxiliary.skill_version
                    and result.skill_version != auxiliary.skill_version
                ):
                    raise ValueError(
                        "auxiliary SkillResult skill_version does not match "
                        "committed request"
                    )
                ignored_request_ids.add(result.request_id)
                ignored += 1
                continue
            if result.request_id in by_request:
                raise ValueError(
                    "multiple SkillResult values reference one request"
                )
            by_request[result.request_id] = result
        return by_request, ignored

    @staticmethod
    def _traces_by_request(
        traces: list[SkillTrace],
        *,
        planned_request_ids: set[str],
    ) -> dict[str, SkillTrace]:
        by_request: dict[str, SkillTrace] = {}
        for trace in traces:
            if trace.request_id not in planned_request_ids:
                continue
            if trace.request_id in by_request:
                raise ValueError(
                    "multiple SkillTrace values reference one request"
                )
            by_request[trace.request_id] = trace
        return by_request

    @staticmethod
    def _result_status(
        reported_status: str,
    ) -> tuple[ExecutionEvidenceStatus, str | None]:
        normalized = str(reported_status or "").strip().casefold()
        if normalized in {
            "completed",
            "failed",
            "cancelled",
            "timed_out",
            "refused",
        }:
            return normalized, None  # type: ignore[return-value]
        return "failed", "non_terminal_skill_result"


def build_execution_outcome_bundle(
    *,
    turn_id: str,
    plan: CanonicalPlan,
    interaction_id: str,
    requests: Iterable[SkillRequest],
    results: Iterable[SkillResult],
    output_schemas: Mapping[str, dict[str, Any]] | None = None,
    committed_auxiliary_result_skills: Mapping[str, str] | None = None,
    traces: Iterable[SkillTrace] = (),
    provider_postconditions: Iterable[
        ProviderPostconditionEvidence
    ] = (),
    max_observation_bytes: int = 8192,
    max_total_observation_bytes: int = 32768,
) -> ExecutionOutcomeBundle:
    return ExecutionOutcomeReconciler(
        max_observation_bytes=max_observation_bytes,
        max_total_observation_bytes=max_total_observation_bytes,
    ).build(
        turn_id=turn_id,
        plan=plan,
        interaction_id=interaction_id,
        requests=requests,
        results=results,
        output_schemas=output_schemas,
        committed_auxiliary_result_skills=(
            committed_auxiliary_result_skills
        ),
        traces=traces,
        provider_postconditions=provider_postconditions,
    )
