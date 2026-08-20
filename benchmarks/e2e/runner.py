from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Protocol

from benchmarks.runners.evaluation import evaluate_boundaries

from .evidence import validate_claims, validate_evidence, validate_timing
from .executor import E2EExecutionRecord
from .profiles import EvidenceProfile


class E2EExecutor(Protocol):
    def execute(
        self,
        scenario: Mapping[str, Any],
        run: Mapping[str, Any],
        profile: EvidenceProfile,
    ) -> E2EExecutionRecord: ...


@dataclass(frozen=True)
class E2ERunProfile:
    run_id: str
    evidence_profile: EvidenceProfile
    model: str | None = None
    prompt_revision: str | None = None
    code_revision: str | None = None
    provider_revision: str | None = None
    hardware_profile: str | None = None
    operator: str | None = None
    effective_model_topology: Mapping[str, str] = field(default_factory=dict)
    mind_profile: str | None = None
    social_interaction_style: str | None = None
    social_attention_mode: str | None = None
    semantic_authority_owner: str | None = None
    runtime_topology: str | None = None
    sample_count: int = 1
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.sample_count < 1:
            raise ValueError("E2E sample_count must be at least 1")
        if self.social_attention_mode not in {None, "off", "report_only", "on"}:
            raise ValueError(
                "social_attention_mode must be off, report_only, on, or omitted"
            )
        if not all(
            isinstance(name, str) and name.strip() and isinstance(model, str) and model.strip()
            for name, model in self.effective_model_topology.items()
        ):
            raise ValueError(
                "effective_model_topology must map non-empty component names to models"
            )
    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": "e2e",
            "run_id": self.run_id,
            "evidence_level": self.evidence_profile.evidence_level,
            "evidence_profile": self.evidence_profile.id,
            "input_mode": self.evidence_profile.input_mode,
            "embodiment": self.evidence_profile.embodiment,
            "supervision": self.evidence_profile.supervision,
            "model": self.model,
            "prompt_revision": self.prompt_revision,
            "code_revision": self.code_revision,
            "provider_revision": self.provider_revision,
            "hardware_profile": self.hardware_profile,
            "operator": self.operator,
            "effective_model_topology": dict(self.effective_model_topology),
            "mind_profile": self.mind_profile,
            "social_interaction_style": self.social_interaction_style,
            "social_attention_mode": self.social_attention_mode,
            "semantic_authority_owner": self.semantic_authority_owner,
            "runtime_topology": self.runtime_topology,
            "sample_count": self.sample_count,
            "metadata": dict(self.metadata),
        }


