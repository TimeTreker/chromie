# Chromie Roadmap

Chromie is in active development. This roadmap owns delivery order and exit
criteria; current implementation and evidence state live in
[docs/STATUS.md](docs/STATUS.md).

The current focus is a **Goal-driven single semantic authority**. The Cognitive
Gateway owns ingress, protective reflexes, and attention admission. The
Goal-driven Cognitive Core owns ordinary semantic interpretation, goal
association, planning, response composition, and outcome reconciliation.
Provider and Host boundaries remain the only authorities for effects.
The core embodied target is a qualified simulator provider. Chromie's cognition
must remain backend-neutral; physical-robot commissioning is optional
Soridormi/provider work and is not a Chromie milestone or release prerequisite.

Sequential milestone codes are not part of the current project model. Work is
organized by capability, risk, and retained evidence.

## Immediate architecture line — consolidate the reviewed authority baseline

The broad architecture-discovery phase is closed. New work starts from the canonical
`Goal Interpretation → Responsibility evidence → Fast Planner advancement → immediate
safe Activity and/or Goal Association/Deep continuation → Canonical Goal when persistent
continuity is required → canonical planning → Work/Primary Activities → realization →
Provider → Evidence` authority seam
and must pass the Charter's architecture-irreducibility review before adding a new
principle, owner, persistent state concept, manager, workflow, contract field, or
mechanism.

Next design/implementation order:

1. **Fast Planner first-advancement seam — implemented in the maintained path.** Keep
   Responsibility evidence as Goal Interpretation's provider-neutral WHAT handoff. The
   same Fast Planner is the first HOW owner: before canonical Goal binding it may author
   one immediate safe conversational Activity and typed continuation dispositions for
   Goal Association and/or Deep Planner. Goal Association remains the only canonical
   Goal-continuity authority; commitment-bearing Capability work still requires
   applicable canonical Goal grounding and trusted validation. Goal-Interpreter
   `native_response`/`fast_speech` survive only as compatibility vocabulary and are not
   maintained wording owners.
2. **Epistemic Qualification contract detail — first source slice implemented.** Do not add an `EpistemicManager`.
   Extend existing capability/evidence contracts to represent claim-specific required
   observations, provenance/trust-domain independence, alternatives/corroboration,
   validity/freshness, closed-world coverage, and qualification state
   (`established|insufficient|stale|contradicted|unknown`). Keep ASR/input fidelity in
   Gateway and semantic meaning in GI/GA. Principal recognition/authentication uses
   the ordinary Capability/Provider/Evidence path; authorization/consent remains Host
   policy.
3. **Forward Adaptation contract detail — first source slice implemented.** Separate open-Responsibility actions from
   terminal-history learning proposals. Online Reflection may create only bounded
   advisory experience/calibration; trusted policy caps scope and lifetime and Memory
   materializes it with explicit expiry. It may not modify Stable Mind/shared prompts/models/global
   Fast/Deep policy, authorization/safety, Capability semantics, or cache semantic
   decisions. Shared/systemic changes remain offline and owner-governed.
4. **Retention/negative-evidence consistency.** Make `immutable while retained !=
   permanent` explicit across Evidence/Memory/Data Loop. No universal tombstone is
   required; absence supports a negative claim only under complete collection and
   retention coverage, otherwise Response must preserve `unknown`.
5. **Machine guards and scenarios.** Only after contract text is stable, add the
   smallest schema/runtime/audit changes needed to protect these boundaries. Tests
   should guard authority and observable semantics, not one incidental call sequence.
6. **Qualification after implementation.** Source/test success, target qualification,
   and release readiness stay separate; relevant revision/model/provider/config changes
   invalidate the corresponding qualification claim before age-based review does.

Exit criteria for this line:

- no reviewed case requires a new top-level semantic authority;
- native response, later response composition, and result interpretation obey one
  semantic wording owner per conversational act;
- evidence integrity and evidence sufficiency are explicitly distinct;
- terminal history can teach bounded future cognition without reopening history;
- local adaptation has separately bounded scope and lifetime and cannot self-promote to
  shared policy; and
