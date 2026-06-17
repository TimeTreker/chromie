from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import math
import os
import re
import threading
import time
import types
from pathlib import Path
from typing import Optional

import numpy as np
import outetts
import soundfile as sf
import torch
import websockets
from outetts import (
    Backend,
    GenerationConfig,
    Interface,
    LlamaCppQuantization,
    Models,
    SamplerConfig,
)
from scipy import signal

from model_sources import apply_model_sources, resolve_model_sources

from cancellable_worker import RestartableProcessWorker

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("chromie-tts")


def env_int(name: str, default: int, *, minimum: int | None = None) -> int:
    raw = os.getenv(name)
    try:
        value = int(raw) if raw not in (None, "") else int(default)
    except ValueError:
        logger.warning("Invalid integer env %s=%r; using %s", name, raw, default)
        value = int(default)
    if minimum is not None and value < minimum:
        logger.warning("Env %s=%s is below minimum %s; using %s", name, value, minimum, minimum)
        value = minimum
    return value


HOST = os.getenv("TTS_HOST", "0.0.0.0")
PORT = env_int("TTS_PORT", 5000, minimum=1)
MODEL_SIZE = os.getenv("TTS_MODEL_SIZE", "0.6B")
QUANTIZATION_NAME = os.getenv("TTS_QUANTIZATION", "FP16")

# Raw PCM sample rate reported to orchestrator. The host orchestrator may resample
# this source rate to the actual speaker output rate.
TTS_SAMPLE_RATE = env_int("TTS_SAMPLE_RATE", 44100, minimum=8000)
TTS_CHUNK_MS = env_int("TTS_CHUNK_MS", 120, minimum=20)
TTS_N_GPU_LAYERS = env_int("TTS_N_GPU_LAYERS", -1)
TTS_CONTEXT_SIZE = env_int("TTS_CONTEXT_SIZE", 4096, minimum=512)

# IMPORTANT:
# TTS_MAX_LENGTH is the OuteTTS/llama generation token budget, not a text
# character limit. Very small values such as 100/120/180 can make OuteTTS emit
# zero audio codec tokens, which later fails in DAC decode with:
#   torch.cat(): expected a non-empty list of Tensors
# Use TTS_MAX_TEXT_CHARS to limit spoken text length.
REQUESTED_TTS_MAX_LENGTH = env_int("TTS_MAX_LENGTH", TTS_CONTEXT_SIZE, minimum=1)
MIN_TTS_GENERATION_LENGTH = env_int("MIN_TTS_GENERATION_LENGTH", 1024, minimum=128)

if TTS_CONTEXT_SIZE < MIN_TTS_GENERATION_LENGTH:
    logger.warning(
        "TTS_CONTEXT_SIZE=%s is smaller than MIN_TTS_GENERATION_LENGTH=%s; "
        "effective generation length will be capped at context size.",
        TTS_CONTEXT_SIZE,
        MIN_TTS_GENERATION_LENGTH,
    )

EFFECTIVE_TTS_MAX_LENGTH = min(
    max(REQUESTED_TTS_MAX_LENGTH, min(MIN_TTS_GENERATION_LENGTH, TTS_CONTEXT_SIZE)),
    TTS_CONTEXT_SIZE,
)

if REQUESTED_TTS_MAX_LENGTH != EFFECTIVE_TTS_MAX_LENGTH:
    logger.warning(
        "Adjusted TTS generation length: requested TTS_MAX_LENGTH=%s, "
        "effective=%s, context=%s, min_generation=%s. "
        "Use TTS_MAX_TEXT_CHARS to limit text length, not TTS_MAX_LENGTH.",
        REQUESTED_TTS_MAX_LENGTH,
        EFFECTIVE_TTS_MAX_LENGTH,
        TTS_CONTEXT_SIZE,
        MIN_TTS_GENERATION_LENGTH,
    )

