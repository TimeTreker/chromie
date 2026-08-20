from __future__ import annotations

import asyncio
from collections import deque
from difflib import SequenceMatcher
import json
import logging
import math
import os
import re
import threading
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv

ORCH_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = ORCH_DIR.parent


def load_runtime_environment(
    *,
    project_root: Path = PROJECT_ROOT,
    orchestrator_dir: Path = ORCH_DIR,
) -> None:
    """Load generated runtime configuration only for an explicit bootstrap."""

    load_dotenv(project_root / ".env.runtime")
    load_dotenv(orchestrator_dir / ".env.local")


if __name__ == "__main__":
    load_runtime_environment()

import aiohttp
import numpy as np
import websockets
from scipy import signal

from orchestrator.audio_device_manager import AudioDeviceManager
from orchestrator.readiness import ServiceReadinessGate
from orchestrator.vad import VAD
from orchestrator.clients.action_client import ActionClient
from orchestrator.runtime.body_recovery import (
    BodyRecoveryConfirmation,
    build_body_recovery_confirmation,
)
from orchestrator.runtime.confirmation import (
    ConfirmationDialogue,
    ConfirmationReplyMeaning,
    PendingConfirmation,
    confirmation_meaning_from_goal_association,
    pending_confirmation_goal_ids,
)
from orchestrator.runtime.named_goal_cancellation import (
    ActiveGoalCancellationRequiresRuntimeDispatch,
    NamedGoalCancellationClosureError,
    cancellation_target_goal_ids,
    replacement_target_goal_ids,
    dispatch_named_goal_cancellation,
    dispatch_goal_replacement,
)
from orchestrator.runtime.cognitive_runtime import (
    CanonicalPlanRuntimeAdapter,
    CognitiveEvidenceRecorder,
    CognitiveRuntimePolicy,
    CognitiveRuntimeResolution,
    GoalDrivenRuntimeCoordinator,
)
from orchestrator.runtime.cognitive_turn_closure import CognitiveTurnClosure
from orchestrator.runtime.cognitive_gateway import (
    CognitiveGateway,
)
from orchestrator.runtime.evidence_identity import (
    load_runtime_evidence_identity,
)
from orchestrator.runtime.host_components import (
    build_agent_client,
    build_host_support,
    build_interaction_runtime,
)
from orchestrator.runtime.host_settings import HostSettingsSnapshot
from orchestrator.runtime.input_turn_lifecycle import InputTurnLifecycle
from orchestrator.runtime.input_session_runtime import input_session_runtime_for
from orchestrator.runtime.outcome_delivery import build_host_outcome_delivery
from orchestrator.runtime.playback_delivery import PlaybackDeliveryLifecycle
from orchestrator.runtime.playback_transport import transport_for as playback_transport_for
from orchestrator.runtime.outcome_response import compose_outcome_response
from orchestrator.runtime.response_plan import validate_immediate_response_plan
from orchestrator.runtime.runtime_ready_greeting import (
    RuntimeReadyGreetingCoordinator,
    RuntimeReadyGreetingPolicy,
    execute_default_runtime_ready_orientation,
)
from orchestrator.runtime.session import (
    now_ms,
    record_session_workflow_stage,
    summarize_provider_start_evidence,
)
from shared.chromie_runtime.accelerator_telemetry import (
    ACCELERATOR_SAMPLE_MODULE,
)
from shared.chromie_runtime.runtime_trace import TraceModule, runtime_tracer
from orchestrator.runtime.capability_runtime import CapabilityRuntimeResult
from shared.chromie_contracts.core_interpretation import (
    CognitiveResponsibilityProposal,
    CognitiveWorkRequest,
    CoreInterpretationResult,
)
from shared.chromie_contracts.interaction import (
    InteractionResponse,
    InteractionSpeech,
    CapabilityRequest,
    CapabilityResult,
)
from shared.chromie_contracts.goal import GoalAssociationResolution
from shared.chromie_contracts.plan import CanonicalPlan
from shared.chromie_contracts.execution_outcome import (
    ExecutionEvidence,
    goal_completion_qualification_summary,
)
from shared.chromie_contracts.situation import CognitiveOpportunity
from shared.chromie_contracts.tool_result import (
    ToolExecutionRequest,
    ToolExecutionResponse,
    ToolResultEvidence,
    canonical_value_sha256,
)
from shared.chromie_contracts.reflex import (
    CancellationDirective,
    CancellationDispatchReceipt,
    ReflexOutcome,
)
from shared.chromie_contracts.user_turn import UserTurnEnvelope
from shared.chromie_contracts.semantic_authority import (
    SemanticAuthorityClaim,
    context_with_semantic_authority,
)
from shared.chromie_runtime.ollama_non_thinking import (
    enforce_non_thinking_ollama_response,
)
from shared.chromie_runtime.llm_diagnostics import (
    log_llm_call_evidence,
    new_llm_call_id,
    ollama_completion_diagnostics,
    ollama_prompt_preflight_diagnostics,
)

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="[%(levelname)s] %(asctime)s - %(threadName)s - %(funcName)s - %(message)s",
)
logger = logging.getLogger("chromie-orchestrator")

TTS_TRACE_MODULE = TraceModule(
    name="orchestrator.tts",
    component_type="audio",
    implementation="ChromieOrchestrator",
)
PLAYBACK_TRACE_MODULE = TraceModule(
    name="orchestrator.audio_playback",
    component_type="audio",
    implementation="ChromieOrchestrator",
)


def trace_session_async(module: TraceModule, operation: str, session_arg: str):
    """Instrument an async orchestrator method on its detached session trace."""

    def decorate(function):
        async def wrapped(self, *args, **kwargs):
            import inspect

            bound = inspect.signature(function).bind(self, *args, **kwargs)
            bound.apply_defaults()
            session_id = bound.arguments.get(session_arg)
            with self.sessions.trace_context(session_id):
                async with runtime_tracer.span(
                    module=module,
                    operation=operation,
                    attributes={"session_id": session_id or ""},
                ):
                    return await function(self, *args, **kwargs)

        wrapped.__name__ = function.__name__
        wrapped.__doc__ = function.__doc__
        return wrapped

    return decorate








