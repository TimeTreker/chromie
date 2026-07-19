# Chromie ASR Service

`chromie-asr` is Chromie's sherpa-onnx SenseVoice final-utterance transcription
service. It runs in Docker and listens on WebSocket port `9001` by default.

The host Orchestrator owns microphone capture, VAD, utterance boundaries, and
barge-in. ASR receives one complete utterance as binary PCM16 and returns one
final transcript. The current protocol does not emit partial transcripts.

## WebSocket protocol

Connect to `ws://<host>:9001`.

Health request:

```json
{"type": "ping"}
```

Health response:

```json
{
  "type": "pong",
  "service": "asr",
  "backend": "sherpa_onnx",
  "mode": "final",
  "model": "...",
  "model_revision": "..."
}
```

`{"type":"health"}` is also accepted.

Send one binary frame containing signed little-endian PCM16 mono samples at
`ASR_SAMPLE_RATE`, normally 16000 Hz.

Successful response:

```json
{"type": "final", "text": "hello", "duration": 1.24}
```

Failure response:

```json
{"type": "error", "message": "..."}
```

The service converts PCM16 to float32 and performs one SenseVoice decode per
binary message. Blocking recognition runs in a bounded executor, so health
connections remain responsive during transcription.

## Configuration

```env
ASR_HOST=0.0.0.0
ASR_PORT=9001
ASR_MODE=final
ASR_MODEL=/root/.cache/huggingface/sherpa-onnx/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17
ASR_MODEL_REVISION=asr-models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17
ASR_DEVICE=cuda
ASR_SAMPLE_RATE=16000
ASR_LANGUAGE=
ASR_MAX_CONCURRENT_TRANSCRIPTIONS=1
SHERPA_ONNX_MODEL_TYPE=sense_voice
SHERPA_ONNX_PROVIDER=cuda
SHERPA_ONNX_NUM_THREADS=2
SHERPA_ONNX_LANGUAGE=auto
SHERPA_ONNX_USE_ITN=true
ASR_STARTUP_WARMUP_ENABLED=true
ASR_STARTUP_WARMUP_AUDIO_SECONDS=1.0
```

`ASR_MODE=final` is the only supported protocol mode. Streaming partials require
a future protocol change.

`ASR_MODEL` must be a local directory containing `model.int8.onnx` or
`model.onnx` plus `tokens.txt`. You can instead set
`SHERPA_ONNX_MODEL_FILE` and `SHERPA_ONNX_TOKENS_FILE` explicitly.

The repository mounts `./hf_cache` at `/root/.cache/huggingface`. A convenient
local model location is:

```bash
mkdir -p hf_cache/sherpa-onnx
cd hf_cache/sherpa-onnx
curl -LO https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17.tar.bz2
tar xjf sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17.tar.bz2
```

The maintained desktop default uses CUDA and performs a one-second startup
warm-up before the WebSocket server accepts requests. Set `ASR_DEVICE=cpu` and
`SHERPA_ONNX_PROVIDER=cpu` for CPU operation.

## Accuracy evaluation

Use `scripts/evaluate_asr_accuracy.py` on the built-in smoke audio or a JSONL
manifest:

```bash
docker run --rm \
  -v "$PWD:/workspace" \
  -v "$PWD/hf_cache:/root/.cache/huggingface" \
  -w /workspace \
  chromie-asr:latest \
  python scripts/evaluate_asr_accuracy.py --sample-set sensevoice-smoke --json
```

Manifest format:

```json
{"id":"kitchen_light_en","audio":"recordings/kitchen_light_en.wav","text":"turn on the kitchen light","language":"en"}
{"id":"walk_forward_zh","audio":"recordings/walk_forward_zh.wav","text":"向前走一点","language":"zh"}
```

The evaluator reports WER, CER, decode time, and real-time factor. The built-in
two-file sample is a smoke check, not sufficient release evidence.

The host waits up to `ORCH_ASR_TIMEOUT_MS` for the final response. Increase that
budget for slower profiles or unusually long utterances; it is independent of
the service's bounded inference concurrency.

## Start and verify

```bash
./scripts/start_services.sh
./scripts/gpu_smoke_test.sh
```

See [`../docs/SENSEVOICE_ASR.md`](../docs/SENSEVOICE_ASR.md) for architecture and
evidence requirements, and [`../docs/ACCEPTANCE.md`](../docs/ACCEPTANCE.md) for
container, simulator, and physical voice acceptance levels.
