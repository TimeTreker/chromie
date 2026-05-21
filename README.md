# Chromie Voice Assistant

This package is configured for an **RTX 4090 Laptop GPU**.

Chromie runs a local real-time voice assistant pipeline:

- **ASR**: Faster-Whisper websocket server
- **LLM**: Ollama
- **TTS**: OuteTTS / llama.cpp websocket server
- **Orchestrator**: host-side microphone, VAD, LLM streaming, TTS streaming, playback, session latency logs

## RTX 4090 Laptop GPU defaults

The RTX 4090 Laptop GPU uses the Ada CUDA architecture target:

```env
TTS_CUDA_ARCH=89
```

This build also forces OuteTTS / llama.cpp to use GPU offload:

```env
NVIDIA_VISIBLE_DEVICES=all
NVIDIA_DRIVER_CAPABILITIES=compute,utility
TTS_N_GPU_LAYERS=-1
```

`TTS_N_GPU_LAYERS=-1` means “offload all possible llama.cpp layers to the GPU.” This is preferred over a fixed high value such as `99` because it is model-size independent.

## What is included

```text
asr/                 Faster-Whisper websocket service
tts/                 OuteTTS websocket service with built-in speaker creation
orchestrator/        Host microphone/VAD/LLM/TTS/playback controller
scripts/             Setup, start, GPU check, speaker helper scripts
```

The final TTS design does **not** require `torchcodec`, NVIDIA NPP, or FFmpeg for speaker creation. The server patches OuteTTS speaker audio loading to use:

```text
soundfile + scipy.signal.resample_poly
```

This avoids the `torchaudio -> torchcodec -> FFmpeg -> libnppicc.so.13` dependency chain.

## Important TTS GPU fix in this build

This package includes the accepted fix for the problem where TTS could appear to start but run on CPU instead of the NVIDIA GPU.

Changes included:

- `docker-compose.yml` exposes NVIDIA devices explicitly with `gpus: all`, device reservations, `NVIDIA_VISIBLE_DEVICES=all`, and `NVIDIA_DRIVER_CAPABILITIES=compute,utility`.
- `tts/Dockerfile` still uses CUDA stub libraries while compiling `llama-cpp-python`, but does **not** leave CUDA stubs in the final runtime `LD_LIBRARY_PATH`.
- `.env` uses `TTS_CUDA_ARCH=89` for RTX 4090 Laptop GPU.
- `.env` uses `TTS_N_GPU_LAYERS=-1` so llama.cpp can offload all possible model layers.
- `tts/server.py` and `tts/create_speaker.py` set the OuteTTS llama.cpp config to CUDA and pass `n_gpu_layers=-1`, `main_gpu=0`, and verbose llama.cpp loading logs.

After rebuilding, the TTS logs should include CUDA backend information and llama.cpp layer-offload messages. You can also watch GPU memory/activity with `nvidia-smi`.

## Optimization notes in this build

This package includes a small optimization pass focused on lower latency and safer operations:

- The orchestrator now flushes the first complete streamed sentence to TTS immediately, instead of waiting for the whole buffer to end with punctuation.
- Audio resampling now uses polyphase resampling (`scipy.signal.resample_poly`) for the host playback path and speaker-reference conversion.
- Raw input/output audio recording is disabled by default with `ORCH_SAVE_AUDIO=false`; enable it only when debugging.
- ASR latency/accuracy knobs are exposed as env vars: `ASR_BEAM_SIZE`, `ASR_VAD_FILTER`, and `ASR_CONDITION_ON_PREVIOUS_TEXT`.
- Docker services use `init: true`, healthchecks, explicit NVIDIA GPU wiring, and smaller `.dockerignore` build contexts.
- `scripts/start_services.sh` now creates required cache/data folders, rebuilds the named services, supports `REBUILD_NO_CACHE=1`, and only follows logs when `FOLLOW_LOGS=1` is set.


## GitHub master merge notes

This package was compared with `https://github.com/TimeTreker/chromie.git` on branch `master`. The online branch contained useful packaging/runtime pieces, but also older RTX 5090 / Blackwell defaults. This package keeps the RTX 4090 Laptop GPU fixes and merges only the useful generic pieces:

- Apache-2.0 `LICENSE`
- `.env.example`
- Updated `FINAL_RUNTIME_NOTES.md` and `MINIMAL_TTS_FIX_NOTES.md`
- Optional container proxy wiring with `HTTP_PROXY`, `HTTPS_PROXY`, `NO_PROXY`, and `host.docker.internal`
- Explicit `chromie-net` Docker network
- Cache/data placeholder directories for `hf_cache`, `ollama_data`, and `recordings`
- `llm.md` compatibility pointer to the canonical `llm_context.md`

The online branch's `CUDA_ARCHITECTURES=120`, RTX 5090 wording, and `TTS_N_GPU_LAYERS=99` are intentionally not used in this RTX 4090 Laptop GPU package.

## Helper scripts

```bash
./scripts/setup_orchestrator.sh          # create host Python env, install orchestrator deps, list audio devices
./scripts/start_services.sh              # build/start chromie-asr, chromie-llm, chromie-tts; set FOLLOW_LOGS=1 to tail logs
./scripts/verify_tts_gpu.sh              # verify nvidia-smi, llama-cpp CUDA backend, and TTS websocket health
./scripts/warm_ollama.sh                 # pre-load Ollama model to reduce first-token latency
./scripts/record_voice.sh                # record a reference WAV for speaker creation
./scripts/create_speaker_in_container.sh # ask the running TTS server to create a speaker profile
```


## Optional proxy for container downloads

The GitHub `master` project used `host.docker.internal` proxy wiring for ASR/TTS model downloads. This package keeps that capability, but leaves it disabled by default.

