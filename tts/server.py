import asyncio
import contextlib
import json
import logging
import math
import os
import re
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

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("chromie-tts")

HOST = os.getenv("TTS_HOST", "0.0.0.0")
PORT = int(os.getenv("TTS_PORT", "5000"))
MODEL_SIZE = os.getenv("TTS_MODEL_SIZE", "0.6B")
QUANTIZATION_NAME = os.getenv("TTS_QUANTIZATION", "FP16")

# This is the raw PCM sample rate reported to orchestrator.
# Orchestrator will resample this source rate to the real speaker output rate.
TTS_SAMPLE_RATE = int(os.getenv("TTS_SAMPLE_RATE", "44100"))
TTS_CHUNK_MS = int(os.getenv("TTS_CHUNK_MS", "120"))

TTS_N_GPU_LAYERS = int(os.getenv("TTS_N_GPU_LAYERS", "-1"))
TTS_CONTEXT_SIZE = int(os.getenv("TTS_CONTEXT_SIZE", "4096"))
TTS_MAX_LENGTH = int(os.getenv("TTS_MAX_LENGTH", "4096"))
TTS_N_BATCH = int(os.getenv("TTS_N_BATCH", "256"))
TTS_THREADS = int(os.getenv("TTS_THREADS", "4"))
TTS_TEMPERATURE = float(os.getenv("TTS_TEMPERATURE", "0.4"))
TTS_REPETITION_PENALTY = float(os.getenv("TTS_REPETITION_PENALTY", "1.1"))
MAX_CONCURRENT_SYNTHESIS = int(os.getenv("TTS_MAX_CONCURRENT_SYNTHESIS", "1"))
TTS_MIN_TEXT_CHARS = int(os.getenv("TTS_MIN_TEXT_CHARS", "4"))
TTS_MAX_TEXT_CHARS = int(os.getenv("TTS_MAX_TEXT_CHARS", "220"))
TTS_GENERATION_RETRIES = max(1, int(os.getenv("TTS_GENERATION_RETRIES", "2")))
SPEAKER_DIR = Path(os.getenv("SPEAKER_DIR", "/app/speakers"))
SPEAKER_DIR.mkdir(parents=True, exist_ok=True)

synthesis_semaphore = asyncio.Semaphore(MAX_CONCURRENT_SYNTHESIS)

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
        "n_ctx=%s max_length=%s n_batch=%s n_threads=%s",
        MODEL_SIZE,
        QUANTIZATION_NAME,
        TTS_N_GPU_LAYERS,
        TTS_CONTEXT_SIZE,
        min(TTS_MAX_LENGTH, TTS_CONTEXT_SIZE),
        TTS_N_BATCH,
        TTS_THREADS,
    )

    cfg = outetts.ModelConfig.auto_config(
        model=get_model_version(),
        backend=Backend.LLAMACPP,
        quantization=get_quantization(),
    )

    cfg.n_gpu_layers = TTS_N_GPU_LAYERS
    cfg.max_seq_length = TTS_CONTEXT_SIZE
    cfg.device = "cuda"
    cfg.verbose = True
    
    # Do not duplicate OuteTTS top-level fields here.
    # OuteTTS already passes cfg.n_gpu_layers, cfg.max_seq_length, and cfg.verbose
    # into llama-cpp-python internally.
    cfg.additional_model_config = {
        "n_batch": TTS_N_BATCH,
        "n_threads": TTS_THREADS,
        "main_gpu": 0,
    }

    logger.info("OuteTTS additional_model_config=%s", cfg.additional_model_config)
    logger.info("OuteTTS cfg.n_gpu_layers=%s", getattr(cfg, "n_gpu_layers", None))
    return cfg


def load_audio_with_soundfile(path: str, target_sr: int) -> torch.Tensor:
    """Load speaker reference audio without torchaudio/torchcodec.

    This avoids the torchcodec -> FFmpeg -> CUDA NPP dependency chain. It is enough
    for normal WAV/FLAC speaker-reference clips.
    """

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
    """Work around an OuteTTS v3 speaker-creation edge case.

    Some OuteTTS versions rebuild speaker audio from raw bytes as a 1D tensor,
    then slice it as audio[:, start:end]. This patch only handles that exact
    pattern and does not interfere with tensor[:, None] used by Whisper.
    """

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


