# Chromie Roadmap

Chromie is in active development. This roadmap owns delivery order and exit
criteria; current implementation and evidence state live in
[docs/STATUS.md](docs/STATUS.md), and completed history lives in Git and the
[CHANGELOG](CHANGELOG.md).

The current focus is a **Goal-driven single semantic authority**. The Cognitive
Gateway owns ingress, protective reflexes, and attention admission. The
Goal-driven Cognitive Core owns ordinary semantic interpretation, goal
association, Planner-authored Work, Value Judgment, Social Cognition
communication, and outcome reconciliation. Provider and Host boundaries remain
the only authorities for effects. The core embodied target is a qualified
simulator provider. Chromie's cognition must remain backend-neutral;
physical-robot commissioning is optional Soridormi/provider work and is not a
Chromie milestone or release prerequisite.

Sequential milestone codes are not part of the current project model. Work is
organized by capability, risk, and retained evidence.

UMI owns complete natural-language meaning and provider-neutral result type; GA
owns retained Goal association and Host inherits new Goal meaning; the one
Planner owns parameter extraction, realization and readiness
(PLANNER-AUTHORITY-001); Value Judgment reviews value-relevant effects
(VALUE-JUDGMENT-001); SC owns ordinary communication. No model, profile or
release is promoted.

## Social Cognition migration