TTS_N_BATCH = env_int("TTS_N_BATCH", 256, minimum=1)
TTS_THREADS = env_int("TTS_THREADS", 4, minimum=1)
TTS_TEMPERATURE = float(os.getenv("TTS_TEMPERATURE", "0.4"))
TTS_REPETITION_PENALTY = float(os.getenv("TTS_REPETITION_PENALTY", "1.1"))
MAX_CONCURRENT_SYNTHESIS = env_int("TTS_MAX_CONCURRENT_SYNTHESIS", 1, minimum=1)
TTS_WORKER_COUNT = env_int("TTS_WORKER_COUNT", 1, minimum=1)
TTS_MIN_TEXT_CHARS = env_int("TTS_MIN_TEXT_CHARS", 4, minimum=1)
TTS_MAX_TEXT_CHARS = env_int("TTS_MAX_TEXT_CHARS", 220, minimum=TTS_MIN_TEXT_CHARS)
TTS_GENERATION_RETRIES = env_int("TTS_GENERATION_RETRIES", 1, minimum=1)
TTS_RESET_LLAMA_STATE = os.getenv("TTS_RESET_LLAMA_STATE", "1").lower() not in {
    "0",
    "false",
    "no",
    "off",
}

SPEAKER_DIR = Path(os.getenv("SPEAKER_DIR", "/app/speakers"))
SPEAKER_DIR.mkdir(parents=True, exist_ok=True)

synthesis_semaphore = asyncio.Semaphore(MAX_CONCURRENT_SYNTHESIS)

# One global OuteTTS Interface owns one llama.cpp model/context. Treat it as
# process-global mutable CUDA state inside the generation worker process.
tts_interface_lock = threading.RLock()


def sanitize_speaker_id(speaker_id: str) -> str:
    speaker_id = (speaker_id or "default").strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", speaker_id):
        raise ValueError("speaker_id may only contain letters, numbers, dots, underscores, and hyphens")
    return speaker_id


def speaker_path_inside_dir(path: Path) -> Path:
    root = SPEAKER_DIR.resolve()
    resolved = path.resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError(f"Speaker WAV path must be inside {root}: {resolved}")
    return resolved


