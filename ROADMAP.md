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

1. Preserve the merged source contracts from Issues
   [#17](https://github.com/TimeTreker/chromie/issues/17) and
   [#18](https://github.com/TimeTreker/chromie/issues/18), then complete
   [#20](https://github.com/TimeTreker/chromie/issues/20) before qualifying a
   replacement model profile. Same-model timing evidence must remain separate
   from cross-model reload measurement; no prompt-prefix result may claim
   cross-model KV reuse or model-reload savings.
2. Preserve the closed 2026-08-07 post-merge audit contracts. Clean merged
   Chromie `a36444b` and Soridormi `fa8080d2` retain exact compound arguments,
   ordered MuJoCo execution, provider-start deterministic cancellation, and
   safe-idle recovery. The dependency-complete source gate and rebuilt clean
   generated-speech/GPU profile remain bound to `90aa72a`; the absent
   independent semantic reviewer remains an explicit non-release gap. Hard
   semantic, delivery-evidence, safety, provider, or provenance failures remain
   non-averageable blockers.
3. Keep every admitted non-operational turn on one Goal-driven semantic path.
   Interpretation failure must remain an explicit unavailable outcome; it must
   never be converted into plausible chat, tool, memory, or motion intent.
4. Preserve the source-qualified `chromie.vocal.perform` contract and its clean
   default-provider distinction evidence; real modes remain a separate target
   evidence track.
5. Preserve Issue #7's source-qualified peer media-playback contract and its
   clean default-provider distinction evidence. Real operations remain a
   separate target-evidence track; singing remains Speaking, existing-audio
   playback remains Activity, and ordinary TTS is neither kind of evidence.
6. Preserve exact provider-prefixed capability identity from model proposal
   through trusted validation, authorization, execution, and evidence. Backend
   replacement stays behind that exact capability identity; do not introduce a
   neutral late-binding alias merely to relocate implementation.
7. Close source-bound and target-bound evidence separately. A passing source
   gate does not prove GPU, microphone, speaker, simulator, or physical-provider
   behavior.
8. Reduce compatibility surfaces only after the maintained path has equivalent
   retained evidence. Compatibility code must be gated, named, and unable to
   re-enter after Goal-driven authority has been selected.
9. Keep documentation, benchmarks, static analysis, configuration ownership,
   and unit behavior in the canonical pull-request gate.

## Completed foundations

Completed foundations are represented by capabilities and evidence, not by
sequential milestone numbers. Earlier incremental work is represented by two completed foundation groups:

- **Local interaction foundation:** Compose-based services, ASR/TTS contracts,
  bounded session state, playback ordering, reversible speech-start barge-in,
  order-aware echo resume, deterministic stop and cancellation, and simulator
  integration. Clean generated-speech evidence for `94718ab` retains acoustic
  and later semantic cancellation as distinct receipts; physical audio remains
  an open evidence track.
- **Goal-driven control-plane foundation:** Cognitive Gateway admission,
  immutable turn envelopes, Core-owned Goal Interpretation, Goal Association,
  Fast and Deep Planner contracts, Response Composer, Trusted Capability
  Runtime validation, outcome evidence, and fail-closed execution.

These foundations are maintained only while their automated contracts remain
passing.

## Active source work

### Layered prompt prefix integration — source complete

Issue [#17](https://github.com/TimeTreker/chromie/issues/17) owns the design and
Issue [#18](https://github.com/TimeTreker/chromie/issues/18) owns the completed
source integration and its explicit target-evidence boundary. The architecture defines six ordered layers: a
constitutional foundation; exact identity/world projection; exact Agent role;
exact capability/Skill/schema projection; session context; and current turn.
Only identical rendered layers 0 through 3 form a stable-prefix candidate.
Preserve the current model-facing contracts and deterministic validation; do
not add a Host semantic cache, a runtime flag, or a compatibility path.

Exit criteria:

- each layer has one owner, allowed content, mutability rule, and invalidation
  condition;
- current time, session state, Goals, memory, observations, evidence, validator
  feedback, and current user input remain volatile;
- owner identity/world and capability projections are stable only while their
  exact rendered content is unchanged;
- hashes are defined as non-sensitive invalidation/observability evidence, not
  a provider cache-key API or cache-hit claim; and
- `OllamaClient` owns exact assembly, context accounting, non-sensitive layer
  digests, request-contract identity, and provider timing correlation; and
- focused non-live regressions pass; the same-model RTX 4090 Laptop measurement
  remains part of the next model-profile qualification and must distinguish
  source completion from target evidence.

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

- Issue [#20](https://github.com/TimeTreker/chromie/issues/20) owns the current
  P0 containment line: schema-bound semantic review must use a transport that
  the selected Ollama model actually honors, advisory route narrowing must not
  destroy the supplied recovery catalog, and an unresolved typed effectful Goal
  must never become a successful zero-step response.
- Treat non-empty interpretation failure as `interpretation_unavailable`.
- Permit semantic repair to return only strictly typed, catalog-backed action
  proposals for `robot_action`.
- Revalidate capability IDs, argument schemas, confidence, confirmation policy,
  resources, and effect envelopes after every model stage.
- Expand general-ability scenarios rather than phrase-specific routing rules.

Exit criteria:

- no fallback invents an ordinary semantic lane;
- malformed structured review either receives one same-contract transport
  compatibility retry or fails closed;
- candidate ordering remains advisory while the supplied common/full catalog
  stays available to semantic repair;
- an effectful Goal has an owned executable step, delivered evidence for the
  same Goal, or an explicit clarify/escalate/unavailable/refused outcome;
- compound body requests retain ordered exact capabilities;
- missing abilities remain honest terminal outcomes;
- behavior scenarios cover unavailable, repair, and rejection paths.

### Vocal semantics and provider qualification

The retained compound walk/sing/blink defect has met its source and Level C
simulator exit criteria; [Current Status](docs/STATUS.md) owns the evidence.
Issue #6 has an exact source-qualified `chromie.vocal.perform` provider contract
while keeping the maintained ownership boundary. Fake-provider tests, an exact
recitation scenario, the relevant general-ability class, ordinary TTS
regressions, and the canonical gate meet the source criteria. Clean Chromie
`e558ff4` and Soridormi `1c15371` then passed the default-provider
walk/sing/blink replay retained at
`.chromie/acceptance/vocal-issue-6/issue-6-e558ff4-clean`: body work completed,
singing remained unavailable with zero steps, all ordinary-TTS chunks played,
and safe idle held before and after. Real vocal modes remain target evidence.

Issue #7 now has the exact provider-prefixed
`chromie.media.play|pause|resume|seek|stop|volume|status` source contract with a
bounded persistent lifecycle beneath Activity. Qualified fake-provider tests
cover supported-kind negotiation, state/progress, exact operation evidence,
cancellation, mixer policy, and private backend identity. Focused scenarios
retain a mixed Soridormi walk plus exact media step and deterministic
`media_output` cancellation. The default-provider live profile keeps playback
unavailable with no media execution, keeps singing in Speaking, completes an
independent Soridormi/MuJoCo walk, retains a cognition-bypassing stop-media
receipt, and returns safe-idle. Existing audio playback therefore does not
become authored vocal performance; real media and acoustic behavior remain
target evidence.
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
- Carry a typed mode for speech, expressive speech, recitation, singing,
  humming, or nonverbal vocalization. Provider declarations own supported modes,
  streaming, timing marks, sample formats, concurrency, cancellation, and model
  provenance.
- Do not let ordinary expressive TTS advertise or close a singing outcome.
- Return exact unavailable outcomes for unsupported modes; never silently
  downgrade one vocal mode to another.
- Do not attach resource-acquisition responsibility to ordinary vocal output.
- Keep one authoritative Planner step-ownership representation and derive or
  strictly validate redundant references.

Exit criteria:

- exact capability identity survives proposal, validation, authorization,
  execution, cancellation, and evidence;
- a fake provider proves supported-mode negotiation, exact unsupported outcomes,
  cancellation, and provenance in source tests;
- ordinary TTS remains equivalent for ordering, interruption, echo handling,
  and audible-delivery evidence without becoming singing evidence;
- the retained Chinese walk/sing/blink and generalized vocal/media distinctions
  remain passing; and
- real singing and physical audio are claimed only from retained mode-specific
  target evidence.

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
