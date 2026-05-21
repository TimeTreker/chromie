# Chromie Voice Assistant - LLM Context

This file summarizes the whole project so a new LLM/chat session can quickly understand the current architecture, important design decisions, recent fixes, and how to continue development safely.

## Hardware preset in this package

- Preset: **RTX4090 laptop**
- TTS CUDA architecture: `89`
- TTS GPU layer offload: `TTS_N_GPU_LAYERS=-1` (all possible llama.cpp layers)
- NVIDIA visibility: `NVIDIA_VISIBLE_DEVICES=all`, `NVIDIA_DRIVER_CAPABILITIES=compute,utility`
- TTS threads: `4`
- TTS batch: `192`
- Note: Use CUDA 12.8 images for consistency. `TTS_CUDA_ARCH=89` for Ada / RTX4090 Laptop GPU.

This package is the RTX4090 laptop build. It keeps the same application logic as the prior optimized package, with an additional TTS GPU-offload fix for OuteTTS / llama-cpp-python.

## Goal of the project

Chromie is a local real-time voice assistant pipeline:

1. The host orchestrator captures microphone audio.
2. VAD detects valid user speech.
3. ASR converts speech to text through a websocket service.
4. Ollama streams LLM text tokens.
5. The orchestrator chunks speakable text and sends it to TTS.
6. OuteTTS streams PCM audio back.
7. The orchestrator resamples the TTS source rate to the real speaker output rate and plays it.

The project is optimized for local GPU use and low voice-assistant latency.

## Top-level structure

```text
.env                         Hardware/service preset values
docker-compose.yml            Starts ASR, TTS, and Ollama services
README.md                     Human setup instructions
llm_context.md                This project summary for future LLM sessions

asr/
  Dockerfile                  Faster-Whisper CUDA image
  requirements.txt
  server.py                   ASR websocket server, listens on port 9001

llm/
  Not a local folder. Uses ollama/ollama container, port 11434.

tts/
  Dockerfile                  OuteTTS / llama-cpp CUDA image
  requirements.txt
  server.py                   TTS websocket server, listens on port 5000
  create_speaker.py           Optional helper; production speaker creation is in server.py
  speakers/                   Stores WAV references and speaker JSON profiles

orchestrator/
  orchestrator.py             Host-side controller: mic, VAD, ASR, LLM, TTS, playback
  audio_device_manager.py     Selects input/output devices and detects sample rates
  vad.py                      WebRTC VAD wrapper
  list_devices.py             Prints sounddevice input/output device list
  requirements.txt
  .env.local.example          Host orchestrator runtime settings

scripts/
  setup_orchestrator.sh       Create host Python env and install orchestrator deps
  start_services.sh           Build/start Docker services
  verify_tts_gpu.sh           Check llama-cpp CUDA backend and TTS health
  warm_ollama.sh              Preload Ollama model to reduce first-token latency
  record_voice.sh             Record a reference WAV
  create_speaker_in_container.sh Create speaker profile through running TTS server
```

## Services

### ASR service

- Container: `chromie-asr`
- Port: `9001`
- Protocol: websocket
- Default model: `dropbox-dash/faster-whisper-large-v3-turbo`
- Device: CUDA / float16
- It receives raw 16 kHz mono PCM S16LE audio from the orchestrator and returns JSON results.

### LLM service

- Container: `chromie-llm`
- Image: `ollama/ollama:latest`
- Port: `11434`
- Default model: `gemma4:e2b`
- The orchestrator calls `/api/generate` with streaming enabled.
- Important fix: payload includes `"think": false` so thinking-capable models do not consume the entire token budget in the `thinking` field and return zero speakable `response` text.

### TTS service

- Container: `chromie-tts`
- Port: `5000`
- Protocol: websocket
- Model: OuteTTS 1.0 0.6B GGUF with llama-cpp backend
- Default quantization: FP16
- The TTS server streams PCM S16LE audio chunks to the orchestrator.
- TTS source sample rate defaults to `44100`. This is **not** necessarily the speaker rate. The orchestrator resamples to the detected speaker output rate.
- RTX4090 laptop GPU path: llama-cpp-python is compiled with `GGML_CUDA=ON`, `CMAKE_CUDA_ARCHITECTURES=89`, runtime CUDA stubs are not kept in `LD_LIBRARY_PATH`, and OuteTTS passes `n_gpu_layers=-1` / `main_gpu=0`.


## TTS GPU fix added in this package

