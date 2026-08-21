# Chromie Roadmap

Chromie is in active development. This roadmap owns delivery order and exit
criteria; current implementation and evidence state live in
[docs/STATUS.md](docs/STATUS.md).

The current focus is a **Goal-driven single semantic authority**. The Cognitive
Gateway owns ingress, protective reflexes, and attention admission. The
Goal-driven Cognitive Core owns ordinary semantic interpretation, goal
association, Planner-authored communication/work, and outcome reconciliation.
Provider and Host boundaries remain the only authorities for effects.
The core embodied target is a qualified simulator provider. Chromie's cognition
must remain backend-neutral; physical-robot commissioning is optional
Soridormi/provider work and is not a Chromie milestone or release prerequisite.

Sequential milestone codes are not part of the current project model. Work is
organized by capability, risk, and retained evidence.

## Current execution order

The following order is binding until the current-revision target-evidence line is
closed. It applies the already-approved architecture; it does not introduce another
layer or cognitive term.

1. **Make the evidence contract internally reproducible.** Correct the general-
   ability latency assertions so the Planner-local and playback intervals use their
   declared raw anchors. Retain a revision/runtime-bound reviewer packet containing
   explicit profile, input, speaker, assertion-scope, evidence-level, and raw timing
   data. Use the existing evidence sanitizer for external sharing.
2. **Run the highest safe current-revision profile.** First retain the repaired
   injected-text run, then perform supervised physical microphone/audible-speaker
   proof and close the remaining default target-evidence profile. Headless/discarded
   playback must never be promoted to audible evidence.
3. **Resume broad structural simplification after evidence closure.** One narrow
   provenance-protecting source slice is already implemented: pure Planner-reentry
   validation is extracted from the Host composition root and dead wrappers are removed.
   Later decomposition follows existing configuration, input-lifecycle, playback,
   cognitive-dispatch, observability, cancellation, and cleanup ownership seams. Do not
   create one service/manager per cognitive role, and do not use file or method count as
   the architectural reason.
4. **Then resume later semantic Issues in their existing order.** Richer durable
   memory, affect/mood, and ambient autonomy remain separately governed work; they
   are not bundled into the evidence or Host-decomposition patch.

## Immediate architecture line — consolidate the reviewed authority baseline

The broad architecture-discovery phase is closed. New work starts from the canonical
event/readiness authority seam: Goal Interpretation establishes Responsibility / WHAT;
Planner (fast or deep pass) owns HOW; Goal Association independently owns canonical Goal
continuity; Trusted Capability Runtime and Providers realize Work; asynchronous Runtime
events report what happened; Host-bound Evidence records what is true; and a meaningful
state transition may create a bounded `CognitiveOpportunity` that re-enters the same
Planner with Responsibility + Goal + Situation + actual Work + Evidence. Planner may
produce zero, one, or many Activity changes. Existing-Work comparison is a Planner
operation, not a mandatory reconciliation stage. This baseline must pass the Charter's
architecture-irreducibility review before adding a new principle, owner, persistent state
concept, manager, workflow, contract field, or mechanism.

Next design/implementation order:

1. **GI/Planner input-ownership boundary — implemented and source-guarded.** GI is
   WHAT-only: Responsibility meaning, explicit/contextual semantic bindings, Goal
   relation, fresh-evidence need, and bounded unresolved meaning. GI has no authority or
   DTO fields to create/resolve planning InformationGaps, declare Capability inputs
   missing/blocking, or choose `ask_user`, context, observation/query, or default. Fast
   Planner fast pass owns execution-input completeness, source/default policy, gap provenance, and
   clarification selection without reinterpreting Responsibility. The temporary Deep-GI
   external-evidence/`ask_user` defense is removed; Deep GI is one source-based pass only
   for genuine consequential semantic ambiguity. Runtime commits a Planner gap to its
   exact GA-owned Goal before the question can be delivered.