- Status records design/source/test/target evidence separately.

## Immediate architecture line — Continuous Mind implementation from the compressed baseline

The General Progress substrate remains the first implemented slice of
readiness-driven cognition. The complete problem-space discussion has now been
compressed into the architecture baseline in
[Goal-Driven Cognitive Architecture](docs/GOAL_DRIVEN_COGNITIVE_ARCHITECTURE.md#414-continuous-mind-synthesis--compressed-architecture-baseline).
The project should not reopen the ontology by creating one class/manager per
human cognitive term.

The settled target is intentionally small:

- durable Mind state: Stable Mind, Goal as unfinished Responsibility, and Memory;
- live Mind state: bounded, revisable, mostly reconstructable Situation; and
- existing grounding/action substrate: Evidence/Interaction Ledger,
  Progress/CanonicalPlan/request/execution/outcome artifacts, and
  Capability/provider truth.

`Work`, Intention, Commitment, Attention, Readiness, Salience, Concern,
Reflection, Learning, Recovery, Common Ground, Affordance, and similar terms are
currently explanatory/process/derived/policy concepts unless a concrete future
case proves an independent lifecycle or authority that existing owners cannot
represent.

The next work is **detail validation and incremental implementation against this
baseline**, not another broad concept-expansion phase:

1. **Goal/Work truth separation is implemented.** `SemanticGoal` now owns the
   small Responsibility lifecycle while `ActiveGoalSnapshot.work_status` exposes
   the independently owned Work/runtime projection. `ExecutionOutcomeBundle` is
   recorded as historical execution truth before a separate Responsibility
   reconciliation step; non-completed Work leaves the Goal open, and later
   correction may reopen a satisfied Goal without rewriting history. Preserve
   this separation and delete any remaining duplicate commitment/work truth when
   encountered.
2. **The minimal live Situation projection is implemented.** A frozen bounded
   projection now carries only current relevance/interpretation references: turn
   lane/intent, focused Goal IDs, discourse focus, unresolved condition refs,
   ready progress IDs, and evidence refs. It is rebuilt in-process, revisioned
   between Goal Association and planning, prompt-validated, and never owns or
   copies the referenced Goal/Evidence/provider truth.
3. **Goal materialization, refinement, and replacement are implemented.** Fully
   discharged provider-free native conversation stays transient; same-Responsibility
   refinement preserves compatible Work unless `requires_replan=true`; genuine
   replacement creates new Goal lineage, stops incompatible old Work through trusted
   receipts, and supersedes the old Responsibility without rewriting history.
4. **Evidence-driven reactivation and selective Reflection are implemented.**
   Trusted non-completed execution evidence derives an ephemeral fast/slow opportunity.
   Only slow opportunities invoke typed Reflection; its Goal/evidence references are
   runtime-bound, and repeated evidence may promote ephemeral task/session memory only.
5. **Preserve truth semantics and repair forward.** Historical Evidence/outcomes/
   delivered speech are append-only facts; current Goal/Plan/Memory meaning may be
   provenance-preserving revised; Situation remains soft; Stable Mind and
   provider/authorization/safety authority cannot be rewritten by ordinary
   cognition.
6. **Restart/revalidation is implemented for durable Goal continuity.** Only open
   Responsibility is restored; current Work becomes recoverable/revalidation-required,
   stale confirmation/runtime bindings lose current authority, volatile Situation/provider/
   body projections are excluded from durable Goal state, and stale bindings cannot be
   cancelled or superseded before fresh runtime/provider revalidation.
7. **Widen only after the core invariants hold.** Durable scoped consent/privacy,
   multi-user identity, broader autonomy, competence calibration, and richer
   resumable cognition remain later detail work unless a current implementation
   slice requires them.

Architecture review may remove or replace pre-release compatibility/workflow
structures when they obstruct this model. `Use less to solve more` means ending
with fewer truth owners and processes, not preserving an obsolete pipeline or
adding a manager because a useful explanatory term exists.
## Approved architecture line — asynchronous transport-independent Capability Runtime

The Trusted Capability Runtime now has an approved target architecture. Current source
has request identity, validation, resource arbitration, cancellation, provider execution,
bounded internal concurrency, a non-blocking `CapabilityRuntime.submit(...)` dispatch
boundary, and a correlated in-process `CapabilityRuntimeEvent` lifecycle surface. `submit()`
returns a `CapabilityDispatchReceipt` after Host validation, Runtime ownership registration,
and submission-task creation; provider terminal completion is an explicit
`wait_terminal(receipt)` join rather than the dispatch API. No
`CapabilityRuntime.execute(...)` aggregate compatibility API remains. Accepted, running,
progress, and terminal events are published per exact Runtime-owned request without waiting
for sibling completion. The remaining target is incremental terminal Evidence reconciliation
and cognitive re-entry without creating a second Work/Result/Event manager or semantic
agent. Provider transport and durable-execution backend remain below the Capability contract.

Implement this line as separate focused Issues and separate patches:

- **Issue — Canonicalize Capability Runtime vocabulary — source implementation complete.**
  Canonical executable source now uses `CapabilityRuntime`, `CapabilityDefinition`,
  `CapabilityRegistry`, `CapabilityProvider`, `CapabilityRequest`, `CapabilityResult`,
  `capability_id`, and `capability_version`. The old executable `Skill*` aliases/files and
  live `skill_id` compatibility are removed; Agent Skills retain `agent_skill_id`, while
  Soridormi wire `skill_id` is translated only at its adapter boundary. This naming/authority
  cleanup does **not** claim the asynchronous dispatch behavior of the later Issues.
- **Issue — Split capability dispatch from terminal completion — source implementation complete.**
  `CapabilityRuntime.submit(...)` now returns a `CapabilityDispatchReceipt` after validation,
  canonical request registration, and Runtime-owned task creation while provider execution
  continues independently. Terminal joining is explicit through `wait_terminal(receipt)`;
  the old `CapabilityRuntime.execute(...)` API was deleted rather than retained as a
  compatibility wrapper. Existing sequential dependencies, provider grouping, cancellation,
  and resource barriers remain Runtime-owned.
- **Issue — Publish correlated capability lifecycle events — source implementation complete.**
  `CapabilityRuntime` now retains one bounded, cursor-addressable mechanical
  `CapabilityRuntimeEvent` history for accepted/running/progress/terminal state using
  Host-owned request correlation. Consumers keep independent cursors rather than destructively
  competing for one queue. Provider-returned IDs are checked against Runtime ownership and
  identity mismatches fail closed; provider `execute()` cannot close a request with a
  non-terminal `accepted`/`running` result. Each request publishes its terminal event as soon
  as it becomes terminal, even while a parallel sibling is still running. Runtime events are
  lifecycle observations, not terminal Evidence.
- **Issue — Reconcile terminal Evidence incrementally.** Feed terminal events into the
  existing execution/evidence owners without treating still-accepted/running siblings as
  `not_run`. Keep `ExecutionOutcomeBundle` immutable terminal truth; introduce no duplicate
  completion store.
- **Issue — Decouple interaction lifetime from capability lifetime.** Remove the
  assumption that one interaction Python task remains alive until every provider finishes.
  Terminal Capability events create bounded cognitive opportunities/result interpretation
  against current Goal/Plan relevance instead of resuming the original call stack.
- **Issue — Harden cancellation, supersession, and late-result semantics.** Ensure scoped
  cancel/preempt, Goal replacement, stale Plan bindings, and late provider completion cannot
  resurrect obsolete work or force obsolete speech while preserving historical execution
  Evidence.
- **Issue — Introduce a Capability Runtime backend boundary.** Keep an in-process
  `asyncio` backend as the maintained default, with provider adapters for MCP/HTTP/gRPC/ROS
  2/local implementations. Backend IDs remain opaque and cannot replace Chromie request
  identity.
- **Issue — Qualify a DBOS durable backend with read-only/idempotent work.** Use weather
  or another safe information Capability to prove non-blocking submission, concurrent work,
  process restart, result delivery, cancel, and recovery. DBOS remains an optional backend,
  not a Cognitive Core dependency; no physical effect is automatically retried because a
  durable engine can retry execution.
- **Issue — Migrate long-running Soridormi work to asynchronous provider lifecycle.** Reuse
  its submit/status/event/cancel boundary so embodiment can report progress/terminal events
  without making Chromie wait. Physical feasibility, stop/recovery, and retry authority stay
  provider/trusted-runtime owned.
- **Issue — Delete remaining foreground aggregate-wait behavior.** The old
  `CapabilityRuntime.execute(...)` compatibility API is already deleted. Once lifecycle
  events, incremental Evidence, and cognitive re-entry are maintained, remove foreground
  coordinator joins that still wait for a whole response scope before interaction closure,
  plus any stale aggregate-only tests/docs. Do not reintroduce a second execution API.

Each Issue must preserve the central authority invariant: Runtime owns execution lifecycle;
LLM/Core owns meaning. Framework choice must not turn transport, queues, workflows, or
callbacks into a second planner.

## Current priorities

1. Preserve the completed authority spine and implement only the contract detail now
   proven necessary: conversational-act wording ownership, claim-specific Epistemic
   Qualification, and bounded Forward Adaptation. Multi-user identity is not a new owner:
   recognition/authentication is a factual Capability/Evidence claim and effect-specific
   authorization/consent stays in Host policy. New top-level architecture requires the
   Charter irreducibility review.
2. Preserve the merged source contracts from Issues
   [#17](https://github.com/TimeTreker/chromie/issues/17),
   [#18](https://github.com/TimeTreker/chromie/issues/18),
   [#20](https://github.com/TimeTreker/chromie/issues/20), and the completed
   Goal-scoped cross-lane Interaction Context from
   [#22](https://github.com/TimeTreker/chromie/issues/22) before qualifying a
   replacement model profile. Same-model timing evidence must remain separate
   from cross-model reload measurement; no prompt-prefix result may claim
   cross-model KV reuse or model-reload savings.
3. Preserve the closed 2026-08-07 post-merge audit contracts. Clean merged
   Chromie `a36444b` and Soridormi `fa8080d2` retain exact compound arguments,
   ordered MuJoCo execution, provider-start deterministic cancellation, and
   safe-idle recovery. The dependency-complete source gate and rebuilt clean
   generated-speech/GPU profile remain bound to `90aa72a`. Current source
   replaces the former online semantic-review/recovery chain with bounded Fast
   interpretation, one risk-bounded Deep escalation for uncertain `tool`,
   `memory`, or `robot_action` work, and terminal Host validation. Hard semantic,
   delivery-evidence, safety, provider, or provenance failures remain
   non-averageable blockers.
4. Keep every admitted non-operational turn on one Goal-driven semantic path.
   Interpretation failure must remain an explicit unavailable outcome; it must
   never be converted into plausible chat, tool, memory, or motion intent.
5. Preserve the source-qualified `chromie.vocal.perform` contract and its clean
   default-provider distinction evidence; real modes remain a separate target
   evidence track.
6. Preserve Issue #7's source-qualified peer media-playback contract and its
   clean default-provider distinction evidence. Real operations remain a
   separate target-evidence track; singing remains in Vocal, existing-audio
   playback remains Activity, and ordinary TTS is neither kind of evidence.
7. Preserve exact provider-prefixed capability identity from model proposal
   through trusted validation, authorization, execution, and evidence. Backend
   replacement stays behind that exact capability identity; do not introduce a
   neutral late-binding alias merely to relocate implementation.
8. Close source-bound and target-bound evidence separately. A passing source
   gate does not prove GPU, microphone, speaker, simulator, or physical-provider
   behavior. Core embodied closure requires simulator evidence; physical-provider
   evidence is recorded only when an optional concrete deployment is being
   qualified and never blocks ordinary Chromie completion.
9. Reduce compatibility surfaces only after the maintained path has equivalent
   retained evidence. Compatibility code must be gated, named, and unable to
   re-enter after Goal-driven authority has been selected.
10. Keep documentation, benchmarks, static analysis, configuration ownership,
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

### Goal-scoped Interaction Ledger and current-turn continuity

Issue [#22](https://github.com/TimeTreker/chromie/issues/22) owns the append-only
Interaction Ledger and bounded Goal-scoped Interaction Context supplied to Goal
Association, Fast Planner, Deep Planner, and Response Composer. The Ledger
transports facts from existing owners; it does not replace or rewrite playback,
`TaskProposalLedger`, Social Attention results, Goal state, or
`ExecutionOutcomeBundle` evidence.

Exit criteria:

- delivered response-stage speech retains exact turn, Goal, Plan, claim, and
  completion-restriction provenance;
- Cognitive Runtime, playback, Trusted Capability Runtime, and execution
  closure append only typed facts they authoritatively observe;
- replay cannot change an immutable event, and terminal Activity entries require
  trusted execution evidence references;
- Goal Association receives bounded recent Interaction Context and later
  planners/composition receive the Goal-scoped projection so they can produce
  only the still-needed delta;
- pre-Goal Fast speech remains explicitly unbound rather than receiving
  Host-invented Goal ownership;
- Goal-bound speech cannot be reused for unrelated Goals or a different Plan;
- scheduled and delivered speech remain distinct, and neither proves Activity
  execution or completion; and
- focused lane/runtime/model-prompt regressions plus the canonical source gate
  pass without a new runtime switch, compatibility path, standalone document,
  or competing semantic/effect authority.

### Interpretation and capability grounding

- Preserve one Fast Goal Interpretation transaction: one primary interpretation,
  at most one mechanical DTO repair, then accept, delegate low-confidence
  `tool`, `memory`, or `robot_action` work once to Deep Thinking, or fail closed.
  Schema-valid benign chat remains on the fast conversational path.
- Treat non-empty interpretation failure as `interpretation_unavailable`; never
  rewrite it into plausible chat, tool, memory, or motion intent.
- Keep semantic reconsideration source-based. Do not restore intent reviewers,
  generic-chat critics, capability-grounding reviewers, contract-loss recovery,
  or repair-of-repair around previous model output.
- Preserve Goal Association's independent evidence-bearing coverage certificate
  and one fresh source-based interpretation after rejection; the certificate is
  immutable evidence, not a second Goal authority.
- Revalidate capability IDs, argument schemas, confidence, confirmation policy,
  resources, and effect envelopes at trusted boundaries. Fast may escalate once
  to Deep Planner; same-tier regeneration is reserved for one mechanically malformed
  DTO only; semantic rejection in Deep and trusted Host rejection are terminal.
- Expand general-ability scenarios rather than phrase-specific routing rules.

Exit criteria:

- no fallback invents an ordinary semantic lane;
- a second malformed Fast DTO or semantic contradiction fails closed;
- low-confidence Fast meaning that could change responsibility, external work,
  memory, or effects reaches Deep Thinking without an intermediate semantic
  repair model; low-confidence benign chat remains fast;
- an effectful Goal has an owned executable step, delivered evidence for the
  same Goal, or an explicit clarify/escalate/unavailable/refused outcome;
- compound body requests retain ordered exact capabilities;
- missing abilities remain honest terminal outcomes;
- semantic outcome tests enforce the logical model-call budgets instead of an
  exact historical prompt sequence.

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
unavailable with no media execution, keeps singing in Vocal, completes an
independent Soridormi/MuJoCo walk, retains a cognition-bypassing stop-media
receipt, and returns safe-idle. Existing audio playback therefore does not
become authored vocal performance; real media and acoustic behavior remain
target evidence.
Vocal, TTS synthesis, playback transport, echo handling, audible-delivery
ordering, and user-level barge-in remain Chromie-owned. Soridormi remains a peer
embodied Capability Provider beneath Activity.

- Typed Goal and Planner projections now separate completion modality,
  execution lane, output mode, and exact-provider need; preserve this contract
  through canonical and live evidence closure.
- Keep `singing`, `humming`, `recitation`, and other authored vocal performance
  in Vocal even when coordinated with body work.
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
Soridormi as part of the vocal architecture work. Reopen the hosting decision only
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
