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
import sounddevice as sd
import websockets
from scipy import signal

from orchestrator.audio_device_manager import AudioDeviceManager
from orchestrator.audio_injection import read_audio_packet
from orchestrator.readiness import ServiceReadinessGate
from orchestrator.vad import VAD
from orchestrator.clients.action_client import ActionClient
from orchestrator.clients.agent_client import AgentClient
from orchestrator.clients.router_client import RouterClient
from orchestrator.runtime.session import SessionTracker, now_ms
from orchestrator.runtime.confirmation import ConfirmationDialogue
from orchestrator.runtime.conversation_state import ConversationStateManager
from orchestrator.runtime.interaction_coordinator import (
    InteractionRuntimeCoordinator,
    build_soridormi_invoker,
)
from orchestrator.runtime.skill_runtime import SkillRuntimeResult
from orchestrator.schemas.agent import AgentResult, SpeechItem
from orchestrator.schemas.route import RouteDecision
from shared.chromie_contracts.interaction import InteractionResponse

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="[%(levelname)s] %(asctime)s - %(threadName)s - %(funcName)s - %(message)s",
)
logger = logging.getLogger("chromie-orchestrator")


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


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
        self.router_url = os.getenv("ROUTER_URL", "http://127.0.0.1:8091")
        self.agent_url = os.getenv("AGENT_URL", "http://127.0.0.1:8092")
        self.action_executor_url = os.getenv("ACTION_EXECUTOR_URL", "http://127.0.0.1:8095")
        self.action_dry_run = env_bool("ORCH_ACTION_DRY_RUN", True)
        self.router_client = RouterClient(self.router_url, int(os.getenv("ORCH_ROUTER_TIMEOUT_MS", "2000")))
        self.agent_client = AgentClient(self.agent_url, int(os.getenv("ORCH_AGENT_TIMEOUT_MS", "3000")))
        self.action_client = ActionClient(self.action_executor_url, int(os.getenv("ORCH_ACTION_TIMEOUT_MS", "5000")))
        self.asr_timeout_s = max(
            0.001,
            int(os.getenv("ORCH_ASR_TIMEOUT_MS", "30000")) / 1000.0,
        )

        self.min_rms = float(os.getenv("ORCH_MIN_RMS", "120"))
        self.barge_in_min_rms = float(os.getenv("ORCH_BARGE_IN_MIN_RMS", "350"))
        self.min_audio_ms = int(os.getenv("ORCH_MIN_AUDIO_MS", "1200"))
        self.tts_flush_chars = int(os.getenv("TTS_FLUSH_CHARS", "160"))
        self.tts_text_chunking_enabled = env_bool("ORCH_TTS_TEXT_CHUNKING", True)
        self.tts_chunk_chars = max(
            20,
            int(os.getenv("ORCH_TTS_CHUNK_CHARS", str(self.tts_flush_chars))),
        )
        self.tts_min_chunk_chars = max(
            1,
            int(os.getenv("ORCH_TTS_MIN_CHUNK_CHARS", "40")),
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
        self.confirmation_dialogue = ConfirmationDialogue(
            ttl_s=float(os.getenv("ORCH_CONFIRMATION_TTL_SEC", "20")),
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
        self.active_llm_task: asyncio.Task | None = None
        self.active_interaction_task: asyncio.Task | None = None
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
            "Input device name=%s index=%s rate=%sHz channels=%s blocksize=%s block_ms=%s latency=%s min_rms=%s barge_in_min_rms=%s",
            self.input_params["name"],
            self.input_device,
            self.input_rate,
            self.input_channels,
            self.input_block_size,
            self.input_params["block_ms"],
            self.input_latency,
            self.min_rms,
            self.barge_in_min_rms,
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
            "Control plane: router=%s enabled=%s agent=%s enabled=%s action_url=%s dry_run=%s",
            self.router_url,
            self.enable_router,
            self.agent_url,
            self.enable_agent,
            self.action_executor_url,
            self.action_dry_run,
        )

        self.target_asr_rate = 16000
        self.frame_duration_ms = 30
        self.vad = VAD(
            mode=int(os.getenv("ORCH_VAD_MODE", "3")),
            sample_rate=self.target_asr_rate,
            frame_duration_ms=self.frame_duration_ms,
            silence_timeout_ms=int(os.getenv("ORCH_VAD_SILENCE_MS", "650")),
        )

        self.loop: asyncio.AbstractEventLoop | None = None
        self.mic_queue: asyncio.Queue = asyncio.Queue(maxsize=50)
        self._vad_leftover = b""
        self.playback_queue: asyncio.Queue = asyncio.Queue()
        self.playback_task: asyncio.Task | None = None
        self.active_synthesis_tasks: set[asyncio.Task] = set()
        self.active_asr_task: asyncio.Task | None = None
        self.synthesis_semaphore = asyncio.Semaphore(int(os.getenv("ORCH_TTS_CONCURRENCY", "1")))
        self.next_playback_order = 0
        self.pending_audio: dict[int, tuple[int, bytes, int, str | None, str | None]] = {}
        self.synthesis_order = 0
        self.playback_generation = 0
        self.playback_start_waiters: dict[
            tuple[int, int, str | None],
            asyncio.Future[bool],
        ] = {}
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
            "Interaction runtime: endpoint=%s soridormi_skills=%s auto_confirm_sim=%s confirmation_ttl_s=%.1f",
            self.enable_interaction_response,
            self.enable_soridormi_skills,
            self.auto_confirm_sim_skills,
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
        limit = max(20, int(flush_chars or self.tts_flush_chars))
        match = re.search(r".+?[.!?。！？](?:\s+|$)", candidate)
        if match and (match.end() <= limit or len(candidate) <= limit):
            end = match.end()
            return candidate[:end].strip(), candidate[end:].strip()
        if len(candidate) >= limit:
            cut = candidate[:limit]
            cut_points = [cut.rfind(sep) for sep in (",", "，", "、", ";", ":", " ")]
            cut_at = max(cut_points)
            if cut_at < max(20, limit // 2):
                cut_at = limit
            else:
                cut_at += 1
            return candidate[:cut_at].strip(), candidate[cut_at:].strip()
        return None, candidate

    def split_tts_text(self, text: str) -> list[str]:
        candidate = self.normalize_tts_candidate(text)
        if not self.is_valid_tts_text(candidate):
            return []
        if not getattr(self, "tts_text_chunking_enabled", True):
            return [candidate]
        limit = max(
            20,
            int(getattr(self, "tts_chunk_chars", getattr(self, "tts_flush_chars", 160))),
        )
        if len(candidate) <= limit:
            return [candidate]

        raw_chunks: list[str] = []
        remaining = candidate
        while remaining:
            chunk, remaining = self.pop_tts_chunk(remaining, flush_chars=limit)
            if chunk is None:
                chunk, remaining = remaining, ""
            if self.is_valid_tts_text(chunk):
                raw_chunks.append(chunk)
        if not raw_chunks:
            return [candidate]

        chunks: list[str] = []
        current = ""
        min_chars = max(1, int(getattr(self, "tts_min_chunk_chars", 40)))
        overflow_limit = limit + min(10, max(0, min_chars // 4))
        for chunk in raw_chunks:
            merged = f"{current} {chunk}".strip() if current else chunk
            if not current:
                current = chunk
            elif len(merged) <= limit or (
                len(current) < min_chars and len(merged) <= overflow_limit
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

    async def reset_playback_ordering(self):
        async with self.order_lock:
            self.resolve_all_playback_start_waiters(
                started=False,
                reason="reset_playback_ordering",
            )
            self.synthesis_order = 0
            self.next_playback_order = 0
            self.pending_audio.clear()
            while not self.playback_queue.empty():
                try:
                    self.playback_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
        if self.playback_task is None or self.playback_task.done():
            self.playback_task = asyncio.create_task(self.playback_worker())

    async def process_llm_tts(self, user_text: str, session_id: Optional[str]):
        payload = {
            "model": self.ollama_model,
            "prompt": f"{self.voice_system_prompt}\n\nUser: {user_text}\nAssistant:",
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
        await self.reset_playback_ordering()
        sentence = ""
        llm_start_ms = now_ms()
        self.session_log(session_id, "llm_request_start: prompt_chars=%s text=%r think=%s num_ctx=%s num_predict=%s", len(user_text), user_text, payload.get("think"), payload["options"]["num_ctx"], payload["options"]["num_predict"])
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

    def build_context(self, session_id: str | None) -> dict[str, Any]:
        conversation = self.conversation_state.snapshot()
        return {
            "is_speaking": self.is_playing_audio,
            "current_generation": self.playback_generation,
            "session_id": session_id,
            "conversation_id": conversation.get("conversation_id"),
            "conversation": conversation,
            "history": conversation.get("history", []),
            "pending_tasks": conversation.get("pending_tasks", []),
            "active_pending_tasks": conversation.get("active_pending_tasks", []),
            "robot_state": {
                "available": not self.action_dry_run,
                "source": "host_orchestrator",
            },
        }

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
            self.active_llm_task = asyncio.create_task(self.process_llm_tts(user_text, session_id))
            return

        session = await self.get_http_session()
        context = self.build_context(session_id)
        self.session_log(
            session_id,
            "context_snapshot: conversation_id=%s history_turns=%s pending_tasks=%s",
            context.get("conversation_id"),
            len(context.get("history", [])),
            len(context.get("active_pending_tasks", []) or context.get("pending_tasks", [])),
        )
        router_start_ms = now_ms()
        self.session_log(session_id, "router_start: text_chars=%s text=%r", len(user_text), user_text)
        try:
            decision = await self.router_client.route(session, text=user_text, sid=session_id, context=context)
            self.session_log(
                session_id,
                "router_done: router_ms=%.1f route=%s agents=%s intent=%s confidence=%.2f interrupt=%s needs_agent=%s",
                now_ms() - router_start_ms,
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
            self.conversation_state.record_user_turn(
                session_id,
                user_text,
                route="direct_llm",
                intent="router_exception",
                metadata={"source": "router_exception", "error": str(exc)},
            )
            self.active_llm_task = asyncio.create_task(self.process_llm_tts(user_text, session_id))
            return

        self.conversation_state.record_user_turn(
            session_id,
            user_text,
            route=decision.route,
            intent=decision.intent,
            metadata={"source": decision.source, "confidence": decision.confidence},
        )

        if decision.interrupt_current or decision.route == "interrupt":
            await self.interrupt(new_session_id=session_id)
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
            self.active_llm_task = asyncio.create_task(self.process_llm_tts(user_text, session_id))
            return

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
                response = response.model_copy(
                    deep=True,
                    update={
                        "metadata": {
                            **response.metadata,
                            "language": decision.language,
                        }
                    },
                )
                self.session_log(
                    session_id,
                    "interaction_done: agent_ms=%.1f speech=%s skills=%s requires_confirmation=%s",
                    now_ms() - agent_start_ms,
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
                ):
                    return

                self.conversation_state.record_agent_result(session_id, response)
                self._launch_interaction(response, session_id)
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
            self.conversation_state.record_agent_result(session_id, result)
            await self.execute_agent_result(result, session_id)
        except Exception as exc:
            self.session_log(session_id, "agent_exception: agent_ms=%.1f error=%s", now_ms() - agent_start_ms, exc)
            logger.warning("Agent failed; falling back to direct LLM: %s", exc, exc_info=True)
            self.active_llm_task = asyncio.create_task(self.process_llm_tts(user_text, session_id))

    async def _stage_interaction_confirmation(
        self,
        response: InteractionResponse,
        session_id: str,
        *,
        language: str | None,
    ) -> bool:
        confirmation_request_ids = (
            await self.interaction_runtime.confirmation_request_ids(response)
        )
        if not confirmation_request_ids:
            return False

        pending = self.confirmation_dialogue.begin(
            response,
            confirmed_request_ids=confirmation_request_ids,
            origin_session_id=session_id,
            conversation_id=self.conversation_state.conversation_id,
            language=language,
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
        self._launch_interaction(prompt_response, session_id)
        return True

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

    def _host_speech_response(
        self,
        text: str,
        *,
        style: str,
    ) -> InteractionResponse:
        return InteractionResponse(
            speech=[
                {
                    "text": text,
                    "style": style,
                    "timing": "immediate",
                    "priority": "high",
                    "interruptible": True,
                    "metadata": {"source": "host_confirmation_dialogue"},
                }
            ],
            metadata={"source": "host_confirmation_dialogue"},
        )

    async def _execute_planning_task_graph(self, graph: dict[str, Any]) -> dict[str, Any]:
        session = await self.get_http_session()
        return await self.agent_client.execute_planning_task_graph(session, graph)

    def _launch_interaction(
        self,
        response: InteractionResponse,
        session_id: str | None,
        *,
        confirmed_request_ids: set[str] | None = None,
    ) -> None:
        task = asyncio.create_task(
            self.execute_interaction_response(
                response,
                session_id,
                confirmed_request_ids=confirmed_request_ids,
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
    ) -> SkillRuntimeResult:
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
            raise
        finally:
            state = self.sessions.state.get(session_id or "")
            if state is not None:
                state["llm_done"] = True
                state["response_chars"] = state.get(
                    "response_chars",
                    0,
                ) + sum(len(item.text) for item in response.speech)
            self.maybe_session_done(session_id)

    async def execute_agent_result(self, result: AgentResult, session_id: str | None) -> None:
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

    async def interrupt(self, new_session_id: Optional[str] = None):
        self.playback_generation += 1
        self.resolve_all_playback_start_waiters(
            started=False,
            reason="interrupt",
        )
        if self.active_llm_task and not self.active_llm_task.done():
            self.active_llm_task.cancel()
        if self.active_interaction_task and not self.active_interaction_task.done():
            self.active_interaction_task.cancel()
        await self.interaction_runtime.cancel_all()
        for task in list(self.active_synthesis_tasks):
            if not task.done():
                task.cancel()
        self.pending_audio.clear()
        while not self.playback_queue.empty():
            try:
                self.playback_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        self.next_playback_order = 0
        self.synthesis_order = 0
        await self.abort_output_stream()
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
        await self.interrupt(new_session_id=session_id)

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
                    await self.handle_routed_text(user_text, session_id)
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
                if self.active_asr_task is None or self.active_asr_task.done():
                    self.active_asr_task = asyncio.create_task(
                        self.handle_vad_audio(vad_audio)
                    )
                else:
                    logger.warning("ASR is still processing; dropping new utterance")
        self._vad_leftover = buffered[offset:]
        await asyncio.sleep(0)

    async def mic_stream(self):
        logger.info("Opening microphone with sounddevice")
        self.loop = asyncio.get_running_loop()
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
