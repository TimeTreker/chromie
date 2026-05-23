# Chromie Voice Assistant

Chromie is a local, GPU-accelerated realtime voice assistant stack.

The current architecture is:

```text
microphone on host
  ↓
host orchestrator
  ↓
chromie-asr        Faster-Whisper websocket ASR
chromie-router     fast route/intent decision service
chromie-agent      multi-agent reasoning / speaking brain
chromie-llm        Ollama model server
chromie-tts        OuteTTS / llama.cpp websocket TTS
  ↓
host orchestrator playback
```

The most important runtime rule is:

> Docker services handle ASR / Router / Agent / LLM / TTS.  
> The orchestrator runs on the host because it owns microphone input, VAD, playback, interruption, and audio-device selection.

## Services

| Service | Runs where | Port | Purpose |
|---|---:|---:|---|
| `chromie-asr` | Docker | `9001` | Faster-Whisper websocket ASR |
| `chromie-tts` | Docker | `5000` | OuteTTS websocket TTS |
| `chromie-llm` | Docker | `11434` | Ollama model server |
| `chromie-router` | Docker | `8091` | Lightweight route / intent decision |
| `chromie-agent` | Docker | `8092` | Conversation, speaker, action, tool, memory agents |
| `orchestrator` | Host | n/a | Mic, VAD, ASR/TTS clients, routing, playback |

## Current recommended design

Use the Router as a fast control-plane component. Do not use a large model for routing unless you have a specific reason.

```env
ROUTER_USE_LLM=0
ROUTER_MODEL=qwen3:0.6b
ROUTER_TIMEOUT_MS=1500
```

Use the Agent as the real talking brain.

```env
AGENT_USE_LLM=1
AGENT_OLLAMA_URL=http://chromie-llm:11434
AGENT_MODEL=gemma4:26b
AGENT_TIMEOUT_MS=120000
AGENT_MAX_SPEAK_CHARS=220
```

For a more realtime-feeling robot, use a smaller `AGENT_MODEL`, such as `gemma4:e2b`, `gemma4:4b`, `qwen3:1.7b`, or another model already installed in Ollama.

## Hardware / CUDA notes

Prefer auto-detection for TTS CUDA architecture:

```bash
./scripts/detect-cuda-arch.sh
```

Typical values:

```env
# RTX 4090 / Ada
TTS_CUDA_ARCH=89

# RTX 5090 / Blackwell
TTS_CUDA_ARCH=120
```

The TTS llama.cpp backend should use GPU offload:

```env
NVIDIA_VISIBLE_DEVICES=all
NVIDIA_DRIVER_CAPABILITIES=compute,utility
TTS_N_GPU_LAYERS=-1
TTS_MAX_CONCURRENT_SYNTHESIS=1
TTS_GENERATION_RETRIES=1
TTS_RESET_LLAMA_STATE=1
```

Use `TTS_N_GPU_LAYERS=-1` instead of a magic fixed value such as `99`; it means "offload all possible layers".

## Required directories

These are created by `scripts/start_services.sh` if missing:

```text
hf_cache/
ollama_data/
recordings/
```

If a path exists but is a file instead of a directory, fix that before starting.

## Recommended root `.env`

These are the important values for the current Router / Agent / Ollama architecture:

```env
COMPOSE_PROJECT_NAME=chromie

# GPU
NVIDIA_VISIBLE_DEVICES=all
NVIDIA_DRIVER_CAPABILITIES=compute,utility

# ASR
ASR_MODEL=dropbox-dash/faster-whisper-large-v3-turbo
ASR_DEVICE=cuda
ASR_COMPUTE_TYPE=float16
ASR_BEAM_SIZE=1
ASR_VAD_FILTER=false
ASR_CONDITION_ON_PREVIOUS_TEXT=false

# TTS
TTS_MODEL_SIZE=0.6B
TTS_QUANTIZATION=FP16
TTS_N_GPU_LAYERS=-1
TTS_CONTEXT_SIZE=4096
TTS_MAX_LENGTH=4096
TTS_N_BATCH=192
TTS_THREADS=4
TTS_SAMPLE_RATE=44100
TTS_CHUNK_MS=120
TTS_MAX_CONCURRENT_SYNTHESIS=1
TTS_GENERATION_RETRIES=1
TTS_RESET_LLAMA_STATE=1
TTS_MAX_TEXT_CHARS=220

# Ollama
OLLAMA_KEEP_ALIVE=24h
OLLAMA_LOAD_TIMEOUT=10m
OLLAMA_CONTEXT_LENGTH=2048
OLLAMA_NUM_PARALLEL=1
OLLAMA_WARM_TIMEOUT_SECONDS=600
OLLAMA_WARM_REQUEST_TIMEOUT_SECONDS=300

# Router
ROUTER_USE_LLM=0
ROUTER_MODEL=qwen3:0.6b
ROUTER_TIMEOUT_MS=1500

# Agent
AGENT_USE_LLM=1
AGENT_MODEL=gemma4:26b
AGENT_TIMEOUT_MS=120000
AGENT_MAX_SPEAK_CHARS=220
AGENT_ENABLE_HARDWARE_CLIENT=0
HARDWARE_DAEMON_URL=http://host.docker.internal:8095

# Host orchestrator waits longer than Agent waits for Ollama.
ORCH_AGENT_TIMEOUT_MS=130000

# Logs
LOG_LEVEL=INFO

# Proxy. Leave blank if not needed.
HTTP_PROXY=
HTTPS_PROXY=
NO_PROXY=localhost,127.0.0.1,host.docker.internal,chromie-asr,chromie-tts,chromie-llm,chromie-router,chromie-agent
```

## Host orchestrator env