class E2EBenchmarkRunner:
    def __init__(self, executor: E2EExecutor, run_profile: E2ERunProfile) -> None:
        self._executor = executor
        self._run_profile = run_profile

    def run(self, cases: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
        original_cases = [dict(item) for item in cases]
        results = [self._run_one(case) for case in original_cases]
        counts = Counter(item["status"] for item in results)
        evidence_counts = Counter(
            item["qualification"]["evidence_state"] for item in results
        )
        lifecycle_counts: dict[str, Counter[str]] = {
            name: Counter()
            for name in (
                "proposal_state",
                "materialization_state",
                "provider_acceptance_state",
                "provider_completion_state",
                "safe_idle_state",
            )
        }
        for item in results:
            lifecycle = item.get("observations", {}).get(
                "social_attention_lifecycle", {}
            )
            if not isinstance(lifecycle, Mapping):
                continue
            for name, counter in lifecycle_counts.items():
                value = lifecycle.get(name, "not_observed")
                if isinstance(value, str) and value:
                    counter[value] += 1
        return {
            "schema_version": 1,
            "run": self._run_profile.to_dict(),
            "profile": self._run_profile.evidence_profile.to_dict(),
            "summary": {
                "total": len(results),
                "pass": counts["pass"],
                "fail": counts["fail"],
                "review": counts["review"],
                "error": counts["error"],
                "evidence_complete": evidence_counts["complete"],
                "evidence_partial": evidence_counts["partial"],
                "evidence_missing": evidence_counts["missing"],
                "social_attention_lifecycle": {
                    name: dict(sorted(counter.items()))
                    for name, counter in lifecycle_counts.items()
                },
            },
            "qualification": {
                "release_qualified": False,
                "human_approval_required": self._run_profile.evidence_profile.human_approval_required,
                "state": self._suite_qualification_state(results),
                "claim_ceiling": list(
                    self._run_profile.evidence_profile.allowed_execution_claims
                ),
            },
            "results": results,
        }

    def _run_one(self, scenario: Mapping[str, Any]) -> dict[str, Any]:
        scenario_id = str(scenario["id"])
        correlation_id = f"{self._run_profile.run_id}:{scenario_id}"
        run = self._run_profile.to_dict()
        run["correlation_id"] = correlation_id
        record = self._executor.execute(
            scenario,
            run,
            self._run_profile.evidence_profile,
        )
        evidence_validation = validate_evidence(
            self._run_profile.evidence_profile,
            record.evidence,
            correlation_id=correlation_id,
        )
        claims_validation = validate_claims(
            self._run_profile.evidence_profile,
            record.execution_claims,
        )
        if record.observation is None:
            timing_validation = {
                "complete": not self._run_profile.evidence_profile.required_timing_markers,
                "required": list(
                    self._run_profile.evidence_profile.required_timing_markers
                ),
                "observed": {},
                "missing": list(
                    self._run_profile.evidence_profile.required_timing_markers
                ),
                "ordering_errors": [],
                "derived": {},
            }
            base = {
                "schema_version": 1,
                "scenario_id": scenario_id,
                "status": "error",
                "run": run,
                "observations": {
                    "primary_task_passed": None,
                    "primary_outcome": None,
                    "auxiliary_behavior": None,
                    "behaviors": [],
                    "latency_ms": None,
                    "social_attention_lifecycle": {},
                    "evidence": [item.to_dict() for item in record.evidence],
                },
                "evaluation": {
                    "semantic_review_required": False,
                    "forbidden_behavior_hits": [],
                },
                "invariant_results": [],
                "artifacts": list(record.artifacts),
            }
        else:
            base = evaluate_boundaries(scenario, record.observation, self._run_profile)
            timing_validation = validate_timing(
                self._run_profile.evidence_profile,
                record.timing,
                auxiliary_behavior=record.observation.auxiliary_behavior,
            )

        base["run"] = run
        base["artifacts"] = list(record.artifacts)
        base["observations"].update(
            {
                "correlation_id": correlation_id,
                "execution_state": record.execution_state,
                "execution_claims": list(record.execution_claims),
                "timing": timing_validation["observed"],
                "derived_timing": timing_validation["derived"],
                "partial_evidence_retained": record.partial_evidence_retained,
            }
        )
        evidence_complete = bool(evidence_validation["complete"])
        timing_complete = bool(timing_validation["complete"])
        claims_valid = bool(claims_validation["valid"])
        if record.error or record.execution_state in {"timeout", "adapter_error"}:
            status = "error"
        elif record.execution_state in {"failed", "partial"}:
            status = "fail"
        elif not evidence_complete or not timing_complete or not claims_valid:
            status = "fail"
        else:
            status = base["status"]
        base["status"] = status
        evidence_state = "complete"
        if not record.evidence:
            evidence_state = "missing"
        elif not evidence_complete or record.execution_state != "completed":
            evidence_state = "partial"
        base["evidence_profile_validation"] = {
            "evidence": evidence_validation,
            "claims": claims_validation,
            "timing": timing_validation,
        }
        base["execution_error"] = record.error
        base["qualification"] = {
            "evidence_state": evidence_state,
            "release_qualified": False,
            "human_approval_required": self._run_profile.evidence_profile.human_approval_required,
            "state": self._result_qualification_state(status, evidence_state),
        }
        return base

    def _result_qualification_state(self, status: str, evidence_state: str) -> str:
        if status in {"fail", "error"}:
            return "not_eligible"
        if evidence_state != "complete":
            return "evidence_incomplete"
        if self._run_profile.evidence_profile.human_approval_required:
            return "human_review_required"
        return "evidence_complete"

    def _suite_qualification_state(self, results: list[Mapping[str, Any]]) -> str:
        if any(item["status"] in {"fail", "error"} for item in results):
            return "not_eligible"
        if any(
            item["qualification"]["evidence_state"] != "complete"
            for item in results
        ):
            return "evidence_incomplete"
        if self._run_profile.evidence_profile.human_approval_required:
            return "human_review_required"
        return "evidence_complete"