Leave these blank if you do not use a proxy:

```env
HTTP_PROXY=
HTTPS_PROXY=
```

For a host-side proxy running on port `7897`, set:

```env
HTTP_PROXY=http://host.docker.internal:7897
HTTPS_PROXY=http://host.docker.internal:7897
NO_PROXY=localhost,127.0.0.1,host.docker.internal,chromie-asr,chromie-tts,chromie-llm,asr,tts,llm
```

Do not use `http://127.0.0.1:7897` inside containers because that points to the container itself, not the host.

## First start on the RTX 4090 laptop

For the first run after this GPU fix, rebuild CUDA services without cache:

```bash
docker compose down
REBUILD_NO_CACHE=1 ./scripts/start_services.sh
```

Or manually:

```bash
docker compose down
docker compose build --no-cache chromie-asr chromie-tts
docker compose up -d --build chromie-asr chromie-llm chromie-tts
```

Check TTS startup:

```bash
docker compose logs -f chromie-tts
```

You want to see:

```text
llama-cpp-python CUDA backend detected
OuteTTS additional_model_config={'n_gpu_layers': -1, ...}
TTS model loaded
TTS server ready on ws://0.0.0.0:5000
```

Then verify the GPU path:

```bash
./scripts/verify_tts_gpu.sh
docker exec chromie-tts nvidia-smi
```


## Local audio env file

This repository-ready package does not include `orchestrator/.env.local` because it is machine-specific. Create it from the example:

```bash
cp orchestrator/.env.local.example orchestrator/.env.local
python orchestrator/list_devices.py
```

Then edit the input/output device indexes for your laptop.

## Run host orchestrator

```bash
cd orchestrator
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.local.example .env.local
python list_devices.py
python orchestrator.py
```

Edit `orchestrator/.env.local` and set your real input/output device indexes. Avoid generic devices like `default`, `sysdefault`, `pipewire`, and `monitor` if possible.

Example:

```env
INPUT_DEVICE_INDEX=22
OUTPUT_DEVICE_INDEX=18
```

The orchestrator automatically resamples the TTS PCM source rate to your real speaker output rate. `TTS_SAMPLE_RATE` is the **TTS source PCM rate**, not the speaker rate.

## Create your own OuteTTS speaker

Record a clean 10-15 second WAV:

```bash
mkdir -p tts/speakers
arecord -D default -f S16_LE -r 48000 -c 1 -d 14 tts/speakers/chromie_voice.wav
```

Start TTS first:

```bash
docker compose up -d chromie-tts
```

Then create the profile through the running TTS server:

```bash
./scripts/create_speaker_in_container.sh /app/speakers/chromie_voice.wav chromie_voice --make-default
```

This creates:

```text
tts/speakers/chromie_voice.json
tts/speakers/default.json
```

Use the speaker from the host orchestrator:

```env
TTS_SPEAKER_ID=chromie_voice
```

`tts/create_speaker.py` is still included as an optional manual helper, but production speaker creation is built into `tts/server.py`.

## Hugging Face cache

The TTS GGUF model should be cached locally. If your network/proxy blocks Hugging Face, download it on the host:

```bash
mkdir -p hf_cache
HF_HOME="$(pwd)/hf_cache" huggingface-cli download \
  OuteAI/OuteTTS-1.0-0.6B-GGUF \
  OuteTTS-1.0-0.6B-FP16.gguf
```

Then set offline mode in `.env`:

```env
HF_HUB_OFFLINE=1
TRANSFORMERS_OFFLINE=1
```

If `hf_cache` is a symlink, mount the real path in `docker-compose.yml`.

## Latency logs

The orchestrator logs events like:

```text
[SID:abcd1234 +123.4ms] asr_final: ...
[SID:abcd1234 +900.1ms] llm_first_token: ...
[SID:abcd1234 +1600.0ms] tts_stream_end: ...
[SID:abcd1234 +3300.0ms] playback_end: ...
```

Important LLM fix included: Ollama requests use `think=false`, so thinking-capable models do not spend the whole token budget in `thinking` and return zero speakable `response` text.

For first-token latency, tune:

```env
OLLAMA_NUM_CTX=2048
OLLAMA_NUM_PREDICT=96
OLLAMA_KEEP_ALIVE=30m
```

For ASR latency/accuracy tradeoffs, tune:

```env
ASR_BEAM_SIZE=1
ASR_VAD_FILTER=false
ASR_CONDITION_ON_PREVIOUS_TEXT=false
```

For false VAD interrupts, tune:

```env
ORCH_VAD_MODE=3
ORCH_MIN_RMS=120
ORCH_BARGE_IN_MIN_RMS=350
ORCH_MIN_AUDIO_MS=1200
ORCH_VAD_SILENCE_MS=650
```

## Troubleshooting TTS still using CPU

Run:

```bash
./scripts/verify_tts_gpu.sh
docker compose logs chromie-tts | grep -Ei 'cuda|cublas|offload|n_gpu_layers|ggml'
```

If the container cannot see the GPU, fix the host first:

```bash
nvidia-smi
docker run --rm --gpus all nvidia/cuda:12.8.1-base-ubuntu24.04 nvidia-smi
```

If `nvidia-smi` works but llama.cpp is CPU-only, rebuild without cache:

```bash
docker compose down
docker compose build --no-cache chromie-tts
docker compose up -d chromie-tts
```

If CUDA is detected but GPU memory does not increase when TTS loads, confirm `.env` contains:

```env
TTS_CUDA_ARCH=89
TTS_N_GPU_LAYERS=-1
NVIDIA_VISIBLE_DEVICES=all
NVIDIA_DRIVER_CAPABILITIES=compute,utility
```
