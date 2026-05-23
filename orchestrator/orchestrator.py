from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import re
import time
from typing import Any, Optional

from dotenv import load_dotenv

load_dotenv(".env.local")
load_dotenv("../.env")

import aiohttp
import numpy as np
import sounddevice as sd
import websockets
from scipy import signal

from audio_device_manager import AudioDeviceManager
from readiness import ServiceReadinessGate
from vad import VAD
from clients.action_client import ActionClient
from clients.agent_client import AgentClient
from clients.router_client import RouterClient
from runtime.session import SessionTracker, now_ms
from schemas.agent import AgentResult, SpeechItem
from schemas.route import RouteDecision

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
        self.router_url = os.getenv("ROUTER_URL", "http://127.0.0.1:8091")
        self.agent_url = os.getenv("AGENT_URL", "http://127.0.0.1:8092")
        self.action_executor_url = os.getenv("ACTION_EXECUTOR_URL", "http://127.0.0.1:8095")
        self.action_dry_run = env_bool("ORCH_ACTION_DRY_RUN", True)
        self.router_client = RouterClient(self.router_url, int(os.getenv("ORCH_ROUTER_TIMEOUT_MS", "900")))
        self.agent_client = AgentClient(self.agent_url, int(os.getenv("ORCH_AGENT_TIMEOUT_MS", "3000")))
        self.action_client = ActionClient(self.action_executor_url, int(os.getenv("ORCH_ACTION_TIMEOUT_MS", "5000")))

        self.min_rms = float(os.getenv("ORCH_MIN_RMS", "120"))
        self.barge_in_min_rms = float(os.getenv("ORCH_BARGE_IN_MIN_RMS", "350"))
        self.min_audio_ms = int(os.getenv("ORCH_MIN_AUDIO_MS", "1200"))
        self.tts_flush_chars = int(os.getenv("TTS_FLUSH_CHARS", "160"))
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

        self.asr_ws = None
        self.http_session: aiohttp.ClientSession | None = None
        self.sessions = SessionTracker(enabled=self.enable_session_timing)
        self.active_llm_task: asyncio.Task | None = None
        self.is_playing_audio = False

        self.audio_mgr = AudioDeviceManager()
        self.input_params = self.audio_mgr.get_input_params()
        self.output_params = self.audio_mgr.get_output_params()
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
        self.playback_queue: asyncio.Queue = asyncio.Queue()
        self.playback_task: asyncio.Task | None = None
        self.active_synthesis_tasks: set[asyncio.Task] = set()
        self.active_asr_task: asyncio.Task | None = None
        self.synthesis_semaphore = asyncio.Semaphore(int(os.getenv("ORCH_TTS_CONCURRENCY", "1")))
        self.next_playback_order = 0
        self.pending_audio: dict[int, tuple[int, bytes, int, str | None, str | None]] = {}
        self.synthesis_order = 0
        self.playback_generation = 0
        self.order_lock = asyncio.Lock()
        self.output_stream = None
        self.output_stream_lock = asyncio.Lock()
        self.output_write_lock = asyncio.Lock()
        self.playback_chunk_ms = int(os.getenv("ORCH_PLAYBACK_CHUNK_MS", "80"))
        self.recordings_dir = os.getenv("RECORDINGS_DIR", "../recordings")
        os.makedirs(self.recordings_dir, exist_ok=True)

    @property
    def session_id(self) -> str | None:
        return self.sessions.current_sid

    def session_log(self, sid: Optional[str], message: str, *args: Any) -> None:
        self.sessions.log(sid, message, *args)

    def maybe_session_done(self, sid: Optional[str]) -> None:
        self.sessions.maybe_done(sid)

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

    def pop_tts_chunk(self, buffer: str) -> tuple[str | None, str]:
        candidate = self.normalize_tts_candidate(buffer)
        if not candidate:
            return None, ""
        match = re.search(r".+?[.!?。！？](?:\s+|$)", candidate)
        if match:
            end = match.end()
            return candidate[:end].strip(), candidate[end:].strip()
        if len(candidate) >= self.tts_flush_chars:
            cut = candidate[: self.tts_flush_chars]
            cut_points = [cut.rfind(sep) for sep in (",", "，", "、", ";", ":", " ")]
            cut_at = max(cut_points)
            if cut_at < max(40, self.tts_flush_chars // 2):
                cut_at = self.tts_flush_chars
            else:
                cut_at += 1
            return candidate[:cut_at].strip(), candidate[cut_at:].strip()
        return None, candidate

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
                    self.next_playback_order += 1
                    continue
                played = await self.play_one_order(ng, self.next_playback_order, na, nsr, nsid, nreason)
                if played:
                    self.next_playback_order += 1
                else:
                    break

    async def play_one_order(self, generation: int, order: int, audio: bytes, source_rate: int, session_id: Optional[str], skip_reason: Optional[str] = None) -> bool:
        if self.is_stale_playback(generation, session_id):
            return False
        state = self.sessions.state.get(session_id or "")
        if not audio:
            reason = skip_reason or "empty_audio"
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

    async def schedule_tts_sentence(self, sentence: str, session_id: Optional[str]):
        sentence = self.normalize_tts_candidate(sentence)
        if not self.is_valid_tts_text(sentence):
            self.session_log(session_id, "tts_skip_invalid_sentence_no_order: chars=%s text=%r", len(sentence), sentence)
            return
        async with self.order_lock:
            order = self.synthesis_order
            self.synthesis_order += 1
            generation = self.playback_generation
        if self.is_stale_playback(generation, session_id):
            return
        state = self.sessions.state.get(session_id or "")
        if state is not None:
            state["scheduled_tts"] = int(state.get("scheduled_tts", 0)) + 1
        self.session_log(session_id, "tts_schedule: order=%s chars=%s scheduled_tts=%s generation=%s text=%r", order, len(sentence), state.get("scheduled_tts", 0) if state else "unknown", generation, sentence)
        task = asyncio.create_task(self.synthesize_one(sentence, order, session_id, generation))
        self.active_synthesis_tasks.add(task)
        task.add_done_callback(self.active_synthesis_tasks.discard)

    async def reset_playback_ordering(self):
        async with self.order_lock:
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
        return {
            "is_speaking": self.is_playing_audio,
            "current_generation": self.playback_generation,
            "session_id": session_id,
            "robot_state": {
                "available": not self.action_dry_run,
                "source": "host_orchestrator",
            },
        }

    async def handle_routed_text(self, user_text: str, session_id: str) -> None:
        if not self.enable_router:
            self.active_llm_task = asyncio.create_task(self.process_llm_tts(user_text, session_id))
            return

        session = await self.get_http_session()
        context = self.build_context(session_id)
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
            self.active_llm_task = asyncio.create_task(self.process_llm_tts(user_text, session_id))
            return

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
            result = await self.agent_client.run(session, text=user_text, route_decision=decision, sid=session_id, context=context)
            self.session_log(
                session_id,
                "agent_done: agent_ms=%.1f speak_immediate=%s actions=%s speak_after=%s requires_confirmation=%s",
                now_ms() - agent_start_ms,
                len(result.speak_immediate),
                len(result.actions),
                len(result.speak_after),
                result.requires_confirmation,
            )
            await self.execute_agent_result(result, session_id)
        except Exception as exc:
            self.session_log(session_id, "agent_exception: agent_ms=%.1f error=%s", now_ms() - agent_start_ms, exc)
            logger.warning("Agent failed; falling back to direct LLM: %s", exc, exc_info=True)
            self.active_llm_task = asyncio.create_task(self.process_llm_tts(user_text, session_id))

    async def execute_agent_result(self, result: AgentResult, session_id: str | None) -> None:
        await self.reset_playback_ordering()
        for item in result.speak_immediate:
            await self.schedule_tts_sentence(item.text, session_id)

        session = await self.get_http_session()
        for action in result.actions:
            action_start_ms = now_ms()
            self.session_log(session_id, "action_start: id=%s target=%s type=%s blocking=%s dry_run=%s", action.id, action.target, action.type, action.blocking, self.action_dry_run)
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
            await self.schedule_tts_sentence(item.text, session_id)

        state = self.sessions.state.get(session_id or "")
        if state is not None:
            state["llm_done"] = True
            state["response_chars"] = state.get("response_chars", 0) + sum(len(i.text) for i in result.speak_immediate + result.speak_after)
        self.maybe_session_done(session_id)

    async def interrupt(self, new_session_id: Optional[str] = None):
        self.playback_generation += 1
        if self.active_llm_task and not self.active_llm_task.done():
            self.active_llm_task.cancel()
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
            resp = await asyncio.wait_for(self.asr_ws.recv(), timeout=15.0)
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

    async def mic_stream(self):
        logger.info("Opening microphone with sounddevice")
        self.loop = asyncio.get_running_loop()
        frame_bytes_target = int(self.target_asr_rate * self.frame_duration_ms / 1000) * 2
        leftover = b""
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
            while True:
                audio = await self.mic_queue.get()
                pcm_16k = leftover + self.prepare_mic_chunk_for_asr(audio)
                offset = 0
                while offset + frame_bytes_target <= len(pcm_16k):
                    frame = pcm_16k[offset : offset + frame_bytes_target]
                    offset += frame_bytes_target
                    started, ended, vad_audio = self.vad.process_chunk(frame)
                    if started:
                        logger.info("VAD detected voice")
                    if ended and vad_audio:
                        if self.active_asr_task is None or self.active_asr_task.done():
                            self.active_asr_task = asyncio.create_task(self.handle_vad_audio(vad_audio))
                        else:
                            logger.warning("ASR is still processing; dropping new utterance")
                leftover = pcm_16k[offset:]
                await asyncio.sleep(0)

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
        await self.mic_stream()

    async def cleanup(self):
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