2. **Planner fast-pass first advancement — implemented in the maintained path.** Keep
   Responsibility evidence as Goal Interpretation's provider-neutral WHAT handoff. The
   Planner fast pass is the first HOW path: before canonical Goal binding it may author
   one immediate safe Communicative Act and typed continuation dispositions for
   Goal Association and/or Planner deep pass. Goal Association remains the only canonical
   Goal-continuity authority; commitment-bearing Capability work still requires
   applicable canonical Goal grounding and trusted validation. Goal Interpretation
   has no speech or response contract. A Communicative Activity contains function,
   exact wording, timing, truth/evidence provenance, and constraints. The Host validates
   and schedules it mechanically before Vocal/TTS delivery; there is no second
   response-authoring semantic owner.
3. **Planner-owned communication and Evidence re-entry — implemented and source-guarded.**
   Planner is the only ordinary response semantic owner. Trusted Runtime/Host binds
   terminal Evidence through immutable request
   provenance to exact Goal IDs, then creates a bounded readiness opportunity for Planner
   with a version-consistent Goal/Evidence/Work snapshot. Planner chooses answer,
   follow-up Work, revision, clarification, waiting, silence, or no new Activity. Social Attention remains optional
   decoration attached to the same observable Main Activity and never delays it.
   Retain separate first-commit, TTS-first-PCM, playback-start, result-reentry,
   and Social-Attention-opportunity timing evidence.
4. **Epistemic Qualification contract detail — first source slice implemented.** Do not add an `EpistemicManager`.
   Extend existing capability/evidence contracts to represent claim-specific required
   observations, provenance/trust-domain independence, alternatives/corroboration,
   validity/freshness, closed-world coverage, and qualification state
   (`established|insufficient|stale|contradicted|unknown`). Keep ASR/input fidelity in
   Gateway and semantic meaning in GI/GA. Principal recognition/authentication uses
   the ordinary Capability/Provider/Evidence path; authorization/consent remains Host
   policy.
5. **Forward Adaptation contract detail — first source slice implemented.** Separate open-Responsibility actions from
   terminal-history learning proposals. Online Reflection may create only bounded
   advisory experience/calibration; trusted policy caps scope and lifetime and Memory
   materializes it with explicit expiry. It may not modify Stable Mind/shared prompts/models/global
   Fast/Deep policy, authorization/safety, Capability semantics, or cache semantic
   decisions. Shared/systemic changes remain offline and owner-governed.
6. **Retention/negative-evidence consistency.** Make `immutable while retained !=
   permanent` explicit across Evidence/Memory/Data Loop. No universal tombstone is
   required; absence supports a negative claim only under complete collection and
   retention coverage, otherwise Response must preserve `unknown`.
7. **Machine guards and scenarios.** Only after contract text is stable, add the
   smallest schema/runtime/audit changes needed to protect these boundaries. Tests
   should guard authority and observable semantics, not one incidental call sequence.
8. **Qualification after implementation.** Source/test success, target qualification,
   and release readiness stay separate; relevant revision/model/provider/config changes
   invalidate the corresponding qualification claim before age-based review does.

Exit criteria for this line:

- no reviewed case requires a new top-level semantic authority;
- GI emits no planning InformationGap or resolution strategy, while Planner resolves
  execution inputs without changing Responsibility meaning;
- Planner-selected Communicative Acts retain their exact model-authored wording,
  while Host delivery remains a mechanically validating non-authoring boundary;
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
   projection now carries only current relevance/interpretation references: the
   current turn ID, focused Goal IDs, discourse focus, unresolved condition refs,
   and evidence refs. It is rebuilt in-process, revisioned
   between Goal Association and planning, prompt-validated, and never owns or
   copies the referenced Goal/Evidence/provider truth.
3. **Goal materialization, refinement, and replacement are implemented.** A fully
   discharged provider-free interaction still receives canonical conversational Goal
   continuity for the admitted turn, but a closed Goal need not be durably retained merely
   because the response was immediate. Same-Responsibility refinement changes Canonical
   Goal meaning only. Planner may compare that meaning with retained/provisional Work and
   explicitly select reuse, correction, replacement, or no change; this is a Planner
   operation rather than a Work-Reconciliation stage. GA and Host never decide
   compatibility. Genuine
   replacement creates new Goal lineage, stops Planner-rejected old Work through
   trusted receipts, and supersedes the old Responsibility without rewriting history.
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

