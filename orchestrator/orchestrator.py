from __future__ import annotations

import asyncio
import logging
import math
import os
import re
import time
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
from orchestrator.runtime.audio_device_lifecycle import (
    audio_device_monitor,
    uses_followed_system_default,
)
from orchestrator.runtime.confirmation import (
    ConfirmationDialogue,
    ConfirmationReplyMeaning,
    PendingConfirmation,
)
from orchestrator.runtime.cognitive_runtime import (
    CognitiveRuntimePolicy,
    CognitiveRuntimeResolution,
    GoalDrivenRuntimeCoordinator,
)
from orchestrator.runtime.canonical_plan_adapter import CanonicalPlanRuntimeAdapter
from orchestrator.runtime.cognitive_evidence import CognitiveEvidenceRecorder
from orchestrator.runtime.cognitive_turn_closure import CognitiveTurnClosure
from orchestrator.runtime.cognitive_gateway import (
    CognitiveGateway,
)
from orchestrator.runtime.soridormi_scene_perception import (
    run_soridormi_ambient_perception_loop,
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
from orchestrator.runtime.goal_list_console import (
    goal_list_change_by_task,
    goal_list_item_text,
)
from orchestrator.runtime.input_turn_lifecycle import InputTurnLifecycle
from orchestrator.runtime.input_session_runtime import input_session_runtime_for
from orchestrator.runtime.playback_delivery import PlaybackDeliveryLifecycle
from orchestrator.runtime.playback_transport import transport_for as playback_transport_for
from orchestrator.runtime.observability_recording import (
    schedule_accelerator_sample,
)
from orchestrator.runtime.situation import (
    run_time_condition_wake_loop,
)
from orchestrator.runtime.shutdown_lifecycle import shutdown_voice_assistant
from orchestrator.runtime.capability_runtime import CapabilityRuntimeResult
from shared.chromie_contracts.core_interpretation import (
    CognitiveResponsibilityProposal,
    CoreInterpretationResult,
)
from shared.chromie_contracts.interaction import (
    InteractionResponse,
    CapabilityRequest,
    CapabilityResult,
)
from shared.chromie_contracts.goal import GoalAssociationResolution
from shared.chromie_contracts.value_judgment import (
    VALUE_REVIEW_RELATIVE_PATH,
    load_value_review_capability_ids,
)
from shared.chromie_contracts.plan import (
    CanonicalPlan,
)
from shared.chromie_contracts.tool_result import (
    ToolExecutionRequest,
    ToolExecutionResponse,
    ToolResultEvidence,
)
from shared.chromie_contracts.reflex import (
    CancellationDirective,
    CancellationDispatchReceipt,
    ReflexOutcome,
)
from shared.chromie_contracts.user_turn import (
    UserTurnEnvelope,
)
from shared.chromie_contracts.semantic_authority import (
    SemanticAuthorityClaim,
    context_with_semantic_authority,
)
from tts.text_normalization import has_speakable_content, strip_speech_markup
from orchestrator.runtime import cognitive_outcome_host
from orchestrator.runtime import cognitive_pipeline_host
from orchestrator.runtime import confirmation_host
from orchestrator.runtime import interaction_dispatch_host
from orchestrator.runtime import interaction_speech_host
from orchestrator.runtime import planner_reentry_host
from orchestrator.runtime import reflex_cancellation_host
from orchestrator.runtime import routed_turn_host
from orchestrator.runtime import runtime_ready_greeting
from orchestrator.runtime import tts_echo
from orchestrator.runtime import tts_text

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="[%(levelname)s] %(asctime)s - %(threadName)s - %(funcName)s - %(message)s",
)
logger = logging.getLogger("chromie-orchestrator")

