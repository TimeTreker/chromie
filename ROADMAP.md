# Chromie Roadmap

Chromie is in active development. This roadmap owns delivery order and exit
criteria; current implementation and evidence state live in
[docs/STATUS.md](docs/STATUS.md).

The current focus is a **Goal-driven single semantic authority**. The Cognitive
Gateway owns ingress, protective reflexes, and attention admission. The
Goal-driven Cognitive Core owns ordinary semantic interpretation, goal
association, planning, response composition, and outcome reconciliation.
Provider and Host boundaries remain the only authorities for effects. The
approved platform direction keeps interaction and semantic orchestration in
Chromie while moving platform-facing body, vocal, media, and device execution
behind a two-container Soridormi runtime and platform-provider boundary.

Sequential milestone codes are not part of the current project model. Work is
organized by capability, risk, and retained evidence.

## Current priorities

1. Keep every admitted non-operational turn on one Goal-driven semantic path.
   Interpretation failure must remain an explicit unavailable outcome; it must
   never be converted into plausible chat, tool, memory, or motion intent.
2. Repair vocal semantics before further execution work: singing and humming
   are Speaking outcomes, media playback is Activity, and neither may be
   replaced by a body gesture, generic TTS claim, or invalid resource Goal.
3. Preserve exact capability identity from model proposal through trusted
   validation, authorization, execution, and evidence. Agent Skills may teach
   reasoning methods but never authorize effects.
4. Establish the Chromie-to-Soridormi execution boundary without moving Goal
   meaning, confirmation, or user-level cancellation semantics out of Chromie.
5. Close source-bound and target-bound evidence separately. A passing source
   gate does not prove GPU, microphone, speaker, simulator, or physical-provider
   behavior.
6. Reduce compatibility surfaces only after the maintained path has equivalent
   retained evidence. Compatibility code must be gated, named, and unable to
   re-enter after Goal-driven authority has been selected.
7. Keep documentation, benchmarks, static analysis, configuration ownership,
   and unit behavior in the canonical pull-request gate.

## Completed foundations

Completed foundations are represented by capabilities and evidence, not by
sequential milestone numbers. Earlier incremental work is represented by two completed foundation groups:

- **Local interaction foundation:** Compose-based services, ASR/TTS contracts,
  bounded session state, playback ordering, barge-in, deterministic stop and
  cancellation, and simulator integration.
- **Goal-driven control-plane foundation:** Cognitive Gateway admission,
  immutable turn envelopes, Core-owned Goal Interpretation, Goal Association,
  Fast and Deep Planner contracts, Response Composer, Trusted Capability
  Runtime validation, outcome evidence, and fail-closed execution.

These foundations are maintained only while their automated contracts remain
passing.

## Active source work

### Semantic authority closure

- Keep `chat`, `memory`, `tool`, and trusted `robot_action` turns on the
  Goal-driven apply path for profiles that enable those lanes.
- Fail closed when a mapped lane is disabled or unsupported; do not resume the
  legacy Agent planner for the same turn.
- Keep emergency compatibility endpoints disabled by default and protected by
  service and per-turn authority gates.
- Remove the remaining compatibility planner only after retained replay and live
  evidence show no required rollback dependency.

Exit criteria:

- the semantic-authority matrix has exactly one owner per entry point;
- excluded lanes produce typed no-action outcomes;
- no authoritative failure enters another semantic planner;
- current docs and profiles describe the same lane policy.

### Interpretation and capability grounding

- Treat non-empty interpretation failure as `interpretation_unavailable`.
- Permit semantic repair to return only strictly typed, catalog-backed action
  proposals for `robot_action`.
- Revalidate capability IDs, argument schemas, confidence, confirmation policy,
  resources, and effect envelopes after every model stage.
- Expand general-ability scenarios rather than phrase-specific routing rules.

Exit criteria:

- no fallback invents an ordinary semantic lane;
- compound body requests retain ordered exact capabilities;
- missing abilities remain honest terminal outcomes;
- behavior scenarios cover unavailable, repair, and rejection paths.

### Chromie-Soridormi execution-boundary migration

This is an ordered set of Issue-sized changes, not a new milestone numbering
system. Each Issue must land with its own root-cause explanation, compatibility
plan, tests, and evidence ceiling. Do not combine the sequence into one large
rewrite.

1. **Repair vocal-mode Goal and Planner semantics.** Introduce typed lane and
   output-mode judgments sufficient to distinguish speech, expressive speech,
   recitation, singing, humming, body action, and media playback. Reproduce the
   retained Chinese walk/sing/blink episode. Goal Association must regenerate a
   suspicious compound decomposition from authoritative context rather than
   copy the prior DTO; vocal Goals cannot carry invented resource
   responsibilities; Planner outcome references cannot name nonexistent steps.
2. **Define the immutable Chromie-to-Soridormi execution envelope.** Specify
   authorization identity, Goal ownership, vocal/activity members, timing
   relation, confirmation state, deadline, cancellation scope, prepared/start
   states, and normalized per-member evidence. Chromie owns semantic validation
   and authorization; Soridormi owns provider-local execution.
3. **Introduce the Soridormi Execution Runtime facade.** Route existing body
   capabilities through the new envelope without changing behavior. Keep the
   current path as an explicit compatibility adapter until replay, cancellation,
   and MuJoCo evidence match.
4. **Move vocal execution and TTS behind Soridormi.** Add provider-declared vocal
   modes, streaming audio, timing marks, interruption, and delivery receipts.
   Ordinary expressive TTS must not advertise singing unless the selected
   provider has mode-specific evidence.
5. **Move media playback behind Soridormi as Activity capabilities.** Implement
   play, pause, resume, seek, stop, volume, and completion evidence independently
   from Speaking. Vocal and media streams may share a mixer but not a semantic
   lifecycle.
