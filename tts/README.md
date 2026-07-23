# Chromie TTS Service

`chromie-tts` is Chromie's framework-neutral speech-synthesis endpoint on
WebSocket port `5000`. The maintained default implementation is
**Fun-CosyVoice3 0.5B**. The host Orchestrator continues to own response
chunking, output-device playback, resampling, ordering, barge-in, stale-session
suppression, and user-visible interruption semantics.

The provider boundary is defined in `provider.py`. An unknown or mismatched
`TTS_PROVIDER` fails closed at startup. OuteTTS and Qwen3-TTS implement the same
wire contract as explicit alternative backends:

| Backend | Service | Host port | Role |
|---|---|---:|---|
| CosyVoice3 | `chromie-tts` | 5000 | Maintained default |
| OuteTTS | `chromie-tts-oute` | 5001 | Low-resource GGUF fallback and diagnostic reference generator |
| Qwen3-TTS | `chromie-tts-qwen3` | 5002 | Alternative cloned-voice backend |

The alternatives are enabled through the `tts-evaluation` Compose profile or
selected by `./scripts/start_chromie.sh --tts-backend ...`.

## Default voice reference

CosyVoice3 requires an operator-authorized reference WAV, its exact transcript,
and a nonempty license/authorization identity. Install it before the first
startup:

```bash
python scripts/tts_reference.py install \
  --source-wav /path/to/chromie-reference.wav \
  --transcript '这里填写录音中逐字一致的文本。' \
  --license-id 'user-owned-recording'
```

This creates ignored local files under:

```text
.chromie/private/tts-voice/reference.wav
.chromie/private/tts-voice/reference.json
```

Validate them independently with:

```bash
python scripts/tts_reference.py validate
```

The metadata binds the complete WAV with SHA-256. Startup fails closed when the
WAV, transcript, authorization identity, or digest is missing or inconsistent.
Private voice material is never committed to Git.

## Concurrency and interruption

CosyVoice currently uses one resident model worker. The supported host
concurrency is therefore `ORCH_TTS_CONCURRENCY=1`; increasing host concurrency
would only add hidden queueing. CosyVoice emits native streamed audio chunks,
but its upstream inference call remains synchronous inside the worker.

When a request is cancelled, Chromie first holds the singleton worker lock for
a bounded drain. A nearly complete result is discarded without unloading the
model. If the worker does not finish within the drain bound, it is restarted
fail-closed before another request begins. This prevents stale audio, although
a hard cancellation can still pay a model cold-reload cost.

OuteTTS owns mutable llama.cpp/DAC state in restartable worker processes and may
use more than one worker on a high-memory diagnostic profile. Qwen3-TTS returns
a completed native waveform through the same transport contract and declares
its streaming capability accurately.

## WebSocket protocol

Connect to `ws://<host>:5000` for the default provider.

### Health

Request:

```json
{"type": "health"}
```

Response:

```json
{
  "type": "pong",
  "service": "tts",
  "provider_contract_version": 1,
  "provider": {"provider_id": "fun-cosyvoice3-0.5b"},
  "provider_health": {},
  "sample_rate": 24000,
  "speakers": ["default"]
}
```

`{"type":"ping"}` is equivalent. Health includes immutable provider/model
identity, declared capabilities, worker readiness, cancellation counters, and
backend-specific metadata.

### List speakers

```json
{"type": "list_speakers"}
```

CosyVoice and Qwen expose the installed cloned reference as `default`. The
reference itself is managed by `scripts/tts_reference.py`, not by a network
speaker-creation operation.

### Stream synthesis

Request:

```json
{
  "type": "synthesize_stream",
  "request_id": "turn-123-speech-1",
  "text": "你好，我是 Chromie。",
  "speaker_id": "default",
  "language_hint": "zh"
}
```

Response sequence:

1. JSON `start` metadata with sample rate, PCM format, channels, and provider declaration;
2. one or more binary mono `pcm_s16le` chunks;
3. JSON `end` metadata with comparable timing and provider metadata, or JSON `error`.

The Orchestrator may split one logical response into ordered synthesis requests
and may resample the provider rate for the selected playback device.

### Oute-only speaker creation

The optional Oute fallback service retains `create_speaker` on port `5001` for
its private v3 speaker profiles. That operation is not part of the default
CosyVoice endpoint. Use `./scripts/create_speaker_in_container.sh` only when
explicitly operating the Oute fallback.

## Configuration

Maintained defaults:

```env
CHROMIE_TTS_BACKEND=cosyvoice3
TTS_PROVIDER=fun-cosyvoice3-0.5b
TTS_REFERENCE_DIR=.chromie/private/tts-voice
COSYVOICE3_MODEL_ID=FunAudioLLM/Fun-CosyVoice3-0.5B-2512
ORCH_TTS_CONCURRENCY=1
TTS_COSYVOICE_COMPACT_COGNITION=1
TTS_COSYVOICE_OLLAMA_MODEL=qwen3:4b
```

The compact cognition setting keeps one Ollama model resident while CosyVoice
shares the GPU. It is a resource policy, not a change to semantic authority or
safety contracts.

Select an alternative explicitly:

```bash
./scripts/start_chromie.sh --tts-backend oute
./scripts/start_chromie.sh --tts-backend qwen3
```

Normal startup uses CosyVoice:

```bash
./scripts/start_chromie.sh
```

## Verification and comparison

Verify the selected backend and GPU path:

```bash
./scripts/verify_tts_gpu.sh
```

Run the common CosyVoice/Qwen comparison matrix:

```bash
TTS_AB_REFERENCE_DIR=.chromie/private/tts-voice \
TTS_AB_SKIP_REFERENCE_GENERATION=1 \
./scripts/run_tts_candidate_ab.sh
```

The runner retains WAVs, objective timing/stability results, and a listening
review template. Objective completion and ASR round-trip checks do not replace
human evaluation of Mandarin pronunciation, tones, prosody, speaker similarity,
or audible artifacts. See
[`../docs/TTS_PROVIDER_EVALUATION.md`](../docs/TTS_PROVIDER_EVALUATION.md).
