# TTS Provider Contract and Evaluation

This document owns Chromie's framework-neutral text-to-speech provider boundary
and the evidence used to compare or change backends. Runtime settings live in
[Configuration](CONFIGURATION.md), protocol fields in
[API Reference](API_REFERENCE.md), and evidence levels in
[Acceptance](ACCEPTANCE.md).

## Current decision

Chromie's maintained default TTS backend is **Fun-CosyVoice3 0.5B**. The change
was made because the maintained OuteTTS path repeatedly produced unacceptable
Mandarin pronunciation and, in one live diagnostic, leaked the bilingual voice
enrollment text into a nominally short Chinese acknowledgement. Supplying a
valid Chinese reference improved acoustic conditioning but did not repair the
model's Chinese pronunciation quality.

CosyVoice is selected as the current engineering default because it combines:

- native streamed audio chunks;
- a dedicated Chinese-capable model and text front end;
- zero-shot voice cloning from the source-controlled Chromie voice catalog;
- lower ordinary first-audio latency and RTF than the current Qwen3-TTS adapter
  in Chromie's repeated isolated comparisons.

This decision does not claim that CosyVoice is universally the best TTS system.
Its hard-cancellation recovery remains slower because synchronous inference may
require a worker restart. Qwen3-TTS remains an explicit alternative and OuteTTS
remains a low-resource GGUF fallback.

## Ownership boundary

The provider owns:

- immutable runtime/model identity and separate software/model license declarations;
- provider lifecycle, model readiness, and worker health;
- synthesis from validated text and an installed speaker/reference identity;
- accurate native-streaming and concurrency declarations;
- cancellation or isolation of native work;
- sample rate, PCM chunks, completion metadata, and comparable timing;
- provider-specific voice-reference or profile handling.

The host Orchestrator owns:

- text scheduling and ordered audible playback;
- sentence/clause chunking;
- output-device selection and resampling;
- barge-in and stale-session suppression;
- request, interaction, Goal, trace, and evidence correlation.

A provider must not play directly to a device or emit audio after its request is
cancelled.

## Provider contract

[`tts/provider.py`](../tts/provider.py) defines contract version 1. It includes
provider provenance, model artifacts, languages, rates, concurrency, native
streaming, cancellation, speaker profiles, voice cloning, request identity,
PCM chunks, completion metrics, lifecycle operations, health, and optional
provider-specific profile creation.

The maintained topology is:

| Provider | Service | Port | Status |
|---|---|---:|---|
| `fun-cosyvoice3-0.5b` | `chromie-tts` | 5000 | Default |
| `oute` | `chromie-tts-oute` | 5001 | Explicit fallback/evaluation profile |
| `qwen3-tts-0.6b-base` | `chromie-tts-qwen3` | 5002 | Explicit alternative/evaluation profile |

Unknown provider selections and provider/image mismatches fail closed.

Contract version 1 records native text streaming, but Chromie's current
WebSocket request carries one complete text chunk. Therefore native input
streaming remains capability metadata until an incremental token-to-audio input
transport is implemented and measured end to end.

## Built-in voice catalog

The default CosyVoice service reads the Git-controlled catalog under
`assets/tts/voices`. It contains `chromie_zh`, `chromie_en`, and
`chromie_mixed`; the mixed profile is the catalog default, while a request with
`speaker_id=default` routes Chinese and English text to the language-specific
profiles. Every profile binds its AI-generated WAV to the exact prompt text and
SHA-256 digest.

The initial repository migration is performed once on the owner's checkout:

```bash
python scripts/promote_builtin_tts_voices.py \
  --source-dir .chromie/private/tts-voice
git add assets/tts/voices
```

Future clones consume only the committed catalog and do not depend on `.chromie`.

## Common evaluation matrix

[`scenarios/tts_provider_ab.json`](../scenarios/tts_provider_ab.json) covers:

1. Mandarin daily speech;
2. English daily speech;
3. Chinese/English mixed text;
4. interruption followed by recovery;
5. a six-turn bilingual conversation;
6. four simultaneous short requests.

Validate it without services:

```bash
python scripts/tts_provider_ab.py --check
```

Run the pinned CosyVoice/Qwen comparison:

```bash
./scripts/run_tts_candidate_ab.sh
```

The workflow validates the committed catalog, temporarily releases the normal
shared-GPU services, starts CosyVoice on port 5000 and Qwen3-TTS on port 5002,
uses `chromie_mixed` for the cross-provider comparison, and restores the default
topology on exit. It is isolated provider evidence, not a shared-load
voice-quality conclusion.

## Retained diagnostic results

Two isolated RTX 5090 runs showed the same tradeoff:

| Provider | Median first binary | Median RTF | Cancel-to-recovery first binary |
|---|---:|---:|---:|
| Fun-CosyVoice3 0.5B | 3.0987 s | 0.5419 | 18.7919 s |
| Qwen3-TTS 0.6B Base | 5.6786 s | 0.9364 | 8.0885 s |

An earlier generated-reference run measured 2.3989 s / 0.4827 / 18.2843 s for
CosyVoice and 4.8282 s / 0.9455 / 7.7428 s for Qwen. Both runs were isolated and
came from dirty working trees. They established a repeatable ordinary-latency
versus interruption-recovery tradeoff, not a listening-quality verdict.

The corrected Oute `chromie_mixed` profile had 776 DAC code pairs and passed
transport/stability matrices at an 8192-token budget. A later live diagnostic
nevertheless reproduced bilingual enrollment-text leakage and unnatural Chinese.
That result is the decisive reason Oute is no longer the maintained default.

## Cancellation and readiness

CosyVoice exposes one singleton model worker. Chromie therefore sets host TTS
concurrency to one, validates application health over WebSocket, and performs a
no-playback warm synthesis before declaring the default provider ready.

Cancellation uses a bounded drain while retaining the singleton lock. An
almost-complete result is discarded without unloading the model. Timeout,
malformed output, or a dead worker causes a fail-closed restart. Health reports
drain and restart counters. This guarantees stale-audio isolation but does not
yet eliminate the cold-reload tail of a hard cancellation.

## Mandarin quality gate

The existing objective matrix must be supplemented with a Mandarin-focused
listening set containing:

- tones and common polyphonic characters;
- numbers, dates, units, and decimals;
- robot and autonomous-driving terminology;
- names and product terms;
- Chinese/English code switching;
- confirmations, warnings, apologies, questions, and longer dialogue.

Retain CER/term correctness and ASR round-trip diagnostics, but use blinded
human listening for pronunciation, naturalness, prosody, speaker similarity,
and audible artifacts. A successful waveform or ASR match alone is not voice
acceptance.

## Alternative backend policy

Qwen3-TTS remains the primary comparison and fallback for faster post-cancel
recovery. Oute remains the GGUF/llama.cpp low-resource fallback. Additional
frameworks may be added only through the same provider contract, immutable
model/runtime locks, cancellation tests, and common evaluation surface.

A future default change should update configuration, model locks, launchers,
health checks, operational documentation, tests, and rollback instructions in
one patch. It must not be implemented by changing only `TTS_PROVIDER`.
