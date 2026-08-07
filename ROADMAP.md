# Chromie Roadmap

Chromie is in active development. This roadmap owns delivery order and exit
criteria; current implementation and evidence state live in
[docs/STATUS.md](docs/STATUS.md).

The current focus is a **Goal-driven single semantic authority**. The Cognitive
Gateway owns ingress, protective reflexes, and attention admission. The
Goal-driven Cognitive Core owns ordinary semantic interpretation, goal
association, planning, response composition, and outcome reconciliation.
Provider and Host boundaries remain the only authorities for effects.

Sequential milestone codes are not part of the current project model. Work is
organized by capability, risk, and retained evidence.

## Current priorities

1. Keep every admitted non-operational turn on one Goal-driven semantic path.
   Interpretation failure must remain an explicit unavailable outcome; it must
   never be converted into plausible chat, tool, memory, or motion intent.
2. Close speech-start barge-in with reversible playback ducking while keeping
   acoustic mitigation separate from semantic cancellation authority.
3. After barge-in evidence closes, qualify an exact vocal-performance provider,
   then a peer media-playback provider. Singing remains Speaking; existing-audio
   playback remains Activity; ordinary TTS is neither kind of evidence.
4. Preserve exact provider-prefixed capability identity from model proposal
   through trusted validation, authorization, execution, and evidence. Backend
   replacement stays behind that exact capability identity; do not introduce a
   neutral late-binding alias merely to relocate implementation.
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

### Speech-start barge-in and reversible ducking

VAD, playback transport, echo handling, output interruption, and user-level
cancellation scope remain Host Orchestrator responsibilities. Acoustic handling
may duck or temporarily pause output on credible speech start, but it cannot
cancel Cognitive Core work, Goals, body work, or capability execution.

- Bound the speech-start confirmation window and use available echo or AEC
  evidence.
- Abort the active output generation after external speech is confirmed.
- Resume safely after likely echo or noise without replay, duplicated delivery,
  or late terminal speech.
- Leave output-only, motion, interaction, Goal, emergency, and ordinary semantic
  scope to later ASR and Gateway resolution, with distinct cancellation receipts.

Exit criteria:

- retained evidence measures VAD-start-to-duck and confirmed-speech-to-silence;
- acoustic-stage evidence records `cancel_cognitive_work=false`;
- echo rejection and safe resume pass focused and automated audio E2E scenarios;
- no duplicated or late terminal speech survives confirmed interruption; and
- every semantic cancellation scope remains distinct in evidence.

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

### Vocal semantics and provider qualification

The retained compound walk/sing/blink defect has met its source and Level C
simulator exit criteria; [Current Status](docs/STATUS.md) owns the evidence.
Keep the maintained ownership boundary while qualifying future exact providers.
Speaking, TTS synthesis, playback transport, echo handling, audible-delivery
ordering, and user-level barge-in remain Chromie-owned. Soridormi remains a peer
embodied Capability Provider beneath Activity.

- Typed Goal and Planner projections now separate completion modality,
  execution lane, output mode, and exact-provider need; preserve this contract
  through canonical and live evidence closure.
- Keep `singing`, `humming`, `recitation`, and other authored vocal performance
  in Speaking even when coordinated with body work.
- Keep playback of existing music, recordings, streams, and sound effects in
  Activity with an exact media-provider capability identity.
- Use an exact provider-prefixed vocal capability such as
  `chromie.vocal.perform`; provider implementation may change behind the stable
  identity, but the Planner-to-evidence identity must not.
- Do not let ordinary expressive TTS advertise or close a singing outcome.
- Do not attach resource-acquisition responsibility to ordinary vocal output.
- Keep one authoritative Planner step-ownership representation and derive or
  strictly validate redundant references.

Exit criteria:

- the retained Chinese walk/sing/blink episode and generalized vocal/media
  variants pass focused and general-ability source tests;
- Planner output contains no unknown step reference and no body/media
  substitution for singing;
- `scripts/vocal_issue_closure.py` reports `closure_eligible=true` from one clean
  revision after the canonical source gate, exact typed Goal/Plan validation,
  real Soridormi/MuJoCo walking and blinking completion, exact singing
  unavailability or refusal, matching source identity, and safe-idle recovery;
  and
- target audio or robot behavior is claimed only from retained target evidence.

### Conditional vocal-hosting review

Do not move TTS, playback, microphone, speaker, or media execution into
Soridormi as part of the vocal semantic repair. Reopen the hosting decision only
when retained evidence demonstrates at least one concrete blocker that the
current peer-provider boundary cannot meet, such as:

- frame-accurate viseme/body/audio synchronization required by a physical robot;
- measured cross-boundary start skew outside a named acceptance budget;
- measured cancel-to-silence latency outside a named barge-in budget;
- unavoidable platform audio adaptation leaking into cognitive or semantic
  code; or
- shared accelerator or mixer contention that cannot be solved behind the
  existing provider contract.

Any such review is a separate architecture decision. It must update the Project
Charter, `AGENTS.md`, capability contracts, Status, Roadmap, tests, and evidence
plan in one coherent change. Co-location or a cockpit/ADAS analogy is not by
 itself sufficient evidence.

### Structural simplification

The maintained component and failure contracts are
[VoiceAssistant Composition Root](docs/VOICE_ASSISTANT_COMPOSITION_ROOT.md) and
[Runtime Failure Paths](docs/RUNTIME_FAILURE_PATHS.md).

- Decompose the Orchestrator composition root without raising existing method,
  property, initializer, exception-boundary, or direct-model-call ratchets.
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
- Is the behavior owned by Chromie or Soridormi, and is that boundary preserved?
- Is the required evidence level explicit: source, simulator, target, or
  physical pilot?
- Does it preserve one Goal-driven semantic authority and trusted effect
  authorization?
- Does it reduce or clearly bound compatibility and documentation surface?
