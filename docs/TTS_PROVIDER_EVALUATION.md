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
contains the provider contract, an Oute adapter, isolated Fun-CosyVoice3 and
Qwen3-TTS candidate services, and a common comparison matrix; it does not yet
contain the listening and shared-resource evidence required for an approved
replacement.

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

The maintained container currently registers only `oute`. The optional
`tts-evaluation` Compose profile exposes Fun-CosyVoice3 and Qwen3-TTS through
separate images and endpoints with the same WebSocket and health contract.
Their source/model locks live in `tts_candidates/model-lock.json`; neither is
selected by `TTS_PROVIDER` or included in the default profile. Importing a
second framework into the Oute image is not the integration strategy.

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

Or build, start, compare, and restore the two pinned candidates:

```bash
./scripts/run_tts_candidate_ab.sh
```

By default that workflow generates one local bilingual Oute reference and
binds its WAV hash and provider declaration into both candidates. An existing
authorized reference can instead be supplied without copying it into Git:

```bash
TTS_AB_REFERENCE_DIR=.chromie/private/tts-voice \
TTS_AB_SKIP_REFERENCE_GENERATION=1 \
TTS_AB_RUN_ID=<run-id> \
./scripts/run_tts_candidate_ab.sh
```

The directory must contain `reference.wav` and `reference.json`. The metadata
must carry its exact transcript, matching `audio_sha256`, and a nonempty
`license_id`; both candidate declarations retain that voice-license identity.
The workflow temporarily stops Oute and Ollama to make the run fit predictably,
so the result is isolated service evidence rather than shared-GPU
qualification.

### Local isolated deployment results

The local run `20260722-initial-isolated` loaded both exact model/runtime locks
on the RTX 5090 and passed all six objective cases for both providers. It was
run from a dirty working tree and the artifacts remain under the ignored local
`.chromie/evidence/` tree, so it is diagnostic deployment evidence rather than
source-bound Target validation.

| Provider | Cases | Median first binary | Median RTF | Cancel-to-recovery first binary |
|---|---:|---:|---:|---:|
| Fun-CosyVoice3 0.5B | 6/6 | 2.3989 s | 0.4827 | 18.2843 s |
| Qwen3-TTS 0.6B Base | 6/6 | 4.8282 s | 0.9455 | 7.7428 s |

The later run `20260722-chromie-ai-girl-v1` used the user-authorized,
AI-generated candidate reference `chromie-ai-girl-v1`, revision
`sha256:b64bf30929220e03ee310c5a43ee87dddd765050fb959833e96ef95fa377e415`.
It also passed all six objective cases for both providers:

| Provider | Cases | Median first binary | Median RTF | Cancel-to-recovery first binary |
|---|---:|---:|---:|---:|
| Fun-CosyVoice3 0.5B | 6/6 | 3.0987 s | 0.5419 | 18.7919 s |
| Qwen3-TTS 0.6B Base | 6/6 | 5.6786 s | 0.9364 | 8.0885 s |

Both runs show the same tradeoff: CosyVoice3 was faster for ordinary
synthesis, while Qwen3-TTS recovered faster after the worker was terminated
for interruption. Neither establishes a winner. No recovery bound has been
approved, no blinded listening or intended-deployment license review is
complete, and the maintained ASR, Router, Agent, and Ollama workloads were
intentionally absent. The owner approved the supplied voice style for Chromie,
but that does not accept the CosyVoice3 or Qwen3-TTS outputs or satisfy their
provider listening gate.

### OuteTTS voice-profile diagnostic

The same supplied English and Chinese recordings created separate OuteTTS
profiles with transcript/alignment similarities `1.00` and `0.95`; their
combined bilingual reference created a third profile at `1.00`. Short English
and Chinese auditions and the short mixed prompt `你好，Hello.` produced audio.
A longer mixed prompt exhausted the 4096-token generation budget without any
audio-code tokens, including its configured retry, and was rejected instead of
playing empty or incomplete audio. Rebuilt-container default-speaker tests then
reproduced stochastic exhaustion with `chromie_mixed` on a short Chinese case
and with the Chinese-aligned `chromie_zh` profile on a 26-character Chinese
case. Raising the RTX 5090 diagnostic budget to 8192 still exhausted all 7632
available generation tokens after the prompt. This locates the blocker in
Oute's cloned-speaker termination behavior rather than the configured context
size. The supplied style was therefore not promoted to the maintained default;
the profiles and source recordings remain ignored local artifacts. This is
local synthesis evidence only and does not establish pronunciation,
naturalness, voice similarity, or listening quality.

The runner verifies the provider declaration, generates WAV artifacts for the
same text, records first-binary latency, total latency, audio duration,
real-time factor, long-dialogue stability, bounded concurrency, and
post-interruption recovery. It writes `result.json` plus a
`listening-review.json` template. It intentionally sets
`selection_ready=false`: automated timing cannot judge pronunciation,
naturalness, prosody, code switching, speaker consistency, or audible defects.
New result files also record the run ID, UTC timestamp, Chromie revision, and
dirty state; a dirty run adds a clean-source rerun to the selection blockers.

## Candidate policy

Candidate descriptions below are discovery inputs, not Chromie evidence:

- [Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS) publishes 0.6B and 1.7B
  models, multilingual and streaming features, and an Apache-2.0 repository.
  Its reported “as low as” latency is a vendor result until reproduced with
  Chromie's chunking, IPC, GPU sharing, and playback path. Chromie's first
  adapter locks `Qwen3-TTS-12Hz-0.6B-Base` so it can use the same reference
  voice as CosyVoice; the current upstream API returns a completed waveform,
  so this adapter truthfully declares native audio streaming false.
- [Fun-CosyVoice3](https://github.com/FunAudioLLM/CosyVoice) publishes a 0.5B
  model, bi-streaming support, deployment tooling, and an Apache-2.0
  repository. Chromie's adapter locks `Fun-CosyVoice3-0.5B-2512`, uses native
  streamed audio chunks, and conditions on the same reference voice. It remains
  a primary comparison candidate rather than being excluded based on older
  CosyVoice generations.
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