logger.info("Initializing TTS interface")
log_llama_cpp_backend()
interface = Interface(config=build_model_config())
patch_audio_loader(interface)
logger.info("TTS model loaded")


def load_default_speaker():
    speaker_json = SPEAKER_DIR / "default.json"
    speaker_wav = SPEAKER_DIR / "default.wav"

    if speaker_json.exists():
        logger.info("Loading default speaker from %s", speaker_json)
        return interface.load_speaker(str(speaker_json))

    if speaker_wav.exists():
        logger.info("Creating default speaker from %s", speaker_wav)
        return create_speaker_profile_from_wav("default", speaker_wav, save_as_default=False)

    logger.warning("No default speaker found, using built-in EN-FEMALE-1-NEUTRAL")
    return interface.load_default_speaker("EN-FEMALE-1-NEUTRAL")


def audio_to_pcm16(audio) -> bytes:
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
    speaker_id = sanitize_speaker_id(speaker_id)

    if speaker_id in speakers_cache:
        return speakers_cache[speaker_id]

    speaker_json = SPEAKER_DIR / f"{speaker_id}.json"
    speaker_wav = SPEAKER_DIR / f"{speaker_id}.wav"

    if speaker_json.exists():
        logger.info("Loading speaker_id=%s from %s", speaker_id, speaker_json)
        speaker = interface.load_speaker(str(speaker_json))
        speakers_cache[speaker_id] = speaker
        return speaker

    if speaker_wav.exists():
        logger.info("Creating speaker_id=%s from %s", speaker_id, speaker_wav)
        return create_speaker_profile_from_wav(speaker_id, speaker_wav, save_as_default=False)

    return None


def list_speaker_ids():
    ids = set()

    for path in SPEAKER_DIR.glob("*.json"):
        ids.add(path.stem)

    for path in SPEAKER_DIR.glob("*.wav"):
        ids.add(path.stem)

    ids.update(speakers_cache.keys())
    return sorted(ids)


# Speaker cache is used by speaker creation and loading helpers.
speakers_cache = {}

# Load default after helper functions are available.
default_speaker = load_default_speaker()
speakers_cache["default"] = default_speaker


async def send_json(ws, payload):
    await ws.send(json.dumps(payload, ensure_ascii=False))


async def synthesize_text(text: str, speaker, ws, request_id: Optional[str] = None):
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
            },
        )

        for attempt in range(1, TTS_GENERATION_RETRIES + 1):
            try:
                cfg = GenerationConfig(
                    text=text,
                    generation_type=outetts.GenerationType.CHUNKED,
                    speaker=speaker,
                    sampler_config=SamplerConfig(
                        temperature=TTS_TEMPERATURE,
                        repetition_penalty=TTS_REPETITION_PENALTY,
                    ),
                    max_length=min(TTS_MAX_LENGTH, TTS_CONTEXT_SIZE),
                )

                generate_start = time.time()
                output = await asyncio.to_thread(interface.generate, config=cfg)
                generate_seconds = time.time() - generate_start

                pcm = audio_to_pcm16(output.audio)
                if not pcm:
                    raise RuntimeError("OuteTTS generated empty audio")

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
                    "TTS done request_id=%s attempt=%s audio=%.2fs generate=%.2fs total=%.2fs",
                    request_id,
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
        speaker = await asyncio.to_thread(
            create_speaker_profile_from_wav,
            speaker_id,
            wav_path,
            make_default,
        )
        speakers_cache[speaker_id] = speaker
        if make_default:
            speakers_cache["default"] = speaker

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
                speaker = get_or_load_speaker(data.get("speaker_id", "default"))
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
            if speaker is None:
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
                synthesize_text(data.get("text", ""), speaker, ws, data.get("request_id"))
            )
            active_tasks.add(task)
            task.add_done_callback(active_tasks.discard)

    except websockets.exceptions.ConnectionClosed:
        logger.info("TTS websocket closed")
    finally:
        for task in active_tasks:
            task.cancel()


async def main():
    logger.info(
        "TTS server ready on ws://%s:%s output=%sHz pcm_s16le chunk_ms=%s",
        HOST,
        PORT,
        TTS_SAMPLE_RATE,
        TTS_CHUNK_MS,
    )
    async with websockets.serve(
        ws_handler,
        HOST,
        PORT,
        max_size=10**7,
        ping_interval=20,
        ping_timeout=20,
    ):
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
