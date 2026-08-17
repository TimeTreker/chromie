from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from shared.chromie_contracts.core_interpretation import CognitiveResponsibilityProposal
from shared.chromie_contracts.interaction import CapabilityIdentityModel, InteractionResponse
from shared.chromie_contracts.mind import MindProfile
from shared.chromie_runtime.runtime_events import persist_runtime_event

from .capability_runtime import CapabilityRuntimeResult


logger = logging.getLogger("chromie.orchestrator.episode")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _compact_text(value: str, *, limit: int = 800) -> str:
    text = " ".join((value or "").strip().split())
    if len(text) > limit:
        return text[:limit].rstrip() + "..."
    return text

if TYPE_CHECKING:
    from .host_settings import EpisodeSettings


class EpisodeGoalInterpretationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    responsibilities: list[CognitiveResponsibilityProposal] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)
    latency_ms: float | None = Field(default=None, ge=0.0)


class EpisodeCapabilityRequestRecord(CapabilityIdentityModel):
    request_id: str
    args: dict[str, Any] = Field(default_factory=dict)
    timing: str = "parallel"
    requires_confirmation: bool = False


class EpisodeAgentRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = "unknown"
    speech: list[str] = Field(default_factory=list)
    selected_capabilities: list[EpisodeCapabilityRequestRecord] = Field(default_factory=list)
    requires_confirmation: bool = False
    reason: str | None = None
    latency_ms: float | None = Field(default=None, ge=0.0)

    @field_validator("speech")
    @classmethod
    def compact_speech(cls, value: list[str]) -> list[str]:
        return [_compact_text(item, limit=500) for item in value if item.strip()]


class EpisodeCapabilityResultRecord(CapabilityIdentityModel):
    request_id: str
    status: str
    provider_id: str | None = None
    execution_mode: str | None = None
    no_motion: bool | None = None
    recommendation_only: bool | None = None
    reason_code: str | None = None
    message: str = ""

    @field_validator("message")
    @classmethod
    def compact_message(cls, value: str) -> str:
        return _compact_text(value, limit=500)


class EpisodeExecutionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = "not_executed"
    capability_results: list[EpisodeCapabilityResultRecord] = Field(default_factory=list)


class EpisodeTurnRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sid: str | None = None
    turn_index: int = Field(ge=1)
    created_at: str = Field(default_factory=_now_iso)
    user_text: str = ""
    goal_interpretation: EpisodeGoalInterpretationRecord = Field(default_factory=EpisodeGoalInterpretationRecord)
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
EpisodeCaseQuality = Literal["good_case", "bad_case", "needs_review"]


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


class EpisodeOfflineReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    review_id: str = Field(default_factory=lambda: f"review_{uuid4().hex[:12]}")
    created_at: str = Field(default_factory=_now_iso)
    episode_id: str
    conversation_id: str | None = None
    evaluation_id: str
    case_quality: EpisodeCaseQuality
    overall_score: int = Field(ge=0, le=100)
    severity: EvaluationSeverity
    summary: str
    root_cause: str
    strengths: list[str] = Field(default_factory=list)
    failure_tags: list[str] = Field(default_factory=list)
    learning_actions: list[str] = Field(default_factory=list)
    should_create_scenario: bool = False
    should_create_mind_update: bool = False
    compact_memory_notes: list[str] = Field(default_factory=list)
    training_signal: dict[str, Any] = Field(default_factory=dict)
    requires_owner_approval: bool = True
    auto_apply: bool = False
    reviewer: str = "offline_review"

    @field_validator("summary", "root_cause")
    @classmethod
    def compact_review_text(cls, value: str) -> str:
        return _compact_text(value, limit=1000)

    @field_validator("strengths", "failure_tags", "learning_actions", "compact_memory_notes")
    @classmethod
    def compact_review_lists(cls, value: list[str]) -> list[str]:
        return [_compact_text(item, limit=300) for item in value if item.strip()]

    @field_validator("auto_apply")
    @classmethod
    def forbid_auto_apply(cls, value: bool) -> bool:
        if value:
            raise ValueError("offline review updates must never auto-apply")
        return value


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
        emit_runtime_events: bool = False,
        event_root: Path | None = None,
        trigger_root: Path | None = None,
    ) -> None:
        self.enabled = enabled
        self.log_path = log_path
        self.max_turns = max(1, int(max_turns))
        self.source = source
        self.emit_runtime_events = bool(emit_runtime_events)
        self.event_root = event_root
        self.trigger_root = trigger_root
        self._episodes: dict[str, EpisodeRecord] = {}

    @classmethod
    def from_settings(cls, settings: "EpisodeSettings") -> "EpisodeRecorder":
        return cls(
            enabled=settings.enabled,
            log_path=settings.log_path,
            max_turns=settings.max_turns,
            emit_runtime_events=settings.emit_runtime_events,
            event_root=settings.event_root,
            trigger_root=settings.trigger_root,
        )

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
        emit_runtime_events = os.getenv(
            "ORCH_EMIT_EPISODE_RUNTIME_EVENTS", "0"
        ).strip().lower() in {"1", "true", "yes", "on"}
        event_root = cls._optional_env_path("CHROMIE_RUNTIME_EVENT_ROOT", project_root)
        trigger_root = cls._optional_env_path(
            "CHROMIE_DATA_LOOP_TRIGGER_ROOT", project_root
        )
        return cls(
            enabled=enabled,
            log_path=log_path,
            max_turns=max_turns,
            emit_runtime_events=emit_runtime_events,
            event_root=event_root,
            trigger_root=trigger_root,
        )

    def record_interaction(
        self,
        *,
        response: InteractionResponse,
        execution: CapabilityRuntimeResult | None,
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
        interaction_session_evidence = context.get(
            "interaction_session_evidence"
        )
        if not isinstance(interaction_session_evidence, dict):
            interaction_session_evidence = None
        if episode is None:
            episode = EpisodeRecord(
                conversation_id=conversation_id,
                source=self.source,
                metadata={
                    "mind_profile_id": mind_profile.profile_id,
                    "mind_profile_version": mind_profile.version,
                    **(
                        {
                            "interaction_session_evidence": dict(
                                interaction_session_evidence
                            )
                        }
                        if interaction_session_evidence is not None
                        else {}
                    ),
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
                    **(
                        {
                            "interaction_session_evidence": dict(
                                interaction_session_evidence
                            )
                        }
                        if interaction_session_evidence is not None
                        else {}
                    ),
                },
            },
        )
        self._episodes[conversation_id] = episode
        self._append_jsonl(self.log_path, episode.model_dump(mode="json"))
        self._emit_episode_event(
            episode=episode,
            response=response,
            session_id=session_id,
        )
        return episode

    def reset_thread(self, conversation_id: str) -> None:
        self._episodes.pop(conversation_id, None)

    def _emit_episode_event(
        self,
        *,
        episode: EpisodeRecord,
        response: InteractionResponse,
        session_id: str | None,
    ) -> None:
        if not self.emit_runtime_events:
            return
        try:
            latest_turn = episode.turns[-1] if episode.turns else None
            persist_runtime_event(
                event_type="chromie.experience_episode",
                event_subtype="episode_snapshot",
                severity="info",
                producer="chromie.episode_recorder",
                event_root=self.event_root,
                trigger_root=self.trigger_root,
                correlations={
                    "episode_id": episode.episode_id,
                    "conversation_id": episode.conversation_id,
                    "session_id": session_id or "",
                    "interaction_id": response.interaction_id,
                    "turn_index": latest_turn.turn_index if latest_turn else 0,
                },
                attributes={
                    "source": episode.source,
                    "turn_count": len(episode.turns),
                    "agent_status": latest_turn.agent.status if latest_turn else "unknown",
                    "execution_status": (
                        latest_turn.execution.status if latest_turn else "not_executed"
                    ),
                    "has_errors": bool(latest_turn.errors) if latest_turn else False,
                },
                derivation={
                    "scenario_candidate_eligible": True,
                    "scenario_auto_promotion_allowed": False,
                    "offline_evaluation_supported": True,
                },
                payloads={"episode.json": episode.model_dump(mode="json")},
            )
        except Exception as exc:
            # Evidence emission is best-effort and must never break the realtime path,
            # but the evidence loss must remain observable to operators.
            logger.warning(
                "Episode runtime-event evidence emission failed episode_id=%s error_type=%s error=%s",
                episode.episode_id,
                type(exc).__name__,
                exc,
            )
            return

    @staticmethod
    def _optional_env_path(name: str, project_root: Path) -> Path | None:
        raw = os.getenv(name, "").strip()
        if not raw:
            return None
        path = Path(raw).expanduser()
        return path if path.is_absolute() else project_root / path

    def _turn_from_response(
        self,
        *,
        response: InteractionResponse,
        execution: CapabilityRuntimeResult | None,
        session_id: str | None,
        context: dict[str, Any],
        turn_index: int,
        errors: list[str] | None,
    ) -> EpisodeTurnRecord:
        capability_results: list[EpisodeCapabilityResultRecord] = []
        execution_status = "not_executed"
        if execution is not None:
            execution_status = execution.status
            for result in execution.results:
                output = result.output if isinstance(result.output, dict) else {}
                mode = str(output.get("mode") or "").strip() or None
                no_motion = output.get("no_motion")
                recommendation_only = output.get("recommendation_only")
                capability_results.append(
                    EpisodeCapabilityResultRecord(
                        request_id=result.request_id,
                        capability_id=result.capability_id,
                        status=result.status,
                        provider_id=result.provider_id,
                        execution_mode=mode,
                        no_motion=(
                            no_motion if isinstance(no_motion, bool) else None
                        ),
                        recommendation_only=(
                            recommendation_only
                            if isinstance(recommendation_only, bool)
                            else None
                        ),
                        reason_code=result.reason_code,
                        message=result.message,
                    )
                )
        return EpisodeTurnRecord(
            sid=session_id,
            turn_index=turn_index,
            user_text=str(context.get("user_text") or ""),
            goal_interpretation=EpisodeGoalInterpretationRecord(
                confidence=self._float_or_none(
                    context.get("goal_interpretation_confidence")
                ),
                responsibilities=list(
                    (
                        context.get("goal_interpretation")
                        if isinstance(context.get("goal_interpretation"), dict)
                        else {}
                    ).get("responsibilities")
                    or []
                ),
                unresolved=[
                    str(item)
                    for item in context.get("goal_interpretation_unresolved", [])
                    if str(item).strip()
                ],
                latency_ms=self._float_or_none(
                    context.get("goal_interpretation_latency_ms")
                ),
            ),
            agent=EpisodeAgentRecord(
                status=response.status,
                speech=[item.text for item in response.speech],
                selected_capabilities=[
                    EpisodeCapabilityRequestRecord(
                        request_id=request.request_id,
                        capability_id=request.capability_id,
                        args=request.args,
                        timing=request.timing,
                        requires_confirmation=request.requires_confirmation,
                    )
                    for request in response.capabilities
                ],
                requires_confirmation=response.requires_confirmation,
                reason=response.reason,
                latency_ms=self._float_or_none(context.get("agent_latency_ms")),
            ),
            execution=EpisodeExecutionRecord(
                status=execution_status,
                capability_results=capability_results,
            ),
            errors=list(errors or ()),
            metadata={
                "interaction_id": response.interaction_id,
                **(
                    {
                        "interaction_session_evidence": dict(
                            context["interaction_session_evidence"]
                        )
                    }
                    if isinstance(
                        context.get("interaction_session_evidence"), dict
                    )
                    else {}
                ),
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
