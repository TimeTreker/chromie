from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Protocol

from benchmarks.e2e.runner import E2EBenchmarkRunner, E2EExecutor, E2ERunProfile
from benchmarks.e2e.profiles import EvidenceProfile

from .analyzer import analyze_results
from .profiles import StressWorkload
from .workloads import StressSample, build_sample_plan


class StressExecutorFactory(Protocol):
    def __call__(self, sample: StressSample) -> E2EExecutor: ...


@dataclass(frozen=True)
class StressRunProfile:
    run_id: str
    model: str | None = None
    prompt_revision: str | None = None
    mind_profile: str | None = None
    code_revision: str | None = None
    provider_revision: str | None = None
    hardware_profile: str | None = None
    operator: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": "stress",
            "run_id": self.run_id,
            "model": self.model,
            "prompt_revision": self.prompt_revision,
            "mind_profile": self.mind_profile,
            "code_revision": self.code_revision,
            "provider_revision": self.provider_revision,
            "hardware_profile": self.hardware_profile,
            "operator": self.operator,
            "metadata": dict(self.metadata),
        }


class StressBenchmarkRunner:
    def __init__(
        self,
        executor_factory: StressExecutorFactory,
        run_profile: StressRunProfile,
        workload: StressWorkload,
        evidence_profile: EvidenceProfile,
    ) -> None:
        self._executor_factory = executor_factory
        self._run_profile = run_profile
        self._workload = workload
        self._evidence_profile = evidence_profile

    def run(self, cases: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
        plan = build_sample_plan(cases, self._workload)
        if self._workload.concurrency == 1:
            results = [self._run_sample_safe(sample) for sample in plan]
        else:
            results_by_index: dict[int, dict[str, Any]] = {}
            with ThreadPoolExecutor(max_workers=self._workload.concurrency) as pool:
                future_map = {
                    pool.submit(self._run_sample_safe, sample): sample.index for sample in plan
                }
                for future in as_completed(future_map):
                    index = future_map[future]
                    results_by_index[index] = future.result()
            results = [results_by_index[index] for index in sorted(results_by_index)]
        counts = Counter(str(item.get("status", "error")) for item in results)
        evidence_counts = Counter(
            str(item.get("qualification", {}).get("evidence_state", "missing"))
            for item in results
        )
        distribution = analyze_results(results)
        return {
            "schema_version": 1,
            "run": self._run_profile.to_dict(),
            "workload": self._workload.to_dict(),
            "evidence_profile": self._evidence_profile.to_dict(),
            "summary": {
                "samples": len(results),
                "sessions": self._workload.session_count,
                "configured_concurrency": self._workload.concurrency,
                "pass": counts["pass"],
                "fail": counts["fail"],
                "review": counts["review"],
                "error": counts["error"],
                "evidence_complete": evidence_counts["complete"],
                "evidence_partial": evidence_counts["partial"],
                "evidence_missing": evidence_counts["missing"],
            },
            "distribution": distribution,
            "qualification": {
                "release_qualified": False,
                "human_approval_required": True,
                "metrics_are_observational": True,
                "runtime_policy_authority": False,
                "state": self._qualification_state(counts, evidence_counts),
            },
            "results": results,
        }

    def _run_sample_safe(self, sample: StressSample) -> dict[str, Any]:
        try:
            return self._run_sample(sample)
        except Exception as exc:  # benchmark harness failure must stay observable
            return self._error_result(sample, str(exc))

    def _run_sample(self, sample: StressSample) -> dict[str, Any]:
        stress_metadata = {
            "workload_id": self._workload.id,
            "workload_kind": self._workload.kind,
            "sample_id": sample.sample_id,
            "sample_index": sample.index,
            "session_id": sample.session_id,
            "sequence_position": sample.sequence_position,
            "participant_id": sample.participant_id,
            "conditions": dict(self._workload.conditions),
            "runtime_policy_authority": False,
        }
        e2e_profile = E2ERunProfile(
            run_id=f"{self._run_profile.run_id}.{sample.sample_id}",
            evidence_profile=self._evidence_profile,
            model=self._run_profile.model,
            prompt_revision=self._run_profile.prompt_revision,
            code_revision=self._run_profile.code_revision,
            provider_revision=self._run_profile.provider_revision,
            hardware_profile=self._run_profile.hardware_profile,
            operator=self._run_profile.operator,
            metadata={**dict(self._run_profile.metadata), "stress": stress_metadata},
        )
        report = E2EBenchmarkRunner(
            self._executor_factory(sample), e2e_profile
        ).run([sample.scenario])
        result = dict(report["results"][0])
        result["sample"] = sample.to_dict()
        result["sample"]["stress_conditions"] = dict(self._workload.conditions)
        return result

    def _error_result(self, sample: StressSample, error: str) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "scenario_id": sample.source_scenario_id,
            "status": "error",
            "run": self._run_profile.to_dict(),
            "sample": {
                **sample.to_dict(),
                "stress_conditions": dict(self._workload.conditions),
            },
            "observations": {
                "primary_task_passed": None,
                "primary_outcome": None,
                "auxiliary_behavior": None,
                "behaviors": [],
                "latency_ms": None,
                "evidence": [],
            },
            "evaluation": {
                "semantic_review_required": False,
                "forbidden_behavior_hits": [],
            },
            "invariant_results": [],
            "artifacts": [],
            "execution_error": error,
            "qualification": {
                "evidence_state": "missing",
                "release_qualified": False,
                "human_approval_required": True,
                "state": "not_eligible",
            },
        }

    @staticmethod
    def _qualification_state(
        counts: Counter[str], evidence_counts: Counter[str]
    ) -> str:
        if counts["fail"] or counts["error"]:
            return "not_eligible"
        if evidence_counts["partial"] or evidence_counts["missing"]:
            return "evidence_incomplete"
        return "human_review_required"