def normalize_tts_text(text: str) -> str:
    text = (text or "").strip()
    text = text.replace("```", " ").replace("`", " ").replace("**", " ")
    text = re.sub(r"[*_#>\[\]{}|]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    if len(text) > TTS_MAX_TEXT_CHARS:
        cut = text[:TTS_MAX_TEXT_CHARS]
        last_punct = max(
            cut.rfind("."),
            cut.rfind("!"),
            cut.rfind("?"),
            cut.rfind("。"),
            cut.rfind("！"),
            cut.rfind("？"),
            cut.rfind(","),
            cut.rfind("，"),
        )
        text = cut[: last_punct + 1] if last_punct >= 40 else cut
    return text.strip()


def is_valid_tts_text(text: str) -> bool:
    text = normalize_tts_text(text)
    if len(text) < TTS_MIN_TEXT_CHARS:
        return False
    if re.fullmatch(r"\d+[\.)]?", text):
        return False
    return any(ch.isalnum() or "\u4e00" <= ch <= "\u9fff" for ch in text)


def get_model_version():
    if MODEL_SIZE == "1B":
        logger.info("Using OuteTTS 1B model")
        return Models.VERSION_1_0_SIZE_1B
    logger.info("Using OuteTTS 0.6B model")
    return Models.VERSION_1_0_SIZE_0_6B


def get_quantization():
    mapping = {
        "FP16": LlamaCppQuantization.FP16,
        "Q8_0": LlamaCppQuantization.Q8_0,
        "Q6_K": LlamaCppQuantization.Q6_K,
        "Q5_K_M": LlamaCppQuantization.Q5_K_M,
        "Q4_K_M": LlamaCppQuantization.Q4_K_M,
    }
    return mapping.get(QUANTIZATION_NAME.upper(), LlamaCppQuantization.FP16)


def log_llama_cpp_backend():
    try:
        from llama_cpp import llama_cpp

        info = llama_cpp.llama_print_system_info().decode(errors="ignore")
        logger.info("llama.cpp system info:\n%s", info)
        upper = info.upper()
        if "CUDA" not in upper and "CUBLAS" not in upper:
            logger.warning("llama-cpp-python appears to be CPU-only")
        else:
            logger.info("llama-cpp-python CUDA backend detected")
    except Exception as exc:
        logger.warning("Failed to print llama.cpp system info: %s", exc)


def build_model_config():
    logger.info(
        "Loading OuteTTS model: size=%s quantization=%s n_gpu_layers=%s "
        "n_ctx=%s requested_max_length=%s effective_max_length=%s "
        "min_generation_length=%s n_batch=%s n_threads=%s max_text_chars=%s",
        MODEL_SIZE,
        QUANTIZATION_NAME,
        TTS_N_GPU_LAYERS,
        TTS_CONTEXT_SIZE,
        REQUESTED_TTS_MAX_LENGTH,
        EFFECTIVE_TTS_MAX_LENGTH,
        MIN_TTS_GENERATION_LENGTH,
        TTS_N_BATCH,
        TTS_THREADS,
        TTS_MAX_TEXT_CHARS,
    )

    cfg = outetts.ModelConfig.auto_config(
        model=get_model_version(),
        backend=Backend.LLAMACPP,
        quantization=get_quantization(),
    )
    sources = resolve_model_sources(MODEL_SIZE, QUANTIZATION_NAME)
    apply_model_sources(cfg, sources)
    logger.info(
        "Using pinned OuteTTS sources: tokenizer=%s@%s gguf=%s@%s file=%s",
        sources.tokenizer_repo,
        sources.tokenizer_revision,
        sources.gguf_repo,
        sources.gguf_revision,
        sources.gguf_filename,
    )
    cfg.n_gpu_layers = TTS_N_GPU_LAYERS
    cfg.max_seq_length = TTS_CONTEXT_SIZE
    cfg.device = "cuda"
    cfg.verbose = True

    # Do not duplicate OuteTTS top-level fields here. OuteTTS already passes
    # cfg.n_gpu_layers, cfg.max_seq_length, and cfg.verbose into llama-cpp-python.
    cfg.additional_model_config = {
        "n_batch": TTS_N_BATCH,
        "n_threads": TTS_THREADS,
        "main_gpu": 0,
    }
    logger.info("OuteTTS additional_model_config=%s", cfg.additional_model_config)
    logger.info("OuteTTS cfg.n_gpu_layers=%s", getattr(cfg, "n_gpu_layers", None))
    return cfg


def load_audio_with_soundfile(path: str, target_sr: int) -> torch.Tensor:
    """Load speaker reference audio without torchaudio/torchcodec."""
    wav, sr = sf.read(path, dtype="float32", always_2d=False)
    if wav.size == 0:
        raise ValueError(f"Audio file is empty: {path}")
    if wav.ndim == 2:
        wav = wav.mean(axis=1)
    wav = np.asarray(wav, dtype=np.float32)

    if sr != target_sr:
        if sr <= 0 or target_sr <= 0:
            raise ValueError(f"Invalid resample rates from sr={sr} to target_sr={target_sr}")
        gcd = math.gcd(int(sr), int(target_sr))
        wav = signal.resample_poly(wav, int(target_sr // gcd), int(sr // gcd)).astype(np.float32)

    peak = float(np.max(np.abs(wav))) if wav.size else 0.0
    if peak > 1.0:
        wav = wav / peak

    # OuteTTS speaker creation expects [channels, samples].
    return torch.from_numpy(wav).float().unsqueeze(0)


def patch_audio_loader(tts_interface: Interface):
    """Patch OuteTTS audio loader to avoid torchaudio/torchcodec."""
    target_sr = int(getattr(tts_interface.audio_codec, "sr", 24000))

    def load_audio_without_torchcodec(self, path):
        return load_audio_with_soundfile(path, target_sr=target_sr)

    tts_interface.audio_codec.load_audio = types.MethodType(
        load_audio_without_torchcodec,
        tts_interface.audio_codec,
    )
    logger.info(
        "Patched OuteTTS speaker audio loader: soundfile/scipy instead of "
        "torchaudio/torchcodec. target_sr=%s",
        target_sr,
    )


@contextlib.contextmanager
def patch_torch_1d_audio_slice():
    """Work around an OuteTTS speaker-creation edge case."""
    original_getitem = torch.Tensor.__getitem__

    def safe_getitem(self, index):
        if (
            self.dim() == 1
            and isinstance(index, tuple)
            and len(index) == 2
            and isinstance(index[0], slice)
            and index[0].start is None
            and index[0].stop is None
            and index[0].step is None
            and isinstance(index[1], slice)
        ):
            return original_getitem(self, index[1]).unsqueeze(0)
        return original_getitem(self, index)

    torch.Tensor.__getitem__ = safe_getitem
    try:
        yield
    finally:
        torch.Tensor.__getitem__ = original_getitem


def save_speaker_json(speaker, output_json: Path):
    """Save speaker profile safely despite OuteTTS path suffix behavior."""
    output_json.parent.mkdir(parents=True, exist_ok=True)
    tmp_base = output_json.parent / f".{output_json.stem}.tmp"
    tmp_candidates = [
        tmp_base,
        tmp_base.with_suffix(".json"),
        Path(str(tmp_base) + ".json"),
    ]
    for candidate in tmp_candidates:
        if candidate.exists():
            candidate.unlink()

    with tts_interface_lock:
        interface.save_speaker(speaker, str(tmp_base))

    created_json = None
    for candidate in tmp_candidates:
        if candidate.exists():
            created_json = candidate
            break
    if created_json is None:
        raise FileNotFoundError(f"OuteTTS did not create speaker JSON near {tmp_base}")

    with created_json.open("r", encoding="utf-8") as file:
        json.load(file)
    if output_json.exists():
        output_json.unlink()
    created_json.replace(output_json)
    logger.info("Speaker saved to %s", output_json)


def create_speaker_profile_from_wav(speaker_id: str, wav_path: Path, save_as_default: bool = False):
    if not wav_path.exists():
        raise FileNotFoundError(f"Speaker WAV not found: {wav_path}")

    speaker_id = sanitize_speaker_id(speaker_id)
    output_json = SPEAKER_DIR / f"{speaker_id}.json"
    logger.info("Creating speaker profile speaker_id=%s wav=%s", speaker_id, wav_path)

    with tts_interface_lock:
        with patch_torch_1d_audio_slice():
            speaker = interface.create_speaker(str(wav_path))
        save_speaker_json(speaker, output_json)

    if save_as_default and speaker_id != "default":
        default_json = SPEAKER_DIR / "default.json"
        save_speaker_json(speaker, default_json)

    speakers_cache[speaker_id] = speaker
    if save_as_default:
        speakers_cache["default"] = speaker
    return speaker


# The model is initialized only in the restartable generation subprocess. This
# lets websocket cancellation terminate native OuteTTS/llama.cpp work rather
# than leaving stale generation on the sole worker.
interface: Interface | None = None


def reset_llama_generation_state() -> None:
    """Clear llama-cpp-python prompt/KV reuse state between independent TTS jobs."""
    if not TTS_RESET_LLAMA_STATE:
        return
    try:
        if interface is None:
            return
        llama = getattr(getattr(interface, "model", None), "model", None)
        reset = getattr(llama, "reset", None)
        if callable(reset):
            reset()
    except Exception as exc:
        logger.debug("Could not reset llama generation state: %s", exc)


def generate_tts_sync(cfg: GenerationConfig):
    """Run OuteTTS generation under a process-wide interface lock."""
    if interface is None:
        raise RuntimeError("TTS interface is not initialized")
    with tts_interface_lock:
        reset_llama_generation_state()
        try:
            return interface.generate(config=cfg)
        finally:
            reset_llama_generation_state()

def load_default_speaker():
    if interface is None:
        raise RuntimeError("TTS interface is not initialized")
    speaker_json = SPEAKER_DIR / "default.json"
    speaker_wav = SPEAKER_DIR / "default.wav"

    if speaker_json.exists():
        logger.info("Loading default speaker from %s", speaker_json)
        with tts_interface_lock:
            return interface.load_speaker(str(speaker_json))

    if speaker_wav.exists():
        logger.info("Creating default speaker from %s", speaker_wav)
        return create_speaker_profile_from_wav("default", speaker_wav, save_as_default=False)

    logger.warning("No default speaker found, using built-in EN-FEMALE-1-NEUTRAL")
    with tts_interface_lock:
        return interface.load_default_speaker("EN-FEMALE-1-NEUTRAL")


def audio_to_pcm16(audio) -> bytes:
    if audio is None:
        return b""
    if hasattr(audio, "detach"):
        audio = audio.detach().cpu().numpy()
    elif hasattr(audio, "cpu"):
        audio = audio.cpu().numpy()
    audio = np.asarray(audio, dtype=np.float32).reshape(-1)
    if audio.size == 0:
        return b""
    peak = float(np.max(np.abs(audio)))
    if peak > 1.0:
        audio = audio / peak
    return (np.clip(audio, -1.0, 1.0) * 32767.0).astype(np.int16).tobytes()


def get_or_load_speaker(speaker_id: str):
    if interface is None:
        raise RuntimeError("TTS interface is not initialized")
    speaker_id = sanitize_speaker_id(speaker_id)
    if speaker_id in speakers_cache:
        return speakers_cache[speaker_id]

    speaker_json = SPEAKER_DIR / f"{speaker_id}.json"
    speaker_wav = SPEAKER_DIR / f"{speaker_id}.wav"

    if speaker_json.exists():
        logger.info("Loading speaker_id=%s from %s", speaker_id, speaker_json)
        with tts_interface_lock:
            speaker = interface.load_speaker(str(speaker_json))
        speakers_cache[speaker_id] = speaker
        return speaker

    if speaker_wav.exists():
        logger.info("Creating speaker_id=%s from %s", speaker_id, speaker_wav)
        return create_speaker_profile_from_wav(speaker_id, speaker_wav, save_as_default=False)

    return None


def list_speaker_ids():
    ids = {"default"}
    for path in SPEAKER_DIR.glob("*.json"):
        ids.add(path.stem)
    for path in SPEAKER_DIR.glob("*.wav"):
        ids.add(path.stem)
    ids.update(speakers_cache.keys())
    return sorted(ids)


# Speaker state is populated inside the generation subprocess.
speakers_cache: dict[str, object] = {}
default_speaker = None


def generation_worker_main(connection) -> None:
    """Own the mutable model in a process that can be terminated on cancel."""
    global interface, speakers_cache, default_speaker

    try:
        logger.info("Initializing TTS interface in generation worker")
        log_llama_cpp_backend()
        interface = Interface(config=build_model_config())
        patch_audio_loader(interface)
        speakers_cache = {}
        default_speaker = load_default_speaker()
        speakers_cache["default"] = default_speaker
        logger.info("TTS model loaded in generation worker")
        connection.send({"type": "ready"})
    except Exception as exc:
        logger.error("TTS generation worker failed to initialize: %s", exc, exc_info=True)
        try:
            connection.send({"type": "startup_error", "message": str(exc)})
        finally:
            connection.close()
        return

    try:
        while True:
            command = connection.recv()
            command_type = command.get("type") if isinstance(command, dict) else None
            if command_type == "shutdown":
                connection.send({"type": "stopped"})
                return

            try:
                if command_type == "generate":
                    speaker_id = sanitize_speaker_id(command.get("speaker_id", "default"))
                    speaker = get_or_load_speaker(speaker_id)
                    if speaker is None:
                        raise ValueError(f"Speaker not found: {speaker_id}")
                    cfg = GenerationConfig(
                        text=str(command.get("text") or ""),
                        generation_type=outetts.GenerationType.CHUNKED,
                        speaker=speaker,
                        sampler_config=SamplerConfig(
                            temperature=TTS_TEMPERATURE,
                            repetition_penalty=TTS_REPETITION_PENALTY,
                        ),
                        max_length=EFFECTIVE_TTS_MAX_LENGTH,
                    )
                    started = time.time()
                    output = generate_tts_sync(cfg)
                    connection.send(
                        {
                            "type": "generated",
                            "pcm": audio_to_pcm16(getattr(output, "audio", None)),
                            "generate_seconds": time.time() - started,
                        }
                    )
                    continue

                if command_type == "create_speaker":
                    speaker_id = sanitize_speaker_id(command.get("speaker_id", "default"))
                    wav_path = speaker_path_inside_dir(Path(command["wav_path"]))
                    make_default = bool(command.get("make_default", False))
                    create_speaker_profile_from_wav(
                        speaker_id,
                        wav_path,
                        save_as_default=make_default,
                    )
                    connection.send(
                        {
                            "type": "speaker_created",
                            "speaker_id": speaker_id,
                            "speaker_json": str(SPEAKER_DIR / f"{speaker_id}.json"),
                            "make_default": make_default,
                        }
                    )
                    continue

                raise ValueError(f"Unknown generation-worker command: {command_type}")
            except Exception as exc:
                logger.error(
                    "TTS generation worker command failed type=%s error=%s",
                    command_type,
                    exc,
                    exc_info=True,
                )
                connection.send({"type": "error", "message": str(exc)})
    except (EOFError, BrokenPipeError, OSError):
        logger.info("TTS generation worker connection closed")
    finally:
        connection.close()


generation_workers = [
    RestartableProcessWorker(
        generation_worker_main,
        name=f"chromie-tts-generation-{index}",
        startup_timeout_s=float(os.getenv("TTS_WORKER_STARTUP_TIMEOUT_SEC", "600")),
    )
    for index in range(TTS_WORKER_COUNT)
]
generation_worker_cursor = 0
generation_worker_select_lock: asyncio.Lock | None = None


def generation_worker_lock() -> asyncio.Lock:
    global generation_worker_select_lock
    if generation_worker_select_lock is None:
        generation_worker_select_lock = asyncio.Lock()
    return generation_worker_select_lock


async def select_generation_worker() -> tuple[int, RestartableProcessWorker]:
    global generation_worker_cursor
    async with generation_worker_lock():
        index = generation_worker_cursor % len(generation_workers)
        generation_worker_cursor += 1
        return index, generation_workers[index]


def generation_worker_status() -> list[dict[str, object]]:
    return [
        {
            "index": index,
            "alive": worker.is_alive,
            "restart_count": worker.restart_count,
        }
        for index, worker in enumerate(generation_workers)
    ]


async def start_generation_workers() -> None:
    await asyncio.gather(*(worker.start() for worker in generation_workers))


async def stop_generation_workers() -> None:
    await asyncio.gather(
        *(worker.stop() for worker in generation_workers),
        return_exceptions=True,
    )


async def send_json(ws, payload):
    await ws.send(json.dumps(payload, ensure_ascii=False))


async def synthesize_text(
    text: str,
    speaker_id: str,
    ws,
    request_id: Optional[str] = None,
):
    async with synthesis_semaphore:
        text = normalize_tts_text(text)
        if not is_valid_tts_text(text):
            logger.warning("Skipping invalid TTS text request_id=%s text=%r", request_id, text)
            await send_json(ws, {"type": "end", "request_id": request_id})
            return

        if text[-1] not in ".!?。！？":
            text += "."

        logger.info("TTS input request_id=%s text=%r", request_id, text)
        start_time = time.time()
        last_error = None

        await send_json(
            ws,
            {
                "type": "start",
                "request_id": request_id,
                "sample_rate": TTS_SAMPLE_RATE,
                "format": "pcm_s16le",
                "channels": 1,
                "max_length": EFFECTIVE_TTS_MAX_LENGTH,
            },
        )

        for attempt in range(1, TTS_GENERATION_RETRIES + 1):
            try:
                worker_index, worker = await select_generation_worker()
                response = await worker.request(
                    {
                        "type": "generate",
                        "text": text,
                        "speaker_id": speaker_id,
                    }
                )
                if response.get("type") == "error":
                    raise RuntimeError(str(response.get("message") or "generation failed"))
                if response.get("type") != "generated":
                    raise RuntimeError(
                        f"Unexpected generation-worker response: {response.get('type')!r}"
                    )
                pcm = response.get("pcm") or b""
                generate_seconds = float(response.get("generate_seconds") or 0.0)
                if not pcm:
                    raise RuntimeError(
                        "OuteTTS generated empty audio. "
                        f"effective_max_length={EFFECTIVE_TTS_MAX_LENGTH}, "
                        f"text_chars={len(text)}. Do not set TTS_MAX_LENGTH too low; "
                        "use TTS_MAX_TEXT_CHARS to shorten spoken text."
                    )

                chunk_bytes = int(TTS_SAMPLE_RATE * TTS_CHUNK_MS / 1000) * 2
                for offset in range(0, len(pcm), chunk_bytes):
                    await ws.send(pcm[offset : offset + chunk_bytes])
                    await asyncio.sleep(0)

                audio_seconds = len(pcm) / (TTS_SAMPLE_RATE * 2)
                await send_json(
                    ws,
                    {
                        "type": "end",
                        "request_id": request_id,
                        "audio_seconds": audio_seconds,
                        "generate_seconds": generate_seconds,
                        "total_seconds": time.time() - start_time,
                    },
                )
                logger.info(
                    "TTS done request_id=%s worker=%s attempt=%s audio=%.2fs generate=%.2fs total=%.2fs",
                    request_id,
                    worker_index,
                    attempt,
                    audio_seconds,
                    generate_seconds,
                    time.time() - start_time,
                )
                return
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "TTS generation failed request_id=%s attempt=%s/%s text=%r error=%s",
                    request_id,
                    attempt,
                    TTS_GENERATION_RETRIES,
                    text,
                    exc,
                    exc_info=True,
                )
                await asyncio.sleep(0.05)

        await send_json(
            ws,
            {
                "type": "error",
                "request_id": request_id,
                "message": f"TTS generated no audio after retries: {last_error}",
            },
        )


async def handle_create_speaker(data: dict, ws):
    request_id = data.get("request_id")
    speaker_id = data.get("speaker_id") or "default"
    wav_path = data.get("wav_path")
    make_default = bool(data.get("make_default", False))

    try:
        speaker_id = sanitize_speaker_id(speaker_id)
        wav_path = speaker_path_inside_dir(Path(wav_path) if wav_path else SPEAKER_DIR / f"{speaker_id}.wav")
        response = await generation_workers[0].request(
            {
                "type": "create_speaker",
                "speaker_id": speaker_id,
                "wav_path": str(wav_path),
                "make_default": make_default,
            }
        )
        if response.get("type") == "error":
            raise RuntimeError(str(response.get("message") or "speaker creation failed"))
        if response.get("type") != "speaker_created":
            raise RuntimeError(
                f"Unexpected generation-worker response: {response.get('type')!r}"
            )

        await send_json(
            ws,
            {
                "type": "speaker_created",
                "request_id": request_id,
                "speaker_id": speaker_id,
                "speaker_json": str(SPEAKER_DIR / f"{speaker_id}.json"),
                "make_default": make_default,
            },
        )
    except Exception as exc:
        logger.error("Speaker creation failed: %s", exc, exc_info=True)
        await send_json(
            ws,
            {
                "type": "error",
                "request_id": request_id,
                "message": f"Speaker creation failed: {exc}",
            },
        )


async def ws_handler(ws):
    logger.info("New TTS websocket connection")
    active_tasks = set()
    try:
        async for msg in ws:
            if not isinstance(msg, str):
                continue
            try:
                data = json.loads(msg)
            except Exception:
                await send_json(ws, {"type": "error", "message": "Invalid JSON"})
                continue

            msg_type = data.get("type")
            if msg_type in {"health", "ping"}:
                await send_json(
                    ws,
                    {
                        "type": "pong",
                        "service": "tts",
                        "sample_rate": TTS_SAMPLE_RATE,
                        "gpu_layers": TTS_N_GPU_LAYERS,
                        "reset_llama_state": TTS_RESET_LLAMA_STATE,
                        "single_model_worker": TTS_WORKER_COUNT == 1,
                        "worker_count": TTS_WORKER_COUNT,
                        "max_concurrent_synthesis": MAX_CONCURRENT_SYNTHESIS,
                        "worker_process_alive": all(
                            worker.is_alive for worker in generation_workers
                        ),
                        "worker_restart_count": sum(
                            worker.restart_count for worker in generation_workers
                        ),
                        "workers": generation_worker_status(),
                        "cancellation_mode": "terminate_and_restart_worker",
                        "requested_max_length": REQUESTED_TTS_MAX_LENGTH,
                        "effective_max_length": EFFECTIVE_TTS_MAX_LENGTH,
                        "min_generation_length": MIN_TTS_GENERATION_LENGTH,
                        "max_text_chars": TTS_MAX_TEXT_CHARS,
                        "speakers": list_speaker_ids(),
                    },
                )
                continue

            if msg_type == "list_speakers":
                await send_json(ws, {"type": "speakers", "speakers": list_speaker_ids()})
                continue

            if msg_type == "create_speaker":
                task = asyncio.create_task(handle_create_speaker(data, ws))
                active_tasks.add(task)
                task.add_done_callback(active_tasks.discard)
                continue

            if msg_type != "synthesize_stream":
                await send_json(ws, {"type": "error", "message": f"Unknown message type: {msg_type}"})
                continue

            try:
                speaker_id = sanitize_speaker_id(data.get("speaker_id", "default"))
            except ValueError as exc:
                await send_json(
                    ws,
                    {
                        "type": "error",
                        "request_id": data.get("request_id"),
                        "message": str(exc),
                    },
                )
                continue

            if speaker_id != "default" and not (
                (SPEAKER_DIR / f"{speaker_id}.json").exists()
                or (SPEAKER_DIR / f"{speaker_id}.wav").exists()
            ):
                await send_json(
                    ws,
                    {
                        "type": "error",
                        "request_id": data.get("request_id"),
                        "message": "Speaker not found",
                    },
                )
                continue

            task = asyncio.create_task(
                synthesize_text(
                    data.get("text", ""),
                    speaker_id,
                    ws,
                    data.get("request_id"),
                )
            )
            active_tasks.add(task)
            task.add_done_callback(active_tasks.discard)
    except websockets.exceptions.ConnectionClosed:
        logger.info("TTS websocket closed")
    finally:
        for task in active_tasks:
            task.cancel()
        if active_tasks:
            await asyncio.gather(*active_tasks, return_exceptions=True)


async def main():
    await start_generation_workers()
    logger.info(
        "TTS server ready on ws://%s:%s output=%sHz pcm_s16le chunk_ms=%s "
        "effective_max_length=%s max_text_chars=%s worker_count=%s max_concurrent=%s",
        HOST,
        PORT,
        TTS_SAMPLE_RATE,
        TTS_CHUNK_MS,
        EFFECTIVE_TTS_MAX_LENGTH,
        TTS_MAX_TEXT_CHARS,
        TTS_WORKER_COUNT,
        MAX_CONCURRENT_SYNTHESIS,
    )
    try:
        async with websockets.serve(
            ws_handler,
            HOST,
            PORT,
            max_size=10**7,
            ping_interval=20,
            ping_timeout=20,
        ):
            await asyncio.Future()
    finally:
        await stop_generation_workers()


if __name__ == "__main__":
    asyncio.run(main())
