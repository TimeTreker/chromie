from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv

ORCH_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = ORCH_DIR.parent
load_dotenv(PROJECT_ROOT / ".env.runtime")
load_dotenv(ORCH_DIR / ".env.local")

import aiohttp
import numpy as np
import websockets
from scipy import signal

from orchestrator.audio_device_manager import AudioDeviceManager
from orchestrator.audio_injection import read_audio_packet
from orchestrator.readiness import ServiceReadinessGate
from orchestrator.vad import VAD
from orchestrator.clients.action_client import ActionClient
from orchestrator.clients.agent_client import AgentClient
from orchestrator.clients.router_client import RouterClient
from orchestrator.runtime.abilities import (
    AbilityRegistry,
    build_default_ability_registry,
)
from orchestrator.runtime.body_recovery import (
    BodyRecoveryConfirmation,
    build_body_recovery_confirmation,
)
from orchestrator.runtime.confirmation import ConfirmationDialogue
from orchestrator.runtime.named_goal_cancellation import (
    ActiveGoalCancellationRequiresRuntimeDispatch,
    NamedGoalCancellationClosureError,
    cancellation_target_goal_ids,
    dispatch_named_goal_cancellation,
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
    GatewayCoreCompatibilityAdapter,
)
from orchestrator.runtime.conversation_state import ConversationStateManager
from orchestrator.runtime.episode import EpisodeRecorder
from orchestrator.runtime.experience import ExperienceManager
from orchestrator.runtime.fast_first_audio import (
    CachedFastFirstAudio,
    FastFirstAudioCache,
)
from orchestrator.runtime.deepthinking_policy import (
    DeepThinkingDelegationPolicy,
    DeepThinkingPolicyConfig,
)
from orchestrator.runtime.interaction_coordinator import (
    InteractionRuntimeCoordinator,
    build_soridormi_invoker,
)
from orchestrator.runtime.mind import MindManager
from orchestrator.runtime.post_interrupt import lock_post_interrupt_physical_resume
from orchestrator.runtime.outcome_response import compose_outcome_response
from orchestrator.runtime.response_plan import validate_immediate_response_plan
from orchestrator.runtime.session import SessionTracker, now_ms
from shared.chromie_runtime.accelerator_telemetry import (
    ACCELERATOR_SAMPLE_MODULE,
    AcceleratorTelemetrySampler,
)
from shared.chromie_runtime.runtime_trace import TraceModule, runtime_tracer
from orchestrator.runtime.skill_runtime import SkillRuntimeResult
from orchestrator.schemas.agent import AgentResult, SpeechItem
from orchestrator.schemas.route import RouteDecision
from shared.chromie_contracts.interaction import (
    InteractionResponse,
    InteractionSpeech,
    SkillRequest,
    SkillResult,
)
from shared.chromie_contracts.tool_result import (
    ToolResultEvidence,
    ToolResultInterpretationRequest,
    canonical_value_sha256,
)
from shared.chromie_contracts.reflex import (
    CancellationDirective,
    CancellationDispatchReceipt,
    DEFAULT_REFLEX_FILTER,
    ReflexOutcome,
)
from shared.chromie_contracts.user_turn import UserTurnEnvelope
from shared.chromie_contracts.semantic_authority import (
    SemanticAuthorityClaim,
    context_with_semantic_authority,
)
from shared.chromie_runtime.llm_diagnostics import (
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
VAD_TRACE_MODULE = TraceModule(
    name="orchestrator.vad",
    component_type="audio_input",
    implementation="ChromieOrchestrator",
)
ASR_TRACE_MODULE = TraceModule(
    name="orchestrator.asr",
    component_type="speech_recognition",
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


def _sounddevice() -> Any:
    import sounddevice as sd

    return sd


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int, *, minimum: int = 0) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return max(minimum, int(value))
    except ValueError:
        return default


def env_float(name: str, default: float, *, minimum: float = 0.0) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return max(minimum, float(value))
    except ValueError:
        return default


class VoiceAssistant:
    def __init__(self):
        self.asr_url = os.getenv("ASR_URL", "ws://localhost:9001")
        self.tts_url = os.getenv("TTS_URL", "ws://localhost:5000")
        self.llm_url = os.getenv("LLM_URL", "http://localhost:11434/api/generate")
        self.ollama_model = os.getenv("OLLAMA_MODEL", "gemma4:e2b")

        self.enable_router = env_bool("ORCH_ENABLE_ROUTER", False)
        self.enable_agent = env_bool("ORCH_ENABLE_AGENT", False)
        self.enable_interaction_response = env_bool(
            "ORCH_ENABLE_INTERACTION_RESPONSE",
            False,
        )
        self.enable_soridormi_skills = env_bool(
            "ORCH_ENABLE_SORIDORMI_SKILLS",
            False,
        )
        self.auto_confirm_sim_skills = env_bool(
            "ORCH_AUTO_CONFIRM_SIM_SKILLS",
            False,
        )
        self.addressedness_gate_enabled = env_bool(
            "ORCH_ADDRESSEDNESS_GATE_ENABLED",
            True,
        )
        self.addressedness_engagement_timeout_s = env_float(
            "ORCH_ADDRESSEDNESS_ENGAGEMENT_TIMEOUT_SEC",
            45.0,
            minimum=1.0,
        )
        self.fast_first_response_enabled = env_bool(
            "ORCH_FAST_FIRST_RESPONSE_ENABLED",
            True,
        )
        self.fast_first_tool_response_enabled = env_bool(
            "ORCH_FAST_FIRST_TOOL_RESPONSE_ENABLED",
            False,
        )
        self.router_generated_fast_speech_enabled = env_bool(
            "ORCH_ROUTER_GENERATED_FAST_SPEECH_ENABLED",
            False,
        )
        self.fast_first_audio_enabled = env_bool(
            "ORCH_FAST_FIRST_AUDIO_ENABLED",
            True,
        )
        self.fast_first_audio_hedge_ms = env_int(
            "ORCH_FAST_FIRST_AUDIO_HEDGE_MS",
            750,
            minimum=0,
        )
        self.fast_first_audio_prime_on_startup = env_bool(
            "ORCH_FAST_FIRST_AUDIO_PRIME_ON_STARTUP",
            True,
        )
        self.fast_first_audio_prime_timeout_ms = env_int(
            "ORCH_FAST_FIRST_AUDIO_PRIME_TIMEOUT_MS",
            120000,
            minimum=1000,
        )
        self.fast_first_audio_content_gate_enabled = env_bool(
            "ORCH_FAST_FIRST_AUDIO_CONTENT_GATE_ENABLED",
            True,
        )
        self.fast_first_audio_max_cue_seconds = env_float(
            "ORCH_FAST_FIRST_AUDIO_MAX_CUE_SECONDS",
            4.0,
            minimum=0.25,
        )
        self.fast_first_audio_transcript_min_similarity = env_float(
            "ORCH_FAST_FIRST_AUDIO_TRANSCRIPT_MIN_SIMILARITY",
            0.65,
            minimum=0.0,
        )
        self.fast_first_audio_generation_attempts = env_int(
            "ORCH_FAST_FIRST_AUDIO_GENERATION_ATTEMPTS",
            2,
            minimum=1,
        )
        fast_first_cache_dir = Path(
            os.getenv(
                "ORCH_FAST_FIRST_AUDIO_CACHE_DIR",
                ".chromie/cache/fast-first-audio",
            )
        ).expanduser()
        if not fast_first_cache_dir.is_absolute():
            fast_first_cache_dir = PROJECT_ROOT / fast_first_cache_dir
        self.fast_first_audio_cache = FastFirstAudioCache(
            fast_first_cache_dir,
            enabled=(
                self.fast_first_response_enabled
                and self.fast_first_audio_enabled
            ),
            prime_on_startup=self.fast_first_audio_prime_on_startup,
            request_timeout_s=min(
                30.0,
                self.fast_first_audio_prime_timeout_ms / 1000.0,
            ),
            content_validation_enabled=self.fast_first_audio_content_gate_enabled,
            max_cue_seconds=self.fast_first_audio_max_cue_seconds,
            transcript_min_similarity=min(
                1.0,
                self.fast_first_audio_transcript_min_similarity,
            ),
            generation_attempts=self.fast_first_audio_generation_attempts,
            cache_revision=os.getenv(
                "ORCH_FAST_FIRST_AUDIO_CACHE_REVISION",
                "",
            ),
        )
        self.fast_planner_mode = os.getenv("ORCH_FAST_PLANNER_MODE", "off").strip().lower()
        if self.fast_planner_mode not in {"off", "report_only"}:
            raise ValueError("ORCH_FAST_PLANNER_MODE must be off or report_only")
        self.fast_planner_timeout_ms = env_int("ORCH_FAST_PLANNER_TIMEOUT_MS", 3000, minimum=100)
        self.deep_planner_mode = os.getenv("ORCH_DEEP_PLANNER_MODE", "off").strip().lower()
        if self.deep_planner_mode not in {"off", "report_only"}:
            self.deep_planner_mode = "off"
        self.deep_planner_timeout_ms = env_int("ORCH_DEEP_PLANNER_TIMEOUT_MS", 10000, minimum=100)
        self.response_composer_mode = os.getenv(
            "ORCH_RESPONSE_COMPOSER_MODE", "off"
        ).strip().lower()
        if self.response_composer_mode not in {"off", "report_only"}:
            raise ValueError("ORCH_RESPONSE_COMPOSER_MODE must be off or report_only")
        self.response_composer_timeout_ms = env_int(
            "ORCH_RESPONSE_COMPOSER_TIMEOUT_MS", 5000, minimum=100
        )
        self.tool_result_interpreter_timeout_ms = env_int(
            "ORCH_TOOL_RESULT_INTERPRETER_TIMEOUT_MS", 5500, minimum=100
        )
        self.goal_association_mode = os.getenv(
            "ORCH_GOAL_ASSOCIATION_MODE",
            "off",
        ).strip().lower()
        if self.goal_association_mode not in {"off", "report_only"}:
            raise ValueError("ORCH_GOAL_ASSOCIATION_MODE must be off or report_only")
        self.goal_association_timeout_ms = env_int(
            "ORCH_GOAL_ASSOCIATION_TIMEOUT_MS",
            3500,
            minimum=100,
        )
        self.task_continuity_mode = os.getenv(
            "ORCH_TASK_CONTINUITY_MODE",
            "off",
        ).strip().lower()
        if self.task_continuity_mode not in {"off", "report_only", "apply"}:
            raise ValueError(
                "ORCH_TASK_CONTINUITY_MODE must be off, report_only, or apply"
            )
        self.task_continuity_timeout_ms = env_int(
            "ORCH_TASK_CONTINUITY_TIMEOUT_MS",
            3500,
            minimum=100,
        )
        self.cognitive_runtime_mode = os.getenv(
            "ORCH_COGNITIVE_RUNTIME_MODE", "apply"
        ).strip().lower()
        if self.cognitive_runtime_mode not in {"off", "report_only", "apply"}:
            raise ValueError(
                "ORCH_COGNITIVE_RUNTIME_MODE must be off, report_only, or apply"
            )
        raw_apply_lanes = os.getenv(
            "ORCH_COGNITIVE_APPLY_LANES", "chat"
        )
        self.cognitive_apply_lanes = frozenset(
            item.strip()
            for item in raw_apply_lanes.split(",")
            if item.strip()
        )
        requested_cognitive_fallback_policy = os.getenv(
            "ORCH_COGNITIVE_FALLBACK_POLICY", "fail_closed"
        ).strip().lower()
        if requested_cognitive_fallback_policy not in {"legacy", "fail_closed"}:
            raise ValueError(
                "ORCH_COGNITIVE_FALLBACK_POLICY must be legacy or fail_closed"
            )
        # Once the goal-driven pipeline starts, it owns semantic resolution for
        # the turn. A later legacy planner would be a second authority, so the
        # effective post-acquisition policy is always fail-closed. The legacy
        # value is retained only as a deprecated configuration input.
        self.cognitive_fallback_policy = "fail_closed"
        self.legacy_semantic_fallback_enabled = env_bool(
            "ORCH_LEGACY_SEMANTIC_FALLBACK_ENABLED", False
        )
        if requested_cognitive_fallback_policy == "legacy":
            logger.warning(
                "ORCH_COGNITIVE_FALLBACK_POLICY=legacy is deprecated; "
                "post-acquisition semantic fallback is forced to fail_closed"
            )
        self.cognitive_runtime_timeout_ms = env_int(
            "ORCH_COGNITIVE_RUNTIME_TIMEOUT_MS", 25000, minimum=1000
        )
        self.cognitive_host_replan_budget = env_int(
            "ORCH_COGNITIVE_HOST_REPLAN_BUDGET", 1, minimum=0
        )
        self.cognitive_evidence_enabled = env_bool(
            "ORCH_COGNITIVE_EVIDENCE_ENABLED", True
        )
        self.cognitive_evidence_include_text = env_bool(
            "ORCH_COGNITIVE_EVIDENCE_INCLUDE_TEXT", False
        )
        cognitive_evidence_path = Path(
            os.getenv(
                "ORCH_COGNITIVE_EVIDENCE_PATH",
                ".chromie/evidence/cognitive-runtime/events.jsonl",
            )
        ).expanduser()
        if not cognitive_evidence_path.is_absolute():
            cognitive_evidence_path = PROJECT_ROOT / cognitive_evidence_path
        self.cognitive_evidence_path = cognitive_evidence_path
        self.deepthinking_policy = DeepThinkingDelegationPolicy(
            DeepThinkingPolicyConfig.from_env()
        )
        self.router_url = os.getenv("ROUTER_URL", "http://127.0.0.1:8091")
        self.agent_url = os.getenv("AGENT_URL", "http://127.0.0.1:8092")
        self.action_executor_url = os.getenv("ACTION_EXECUTOR_URL", "http://127.0.0.1:8095")
        self.action_dry_run = env_bool("ORCH_ACTION_DRY_RUN", True)
        self.abilities = build_default_ability_registry(
            enable_agent=self.enable_agent,
            enable_interaction_response=self.enable_interaction_response,
            enable_soridormi_skills=self.enable_soridormi_skills,
            auto_confirm_sim_skills=self.auto_confirm_sim_skills,
            action_dry_run=self.action_dry_run,
        )
        self.router_client = RouterClient(self.router_url, int(os.getenv("ORCH_ROUTER_TIMEOUT_MS", "9000")))
        self.agent_client = AgentClient(self.agent_url, int(os.getenv("ORCH_AGENT_TIMEOUT_MS", "3000")))
        self.action_client = ActionClient(self.action_executor_url, int(os.getenv("ORCH_ACTION_TIMEOUT_MS", "5000")))
        self.asr_timeout_s = max(
            0.001,
            int(os.getenv("ORCH_ASR_TIMEOUT_MS", "30000")) / 1000.0,
        )

        self.min_rms = float(os.getenv("ORCH_MIN_RMS", "120"))
        self.barge_in_min_rms = float(os.getenv("ORCH_BARGE_IN_MIN_RMS", "350"))
        self.min_audio_ms = int(os.getenv("ORCH_MIN_AUDIO_MS", "450"))
        self.max_vad_utterance_ms = env_int(
            "ORCH_VAD_MAX_UTTERANCE_MS",
            20000,
            minimum=1000,
        )
        self.input_gain = max(0.0, float(os.getenv("ORCH_INPUT_GAIN", "1.0")))
        self.tts_flush_chars = int(os.getenv("TTS_FLUSH_CHARS", "160"))
        self.tts_max_text_chars = max(20, int(os.getenv("TTS_MAX_TEXT_CHARS", "220")))
        self.tts_text_chunking_enabled = env_bool("ORCH_TTS_TEXT_CHUNKING", True)
        self.tts_chunk_chars = max(
            20,
            min(
                self.tts_max_text_chars,
                int(os.getenv("ORCH_TTS_CHUNK_CHARS", "120")),
            ),
        )
        self.tts_cjk_chunk_chars = max(
            12,
            min(
                self.tts_max_text_chars,
                int(os.getenv("ORCH_TTS_CJK_CHUNK_CHARS", "36")),
            ),
        )
        self.tts_first_chunk_chars = max(
            0,
            int(os.getenv("ORCH_TTS_FIRST_CHUNK_CHARS", "16")),
        )
        self.tts_min_chunk_chars = max(
            1,
            int(os.getenv("ORCH_TTS_MIN_CHUNK_CHARS", "20")),
        )
        self.tts_cjk_min_chunk_chars = max(
            1,
            int(os.getenv("ORCH_TTS_CJK_MIN_CHUNK_CHARS", "8")),
        )
        self.default_tts_rate = int(os.getenv("TTS_SAMPLE_RATE", "44100"))
        self.speaker_id = os.getenv("TTS_SPEAKER_ID", "default")
        self.save_audio_enabled = env_bool("ORCH_SAVE_AUDIO", False)
        self.enable_session_timing = env_bool("ORCH_SESSION_TIMING_LOGS", True)
        self.voice_system_prompt = os.getenv(
            "ORCH_VOICE_SYSTEM_PROMPT",
            "You are a real-time voice assistant. Answer briefly in 1 to 3 short sentences. "
            "Do not use markdown. Do not use numbered lists unless the user explicitly asks for a list. "
            "Avoid long explanations unless the user asks for details.",
        )
        self.tts_ws_retries = int(os.getenv("ORCH_TTS_WS_RETRIES", "2"))
        self.tts_ws_retry_delay_ms = int(os.getenv("ORCH_TTS_WS_RETRY_DELAY_MS", "300"))
        self.playback_chunk_ms = int(os.getenv("ORCH_PLAYBACK_CHUNK_MS", "80"))

        self.asr_ws = None
        self.http_session: aiohttp.ClientSession | None = None
        self.accelerator_sampler = AcceleratorTelemetrySampler.from_env()
        self.sessions = SessionTracker(enabled=self.enable_session_timing)
        self.sessions.register_resource_snapshot_provider(
            module=ACCELERATOR_SAMPLE_MODULE,
            name="accelerator_resource_sample",
            provider=self.accelerator_sampler.cached_sample,
        )
        self.conversation_state = ConversationStateManager.from_env()
        self.mind = MindManager.from_env(project_root=PROJECT_ROOT)
        self.experience = ExperienceManager.from_env(PROJECT_ROOT)
        self.episode_recorder = EpisodeRecorder.from_env(PROJECT_ROOT)
        self.confirmation_dialogue = ConfirmationDialogue(
            ttl_s=float(os.getenv("ORCH_CONFIRMATION_TTL_SEC", "20")),
        )
        self.body_recovery_max_attempts = env_int(
            "ORCH_BODY_RECOVERY_MAX_ATTEMPTS",
            1,
        )
        self.body_recovery_confirmation_ttl_s = env_float(
            "ORCH_BODY_RECOVERY_CONFIRMATION_TTL_S",
            10.0,
            minimum=1.0,
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
        self.active_llm_task: asyncio.Task | None = None
        self.active_interaction_task: asyncio.Task | None = None
        self.active_interaction_id: str | None = None
        self.active_interaction_tasks: dict[asyncio.Task, str] = {}
        self.active_interaction_reservations: dict[
            asyncio.Task,
            str,
        ] = {}
        self.task_continuity_report_tasks: set[asyncio.Task] = set()
        self.goal_association_report_tasks: set[asyncio.Task] = set()
        self.fast_planner_report_tasks: set[asyncio.Task] = set()
        self.observability_tasks: set[asyncio.Task] = set()
        self.deep_planner_report_tasks: set[asyncio.Task] = set()
        self.cognitive_runtime_report_tasks: set[asyncio.Task] = set()
        self.is_playing_audio = False

        self.audio_input_mode = os.getenv("ORCH_AUDIO_INPUT_MODE", "device").strip().lower()
        self.audio_output_mode = os.getenv("ORCH_AUDIO_OUTPUT_MODE", "device").strip().lower()
        if self.audio_input_mode not in {"device", "stdin"}:
            raise ValueError(
                "ORCH_AUDIO_INPUT_MODE must be 'device' or 'stdin', got "
                f"{self.audio_input_mode!r}"
            )
        if self.audio_output_mode not in {"device", "discard"}:
            raise ValueError(
                "ORCH_AUDIO_OUTPUT_MODE must be 'device' or 'discard', got "
                f"{self.audio_output_mode!r}"
            )
        self.discard_playback_realtime = env_bool(
            "ORCH_DISCARD_PLAYBACK_REALTIME",
            True,
        )

        self.audio_mgr = AudioDeviceManager()
        if self.audio_input_mode == "device":
            self.input_params = self.audio_mgr.get_input_params()
        else:
            injected_rate = int(os.getenv("ORCH_INPUT_RATE", "16000"))
            injected_channels = int(os.getenv("ORCH_INPUT_CHANNELS", "1"))
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
            discard_rate = int(os.getenv("ORCH_OUTPUT_RATE", str(self.default_tts_rate)))
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
            "Input device name=%s index=%s rate=%sHz channels=%s blocksize=%s block_ms=%s latency=%s min_rms=%s barge_in_min_rms=%s input_gain=%.2f",
            self.input_params["name"],
            self.input_device,
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
            "Output device name=%s index=%s rate=%sHz channels=%s blocksize=%s block_ms=%s latency=%s",
            self.output_params["name"],
            self.output_device,
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
            "Control plane: router=%s enabled=%s agent=%s enabled=%s action_url=%s dry_run=%s task_continuity_mode=%s cognitive_runtime_mode=%s cognitive_apply_lanes=%s",
            self.router_url,
            self.enable_router,
            self.agent_url,
            self.enable_agent,
            self.action_executor_url,
            self.action_dry_run,
            self.task_continuity_mode,
            self.cognitive_runtime_mode,
            ",".join(sorted(self.cognitive_apply_lanes)) or "none",
        )

        self.target_asr_rate = 16000
        self.frame_duration_ms = 30
        self.vad = VAD(
            mode=int(os.getenv("ORCH_VAD_MODE", "3")),
            sample_rate=self.target_asr_rate,
            frame_duration_ms=self.frame_duration_ms,
            silence_timeout_ms=int(os.getenv("ORCH_VAD_SILENCE_MS", "650")),
            max_utterance_ms=self.max_vad_utterance_ms,
        )

        self.loop: asyncio.AbstractEventLoop | None = None
        self.mic_queue: asyncio.Queue = asyncio.Queue(maxsize=50)
        self._vad_leftover = b""
        self.playback_queue: asyncio.Queue = asyncio.Queue()
        self.playback_task: asyncio.Task | None = None
        self.active_synthesis_tasks: set[asyncio.Task] = set()
        # ASR and routed-turn lifecycles are intentionally separate. Keeping
        # handle_routed_text inside active_asr_task caused barge-in utterances
        # to be dropped while the Agent or TTS was still working.
        self.active_asr_task: asyncio.Task | None = None
        self.active_turn_task: asyncio.Task | None = None
        self.active_reflex_task: asyncio.Task | None = None
        self.concurrent_protective_reflex_tasks: set[asyncio.Task] = set()
        self._protective_reflex_failure = False
        self._pending_turn_after_reflex: tuple[str, str] | None = None
        self._pending_vad_audio: bytes | None = None
        self.synthesis_semaphore = asyncio.Semaphore(int(os.getenv("ORCH_TTS_CONCURRENCY", "1")))
        self.next_playback_order = 0
        self.pending_audio: dict[int, tuple[int, bytes, int, str | None, str | None]] = {}
        self.synthesis_order = 0
        self.playback_generation = 0
        self.playback_start_waiters: dict[
            tuple[int, int, str | None],
            asyncio.Future[bool],
        ] = {}
        self.cancelled_playback_orders: set[tuple[int, int, str | None]] = set()
        self.order_lock = asyncio.Lock()
        self.output_stream = None
        self.output_stream_lock = asyncio.Lock()
        self.output_write_lock = asyncio.Lock()
        recordings_dir = Path(os.getenv("RECORDINGS_DIR", "recordings")).expanduser()
        if not recordings_dir.is_absolute():
            recordings_dir = PROJECT_ROOT / recordings_dir
        self.recordings_dir = str(recordings_dir.resolve())
        recordings_dir.mkdir(parents=True, exist_ok=True)

        soridormi_invoker = None
        if self.enable_soridormi_skills:
            manifest_path = Path(
                os.getenv(
                    "ORCH_SORIDORMI_MANIFEST",
                    str(PROJECT_ROOT / "capabilities" / "soridormi.json"),
                )
            ).expanduser()
            if not manifest_path.is_absolute():
                manifest_path = PROJECT_ROOT / manifest_path
            soridormi_invoker = build_soridormi_invoker(
                manifest_path=manifest_path,
            )
        self.interaction_runtime = InteractionRuntimeCoordinator(
            self._schedule_interaction_speech,
            speech_cancel_scheduler=self._cancel_interaction_speech,
            soridormi_invoker=soridormi_invoker,
            task_graph_handler=self._execute_planning_task_graph,
            task_graph_cancel_handler=self._cancel_planning_task_graph,
            auto_confirm_sim=self.auto_confirm_sim_skills,
        )
        self.cognitive_runtime_policy = CognitiveRuntimePolicy(
            mode=self.cognitive_runtime_mode,
            apply_lanes=self.cognitive_apply_lanes,
            fallback_policy=self.cognitive_fallback_policy,
            max_total_ms=self.cognitive_runtime_timeout_ms,
            host_replan_budget=self.cognitive_host_replan_budget,
            goal_association_timeout_ms=self.goal_association_timeout_ms,
            fast_planner_timeout_ms=self.fast_planner_timeout_ms,
            deep_planner_timeout_ms=self.deep_planner_timeout_ms,
            response_composer_timeout_ms=self.response_composer_timeout_ms,
        )
        self.cognitive_evidence = CognitiveEvidenceRecorder(
            self.cognitive_evidence_path,
            enabled=self.cognitive_evidence_enabled,
            include_text=self.cognitive_evidence_include_text,
        )
        self.cognitive_turn_closure = CognitiveTurnClosure(
            self.interaction_runtime
        )
        self.cognitive_gateway = GatewayCoreCompatibilityAdapter()
        self.cognitive_runtime = GoalDrivenRuntimeCoordinator(
            agent_client=self.agent_client,
            adapter=CanonicalPlanRuntimeAdapter(
                self.interaction_runtime,
                social_attention_mode=(
                    os.getenv("CHROMIE_SOCIAL_ATTENTION_MODE")
                    or os.getenv("AGENT_SOCIAL_ATTENTION_MODE")
                    or "off"
                ),
            ),
            policy=self.cognitive_runtime_policy,
            # Goal state is committed by the host only after the canonical plan
            # and composed response have also passed trusted-runtime preparation.
            goal_state_apply=None,
        )
        logger.info(
            "Interaction runtime: endpoint=%s soridormi_skills=%s auto_confirm_sim=%s "
            "confirmation_ttl_s=%.1f fast_first_response=%s fast_first_tool=%s "
            "router_generated_fast_speech=%s fast_first_audio=%s hedge_ms=%s "
            "cache_dir=%s prime_on_startup=%s prime_timeout_ms=%s",
            self.enable_interaction_response,
            self.enable_soridormi_skills,
            self.auto_confirm_sim_skills,
            self.confirmation_dialogue.ttl_s,
            self.fast_first_response_enabled,
            self.fast_first_tool_response_enabled,
            self.router_generated_fast_speech_enabled,
            self.fast_first_audio_cache.enabled,
            self.fast_first_audio_hedge_ms,
            self.fast_first_audio_cache.cache_dir,
            self.fast_first_audio_prime_on_startup,
            self.fast_first_audio_prime_timeout_ms,
        )

    @property
    def session_id(self) -> str | None:
        return self.sessions.current_sid

    def session_log(self, sid: Optional[str], message: str, *args: Any) -> None:
        self.sessions.log(sid, message, *args)

    def maybe_session_done(self, sid: Optional[str]) -> None:
        self.sessions.maybe_done(sid)

    def playback_start_key(
        self,
        generation: int,
        order: int,
        session_id: Optional[str],
    ) -> tuple[int, int, str | None]:
        return (generation, order, session_id)

    def resolve_playback_start_waiter(
        self,
        generation: int,
        order: int,
        session_id: Optional[str],
        *,
        started: bool,
        reason: str,
    ) -> None:
        key = self.playback_start_key(generation, order, session_id)
        waiter = self.playback_start_waiters.pop(key, None)
        if waiter is None or waiter.done():
            return
        waiter.set_result(started)
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
        waiters = list(self.playback_start_waiters.items())
        self.playback_start_waiters.clear()
        for (_, order, session_id), waiter in waiters:
            if not waiter.done():
                waiter.set_result(started)
                self.session_log(
                    session_id,
                    "tts_playback_start_waiter_resolved: order=%s started=%s reason=%s",
                    order,
                    started,
                    reason,
                )

    async def wait_for_playback_start(
        self,
        *,
        generation: int,
        order: int,
        session_id: Optional[str],
        timeout_s: float,
    ) -> bool:
        key = self.playback_start_key(generation, order, session_id)
        waiter = self.playback_start_waiters.get(key)
        if waiter is None:
            return False
        try:
            # Keep the waiter live on timeout so the caller can invalidate the
            # scheduled order.  ``wait_for`` otherwise cancels the Future and
            # a late synthesis result can slip through to audible playback
            # after the physical-effect barrier has already failed.
            return await asyncio.wait_for(asyncio.shield(waiter), timeout=timeout_s)
        except TimeoutError:
            self.session_log(
                session_id,
                "tts_playback_start_waiter_timeout: order=%s timeout_s=%.3f",
                order,
                timeout_s,
            )
            return False

    def _cancel_playback_order_before_start(
        self,
        *,
        generation: int,
        order: int,
        session_id: str | None,
        reason: str,
    ) -> bool:
        key = self.playback_start_key(generation, order, session_id)
        if not hasattr(self, "cancelled_playback_orders"):
            self.cancelled_playback_orders = set()
        waiter = self.playback_start_waiters.get(key)
        if waiter is None or waiter.done():
            return False
        self.cancelled_playback_orders.add(key)
        self.resolve_playback_start_waiter(
            generation,
            order,
            session_id,
            started=False,
            reason=reason,
        )
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

    async def schedule_cached_fast_first_audio(
        self,
        audio: CachedFastFirstAudio,
        session_id: str | None,
    ) -> dict[str, Any]:
        if not audio.pcm16 or audio.sample_rate <= 0:
            return {"scheduled": False, "reason": "invalid_cached_audio"}
        async with self.order_lock:
            order = self.synthesis_order
            self.synthesis_order += 1
            generation = self.playback_generation
        if self.is_stale_playback(generation, session_id):
            return {"scheduled": False, "reason": "stale_playback"}
        key = self.playback_start_key(generation, order, session_id)
        self.playback_start_waiters[key] = asyncio.get_running_loop().create_future()
        state = self.sessions.state.get(session_id or "")
        if state is not None:
            state["scheduled_tts"] = int(state.get("scheduled_tts", 0)) + 1
            state["queued_tts"] = int(state.get("queued_tts", 0)) + 1
        self.session_log(
            session_id,
            "fast_first_audio_schedule: order=%s purpose=%s language=%s chars=%s "
            "bytes=%s sample_rate=%s hedge_ms=%s generation=%s",
            order,
            audio.purpose,
            audio.language,
            len(audio.text),
            len(audio.pcm16),
            audio.sample_rate,
            self.fast_first_audio_hedge_ms,
            generation,
        )
        self.ensure_playback_worker()
        await self.playback_queue.put(
            (generation, order, audio.pcm16, audio.sample_rate, session_id, None)
        )
        return {
            "scheduled": True,
            "order": order,
            "generation": generation,
            "purpose": audio.purpose,
            "language": audio.language,
            "text": audio.text,
            "cached": True,
        }

    def _start_fast_first_audio_hedge(
        self,
        decision: RouteDecision,
        user_text: str,
        session_id: str,
    ) -> asyncio.Task[dict[str, Any]] | None:
        cache = getattr(self, "fast_first_audio_cache", None)
        if (
            not self.fast_first_response_enabled
            or cache is None
            or not cache.enabled
            or not decision.should_speak
            or decision.route in {"chat", "clarify", "interrupt", "ignore"}
            or bool((decision.metadata or {}).get("fast_first_response_scheduled"))
        ):
            return None
        audio = cache.get(
            route=decision.route,
            language=decision.language,
            user_text=user_text,
        )
        if audio is None:
            self.session_log(
                session_id,
                "fast_first_audio_skipped: route=%s intent=%s reason=cache_miss ready=%s",
                decision.route,
                decision.intent,
                cache.ready_count,
            )
            return None

        metadata = dict(decision.metadata or {})
        metadata["fast_first_audio_hedge"] = {
            "pending": True,
            "purpose": audio.purpose,
            "language": audio.language,
            "hedge_ms": self.fast_first_audio_hedge_ms,
        }
        decision.metadata = metadata
        # The cached cue owns the immediate acknowledgement for this turn. Keep
        # the Router's dynamic wording as audit metadata, but do not let the
        # downstream Agent repeat it after the hedge fires.
        if decision.speak_first:
            metadata["router_speak_first_suppressed_by_audio_hedge"] = decision.speak_first
            decision.speak_first = None

        async def delayed_schedule() -> dict[str, Any]:
            try:
                await asyncio.sleep(max(0, self.fast_first_audio_hedge_ms) / 1000.0)
                if self.is_stale_playback(self.playback_generation, session_id):
                    return {"scheduled": False, "reason": "stale_session"}
                return await self.schedule_cached_fast_first_audio(audio, session_id)
            except asyncio.CancelledError:
                return {"scheduled": False, "reason": "final_ready_before_hedge"}

        self.session_log(
            session_id,
            "fast_first_audio_hedge_started: route=%s intent=%s purpose=%s "
            "language=%s hedge_ms=%s",
            decision.route,
            decision.intent,
            audio.purpose,
            audio.language,
            self.fast_first_audio_hedge_ms,
        )
        return asyncio.create_task(delayed_schedule())

    async def _settle_fast_first_audio_hedge(
        self,
        hedge_task: asyncio.Task[dict[str, Any]] | None,
        *,
        decision: RouteDecision,
        session_id: str,
    ) -> bool:
        if hedge_task is None:
            return False
        if not hedge_task.done():
            hedge_task.cancel()
        try:
            result = await hedge_task
        except asyncio.CancelledError:
            result = {"scheduled": False, "reason": "final_ready_before_hedge"}
        except Exception as exc:
            self.session_log(
                session_id,
                "fast_first_audio_hedge_failed: error_type=%s error=%s",
                type(exc).__name__,
                exc,
            )
            return False

        if result.get("scheduled") is not True:
            self.session_log(
                session_id,
                "fast_first_audio_suppressed: route=%s intent=%s reason=%s",
                decision.route,
                decision.intent,
                result.get("reason", "not_scheduled"),
            )
            return False

        generation = int(result["generation"])
        order = int(result["order"])
        if self._cancel_playback_order_before_start(
            generation=generation,
            order=order,
            session_id=session_id,
            reason="final_ready_before_cached_playback",
        ):
            self.session_log(
                session_id,
                "fast_first_audio_suppressed: route=%s intent=%s reason=final_ready_before_playback",
                decision.route,
                decision.intent,
            )
            return False

        metadata = dict(decision.metadata or {})
        hedge = dict(metadata.get("fast_first_audio_hedge") or {})
        hedge.update(
            {
                "pending": False,
                "played_or_started": True,
                "order": order,
                "generation": generation,
                "text": result.get("text"),
            }
        )
        metadata["fast_first_audio_hedge"] = hedge
        metadata["fast_first_response_scheduled"] = True
        decision.metadata = metadata
        return True

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

    def mono_to_output_channels(self, samples: np.ndarray) -> np.ndarray:
        if self.output_channels == 1:
            return samples
        if self.output_channels == 2:
            return np.column_stack([samples, samples])
        return np.tile(samples.reshape(-1, 1), (1, self.output_channels))

    async def ensure_output_stream(self):
        if self.output_stream is not None:
            return
        async with self.output_stream_lock:
            if self.output_stream is not None:
                return
            sd = _sounddevice()
            self.output_stream = sd.OutputStream(
                samplerate=self.output_rate,
                channels=self.output_channels,
                dtype="int16",
                device=self.output_device,
                latency=self.output_latency,
                blocksize=self.output_params.get("blocksize", 0),
            )
            self.output_stream.start()
            logger.info(
                "Output stream opened: device=%s rate=%s channels=%s latency=%s",
                self.output_device,
                self.output_rate,
                self.output_channels,
                self.output_latency,
            )

    async def abort_output_stream(self):
        async with self.output_write_lock:
            async with self.output_stream_lock:
                if self.output_stream is None:
                    return
                stream = self.output_stream

                def abort_and_close() -> None:
                    try:
                        stream.abort()
                    except Exception as exc:
                        logger.warning(
                            "Failed to abort output stream: %s",
                            exc,
                        )
                    try:
                        stream.close()
                    except Exception as exc:
                        logger.warning(
                            "Failed to close output stream after abort: %s",
                            exc,
                        )

                try:
                    await asyncio.to_thread(abort_and_close)
                finally:
                    if self.output_stream is stream:
                        self.output_stream = None

    async def close_output_stream(self):
        async with self.output_write_lock:
            async with self.output_stream_lock:
                if self.output_stream is None:
                    return
                try:
                    self.output_stream.stop()
                except Exception:
                    pass
                try:
                    self.output_stream.close()
                except Exception:
                    pass
                self.output_stream = None

    def is_stale_playback(self, generation: int, session_id: Optional[str]) -> bool:
        return generation != self.playback_generation or session_id != self.session_id

    async def play_audio(self, audio_bytes: bytes, source_rate: Optional[int], generation: int, session_id: Optional[str]):
        pcm = self.resample_int16_bytes(audio_bytes, source_rate or self.default_tts_rate, self.output_rate)
        samples = np.frombuffer(pcm, dtype=np.int16)
        if samples.size == 0:
            return
        if self.audio_output_mode == "discard":
            frames_per_chunk = max(
                1,
                int(self.output_rate * self.playback_chunk_ms / 1000),
            )
            for offset in range(0, samples.size, frames_per_chunk):
                if self.is_stale_playback(generation, session_id):
                    raise asyncio.CancelledError(
                        "Discarded playback interrupted by newer session"
                    )
                if self.discard_playback_realtime:
                    chunk_frames = min(frames_per_chunk, samples.size - offset)
                    await asyncio.sleep(chunk_frames / self.output_rate)
                else:
                    await asyncio.sleep(0)
            return
        output = self.mono_to_output_channels(samples)
        await self.ensure_output_stream()
        stream = self.output_stream
        if stream is None:
            raise RuntimeError("Output stream is not available")
        frames_per_chunk = max(1, int(self.output_rate * self.playback_chunk_ms / 1000))
        for offset in range(0, len(output), frames_per_chunk):
            if self.is_stale_playback(generation, session_id):
                await self.abort_output_stream()
                raise asyncio.CancelledError("Playback interrupted by newer session")
            chunk = output[offset : offset + frames_per_chunk]
            async with self.output_write_lock:
                if self.output_stream is not stream:
                    raise asyncio.CancelledError("Output stream changed during playback")
                if self.is_stale_playback(generation, session_id):
                    raise asyncio.CancelledError("Playback interrupted by newer session")
                await asyncio.to_thread(stream.write, chunk)

    async def enqueue_playback_skip(self, generation: int, order: int, session_id: Optional[str], reason: str):
        if self.is_stale_playback(generation, session_id):
            self.session_log(
                session_id,
                "playback_skip_drop_stale: order=%s reason=%s generation=%s current_generation=%s current_sid=%s",
                order,
                reason,
                generation,
                self.playback_generation,
                self.session_id,
            )
            return
        await self.playback_queue.put((generation, order, b"", self.default_tts_rate, session_id, reason))

    async def playback_worker(self):
        while True:
            item = await self.playback_queue.get()
            if not item:
                continue
            generation = item[0]
            if generation is None:
                break
            generation, order, audio, source_rate, session_id, skip_reason = item
            if self.is_stale_playback(generation, session_id):
                self.resolve_playback_start_waiter(
                    generation,
                    order,
                    session_id,
                    started=False,
                    reason="stale_before_order",
                )
                self.session_log(session_id, "playback_drop_stale_before_order: order=%s", order)
                continue
            if order != self.next_playback_order:
                self.pending_audio[order] = (generation, audio, source_rate, session_id, skip_reason)
                continue
            played = await self.play_one_order(generation, order, audio, source_rate, session_id, skip_reason)
            if played:
                self.next_playback_order += 1
            while self.next_playback_order in self.pending_audio:
                ng, na, nsr, nsid, nreason = self.pending_audio.pop(self.next_playback_order)
                if self.is_stale_playback(ng, nsid):
                    self.resolve_playback_start_waiter(
                        ng,
                        self.next_playback_order,
                        nsid,
                        started=False,
                        reason="stale_pending_order",
                    )
                    self.next_playback_order += 1
                    continue
                played = await self.play_one_order(ng, self.next_playback_order, na, nsr, nsid, nreason)
                if played:
                    self.next_playback_order += 1
                else:
                    break

    @trace_session_async(PLAYBACK_TRACE_MODULE, "play_one_order", "session_id")
    async def play_one_order(self, generation: int, order: int, audio: bytes, source_rate: int, session_id: Optional[str], skip_reason: Optional[str] = None) -> bool:
        key = self.playback_start_key(generation, order, session_id)
        cancelled_orders = getattr(self, "cancelled_playback_orders", set())
        if key in cancelled_orders:
            cancelled_orders.discard(key)
            self.session_log(
                session_id,
                "playback_skip_cancelled: order=%s generation=%s",
                order,
                generation,
            )
            self.maybe_session_done(session_id)
            return True
        if self.is_stale_playback(generation, session_id):
            self.resolve_playback_start_waiter(
                generation,
                order,
                session_id,
                started=False,
                reason="stale_playback",
            )
            return False
        state = self.sessions.state.get(session_id or "")
        if not audio:
            reason = skip_reason or "empty_audio"
            self.resolve_playback_start_waiter(
                generation,
                order,
                session_id,
                started=False,
                reason=reason,
            )
            if state is not None:
                if reason in {"tts_error", "tts_exception", "playback_exception"}:
                    state["failed_tts"] = int(state.get("failed_tts", 0)) + 1
                else:
                    state["skipped_tts"] = int(state.get("skipped_tts", 0)) + 1
            self.session_log(session_id, "playback_skip_empty: order=%s reason=%s", order, reason)
            self.maybe_session_done(session_id)
            return True

        audio_ms = (len(audio) / (source_rate * 2)) * 1000.0 if source_rate else 0.0
        self.sessions.trace_mark(
            session_id,
            "first_audio_playback" if not state or not state.get("trace_first_audio_marked") else "audio_playback_started",
            kind="user_observable",
            attributes={"order": order, "audio_ms": round(audio_ms, 3)},
        )
        if state is not None:
            state["trace_first_audio_marked"] = True
        self.session_log(
            session_id,
            "playback_start: order=%s source_rate=%s output_rate=%s audio_ms=%.1f generation=%s",
            order,
            source_rate,
            self.output_rate,
            audio_ms,
            generation,
        )
        self.resolve_playback_start_waiter(
            generation,
            order,
            session_id,
            started=True,
            reason="playback_start",
        )
        playback_start_ms = now_ms()
        try:
            self.is_playing_audio = True
            try:
                await self.play_audio(audio, source_rate, generation, session_id)
            finally:
                self.is_playing_audio = False
        except asyncio.CancelledError:
            self.session_log(session_id, "playback_aborted_by_interrupt: order=%s playback_ms=%.1f generation=%s", order, now_ms() - playback_start_ms, generation)
            return False
        except Exception as exc:
            await self.abort_output_stream()
            if state is not None:
                state["failed_tts"] = int(state.get("failed_tts", 0)) + 1
            self.session_log(session_id, "playback_exception: order=%s playback_ms=%.1f error=%s", order, now_ms() - playback_start_ms, exc)
            logger.error("Playback exception: %s", exc, exc_info=True)
            self.maybe_session_done(session_id)
            return True

        playback_ms = now_ms() - playback_start_ms
        if self.is_stale_playback(generation, session_id):
            self.session_log(session_id, "playback_aborted_by_interrupt: order=%s playback_ms=%.1f generation=%s", order, playback_ms, generation)
            return False
        if state is not None:
            state["played_tts"] = int(state.get("played_tts", 0)) + 1
        self.session_log(session_id, "playback_end: order=%s playback_ms=%.1f played_tts=%s", order, playback_ms, state.get("played_tts", 0) if state else "unknown")
        self.save_audio(audio, "output", session_id=session_id)
        self.maybe_session_done(session_id)
        return True

    @trace_session_async(TTS_TRACE_MODULE, "synthesize_one", "session_id")
    async def synthesize_one(self, text: str, order: int, session_id: Optional[str], generation: int):
        text = self.normalize_tts_candidate(text)
        if not self.is_valid_tts_text(text):
            self.session_log(session_id, "tts_skip_invalid_sentence: order=%s chars=%s text=%r", order, len(text), text)
            await self.enqueue_playback_skip(generation, order, session_id, "invalid_tts_text")
            return
        if self.is_stale_playback(generation, session_id):
            return
        async with self.synthesis_semaphore:
            request_id = f"{session_id}-{order}"
            tts_start_ms = now_ms()
            max_attempts = max(1, self.tts_ws_retries)
            retry_delay = max(0, self.tts_ws_retry_delay_ms) / 1000.0
            last_error: Exception | None = None
            self.session_log(session_id, "tts_request_start: order=%s chars=%s generation=%s retries=%s text=%r", order, len(text), generation, max_attempts, text)
            for attempt in range(1, max_attempts + 1):
                if self.is_stale_playback(generation, session_id):
                    return
                try:
                    async with websockets.connect(self.tts_url, max_size=10**7, open_timeout=10, ping_interval=20, ping_timeout=20) as ws:
                        await ws.send(json.dumps({"type": "synthesize_stream", "text": text, "speaker_id": self.speaker_id, "request_id": request_id}, ensure_ascii=False))
                        audio_buffer = bytearray()
                        source_rate = self.default_tts_rate
                        async for msg in ws:
                            if self.is_stale_playback(generation, session_id):
                                return
                            if isinstance(msg, bytes):
                                audio_buffer.extend(msg)
                                continue
                            data = json.loads(msg)
                            msg_type = data.get("type")
                            if msg_type == "start":
                                source_rate = int(data.get("sample_rate") or self.default_tts_rate)
                                self.sessions.trace_mark(
                                    session_id,
                                    "tts_stream_started",
                                    attributes={"order": order, "attempt": attempt, "source_rate": source_rate},
                                )
                                self.session_log(session_id, "tts_stream_start: order=%s attempt=%s/%s source_rate=%s output_rate=%s generation=%s", order, attempt, max_attempts, source_rate, self.output_rate, generation)
                                continue
                            if msg_type == "error":
                                self.session_log(session_id, "tts_error: order=%s attempt=%s/%s tts_ms=%.1f error=%s", order, attempt, max_attempts, now_ms() - tts_start_ms, data.get("message"))
                                await self.enqueue_playback_skip(generation, order, session_id, "tts_error")
                                self.maybe_session_done(session_id)
                                return
                            if msg_type == "end":
                                provider_metadata = data.get("provider")
                                if not isinstance(provider_metadata, dict):
                                    provider_metadata = {}
                                model_artifacts = provider_metadata.get("model_artifacts")
                                if not isinstance(model_artifacts, list):
                                    model_artifacts = []
                                provider_revision_summary = ",".join(
                                    f"{artifact.get('kind')}={artifact.get('revision')}"
                                    for artifact in model_artifacts
                                    if isinstance(artifact, dict)
                                    and artifact.get("kind")
                                    and artifact.get("revision")
                                )
                                self.sessions.trace_mark(
                                    session_id,
                                    "tts_stream_finished",
                                    attributes={
                                        "order": order,
                                        "attempt": attempt,
                                        "audio_bytes": len(audio_buffer),
                                        "source_rate": source_rate,
                                        "queue_wait_seconds": float(data.get("queue_wait_seconds") or 0.0),
                                        "generate_seconds": float(data.get("generate_seconds") or 0.0),
                                        "provider_id": provider_metadata.get("provider_id"),
                                        "provider_implementation": provider_metadata.get("implementation"),
                                        "provider_model_revisions": provider_revision_summary,
                                    },
                                )
                                self.session_log(session_id, "tts_stream_end: order=%s attempt=%s/%s tts_ms=%.1f bytes=%s source_rate=%s generation=%s", order, attempt, max_attempts, now_ms() - tts_start_ms, len(audio_buffer), source_rate, generation)
                                self.session_log(
                                    session_id,
                                    "tts_server_metrics: order=%s provider=%s implementation=%s model_revisions=%s audio_s=%.3f generate_s=%.3f model_s=%.3f codec_s=%.3f pcm_s=%.3f queue_s=%.3f rtf=%s codec_device=%s quantization=%s context=%s prompt_tokens=%s generated_tokens=%s headroom=%s limit_reached=%s",
                                    order,
                                    provider_metadata.get("provider_id"),
                                    provider_metadata.get("implementation"),
                                    provider_revision_summary,
                                    float(data.get("audio_seconds") or 0.0),
                                    float(data.get("generate_seconds") or 0.0),
                                    float(data.get("model_generate_seconds") or 0.0),
                                    float(data.get("codec_decode_seconds") or 0.0),
                                    float(data.get("pcm_conversion_seconds") or 0.0),
                                    float(data.get("queue_wait_seconds") or 0.0),
                                    data.get("realtime_factor"),
                                    data.get("audio_codec_device"),
                                    data.get("quantization"),
                                    data.get("context_size"),
                                    data.get("model_prompt_tokens"),
                                    data.get("model_generated_tokens"),
                                    data.get("generation_headroom_tokens"),
                                    data.get("generation_limit_reached"),
                                )
                                state = self.sessions.state.get(session_id or "")
                                if audio_buffer:
                                    if state is not None:
                                        state["queued_tts"] = int(state.get("queued_tts", 0)) + 1
                                    await self.playback_queue.put((generation, order, bytes(audio_buffer), source_rate, session_id, None))
                                else:
                                    await self.enqueue_playback_skip(generation, order, session_id, "tts_empty_audio")
                                self.maybe_session_done(session_id)
                                return
                        raise RuntimeError("TTS websocket closed before end message")
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    last_error = exc
                    self.session_log(session_id, "tts_ws_attempt_failed: order=%s attempt=%s/%s tts_ms=%.1f error=%s", order, attempt, max_attempts, now_ms() - tts_start_ms, exc)
                    if attempt < max_attempts:
                        await asyncio.sleep(retry_delay)
            logger.error("TTS error after retries: %s", last_error, exc_info=True)
            await self.enqueue_playback_skip(generation, order, session_id, "tts_exception")
            self.maybe_session_done(session_id)

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
            order = self.synthesis_order
            self.synthesis_order += 1
            generation = self.playback_generation
        if self.is_stale_playback(generation, session_id):
            return {"scheduled": False, "reason": "stale_playback"}
        key = self.playback_start_key(generation, order, session_id)
        self.playback_start_waiters[key] = asyncio.get_running_loop().create_future()
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
        request: SkillRequest,
        scheduled: dict[str, Any],
    ) -> None:
        """Cancel one goal-bound speech request at the shared output boundary.

        Pending chunks are invalidated by exact generation/order.  Once any
        chunk may have started, Chromie's playback resource is global, so the
        only truthful cancellation is a shared output abort.  Skill Runtime
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
        scheduled = await self.schedule_tts_text(str(args.get("text") or ""), session_id)
        if (
            isinstance(metadata, dict)
            and metadata.get("wait_for_playback_start") is True
            and scheduled.get("scheduled") is True
        ):
            raw_timeout_ms = metadata.get(
                "playback_start_timeout_ms",
                os.getenv("ORCH_TTS_PLAYBACK_START_TIMEOUT_MS", "20000"),
            )
            try:
                timeout_ms = int(raw_timeout_ms)
            except (TypeError, ValueError):
                timeout_ms = 20000
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

    async def process_llm_tts(
        self,
        user_text: str,
        session_id: Optional[str],
        *,
        reset_playback: bool = True,
        fallback_reason: str | None = None,
        route: str | None = None,
    ):
        prompt = self._build_direct_llm_prompt(
            user_text,
            session_id,
            fallback_reason=fallback_reason,
            route=route,
        )
        payload = {
            "model": self.ollama_model,
            "prompt": prompt,
            "stream": True,
            "think": False,
            "keep_alive": os.getenv("OLLAMA_KEEP_ALIVE", "24h"),
            "options": {
                "num_ctx": int(os.getenv("OLLAMA_NUM_CTX", "2048")),
                "num_predict": int(os.getenv("OLLAMA_NUM_PREDICT", "96")),
                "temperature": float(os.getenv("OLLAMA_TEMPERATURE", "0.4")),
                "top_p": float(os.getenv("OLLAMA_TOP_P", "0.9")),
            },
        }
        logger.info("[%s] LLM processing: %s", session_id, user_text)
        if reset_playback:
            await self.reset_playback_ordering()
        sentence = ""
        llm_start_ms = now_ms()
        self.session_log(session_id, "llm_request_start: prompt_chars=%s input_chars=%s text=%r fallback_reason=%s route=%s think=%s num_ctx=%s num_predict=%s", len(prompt), len(user_text), user_text, fallback_reason or "", route or "", payload.get("think"), payload["options"]["num_ctx"], payload["options"]["num_predict"])
        for diagnostic in ollama_prompt_preflight_diagnostics(
            prompt_chars=len(prompt),
            options=payload.get("options"),
        ):
            self.session_log(session_id, "%s", diagnostic.render())
        try:
            session = await self.get_http_session()
            async with session.post(self.llm_url, json=payload) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    state = self.sessions.state.get(session_id or "")
                    if state is not None:
                        state["llm_done"] = True
                    self.session_log(session_id, "llm_http_error: status=%s body=%s", resp.status, body)
                    self.maybe_session_done(session_id)
                    return
                async for line in resp.content:
                    if session_id != self.session_id:
                        self.session_log(session_id, "llm_drop_stale_stream: current_sid=%s", self.session_id)
                        return
                    if not line:
                        continue
                    try:
                        data = json.loads(line.decode())
                    except json.JSONDecodeError:
                        continue
                    token = data.get("response", "")
                    if token:
                        state = self.sessions.state.get(session_id or "")
                        if state is not None:
                            if not state.get("first_token_logged"):
                                state["first_token_logged"] = True
                                self.session_log(session_id, "llm_first_token: first_token_ms=%.1f", now_ms() - llm_start_ms)
                            state["response_chars"] = int(state.get("response_chars", 0)) + len(token)
                        sentence += token
                        while True:
                            chunk, sentence = self.pop_tts_chunk(sentence)
                            if not chunk:
                                break
                            if self.is_valid_tts_text(chunk):
                                self.session_log(session_id, "llm_flush_to_tts: chars=%s text=%r", len(chunk), chunk)
                                await self.schedule_tts_sentence(chunk, session_id)
                    if data.get("done"):
                        final_text = self.normalize_tts_candidate(sentence)
                        if self.is_valid_tts_text(final_text):
                            self.session_log(session_id, "llm_final_flush_to_tts: chars=%s text=%r", len(final_text), final_text)
                            await self.schedule_tts_sentence(final_text, session_id)
                        state = self.sessions.state.get(session_id or "")
                        if state is not None:
                            state["llm_done"] = True
                        self.session_log(session_id, "llm_done: llm_ms=%.1f response_chars=%s scheduled_tts=%s", now_ms() - llm_start_ms, state.get("response_chars", 0) if state else "unknown", state.get("scheduled_tts", 0) if state else "unknown")
                        self.session_log(session_id, "llm_done_raw: done_reason=%s total_duration=%s load_duration=%s prompt_eval_count=%s prompt_eval_duration=%s eval_count=%s eval_duration=%s", data.get("done_reason"), data.get("total_duration"), data.get("load_duration"), data.get("prompt_eval_count"), data.get("prompt_eval_duration"), data.get("eval_count"), data.get("eval_duration"))
                        for diagnostic in ollama_completion_diagnostics(
                            options=payload.get("options"),
                            data=data,
                            prompt_chars=len(prompt),
                        ):
                            self.session_log(session_id, "%s", diagnostic.render())
                        self.maybe_session_done(session_id)
                        return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            state = self.sessions.state.get(session_id or "")
            if state is not None:
                state["llm_done"] = True
            logger.error("LLM processing failed: %s", exc, exc_info=True)
            self.session_log(session_id, "llm_exception: error=%s", exc)
            self.maybe_session_done(session_id)

    def _build_direct_llm_prompt(
        self,
        user_text: str,
        session_id: str | None,
        *,
        fallback_reason: str | None = None,
        route: str | None = None,
    ) -> str:
        mind_summary = self._direct_llm_mind_summary()
        self_model_json = self._direct_llm_self_model_json()
        context_json = self._direct_llm_context_json(session_id)
        fallback_line = (
            f"Direct fallback reason: {fallback_reason}."
            if fallback_reason
            else "Direct voice mode."
        )
        route_line = f"Route hint: {route}." if route else "Route hint: unknown."
        return (
            f"{self.voice_system_prompt}\n\n"
            "Use the supplied owner-approved self model as the ontology for the speaking entity.\n"
            f"Self model JSON: {self_model_json}\n"
            "Owner-approved mind summary:\n"
            f"{mind_summary}\n\n"
            "Response contract:\n"
            "- Generate first-person speech for self_model.speaker_entity.\n"
            "- Follow self_model.social_presentation: speak naturally as Chromie and foreground name, personality, relationship, and current context rather than volunteering system category, embodiment category, age label, or internal architecture.\n"
            "- Treat internal_components as resources used by that entity, not as alternate speakers or body owners.\n"
            "- Ground capability statements in the bounded runtime context and do not invent tool results or completed actions.\n"
            "- Reply with only the final spoken response; do not expose reasoning, analysis, JSON, markdown, or internal tool names.\n"
            "- Normally do not repeat, quote, or paraphrase the user's current words unless confirmation, clarification, or read-back is required.\n"
            "- This direct fallback can speak only. If the user asked for body movement or another action, be honest that no valid motion result was produced; ask for a clearer command only when the request is actually ambiguous.\n\n"
            f"{fallback_line}\n"
            f"{route_line}\n"
            f"Bounded runtime context JSON: {context_json}\n\n"
            f"User: {user_text}\n"
            "Chromie:"
        )


    def _direct_llm_self_model_json(self) -> str:
        try:
            context = self.mind.context()
            self_model = context.get("self_model", {}) if isinstance(context, dict) else {}
        except Exception as exc:
            logger.warning("direct_llm_self_model_failed: %s", exc)
            self_model = {}
        if not isinstance(self_model, dict):
            self_model = {}
        return json.dumps(self_model, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    def _direct_llm_mind_summary(self) -> str:
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

    def _direct_llm_context_json(self, session_id: str | None) -> str:
        try:
            conversation = self.conversation_state.snapshot()
        except Exception as exc:
            logger.warning("direct_llm_context_snapshot_failed: %s", exc)
            conversation = {}
        history = conversation.get("history")
        if not isinstance(history, list):
            history = []
        session_memory = conversation.get("session_memory")
        if not isinstance(session_memory, dict):
            session_memory = {}
        payload = {
            "session_id": session_id,
            "conversation_id": conversation.get("conversation_id"),
            "memory_summary": session_memory.get("memory_summary"),
            "extracted_memory": session_memory.get("extracted_memory") or [],
            "recent_turn_fallback": history[-2:],
            "active_pending_tasks": conversation.get("active_pending_tasks") or [],
            "active_task_snapshots": conversation.get("active_task_snapshots") or [],
            "current_task_context": conversation.get("current_task_context"),
        }
        return self._compact_json_for_prompt(payload, max_chars=1600)

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

    def build_context(self, session_id: str | None) -> dict[str, Any]:
        conversation = self.conversation_state.snapshot()
        mind_context = self.mind.context()
        return {
            "is_speaking": self.is_playing_audio,
            "current_generation": self.playback_generation,
            "session_id": session_id,
            "conversation_id": conversation.get("conversation_id"),
            "interaction_engagement": self._interaction_engagement_context(
                conversation
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
            "current_task_context": conversation.get("current_task_context"),
            "robot_state": {
                "available": not self.action_dry_run,
                "source": "host_orchestrator",
            },
        }

    def _interaction_engagement_context(
        self,
        conversation: dict[str, Any],
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
        last_exchange_ms = 0.0
        for turn in history:
            if not isinstance(turn, dict):
                continue
            # Ambient speech is recorded for traceability, but accepting it as
            # a conversation turn would make the next ambient fragment look
            # actively addressed for the whole engagement window.
            if str(turn.get("route") or "").strip().casefold() == "ignore":
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
        active = bool(has_active_work or recent_exchange)
        evidence = (
            "active_task"
            if has_active_work
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

    def _experience_context(
        self,
        *,
        user_text: str,
        decision: RouteDecision,
        router_latency_ms: float | None = None,
        agent_latency_ms: float | None = None,
    ) -> dict[str, Any]:
        return {
            "user_text": " ".join((user_text or "").strip().split())[:500],
            "route": decision.route,
            "intent": decision.intent,
            "route_source": decision.source,
            "route_confidence": decision.confidence,
            "router_latency_ms": router_latency_ms,
            "agent_latency_ms": agent_latency_ms,
            "conversation_id": self.conversation_state.conversation_id,
            "mind_profile_id": self.mind.profile.profile_id,
            "mind_profile_version": self.mind.profile.version,
        }

    def _record_experience(
        self,
        *,
        response: InteractionResponse,
        execution: SkillRuntimeResult | None,
        session_id: str | None,
        errors: list[str] | None = None,
    ) -> None:
        conversation_state = getattr(self, "conversation_state", None)
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
                "experience_recorded: experience_id=%s route=%s execution_status=%s",
                record.experience_id,
                record.route,
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
        execution: SkillRuntimeResult | None,
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
            if errors is not None:
                record_kwargs["errors"] = errors
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

    def _ability_registry(self) -> AbilityRegistry:
        abilities = getattr(self, "abilities", None)
        if isinstance(abilities, AbilityRegistry):
            return abilities
        return build_default_ability_registry(
            enable_agent=bool(getattr(self, "enable_agent", True)),
            enable_interaction_response=bool(
                getattr(self, "enable_interaction_response", False)
            ),
            enable_soridormi_skills=bool(
                getattr(self, "enable_soridormi_skills", False)
            ),
            auto_confirm_sim_skills=bool(
                getattr(self, "auto_confirm_sim_skills", True)
            ),
            action_dry_run=bool(getattr(self, "action_dry_run", True)),
        )

    def _ability_unavailable_response(
        self,
        ability_id: str,
        *,
        language: str | None,
        user_text: str = "",
    ) -> InteractionResponse:
        abilities = self._ability_registry()
        ability = abilities.get(ability_id)
        return InteractionResponse(
            speech=[
                {
                    "text": abilities.unavailable_message(
                        ability_id,
                        language=language,
                        user_text=user_text,
                    ),
                    "style": "brief",
                    "timing": "immediate",
                    "priority": "normal",
                    "interruptible": True,
                    "metadata": {
                        "source": "host_ability_registry",
                        "ability_id": ability.ability_id,
                        "ability_status": ability.status,
                    },
                }
            ],
            metadata={
                "source": "host_ability_registry",
                "ability_id": ability.ability_id,
                "ability_status": ability.status,
            },
        )

    def _deep_thought_prelude_allowed(self, decision: RouteDecision) -> bool:
        if decision.route != "deep_thought" or not decision.should_speak:
            return False
        metadata = decision.metadata if isinstance(decision.metadata, dict) else {}
        original = metadata.get("orchestrator_original_route")
        original_intent = ""
        if isinstance(original, dict):
            original_intent = str(original.get("intent") or "").strip().casefold()
        if str(decision.intent or "").startswith("clarify_") or original_intent.startswith("clarify_"):
            return False
        if decision.intent == "deep_thought_low_confidence" and not decision.speak_first:
            return False
        if metadata.get("thinking_ack_allowed") is False:
            return False
        return True

    def _deep_thought_ack_text(
        self,
        decision: RouteDecision,
        user_text: str,
    ) -> str | None:
        if not self._deep_thought_prelude_allowed(decision):
            return None
        if decision.fast_speech is not None and getattr(
            self,
            "router_generated_fast_speech_enabled",
            False,
        ):
            model_text = self._validated_fast_speech_payload_text(
                decision.fast_speech
            )
            if model_text:
                return model_text

        abilities = self._ability_registry()
        if not abilities.can_execute("speech.thinking_ack"):
            return None
        return self._safe_immediate_route_speech(
            abilities.localized_speech(
                "speech.thinking_ack",
                language=decision.language,
                user_text=user_text,
            )
        )

    def _route_item_dicts(self, decision: RouteDecision) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for item in getattr(decision, "routes", []) or []:
            if hasattr(item, "model_dump"):
                dumped = item.model_dump(mode="json", exclude_none=True)
                if isinstance(dumped, dict):
                    items.append(dumped)
            elif isinstance(item, dict):
                items.append(item)
        metadata = decision.metadata if isinstance(decision.metadata, dict) else {}
        raw = metadata.get("route_items")
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict):
                    items.append(item)
        seen: set[str] = set()
        unique: list[dict[str, Any]] = []
        for index, item in enumerate(items):
            key = str(
                item.get("id")
                or item.get("route_item_id")
                or (item.get("metadata") or {}).get("route_item_id")
                or f"{index}:{item.get('route')}:{item.get('intent')}:{item.get('text')}"
            )
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)
        return unique

    @staticmethod
    def _fast_speech_payload_text(payload: Any) -> str | None:
        if not payload:
            return None
        if hasattr(payload, "model_dump"):
            payload = payload.model_dump(mode="json", exclude_none=True)
        if isinstance(payload, dict):
            return str(payload.get("text") or "")
        return None

    @staticmethod
    def _safe_validated_response_plan_speech(text: str | None) -> str | None:
        cleaned = " ".join((text or "").strip().split())
        if not cleaned or len(cleaned) > 160:
            return None
        lowered = cleaned.casefold()
        if any(marker in lowered for marker in ("soridormi.", "chromie.")):
            return None
        return cleaned

    @classmethod
    def _validated_fast_speech_payload_text(cls, payload: Any) -> str | None:
        """Validate the whole dynamic FastSpeech contract before playback.

        Bare strings and partially structured objects remain parseable at API
        boundaries for compatibility, but they are not sufficient authority to
        produce immediate audio. Dynamic playback requires an explicit process
        speech act and a non-terminal commitment, while the completion marker
        must retain its fail-closed true value.
        """

        if hasattr(payload, "model_dump"):
            payload = payload.model_dump(mode="json", exclude_none=True)
        if not isinstance(payload, dict):
            return None
        if payload.get("must_not_claim_completion") is not True:
            return None
        if str(payload.get("purpose") or "").strip().casefold() not in {
            "acknowledge",
            "acknowledge_and_check",
            "clarify",
            "thinking",
            "safety_prelude",
        }:
            return None
        if str(payload.get("commitment") or "").strip().casefold() not in {
            "checking_only",
            "needs_confirmation",
            "prelude_only",
        }:
            return None
        return cls._safe_immediate_route_speech(str(payload.get("text") or ""))

    @staticmethod
    def _safe_immediate_route_speech(text: str | None) -> str | None:
        cleaned = " ".join((text or "").strip().split())
        if not cleaned or len(cleaned) > 120:
            return None
        lowered = cleaned.casefold()
        blocked_terms = (
            "soridormi.",
            "chromie.",
            "task split",
            "key risk",
            "next step",
            "done",
            "completed",
            "finished",
            "handled",
            "took care",
            "resolved",
            "delivered",
            "performed",
            "executing",
            "moving",
            "walking",
            "turning",
            "tool result",
            "the result is",
            "i found the result",
            "i remembered",
            "i have remembered",
            "我记住了",
            "我查到",
            "查询结果",
            "已经",
            "完成",
            "执行",
            "正在",
        )
        if any(term in lowered for term in blocked_terms):
            return None
        terminal_claim_patterns = (
            r"\b(?:i|we)(?:['’]ve|\s+have|\s+already|\s+just|\s+successfully)*\s+"
            r"(?:did|made|fixed|sent|saved|booked|updated|changed|created|removed|"
            r"deleted|ordered|called|emailed|wrote|finished|completed|handled|resolved)\b",
            r"\b(?:it|that|this)(?:['’]s|\s+is|\s+has\s+been)\s+"
            r"(?:done|ready|fixed|sent|saved|finished|completed|handled|resolved)\b",
            r"\b(?:taken\s+care\s+of|all\s+set)\b",
            r"(?:任务|事情|这件事|这个请求|工作|处理).{0,6}"
            r"(?:办好|做好|处理好|搞定|完成)了?",
            r"(?:办好了|做好了|处理好了|搞定了)",
        )
        if any(re.search(pattern, lowered) for pattern in terminal_claim_patterns):
            return None
        return cleaned

    def _router_fast_speech_diagnostics(self, decision: RouteDecision) -> dict[str, Any]:
        top_raw = self._fast_speech_payload_text(getattr(decision, "fast_speech", None))
        top_safe = self._validated_fast_speech_payload_text(
            getattr(decision, "fast_speech", None)
        )
        item_raw_count = 0
        item_safe_count = 0
        direct_item_count = 0
        for item in self._route_item_dicts(decision):
            item_raw = self._fast_speech_payload_text(item.get("fast_speech"))
            if item_raw:
                item_raw_count += 1
                if self._validated_fast_speech_payload_text(item.get("fast_speech")):
                    item_safe_count += 1
            if str(item.get("lane") or "") in {"immediate_speech", "fast_tts"} and item.get("direct_to_tts") is True:
                direct_item_count += 1
        speak_first_raw = " ".join((decision.speak_first or "").split())
        speak_first_safe = self._safe_immediate_route_speech(speak_first_raw)
        return {
            "router_generated_fast_speech_enabled": bool(
                getattr(self, "router_generated_fast_speech_enabled", False)
            ),
            "top_fast_speech_present": bool(top_raw),
            "top_fast_speech_safe": bool(top_safe),
            "route_item_fast_speech_count": item_raw_count,
            "route_item_fast_speech_safe_count": item_safe_count,
            "direct_immediate_speech_items": direct_item_count,
            "speak_first_present": bool(speak_first_raw),
            "speak_first_safe": bool(speak_first_safe),
        }

    def _router_fast_speech_text(
        self,
        decision: RouteDecision,
        *,
        task_snapshots: list[dict[str, Any]] | None = None,
    ) -> str | None:
        metadata = decision.metadata if isinstance(decision.metadata, dict) else {}
        response_plan = metadata.get("response_plan")
        if isinstance(response_plan, dict):
            validation = validate_immediate_response_plan(
                response_plan,
                task_snapshots or [],
            )
            metadata["response_plan_validation"] = validation.as_dict()
            if validation.accepted and validation.stage is not None:
                planned_text = self._safe_validated_response_plan_speech(
                    validation.stage.text
                )
                if planned_text:
                    return planned_text
        if not getattr(self, "router_generated_fast_speech_enabled", False):
            return None

        text = self._validated_fast_speech_payload_text(
            getattr(decision, "fast_speech", None)
        )
        if text:
            return text

        for item in self._route_item_dicts(decision):
            item_fast = self._validated_fast_speech_payload_text(
                item.get("fast_speech")
            )
            if item_fast:
                return item_fast
            if str(item.get("lane") or "") not in {"immediate_speech", "fast_tts"}:
                continue
            if item.get("direct_to_tts") is not True:
                continue
        return None

    def _immediate_route_speech_text(self, decision: RouteDecision) -> str | None:
        # Backward-compatible name used by older tests/call sites. The actual
        # source of fast-first speech is now the Router-generated fast_speech
        # field or an immediate_speech route item, not an Orchestrator template.
        return self._router_fast_speech_text(decision)

    async def _schedule_deep_thought_ack(
        self,
        decision: RouteDecision,
        user_text: str,
        session_id: str,
    ) -> bool:
        text = self._deep_thought_ack_text(decision, user_text)
        if not text:
            return False

        self.session_log(
            session_id,
            "deep_thought_ack_schedule: chars=%s text=%r",
            len(text),
            text,
        )
        scheduled = await self.schedule_tts_text(text, session_id)
        if scheduled.get("scheduled") is True:
            self.session_log(
                session_id,
                "deep_thought_ack_scheduled: order=%s chunks=%s generation=%s",
                scheduled.get("order"),
                scheduled.get("chunks", 1),
                scheduled.get("generation"),
            )
            return True

        self.session_log(
            session_id,
            "deep_thought_ack_skipped: reason=%s",
            scheduled.get("reason", "unknown"),
        )
        return False


    def _weather_tool_ack_text(
        self,
        decision: RouteDecision,
        user_text: str,
    ) -> str | None:
        route_candidates: list[dict[str, Any]] = []
        metadata = decision.metadata if isinstance(decision.metadata, dict) else {}
        route_candidates.append({
            "route": decision.route,
            "intent": decision.intent,
            "metadata": metadata,
        })
        route_candidates.extend(self._route_item_dicts(decision))

        for item in route_candidates:
            intent = str(item.get("intent") or "").casefold()
            item_metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            if (
                str(item.get("route") or "") != "tool"
                and str(item_metadata.get("tool_name") or "").casefold() != "weather"
                and "weather" not in intent
                and "forecast" not in intent
            ):
                continue
            if (
                str(item_metadata.get("tool_name") or "").casefold() != "weather"
                and "weather" not in intent
                and "forecast" not in intent
                and not isinstance(item_metadata.get("weather_query"), dict)
            ):
                continue
            query = item_metadata.get("weather_query")
            location = ""
            date = "today"
            if isinstance(query, dict):
                location = " ".join(str(query.get("location") or "").split())
                date = str(query.get("date") or "today").strip().casefold()
            language = (decision.language or "").lower()
            zh = language.startswith("zh") or any(
                "\u4e00" <= ch <= "\u9fff" for ch in user_text
            )
            if zh:
                day = "明天" if date in {"tomorrow", "明天"} else "今天"
                return f"我查一下{location}{day}的天气。" if location else f"我查一下{day}的天气。"
            day = "tomorrow" if date == "tomorrow" else "today"
            return f"Let me check {location}'s weather {day}." if location else f"Let me check the weather {day}."
        return None

    def _fast_first_response_text(
        self,
        decision: RouteDecision,
        user_text: str,
        *,
        task_snapshots: list[dict[str, Any]] | None = None,
    ) -> str | None:
        if not self.fast_first_response_enabled or not decision.should_speak:
            return None
        if decision.route in {"interrupt", "ignore"}:
            return None
        # Generative TTS can take longer than a small read-only tool call. Keep
        # tool acknowledgements opt-in so a weather result is not queued behind
        # a slower “I am checking” synthesis. Deep reasoning and guarded action
        # preludes remain independently available.
        if (
            decision.route == "tool"
            and not getattr(self, "fast_first_tool_response_enabled", False)
        ):
            return None

        router_text = self._router_fast_speech_text(
            decision,
            task_snapshots=task_snapshots,
        )
        if router_text:
            return router_text

        # Raw speak_first is retained in the wire schema for compatibility but
        # is not independently playable. When the dynamic compatibility gate is
        # enabled it is considered only by the deep-thought path below, which
        # still applies the completion-claim guard.

        if decision.route == "deep_thought":
            return self._deep_thought_ack_text(decision, user_text)

        # Do not invent route-specific fast-first wording here. The quick Router
        # is responsible for natural, context-aware immediate speech. If it did
        # not provide one, stay silent and let the downstream Agent/Tool speak.
        return None

    async def _schedule_fast_first_response(
        self,
        decision: RouteDecision,
        user_text: str,
        session_id: str,
    ) -> bool:
        conversation_state = getattr(self, "conversation_state", None)
        task_snapshots = (
            conversation_state.active_task_snapshots()
            if conversation_state is not None
            else []
        )
        text = self._fast_first_response_text(
            decision,
            user_text,
            task_snapshots=task_snapshots,
        )
        if not text:
            self.session_log(
                session_id,
                "fast_first_response_skipped: route=%s intent=%s reason=%s diagnostics=%s",
                decision.route,
                decision.intent,
                "not_applicable",
                json.dumps(
                    self._router_fast_speech_diagnostics(decision),
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            )
            return False

        self.session_log(
            session_id,
            "fast_first_response_schedule: route=%s intent=%s chars=%s text=%r",
            decision.route,
            decision.intent,
            len(text),
            text,
        )
        scheduled = await self.schedule_tts_text(text, session_id)
        if scheduled.get("scheduled") is True:
            self.session_log(
                session_id,
                "fast_first_response_scheduled: route=%s order=%s chunks=%s generation=%s",
                decision.route,
                scheduled.get("order"),
                scheduled.get("chunks", 1),
                scheduled.get("generation"),
            )
            decision.metadata = {
                **(decision.metadata or {}),
                "fast_first_response_scheduled": True,
                "fast_first_response": {
                    "scheduled": True,
                    "route": decision.route,
                    "intent": decision.intent,
                    "text": text,
                    "chunks": scheduled.get("chunks", 1),
                    "generation": scheduled.get("generation"),
                },
            }
            if decision.speak_first and decision.speak_first.strip() == text:
                decision.speak_first = None
            return True

        self.session_log(
            session_id,
            "fast_first_response_skipped: route=%s intent=%s reason=%s",
            decision.route,
            decision.intent,
            scheduled.get("reason", "unknown"),
        )
        return False

    def _deep_thought_body_cue_response(
        self,
        decision: RouteDecision,
        user_text: str,
    ) -> InteractionResponse | None:
        if not self._deep_thought_prelude_allowed(decision):
            return None
        abilities = self._ability_registry()
        ability = abilities.get("social.thinking_pose")
        if not ability.can_execute or not ability.soridormi_skill_id:
            return None

        language = (decision.language or "").lower()
        zh = language.startswith("zh") or any(
            "\u4e00" <= ch <= "\u9fff" for ch in user_text
        )
        return InteractionResponse(
            skills=[
                SkillRequest(
                    skill_id=ability.soridormi_skill_id,
                    args=dict(ability.default_args),
                    timing="parallel",
                    timeout_ms=ability.timeout_ms,
                    requires_confirmation=True,
                    metadata={
                        "source": "host_deep_thought_ack",
                        "ability_id": ability.ability_id,
                        "ability_status": ability.status,
                        "reason": "thinking_attention",
                    },
                )
            ],
            metadata={
                "source": "host_deep_thought_ack",
                "ability_id": ability.ability_id,
                "ability_status": ability.status,
                "optional_body_cue": True,
                "language": "zh-CN" if zh else (decision.language or "en-US"),
            },
        )

    async def _launch_deep_thought_body_cue(
        self,
        decision: RouteDecision,
        user_text: str,
        session_id: str,
    ) -> bool:
        response = self._deep_thought_body_cue_response(decision, user_text)
        if response is None:
            return False

        skill_id = response.skills[0].skill_id if response.skills else "<none>"
        self.session_log(
            session_id,
            "deep_thought_body_cue_launch: skill_id=%s",
            skill_id,
        )
        self._launch_interaction(
            response,
            session_id,
            reset_playback=False,
            mark_session_done=False,
        )
        return True

    def _apply_conditional_deepthinking_policy(
        self,
        decision: RouteDecision,
        *,
        context: dict[str, Any],
        session_id: str,
    ) -> RouteDecision:
        policy = getattr(self, "deepthinking_policy", None)
        if policy is None:
            policy = DeepThinkingDelegationPolicy()
        delegation = policy.evaluate(decision, context=context)
        if not delegation.should_delegate:
            return decision
        delegated = policy.delegate_decision(decision, delegation)
        self.session_log(
            session_id,
            "conditional_deepthinking_delegate: original_route=%s original_intent=%s "
            "confidence=%.2f reasons=%s",
            delegation.original_route,
            delegation.original_intent,
            delegation.original_confidence,
            ",".join(delegation.reasons),
        )
        return delegated

    def _cognitive_gateway_adapter(self) -> GatewayCoreCompatibilityAdapter:
        adapter = getattr(self, "cognitive_gateway", None)
        if adapter is None:
            adapter = GatewayCoreCompatibilityAdapter()
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
    def _cognitive_lane_from_route(decision: RouteDecision) -> str:
        if decision.route in {"chat", "clarify", "deep_thought"}:
            return "chat"
        if decision.route in {"robot_action", "tool", "memory"}:
            return decision.route
        return "unsupported"

    @staticmethod
    def _cognitive_resolution_summary(
        resolution: CognitiveRuntimeResolution,
    ) -> dict[str, Any]:
        terminal = resolution.terminal_plan
        return {
            "mode": resolution.mode,
            "status": resolution.status,
            "lane": resolution.lane,
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

    def _legacy_agent_authority_context(
        self,
        context: dict[str, Any],
        *,
        session_id: str,
        decision: RouteDecision,
        reason: str,
    ) -> dict[str, Any]:
        if decision.route == "robot_action" and decision.actions:
            claim = SemanticAuthorityClaim(
                owner="router_action_adapter",
                role="adapter",
                turn_id=session_id,
                reason=reason,
            )
        elif (
            decision.route == "robot_action"
            and "capability_agent" in decision.agents
            and getattr(self, "legacy_semantic_fallback_enabled", False)
        ):
            claim = SemanticAuthorityClaim(
                owner="legacy_capability_fallback",
                role="authoritative",
                turn_id=session_id,
                reason=reason,
                emergency_fallback=True,
            )
        else:
            claim = SemanticAuthorityClaim(
                owner="legacy_agent_pipeline",
                role="authoritative",
                turn_id=session_id,
                reason=reason,
            )
        return context_with_semantic_authority(context, claim)

    async def _run_cognitive_runtime_pipeline(
        self,
        session: aiohttp.ClientSession,
        *,
        user_text: str,
        session_id: str,
        context: dict[str, Any],
        decision: RouteDecision,
        record_evidence: bool = True,
        turn_envelope: UserTurnEnvelope | None = None,
    ) -> CognitiveRuntimeResolution:
        started_ms = now_ms()
        if turn_envelope is None:
            resolution = CognitiveRuntimeResolution(
                mode=self.cognitive_runtime_mode,
                status="error",
                lane=self._cognitive_lane_from_route(decision),
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
        resolved_language = decision.language or (
            "zh-CN" if self._looks_zh(user_text) else "en-US"
        )
        resolved_history = authority_context.get("history", [])
        if turn_envelope is not None:
            projection = self._cognitive_gateway_adapter().project_for_core(
                turn_envelope,
                legacy_text=user_text,
                legacy_session_id=session_id,
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
                    route_decision=decision,
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
                lane=self._cognitive_lane_from_route(decision),
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
            "cognitive_runtime_done: mode=%s status=%s lane=%s total_ms=%.1f "
            "planner=%s disposition=%s steps=%s failure_stage=%s failure_class=%s "
            "architecture_attribution=%s fallback=%s",
            resolution.mode,
            resolution.status,
            resolution.lane,
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

    async def _run_cognitive_runtime_report(
        self,
        session: aiohttp.ClientSession,
        *,
        user_text: str,
        session_id: str,
        context: dict[str, Any],
        decision: RouteDecision,
        turn_envelope: UserTurnEnvelope | None = None,
    ) -> None:
        await self._run_cognitive_runtime_pipeline(
            session,
            user_text=user_text,
            session_id=session_id,
            context=context,
            decision=decision,
            turn_envelope=turn_envelope,
        )

    def _schedule_cognitive_runtime_report(
        self,
        session: aiohttp.ClientSession,
        *,
        user_text: str,
        session_id: str,
        context: dict[str, Any],
        decision: RouteDecision,
        turn_envelope: UserTurnEnvelope | None = None,
    ) -> RouteDecision:
        if (
            self.cognitive_runtime_mode != "report_only"
            or not self.enable_agent
            or decision.interrupt_current
            or decision.route in {"interrupt", "ignore"}
        ):
            return decision
        task = asyncio.create_task(
            self._run_cognitive_runtime_report(
                session,
                user_text=user_text,
                session_id=session_id,
                context=context,
                decision=decision,
                turn_envelope=turn_envelope,
            )
        )
        self.cognitive_runtime_report_tasks.add(task)
        task.add_done_callback(self.cognitive_runtime_report_tasks.discard)
        metadata = dict(decision.metadata or {})
        metadata["cognitive_runtime_resolution"] = {
            "status": "scheduled",
            "mode": "report_only",
            "active_goal_count": len(context.get("active_goal_snapshots") or []),
        }
        metadata["cognitive_runtime_mode"] = "report_only"
        self.session_log(
            session_id,
            "cognitive_runtime_report_scheduled: active_goals=%s",
            len(context.get("active_goal_snapshots") or []),
        )
        return decision.model_copy(update={"metadata": metadata})

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
        decision: RouteDecision,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Bridge the Core's semantic target to trusted cancellation closure."""

        return await dispatch_named_goal_cancellation(
            conversation_state=self.conversation_state,
            interaction_runtime=self.interaction_runtime,
            confirmation_dialogue=getattr(self, "confirmation_dialogue", None),
            resolution=resolution,
            session_id=session_id,
            user_text=user_text,
            decision=decision,
        )

    def _apply_cognitive_goal_state(
        self,
        resolution: CognitiveRuntimeResolution,
        *,
        session_id: str,
        user_text: str,
        decision: RouteDecision,
    ) -> list[dict[str, Any]]:
        association = resolution.goal_association
        if association is None:
            return []
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
            route=decision.route,
            intent=decision.intent,
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

    async def _try_apply_cognitive_runtime(
        self,
        session: aiohttp.ClientSession,
        *,
        user_text: str,
        session_id: str,
        context: dict[str, Any],
        decision: RouteDecision,
        router_latency_ms: float,
        turn_envelope: UserTurnEnvelope | None = None,
    ) -> tuple[bool, RouteDecision]:
        cognitive_lane = self._cognitive_lane_from_route(decision)
        if (
            self.cognitive_runtime_mode != "apply"
            or not self.enable_agent
            or not self.enable_interaction_response
            or decision.interrupt_current
            or decision.route in {"interrupt", "ignore"}
            or cognitive_lane not in getattr(
                self,
                "cognitive_apply_lanes",
                frozenset({"chat"}),
            )
        ):
            return False, decision

        fast_first_hedge = self._start_fast_first_audio_hedge(
            decision, user_text, session_id
        )
        resolution = await self._run_cognitive_runtime_pipeline(
            session,
            user_text=user_text,
            session_id=session_id,
            context=context,
            decision=decision,
            record_evidence=False,
            turn_envelope=turn_envelope,
        )
        if turn_envelope is not None and resolution.turn_envelope is None:
            resolution = resolution.model_copy(
                update={"turn_envelope": turn_envelope}
            )
        summary = self._cognitive_resolution_summary(resolution)
        metadata = dict(decision.metadata or {})
        metadata["cognitive_runtime_resolution"] = summary
        metadata["cognitive_runtime_mode"] = "apply"
        decision = decision.model_copy(update={"metadata": metadata})

        if resolution.status != "applied" or resolution.interaction_response is None:
            fast_first_scheduled = await self._settle_fast_first_audio_hedge(
                fast_first_hedge,
                decision=decision,
                session_id=session_id,
            )
            safe_response = self._agent_exception_safe_response(
                decision, user_text=user_text
            )
            if safe_response is None:
                text = (
                    "我没能可靠地完成这次理解，所以先不继续。你可以换一种说法。"
                    if self._looks_zh(user_text)
                    else "I could not resolve that reliably, so I stopped before acting. Please rephrase it."
                )
                safe_response = self._host_speech_response(
                    text,
                    style="warning",
                    source="host_cognitive_runtime_fail_closed",
                )
            self.conversation_state.record_user_turn(
                session_id,
                user_text,
                route=decision.route,
                intent=decision.intent,
                metadata=self._metadata_with_turn_envelope(
                    {
                        "source": "goal_driven_cognitive_runtime",
                        "semantic_task_resolution_authoritative": True,
                        "cognitive_runtime_resolution": summary,
                    },
                    turn_envelope,
                ),
            )
            self.conversation_state.record_agent_result(session_id, safe_response)
            self._record_cognitive_runtime_evidence(
                resolution, session_id=session_id, user_text=user_text
            )
            self._launch_interaction(
                safe_response,
                session_id,
                reset_playback=not fast_first_scheduled,
            )
            return True, decision

        response = resolution.interaction_response.model_copy(deep=True)
        try:
            response_metadata = self._metadata_with_turn_envelope(
                {
                    **response.metadata,
                    "language": decision.language,
                    **self._route_proposal_metadata(decision),
                    "cognitive_runtime_resolution": summary,
                    "experience_context": self._experience_context(
                        user_text=user_text,
                        decision=decision,
                        router_latency_ms=router_latency_ms,
                        agent_latency_ms=float(
                            resolution.timings_ms.get("total", 0.0)
                        ),
                    ),
                },
                turn_envelope,
            )
            response = response.model_copy(
                deep=True,
                update={
                    "metadata": response_metadata,
                },
            )
            cancellation_goal_ids = cancellation_target_goal_ids(resolution)
            if cancellation_goal_ids:
                goal_state_results, cancellation_metadata = (
                    await self._dispatch_named_goal_cancellation(
                        resolution,
                        session_id=session_id,
                        user_text=user_text,
                        decision=decision,
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
                goal_state_results = self._apply_cognitive_goal_state(
                    resolution,
                    session_id=session_id,
                    user_text=user_text,
                    decision=decision,
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
            fast_first_scheduled = await self._settle_fast_first_audio_hedge(
                fast_first_hedge,
                decision=decision,
                session_id=session_id,
            )
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
            metadata = dict(decision.metadata or {})
            metadata["cognitive_runtime_resolution"] = summary
            metadata["cognitive_runtime_mode"] = "apply"
            decision = decision.model_copy(update={"metadata": metadata})
            safe_response = (
                cancellation_failure_response
                or self._agent_exception_safe_response(
                    decision, user_text=user_text
                )
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
            self.conversation_state.record_user_turn(
                session_id,
                user_text,
                route=decision.route,
                intent=decision.intent,
                metadata=self._metadata_with_turn_envelope(
                    {
                        "source": "goal_driven_cognitive_runtime",
                        "semantic_task_resolution_authoritative": True,
                        "cognitive_runtime_resolution": summary,
                    },
                    turn_envelope,
                ),
            )
            self.conversation_state.record_agent_result(session_id, safe_response)
            self._record_cognitive_runtime_evidence(
                resolution, session_id=session_id, user_text=user_text
            )
            self._launch_interaction(
                safe_response, session_id, reset_playback=not fast_first_scheduled
            )
            return True, decision

        self.conversation_state.record_user_turn(
            session_id,
            user_text,
            route=decision.route,
            intent=decision.intent,
            metadata=self._metadata_with_turn_envelope(
                {
                    "source": "goal_driven_cognitive_runtime",
                    "confidence": decision.confidence,
                    "semantic_task_resolution_authoritative": True,
                    "cognitive_runtime_resolution": summary,
                },
                turn_envelope,
            ),
        )
        self._record_cognitive_runtime_evidence(
            resolution, session_id=session_id, user_text=user_text
        )
        self.session_log(
            session_id,
            "cognitive_interaction_ready: speech=%s skills=%s requires_confirmation=%s",
            len(response.speech),
            len(response.skills),
            response.requires_confirmation,
        )
        for request in response.skills:
            self.session_log(
                session_id,
                "cognitive_skill_proposed: request_id=%s skill_id=%s timing=%s "
                "requires_confirmation=%s args=%s",
                request.request_id,
                request.skill_id,
                request.timing,
                request.requires_confirmation,
                json.dumps(request.args, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            )
        fast_first_scheduled = await self._settle_fast_first_audio_hedge(
            fast_first_hedge,
            decision=decision,
            session_id=session_id,
        )
        if await self._stage_interaction_confirmation(
            response,
            session_id,
            language=decision.language,
            reset_playback=not fast_first_scheduled,
        ):
            return True, decision
        self.conversation_state.record_agent_result(session_id, response)
        self._launch_interaction(
            response, session_id, reset_playback=not fast_first_scheduled
        )
        return True, decision

    async def _run_response_composer_report(
        self,
        session: aiohttp.ClientSession,
        *,
        user_text: str,
        session_id: str,
        context: dict[str, Any],
        decision: RouteDecision,
        plan: Any,
    ) -> None:
        if getattr(self, "response_composer_mode", "off") != "report_only":
            return
        started_ms = now_ms()
        composition_context = dict(context)
        composition_context["canonical_plan_resolution"] = plan.model_dump(mode="json")
        self.session_log(
            session_id,
            "response_composer_report_started: plan_id=%s disposition=%s goals=%s",
            plan.plan_id,
            plan.disposition,
            len(plan.goal_ids),
        )
        try:
            resolution = await self.agent_client.compose_response_plan(
                session,
                text=user_text,
                route_decision=decision,
                sid=session_id,
                context=composition_context,
                history=context.get("history", []),
                timeout_ms=getattr(self, "response_composer_timeout_ms", 5000),
            )
        except Exception as exc:
            self.session_log(
                session_id,
                "response_composer_report_failed: ms=%.1f error_type=%s error=%s",
                now_ms() - started_ms,
                type(exc).__name__,
                exc,
            )
            return
        composition = resolution.composition
        if composition is None:
            self.session_log(
                session_id,
                "response_composer_report_done: ms=%.1f status=%s composition=false reason=%s",
                now_ms() - started_ms,
                resolution.status,
                resolution.reason_summary or "none",
            )
            return
        response_plan = composition.response_plan
        stage_count = sum(
            1
            for stage in (
                response_plan.immediate,
                response_plan.pre_action,
                *response_plan.progress,
                response_plan.final,
            )
            if stage is not None
        )
        attention = composition.social_attention_plan
        self.session_log(
            session_id,
            "response_composer_report_done: ms=%.1f status=%s stages=%s attention=%s confidence=%.2f fingerprint=%s",
            now_ms() - started_ms,
            resolution.status,
            stage_count,
            attention.decision if attention is not None else "absent",
            composition.confidence,
            composition.canonical_plan_fingerprint[:12],
        )

    async def _run_fast_planner_report(
        self, session: aiohttp.ClientSession, *, user_text: str, session_id: str,
        context: dict[str, Any], decision: RouteDecision,
    ) -> None:
        started_ms = now_ms()
        try:
            plan = await self.agent_client.resolve_fast_plan(
                session, text=user_text, route_decision=decision, sid=session_id,
                context=context, history=context.get("history", []), timeout_ms=self.fast_planner_timeout_ms,
            )
        except Exception as exc:
            self.session_log(session_id, "fast_planner_report_failed: ms=%.1f error_type=%s error=%s",
                             now_ms() - started_ms, type(exc).__name__, exc)
            return
        self.session_log(session_id,
            "fast_planner_report_done: ms=%.1f coverage=%s disposition=%s steps=%s confidence=%.2f escalation=%s",
            now_ms() - started_ms, plan.coverage, plan.disposition, len(plan.steps), plan.confidence,
            plan.escalation_reason or "none")
        if plan.disposition != "escalate":
            await self._run_response_composer_report(
                session, user_text=user_text, session_id=session_id,
                context=context, decision=decision, plan=plan,
            )
            return
        if self.deep_planner_mode != "report_only":
            return
        deep_context = dict(context)
        deep_context["fast_plan_resolution"] = plan.model_dump(mode="json")
        deep_started_ms = now_ms()
        self.session_log(session_id, "deep_planner_report_started: fast_plan_id=%s reason=%s",
                         plan.plan_id, plan.escalation_reason or "unspecified")
        try:
            deep_plan = await self.agent_client.resolve_deep_plan(
                session, text=user_text, route_decision=decision, sid=session_id,
                context=deep_context, history=context.get("history", []),
                timeout_ms=self.deep_planner_timeout_ms,
            )
        except Exception as exc:
            self.session_log(session_id, "deep_planner_report_failed: ms=%.1f error_type=%s error=%s",
                             now_ms() - deep_started_ms, type(exc).__name__, exc)
            return
        self.session_log(session_id,
            "deep_planner_report_done: ms=%.1f coverage=%s disposition=%s steps=%s confidence=%.2f attempts=%s",
            now_ms() - deep_started_ms, deep_plan.coverage, deep_plan.disposition, len(deep_plan.steps),
            deep_plan.confidence, deep_plan.metadata.get("attempt_count", 1))
        await self._run_response_composer_report(
            session, user_text=user_text, session_id=session_id,
            context=context, decision=decision, plan=deep_plan,
        )

    def _schedule_fast_planner_report(
        self, session: aiohttp.ClientSession, *, user_text: str, session_id: str,
        context: dict[str, Any], decision: RouteDecision,
    ) -> RouteDecision:
        if self.fast_planner_mode != "report_only" or not self.enable_agent or decision.interrupt_current or decision.route in {"interrupt", "ignore"}:
            return decision
        task = asyncio.create_task(self._run_fast_planner_report(
            session, user_text=user_text, session_id=session_id, context=context, decision=decision))
        self.fast_planner_report_tasks.add(task)
        task.add_done_callback(self.fast_planner_report_tasks.discard)
        metadata = dict(decision.metadata or {})
        metadata["fast_planner_resolution"] = {"status": "scheduled", "mode": "report_only"}
        metadata["fast_planner_mode"] = "report_only"
        if getattr(self, "response_composer_mode", "off") == "report_only":
            metadata["response_composer_resolution"] = {
                "status": "waiting_for_terminal_plan",
                "mode": "report_only",
            }
            metadata["response_composer_mode"] = "report_only"
        self.session_log(session_id, "fast_planner_report_scheduled")
        return decision.model_copy(update={"metadata": metadata})

    async def _run_goal_association_report(
        self,
        session: aiohttp.ClientSession,
        *,
        user_text: str,
        session_id: str,
        context: dict[str, Any],
        decision: RouteDecision,
    ) -> None:
        started_ms = now_ms()
        try:
            resolution = await self.agent_client.resolve_goal_association(
                session,
                text=user_text,
                route_decision=decision,
                sid=session_id,
                context=context,
                history=context.get("history", []),
                timeout_ms=self.goal_association_timeout_ms,
            )
        except Exception as exc:
            self.session_log(
                session_id,
                "goal_association_report_failed: ms=%.1f error_type=%s error=%s",
                now_ms() - started_ms,
                type(exc).__name__,
                exc,
            )
            return
        status = str((resolution.metadata or {}).get("status") or "resolved")
        relationships = ",".join(item.relationship for item in resolution.associations) or "none"
        self.session_log(
            session_id,
            "goal_association_report_done: ms=%.1f status=%s associations=%s new_goals=%s clarification=%s confidence=%.2f",
            now_ms() - started_ms,
            status,
            relationships,
            len(resolution.new_goals),
            bool(resolution.clarification),
            resolution.confidence,
        )

    def _schedule_goal_association_report(
        self,
        session: aiohttp.ClientSession,
        *,
        user_text: str,
        session_id: str,
        context: dict[str, Any],
        decision: RouteDecision,
    ) -> RouteDecision:
        if (
            self.goal_association_mode != "report_only"
            or not self.enable_agent
            or decision.interrupt_current
            or decision.route in {"interrupt", "ignore"}
        ):
            return decision
        task = asyncio.create_task(
            self._run_goal_association_report(
                session,
                user_text=user_text,
                session_id=session_id,
                context=context,
                decision=decision,
            )
        )
        self.goal_association_report_tasks.add(task)
        task.add_done_callback(self.goal_association_report_tasks.discard)
        metadata = dict(decision.metadata or {})
        metadata["goal_association_resolution"] = {
            "status": "scheduled",
            "mode": "report_only",
            "active_goal_count": len(context.get("active_goal_snapshots") or []),
        }
        metadata["goal_association_mode"] = "report_only"
        self.session_log(
            session_id,
            "goal_association_report_scheduled: active_goals=%s",
            len(context.get("active_goal_snapshots") or []),
        )
        return decision.model_copy(update={"metadata": metadata})

    async def _run_task_continuity_report(
        self,
        session: aiohttp.ClientSession,
        *,
        user_text: str,
        session_id: str,
        context: dict[str, Any],
        decision: RouteDecision,
    ) -> None:
        started_ms = now_ms()
        try:
            resolution = await self.agent_client.resolve_task_continuity(
                session,
                text=user_text,
                route_decision=decision,
                sid=session_id,
                context=context,
                history=context.get("history", []),
                timeout_ms=self.task_continuity_timeout_ms,
            )
        except Exception as exc:
            self.session_log(
                session_id,
                "task_continuity_report_failed: ms=%.1f error_type=%s error=%s",
                now_ms() - started_ms,
                type(exc).__name__,
                exc,
            )
            return
        status = str((resolution.metadata or {}).get("status") or "resolved")
        self.session_log(
            session_id,
            "task_continuity_report_done: ms=%.1f status=%s operations=%s confidence=%.2f",
            now_ms() - started_ms,
            status,
            len(resolution.operations),
            resolution.confidence,
        )

    async def _review_task_continuity(
        self,
        session: aiohttp.ClientSession,
        *,
        user_text: str,
        session_id: str,
        context: dict[str, Any],
        decision: RouteDecision,
    ) -> RouteDecision:
        if (
            self.task_continuity_mode == "off"
            or not self.enable_agent
            or decision.interrupt_current
            or decision.route in {"interrupt", "ignore"}
        ):
            return decision
        active_tasks = context.get("active_task_snapshots")
        if not isinstance(active_tasks, list) or not active_tasks:
            return decision

        if self.task_continuity_mode == "report_only":
            task = asyncio.create_task(
                self._run_task_continuity_report(
                    session,
                    user_text=user_text,
                    session_id=session_id,
                    context=context,
                    decision=decision,
                )
            )
            tasks = getattr(self, "task_continuity_report_tasks", None)
            if not isinstance(tasks, set):
                tasks = set()
                self.task_continuity_report_tasks = tasks
            tasks.add(task)
            task.add_done_callback(tasks.discard)
            metadata = dict(decision.metadata or {})
            metadata["task_continuity_resolution"] = {
                "status": "scheduled",
                "mode": "report_only",
                "active_task_count": len(active_tasks),
            }
            metadata["task_continuity_mode"] = "report_only"
            self.session_log(
                session_id,
                "task_continuity_report_scheduled: active_tasks=%s",
                len(active_tasks),
            )
            return decision.model_copy(update={"metadata": metadata})

        started_ms = now_ms()
        try:
            resolution = await self.agent_client.resolve_task_continuity(
                session,
                text=user_text,
                route_decision=decision,
                sid=session_id,
                context=context,
                history=context.get("history", []),
                timeout_ms=self.task_continuity_timeout_ms,
            )
        except Exception as exc:
            self.session_log(
                session_id,
                "task_continuity_failed: mode=%s ms=%.1f error_type=%s error=%s",
                self.task_continuity_mode,
                now_ms() - started_ms,
                type(exc).__name__,
                exc,
            )
            metadata = dict(decision.metadata or {})
            metadata["task_continuity_resolution"] = {
                "status": "failed",
                "mode": self.task_continuity_mode,
                "error_type": type(exc).__name__,
                "error": str(exc)[:300],
            }
            return decision.model_copy(update={"metadata": metadata})

        payload = resolution.model_dump(mode="json", exclude_none=True)
        metadata = dict(decision.metadata or {})
        metadata["task_continuity_resolution"] = payload
        metadata["task_continuity_mode"] = self.task_continuity_mode
        resolution_status = str((resolution.metadata or {}).get("status") or "resolved")
        if self.task_continuity_mode == "apply" and resolution_status == "resolved":
            for key in (
                "semantic_task_operations",
                "task_operations",
                "semantic_task_operation",
            ):
                metadata.pop(key, None)
            metadata["semantic_task_operations"] = [
                operation.model_dump(mode="json", exclude_none=True)
                for operation in resolution.operations
            ]
            metadata["semantic_task_resolution_authoritative"] = True
            if resolution.response_plan is not None:
                metadata["response_plan"] = resolution.response_plan.model_dump(
                    mode="json",
                    exclude_none=True,
                )
        elif self.task_continuity_mode == "apply":
            metadata["task_continuity_apply_skipped"] = {
                "reason": "resolver_not_healthy",
                "status": resolution_status,
            }
        self.session_log(
            session_id,
            "task_continuity_done: mode=%s ms=%.1f operations=%s confidence=%.2f",
            self.task_continuity_mode,
            now_ms() - started_ms,
            len(resolution.operations),
            resolution.confidence,
        )
        return decision.model_copy(update={"metadata": metadata})

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
                "cognitive_gateway_reflex_detected: action=%s trigger=%s intent=%s confidence=%.2f",
                reflex_outcome.action,
                reflex_outcome.trigger,
                reflex_outcome.intent,
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
                    intent=reflex_outcome.intent,
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
            self.conversation_state.record_user_turn(
                session_id,
                user_text,
                route="interrupt",
                intent=reflex_outcome.intent,
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
                "cognitive_gateway_reflex_applied: action=%s trigger=%s router_bypassed=True",
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
            self.conversation_state.record_user_turn(
                session_id,
                user_text,
                route="ignore",
                intent=reflex_outcome.intent,
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
                "cognitive_gateway_reflex_applied: action=%s trigger=%s router_bypassed=True",
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

        if not self.enable_router:
            turn_envelope = gateway.for_direct(
                turn_capture,
                source="orchestrator.router_disabled",
                reason="compatibility Router is disabled; preserving existing direct path",
            )
            self.conversation_state.record_user_turn(
                session_id,
                user_text,
                route="direct_llm",
                intent="unknown",
                metadata=self._metadata_with_turn_envelope(
                    {"source": "router_disabled"},
                    turn_envelope,
                ),
            )
            self.active_llm_task = asyncio.create_task(
                self.process_llm_tts(
                    user_text,
                    session_id,
                    fallback_reason="router_disabled",
                    route="direct_llm",
                )
            )
            return

        session = await self.get_http_session()
        context = self.build_context(session_id)
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
        router_start_ms = now_ms()
        self.session_log(session_id, "router_start: text_chars=%s text=%r", len(user_text), user_text)
        try:
            decision = await self.router_client.route(session, text=user_text, sid=session_id, context=context)
            router_latency_ms = now_ms() - router_start_ms
            self.session_log(
                session_id,
                "router_done: router_ms=%.1f route=%s agents=%s intent=%s confidence=%.2f interrupt=%s needs_agent=%s",
                router_latency_ms,
                decision.route,
                ",".join(decision.agents),
                decision.intent,
                decision.confidence,
                decision.interrupt_current,
                decision.needs_agent,
            )
        except Exception as exc:
            self.session_log(session_id, "router_exception: router_ms=%.1f error=%s", now_ms() - router_start_ms, exc)
            logger.warning("Router failed; falling back to direct LLM: %s", exc)
            safe_response = self._router_exception_safe_response(
                user_text,
                context=context,
            )
            turn_envelope = gateway.for_direct(
                turn_capture,
                context=context,
                source="orchestrator.router_exception",
                reason="compatibility Router failed; preserving existing fallback path",
            )
            if safe_response is not None:
                self.conversation_state.record_user_turn(
                    session_id,
                    user_text,
                    route="safe_fallback",
                    intent="router_exception_embodied",
                    metadata=self._metadata_with_turn_envelope(
                        {"source": "router_exception", "error": str(exc)},
                        turn_envelope,
                    ),
                )
                self.session_log(
                    session_id,
                    "router_exception_safe_fallback: reason=embodied_request text=%r",
                    user_text,
                )
                self.conversation_state.record_agent_result(session_id, safe_response)
                self._launch_interaction(safe_response, session_id)
                return
            self.conversation_state.record_user_turn(
                session_id,
                user_text,
                route="direct_llm",
                intent="router_exception",
                metadata=self._metadata_with_turn_envelope(
                    {"source": "router_exception", "error": str(exc)},
                    turn_envelope,
                ),
            )
            self.active_llm_task = asyncio.create_task(
                self.process_llm_tts(
                    user_text,
                    session_id,
                    fallback_reason="router_exception",
                    route="direct_llm",
                )
            )
            return

        turn_envelope = gateway.for_route(
            turn_capture,
            context=context,
            decision=decision,
        )
        if self.cognitive_runtime_mode == "apply":
            handled, decision = await self._try_apply_cognitive_runtime(
                session,
                user_text=user_text,
                session_id=session_id,
                context=context,
                decision=decision,
                router_latency_ms=router_latency_ms,
                turn_envelope=turn_envelope,
            )
            if handled:
                return
        elif self.cognitive_runtime_mode == "report_only":
            decision = self._schedule_cognitive_runtime_report(
                session,
                user_text=user_text,
                session_id=session_id,
                context=context,
                decision=decision,
                turn_envelope=turn_envelope,
            )

        # The legacy conditional-deepthinking and task-continuity chain remains
        # the compatibility path.  Goal-driven apply never loops back through it.
        decision = self._apply_conditional_deepthinking_policy(
            decision,
            context=context,
            session_id=session_id,
        )
        if self.cognitive_runtime_mode == "off":
            decision = self._schedule_goal_association_report(
                session,
                user_text=user_text,
                session_id=session_id,
                context=context,
                decision=decision,
            )
            decision = self._schedule_fast_planner_report(
                session,
                user_text=user_text,
                session_id=session_id,
                context=context,
                decision=decision,
            )
            decision = await self._review_task_continuity(
                session,
                user_text=user_text,
                session_id=session_id,
                context=context,
                decision=decision,
            )

        turn_metadata = {
            "source": decision.source,
            "confidence": decision.confidence,
        }
        if isinstance(decision.metadata, dict):
            for key in (
                "goal_association_resolution",
                "goal_association_mode",
                "cognitive_runtime_resolution",
                "cognitive_runtime_mode",
                "task_relation",
                "target_task_id",
                "task_context_patch",
                "semantic_task_operations",
                "task_operations",
                "semantic_task_operation",
                "semantic_task_resolution_authoritative",
                "task_continuity_resolution",
                "task_continuity_mode",
                "response_plan",
                "orchestrator_deepthinking_delegation",
                "orchestrator_original_route",
            ):
                if key in decision.metadata:
                    turn_metadata[key] = decision.metadata[key]
            review = decision.metadata.get("post_interrupt_review")
            if isinstance(review, dict):
                turn_metadata["post_interrupt_review_status"] = review.get("status")
                corrected = decision.metadata.get("post_interrupt_decision") or review.get(
                    "post_interrupt_decision"
                )
                if isinstance(corrected, dict):
                    turn_metadata["post_interrupt_corrected_route"] = corrected.get("route")
                    turn_metadata["post_interrupt_corrected_intent"] = corrected.get("intent")

        turn_metadata = self._metadata_with_turn_envelope(
            turn_metadata,
            turn_envelope,
        )
        self.conversation_state.record_user_turn(
            session_id,
            user_text,
            route=decision.route,
            intent=decision.intent,
            metadata=turn_metadata,
        )
        # Semantic task operations are advisory Router output, but the
        # ConversationStateManager applies and versions them deterministically.
        # Rebuild the bounded context so downstream planning sees the accepted
        # task/goal state from this same turn rather than the pre-route snapshot.
        context = self.build_context(session_id)

        if decision.interrupt_current or decision.route == "interrupt":
            await self.interrupt(new_session_id=session_id)
            correction = self._post_interrupt_corrected_decision(decision)
            if correction is not None and self.enable_agent and correction.needs_agent:
                self.session_log(
                    session_id,
                    "post_interrupt_correction_start: route=%s intent=%s confidence=%.2f",
                    correction.route,
                    correction.intent,
                    correction.confidence,
                )
                self.active_llm_task = asyncio.create_task(
                    self._run_post_interrupt_correction(
                        session,
                        user_text=user_text,
                        session_id=session_id,
                        context=context,
                        decision=correction,
                        turn_envelope=turn_envelope,
                    )
                )
                return
            state = self.sessions.state.get(session_id)
            if state is not None:
                state["llm_done"] = True
            self.maybe_session_done(session_id)
            return

        if decision.route == "ignore":
            self.session_log(session_id, "router_ignore: intent=%s reason=%s", decision.intent, decision.reason)
            state = self.sessions.state.get(session_id)
            if state is not None:
                state["llm_done"] = True
            self.maybe_session_done(session_id)
            return

        if not self.enable_agent or not decision.needs_agent:
            self.active_llm_task = asyncio.create_task(
                self.process_llm_tts(
                    user_text,
                    session_id,
                    fallback_reason="agent_disabled_or_not_needed",
                    route=decision.route,
                )
            )
            return

        fast_first_hedge = self._start_fast_first_audio_hedge(
            decision,
            user_text,
            session_id,
        )
        fast_first_scheduled = bool(
            (decision.metadata or {}).get("fast_first_response_scheduled")
        )
        await self._launch_deep_thought_body_cue(
            decision,
            user_text,
            session_id,
        )

        agent_context = self._legacy_agent_authority_context(
            context,
            session_id=session_id,
            decision=decision,
            reason=f"orchestrator_{self.cognitive_runtime_mode}_agent_path",
        )
        agent_start_ms = now_ms()
        self.session_log(session_id, "agent_start: route=%s agents=%s intent=%s", decision.route, ",".join(decision.agents), decision.intent)
        try:
            if self.enable_interaction_response:
                response = await self.agent_client.run_interaction(
                    session,
                    text=user_text,
                    route_decision=decision,
                    sid=session_id,
                    context=agent_context,
                    history=agent_context.get("history", []),
                )
                agent_latency_ms = now_ms() - agent_start_ms
                response = response.model_copy(
                    deep=True,
                    update={
                        "metadata": {
                            **response.metadata,
                            "language": decision.language,
                            **self._route_proposal_metadata(decision),
                            "experience_context": self._experience_context(
                                user_text=user_text,
                                decision=decision,
                                router_latency_ms=router_latency_ms,
                                agent_latency_ms=agent_latency_ms,
                            ),
                        }
                    },
                )
                response = self.interaction_runtime.prepare_response(
                    response,
                    session_id=session_id,
                )
                self.session_log(
                    session_id,
                    "interaction_done: agent_ms=%.1f speech=%s skills=%s requires_confirmation=%s",
                    agent_latency_ms,
                    len(response.speech),
                    len(response.skills),
                    response.requires_confirmation,
                )
                for request in response.skills:
                    self.session_log(
                        session_id,
                        "skill_proposed: request_id=%s skill_id=%s timing=%s "
                        "cancellable=%s requires_confirmation=%s args=%s",
                        request.request_id,
                        request.skill_id,
                        request.timing,
                        request.cancellable,
                        request.requires_confirmation,
                        json.dumps(request.args, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                    )
                fast_first_scheduled = await self._settle_fast_first_audio_hedge(
                    fast_first_hedge,
                    decision=decision,
                    session_id=session_id,
                )
                if await self._stage_interaction_confirmation(
                    response,
                    session_id,
                    language=decision.language,
                    reset_playback=not fast_first_scheduled,
                ):
                    return

                self.conversation_state.record_agent_result(session_id, response)
                self._launch_interaction(
                    response,
                    session_id,
                    reset_playback=not fast_first_scheduled,
                )
                return

            result = await self.agent_client.run(
                session,
                text=user_text,
                route_decision=decision,
                sid=session_id,
                context=agent_context,
                history=agent_context.get("history", []),
            )
            self.session_log(
                session_id,
                "agent_done: agent_ms=%.1f speak_immediate=%s actions=%s task_graphs=%s speak_after=%s requires_confirmation=%s",
                now_ms() - agent_start_ms,
                len(result.speak_immediate),
                len(result.actions),
                len(result.task_graphs),
                len(result.speak_after),
                result.requires_confirmation,
            )
            fast_first_scheduled = await self._settle_fast_first_audio_hedge(
                fast_first_hedge,
                decision=decision,
                session_id=session_id,
            )
            if result.actions:
                locked_actions = []
                locked_ids = []
                for action in result.actions:
                    locked_ids.append(action.id)
                    locked_actions.append(
                        action.model_copy(
                            deep=True,
                            update={
                                "requires_confirmation": True,
                                "metadata": {
                                    **action.metadata,
                                    "post_interrupt_physical_resume_lock": True,
                                    "post_interrupt_resume_policy": "requires_fresh_confirmation",
                                },
                            },
                        )
                    )
                result.actions = locked_actions
                result.requires_confirmation = True
                self.session_log(
                    session_id,
                    "post_interrupt_legacy_physical_resume_locked: action_ids=%s",
                    ",".join(locked_ids),
                )
            self.conversation_state.record_agent_result(session_id, result)
            await self.execute_agent_result(
                result,
                session_id,
                reset_playback=not fast_first_scheduled,
            )
        except Exception as exc:
            fast_first_scheduled = await self._settle_fast_first_audio_hedge(
                fast_first_hedge,
                decision=decision,
                session_id=session_id,
            )
            self.session_log(session_id, "agent_exception: agent_ms=%.1f error=%s", now_ms() - agent_start_ms, exc)
            logger.warning("Agent failed; selecting fail-closed fallback policy: %s", exc, exc_info=True)
            safe_response = self._agent_exception_safe_response(
                decision,
                user_text=user_text,
            )
            if safe_response is not None:
                self.conversation_state.record_agent_result(session_id, safe_response)
                self._launch_interaction(
                    safe_response,
                    session_id,
                    reset_playback=not fast_first_scheduled,
                )
                return
            self.active_llm_task = asyncio.create_task(
                self.process_llm_tts(
                    user_text,
                    session_id,
                    reset_playback=not fast_first_scheduled,
                    fallback_reason="agent_exception",
                    route=decision.route,
                )
            )

    def _post_interrupt_corrected_decision(
        self,
        decision: RouteDecision,
    ) -> RouteDecision | None:
        metadata = decision.metadata if isinstance(decision.metadata, dict) else {}
        review = metadata.get("post_interrupt_review")
        if not isinstance(review, dict) or review.get("status") != "corrected":
            return None
        raw = metadata.get("post_interrupt_decision") or review.get("post_interrupt_decision")
        if not isinstance(raw, dict):
            return None
        try:
            corrected = RouteDecision.model_validate(raw)
        except Exception as exc:
            logger.warning("Invalid post-interrupt corrected route: %s", exc)
            return None
        if corrected.route in {"interrupt", "ignore"} or corrected.interrupt_current:
            return None
        corrected.metadata = {
            **(corrected.metadata or {}),
            "post_interrupt_correction": True,
            "original_interrupt_intent": decision.intent,
            "original_interrupt_confidence": decision.confidence,
        }
        return corrected

    async def _run_post_interrupt_correction(
        self,
        session: aiohttp.ClientSession,
        *,
        user_text: str,
        session_id: str,
        context: dict[str, Any],
        decision: RouteDecision,
        turn_envelope: UserTurnEnvelope,
    ) -> None:
        fast_first_scheduled = False
        if decision.speak_first:
            fast_first_scheduled = await self._schedule_fast_first_response(
                decision,
                user_text,
                session_id,
            )

        if self.cognitive_runtime_mode == "apply":
            handled, decision = await self._try_apply_cognitive_runtime(
                session,
                user_text=user_text,
                session_id=session_id,
                context=context,
                decision=decision,
                router_latency_ms=0.0,
                turn_envelope=turn_envelope,
            )
            if handled:
                return

        agent_context = self._legacy_agent_authority_context(
            context,
            session_id=session_id,
            decision=decision,
            reason="post_interrupt_compatibility_path",
        )
        agent_start_ms = now_ms()
        self.session_log(
            session_id,
            "post_interrupt_agent_start: route=%s agents=%s intent=%s",
            decision.route,
            ",".join(decision.agents),
            decision.intent,
        )
        try:
            if self.enable_interaction_response:
                response = await self.agent_client.run_interaction(
                    session,
                    text=user_text,
                    route_decision=decision,
                    sid=session_id,
                    context=agent_context,
                    history=agent_context.get("history", []),
                )
                agent_latency_ms = now_ms() - agent_start_ms
                response = response.model_copy(
                    deep=True,
                    update={
                        "metadata": {
                            **response.metadata,
                            "language": decision.language,
                            "post_interrupt_correction": True,
                            **self._route_proposal_metadata(decision),
                        }
                    },
                )
                response = self.interaction_runtime.prepare_response(
                    response,
                    session_id=session_id,
                )
                response, locked_request_ids = lock_post_interrupt_physical_resume(response)
                if locked_request_ids:
                    self.session_log(
                        session_id,
                        "post_interrupt_physical_resume_locked: request_ids=%s",
                        ",".join(locked_request_ids),
                    )
                self.session_log(
                    session_id,
                    "post_interrupt_interaction_done: agent_ms=%.1f speech=%s skills=%s requires_confirmation=%s",
                    agent_latency_ms,
                    len(response.speech),
                    len(response.skills),
                    response.requires_confirmation,
                )
                for request in response.skills:
                    self.session_log(
                        session_id,
                        "skill_proposed: request_id=%s skill_id=%s timing=%s "
                        "cancellable=%s requires_confirmation=%s",
                        request.request_id,
                        request.skill_id,
                        request.timing,
                        request.cancellable,
                        request.requires_confirmation,
                    )
                if await self._stage_interaction_confirmation(
                    response,
                    session_id,
                    language=decision.language,
                    reset_playback=not fast_first_scheduled,
                ):
                    return
                self.conversation_state.record_agent_result(session_id, response)
                self._launch_interaction(
                    response,
                    session_id,
                    reset_playback=not fast_first_scheduled,
                )
                return

            result = await self.agent_client.run(
                session,
                text=user_text,
                route_decision=decision,
                sid=session_id,
                context=agent_context,
                history=agent_context.get("history", []),
            )
            self.session_log(
                session_id,
                "post_interrupt_agent_done: agent_ms=%.1f speak_immediate=%s actions=%s task_graphs=%s speak_after=%s requires_confirmation=%s",
                now_ms() - agent_start_ms,
                len(result.speak_immediate),
                len(result.actions),
                len(result.task_graphs),
                len(result.speak_after),
                result.requires_confirmation,
            )
            self.conversation_state.record_agent_result(session_id, result)
            await self.execute_agent_result(
                result,
                session_id,
                reset_playback=not fast_first_scheduled,
            )
        except Exception as exc:
            self.session_log(
                session_id,
                "post_interrupt_agent_exception: agent_ms=%.1f error=%s",
                now_ms() - agent_start_ms,
                exc,
            )
            logger.warning(
                "Post-interrupt correction Agent failed: %s",
                exc,
                exc_info=True,
            )
            self.active_llm_task = asyncio.create_task(
                self.process_llm_tts(
                    user_text,
                    session_id,
                    reset_playback=not fast_first_scheduled,
                    fallback_reason="post_interrupt_agent_exception",
                    route=decision.route,
                )
            )

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
        exempted_request_ids = (
            await self.interaction_runtime.confirmation_exemption_request_ids(response)
        )
        if exempted_request_ids:
            self.session_log(
                session_id,
                "confirmation_exempted: reason=sim_auto_confirm mode=sim request_ids=%s",
                ",".join(sorted(exempted_request_ids)),
            )
        if not confirmation_request_ids:
            if exempted_request_ids:
                self._suppress_auto_confirm_confirmation_speech(
                    response,
                    exempted_request_ids=exempted_request_ids,
                    session_id=session_id,
                )
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
                    request.skill_id
                    for request in response.skills
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

    def _suppress_auto_confirm_confirmation_speech(
        self,
        response: InteractionResponse,
        *,
        exempted_request_ids: set[str],
        session_id: str,
    ) -> None:
        if not exempted_request_ids or len(response.speech) < 2:
            return
        kept = []
        dropped_text: list[str] = []
        for speech in response.speech:
            if self._is_confirmation_only_speech(speech.text):
                dropped_text.append(speech.text)
                continue
            kept.append(speech)
        if not dropped_text or not kept:
            return
        response.speech = kept
        response.metadata = {
            **response.metadata,
            "auto_confirm_suppressed_confirmation_speech": len(dropped_text),
        }
        self.session_log(
            session_id,
            "auto_confirm_speech_suppressed: dropped=%s kept=%s request_ids=%s",
            len(dropped_text),
            len(kept),
            ",".join(sorted(exempted_request_ids)),
        )

    @staticmethod
    def _is_confirmation_only_speech(text: str) -> bool:
        normalized = " ".join((text or "").casefold().split())
        if not normalized:
            return False
        confirmation_needles = (
            "can you confirm",
            "please confirm",
            "confirm this action",
            "confirm the action",
            "do you confirm",
            "确认这个动作",
            "请确认",
            "你确认",
            "确认吗",
        )
        return any(needle in normalized for needle in confirmation_needles)

    async def _handle_confirmation_reply(
        self,
        user_text: str,
        session_id: str,
        *,
        turn_envelope: UserTurnEnvelope | None = None,
    ) -> bool:
        resolution = self.confirmation_dialogue.resolve(user_text)
        if resolution.decision == "not_confirmation":
            return False

        if resolution.decision == "operational_interrupt":
            self.session_log(
                session_id,
                "confirmation_rejected: confirmation_id=%s reason=%s fingerprint=%s",
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
                    self.conversation_state.update_pending_task_status(
                        metadata_key="confirmation_id",
                        metadata_value=resolution.confirmation_id,
                        status="cancelled",
                    )
            return False

        self.conversation_state.record_user_turn(
            session_id,
            user_text,
            route="confirmation",
            intent=f"confirmation_{resolution.decision}",
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
            assert resolution.response is not None
            self.session_log(
                session_id,
                "confirmation_authorized: confirmation_id=%s interaction_id=%s "
                "request_ids=%s fingerprint=%s",
                resolution.confirmation_id,
                resolution.response.interaction_id,
                ",".join(sorted(resolution.confirmed_request_ids)),
                resolution.fingerprint,
            )
            self.conversation_state.record_agent_result(
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
        self.conversation_state.record_agent_result(session_id, response)
        self._launch_interaction(response, session_id)
        return True

    def _revoke_pending_confirmation_for_reflex(
        self,
        outcome: ReflexOutcome,
    ) -> Any | None:
        """Revoke an approval token synchronously, before interruption awaits."""

        dialogue = getattr(self, "confirmation_dialogue", None)
        if outcome.cancellation_scope == "output_only":
            return None
        if outcome.cancellation_scope == "embodied_motion":
            pending = getattr(dialogue, "pending", None)
            if pending is None:
                return None
            confirmed = set(
                getattr(pending, "confirmed_request_ids", ()) or ()
            )
            response = getattr(pending, "response", None)
            requests = getattr(response, "skills", ()) or ()
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
                    definition = registry.get(request.skill_id)
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
            for request in (getattr(response, "skills", ()) or ())
        }
        for request_id in confirmed_request_ids:
            request = request_by_id.get(request_id)
            if request is None:
                unknown_request_ids.add(request_id)
                continue
            try:
                definition = registry.get(request.skill_id)
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
        intent: str,
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
                intent=intent,
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

    def _router_exception_safe_response(
        self,
        user_text: str,
        *,
        context: dict[str, Any] | None = None,
    ) -> InteractionResponse | None:
        if not self._looks_like_embodied_request(user_text, context=context):
            return None
        zh = self._looks_zh(user_text)
        text = (
            "我听到了动作请求，但路由没有生成有效的动作结果，所以我不会移动。"
            if zh
            else "I heard a movement request, but routing did not produce a valid motion result, so I will not move."
        )
        return self._host_speech_response(
            text,
            style="warning",
            source="host_router_exception_safe_fallback",
        )

    def _agent_exception_safe_response(
        self,
        decision: RouteDecision,
        *,
        user_text: str,
    ) -> InteractionResponse | None:
        """Fail closed when an effectful Agent path becomes unavailable.

        This guard uses the already-selected route and structured action
        proposals.  It does not reinterpret user language or select a skill.
        """

        metadata = decision.metadata if isinstance(decision.metadata, dict) else {}
        task_list = metadata.get("task_list")
        has_effectful_task = bool(decision.actions)
        if isinstance(task_list, list):
            has_effectful_task = has_effectful_task or any(
                isinstance(item, dict)
                and (
                    str(item.get("task_type") or "").startswith("task.execute")
                    or bool(str(item.get("capability_id") or item.get("skill_id") or "").strip())
                )
                for item in task_list
            )
        if decision.route not in {"robot_action", "tool", "memory"} and not has_effectful_task:
            return None

        zh = self._looks_zh(user_text)
        if decision.route == "robot_action" or has_effectful_task:
            text = (
                "动作规划服务暂时不可用，所以我没有执行这个动作。"
                if zh
                else "The action planner is temporarily unavailable, so I did not perform that action."
            )
        elif decision.route == "tool":
            text = (
                "查询服务暂时不可用，所以我没有返回未经验证的结果。"
                if zh
                else "The lookup service is temporarily unavailable, so I will not invent a result."
            )
        else:
            text = (
                "记忆服务暂时不可用，所以这次没有保存更改。"
                if zh
                else "The memory service is temporarily unavailable, so that change was not saved."
            )
        return self._host_speech_response(
            text,
            style="warning",
            source="host_agent_exception_safe_fallback",
        )

    def _looks_like_embodied_request(
        self,
        user_text: str,
        *,
        context: dict[str, Any] | None = None,
    ) -> bool:
        normalized = " ".join((user_text or "").casefold().split())
        embodied_terms = (
            "walk",
            "move",
            "go forward",
            "turn",
            "nod",
            "shake your head",
            "blink",
            "look at",
            "快一点",
            "走",
            "前进",
            "转",
            "点头",
            "眨眼",
        )
        if any(term in normalized for term in embodied_terms):
            return True
        for task in (context or {}).get("active_pending_tasks", []) or []:
            if not isinstance(task, dict):
                continue
            summary = str(task.get("summary") or "").casefold()
            task_type = str(task.get("type") or "").casefold()
            if "soridormi" in summary or task_type in {"confirmation", "robot_action"}:
                return True
        return False

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

    @staticmethod
    def _route_proposal_metadata(decision: RouteDecision) -> dict[str, Any]:
        metadata = decision.metadata if isinstance(decision.metadata, dict) else {}
        out: dict[str, Any] = {
            "route_final": decision.route,
            "route_intent": decision.intent,
            "route_source": decision.source,
            "route_confidence": decision.confidence,
        }
        route_stage_outputs = metadata.get("route_stage_outputs")
        if isinstance(route_stage_outputs, list):
            out["route_stage_outputs"] = route_stage_outputs
        route_items = metadata.get("route_items")
        if isinstance(route_items, list):
            out["route_items"] = route_items
        task_proposals = metadata.get("task_proposals")
        if isinstance(task_proposals, list):
            out["route_task_proposals"] = task_proposals
        task_list = metadata.get("task_list")
        if isinstance(task_list, list):
            out["route_task_list"] = task_list
        route_merge = metadata.get("route_merge")
        if isinstance(route_merge, dict):
            out["route_merge"] = route_merge
        superseded = metadata.get("superseded_task_proposals")
        if isinstance(superseded, list):
            out["superseded_task_proposals"] = superseded
        revised = metadata.get("revised_task_proposals")
        if isinstance(revised, list):
            out["revised_task_proposals"] = revised
        revisions = metadata.get("task_proposal_revisions")
        if isinstance(revisions, list):
            out["task_proposal_revisions"] = revisions
        if metadata.get("truth_reconciled") is True:
            out["truth_reconciled"] = True
        truth_reason = metadata.get("truth_reconciliation_reason")
        if isinstance(truth_reason, str) and truth_reason.strip():
            out["truth_reconciliation_reason"] = truth_reason.strip()
        return out

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

    async def _execute_cognitive_outcome_response(
        self,
        response: InteractionResponse,
        *,
        session_id: str | None,
    ) -> str:
        try:
            execution = await self.interaction_runtime.execute(
                response,
                session_id=session_id,
            )
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
        execution: SkillRuntimeResult,
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
                and result.skill_id == "chromie.speak"
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
                "skills": [],
                "requires_confirmation": False,
            },
        )
        try:
            self.conversation_state.record_agent_result(
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
        execution: SkillRuntimeResult,
        session_id: str | None,
        generation: int,
        provider_status: dict[str, Any] | None,
        recovery_confirmation_staged: bool,
        suppress_final_reason: str | None = None,
    ) -> str:
        closure = self._cognitive_turn_closure_adapter()
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
        goal_state_results: list[dict[str, Any]] = []
        try:
            goal_state_results = (
                self.conversation_state.record_execution_outcome_bundle(
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
        self.session_log(
            session_id,
            "cognitive_outcome_reconciled: outcome_id=%s aggregate=%s goals=%s evidence=%s",
            bundle.outcome_id,
            bundle.aggregate_status,
            len(bundle.goal_outcomes),
            len(bundle.evidence),
        )

        if self._outcome_response_is_stale(
            generation=generation,
            session_id=session_id,
        ):
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

        try:
            final_response = await self._compose_evidence_bound_tool_result_response(
                source_response=response,
                bundle=bundle,
                plan=plan,
                session_id=session_id,
            )
            if final_response is None:
                final_response = compose_outcome_response(
                    bundle,
                    plan,
                    str(response.metadata.get("language") or "en-US"),
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
                delivery_status="composition_failed",
                suppression_reason=type(exc).__name__,
                goal_state_results=goal_state_results,
            )
            return "composition_failed"

        delivery_status = await self._execute_cognitive_outcome_response(
            final_response,
            session_id=session_id,
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

    async def _compose_evidence_bound_tool_result_response(
        self,
        *,
        source_response: InteractionResponse,
        bundle: Any,
        plan: Any,
        session_id: str | None,
    ) -> InteractionResponse | None:
        """Ask the Agent to interpret bounded tool output before speaking it.

        Complete observations stay in the immutable ExecutionOutcomeBundle. The
        model receives only schema-validated ModelObservation data and selects
        exact fact pointers. The Host rechecks those pointers and correlations
        before accepting one concise spoken answer.
        """

        evidence: list[ToolResultEvidence] = []
        for item in bundle.evidence:
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
                    tool_id=item.skill_id,
                    status=item.status,
                    data=observation.data,
                    output_sha256=canonical_value_sha256(observation.data),
                )
            )
        if not evidence:
            return None

        metadata = source_response.metadata if isinstance(source_response.metadata, dict) else {}
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
            or (normalized_input.get("language") if isinstance(normalized_input, dict) else "")
            or "en-US"
        )
        interpretation_request = ToolResultInterpretationRequest(
            sid=str(session_id or ""),
            user_request=user_request,
            language=language,
            evidence=evidence,
            max_spoken_chars=96 if language.lower().startswith("zh") else 240,
            detailed_max_spoken_chars=320 if language.lower().startswith("zh") else 700,
            max_sentences=2,
            detailed_max_sentences=5,
            context={
                "aggregate_status": bundle.aggregate_status,
                "goal_statuses": [
                    {"goal_id": item.goal_id, "status": item.status}
                    for item in bundle.goal_outcomes
                ],
            },
        )
        try:
            session = await self.get_http_session()
            interpretation = await self.agent_client.interpret_tool_result(
                session,
                request=interpretation_request,
                timeout_ms=self.tool_result_interpreter_timeout_ms,
            )
        except Exception as exc:
            self.session_log(
                session_id,
                "tool_result_interpretation_failed: error_type=%s error=%s",
                type(exc).__name__,
                exc,
            )
            return None
        if interpretation.status not in {"resolved", "fallback"}:
            return None

        evidence_by_id = {item.evidence_id: item for item in evidence}
        for reference in interpretation.selected_facts:
            selected = evidence_by_id.get(reference.evidence_id)
            if selected is None:
                raise ValueError("tool result interpretation references unknown evidence")
            self._resolve_tool_result_pointer(selected.data, reference.json_pointer)

        fingerprint = str(bundle.outcome_id).replace(" ", "")[:12] or "result"
        goal_ids = list(plan.executable_goal_ids())
        status = (
            "ok"
            if bundle.aggregate_status == "completed"
            else "refused"
            if bundle.aggregate_status == "refused"
            else "error"
        )
        return InteractionResponse(
            interaction_id=bundle.interaction_id,
            status=status,
            speech=[
                InteractionSpeech(
                    id=f"speech_tool_result_{fingerprint}",
                    text=interpretation.spoken_response,
                    timing="immediate",
                    style="brief" if status == "ok" else "warning",
                    priority="normal",
                    interruptible=True,
                    metadata={
                        "source": "evidence_bound_tool_result_interpretation",
                        "phase": "post_execution",
                        "wait_for_playback_start": True,
                        "playback_start_required_for_delivery": True,
                        "covers_goal_ids": goal_ids,
                        "selected_facts": [
                            item.model_dump(mode="json")
                            for item in interpretation.selected_facts
                        ],
                        "answer_mode": interpretation.answer_mode,
                        "full_tool_result_retained": True,
                    },
                )
            ],
            skills=[],
            requires_confirmation=False,
            reason=(
                None
                if bundle.aggregate_status == "completed"
                else f"post_execution_{bundle.aggregate_status}"
            ),
            metadata={
                "source": "evidence_bound_tool_result_interpretation",
                "phase": "post_execution",
                "language": language,
                "canonical_plan_id": plan.plan_id,
                "canonical_plan_fingerprint": bundle.canonical_plan_fingerprint,
                "execution_outcome_bundle": bundle.model_dump(mode="json"),
                "aggregate_status": bundle.aggregate_status,
                "interpretation": interpretation.model_dump(mode="json"),
                "full_tool_result_retained": True,
            },
        )

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
        reserve = getattr(
            getattr(self, "interaction_runtime", None),
            "reserve_interaction",
            None,
        )
        release = getattr(
            getattr(self, "interaction_runtime", None),
            "release_interaction",
            None,
        )
        reserved = False
        if callable(reserve):
            reserve(response.interaction_id)
            reserved = True
        try:
            task = asyncio.create_task(
                self.execute_interaction_response(
                    response,
                    session_id,
                    confirmed_request_ids=confirmed_request_ids,
                    reset_playback=reset_playback,
                    mark_session_done=mark_session_done,
                )
            )
        except BaseException:
            if reserved and callable(release):
                release(response.interaction_id)
            raise
        active_tasks = getattr(self, "active_interaction_tasks", None)
        if not isinstance(active_tasks, dict):
            active_tasks = {}
            self.active_interaction_tasks = active_tasks
        active_tasks[task] = response.interaction_id
        if reserved:
            reservations = getattr(
                self,
                "active_interaction_reservations",
                None,
            )
            if not isinstance(reservations, dict):
                reservations = {}
                self.active_interaction_reservations = reservations
            reservations[task] = response.interaction_id
        self.active_interaction_task = task
        self.active_interaction_id = response.interaction_id
        task.add_done_callback(self._interaction_task_done)

    def _interaction_task_done(self, task: asyncio.Task) -> None:
        reservations = getattr(
            self,
            "active_interaction_reservations",
            None,
        )
        reserved_interaction_id = (
            reservations.pop(task, None)
            if isinstance(reservations, dict)
            else None
        )
        if reserved_interaction_id:
            release = getattr(
                getattr(self, "interaction_runtime", None),
                "release_interaction",
                None,
            )
            if callable(release):
                release(reserved_interaction_id)
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

    async def execute_interaction_response(
        self,
        response: InteractionResponse,
        session_id: str | None,
        *,
        confirmed_request_ids: set[str] | None = None,
        reset_playback: bool = True,
        mark_session_done: bool = True,
    ) -> SkillRuntimeResult:
        if reset_playback:
            await self.reset_playback_ordering()
        execution_generation = int(
            getattr(self, "playback_generation", 0)
        )
        started_ms = now_ms()
        has_soridormi_request = any(
            request.skill_id.startswith("soridormi.") for request in response.skills
        )
        execution: SkillRuntimeResult | None = None
        provider_status: dict[str, Any] | None = None
        cognitive_closure_attempted = False
        try:
            execution = await self.interaction_runtime.execute(
                response,
                session_id=session_id,
                confirmed_request_ids=confirmed_request_ids,
            )
            self.session_log(
                session_id,
                "skill_runtime_done: status=%s results=%s traces=%s provider_mode=%s runtime_ms=%.1f",
                execution.status,
                len(execution.results),
                len(execution.traces),
                getattr(self.interaction_runtime, "soridormi_mode", None) or "not-used",
                now_ms() - started_ms,
            )
            for result in execution.results:
                self.session_log(
                    session_id,
                    "skill_result: request_id=%s skill_id=%s status=%s reason=%s message=%s",
                    result.request_id,
                    result.skill_id,
                    result.status,
                    result.reason_code,
                    result.message,
                )
                self.conversation_state.update_pending_task_status_for_request_id(
                    request_id=result.request_id,
                    status=result.status,
                )
            if response.metadata.get(
                "history_after_successful_delivery"
            ) is True:
                self._record_successfully_delivered_speech(
                    response,
                    execution,
                    session_id=session_id,
                    log_event="interaction_history_after_delivery",
                )
            if has_soridormi_request:
                provider_status = await self._record_soridormi_post_status(
                    session_id
                )
            completed_request_ids = {result.request_id for result in execution.results}
            recovery_confirmation_staged = False
            if execution.status != "completed":
                is_cognitive_effectful = bool(
                    response.metadata.get("cognitive_runtime_apply") is True
                    and response.metadata.get("canonical_plan")
                    and response.skills
                )
                for request in response.skills:
                    if request.request_id in completed_request_ids:
                        continue
                    self.conversation_state.update_pending_task_status_for_request_id(
                        request_id=request.request_id,
                        status=(
                            "not_run"
                            if is_cognitive_effectful
                            else execution.status
                        ),
                    )
                for speech in response.speech:
                    if speech.id in completed_request_ids:
                        continue
                    self.conversation_state.update_pending_task_status_for_request_id(
                        request_id=speech.id,
                        status=execution.status,
                    )
                recovery_confirmation_staged = (
                    await self._maybe_stage_body_recovery_confirmation(
                        response,
                        execution,
                        session_id,
                    )
                )
            cognitive_closure_attempted = True
            closure_status = await self._close_cognitive_execution(
                response=response,
                execution=execution,
                session_id=session_id,
                generation=execution_generation,
                provider_status=provider_status,
                recovery_confirmation_staged=recovery_confirmation_staged,
            )
            if closure_status != "not_applicable":
                response.metadata["cognitive_turn_closure_status"] = (
                    closure_status
                )
            self._record_execution_experience_safely(
                response=response,
                execution=execution,
                session_id=session_id,
                confirmed_request_ids=confirmed_request_ids,
            )
            return execution
        except asyncio.CancelledError:
            self.session_log(
                session_id,
                "skill_runtime_cancelled: runtime_ms=%.1f",
                now_ms() - started_ms,
            )
            cancelled_execution = (
                self._cancelled_execution_with_unknown_request_results(
                    response,
                    execution,
                )
            )
            completed_by_request = {
                result.request_id: result
                for result in cancelled_execution.results
            }
            for request in response.skills:
                result = completed_by_request.get(request.request_id)
                self.conversation_state.update_pending_task_status_for_request_id(
                    request_id=request.request_id,
                    status=result.status if result is not None else "not_run",
                )
            for speech in response.speech:
                result = completed_by_request.get(speech.id)
                self.conversation_state.update_pending_task_status_for_request_id(
                    request_id=speech.id,
                    status=result.status if result is not None else "cancelled",
                )
            if has_soridormi_request:
                provider_status = await asyncio.shield(
                    self._record_soridormi_post_status(session_id)
                )

            try:
                cognitive_plan = (
                    self._cognitive_turn_closure_adapter().canonical_plan(
                        response
                    )
                )
            except Exception:
                cognitive_plan = None
            if cognitive_plan is not None:
                outcome_execution = cancelled_execution
                closure_status = await asyncio.shield(
                    self._close_cognitive_execution(
                        response=response,
                        execution=outcome_execution,
                        session_id=session_id,
                        generation=execution_generation,
                        provider_status=provider_status,
                        recovery_confirmation_staged=False,
                        # A stop/interruption must never emit a late terminal
                        # utterance, even if playback generation is unchanged
                        # in a synthetic or test caller.
                        suppress_final_reason="interaction_cancelled",
                    )
                )
                response.metadata["cognitive_turn_closure_status"] = (
                    closure_status
                )
                self._record_execution_experience_safely(
                    response=response,
                    execution=outcome_execution,
                    session_id=session_id,
                    confirmed_request_ids=confirmed_request_ids,
                    errors=["interaction_cancelled"],
                )
                return outcome_execution
            raise
        except Exception as exc:
            self.session_log(
                session_id,
                "skill_runtime_exception: runtime_ms=%.1f error=%s",
                now_ms() - started_ms,
                exc,
            )
            try:
                cognitive_plan = (
                    self._cognitive_turn_closure_adapter().canonical_plan(
                        response
                    )
                )
            except Exception:
                cognitive_plan = None
            if cognitive_plan is not None:
                outcome_execution = execution or SkillRuntimeResult(
                    interaction_id=response.interaction_id,
                    status="failed",
                )
                if execution is None and has_soridormi_request:
                    provider_status = (
                        await self._record_soridormi_post_status(session_id)
                    )
                if execution is None:
                    for request in response.skills:
                        self.conversation_state.update_pending_task_status_for_request_id(
                            request_id=request.request_id,
                            status="not_run",
                        )
                    for speech in response.speech:
                        self.conversation_state.update_pending_task_status_for_request_id(
                            request_id=speech.id,
                            status="failed",
                        )
                if cognitive_closure_attempted:
                    closure_status = str(
                        response.metadata.get(
                            "cognitive_turn_closure_status",
                            "closure_already_attempted",
                        )
                    )
                    response.metadata[
                        "cognitive_turn_closure_followup_error"
                    ] = type(exc).__name__
                else:
                    cognitive_closure_attempted = True
                    closure_status = await self._close_cognitive_execution(
                        response=response,
                        execution=outcome_execution,
                        session_id=session_id,
                        generation=execution_generation,
                        provider_status=provider_status,
                        recovery_confirmation_staged=False,
                    )
                response.metadata["cognitive_turn_closure_status"] = (
                    closure_status
                )
                self._record_execution_experience_safely(
                    response=response,
                    execution=outcome_execution,
                    session_id=session_id,
                    confirmed_request_ids=confirmed_request_ids,
                    errors=[str(exc) or exc.__class__.__name__],
                )
                return outcome_execution
            for request_id in [
                *(request.request_id for request in response.skills),
                *(speech.id for speech in response.speech),
            ]:
                self.conversation_state.update_pending_task_status_for_request_id(
                    request_id=request_id,
                    status="failed",
                )
            self._record_execution_experience_safely(
                response=response,
                execution=execution,
                session_id=session_id,
                confirmed_request_ids=confirmed_request_ids,
                errors=[str(exc) or exc.__class__.__name__],
            )
            raise
        finally:
            if mark_session_done:
                state = self.sessions.state.get(session_id or "")
                if state is not None:
                    state["llm_done"] = True
                    state["response_chars"] = state.get(
                        "response_chars",
                        0,
                    ) + sum(len(item.text) for item in response.speech)
                self.maybe_session_done(session_id)

    @staticmethod
    def _cancelled_execution_with_unknown_request_results(
        response: InteractionResponse,
        execution: SkillRuntimeResult | None,
    ) -> SkillRuntimeResult:
        """Conservatively retain cancellation when terminal evidence is lost.

        When cancellation propagates through a coordinator, the host cannot
        prove that a request with no returned result never started. Marking it
        ``not_run`` would be an unsafe assertion for physical work, so every
        committed request lacking terminal evidence is retained as cancelled
        with an explicit unknown-start diagnostic.
        """

        existing_results = list(execution.results if execution else [])
        existing_by_request = {
            result.request_id: result for result in existing_results
        }
        merged_results: list[SkillResult] = []
        committed_request_ids: set[str] = set()
        for request in response.skills:
            committed_request_ids.add(request.request_id)
            result = existing_by_request.get(request.request_id)
            if result is None:
                result = SkillResult(
                    request_id=request.request_id,
                    skill_id=request.skill_id,
                    skill_version=request.skill_version,
                    status="cancelled",
                    reason_code=(
                        "interaction_cancelled_terminal_result_unavailable"
                    ),
                    message=(
                        "Interaction cancellation propagated before terminal "
                        "per-request evidence was returned; start state is "
                        "unknown."
                    ),
                )
            merged_results.append(result)
        merged_results.extend(
            result
            for result in existing_results
            if result.request_id not in committed_request_ids
        )
        return SkillRuntimeResult(
            interaction_id=response.interaction_id,
            status="cancelled",
            results=merged_results,
            traces=list(execution.traces if execution else []),
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
        execution: SkillRuntimeResult,
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
                request.skill_id
                for request in recovery.response.skills
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
        prompt_execution = await self.interaction_runtime.execute(
            prompt_response,
            session_id=session_id,
        )
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

    async def execute_agent_result(
        self,
        result: AgentResult,
        session_id: str | None,
        *,
        reset_playback: bool = True,
    ) -> None:
        if reset_playback:
            await self.reset_playback_ordering()
        for item in result.speak_immediate:
            await self.schedule_tts_text(item.text, session_id)

        for graph in result.task_graphs:
            self.session_log(
                session_id,
                "task_graph_planned: graph_id=%s nodes=%s execution=disabled",
                graph.get("graph_id", "<missing>"),
                len(graph.get("nodes", [])),
            )

        session = await self.get_http_session()
        for action in result.actions:
            action_start_ms = now_ms()
            self.session_log(session_id, "action_start: id=%s target=%s type=%s blocking=%s dry_run=%s", action.id, action.target, action.type, action.blocking, self.action_dry_run)
            if action.requires_confirmation:
                self.session_log(
                    session_id,
                    "action_waiting_confirmation: id=%s target=%s type=%s",
                    action.id,
                    action.target,
                    action.type,
                )
                continue
            if self.action_dry_run:
                self.session_log(session_id, "action_dry_run: id=%s target=%s type=%s params=%s", action.id, action.target, action.type, action.params)
                continue
            try:
                res = await self.action_client.execute(session, action)
                self.session_log(session_id, "action_done: id=%s target=%s type=%s status=%s action_ms=%.1f message=%s", res.id, res.target, res.type, res.status, now_ms() - action_start_ms, res.message)
            except Exception as exc:
                self.session_log(session_id, "action_exception: id=%s target=%s type=%s action_ms=%.1f error=%s", action.id, action.target, action.type, now_ms() - action_start_ms, exc)
                logger.error("Action execution failed: %s", exc, exc_info=True)

        for item in result.speak_after:
            await self.schedule_tts_text(item.text, session_id)

        state = self.sessions.state.get(session_id or "")
        if state is not None:
            state["llm_done"] = True
            state["response_chars"] = state.get("response_chars", 0) + sum(len(i.text) for i in result.speak_immediate + result.speak_after)
        self.maybe_session_done(session_id)

    def _invalidate_output_state(
        self,
        *,
        cancel_cognitive_work: bool = True,
    ) -> None:
        self.playback_generation += 1
        self.resolve_all_playback_start_waiters(
            started=False,
            reason="interrupt",
        )
        # ``active_llm_task`` is the legacy direct speech-stream producer. It
        # must stop for every output interruption or it can enqueue fresh audio
        # after the queues below have been invalidated. The broader routed turn
        # is cancelled separately so output-only scope can preserve committed
        # Skill Runtime work.
        if self.active_llm_task and not self.active_llm_task.done():
            self.active_llm_task.cancel()
        current_task = asyncio.current_task()
        active_turn_task = getattr(self, "active_turn_task", None)
        active_reflex_task = getattr(self, "active_reflex_task", None)
        if (
            cancel_cognitive_work
            and active_turn_task is not None
            and active_turn_task is not current_task
            and active_turn_task is not active_reflex_task
            and not active_turn_task.done()
        ):
            active_turn_task.cancel()
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
        if scope == "global_emergency":
            host_scope_interaction_ids = tuple(
                sorted(
                    {
                        interaction_id
                        for _, interaction_id in active_host_interactions
                    }
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
                # Compatibility-only fallback for older injected runtimes.
                # It is intentionally broad only for broad scopes.
                if scope in {
                    "current_interaction",
                    "global_emergency",
                }:
                    cancel_all = getattr(
                        self.interaction_runtime,
                        "cancel_all",
                        None,
                    )
                    if callable(cancel_all):
                        runtime_operation_kind = "runtime_legacy"
                        phase_operations.append(
                            (runtime_operation_kind, cancel_all())
                        )
                    else:
                        dispatch_failures.append(
                            "skill_runtime:dispatch_unsupported"
                        )
                elif scope == "embodied_motion":
                    dispatch_failures.append(
                        "skill_runtime:scoped_dispatch_unsupported"
                    )

        if scope in {
            "output_only",
            "current_interaction",
            "global_emergency",
        }:
            try:
                self._invalidate_output_state(
                    cancel_cognitive_work=(scope != "output_only"),
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
                        "skill_runtime:"
                        f"{type(result).__name__}:{str(result)[:300]}"
                    )
                elif isinstance(result, CancellationDispatchReceipt):
                    receipt = result
                else:
                    dispatch_failures.append(
                        "skill_runtime:invalid_dispatch_receipt"
                    )
            elif operation_kind == "runtime_legacy":
                if isinstance(result, BaseException):
                    dispatch_failures.append(
                        "skill_runtime_legacy:"
                        f"{type(result).__name__}:{str(result)[:300]}"
                    )
                elif active_interaction_id:
                    receipt = receipt.model_copy(
                        update={
                            "interaction_ids": (
                                active_interaction_id,
                            )
                        }
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
                    cancel_cognitive_work=(scope != "output_only"),
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
            len(receipt.selected_request_ids),
            len(receipt.active_request_ids),
            len(receipt.queued_request_ids),
            len(receipt.non_interruptible_request_ids),
            len(receipt.provider_cancel_failures),
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
        tasks = set(
            task
            for task in getattr(
                self,
                "active_interaction_tasks",
                {},
            )
            if not task.done()
        )
        active = getattr(self, "active_interaction_task", None)
        if active is not None and not active.done():
            tasks.add(active)
        for task in tasks:
            task.cancel()
        await self.interaction_runtime.cancel_all()
        if new_session_id:
            self.session_log(new_session_id, "interrupt_previous_audio_done: playback_generation=%s", self.playback_generation)

    def mic_callback(self, indata, frames, time_info, status):
        if status:
            logger.warning("Microphone status: %s", status)
        if self.loop is None:
            return
        audio = indata.copy()

        def enqueue_audio():
            if self.mic_queue.full():
                try:
                    self.mic_queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                self.mic_queue.put_nowait(audio)
            except asyncio.QueueFull:
                pass

        self.loop.call_soon_threadsafe(enqueue_audio)

    async def handle_vad_audio(self, audio: bytes):
        duration_ms = (len(audio) / (self.target_asr_rate * 2)) * 1000.0
        duration = duration_ms / 1000.0
        rms = float(np.sqrt(np.mean(np.square(np.frombuffer(audio, dtype=np.int16).astype(np.float32))))) if audio else 0.0
        if duration_ms >= self.max_vad_utterance_ms:
            logger.warning(
                "VAD speech ended but discarded at hard maximum: duration=%.2fs max_audio_ms=%s",
                duration,
                self.max_vad_utterance_ms,
            )
            return
        if duration_ms < self.min_audio_ms:
            logger.warning("VAD speech ended but skipped: duration=%.2fs min_audio_ms=%s", duration, self.min_audio_ms)
            return
        effective_min_rms = self.barge_in_min_rms if self.is_playing_audio else self.min_rms
        if rms < effective_min_rms:
            logger.warning("VAD speech ended but skipped: duration=%.2fs RMS=%.1f min_rms=%.1f playing=%s", duration, rms, effective_min_rms, self.is_playing_audio)
            return

        session_id = self.create_session()
        with self.sessions.trace_context(session_id):
            runtime_tracer.mark(
                module=VAD_TRACE_MODULE,
                name="vad_validated",
                kind="audio_input",
                attributes={
                    "audio_duration_ms": round(duration_ms, 3),
                    "audio_bytes": len(audio),
                    "rms": round(rms, 3),
                    "playing_audio": bool(self.is_playing_audio),
                },
            )
            self.session_log(session_id, "vad_valid_end: audio=%.2fs rms=%.1f bytes=%s", duration, rms, len(audio))
            self.save_audio(audio, "input", session_id=session_id)
            # Barge-in must silence audio immediately, before ASR is available,
            # but it cannot yet know whether the utterance means stop talking,
            # stop moving, cancel the foreground turn, or something ordinary.
            # Scope-dependent cognitive/runtime cancellation happens only after
            # the transcript reaches the Cognitive Gateway.
            self._invalidate_output_state(
                cancel_cognitive_work=False,
            )
            self._schedule_output_abort(
                new_session_id=session_id,
                log_event=True,
            )

            try:
                async with runtime_tracer.span(
                    module=ASR_TRACE_MODULE,
                    operation="transcribe",
                    kind="model_call",
                    attributes={
                        "audio_duration_ms": round(duration_ms, 3),
                        "audio_bytes": len(audio),
                        "timeout_ms": round(self.asr_timeout_s * 1000.0, 3),
                    },
                ) as asr_span:
                    if self.asr_ws is None or getattr(self.asr_ws, "close_code", None) is not None:
                        reconnect_start_ms = now_ms()
                        await self.connect_services()
                        reconnect_ms = now_ms() - reconnect_start_ms
                        asr_span.set_attribute("reconnect_ms", round(reconnect_ms, 3))
                        self.session_log(session_id, "asr_reconnect_done: reconnect_ms=%.1f", reconnect_ms)

                    asr_start_ms = now_ms()
                    self.session_log(session_id, "asr_send_start: audio_ms=%.1f bytes=%s", duration_ms, len(audio))
                    await self.asr_ws.send(audio)
                    send_ms = now_ms() - asr_start_ms
                    asr_span.set_attribute("send_ms", round(send_ms, 3))
                    self.session_log(session_id, "asr_send_done: send_ms=%.1f", send_ms)
                    resp = await asyncio.wait_for(self.asr_ws.recv(), timeout=self.asr_timeout_s)
                    asr_done_ms = now_ms()
                    result = json.loads(resp)
                    asr_span.set_attribute("result_type", str(result.get("type") or "unknown"))
                    if result.get("type") == "error":
                        asr_span.set_status("error")
                        self.session_log(session_id, "asr_error: asr_ms=%.1f error=%s", asr_done_ms - asr_start_ms, result)
                        return
                    if result.get("type") == "final":
                        user_text = result.get("text", "").strip()
                        asr_span.set_attribute("text_chars", len(user_text))
                        runtime_tracer.mark(
                            module=ASR_TRACE_MODULE,
                            name="asr_final_available",
                            kind="milestone",
                            attributes={"text_chars": len(user_text)},
                        )
                        self.session_log(session_id, "asr_final: asr_ms=%.1f text_chars=%s text=%r", asr_done_ms - asr_start_ms, len(user_text), user_text)
                        if user_text:
                            self._launch_routed_turn(user_text, session_id)
                        else:
                            self.session_log(session_id, "asr_empty_text")
            except Exception as exc:
                self.session_log(session_id, "asr_exception: error=%s", exc)
                logger.error("%s ASR error: %s", session_id, exc, exc_info=True)
                try:
                    if self.asr_ws:
                        await self.asr_ws.close()
                except Exception:
                    pass
                self.asr_ws = None

    def _has_active_protective_reflex(
        self,
        *,
        excluding: asyncio.Task | None = None,
    ) -> bool:
        primary = getattr(self, "active_reflex_task", None)
        if primary is not None and primary is not excluding:
            return True
        return any(
            task is not excluding
            for task in getattr(
                self,
                "concurrent_protective_reflex_tasks",
                set(),
            )
        )

    def _launch_routed_turn(self, user_text: str, session_id: str) -> None:
        reflex_candidate = DEFAULT_REFLEX_FILTER.evaluate(user_text)
        if self._has_active_protective_reflex():
            if reflex_candidate.action == "interrupt":
                # A new deterministic protective input is independent of an
                # older protective operation. It must not wait behind output
                # cleanup or provider I/O, and an ordinary queued turn must
                # never be able to replace it.
                task = asyncio.create_task(
                    self.handle_routed_text(user_text, session_id)
                )
                tasks = getattr(
                    self,
                    "concurrent_protective_reflex_tasks",
                    None,
                )
                if not isinstance(tasks, set):
                    tasks = set()
                    self.concurrent_protective_reflex_tasks = tasks
                tasks.add(task)

                def protective_done(completed: asyncio.Task) -> None:
                    tasks.discard(completed)
                    self._on_routed_turn_done(
                        completed,
                        session_id,
                        concurrent_reflex=True,
                    )

                task.add_done_callback(protective_done)
                self.session_log(
                    session_id,
                    "protective_reflex_launched_concurrently: scope=%s",
                    reflex_candidate.cancellation_scope,
                )
                return
            replaced = getattr(self, "_pending_turn_after_reflex", None)
            if replaced is not None:
                _, replaced_session_id = replaced
                self.session_log(
                    replaced_session_id,
                    "turn_replaced_while_reflex_active: replacement_sid=%s",
                    session_id,
                )
                state = self.sessions.state.get(replaced_session_id)
                if state is not None:
                    state["llm_done"] = True
                self.maybe_session_done(replaced_session_id)
            self._pending_turn_after_reflex = (user_text, session_id)
            self.session_log(
                session_id,
                "turn_queued_behind_cognitive_gateway_reflex: replaced=%s",
                replaced is not None,
            )
            return

        previous = getattr(self, "active_turn_task", None)
        if previous is not None and not previous.done():
            previous.cancel()
        task = asyncio.create_task(self.handle_routed_text(user_text, session_id))
        self.active_turn_task = task
        if reflex_candidate.action == "interrupt":
            # Mark the task at launch time so a following utterance cannot
            # cancel it before the coroutine reaches its first instruction.
            self.active_reflex_task = task
            self._protective_reflex_failure = False
        task.add_done_callback(
            lambda completed, sid=session_id: self._on_routed_turn_done(
                completed,
                sid,
            )
        )

    def _on_routed_turn_done(
        self,
        task: asyncio.Task,
        session_id: str,
        *,
        concurrent_reflex: bool = False,
    ) -> None:
        was_primary_reflex = (
            getattr(self, "active_reflex_task", None) is task
        )
        was_concurrent_reflex = concurrent_reflex or task in getattr(
            self,
            "concurrent_protective_reflex_tasks",
            set(),
        )
        was_reflex = was_primary_reflex or was_concurrent_reflex
        if getattr(self, "active_turn_task", None) is task:
            self.active_turn_task = None
        completed_ok = False
        if task.cancelled():
            self.session_log(session_id, "turn_cancelled_by_new_session")
            state = self.sessions.state.get(session_id)
            if state is not None:
                state["llm_done"] = True
            self.maybe_session_done(session_id)
        else:
            try:
                task.result()
                completed_ok = True
            except Exception as exc:  # pragma: no cover - defensive callback logging
                logger.error(
                    "%s routed turn failed outside normal handler: %s",
                    session_id,
                    exc,
                    exc_info=True,
                )

        if not was_reflex:
            return
        if not completed_ok:
            self._protective_reflex_failure = True
        if was_primary_reflex:
            self.active_reflex_task = None
        if self._has_active_protective_reflex():
            return
        pending = getattr(self, "_pending_turn_after_reflex", None)
        self._pending_turn_after_reflex = None
        protective_failed = bool(
            getattr(self, "_protective_reflex_failure", False)
        )
        self._protective_reflex_failure = False
        if pending is None:
            return
        pending_text, pending_session_id = pending
        if not protective_failed:
            self.session_log(
                pending_session_id,
                "turn_released_after_cognitive_gateway_reflex",
            )
            self._launch_routed_turn(pending_text, pending_session_id)
            return
        self.session_log(
            pending_session_id,
            "turn_dropped_after_failed_cognitive_gateway_reflex",
        )
        state = self.sessions.state.get(pending_session_id)
        if state is not None:
            state["llm_done"] = True
        self.maybe_session_done(pending_session_id)

    def _queue_vad_utterance(self, audio: bytes) -> None:
        active = getattr(self, "active_asr_task", None)
        if active is not None and not active.done():
            replaced = getattr(self, "_pending_vad_audio", None) is not None
            self._pending_vad_audio = audio
            logger.info(
                "ASR is processing; queued latest utterance%s",
                " and replaced older pending audio" if replaced else "",
            )
            return
        task = asyncio.create_task(self.handle_vad_audio(audio))
        self.active_asr_task = task
        task.add_done_callback(self._on_asr_task_done)

    def _on_asr_task_done(self, task: asyncio.Task) -> None:
        if getattr(self, "active_asr_task", None) is task:
            self.active_asr_task = None
        if not task.cancelled():
            try:
                task.result()
            except Exception as exc:  # pragma: no cover - handle_vad_audio logs normally
                logger.error("ASR task failed: %s", exc, exc_info=True)
        pending = getattr(self, "_pending_vad_audio", None)
        self._pending_vad_audio = None
        if pending:
            self._queue_vad_utterance(pending)

    async def _feed_vad_pcm16(self, pcm_16k: bytes) -> None:
        frame_bytes_target = int(
            self.target_asr_rate * self.frame_duration_ms / 1000
        ) * 2
        buffered = self._vad_leftover + pcm_16k
        offset = 0
        while offset + frame_bytes_target <= len(buffered):
            frame = buffered[offset : offset + frame_bytes_target]
            offset += frame_bytes_target
            started, ended, vad_audio = self.vad.process_chunk(frame)
            if started:
                logger.info("VAD detected voice")
            if ended and vad_audio:
                if getattr(self.vad, "last_end_reason", None) == "max_duration":
                    logger.warning(
                        "VAD force-closed and discarded an overlong utterance: duration_limit_ms=%s bytes=%s",
                        self.max_vad_utterance_ms,
                        len(vad_audio),
                    )
                else:
                    self._queue_vad_utterance(vad_audio)
        self._vad_leftover = buffered[offset:]
        await asyncio.sleep(0)

    async def mic_stream(self):
        logger.info("Opening microphone with sounddevice")
        self.loop = asyncio.get_running_loop()
        sd = _sounddevice()
        with sd.InputStream(
            samplerate=self.input_rate,
            channels=self.input_channels,
            dtype="float32",
            blocksize=self.input_block_size,
            device=self.input_device,
            latency=self.input_latency,
            callback=self.mic_callback,
        ):
            logger.info("Microphone started")
            logger.info("Audio input started: mode=device")
            while True:
                audio = await self.mic_queue.get()
                pcm_16k = self.prepare_mic_chunk_for_asr(audio)
                await self._feed_vad_pcm16(pcm_16k)

    async def injected_audio_stream(self):
        """Consume framed PCM16 utterances from stdin for acceptance testing.

        The binary framing is intentionally available only through inherited
        stdin. It does not open a network control port in normal operation.
        Each packet is treated as microphone input and still passes through
        Chromie's VAD and ASR path.
        """

        logger.info("Audio input started: mode=stdin protocol=CAUD/v1")
        while True:
            packet = await asyncio.to_thread(read_audio_packet, sys.stdin.buffer)
            if packet is None:
                logger.info("Injected audio input reached EOF")
                return
            samples = np.frombuffer(packet.pcm16, dtype=np.int16)
            if packet.channels > 1:
                samples = samples.reshape(-1, packet.channels).mean(axis=1).astype(
                    np.int16
                )
            pcm = samples.astype(np.int16, copy=False).tobytes()
            pcm_16k = self.resample_int16_bytes(
                pcm,
                packet.sample_rate,
                self.target_asr_rate,
            )
            duration_ms = len(pcm_16k) / (self.target_asr_rate * 2) * 1000.0
            logger.info(
                "Injected audio received: source_rate=%s channels=%s bytes=%s "
                "resampled_ms=%.1f",
                packet.sample_rate,
                packet.channels,
                len(packet.pcm16),
                duration_ms,
            )
            await self._feed_vad_pcm16(pcm_16k)
            # Ensure the VAD sees enough trailing silence to close the utterance.
            silence_ms = max(
                900,
                int(os.getenv("ORCH_VAD_SILENCE_MS", "650")) + 150,
            )
            silence = b"\x00\x00" * int(
                self.target_asr_rate * silence_ms / 1000
            )
            await self._feed_vad_pcm16(silence)

    async def _session_idle_sweeper(self) -> None:
        interval_s = max(1.0, float(os.getenv("ORCH_SESSION_IDLE_SWEEP_S", "5")))
        idle_timeout_ms = max(1000.0, float(os.getenv("ORCH_SESSION_IDLE_TIMEOUT_MS", "120000")))
        loop = asyncio.get_running_loop()
        expected_wake = loop.time() + interval_s
        while True:
            await asyncio.sleep(interval_s)
            actual_wake = loop.time()
            event_loop_lag_ms = max(0.0, (actual_wake - expected_wake) * 1000.0)
            expected_wake = actual_wake + interval_s
            self.sessions.sample_active_resources(
                event_loop_lag_ms=event_loop_lag_ms,
                attributes={
                    "playback_queue_depth": self.playback_queue.qsize(),
                    "mic_queue_depth": self.mic_queue.qsize(),
                    "active_synthesis_tasks": len(self.active_synthesis_tasks),
                },
            )
            await self._sample_accelerator_resources(reason="periodic")
            self.sessions.checkpoint_active_traces()
            self.sessions.finalize_idle_sessions(idle_timeout_ms=idle_timeout_ms)

    async def _prime_fast_first_audio(self) -> dict[str, int]:
        fast_first_cache = getattr(self, "fast_first_audio_cache", None)
        if fast_first_cache is None or not fast_first_cache.enabled:
            return {"loaded": 0, "generated": 0, "failed": 0}
        prime_started_ms = now_ms()
        try:
            stats = await asyncio.wait_for(
                fast_first_cache.prime_missing(
                    tts_url=self.tts_url,
                    speaker_id=self.speaker_id,
                    asr_url=self.asr_url,
                    asr_sample_rate=self.target_asr_rate,
                ),
                timeout=self.fast_first_audio_prime_timeout_ms / 1000.0,
            )
        except asyncio.TimeoutError:
            stats = {"loaded": fast_first_cache.ready_count, "generated": 0, "failed": 1}
            logger.warning(
                "Fast-first audio cache priming exceeded total timeout_ms=%s; "
                "continuing with ready=%s",
                self.fast_first_audio_prime_timeout_ms,
                fast_first_cache.ready_count,
            )
        logger.info(
            "Fast-first audio cache ready=%s loaded=%s generated=%s failed=%s ms=%.1f",
            fast_first_cache.ready_count,
            stats.get("loaded", 0),
            stats.get("generated", 0),
            stats.get("failed", 0),
            now_ms() - prime_started_ms,
        )
        return stats

    async def run(self):
        gate = ServiceReadinessGate(
            asr_url=self.asr_url,
            tts_url=self.tts_url,
            llm_url=self.llm_url,
            ollama_model=self.ollama_model,
            speaker_id=self.speaker_id,
            get_http_session=self.get_http_session,
            router_url=self.router_url,
            agent_url=self.agent_url,
            enable_router=self.enable_router,
            enable_agent=self.enable_agent,
        )
        self.asr_ws = await gate.wait_until_ready()
        await self._prime_fast_first_audio()
        self.playback_task = asyncio.create_task(self.playback_worker())
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
        if self.active_llm_task and not self.active_llm_task.done():
            self.active_llm_task.cancel()
        for task in list(self.active_synthesis_tasks):
            task.cancel()
        if self.active_asr_task and not self.active_asr_task.done():
            self.active_asr_task.cancel()
        if self.active_turn_task and not self.active_turn_task.done():
            self.active_turn_task.cancel()
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
        self._pending_turn_after_reflex = None
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
