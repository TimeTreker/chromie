from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from shared.chromie_contracts.interaction import InteractionResponse
from shared.chromie_contracts.mind import MindProfile

from .skill_runtime import SkillRuntimeResult


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _compact_text(value: str, *, limit: int = 800) -> str:
    text = " ".join((value or "").strip().split())
    if len(text) > limit:
        return text[:limit].rstrip() + "..."
    return text


class EpisodeRouterRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    route: str = "unknown"
    intent: str = "unknown"
    source: str = "unknown"
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    latency_ms: float | None = Field(default=None, ge=0.0)


class EpisodeSkillRequestRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    skill_id: str
    args: dict[str, Any] = Field(default_factory=dict)
    timing: str = "parallel"
    requires_confirmation: bool = False


class EpisodeAgentRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = "unknown"
    speech: list[str] = Field(default_factory=list)
    selected_skills: list[EpisodeSkillRequestRecord] = Field(default_factory=list)
    requires_confirmation: bool = False
    reason: str | None = None
    latency_ms: float | None = Field(default=None, ge=0.0)

    @field_validator("speech")
    @classmethod
    def compact_speech(cls, value: list[str]) -> list[str]:
        return [_compact_text(item, limit=500) for item in value if item.strip()]


class EpisodeSkillResultRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    skill_id: str
    status: str
    reason_code: str | None = None
    message: str = ""

    @field_validator("message")
    @classmethod
    def compact_message(cls, value: str) -> str:
        return _compact_text(value, limit=500)


class EpisodeExecutionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = "not_executed"
    skill_results: list[EpisodeSkillResultRecord] = Field(default_factory=list)


class EpisodeTurnRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sid: str | None = None
    turn_index: int = Field(ge=1)
    created_at: str = Field(default_factory=_now_iso)
    user_text: str = ""
    router: EpisodeRouterRecord = Field(default_factory=EpisodeRouterRecord)
    agent: EpisodeAgentRecord = Field(default_factory=EpisodeAgentRecord)
    execution: EpisodeExecutionRecord = Field(default_factory=EpisodeExecutionRecord)
    errors: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("user_text")
    @classmethod
    def compact_user_text(cls, value: str) -> str:
        return _compact_text(value, limit=500)


class EpisodeRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    episode_id: str = Field(default_factory=lambda: f"episode_{uuid4().hex[:12]}")
    conversation_id: str
    source: str = "voice_runtime"
    started_at: str = Field(default_factory=_now_iso)
    updated_at: str = Field(default_factory=_now_iso)
    turns: list[EpisodeTurnRecord] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


EvaluationSeverity = Literal["pass", "minor", "major", "critical"]


class EpisodeEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    evaluation_id: str = Field(default_factory=lambda: f"eval_{uuid4().hex[:12]}")
    created_at: str = Field(default_factory=_now_iso)
    episode_id: str
    conversation_id: str | None = None
    overall_score: int = Field(ge=0, le=100)
    passed: bool
    severity: EvaluationSeverity
    summary: str
    scores: dict[str, int] = Field(default_factory=dict)
    failure_tags: list[str] = Field(default_factory=list)
    candidate_scenario: dict[str, Any] = Field(default_factory=dict)
    evaluator: str = "contract_precheck"

    @field_validator("summary")
    @classmethod
    def compact_summary(cls, value: str) -> str:
        return _compact_text(value, limit=1000)


