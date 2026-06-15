# Chromie ASR Service

`chromie-asr` is the GPU-backed final-utterance transcription service. It runs
inside Docker and listens on WebSocket port `9001` by default.

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
{"type": "pong", "service": "asr"}
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

The service converts PCM16 to float32 and calls `faster-whisper` once per binary
message. Blocking model inference and consumption of faster-whisper's segment
generator run in a bounded thread executor rather than on the WebSocket event
loop. Separate health/ping connections therefore remain responsive while an
utterance is being transcribed.

## Configuration

```env
ASR_HOST=0.0.0.0
ASR_PORT=9001
ASR_MODEL=dropbox-dash/faster-whisper-large-v3-turbo
ASR_MODEL_REVISION=<immutable-hugging-face-commit>
ASR_DEVICE=cuda
ASR_COMPUTE_TYPE=float16
ASR_SAMPLE_RATE=16000
ASR_LANGUAGE=
ASR_BEAM_SIZE=1
ASR_VAD_FILTER=false
ASR_CONDITION_ON_PREVIOUS_TEXT=false
ASR_MAX_CONCURRENT_TRANSCRIPTIONS=1
```

`ASR_MODEL_REVISION` is passed to Faster-Whisper and must identify the exact
model snapshot. Maintained hardware profiles provide revisions recorded in
[`../release/model-lock.json`](../release/model-lock.json). Custom models must
provide their own immutable revision.

Leaving `ASR_LANGUAGE` empty enables model language detection. Host-side VAD is
the normal utterance boundary; enabling the model's VAD filter is a separate
choice.

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