### Incremental implementation rhythm for human-like behavior

This sequence does not reorder the binding current execution order. It begins only
after the current-revision evidence line and the already-queued structural
simplification permit later semantic work. Here, `rhythm` means delivery cadence only;
it is not architecture vocabulary, a runtime mode, a persistent state, or another
manager. Each item should be one focused Issue/patch with an originating episode, the
earliest wrong boundary, a General Ability regression, canonical gates, and the highest
safe evidence profile available.

1. **Make simple interaction promptly useful.** Meet the approved Fast-Planner and
   audible-start budgets by removing avoidable model reloads, duplicate generations,
   and serial waits inside existing owners. A provider-free answer may close its canonical
   conversational Goal immediately without making that closed Goal durable; a pending-work
   acknowledgement must add truthful common ground
   and must not claim execution. Preserve Epistemic Qualification and every existing
   truth/safety validator.
2. **Keep conversation available while Work continues.** Exercise a follow-up or
   correction while safe read-only or embodied Work is queued/running. Gateway keeps
   accepting input, GI/GA preserve responsibility continuity, Planner revises only
   affected Work, and independent Work survives. Barge-in stops stale output without
   silently cancelling unrelated Goals.
3. **Speak from state changes, not pipeline milestones.** On progress, terminal
   Evidence, timeout, refusal, or cancellation, reactivate the existing Fast Planner
   with the bounded current snapshot. Deliver only the still-needed response delta at
   an appropriate conversational opening; suppress duplicate acknowledgement and
   completion speech. Safety/control obligations retain deterministic pre-emption.
4. **Make correction and waiting feel continuous.** Retain open Responsibility while
   waiting for user input, time, provider readiness, or trustworthy Evidence. A later
   event should resume from current Goal/Work/Evidence state rather than restart the
   whole request. Corrections revise current meaning, reuse compatible Work, and repair
   incompatible speech or effects forward without rewriting history.
5. **Add restrained embodied expression.** Qualify Social Attention only around an
   explicit primary Activity with current target/scene evidence. Optional gaze, posture,
   or expression remains resource-aware and fail-soft, never delays the primary outcome,
   and never becomes Goal-completion Evidence. Missing expression is preferable to a
   mismatched or unsafe gesture.
6. **Learn selectively after the interaction.** Use existing Reflection and Memory
   boundaries to retain only supported, reusable, scope- and lifetime-bounded meaning.
   Prove in a later episode that the retained lesson improves context without replacing
   fresh grounding, mutating Stable Mind/shared policy, or reopening completed history.

Do not bundle affect simulation, ambient autonomy, multi-user identity, or new durable
Mind objects into these slices. Those require their separately governed evidence,
privacy, consent, and authority decisions. The target is coherent behavior over time,
not a claim that Chromie is a human being.

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
for sibling completion. Incremental terminal Evidence reconciliation and detached cognitive
re-entry are now maintained without creating a second Work/Result/Event manager or semantic
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
- **Issue — Reconcile terminal Evidence incrementally — source implementation complete.**
  `ExecutionOutcomeReconciler.reconcile_terminal_result(...)` validates the full committed
  request set against the immutable Plan but emits canonical `ExecutionEvidence` only for the
  exact terminal request. `CognitiveTurnClosure.build_terminal_evidence(...)` applies the same
  committed output-schema and completion-evidence gates used by final closure. A sibling with
  no terminal result is absent from incremental Evidence rather than fabricated as
  `not_run`/`missing_result`; the terminal request receives the same stable `evidence_id` used
  by final aggregate reconciliation. `ExecutionOutcomeBundle` remains final terminal truth,
  not a live scheduler snapshot, and no duplicate completion store is introduced.
