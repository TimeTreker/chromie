# VoiceAssistant Composition Root

Status: current composition and decomposition contract

## Role

`VoiceAssistant` remains the Host lifecycle and dependency-composition owner. It
connects audio input, deterministic reflexes, Cognitive Gateway/Core dispatch,
trusted execution, TTS/playback, evidence, and cleanup. Decomposition must make
those responsibilities independently testable without moving semantic authority
into Host rules or physical safety out of Soridormi.

## Completed first extraction set

The runtime-ready greeting playback lifecycle is owned by
`RuntimeReadyGreetingCoordinator` in
`orchestrator/runtime/runtime_ready_greeting.py`.

Its explicit inputs are:

- an immutable eligibility and timeout policy;
- an injected model/configuration greeting generator;
- validated-text and TTS scheduling callables;
- playback-start waiter access and the current playback order.

Its outputs are deterministic side effects only: optional scheduling, bounded
playback-start/completion waiting, diagnostic logs, and fail-open release to the
microphone loop. It cannot create a conversation turn, interpret user intent,
authorize a Capability, or alter Soridormi safety.

`VoiceAssistant._announce_runtime_ready` is now a delegation wrapper. Wording
generation remains behind the existing validated LLM boundary, while scheduling
and playback barrier semantics live in the collaborator. Existing timeout,
fallback, injected-audio skip, cancellation, and playback ordering behavior is
preserved.

## Remaining decomposition backlog

The first extraction proves the collaborator pattern; it does not retire the
composition-root risk. The current archive still contains an 8,886-line module,
a `VoiceAssistant` class with 167 directly declared methods, and a 615-line
initializer. These counts are diagnostic signals, not mechanical limits. Further
extraction begins only after current-revision target evidence is retained, then
uses live traces and failure evidence to select one independently tested owner at
a time.

The main candidate responsibilities are:

| Responsibility | Required extraction boundary |
|---|---|
| audio device creation and VAD/ASR handoff | one input-turn lifecycle owner with explicit queue and injected-audio contracts |
| playback worker and synthesis ordering | one output/playback owner preserving interruption, cancellation, ordering, and delivery evidence |
| Cognitive Gateway/Core turn dispatch | one turn-execution owner that delegates semantic work without gaining semantic authority |
| stop, interruption, approval revocation, and active-Goal cancellation | an atomic deterministic control owner with explicit state transitions |
| evidence, episode, and runtime trace recording | one observability coordinator with typed events and no semantic decisions |
| cleanup | the root retains only top-level reverse-order collaborator shutdown |

This audit is not a prohibition on future extraction. Each future activity must
name a concrete seam, preserve ordering and cancellation, add narrow tests, and
leave `VoiceAssistant` as the public lifecycle owner.
