# VoiceAssistant Composition Root

Status: maintained current boundary; approved Soridormi migration target

## Role

`VoiceAssistant` is the current Host lifecycle and dependency-composition
owner. Today it connects audio input, deterministic protective reflexes,
Cognitive Gateway/Core dispatch, trusted execution, TTS/playback, evidence, and
cleanup. It must not become a second semantic planner, and it must not absorb
Soridormi's execution or physical-safety authority.

The long-term owner is the **Chromie Interaction Orchestrator**. It remains in
Chromie and coordinates user interaction, not platform execution. The public
runtime must stay stable while TTS, media, body, and device execution move
behind Soridormi contracts with equivalent cancellation and evidence.

## Extracted collaborators

The root currently composes, among other collaborators:

- `RuntimeReadyGreetingCoordinator` for bounded startup orientation and optional
  greeting delivery;
- `InputTurnLifecycle` for mutable input-turn and cancellation state;
- `PlaybackDelivery` for synthesis ordering, playback barriers, transport,
  cancellation, and audible-delivery evidence;
- Cognitive Gateway/Core clients for admitted-turn cognition;
- trusted execution providers and evidence stores.

`RuntimeReadyGreetingCoordinator` may dispatch only exact maintained Social
Attention capabilities supplied by the Host. It cannot create a conversation
turn, infer a person or room state, interpret user intent, weaken confirmation,
or alter Soridormi safety.

## Approved target boundary

The Chromie Interaction Orchestrator retains:

- session, conversation, and input-turn lifecycle;
- VAD and ASR coordination over normalized audio streams;
- Cognitive Gateway and Cognitive Core dispatch;
- Goal state, confirmation dialogue, cancellation semantics, and user-level
  interruption scope;
- platform-neutral vocal and activity requests;
- authorization identity and end-to-end evidence correlation; and
- top-level startup and reverse-order shutdown of its collaborators.

The following responsibilities move to Soridormi Runtime as their replacement
contracts become proven:

- TTS and other vocal synthesis execution;
- PCM stream execution, output-device use, and audible-output receipts;
- music, recording, and sound-effect playback;
- body motion, expression, and posture execution;
- provider-local multimodal preparation, start, resource arbitration,
  cancellation, recovery, and per-member execution evidence; and
- all simulator, robot, microphone, speaker, sensor, and operating-system device
  adaptation through the Soridormi Platform Provider.

Chromie still decides what to say, whether the requested mode is speech,
recitation, singing, or humming, and how that outcome relates to the user's
Goals. Soridormi decides how an authorized vocal or activity request is executed
on the current platform. Neither side may silently reinterpret the other's
contract.

The current `PlaybackDelivery` collaborator is therefore a migration boundary,
not the desired permanent device owner. It remains authoritative until
Soridormi returns equivalent streaming, interruption, delivery, and evidence
contracts; removal before that proof would create a regression rather than a
simplification.

## Mechanical structural baseline

The executable baseline is owned by
`config/runtime_structure_ratchets.json` and checked by:

```bash
python scripts/check_runtime_structure.py
```

At this revision the checker reports:

| Measure | Current ratchet |
|---|---:|
| `VoiceAssistant` methods | 187 |
| properties | 1 |
| `__init__` lines | 409 |
| initialized `self` attributes | 139 |
| direct-LLM compatibility call sites | 1 |

These values are a **non-growth ceiling**, not proof that structural
simplification is complete. Constructor and state ownership have improved, but
the method-count reduction criterion remains open. A ratchet increase requires
an explicit reviewed before/after rationale in the same change; ordinary work
must hold or lower every ceiling.

## Remaining ownership seams

Further work is ordered by
[Roadmap structural simplification](../ROADMAP.md#structural-simplification):

| Responsibility | Required ownership direction |
|---|---|
| Host configuration | immutable typed audio, cognition, playback, session, and evidence settings composed before `VoiceAssistant` |
| playback delivery | keep the current synthesis/playback path behind one collaborator until Soridormi vocal execution has equivalent streaming, cancellation, and delivery receipts; then remove direct TTS and output-device ownership from Chromie |
| input session lifecycle | retain VAD/ASR, routed turns, and interaction interruption in Chromie while moving device-specific microphone capture behind a normalized Soridormi platform stream |
| platform execution dispatch | reduce the Host to authorization, immutable dispatch, cancellation-scope selection, and outcome correlation; Soridormi owns provider-local scheduling and execution |
| direct-LLM compatibility | prove maintained-profile unreachability, then remove it or retain only a separately tested emergency contract |
| Cognitive Gateway/Core dispatch | one Host turn-execution owner that delegates semantic work without gaining semantic authority |
| observability recording | storage and lifecycle sampling remain delegated with exact turn/session correlation |
| stop, interruption, approval revocation, and active-Goal cancellation | Chromie resolves user-level scope atomically; Soridormi executes the authorized output, motion, interaction, or emergency cancellation and returns evidence |
| cleanup | the root retains only top-level reverse-order collaborator shutdown |

Each extraction must preserve ordering, cancellation, confirmation, and evidence
semantics; add narrow regression tests; and lower or hold the mechanical
ratchets. File size alone is not an acceptance criterion.

## Migration completion criteria

The composition-root migration is complete only when:

- no Chromie module selects a TTS backend, sound device, robot controller,
  simulator, or platform SDK;
- normal Speaking and platform-facing Activity execution cross one immutable
  Soridormi envelope;
- output-only interruption remains distinct from Goal or body cancellation;
- current confirmation, playback-start, cancellation, and evidence tests have
  equivalent Soridormi-backed coverage;
- structural ratchets decrease rather than moving the same monolith to another
  file; and
- live retained traces prove speech, media, body execution, failure, and stop
  behavior for the migrated revision.