- **Issue — Decouple interaction lifetime from capability lifetime — source implementation complete.**
  All maintained interaction responses now submit through `submit_response(...)`; the foreground
  interaction task ends after Runtime acceptance while a Runtime-correlated result consumer owns
  lifecycle observation until terminal closure. Each terminal Capability result may become exact incremental `ExecutionEvidence`, then an
  internal `CognitiveOpportunity`, then Planner re-entry when the affected Responsibility remains
  relevant. Result arrival is never fabricated as a user turn and the callback never chooses speech.
  Planner receives the current Goal/Responsibility/Situation/Work/Evidence view and may answer,
  author genuinely new follow-up Work, wait, or emit no Activity; newly planned Work returns through
  the same detached Runtime boundary. Planner-authored `after_capabilities` terminal wording is
  excluded from detached execution because completion language belongs to terminal Evidence. Final
  aggregate closure remains available for whole-scope truth and filters Evidence already consumed
  incrementally so the same transition is not planned or spoken twice. Runtime open-interaction ownership
  also remains visible to scoped cancellation after the foreground Python task has exited.
- **Issue — Harden cancellation, supersession, and late-result semantics — source implementation complete.**
  Late terminal Evidence remains valid execution history, but cognitive re-entry now fails closed
  unless every source Goal still has open Responsibility and the Host-owned current binding matches
  the exact canonical Plan ID/fingerprint and request ID that originally dispatched the work. Goal
  cancellation, Goal supersession, replanning, or request rebinding therefore suppress obsolete
  result speech/action without discarding the terminal Evidence. Existing exact cancellation receipts
  continue to own provider stop truth; a late provider completion cannot reopen terminal Goal state.
- **Issue — Introduce a Capability Runtime backend boundary — source implementation complete.**
  `CapabilityRuntimeBackend` now isolates submission-liveness mechanics from canonical Runtime
  semantics. `InProcessAsyncioBackend` is the maintained default. Backend handles are opaque
  Runtime-internal references: they are absent from `CapabilityDispatchReceipt`, lifecycle events,
  provider contracts, Goal/Plan/request identity, and cognitive context. Validation, scheduling,
  cancellation scope, event publication, and terminal truth remain owned by `CapabilityRuntime`.
- **Issue — Qualify a DBOS durable backend with read-only/idempotent work — source qualification complete; production activation intentionally gated.**
  `DBOSCapabilityRuntimeBackend` now defines a serializable durable carrier and a lazy optional
  DBOS adapter. Durable execution requires explicit `durable_runtime_eligible` opt-in plus
  canonical idempotence and side-effect-free/safe-read metadata; the weather lookup is the first
  opted-in Capability. Physical/effectful work fails closed. Repository tests prove durable-ID
  retrieval across fresh backend instances and backend cancellation without leaking workflow IDs
  into Chromie identity. Real DBOS crash/restart qualification is not claimed in this source tree:
  production activation additionally needs startup rehydration of CapabilityRuntime ownership and
  terminal-result consumers, and must be exercised with the optional DBOS dependency before enablement.
- **Issue — Migrate long-running Soridormi work to asynchronous provider lifecycle — source implementation complete for provider activities.**
  Soridormi body-activity execution may now acknowledge `running`/non-terminal state; the adapter
  retains the provider-owned `compiled_activity_id`, polls `soridormi.activity.status`, and projects
  each non-terminal snapshot through `CapabilityExecutionContext.publish_progress(...)` into generic
  `CapabilityRuntimeEvent(progress)` observations. Terminal member evidence is produced only after
  Soridormi reports terminal activity state. Runtime timeout/cancellation still invokes the existing
  provider-local `soridormi.activity.cancel` path. Chromie never interprets provider status as a new
  cognitive plan and never exposes Soridormi activity identity as canonical Capability identity.
  Single named-skill calls keep their existing wire execution path because the checked-in provider
  contract exposes no named-skill status/event endpoint; no fake polling API is invented.