`orchestrator/.env.local` is machine-specific and should not be committed. Create it from the example:

```bash
cp orchestrator/.env.local.example orchestrator/.env.local
python orchestrator/list_devices.py
```

Important values:

```env
ASR_URL=ws://127.0.0.1:9001
TTS_URL=ws://127.0.0.1:5000

ROUTER_ENABLED=true
ROUTER_URL=http://127.0.0.1:8091

AGENT_ENABLED=true
AGENT_URL=http://127.0.0.1:8092
ORCH_AGENT_TIMEOUT_MS=130000

ACTION_URL=http://127.0.0.1:8095
ACTION_DRY_RUN=true

INPUT_DEVICE_INDEX=
OUTPUT_DEVICE_INDEX=
TTS_SPEAKER_ID=default

ORCH_VAD_MODE=3
ORCH_MIN_RMS=120
ORCH_BARGE_IN_MIN_RMS=350
ORCH_MIN_AUDIO_MS=1200
ORCH_VAD_SILENCE_MS=650

ORCH_TTS_WS_RETRIES=2
ORCH_TTS_WS_RETRY_DELAY_MS=300
ORCH_TTS_CONCURRENCY=1
ORCH_SESSION_TIMING_LOGS=true
ORCH_SAVE_AUDIO=false
```

Avoid generic devices such as `default`, `sysdefault`, `pipewire`, `monitor`, `Default Sink`, or `Default Source` when possible. Select real microphone and speaker devices.

## Startup

Start Docker services:

```bash
bash scripts/start_services.sh
```

Pull the talking model if needed:

```bash
docker compose exec chromie-llm ollama list
docker compose exec chromie-llm ollama pull gemma4:26b
```

Warm the model before starting the host voice loop:

```bash
bash scripts/warm_ollama.sh gemma4:26b
```

Start the host orchestrator:

```bash
bash scripts/start_orchestrator.sh
```

The orchestrator should be run as a Python module from the repo root:

```bash
python -m orchestrator.orchestrator
```

Do not use `cd orchestrator && python orchestrator.py` for the current package-style import layout.

## Conda setup

If using conda, the recommended environment name is:

```text
Chromie
```

`start_orchestrator.sh` should activate it before running the module:

```bash
conda activate Chromie
python -m orchestrator.orchestrator
```

## One orchestrator process only

Only run one host orchestrator at a time. If two are running, they both listen to the microphone and both send the same response to TTS, causing duplicate speech.

Check:

```bash
pgrep -af "orchestrator"
ps aux | grep -E "python.*orchestrator|start_orchestrator" | grep -v grep
```

Stop all old orchestrators:

```bash
pkill -f "python.*orchestrator"
pkill -f "start_orchestrator.sh"
```

Then start exactly one:

```bash
bash scripts/start_orchestrator.sh
```

## Warm Ollama before voice input

Large models such as `gemma4:26b` may take longer than a normal voice-turn timeout to load. If the first user utterance triggers loading, the request can be canceled and Ollama logs may show:

```text
context canceled
Load failed
POST "/api/generate" 500
```

Use:

```bash
bash scripts/warm_ollama.sh "${AGENT_MODEL:-gemma4:26b}"
```

before starting the host orchestrator.

## Troubleshooting

### Agent always says "I understand."

The Agent is probably returning a hardcoded fallback or not calling Ollama. Check:

```bash
docker compose logs -f chromie-agent
```

You should see:

```text
conversation_agent_llm_start
ollama_generate_start
ollama_generate_http_done
conversation_agent_llm_done
```

### Agent says "my language model is not responding"

Check these first:

```bash
docker compose exec chromie-agent env | grep -E "AGENT_USE_LLM|AGENT_OLLAMA_URL|AGENT_MODEL|AGENT_TIMEOUT_MS"
docker compose exec chromie-llm ollama list
```

Common fixes:

```env
AGENT_USE_LLM=1
AGENT_OLLAMA_URL=http://chromie-llm:11434
AGENT_TIMEOUT_MS=120000
```

If Ollama returns 404, the model name is wrong or not installed:

```bash
docker compose exec chromie-llm ollama pull "$AGENT_MODEL"
```

### Ollama returns empty response

For thinking-capable models, make sure the payload includes:

```json
"think": false
```

The Agent should not speak Ollama's hidden thinking text. It should use only the final `response`.

### Duplicate spoken replies

If TTS logs show two different request IDs with the same text, the usual cause is two host orchestrator processes. TTS is only doing what it was asked to do.

Example:

```text
TTS input request_id=553c8a1f-0 text="..."
TTS input request_id=d93f5765-0 text="..."
```

Different session IDs mean different orchestrator sessions.

### TTS CUDA / GPU verification

```bash
./scripts/verify_tts_gpu.sh
docker exec chromie-tts nvidia-smi
docker compose logs chromie-tts | grep -Ei "cuda|cublas|offload|n_gpu_layers|ggml"
```

If `nvidia-smi` works but llama.cpp is CPU-only:

```bash
docker compose down
docker compose build --no-cache chromie-tts
docker compose up -d chromie-tts
```

### Audio plays too slow or too fast

`TTS_SAMPLE_RATE` is the source PCM rate from TTS, usually `44100`. The speaker output rate is detected from the selected output device, often `48000`. The host orchestrator resamples automatically.

Wrong playback speed usually means the selected output device is wrong or generic.

## Development notes

- Router should stay fast and deterministic.
- Agent should own conversation intelligence.
- Orchestrator should own audio, VAD, interruption, action execution, TTS scheduling, and playback.
- TTS should serialize generation: one active synthesis at a time.
- Large Ollama models should be warmed before voice input.
- Keep logs explicit. Silent fallback wastes debugging time.