This package includes the accepted fix for TTS using CPU instead of the RTX4090 Laptop GPU. The likely failure mode was a weak runtime CUDA path: CUDA-enabled `llama-cpp-python` could be built, but OuteTTS was not forced strongly enough to offload all layers, and CUDA stub libraries were left in the runtime library path.

Final fix:

- `.env` sets `TTS_CUDA_ARCH=89` for the RTX4090 Laptop GPU.
- `.env` sets `TTS_N_GPU_LAYERS=-1` so llama.cpp offloads all possible layers.
- `.env` sets `NVIDIA_VISIBLE_DEVICES=all` and `NVIDIA_DRIVER_CAPABILITIES=compute,utility`.
- `docker-compose.yml` has `gpus: all` plus explicit NVIDIA device reservations for ASR, TTS, and Ollama.
- `tts/Dockerfile` uses `/usr/local/cuda/lib64/stubs` only during `llama-cpp-python` compilation; final runtime `LD_LIBRARY_PATH` excludes the stubs directory.
- `tts/server.py` and `tts/create_speaker.py` set `cfg.device = "cuda"`, `cfg.n_gpu_layers = -1`, and `additional_model_config` includes `n_gpu_layers`, `main_gpu=0`, and verbose llama.cpp logs.

Expected runtime proof:

```text
llama-cpp-python CUDA backend detected
OuteTTS additional_model_config={'n_gpu_layers': -1, ...}
llama.cpp log lines mentioning CUDA/GGML and layer offload
```

If the host/container NVIDIA runtime is configured correctly, `docker exec chromie-tts nvidia-smi` should work and GPU memory should increase while the model is loaded.

## Optimization pass added in this package

The project has been lightly optimized without changing the core ASR → LLM → TTS → playback architecture. The important changes are:

- Orchestrator TTS chunking now extracts and schedules the first complete sentence from the streaming LLM buffer, reducing time-to-first-audio on multi-sentence replies.
- Host playback resampling and speaker-reference resampling now use `scipy.signal.resample_poly` instead of FFT `signal.resample`, which is generally better for realtime sample-rate conversion.
- `ORCH_SAVE_AUDIO=false` disables raw `.raw` input/output writes by default to avoid extra disk I/O and recording growth during normal operation.
- ASR exposes runtime env knobs: `ASR_BEAM_SIZE`, `ASR_VAD_FILTER`, and `ASR_CONDITION_ON_PREVIOUS_TEXT`. The low-latency defaults remain beam size 1, no internal ASR VAD, and no previous-text conditioning.
- TTS speaker IDs and speaker WAV paths are validated so websocket speaker creation cannot write outside `SPEAKER_DIR`.
- Docker Compose now uses `init: true`, healthchecks, explicit NVIDIA GPU wiring, no production bind-mount override for `tts/server.py`, and smaller Docker build contexts through service-level `.dockerignore` files.
- `scripts/start_services.sh` creates required directories, rebuilds the three named services, supports `REBUILD_NO_CACHE=1` for clean CUDA rebuilds, and only tails logs when `FOLLOW_LOGS=1`.

## Important final fixes already included

### 1. Ollama `think=false`

Problem observed:

```text
llm_done: response_chars=0 scheduled_tts=0
llm_done_raw: done_reason=length eval_count=96
```

Diagnosis: the model generated tokens, but they were in a thinking stream rather than the `response` field. No TTS was scheduled.

Fix in `orchestrator.py`:

```python
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
```

### 2. OuteTTS speaker creation without torchcodec / FFmpeg / NPP

Problem observed while creating custom voice profiles:

- `torchcodec` missing
- then FFmpeg shared libraries missing
- then `libnppicc.so.13` missing

Final design:

- Production speaker creation is built into `tts/server.py`.
- `tts/create_speaker.py` remains as an optional manual helper.
- Speaker creation patches OuteTTS audio loading to use `soundfile + scipy resample` rather than `torchaudio -> torchcodec -> FFmpeg -> NVIDIA NPP`.
- No `torchcodec`, FFmpeg, or NPP Dockerfile changes are required for speaker creation.

Expected speaker files:

```text
tts/speakers/chromie_voice.wav   Reference voice recording
tts/speakers/chromie_voice.json  Generated speaker profile
tts/speakers/default.json        Optional default speaker profile
```

Use from orchestrator:

```env
TTS_SPEAKER_ID=chromie_voice
```

### 3. Auto-resampling TTS output to real speaker rate

Important distinction:

- `TTS_SAMPLE_RATE` = source PCM rate from TTS, usually `44100`.
- Output device rate = real speaker rate, detected by `audio_device_manager.py`, often `48000` for PipeWire/PulseAudio/USB devices.

