# Chromie optimization notes

This pass keeps the current architecture intact and focuses on safe latency, reliability, and hygiene improvements.

## Changed

- Lower time-to-first-audio by flushing the first complete streamed LLM sentence to TTS immediately.
- Replaced FFT-style audio resampling with polyphase resampling for host playback and speaker-reference conversion.
- Disabled raw audio saves by default with `ORCH_SAVE_AUDIO=false`. Turn it on only for debugging.
- Added ASR environment knobs for beam size, internal VAD, and previous-text conditioning.
- Hardened TTS speaker creation by validating `speaker_id` and requiring WAV paths to stay inside `SPEAKER_DIR`.
- Improved Docker Compose reliability with `init: true` and service healthchecks.
- Removed the production `./tts/server.py:/app/server.py` bind mount so the built image is reproducible.
- Added `.dockerignore` files for ASR and TTS build contexts.
- Improved `scripts/start_services.sh`: required folders are created, named services are rebuilt, and log following is opt-in via `FOLLOW_LOGS=1`.


## RTX4090 Laptop TTS GPU fix

- `.env` now uses `TTS_CUDA_ARCH=89`, `TTS_N_GPU_LAYERS=-1`, `NVIDIA_VISIBLE_DEVICES=all`, and `NVIDIA_DRIVER_CAPABILITIES=compute,utility`.
- `docker-compose.yml` now exposes NVIDIA GPUs with both `gpus: all` and explicit device reservations.
- `tts/Dockerfile` uses CUDA stubs only while compiling `llama-cpp-python`; the final runtime `LD_LIBRARY_PATH` excludes `/usr/local/cuda/lib64/stubs`.
- `tts/server.py` and `tts/create_speaker.py` now force the OuteTTS llama.cpp config toward CUDA with `cfg.device = "cuda"`, `n_gpu_layers=-1`, `main_gpu=0`, and verbose llama.cpp logs.
- Use `REBUILD_NO_CACHE=1 ./scripts/start_services.sh` or `docker compose build --no-cache chromie-tts` after changing CUDA build settings.

## Validation performed

- Python syntax compile passed for ASR, TTS, speaker helper, and orchestrator files.
- Shell syntax check passed for all helper scripts.
- Docker Compose YAML parsed successfully. Docker itself was not available in this sandbox, so container build/runtime checks were not executed here.

## Next runtime checks on the target machine

```bash
./scripts/start_services.sh
docker compose ps
./scripts/verify_tts_gpu.sh
./scripts/warm_ollama.sh
cd orchestrator && source .venv/bin/activate && python orchestrator.py
```

To watch startup logs during service start:

```bash
FOLLOW_LOGS=1 ./scripts/start_services.sh
```