6. **Move platform audio and sensor adaptation into the Soridormi Platform
   Provider.** Chromie receives normalized audio streams and retains VAD, ASR,
   Gateway, and user-level barge-in semantics. No Chromie module should retain
   ALSA, device-index, robot-SDK, or simulator-specific adaptation.
7. **Add provider-local multimodal coordination.** Support prepare/start/cancel
   for compatible body, vocal, and media members with a monotonic barrier,
   resource declarations, per-member failure policy, and measured overlap
   evidence. Do not claim atomic or synchronized execution before this Issue.
8. **Slim the Chromie Interaction Orchestrator.** Remove direct TTS synthesis,
   PCM output, media, body-provider, and platform-device ownership while
   preserving session lifecycle, VAD/ASR coordination, Gateway/Core dispatch,
   confirmation, cancellation semantics, and evidence correlation. Structural
   ratchets must decrease.
9. **Qualify the migrated boundary and remove compatibility paths.** Run source,
   live-service, virtual/physical audio, MuJoCo, cancellation, recovery, and
   latency evidence against the same revision before deleting old dispatch or
   playback adapters.

Migration exit criteria:

- Chromie contains no simulator, robot, sound-device, TTS-backend, or media-
  backend selection logic;
- Soridormi exposes one stable execution contract and one private platform
  contract across MuJoCo and physical providers;
- singing, ordinary speech, and media playback have distinct typed semantics
  and mode-specific evidence;
- user-level stop/cancel meaning remains in Chromie while Soridormi supplies
  exact execution receipts;
- body, vocal, and media members can be coordinated without duplicate planners
  or unknown step ownership; and
- current-revision target traces prove the migrated path before compatibility is
  removed.

### Deferred interaction issue - speech-start barge-in

Record but do not implement this inside the execution-boundary Issues: VAD
currently invalidates playback after a complete accepted utterance, not at first
speech onset. A later Issue will add reversible speech-start ducking or pause,
echo/noise confirmation, and resume/abort behavior without cancelling Goals or
body work at the acoustic stage. Its implementation should follow the audio-
ownership contract so it is not built twice during migration.

### Structural simplification

The maintained component and failure contracts are
[VoiceAssistant Composition Root](docs/VOICE_ASSISTANT_COMPOSITION_ROOT.md) and
[Runtime Failure Paths](docs/RUNTIME_FAILURE_PATHS.md).

- Decompose the Orchestrator composition root along the approved Chromie
  Interaction Orchestrator and Soridormi Execution Runtime boundary without
  raising existing method, property, initializer, exception-boundary, or
  direct-model-call ratchets.
- Remove import-time global logging configuration from library modules.
- Keep configuration parsing inside typed settings owners.
- Delete transient implementation plans once their durable contracts have moved
  to canonical architecture or policy documents.

Exit criteria:

- structural ratchets decrease or remain unchanged;
- no deleted document has an incoming link;
- every specialized document has a component, operator, or mechanical owner.

### Reproducible verification

- Run repository policy, test ownership, static analysis, configuration,
  runtime structure, documentation, benchmark, unit, and legacy compatibility
  checks from one canonical entry point.
- Pin third-party GitHub Actions by immutable commit SHA.
- Record source identity from Git when available and from a deterministic source
  tree digest for archives.
- Continue rejecting mutable runtime images and model artifacts for publishable
  provenance while allowing clearly labeled local-development aliases.

Exit criteria:

- a clean dependency-complete environment passes `./scripts/run_tests.sh`;
- source archives can produce immutable run metadata without `.git`;
- release provenance contains resolved image and model digests.

## Open evidence track - Physical audio validation

Physical audio remains an evidence task, not a source-code assumption. Retain:

- intelligible microphone-to-ASR utterances in supported languages;
- first audible TTS latency and uninterrupted playback evidence;
- barge-in, stop-talking, and recovery behavior under real devices;
- device identity, sample rate, provider revision, and correlated trace IDs.

Source tests may validate collectors and schemas, but only target runs can close
this track.

## Target-evidence closure track

Use [docs/TARGET_EVIDENCE_CLOSURE.md](docs/TARGET_EVIDENCE_CLOSURE.md) for the
coordinated workflow. Required retained evidence includes:

- current source identity and clean-state declaration;
- profile and provider identity;
- Gateway-to-Core-to-planner contract smoke results;
- simulator or hardware capability receipts;
- failure, cancellation, and recovery evidence;
- benchmark and latency summaries with explicit exclusions.

A run that cannot execute a required target gate must report it as unavailable,
not passed.

## Future phase - Physical pilot preparation

Physical pilot work starts only after simulator behavior, source verification,
and target evidence are current. The pilot must progress through shadow,
dry-run, bounded single-capability, supervised composition, and broader use.
Each widening requires explicit stop/recovery proof and operator rollback.

## Later work

- richer perception and social-attention providers;
- durable memory with explicit consent, retention, inspection, and deletion;
- additional local information providers;
- provider-neutral multi-robot capability composition;
- publication and signed release artifacts after a release target exists.

## Anti-drift review

Before accepting work, ask:

- Does it close the active milestone represented by the current priority and its
  exit criteria, rather than only one visible example?
- Is the behavior owned by the Cognitive Core, Chromie Interaction
  Orchestrator, Soridormi Execution Runtime, or Soridormi Platform Provider, and
  is that boundary preserved?
- Is the required evidence level explicit: source, simulator, target, or
  physical pilot?
- Does it preserve one Goal-driven semantic authority and trusted effect
  authorization?
- Does it reduce or clearly bound compatibility and documentation surface?
