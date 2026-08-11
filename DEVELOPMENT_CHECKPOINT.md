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

## Immediate checkpoint — discuss architecture before adding modules

The **next development work is to finish the Continuous Mind architecture
synthesis**, then implement it incrementally. Do not add a `BeliefManager`,
`ReflectionManager`, generic priority engine, background-thought loop, or other
new cognitive framework merely because the corresponding human phenomenon is in
the problem-space list.

The authoritative problem space, questions, directions, and compression rule are
in
[Goal-Driven Cognitive Architecture](docs/GOAL_DRIVEN_COGNITIVE_ARCHITECTURE.md#411-candidate-continuous-mind-state-model--immediate-architecture-work).
The delivery order is in [Roadmap](ROADMAP.md#immediate-architecture-line--continuous-mind-synthesis).

Immediate discussion order:

1. compress the candidate state model: Observation/Belief, unfinished
   Responsibility, Intention/Progress/Commitment, Attention/Working Set,
   Memory/Experience, Reflection/Metacognition, with authority as a cross-cutting
   boundary;
2. decide which concepts are already represented by Goal, Interaction Ledger,
   CanonicalPlan, ExecutionOutcome, Memory, Capability/provider state, and
   General Progress, and which truly need a new first-class lifecycle;
3. settle Goal as unfinished responsibility versus immediately completed
   transient progress, including concerns, promises, time/dependencies, and slow
   cognition reactivation;
4. settle observation-driven belief/revision, uncertainty, common ground,
   intention/commitment, incremental planning, attention/preemption, and selective
   Reflection; and
5. only then implement slices in dependency order and delete superseded pipeline
   or compatibility concepts instead of layering adapters around them.

The design rule is: **design the whole Mind, implement the next invariant, and
keep the final concept count small.** Weather, chat, walking, or any individual
scenario is evidence for a general ability, never the architecture target.

## Verification state

`docs/STATUS.md` owns current implementation and evidence claims. The General
Progress change retains source regressions for native conversation, exact
capability progress, Goal binding, safe-read readiness, effectful negative
boundaries, peer Social Attention, and truthful outcome presentation. It does not
by itself establish live-model latency, physical audio, simulator, or physical
robot qualification.

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

## Near-term implementation order after architecture decisions

1. responsibility/Goal materialization and lifecycle semantics;
2. bounded Observation/Belief update plus evidence-driven reactivation;
3. Intention/Progress/Commitment and revision/incremental-planning semantics;
4. Attention/Working Set, time/dependency wake-up, and cognitive preemption;
5. selective Reflection, memory consolidation/forgetting, and learning promotion;
6. multi-user privacy/consent, durable recovery, competence/calibration, and
   bounded autonomy after the earlier authority model is stable.

Every slice must first identify the reusable cognitive invariant, map or remove
existing concepts, retain general scenarios, and avoid a new permanent abstraction
when an existing owner can represent the state correctly.

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
