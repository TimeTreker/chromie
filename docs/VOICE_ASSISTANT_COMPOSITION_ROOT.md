# VoiceAssistant Composition Root

Status: maintained boundary; structural simplification remains active

## Role

`VoiceAssistant` is the Host lifecycle and dependency-composition owner. It
connects audio input, deterministic protective reflexes, Cognitive Gateway/Core
dispatch, trusted execution, TTS/playback, evidence, and cleanup. It must not
become a second semantic planner, and it must not absorb Soridormi's physical
safety authority.

The public runtime remains intentionally stable while internal responsibilities
move behind narrow collaborators with explicit contracts and focused tests.

There is one maintained Host-to-Agent service boundary. `chromie-agent` is one
FastAPI service containing separately testable GI, GA, Planner fast/deep passes,
Reflection, and Social Attention modules/endpoints; those cognitive roles are not
independent deployment services. `VoiceAssistant` coordinates their lifecycle and
dataflow but cannot reinterpret one module's semantics or become a response author.

TTS synthesis, playback transport, echo handling, audible-delivery ordering,
and user-level barge-in remain Chromie-owned at the maintained boundary. The
current vocal semantic defect must be fixed without relocating those
responsibilities. A future hosting review requires retained evidence of a real
latency, synchronization, platform-adaptation, or resource-contention blocker;
co-location by itself is not an ownership argument.

## Extracted collaborators

The root currently composes, among other collaborators:

- `RuntimeReadyGreetingCoordinator` for bounded startup orientation and optional
  greeting delivery;
- `InputTurnLifecycle` for mutable input-turn and cancellation state;
- `PlaybackDelivery` for synthesis ordering, playback barriers, transport,
  cancellation, and audible-delivery evidence;
- `orchestrator.runtime.planner_reentry` for pure current-binding, Responsibility-
  provenance, completed-Activity, and delivered-speech validation before/after Planner
  re-entry; it has no semantic or execution authority;
- Cognitive Gateway/Core clients for admitted-turn cognition;
- trusted execution providers and evidence stores.

`RuntimeReadyGreetingCoordinator` may dispatch only exact maintained Social
Attention capabilities supplied by the Host. It cannot create a conversation
turn, infer a person or room state, interpret user intent, weaken confirmation,
or alter Soridormi safety.

## Mechanical structural baseline

The executable baseline is owned by
`config/runtime_structure_ratchets.json` and checked by:

```bash
python scripts/check_runtime_structure.py
```

At this revision the checker reports:

| Measure | Current ratchet |
|---|---:|
| `VoiceAssistant` methods | 105 |
| properties | 1 |
| `__init__` lines | 301 |
| initialized `self` attributes | 108 |
| direct-LLM compatibility call sites | 0 |

These values are a **non-growth ceiling**, not proof that structural
simplification is complete. The composition root has already moved transport, input/session,
shutdown, observability, confirmation bookkeeping, and other mechanical lifecycle concerns to
their existing owners. Historical ratchet transitions belong in Git history/CHANGELOG; this
document records only the current maintained boundary. A ratchet increase requires an explicit
reviewed before/after rationale in the same change; ordinary work must hold or lower every
ceiling.

## Remaining ownership seams

Further work is ordered by
[Roadmap structural simplification](../ROADMAP.md#structural-simplification):

| Responsibility | Required ownership direction |
|---|---|
| Host configuration | immutable typed audio, cognition, playback, session, and evidence settings composed before `VoiceAssistant` |
| playback delivery | keep synthesis, transport, playback barriers, echo handling, cancellation, and delivery evidence behind one collaborator |
| audio-device lifecycle | keep OS-default detection, validated pending-device queueing, cross-device input reset, and output rollover as Host mechanics; device discovery stays in `AudioDeviceManager` and output I/O stays in `PlaybackTransport` |
| input session lifecycle | keep microphone/VAD/ASR transport, injected audio, routed turns, idle sweeping, and deterministic task shutdown behind the session/lifecycle owners |
| direct-LLM compatibility | prove maintained-profile unreachability, then remove it or retain only a separately tested emergency contract |
| Cognitive Gateway/Core dispatch | one Host turn-execution owner that delegates semantic work without gaining semantic authority |
| observability recording | storage and lifecycle sampling remain delegated with exact turn/session correlation |
| stop, interruption, approval revocation, and active-Goal cancellation | fixed-reflex token revocation/audit bookkeeping stays with the existing confirmation token owner; interruption dispatch and Goal cancellation remain atomic Host/runtime responsibilities |
| shutdown lifecycle | top-level `shutdown_voice_assistant()` sequences mechanical teardown; task ownership remains in `InputTurnLifecycle`, playback teardown remains in Playback lifecycle/transport, session trace finalization remains in Session state, and process teardown never interprets or cancels Goals semantically |

Each extraction must preserve ordering, cancellation, confirmation, and evidence
semantics; add narrow regression tests; and lower or hold the mechanical
ratchets. File size alone is not an acceptance criterion.

Broader decomposition starts only after the active current-revision evidence closure.
Two narrow source slices are implemented. Pure Planner-reentry validation protects the
current Evidence-provenance line. Pure TTS text segmentation and Goal-list console
projection remove deterministic formatting algorithms from the composition root without
changing public runtime behavior or adding a manager. Later candidates remain the existing
ownership seams in the table, selected by
independent testability, lifecycle, configuration authority, and failure semantics;
method or file length alone does not justify a new manager. Durable memory, mood,
ambient autonomy, or another cognitive service are not part of this structural work.
