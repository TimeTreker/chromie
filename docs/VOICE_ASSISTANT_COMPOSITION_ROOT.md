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
FastAPI service containing separately testable UMI, GA, Planner, Value Judgment, Social Cognition
and Reflection modules/endpoints. Optional Social Attention is part of Social Cognition
output (`auxiliary_activities` on its Communicative Act), not Planner output or another
module or endpoint; these cognitive roles are not
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

Host behavior that runs against the root lives in function modules under
`orchestrator/runtime/` that take the `VoiceAssistant` as `host`:
`routed_turn_host` (routed-turn intake), `cognitive_pipeline_host` (goal-driven
runtime application, Goal state and named-Goal cancellation),
`confirmation_host` (pending-confirmation staging and replies),
`reflex_cancellation_host` (reflex cancellation and receipt reconciliation),
`cognitive_outcome_host` (cognitive execution closure and outcome delivery),
`planner_reentry_host` (Planner re-entry after terminal results and provider
state), `interaction_dispatch_host` (detached dispatch and terminal consumers),
`interaction_speech_host` (Capability Runtime speech scheduling), `tts_echo`
(ASR echo detection), `tts_text.split_tts_text` and the startup greeting
functions in `runtime_ready_greeting`. `VoiceAssistant` keeps thin methods only
where other modules, tests or live checks bind or replace a seam on the
instance. These modules gain no semantic authority; the Host semantic-authority
policy guards apply to them as to `orchestrator.py`.

`RuntimeReadyGreetingCoordinator` may dispatch only exact maintained Social
Attention capabilities supplied by the Host. It cannot create a conversation
turn, infer a person or room state, interpret user intent, weaken confirmation,
or alter Soridormi safety.

## Mechanical structural baseline

Blocking ownership rules and size ratchets are owned by
`config/runtime_structure_ratchets.json` and checked by:

```bash
python scripts/check_runtime_structure.py
```

The config holds the VoiceAssistant method, property, `__init__` line and
initialized-attribute baselines, and line baselines for `orchestrator.py` and the
other runtime files over 3,000 lines, measured at its `size_baseline_revision`.
Each run reports current values and signed deltas, and fails if a value grows
above its baseline. Staying under the baselines does not prove that structural
simplification is complete. Missing collaborators,
returned lifecycle state, forbidden compatibility methods and any direct legacy
Host model call remain blocking. The Host makes no model call. When an owner
explicitly sets `ORCH_RUNTIME_READY_GREETING_SPEECH_ENABLED=1` and leaves
`ORCH_RUNTIME_READY_GREETING_TEXT` empty, `VoiceAssistant._generate_runtime_ready_greeting`
sends the owner-approved Mind and trusted local clock facts to Social Cognition
(`POST /social-cognition/startup-greeting`); SC decides whether to speak and authors the
words, and the Host only validates delivery bounds. A configured text is the owner's own
wording and is played as given. The composition root has already moved transport, input/session,
shutdown, observability, confirmation bookkeeping, and other mechanical lifecycle concerns to
their existing owners. Historical transitions belong in Git history/CHANGELOG.
Review size deltas alongside ownership and readability; do not move code merely to
reduce a count. [Repository Engineering Policies](REPOSITORY_ENGINEERING_POLICIES.md)
owns the size-review and rebaselining rules.

## Remaining ownership seams

Further work is ordered by
[Roadmap structural simplification](../ROADMAP.md#structural-simplification):

| Responsibility | Required ownership direction |
|---|---|
| Host configuration | immutable typed audio, cognition, playback, session, and evidence settings composed before `VoiceAssistant` |
| playback delivery | keep synthesis, transport, playback barriers, echo handling, cancellation, and delivery evidence behind one collaborator |
| audio-device lifecycle | keep OS-default detection, validated pending-device queueing, cross-device input reset, and output rollover as Host mechanics; device discovery stays in `AudioDeviceManager` and output I/O stays in `PlaybackTransport` |
| input session lifecycle | keep microphone/VAD/ASR transport, injected audio, routed turns, idle sweeping, and deterministic task shutdown behind the session/lifecycle owners |
| Cognitive Gateway/Core dispatch | one Host turn-execution owner that delegates semantic work without gaining semantic authority |
| observability recording | storage and lifecycle sampling remain delegated with exact turn/session correlation |
| stop, interruption, approval revocation, and active-Goal cancellation | fixed-reflex token revocation/audit bookkeeping stays with the existing confirmation token owner; interruption dispatch and Goal cancellation remain atomic Host/runtime responsibilities |
| shutdown lifecycle | top-level `shutdown_voice_assistant()` sequences mechanical teardown; task ownership remains in `InputTurnLifecycle`, playback teardown remains in Playback lifecycle/transport, session trace finalization remains in Session state, and process teardown never interprets or cancels Goals semantically |

Each extraction must preserve ordering, cancellation, confirmation, and evidence
semantics, add narrow regression tests, and preserve blocking ownership checks.
Review the size deltas; file size alone is not an acceptance criterion.

Broader decomposition starts only after the active current-revision evidence closure.
Two narrow source slices are implemented. Pure Planner-reentry validation protects the
current Evidence-provenance line. Pure TTS text segmentation and Goal-list console
projection remove deterministic formatting algorithms from the composition root without
changing public runtime behavior or adding a manager. Later candidates remain the existing
ownership seams in the table, selected by
independent testability, lifecycle, configuration authority, and failure semantics;
method or file length alone does not justify a new manager. Durable memory, mood,
ambient autonomy, or another cognitive service are not part of this structural work.
