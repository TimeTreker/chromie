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
from orchestrator.runtime.response_plan import validate_immediate_response_plan
from orchestrator.runtime.session import SessionTracker, now_ms
from orchestrator.runtime.skill_runtime import SkillRuntimeResult
from orchestrator.schemas.agent import AgentResult, SpeechItem
from orchestrator.schemas.route import RouteDecision
from shared.chromie_contracts.interaction import InteractionResponse, SkillRequest
from shared.chromie_runtime.llm_diagnostics import (
    ollama_completion_diagnostics,
    ollama_prompt_preflight_diagnostics,
)

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="[%(levelname)s] %(asctime)s - %(threadName)s - %(funcName)s - %(message)s",
)
logger = logging.getLogger("chromie-orchestrator")


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
            True,
        )
        self.fast_first_response_enabled = env_bool(
            "ORCH_FAST_FIRST_RESPONSE_ENABLED",
            True,
        )
        self.fast_first_tool_response_enabled = env_bool(
            "ORCH_FAST_FIRST_TOOL_RESPONSE_ENABLED",
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
        )
        self.fast_planner_mode = os.getenv("ORCH_FAST_PLANNER_MODE", "off").strip().lower()
        if self.fast_planner_mode not in {"off", "report_only"}:
            raise ValueError("ORCH_FAST_PLANNER_MODE must be off or report_only")
        self.fast_planner_timeout_ms = env_int("ORCH_FAST_PLANNER_TIMEOUT_MS", 3000, minimum=100)
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
        self.router_client = RouterClient(self.router_url, int(os.getenv("ORCH_ROUTER_TIMEOUT_MS", "3000")))
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
        self.sessions = SessionTracker(enabled=self.enable_session_timing)
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
        self.task_continuity_report_tasks: set[asyncio.Task] = set()
        self.goal_association_report_tasks: set[asyncio.Task] = set()
        self.fast_planner_report_tasks: set[asyncio.Task] = set()
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
            "Control plane: router=%s enabled=%s agent=%s enabled=%s action_url=%s dry_run=%s task_continuity_mode=%s",
            self.router_url,
            self.enable_router,
            self.agent_url,
            self.enable_agent,
            self.action_executor_url,
            self.action_dry_run,
            self.task_continuity_mode,
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
            soridormi_invoker=soridormi_invoker,
            task_graph_handler=self._execute_planning_task_graph,
            auto_confirm_sim=self.auto_confirm_sim_skills,
        )
        logger.info(
            "Interaction runtime: endpoint=%s soridormi_skills=%s auto_confirm_sim=%s "
            "confirmation_ttl_s=%.1f fast_first_response=%s fast_first_tool=%s "
            "fast_first_audio=%s hedge_ms=%s cache_dir=%s",
            self.enable_interaction_response,
            self.enable_soridormi_skills,
            self.auto_confirm_sim_skills,
            self.confirmation_dialogue.ttl_s,
            self.fast_first_response_enabled,
            self.fast_first_tool_response_enabled,
            self.fast_first_audio_cache.enabled,
            self.fast_first_audio_hedge_ms,
            self.fast_first_audio_cache.cache_dir,
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
            return await asyncio.wait_for(waiter, timeout=timeout_s)
        except TimeoutError:
            self.playback_start_waiters.pop(key, None)
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
        return self.sessions.create()

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
                try:
                    self.output_stream.abort()
                except Exception as exc:
                    logger.warning("Failed to abort output stream: %s", exc)
                try:
                    self.output_stream.close()
                except Exception as exc:
                    logger.warning("Failed to close output stream after abort: %s", exc)
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
                                self.session_log(session_id, "tts_stream_start: order=%s attempt=%s/%s source_rate=%s output_rate=%s generation=%s", order, attempt, max_attempts, source_rate, self.output_rate, generation)
                                continue
                            if msg_type == "error":
                                self.session_log(session_id, "tts_error: order=%s attempt=%s/%s tts_ms=%.1f error=%s", order, attempt, max_attempts, now_ms() - tts_start_ms, data.get("message"))
                                await self.enqueue_playback_skip(generation, order, session_id, "tts_error")
                                self.maybe_session_done(session_id)
                                return
                            if msg_type == "end":
                                self.session_log(session_id, "tts_stream_end: order=%s attempt=%s/%s tts_ms=%.1f bytes=%s source_rate=%s generation=%s", order, attempt, max_attempts, now_ms() - tts_start_ms, len(audio_buffer), source_rate, generation)
                                self.session_log(
                                    session_id,
                                    "tts_server_metrics: order=%s audio_s=%.3f generate_s=%.3f model_s=%.3f codec_s=%.3f pcm_s=%.3f queue_s=%.3f rtf=%s codec_device=%s quantization=%s context=%s prompt_tokens=%s generated_tokens=%s headroom=%s limit_reached=%s",
                                    order,
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
        return scheduled

    def ensure_playback_worker(self) -> None:
        if not hasattr(self, "playback_queue"):
            return
        playback_task = getattr(self, "playback_task", None)
        if playback_task is None or playback_task.done():
            self.playback_task = asyncio.create_task(self.playback_worker())

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
            "keep_alive": os.getenv("OLLAMA_KEEP_ALIVE", "30m"),
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
            self.session_log(
                session_id,
                "episode_recorded: episode_id=%s conversation_id=%s turns=%s",
                episode.episode_id,
                episode.conversation_id,
                len(episode.turns),
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
        if decision.speak_first:
            return decision.speak_first.strip() or None

        abilities = self._ability_registry()
        if not abilities.can_execute("speech.thinking_ack"):
            return None
        return abilities.localized_speech(
            "speech.thinking_ack",
            language=decision.language,
            user_text=user_text,
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
        return cleaned

    def _router_fast_speech_diagnostics(self, decision: RouteDecision) -> dict[str, Any]:
        top_raw = self._fast_speech_payload_text(getattr(decision, "fast_speech", None))
        top_safe = self._safe_immediate_route_speech(top_raw)
        item_raw_count = 0
        item_safe_count = 0
        direct_item_count = 0
        for item in self._route_item_dicts(decision):
            item_raw = self._fast_speech_payload_text(item.get("fast_speech"))
            if item_raw:
                item_raw_count += 1
                if self._safe_immediate_route_speech(item_raw):
                    item_safe_count += 1
            if str(item.get("lane") or "") in {"immediate_speech", "fast_tts"} and item.get("direct_to_tts") is True:
                direct_item_count += 1
        speak_first_raw = " ".join((decision.speak_first or "").split())
        speak_first_safe = self._safe_immediate_route_speech(speak_first_raw)
        return {
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
        text = self._safe_immediate_route_speech(
            self._fast_speech_payload_text(getattr(decision, "fast_speech", None))
        )
        if text:
            return text

        for item in self._route_item_dicts(decision):
            item_fast = self._safe_immediate_route_speech(
                self._fast_speech_payload_text(item.get("fast_speech"))
            )
            if item_fast:
                return item_fast
            if str(item.get("lane") or "") not in {"immediate_speech", "fast_tts"}:
                continue
            if item.get("direct_to_tts") is not True:
                continue
            item_text = self._safe_immediate_route_speech(str(item.get("text") or ""))
            if item_text:
                return item_text
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

        # Backward compatibility for validators that still populate speak_first
        # directly, such as low-information clarification and low-confidence
        # deep-thought handoff. This text still goes through the same safety
        # filter and should remain a prelude, not a result or completion claim.
        speak_first = self._safe_immediate_route_speech(decision.speak_first)
        if speak_first:
            return speak_first

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

    async def handle_routed_text(self, user_text: str, session_id: str) -> None:
        if await self._handle_confirmation_reply(user_text, session_id):
            return

        boundary = self.conversation_state.prepare_for_user_text(user_text, session_id)
        if boundary.get("started_new"):
            self.session_log(
                session_id,
                "conversation_boundary: started_new=True conversation_id=%s reason=%s",
                boundary.get("conversation_id"),
                boundary.get("reason"),
            )

        if not self.enable_router:
            self.conversation_state.record_user_turn(
                session_id,
                user_text,
                route="direct_llm",
                intent="unknown",
                metadata={"source": "router_disabled"},
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
        self.session_log(
            session_id,
            "context_snapshot: conversation_id=%s history_turns=%s pending_tasks=%s",
            context.get("conversation_id"),
            len(context.get("history", [])),
            len(context.get("active_pending_tasks", [])),
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
            if safe_response is not None:
                self.conversation_state.record_user_turn(
                    session_id,
                    user_text,
                    route="safe_fallback",
                    intent="router_exception_embodied",
                    metadata={"source": "router_exception", "error": str(exc)},
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
                metadata={"source": "router_exception", "error": str(exc)},
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

        decision = self._apply_conditional_deepthinking_policy(
            decision,
            context=context,
            session_id=session_id,
        )
        decision = self._schedule_goal_association_report(
            session,
            user_text=user_text,
            session_id=session_id,
            context=context,
            decision=decision,
        )
        decision = self._schedule_fast_planner_report(
            session, user_text=user_text, session_id=session_id, context=context, decision=decision
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
        fast_first_scheduled = False
        await self._launch_deep_thought_body_cue(
            decision,
            user_text,
            session_id,
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
                    context=context,
                    history=context.get("history", []),
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
                        "cancellable=%s requires_confirmation=%s",
                        request.request_id,
                        request.skill_id,
                        request.timing,
                        request.cancellable,
                        request.requires_confirmation,
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
                context=context,
                history=context.get("history", []),
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
    ) -> None:
        fast_first_scheduled = False
        if decision.speak_first:
            fast_first_scheduled = await self._schedule_fast_first_response(
                decision,
                user_text,
                session_id,
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
                    context=context,
                    history=context.get("history", []),
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
                context=context,
                history=context.get("history", []),
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
        self.conversation_state.record_agent_result(
            session_id,
            prompt_response,
        )
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
            metadata={
                "confirmation_id": resolution.confirmation_id,
                "fingerprint": resolution.fingerprint,
            },
        )
        self.session_log(
            session_id,
            "confirmation_reply: confirmation_id=%s decision=%s fingerprint=%s",
            resolution.confirmation_id,
            resolution.decision,
            resolution.fingerprint,
        )
        if resolution.confirmation_id:
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
                    "metadata": {"source": source},
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

    def _launch_interaction(
        self,
        response: InteractionResponse,
        session_id: str | None,
        *,
        confirmed_request_ids: set[str] | None = None,
        reset_playback: bool = True,
        mark_session_done: bool = True,
    ) -> None:
        task = asyncio.create_task(
            self.execute_interaction_response(
                response,
                session_id,
                confirmed_request_ids=confirmed_request_ids,
                reset_playback=reset_playback,
                mark_session_done=mark_session_done,
            )
        )
        self.active_interaction_task = task
        task.add_done_callback(self._interaction_task_done)

    def _interaction_task_done(self, task: asyncio.Task) -> None:
        if self.active_interaction_task is task:
            self.active_interaction_task = None
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
        started_ms = now_ms()
        try:
            execution = await self.interaction_runtime.execute(
                response,
                session_id=session_id,
                confirmed_request_ids=confirmed_request_ids,
            )
            self.session_log(
                session_id,
                "skill_runtime_done: status=%s results=%s traces=%s runtime_ms=%.1f",
                execution.status,
                len(execution.results),
                len(execution.traces),
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
            completed_request_ids = {result.request_id for result in execution.results}
            if execution.status != "completed":
                for request in response.skills:
                    if request.request_id in completed_request_ids:
                        continue
                    self.conversation_state.update_pending_task_status_for_request_id(
                        request_id=request.request_id,
                        status=execution.status,
                    )
                await self._maybe_stage_body_recovery_confirmation(
                    response,
                    execution,
                    session_id,
                )
            self._record_experience(
                response=self._prepared_interaction_response_for_record(
                    response,
                    session_id=session_id,
                    confirmed_request_ids=confirmed_request_ids,
                ),
                execution=execution,
                session_id=session_id,
            )
            return execution
        except asyncio.CancelledError:
            self.session_log(
                session_id,
                "skill_runtime_cancelled: runtime_ms=%.1f",
                now_ms() - started_ms,
            )
            raise
        except Exception as exc:
            self.session_log(
                session_id,
                "skill_runtime_exception: runtime_ms=%.1f error=%s",
                now_ms() - started_ms,
                exc,
            )
            self._record_experience(
                response=self._prepared_interaction_response_for_record(
                    response,
                    session_id=session_id,
                    confirmed_request_ids=confirmed_request_ids,
                ),
                execution=None,
                session_id=session_id,
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
        self.conversation_state.record_agent_result(
            session_id,
            recovery.response,
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
        self.conversation_state.record_agent_result(session_id, prompt_response)
        await self.interaction_runtime.execute(
            prompt_response,
            session_id=session_id,
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

    async def interrupt_output(
        self,
        new_session_id: Optional[str] = None,
        *,
        log_event: bool = True,
    ):
        self.playback_generation += 1
        self.resolve_all_playback_start_waiters(
            started=False,
            reason="interrupt",
        )
        if self.active_llm_task and not self.active_llm_task.done():
            self.active_llm_task.cancel()
        current_task = asyncio.current_task()
        active_turn_task = getattr(self, "active_turn_task", None)
        if (
            active_turn_task is not None
            and active_turn_task is not current_task
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
        await self.abort_output_stream()
        if new_session_id and log_event:
            self.session_log(new_session_id, "interrupt_previous_audio_done: playback_generation=%s", self.playback_generation)

    async def interrupt(self, new_session_id: Optional[str] = None):
        await self.interrupt_output(new_session_id, log_event=False)
        if self.active_interaction_task and not self.active_interaction_task.done():
            self.active_interaction_task.cancel()
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
        self.session_log(session_id, "vad_valid_end: audio=%.2fs rms=%.1f bytes=%s", duration, rms, len(audio))
        self.save_audio(audio, "input", session_id=session_id)
        await self.interrupt_output(new_session_id=session_id)

        try:
            if self.asr_ws is None or getattr(self.asr_ws, "close_code", None) is not None:
                reconnect_start_ms = now_ms()
                await self.connect_services()
                self.session_log(session_id, "asr_reconnect_done: reconnect_ms=%.1f", now_ms() - reconnect_start_ms)

            asr_start_ms = now_ms()
            self.session_log(session_id, "asr_send_start: audio_ms=%.1f bytes=%s", duration_ms, len(audio))
            await self.asr_ws.send(audio)
            self.session_log(session_id, "asr_send_done: send_ms=%.1f", now_ms() - asr_start_ms)
            resp = await asyncio.wait_for(self.asr_ws.recv(), timeout=self.asr_timeout_s)
            asr_done_ms = now_ms()
            result = json.loads(resp)
            if result.get("type") == "error":
                self.session_log(session_id, "asr_error: asr_ms=%.1f error=%s", asr_done_ms - asr_start_ms, result)
                return
            if result.get("type") == "final":
                user_text = result.get("text", "").strip()
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

    def _launch_routed_turn(self, user_text: str, session_id: str) -> None:
        previous = getattr(self, "active_turn_task", None)
        if previous is not None and not previous.done():
            previous.cancel()
        task = asyncio.create_task(self.handle_routed_text(user_text, session_id))
        self.active_turn_task = task
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
    ) -> None:
        if getattr(self, "active_turn_task", None) is task:
            self.active_turn_task = None
        if task.cancelled():
            self.session_log(session_id, "turn_cancelled_by_new_session")
            state = self.sessions.state.get(session_id)
            if state is not None:
                state["llm_done"] = True
            self.maybe_session_done(session_id)
            return
        try:
            task.result()
        except Exception as exc:  # pragma: no cover - defensive callback logging
            logger.error(
                "%s routed turn failed outside normal handler: %s",
                session_id,
                exc,
                exc_info=True,
            )

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
        fast_first_cache = getattr(self, "fast_first_audio_cache", None)
        if fast_first_cache is not None and fast_first_cache.enabled:
            prime_started_ms = now_ms()
            try:
                stats = await asyncio.wait_for(
                    fast_first_cache.prime_missing(
                        tts_url=self.tts_url,
                        speaker_id=self.speaker_id,
                    ),
                    timeout=self.fast_first_audio_prime_timeout_ms / 1000.0,
                )
            except TimeoutError:
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
        self.playback_task = asyncio.create_task(self.playback_worker())
        if self.audio_input_mode == "stdin":
            await self.injected_audio_stream()
        else:
            await self.mic_stream()

    async def cleanup(self):
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
        self._pending_vad_audio = None
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
    asyncio.run(main())
