import argparse
import contextlib
import json
import logging
import math
import os
import shutil
import types
from pathlib import Path

import numpy as np
import outetts
import soundfile as sf
import torch
from outetts import Backend, Interface, LlamaCppQuantization, Models
from scipy import signal

from model_sources import apply_model_sources, resolve_model_sources

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("create-oute-speaker")

MODEL_SIZE = os.getenv("TTS_MODEL_SIZE", "0.6B")
QUANTIZATION_NAME = os.getenv("TTS_QUANTIZATION", "FP16")
TTS_N_GPU_LAYERS = int(os.getenv("TTS_N_GPU_LAYERS", "-1"))
TTS_CONTEXT_SIZE = int(os.getenv("TTS_CONTEXT_SIZE", "4096"))
TTS_N_BATCH = int(os.getenv("TTS_N_BATCH", "256"))
TTS_THREADS = int(os.getenv("TTS_THREADS", "4"))
SPEAKER_DIR = Path(os.getenv("SPEAKER_DIR", "/app/speakers"))


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
    quant = mapping.get(QUANTIZATION_NAME.upper())
    if quant is None:
        logger.warning("Unknown TTS_QUANTIZATION=%s, falling back to FP16", QUANTIZATION_NAME)
        return LlamaCppQuantization.FP16
    return quant


def log_llama_cpp_backend():
    try:
        from llama_cpp import llama_cpp
        info = llama_cpp.llama_print_system_info().decode(errors="ignore")
        logger.info("llama.cpp system info:\n%s", info)
        if "CUDA" in info.upper() or "CUBLAS" in info.upper():
            logger.info("llama-cpp-python CUDA backend detected")
        else:
            logger.warning("llama-cpp-python appears to be CPU-only")
    except Exception as exc:
        logger.warning("Failed to print llama.cpp system info: %s", exc)


def build_model_config():
    logger.info(
        "Building OuteTTS config: size=%s quantization=%s n_gpu_layers=%s n_ctx=%s n_batch=%s n_threads=%s",
        MODEL_SIZE,
        QUANTIZATION_NAME,
        TTS_N_GPU_LAYERS,
        TTS_CONTEXT_SIZE,
        TTS_N_BATCH,
        TTS_THREADS,
    )
    cfg = outetts.ModelConfig.auto_config(model=get_model_version(), backend=Backend.LLAMACPP, quantization=get_quantization())
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
    cfg.additional_model_config = {
        "n_gpu_layers": TTS_N_GPU_LAYERS,
        "n_ctx": TTS_CONTEXT_SIZE,
        "n_batch": TTS_N_BATCH,
        "n_threads": TTS_THREADS,
        "main_gpu": 0,
        "verbose": True,
    }
    return cfg


def validate_input_audio(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"Input audio does not exist: {path}")
    if not path.is_file():
        raise ValueError(f"Input audio is not a file: {path}")
    if path.suffix.lower() not in {".wav", ".flac", ".ogg", ".aiff", ".aif"}:
        logger.warning("Input extension is %s. soundfile may still load it if libsndfile supports it.", path.suffix)