- **Issue — Delete remaining foreground aggregate-wait behavior — source implementation complete.**
  The old `CapabilityRuntime.execute(...)`, `InteractionRuntimeCoordinator.execute(...)`, and
  `VoiceAssistant.execute_interaction_response(...)` aggregate APIs are deleted. Every maintained
  foreground interaction now dispatches through `submit_response(...)` and returns after Runtime
  acceptance; terminal joining is explicit only in result consumers or bounded internal call sites
  that genuinely require terminal truth. Planner-authored `after_capabilities` completion wording
  is never executed before terminal Evidence, and the coordinator no longer invents semantic failure
  speech. Repository policy forbids reintroducing the removed aggregate APIs or bypassing detached
  result consumers.

Each Issue must preserve the central authority invariant: Runtime owns execution lifecycle;
LLM/Core owns meaning. Framework choice must not turn transport, queues, workflows, or
callbacks into a second planner.

## Current priorities

1. Implement the owner-approved GI/Fast-Planner input-ownership migration before
   treating the Chongqing weather fix as architectural closure. Then preserve the
   completed authority spine and implement only the contract detail now proven necessary:
   Communicative-Act/wording ownership, claim-specific Epistemic Qualification, and
   bounded Forward Adaptation. Multi-user identity is not a new owner:
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
  Fast and Deep Planner contracts, Planner-owned Communicative Activities, Trusted Capability
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

### Semantic authority closure — source complete

- `apply` is the only maintained authoritative semantic path.
- `report_only` is observer-only and `off` is diagnostic fail-closed disablement.
- GI owns WHAT; Goal Association owns canonical Goal continuity; Fast/Deep Planner
  own HOW and exact Communicative Activities.
- Runtime derives the execution lane mechanically from the terminal Plan and fails
  closed when that lane is unsupported or disabled.
- Retired Agent `/run`, `/interaction`, `/agents`, CapabilityAgent, direct-LLM,
  route/intent, and emergency semantic fallback surfaces are not rollback options.

Exit criteria:

- the semantic-authority matrix has exactly one owner per maintained entrypoint;
- unsupported/disallowed terminal Plan lanes produce typed no-action outcomes;
- no authoritative failure enters another semantic planner;
- current docs, profiles, and source describe the same authority and lane policy.

### Goal-scoped Interaction Ledger and current-turn continuity

