# Chromie TTS Service

`chromie-tts` is the GPU-backed OuteTTS speech-synthesis service. It runs inside
Docker and listens on WebSocket port `5000` by default. The host Orchestrator
owns playback, resampling to the selected output device, interruption, and
barge-in.

## Concurrency model

One process-global OuteTTS/llama.cpp interface owns mutable model and CUDA
state. Generation is therefore serialized through a single worker and lock,
even when multiple WebSocket clients are connected. `TTS_MAX_CONCURRENT_SYNTHESIS`
limits admitted synthesis work, but it does not make model generation parallel.

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
TTS_QUANTIZATION=FP16
TTS_SAMPLE_RATE=44100
TTS_CHUNK_MS=120
TTS_N_GPU_LAYERS=-1
TTS_CONTEXT_SIZE=4096
TTS_MAX_LENGTH=4096
TTS_MAX_TEXT_CHARS=220
TTS_MIN_TEXT_CHARS=4
TTS_MAX_CONCURRENT_SYNTHESIS=1
TTS_GENERATION_RETRIES=1
TTS_RESET_LLAMA_STATE=1
TTS_SPEAKER_ID=default
```

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
