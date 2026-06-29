# Chromie ASR Service

`chromie-asr` is the final-utterance transcription service. It runs inside
Docker and listens on WebSocket port `9001` by default.

The host Orchestrator owns microphone capture, VAD, utterance boundaries, and
barge-in. ASR receives one complete utterance as binary PCM and returns one
final transcript. The current protocol does not emit partial transcripts.

## WebSocket protocol

Connect to `ws://<host>:9001`.

### Health

Client text frame:

```json
{"type": "ping"}
```

Server text frame:

```json
{"type": "pong", "service": "asr", "backend": "sherpa_onnx", "mode": "final"}
```

`{"type":"health"}` is also accepted.

### Transcription

Send one binary frame containing signed little-endian PCM16 mono samples at
`ASR_SAMPLE_RATE` (normally 16000 Hz).

Successful response:

```json
{"type": "final", "text": "hello", "duration": 1.24}
```

Failure response:

```json
{"type": "error", "message": "..."}
```

The service converts PCM16 to float32 and calls the configured final ASR
backend once per binary message. The supported default backend is
`ASR_BACKEND=sherpa_onnx` with `ASR_MODE=final`. Blocking model inference and
backend result handling run in a bounded thread executor rather than on the
WebSocket event loop. Separate health/ping connections therefore remain
responsive while an utterance is being transcribed.

Faster-Whisper remains installed and selectable with
`ASR_BACKEND=faster_whisper`; the WebSocket protocol is unchanged.

## Configuration

```env
ASR_HOST=0.0.0.0
ASR_PORT=9001
ASR_BACKEND=sherpa_onnx
ASR_MODE=final
ASR_MODEL=/root/.cache/huggingface/sherpa-onnx/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17
ASR_MODEL_REVISION=asr-models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17
ASR_DEVICE=cuda
ASR_COMPUTE_TYPE=int8
ASR_SAMPLE_RATE=16000
ASR_LANGUAGE=
ASR_BEAM_SIZE=1
ASR_VAD_FILTER=false
ASR_CONDITION_ON_PREVIOUS_TEXT=false
ASR_MAX_CONCURRENT_TRANSCRIPTIONS=1
SHERPA_ONNX_MODEL_TYPE=sense_voice
SHERPA_ONNX_PROVIDER=cuda
SHERPA_ONNX_NUM_THREADS=2
SHERPA_ONNX_LANGUAGE=auto
SHERPA_ONNX_USE_ITN=true
ASR_STARTUP_WARMUP_ENABLED=true
ASR_STARTUP_WARMUP_AUDIO_SECONDS=1.0
```

`ASR_BACKEND=sherpa_onnx` is the supported default backend.
`ASR_MODE=final` is the only supported protocol mode; streaming partials are a
future protocol change, not an implicit backend behavior.

For custom Faster-Whisper deployments, `ASR_MODEL_REVISION` must identify
the exact model snapshot and should be recorded in [`../release/model-lock.json`](../release/model-lock.json).

Host-side VAD is the normal utterance boundary; enabling a backend's own VAD
filter is a separate choice.

### sherpa-onnx model files

The first sherpa-onnx backend path is non-streaming SenseVoice:

```env
ASR_BACKEND=sherpa_onnx
ASR_MODEL=/root/.cache/huggingface/sherpa-onnx/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17
ASR_MODEL_REVISION=asr-models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17
SHERPA_ONNX_MODEL_TYPE=sense_voice
SHERPA_ONNX_PROVIDER=cuda
SHERPA_ONNX_NUM_THREADS=2
SHERPA_ONNX_LANGUAGE=auto
SHERPA_ONNX_USE_ITN=true
```

`ASR_MODEL` must be a local directory inside the container containing
`model.int8.onnx` or `model.onnx` plus `tokens.txt`. You can also set
`SHERPA_ONNX_MODEL_FILE` and `SHERPA_ONNX_TOKENS_FILE` explicitly. The
repository startup mounts `./hf_cache` at `/root/.cache/huggingface`, so a
convenient local cache location is:

```bash
mkdir -p hf_cache/sherpa-onnx
cd hf_cache/sherpa-onnx
curl -LO https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17.tar.bz2
tar xjf sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17.tar.bz2
```

The x86_64 ASR image installs the CUDA-enabled sherpa-onnx wheel pinned in
`asr/requirements.txt`; ARM profiles install the CPU wheel. The maintained
desktop default uses CUDA and performs a one-second startup warm-up before the
WebSocket server begins accepting requests. That warm-up pays the ONNX Runtime
CUDA cold-start cost before the first user utterance can hit
`ORCH_ASR_TIMEOUT_MS`. Set `ASR_DEVICE=cpu` and `SHERPA_ONNX_PROVIDER=cpu` for
CPU fallback.

### Accuracy comparison

Use `scripts/compare_asr_accuracy.py` to compare final-utterance backends on
the same reference audio. The built-in `sensevoice-smoke` sample set is only a
two-file sanity check from the downloaded SenseVoice bundle; use a JSONL
manifest for real accuracy claims.

Run the built-in smoke comparison inside the ASR image:

```bash
docker run --rm \
  -v "$PWD:/workspace" \
  -v "$PWD/hf_cache:/root/.cache/huggingface" \
  -w /workspace \
  chromie-asr:latest \
  python scripts/compare_asr_accuracy.py --sample-set sensevoice-smoke --json
```

A custom manifest is one JSON object per line:

```json
{"id":"kitchen_light_en","audio":"recordings/kitchen_light_en.wav","text":"turn on the kitchen light","language":"en"}
{"id":"walk_forward_zh","audio":"recordings/walk_forward_zh.wav","text":"向前走一点","language":"zh"}
```

The evaluator reports WER, CER, decode time, and real-time factor per backend.
Use CER for Chinese-heavy sets and WER for whitespace-tokenized English sets.

The host waits up to `ORCH_ASR_TIMEOUT_MS` (common default `30000`) for the final
response. Increase that budget for slower profiles or unusually long
utterances; it is independent of the service's bounded inference concurrency.

## Start and verify

Start through the repository launcher:

```bash
./scripts/start_services.sh
```

Check the service through the project smoke test:

```bash
./scripts/gpu_smoke_test.sh
```

See [`../docs/ACCEPTANCE.md`](../docs/ACCEPTANCE.md) for the distinction between
container health, GPU smoke evidence, and complete microphone acceptance.
