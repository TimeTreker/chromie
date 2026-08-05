# VoiceAssistant Composition Root

Status: first extraction implemented; further decomposition queued after
current-revision live proof

## Role

`VoiceAssistant` remains the Host lifecycle and dependency-composition owner. It
connects audio input, deterministic reflexes, Cognitive Gateway/Core dispatch,
trusted execution, TTS/playback, evidence, and cleanup. Decomposition must make
those responsibilities independently testable without moving semantic authority
into Host rules or physical safety out of Soridormi.

## Completed first extraction set

The runtime-ready orientation and optional greeting lifecycle is owned by
`RuntimeReadyGreetingCoordinator` in
`orchestrator/runtime/runtime_ready_greeting.py`.

Its explicit inputs are:

- an immutable eligibility and timeout policy;
- an injected bounded non-verbal orientation callback;
- an optional model/configuration greeting generator;
- validated-text and TTS scheduling callables;
- playback-start waiter access and the current playback order.

Its outputs are deterministic side effects only: one optional untargeted
startup-orientation dispatch, optional speech scheduling, bounded
playback-start/completion waiting, diagnostic logs, and fail-open release to the
microphone loop. The orientation callback may use only exact maintained Social
Attention capabilities and provider-declared schemas. It cannot create a
conversation turn, infer a person or room state, interpret user intent, weaken
confirmation, or alter Soridormi safety.

`VoiceAssistant._announce_runtime_ready` is now a delegation wrapper. Wording
generation remains behind the existing validated LLM boundary, while scheduling
and playback barrier semantics live in the collaborator. Existing timeout,
fallback, injected-audio skip, cancellation, and playback ordering behavior is
preserved.

## Current structural baseline

The 2026-08-01 runtime OS-default device correction repaired a reproduced Host
audio-lifecycle gap before target-evidence closure. Because stream ownership is
still in `VoiceAssistant`, the change necessarily grew that existing root:

| Measure | Before runtime following | Current | Delta |
|---|---:|---:|---:|
| `orchestrator/orchestrator.py` | 8,902 lines | 9,164 lines | +262 |
| `VoiceAssistant` methods | 167 | 174 | +7 |
| `VoiceAssistant.__init__` | 617 lines | 626 lines | +9 |
| distinct `self` attributes referenced by `__init__` | 160 | 167 | +7 |

The existing `AudioDeviceManager` grew from 162 to 293 lines; no new document,
environment variable, compatibility path, or architectural term was added. The
consolidation opportunity is the already queued playback-delivery and input-turn
lifecycle work: after evidence closure, those owners should absorb default-device
monitoring, stream rollover, and switch state, then remove the seven temporary
delegation/state methods from the composition root.

These counts are structural evidence, not semantic quality measures. They show that
calling all remaining responsibilities “intentionally composed” is not a
sufficient closure criterion. The canonical gate prerequisite is complete.
Further extraction begins only after the current-revision live-proof
implementation, default target-evidence profile, and queued grounded-response
latency Issue close, then uses live traces and failure evidence to select one
independently tested owner at a time.

## Queued ownership seams

Further work is ordered by
[Repository Engineering Sustainability Plan](REPOSITORY_ENGINEERING_SUSTAINABILITY_PLAN.md):

| Responsibility | Required ownership direction |
|---|---|
| Host configuration | immutable typed audio, cognition, playback, session, and evidence settings composed before `VoiceAssistant` |
| playback delivery | one owner for TTS chunking, synthesis order, transport-versus-audible streaming, incremental PCM playback, playback barriers, echo handling, cancellation, output-generation versus future-result eligibility, and delivery evidence |
| input turn/session lifecycle | `InputTurnLifecycle` owns mutable input/task state and `InputSessionRuntime` owns microphone/VAD/ASR transport, injected audio, routed turns, idle sweeping, and deterministic task shutdown; `SessionRegistry` remains the independent trace/session store |
| direct-LLM compatibility path | prove maintained-profile reachability; remove it when unreachable or confine it to an explicit rollback contract |
| Cognitive Gateway/Core turn dispatch | one turn-execution owner that delegates semantic work without gaining semantic authority |
| observability recording | keep storage mechanics delegated and move lifecycle sampling only when a concrete owner can preserve correlation |
| stop, interruption, approval revocation, and active-Goal cancellation | remain atomic and Host-owned unless a narrow collaborator preserves the exact deterministic contract |
| cleanup | the root retains only top-level reverse-order collaborator shutdown |

Each activity must reduce the structural baseline, preserve ordering and
cancellation, add narrow tests, and leave `VoiceAssistant` as the public
lifecycle owner. Arbitrary file-size or method-count targets do not replace
behavioral evidence.
