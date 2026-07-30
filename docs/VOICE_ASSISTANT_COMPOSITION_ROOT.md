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

## Intentionally composed responsibilities

A post-extraction audit leaves these responsibilities in the composition root
until a later concrete maintenance need justifies another independently tested
collaborator:

| Responsibility | Why it remains composed |
|---|---|
| audio device creation and VAD/ASR handoff | shares lifecycle ownership with microphone queues and injected-audio acceptance |
| playback worker and synthesis ordering | tightly coupled to interruption, generation cancellation, and session delivery evidence |
| Cognitive Gateway/Core turn dispatch | already delegates semantic work to explicit runtime and Agent boundaries |
| stop, interruption, approval revocation, and active-Goal cancellation | deterministic Host safety/commitment coordination must remain atomic |
| evidence, episode, and runtime trace recording | cross-cuts the lifecycle and already delegates storage/trace mechanics to dedicated modules |
| cleanup | is the final composition-root responsibility for every owned collaborator and resource |

This audit is not a prohibition on future extraction. Each future activity must
name a concrete seam, preserve ordering and cancellation, add narrow tests, and
leave `VoiceAssistant` as the public lifecycle owner.