The owner approved the [Social Cognition target](docs/PROJECT_CHARTER.md#social-cognition--accepted-target-2026-09-14)
on 2026-09-14 and authorized implementation, multimodal interaction,
environment-driven initiative and high-priority foreground scheduling. The
communication responsibility has moved from Planner to this distinct Core owner;
UMI/GA, Work planning, Memory, Host and Soridormi retain their own truth and
permissions. The retired response/critic/Social Attention model paths and
Planner-authored speech must not return.

The transaction contracts and the coherent migration of the maintained path are
source-complete. Remaining order:

1. **Prove authority and behavior.** Freeze bilingual contrasting episodes,
   including substantive dialogue without Work, pending/delivered speech,
   results overtaking progress, multi-Goal scope, failures and interruption.
   Apply the [acceptance contract](docs/ACCEPTANCE.md#social-cognition-acceptance)
   and semantic qualification method to both owners and the combined workflow.
2. **Measure the scheduling tradeoff.** Verify SGLang scheduler support and
   configuration for independently prioritized requests; measure idle and
   contended first meaningful response, task completion and TTS, and rule out
   Planner starvation.
3. **Retain the evidence closure sequence.** Canonical local gates, narrow
   current-revision supervised voice and the default target-evidence profile
   remain required. Source implementation, automated verification, target
   validation and release readiness are recorded separately in Status.

## Current priorities

1. **Everyday live-cohort root-cause repairs (active Issue).** Run the
   `scenarios/everyday/` cohort against Soridormi MuJoCo, judge every case and
   repair each failure at its earliest responsible owner. Scope:
   [checkpoint](DEVELOPMENT_CHECKPOINT.md); next steps:
   [Status open work](docs/STATUS.md#current-open-work).
2. **Semantic transaction simplification and generalization.** Source-span
   provenance, semantic-artifact lineage, the SC model-view diet and the
   provider-declared semantic Capability facade substrate are implemented.
   Remaining, in order:
   - publish the semantic facade on the live Soridormi catalog, beginning with
     semantic turn direction, and prove backend changes do not change Goal/Plan
     meaning;
   - add declared metamorphic families (paraphrase, bilingual equivalence,
     irrelevant context, catalog permutation, controlled semantic deltas,
     provider-realization invariance, compositional recombination) and bounded
     stateful episodes to the existing scenario and general-ability
     infrastructure;
   - only then requalify the model/profile on the reduced transactions, then
     SGLang priority/contention, then latency.
3. **Persistent Social Mind qualification.** The person-first identity,
   Goal-free Situation wake, trusted social-perception ingress, relational
   Memory with privacy provenance, social feedback and bounded self-initiative
   contracts are source-implemented. Concrete perception and identity
   adapters, real-model social judgment and live multi-person interaction
   remain unqualified. Extend General Ability evidence (family life, meeting a
   new person, familiarity, negative feedback, privacy boundaries, doing
   nothing, Capability temptation without need) before wider autonomy.
4. **Evidence closure.** Preserve the canonical local gate, then narrow
   current-revision voice proof, then default target-evidence closure.

Across all lines: `use less to solve more`; fix the earliest wrong boundary; do
not add a `SpeechManager`, Response Composer, recovery brain, compatibility
semantic path, or a second WorkDAG semantic owner.

## Completed foundations

Completed foundations are represented by capabilities and evidence, not by
sequential milestone numbers. Earlier incremental work is represented by two completed foundation groups:

- **Local interaction foundation:** Compose-based services, ASR/TTS contracts,
  bounded session state, playback ordering, reversible speech-start barge-in,
  order-aware echo resume, deterministic stop and cancellation, and simulator
  integration. Physical audio remains an open evidence track.
- **Goal-driven control-plane foundation:** Cognitive Gateway admission,
  immutable turn envelopes, Core-owned User Meaning Interpretation, Goal Association,
  the Planner contract, SC-owned Communicative Activities, Trusted Capability
  Runtime validation, outcome evidence, and fail-closed execution.

Source lines completed on top of them (details in Git history and the CHANGELOG):
asynchronous transport-independent Capability Runtime (dispatch receipts,
lifecycle events, incremental terminal Evidence, detached re-entry, late-result
suppression); removal of Host-authored semantic responses for confirmation,
cancellation, result meaning and body recovery; Planner-owned WorkDAG with a
mechanical DAGEngine; Continuous Mind wake/re-entry, bounded Situation,
structured time conditions and context-activated Memory; layered prompt prefixes;
semantic authority closure (`apply` is the only authoritative semantic path);
the need-first one-Planner contract; and Value
Judgment.

These foundations are maintained only while their automated contracts remain
passing.

## Active source work

### Social Cognition interaction and independent Work — source implemented, qualification open

`/plan-advance` emits one complete Work decision; `/social-cognition` authors
interaction from the shared UMI result, canonical needs, Work/Evidence state or
trusted Situation. GA/Work and SC proceed independently until a required
confirmation or explicit ordering dependency must join.

Maintained exit criteria:

- complete validated SC results precede delivery; no raw tokens or partial JSON;
- exact typed communication needs preserve confirmation, input and before/after
  Work ordering; optional SC does not delay independent Work;
- actual playback, interruption and cancellation retain exact identity and truth;
- trusted environmental initiative needs no synthetic UMI or task Goal;
- optional expression uses qualified targets and providers without task authority;
- freeze and adjudicate SC and Work transactions, run full local gates, and retain
  current-target latency/contention and physical-evidence gaps separately.

Current evidence is owned by [STATUS.md](docs/STATUS.md#social-cognition-migration).

### Goal-scoped Interaction Ledger and current-turn continuity

The append-only Interaction Ledger and bounded Goal-scoped Interaction Context
are supplied to Goal Association and the Planner. The Ledger transports facts
from existing owners; it does not replace or rewrite playback, auxiliary-Activity
results, the canonical Plan, Goal state, static preflight diagnostics, or
`ExecutionOutcomeBundle` evidence.

Exit criteria:

- delivered speech retains exact turn, Goal, Plan, claim, and
  completion-restriction provenance;
- Cognitive Runtime, playback, Trusted Capability Runtime, and execution
  closure append only typed facts they authoritatively observe;
- replay cannot change an immutable event, and terminal Activity entries require
  trusted execution evidence references;
- an SC Communicative Activity scheduled before GA finishes retains UMI
  Responsibility refs and is later bound only through GA-owned canonical Goal identity;
- Goal-bound speech cannot be reused for unrelated Goals or a different Plan;
- scheduled and delivered speech remain distinct, and neither proves Activity
  execution or completion.

### Interpretation and capability grounding

- UMI emits no planning InformationGap or strategy fields and never authors
  bindings; the Planner owns execution-input completeness, source/default choice,
  blocking, gap provenance, and clarification selection. UMI keeps bounded
  unresolved meaning for genuine semantic ambiguity.
- One User Meaning Interpretation transaction: one primary interpretation, then
  accept, delegate genuine consequential unresolved WHAT once to source-based
  Deep UMI, or fail closed. Invalid DTOs receive no same-authority semantic repair.
- Treat non-empty interpretation failure as `interpretation_unavailable`; never
  rewrite it into plausible chat, tool, memory, or motion intent.
- Goal Association is primary-only: one call, at most one semantics-preserving
  repair for a Pydantic-invalid DTO, then trusted closed-reference, provenance,
  cardinality and continuity validation; every UMI Responsibility is conserved
  exactly once across associations and new Goals.
- There is one Planner pass plus at most one need-first library search and
  re-plan; regeneration is reserved for one mechanically malformed DTO; semantic
  rejection and trusted Host rejection are terminal.
- Expand general-ability scenarios rather than phrase-specific routing rules.

Exit criteria:

- no fallback invents an ordinary semantic lane;
- an effectful Goal has an owned executable step, delivered evidence for the
  same Goal, or an explicit clarify/unavailable/refused outcome;
- compound body requests retain ordered exact capabilities;
- missing abilities remain honest terminal outcomes;
- semantic outcome tests enforce logical model-call budgets instead of an exact
  historical prompt sequence.

### Vocal semantics and provider qualification

`chromie.vocal.perform` and `chromie.media.play|pause|resume|seek|stop|volume|status`
have source-qualified provider contracts; real vocal modes and real media remain
target evidence. Vocal, TTS synthesis, playback transport, echo handling,
audible-delivery ordering, and user-level barge-in remain Chromie-owned;
Soridormi is a peer embodied Capability Provider beneath Activity.

- Keep `singing`, `humming`, `recitation`, and other authored vocal performance
  in Vocal even when coordinated with body work; keep playback of existing
  audio in Activity with an exact media-provider capability identity.
- Return exact unavailable outcomes for unsupported modes; never silently
  downgrade one vocal mode to another, and do not let ordinary expressive TTS
  close a singing outcome.

Exit criteria: exact capability identity survives proposal, validation,
authorization, execution, cancellation, and evidence; real singing and physical
audio are claimed only from retained mode-specific target evidence.

### Conditional vocal-hosting review

Do not move TTS, playback, microphone, speaker, or media execution into
Soridormi. Reopen the hosting decision only when retained evidence demonstrates
a concrete blocker the current peer-provider boundary cannot meet: frame-accurate
viseme/body/audio synchronization on a physical robot, measured start skew or
cancel-to-silence latency outside a named budget, platform audio adaptation
leaking into cognitive code, or accelerator/mixer contention that cannot be
solved behind the provider contract. Any such review is a separate architecture
decision that updates the Charter, `AGENTS.md`, capability contracts, Status,
Roadmap, tests, and evidence plan together.

### Structural simplification

The maintained component and failure contracts are
[VoiceAssistant Composition Root](docs/VOICE_ASSISTANT_COMPOSITION_ROOT.md) and
[Runtime Failure Paths](docs/RUNTIME_FAILURE_PATHS.md). Planner prompt
construction lives in `agent/app/planner_prompt.py` and produces one complete
Work DTO with no presentation wording; the Planner owner is split into
model-contract, context, grounding, schema, validation and fallback modules
without a re-export facade. Goal Association is split into contract, schema,
validation and prompt modules while `GoalAssociationResolver` remains the only
GA transaction.

- Decompose the Orchestrator composition root when ownership or independently
  testable boundaries improve; preserve blocking ownership, exception-boundary
  and direct-model-call checks.
- Remove import-time global logging configuration from library modules.
- Keep configuration parsing inside typed settings owners.
- Delete transient implementation plans once their durable contracts have moved
  to canonical architecture or policy documents.

Exit criteria:

- size deltas and ownership rationale are reviewed; no size-only pass condition;
- ownership, exception-boundary and direct-model-call checks remain effective;
- no deleted document has an incoming link;
- every specialized document has a component, operator, or mechanical owner.

### Reproducible verification

- Run repository policy, test ownership, static analysis, configuration,
  runtime structure, documentation, benchmark, unit, and legacy compatibility
  checks from one canonical entry point (`./scripts/run_tests.sh`).
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
