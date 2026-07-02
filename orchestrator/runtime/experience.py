from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from shared.chromie_contracts.interaction import InteractionResponse
from shared.chromie_contracts.mind import (
    ExperienceRecord,
    MindProfile,
    MindUpdateProposal,
)

from .skill_runtime import SkillRuntimeResult


class ExperienceManager:
    """Append-only robot experience journal and human-review proposal writer."""

    def __init__(
        self,
        *,
        enabled: bool = True,
        log_path: Path,
        proposal_path: Path,
    ) -> None:
        self.enabled = enabled
        self.log_path = log_path
        self.proposal_path = proposal_path

    @classmethod
    def from_env(cls, project_root: Path) -> "ExperienceManager":
        enabled = os.getenv("ORCH_ENABLE_EXPERIENCE_JOURNAL", "1").strip().lower() not in {
            "0",
            "false",
            "no",
            "off",
        }
        log_path = cls._path_from_env(
            "ORCH_EXPERIENCE_LOG_PATH",
            project_root / ".chromie" / "experience" / "experience.jsonl",
            project_root,
        )
        proposal_path = cls._path_from_env(
            "ORCH_MIND_PROPOSAL_LOG_PATH",
            project_root / ".chromie" / "experience" / "mind_update_proposals.jsonl",
            project_root,
        )
        return cls(enabled=enabled, log_path=log_path, proposal_path=proposal_path)

    @staticmethod
    def _path_from_env(name: str, default: Path, project_root: Path) -> Path:
        raw = os.getenv(name, "").strip()
        if not raw:
            return default
        path = Path(raw).expanduser()
        return path if path.is_absolute() else project_root / path

    def record_interaction(
        self,
        *,
        response: InteractionResponse,
        execution: SkillRuntimeResult | None,
        session_id: str | None,
        mind_profile: MindProfile,
        errors: list[str] | None = None,
    ) -> ExperienceRecord | None:
        if not self.enabled:
            return None
        context = response.metadata.get("experience_context")
        if not isinstance(context, dict):
            context = {}
        selected_skills = [request.skill_id for request in response.skills]
        skill_results = []
        execution_status = "not_executed"
        if execution is not None:
            execution_status = execution.status
            skill_results = [
                {
                    "request_id": result.request_id,
                    "skill_id": result.skill_id,
                    "status": result.status,
                    "reason_code": result.reason_code,
                    "message": result.message,
                }
                for result in execution.results
            ]
        record = ExperienceRecord(
            sid=session_id,
            conversation_id=self._str_or_none(context.get("conversation_id")),
            user_text=str(context.get("user_text") or ""),
            route=str(context.get("route") or "unknown"),
            intent=str(context.get("intent") or "unknown"),
            route_source=str(context.get("route_source") or "unknown"),
            route_confidence=self._float_or_none(context.get("route_confidence")),
            response_status=response.status,
            execution_status=execution_status,
            selected_skills=selected_skills,
            skill_results=skill_results,
            speech_count=len(response.speech),
            errors=list(errors or ()),
            mind_profile_id=mind_profile.profile_id,
            mind_profile_version=mind_profile.version,
            metadata={
                "response_reason": response.reason,
                "requires_confirmation": response.requires_confirmation,
                **self._proposal_learning_metadata(response),
            },
        )
        self._append_jsonl(self.log_path, record.model_dump(mode="json"))
        proposal = self.proposal_from_experience(record)
        if proposal is not None:
            self._append_jsonl(self.proposal_path, proposal.model_dump(mode="json"))
        return record

    def proposal_from_experience(
        self,
        record: ExperienceRecord,
    ) -> MindUpdateProposal | None:
        failure_statuses = {"failed", "error", "timed_out", "cancelled", "refused"}
        failed_skill = any(
            str(result.get("status") or "").lower() in failure_statuses
            for result in record.skill_results
        )
        learning_signal = self._learning_signal_from_metadata(record.metadata)
        if (
            record.execution_status.lower() not in failure_statuses
            and not failed_skill
            and not record.errors
            and not learning_signal
        ):
            return None
        proposed_change = (
            "Review the failed or uncertain interaction and consider updating "
            "routing examples, skill-selection preferences, tests, or long-term "
            "goals. Do not change core principles without owner approval."
        )
        if learning_signal:
            proposed_change = (
                "Review the proposal/preflight mismatch and consider updating "
                "router merge examples, deepthinking output contracts, scenario "
                "coverage, or skill-selection preferences. Do not change core "
                "principles or physical safety rules without owner approval."
            )
        return MindUpdateProposal(
            target="experience_tuned_strategy",
            proposed_change=proposed_change,
            rationale=(
                f"Experience {record.experience_id} ended with execution_status="
                f"{record.execution_status!r}, route={record.route!r}, "
                f"intent={record.intent!r}."
                + (f" Learning signal: {learning_signal}." if learning_signal else "")
            ),
            evidence_ids=[record.experience_id],
            requires_owner_approval=True,
            auto_apply=False,
        )

    @classmethod
    def _proposal_learning_metadata(
        cls,
        response: InteractionResponse,
    ) -> dict[str, Any]:
        metadata: dict[str, Any] = {}
        ledger = response.metadata.get("task_proposal_ledger")
        if isinstance(ledger, dict):
            summary = cls._safe_summary(ledger.get("summary"))
            if summary:
                metadata["task_proposal_summary"] = summary
        preflight = response.metadata.get("preflight_validation")
        if isinstance(preflight, dict):
            summary = cls._safe_summary(preflight.get("summary"))
            if summary:
                metadata["preflight_summary"] = summary
        if response.metadata.get("truth_reconciled") is True:
            metadata["truth_reconciled"] = True
            reason = str(response.metadata.get("truth_reconciliation_reason") or "").strip()
            if reason:
                metadata["truth_reconciliation_reason"] = reason[:160]
        return metadata

    @classmethod
    def _learning_signal_from_metadata(cls, metadata: dict[str, Any]) -> str:
        proposal = metadata.get("task_proposal_summary")
        preflight = metadata.get("preflight_summary")
        signals: list[str] = []
        if isinstance(proposal, dict):
            not_committed = cls._int_from_summary(
                proposal,
                "not_committed_effectful_count",
            )
            rejected = cls._int_from_mapping(proposal.get("states"), "rejected")
            superseded = cls._int_from_summary(proposal, "superseded_count")
            if not_committed > 0:
                signals.append(f"{not_committed} effectful proposal(s) were not committed")
            if rejected > 0:
                signals.append(f"{rejected} proposal(s) were rejected")
            if superseded > 0:
                signals.append(f"{superseded} proposal(s) were superseded")
        if isinstance(preflight, dict):
            blocked = cls._int_from_summary(preflight, "blocked_count")
            if blocked > 0:
                signals.append(f"{blocked} committed skill(s) failed static preflight")
        if metadata.get("truth_reconciled") is True:
            signals.append("truth reconciliation corrected optimistic action speech")
        return "; ".join(signals)

    @staticmethod
    def _safe_summary(value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        out: dict[str, Any] = {}
        for key, item in value.items():
            if isinstance(item, (str, int, float, bool)) or item is None:
                out[str(key)] = item
                continue
            if isinstance(item, dict):
                nested: dict[str, Any] = {}
                for nested_key, nested_item in item.items():
                    if isinstance(nested_item, (str, int, float, bool)) or nested_item is None:
                        nested[str(nested_key)] = nested_item
                if nested:
                    out[str(key)] = nested
        return out

    @staticmethod
    def _int_from_summary(summary: dict[str, Any], key: str) -> int:
        value = summary.get(key)
        if isinstance(value, bool):
            return 0
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        try:
            return int(str(value))
        except (TypeError, ValueError):
            return 0

    @classmethod
    def _int_from_mapping(cls, value: Any, key: str) -> int:
        if not isinstance(value, dict):
            return 0
        return cls._int_from_summary(value, key)

    @staticmethod
    def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")

    @staticmethod
    def _str_or_none(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _float_or_none(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
