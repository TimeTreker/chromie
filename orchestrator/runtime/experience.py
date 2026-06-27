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
        if (
            record.execution_status.lower() not in failure_statuses
            and not failed_skill
            and not record.errors
        ):
            return None
        return MindUpdateProposal(
            target="experience_tuned_strategy",
            proposed_change=(
                "Review the failed or uncertain interaction and consider updating "
                "routing examples, skill-selection preferences, tests, or long-term "
                "goals. Do not change core principles without owner approval."
            ),
            rationale=(
                f"Experience {record.experience_id} ended with execution_status="
                f"{record.execution_status!r}, route={record.route!r}, "
                f"intent={record.intent!r}."
            ),
            evidence_ids=[record.experience_id],
            requires_owner_approval=True,
            auto_apply=False,
        )

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