The orchestrator automatically resamples:

```text
TTS source PCM rate -> detected output device sample rate
```

If sound is too slow or too fast, check that the real output device is selected, not a generic wrapper.

Prefer explicit devices in `orchestrator/.env.local`:

```env
INPUT_DEVICE_INDEX=22
OUTPUT_DEVICE_INDEX=18
```

Avoid generic devices when possible:

```text
default
sysdefault
pipewire
dmix
monitor
Default Sink
Default Source
```

### 4. Playback no-sound fix

Old issue:

- `sd.play(..., blocking=True)` could hang after repeated interruptions.
- Later TTS audio was generated but playback worker never played it.

Final design:

- Uses persistent `sd.OutputStream`.
- Writes audio in small chunks.
- Uses `output_write_lock` so the stream is not aborted while `stream.write()` is active.
- Uses `playback_generation` so new user speech invalidates stale playback.

Related env:

```env
ORCH_PLAYBACK_CHUNK_MS=80
```

### 5. Empty/error TTS order skip markers

Old issue:

- TTS order N could return empty audio.
- Playback waited forever for order N, blocking later valid audio.

Fix:

- Empty/error/exception TTS orders enqueue a skip marker.
- Playback order advances safely.
- Session completion uses:

```text
scheduled_tts == played_tts + failed_tts + skipped_tts
```

### 6. TTS websocket retry

TTS websocket can occasionally close or fail with:

```text
no close frame received or sent
did not receive a valid HTTP response
```

Fix:

```env
ORCH_TTS_WS_RETRIES=2
ORCH_TTS_WS_RETRY_DELAY_MS=300
```

### 7. VAD false-trigger / barge-in protection

Observed issue:

- VAD detected speaker echo/noise and started false sessions.
- False sessions cancelled active LLM/TTS responses.

Final protections:

```env
ORCH_VAD_MODE=3
ORCH_MIN_RMS=120
ORCH_BARGE_IN_MIN_RMS=350
ORCH_MIN_AUDIO_MS=1200
ORCH_VAD_SILENCE_MS=650
```

When the assistant is speaking, barge-in requires the higher RMS threshold.

## Recommended `.env` service settings

Common:

```env
COMPOSE_PROJECT_NAME=chromie
HF_HUB_OFFLINE=0
TRANSFORMERS_OFFLINE=0

ASR_MODEL=dropbox-dash/faster-whisper-large-v3-turbo
ASR_DEVICE=cuda
ASR_COMPUTE_TYPE=float16
ASR_BEAM_SIZE=1
ASR_VAD_FILTER=false
ASR_CONDITION_ON_PREVIOUS_TEXT=false

TTS_MODEL_SIZE=0.6B
TTS_QUANTIZATION=FP16
TTS_N_GPU_LAYERS=-1
TTS_CONTEXT_SIZE=4096
TTS_MAX_LENGTH=4096
TTS_SAMPLE_RATE=44100
TTS_CHUNK_MS=120
TTS_MAX_TEXT_CHARS=220
TTS_GENERATION_RETRIES=2

OLLAMA_MODEL=gemma4:e2b
OLLAMA_KEEP_ALIVE=30m
OLLAMA_NUM_PARALLEL=1
OLLAMA_CONTEXT_LENGTH=2048
OLLAMA_NUM_CTX=2048
OLLAMA_NUM_PREDICT=96
OLLAMA_TEMPERATURE=0.4
OLLAMA_TOP_P=0.9
```

Preset-specific values:

```env
TTS_CUDA_ARCH=89
NVIDIA_VISIBLE_DEVICES=all
NVIDIA_DRIVER_CAPABILITIES=compute,utility
TTS_N_BATCH=192
TTS_THREADS=4
```

## Recommended `orchestrator/.env.local`

