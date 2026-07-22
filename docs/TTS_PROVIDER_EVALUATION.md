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
combined bilingual reference created a third profile at `1.00`. Those checks
were incomplete: the soundfile fallback returned `[channels, samples]` while
OuteTTS's DAC path requires `[batch, channels, samples]`. Oute's loudness stage
therefore collapsed each complete recording to one sample, and all three JSON
profiles contained only one DAC code pair even though text alignment passed.
The earlier 4096/8192 exhaustion result came from those malformed profiles and
did not isolate a model-only termination defect.

The loader now preserves all three axes. Creation rejects missing/mismatched DAC
codebooks, fewer than 30 acoustic codes, or less than 50 percent reference-audio
coverage; invalid stored profiles rebuild only from a matching WAV and exact
transcript. Generation deep-copies profiles because OuteTTS 0.4.4 mutates the
last aligned word while composing a prompt, and accepted profiles are reloaded
across every service worker. The regenerated `chromie_mixed` profile has 776
DAC code pairs, 28/28 acoustically conditioned words, and 10.35 seconds of code
coverage. A corrected-profile 4096 full matrix still exhausted one 23-character
Chinese dialogue turn because its approximately 1900-token acoustic prompt left
insufficient stochastic generation headroom. With the RTX 5090 context and
generation limit raised to 8192 and per-request llama reset enabled, a 10/10
smoke passed and two repeated full matrices each passed all six Mandarin,
English, mixed, interruption/recovery, long-dialogue, and concurrency cases.
Median first-binary/RTF was `6.7510 s/0.7769` and `7.1491 s/0.7841`.

The owner installation now selects `chromie_mixed`, but the profile and source
recordings remain ignored local artifacts. A clean installation without that
profile still uses Oute's built-in speaker. This is local, dirty-tree synthesis
evidence; it does not establish pronunciation, naturalness, voice similarity,
physical speaker quality, or release readiness.

A later live-output diagnosis found a content failure that the transport matrix
did not measure: OuteTTS `chromie_mixed` generated the bilingual enrollment
sentence inside nominally short Chinese acknowledgement cues, and the remaining
Chinese was audibly unnatural. Local ASR reproduced the leaked English sentence.
This means the successful Oute matrix proves completion, stability, and timing,
not intelligibility or acceptance of that speaker. `chromie_mixed` remains the
owner installation's configured experiment, but it has not passed the listening
gate and must not be described as a production-quality Chinese voice.

The host now binds fast-first cache keys to the endpoint, provider/model
declaration, speaker ID, reported speaker revision, and optional operator
revision. Every existing or newly generated cue is duration-limited and, by
default, transcribed through ASR before it can enter the in-memory playback
cache. A mismatched cue fails closed. This protects acknowledgement playback;
it does not repair OuteTTS pronunciation or promote another provider. Missing
cues receive at most two generation attempts by default when synthesis
completes but content validation rejects the sample; every attempt must pass
the same gate, and rejected audio is never cached. A synthesis timeout aborts
the remaining startup generation instead of cancelling and repeatedly
cold-loading the provider.

For supervised listening only, `./scripts/start_chromie.sh --tts-trial
cosyvoice --keep-services` selects the isolated CosyVoice3 service and the
installation-local authorized reference for that run. It stops OuteTTS to avoid
GPU contention, maps every cognitive lane to the compact
`TTS_COSYVOICE_TRIAL_OLLAMA_MODEL` (`qwen3:4b` by default), permits one resident
Ollama model, and points the host Orchestrator at port 5001 without editing the
normal provider configuration. It loads existing validated fast-first cues but
does not generate missing cues before opening the microphone. The next normal
launch restores OuteTTS and the normal model profile. This trial path is not a
provider-selection decision.

The July 22 local trial also exposed and fixed a candidate deployment defect:
`onnxruntime-gpu==1.18.0` expected cuDNN 8 while the CUDA 12.8 candidate image
provides cuDNN 9. The candidate now pins 1.18.1 and starts its normalizer with
`CUDAExecutionProvider`; its ModelScope WeText cache is persistent. After that
fix, all six English and Chinese fast-first cues passed the duration and ASR
content gates. This is local automated content evidence, not the operator's
listening verdict or a provider promotion.

The first full-stack trial exposed a separate shared-resource startup failure
that the isolated matrix could not reveal. The normal `qwen3:4b` plus
`gemma4:26b` cognitive profile, CosyVoice, ASR, and runtime processes occupied
roughly 28 GiB of GPU memory before candidate inference. Short-cue synthesis
then exceeded its 30-second request budget; cancelling each WebSocket request
restarted CosyVoice's process worker and the next retry paid another cold load.
After the 120-second outer budget, Python 3.10's `asyncio.TimeoutError` escaped
the old built-in-only timeout handler and terminated the host before microphone
startup. The trial-specific one-model profile and disabled missing-cue startup
generation remove that contention loop, while the host now treats the outer
timeout as non-fatal. On July 22 the exact full launcher reached service
readiness, resolved the cache in 4.1 ms with zero generation, and logged
`Microphone started`. This is local operational startup evidence only; no voice
quality or provider-selection verdict follows from it.

The following live conversation exposed two more trial-topology limits. First,
the host used two concurrent synthesis requests because the RTX 5090 Oute
profile has two workers, while CosyVoice has one singleton model worker. The
second request therefore waited behind the first without gaining throughput.
Second, cancelling synchronous candidate inference restarted and reloaded the
worker, reproducing the measured roughly 18–19 second recovery tail. These
delays made speech arrive after related simulator effects and made an unrelated
goal-lifecycle defect much more visible, but CosyVoice did not cause the old
walk/blink plan to be selected: the Router had correctly classified the
reported follow-up as `chat/social_exchange` before the cognitive runtime
replayed stale goals.

The reversible CosyVoice trial now forces `ORCH_TTS_CONCURRENCY=1`, validates
ASR/TTS application health over WebSocket rather than treating an open TCP port
as readiness, and completes one no-playback synthesis with nonempty PCM before
the launcher reports the candidate ready. Candidate cancellation holds the
singleton lock for a bounded three-second drain: an almost-complete result is
discarded without unloading the model, while timeout, malformed output, or a
dead worker still triggers a fail-closed restart before another request can
begin. Health exposes drain and restart counters. Because upstream CosyVoice
inference is still synchronous at this boundary, a request that cannot finish
inside the drain may continue to pay the cold-reload recovery cost; the fix
prevents false concurrency/readiness claims and stale audio, not a new latency
claim or provider promotion.

The rebuilt service-only trial completed both application-health checks and a
full no-playback synthesis under the shared service load, returning 485760
bytes of PCM from `fun-cosyvoice3-0.5b`. That run also exposed an older host
Orchestrator still holding the microphone and submitting requests while the
containers were recreated. The old process was stopped, and the top-level
launcher now checks the same exclusive Orchestrator lock before changing
runtime files or services. This is startup and synthesis-readiness evidence;
the host Orchestrator was deliberately left stopped, so it is not a supervised
listening or robot-behavior result.

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