Issue [#22](https://github.com/TimeTreker/chromie/issues/22) owns the append-only
Interaction Ledger and bounded Goal-scoped Interaction Context supplied to Goal
Association, Fast Planner, and Deep Planner. The Ledger
transports facts from existing owners; it does not replace or rewrite playback,
Social Attention results, the canonical Plan, Goal state, static preflight
diagnostics, or `ExecutionOutcomeBundle` evidence.

Exit criteria:

- delivered response-stage speech retains exact turn, Goal, Plan, claim, and
  completion-restriction provenance;
- Cognitive Runtime, playback, Trusted Capability Runtime, and execution
  closure append only typed facts they authoritatively observe;
- replay cannot change an immutable event, and terminal Activity entries require
  trusted execution evidence references;
- Goal Association receives bounded recent Interaction Context and later
  Planners receive the Goal-scoped projection so they can produce
  only the still-needed delta;
- A Fast Planner Communicative Activity scheduled before GA finishes retains GI Responsibility refs and is
  later bound only through GA-owned canonical Goal identity;
- Goal-bound speech cannot be reused for unrelated Goals or a different Plan;
- scheduled and delivered speech remain distinct, and neither proves Activity
  execution or completion; and
- focused lane/runtime/model-prompt regressions plus the canonical source gate
  pass without a new runtime switch, compatibility path, standalone document,
  or competing semantic/effect authority.

### Interpretation and capability grounding

- Preserve the implemented ownership boundary: GI emits no planning InformationGap or
  strategy fields; Fast Planner owns execution-input completeness, source/default choice,
  blocking, gap provenance, and clarification selection. Keep GI bounded unresolved
  meaning for genuine semantic ambiguity, GA-only canonical Goal commit, and exact
  pending-clarification continuity. Keep clear weather, missing lookup input, ambiguous
  referent, and movement regressions in the relevant general-ability classes.
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

**First source slice implemented.** Planner re-entry from terminal Evidence now uses a
pure Host policy module for current Goal/Plan/request validation, exact originating
Responsibility selection, completed-Activity idempotence, and already-delivered speech
delta suppression. Missing Responsibility provenance fails closed instead of fabricating
a callback Responsibility. This extraction removes nine private methods from
`VoiceAssistant`, lowering its method count from 159 to 150. A second mechanical slice
moves TTS text segmentation and Goal-list console projection behind existing Host/runtime
module boundaries, lowering the composition root from 150 to 142 methods. Stateless observability-recording containment then lowers it to 139 methods. Fixed-reflex confirmation-token revocation, widening evidence, and state bookkeeping now live with the existing ConfirmationDialogue owner, lowering it to 136 methods while confirmation meaning remains GA-owned and confirmation speech remains Planner-owned. OS-default audio-device detection, pending-switch queueing, cross-device input reset, and output rollover then move to stateless `audio_device_lifecycle.py`, lowering the root to 129 methods while device discovery remains `AudioDeviceManager`-owned and output I/O remains `PlaybackTransport`-owned. Top-level process teardown then moves to stateless `shutdown_lifecycle.py`: it reuses the existing InputTurn task owner, Playback wait/duck/transport owners, Session trace finalizer, and concrete ASR/HTTP/audio resource closers. Removing the old `VoiceAssistant.cleanup()` method and cleanup-only output-close compatibility wrapper lowers the root to 127 methods. Accelerator telemetry schedule/sample/task-tracking then moves into the existing stateless observability policy, lowering the root to 124 methods while Session remains the trace owner and telemetry remains non-semantic. The next mechanical slice removes the seven remaining PlaybackTransport/TTS compatibility delegates from `VoiceAssistant`: the transport now calls its own provider/output methods, Host call sites access the cached transport directly, and the existing TTS/playback trace spans move to that real owner. This lowers the root to 117 methods without moving Planner-authored speech semantics, playback-generation authority, or barge-in/reflex interruption policy. The next slice removes twelve `VoiceAssistant` input/session compatibility delegates: `InputSessionRuntime` calls its own microphone callback, VAD/ASR queue, routed-turn lifecycle, injected/device audio streams, and session-idle sweep directly, while Host integration obtains that existing runtime explicitly and `InputTurnLifecycle` remains the task-state owner. This lowers the root to 105 methods without moving Gateway, turn, reflex, or conversation semantics. None of these
slices adds a semantic owner, manager, state store, service, environment key, or public
runtime path.

**Goal Association internal decomposition implemented further.** GA now separates model DTO/schema/normalization/typed-integrity mechanics into `agent/app/goal_association_contract.py` and bounded prompt projection/system-prompt construction into `agent/app/goal_association_prompt.py`. `GoalAssociationResolver` remains the only GA model-invocation/continuity transaction and the only canonical Goal-continuity writer. Neither extracted module may own Ollama invocation, runtime state, Goal commit, tracing, or a second semantic lifecycle. The resolver source is therefore concentrated on semantic transaction/materialization rather than decoder-schema and prompt mechanics. The same standard applies to future Planner/GA internal decomposition: extract representation, projection, decode, normalization, or mechanical validation only when the original semantic owner remains singular.

**Planner prompt/projection decomposition implemented.** Fast and Deep Planner prompt construction, first-response truth/progress prompt text, system prompts, capability projection, and layered-prompt assembly now live in `agent/app/planner_prompt.py`. The module is projection-only: it has no model client, runtime trace, Plan validation/materialization, Goal mutation, execution authorization, or second semantic lifecycle. `FastPlannerResolver` and `DeepPlannerResolver` retain model invocation, same-tier repair/escalation, Plan validation, and the single Planner HOW authority; fast/deep remain cognition depth/pass labels rather than separate planners.

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