```env
ASR_URL=ws://localhost:9001
TTS_URL=ws://localhost:5000
LLM_URL=http://localhost:11434/api/generate
OLLAMA_MODEL=gemma4:e2b

INPUT_DEVICE_INDEX=
OUTPUT_DEVICE_INDEX=
INPUT_DEVICE_NAME=
OUTPUT_DEVICE_NAME=

TTS_SPEAKER_ID=default
TTS_SAMPLE_RATE=44100
TTS_FLUSH_CHARS=160

ORCH_VAD_MODE=3
ORCH_MIN_RMS=120
ORCH_BARGE_IN_MIN_RMS=350
ORCH_MIN_AUDIO_MS=1200
ORCH_VAD_SILENCE_MS=650

ORCH_PLAYBACK_CHUNK_MS=80
ORCH_TTS_WS_RETRIES=2
ORCH_TTS_WS_RETRY_DELAY_MS=300
ORCH_TTS_CONCURRENCY=1

OLLAMA_NUM_CTX=2048
OLLAMA_NUM_PREDICT=96
OLLAMA_TEMPERATURE=0.4
OLLAMA_TOP_P=0.9
OLLAMA_KEEP_ALIVE=30m

ORCH_SESSION_TIMING_LOGS=true
ORCH_SAVE_AUDIO=false
RECORDINGS_DIR=../recordings
LOG_LEVEL=INFO
```

## Startup workflow

1. Start Docker services:

```bash
./scripts/start_services.sh
```

or manually:

```bash
docker compose up -d --build chromie-asr chromie-llm chromie-tts
```

2. Verify TTS GPU:

```bash
./scripts/verify_tts_gpu.sh
```

Look for CUDA in llama-cpp system info, `n_gpu_layers=-1`, layer-offload messages, and `TTS server ready`.

3. Warm Ollama:

```bash
./scripts/warm_ollama.sh
```

4. Set up host orchestrator if needed:

```bash
./scripts/setup_orchestrator.sh
```

5. Choose real audio devices:

```bash
cd orchestrator
source .venv/bin/activate
python list_devices.py
```

6. Edit `orchestrator/.env.local`, then run:

```bash
python orchestrator.py
```

## Custom voice / speaker workflow

1. Record a clean 10-15 second WAV:

```bash
./scripts/record_voice.sh
```

or manually:

```bash
mkdir -p tts/speakers
arecord -D default -f S16_LE -r 48000 -c 1 -d 14 tts/speakers/chromie_voice.wav
```

2. Start TTS:

```bash
docker compose up -d chromie-tts
```

3. Create speaker through the running TTS server:

```bash
./scripts/create_speaker_in_container.sh /app/speakers/chromie_voice.wav chromie_voice --make-default
```

4. Set speaker in orchestrator:

```env
TTS_SPEAKER_ID=chromie_voice
```

If `--make-default` was used, `TTS_SPEAKER_ID=default` also works.

## Hugging Face cache and offline mode

ASR/TTS models may need Hugging Face cache. If network/proxy is unreliable, download models on host and run offline.

TTS GGUF model:

```bash
mkdir -p hf_cache
HF_HOME="$(pwd)/hf_cache" huggingface-cli download   OuteAI/OuteTTS-1.0-0.6B-GGUF   OuteTTS-1.0-0.6B-FP16.gguf
```

Then set:

```env
HF_HUB_OFFLINE=1
TRANSFORMERS_OFFLINE=1
```

If `hf_cache` or `ollama_data` is a symlink, use the real path in `docker-compose.yml` volumes:

```bash
readlink -f ./hf_cache
readlink -f ./ollama_data
```

## Latency log interpretation

Important orchestrator log events:

```text
session_start
vad_valid_end
asr_send_start / asr_final
llm_request_start
llm_first_token
llm_flush_to_tts / llm_final_flush_to_tts
tts_schedule
tts_stream_start / tts_stream_end
playback_start / playback_end
session_done
```

Healthy rough ranges:

```text
ASR: usually ~150-250 ms after audio send
LLM first token: target ~0.5-2.5 s after ASR, model dependent
TTS: often ~0.8-1.8 s per chunk
Playback: roughly equal to audio duration
```

If `llm_done` shows `response_chars=0` and `eval_count>0`, check `think=false` and make sure the current orchestrator file is used.

If TTS generates audio but no playback starts, check playback worker logs and output device selection.

If VAD interrupts too much, increase:

```env
ORCH_MIN_RMS=180
ORCH_BARGE_IN_MIN_RMS=500
ORCH_MIN_AUDIO_MS=1500
ORCH_VAD_SILENCE_MS=750
```

If ASR transcribes repeated phrases from silence/noise, the input device may be a monitor source or speaker echo. Select a real microphone device.

## Common troubleshooting

### No voice output, but ASR works

Check logs:

- If `llm_done response_chars=0 scheduled_tts=0`: LLM produced no speakable response. Check `think=false`, `OLLAMA_NUM_PREDICT`, and model direct curl test.
- If `tts_schedule` exists but no `tts_stream_start`: TTS websocket/server issue.
- If `tts_stream_end bytes>0` exists but no `playback_start`: playback queue/device issue.
- If `playback_start` exists but no sound: wrong output device or speaker rate/device route.

