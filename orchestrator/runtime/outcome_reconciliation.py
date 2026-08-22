from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from typing import Any

from agent.app.capabilities.validator import validate_value_for_schema

from shared.chromie_contracts.execution_outcome import (
    ClaimCoverageStatus,
    ClaimQualification,
    ClaimQualificationPolicy,
    EvidenceRequirement,
    ExecutionEvidence,
    ExecutionEvidenceStatus,
    ExecutionOutcomeBundle,
    GoalExecutionOutcome,
    ModelObservation,
    goal_completion_qualification_summary,
    ProviderPostconditionEvidence,
    aggregate_execution_status,
    claim_qualification_policy_sha256,
)
from shared.chromie_contracts.interaction import (
    CapabilityRequest,
    CapabilityResult,
    CapabilityTrace,
    output_schema_declaration_error,
)
from shared.chromie_contracts.plan import CanonicalPlan
from shared.chromie_contracts.plan import canonical_plan_fingerprint


_PRIMARY_PLAN_SOURCE = "goal_driven_canonical_plan"
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


def _provider_retryability_truth(result: CapabilityResult) -> dict[str, Any]:
    """Return bounded provider-declared recovery facts without interpreting them.

    Providers may mark a failed operation recoverable/retryable or classify the
    failure. Those declarations are execution facts useful to Planner re-entry;
    they are not Host authorization, a retry recommendation, or user-facing text.
    """

    output = result.output if isinstance(result.output, dict) else {}
    recovery = output.get("recovery")
    recovery = recovery if isinstance(recovery, dict) else {}
    truth: dict[str, Any] = {}
    for key in ("recoverable", "retryable"):
        value = output.get(key)
        if not isinstance(value, bool):
            value = recovery.get(key)
        if isinstance(value, bool):
            truth[key] = value
    failure_class = (
        output.get("failure_class")
        or output.get("failure_type")
        or recovery.get("failure_class")
        or recovery.get("failure_type")
    )
    if isinstance(failure_class, str):
        normalized = " ".join(failure_class.strip().split())[:160]
        if normalized:
            truth["failure_class"] = normalized
    return truth


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
        requests: Iterable[CapabilityRequest],
        results: Iterable[CapabilityResult],
        output_schemas: Mapping[str, dict[str, Any]] | None = None,
        completion_evidence_policies: Mapping[
            str, ClaimQualificationPolicy
        ] | None = None,
        completion_evidence_gate_reasons: Mapping[str, str] | None = None,
        committed_auxiliary_result_capabilities: Mapping[str, str] | None = None,
        traces: Iterable[CapabilityTrace] = (),
        provider_postconditions: Iterable[
            ProviderPostconditionEvidence
        ] = (),
    ) -> ExecutionOutcomeBundle:
        (
            normalized_turn_id,
            normalized_interaction_id,
            fingerprint,
            outcome_id,
        ) = self._outcome_identity(
            turn_id=turn_id,
            interaction_id=interaction_id,
            plan=plan,
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
            committed_auxiliary_result_capabilities=(
                committed_auxiliary_result_capabilities or {}
            ),
        )
        traces_by_request = self._traces_by_request(
            list(traces),
            planned_request_ids=planned_request_ids,
        )
        # Closure binds schemas and claim-sufficiency policy to committed request
        # IDs. The capability-ID schema fallback preserves the lower-level builder API
        # used by direct contract tests; qualification policy never falls back by
        # capability ID because the exact committed request owns that boundary.
        schemas = output_schemas or {}
        qualification_policies = completion_evidence_policies or {}
        qualification_gate_reasons = completion_evidence_gate_reasons or {}
        postconditions = list(provider_postconditions)
        evaluated_at = datetime.now(timezone.utc)

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
                policy = qualification_policies.get(request.request_id)
                qualification = (
                    self.qualify_completion_claim(
                        policy=policy,
                        evidence_id=evidence_id,
                        execution_status="not_run",
                        execution_observation=None,
                        execution_output=None,
                        execution_trust_domain="",
                        execution_finished_at=None,
                        source_goal_ids=step.source_goal_ids,
                        provider_postconditions=postconditions,
                        evaluated_at=evaluated_at,
                        missing_result=True,
                    )
                    if policy is not None
                    else None
                )
                gate_reason = qualification_gate_reasons.get(request.request_id, "")
                evidence.append(
                    ExecutionEvidence(
                        evidence_id=evidence_id,
                        request_id=request.request_id,
                        step_id=step.step_id,
                        capability_id=step.capability_id,
                        source_goal_ids=step.source_goal_ids,
                        status="not_run",
                        completion_qualification=qualification,
                        reason_code="missing_capability_result",
                        message=(
                            "No terminal CapabilityResult was returned for the "
                            "committed request."
                        ),
                        missing_result=True,
                        metadata={
                            "correlation": "plan_step_and_committed_request",
                            "request_args": dict(request.args),
                            "safety_class": str(
                                request.metadata.get("safety_class") or ""
                            ),
                            "effects": list(request.metadata.get("effects") or []),
                            "execution_lane": str(
                                request.metadata.get("execution_lane") or "activity"
                            ),
                            "retryable_safe_read": (
                                request.metadata.get("retryable_safe_read") is True
                            ),
                            "completion_qualification_required": bool(
                                policy is not None or gate_reason
                            ),
                            "completion_evidence_gate_reason": gate_reason,
                        },
                    )
                )
                continue
            result_evidence, observation_bytes = self._build_result_evidence(
                normalized_interaction_id=normalized_interaction_id,
                outcome_id=outcome_id,
                step=step,
                request=request,
                result=result,
                trace=trace,
                output_schema=schemas.get(
                    request.request_id,
                    schemas.get(step.capability_id),
                ),
                qualification_policy=qualification_policies.get(
                    request.request_id
                ),
                qualification_gate_reason=qualification_gate_reasons.get(
                    request.request_id, ""
                ),
                provider_postconditions=postconditions,
                evaluated_at=evaluated_at,
                remaining_total_bytes=max(
                    0,
                    self.max_total_observation_bytes - observation_bytes_used,
                ),
            )
            observation_bytes_used += observation_bytes
            evidence.append(result_evidence)

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
            provider_postconditions=postconditions,
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

    @staticmethod
    def _observation_value(data: dict[str, Any], path: str) -> tuple[bool, Any]:
        current: Any = data
        for part in path.split("."):
            if not isinstance(current, dict) or part not in current:
                return False, None
            current = current[part]
        return True, current

    @classmethod
    def _assertion_status(
        cls,
        data: dict[str, Any],
        requirement: EvidenceRequirement,
    ) -> tuple[str, list[str]]:
        reasons: list[str] = []
        for path, expected in requirement.field_assertions.items():
            found, actual = cls._observation_value(data, path)
            if not found:
                reasons.append(f"required_field_missing:{path}")
                continue
            if actual != expected:
                return "contradicted", [f"field_assertion_mismatch:{path}"]
        return ("insufficient", reasons) if reasons else ("established", [])

    @staticmethod
    def _freshness_status(
        *,
        observed_at: datetime | None,
        max_age_ms: int | None,
        evaluated_at: datetime,
    ) -> tuple[str, list[str]]:
        if max_age_ms is None:
            return "established", []
        if observed_at is None:
            return "unknown", ["observation_time_unknown"]
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            return "unknown", ["observation_time_unqualified"]
        age_ms = max(0.0, (evaluated_at - observed_at).total_seconds() * 1000.0)
        if age_ms > max_age_ms:
            return "stale", ["observation_stale"]
        return "established", []

    @classmethod
    def _evaluate_requirement(
        cls,
        requirement: EvidenceRequirement,
        *,
        evidence_id: str,
        execution_observation: ModelObservation | None,
        execution_output: dict[str, Any] | None,
        execution_trust_domain: str,
        execution_finished_at: datetime | None,
        source_goal_ids: list[str],
        provider_postconditions: list[ProviderPostconditionEvidence],
        evaluated_at: datetime,
    ) -> tuple[str, str | None, str, list[str]]:
        if requirement.source == "execution_observation":
            observation = execution_observation
            if observation is None:
                return "unknown", None, "", ["execution_observation_missing"]
            if not observation.schema_validated:
                return (
                    "insufficient",
                    evidence_id,
                    execution_trust_domain,
                    [f"execution_observation_{observation.status}"],
                )
            if (
                requirement.trust_domain
                and execution_trust_domain != requirement.trust_domain
            ):
                return (
                    "insufficient",
                    evidence_id,
                    execution_trust_domain,
                    ["execution_trust_domain_mismatch"],
                )
            freshness, freshness_reasons = cls._freshness_status(
                observed_at=execution_finished_at,
                max_age_ms=requirement.max_age_ms,
                evaluated_at=evaluated_at,
            )
            if freshness != "established":
                return (
                    freshness,
                    evidence_id,
                    execution_trust_domain,
                    freshness_reasons,
                )
            assertion_status, assertion_reasons = cls._assertion_status(
                execution_output or {},
                requirement,
            )
            return (
                assertion_status,
                evidence_id,
                execution_trust_domain,
                assertion_reasons,
            )

        goal_set = set(source_goal_ids)
        candidates = [
            item
            for item in provider_postconditions
            if item.condition == requirement.condition
            and (
                not item.source_goal_ids
                or bool(goal_set.intersection(item.source_goal_ids))
            )
        ]
        if not candidates:
            return (
                "insufficient",
                None,
                "",
                [f"provider_postcondition_missing:{requirement.condition}"],
            )

        candidate_statuses: list[str] = []
        candidate_reasons: list[str] = []
        for item in candidates:
            trust_domain = item.trust_domain or item.provider_id
            if requirement.trust_domain and trust_domain != requirement.trust_domain:
                candidate_statuses.append("insufficient")
                candidate_reasons.append("postcondition_trust_domain_mismatch")
                continue
            if not item.observation.schema_validated:
                candidate_statuses.append("insufficient")
                candidate_reasons.append(
                    f"postcondition_observation_{item.observation.status}"
                )
                continue
            freshness, freshness_reasons = cls._freshness_status(
                observed_at=item.observed_at,
                max_age_ms=requirement.max_age_ms,
                evaluated_at=evaluated_at,
            )
            if freshness != "established":
                candidate_statuses.append(freshness)
                candidate_reasons.extend(freshness_reasons)
                continue
            assertion_status, assertion_reasons = cls._assertion_status(
                item.observation.data,
                requirement,
            )
            if assertion_status == "established":
                return "established", item.evidence_id, trust_domain, []
            candidate_statuses.append(assertion_status)
            candidate_reasons.extend(assertion_reasons)

        if candidate_statuses and all(
            status == "contradicted" for status in candidate_statuses
        ):
            return "contradicted", None, "", list(dict.fromkeys(candidate_reasons))
        if "stale" in candidate_statuses:
            return "stale", None, "", list(dict.fromkeys(candidate_reasons))
        if "insufficient" in candidate_statuses:
            return "insufficient", None, "", list(dict.fromkeys(candidate_reasons))
        return "unknown", None, "", list(dict.fromkeys(candidate_reasons))

    @classmethod
    def qualify_completion_claim(
        cls,
        *,
        policy: ClaimQualificationPolicy,
        evidence_id: str,
        execution_status: ExecutionEvidenceStatus,
        execution_observation: ModelObservation | None,
        execution_output: dict[str, Any] | None,
        execution_trust_domain: str,
        execution_finished_at: datetime | None,
        source_goal_ids: list[str],
        provider_postconditions: list[ProviderPostconditionEvidence],
        evaluated_at: datetime,
        missing_result: bool,
        coverage: ClaimCoverageStatus = "not_required",
    ) -> ClaimQualification:
        digest = claim_qualification_policy_sha256(policy)
        if policy.requires_complete_coverage and coverage != "complete":
            return ClaimQualification(
                claim=policy.claim,
                status=("unknown" if coverage == "unknown" else "insufficient"),
                policy_sha256=digest,
                reason_codes=["closed_world_coverage_not_complete"],
                coverage=coverage,
                evaluated_at=evaluated_at,
            )
        if missing_result:
            return ClaimQualification(
                claim=policy.claim,
                status="unknown",
                policy_sha256=digest,
                reason_codes=["execution_result_missing"],
                coverage=coverage,
                evaluated_at=evaluated_at,
            )
        if execution_status != "completed":
            return ClaimQualification(
                claim=policy.claim,
                status="contradicted",
                policy_sha256=digest,
                evidence_ids=[evidence_id],
                reason_codes=[f"execution_status_{execution_status}"],
                trust_domains=(
                    [execution_trust_domain] if execution_trust_domain else []
                ),
                coverage=coverage,
                evaluated_at=evaluated_at,
            )

        group_statuses: list[str] = []
        group_reasons: list[str] = []
        for group_index, group in enumerate(policy.requirement_groups):
            evidence_ids: list[str] = []
            trust_domains: list[str] = []
            requirement_statuses: list[str] = []
            reasons: list[str] = []
            for requirement in group.requirements:
                status, matched_id, trust_domain, requirement_reasons = (
                    cls._evaluate_requirement(
                        requirement,
                        evidence_id=evidence_id,
                        execution_observation=execution_observation,
                        execution_output=execution_output,
                        execution_trust_domain=execution_trust_domain,
                        execution_finished_at=execution_finished_at,
                        source_goal_ids=source_goal_ids,
                        provider_postconditions=provider_postconditions,
                        evaluated_at=evaluated_at,
                    )
                )
                requirement_statuses.append(status)
                reasons.extend(requirement_reasons)
                if matched_id:
                    evidence_ids.append(matched_id)
                if trust_domain:
                    trust_domains.append(trust_domain)
            unique_domains = list(dict.fromkeys(trust_domains))
            if all(status == "established" for status in requirement_statuses):
                if len(unique_domains) < group.minimum_independent_trust_domains:
                    group_statuses.append("insufficient")
                    group_reasons.append("independent_trust_domains_insufficient")
                    continue
                return ClaimQualification(
                    claim=policy.claim,
                    status="established",
                    policy_sha256=digest,
                    evidence_ids=list(dict.fromkeys(evidence_ids)),
                    trust_domains=unique_domains,
                    coverage=coverage,
                    satisfied_group_index=group_index,
                    evaluated_at=evaluated_at,
                )
            if (
                "contradicted" in requirement_statuses
                and all(
                    status in {"established", "contradicted"}
                    for status in requirement_statuses
                )
            ):
                group_statuses.append("contradicted")
            elif "stale" in requirement_statuses:
                group_statuses.append("stale")
            elif "insufficient" in requirement_statuses:
                group_statuses.append("insufficient")
            else:
                group_statuses.append("unknown")
            group_reasons.extend(reasons)

        if group_statuses and all(status == "contradicted" for status in group_statuses):
            status = "contradicted"
        elif "stale" in group_statuses:
            status = "stale"
        elif "insufficient" in group_statuses:
            status = "insufficient"
        else:
            status = "unknown"
        return ClaimQualification(
            claim=policy.claim,
            status=status,
            policy_sha256=digest,
            evidence_ids=[evidence_id],
            reason_codes=list(dict.fromkeys(group_reasons))[:16],
            trust_domains=(
                [execution_trust_domain] if execution_trust_domain else []
            ),
            coverage=coverage,
            evaluated_at=evaluated_at,
        )

    @staticmethod
    def _outcome_identity(
        *,
        turn_id: str,
        interaction_id: str,
        plan: CanonicalPlan,
    ) -> tuple[str, str, str, str]:
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
        return (
            normalized_turn_id,
            normalized_interaction_id,
            fingerprint,
            outcome_id,
        )

    def reconcile_terminal_result(
        self,
        *,
        turn_id: str,
        plan: CanonicalPlan,
        interaction_id: str,
        requests: Iterable[CapabilityRequest],
        result: CapabilityResult,
        output_schemas: Mapping[str, dict[str, Any]] | None = None,
        completion_evidence_policies: Mapping[
            str, ClaimQualificationPolicy
        ] | None = None,
        completion_evidence_gate_reasons: Mapping[str, str] | None = None,
        traces: Iterable[CapabilityTrace] = (),
        provider_postconditions: Iterable[
            ProviderPostconditionEvidence
        ] = (),
    ) -> ExecutionEvidence:
        """Reconcile one exact terminal result without closing sibling requests.

        This is the incremental Evidence boundary for asynchronous Runtime
        lifecycle. It validates the complete committed request set against the
        immutable plan, then emits Evidence only for ``result.request_id``. A
        sibling with no terminal result is deliberately absent rather than
        represented as ``not_run`` or ``missing_result``. The resulting
        ``evidence_id`` is the same stable identity used by final aggregate
        :meth:`build` reconciliation.
        """

        if result.status not in {
            "completed",
            "failed",
            "refused",
            "cancelled",
            "timed_out",
        }:
            raise ValueError(
                "incremental execution evidence requires a terminal CapabilityResult"
            )
        (
            _normalized_turn_id,
            normalized_interaction_id,
            fingerprint,
            outcome_id,
        ) = self._outcome_identity(
            turn_id=turn_id,
            interaction_id=interaction_id,
            plan=plan,
        )
        planned_requests, _auxiliary_requests, _ignored = self._planned_requests(
            plan,
            fingerprint=fingerprint,
            requests=list(requests),
        )
        step_by_request_id = {
            request.request_id: step_id
            for step_id, request in planned_requests.items()
        }
        step_id = step_by_request_id.get(result.request_id)
        if step_id is None:
            raise ValueError(
                "terminal CapabilityResult does not reference a committed canonical plan request"
            )
        request = planned_requests[step_id]
        step = next(item for item in plan.steps if item.step_id == step_id)
        traces_by_request = self._traces_by_request(
            list(traces),
            planned_request_ids={item.request_id for item in planned_requests.values()},
        )
        schemas = output_schemas or {}
        policies = completion_evidence_policies or {}
        gate_reasons = completion_evidence_gate_reasons or {}
        evidence, _observation_bytes = self._build_result_evidence(
            normalized_interaction_id=normalized_interaction_id,
            outcome_id=outcome_id,
            step=step,
            request=request,
            result=result,
            trace=traces_by_request.get(result.request_id),
            output_schema=schemas.get(
                request.request_id,
                schemas.get(step.capability_id),
            ),
            qualification_policy=policies.get(request.request_id),
            qualification_gate_reason=gate_reasons.get(request.request_id, ""),
            provider_postconditions=list(provider_postconditions),
            evaluated_at=datetime.now(timezone.utc),
            remaining_total_bytes=self.max_total_observation_bytes,
        )
        return evidence

    def _build_result_evidence(
        self,
        *,
        normalized_interaction_id: str,
        outcome_id: str,
        step: Any,
        request: CapabilityRequest,
        result: CapabilityResult,
        trace: CapabilityTrace | None,
        output_schema: dict[str, Any] | None,
        qualification_policy: ClaimQualificationPolicy | None,
        qualification_gate_reason: str,
        provider_postconditions: list[ProviderPostconditionEvidence],
        evaluated_at: datetime,
        remaining_total_bytes: int,
    ) -> tuple[ExecutionEvidence, int]:
        if result.request_id != request.request_id:
            raise ValueError(
                "CapabilityResult request_id does not match committed request"
            )
        if result.capability_id != request.capability_id:
            raise ValueError(
                "CapabilityResult capability_id does not match committed request"
            )
        if (
            result.capability_version
            and request.capability_version
            and result.capability_version != request.capability_version
        ):
            raise ValueError(
                "CapabilityResult capability_version does not match committed request"
            )

        evidence_id = _stable_id(
            "evidence",
            outcome_id,
            step.step_id,
            request.request_id,
        )
        status, normalization_reason = self._result_status(result.status)
        reason_code = result.reason_code or normalization_reason
        observation = self.build_model_observation(
            result.output,
            output_schema=output_schema,
            remaining_total_bytes=remaining_total_bytes,
        )
        observation_bytes = (
            observation.output_size_bytes if observation.status == "available" else 0
        )
        if (
            status == "completed"
            and isinstance(output_schema, dict)
            and bool(output_schema)
            and observation.status in {"schema_unavailable", "schema_invalid"}
        ):
            status = "failed"
            reason_code = "completion_observation_not_trusted"

        started_at = result.started_at
        finished_at = result.finished_at
        trace_id = result.trace_id
        provider_id = result.provider_id
        if trace is not None:
            if trace.interaction_id != normalized_interaction_id:
                raise ValueError(
                    "CapabilityTrace interaction_id does not match outcome interaction"
                )
            if trace.capability_id != step.capability_id:
                raise ValueError(
                    "CapabilityTrace capability_id does not match planned step"
                )
            if trace.status != result.status:
                raise ValueError(
                    "CapabilityTrace status does not match CapabilityResult"
                )
            if provider_id and provider_id != trace.provider_id:
                raise ValueError(
                    "CapabilityTrace provider_id does not match CapabilityResult"
                )
            if trace_id and trace_id != trace.trace_id:
                raise ValueError(
                    "CapabilityResult trace_id does not match CapabilityTrace"
                )
            provider_id = provider_id or trace.provider_id
            trace_id = trace_id or trace.trace_id
            started_at = started_at or trace.started_at
            finished_at = finished_at or trace.finished_at

        trust_domain = " ".join(
            str(
                result.metadata.get("evidence_trust_domain")
                or provider_id
                or ""
            ).strip().split()
        )
        qualification = (
            self.qualify_completion_claim(
                policy=qualification_policy,
                evidence_id=evidence_id,
                execution_status=status,
                execution_observation=observation,
                execution_output=result.output,
                execution_trust_domain=trust_domain,
                execution_finished_at=finished_at,
                source_goal_ids=step.source_goal_ids,
                provider_postconditions=provider_postconditions,
                evaluated_at=evaluated_at,
                missing_result=False,
            )
            if qualification_policy is not None
            else None
        )

        return (
            ExecutionEvidence(
                evidence_id=evidence_id,
                request_id=request.request_id,
                step_id=step.step_id,
                capability_id=step.capability_id,
                source_goal_ids=step.source_goal_ids,
                status=status,
                reported_status=result.status,
                provider_id=provider_id,
                trust_domain=trust_domain,
                observation=observation,
                completion_qualification=qualification,
                reason_code=reason_code,
                message=result.message,
                trace_id=trace_id,
                started_at=started_at,
                finished_at=finished_at,
                missing_result=False,
                metadata={
                    "correlation": "plan_step_request_and_capability_result",
                    "request_args": dict(request.args),
                    "provider_execution": dict(result.metadata),
                    "provider_retryability": _provider_retryability_truth(result),
                    "reported_provider_completion": (
                        str(result.status).strip().casefold() == "completed"
                    ),
                    "completion_observation_status": observation.status,
                    "safety_class": str(
                        request.metadata.get("safety_class") or ""
                    ),
                    "effects": list(request.metadata.get("effects") or []),
                    "execution_lane": str(
                        request.metadata.get("execution_lane") or "activity"
                    ),
                    "retryable_safe_read": (
                        request.metadata.get("retryable_safe_read") is True
                    ),
                    "completion_qualification_required": bool(
                        qualification_policy is not None
                        or qualification_gate_reason
                    ),
                    "completion_evidence_gate_reason": qualification_gate_reason,
                },
            ),
            observation_bytes,
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
        schema_error = output_schema_declaration_error(output_schema)
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
    def _request_timing_matches_step(
        step: Any,
        request: CapabilityRequest,
    ) -> bool:
        if request.timing == step.timing:
            return True
        metadata = request.metadata if isinstance(request.metadata, dict) else {}
        return bool(
            request.timing == "parallel"
            and step.timing != "parallel"
            and request.requires_confirmation is False
            and metadata.get("runtime_timing_adjustment")
            == "safe_read_parallel"
            and metadata.get("canonical_timing") == step.timing
            and metadata.get("effective_timing") == request.timing
            and metadata.get("retryable_safe_read") is True
            and metadata.get("parallel_with_vocal") is True
            and str(metadata.get("safety_class") or "") == "safe_read"
        )

    @staticmethod
    def _planned_requests(
        plan: CanonicalPlan,
        *,
        fingerprint: str,
        requests: list[CapabilityRequest],
    ) -> tuple[
        dict[str, CapabilityRequest],
        dict[str, CapabilityRequest],
        int,
    ]:
        by_step: dict[str, CapabilityRequest] = {}
        auxiliary_by_request: dict[str, CapabilityRequest] = {}
        seen_request_ids: set[str] = set()
        ignored = 0
        known_steps = {step.step_id: step for step in plan.steps}
        for request in requests:
            if request.request_id in seen_request_ids:
                raise ValueError(
                    "multiple committed CapabilityRequest values use one request_id"
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
            if request.capability_id != step.capability_id:
                raise ValueError(
                    "canonical step request capability_id does not match plan"
                )
            if request.args != step.args:
                raise ValueError(
                    "canonical step request args do not match plan"
                )
            if not ExecutionOutcomeReconciler._request_timing_matches_step(
                step, request
            ):
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
                "canonical plan steps have no committed CapabilityRequest: "
                + ",".join(missing)
            )
        return by_step, auxiliary_by_request, ignored

    @staticmethod
    def _results_by_request(
        results: list[CapabilityResult],
        *,
        planned_request_ids: set[str],
        auxiliary_requests: Mapping[str, CapabilityRequest],
        committed_auxiliary_result_capabilities: Mapping[str, str],
    ) -> tuple[dict[str, CapabilityResult], int]:
        by_request: dict[str, CapabilityResult] = {}
        ignored_request_ids: set[str] = set()
        auxiliary_result_capabilities = {
            request_id: request.capability_id
            for request_id, request in auxiliary_requests.items()
        }
        for raw_request_id, raw_capability_id in (
            committed_auxiliary_result_capabilities.items()
        ):
            request_id = str(raw_request_id or "").strip()
            capability_id = str(raw_capability_id or "").strip()
            if not request_id or not capability_id:
                raise ValueError(
                    "committed auxiliary result binding requires request_id "
                    "and capability_id"
                )
            if (
                request_id in planned_request_ids
                or request_id in auxiliary_result_capabilities
            ):
                raise ValueError(
                    "committed auxiliary result binding collides with a "
                    "CapabilityRequest"
                )
            auxiliary_result_capabilities[request_id] = capability_id
        ignored = 0
        for result in results:
            if result.request_id not in planned_request_ids:
                auxiliary = auxiliary_requests.get(result.request_id)
                expected_capability_id = auxiliary_result_capabilities.get(
                    result.request_id
                )
                if expected_capability_id is None:
                    raise ValueError(
                        "CapabilityResult has no committed canonical or auxiliary "
                        f"CapabilityRequest: {result.request_id}"
                    )
                if result.request_id in ignored_request_ids:
                    raise ValueError(
                        "multiple CapabilityResult values reference one auxiliary "
                        "request"
                    )
                if result.capability_id != expected_capability_id:
                    raise ValueError(
                        "auxiliary CapabilityResult capability_id does not match "
                        "committed request"
                    )
                if (
                    auxiliary is not None
                    and result.capability_version
                    and auxiliary.capability_version
                    and result.capability_version != auxiliary.capability_version
                ):
                    raise ValueError(
                        "auxiliary CapabilityResult capability_version does not match "
                        "committed request"
                    )
                ignored_request_ids.add(result.request_id)
                ignored += 1
                continue
            if result.request_id in by_request:
                raise ValueError(
                    "multiple CapabilityResult values reference one request"
                )
            by_request[result.request_id] = result
        return by_request, ignored

    @staticmethod
    def _traces_by_request(
        traces: list[CapabilityTrace],
        *,
        planned_request_ids: set[str],
    ) -> dict[str, CapabilityTrace]:
        by_request: dict[str, CapabilityTrace] = {}
        for trace in traces:
            if trace.request_id not in planned_request_ids:
                continue
            if trace.request_id in by_request:
                raise ValueError(
                    "multiple CapabilityTrace values reference one request"
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
        return "failed", "non_terminal_capability_result"


def planner_execution_outcome_truth(
    bundle: ExecutionOutcomeBundle,
) -> dict[str, Any]:
    """Project immutable execution truth for Planner re-entry.

    This projection carries only factual terminal status, evidence correlation,
    observation availability, and mechanical completion qualification. It does
    not interpret those facts, recommend next Work, or author user-visible text.
    """

    validated = ExecutionOutcomeBundle.model_validate(
        bundle.model_dump(mode="python")
    )
    evidence_rows: list[dict[str, Any]] = []
    for evidence in validated.evidence:
        observation = evidence.observation
        evidence_rows.append(
            {
                "evidence_id": evidence.evidence_id,
                "capability_id": evidence.capability_id,
                "source_goal_ids": list(evidence.source_goal_ids),
                "status": evidence.status,
                "reason_code": str(evidence.reason_code or ""),
                "observation_status": (
                    observation.status if observation is not None else "none"
                ),
                "provider_retryability": dict(
                    evidence.metadata.get("provider_retryability") or {}
                ),
            }
        )
    return {
        "outcome_id": validated.outcome_id,
        "aggregate_status": validated.aggregate_status,
        "goal_outcomes": [
            {
                "goal_id": outcome.goal_id,
                "status": outcome.status,
                "reason_codes": list(outcome.reason_codes),
                "evidence_ids": list(outcome.evidence_ids),
                "completion_qualification": (
                    goal_completion_qualification_summary(validated, outcome)
                ),
            }
            for outcome in validated.goal_outcomes
        ],
        "evidence": evidence_rows,
    }


def build_execution_outcome_bundle(
    *,
    turn_id: str,
    plan: CanonicalPlan,
    interaction_id: str,
    requests: Iterable[CapabilityRequest],
    results: Iterable[CapabilityResult],
    output_schemas: Mapping[str, dict[str, Any]] | None = None,
    completion_evidence_policies: Mapping[
        str, ClaimQualificationPolicy
    ] | None = None,
    completion_evidence_gate_reasons: Mapping[str, str] | None = None,
    committed_auxiliary_result_capabilities: Mapping[str, str] | None = None,
    traces: Iterable[CapabilityTrace] = (),
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
        completion_evidence_policies=completion_evidence_policies,
        completion_evidence_gate_reasons=completion_evidence_gate_reasons,
        committed_auxiliary_result_capabilities=(
            committed_auxiliary_result_capabilities
        ),
        traces=traces,
        provider_postconditions=provider_postconditions,
    )
