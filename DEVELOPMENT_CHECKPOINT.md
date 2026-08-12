# Chromie Development Checkpoint

Status: current resume point

## Direction

Continue the **Goal-driven single semantic authority** architecture as a
readiness-driven Continuous Mind rather than a mandatory cognition pipeline.
The Cognitive Gateway owns ingress and deterministic protective reflexes; the
Cognitive Core owns meaning and responsibility; trusted Host/provider boundaries
remain the only authorities for effects and evidence.

The current General Progress implementation is a substrate, not the finished
Mind model. Fast Understanding can surface a complete `native_response` or exact
`capability` progress candidate; ready native conversation and trusted safe-read
work may advance while Goal Association continues, and Goal Association later
provides explicit canonical responsibility binding. Effectful work still waits
for the applicable planning, confirmation, authorization, resource, and provider
safety boundaries. Social Attention is a peer event lane and does not own Goals
or completion.

## Architecture checkpoint — Continuous Mind synthesis compressed

The broad architecture discussion is now sufficiently complete to move from
ontology expansion to detail validation and incremental implementation. Do not
add a `BeliefManager`, `SituationManager`, `ReflectionManager`, generic priority
engine, dependency graph, background-thought loop, or another cognitive framework
merely because the corresponding human phenomenon has a useful name.

The authoritative complete problem space remains in
[Goal-Driven Cognitive Architecture](docs/GOAL_DRIVEN_COGNITIVE_ARCHITECTURE.md#412-complete-continuous-mind-problem-space--retained-design-inventory).
The compressed conclusion is
[Continuous Mind synthesis](docs/GOAL_DRIVEN_COGNITIVE_ARCHITECTURE.md#414-continuous-mind-synthesis--compressed-architecture-baseline),
and the implementation order is in
[Roadmap](ROADMAP.md#immediate-architecture-line--continuous-mind-implementation-from-the-compressed-baseline).

Current architecture baseline:

```text
Durable Mind
  Stable Mind
  Goal       = canonical unfinished Responsibility
  Memory

Live Mind
  Situation  = bounded, revisable, mostly reconstructable soft state

Grounding/action substrate
  Evidence/Ledger; Progress/Plan/Request/Execution/Outcome; Capability/provider truth
```

`Responsibility` and `Work` are architecture vocabulary, not approved parallel
runtime objects: Goal owns the former; existing Progress/Plan/Execution artifacts
express the latter. Intention, Commitment, Readiness, Attention, Salience,
Concern, Reflection, Learning, Recovery, Common Ground, Affordance, and similar
terms remain derived/process/policy/projection concepts unless a concrete case
proves information loss without a new owner.

The design rule remains: **design the whole Mind, implement the next invariant,
and keep the permanent concept count small.** Individual scenarios are evidence
for a general ability, never the architecture target.

Key invariants now settled for detail work:

- Reality enters through Evidence; Goal/Plan/model inference cannot manufacture
  grounding.
- Situation is current soft interpretation, not a copied world database or
  historical authority.
- A Goal materializes only for an owned outcome that remains unfinished and
  needs semantic continuity; immediately completed ready progress need not create
  durable Goal state.
- Goal identity follows Responsibility continuity; refinement may revise current
  Goal meaning with provenance, while a genuinely different Responsibility gets
  a new Goal.
- Decomposition belongs to Work/Plan unless an independent Responsibility truly
  emerges; dependencies are usually Situation/world conditions rather than a
  Goal graph.
- Current canonical meaning may be revised; historical Evidence, execution
  outcomes, and delivered speech are never silently rewritten. Repair forward.
- Goal lifecycle is responsibility-level, not workflow-level: planning, waiting,
  confirmation, scheduling, running, retry/recovery, provider failure, and timeout
  belong to Work/runtime artifacts. Execution success/failure is evidence for
  reconciliation and cannot by itself decide whether the Responsibility is
  satisfied or abandoned.
- Existing Work survives an upstream revision when it remains semantically
  compatible; do not invalidate everything merely because a version changed.
- Open Goals wait for relevant events rather than a polling thought loop. A state
  change may require none, local, fast, slow, or overlapping cognition.
- Memory is selective reusable past meaning; Reflection/learning are bounded
  processes and cannot rewrite provider authority or Stable Mind.

## Verification state

`docs/STATUS.md` owns current implementation and evidence claims. General
Progress plus the first Goal/Work truth-separation slice now cover ready progress,
canonical Responsibility lifecycle, explicit execution-to-Goal reconciliation,
and correction-driven reopening. They do not by themselves establish live-model
latency, physical audio, simulator, or physical robot qualification.

Before claiming the working tree is clean, run the canonical gate in a
dependency-complete environment:

```bash
./scripts/run_tests.sh
```

Useful focused ownership/structure checks are:

```bash
python scripts/check_repository_policies.py
python scripts/check_test_ownership.py
python scripts/runtime_configuration_inventory.py --check
python scripts/check_runtime_structure.py
python scripts/check_docs.py
python scripts/semantic_authority_audit.py --check
./scripts/benchmark_check.sh
```

Do not report Ruff, Mypy, GPU, microphone, speaker, MuJoCo, physical-provider,
or live-model results unless those exact gates actually ran and retained their
evidence.

## Near-term implementation order from the compressed baseline

1. **implemented:** Goal Responsibility lifecycle is separated from
   Task/Plan/request/execution lifecycle; Goal satisfaction/reopening now crosses
   explicit reconciliation rather than provider/request status projection;
2. **implemented:** the minimum bounded Situation projection is reconstructed from
   current authoritative references, revisioned across cognition, and never persisted
   as a Belief/world-state database;
3. **implemented:** transient materialization, compatible same-Responsibility refinement,
   genuine replacement lineage, and trusted Work-stop/forward repair;
4. **implemented:** trusted execution-state deltas derive ephemeral bounded
   `CognitiveOpportunity` events for fast/slow reactivation without polling or a queue;
5. **implemented:** slow opportunities selectively invoke typed Reflection; repeated
   evidence may promote only ephemeral task/session memory, never Stable Mind or authority;
6. **implemented:** restart restores unfinished Responsibility while current Work is
   recoverable/revalidation-required; volatile Situation/provider/body/confirmation state
   is discarded or archived as recovery provenance rather than restored as current truth;
7. defer multi-user privacy/scoped durable consent, broader recovery/autonomy,
   competence calibration, and richer continuation semantics until a concrete
   slice requires their missing authority/lifecycle.

Every slice must first identify the reusable cognitive invariant, map or remove
existing concepts, retain general scenarios, and avoid a new permanent
abstraction when an existing owner can represent the state correctly. If a new
concept is proposed, the review must name the two behaviorally different states
that would otherwise become indistinguishable.

## Canonical owners

- stable boundaries and principles: [Project Charter](docs/PROJECT_CHARTER.md)
- cognitive constitution and complete problem space:
  [Goal-Driven Cognitive Architecture](docs/GOAL_DRIVEN_COGNITIVE_ARCHITECTURE.md)
- executable turn/evidence lifecycle: [Cognitive Turn Loop](docs/COGNITIVE_TURN_LOOP.md)
- delivery order: [Roadmap](ROADMAP.md)
- implementation and evidence: [Current Status](docs/STATUS.md)
- target workflow: [Target Evidence Closure](docs/TARGET_EVIDENCE_CLOSURE.md)
- interfaces: [API Reference](docs/API_REFERENCE.md)
- operation: [Runbook](CHROMIE_RUNBOOK.md)