def load_audio_with_soundfile(path: str, target_sr: int) -> torch.Tensor:
    wav, sr = sf.read(path, dtype="float32", always_2d=False)
    if wav.size == 0:
        raise ValueError(f"Audio file is empty: {path}")
    if wav.ndim == 2:
        wav = wav.mean(axis=1)
    wav = np.asarray(wav, dtype=np.float32)
    if sr != target_sr:
        gcd = math.gcd(int(sr), int(target_sr))
        wav = signal.resample_poly(wav, int(target_sr // gcd), int(sr // gcd)).astype(np.float32)
    peak = float(np.max(np.abs(wav))) if wav.size else 0.0
    if peak > 1.0:
        wav = wav / peak
    # Match OuteTTS DacInterface.load_audio: [batch, channels, samples].
    # A two-dimensional tensor is collapsed to one sample by OuteTTS's
    # loudness normalizer and creates a malformed one-token speaker profile.
    return torch.from_numpy(wav).float().unsqueeze(0).unsqueeze(0)


def patch_audio_loader(interface: Interface):
    target_sr = int(getattr(interface.audio_codec, "sr", 24000))

    def load_audio_without_torchcodec(self, path):
        return load_audio_with_soundfile(path, target_sr=target_sr)

    interface.audio_codec.load_audio = types.MethodType(load_audio_without_torchcodec, interface.audio_codec)
    logger.info("Patched OuteTTS audio loader: soundfile/scipy instead of torchaudio/torchcodec. target_sr=%s", target_sr)


@contextlib.contextmanager
def patch_torch_1d_audio_slice():
    """Only patch OuteTTS's accidental 1D audio[:, start:end] slice pattern."""
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


def atomic_save_speaker(interface: Interface, speaker, output_json: Path):
    output_json.parent.mkdir(parents=True, exist_ok=True)
    tmp_base = output_json.parent / f".{output_json.stem}.tmp"
    candidates_to_remove = {
        tmp_base,
        tmp_base.with_suffix(".json"),
        Path(str(tmp_base) + ".json"),
        Path(str(output_json) + ".tmp"),
        Path(str(output_json) + ".tmp.json"),
    }
    for candidate in candidates_to_remove:
        if candidate.exists():
            candidate.unlink()
    interface.save_speaker(speaker, str(tmp_base))
    candidates = [tmp_base, tmp_base.with_suffix(".json"), Path(str(tmp_base) + ".json"), Path(str(output_json) + ".tmp.json")]
    created_json = None
    for candidate in candidates:
        if candidate.exists():
            created_json = candidate
            break
    if created_json is None:
        raise FileNotFoundError(f"OuteTTS save_speaker did not create expected temp JSON near: {tmp_base}")
    with created_json.open("r", encoding="utf-8") as file:
        json.load(file)
    if output_json.exists():
        output_json.unlink()
    created_json.replace(output_json)


def create_speaker(input_audio: Path, output_json: Path, make_default: bool):
    validate_input_audio(input_audio)
    SPEAKER_DIR.mkdir(parents=True, exist_ok=True)
    log_llama_cpp_backend()
    logger.info("Loading OuteTTS interface")
    interface = Interface(config=build_model_config())
    patch_audio_loader(interface)
    logger.info("Creating speaker profile from audio: %s", input_audio)
    with patch_torch_1d_audio_slice():
        speaker = interface.create_speaker(str(input_audio))
    logger.info("Saving speaker profile JSON: %s", output_json)
    atomic_save_speaker(interface, speaker, output_json)
    if make_default:
        default_json = output_json.parent / "default.json"
        shutil.copy2(output_json, default_json)
        logger.info("Copied speaker profile to default speaker: %s", default_json)
    logger.info("Done")
    logger.info("Speaker JSON: %s", output_json)


def parse_args():
    parser = argparse.ArgumentParser(description="Create an OuteTTS speaker profile JSON from reference audio.")
    parser.add_argument("--input", "-i", required=True, help="Path to reference audio, e.g. /app/speakers/chromie_voice.wav")
    parser.add_argument("--speaker-id", "-s", default="chromie_voice", help="Speaker ID / output JSON basename")
    parser.add_argument("--output", "-o", default=None, help="Optional output JSON path")
    parser.add_argument("--make-default", action="store_true", help="Also copy output JSON to /app/speakers/default.json")
    parser.add_argument("--test-load-only", action="store_true", help="Only test soundfile loading/resampling")
    return parser.parse_args()


def main():
    args = parse_args()
    input_audio = Path(args.input).expanduser().resolve()
    if args.test_load_only:
        validate_input_audio(input_audio)
        audio = load_audio_with_soundfile(str(input_audio), target_sr=24000)
        logger.info("Audio load test OK: tensor_shape=%s", tuple(audio.shape))
        return
    output_json = Path(args.output).expanduser().resolve() if args.output else SPEAKER_DIR / f"{args.speaker_id}.json"
    create_speaker(input_audio=input_audio, output_json=output_json, make_default=args.make_default)


if __name__ == "__main__":
    main()
