# TTS Provider Contract and Evaluation

This document owns Chromie's framework-neutral text-to-speech provider boundary
and the evidence required before changing the maintained backend. Runtime
configuration remains in [Configuration](CONFIGURATION.md), protocol fields in
[API Reference](API_REFERENCE.md), and claim levels in
[Acceptance](ACCEPTANCE.md).

## Decision

Chromie does not select a production TTS framework from vendor/model latency
claims alone. It first requires each candidate to implement the same
`TTSProvider` contract and then runs the same functional, latency, stability,
resource, and listening evaluation on the intended host.

The current OuteTTS deployment remains the maintained release-locked baseline.
This is not a conclusion that OuteTTS is the best backend. The repository now
contains the provider contract, an Oute adapter, and a common comparison
matrix; it does not yet contain a retained multi-provider target run or an
approved replacement.

## Ownership boundary

The provider owns:

- immutable model/runtime identity, a software-license declaration, and a
  separate license declaration for every tokenizer/weight artifact;
- provider lifecycle and readiness;
- synthesis from validated text and a named speaker profile;
- native audio streaming when the backend supports it;
- stopping or isolating native work when a request is cancelled;
- sample rate, PCM chunks, completion metadata, and comparable timing metrics;
- provider-specific speaker-profile creation behind the common operation.

The host Orchestrator continues to own:

- text scheduling and ordered audible playback;
- sentence/clause chunking of a complete response;
- output-device selection and resampling;
- barge-in, stale-session suppression, and user-visible interruption policy;
- correlation with the interaction, TaskGraph, and evidence records.

A provider must not play directly to a device or continue emitting audio after
its request is cancelled. A backend with no native streaming may yield a
completed buffer in transport-sized chunks, but its capability declaration must
keep `native_audio_streaming=false`.

## Contract

[`tts/provider.py`](../tts/provider.py) defines contract version 1:

- `TTSProviderCapabilities` declares provider provenance, software license,
  license-review status, immutable model artifacts with their own licenses,
  languages, output rates, concurrency, native streaming, cancellation,
  speaker-profile, and voice-cloning support;
- `TTSSynthesisRequest` carries stable request identity, text, speaker, and an
  optional language hint;
- `TTSAudioChunk` carries mono `pcm_s16le` plus its sample rate;
- `TTSSynthesisCompleted` carries comparable metrics and provider metadata;
- `TTSProvider` defines lifecycle, streaming synthesis, health, speakers, and
  optional profile creation;
- `TTSProviderRegistry` selects only explicitly registered adapters and fails
  closed on an unknown `TTS_PROVIDER` value.

The maintained container currently registers only `oute`. Alternative
candidate services must expose the same WebSocket and health contract before
they can enter the common A/B runner. Adding an adapter also requires immutable
source/model locks, isolated dependencies, configuration documentation, and
focused contract tests; importing a second framework into the Oute image is not
the default integration strategy.

Contract version 1 records whether a backend supports native text streaming,
but the current WebSocket request carries one complete text chunk. Therefore a
`native_text_streaming=true` declaration is discovery metadata, not evidence of
end-to-end token-to-audio streaming in Chromie. That claim requires an
incremental input transport and a retained target run.

## Common evaluation matrix

[`scenarios/tts_provider_ab.json`](../scenarios/tts_provider_ab.json) is the
single comparison input. It covers:

1. Mandarin daily speech;
2. English daily speech;
3. Chinese/English code switching;
4. interruption followed by a fresh recovery utterance;
5. a six-turn bilingual long conversation;
6. four simultaneous short requests.

Validate it without services:

```bash
python scripts/tts_provider_ab.py --check
```

Run two or more contract-compatible endpoints:

```bash
python scripts/tts_provider_ab.py \
  --provider oute=ws://127.0.0.1:5000 \
  --provider candidate=ws://127.0.0.1:5001 \
  --warmup 1 \
  --output-dir .chromie/evidence/tts-provider-ab/<run-id>
```

The runner verifies the provider declaration, generates WAV artifacts for the
same text, records first-binary latency, total latency, audio duration,
real-time factor, long-dialogue stability, bounded concurrency, and
post-interruption recovery. It writes `result.json` plus a
`listening-review.json` template. It intentionally sets
`selection_ready=false`: automated timing cannot judge pronunciation,
naturalness, prosody, code switching, speaker consistency, or audible defects.

## Candidate policy

Candidate descriptions below are discovery inputs, not Chromie evidence:

- [Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS) publishes 0.6B and 1.7B
  models, multilingual and streaming features, and an Apache-2.0 repository.
  Its reported “as low as” latency is a vendor result until reproduced with
  Chromie's chunking, IPC, GPU sharing, and playback path.
- [Fun-CosyVoice3](https://github.com/FunAudioLLM/CosyVoice) publishes a 0.5B
  model, bi-streaming support, deployment tooling, and an Apache-2.0
  repository. It remains a primary comparison candidate rather than being
  excluded based on older CosyVoice generations.
- [GPT-SoVITS](https://github.com/RVC-Boss/GPT-SoVITS) remains relevant for
  custom character-voice production and may enter the online matrix only after
  a contract adapter demonstrates interruption and sustained service behavior.
- OuteTTS remains the low-resource and GGUF/llama.cpp baseline already wired in
  Chromie. Claims about Raspberry Pi, Jetson, or CPU realtime behavior require
  measurements on that exact target.
- Fish Speech and IndexTTS may be evaluated only after their current model and
  software license terms are reviewed for the intended use. Local inference is
  not equivalent to permissive commercial licensing. In particular, the
  [Fish Speech license](https://github.com/fishaudio/fish-speech/blob/main/LICENSE)
  requires a separate agreement for commercial use, while
  [IndexTTS uses custom terms](https://github.com/index-tts/index-tts/blob/main/LICENSE).

Do not encode this candidate list as a hardcoded winner or permanent ranking.
Projects, models, runtimes, and licenses change; record exact repository and
model revisions in every retained evaluation.

## Selection gate

A provider can replace the maintained default only when all of these are true:

- its adapter passes Level A contract and cancellation tests;
- model and runtime revisions are immutable and available for offline startup;
- the full common matrix passes without empty, incomplete, stale, or
  cross-request audio;
- target-host warm runs retain cold/warm first-audio, p50/p95 total latency,
  RTF, GPU memory, utilization, power, host memory, and failure causes;
- concurrency is tested at the declared worker/resource limit while ASR,
  Router, Agent, and Ollama use the same machine;
- interruption recovery meets an approved bound and old speech never reaches
  playback after cancellation;
- a blinded listening review accepts Mandarin, English, mixed language,
  numbers/names, long-dialogue consistency, and the intended Chromie voice;
- license and distribution obligations are reviewed for software, weights,
  voices, and generated artifacts;
- retained Level B/D evidence is bound to the exact candidate source and target
  environment;
- configuration, support, rollback, model lock, and release compatibility are
  updated in the same candidate patch.

Until then, provider comparison is implemented and automatically verifiable,
but not target validated or release ready.