# Below uvicorn's default 5 s ``timeout_keep_alive`` used by the Agent service.
AGENT_HTTP_IDLE_KEEPALIVE_S = 3.0


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
        self.failure_speech_mode = session_settings.failure_speech_mode
        self.addressedness_gate_enabled = session_settings.addressedness_gate_enabled
        self.addressedness_engagement_timeout_s = (
            session_settings.addressedness_engagement_timeout_s
        )
        self.planner_mode = cognition_settings.planner_mode
        self.planner_timeout_ms = cognition_settings.planner_timeout_ms
        self.deliberative_timeout_ms = cognition_settings.deliberative_timeout_ms
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
        self.action_dry_run = cognition_settings.action_dry_run
        self.agent_client = build_agent_client(self.host_settings)
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
        self.active_cognitive_runtime_tasks: dict[asyncio.Task, str] = {}
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
            "Control plane: cognitive_gateway=embedded cognitive_core=%s enabled=%s dry_run=%s cognitive_runtime_mode=%s",
            self.agent_url,
            self.enable_agent,
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

        # Focused collaborators own task, microphone, playback, and ledger state.
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
            goal_association_timeout_ms=self.goal_association_timeout_ms,
            planner_timeout_ms=self.planner_timeout_ms,
            deliberative_timeout_ms=self.deliberative_timeout_ms,
            value_review_capability_ids=load_value_review_capability_ids(
                PROJECT_ROOT / VALUE_REVIEW_RELATIVE_PATH
            ),
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
        self.interaction_runtime.runtime.goal_state_provider = lambda: [
            *self.conversation_state.active_goal_snapshots(),
            *self.conversation_state.recent_goal_snapshots(),
        ]
        self.cognitive_runtime = GoalDrivenRuntimeCoordinator(
            agent_client=self.agent_client,
            adapter=CanonicalPlanRuntimeAdapter(
                self.interaction_runtime,
            ),
            policy=self.cognitive_runtime_policy,
            # Goal Association is already the validated, model-owned semantic
            # result.  Publish it immediately so concurrent follow-up turns can
            # reason over the in-flight Goal while planning and composition
            # continue.  Effectful execution still remains behind the trusted
            # canonical-plan/runtime boundary.
            goal_state_apply=self._commit_goal_association_state,
            communicative_goal_completion_apply=(
                self.conversation_state.reconcile_communicative_goal_completion
            ),
            planner_gap_apply=self._commit_planner_information_gaps,
            context_refresh=self.build_context,
            delivered_turn_speech_provider=self._delivered_turn_speech_events,
            workflow_stage_sink=host_support.sessions.record_cognitive_stage,
            social_task_tracker=host_support.sessions.track_social_task,
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

    def playback_start_key(
        self,
        generation: int,
        order: int,
        session_id: Optional[str],
    ) -> tuple[int, int, str | None]:
        return self.playback_delivery.key(generation, order, session_id)

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
        communicative_activity_ids: list[str] | None = None,
        addressed_need_ids: list[str] | None = None,
        source_responsibility_refs: list[str] | None = None,
        wording_owner: str = "",
        turn_id: str | None = None,
        source_goal_ids: list[str] | None = None,
        canonical_plan_id: str = "",
        canonical_plan_fingerprint: str = "",
        goal_association_fingerprint: str = "",
        delivery_role: str = "response",
        claims: list[str] | None = None,
        must_not_claim_completion: bool | None = None,
        cognitive_opportunity_id: str = "",
        situation_signature: str = "",
        subject_refs: list[str] | None = None,
        origin_session_id: str | None = None,
    ) -> dict[str, Any] | None:
        return self.playback_delivery.register_turn_speech_event(
            session_id=session_id,
            origin_session_id=origin_session_id,
            generation=generation,
            orders=orders,
            normalized_text=self.normalize_tts_candidate(text),
            stage=stage,
            purpose=purpose,
            commitment=commitment,
            fast_activity_id=fast_activity_id,
            communicative_activity_ids=communicative_activity_ids,
            addressed_need_ids=addressed_need_ids,
            source_responsibility_refs=source_responsibility_refs,
            wording_owner=wording_owner,
            turn_id=turn_id,
            source_goal_ids=source_goal_ids,
            canonical_plan_id=canonical_plan_id,
            canonical_plan_fingerprint=canonical_plan_fingerprint,
            goal_association_fingerprint=goal_association_fingerprint,
            delivery_role=delivery_role,
            claims=claims,
            must_not_claim_completion=must_not_claim_completion,
            cognitive_opportunity_id=cognitive_opportunity_id,
            situation_signature=situation_signature,
            subject_refs=subject_refs,
        )

    def _delivered_turn_speech_events(
        self,
        session_id: str,
    ) -> list[dict[str, Any]]:
        return self.playback_delivery.delivered_turn_speech_events(session_id)

    def resolve_playback_start_waiter(
        self,
        generation: int,
        order: int,
        session_id: Optional[str],
        *,
        started: bool,
        reason: str,
    ) -> None:
        resolved = self.playback_delivery.resolve_playback_start_waiter(
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
        for _, order, session_id in self.playback_delivery.resolve_all_playback_start_waiters(
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
        self.playback_delivery.resolve_all_playback_release_waiters(reason=reason)

    async def wait_for_playback_start(
        self,
        *,
        generation: int,
        order: int,
        session_id: Optional[str],
        timeout_s: float,
    ) -> bool:
        started = await self.playback_delivery.wait_for_playback_start(
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
        cancelled = self.playback_delivery.cancel_order_before_start(
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
        schedule_accelerator_sample(self, reason="session_start", session_ids=[sid])
        return sid

    def normalize_tts_candidate(self, text: str) -> str:
        text = strip_speech_markup(text)
        text = re.sub(r"^[-•]+\s*", "", text).strip()
        text = re.sub(r"\s+([,.;:!?])", r"\1", text)
        return text

    def is_valid_tts_text(self, text: str) -> bool:
        return has_speakable_content(self.normalize_tts_candidate(text), min_chars=2)

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
            # Release an idle connection before the services close it: uvicorn's default
            # keep-alive is 5 s, and reusing a socket the Agent just closed failed a Value
            # Judgment with ServerDisconnectedError (live 2026-10-12).
            connector = aiohttp.TCPConnector(limit=20, limit_per_host=10,
                                             keepalive_timeout=AGENT_HTTP_IDLE_KEEPALIVE_S,
                                             enable_cleanup_closed=True)
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

    def is_stale_playback(self, generation: int, session_id: Optional[str]) -> bool:
        return generation != self.playback_delivery.playback_generation or session_id != self.session_id

    async def schedule_tts_sentence(
        self,
        sentence: str,
        session_id: Optional[str],
    ) -> dict[str, Any]:
        sentence = self.normalize_tts_candidate(sentence)
        if not self.is_valid_tts_text(sentence):
            self.session_log(session_id, "tts_skip_invalid_sentence_no_order: chars=%s text=%r", len(sentence), sentence)
            return {"scheduled": False, "reason": "invalid_tts_text"}
        async with self.playback_delivery.order_lock:
            generation = self.playback_delivery.playback_generation
            if self.is_stale_playback(generation, session_id):
                self.session_log(
                    session_id,
                    "tts_drop_stale_no_order: chars=%s generation=%s current_generation=%s current_sid=%s text=%r",
                    len(sentence),
                    generation,
                    self.playback_delivery.playback_generation,
                    self.session_id,
                    sentence,
                )
                return {"scheduled": False, "reason": "stale_playback"}
            order = self.playback_delivery.synthesis_order
            self.playback_delivery.synthesis_order += 1
        if self.is_stale_playback(generation, session_id):
            return {"scheduled": False, "reason": "stale_playback"}
        tts_echo.remember_tts_text(self, generation, sentence)
        key = self.playback_start_key(generation, order, session_id)
        from orchestrator.runtime.scheduler import current_execution_start
        execution_start = current_execution_start.get()
        if execution_start is not None:
            self.playback_delivery.execution_starts[key] = execution_start
        self.playback_delivery.playback_start_waiters[key] = asyncio.get_running_loop().create_future()
        self.playback_delivery.create_playback_release_waiter(
            generation=generation,
            order=order,
            session_id=session_id,
        )
        state = self.sessions.state.get(session_id or "")
        if state is not None:
            state["scheduled_tts"] = int(state.get("scheduled_tts", 0)) + 1
        self.session_log(session_id, "tts_schedule: order=%s chars=%s scheduled_tts=%s generation=%s text=%r", order, len(sentence), state.get("scheduled_tts", 0) if state else "unknown", generation, sentence)
        task = asyncio.create_task(playback_transport_for(self).synthesize_one(sentence, order, session_id, generation))
        self.playback_delivery.active_synthesis_tasks.add(task)
        task.add_done_callback(self.playback_delivery.active_synthesis_tasks.discard)
        self.ensure_playback_worker()
        return {"scheduled": True, "order": order, "generation": generation}

    async def schedule_tts_text(
        self,
        text: str,
        session_id: Optional[str],
    ) -> dict[str, Any]:
        chunks = tts_text.split_tts_text(self, text)
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
        return await interaction_speech_host.cancel_interaction_speech(self, request, scheduled)

    async def _schedule_interaction_speech(
        self,
        args: dict[str, Any],
    ) -> dict[str, Any]:
        return await interaction_speech_host.schedule_interaction_speech(self, args)

    def ensure_playback_worker(self) -> None:
        playback_task = self.playback_delivery.playback_task
        if playback_task is None or playback_task.done():
            self.playback_delivery.playback_task = asyncio.create_task(playback_transport_for(self).playback_worker())
        sweeper_task = getattr(self, "session_idle_sweeper_task", None)
        if sweeper_task is None or sweeper_task.done():
            self.session_idle_sweeper_task = asyncio.create_task(
                input_session_runtime_for(self)._session_idle_sweeper()
            )

    async def reset_playback_ordering(self):
        async with self.playback_delivery.order_lock:
            self.resolve_all_playback_start_waiters(
                started=False,
                reason="reset_playback_ordering",
            )
            self.playback_delivery.synthesis_order = 0
            self.playback_delivery.next_playback_order = 0
            self.playback_delivery.pending_audio.clear()
            self.playback_delivery.cancelled_playback_orders.clear()
            while not self.playback_delivery.playback_queue.empty():
                try:
                    self.playback_delivery.playback_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
        self.ensure_playback_worker()

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
        change_by_task = goal_list_change_by_task(applied_operations)
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
                    goal_list_item_text(
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
            "current_generation": self.playback_delivery.playback_generation,
            "session_id": session_id,
            "conversation_id": conversation.get("conversation_id"),
            "interaction_engagement": self._interaction_engagement_context(
                conversation,
                session_id=session_id,
            ),
            "conversation": conversation,
            "session_memory": conversation.get("session_memory", {}),
            "memory_summary": (conversation.get("session_memory") or {}).get("memory_summary"),
            # Model-facing Memory must come from the Memory owner's disclosure-safe
            # prompt projection, never the raw retained snapshot. The raw aggregate
            # remains internal conversation state for retention/debug ownership only.
            "extracted_memory": (conversation.get("session_memory") or {}).get(
                "extracted_memory", []
            ),
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
            "working_goal_memory": conversation.get("working_goal_memory", []),
            "long_term_goal_memory": conversation.get("long_term_goal_memory", []),
            # UMI receives only a small semantic projection of RAM-resident Goal meaning.
            # It uses this to understand ellipsis/correction/confirmation, never to choose
            # canonical Goal identity; GA receives both working and long-term Goal memory.
            "user_meaning_goal_context": list(conversation.get("working_goal_memory", []))[-4:],
            "goal_association_candidates": conversation.get(
                "goal_association_candidates", []
            ),
            "recent_goal_snapshots": conversation.get("recent_goal_snapshots", []),
            "situation": (
                self._ambient_situation_projection.prompt_projection()
                if getattr(self, "_ambient_situation_projection", None) is not None
                else None
            ),
            "current_task_context": conversation.get("current_task_context"),
            "discourse_referents": conversation.get("discourse_referents", []),
            "discourse_focus": conversation.get("discourse_focus", []),
            "verified_tool_memory_index": conversation.get(
                "verified_tool_memory_index", []
            ),
            "recent_tool_evidence": conversation.get("recent_tool_evidence", []),
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
        active_routed_turns = self.input_turn_lifecycle.active_turn_tasks
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

    def _cognitive_gateway_adapter(self) -> CognitiveGateway:
        adapter = getattr(self, "cognitive_gateway", None)
        if adapter is None:
            adapter = CognitiveGateway()
            self.cognitive_gateway = adapter
        return adapter

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

    def _cognitive_core_authority_context(
        self,
        context: dict[str, Any],
        *,
        session_id: str,
        observer: bool,
    ) -> dict[str, Any]:
        return context_with_semantic_authority(
            context,
            SemanticAuthorityClaim(
                owner="cognitive_core_runtime",
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
        return await cognitive_pipeline_host.run_cognitive_runtime_pipeline(
            self,
            session,
            user_text=user_text,
            session_id=session_id,
            context=context,
            core_interpretation=core_interpretation,
            record_evidence=record_evidence,
            turn_envelope=turn_envelope,
        )

    def _apply_cognitive_goal_state(
        self,
        resolution: CognitiveRuntimeResolution,
        *,
        session_id: str,
        user_text: str,
    ) -> list[dict[str, Any]]:
        return cognitive_pipeline_host.apply_cognitive_goal_state(
            self,
            resolution,
            session_id=session_id,
            user_text=user_text,
        )

    def _commit_goal_association_state(
        self,
        association: GoalAssociationResolution,
        *,
        sid: str | None,
        user_text: str,
        source: str,
    ) -> list[dict[str, Any]]:
        return cognitive_pipeline_host.commit_goal_association_state(
            self,
            association,
            sid=sid,
            user_text=user_text,
            source=source,
        )

    def _commit_planner_information_gaps(
        self,
        gaps_by_goal_id: dict[str, list[Any]],
        *,
        turn_id: str,
        sid: str | None,
        user_text: str,
        source: str,
    ) -> list[dict[str, Any]]:
        return cognitive_pipeline_host.commit_planner_information_gaps(
            self,
            gaps_by_goal_id,
            turn_id=turn_id,
            sid=sid,
            user_text=user_text,
            source=source,
        )

    def _finish_delivered_social_session(
        self, session_id: str, response: InteractionResponse,
    ) -> None:
        # SC already waited for Runtime and playback delivery. This branch bypasses
        # _launch_interaction's completion consumer, so close its LLM work here.
        state = self.sessions.state.get(session_id)
        if state is not None:
            state["llm_done"] = True
            state["response_chars"] = state.get("response_chars", 0) + sum(
                len(item.text) for item in response.speech
            )
        self.maybe_session_done(session_id)

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
        return await cognitive_pipeline_host.try_apply_cognitive_runtime(
            self,
            session,
            user_text=user_text,
            session_id=session_id,
            context=context,
            core_interpretation=core_interpretation,
            core_interpretation_latency_ms=core_interpretation_latency_ms,
            turn_envelope=turn_envelope,
        )

    async def handle_routed_text(
        self,
        user_text: str,
        session_id: str,
        *,
        channel: str = "voice",
    ) -> None:
        return await routed_turn_host.handle_routed_text(
            self,
            user_text,
            session_id,
            channel=channel,
        )

    async def _stage_interaction_confirmation(
        self,
        response: InteractionResponse,
        session_id: str,
        *,
        language: str | None,
        reset_playback: bool = True,
    ) -> bool:
        return await confirmation_host.stage_interaction_confirmation(
            self,
            response,
            session_id,
            language=language,
            reset_playback=reset_playback,
        )

    async def _handle_confirmation_reply(
        self,
        user_text: str,
        session_id: str,
        *,
        turn_envelope: UserTurnEnvelope | None = None,
    ) -> bool:
        return await confirmation_host.handle_confirmation_reply(
            self,
            user_text,
            session_id,
            turn_envelope=turn_envelope,
        )

    async def _resolve_pending_confirmation_meaning(
        self,
        user_text: str,
        *,
        session_id: str,
        pending: PendingConfirmation,
    ) -> ConfirmationReplyMeaning:
        return await confirmation_host.resolve_pending_confirmation_meaning(
            self,
            user_text,
            session_id=session_id,
            pending=pending,
        )

    def _reconcile_reflex_cancellation_receipt(
        self,
        receipt: CancellationDispatchReceipt,
        pending: Any | None,
        session_id: str,
        *,
        user_text: str,
        cancellation_scope: str,
    ) -> dict[str, Any]:
        return reflex_cancellation_host.reconcile_reflex_cancellation_receipt(
            self,
            receipt,
            pending,
            session_id,
            user_text=user_text,
            cancellation_scope=cancellation_scope,
        )

    def _cognitive_core_exception_safe_response(
        self,
        user_text: str,
        *,
        context: dict[str, Any] | None = None,
        failure_stage: str | None = None,
        failure_class: str | None = None,
        failure_error: str | None = None,
    ) -> InteractionResponse:
        return cognitive_outcome_host.cognitive_core_exception_safe_response(
            self,
            user_text,
            context=context,
            failure_stage=failure_stage,
            failure_class=failure_class,
            failure_error=failure_error,
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

    async def _execute_planning_work_dag(self, dag: dict[str, Any]) -> dict[str, Any]:
        session = await self.get_http_session()
        return await self.agent_client.execute_planning_work_dag(session, dag)

    async def _cancel_planning_work_dag(
        self,
        dag_id: str,
    ) -> dict[str, Any]:
        session = await self.get_http_session()
        return await self.agent_client.cancel_planning_work_dag(
            session,
            dag_id,
        )

    def _outcome_response_is_stale(
        self,
        *,
        generation: int,
        session_id: str | None,
    ) -> bool:
        current_generation = int(
            self.playback_delivery.playback_generation
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
        detached_delivery: bool = False,
    ) -> str:
        return await cognitive_outcome_host.execute_cognitive_outcome_response(
            self,
            response,
            session_id=session_id,
            detached_delivery=detached_delivery,
        )

    async def _close_cognitive_execution(
        self,
        *,
        response: InteractionResponse,
        execution: CapabilityRuntimeResult,
        session_id: str | None,
        generation: int,
        provider_status: dict[str, Any] | None,
        suppress_final_reason: str | None = None,
    ) -> str:
        return await cognitive_outcome_host.close_cognitive_execution(
            self,
            response=response,
            execution=execution,
            session_id=session_id,
            generation=generation,
            provider_status=provider_status,
            suppress_final_reason=suppress_final_reason,
        )

    async def _reenter_cognition_for_terminal_capability(
        self,
        *,
        response: InteractionResponse,
        result: CapabilityResult,
        session_id: str | None,
        generation: int,
    ) -> None:
        return await planner_reentry_host.reenter_cognition_for_terminal_capability(
            self,
            response=response,
            result=result,
            session_id=session_id,
            generation=generation,
        )

    async def _apply_planner_reentry_response(
        self,
        response: InteractionResponse,
        *,
        session_id: str | None,
    ) -> str:
        return await planner_reentry_host.apply_planner_reentry_response(
            self,
            response,
            session_id=session_id,
        )

    async def _planner_state_reentry_response(
        self,
        *,
        source_response: InteractionResponse | None,
        canonical_plan: CanonicalPlan | None,
        user_request: str,
        language: str,
        goal_ids: list[str],
        evidence_goal_ids: list[str],
        evidence_refs: list[str],
        session_id: str | None,
        phase: str,
        context_updates: dict[str, Any],
        fast_workflow_stage: str,
        response_source: str,
        responsibilities_override: list[CognitiveResponsibilityProposal] | None = None,
        parent_interaction_id: str | None = None,
        repeat_check_evidence: list[ToolResultEvidence] | None = None,
        repeat_check_context: dict[str, Any] | None = None,
    ) -> InteractionResponse | None:
        return await planner_reentry_host.planner_state_reentry_response(
            self,
            source_response=source_response,
            canonical_plan=canonical_plan,
            user_request=user_request,
            language=language,
            goal_ids=goal_ids,
            evidence_goal_ids=evidence_goal_ids,
            evidence_refs=evidence_refs,
            session_id=session_id,
            phase=phase,
            context_updates=context_updates,
            fast_workflow_stage=fast_workflow_stage,
            response_source=response_source,
            responsibilities_override=responsibilities_override,
            parent_interaction_id=parent_interaction_id,
            repeat_check_evidence=repeat_check_evidence,
            repeat_check_context=repeat_check_context,
        )

    async def _plan_evidence_bound_capability_result_response(
        self,
        *,
        source_response: InteractionResponse,
        bundle: Any,
        plan: Any,
        session_id: str | None,
    ) -> InteractionResponse | None:
        return await planner_reentry_host.plan_evidence_bound_capability_result_response(
            self,
            source_response=source_response,
            bundle=bundle,
            plan=plan,
            session_id=session_id,
        )

    def _launch_interaction(
        self,
        response: InteractionResponse,
        session_id: str | None,
        *,
        confirmed_request_ids: set[str] | None = None,
        reset_playback: bool = True,
        mark_session_done: bool = True,
    ) -> None:
        return interaction_dispatch_host.launch_interaction(
            self,
            response,
            session_id,
            confirmed_request_ids=confirmed_request_ids,
            reset_playback=reset_playback,
            mark_session_done=mark_session_done,
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
        return await interaction_dispatch_host.dispatch_detached_interaction(
            self,
            response,
            session_id,
            confirmed_request_ids=confirmed_request_ids,
            reset_playback=reset_playback,
            mark_session_done=mark_session_done,
        )

    def start_soridormi_ambient_perception(self) -> asyncio.Task | None:
        """Start the one mechanical ambient scene poll for this Host, if enabled.

        Every Host entrypoint that admits turns against Soridormi uses this, so
        Planner Situation reflects current trusted perception in voice and text.
        """

        if not getattr(self, "enable_soridormi_capabilities", False):
            return None
        existing = getattr(self, "_ambient_perception_task", None)
        if existing is not None and not existing.done():
            return existing
        task = asyncio.create_task(
            run_soridormi_ambient_perception_loop(self),
            name="soridormi-ambient-perception",
        )
        self.active_cognitive_runtime_tasks[task] = "soridormi-ambient-perception"
        task.add_done_callback(self._cognitive_runtime_task_done)
        self._ambient_perception_task = task
        return task

    def _cognitive_runtime_task_done(self, task: asyncio.Task) -> None:
        result_tasks = getattr(self, "active_cognitive_runtime_tasks", None)
        if isinstance(result_tasks, dict):
            result_tasks.pop(task, None)
        if task.cancelled():
            return
        error = task.exception()
        if error is not None:
            logger.error(
                "Detached cognitive runtime task failed: %s",
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
        return await interaction_dispatch_host.consume_detached_non_cognitive_dispatch(
            self,
            dispatch,
            session_id=session_id,
            generation=generation,
            confirmed_request_ids=confirmed_request_ids,
        )

    async def _consume_detached_cognitive_dispatch(
        self,
        dispatch: Any,
        *,
        session_id: str | None,
        generation: int,
        confirmed_request_ids: set[str] | None,
    ) -> CapabilityRuntimeResult:
        return await interaction_dispatch_host.consume_detached_cognitive_dispatch(
            self,
            dispatch,
            session_id=session_id,
            generation=generation,
            confirmed_request_ids=confirmed_request_ids,
        )

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
        return await interaction_dispatch_host.record_soridormi_post_status(self, session_id)

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
        self.playback_delivery.playback_generation += 1
        self.playback_delivery.cancel_output_duck()
        self.resolve_all_playback_start_waiters(
            started=False,
            reason="interrupt",
        )
        if cancel_cognitive_work:
            input_session_runtime_for(self)._cancel_active_routed_turns(
                excluding=asyncio.current_task(),
                cancel_all=False,
                reason="foreground_interaction_interrupted",
            )
        for task in list(self.playback_delivery.active_synthesis_tasks):
            if not task.done():
                task.cancel()
        self.playback_delivery.pending_audio.clear()
        self.playback_delivery.cancelled_playback_orders.clear()
        while not self.playback_delivery.playback_queue.empty():
            try:
                self.playback_delivery.playback_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        self.playback_delivery.next_playback_order = 0
        self.playback_delivery.synthesis_order = 0

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
            await playback_transport_for(self).abort_output_stream()
            if new_session_id and log_event:
                self.session_log(
                    new_session_id,
                    "interrupt_previous_audio_done: playback_generation=%s",
                    self.playback_delivery.playback_generation,
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
        coordinator = getattr(self, "cognitive_runtime", None)
        if coordinator is not None:
            await coordinator.cancel_social_interaction()
        self._invalidate_output_state(
            cancel_cognitive_work=cancel_cognitive_work,
        )
        presentation_compute_lease = getattr(
            self, "presentation_compute_lease", None
        )
        if presentation_compute_lease is not None:
            await presentation_compute_lease.revoke(
                reason="explicit_output_interrupt"
            )
        await playback_transport_for(self).abort_output_stream()
        if new_session_id and log_event:
            self.session_log(new_session_id, "interrupt_previous_audio_done: playback_generation=%s", self.playback_delivery.playback_generation)

    async def _apply_reflex_cancellation(
        self,
        outcome: ReflexOutcome,
        *,
        source_turn_id: str,
    ) -> CancellationDispatchReceipt:
        return await reflex_cancellation_host.apply_reflex_cancellation(
            self,
            outcome,
            source_turn_id=source_turn_id,
        )

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
            self.session_log(new_session_id, "interrupt_previous_audio_done: playback_generation=%s", self.playback_delivery.playback_generation)

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

    async def _generate_runtime_ready_greeting(self) -> tuple[str, str]:
        return await runtime_ready_greeting.generate_runtime_ready_greeting(self)

    async def _announce_runtime_ready(self) -> None:
        """Delegate startup orientation and optional speech to one collaborator."""

        await runtime_ready_greeting.build_runtime_ready_greeting_coordinator(self).announce()

    async def wait_for_interaction_services(
        self, *, require_asr: bool = True, deadline_s: float | None = None,
    ) -> ServiceReadinessGate:
        """Interact only once every service reports it can serve a turn (TTS: warm)."""
        gate = ServiceReadinessGate(
            asr_url=self.asr_url,
            tts_url=self.tts_url,
            speaker_id=self.speaker_id,
            get_http_session=self.get_http_session,
            agent_url=self.agent_url,
            enable_agent=self.enable_agent,
        )
        gate.asr_ws = await gate.wait_until_ready(require_asr=require_asr, deadline_s=deadline_s)
        return gate

    async def run(self):
        self.asr_ws = (await self.wait_for_interaction_services()).asr_ws
        self.playback_delivery.playback_task = asyncio.create_task(playback_transport_for(self).playback_worker())
        if any(
            uses_followed_system_default(self, kind)
            for kind in ("input", "output")
        ):
            self.audio_device_monitor_task = asyncio.create_task(
                audio_device_monitor(self)
            )
        await self._announce_runtime_ready()
        time_condition_task = asyncio.create_task(
            run_time_condition_wake_loop(self),
            name="time-condition-cognition-wake",
        )
        self.active_cognitive_runtime_tasks[time_condition_task] = (
            "time-condition-cognition-wake"
        )
        time_condition_task.add_done_callback(self._cognitive_runtime_task_done)
        self.start_soridormi_ambient_perception()
        if self.conversation_state.runtime_revalidation_candidates():
            task = asyncio.create_task(
                planner_reentry_host.revalidate_restored_goals_from_provider_state(self),
                name="restored-goal-provider-revalidation",
            )
            self.active_cognitive_runtime_tasks[task] = (
                "restored-goal-provider-revalidation"
            )
            task.add_done_callback(self._cognitive_runtime_task_done)
        input_runtime = input_session_runtime_for(self)
        if self.audio_input_mode == "stdin":
            await input_runtime.injected_audio_stream()
        else:
            await input_runtime.mic_stream()


async def main():
    assistant = VoiceAssistant()
    try:
        await assistant.run()
    finally:
        await shutdown_voice_assistant(
            assistant,
            close_output_stream=playback_transport_for(assistant).close_output_stream,
        )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Orchestrator stopped by operator")