class EpisodeRecorder:
    """Append-only conversation episode snapshots for offline evaluation.

    The recorder is deliberately best-effort. It must never break the realtime
    voice path if local evidence storage is unavailable.
    """

    def __init__(
        self,
        *,
        enabled: bool = True,
        log_path: Path,
        max_turns: int = 12,
        source: str = "voice_runtime",
    ) -> None:
        self.enabled = enabled
        self.log_path = log_path
        self.max_turns = max(1, int(max_turns))
        self.source = source
        self._episodes: dict[str, EpisodeRecord] = {}

    @classmethod
    def from_env(cls, project_root: Path) -> "EpisodeRecorder":
        enabled = os.getenv("ORCH_ENABLE_EPISODE_RECORDING", "1").strip().lower() not in {
            "0",
            "false",
            "no",
            "off",
        }
        raw_path = os.getenv("ORCH_EPISODE_LOG_PATH", "").strip()
        if raw_path:
            path = Path(raw_path).expanduser()
            log_path = path if path.is_absolute() else project_root / path
        else:
            log_path = project_root / ".chromie" / "experience" / "episodes.jsonl"
        max_turns = int(os.getenv("ORCH_EPISODE_MAX_TURNS", "12"))
        return cls(enabled=enabled, log_path=log_path, max_turns=max_turns)

    def record_interaction(
        self,
        *,
        response: InteractionResponse,
        execution: SkillRuntimeResult | None,
        session_id: str | None,
        mind_profile: MindProfile,
        errors: list[str] | None = None,
    ) -> EpisodeRecord | None:
        if not self.enabled:
            return None
        context = response.metadata.get("experience_context")
        if not isinstance(context, dict):
            context = {}
        conversation_id = str(context.get("conversation_id") or "local_default")
        episode = self._episodes.get(conversation_id)
        if episode is None:
            episode = EpisodeRecord(
                conversation_id=conversation_id,
                source=self.source,
                metadata={
                    "mind_profile_id": mind_profile.profile_id,
                    "mind_profile_version": mind_profile.version,
                },
            )
            self._episodes[conversation_id] = episode

        turn = self._turn_from_response(
            response=response,
            execution=execution,
            session_id=session_id,
            context=context,
            turn_index=len(episode.turns) + 1,
            errors=errors,
        )
        turns = [*episode.turns, turn]
        if len(turns) > self.max_turns:
            turns = turns[-self.max_turns :]
            for index, item in enumerate(turns, start=1):
                item.turn_index = index
        episode = episode.model_copy(
            deep=True,
            update={
                "updated_at": _now_iso(),
                "turns": turns,
                "metadata": {
                    **episode.metadata,
                    "last_sid": session_id,
                    "last_interaction_id": response.interaction_id,
                },
            },
        )
        self._episodes[conversation_id] = episode
        self._append_jsonl(self.log_path, episode.model_dump(mode="json"))
        return episode

    def reset_thread(self, conversation_id: str) -> None:
        self._episodes.pop(conversation_id, None)

    def _turn_from_response(
        self,
        *,
        response: InteractionResponse,
        execution: SkillRuntimeResult | None,
        session_id: str | None,
        context: dict[str, Any],
        turn_index: int,
        errors: list[str] | None,
    ) -> EpisodeTurnRecord:
        skill_results: list[EpisodeSkillResultRecord] = []
        execution_status = "not_executed"
        if execution is not None:
            execution_status = execution.status
            skill_results = [
                EpisodeSkillResultRecord(
                    request_id=result.request_id,
                    skill_id=result.skill_id,
                    status=result.status,
                    reason_code=result.reason_code,
                    message=result.message,
                )
                for result in execution.results
            ]
        return EpisodeTurnRecord(
            sid=session_id,
            turn_index=turn_index,
            user_text=str(context.get("user_text") or ""),
            router=EpisodeRouterRecord(
                route=str(context.get("route") or "unknown"),
                intent=str(context.get("intent") or "unknown"),
                source=str(context.get("route_source") or "unknown"),
                confidence=self._float_or_none(context.get("route_confidence")),
                latency_ms=self._float_or_none(context.get("router_latency_ms")),
            ),
            agent=EpisodeAgentRecord(
                status=response.status,
                speech=[item.text for item in response.speech],
                selected_skills=[
                    EpisodeSkillRequestRecord(
                        request_id=request.request_id,
                        skill_id=request.skill_id,
                        args=request.args,
                        timing=request.timing,
                        requires_confirmation=request.requires_confirmation,
                    )
                    for request in response.skills
                ],
                requires_confirmation=response.requires_confirmation,
                reason=response.reason,
                latency_ms=self._float_or_none(context.get("agent_latency_ms")),
            ),
            execution=EpisodeExecutionRecord(
                status=execution_status,
                skill_results=skill_results,
            ),
            errors=list(errors or ()),
            metadata={
                "interaction_id": response.interaction_id,
                "route_stage": context.get("route_stage"),
            },
        )

    @staticmethod
    def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")

    @staticmethod
    def _float_or_none(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