class VoiceAssistant:
    def __init__(self):
        # Parse the maintained Host configuration surface exactly once. Runtime
        # collaborators receive immutable typed groups rather than re-reading
        # environment variables with inconsistent fallback behavior.
        self.host_settings = HostSettingsSnapshot.from_env(
            project_root=PROJECT_ROOT
        )
        audio_settings = self.host_settings.audio_input
        cognition_settings = self.host_settings.cognition
        playback_settings = self.host_settings.playback
        session_settings = self.host_settings.session
        evidence_settings = self.host_settings.evidence

        self.asr_url = audio_settings.asr_url
        self.tts_url = playback_settings.tts_url
        self.llm_url = cognition_settings.llm_url
        self.ollama_model = cognition_settings.ollama_model

        self.enable_agent = cognition_settings.enable_agent
        self.enable_interaction_response = (
            cognition_settings.enable_interaction_response
        )
        self.enable_soridormi_capabilities = cognition_settings.enable_soridormi_capabilities
        self.addressedness_gate_enabled = session_settings.addressedness_gate_enabled
        self.addressedness_engagement_timeout_s = (
            session_settings.addressedness_engagement_timeout_s
        )
        self.fast_planner_mode = cognition_settings.fast_planner_mode
        self.fast_planner_timeout_ms = cognition_settings.fast_planner_timeout_ms
        self.deep_planner_mode = cognition_settings.deep_planner_mode
        self.deep_planner_timeout_ms = cognition_settings.deep_planner_timeout_ms
        self.goal_association_mode = cognition_settings.goal_association_mode
        self.goal_association_timeout_ms = (
            cognition_settings.goal_association_timeout_ms
        )
        self.cognitive_runtime_mode = cognition_settings.runtime_mode
        self.cognitive_runtime_timeout_ms = cognition_settings.runtime_timeout_ms
        self.cognitive_evidence_enabled = evidence_settings.cognitive_enabled
        self.cognitive_evidence_include_text = (
            evidence_settings.cognitive_include_text
        )
        self.cognitive_evidence_path = evidence_settings.cognitive_path
        self.cognitive_run_identity_path = evidence_settings.runtime_identity_path
        self.cognitive_run_identity = load_runtime_evidence_identity(
            self.cognitive_run_identity_path
        )

        self.agent_url = cognition_settings.agent_url
        self.action_executor_url = cognition_settings.action_executor_url
        self.action_dry_run = cognition_settings.action_dry_run
        self.agent_client = build_agent_client(self.host_settings)
        self.action_client = ActionClient(
            self.action_executor_url,
            cognition_settings.action_timeout_ms,
        )
        self.asr_timeout_s = max(0.001, audio_settings.asr_timeout_ms / 1000.0)

        self.min_rms = audio_settings.min_rms
        self.barge_in_min_rms = audio_settings.barge_in_min_rms
        self.min_audio_ms = audio_settings.min_audio_ms
        self.max_vad_utterance_ms = audio_settings.vad_max_utterance_ms
        self.input_gain = audio_settings.input_gain
        self.tts_flush_chars = playback_settings.flush_chars
        self.tts_max_text_chars = playback_settings.max_text_chars
        self.tts_text_chunking_enabled = playback_settings.text_chunking_enabled
        self.tts_chunk_chars = playback_settings.chunk_chars
        self.tts_cjk_chunk_chars = playback_settings.cjk_chunk_chars
        self.tts_first_chunk_chars = playback_settings.first_chunk_chars
        self.tts_min_chunk_chars = playback_settings.min_chunk_chars
        self.tts_cjk_min_chunk_chars = playback_settings.cjk_min_chunk_chars
        self.default_tts_rate = playback_settings.sample_rate
        self.speaker_id = playback_settings.speaker_id
        self.save_audio_enabled = playback_settings.save_audio_enabled
        self.enable_session_timing = session_settings.timing_logs_enabled
        self.voice_system_prompt = playback_settings.voice_system_prompt
        self.tts_ws_retries = playback_settings.ws_retries
        self.tts_ws_retry_delay_ms = playback_settings.ws_retry_delay_ms
        self.playback_chunk_ms = playback_settings.playback_chunk_ms

        self.asr_ws = None
        self.http_session: aiohttp.ClientSession | None = None
        host_support = build_host_support(
            self.host_settings, timing_enabled=self.enable_session_timing
        )
        self.accelerator_sampler = host_support.accelerator_sampler
        self.sessions = host_support.sessions
        self.conversation_state = host_support.conversation_state
        self.mind = host_support.mind
        self.experience = host_support.experience
        self.episode_recorder = host_support.episode_recorder
        self.confirmation_dialogue = ConfirmationDialogue(
            ttl_s=session_settings.confirmation_ttl_s,
        )
        self.body_recovery_max_attempts = session_settings.body_recovery_max_attempts
        self.body_recovery_confirmation_ttl_s = (
            session_settings.body_recovery_confirmation_ttl_s
        )
        logger.info(
            "Conversation state: enabled=%s conversation_id=%s max_turns=%s idle_s=%s hard_idle_s=%s max_context_chars=%s",
            self.conversation_state.enabled,
            self.conversation_state.conversation_id,
            self.conversation_state.max_turns,
            self.conversation_state.soft_idle_timeout_sec,
            self.conversation_state.hard_idle_timeout_sec,
            self.conversation_state.max_context_chars,
        )
        logger.info(
            "Mind profile: profile_id=%s version=%s owner_approved=%s experience_journal=%s",
            self.mind.profile.profile_id,
            self.mind.profile.version,
            self.mind.profile.owner_approved,
            self.experience.enabled,
        )
        logger.info(
            "Episode recorder: enabled=%s path=%s max_turns=%s",
            self.episode_recorder.enabled,
            self.episode_recorder.log_path,
            self.episode_recorder.max_turns,
        )
        self.active_interaction_task: asyncio.Task | None = None
        self.active_interaction_id: str | None = None
        self.active_interaction_tasks: dict[asyncio.Task, str] = {}
        # Detached provider work is not an active foreground interaction task.
        # These tasks consume Runtime lifecycle/Evidence after submit() returned.
        self.active_capability_result_tasks: dict[asyncio.Task, str] = {}
        self.observability_tasks: set[asyncio.Task] = set()
        self.is_playing_audio = False

        self.audio_input_mode = audio_settings.mode
        self.audio_output_mode = playback_settings.output_mode
        self.discard_playback_realtime = (
            playback_settings.discard_playback_realtime
        )
        self.runtime_ready_greeting_enabled = (
            playback_settings.ready_greeting_enabled
        )
        self.runtime_ready_greeting_text = playback_settings.ready_greeting_text
        self.runtime_ready_greeting_fallback_text = (
            playback_settings.ready_greeting_fallback_text
        )
        self.runtime_ready_greeting_language = (
            playback_settings.ready_greeting_language
        )
        self.runtime_ready_greeting_model = playback_settings.ready_greeting_model
        self.runtime_ready_greeting_num_predict = (
            playback_settings.ready_greeting_num_predict
        )
        self.runtime_ready_greeting_generation_timeout_ms = (
            playback_settings.ready_greeting_generation_timeout_ms
        )
        self.runtime_ready_greeting_timeout_ms = (
            playback_settings.ready_greeting_timeout_ms
        )

        self.audio_mgr = AudioDeviceManager(self.host_settings.audio_device)
        if self.audio_input_mode == "device":
            self.input_params = self.audio_mgr.get_input_params()
        else:
            injected_rate = audio_settings.injected_rate
            injected_channels = audio_settings.injected_channels
            self.input_params = {
                "name": "framed PCM16 stdin injection",
                "device": None,
                "rate": injected_rate,
                "channels": injected_channels,
                "blocksize": max(1, int(injected_rate * 30 / 1000)),
                "block_ms": 30,
                "latency": "none",
            }
        if self.audio_output_mode == "device":
            self.output_params = self.audio_mgr.get_output_params()
        else:
            discard_rate = playback_settings.output_rate
            self.output_params = {
                "name": "discarded acceptance playback",
                "device": None,
                "rate": discard_rate,
                "channels": 1,
                "blocksize": 0,
                "block_ms": self.playback_chunk_ms,
                "latency": "none",
            }
        self.input_rate = self.input_params["rate"]
        self.input_channels = self.input_params["channels"]
        self.input_device = self.input_params["device"]
        self.input_block_size = self.input_params["blocksize"]
        self.input_latency = self.input_params["latency"]
        self.output_rate = self.output_params["rate"]
        self.output_channels = self.output_params["channels"]
        self.output_device = self.output_params["device"]
        self.output_latency = self.output_params["latency"]

        logger.info(
            "Input device name=%s index=%s selection=%s rate=%sHz channels=%s blocksize=%s block_ms=%s latency=%s min_rms=%s barge_in_min_rms=%s input_gain=%.2f",
            self.input_params["name"],
            self.input_device,
            self.input_params.get("selection_source", "injected"),
            self.input_rate,
            self.input_channels,
            self.input_block_size,
            self.input_params["block_ms"],
            self.input_latency,
            self.min_rms,
            self.barge_in_min_rms,
            self.input_gain,
        )
        logger.info(
            "Output device name=%s index=%s selection=%s rate=%sHz channels=%s blocksize=%s block_ms=%s latency=%s",
            self.output_params["name"],
            self.output_device,
            self.output_params.get("selection_source", "discard"),
            self.output_rate,
            self.output_channels,
            self.output_params["blocksize"],
            self.output_params["block_ms"],
            self.output_latency,
        )
        logger.info(
            "Audio modes: input=%s output=%s discard_realtime=%s",
            self.audio_input_mode,
            self.audio_output_mode,
            self.discard_playback_realtime,
        )
        logger.info(
            "Control plane: cognitive_gateway=embedded cognitive_core=%s enabled=%s action_url=%s dry_run=%s cognitive_runtime_mode=%s",
            self.agent_url,
            self.enable_agent,
            self.action_executor_url,
            self.action_dry_run,
            self.cognitive_runtime_mode,
        )

        self.target_asr_rate = 16000
        self.frame_duration_ms = 30
        self.vad = VAD(
            mode=audio_settings.vad_mode,
            sample_rate=self.target_asr_rate,
            frame_duration_ms=self.frame_duration_ms,
            silence_timeout_ms=audio_settings.vad_silence_ms,
            max_utterance_ms=self.max_vad_utterance_ms,
        )

        # Focused collaborators own task, microphone, playback, and ledger state;
        # the Host keeps compatibility aliases while lifecycle mutation stays testable.
        self.input_turn_lifecycle = InputTurnLifecycle()
        self.playback_delivery = PlaybackDeliveryLifecycle(
            interaction_event_sink=host_support.interaction_ledger.record_playback_event,
            synthesis_semaphore=asyncio.Semaphore(playback_settings.concurrency)
        )
        self._protective_reflex_failure = False
        self._audio_device_refresh_lock = asyncio.Lock()
        self._input_device_change_event = asyncio.Event()
        self._pending_input_params: dict[str, Any] | None = None
        self._pending_output_params: dict[str, Any] | None = None
        self._audio_device_errors: dict[str, str] = {}
        self._audio_default_change_queue: asyncio.Queue[str] = asyncio.Queue(
            maxsize=8
        )
        self.audio_device_monitor_task: asyncio.Task | None = None
        recordings_dir = evidence_settings.recordings_dir
        self.recordings_dir = str(recordings_dir)
        recordings_dir.mkdir(parents=True, exist_ok=True)

        self.interaction_runtime = build_interaction_runtime(self, self.host_settings, interaction_ledger=host_support.interaction_ledger)
        self.cognitive_runtime_policy = CognitiveRuntimePolicy(
            mode=self.cognitive_runtime_mode,
            max_total_ms=self.cognitive_runtime_timeout_ms,
            goal_association_timeout_ms=self.goal_association_timeout_ms,
            fast_planner_timeout_ms=self.fast_planner_timeout_ms,
            deep_planner_timeout_ms=self.deep_planner_timeout_ms,
        )
        self.cognitive_evidence = CognitiveEvidenceRecorder(
            self.cognitive_evidence_path,
            enabled=self.cognitive_evidence_enabled,
            include_text=self.cognitive_evidence_include_text,
            run_identity=self.cognitive_run_identity,
            run_identity_path=self.cognitive_run_identity_path,
        )
        self.cognitive_turn_closure = CognitiveTurnClosure(
            self.interaction_runtime
        )
        self.cognitive_gateway = CognitiveGateway()
        self.cognitive_runtime = GoalDrivenRuntimeCoordinator(
            agent_client=self.agent_client,
            adapter=CanonicalPlanRuntimeAdapter(
                self.interaction_runtime,
                social_attention_mode=cognition_settings.social_attention_mode,
            ),
            policy=self.cognitive_runtime_policy,
            # Goal Association is already the validated, model-owned semantic
            # result.  Publish it immediately so concurrent follow-up turns can
            # reason over the in-flight Goal while planning and composition
            # continue.  Effectful execution still remains behind the trusted
            # canonical-plan/runtime boundary.
            goal_state_apply=self._commit_goal_association_state,
            planner_gap_apply=self._commit_planner_information_gaps,
            context_refresh=self.build_context,
            delivered_turn_speech_provider=self._delivered_turn_speech_events,
            workflow_stage_sink=host_support.sessions.record_cognitive_stage,
        )
        logger.info(
            "Interaction runtime: endpoint=%s soridormi_skills=%s confirmation_ttl_s=%.1f",
            self.enable_interaction_response,
            self.enable_soridormi_capabilities,
            self.confirmation_dialogue.ttl_s,
        )

    @property
    def session_id(self) -> str | None:
        return self.sessions.current_sid

    def session_log(self, sid: Optional[str], message: str, *args: Any) -> None:
        self.sessions.log(sid, message, *args)

    def maybe_session_done(self, sid: Optional[str]) -> None:
        self.sessions.maybe_done(sid)

    def _playback_state(self) -> PlaybackDeliveryLifecycle:
        state = self.__dict__.get("playback_delivery")
        if not isinstance(state, PlaybackDeliveryLifecycle):
            state = PlaybackDeliveryLifecycle()
            self.__dict__["playback_delivery"] = state
        return state

    def _input_turn_state(self) -> InputTurnLifecycle:
        state = self.__dict__.get("input_turn_lifecycle")
        if not isinstance(state, InputTurnLifecycle):
            state = InputTurnLifecycle()
            self.__dict__["input_turn_lifecycle"] = state
        return state

    _PLAYBACK_STATE_ALIASES = {
        "next_playback_order": "next_playback_order",
        "pending_audio": "pending_audio",
        "synthesis_order": "synthesis_order",
        "playback_generation": "playback_generation",
        "_tts_text_by_generation": "tts_text_by_generation",
        "playback_start_waiters": "playback_start_waiters",
        "playback_release_waiters": "playback_release_waiters",
        "playback_released_keys": "playback_released_keys",
        "cancelled_playback_orders": "cancelled_playback_orders",
        "_turn_speech_events": "turn_speech_events",
        "_turn_speech_event_by_playback_key": "turn_speech_event_by_playback_key",
        "order_lock": "order_lock",
        "playback_queue": "playback_queue",
        "playback_task": "playback_task",
        "active_synthesis_tasks": "active_synthesis_tasks",
        "synthesis_semaphore": "synthesis_semaphore",
        "output_stream": "output_stream",
        "output_stream_lock": "output_stream_lock",
        "output_write_lock": "output_write_lock",
    }
    _PLAYBACK_STATE_COERCERS = {
        "next_playback_order": int,
        "synthesis_order": int,
        "playback_generation": int,
    }
    _INPUT_TURN_STATE_ALIASES = {
        "loop": "loop",
        "mic_queue": "mic_queue",
        "_vad_leftover": "vad_leftover",
        "_vad_segment_started_during_playback": (
            "vad_segment_started_during_playback"
        ),
        "_vad_segment_playback_generation": (
            "vad_segment_playback_generation"
        ),
        "active_asr_task": "active_asr_task",
        "active_turn_task": "active_turn_task",
        "active_turn_tasks": "active_turn_tasks",
        "_turn_cancellation_reasons": "turn_cancellation_reasons",
        "active_reflex_task": "active_reflex_task",
        "concurrent_protective_reflex_tasks": "concurrent_protective_reflex_tasks",
        "_pending_turn_after_reflex": "pending_turn_after_reflex",
        "_pending_vad_audio": "pending_vad_audio",
    }

    def __getattr__(self, name: str) -> Any:
        playback_field = self._PLAYBACK_STATE_ALIASES.get(name)
        if playback_field is not None:
            return getattr(self._playback_state(), playback_field)
        input_field = self._INPUT_TURN_STATE_ALIASES.get(name)
        if input_field is not None:
            return getattr(self._input_turn_state(), input_field)
        raise AttributeError(f"{type(self).__name__!s} has no attribute {name!r}")

    def __setattr__(self, name: str, value: Any) -> None:
        playback_field = self._PLAYBACK_STATE_ALIASES.get(name)
        if playback_field is not None:
            coercer = self._PLAYBACK_STATE_COERCERS.get(name)
            setattr(
                self._playback_state(),
                playback_field,
                coercer(value) if coercer is not None else value,
            )
            return
        input_field = self._INPUT_TURN_STATE_ALIASES.get(name)
        if input_field is not None:
            setattr(self._input_turn_state(), input_field, value)
            return
        object.__setattr__(self, name, value)

    def playback_start_key(
        self,
        generation: int,
        order: int,
        session_id: Optional[str],
    ) -> tuple[int, int, str | None]:
        return self._playback_state().key(generation, order, session_id)

    def _register_turn_speech_event(
        self,
        *,
        session_id: str | None,
        generation: int,
        orders: list[int],
        text: str,
        stage: str,
        purpose: str,
        commitment: str = "",
        fast_activity_id: str = "",
        turn_id: str | None = None,
        source_goal_ids: list[str] | None = None,
        canonical_plan_id: str = "",
        canonical_plan_fingerprint: str = "",
        goal_association_fingerprint: str = "",
        delivery_role: str = "response",
        claims: list[str] | None = None,
        must_not_claim_completion: bool | None = None,
    ) -> dict[str, Any] | None:
        return self._playback_state().register_turn_speech_event(
            session_id=session_id,
            generation=generation,
            orders=orders,
            normalized_text=self.normalize_tts_candidate(text),
            stage=stage,
            purpose=purpose,
            commitment=commitment,
            fast_activity_id=fast_activity_id,
            turn_id=turn_id,
            source_goal_ids=source_goal_ids,
            canonical_plan_id=canonical_plan_id,
            canonical_plan_fingerprint=canonical_plan_fingerprint,
            goal_association_fingerprint=goal_association_fingerprint,
            delivery_role=delivery_role,
            claims=claims,
            must_not_claim_completion=must_not_claim_completion,
        )

    def _update_turn_speech_event_for_playback(
        self,
        *,
        generation: int,
        order: int,
        session_id: str | None,
        started: bool,
        reason: str,
    ) -> None:
        self._playback_state().update_turn_speech_event_for_playback(
            generation=generation,
            order=order,
            session_id=session_id,
            started=started,
            reason=reason,
        )

    def _delivered_turn_speech_events(
        self,
        session_id: str,
    ) -> list[dict[str, Any]]:
        return self._playback_state().delivered_turn_speech_events(session_id)

    def resolve_playback_start_waiter(
        self,
        generation: int,
        order: int,
        session_id: Optional[str],
        *,
        started: bool,
        reason: str,
    ) -> None:
        resolved = self._playback_state().resolve_playback_start_waiter(
            generation=generation,
            order=order,
            session_id=session_id,
            started=started,
            reason=reason,
        )
        if resolved:
            self.session_log(
                session_id,
                "tts_playback_start_waiter_resolved: order=%s started=%s reason=%s",
                order,
                started,
                reason,
            )

    def resolve_all_playback_start_waiters(
        self,
        *,
        started: bool,
        reason: str,
    ) -> None:
        for _, order, session_id in self._playback_state().resolve_all_playback_start_waiters(
            started=started,
            reason=reason,
        ):
            self.session_log(
                session_id,
                "tts_playback_start_waiter_resolved: order=%s started=%s reason=%s",
                order,
                started,
                reason,
            )
        self._playback_state().resolve_all_playback_release_waiters(reason=reason)


    async def wait_for_playback_start(
        self,
        *,
        generation: int,
        order: int,
        session_id: Optional[str],
        timeout_s: float,
    ) -> bool:
        started = await self._playback_state().wait_for_playback_start(
            generation=generation,
            order=order,
            session_id=session_id,
            timeout_s=timeout_s,
        )
        if not started:
            self.session_log(
                session_id,
                "tts_playback_start_waiter_timeout: order=%s timeout_s=%.3f",
                order,
                timeout_s,
            )
        return started

    def _cancel_playback_order_before_start(
        self,
        *,
        generation: int,
        order: int,
        session_id: str | None,
        reason: str,
    ) -> bool:
        cancelled = self._playback_state().cancel_order_before_start(
            generation=generation,
            order=order,
            session_id=session_id,
            reason=reason,
        )
        if not cancelled:
            return False
        state = self.sessions.state.get(session_id or "")
        if state is not None:
            state["skipped_tts"] = int(state.get("skipped_tts", 0)) + 1
        self.session_log(
            session_id,
            "playback_cancel_before_start: order=%s generation=%s reason=%s",
            order,
            generation,
            reason,
        )
        self.maybe_session_done(session_id)
        return True

    def _cancel_scheduled_playback_before_start(
        self,
        scheduled: dict[str, Any],
        *,
        session_id: str | None,
        reason: str,
    ) -> list[int]:
        """Invalidate every still-pending order owned by one speech request.

        A playback-start barrier covers the whole utterance, not only its first
        chunk.  If that barrier fails, later synthesis results must be consumed
        as cancelled rather than becoming delayed, misleading speech.
        """

        try:
            generation = int(scheduled["generation"])
        except (KeyError, TypeError, ValueError):
            return []
        raw_orders = scheduled.get("orders")
        if not isinstance(raw_orders, list):
            raw_orders = [scheduled.get("order")]
        cancelled: list[int] = []
        for raw_order in raw_orders:
            try:
                order = int(raw_order)
            except (TypeError, ValueError):
                continue
            if self._cancel_playback_order_before_start(
                generation=generation,
                order=order,
                session_id=session_id,
                reason=reason,
            ):
                cancelled.append(order)
        return cancelled

    def create_session(self) -> str:
        sid = self.sessions.create()
        self._schedule_accelerator_sample(reason="session_start", session_ids=[sid])
        return sid

    def _track_observability_task(self, task: asyncio.Task) -> None:
        tasks = getattr(self, "observability_tasks", None)
        if tasks is None:
            tasks = set()
            self.observability_tasks = tasks
        tasks.add(task)
        task.add_done_callback(tasks.discard)

    def _schedule_accelerator_sample(
        self,
        *,
        reason: str,
        session_ids: list[str] | None = None,
    ) -> None:
        sampler = getattr(self, "accelerator_sampler", None)
        if sampler is None or not sampler.should_sample(reason):
            return
        try:
            task = asyncio.get_running_loop().create_task(
                self._sample_accelerator_resources(
                    reason=reason,
                    session_ids=session_ids,
                )
            )
        except RuntimeError:
            return
        self._track_observability_task(task)

    async def _sample_accelerator_resources(
        self,
        *,
        reason: str,
        session_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        sampler = getattr(self, "accelerator_sampler", None)
        sessions = getattr(self, "sessions", None)
        if sampler is None or sessions is None:
            return {}
        payload = await sampler.sample(reason=reason)
        if not payload:
            return {}
        if session_ids is None:
            sessions.record_active_resource_sample(
                module=ACCELERATOR_SAMPLE_MODULE,
                name="accelerator_resource_sample",
                attributes=payload,
            )
        else:
            for sid in session_ids:
                sessions.record_resource_sample(
                    sid,
                    module=ACCELERATOR_SAMPLE_MODULE,
                    name="accelerator_resource_sample",
                    attributes=payload,
                )
        return payload

    def normalize_tts_candidate(self, text: str) -> str:
        text = (text or "").strip()
        text = text.replace("```", " ").replace("`", " ").replace("**", " ")
        text = re.sub(r"[*_#>\[\]{}|]+", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        text = re.sub(r"^[-•]+\s*", "", text).strip()
        text = re.sub(r"\s+([,.;:!?])", r"\1", text)
        return text

    def is_valid_tts_text(self, text: str) -> bool:
        text = self.normalize_tts_candidate(text)
        if len(text) < 2:
            return False
        if re.fullmatch(r"\d+[\.)]?", text):
            return False
        return any(ch.isalnum() or "\u4e00" <= ch <= "\u9fff" for ch in text)

    def pop_tts_chunk(
        self,
        buffer: str,
        *,
        flush_chars: int | None = None,
    ) -> tuple[str | None, str]:
        candidate = self.normalize_tts_candidate(buffer)
        if not candidate:
            return None, ""
        limit = max(4, int(flush_chars or self.tts_flush_chars))
        match = re.search(r".+?[.!?。！？](?:\s+|$)", candidate)
        if match and (match.end() <= limit or len(candidate) <= limit):
            end = match.end()
            return candidate[:end].strip(), candidate[end:].strip()
        if len(candidate) >= limit:
            cut = candidate[:limit]
            cut_points = [cut.rfind(sep) for sep in (",", "，", "、", ";", ":", " ")]
            cut_at = max(cut_points)
            if cut_at < max(4, limit // 2):
                cut_at = limit
            else:
                cut_at += 1
            return candidate[:cut_at].strip(), candidate[cut_at:].strip()
        return None, candidate

    @staticmethod
    def _ends_with_tts_sentence_boundary(text: str) -> bool:
        stripped = text.rstrip()
        while stripped and stripped[-1] in "\"'”’)]}」』":
            stripped = stripped[:-1].rstrip()
        return bool(stripped and stripped[-1] in ".!?。！？")

    @staticmethod
    def _ends_with_tts_natural_boundary(text: str) -> bool:
        stripped = text.rstrip()
        while stripped and stripped[-1] in "\"'”’)]}」』":
            stripped = stripped[:-1].rstrip()
        return bool(stripped and stripped[-1] in ".!?。！？,，、;；:：")

    @staticmethod
    def _split_tts_sentence_units(text: str) -> list[str]:
        end_chars = ".!?。！？"
        closing_chars = "\"'”’)]}」』"
        units: list[str] = []
        start = 0
        i = 0
        while i < len(text):
            if text[i] in end_chars:
                sentence_mark = text[i]
                end = i + 1
                while end < len(text) and text[end] in closing_chars:
                    end += 1
                if end == len(text) or text[end].isspace() or sentence_mark in "。！？":
                    unit = text[start:end].strip()
                    if unit:
                        units.append(unit)
                    start = end
                    while start < len(text) and text[start].isspace():
                        start += 1
                    i = start
                    continue
            i += 1
        tail = text[start:].strip()
        if tail:
            units.append(tail)
        return units or [text]

    @staticmethod
    def _split_tts_clause_units(
        text: str,
        *,
        min_chars: int,
        trigger_chars: int,
    ) -> list[str]:
        if len(text) <= trigger_chars:
            return [text]

        split_chars = ",，、;；:："
        opening_quotes = {"“": "”", "「": "」", "『": "』"}
        closing_quotes = {"”", "」", "』"}
        quote_stack: list[str] = []
        in_plain_quote = False
        units: list[str] = []
        start = 0
        i = 0
        while i < len(text):
            char = text[i]
            if char == '"':
                in_plain_quote = not in_plain_quote
            elif char in opening_quotes:
                quote_stack.append(opening_quotes[char])
            elif char in closing_quotes and quote_stack and char == quote_stack[-1]:
                quote_stack.pop()
            elif char in split_chars and not in_plain_quote and not quote_stack:
                end = i + 1
                unit = text[start:end].strip()
                tail = text[end:].strip()
                if len(unit) >= min_chars and len(tail) >= min_chars:
                    units.append(unit)
                    start = end
                    while start < len(text) and text[start].isspace():
                        start += 1
                    i = start
                    continue
            i += 1

        tail = text[start:].strip()
        if tail:
            units.append(tail)
        return units or [text]

    @staticmethod
    def _split_oversized_tts_unit(text: str, hard_limit: int) -> list[str]:
        if len(text) <= hard_limit:
            return [text]
        chunks: list[str] = []
        remaining = text
        while len(remaining) > hard_limit:
            cut = remaining[:hard_limit]
            cut_points = [
                cut.rfind(sep)
                for sep in (",", "，", "、", ";", "；", ":", "：", " ")
            ]
            cut_at = max(cut_points)
            if cut_at < max(20, hard_limit // 2):
                cut_at = hard_limit
            else:
                cut_at += 1
            chunk = remaining[:cut_at].strip()
            if chunk:
                chunks.append(chunk)
            remaining = remaining[cut_at:].strip()
        if remaining:
            chunks.append(remaining)
        return chunks

    def _should_merge_tts_chunks(
        self,
        current: str,
        chunk: str,
        *,
        limit: int,
        hard_limit: int,
        min_chars: int,
    ) -> bool:
        merged_len = len(current) + 1 + len(chunk)
        if merged_len > hard_limit:
            return False
        if len(current) < min_chars:
            return True
        if len(chunk) < min_chars and merged_len <= limit:
            return True
        if not self._ends_with_tts_natural_boundary(current) and merged_len <= limit:
            return True
        return False

    def split_tts_text(self, text: str) -> list[str]:
        candidate = self.normalize_tts_candidate(text)
        if not self.is_valid_tts_text(candidate):
            return []
        if not getattr(self, "tts_text_chunking_enabled", True):
            return [candidate]
        max_text_chars = max(20, int(getattr(self, "tts_max_text_chars", 220)))
        limit = max(
            20,
            min(
                max_text_chars,
                int(getattr(self, "tts_chunk_chars", getattr(self, "tts_flush_chars", 160))),
            ),
        )
        contains_cjk = any("\u4e00" <= char <= "\u9fff" for char in candidate)
        if contains_cjk:
            limit = min(
                limit,
                max(12, int(getattr(self, "tts_cjk_chunk_chars", 36))),
            )
        first_limit = int(getattr(self, "tts_first_chunk_chars", min(limit, 16)) or 0)
        first_limit = max(4, min(limit, first_limit)) if first_limit > 0 else limit
        hard_limit = min(max_text_chars, limit) if contains_cjk else max_text_chars

        raw_chunks: list[str] = []
        min_chars = max(1, int(getattr(self, "tts_min_chunk_chars", 40)))
        if contains_cjk:
            min_chars = min(
                min_chars,
                max(1, int(getattr(self, "tts_cjk_min_chunk_chars", 8))),
            )
            clause_trigger = max(limit, min_chars * 2)
        else:
            clause_trigger = max(80, min(limit, hard_limit) // 2, min_chars * 3)
        for unit in self._split_tts_sentence_units(candidate):
            for clause in self._split_tts_clause_units(
                unit,
                min_chars=min_chars,
                trigger_chars=clause_trigger,
            ):
                raw_chunks.extend(self._split_oversized_tts_unit(clause, hard_limit))
        if not raw_chunks:
            return [candidate]

        chunks: list[str] = []
        current = ""
        grouped_chunks = raw_chunks
        if (
            first_limit < limit
            and len(raw_chunks) > 1
            and len(raw_chunks[0]) <= first_limit
            and self._ends_with_tts_sentence_boundary(raw_chunks[0])
        ):
            chunks.append(raw_chunks[0])
            grouped_chunks = raw_chunks[1:]
        for chunk in grouped_chunks:
            merged = f"{current} {chunk}".strip() if current else chunk
            if not current:
                current = chunk
            elif self._should_merge_tts_chunks(
                current,
                chunk,
                limit=limit,
                hard_limit=hard_limit,
                min_chars=min_chars,
            ):
                current = merged
            else:
                chunks.append(current)
                current = chunk
        if current:
            chunks.append(current)
        return chunks or [candidate]

    def save_audio(self, data: bytes, prefix: str, session_id: Optional[str] = None) -> None:
        if not self.save_audio_enabled or not data:
            return
        sid = session_id or self.session_id or "nosession"
        filename = os.path.join(self.recordings_dir, f"{prefix}_{sid}_{int(time.time() * 1000)}.raw")
        with open(filename, "wb") as f:
            f.write(data)
        logger.info("Saved %s audio to %s", prefix, filename)

    async def get_http_session(self) -> aiohttp.ClientSession:
        if self.http_session is None or self.http_session.closed:
            connector = aiohttp.TCPConnector(limit=20, limit_per_host=10, keepalive_timeout=60, enable_cleanup_closed=True)
            timeout = aiohttp.ClientTimeout(total=None, connect=10, sock_connect=10, sock_read=None)
            self.http_session = aiohttp.ClientSession(connector=connector, timeout=timeout)
        return self.http_session

    async def connect_services(self):
        while True:
            try:
                logger.info("Connecting to ASR: %s", self.asr_url)
                self.asr_ws = await websockets.connect(
                    self.asr_url,
                    max_size=10**7,
                    open_timeout=10,
                    ping_interval=20,
                    ping_timeout=20,
                )
                logger.info("Connected to ASR")
                return
            except Exception as exc:
                logger.warning("ASR not ready yet: %s", exc)
                await asyncio.sleep(3)

    @staticmethod
    def resample_int16_bytes(audio_bytes: bytes, src_rate: int, dst_rate: int) -> bytes:
        if src_rate == dst_rate:
            return audio_bytes
        if src_rate <= 0 or dst_rate <= 0:
            raise ValueError(f"Invalid sample-rate conversion: {src_rate} -> {dst_rate}")
        samples = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32)
        if len(samples) == 0:
            return b""
        gcd = math.gcd(int(src_rate), int(dst_rate))
        up = int(dst_rate // gcd)
        down = int(src_rate // gcd)
        resampled = signal.resample_poly(samples, up, down)
        return np.clip(resampled, -32768, 32767).astype(np.int16).tobytes()

    def prepare_mic_chunk_for_asr(self, audio: np.ndarray) -> bytes:
        arr = np.asarray(audio)
        if arr.ndim > 1:
            arr = arr[:, 0]
        if arr.dtype != np.float32:
            arr = arr.astype(np.float32)
        if self.input_gain != 1.0:
            arr = arr * self.input_gain
        arr = np.clip(arr, -1.0, 1.0)
        pcm = (arr * 32767.0).astype(np.int16).tobytes()
        return self.resample_int16_bytes(pcm, self.input_rate, self.target_asr_rate)

    def _set_input_device_params(self, params: dict[str, Any]) -> None:
        self.input_params = params
        self.input_rate = params["rate"]
        self.input_channels = params["channels"]
        self.input_device = params["device"]
        self.input_block_size = params["blocksize"]
        self.input_latency = params["latency"]

    def _set_output_device_params(self, params: dict[str, Any]) -> None:
        self.output_params = params
        self.output_rate = params["rate"]
        self.output_channels = params["channels"]
        self.output_device = params["device"]
        self.output_latency = params["latency"]

    def _uses_followed_system_default(self, kind: str) -> bool:
        mode = self.audio_input_mode if kind == "input" else self.audio_output_mode
        return mode == "device" and self.audio_mgr.follows_system_default(kind)

    async def _refresh_system_default_audio_devices(
        self,
        *,
        force_kinds: set[str] | None = None,
    ) -> set[str]:
        """Queue validated stream changes for OS-default-following directions."""

        forced = force_kinds or set()
        queued: set[str] = set()
        async with self._audio_device_refresh_lock:
            for kind in ("input", "output"):
                if not self._uses_followed_system_default(kind):
                    continue
                getter = (
                    self.audio_mgr.get_input_params
                    if kind == "input"
                    else self.audio_mgr.get_output_params
                )
                try:
                    candidate = await asyncio.to_thread(getter)
                except Exception as exc:
                    error = f"{type(exc).__name__}: {exc}"
                    if self._audio_device_errors.get(kind) != error:
                        logger.warning(
                            "Could not refresh OS-default %s device; keeping "
                            "the current stream until a valid default appears: %s",
                            kind,
                            error,
                        )
                    self._audio_device_errors[kind] = error
                    continue

                previous_error = self._audio_device_errors.pop(kind, None)
                if previous_error is not None:
                    logger.info("OS-default %s device is available again", kind)
                current = self.input_params if kind == "input" else self.output_params
                pending = (
                    self._pending_input_params
                    if kind == "input"
                    else self._pending_output_params
                )
                if pending is not None and not self.audio_mgr.device_params_changed(
                    pending,
                    candidate,
                ):
                    continue
                changed = self.audio_mgr.device_params_changed(current, candidate)
                if kind not in forced and not changed:
                    continue
                logger.info(
                    "OS-default %s device change detected: old=%s(%r) new=%s(%r) "
                    "signal=%s",
                    kind,
                    current.get("name", "unknown"),
                    current.get("device"),
                    candidate.get("name", "unknown"),
                    candidate.get("device"),
                    "os_metadata" if kind in forced else "portaudio_default",
                )
                if kind == "input":
                    self._pending_input_params = candidate
                    self._input_device_change_event.set()
                else:
                    self._pending_output_params = candidate
                queued.add(kind)
        return queued

    async def _audio_device_monitor(self) -> None:
        """Poll portable defaults and consume read-only PipeWire change events."""

        async def collect_pipewire_changes() -> None:
            try:
                async for kind in self.audio_mgr.watch_system_default_changes():
                    try:
                        self._audio_default_change_queue.put_nowait(kind)
                    except asyncio.QueueFull:
                        # Polling still detects a concrete PortAudio identity
                        # change. A full queue already contains refresh work.
                        pass
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "PipeWire default-device notifications stopped; portable "
                    "PortAudio polling remains active: %s",
                    exc,
                )

        pipewire_task = asyncio.create_task(collect_pipewire_changes())
        try:
            await self._refresh_system_default_audio_devices()
            while True:
                forced: set[str] = set()
                try:
                    kind = await asyncio.wait_for(
                        self._audio_default_change_queue.get(),
                        timeout=1.0,
                    )
                    forced.add(kind)
                    while not self._audio_default_change_queue.empty():
                        forced.add(self._audio_default_change_queue.get_nowait())
                except asyncio.TimeoutError:
                    pass
                await self._refresh_system_default_audio_devices(
                    force_kinds=forced,
                )
        finally:
            pipewire_task.cancel()
            await asyncio.gather(pipewire_task, return_exceptions=True)

    async def _apply_pending_input_device_change(self) -> bool:
        """Activate a queued input device after the old stream has closed."""

        async with self._audio_device_refresh_lock:
            params = self._pending_input_params
            self._pending_input_params = None
            self._input_device_change_event.clear()
        if params is None:
            return False

        dropped_frames = 0
        while not self.mic_queue.empty():
            try:
                self.mic_queue.get_nowait()
                dropped_frames += 1
            except asyncio.QueueEmpty:
                break
        self.vad.reset()
        self._vad_leftover = b""
        duck_state = self._playback_state()
        if duck_state.output_duck_generation is not None:
            await playback_transport_for(self).resume_output_after_duck(
                generation=duck_state.output_duck_generation,
                session_id=duck_state.output_duck_session_id,
                reason="input_device_change",
            )
        self._vad_segment_started_during_playback = False
        self._vad_segment_playback_generation = None
        self._set_input_device_params(params)
        logger.info(
            "Audio input switched to OS default: name=%s device=%r rate=%s "
            "channels=%s discarded_old_frames=%s",
            params.get("name", "unknown"),
            params.get("device"),
            params.get("rate"),
            params.get("channels"),
            dropped_frames,
        )
        return True

    async def _apply_pending_output_device_change(self) -> bool:
        """Close the old output so the next ordered audio uses the new default."""

        async with self._audio_device_refresh_lock:
            params = self._pending_output_params
            self._pending_output_params = None
        if params is None:
            return False

        async with self.output_write_lock:
            async with self.output_stream_lock:
                stream = self.output_stream
                if stream is not None:
                    def stop_and_close() -> None:
                        try:
                            stream.stop()
                        except Exception as exc:
                            logger.debug(
                                "Old output stream stop failed during device switch: %s",
                                exc,
                            )
                        try:
                            stream.close()
                        except Exception as exc:
                            logger.debug(
                                "Old output stream close failed during device switch: %s",
                                exc,
                            )

                    await asyncio.to_thread(stop_and_close)
                    if self.output_stream is stream:
                        self.output_stream = None
                self._set_output_device_params(params)
        logger.info(
            "Audio output switched to OS default: name=%s device=%r rate=%s "
            "channels=%s",
            params.get("name", "unknown"),
            params.get("device"),
            params.get("rate"),
            params.get("channels"),
        )
        return True

    def mono_to_output_channels(self, samples: np.ndarray) -> np.ndarray:
        if self.output_channels == 1:
            return samples
        if self.output_channels == 2:
            return np.column_stack([samples, samples])
        return np.tile(samples.reshape(-1, 1), (1, self.output_channels))

    async def ensure_output_stream(self):
        return await playback_transport_for(self).ensure_output_stream()

    async def abort_output_stream(self):
        return await playback_transport_for(self).abort_output_stream()

    async def close_output_stream(self):
        return await playback_transport_for(self).close_output_stream()

    def is_stale_playback(self, generation: int, session_id: Optional[str]) -> bool:
        return generation != self.playback_generation or session_id != self.session_id

    async def play_audio(self, audio_bytes: bytes, source_rate: Optional[int], generation: int, session_id: Optional[str]):
        return await playback_transport_for(self).play_audio(audio_bytes, source_rate, generation, session_id)

    async def enqueue_playback_skip(self, generation: int, order: int, session_id: Optional[str], reason: str):
        return await playback_transport_for(self).enqueue_playback_skip(generation, order, session_id, reason)

    async def playback_worker(self):
        return await playback_transport_for(self).playback_worker()

    @trace_session_async(PLAYBACK_TRACE_MODULE, "play_one_order", "session_id")
    async def play_one_order(self, generation: int, order: int, audio: bytes, source_rate: int, session_id: Optional[str], skip_reason: Optional[str] = None) -> bool:
        return await playback_transport_for(self).play_one_order(generation, order, audio, source_rate, session_id, skip_reason)

    @trace_session_async(TTS_TRACE_MODULE, "synthesize_one", "session_id")
    async def synthesize_one(self, text: str, order: int, session_id: Optional[str], generation: int):
        return await playback_transport_for(self).synthesize_one(text, order, session_id, generation)

    @staticmethod
    def _normalize_echo_text(text: str) -> str:
        normalized = unicodedata.normalize("NFKC", str(text or "")).casefold()
        return "".join(char for char in normalized if char.isalnum())

    def _remember_tts_text(self, generation: int, text: str) -> None:
        normalized = self.normalize_tts_candidate(text)
        if not normalized:
            return
        store = getattr(self, "_tts_text_by_generation", None)
        if not isinstance(store, dict):
            store = {}
            self._tts_text_by_generation = store
        history = store.setdefault(int(generation), [])
        history.append(normalized)
        # Retain only the current and a few recent generations.  A delayed ASR
        # response may arrive after playback advances, but old dialogue must not
        # accumulate for the lifetime of the process.
        minimum_generation = int(generation) - 3
        for old_generation in list(store):
            if old_generation < minimum_generation:
                store.pop(old_generation, None)

    def _likely_tts_echo(
        self,
        transcript: str,
        *,
        playback_generation_at_start: int | None,
    ) -> tuple[bool, float, float]:
        if playback_generation_at_start is None:
            return False, 0.0, 0.0
        store = getattr(self, "_tts_text_by_generation", {})
        if not isinstance(store, dict):
            store = {}
        spoken_parts = store.get(
            int(playback_generation_at_start),
            [],
        )
        transcript_key = self._normalize_echo_text(transcript)
        part_keys = [
            key
            for part in spoken_parts
            if (key := self._normalize_echo_text(part))
        ]
        if len(transcript_key) < 2 or not part_keys:
            return False, 0.0, 0.0
        # One retained output recording corresponds to one scheduled TTS order.
        # Compare ASR against each order first so a short replay is not diluted
        # by an entire multi-sentence generation.  Adjacent and whole-generation
        # candidates retain coverage for VAD segments that cross order bounds.
        candidate_keys = list(part_keys)
        candidate_keys.extend(
            left + right
            for left, right in zip(part_keys, part_keys[1:], strict=False)
        )
        candidate_keys.append("".join(part_keys))

        best_ratio = 0.0
        best_coverage = 0.0
        best_strength = -1.0
        for spoken_key in dict.fromkeys(candidate_keys):
            if transcript_key in spoken_key:
                return True, 1.0, 1.0
            matcher = SequenceMatcher(
                None,
                transcript_key,
                spoken_key,
                autojunk=False,
            )
            ratio = float(matcher.ratio())
            longest = max(
                (block.size for block in matcher.get_matching_blocks()),
                default=0,
            )
            transcript_coverage = float(
                longest / max(1, len(transcript_key))
            )
            strength = max(ratio / 0.78, transcript_coverage / 0.88)
            if strength > best_strength:
                best_ratio = ratio
                best_coverage = transcript_coverage
                best_strength = strength
        likely = bool(
            best_ratio >= 0.78
            or (best_coverage >= 0.88 and len(transcript_key) >= 6)
        )
        return likely, best_ratio, best_coverage

    async def schedule_tts_sentence(
        self,
        sentence: str,
        session_id: Optional[str],
    ) -> dict[str, Any]:
        sentence = self.normalize_tts_candidate(sentence)
        if not self.is_valid_tts_text(sentence):
            self.session_log(session_id, "tts_skip_invalid_sentence_no_order: chars=%s text=%r", len(sentence), sentence)
            return {"scheduled": False, "reason": "invalid_tts_text"}
        async with self.order_lock:
            generation = self.playback_generation
            if self.is_stale_playback(generation, session_id):
                self.session_log(
                    session_id,
                    "tts_drop_stale_no_order: chars=%s generation=%s current_generation=%s current_sid=%s text=%r",
                    len(sentence),
                    generation,
                    self.playback_generation,
                    self.session_id,
                    sentence,
                )
                return {"scheduled": False, "reason": "stale_playback"}
            order = self.synthesis_order
            self.synthesis_order += 1
        if self.is_stale_playback(generation, session_id):
            return {"scheduled": False, "reason": "stale_playback"}
        self._remember_tts_text(generation, sentence)
        key = self.playback_start_key(generation, order, session_id)
        self.playback_start_waiters[key] = asyncio.get_running_loop().create_future()
        self._playback_state().create_playback_release_waiter(
            generation=generation,
            order=order,
            session_id=session_id,
        )
        state = self.sessions.state.get(session_id or "")
        if state is not None:
            state["scheduled_tts"] = int(state.get("scheduled_tts", 0)) + 1
        self.session_log(session_id, "tts_schedule: order=%s chars=%s scheduled_tts=%s generation=%s text=%r", order, len(sentence), state.get("scheduled_tts", 0) if state else "unknown", generation, sentence)
        task = asyncio.create_task(self.synthesize_one(sentence, order, session_id, generation))
        self.active_synthesis_tasks.add(task)
        task.add_done_callback(self.active_synthesis_tasks.discard)
        self.ensure_playback_worker()
        return {"scheduled": True, "order": order, "generation": generation}

    async def schedule_tts_text(
        self,
        text: str,
        session_id: Optional[str],
    ) -> dict[str, Any]:
        chunks = self.split_tts_text(text)
        if not chunks:
            normalized = self.normalize_tts_candidate(text)
            self.session_log(
                session_id,
                "tts_skip_invalid_text_no_order: chars=%s text=%r",
                len(normalized),
                normalized,
            )
            return {"scheduled": False, "reason": "invalid_tts_text"}

        if len(chunks) > 1:
            self.session_log(
                session_id,
                "tts_text_split: chunks=%s chars=%s chunk_chars=%s",
                len(chunks),
                len(self.normalize_tts_candidate(text)),
                getattr(self, "tts_chunk_chars", getattr(self, "tts_flush_chars", 160)),
            )

        scheduled: list[dict[str, Any]] = []
        # Schedule every chunk now. With one TTS slot, synth tasks queue behind
        # the semaphore and the next chunk starts as soon as prior audio is
        # queued, overlapping generation with ordered playback.
        for chunk in chunks:
            result = await self.schedule_tts_sentence(chunk, session_id)
            if result.get("scheduled") is True:
                scheduled.append(result)

        if not scheduled:
            return {"scheduled": False, "reason": "no_tts_chunks_scheduled"}
        first = scheduled[0]
        last = scheduled[-1]
        return {
            "scheduled": True,
            "order": first["order"],
            "generation": first["generation"],
            "chunks": len(scheduled),
            "orders": [item["order"] for item in scheduled],
            "last_order": last["order"],
        }

    async def _cancel_interaction_speech(
        self,
        request: CapabilityRequest,
        scheduled: dict[str, Any],
    ) -> None:
        """Cancel one goal-bound speech request at the shared output boundary.

        Pending chunks are invalidated by exact generation/order.  Once any
        chunk may have started, Chromie's playback resource is global, so the
        only truthful cancellation is a shared output abort.  Capability Runtime
        marks that provider as global-domain and records every coaffected Goal.
        """

        metadata = request.args.get("metadata")
        session_id = (
            metadata.get("session_id")
            if isinstance(metadata, dict)
            else None
        )
        cancelled_orders = self._cancel_scheduled_playback_before_start(
            scheduled,
            session_id=session_id,
            reason="named_goal_speech_cancelled",
        )
        raw_orders = scheduled.get("orders")
        if not isinstance(raw_orders, list):
            raw_orders = [scheduled.get("order")]
        expected_orders = {
            int(item)
            for item in raw_orders
            if isinstance(item, int)
            or (isinstance(item, str) and item.isdigit())
        }
        needs_global_abort = bool(
            not scheduled
            or scheduled.get("scheduled") is not True
            or scheduled.get("playback_started") is True
            or expected_orders - set(cancelled_orders)
        )
        if needs_global_abort:
            self._invalidate_output_state(cancel_cognitive_work=False)
            await self.abort_output_stream()
        self.session_log(
            session_id,
            "interaction_speech_cancelled: request_id=%s pending_orders=%s "
            "global_abort=%s",
            request.request_id,
            ",".join(str(item) for item in sorted(cancelled_orders)),
            needs_global_abort,
        )

    async def _schedule_interaction_speech(
        self,
        args: dict[str, Any],
    ) -> dict[str, Any]:
        metadata = args.get("metadata")
        session_id = (
            metadata.get("session_id")
            if isinstance(metadata, dict)
            else None
        )
        voice_release_required = bool(
            isinstance(metadata, dict)
            and metadata.get("wait_for_voice_release") is True
        )

        async def wait_for_voice_release(
            generation: int,
            orders: list[int],
            playback_started: bool,
        ) -> bool:
            if not voice_release_required or not playback_started or not orders:
                return False
            raw_timeout_ms = (
                metadata.get("voice_release_timeout_ms", 30000)
                if isinstance(metadata, dict)
                else 30000
            )
            try:
                timeout_ms = max(1000, int(raw_timeout_ms))
            except (TypeError, ValueError):
                timeout_ms = 30000
            return await self._playback_state().wait_for_playback_release(
                generation=generation,
                order=orders[-1],
                session_id=session_id,
                timeout_s=timeout_ms / 1000.0,
            )

        if (
            isinstance(metadata, dict)
            and metadata.get("reuse_current_turn_speech") is True
        ):
            raw_generation = metadata.get("reused_speech_generation")
            raw_orders = metadata.get("reused_speech_orders")
            event_id = str(metadata.get("reused_speech_event_id") or "").strip()
            try:
                generation = int(raw_generation)
            except (TypeError, ValueError):
                return {
                    "scheduled": False,
                    "reason": "reused_speech_missing_generation",
                    "reused": True,
                }
            orders = [
                int(item)
                for item in (raw_orders if isinstance(raw_orders, list) else [])
                if isinstance(item, int)
            ]
            if not orders:
                return {
                    "scheduled": False,
                    "reason": "reused_speech_missing_orders",
                    "reused": True,
                }

            def current_status() -> str:
                events = self._playback_state().turn_speech_events.get(
                    str(session_id or ""),
                    [],
                )
                for item in reversed(events):
                    if event_id and str(item.get("event_id") or "") != event_id:
                        continue
                    raw_event_generation = item.get("generation")
                    try:
                        event_generation = int(raw_event_generation)
                    except (TypeError, ValueError):
                        event_generation = -1
                    if event_generation != generation:
                        continue
                    item_orders = item.get("orders")
                    if not isinstance(item_orders, list) or orders[0] not in item_orders:
                        continue
                    return str(item.get("status") or "")
                return ""

            status = current_status()
            playback_started = status in {
                "playback_started",
                "playback_completed",
            }
            playback_barrier = (
                metadata.get("wait_for_playback_start") is True
                or voice_release_required
            )
            if playback_barrier and not playback_started:
                default_playback_timeout_ms = int(
                    getattr(
                        getattr(
                            getattr(self, "host_settings", None),
                            "playback",
                            None,
                        ),
                        "playback_start_timeout_ms",
                        20000,
                    )
                )
                try:
                    timeout_ms = int(
                        metadata.get(
                            "playback_start_timeout_ms",
                            default_playback_timeout_ms,
                        )
                    )
                except (TypeError, ValueError):
                    timeout_ms = default_playback_timeout_ms
                playback_started = await self.wait_for_playback_start(
                    generation=generation,
                    order=orders[0],
                    session_id=session_id,
                    timeout_s=max(0.001, timeout_ms / 1000.0),
                )
                playback_started = playback_started or current_status() in {
                    "playback_started",
                    "playback_completed",
                }
                if not playback_started:
                    status_after_wait = current_status()
                    reused_request = {
                        "scheduled": True,
                        "generation": generation,
                        "order": orders[0],
                        "orders": orders,
                    }
                    if status_after_wait == "scheduled":
                        self._cancel_scheduled_playback_before_start(
                            reused_request,
                            session_id=session_id,
                            reason="reused_speech_delivery_not_observed",
                        )
                        status_after_wait = current_status()
                    if status_after_wait in {
                        "playback_started",
                        "playback_completed",
                    }:
                        playback_started = True
                    elif status_after_wait in {"not_delivered", ""}:
                        fallback_metadata = dict(metadata)
                        fallback_metadata["reuse_current_turn_speech"] = False
                        fallback_metadata.pop("reused_speech_generation", None)
                        fallback_metadata.pop("reused_speech_orders", None)
                        fallback_metadata.pop("reused_speech_status", None)
                        fallback_metadata.pop("reused_speech_event_id", None)
                        fallback_metadata[
                            "fallback_for_undelivered_speech_event_id"
                        ] = event_id
                        fallback_args = dict(args)
                        fallback_args["metadata"] = fallback_metadata
                        fallback = await self._schedule_interaction_speech(
                            fallback_args
                        )
                        fallback["reused"] = False
                        fallback[
                            "fallback_for_undelivered_speech_event_id"
                        ] = event_id
                        return fallback
            return {
                "scheduled": True,
                "reused": True,
                "speech_event_id": event_id or None,
                "generation": generation,
                "order": orders[0],
                "orders": orders,
                "chunks": len(orders),
                "playback_started": playback_started,
                "voice_release_required": voice_release_required,
                "voice_released": await wait_for_voice_release(
                    generation, orders, playback_started
                ),
                "status": current_status() or status or "scheduled",
            }

        text = str(args.get("text") or "")
        scheduled = await self.schedule_tts_text(text, session_id)
        if scheduled.get("scheduled") is True:
            raw_orders = scheduled.get("orders")
            if not isinstance(raw_orders, list):
                raw_orders = [scheduled.get("order")]
            orders = [
                int(item)
                for item in raw_orders
                if isinstance(item, int)
                or (isinstance(item, str) and item.isdigit())
            ]
            speech_event = self._register_turn_speech_event(
                session_id=session_id,
                generation=int(scheduled.get("generation") or 0),
                orders=orders,
                text=text,
                stage=(
                    str(metadata.get("phase") or "interaction_speech")
                    if isinstance(metadata, dict)
                    else "interaction_speech"
                ),
                purpose=(
                    str(
                        metadata.get("speech_act")
                        or metadata.get("delivery_role")
                        or "response"
                    )
                    if isinstance(metadata, dict)
                    else "response"
                ),
                commitment=(
                    str(metadata.get("commitment_state") or "")
                    if isinstance(metadata, dict)
                    else ""
                ),
                fast_activity_id=(
                    str(metadata.get("fast_activity_id") or "")
                    if isinstance(metadata, dict)
                    else ""
                ),
                turn_id=(
                    str(metadata.get("turn_id") or session_id or "")
                    if isinstance(metadata, dict)
                    else str(session_id or "")
                ),
                source_goal_ids=(
                    list(metadata.get("source_goal_ids") or [])
                    if isinstance(metadata, dict)
                    and isinstance(metadata.get("source_goal_ids"), list)
                    else []
                ),
                canonical_plan_id=(
                    str(metadata.get("canonical_plan_id") or "")
                    if isinstance(metadata, dict)
                    else ""
                ),
                canonical_plan_fingerprint=(
                    str(metadata.get("canonical_plan_fingerprint") or "")
                    if isinstance(metadata, dict)
                    else ""
                ),
                goal_association_fingerprint=(
                    str(metadata.get("goal_association_fingerprint") or "")
                    if isinstance(metadata, dict)
                    else ""
                ),
                delivery_role=(
                    str(metadata.get("delivery_role") or "response")
                    if isinstance(metadata, dict)
                    else "response"
                ),
                claims=(
                    list(metadata.get("claims") or [])
                    if isinstance(metadata, dict)
                    and isinstance(metadata.get("claims"), list)
                    else []
                ),
                must_not_claim_completion=(
                    metadata.get("must_not_claim_completion")
                    if isinstance(metadata, dict)
                    and isinstance(metadata.get("must_not_claim_completion"), bool)
                    else None
                ),
            )
            if speech_event is not None:
                scheduled["speech_event_id"] = speech_event["event_id"]
        if (
            isinstance(metadata, dict)
            and (
                metadata.get("wait_for_playback_start") is True
                or voice_release_required
            )
            and scheduled.get("scheduled") is True
        ):
            default_playback_timeout_ms = int(
                getattr(
                    getattr(
                        getattr(self, "host_settings", None),
                        "playback",
                        None,
                    ),
                    "playback_start_timeout_ms",
                    20000,
                )
            )
            raw_timeout_ms = metadata.get(
                "playback_start_timeout_ms",
                default_playback_timeout_ms,
            )
            try:
                timeout_ms = int(raw_timeout_ms)
            except (TypeError, ValueError):
                timeout_ms = default_playback_timeout_ms
            playback_started = await self.wait_for_playback_start(
                generation=int(scheduled["generation"]),
                order=int(scheduled["order"]),
                session_id=session_id,
                timeout_s=max(0.001, timeout_ms / 1000.0),
            )
            scheduled["playback_started"] = playback_started
            if not playback_started:
                scheduled["cancelled_orders"] = self._cancel_scheduled_playback_before_start(
                    scheduled,
                    session_id=session_id,
                    reason="required_playback_start_not_observed",
                )
        if voice_release_required and scheduled.get("scheduled") is True:
            raw_orders = scheduled.get("orders")
            if not isinstance(raw_orders, list):
                raw_orders = [scheduled.get("order")]
            orders = [int(item) for item in raw_orders if isinstance(item, int)]
            playback_started = bool(scheduled.get("playback_started"))
            scheduled["voice_release_required"] = True
            scheduled["voice_released"] = await wait_for_voice_release(
                int(scheduled.get("generation") or 0),
                orders,
                playback_started,
            )
        return scheduled

    def ensure_playback_worker(self) -> None:
        if not hasattr(self, "playback_queue"):
            return
        playback_task = getattr(self, "playback_task", None)
        if playback_task is None or playback_task.done():
            self.playback_task = asyncio.create_task(self.playback_worker())
        self.session_idle_sweeper_task = asyncio.create_task(self._session_idle_sweeper())

    async def reset_playback_ordering(self):
        async with self.order_lock:
            self.resolve_all_playback_start_waiters(
                started=False,
                reason="reset_playback_ordering",
            )
            self.synthesis_order = 0
            self.next_playback_order = 0
            self.pending_audio.clear()
            getattr(self, "cancelled_playback_orders", set()).clear()
            while not self.playback_queue.empty():
                try:
                    self.playback_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
        self.ensure_playback_worker()





    def _owner_identity_json(self) -> str:
        try:
            context = self.mind.context()
            identity = context.get("identity", {}) if isinstance(context, dict) else {}
        except Exception as exc:
            logger.warning("direct_llm_identity_failed: %s", exc)
            identity = {}
        if not isinstance(identity, dict):
            identity = {}
        return json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))



    def _owner_mind_summary(self) -> str:
        try:
            summary = self.mind.prompt_summary()
        except Exception as exc:
            logger.warning("direct_llm_mind_summary_failed: %s", exc)
            summary = ""
        summary = " ".join(str(summary or "").split())
        if not summary:
            return "Owner-approved mind summary unavailable; rely on the supplied Self model JSON."
        if len(summary) > 1200:
            return summary[:1200].rstrip() + "..."
        return summary


    @staticmethod
    def _compact_json_for_prompt(value: Any, *, max_chars: int) -> str:
        try:
            text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        except TypeError:
            text = str(value)
        text = " ".join(text.split())
        if len(text) > max_chars:
            return text[:max_chars].rstrip() + "..."
        return text

    @staticmethod
    def _goal_list_change_by_task(
        applied_operations: list[dict[str, Any]] | None,
    ) -> dict[str, str]:
        """Map committed Goal-state operations to concise console change labels."""

        labels: dict[str, str] = {}
        priorities = {
            "unchanged": 0,
            "associated": 10,
            "updated": 20,
            "confirmed": 25,
            "resumed": 25,
            "paused": 30,
            "added": 40,
            "cancelled": 50,
            "rejected": 50,
        }
        for item in list(applied_operations or []):
            if not isinstance(item, dict) or item.get("applied") is not True:
                continue
            task_id = " ".join(str(item.get("task_id") or "").split())
            if not task_id:
                continue
            operation = str(item.get("operation") or "").strip().casefold()
            relationship = str(item.get("relationship") or "").strip().casefold()
            if operation == "create":
                label = "added"
            elif relationship in {"continue", "reference"}:
                label = "associated"
            elif operation in {"modify", "clarification_answer", "correct"}:
                label = "updated"
            elif operation == "confirm":
                label = "confirmed"
            elif operation == "resume":
                label = "resumed"
            elif operation == "pause":
                label = "paused"
            elif operation == "cancel":
                label = "cancelled"
            elif operation == "reject":
                label = "rejected"
            elif relationship:
                label = "associated"
            elif operation:
                label = "updated"
            else:
                continue
            previous = labels.get(task_id, "unchanged")
            if priorities.get(label, 1) >= priorities.get(previous, 0):
                labels[task_id] = label
        return labels

    @staticmethod
    def _goal_list_item_text(
        snapshot: dict[str, Any],
        *,
        bucket: str,
        index: int,
        total: int,
        change: str = "unchanged",
    ) -> str:
        goal = snapshot.get("goal") if isinstance(snapshot.get("goal"), dict) else {}
        metadata = (
            snapshot.get("metadata")
            if isinstance(snapshot.get("metadata"), dict)
            else {}
        )
        description = " ".join(
            str(goal.get("description") or snapshot.get("last_user_update") or "").split()
        )
        if len(description) > 180:
            description = description[:179].rstrip() + "…"
        goal_id = " ".join(
            str(snapshot.get("goal_id") or goal.get("goal_id") or "unknown").split()
        )
        responsibility = " ".join(
            str(
                snapshot.get("responsibility_status")
                or goal.get("responsibility_status")
                or "unknown"
            ).split()
        )
        work = " ".join(str(snapshot.get("work_status") or "unknown").split())
        relation = " ".join(str(metadata.get("task_relation") or "unknown").split())
        version = snapshot.get("goal_version") or goal.get("version") or 0
        marker = {
            "added": "+",
            "associated": "~",
            "updated": "~",
            "confirmed": "✓",
            "resumed": ">",
            "paused": "||",
            "cancelled": "x",
            "rejected": "x",
        }.get(change, " ")
        return (
            "goal_list_item: "
            f"change={change} marker={marker} bucket={bucket} index={index}/{total} "
            f"goal_id={goal_id} responsibility={responsibility} work={work} "
            f"relation={relation} version={version} description={description!r}"
        )

    def _log_goal_list(
        self,
        session_id: str | None,
        *,
        phase: str,
        active_goals: list[dict[str, Any]] | None,
        recent_terminal_goals: list[dict[str, Any]] | None,
        applied_operations: list[dict[str, Any]] | None = None,
    ) -> None:
        active = [item for item in list(active_goals or []) if isinstance(item, dict)]
        recent = [
            item
            for item in list(recent_terminal_goals or [])
            if isinstance(item, dict)
        ]
        change_by_task = self._goal_list_change_by_task(applied_operations)
        self.session_log(
            session_id,
            "goal_list: phase=%s active_count=%s recent_terminal_count=%s",
            phase,
            len(active),
            len(recent),
        )
        for bucket, goals in (("active", active), ("recent_terminal", recent)):
            total = len(goals)
            for index, snapshot in enumerate(goals, 1):
                task_id = " ".join(str(snapshot.get("source_task_id") or "").split())
                self.session_log(
                    session_id,
                    "%s",
                    self._goal_list_item_text(
                        snapshot,
                        bucket=bucket,
                        index=index,
                        total=total,
                        change=change_by_task.get(task_id, "unchanged"),
                    ),
                )

    def build_context(self, session_id: str | None) -> dict[str, Any]:
        conversation = self.conversation_state.snapshot()
        mind_context = self.mind.context()
        return {
            "is_speaking": self.is_playing_audio,
            "current_generation": self.playback_generation,
            "session_id": session_id,
            "conversation_id": conversation.get("conversation_id"),
            "interaction_engagement": self._interaction_engagement_context(
                conversation,
                session_id=session_id,
            ),
            "conversation": conversation,
            "session_memory": conversation.get("session_memory", {}),
            "memory_summary": (conversation.get("session_memory") or {}).get("memory_summary"),
            "extracted_memory": conversation.get("extracted_memory", []),
            "mind": mind_context,
            "core_principles": mind_context.get("core_principles", []),
            "long_term_goals": mind_context.get("long_term_goals", []),
            "experience_tuning_policy": mind_context.get("experience_tuning_policy", []),
            "history": conversation.get("history", []),
            "pending_tasks": conversation.get("pending_tasks", []),
            "active_pending_tasks": conversation.get("active_pending_tasks", []),
            "task_contexts": conversation.get("task_contexts", []),
            "active_task_contexts": conversation.get("active_task_contexts", []),
            "active_task_snapshots": conversation.get("active_task_snapshots", []),
            "active_goal_snapshots": self.conversation_state.active_goal_snapshots(),
            "recent_goal_snapshots": conversation.get("recent_goal_snapshots", []),
            "current_task_context": conversation.get("current_task_context"),
            "discourse_referents": conversation.get("discourse_referents", []),
            "discourse_focus": conversation.get("discourse_focus", []),
            "verified_tool_memory_index": conversation.get(
                "verified_tool_memory_index", []
            ),
            "recent_tool_evidence": conversation.get("recent_tool_evidence", []),
            "robot_state": {
                "available": not self.action_dry_run,
                "source": "host_orchestrator",
            },
        }

    def _interaction_engagement_context(
        self,
        conversation: dict[str, Any],
        *,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        history = conversation.get("history")
        if not isinstance(history, list):
            history = []
        active_pending = conversation.get("active_pending_tasks")
        active_tasks = conversation.get("active_task_contexts")
        has_active_work = bool(
            isinstance(active_pending, list)
            and active_pending
            or isinstance(active_tasks, list)
            and active_tasks
        )
        active_routed_turns = getattr(self, "active_turn_tasks", None)
        has_other_in_flight_turn = bool(
            isinstance(active_routed_turns, dict)
            and any(
                not task.done()
                and str(candidate_session_id or "")
                != str(session_id or "")
                for task, candidate_session_id in active_routed_turns.items()
            )
        )
        last_exchange_ms = 0.0
        for turn in history:
            if not isinstance(turn, dict):
                continue
            role = str(turn.get("role") or "").strip().casefold()
            metadata = turn.get("metadata")
            metadata = metadata if isinstance(metadata, dict) else {}
            # Gateway-suppressed room speech remains bounded evidence, but it is
            # not conversational evidence and must not open the follow-up window.
            # Admitted user turns publish this fact explicitly at the Gateway ->
            # conversation boundary. Assistant turns are user-facing dialogue by
            # construction and may extend the exchange after a slow response.
            if role == "user" and metadata.get("accepted_dialogue_evidence") is not True:
                continue
            if role not in {"user", "assistant"}:
                continue
            try:
                last_exchange_ms = max(
                    last_exchange_ms,
                    float(turn.get("ts_ms") or 0.0),
                )
            except (TypeError, ValueError):
                continue
        idle_ms = (
            max(0.0, time.time() * 1000.0 - last_exchange_ms)
            if last_exchange_ms > 0.0
            else None
        )
        recent_exchange = bool(
            idle_ms is not None
            and idle_ms <= self.addressedness_engagement_timeout_s * 1000.0
        )
        active = bool(
            has_active_work
            or has_other_in_flight_turn
            or recent_exchange
        )
        evidence = (
            "active_task"
            if has_active_work
            else "in_flight_turn"
            if has_other_in_flight_turn
            else "recent_exchange"
            if recent_exchange
            else "none"
        )
        return {
            "gate_enabled": self.addressedness_gate_enabled,
            "active": active,
            "evidence": evidence,
            "idle_ms": round(idle_ms, 1) if idle_ms is not None else None,
            "engagement_timeout_ms": round(
                self.addressedness_engagement_timeout_s * 1000.0,
                1,
            ),
        }


    def _record_experience(
        self,
        *,
        response: InteractionResponse,
        execution: CapabilityRuntimeResult | None,
        session_id: str | None,
        errors: list[str] | None = None,
    ) -> None:
        conversation_state = getattr(self, "conversation_state", None)
        capture_reference = self.sessions.interaction_session_capture_reference(
            session_id
        )
        metadata = dict(response.metadata)
        experience_context = dict(metadata.get("experience_context") or {})
        if conversation_state is not None and not str(
            experience_context.get("user_text") or ""
        ).strip():
            turn_snapshot = conversation_state.user_turn_snapshot(session_id)
            if turn_snapshot:
                experience_context["user_text"] = str(
                    turn_snapshot.get("text") or ""
                )
                experience_context.setdefault(
                    "conversation_id",
                    str(turn_snapshot.get("conversation_id") or ""),
                )
        if capture_reference is not None:
            experience_context["interaction_session_evidence"] = capture_reference
        if experience_context:
            metadata["experience_context"] = experience_context
        if metadata != response.metadata:
            response = response.model_copy(update={"metadata": metadata})
        self.sessions.update_trace_correlations(
            session_id,
            conversation_id=getattr(conversation_state, "conversation_id", None),
            interaction_id=response.interaction_id,
        )
        record = None
        try:
            record = self.experience.record_interaction(
                response=response,
                execution=execution,
                session_id=session_id,
                mind_profile=self.mind.profile,
                errors=errors,
            )
        except Exception as exc:  # pragma: no cover - defensive runtime logging
            logger.warning("Experience journal write failed: %s", exc, exc_info=True)
            self.session_log(session_id, "experience_record_failed: error=%s", exc)
        if record is not None:
            self.session_log(
                session_id,
                "experience_recorded: experience_id=%s execution_status=%s",
                record.experience_id,
                record.execution_status,
            )
        try:
            episode = self.episode_recorder.record_interaction(
                response=response,
                execution=execution,
                session_id=session_id,
                mind_profile=self.mind.profile,
                errors=errors,
            )
        except Exception as exc:  # pragma: no cover - defensive runtime logging
            logger.warning("Episode record write failed: %s", exc, exc_info=True)
            self.session_log(session_id, "episode_record_failed: error=%s", exc)
            return
        if episode is not None:
            self.sessions.update_trace_correlations(
                session_id,
                episode_id=episode.episode_id,
                conversation_id=episode.conversation_id,
                interaction_id=response.interaction_id,
            )
            self.sessions.attach_episode_evidence(
                session_id,
                episode.model_dump(mode="json"),
            )
            self.session_log(
                session_id,
                "episode_recorded: episode_id=%s conversation_id=%s turns=%s",
                episode.episode_id,
                episode.conversation_id,
                len(episode.turns),
            )

    def _record_execution_experience_safely(
        self,
        *,
        response: InteractionResponse,
        execution: CapabilityRuntimeResult | None,
        session_id: str | None,
        confirmed_request_ids: set[str] | None,
        errors: list[str] | None = None,
    ) -> None:
        """Keep observability failures outside execution/response semantics."""

        try:
            prepared = self._prepared_interaction_response_for_record(
                response,
                session_id=session_id,
                confirmed_request_ids=confirmed_request_ids,
            )
            record_kwargs: dict[str, Any] = {
                "response": prepared,
                "execution": execution,
                "session_id": session_id,
            }
            effective_errors = list(errors or ())
            metadata = (
                prepared.metadata
                if isinstance(prepared.metadata, dict)
                else {}
            )
            if metadata.get("semantic_status") == "failed":
                stage = str(metadata.get("semantic_failure_stage") or "cognition")
                failure_class = str(
                    metadata.get("semantic_failure_class") or "semantic_failure"
                )
                failure_error = str(metadata.get("semantic_failure_error") or "").strip()
                semantic_error = f"{stage}:{failure_class}"
                if failure_error:
                    semantic_error += f": {failure_error}"
                if semantic_error not in effective_errors:
                    effective_errors.append(semantic_error)
            if effective_errors:
                record_kwargs["errors"] = effective_errors
            self._record_experience(
                **record_kwargs,
            )
        except Exception as exc:  # pragma: no cover - defensive containment
            logger.warning(
                "Execution experience preparation failed: %s",
                exc,
                exc_info=True,
            )
            self.session_log(
                session_id,
                "experience_prepare_failed: error_type=%s error=%s",
                type(exc).__name__,
                exc,
            )

    @staticmethod
    def _safe_validated_response_plan_speech(text: str | None) -> str | None:
        cleaned = " ".join((text or "").strip().split())
        if not cleaned or len(cleaned) > 160:
            return None
        lowered = cleaned.casefold()
        if any(marker in lowered for marker in ("soridormi.", "chromie.")):
            return None
        return cleaned

    @staticmethod
    def _safe_immediate_route_speech(text: str | None) -> str | None:
        """Apply only transport-safe checks to source-authored immediate speech.

        Semantic wording is owned by the Planner's Communicative Activity. Typed
        Planner provenance carries the mechanical claim boundary; the Host does not add a
        second semantic LLM or infer meaning from phrases, keywords, or punctuation.
        """

        cleaned = " ".join((text or "").strip().split())
        if not cleaned or len(cleaned) > 120:
            return None
        lowered = cleaned.casefold()
        if any(marker in lowered for marker in (
            "soridormi.",
            "chromie.",
        )):
            return None
        if any(ord(char) < 32 and char not in {"\t", "\n", "\r"} for char in cleaned):
            return None
        return cleaned








    def _cognitive_gateway_adapter(self) -> CognitiveGateway:
        adapter = getattr(self, "cognitive_gateway", None)
        if adapter is None:
            adapter = CognitiveGateway()
            self.cognitive_gateway = adapter
        return adapter

    def _current_conversation_id(self, session_id: str) -> str:
        conversation_id = str(
            getattr(getattr(self, "conversation_state", None), "conversation_id", "")
            or ""
        ).strip()
        return conversation_id or session_id

    def _metadata_with_turn_envelope(
        self,
        metadata: dict[str, Any],
        turn_envelope: UserTurnEnvelope | None,
    ) -> dict[str, Any]:
        if turn_envelope is None:
            return dict(metadata)
        return {
            **metadata,
            **self._cognitive_gateway_adapter().metadata(turn_envelope),
        }

    @staticmethod

    @staticmethod
    def _cognitive_resolution_summary(
        resolution: CognitiveRuntimeResolution,
    ) -> dict[str, Any]:
        terminal = resolution.terminal_plan
        interaction = resolution.interaction_response
        return {
            "mode": resolution.mode,
            "status": resolution.status,
            "interaction_response_constructed": interaction is not None,
            "provider_request_count": (
                len(interaction.capabilities) if interaction is not None else 0
            ),
            "provider_dispatch_possible": interaction is not None,
            "plan_id": terminal.plan_id if terminal is not None else None,
            "planner_tier": terminal.planner_tier if terminal is not None else None,
            "disposition": terminal.disposition if terminal is not None else None,
            "coverage": terminal.coverage if terminal is not None else None,
            "steps": len(terminal.steps) if terminal is not None else 0,
            "timings_ms": resolution.timings_ms,
            "fallback_reason": resolution.fallback_reason,
            "metadata": resolution.metadata,
        }

    def _record_cognitive_runtime_evidence(
        self,
        resolution: CognitiveRuntimeResolution,
        *,
        session_id: str,
        user_text: str,
    ) -> None:
        try:
            self.cognitive_evidence.record(
                resolution,
                sid=session_id,
                text=user_text,
            )
        except Exception as exc:
            self.session_log(
                session_id,
                "cognitive_runtime_evidence_failed: error_type=%s error=%s",
                type(exc).__name__,
                exc,
            )

    def _record_cognitive_gateway_evidence(
        self,
        turn_envelope: UserTurnEnvelope,
        *,
        user_text: str,
        context_snapshot: Any | None = None,
        attention_review: Any | None = None,
    ) -> None:
        try:
            self.cognitive_evidence.record_gateway(
                turn_envelope,
                text=user_text,
                context_snapshot=context_snapshot,
                attention_review=attention_review,
            )
        except Exception as exc:
            self.session_log(
                turn_envelope.session_id,
                "cognitive_gateway_evidence_failed: error_type=%s error=%s",
                type(exc).__name__,
                exc,
            )

    def _goal_driven_authority_context(
        self,
        context: dict[str, Any],
        *,
        session_id: str,
        observer: bool,
    ) -> dict[str, Any]:
        return context_with_semantic_authority(
            context,
            SemanticAuthorityClaim(
                owner="goal_driven_runtime",
                role="observer" if observer else "authoritative",
                turn_id=session_id,
                reason=(
                    "cognitive_runtime_report_only"
                    if observer
                    else "cognitive_runtime_apply"
                ),
            ),
        )


    async def _run_cognitive_runtime_pipeline(
        self,
        session: aiohttp.ClientSession,
        *,
        user_text: str,
        session_id: str,
        context: dict[str, Any],
        core_interpretation: CoreInterpretationResult,
        record_evidence: bool = True,
        turn_envelope: UserTurnEnvelope | None = None,
    ) -> CognitiveRuntimeResolution:
        started_ms = now_ms()
        if turn_envelope is None:
            resolution = CognitiveRuntimeResolution(
                mode=self.cognitive_runtime_mode,
                status="error",
                timings_ms={"total": round(now_ms() - started_ms, 1)},
                fallback_reason="missing_admitted_user_turn_envelope",
                metadata={
                    "failure_stage": "cognitive_gateway_admission",
                    "failure_class": "missing_user_turn_envelope",
                    "failure_domain": "contract",
                    "architecture_attribution": "cognitive_gateway",
                    "retryable": False,
                },
            )
            if record_evidence:
                self._record_cognitive_runtime_evidence(
                    resolution,
                    session_id=session_id,
                    user_text=user_text,
                )
            self.session_log(
                session_id,
                "cognitive_runtime_rejected: reason=missing_admitted_user_turn_envelope",
            )
            return resolution
        authority_context = self._goal_driven_authority_context(
            context,
            session_id=session_id,
            observer=self.cognitive_runtime_mode != "apply",
        )
        resolved_text = user_text
        resolved_session_id = session_id
        resolved_language = core_interpretation.language or (
            "zh-CN" if self._looks_zh(user_text) else "en-US"
        )
        resolved_history = authority_context.get("history", [])
        if turn_envelope is not None:
            projection = self._cognitive_gateway_adapter().project_for_core(
                turn_envelope,
                current_text=user_text,
                current_session_id=session_id,
                context=authority_context,
            )
            resolved_text = projection.text
            resolved_session_id = projection.sid
            resolved_language = projection.language
            authority_context = projection.context
            resolved_history = projection.history
        try:
            resolution = await asyncio.wait_for(
                self.cognitive_runtime.resolve(
                    session,
                    text=resolved_text,
                    sid=resolved_session_id,
                    core_interpretation=core_interpretation,
                    context=authority_context,
                    history=resolved_history,
                    language=resolved_language,
                    turn_envelope=turn_envelope,
                ),
                timeout=self.cognitive_runtime_timeout_ms / 1000.0,
            )
        except Exception as exc:
            status = "error"
            is_timeout = isinstance(exc, (asyncio.TimeoutError, TimeoutError))
            resolution = CognitiveRuntimeResolution(
                mode=self.cognitive_runtime_mode,
                status=status,
                turn_envelope=turn_envelope,
                timings_ms={"total": round(now_ms() - started_ms, 1)},
                fallback_reason=f"{type(exc).__name__}: {str(exc)[:500]}",
                metadata={
                    "outer_timeout_ms": self.cognitive_runtime_timeout_ms,
                    "failure_stage": "cognitive_runtime_outer",
                    "failure_class": "outer_timeout" if is_timeout else type(exc).__name__,
                    "failure_domain": (
                        "orchestration_budget" if is_timeout else "cognitive_runtime"
                    ),
                    "architecture_attribution": "not_evaluated",
                    "retryable": is_timeout,
                },
            )
        if turn_envelope is not None and resolution.turn_envelope is None:
            resolution = resolution.model_copy(
                update={"turn_envelope": turn_envelope}
            )

        trace_reference = resolution.metadata.get("runtime_trace")
        if isinstance(trace_reference, dict):
            self.sessions.update_trace_correlations(
                session_id,
                cognitive_trace_id=trace_reference.get("trace_id"),
            )

        if record_evidence:
            self._record_cognitive_runtime_evidence(
                resolution, session_id=session_id, user_text=user_text
            )

        terminal = resolution.terminal_plan
        failure_stage = str(resolution.metadata.get("failure_stage") or "none")
        failure_class = str(resolution.metadata.get("failure_class") or "none")
        attribution = str(
            resolution.metadata.get("architecture_attribution") or "not_evaluated"
        )
        self.session_log(
            session_id,
            "cognitive_runtime_done: mode=%s status=%s total_ms=%.1f "
            "planner=%s disposition=%s steps=%s failure_stage=%s failure_class=%s "
            "architecture_attribution=%s fallback=%s",
            resolution.mode,
            resolution.status,
            float(resolution.timings_ms.get("total", now_ms() - started_ms)),
            terminal.planner_tier if terminal is not None else "none",
            terminal.disposition if terminal is not None else "none",
            len(terminal.steps) if terminal is not None else 0,
            failure_stage,
            failure_class,
            attribution,
            resolution.fallback_reason or "none",
        )
        return resolution



    def _named_goal_cancellation_failure_response(
        self,
        exc: Exception,
        *,
        user_text: str,
    ) -> InteractionResponse | None:
        """Render only evidence-qualified named-cancellation failures."""

        zh = self._looks_zh(user_text)
        if isinstance(exc, ActiveGoalCancellationRequiresRuntimeDispatch):
            return self._host_speech_response(
                (
                    "我还不能可靠地把这个目标和正在执行的任务一起停下，"
                    "所以没有把它标记为已取消。"
                )
                if zh
                else (
                    "I could not reliably stop the selected goal together "
                    "with its active execution, so I did not mark it cancelled."
                ),
                style="warning",
                source="host_specific_goal_cancel_not_dispatched",
            )
        if not isinstance(exc, NamedGoalCancellationClosureError):
            return None
        if exc.stage == "confirmation_scope_conflict":
            text = (
                "这个待确认动作同时属于多个目标，无法只取消其中一个；"
                "我保留了原确认和目标状态。"
                if zh
                else (
                    "That pending action is shared by multiple goals, so I "
                    "could not cancel only one of them. I kept the original "
                    "confirmation and goal state unchanged."
                )
            )
            source = "host_specific_goal_cancel_scope_conflict"
        elif exc.runtime_dispatch_attempted:
            text = (
                "我已尝试发送取消请求，但无法可靠地核对并写回这个目标的最终状态；"
                "当前结果是不确定的。"
                if zh
                else (
                    "I attempted to cancel the selected goal, but I could not "
                    "reliably verify and reconcile its final state. The result "
                    "is uncertain."
                )
            )
            source = "host_specific_goal_cancel_result_uncertain"
        else:
            text = (
                "我无法安全地更新这个目标及其确认状态，因此保留了原状态。"
                if zh
                else (
                    "I could not safely update the selected goal and its "
                    "confirmation state, so I left the original state unchanged."
                )
            )
            source = "host_specific_goal_cancel_state_unchanged"
        return self._host_speech_response(
            text,
            style="warning",
            source=source,
        )

    async def _dispatch_named_goal_cancellation(
        self,
        resolution: CognitiveRuntimeResolution,
        *,
        session_id: str,
        user_text: str,
        language: str,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Bridge the Core's semantic target to trusted cancellation closure."""

        return await dispatch_named_goal_cancellation(
            conversation_state=self.conversation_state,
            interaction_runtime=self.interaction_runtime,
            confirmation_dialogue=getattr(self, "confirmation_dialogue", None),
            resolution=resolution,
            session_id=session_id,
            user_text=user_text,
            language=language,
        )

    def _apply_cognitive_goal_state(
        self,
        resolution: CognitiveRuntimeResolution,
        *,
        session_id: str,
        user_text: str,
    ) -> list[dict[str, Any]]:
        association = resolution.goal_association
        if association is None:
            return []
        replacement_goal_ids = {
            goal_id
            for goal in association.new_goals
            for goal_id in goal.supersedes_goal_ids
        }
        if replacement_goal_ids:
            raise ActiveGoalCancellationRequiresRuntimeDispatch(
                sorted(replacement_goal_ids)
            )
        cancel_goal_ids = {
            goal_id
            for item in association.associations
            if item.relationship == "cancel"
            for goal_id in item.target_goal_ids
        }
        if cancel_goal_ids:
            snapshots = self.conversation_state.active_goal_snapshots(
                limit=self.conversation_state.max_pending_tasks
            )
            runtime_bound: list[str] = []
            for snapshot in snapshots:
                goal_id = str(snapshot.get("goal_id") or "").strip()
                if goal_id not in cancel_goal_ids:
                    continue
                status = str(snapshot.get("status") or "").strip()
                metadata = snapshot.get("metadata")
                if not isinstance(metadata, dict):
                    metadata = {}
                remaining = metadata.get("remaining_request_ids")
                if isinstance(remaining, str):
                    remaining = [remaining]
                has_remaining = bool(
                    isinstance(remaining, list)
                    and any(str(item).strip() for item in remaining)
                )
                exact_binding = all(
                    str(metadata.get(key) or "").strip()
                    for key in (
                        "interaction_id",
                        "canonical_plan_id",
                        "canonical_plan_fingerprint",
                    )
                )
                if (
                    status
                    in {
                        "awaiting_confirmation",
                        "committed",
                        "scheduled",
                        "running",
                        "paused",
                    }
                    or has_remaining
                    or exact_binding
                ):
                    runtime_bound.append(goal_id)
            if runtime_bound:
                raise ActiveGoalCancellationRequiresRuntimeDispatch(
                    runtime_bound
                )
        results = self.conversation_state.apply_goal_association_resolution(
            association,
            sid=session_id,
            user_text=user_text,
            source="goal_driven_cognitive_runtime",
            atomic=True,
        )
        rejected = [
            item
            for item in results
            if item.get("applied") is False
            and item.get("reason") != "operation_already_applied"
        ]
        if rejected:
            raise ValueError(
                "goal-state commit rejected: "
                + json.dumps(rejected, ensure_ascii=False)
            )
        return results


    def _commit_goal_association_state(
        self,
        association: GoalAssociationResolution,
        *,
        sid: str | None,
        user_text: str,
        source: str,
    ) -> list[dict[str, Any]]:
        """Commit the validated Goal Association DTO without semantic reinterpretation."""

        results = self.conversation_state.apply_goal_association_resolution(
            association,
            sid=sid,
            user_text=user_text,
            source=source,
            atomic=True,
        )
        applied = [item for item in results if item.get("applied") is True]
        if applied:
            created = [item for item in applied if item.get("operation") == "create"]
            try:
                snapshot = self.conversation_state.snapshot()
                active_goals = self.conversation_state.active_goal_snapshots(
                    limit=self.conversation_state.max_pending_tasks
                )
                recent_goals = snapshot.get("recent_goal_snapshots")
                if not isinstance(recent_goals, list):
                    recent_goals = []
                self._log_goal_list(
                    sid,
                    phase="after_association",
                    active_goals=active_goals,
                    recent_terminal_goals=recent_goals,
                    applied_operations=applied,
                )
            except (AttributeError, KeyError, RuntimeError, TypeError, ValueError) as exc:
                # Observability must never turn committed Goal state into a failed turn.
                logger.warning(
                    "goal_list_after_association_log_failed: applied=%s error_type=%s error=%s",
                    len(applied),
                    type(exc).__name__,
                    exc,
                )
        return results

    def _commit_planner_information_gaps(
        self,
        gaps_by_goal_id: dict[str, list[Any]],
        *,
        turn_id: str,
        sid: str | None,
        user_text: str,
        source: str,
    ) -> list[dict[str, Any]]:
        """Persist Fast-Planner gaps after deterministic Goal identity binding."""

        return self.conversation_state.apply_planner_information_gaps(
            gaps_by_goal_id,
            turn_id=turn_id,
            sid=sid,
            user_text=user_text,
            source=source,
        )

    async def _try_apply_cognitive_runtime(
        self,
        session: aiohttp.ClientSession,
        *,
        user_text: str,
        session_id: str,
        context: dict[str, Any],
        core_interpretation: CoreInterpretationResult,
        core_interpretation_latency_ms: float,
        turn_envelope: UserTurnEnvelope | None = None,
    ) -> bool:
        if (
            self.cognitive_runtime_mode != "apply"
            or not self.enable_agent
            or not self.enable_interaction_response
        ):
            return False

        # Maintained apply mode gives the first HOW/wording decision to Fast Planner.
        # Goal Interpretation contributes Responsibility evidence only.
        fast_first_hedge = None
        runtime_context = dict(context)
        self.session_log(
            session_id,
            "goal_progress_communication_owner=fast_planner_advance gi_speech_bypassed=true",
        )
        resolution = await self._run_cognitive_runtime_pipeline(
            session,
            user_text=user_text,
            session_id=session_id,
            context=runtime_context,
            core_interpretation=core_interpretation,
            record_evidence=False,
            turn_envelope=turn_envelope,
        )
        if turn_envelope is not None and resolution.turn_envelope is None:
            resolution = resolution.model_copy(
                update={"turn_envelope": turn_envelope}
            )
        fast_planner_vocal_scheduled = bool(
            resolution.fast_advance is not None
            and resolution.metadata.get("fast_vocal_activity_ids")
        )
        summary = self._cognitive_resolution_summary(resolution)
        if resolution.status != "applied" or resolution.interaction_response is None:
            fallback_started_ms = now_ms()
            fast_first_scheduled = fast_planner_vocal_scheduled
            safe_response = self._cognitive_core_exception_safe_response(
                user_text,
                failure_stage=str(
                    resolution.metadata.get("failure_stage")
                    or "cognitive_runtime"
                ),
                failure_class=str(
                    resolution.metadata.get("failure_class")
                    or resolution.fallback_reason
                    or resolution.status
                ),
                failure_error=str(resolution.fallback_reason or ""),
            )
            record_session_workflow_stage(
                self,
                session_id,
                stage="fallback_speech",
                started_monotonic_ms=fallback_started_ms,
                finished_monotonic_ms=now_ms(),
                status="selected",
                input_payload={
                    "cognitive_runtime_status": resolution.status,
                    "failure_stage": resolution.metadata.get("failure_stage"),
                    "fallback_reason": resolution.fallback_reason,
                    "user_text": user_text,
                },
                output_payload=safe_response,
                errors=list(resolution.metadata.get("stage_diagnostics") or []),
            )
            self.conversation_state.record_user_turn(
                session_id,
                user_text,
                metadata=self._metadata_with_turn_envelope(
                    {
                        "source": "goal_driven_cognitive_runtime",
                        "semantic_task_resolution_authoritative": True,
                        "cognitive_runtime_resolution": summary,
                        "semantic_status": "failed",
                        "semantic_failure_stage": str(
                            resolution.metadata.get("failure_stage")
                            or "cognitive_runtime"
                        ),
                        "semantic_failure_class": str(
                            resolution.metadata.get("failure_class")
                            or resolution.fallback_reason
                            or resolution.status
                        ),
                        "canonical_goal_committed": (
                            resolution.metadata.get("goal_state_commit_stage")
                            == "goal_association"
                        ),
                    },
                    turn_envelope,
                ),
            )
            self.conversation_state.record_interaction_response(session_id, safe_response)
            await self._queue_response_social_attention(
                safe_response,
                session_id=session_id,
            )
            self._record_cognitive_runtime_evidence(
                resolution, session_id=session_id, user_text=user_text
            )
            self._launch_interaction(
                safe_response,
                session_id,
                reset_playback=not fast_first_scheduled,
            )
            return True

        response = resolution.interaction_response.model_copy(deep=True)
        try:
            response_metadata = self._metadata_with_turn_envelope(
                {
                    **response.metadata,
                    "language": core_interpretation.language,
                    "cognitive_runtime_resolution": summary,
                    "goal_interpretation": core_interpretation.model_dump(mode="json"),
                    "experience_context": {
                        "user_text": user_text,
                        "goal_interpretation_confidence": core_interpretation.confidence,
                        "goal_interpretation_unresolved": list(core_interpretation.unresolved),
                        "goal_interpretation_latency_ms": core_interpretation_latency_ms,
                        "cognitive_runtime_latency_ms": float(
                            resolution.timings_ms.get("total", 0.0)
                        ),
                    },
                },
                turn_envelope,
            )
            response = response.model_copy(
                deep=True,
                update={
                    "metadata": response_metadata,
                },
            )
            replacement_goal_ids = replacement_target_goal_ids(resolution)
            cancellation_goal_ids = cancellation_target_goal_ids(resolution)
            if replacement_goal_ids:
                goal_state_results, replacement_metadata = (
                    await dispatch_goal_replacement(
                        conversation_state=self.conversation_state,
                        interaction_runtime=self.interaction_runtime,
                        confirmation_dialogue=getattr(self, "confirmation_dialogue", None),
                        resolution=resolution,
                        session_id=session_id,
                        user_text=user_text,
                        language=core_interpretation.language,
                    )
                )
                response = self.interaction_runtime.prepare_response(
                    response, session_id=session_id
                )
                response.metadata = {
                    **response.metadata,
                    "goal_state_results": goal_state_results,
                    "goal_replacement": replacement_metadata,
                }
                resolution.goal_state_results = goal_state_results
                resolution.metadata = {
                    **resolution.metadata,
                    "host_commit_status": "goal_replacement_work_stopped_and_committed",
                    "goal_replacement": replacement_metadata,
                }
            elif cancellation_goal_ids:
                goal_state_results, cancellation_metadata = (
                    await self._dispatch_named_goal_cancellation(
                        resolution,
                        session_id=session_id,
                        user_text=user_text,
                        language=core_interpretation.language,
                    )
                )
                zh = self._looks_zh(user_text)
                coaffected = cancellation_metadata.get("coaffected_goal_ids") or []
                replacement_prompt = str(
                    cancellation_metadata.get(
                        "replacement_confirmation_prompt"
                    )
                    or ""
                ).strip()
                if coaffected:
                    text = (
                        "已取消你指定的目标。由于执行器只支持更宽的停止范围，"
                        "相关的正在执行工作也已停止。"
                        if zh
                        else (
                            "I cancelled the selected goal. Because the provider "
                            "supports only a wider stop scope, related active work "
                            "was stopped as well."
                        )
                    )
                else:
                    text = (
                        "已取消你指定的目标。"
                        if zh
                        else "I cancelled the selected goal."
                    )
                if replacement_prompt:
                    text = f"{text} {replacement_prompt}"
                response = self._host_speech_response(
                    text,
                    style="brief",
                    source="host_named_goal_cancellation_reconciled",
                )
                response = response.model_copy(
                    deep=True,
                    update={
                        "metadata": self._metadata_with_turn_envelope(
                            {
                                **response.metadata,
                                "cognitive_runtime_apply": True,
                                "goal_state_results": goal_state_results,
                                "named_goal_cancellation": cancellation_metadata,
                                "cognitive_runtime_resolution": summary,
                            },
                            turn_envelope,
                        )
                    },
                )
                response = self.interaction_runtime.prepare_response(
                    response, session_id=session_id
                )
                resolution.interaction_response = response
                resolution.goal_state_results = goal_state_results
                resolution.metadata = {
                    **resolution.metadata,
                    "host_commit_status": (
                        "named_goal_cancellation_dispatched_and_reconciled"
                    ),
                    "named_goal_cancellation": cancellation_metadata,
                }
            else:
                response = self.interaction_runtime.prepare_response(
                    response, session_id=session_id
                )
                if (
                    str(
                        resolution.metadata.get("goal_state_commit_stage")
                        or ""
                    )
                    == "goal_association"
                ):
                    goal_state_results = list(resolution.goal_state_results)
                else:
                    goal_state_results = self._apply_cognitive_goal_state(
                        resolution,
                        session_id=session_id,
                        user_text=user_text,
                    )
                response.metadata = {
                    **response.metadata,
                    "goal_state_results": goal_state_results,
                }
                resolution.goal_state_results = goal_state_results
                resolution.metadata = {
                    **resolution.metadata,
                    "host_commit_status": "prepared_and_goal_state_committed",
                }
        except Exception as exc:
            cancellation_failure_response = (
                self._named_goal_cancellation_failure_response(
                    exc,
                    user_text=user_text,
                )
                if cancellation_goal_ids
                else None
            )
            self.session_log(
                session_id,
                "cognitive_runtime_commit_failed: error_type=%s error=%s",
                type(exc).__name__,
                exc,
            )
            fast_first_scheduled = fast_planner_vocal_scheduled
            resolution = resolution.model_copy(
                deep=True,
                update={
                    "status": "error",
                    "fallback_reason": f"host_commit_failed:{type(exc).__name__}:{str(exc)[:300]}",
                    "interaction_response": None,
                    "metadata": {
                        **resolution.metadata,
                        "host_commit_status": "rejected",
                    },
                },
            )
            summary = self._cognitive_resolution_summary(resolution)
            safe_response = (
                cancellation_failure_response
                or self._host_speech_response(
                    "这次计划没有通过执行验证，所以我没有继续。"
                    if self._looks_zh(user_text)
                    else (
                        "That plan did not pass execution validation, "
                        "so I stopped before acting."
                    ),
                    style="warning",
                    source="host_cognitive_runtime_commit_failure",
                )
            )
            record_session_workflow_stage(
                self,
                session_id,
                stage="fallback_speech",
                started_monotonic_ms=now_ms(),
                finished_monotonic_ms=now_ms(),
                status="selected",
                input_payload={
                    "failure_stage": "host_commit",
                    "fallback_reason": resolution.fallback_reason,
                    "user_text": user_text,
                },
                output_payload=safe_response,
                errors=[
                    {"error_type": type(exc).__name__, "error": str(exc)}
                ],
            )
            self.conversation_state.record_user_turn(
                session_id,
                user_text,
                metadata=self._metadata_with_turn_envelope(
                    {
                        "source": "goal_driven_cognitive_runtime",
                        "semantic_task_resolution_authoritative": True,
                        "cognitive_runtime_resolution": summary,
                    },
                    turn_envelope,
                ),
            )
            self.conversation_state.record_interaction_response(session_id, safe_response)
            self._record_cognitive_runtime_evidence(
                resolution, session_id=session_id, user_text=user_text
            )
            self._launch_interaction(
                safe_response, session_id, reset_playback=not fast_first_scheduled
            )
            return True

        self.conversation_state.record_user_turn(
            session_id,
            user_text,
            metadata=self._metadata_with_turn_envelope(
                {
                    "source": "goal_driven_cognitive_runtime",
                    "confidence": core_interpretation.confidence,
                    "semantic_task_resolution_authoritative": True,
                    "cognitive_runtime_resolution": summary,
                    **(
                        {
                            "semantic_status": "terminal_without_canonical_goal",
                            "canonical_goal_committed": False,
                        }
                        if resolution.metadata.get("terminal_goal_interpretation") is True
                        else {}
                    ),
                },
                turn_envelope,
            ),
        )
        self._record_cognitive_runtime_evidence(
            resolution, session_id=session_id, user_text=user_text
        )
        self.session_log(
            session_id,
            "cognitive_interaction_ready: speech=%s capabilities=%s requires_confirmation=%s",
            len(response.speech),
            len(response.capabilities),
            response.requires_confirmation,
        )
        for request in response.capabilities:
            self.session_log(
                session_id,
                "cognitive_capability_proposed: request_id=%s capability_id=%s timing=%s "
                "requires_confirmation=%s args=%s",
                request.request_id,
                request.capability_id,
                request.timing,
                request.requires_confirmation,
                json.dumps(request.args, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            )
        fast_first_scheduled = fast_planner_vocal_scheduled
        if await self._stage_interaction_confirmation(
            response,
            session_id,
            language=core_interpretation.language,
            reset_playback=not fast_first_scheduled,
        ):
            return True
        self.conversation_state.record_interaction_response(session_id, response)
        self._launch_interaction(
            response, session_id, reset_playback=not fast_first_scheduled
        )
        return True






    async def handle_routed_text(
        self,
        user_text: str,
        session_id: str,
        *,
        channel: str = "voice",
    ) -> None:
        gateway = self._cognitive_gateway_adapter()
        turn_capture = gateway.capture(
            user_text,
            session_id=session_id,
            conversation_id=self._current_conversation_id(session_id),
            channel=channel,
        )
        reflex_outcome = turn_capture.reflex_candidate
        if reflex_outcome.action == "interrupt":
            self.session_log(
                session_id,
                "cognitive_gateway_reflex_detected: action=%s trigger=%s scope=%s confidence=%.2f",
                reflex_outcome.action,
                reflex_outcome.trigger,
                reflex_outcome.cancellation_scope,
                reflex_outcome.confidence,
            )
            revoked_confirmation = self._revoke_pending_confirmation_for_reflex(
                reflex_outcome
            )
            # The approval token is revoked synchronously before the first
            # await, so slow trusted-provider cancellation cannot leave an old
            # action approvable. Persistence and goal-state reconciliation run
            # only after interruption has begun, so they cannot delay stopping.
            try:
                cancellation_receipt = await self._apply_reflex_cancellation(
                    reflex_outcome,
                    source_turn_id=session_id,
                )
            except BaseException:
                # The approval token was already revoked synchronously. If the
                # operational dispatch itself cannot return a receipt, retain
                # that revocation through the compatibility state path before
                # propagating the failure.
                self._reconcile_revoked_confirmation_for_reflex(
                    revoked_confirmation,
                    session_id,
                    cancellation_scope=reflex_outcome.cancellation_scope,
                )
                raise
            cancellation_reconciliation = (
                self._reconcile_reflex_cancellation_receipt(
                    cancellation_receipt,
                    revoked_confirmation,
                    session_id,
                    user_text=user_text,
                    cancellation_scope=reflex_outcome.cancellation_scope,
                    )
            )
            cancelled_confirmation = dict(
                cancellation_reconciliation.get(
                    "cancelled_confirmation"
                )
                or {}
            )
            reflex_metadata = dict(reflex_outcome.metadata)
            if cancelled_confirmation:
                reflex_metadata["cancelled_confirmation"] = (
                    cancelled_confirmation
                )
            reflex_metadata["cancellation_goal_reconciliation"] = (
                cancellation_reconciliation
            )
            reflex_outcome = reflex_outcome.model_copy(
                update={"metadata": reflex_metadata}
            )
            turn_capture = gateway.with_reflex_outcome(
                turn_capture,
                reflex_outcome,
            )
            turn_envelope = gateway.for_reflex(turn_capture)
            self._record_cognitive_gateway_evidence(
                turn_envelope,
                user_text=user_text,
            )
            self.conversation_state.record_user_turn(
                session_id,
                user_text,
                metadata=self._metadata_with_turn_envelope(
                    {
                        "source": "cognitive_gateway_reflex",
                        "confidence": reflex_outcome.confidence,
                        "reflex_outcome": reflex_outcome.model_dump(mode="json"),
                        "cancellation_dispatch_receipt": (
                            cancellation_receipt.model_dump(mode="json")
                        ),
                        "cancellation_goal_reconciliation": (
                            cancellation_reconciliation
                        ),
                    },
                    turn_envelope,
                ),
            )
            self.session_log(
                session_id,
                "cognitive_gateway_reflex_applied: action=%s trigger=%s goal_interpretation_bypassed=True",
                reflex_outcome.action,
                reflex_outcome.trigger,
            )
            state = self.sessions.state.get(session_id)
            if state is not None:
                state["llm_done"] = True
            self.maybe_session_done(session_id)
            return

        confirmation_envelope = gateway.for_confirmation(turn_capture)
        if await self._handle_confirmation_reply(
            user_text,
            session_id,
            turn_envelope=confirmation_envelope,
        ):
            return

        if reflex_outcome.action == "ignore":
            turn_envelope = gateway.for_suppression(turn_capture)
            self._record_cognitive_gateway_evidence(
                turn_envelope,
                user_text=user_text,
            )
            self.conversation_state.record_user_turn(
                session_id,
                user_text,
                metadata=self._metadata_with_turn_envelope(
                    {
                        "source": "cognitive_gateway_reflex",
                        "confidence": reflex_outcome.confidence,
                        "reflex_outcome": reflex_outcome.model_dump(mode="json"),
                    },
                    turn_envelope,
                ),
            )
            self.session_log(
                session_id,
                "cognitive_gateway_reflex_applied: action=%s trigger=%s goal_interpretation_bypassed=True",
                reflex_outcome.action,
                reflex_outcome.trigger,
            )
            state = self.sessions.state.get(session_id)
            if state is not None:
                state["llm_done"] = True
            self.maybe_session_done(session_id)
            return

        boundary = self.conversation_state.prepare_for_user_text(user_text, session_id)
        turn_capture = gateway.with_conversation_id(
            turn_capture,
            boundary.get("conversation_id"),
        )
        if boundary.get("started_new"):
            self.session_log(
                session_id,
                "conversation_boundary: started_new=True conversation_id=%s reason=%s",
                boundary.get("conversation_id"),
                boundary.get("reason"),
            )

        session = await self.get_http_session()
        context = self.build_context(session_id)
        interaction_ledger = getattr(
            getattr(self, "cognitive_runtime", None),
            "interaction_ledger",
            None,
        )
        if interaction_ledger is not None:
            context["interaction_context"] = interaction_ledger.context(
                str(session_id or ""),
                turn_id=turn_capture.turn_id,
            ).model_dump(mode="json")
        turn_capture = gateway.with_conversation_id(
            turn_capture,
            context.get("conversation_id"),
        )
        self.sessions.update_trace_correlations(
            session_id,
            conversation_id=context.get("conversation_id"),
        )
        self.session_log(
            session_id,
            "context_snapshot: conversation_id=%s history_turns=%s pending_tasks=%s engagement=%s",
            context.get("conversation_id"),
            len(context.get("history", [])),
            len(context.get("active_pending_tasks", [])),
            json.dumps(
                context.get("interaction_engagement", {}),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
        )
        self._log_goal_list(
            session_id,
            phase="before_turn",
            active_goals=context.get("active_goal_snapshots") or [],
            recent_terminal_goals=context.get("recent_goal_snapshots") or [],
        )
        context_snapshot = gateway.assemble_context(turn_capture, context)
        attention_request = gateway.attention_request(
            turn_capture,
            context_snapshot,
        )
        attention_started_ms = now_ms()
        attention_errors: list[dict[str, str]] = []
        try:
            review_attention = self.agent_client.review_attention
            attention_review = await review_attention(
                session,
                request=attention_request,
            )
        except Exception as exc:
            attention_errors.append(
                {"error_type": type(exc).__name__, "error": str(exc)}
            )
            logger.warning(
                "Cognitive Gateway attention review failed open: %s",
                exc,
            )
            attention_review = gateway.attention_fail_open(
                attention_request,
                reason=f"attention review unavailable: {type(exc).__name__}",
            )
        record_session_workflow_stage(
            self,
            session_id,
            stage="cognitive_gateway_attention",
            started_monotonic_ms=attention_started_ms,
            finished_monotonic_ms=now_ms(),
            status=("failed_open" if attention_errors else "accepted"),
            input_payload={
                "user_turn": turn_capture,
                "context_snapshot": context_snapshot,
            },
            output_payload=attention_review,
            errors=attention_errors,
        )
        turn_envelope = gateway.admit_attention(
            turn_capture,
            context_snapshot,
            attention_review,
        )
        self._record_cognitive_gateway_evidence(
            turn_envelope,
            user_text=user_text,
            context_snapshot=context_snapshot,
            attention_review=attention_review,
        )
        self.session_log(
            session_id,
            "cognitive_gateway_attention_done: disposition=%s speech_act=%s confidence=%.2f source=%s",
            attention_review.disposition,
            attention_review.speech_act,
            attention_review.confidence,
            attention_review.source,
        )
        if turn_envelope.admission == "suppress":
            self.conversation_state.record_user_turn(
                session_id,
                user_text,
                metadata=self._metadata_with_turn_envelope(
                    {
                        "source": attention_review.source,
                        "confidence": attention_review.confidence,
                        "speech_act": attention_review.speech_act,
                        "reason": attention_review.reason,
                    },
                    turn_envelope,
                ),
            )
            state = self.sessions.state.get(session_id)
            if state is not None:
                state["llm_done"] = True
            self.maybe_session_done(session_id)
            return

        # Admission is already trusted dialogue evidence even though Goal
        # Association has not run yet. Publish only the user utterance here so a
        # concurrent follow-up can resolve ellipsis/reference against it. Canonical
        # Goal and Task state remains model-owned and is committed later.
        self.conversation_state.record_accepted_user_turn(
            session_id,
            user_text,
            metadata=self._metadata_with_turn_envelope(
                {
                    "source": "cognitive_gateway_admitted_dialogue",
                    "admission": turn_envelope.admission,
                },
                turn_envelope,
            ),
        )
        core_start_ms = now_ms()
        self.session_log(
            session_id,
            "cognitive_core_start: text_chars=%s text=%r admission=%s",
            len(user_text),
            user_text,
            turn_envelope.admission,
        )
        try:
            core_interpretation = await self.agent_client.interpret_turn(
                session,
                turn_envelope=turn_envelope,
                context_snapshot=context_snapshot,
            )
            core_interpretation_latency_ms = now_ms() - core_start_ms
            self.session_log(
                session_id,
                "cognitive_core_done: core_ms=%.1f responsibilities=%s confidence=%.2f unresolved=%s authority=%s",
                core_interpretation_latency_ms,
                len(core_interpretation.responsibilities),
                core_interpretation.confidence,
                len(core_interpretation.unresolved),
                core_interpretation.authority,
            )
            record_session_workflow_stage(
                self,
                session_id,
                stage="goal_interpretation",
                started_monotonic_ms=core_start_ms,
                finished_monotonic_ms=now_ms(),
                status="accepted",
                input_payload={
                    "user_turn_envelope": turn_envelope,
                    "context_snapshot": context_snapshot,
                },
                output_payload={
                    "core_interpretation": core_interpretation,
                },
                errors=[],
            )
        except Exception as exc:
            record_session_workflow_stage(
                self,
                session_id,
                stage="goal_interpretation",
                started_monotonic_ms=core_start_ms,
                finished_monotonic_ms=now_ms(),
                status="failed",
                input_payload={
                    "user_turn_envelope": turn_envelope,
                    "context_snapshot": context_snapshot,
                },
                output_payload=None,
                errors=[
                    {"error_type": type(exc).__name__, "error": str(exc)}
                ],
            )
            self.session_log(session_id, "cognitive_core_exception: core_ms=%.1f error=%s", now_ms() - core_start_ms, exc)
            logger.warning("Cognitive Core interpretation failed; falling back safely: %s", exc)
            safe_response = self._cognitive_core_exception_safe_response(
                user_text,
                context=context,
                failure_stage="goal_interpretation",
                failure_class=type(exc).__name__,
                failure_error=str(exc),
            )
            self.conversation_state.record_user_turn(
                session_id,
                user_text,
                metadata=self._metadata_with_turn_envelope(
                    {
                        "source": "cognitive_core_exception",
                        "error": str(exc),
                        "semantic_status": "failed",
                        "semantic_failure_stage": "goal_interpretation",
                        "semantic_failure_class": type(exc).__name__,
                        "canonical_goal_committed": False,
                    },
                    turn_envelope,
                ),
            )
            self.session_log(
                session_id,
                "cognitive_core_exception_safe_fallback: embodied=%s text=%r",
                bool(safe_response.metadata.get("embodied_request")),
                user_text,
            )
            record_session_workflow_stage(
                self,
                session_id,
                stage="fallback_speech",
                started_monotonic_ms=now_ms(),
                finished_monotonic_ms=now_ms(),
                status="selected",
                input_payload={
                    "failure_stage": "goal_interpretation",
                    "user_text": user_text,
                },
                output_payload=safe_response,
                errors=[
                    {"error_type": type(exc).__name__, "error": str(exc)}
                ],
            )
            self.conversation_state.record_interaction_response(session_id, safe_response)
            self._launch_interaction(safe_response, session_id)
            return

        handled = await self._try_apply_cognitive_runtime(
            session,
            user_text=user_text,
            session_id=session_id,
            context=context,
            core_interpretation=core_interpretation,
            core_interpretation_latency_ms=core_interpretation_latency_ms,
            turn_envelope=turn_envelope,
        )
        if handled:
            return

        # The maintained architecture has no compatibility fallback. Once Goal
        # Interpretation has produced Responsibility evidence, execution may only
        # continue through the goal-driven Cognitive Runtime. A disabled or
        # unavailable runtime therefore fails closed instead of reconstructing a
        # retired route/intent projection or entering a second semantic pipeline.
        safe_response = self._host_speech_response(
            "咦，我现在还做不了这个。"
            if self._looks_zh(user_text)
            else "Oh, I can't do that right now.",
            style="warning",
            source="host_cognitive_runtime_unavailable",
        )
        self.conversation_state.record_user_turn(
            session_id,
            user_text,
            metadata=self._metadata_with_turn_envelope(
                {
                    "source": "goal_driven_cognitive_runtime",
                    "semantic_status": "failed",
                    "semantic_failure_stage": "cognitive_runtime_entry",
                    "semantic_failure_class": "runtime_unavailable",
                    "canonical_goal_committed": False,
                    "goal_interpretation": core_interpretation.model_dump(mode="json"),
                },
                turn_envelope,
            ),
        )
        self.conversation_state.record_interaction_response(session_id, safe_response)
        await self._queue_response_social_attention(
            safe_response,
            session_id=session_id,
        )
        self._launch_interaction(safe_response, session_id)
        return


    async def _stage_interaction_confirmation(
        self,
        response: InteractionResponse,
        session_id: str,
        *,
        language: str | None,
        reset_playback: bool = True,
    ) -> bool:
        confirmation_request_ids = (
            await self.interaction_runtime.confirmation_request_ids(response)
        )
        if not confirmation_request_ids:
            return False

        confirmation_prompt = str(
            (response.metadata or {}).get("confirmation_prompt") or ""
        ).strip()
        pending = self.confirmation_dialogue.begin(
            response,
            confirmed_request_ids=confirmation_request_ids,
            origin_session_id=session_id,
            conversation_id=self.conversation_state.conversation_id,
            language=language,
            prompt_override=confirmation_prompt or None,
        )
        self.session_log(
            session_id,
            "confirmation_requested: confirmation_id=%s interaction_id=%s "
            "request_ids=%s fingerprint=%s expires_at=%.3f",
            pending.confirmation_id,
            response.interaction_id,
            ",".join(sorted(pending.confirmed_request_ids)),
            pending.fingerprint,
            pending.expires_at,
        )
        prompt_response = self._host_speech_response(
            pending.prompt,
            style="confirm",
        )
        prompt_response = prompt_response.model_copy(
            deep=True,
            update={
                "metadata": {
                    **prompt_response.metadata,
                    "history_after_successful_delivery": True,
                    "confirmation_id": pending.confirmation_id,
                }
            },
        )
        record_confirmation_scope = getattr(
            self.conversation_state,
            "record_confirmation_scope",
            None,
        )
        if callable(record_confirmation_scope):
            record_confirmation_scope(
                sid=session_id,
                confirmation_id=pending.confirmation_id,
                interaction_id=response.interaction_id,
                fingerprint=pending.fingerprint,
                expires_at=pending.expires_at,
                response=response,
                confirmed_request_ids=set(pending.confirmed_request_ids),
            )
        else:  # pragma: no cover - compatibility with lightweight test doubles
            self.conversation_state.record_pending_task(
                sid=session_id,
                task_type="confirmation",
                status="awaiting_confirmation",
                summary=", ".join(
                    request.capability_id
                    for request in response.capabilities
                    if request.request_id in pending.confirmed_request_ids
                ),
                metadata={
                    "confirmation_id": pending.confirmation_id,
                    "interaction_id": response.interaction_id,
                    "fingerprint": pending.fingerprint,
                    "expires_at": pending.expires_at,
                },
            )
        self._launch_interaction(
            prompt_response,
            session_id,
            reset_playback=reset_playback,
        )
        return True

    async def _handle_confirmation_reply(
        self,
        user_text: str,
        session_id: str,
        *,
        turn_envelope: UserTurnEnvelope | None = None,
    ) -> bool:
        pending = self.confirmation_dialogue.pending
        if pending is None:
            return False
        meaning = await self._resolve_pending_confirmation_meaning(
            user_text,
            session_id=session_id,
            pending=pending,
        )
        resolution = self.confirmation_dialogue.resolve(
            meaning,
            expected_confirmation_id=pending.confirmation_id,
        )
        if resolution.decision == "not_confirmation":
            return False

        self.conversation_state.record_user_turn(
            session_id,
            user_text,
            metadata=self._metadata_with_turn_envelope(
                {
                    "confirmation_id": resolution.confirmation_id,
                    "fingerprint": resolution.fingerprint,
                },
                turn_envelope,
            ),
        )
        self.session_log(
            session_id,
            "confirmation_reply: confirmation_id=%s decision=%s fingerprint=%s",
            resolution.confirmation_id,
            resolution.decision,
            resolution.fingerprint,
        )
        if resolution.confirmation_id:
            resolve_confirmation_scope = getattr(
                self.conversation_state,
                "resolve_confirmation_scope",
                None,
            )
            handled = bool(
                callable(resolve_confirmation_scope)
                and resolve_confirmation_scope(
                    confirmation_id=resolution.confirmation_id,
                    decision=resolution.decision,
                )
            )
            if not handled:
                pending_status = {
                    "approved": "done",
                    "expired": "expired",
                }.get(resolution.decision, "cancelled")
                self.conversation_state.update_pending_task_status(
                    metadata_key="confirmation_id",
                    metadata_value=resolution.confirmation_id,
                    status=pending_status,
                )

        if resolution.decision == "approved":
            if resolution.response is None:
                raise RuntimeError(
                    "approved confirmation resolution is missing its bound response"
                )
            self.session_log(
                session_id,
                "confirmation_authorized: confirmation_id=%s interaction_id=%s "
                "request_ids=%s fingerprint=%s",
                resolution.confirmation_id,
                resolution.response.interaction_id,
                ",".join(sorted(resolution.confirmed_request_ids)),
                resolution.fingerprint,
            )
            self.conversation_state.record_interaction_response(
                session_id,
                resolution.response,
                confirmed_request_ids=set(resolution.confirmed_request_ids),
            )
            self._launch_interaction(
                resolution.response,
                session_id,
                confirmed_request_ids=set(resolution.confirmed_request_ids),
            )
            return True

        self.session_log(
            session_id,
            "confirmation_rejected: confirmation_id=%s reason=%s fingerprint=%s",
            resolution.confirmation_id,
            resolution.decision,
            resolution.fingerprint,
        )
        response = self._host_speech_response(
            resolution.message,
            style="warning" if resolution.decision in {"ambiguous", "expired"} else "brief",
        )
        self.conversation_state.record_interaction_response(session_id, response)
        self._launch_interaction(response, session_id)
        return True

    async def _resolve_pending_confirmation_meaning(
        self,
        user_text: str,
        *,
        session_id: str,
        pending: PendingConfirmation,
    ) -> ConfirmationReplyMeaning:
        """Ask Goal Association for meaning; never infer it from user phrases."""

        pending_goal_ids = pending_confirmation_goal_ids(pending)
        if not pending_goal_ids:
            self.session_log(
                session_id,
                "confirmation_semantics_failed_closed: confirmation_id=%s reason=missing_goal_scope",
                pending.confirmation_id,
            )
            return "ambiguous"
        context = self.build_context(session_id)
        context = {
            **context,
            "pending_confirmation_scope": {
                "confirmation_id": pending.confirmation_id,
                "goal_ids": sorted(pending_goal_ids),
            },
        }
        request = CognitiveWorkRequest(
            sid=session_id,
            text=user_text,
            language="zh-CN" if self._looks_zh(user_text) else "en-US",
            responsibilities=[
                CognitiveResponsibilityProposal(
                    local_ref="pending_confirmation_reply",
                    outcome=user_text,
                    confidence=1.0,
                )
            ],
            interpretation_confidence=1.0,
            context=context,
            history=list(context.get("history", [])),
        )
        try:
            session = await self.get_http_session()
            association = await self.agent_client.resolve_goal_association(
                session,
                request=request,
                timeout_ms=self.goal_association_timeout_ms,
            )
        except Exception as exc:
            self.session_log(
                session_id,
                "confirmation_semantics_failed_closed: confirmation_id=%s reason=%s error=%s",
                pending.confirmation_id,
                type(exc).__name__,
                str(exc)[:300],
            )
            return "ambiguous"
        meaning = confirmation_meaning_from_goal_association(
            association,
            pending_goal_ids=pending_goal_ids,
        )
        self.session_log(
            session_id,
            "confirmation_semantics_resolved: confirmation_id=%s meaning=%s relationships=%s targets=%s",
            pending.confirmation_id,
            meaning,
            ",".join(item.relationship for item in association.associations) or "none",
            ",".join(
                sorted(
                    goal_id
                    for item in association.associations
                    for goal_id in item.target_goal_ids
                )
            )
            or "none",
        )
        return meaning

    def _revoke_pending_confirmation_for_reflex(
        self,
        outcome: ReflexOutcome,
    ) -> Any | None:
        """Revoke an approval token synchronously, before interruption awaits."""

        dialogue = getattr(self, "confirmation_dialogue", None)
        if outcome.cancellation_scope in {"output_only", "media_output"}:
            return None
        if outcome.cancellation_scope == "embodied_motion":
            pending = getattr(dialogue, "pending", None)
            if pending is None:
                return None
            confirmed = set(
                getattr(pending, "confirmed_request_ids", ()) or ()
            )
            response = getattr(pending, "response", None)
            requests = getattr(response, "capabilities", ()) or ()
            registry = getattr(
                getattr(self, "interaction_runtime", None),
                "registry",
                None,
            )
            has_motion = False
            seen_confirmed_request_ids: set[str] = set()
            unknown_confirmed_request = False
            for request in requests:
                if request.request_id not in confirmed:
                    continue
                seen_confirmed_request_ids.add(request.request_id)
                try:
                    definition = registry.get(request.capability_id)
                except (AttributeError, ValueError):
                    unknown_confirmed_request = True
                    continue
                if "embodied_motion" in definition.cancellation_domains:
                    has_motion = True
                    break
            if confirmed - seen_confirmed_request_ids:
                unknown_confirmed_request = True
            if not has_motion and not unknown_confirmed_request:
                return None
        cancel = getattr(dialogue, "cancel", None)
        return cancel() if callable(cancel) else None

    def _revoked_confirmation_evidence_for_reflex(
        self,
        pending: Any | None,
        *,
        cancellation_scope: str,
    ) -> dict[str, Any]:
        """Describe a synchronously revoked token without mutating Goal state."""

        if pending is None:
            return {}
        confirmation_id = str(getattr(pending, "confirmation_id", "") or "")
        fingerprint = str(getattr(pending, "fingerprint", "") or "")
        confirmed_request_ids = sorted(
            str(item)
            for item in (
                getattr(pending, "confirmed_request_ids", ()) or ()
            )
        )
        motion_request_ids: set[str] = set()
        unknown_request_ids: set[str] = set()
        response = getattr(pending, "response", None)
        registry = getattr(
            getattr(self, "interaction_runtime", None),
            "registry",
            None,
        )
        request_by_id = {
            str(request.request_id): request
            for request in (getattr(response, "capabilities", ()) or ())
        }
        for request_id in confirmed_request_ids:
            request = request_by_id.get(request_id)
            if request is None:
                unknown_request_ids.add(request_id)
                continue
            try:
                definition = registry.get(request.capability_id)
            except (AttributeError, ValueError):
                unknown_request_ids.add(request_id)
                continue
            if "embodied_motion" in definition.cancellation_domains:
                motion_request_ids.add(request_id)
        confirmation_scope_widened = bool(
            cancellation_scope == "embodied_motion"
            and (
                set(confirmed_request_ids) - motion_request_ids
                or unknown_request_ids
            )
        )
        return {
            "confirmation_id": confirmation_id,
            "fingerprint": fingerprint,
            "cancellation_scope": cancellation_scope,
            "confirmed_request_ids": confirmed_request_ids,
            "motion_request_ids": sorted(motion_request_ids),
            "unknown_request_ids": sorted(unknown_request_ids),
            "confirmation_scope_widened": confirmation_scope_widened,
            "widening_reason": (
                "shared_confirmation_token_revoked_conservatively"
                if confirmation_scope_widened
                else ""
            ),
        }

    def _reconcile_revoked_confirmation_for_reflex(
        self,
        pending: Any | None,
        session_id: str,
        *,
        cancellation_scope: str,
    ) -> dict[str, Any]:
        """Compatibility fallback when atomic receipt reconciliation is absent."""

        evidence = self._revoked_confirmation_evidence_for_reflex(
            pending,
            cancellation_scope=cancellation_scope,
        )
        confirmation_id = str(evidence.get("confirmation_id") or "")
        if not confirmation_id:
            return evidence
        conversation_state = getattr(self, "conversation_state", None)
        resolved = False
        resolve_confirmation_scope = getattr(
            conversation_state,
            "resolve_confirmation_scope",
            None,
        )
        if callable(resolve_confirmation_scope):
            resolved = bool(
                resolve_confirmation_scope(
                    confirmation_id=confirmation_id,
                    decision="operational_interrupt",
                )
            )
        if not resolved:
            update_pending_task_status = getattr(
                conversation_state,
                "update_pending_task_status",
                None,
            )
            if callable(update_pending_task_status):
                update_pending_task_status(
                    metadata_key="confirmation_id",
                    metadata_value=confirmation_id,
                    status="cancelled",
                )

        self.session_log(
            session_id,
            "cognitive_gateway_confirmation_cancelled: "
            "confirmation_id=%s fingerprint=%s scope=%s widened=%s",
            confirmation_id or "<unknown>",
            str(evidence.get("fingerprint") or "<unknown>"),
            cancellation_scope,
            bool(evidence.get("confirmation_scope_widened")),
        )
        return evidence

    def _reconcile_reflex_cancellation_receipt(
        self,
        receipt: CancellationDispatchReceipt,
        pending: Any | None,
        session_id: str,
        *,
        user_text: str,
        cancellation_scope: str,
    ) -> dict[str, Any]:
        """Commit a broad fixed-reflex receipt and confirmation as one state update."""

        confirmation_evidence = self._revoked_confirmation_evidence_for_reflex(
            pending,
            cancellation_scope=cancellation_scope,
        )
        apply_receipt = getattr(
            getattr(self, "conversation_state", None),
            "apply_reflex_cancellation_receipt",
            None,
        )
        if not callable(apply_receipt):
            cancelled_confirmation = self._reconcile_revoked_confirmation_for_reflex(
                pending,
                session_id,
                cancellation_scope=cancellation_scope,
            )
            return {
                "status": "compatibility_fallback",
                "goal_state_results": [],
                "cancelled_confirmation": cancelled_confirmation,
            }
        try:
            results = apply_receipt(
                receipt,
                revoked_confirmation=confirmation_evidence,
                sid=session_id,
                user_text=user_text,
                source="cognitive_gateway_fixed_reflex",
            )
        except Exception as exc:
            cancelled_confirmation = self._reconcile_revoked_confirmation_for_reflex(
                pending,
                session_id,
                cancellation_scope=cancellation_scope,
            )
            self.session_log(
                session_id,
                "cognitive_gateway_reflex_goal_reconciliation_failed: "
                "scope=%s error=%s:%s",
                cancellation_scope,
                type(exc).__name__,
                str(exc)[:300],
            )
            return {
                "status": "uncertain",
                "goal_state_results": [],
                "cancelled_confirmation": cancelled_confirmation,
                "error": f"{type(exc).__name__}:{str(exc)[:300]}",
            }
        rejected = [
            item
            for item in results
            if item.get("applied") is False
            and item.get("reason") != "operation_already_applied"
        ]
        if rejected:
            cancelled_confirmation = self._reconcile_revoked_confirmation_for_reflex(
                pending,
                session_id,
                cancellation_scope=cancellation_scope,
            )
            return {
                "status": "uncertain",
                "goal_state_results": results,
                "cancelled_confirmation": cancelled_confirmation,
                "error": "atomic_reflex_cancellation_state_commit_rejected",
            }
        if confirmation_evidence:
            self.session_log(
                session_id,
                "cognitive_gateway_confirmation_cancelled: "
                "confirmation_id=%s fingerprint=%s scope=%s widened=%s",
                str(confirmation_evidence.get("confirmation_id") or "<unknown>"),
                str(confirmation_evidence.get("fingerprint") or "<unknown>"),
                cancellation_scope,
                bool(confirmation_evidence.get("confirmation_scope_widened")),
            )
        return {
            "status": "reconciled",
            "goal_state_results": results,
            "cancelled_confirmation": confirmation_evidence,
        }

    def _cognitive_core_exception_safe_response(
        self,
        user_text: str,
        *,
        context: dict[str, Any] | None = None,
        failure_stage: str | None = None,
        failure_class: str | None = None,
        failure_error: str | None = None,
    ) -> InteractionResponse:
        """Return one non-semantic operational fallback after Core failure.

        The Host does not classify the user's request to choose different
        wording. Exact effect safety is already enforced by the absence of a
        validated Canonical Plan and Trusted Capability Runtime execution.
        """

        # Cognition is unavailable at this boundary. Keep this emergency
        # fail-closed utterance tiny and natural; authoritative safety facts stay
        # in metadata rather than leaking workflow vocabulary into Chromie's voice.
        del context
        zh = self._looks_zh(user_text)
        text = (
            "咦？我刚刚没弄明白。你再跟我说一遍嘛。"
            if zh
            else "Huh? I didn't quite get that. Can you tell me again?"
        )
        response = self._host_speech_response(
            text,
            style="warning",
            source="host_cognitive_core_exception_safe_fallback",
        )
        failure_metadata: dict[str, Any] = {}
        if failure_stage or failure_class or failure_error:
            failure_metadata = {
                "semantic_status": "failed",
                "semantic_failure_stage": str(failure_stage or "cognition"),
                "semantic_failure_class": str(
                    failure_class or "semantic_failure"
                ),
                "semantic_failure_error": str(failure_error or ""),
            }
        return response.model_copy(
            update={
                "metadata": {
                    **response.metadata,
                    "effect_execution": "not_authorized",
                    "semantic_fallback": False,
                    **failure_metadata,
                }
            }
        )

    @staticmethod
    def _looks_zh(text: str) -> bool:
        return any("\u4e00" <= ch <= "\u9fff" for ch in text or "")

    def _host_speech_response(
        self,
        text: str,
        *,
        style: str,
        source: str = "host_confirmation_dialogue",
    ) -> InteractionResponse:
        return InteractionResponse(
            speech=[
                {
                    "text": text,
                    "style": style,
                    "timing": "immediate",
                    "priority": "high",
                    "interruptible": True,
                    "metadata": {
                        "source": source,
                        "wait_for_playback_start": True,
                        "playback_start_required_for_delivery": True,
                    },
                }
            ],
            metadata={"source": source},
        )

    async def _execute_agent_tool(
        self,
        request: ToolExecutionRequest,
        timeout_ms: int,
    ) -> ToolExecutionResponse:
        session = await self.get_http_session()
        return await self.agent_client.execute_tool(
            session,
            request=request,
            timeout_ms=timeout_ms,
        )

    async def _execute_planning_task_graph(self, graph: dict[str, Any]) -> dict[str, Any]:
        session = await self.get_http_session()
        return await self.agent_client.execute_planning_task_graph(session, graph)

    async def _cancel_planning_task_graph(
        self,
        graph_id: str,
    ) -> dict[str, Any]:
        session = await self.get_http_session()
        return await self.agent_client.cancel_planning_task_graph(
            session,
            graph_id,
        )

    def _cognitive_turn_closure_adapter(self) -> CognitiveTurnClosure:
        closure = getattr(self, "cognitive_turn_closure", None)
        if closure is None:
            closure = CognitiveTurnClosure(self.interaction_runtime)
            self.cognitive_turn_closure = closure
        return closure

    def _record_cognitive_outcome_evidence(
        self,
        bundle: Any,
        *,
        session_id: str | None,
        final_response: InteractionResponse | None,
        delivery_status: str,
        suppression_reason: str = "",
        goal_state_results: list[dict[str, Any]] | None = None,
    ) -> None:
        recorder = getattr(self, "cognitive_evidence", None)
        if recorder is None or not hasattr(recorder, "record_outcome"):
            return
        try:
            recorder.record_outcome(
                bundle,
                sid=str(session_id or bundle.turn_id),
                final_response=final_response,
                delivery_status=delivery_status,
                suppression_reason=suppression_reason,
                goal_state_results=goal_state_results,
            )
        except Exception as exc:
            self.session_log(
                session_id,
                "cognitive_outcome_evidence_failed: error_type=%s error=%s",
                type(exc).__name__,
                exc,
            )

    def _outcome_response_is_stale(
        self,
        *,
        generation: int,
        session_id: str | None,
    ) -> bool:
        current_generation = int(
            getattr(self, "playback_generation", generation)
        )
        current_session_id = getattr(self, "session_id", session_id)
        return (
            generation != current_generation
            or (
                session_id is not None
                and current_session_id is not None
                and session_id != current_session_id
            )
        )

    async def _queue_response_social_attention(
        self,
        response: InteractionResponse,
        *,
        session_id: str | None,
    ) -> None:
        """Offer a Host-presented Communicative Act to Social Attention.

        Normal cognitive-runtime responses are already anchored inside the runtime.
        This bridge is for presentation paths that bypass that return boundary, such
        as post-Evidence outcome speech and fail-closed conversational responses.
        """

        runtime = getattr(self, "cognitive_runtime", None)
        queue = getattr(runtime, "queue_interaction_social_attention", None)
        if not callable(queue):
            return
        try:
            session = await self.get_http_session()
            queue(
                session,
                response=response,
                sid=str(session_id or response.interaction_id or "response"),
                context=self.build_context(session_id),
            )
        except (TypeError, ValueError, ValidationError, RuntimeError, AttributeError) as exc:
            self.session_log(
                session_id,
                "response_social_attention_queue_failed: error_type=%s error=%s",
                type(exc).__name__,
                exc,
            )

    async def _execute_cognitive_outcome_response(
        self,
        response: InteractionResponse,
        *,
        session_id: str | None,
        detached_delivery: bool = False,
    ) -> str:
        await self._queue_response_social_attention(
            response,
            session_id=session_id,
        )
        try:
            dispatch = await self.interaction_runtime.submit_response(
                response,
                session_id=None if detached_delivery else session_id,
            )
            execution = await self.interaction_runtime.wait_dispatch(dispatch)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.session_log(
                session_id,
                "cognitive_outcome_response_failed: error_type=%s error=%s",
                type(exc).__name__,
                exc,
            )
            for speech in response.speech:
                self.conversation_state.update_pending_task_status_for_request_id(
                    request_id=speech.id,
                status="failed",
            )
            return "speech_runtime_failed"

        delivered_count = self._record_successfully_delivered_speech(
            response,
            execution,
            session_id=session_id,
            log_event="cognitive_outcome_history_after_delivery",
        )
        for result in execution.results:
            self.conversation_state.update_pending_task_status_for_request_id(
                request_id=result.request_id,
                status=result.status,
            )
        self.session_log(
            session_id,
            "cognitive_outcome_response_done: status=%s speech=%s results=%s",
            execution.status,
            len(response.speech),
            len(execution.results),
        )
        state = self.sessions.state.get(session_id or "")
        if state is not None:
            state["response_chars"] = state.get("response_chars", 0) + sum(
                len(item.text) for item in response.speech
            )
        if (
            execution.status == "completed"
            and delivered_count == len(response.speech)
        ):
            return "speech_runtime_completed"
        if execution.status == "completed":
            return "speech_runtime_delivery_unverified"
        return f"speech_runtime_{execution.status}"

    def _record_successfully_delivered_speech(
        self,
        response: InteractionResponse,
        execution: CapabilityRuntimeResult,
        *,
        session_id: str | None,
        log_event: str,
    ) -> int:
        """Expose only speech the runtime proves was delivered.

        Confirmation prompts are operational turns: recording them before the
        speech provider succeeds would let unheard text influence later model
        context and confirmation resolution.
        """

        results_by_request = {
            result.request_id: result for result in execution.results
        }
        delivered_speech = [
            speech
            for speech in response.speech
            if (
                (result := results_by_request.get(speech.id)) is not None
                and result.capability_id == "chromie.speak"
                and result.status == "completed"
                and (
                    not (
                        speech.metadata.get(
                            "playback_start_required_for_delivery"
                        )
                        is True
                        or speech.metadata.get("wait_for_playback_start")
                        is True
                    )
                    or (
                        isinstance(result.output, dict)
                        and result.output.get("playback_started") is True
                    )
                )
            )
        ]
        if not delivered_speech:
            self.session_log(
                session_id,
                "%s: delivered_speech=0 runtime_status=%s",
                log_event,
                execution.status,
            )
            return 0
        delivered_response = response.model_copy(
            deep=True,
            update={
                "speech": delivered_speech,
                "capabilities": [],
                "requires_confirmation": False,
            },
        )
        try:
            self.conversation_state.record_interaction_response(
                session_id,
                delivered_response,
            )
        except Exception as exc:
            self.session_log(
                session_id,
                "%s_failed: error_type=%s error=%s",
                log_event,
                type(exc).__name__,
                exc,
            )
            return 0
        self.session_log(
            session_id,
            "%s: delivered_speech=%s runtime_status=%s",
            log_event,
            len(delivered_speech),
            execution.status,
        )
        return len(delivered_speech)

    async def _close_cognitive_execution(
        self,
        *,
        response: InteractionResponse,
        execution: CapabilityRuntimeResult,
        session_id: str | None,
        generation: int,
        provider_status: dict[str, Any] | None,
        recovery_confirmation_staged: bool,
        suppress_final_reason: str | None = None,
    ) -> str:
        closure = self._cognitive_turn_closure_adapter()
        interaction_ledger = getattr(
            getattr(self, "interaction_runtime", None),
            "interaction_ledger",
            None,
        )
        envelope = response.metadata.get("user_turn_envelope")
        interaction_turn_id = (
            str(envelope.get("turn_id") or "").strip()
            if isinstance(envelope, dict)
            else ""
        ) or response.interaction_id
        if interaction_ledger is not None:
            try:
                interaction_ledger.record_social_results(
                    session_id=str(session_id or interaction_turn_id),
                    turn_id=interaction_turn_id,
                    interaction_id=response.interaction_id,
                    requests=response.capabilities,
                    results=execution.results,
                )
            except Exception as exc:
                response.metadata["interaction_ledger_error"] = (
                    type(exc).__name__
                )
                self.session_log(
                    session_id,
                    "interaction_ledger_social_append_failed: "
                    "error_type=%s error=%s",
                    type(exc).__name__,
                    exc,
                )
        try:
            plan = closure.canonical_plan(response)
        except Exception as exc:
            plan = None
            self.session_log(
                session_id,
                "cognitive_outcome_plan_rejected: error_type=%s error=%s",
                type(exc).__name__,
                exc,
            )
            response.metadata["execution_outcome_error"] = (
                f"plan_rejected:{type(exc).__name__}"
            )
        if plan is None:
            return "not_applicable"

        try:
            bundle = closure.build(
                response=response,
                execution=execution,
                session_id=session_id,
                provider_status=provider_status,
            )
            if bundle is None:  # pragma: no cover - guarded by plan above
                raise ValueError("effectful cognitive turn produced no outcome")
        except Exception as exc:
            self.session_log(
                session_id,
                "cognitive_outcome_reconciliation_failed: error_type=%s error=%s",
                type(exc).__name__,
                exc,
            )
            response.metadata["execution_outcome_error"] = (
                f"reconciliation_failed:{type(exc).__name__}"
            )
            if (
                not recovery_confirmation_staged
                and suppress_final_reason is None
                and not self._outcome_response_is_stale(
                    generation=generation,
                    session_id=session_id,
                )
            ):
                warning = self._host_speech_response(
                    (
                        "执行已经结束，但我没能可靠核对结果。"
                        if str(response.metadata.get("language") or "").lower().startswith("zh")
                        else "Execution ended, but I could not verify the result reliably."
                    ),
                    style="warning",
                    source="host_cognitive_outcome_reconciliation_failure",
                )
                await self._execute_cognitive_outcome_response(
                    warning,
                    session_id=session_id,
                )
            return "reconciliation_failed"

        response.metadata["execution_outcome_bundle"] = bundle.model_dump(
            mode="json"
        )
        if interaction_ledger is not None:
            try:
                interaction_ledger.record_execution_outcome(
                    bundle,
                    session_id=str(session_id or bundle.turn_id),
                )
            except Exception as exc:
                response.metadata["interaction_ledger_error"] = (
                    type(exc).__name__
                )
                self.session_log(
                    session_id,
                    "interaction_ledger_outcome_append_failed: "
                    "error_type=%s error=%s",
                    type(exc).__name__,
                    exc,
                )
        goal_state_results: list[dict[str, Any]] = []
        responsibility_results: list[dict[str, Any]] = []
        try:
            goal_state_results = (
                self.conversation_state.record_execution_outcome_bundle(
                    bundle,
                    sid=session_id,
                )
            )
            responsibility_results = (
                self.conversation_state.reconcile_execution_outcome_responsibilities(
                    bundle,
                    sid=session_id,
                )
            )
        except Exception as exc:
            self.session_log(
                session_id,
                "cognitive_outcome_goal_state_failed: error_type=%s error=%s",
                type(exc).__name__,
                exc,
            )
            response.metadata["execution_outcome_goal_state_error"] = (
                type(exc).__name__
            )
            warning: InteractionResponse | None = None
            delivery_status = "goal_state_commit_failed"
            if (
                not recovery_confirmation_staged
                and suppress_final_reason is None
                and not self._outcome_response_is_stale(
                    generation=generation,
                    session_id=session_id,
                )
            ):
                warning = self._host_speech_response(
                    (
                        "结果已经返回，但我没能可靠更新任务状态。"
                        if str(response.metadata.get("language") or "").lower().startswith("zh")
                        else "The result returned, but I could not update the task state reliably."
                    ),
                    style="warning",
                    source="host_cognitive_outcome_goal_state_failure",
                )
                delivery_status = await self._execute_cognitive_outcome_response(
                    warning,
                    session_id=session_id,
                )
            self._record_cognitive_outcome_evidence(
                bundle,
                session_id=session_id,
                final_response=warning,
                delivery_status=delivery_status,
                suppression_reason="goal_state_commit_failed",
            )
            return "goal_state_commit_failed"

        response.metadata["execution_outcome_goal_state_results"] = (
            goal_state_results
        )
        response.metadata["responsibility_reconciliation_results"] = (
            responsibility_results
        )
        cognitive_opportunities = (
            self.conversation_state.derive_execution_cognitive_opportunities(
                bundle
            )
        )
        response.metadata["cognitive_opportunities"] = [
            item.prompt_projection() for item in cognitive_opportunities
        ]
        if cognitive_opportunities:
            self.session_log(
                session_id,
                "cognitive_opportunity_raised: count=%s goals=%s modes=%s",
                len(cognitive_opportunities),
                ",".join(
                    goal_id
                    for item in cognitive_opportunities
                    for goal_id in item.goal_ids
                ),
                ",".join(
                    item.recommended_cognition
                    for item in cognitive_opportunities
                ),
            )
        slow_opportunities = [
            item
            for item in cognitive_opportunities
            if item.recommended_cognition == "slow"
        ]
        reflection_resolutions: list[dict[str, Any]] = []
        reflection_state_results: list[dict[str, Any]] = []
        reflection_call = getattr(
            getattr(self, "agent_client", None),
            "resolve_reflection",
            None,
        )
        if slow_opportunities and callable(reflection_call):
            reflection_context = {
                "active_goal_snapshots": self.conversation_state.active_goal_snapshots(),
                "recent_goal_snapshots": self.conversation_state.recent_goal_snapshots(),
            }
            association_projection = response.metadata.get("goal_association")
            if isinstance(association_projection, dict):
                reflection_context["goal_association_resolution"] = dict(
                    association_projection
                )
            situation_projection = response.metadata.get("situation")
            if isinstance(situation_projection, dict):
                reflection_context["situation"] = dict(situation_projection)
            reflection_context["execution_outcome_bundle"] = bundle.model_dump(
                mode="json", exclude_none=True
            )
            reflection_context["canonical_plan"] = plan.model_dump(
                mode="json", exclude_none=True
            )
            reflection_session = await self.get_http_session()
            reflection_calls = []
            for opportunity in slow_opportunities:
                context = {
                    **reflection_context,
                    "cognitive_opportunity": opportunity.prompt_projection(),
                }
                reflection_calls.append(
                    reflection_call(
                        reflection_session,
                        request=CognitiveWorkRequest(
                            sid=session_id,
                            text=self._execution_outcome_user_text(response, plan),
                            language=str(response.metadata.get("language") or "en-US"),
                            responsibilities=[
                                CognitiveResponsibilityProposal(
                                    local_ref=f"reflection:{opportunity.opportunity_id}",
                                    outcome="Reflect on this trusted cognitive opportunity.",
                                    confidence=1.0,
                                )
                            ],
                            interpretation_confidence=1.0,
                            context=context,
                            history=self.conversation_state.get_history(),
                        ),
                        timeout_ms=self.cognitive_runtime_policy.deep_planner_timeout_ms,
                    )
                )
            reflected = await asyncio.gather(
                *reflection_calls,
                return_exceptions=True,
            )
            for opportunity, item in zip(
                slow_opportunities, reflected, strict=True
            ):
                if isinstance(item, BaseException):
                    self.session_log(
                        session_id,
                        "selective_reflection_unavailable: opportunity=%s error_type=%s error=%s",
                        opportunity.opportunity_id,
                        type(item).__name__,
                        item,
                    )
                    continue
                reflection_resolutions.append(item.prompt_projection())
                try:
                    reflection_state_results.extend(
                        self.conversation_state.apply_reflection_resolution(
                            item,
                            sid=session_id,
                        )
                    )
                except Exception as exc:
                    self.session_log(
                        session_id,
                        "selective_reflection_state_rejected: opportunity=%s error_type=%s error=%s",
                        opportunity.opportunity_id,
                        type(exc).__name__,
                        exc,
                    )
            response.metadata["reflection_resolutions"] = reflection_resolutions
            response.metadata["reflection_state_results"] = reflection_state_results

        self.session_log(
            session_id,
            "cognitive_outcome_reconciled: outcome_id=%s aggregate=%s goals=%s evidence=%s",
            bundle.outcome_id,
            bundle.aggregate_status,
            len(bundle.goal_outcomes),
            len(bundle.evidence),
        )

        stale_outcome = self._outcome_response_is_stale(
            generation=generation,
            session_id=session_id,
        )
        current_session_id = self.session_id
        outcome_delivery = build_host_outcome_delivery(self)
        defer_for_ordinary_overlap = (
            stale_outcome
            and outcome_delivery.is_ordinary_overlap(
                origin_session_id=session_id,
                current_session_id=current_session_id,
                generation_changed=(generation != self.playback_generation),
                execution_status=str(execution.status),
                aggregate_status=str(bundle.aggregate_status),
            )
        )
        if stale_outcome and not defer_for_ordinary_overlap:
            self.session_log(
                session_id,
                "cognitive_outcome_response_suppressed: reason=stale_turn",
            )
            self._record_cognitive_outcome_evidence(
                bundle,
                session_id=session_id,
                final_response=None,
                delivery_status="suppressed",
                suppression_reason="stale_turn",
                goal_state_results=goal_state_results,
            )
            return "suppressed_stale"
        if defer_for_ordinary_overlap:
            self.session_log(
                session_id,
                "cognitive_outcome_response_deferred: reason=ordinary_overlap current_sid=%s",
                current_session_id,
            )
        if suppress_final_reason is not None:
            self._record_cognitive_outcome_evidence(
                bundle,
                session_id=session_id,
                final_response=None,
                delivery_status="suppressed",
                suppression_reason=suppress_final_reason,
                goal_state_results=goal_state_results,
            )
            return f"suppressed_{suppress_final_reason}"
        if recovery_confirmation_staged:
            self._record_cognitive_outcome_evidence(
                bundle,
                session_id=session_id,
                final_response=None,
                delivery_status="waiting_for_recovery_confirmation",
                suppression_reason="recovery_confirmation_staged",
                goal_state_results=goal_state_results,
            )
            return "waiting_for_recovery_confirmation"

        delivered_incremental_evidence = {
            str(item).strip()
            for item in response.metadata.get(
                "incremental_result_delivery_evidence_ids",
                [],
            )
            if str(item).strip()
        }
        completed_evidence_ids = {
            item.evidence_id
            for item in bundle.evidence
            if item.status == "completed"
        }
        if (
            bundle.aggregate_status == "completed"
            and completed_evidence_ids
            and completed_evidence_ids.issubset(delivered_incremental_evidence)
        ):
            self.session_log(
                session_id,
                "cognitive_outcome_response_suppressed: "
                "reason=incremental_result_already_delivered evidence=%s",
                len(completed_evidence_ids),
            )
            self._record_cognitive_outcome_evidence(
                bundle,
                session_id=session_id,
                final_response=None,
                delivery_status="incremental_result_delivery_completed",
                suppression_reason="incremental_result_already_delivered",
                goal_state_results=goal_state_results,
            )
            return "incremental_result_delivery_completed"

        try:
            final_response = await self._plan_evidence_bound_capability_result_response(
                source_response=response,
                bundle=bundle,
                plan=plan,
                session_id=session_id,
            )
            if final_response is None:
                self.session_log(
                    session_id,
                    "fast_planner_evidence_reentry_response_unavailable: "
                    "aggregate=%s evidence=%s fallback=mechanical_outcome_projection",
                    bundle.aggregate_status,
                    len(bundle.evidence),
                )
                language = str(response.metadata.get("language") or "en-US")
                final_response = compose_outcome_response(
                    bundle,
                    plan,
                    language,
                )
        except Exception as exc:
            self.session_log(
                session_id,
                "cognitive_outcome_response_rejected: error_type=%s error=%s",
                type(exc).__name__,
                exc,
            )
            self._record_cognitive_outcome_evidence(
                bundle,
                session_id=session_id,
                final_response=None,
                delivery_status="response_planning_failed",
                suppression_reason=type(exc).__name__,
                goal_state_results=goal_state_results,
            )
            return "response_planning_failed"

        detached_delivery = False
        if defer_for_ordinary_overlap:
            goal_ids = tuple(
                str(item.goal_id)
                for item in bundle.goal_outcomes
                if str(item.goal_id or "").strip()
            )
            window = await outcome_delivery.wait_for_window(
                origin_session_id=str(session_id),
                source_goal_ids=goal_ids,
                timeout_s=max(
                    5.0,
                    min(
                        120.0,
                        float(
                            getattr(
                                getattr(
                                    getattr(self, "host_settings", None),
                                    "session",
                                    None,
                                ),
                                "idle_timeout_ms",
                                120000.0,
                            )
                        )
                        / 1000.0,
                    ),
                ),
            )
            if window.status != "ready":
                suppression_reason = (
                    "goal_invalidated_before_deferred_delivery"
                    if window.status == "goal_invalidated"
                    else "ordinary_overlap_delivery_timeout"
                )
                self.session_log(
                    session_id,
                    "cognitive_outcome_response_suppressed: reason=%s waited_for=%s",
                    suppression_reason,
                    ",".join(window.waited_for_session_ids),
                )
                self._record_cognitive_outcome_evidence(
                    bundle,
                    session_id=session_id,
                    final_response=None,
                    delivery_status="suppressed",
                    suppression_reason=suppression_reason,
                    goal_state_results=goal_state_results,
                )
                return f"suppressed_{window.status}"
            detached_delivery = True
            final_response.metadata["deferred_outcome_delivery"] = {
                "reason": "ordinary_overlap",
                "origin_session_id": session_id,
                "waited_for_session_ids": list(window.waited_for_session_ids),
                "source_goal_ids": list(goal_ids),
            }
            self.session_log(
                session_id,
                "cognitive_outcome_response_delivery_ready: reason=ordinary_overlap waited_for=%s",
                ",".join(window.waited_for_session_ids),
            )

        delivery_status = await self._execute_cognitive_outcome_response(
            final_response,
            session_id=session_id,
            detached_delivery=detached_delivery,
        )
        response.metadata["post_execution_response"] = final_response.model_dump(
            mode="json"
        )
        self._record_cognitive_outcome_evidence(
            bundle,
            session_id=session_id,
            final_response=final_response,
            delivery_status=delivery_status,
            goal_state_results=goal_state_results,
        )
        return delivery_status

    @staticmethod
    def _execution_outcome_user_text(
        source_response: InteractionResponse,
        plan: Any,
    ) -> str:
        metadata = (
            source_response.metadata
            if isinstance(source_response.metadata, dict)
            else {}
        )
        envelope = metadata.get("user_turn_envelope")
        normalized_input = (
            envelope.get("normalized_input")
            if isinstance(envelope, dict)
            else None
        )
        if isinstance(normalized_input, dict):
            text = str(normalized_input.get("text") or "").strip()
            if text:
                return text
        return str(getattr(plan, "goal_summary", "") or "").strip()

    @staticmethod
    def _trusted_tool_result_fallback(
        evidence: list[ToolResultEvidence],
        *,
        max_chars: int,
    ) -> str:
        """Return one provider-authored user summary for exceptional fallback only."""

        explicit_fields = ("user_summary",)
        for item in evidence:
            for field in explicit_fields:
                value = item.data.get(field)
                if not isinstance(value, str):
                    continue
                text = " ".join(value.strip().split())
                if not text:
                    continue
                return text[:max_chars].rstrip()
        return ""

    async def _reenter_cognition_for_terminal_capability(
        self,
        *,
        response: InteractionResponse,
        result: CapabilityResult,
        session_id: str | None,
        generation: int,
    ) -> None:
        """Turn one exact terminal Runtime result into an internal cognitive event.

        The result is never encoded as a user message. Runtime owns the lifecycle
        fact, deterministic closure creates terminal Evidence, and Fast Planner
        is reactivated with the exact Goal/request binding to decide whether one
        grounded spoken update is useful while sibling work continues.
        """

        try:
            evidence = self._cognitive_turn_closure_adapter().build_terminal_evidence(
                response=response,
                result=result,
                session_id=session_id,
            )
        except Exception as exc:
            self.session_log(
                session_id,
                "incremental_terminal_evidence_rejected: request_id=%s "
                "error_type=%s error=%s",
                result.request_id,
                type(exc).__name__,
                exc,
            )
            return
        if evidence is None:
            return

        reason_codes = [
            value
            for value in (
                evidence.reason_code,
                f"execution_{evidence.status}",
            )
            if value
        ]
        opportunity = CognitiveOpportunity.create(
            trigger="execution_outcome",
            goal_ids=list(evidence.source_goal_ids),
            evidence_refs=[evidence.evidence_id],
            reason_codes=reason_codes[:8],
            recommended_cognition=(
                "fast" if evidence.status == "completed" else "slow"
            ),
        )
        response.metadata.setdefault(
            "incremental_cognitive_opportunities",
            [],
        ).append(opportunity.prompt_projection())
        self.session_log(
            session_id,
            "incremental_cognitive_opportunity: opportunity_id=%s request_id=%s "
            "goals=%s status=%s",
            opportunity.opportunity_id,
            evidence.request_id,
            ",".join(evidence.source_goal_ids),
            evidence.status,
        )

        relevant, relevance_reason = self._terminal_evidence_is_currently_relevant(
            source_response=response,
            evidence=evidence,
        )
        if not relevant:
            self.session_log(
                session_id,
                "incremental_cognitive_reentry_suppressed: request_id=%s reason=%s",
                evidence.request_id,
                relevance_reason,
            )
            suppressed = response.metadata.setdefault(
                "suppressed_terminal_reentry",
                [],
            )
            suppressed.append(
                {
                    "request_id": evidence.request_id,
                    "evidence_id": evidence.evidence_id,
                    "reason": relevance_reason,
                }
            )
            return
        if self._outcome_response_is_stale(
            generation=generation,
            session_id=session_id,
        ):
            # Ordinary overlap delivery is resolved by the final outcome path;
            # never interrupt a newer user turn with an early sibling result.
            self.session_log(
                session_id,
                "incremental_cognitive_reentry_deferred: request_id=%s reason=turn_overlap",
                evidence.request_id,
            )
            return
        if evidence.status != "completed":
            return
        observation = evidence.observation
        if (
            observation is None
            or observation.status != "available"
            or not observation.schema_validated
            or not observation.data
        ):
            return

        try:
            result_response = await self._plan_incremental_terminal_result_response(
                source_response=response,
                evidence=evidence,
                opportunity=opportunity,
                session_id=session_id,
            )
        except Exception as exc:
            self.session_log(
                session_id,
                "incremental_planner_evidence_reentry_rejected: request_id=%s "
                "error_type=%s error=%s",
                evidence.request_id,
                type(exc).__name__,
                exc,
            )
            return
        if result_response is None:
            return

        delivery_status = await self._execute_cognitive_outcome_response(
            result_response,
            session_id=session_id,
            detached_delivery=True,
        )
        if delivery_status == "speech_runtime_completed":
            delivered = response.metadata.setdefault(
                "incremental_result_delivery_evidence_ids",
                [],
            )
            if evidence.evidence_id not in delivered:
                delivered.append(evidence.evidence_id)
        self.session_log(
            session_id,
            "incremental_cognitive_reentry_done: request_id=%s evidence_id=%s delivery=%s",
            evidence.request_id,
            evidence.evidence_id,
            delivery_status,
        )

    def _terminal_evidence_is_currently_relevant(
        self,
        *,
        source_response: InteractionResponse,
        evidence: ExecutionEvidence,
    ) -> tuple[bool, str]:
        """Fail closed when terminal Evidence belongs to obsolete responsibility.

        Evidence remains valid history even after a Goal is cancelled, superseded,
        or replanned.  What becomes invalid is using that old result to authorize
        new user-facing speech/action.  Re-entry therefore requires the exact
        Host-owned Goal/plan/request binding that originally dispatched the work
        to still be current.
        """

        metadata = (
            source_response.metadata
            if isinstance(source_response.metadata, dict)
            else {}
        )
        expected_plan_id = str(metadata.get("canonical_plan_id") or "").strip()
        expected_fingerprint = str(
            metadata.get("canonical_plan_fingerprint") or ""
        ).strip()
        if not expected_plan_id or not expected_fingerprint:
            return False, "source_plan_binding_missing"

        bindings = {
            str(item.get("goal_id") or "").strip(): item
            for item in self.conversation_state.goal_cancellation_bindings(
                evidence.source_goal_ids
            )
            if str(item.get("goal_id") or "").strip()
        }
        if not evidence.source_goal_ids:
            return False, "source_goal_binding_missing"
        for goal_id in evidence.source_goal_ids:
            binding = bindings.get(goal_id)
            if not binding or binding.get("found") is not True:
                return False, "goal_binding_missing"
            if str(binding.get("responsibility_status") or "") != "open":
                return False, "goal_responsibility_terminal"
            if str(binding.get("canonical_plan_id") or "") != expected_plan_id:
                return False, "canonical_plan_superseded"
            if (
                str(binding.get("canonical_plan_fingerprint") or "")
                != expected_fingerprint
            ):
                return False, "canonical_plan_superseded"
            request_ids = {
                str(item).strip()
                for item in binding.get("request_ids") or ()
                if str(item).strip()
            }
            if evidence.request_id not in request_ids:
                return False, "request_binding_superseded"
        return True, "current"

    async def _plan_incremental_terminal_result_response(
        self,
        *,
        source_response: InteractionResponse,
        evidence: ExecutionEvidence,
        opportunity: CognitiveOpportunity,
        session_id: str | None,
    ) -> InteractionResponse | None:
        observation = evidence.observation
        if (
            observation is None
            or observation.status != "available"
            or not observation.schema_validated
            or not observation.data
        ):
            return None
        metadata = (
            source_response.metadata
            if isinstance(source_response.metadata, dict)
            else {}
        )
        envelope = metadata.get("user_turn_envelope")
        normalized_input = (
            envelope.get("normalized_input")
            if isinstance(envelope, dict)
            else None
        )
        user_request = (
            str(normalized_input.get("text") or "").strip()
            if isinstance(normalized_input, dict)
            else ""
        )
        if not user_request:
            return None
        language = str(
            metadata.get("language")
            or (
                normalized_input.get("language")
                if isinstance(normalized_input, dict)
                else ""
            )
            or "en-US"
        )
        bounded_evidence = ToolResultEvidence(
            evidence_id=evidence.evidence_id,
            tool_id=evidence.capability_id,
            status=evidence.status,
            data=observation.data,
            output_sha256=canonical_value_sha256(observation.data),
        )
        try:
            canonical_plan = CanonicalPlan.model_validate(
                metadata.get("canonical_plan") or {}
            )
        except Exception as exc:
            self.session_log(
                session_id,
                "incremental_evidence_reentry_rejected: request_id=%s "
                "error_type=%s error=%s",
                evidence.request_id,
                type(exc).__name__,
                exc,
            )
            return None
        return await self._planner_evidence_reentry_response(
            source_response=source_response,
            canonical_plan=canonical_plan,
            user_request=user_request,
            language=language,
            goal_ids=list(evidence.source_goal_ids),
            evidence=[bounded_evidence],
            session_id=session_id,
            phase="capability_result_reentry",
            extra_context={
                "incremental_terminal_evidence": True,
                "terminal_request_id": evidence.request_id,
                "terminal_capability_id": evidence.capability_id,
                "terminal_status": evidence.status,
                "cognitive_opportunity": opportunity.prompt_projection(),
            },
        )

    async def _planner_evidence_reentry_response(
        self,
        *,
        source_response: InteractionResponse,
        canonical_plan: CanonicalPlan,
        user_request: str,
        language: str,
        goal_ids: list[str],
        evidence: list[ToolResultEvidence],
        session_id: str | None,
        phase: str,
        extra_context: dict[str, Any] | None = None,
    ) -> InteractionResponse | None:
        """Reactivate Fast Planner from Host-bound terminal Evidence."""

        normalized_goal_ids = list(
            dict.fromkeys(
                str(item).strip() for item in goal_ids if str(item).strip()
            )
        )
        if not normalized_goal_ids or not evidence:
            return None
        metadata = (
            source_response.metadata
            if isinstance(source_response.metadata, dict)
            else {}
        )
        association = metadata.get("goal_association")
        if not isinstance(association, dict):
            self.session_log(
                session_id,
                "planner_evidence_reentry_rejected: reason=missing_goal_association",
            )
            return None
        association_goal_ids = {
            str(goal_id).strip()
            for item in association.get("associations") or []
            if isinstance(item, dict)
            for goal_id in item.get("target_goal_ids") or []
        } | {
            str(item.get("goal_id") or "").strip()
            for item in association.get("new_goals") or []
            if isinstance(item, dict)
        }
        if not set(normalized_goal_ids).issubset(association_goal_ids):
            raise ValueError(
                "terminal Evidence Goal binding is not present in Goal Association"
            )

        sid = str(session_id or canonical_plan.plan_id)
        context = self._goal_driven_authority_context(
            self.build_context(sid),
            session_id=sid,
            observer=False,
        )
        context.update(
            {
                "goal_association_resolution": association,
                "canonical_plan_resolution": canonical_plan.prompt_projection(),
                "trusted_terminal_evidence": [
                    item.model_dump(mode="json") for item in evidence
                ],
                "result_evidence_refs": [item.evidence_id for item in evidence],
                "result_evidence_reentry": {
                    "phase": phase,
                    "source_goal_ids": normalized_goal_ids,
                    "wording_owner": "fast_planner",
                },
            }
        )
        if isinstance(extra_context, dict):
            context.update(extra_context)
        interaction_ledger = getattr(
            getattr(self, "cognitive_runtime", None),
            "interaction_ledger",
            None,
        )
        if interaction_ledger is not None:
            context["interaction_context"] = interaction_ledger.context(
                sid,
                goal_ids=normalized_goal_ids,
                turn_id=str(metadata.get("turn_id") or ""),
            ).model_dump(mode="json")

        request = CognitiveWorkRequest(
            sid=f"{sid}:evidence:{evidence[0].evidence_id}"[:160],
            text=user_request,
            language=language,
            responsibilities=[
                CognitiveResponsibilityProposal(
                    local_ref=f"evidence:{goal_id}"[:160],
                    outcome=(
                        "Choose the next Main Activity for the original request "
                        "from Host-bound terminal Evidence."
                    ),
                    completion_requires_work=False,
                    completion_requires_fresh_evidence=False,
                    confidence=1.0,
                )
                for goal_id in normalized_goal_ids
            ],
            interpretation_confidence=1.0,
            context=context,
            history=list(context.get("history") or []),
        )
        session = await self.get_http_session()
        planner_started_ms = now_ms()
        try:
            replanned = await self.agent_client.resolve_fast_plan(
                session,
                request=request,
                timeout_ms=self.cognitive_runtime_policy.fast_planner_timeout_ms,
            )
        except Exception as exc:
            record_session_workflow_stage(
                self,
                session_id,
                stage="fast_planner_evidence_reentry",
                started_monotonic_ms=planner_started_ms,
                finished_monotonic_ms=now_ms(),
                status="failed",
                input_payload={
                    "source_goal_ids": normalized_goal_ids,
                    "evidence_refs": [item.evidence_id for item in evidence],
                    "phase": phase,
                },
                output_payload=None,
                errors=[{"error_type": type(exc).__name__, "error": str(exc)}],
                metadata={"wording_owner": "fast_planner"},
            )
            raise
        record_session_workflow_stage(
            self,
            session_id,
            stage="fast_planner_evidence_reentry",
            started_monotonic_ms=planner_started_ms,
            finished_monotonic_ms=now_ms(),
            status="resolved",
            input_payload={
                "source_goal_ids": normalized_goal_ids,
                "evidence_refs": [item.evidence_id for item in evidence],
                "phase": phase,
            },
            output_payload=replanned,
            errors=[],
            metadata={"wording_owner": "fast_planner"},
        )
        if set(replanned.goal_ids) != set(normalized_goal_ids):
            raise ValueError("Evidence re-entry Plan changed the bound Goal set")
        if replanned.steps or replanned.disposition != "respond":
            self.session_log(
                session_id,
                "planner_evidence_reentry_no_response: disposition=%s steps=%s",
                replanned.disposition,
                len(replanned.steps),
            )
            return None
        response = await self.cognitive_runtime.adapter.build_planner_owned_response(
            plan=replanned,
            session_id=sid,
            language=language,
            context=context,
        )
        delivered_texts = {
            normalized
            for item in self._delivered_turn_speech_events(sid)
            if (normalized := " ".join(str(item.get("text") or "").strip().split()))
        }
        if delivered_texts and response.speech:
            retained_speech = [
                speech
                for speech in response.speech
                if " ".join(str(speech.text or "").strip().split())
                not in delivered_texts
            ]
            if len(retained_speech) != len(response.speech):
                self.session_log(
                    session_id,
                    "planner_evidence_reentry_duplicate_speech_suppressed: count=%s",
                    len(response.speech) - len(retained_speech),
                )
                if not retained_speech:
                    return response.model_copy(update={"speech": []})
                response = response.model_copy(update={"speech": retained_speech})
        evidence_refs = [item.evidence_id for item in evidence]
        for speech in response.speech:
            speech.metadata.update(
                {
                    "source": "fast_planner_evidence_reentry",
                    "phase": phase,
                    "truth_stage": "post_evidence",
                    "source_goal_ids": normalized_goal_ids,
                    "evidence_refs": evidence_refs,
                }
            )
        response.metadata.update(
            {
                "source": "fast_planner_evidence_reentry",
                "phase": phase,
                "source_goal_ids": normalized_goal_ids,
                "evidence_refs": evidence_refs,
                "planner_reentry_plan": replanned.model_dump(
                    mode="json", exclude_none=True
                ),
            }
        )
        return response

    async def _plan_evidence_bound_capability_result_response(
        self,
        *,
        source_response: InteractionResponse,
        bundle: Any,
        plan: Any,
        session_id: str | None,
    ) -> InteractionResponse | None:
        """Reactivate Fast Planner from bounded terminal Evidence.

        Complete observations stay in the immutable ExecutionOutcomeBundle. The
        Host preserves exact Goal/Plan/request binding, Fast Planner selects the
        still-needed Communicative Activity, and Runtime validates its evidence
        provenance before delivery.
        """

        metadata = source_response.metadata if isinstance(source_response.metadata, dict) else {}
        envelope = metadata.get("user_turn_envelope")
        normalized_input = (
            envelope.get("normalized_input")
            if isinstance(envelope, dict)
            else None
        )
        language = str(
            metadata.get("language")
            or (normalized_input.get("language") if isinstance(normalized_input, dict) else "")
            or "en-US"
        )
        if any(
            outcome.status == "completed"
            and (summary := goal_completion_qualification_summary(bundle, outcome))["required"]
            and not summary["established"]
            for outcome in bundle.goal_outcomes
        ):
            return compose_outcome_response(bundle, plan, language)

        delivered_incremental_evidence = {
            str(item).strip()
            for item in metadata.get(
                "incremental_result_delivery_evidence_ids",
                [],
            )
            if str(item).strip()
        }
        evidence: list[ToolResultEvidence] = []
        for item in bundle.evidence:
            if item.evidence_id in delivered_incremental_evidence:
                continue
            observation = item.observation
            if (
                observation is None
                or observation.status != "available"
                or not observation.schema_validated
                or not observation.data
            ):
                continue
            evidence.append(
                ToolResultEvidence(
                    evidence_id=item.evidence_id,
                    tool_id=item.capability_id,
                    status=item.status,
                    data=observation.data,
                    output_sha256=canonical_value_sha256(observation.data),
                )
            )
        if not evidence:
            return None

        user_request = (
            str(normalized_input.get("text") or "").strip()
            if isinstance(normalized_input, dict)
            else ""
        )
        if not user_request:
            return None
        goal_ids = list(plan.executable_goal_ids())
        try:
            return await self._planner_evidence_reentry_response(
                source_response=source_response,
                canonical_plan=plan,
                user_request=user_request,
                language=language,
                goal_ids=goal_ids,
                evidence=evidence,
                session_id=session_id,
                phase="post_execution",
                extra_context={
                    "execution_outcome_bundle": bundle.model_dump(
                        mode="json", exclude_none=True
                    ),
                "aggregate_status": bundle.aggregate_status,
                    "goal_statuses": [
                        {
                            "goal_id": item.goal_id,
                            "status": item.status,
                            "completion_qualification": (
                                goal_completion_qualification_summary(bundle, item)
                            ),
                        }
                        for item in bundle.goal_outcomes
                    ],
                },
            )
        except Exception as exc:
            self.session_log(
                session_id,
                "planner_evidence_reentry_failed: error_type=%s error=%s",
                type(exc).__name__,
                exc,
            )
            return None

    @staticmethod
    def _resolve_tool_result_pointer(document: Any, pointer: str) -> Any:
        current = document
        for raw_part in pointer.split("/")[1:]:
            part = raw_part.replace("~1", "/").replace("~0", "~")
            if isinstance(current, dict):
                if part not in current:
                    raise ValueError("tool result fact pointer does not exist")
                current = current[part]
            elif isinstance(current, list):
                if not part.isdigit() or int(part) >= len(current):
                    raise ValueError("tool result fact pointer index does not exist")
                current = current[int(part)]
            else:
                raise ValueError("tool result fact pointer traverses a scalar")
        if isinstance(current, (dict, list)):
            raise ValueError("tool result fact pointer must resolve to a scalar")
        return current

    def _launch_interaction(
        self,
        response: InteractionResponse,
        session_id: str | None,
        *,
        confirmed_request_ids: set[str] | None = None,
        reset_playback: bool = True,
        mark_session_done: bool = True,
    ) -> None:
        """Launch every InteractionResponse through the non-blocking dispatch boundary."""

        task = asyncio.create_task(
            self._dispatch_detached_interaction(
                response,
                session_id,
                confirmed_request_ids=confirmed_request_ids,
                reset_playback=reset_playback,
                mark_session_done=mark_session_done,
            )
        )
        active_tasks = getattr(self, "active_interaction_tasks", None)
        if not isinstance(active_tasks, dict):
            active_tasks = {}
            self.active_interaction_tasks = active_tasks
        active_tasks[task] = response.interaction_id
        self.active_interaction_task = task
        self.active_interaction_id = response.interaction_id
        task.add_done_callback(self._interaction_task_done)

    @staticmethod
    def _uses_detached_cognitive_capability_runtime(
        response: InteractionResponse,
    ) -> bool:
        metadata = response.metadata if isinstance(response.metadata, dict) else {}
        return bool(
            metadata.get("cognitive_runtime_apply") is True
            and isinstance(metadata.get("canonical_plan"), dict)
            and response.capabilities
        )

    async def _dispatch_detached_interaction(
        self,
        response: InteractionResponse,
        session_id: str | None,
        *,
        confirmed_request_ids: set[str] | None,
        reset_playback: bool,
        mark_session_done: bool,
    ) -> Any:
        """Submit trusted provider work and end the foreground Python task.

        Terminal work is consumed by a separate result task. The Capability
        Runtime, not this foreground call stack, keeps request ownership alive.
        """

        if reset_playback:
            await self.reset_playback_ordering()
        generation = int(getattr(self, "playback_generation", 0))
        started_ms = now_ms()
        try:
            dispatch = await self.interaction_runtime.submit_response(
                response,
                session_id=session_id,
                confirmed_request_ids=confirmed_request_ids,
            )
        except Exception as exc:
            record_session_workflow_stage(
                self,
                session_id,
                stage="trusted_capability_runtime_dispatch",
                started_monotonic_ms=started_ms,
                finished_monotonic_ms=now_ms(),
                status="failed",
                input_payload={"interaction_response": response},
                output_payload=None,
                errors=[{"error_type": type(exc).__name__, "error": str(exc)}],
                metadata=summarize_provider_start_evidence(response),
            )
            raise

        receipt = dispatch.receipt
        record_session_workflow_stage(
            self,
            session_id,
            stage="trusted_capability_runtime_dispatch",
            started_monotonic_ms=started_ms,
            finished_monotonic_ms=now_ms(),
            status="accepted" if receipt is not None else "terminal_before_dispatch",
            input_payload={"interaction_response": dispatch.source_response},
            output_payload=(
                receipt
                if receipt is not None
                else dispatch.immediate_execution
            ),
            errors=[],
            metadata=summarize_provider_start_evidence(dispatch.source_response),
        )
        self.session_log(
            session_id,
            "capability_runtime_detached: interaction_id=%s dispatch_id=%s requests=%s",
            dispatch.source_response.interaction_id,
            receipt.dispatch_id if receipt is not None else "none",
            len(receipt.request_ids) if receipt is not None else 0,
        )

        result_consumer = (
            self._consume_detached_cognitive_dispatch
            if self._uses_detached_cognitive_capability_runtime(response)
            else self._consume_detached_non_cognitive_dispatch
        )

        async def consume_and_finalize_session() -> CapabilityRuntimeResult:
            try:
                return await result_consumer(
                    dispatch,
                    session_id=session_id,
                    generation=generation,
                    confirmed_request_ids=confirmed_request_ids,
                )
            finally:
                # A dispatch receipt transfers provider ownership but does not prove
                # that response speech was even scheduled.  Closing the session at
                # receipt time lets the next voice turn invalidate that still-pending
                # speech as stale.  Finalize only after Runtime has consumed the
                # detached response (including its playback-start barrier).
                if mark_session_done:
                    state = self.sessions.state.get(session_id or "")
                    if state is not None:
                        state["llm_done"] = True
                        state["response_chars"] = state.get(
                            "response_chars", 0
                        ) + sum(
                            len(item.text)
                            for item in dispatch.runtime_response.speech
                        )
                    self.maybe_session_done(session_id)

        result_task = asyncio.create_task(
            consume_and_finalize_session(),
            name=(
                "capability-result-reentry:"
                f"{dispatch.source_response.interaction_id}:"
                f"{receipt.dispatch_id if receipt is not None else 'immediate'}"
            ),
        )
        result_tasks = getattr(self, "active_capability_result_tasks", None)
        if not isinstance(result_tasks, dict):
            result_tasks = {}
            self.active_capability_result_tasks = result_tasks
        result_tasks[result_task] = dispatch.source_response.interaction_id
        result_task.add_done_callback(self._capability_result_task_done)

        return receipt

    def _capability_result_task_done(self, task: asyncio.Task) -> None:
        result_tasks = getattr(self, "active_capability_result_tasks", None)
        if isinstance(result_tasks, dict):
            result_tasks.pop(task, None)
        if task.cancelled():
            return
        error = task.exception()
        if error is not None:
            logger.error(
                "Detached capability result task failed: %s",
                error,
                exc_info=error,
            )

    async def _consume_detached_non_cognitive_dispatch(
        self,
        dispatch: Any,
        *,
        session_id: str | None,
        generation: int,
        confirmed_request_ids: set[str] | None,
    ) -> CapabilityRuntimeResult:
        """Consume a non-cognitive dispatch without reopening the foreground turn."""

        execution = await self.interaction_runtime.wait_dispatch(dispatch)
        response = dispatch.source_response
        for result in execution.results:
            self.conversation_state.update_pending_task_status_for_request_id(
                request_id=result.request_id, status=result.status
            )
        if response.metadata.get("history_after_successful_delivery") is True:
            self._record_successfully_delivered_speech(
                response, execution, session_id=session_id,
                log_event="interaction_history_after_delivery",
            )
        self._record_execution_experience_safely(
            response=response, execution=execution, session_id=session_id,
            confirmed_request_ids=confirmed_request_ids,
        )
        return execution

    async def _consume_detached_cognitive_dispatch(
        self,
        dispatch: Any,
        *,
        session_id: str | None,
        generation: int,
        confirmed_request_ids: set[str] | None,
    ) -> CapabilityRuntimeResult:
        """Consume Runtime events after the originating foreground task ended."""

        response = dispatch.source_response
        receipt = dispatch.receipt
        started_ms = now_ms()
        source_capability_request_ids = {
            request.request_id for request in response.capabilities
        }
        runtime_capability_request_ids = {
            request.request_id
            for request in dispatch.runtime_response.capabilities
        }
        terminal_capability_ids: set[str] = set()

        preexecuted_capability_results = [
            result
            for result in dispatch.preexecuted_results
            if result.request_id in source_capability_request_ids
        ]
        for result in preexecuted_capability_results:
            terminal_capability_ids.add(result.request_id)
            if runtime_capability_request_ids:
                await self._reenter_cognition_for_terminal_capability(
                    response=response,
                    result=result,
                    session_id=session_id,
                    generation=generation,
                )

        if receipt is not None:
            cursor = receipt.event_cursor
            runtime_terminal_ids: set[str] = set()
            while len(runtime_terminal_ids) < len(runtime_capability_request_ids):
                event = await self.interaction_runtime.runtime.wait_runtime_event(
                    cursor,
                    dispatch_id=receipt.dispatch_id,
                )
                cursor = event.sequence
                if (
                    not event.terminal
                    or event.result is None
                    or event.request_id not in runtime_capability_request_ids
                    or event.request_id in runtime_terminal_ids
                ):
                    continue
                runtime_terminal_ids.add(event.request_id)
                terminal_capability_ids.add(event.request_id)
                self.session_log(
                    session_id,
                    "capability_terminal_reentry_event: dispatch_id=%s request_id=%s "
                    "capability_id=%s status=%s remaining=%s",
                    receipt.dispatch_id,
                    event.request_id,
                    event.capability_id,
                    event.type,
                    max(
                        0,
                        len(source_capability_request_ids)
                        - len(terminal_capability_ids),
                    ),
                )
                if len(terminal_capability_ids) < len(source_capability_request_ids):
                    await self._reenter_cognition_for_terminal_capability(
                        response=response,
                        result=event.result,
                        session_id=session_id,
                        generation=generation,
                    )

        try:
            execution = await self.interaction_runtime.wait_dispatch(
                dispatch
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.session_log(
                session_id,
                "detached_capability_completion_failed: interaction_id=%s "
                "error_type=%s error=%s",
                response.interaction_id,
                type(exc).__name__,
                exc,
            )
            execution = CapabilityRuntimeResult(
                interaction_id=response.interaction_id,
                status="failed",
            )

        record_session_workflow_stage(
            self,
            session_id,
            stage="trusted_capability_runtime_completion",
            started_monotonic_ms=started_ms,
            finished_monotonic_ms=now_ms(),
            status=execution.status,
            input_payload={
                "interaction_id": response.interaction_id,
                "dispatch_id": receipt.dispatch_id if receipt is not None else "",
            },
            output_payload=execution,
            errors=[
                {
                    "request_id": result.request_id,
                    "capability_id": result.capability_id,
                    "status": result.status,
                    "reason_code": result.reason_code,
                    "message": result.message,
                }
                for result in execution.results
                if result.status not in {"completed", "success"}
            ],
            metadata=summarize_provider_start_evidence(response, execution),
        )
        self.session_log(
            session_id,
            "detached_capability_runtime_done: interaction_id=%s status=%s "
            "results=%s runtime_ms=%.1f",
            response.interaction_id,
            execution.status,
            len(execution.results),
            now_ms() - started_ms,
        )
        for result in execution.results:
            self.conversation_state.update_pending_task_status_for_request_id(
                request_id=result.request_id,
                status=result.status,
            )

        has_soridormi_request = any(
            request.capability_id.startswith("soridormi.")
            for request in response.capabilities
        )
        provider_status = (
            await self._record_soridormi_post_status(session_id)
            if has_soridormi_request
            else None
        )
        completed_request_ids = {
            result.request_id for result in execution.results
        }
        if execution.status != "completed":
            for request in response.capabilities:
                if request.request_id in completed_request_ids:
                    continue
                self.conversation_state.update_pending_task_status_for_request_id(
                    request_id=request.request_id,
                    status="not_run",
                )
        recovery_confirmation_staged = (
            await self._maybe_stage_body_recovery_confirmation(
                response,
                execution,
                session_id,
            )
            if execution.status != "completed"
            else False
        )
        closure_status = await self._close_cognitive_execution(
            response=response,
            execution=execution,
            session_id=session_id,
            generation=generation,
            provider_status=provider_status,
            recovery_confirmation_staged=recovery_confirmation_staged,
        )
        response.metadata["cognitive_turn_closure_status"] = closure_status
        self._record_execution_experience_safely(
            response=response,
            execution=execution,
            session_id=session_id,
            confirmed_request_ids=confirmed_request_ids,
        )
        return execution

    def _interaction_task_done(self, task: asyncio.Task) -> None:
        active_tasks = getattr(self, "active_interaction_tasks", None)
        if isinstance(active_tasks, dict):
            active_tasks.pop(task, None)
        if self.active_interaction_task is task:
            replacement = next(
                (
                    (candidate, interaction_id)
                    for candidate, interaction_id in reversed(
                        list((active_tasks or {}).items())
                    )
                    if not candidate.done()
                ),
                None,
            )
            if replacement is None:
                self.active_interaction_task = None
                self.active_interaction_id = None
            else:
                self.active_interaction_task = replacement[0]
                self.active_interaction_id = replacement[1]
        if task.cancelled():
            return
        error = task.exception()
        if error is not None:
            logger.error(
                "Interaction runtime task failed: %s",
                error,
                exc_info=error,
            )

    async def _record_soridormi_post_status(
        self,
        session_id: str | None,
    ) -> dict[str, Any] | None:
        invoker = getattr(self.interaction_runtime, "soridormi_invoker", None)
        if invoker is None:
            self.session_log(
                session_id,
                "soridormi_post_status_failed: reason=provider_unavailable",
            )
            return None
        try:
            outcome = await asyncio.wait_for(
                invoker.invoke("soridormi.robot.get_status", {}),
                timeout=5.0,
            )
        except Exception as exc:
            self.session_log(
                session_id,
                "soridormi_post_status_failed: reason=%s",
                type(exc).__name__,
            )
            return None
        if outcome.status != "success":
            self.session_log(
                session_id,
                "soridormi_post_status_failed: reason=%s",
                outcome.error or outcome.status,
            )
            return None
        status = outcome.output if isinstance(outcome.output, dict) else {}
        self.session_log(
            session_id,
            "soridormi_post_status: mode=%s backend=%s safe_idle=%s "
            "active_task_present=%s emergency_stop=%s fallen=%s",
            status.get("mode"),
            status.get("backend"),
            status.get("safe_idle"),
            status.get("active_task") is not None,
            status.get("emergency_stop"),
            status.get("fallen"),
        )
        return status

    async def _maybe_stage_body_recovery_confirmation(
        self,
        response: InteractionResponse,
        execution: CapabilityRuntimeResult,
        session_id: str | None,
    ) -> bool:
        if execution.status == "cancelled":
            return False
        recovery = build_body_recovery_confirmation(
            response,
            execution.results,
            max_attempts=getattr(self, "body_recovery_max_attempts", 1),
            timeout_s=getattr(self, "body_recovery_confirmation_ttl_s", 10.0),
            language=str(response.metadata.get("language") or ""),
        )
        if recovery is None:
            return False
        return await self._stage_body_recovery_confirmation(
            recovery,
            session_id=session_id,
            language=str(response.metadata.get("language") or ""),
        )

    async def _stage_body_recovery_confirmation(
        self,
        recovery: BodyRecoveryConfirmation,
        *,
        session_id: str | None,
        language: str | None,
    ) -> bool:
        pending = self.confirmation_dialogue.begin(
            recovery.response,
            confirmed_request_ids=set(recovery.confirmed_request_ids),
            origin_session_id=session_id,
            conversation_id=self.conversation_state.conversation_id,
            language=language,
            prompt_override=recovery.prompt,
            ttl_s=getattr(self, "body_recovery_confirmation_ttl_s", 10.0),
        )
        self.session_log(
            session_id,
            "body_recovery_requested: confirmation_id=%s interaction_id=%s "
            "failed_request_ids=%s retry_request_ids=%s attempt=%s/%s expires_at=%.3f",
            pending.confirmation_id,
            recovery.response.interaction_id,
            ",".join(recovery.failed_request_ids),
            ",".join(recovery.retry_request_ids),
            recovery.attempt,
            recovery.max_attempts,
            pending.expires_at,
        )
        self.conversation_state.record_pending_task(
            sid=session_id,
            task_type="body_recovery_confirmation",
            status="awaiting_confirmation",
            summary=", ".join(
                request.capability_id
                for request in recovery.response.capabilities
                if request.request_id in recovery.confirmed_request_ids
            ),
            metadata={
                "confirmation_id": pending.confirmation_id,
                "interaction_id": recovery.response.interaction_id,
                "fingerprint": pending.fingerprint,
                "expires_at": pending.expires_at,
                "failed_request_ids": list(recovery.failed_request_ids),
                "retry_request_ids": list(recovery.retry_request_ids),
                "body_recovery_attempt": recovery.attempt,
                "body_recovery_max_attempts": recovery.max_attempts,
            },
        )
        prompt_response = self._host_speech_response(
            pending.prompt,
            style="confirm",
            source="host_body_recovery_confirmation",
        )
        prompt_dispatch = await self.interaction_runtime.submit_response(
            prompt_response,
            session_id=session_id,
        )
        prompt_execution = await self.interaction_runtime.wait_dispatch(prompt_dispatch)
        self._record_successfully_delivered_speech(
            prompt_response,
            prompt_execution,
            session_id=session_id,
            log_event="body_recovery_history_after_delivery",
        )
        return True

    def _prepared_interaction_response_for_record(
        self,
        response: InteractionResponse,
        *,
        session_id: str | None,
        confirmed_request_ids: set[str] | None,
    ) -> InteractionResponse:
        prepare = getattr(self.interaction_runtime, "prepare_response", None)
        if not callable(prepare):
            return response
        return prepare(
            response,
            session_id=session_id,
            confirmed_request_ids=confirmed_request_ids,
        )


    def _invalidate_output_state(
        self,
        *,
        cancel_cognitive_work: bool = True,
    ) -> None:
        self.playback_generation += 1
        self._playback_state().cancel_output_duck()
        self.resolve_all_playback_start_waiters(
            started=False,
            reason="interrupt",
        )
        if cancel_cognitive_work:
            self._cancel_active_routed_turns(
                excluding=asyncio.current_task(),
                cancel_all=False,
                reason="foreground_interaction_interrupted",
            )
        for task in list(self.active_synthesis_tasks):
            if not task.done():
                task.cancel()
        self.pending_audio.clear()
        getattr(self, "cancelled_playback_orders", set()).clear()
        while not self.playback_queue.empty():
            try:
                self.playback_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        self.next_playback_order = 0
        self.synthesis_order = 0

    def _schedule_output_abort(
        self,
        *,
        new_session_id: str | None,
        log_event: bool,
    ) -> None:
        tasks = getattr(self, "output_abort_tasks", None)
        if not isinstance(tasks, set):
            tasks = set()
            self.output_abort_tasks = tasks
        if any(not task.done() for task in tasks):
            return

        async def abort_and_log() -> None:
            await self.abort_output_stream()
            if new_session_id and log_event:
                self.session_log(
                    new_session_id,
                    "interrupt_previous_audio_done: playback_generation=%s",
                    self.playback_generation,
                )

        task = asyncio.create_task(abort_and_log())
        tasks.add(task)

        def done(completed: asyncio.Task) -> None:
            tasks.discard(completed)
            if completed.cancelled():
                return
            error = completed.exception()
            if error is not None:
                logger.warning(
                    "Detached output abort failed: %s",
                    error,
                    exc_info=error,
                )

        task.add_done_callback(done)

    async def interrupt_output(
        self,
        new_session_id: Optional[str] = None,
        *,
        log_event: bool = True,
        cancel_cognitive_work: bool = True,
    ):
        self._invalidate_output_state(
            cancel_cognitive_work=cancel_cognitive_work,
        )
        await self.abort_output_stream()
        if new_session_id and log_event:
            self.session_log(new_session_id, "interrupt_previous_audio_done: playback_generation=%s", self.playback_generation)

    async def _apply_reflex_cancellation(
        self,
        outcome: ReflexOutcome,
        *,
        source_turn_id: str,
    ) -> CancellationDispatchReceipt:
        """Apply one closed reflex scope without semantic goal guessing."""

        scope = outcome.cancellation_scope
        if scope == "none":
            raise ValueError("reflex cancellation requires a concrete scope")
        if scope == "specific_goal":
            raise ValueError(
                "specific_goal cancellation requires the Core's exact "
                "committed plan binding and cannot originate from ReflexOutcome"
            )
        if scope in {"current_interaction", "global_emergency"}:
            self._cancel_active_routed_turns(
                excluding=asyncio.current_task(),
                cancel_all=(scope == "global_emergency"),
                reason=f"protective_reflex:{scope}",
            )
        active_interaction_id = ""
        active_tasks = getattr(self, "active_interaction_tasks", None)
        active_host_interactions: list[
            tuple[asyncio.Task, str]
        ] = []
        if isinstance(active_tasks, dict):
            active_host_interactions = [
                (task, str(interaction_id).strip())
                for task, interaction_id in active_tasks.items()
                if not task.done() and str(interaction_id).strip()
            ]
            if active_host_interactions:
                active_interaction_id = active_host_interactions[-1][1]
        if not active_interaction_id:
            active_task = getattr(
                self,
                "active_interaction_task",
                None,
            )
            legacy_interaction_id = str(
                getattr(self, "active_interaction_id", None) or ""
            ).strip()
            if active_task is None or not active_task.done():
                active_interaction_id = legacy_interaction_id
            if (
                active_task is not None
                and not active_task.done()
                and legacy_interaction_id
                and all(
                    item[0] is not active_task
                    for item in active_host_interactions
                )
            ):
                active_host_interactions.append(
                    (active_task, legacy_interaction_id)
                )
        runtime_open_interaction_ids: list[str] = []
        runtime = getattr(
            getattr(self, "interaction_runtime", None),
            "runtime",
            None,
        )
        observe_execution = getattr(runtime, "execution_observation", None)
        if callable(observe_execution):
            try:
                observation = await observe_execution()
                runtime_open_interaction_ids = [
                    str(item).strip()
                    for item in observation.open_interaction_ids
                    if str(item).strip()
                ]
            except Exception as exc:
                logger.warning(
                    "Runtime execution observation failed during cancellation: %s",
                    exc,
                )
        if not active_interaction_id and runtime_open_interaction_ids:
            # Detached capability work intentionally outlives the foreground
            # interaction task. Runtime ownership is therefore the authoritative
            # fallback for current-interaction cancellation scope.
            active_interaction_id = runtime_open_interaction_ids[-1]
        if scope == "global_emergency":
            host_scope_interaction_ids = tuple(
                sorted(
                    {
                        interaction_id
                        for _, interaction_id in active_host_interactions
                    }.union(runtime_open_interaction_ids)
                )
            )
        elif (
            scope in {"output_only", "current_interaction"}
            and active_interaction_id
        ):
            host_scope_interaction_ids = (active_interaction_id,)
        else:
            host_scope_interaction_ids = ()
        receipt = CancellationDispatchReceipt(
            source_turn_id=source_turn_id,
            requested_scope=scope,
            effective_scope=scope,
        )
        dispatch_failures: list[str] = []
        emergency_evidence: dict[str, Any] = {}
        phase_operations: list[tuple[str, Any]] = []

        # Safety dispatches lead the first phase. Output teardown can wait on a
        # device write lock; it must never serialize motion cancellation or an
        # emergency stop behind that audio cleanup.
        if scope == "global_emergency":
            emergency_stop = getattr(
                self.interaction_runtime,
                "emergency_stop",
                None,
            )
            if callable(emergency_stop):
                phase_operations.append(
                    (
                        "emergency_stop",
                        emergency_stop(reason=outcome.reason),
                    )
                )
            else:
                emergency_evidence = {
                    "status": "unavailable",
                    "reason": "emergency_stop_dispatch_unsupported",
                }
                dispatch_failures.append(
                    "emergency_stop:dispatch_unsupported"
                )

        runtime_dispatch_required = not (
            scope in {"output_only", "current_interaction"}
            and not active_interaction_id
        )
        runtime_operation_kind = ""
        if runtime_dispatch_required:
            directive = CancellationDirective(
                source_turn_id=source_turn_id,
                requested_scope=scope,
                foreground_interaction_id=(
                    active_interaction_id
                    if scope
                    in {
                        "output_only",
                        "current_interaction",
                        "specific_goal",
                    }
                    else None
                ),
                target_goal_ids=outcome.target_goal_ids,
                reason=outcome.reason,
            )
            cancel_scope = getattr(
                self.interaction_runtime,
                "cancel_scope",
                None,
            )
            if callable(cancel_scope):
                runtime_operation_kind = "runtime_scope"
                phase_operations.append(
                    (
                        runtime_operation_kind,
                        cancel_scope(directive),
                    )
                )
            else:
                dispatch_failures.append(
                    "capability_runtime:scoped_dispatch_unsupported"
                )

        if scope in {
            "output_only",
            "current_interaction",
            "global_emergency",
        }:
            try:
                self._invalidate_output_state(
                    cancel_cognitive_work=False,
                )
                self._schedule_output_abort(
                    new_session_id=source_turn_id,
                    log_event=False,
                )
            except Exception as exc:
                dispatch_failures.append(
                    "output_invalidation:"
                    f"{type(exc).__name__}:{str(exc)[:300]}"
                )

        phase_results = await asyncio.gather(
            *(operation for _, operation in phase_operations),
            return_exceptions=True,
        )
        for (operation_kind, _), result in zip(
            phase_operations,
            phase_results,
            strict=True,
        ):
            if operation_kind == "runtime_scope":
                if isinstance(result, BaseException):
                    dispatch_failures.append(
                        "capability_runtime:"
                        f"{type(result).__name__}:{str(result)[:300]}"
                    )
                elif isinstance(result, CancellationDispatchReceipt):
                    receipt = result
                else:
                    dispatch_failures.append(
                        "capability_runtime:invalid_dispatch_receipt"
                    )
            elif operation_kind == "emergency_stop":
                if isinstance(result, BaseException):
                    emergency_evidence = {
                        "status": "failed",
                        "reason": (
                            f"{type(result).__name__}:{str(result)[:300]}"
                        ),
                    }
                    dispatch_failures.append(
                        "emergency_stop:"
                        f"{type(result).__name__}:{str(result)[:300]}"
                    )
                elif isinstance(result, dict):
                    emergency_evidence = result
                else:
                    emergency_evidence = {
                        "status": "failed",
                        "reason": "invalid_emergency_stop_evidence",
                    }
                    dispatch_failures.append(
                        "emergency_stop:invalid_evidence"
                    )
        receipt = receipt.model_copy(
            update={
                "interaction_ids": tuple(
                    sorted(
                        {
                            *receipt.interaction_ids,
                            *host_scope_interaction_ids,
                        }
                    )
                ),
                "host_interaction_ids": tuple(
                    sorted(
                        {
                            *receipt.host_interaction_ids,
                            *host_scope_interaction_ids,
                        }
                    )
                ),
                "dispatch_failures": tuple(
                    dict.fromkeys(
                        [
                            *receipt.dispatch_failures,
                            *dispatch_failures,
                        ]
                    )
                ),
                "emergency_stop_evidence": (
                    emergency_evidence
                    if scope == "global_emergency"
                    else receipt.emergency_stop_evidence
                ),
                "output_invalidation_requested": (
                    receipt.output_invalidation_requested
                    or scope
                    in {
                        "output_only",
                        "current_interaction",
                        "global_emergency",
                    }
                ),
            }
        )

        # A provider task may have been inside the speech scheduler while
        # runtime cancellation ran. Invalidate once more so no late synthesis
        # can re-enter playback. Device teardown remains detached: a blocked
        # audio driver must not keep this protective reflex active or delay a
        # later emergency reflex.
        if scope in {
            "output_only",
            "current_interaction",
            "global_emergency",
        }:
            try:
                self._invalidate_output_state(
                    cancel_cognitive_work=False,
                )
            except Exception as exc:
                receipt = receipt.model_copy(
                    update={
                        "dispatch_failures": tuple(
                            dict.fromkeys(
                                [
                                    *receipt.dispatch_failures,
                                    "output_reinvalidation:"
                                    f"{type(exc).__name__}:"
                                    f"{str(exc)[:300]}",
                                ]
                            )
                        )
                    }
                )

        host_task_cancel_requested: list[str] = []
        host_cancel_candidates: list[tuple[asyncio.Task, str]] = []
        if scope == "global_emergency":
            # Global emergency is also a host-workflow boundary. If the
            # runtime dispatch fails before it can install durable rules, no
            # older preflight interaction may survive and start work later.
            host_cancel_candidates = list(active_host_interactions)
        elif (
            scope == "current_interaction"
            and not receipt.selected_request_bindings
        ):
            host_cancel_candidates = [
                (task, interaction_id)
                for task, interaction_id in active_host_interactions
                if interaction_id == active_interaction_id
            ]
        current_task = asyncio.current_task()
        for task, interaction_id in host_cancel_candidates:
            if (
                task is not None
                and task is not current_task
                and not task.done()
            ):
                task.cancel()
                if interaction_id:
                    host_task_cancel_requested.append(
                        interaction_id
                    )
        if host_task_cancel_requested:
            receipt = receipt.model_copy(
                update={
                    "host_task_cancel_requested_interaction_ids": tuple(
                        sorted(
                            {
                                *receipt.host_task_cancel_requested_interaction_ids,
                                *host_task_cancel_requested,
                            }
                        )
                    )
                }
            )

        self.session_log(
            source_turn_id,
            "cognitive_gateway_cancellation_dispatched: "
            "requested_scope=%s effective_scope=%s interactions=%s "
            "selected=%s active=%s queued=%s non_interruptible=%s "
            "provider_failures=%s dispatch_failures=%s",
            receipt.requested_scope,
            receipt.effective_scope,
            ",".join(receipt.interaction_ids) or "none",
            len(receipt.selected_request_bindings),
            len(receipt.active_request_bindings),
            len(receipt.queued_request_bindings),
            len(receipt.non_interruptible_request_bindings),
            len(receipt.provider_cancel_failure_evidence),
            len(receipt.dispatch_failures),
        )
        emergency_status = str(
            receipt.emergency_stop_evidence.get("status") or ""
        )
        if scope == "global_emergency" and emergency_status != "success":
            self.session_log(
                source_turn_id,
                "cognitive_gateway_emergency_stop_unconfirmed: status=%s "
                "evidence=%s",
                emergency_status or "missing",
                json.dumps(
                    receipt.emergency_stop_evidence,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            )
        return receipt

    async def interrupt(self, new_session_id: Optional[str] = None):
        await self.interrupt_output(new_session_id, log_event=False)
        active = getattr(self, "active_interaction_task", None)
        active_interaction_id = str(
            getattr(self, "active_interaction_id", None) or ""
        ).strip()
        cancel_scope = getattr(self.interaction_runtime, "cancel_scope", None)
        if callable(cancel_scope) and active_interaction_id:
            await cancel_scope(
                CancellationDirective(
                    source_turn_id=str(new_session_id or "semantic_interrupt"),
                    requested_scope="current_interaction",
                    foreground_interaction_id=active_interaction_id,
                    reason="Core authorized interruption of foreground work",
                )
            )
        if active is not None and not active.done():
            active.cancel()
        if new_session_id:
            self.session_log(new_session_id, "interrupt_previous_audio_done: playback_generation=%s", self.playback_generation)

    def mic_callback(self, indata, frames, time_info, status):
        return input_session_runtime_for(self).mic_callback(indata, frames, time_info, status)

    async def handle_vad_audio(
        self,
        audio: bytes,
        *,
        started_during_playback: bool = False,
        playback_generation_at_start: int | None = None,
    ):
        return await input_session_runtime_for(self).handle_vad_audio(audio, started_during_playback=started_during_playback, playback_generation_at_start=playback_generation_at_start)

    def _has_active_protective_reflex(
        self,
        *,
        excluding: asyncio.Task | None = None,
    ) -> bool:
        return input_session_runtime_for(self)._has_active_protective_reflex(excluding=excluding)

    def _cancel_active_routed_turns(
        self,
        *,
        excluding: asyncio.Task | None,
        cancel_all: bool,
        reason: str,
    ) -> tuple[str, ...]:
        return input_session_runtime_for(self)._cancel_active_routed_turns(excluding=excluding, cancel_all=cancel_all, reason=reason)

    def _launch_routed_turn(self, user_text: str, session_id: str) -> None:
        return input_session_runtime_for(self)._launch_routed_turn(user_text, session_id)

    def _on_routed_turn_done(
        self,
        task: asyncio.Task,
        session_id: str,
        *,
        concurrent_reflex: bool = False,
    ) -> None:
        return input_session_runtime_for(self)._on_routed_turn_done(task, session_id, concurrent_reflex=concurrent_reflex)

    def _queue_vad_utterance(
        self,
        audio: bytes,
        *,
        started_during_playback: bool = False,
        playback_generation_at_start: int | None = None,
    ) -> None:
        return input_session_runtime_for(self)._queue_vad_utterance(audio, started_during_playback=started_during_playback, playback_generation_at_start=playback_generation_at_start)

    def _on_asr_task_done(self, task: asyncio.Task) -> None:
        return input_session_runtime_for(self)._on_asr_task_done(task)

    async def _feed_vad_pcm16(self, pcm_16k: bytes) -> None:
        return await input_session_runtime_for(self)._feed_vad_pcm16(pcm_16k)

    async def mic_stream(self):
        return await input_session_runtime_for(self).mic_stream()

    async def injected_audio_stream(self):
        return await input_session_runtime_for(self).injected_audio_stream()

    async def _session_idle_sweeper(self) -> None:
        return await input_session_runtime_for(self)._session_idle_sweeper()

    @staticmethod
    def _spoken_text_response_schema(
        *,
        max_chars: int,
        semantic_state: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        properties: dict[str, Any] = {
            "text": {
                "type": "string",
                "minLength": 1,
                "maxLength": max_chars,
            }
        }
        required = ["text"]
        for key, value in (semantic_state or {}).items():
            if key == "text":
                raise ValueError("semantic_state must not redefine text")
            properties[key] = {"type": "string", "const": value}
            required.append(key)
        return {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        }

    def _validate_spoken_text_contract(
        self,
        text: str,
        *,
        purpose: str,
        max_chars: int,
        one_sentence: bool = False,
        require_terminal_punctuation: bool = False,
        language: str | None = None,
    ) -> str:
        raw = str(text or "")
        if "\n" in raw or "\r" in raw:
            raise RuntimeError(f"{purpose} returned multiline speech")
        normalized = self.normalize_tts_candidate(raw)
        if not self.is_valid_tts_text(normalized):
            raise RuntimeError(f"{purpose} returned no valid spoken text")
        if len(normalized) > max_chars:
            raise RuntimeError(
                f"{purpose} exceeded spoken text limit: "
                f"chars={len(normalized)} max_chars={max_chars}"
            )
        if one_sentence:
            sentence_endings = re.findall(r"[.!?。！？]+", normalized)
            if len(sentence_endings) > 1:
                raise RuntimeError(f"{purpose} returned more than one sentence")
        if require_terminal_punctuation and not re.search(r"[.!?。！？]$", normalized):
            raise RuntimeError(f"{purpose} returned an incomplete sentence")
        language_code = str(language or "").strip().lower()
        if language_code.startswith("zh") and not re.search(
            r"[\u3400-\u4dbf\u4e00-\u9fff]",
            normalized,
        ):
            raise RuntimeError(f"{purpose} did not use the required Chinese language")
        return normalized

    def _decode_spoken_text_envelope(
        self,
        data: dict[str, Any],
        *,
        purpose: str,
        max_chars: int,
        one_sentence: bool = False,
        require_terminal_punctuation: bool = False,
        language: str | None = None,
        suppressed_thinking_chars: int = 0,
        expected_semantic_state: dict[str, str] | None = None,
    ) -> str:
        thinking = data.get("thinking")
        if isinstance(thinking, str):
            suppressed_thinking_chars += len(thinking)
        if suppressed_thinking_chars:
            logger.warning(
                "%s suppressed non-spoken model thinking: chars=%s",
                purpose,
                suppressed_thinking_chars,
            )

        done_reason = str(data.get("done_reason") or "").strip().lower()
        if done_reason and done_reason != "stop":
            raise RuntimeError(
                f"{purpose} did not complete normally: done_reason={done_reason}"
            )

        raw_response = data.get("response")
        if not isinstance(raw_response, str):
            raise RuntimeError(f"{purpose} returned no response string")
        try:
            envelope = json.loads(raw_response)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"{purpose} returned non-JSON output; refusing to speak it"
            ) from exc
        expected_state = dict(expected_semantic_state or {})
        expected_keys = {"text", *expected_state}
        if not isinstance(envelope, dict) or set(envelope) != expected_keys:
            raise RuntimeError(
                f"{purpose} returned an invalid spoken-output envelope"
            )
        mismatched_state = {
            key: {"expected": value, "actual": envelope.get(key)}
            for key, value in expected_state.items()
            if envelope.get(key) != value
        }
        if mismatched_state:
            raise RuntimeError(
                f"{purpose} changed authoritative semantic state: "
                + json.dumps(mismatched_state, ensure_ascii=False, sort_keys=True)
            )
        return self._validate_spoken_text_contract(
            envelope.get("text", ""),
            purpose=purpose,
            max_chars=max_chars,
            one_sentence=one_sentence,
            require_terminal_punctuation=require_terminal_punctuation,
            language=language,
        )

    @staticmethod
    def _runtime_ready_greeting_time_context(
        local_now: datetime | None = None,
    ) -> dict[str, str]:
        observed = local_now or datetime.now().astimezone()
        if observed.tzinfo is None:
            observed = observed.astimezone()
        hour = observed.hour
        if 5 <= hour < 11:
            local_period = "morning"
        elif 11 <= hour < 14:
            local_period = "midday"
        elif 14 <= hour < 18:
            local_period = "afternoon"
        elif 18 <= hour < 23:
            local_period = "evening"
        else:
            local_period = "late_night"
        offset = observed.strftime("%z")
        if len(offset) == 5:
            offset = f"{offset[:3]}:{offset[3:]}"
        return {
            "local_iso": observed.isoformat(timespec="minutes"),
            "local_period": local_period,
            "timezone": str(observed.tzname() or "local"),
            "utc_offset": offset,
            "weekday": observed.strftime("%A"),
        }

    def _runtime_ready_greeting_prompt(
        self,
        *,
        local_now: datetime | None = None,
    ) -> str:
        language = self.runtime_ready_greeting_language
        identity_json = self._owner_identity_json()
        mind_summary = self._owner_mind_summary()
        time_context = json.dumps(
            self._runtime_ready_greeting_time_context(local_now),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return (
            "Chromie has just woken up and can now hear and talk with her family. "
            "She is the family's six-year-old secretary. Write exactly one complete, "
            "very short greeting she naturally says after waking up. Sound like a "
            "smart, warm six-year-old child, not a device or an adult professional. "
            f"Speak only in {language}. "
            "Do not explain the task, analyze the request, expose reasoning, or mention "
            "the prompt. Do not mention readiness, startup, initialization, systems, "
            "services, models, being an assistant, or operational status. Do not "
            "introduce yourself, repeat your name or age, or ask what help is required. "
            "Use the supplied local period only as quiet grounding, not as a command "
            "to announce the time of day. Prefer the spontaneous first-person delight "
            "of a six-year-old who has just opened her eyes, such as happily saying that "
            "she is awake and looking forward to being together. Do not default to a "
            "formal morning, afternoon, or evening salutation. Do not quote the exact "
            "clock time, calendar date, or weekday. "
            "Do not invent meals, hunger, sleepiness, weather, or another personal "
            "state. Do not ask a question or end mid-clause. "
            "No individual family member has been identified at startup. Use no "
            "vocative, addressee noun, personal name, kinship term, social category, "
            "or relationship label at all. Speak naturally into the shared room without "
            "naming an addressee; a cheerful first-person wake-up line is preferred over "
            "a formal greeting. Return only a JSON "
            "object with one field named text. The text value is the complete spoken "
            "sentence, normally four to twelve Chinese characters and never more "
            "than twenty-four characters. Prefer a complete greeting over filling "
            "the available length.\n\n"
            f"Grounded local temporal context JSON: {time_context}\n"
            f"Owner-approved identity JSON: {identity_json}\n"
            f"Owner-approved mind summary: {mind_summary}\n"
        )

    @staticmethod
    def _validate_runtime_ready_greeting_completion(text: str) -> str:
        if not re.search(r"[。！？!?]$", str(text or "").strip()):
            raise RuntimeError(
                "runtime ready greeting is not a complete punctuated sentence"
            )
        return text

    async def _generate_runtime_ready_greeting(self) -> tuple[str, str]:
        try:
            configured = self._validate_spoken_text_contract(
                self.runtime_ready_greeting_text,
                purpose="configured runtime ready greeting",
                max_chars=24,
                one_sentence=True,
                language=self.runtime_ready_greeting_language,
            )
        except RuntimeError:
            configured = ""
        if configured:
            return configured, "configured"

        model = (
            self.runtime_ready_greeting_model
            or self.host_settings.model_generation.ready_greeting_fallback_model
            or self.ollama_model
        )
        payload = {
            "model": model,
            "prompt": self._runtime_ready_greeting_prompt(),
            "stream": False,
            "think": False,
            "format": self._spoken_text_response_schema(max_chars=24),
            "keep_alive": self.host_settings.model_generation.keep_alive,
            "options": {
                "num_ctx": self.host_settings.model_generation.ready_greeting_num_ctx,
                "num_predict": self.runtime_ready_greeting_num_predict,
                "temperature": 0.55,
                "top_p": 0.9,
            },
        }
        timeout_s = self.runtime_ready_greeting_generation_timeout_ms / 1000.0

        async def request_greeting(request_payload: dict[str, Any]) -> dict[str, Any]:
            session = await self.get_http_session()
            async with session.post(self.llm_url, json=request_payload) as response:
                body = await response.text()
                if response.status != 200:
                    raise RuntimeError(
                        f"runtime greeting model returned HTTP {response.status}: "
                        f"{body[:300]}"
                    )
                provider_data = json.loads(body)
                return enforce_non_thinking_ollama_response(
                    provider_data, structured_output=True
                ).response

        generation_error: Exception | None = None
        for attempt in range(2):
            request_payload = dict(payload)
            if attempt:
                request_payload["prompt"] = (
                    f"{payload['prompt']}\n"
                    "The previous candidate violated the greeting contract. "
                    "Choose a different short, time-grounded greeting without "
                    "self-introduction, age, invented personal state, or any addressee "
                    "noun, name, social category, or relationship label."
                )
            try:
                data = await asyncio.wait_for(
                    request_greeting(request_payload),
                    timeout=timeout_s,
                )
                generated = self._decode_spoken_text_envelope(
                    data,
                    purpose="runtime ready greeting",
                    max_chars=24,
                    one_sentence=True,
                    language=self.runtime_ready_greeting_language,
                )
                self._validate_runtime_ready_greeting_completion(generated)
                return generated, f"llm:{model}"
            except Exception as exc:
                generation_error = exc
                logger.warning(
                    "Runtime ready greeting generation attempt %s failed: %s",
                    attempt + 1,
                    exc,
                )
        logger.warning(
            "Runtime ready greeting generation failed after retries: %s",
            generation_error,
        )
        try:
            fallback = self._validate_spoken_text_contract(
                self.runtime_ready_greeting_fallback_text,
                purpose="runtime ready greeting fallback",
                max_chars=24,
                one_sentence=True,
                language=self.runtime_ready_greeting_language,
            )
        except RuntimeError as fallback_exc:
            logger.warning("Runtime ready greeting fallback rejected: %s", fallback_exc)
            return "", "unavailable"
        return fallback, "fallback"

    def _build_runtime_ready_greeting_coordinator(
        self,
    ) -> RuntimeReadyGreetingCoordinator:
        async def schedule_text(text: str) -> dict[str, Any]:
            return await self.schedule_tts_text(text, session_id=None)

        orientation_enabled = bool(
            getattr(self, "enable_soridormi_capabilities", False)
        )

        async def execute_orientation() -> dict[str, Any]:
            return await execute_default_runtime_ready_orientation(
                self.interaction_runtime,
                enable_soridormi_capabilities=getattr(
                    self, "enable_soridormi_capabilities", False
                ),
            )

        return RuntimeReadyGreetingCoordinator(
            policy=RuntimeReadyGreetingPolicy(
                enabled=self.runtime_ready_greeting_enabled,
                audio_input_mode=self.audio_input_mode,
                audio_output_mode=self.audio_output_mode,
                timeout_ms=self.runtime_ready_greeting_timeout_ms,
                orientation_enabled=orientation_enabled,
                orientation_timeout_ms=min(
                    5000, self.runtime_ready_greeting_timeout_ms
                ),
                speech_enabled=bool(
                    getattr(
                        getattr(
                            getattr(self, "host_settings", None),
                            "playback",
                            None,
                        ),
                        "ready_greeting_speech_enabled",
                        getattr(
                            self,
                            "runtime_ready_greeting_speech_enabled",
                            False,
                        ),
                    )
                ),
            ),
            generate_greeting=self._generate_runtime_ready_greeting,
            is_valid_text=self.is_valid_tts_text,
            schedule_text=schedule_text,
            playback_start_key=self.playback_start_key,
            playback_start_waiters=getattr(self, "playback_start_waiters", {}),
            next_playback_order=lambda: getattr(self, "next_playback_order", 0),
            execute_orientation=execute_orientation,
        )

    async def _announce_runtime_ready(self) -> None:
        """Delegate startup orientation and optional speech to one collaborator."""

        await self._build_runtime_ready_greeting_coordinator().announce()

    async def run(self):
        gate = ServiceReadinessGate(
            asr_url=self.asr_url,
            tts_url=self.tts_url,
            llm_url=self.llm_url,
            ollama_model=self.ollama_model,
            speaker_id=self.speaker_id,
            get_http_session=self.get_http_session,
            agent_url=self.agent_url,
            enable_agent=self.enable_agent,
        )
        self.asr_ws = await gate.wait_until_ready()
        self.playback_task = asyncio.create_task(self.playback_worker())
        if any(
            self._uses_followed_system_default(kind)
            for kind in ("input", "output")
        ):
            self.audio_device_monitor_task = asyncio.create_task(
                self._audio_device_monitor()
            )
        await self._announce_runtime_ready()
        if self.audio_input_mode == "stdin":
            await self.injected_audio_stream()
        else:
            await self.mic_stream()

    async def cleanup(self):
        sessions = getattr(self, "sessions", None)
        if sessions is not None:
            try:
                await self._sample_accelerator_resources(reason="session_finish")
            except Exception as exc:
                logger.debug(
                    "Final accelerator telemetry sample failed: %s",
                    type(exc).__name__,
                )
            sessions.finalize_active_sessions(reason="orchestrator_cleanup")
        self.resolve_all_playback_start_waiters(
            started=False,
            reason="cleanup",
        )
        audio_device_monitor = getattr(self, "audio_device_monitor_task", None)
        if audio_device_monitor is not None and not audio_device_monitor.done():
            audio_device_monitor.cancel()
            await asyncio.gather(
                audio_device_monitor,
                return_exceptions=True,
            )
        for task in list(self.active_synthesis_tasks):
            task.cancel()
        if self.active_asr_task and not self.active_asr_task.done():
            self.active_asr_task.cancel()
        active_turn_tasks = set(
            getattr(self, "active_turn_tasks", {}).keys()
        )
        active_turn_task = getattr(self, "active_turn_task", None)
        if active_turn_task is not None:
            active_turn_tasks.add(active_turn_task)
        for task in active_turn_tasks:
            if not task.done():
                task.cancel()
        for task in list(
            getattr(self, "concurrent_protective_reflex_tasks", set())
        ):
            if not task.done():
                task.cancel()
        output_abort_tasks = list(
            getattr(self, "output_abort_tasks", set())
        )
        for task in output_abort_tasks:
            if not task.done():
                task.cancel()
        if output_abort_tasks:
            await asyncio.gather(
                *output_abort_tasks,
                return_exceptions=True,
            )
        self.active_reflex_task = None
        self._pending_turn_after_reflex = deque()
        self._pending_vad_audio = None
        sweeper = getattr(self, "session_idle_sweeper_task", None)
        if sweeper is not None and not sweeper.done():
            sweeper.cancel()
        for task in list(getattr(self, "observability_tasks", set())):
            if not task.done():
                task.cancel()
        if self.playback_task and not self.playback_task.done():
            await self.playback_queue.put((None, None, None, None, None, None))
            self.playback_task.cancel()
        await self.close_output_stream()
        if self.asr_ws:
            await self.asr_ws.close()
        if self.http_session and not self.http_session.closed:
            await self.http_session.close()
        self.audio_mgr.close()


async def main():
    assistant = VoiceAssistant()
    try:
        await assistant.run()
    finally:
        await assistant.cleanup()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Orchestrator stopped by operator")
