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

## Built-in voice catalog

CosyVoice3 reads the source-controlled catalog under `assets/tts/voices`:

```text
assets/tts/voices/
├── manifest.json
├── chromie_zh/reference.wav + reference.json
├── chromie_en/reference.wav + reference.json
└── chromie_mixed/reference.wav + reference.json
```

`chromie_mixed` is the catalog default. Requests using `speaker_id=default`
route Chinese to `chromie_zh`, English to `chromie_en`, and mixed or unknown
text to `chromie_mixed`. Explicit speaker IDs bypass language routing.

The project owner's existing AI-generated assets are promoted once with:

```bash
python scripts/promote_builtin_tts_voices.py \
  --source-dir .chromie/private/tts-voice
git add assets/tts/voices
```

Each profile carries its exact prompt transcript and SHA-256 binding. After the
voice commit is pushed, a clean clone has no `.chromie` voice dependency.

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
  "speakers": ["default", "chromie_en", "chromie_mixed", "chromie_zh"]
}
```

`{"type":"ping"}` is equivalent. Health includes immutable provider/model
identity, declared capabilities, worker readiness, cancellation counters, and
backend-specific metadata.

### List speakers

```json
{"type": "list_speakers"}
```

CosyVoice exposes the three built-in profiles plus `default`. `default` is a
language-routed logical ID; Qwen uses the committed `chromie_mixed` profile.
The network endpoint does not mutate the source-controlled catalog.

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
TTS_VOICE_ROOT=assets/tts/voices
TTS_DEFAULT_SPEAKER=chromie_mixed
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
./scripts/run_tts_candidate_ab.sh
```

The runner retains WAVs, objective timing/stability results, and a listening
review template. Objective completion and ASR round-trip checks do not replace
human evaluation of Mandarin pronunciation, tones, prosody, speaker similarity,
or audible artifacts. See
[`../docs/TTS_PROVIDER_EVALUATION.md`](../docs/TTS_PROVIDER_EVALUATION.md).