### TTS tries to connect to Hugging Face and fails

The GGUF model is not visible in the mounted cache, or offline mode/cache path is wrong. Verify inside container:

```bash
docker exec -it chromie-tts bash -lc 'find -L /root/.cache/huggingface -name "OuteTTS-1.0-0.6B-FP16.gguf" -ls'
```

### TTS says CPU only

Run:

```bash
./scripts/verify_tts_gpu.sh
docker exec chromie-tts nvidia-smi
docker compose logs chromie-tts | grep -Ei "cuda|cublas|offload|n_gpu_layers|ggml"
```

For this RTX4090 laptop package, `.env` should contain:

```env
TTS_CUDA_ARCH=89
TTS_N_GPU_LAYERS=-1
NVIDIA_VISIBLE_DEVICES=all
NVIDIA_DRIVER_CAPABILITIES=compute,utility
```

If `nvidia-smi` fails inside the container, fix the host NVIDIA Container Toolkit / Docker GPU runtime first. If `nvidia-smi` works but llama.cpp is CPU-only, rebuild TTS without cache:

```bash
docker compose down
docker compose build --no-cache chromie-tts
docker compose up -d chromie-tts
```

### Audio plays too slow or too fast

Likely wrong source/output sample rate. Remember:

- `TTS_SAMPLE_RATE` is the TTS PCM source rate.
- The speaker output rate is detected from the selected output device.
- Select the real output device, not generic `default`.

### Speaker creation errors involving torchcodec, FFmpeg, or libnppicc

The final design should not require that path. Make sure you are using the final `tts/server.py` and optional final `tts/create_speaker.py`, both of which use `soundfile/scipy` for reference audio loading.

## Do not regress these design decisions

- Do not reintroduce `sd.play(..., blocking=True)` for playback.
- Do not use `thinking` text as TTS input.
- Keep Ollama request `think: false` for realtime voice.
- Do not require `torchcodec`, FFmpeg, or NVIDIA NPP for speaker creation.
- Do not treat `TTS_SAMPLE_RATE` as the speaker rate.
- Keep skip markers for empty/error TTS orders.
- Keep `playback_generation` to invalidate stale playback.
- Prefer explicit real audio input/output devices over generic defaults.

## Current project status

This is the RTX4090 laptop integrated build. It includes the final orchestrator, TTS server with built-in custom speaker creation, the TTS GPU-offload fix, helper scripts, and this `llm_context.md` summary for future LLM sessions.


## GitHub master comparison and merge update

Compared with `https://github.com/TimeTreker/chromie.git`, branch `master`.

### Useful upstream items merged

- Apache-2.0 `LICENSE`
- `.env.example`
- Updated runtime note files:
  - `FINAL_RUNTIME_NOTES.md`
  - `MINIMAL_TTS_FIX_NOTES.md`
- Optional proxy wiring for Docker build/runtime:
  - `HTTP_PROXY`
  - `HTTPS_PROXY`
  - `NO_PROXY`
  - `host.docker.internal:host-gateway`
- Explicit Docker network `chromie-net`
- Cache/data placeholders:
  - `hf_cache/.gitkeep`
  - `ollama_data/.gitkeep`
  - `recordings/.gitkeep`
- `llm.md` compatibility pointer to this canonical file.

### Upstream items intentionally not merged

- RTX 5090 / Blackwell defaults are not used for this laptop package.
- `CUDA_ARCHITECTURES=120` is wrong for RTX 4090 Laptop GPU and is not used.
- `TTS_N_GPU_LAYERS=99` is replaced by `TTS_N_GPU_LAYERS=-1`.
- The production TTS source bind mount `./tts:/app` is not restored because it can shadow the built image contents.
- `orchestrator/.env.local` is not included because it is machine-specific; create it from `.env.local.example`.

### Canonical RTX 4090 Laptop GPU values

```env
TTS_CUDA_ARCH=89
TTS_N_GPU_LAYERS=-1
NVIDIA_VISIBLE_DEVICES=all
NVIDIA_DRIVER_CAPABILITIES=compute,utility
```

### Optional proxy rule

If a host proxy is needed inside containers, use `host.docker.internal`, not `127.0.0.1`:

```env
HTTP_PROXY=http://host.docker.internal:7897
HTTPS_PROXY=http://host.docker.internal:7897
NO_PROXY=localhost,127.0.0.1,host.docker.internal,chromie-asr,chromie-tts,chromie-llm,asr,tts,llm
```
