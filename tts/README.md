# Chromie TTS Service

`chromie-tts` is the GPU-backed OuteTTS speech-synthesis service. It runs inside
Docker and listens on WebSocket port `5000` by default. The host Orchestrator
owns playback, resampling to the selected output device, interruption, and
barge-in.

## Concurrency model

Each OuteTTS/llama.cpp interface owns mutable model and CUDA state in a dedicated
child process. `TTS_WORKER_COUNT` controls how many independent model workers
are started; the common/default configuration uses one worker, while the RTX
5090 profile can use two. `TTS_MAX_CONCURRENT_SYNTHESIS` limits admitted
synthesis work and should not exceed the configured worker count unless queueing
inside the service is intentional.

For latency, the host Orchestrator can split one logical reply into multiple
ordered synthesis requests. That allows the first chunk to play while later
chunks wait for or use the model worker. Audible playback remains serialized by
the Orchestrator.

Cancelling an active synthesis (normally because the Orchestrator closes the
WebSocket during barge-in) terminates and restarts the child process. This is
deliberate: cancelling only the asyncio waiter cannot stop native llama.cpp
generation. The restart prevents stale speech work from occupying the sole
model slot, although the next request must wait for the model worker to reload.

## WebSocket protocol

Connect to `ws://<host>:5000` and send JSON text frames.

### Health

Request:

```json
{"type": "ping"}
```

Response:

```json
{"type": "pong", "service": "tts"}
```

`{"type":"health"}` is also accepted.

### List speakers

```json
{"type": "list_speakers"}
```

The response reports available speaker-profile identifiers.

### Create a speaker profile

```json
{
  "type": "create_speaker",
  "speaker_id": "demo",
  "wav_path": "/app/speakers/demo.wav",
  "save_as_default": false
}
```

The WAV path must resolve inside the configured speaker directory.

### Stream synthesis

Request:

```json
{
  "type": "synthesize_stream",
  "text": "Hello from Chromie.",
  "speaker_id": "default"
}
```

Response sequence:

1. JSON `start` metadata including the source sample rate;
2. one or more binary raw PCM chunks;
3. JSON `end` metadata, or JSON `error` on failure.

The Orchestrator may resample the service's source rate to the selected speaker
output rate.

## Important length settings

`TTS_MAX_LENGTH` is a model generation-token budget, not a text character
limit. Setting it very low can produce no audio codec tokens. Use
`TTS_MAX_TEXT_CHARS` to bound spoken text.

The service clamps the effective generation length between a safe minimum and
`TTS_CONTEXT_SIZE` and logs adjustments.

## Configuration

Common settings:

```env
TTS_HOST=0.0.0.0
TTS_PORT=5000
TTS_MODEL_SIZE=0.6B
TTS_TOKENIZER_REPO=OuteAI/OuteTTS-1.0-0.6B
TTS_TOKENIZER_REVISION=<immutable-hugging-face-commit>
TTS_GGUF_REPO=OuteAI/OuteTTS-1.0-0.6B-GGUF
TTS_GGUF_REVISION=<immutable-hugging-face-commit>
TTS_QUANTIZATION=FP16
TTS_SAMPLE_RATE=44100
TTS_CHUNK_MS=120
TTS_N_GPU_LAYERS=-1
TTS_CONTEXT_SIZE=4096
TTS_MAX_LENGTH=4096
TTS_MAX_TEXT_CHARS=220
TTS_MIN_TEXT_CHARS=1
TTS_MAX_CONCURRENT_SYNTHESIS=1
TTS_WORKER_COUNT=1
TTS_GENERATION_RETRIES=1
TTS_RESET_LLAMA_STATE=0
TTS_WORKER_STARTUP_TIMEOUT_SEC=600
TTS_SPEAKER_ID=default
```

The service downloads those exact snapshots and replaces OuteTTS auto-config
paths with local immutable tokenizer and GGUF paths. The maintained lock is
[`../release/model-lock.json`](../release/model-lock.json); enabling another
model size requires updating code, tests, the lock, and these operational docs.

The full settings list is in
[`../docs/CONFIGURATION.md`](../docs/CONFIGURATION.md).

## Speaker setup and verification

Repository helpers:

```bash
./scripts/record_voice.sh
./scripts/create_speaker_in_container.sh
./scripts/verify_tts_gpu.sh
```

Start the service set with:

```bash
./scripts/start_services.sh
```

See [`../docs/ACCEPTANCE.md`](../docs/ACCEPTANCE.md) before treating successful
container startup as end-to-end microphone or playback acceptance.
