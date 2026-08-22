# Chromie Development Checkpoint

Status: current resume point; incomplete development snapshot
Updated: 2026-08-22
Patch baseline: user-supplied `chromie_2026082206.zip` plus the applied rebased Phase 1C
and Phase 1D patches. The archive already contained the user's applied Phase 1A/1B state.
No archive-wide Git identity is claimed.

## Read first

Canonical owners remain [Project Charter](docs/PROJECT_CHARTER.md),
[Human-Like Interaction Contract](docs/HUMAN_LIKE_INTERACTION_CONTRACT.md),
[Current Status](docs/STATUS.md), [Roadmap](ROADMAP.md), and
[Acceptance](docs/ACCEPTANCE.md). Source and executable evidence win over stale prose.

Current focus: **Phase 4 repository hygiene**, after source-closing Phase 3 WorkDAG /
DAGEngine authority convergence. Do not redesign the Goal-driven backbone, put DAG
semantics into Goal Association, or reintroduce removed response/recovery owners.

## Current architecture

```text
person -> Gateway -> GI -> Responsibility / WHAT
                           |-> GA -> canonical Goal continuity
                           `-> Planner fast/deep -> Plan / Activities
                                                 -> optional WorkDAG
                                                 -> DAGEngine / Runtime -> Provider
                                                 -> async event -> Evidence
Responsibility + Goal + Situation + Work + Evidence
                           -> CognitiveOpportunity -> Planner
                           -> 0..N Activity changes or none
```

- GI owns provider-neutral Responsibility meaning only.
- GA owns canonical Goal identity and continuity only.
- Fast/Deep are cognition passes of one Planner HOW authority.
- Planner owns ordinary Communicative Activities and exact wording.
- Runtime/Providers report execution facts; Evidence records trusted truth.
- `CognitiveOpportunity` is readiness, not another semantic owner.
- Provider/body-local DAGs may implement one selected Capability without becoming
  Chromie's global planner.

Planner implementation remains internally decomposed without changing authority:
`planner_model_contract.py`, `planner_context.py`, `planner_grounding.py`,
`planner_schema.py`, `planner_validation.py`, `planner_fallback.py`,
`planner_audit.py`, and `planner_prompt.py` are implementation layers of that same owner.

## Audit remediation closed in source

The 2026-08-22 audits converged on two layers: live semantic-authority correctness and
repository/documentation debt. The live Phase 1 findings are source-closed:

- Confirmation state owns authorization facts only and requires Planner-authored wording.
- Named cancellation returns bounded cancellation Evidence to the same Planner path;
  Host no longer replaces the current Planner response or rebuilds child confirmation Plans.
- Deterministic post-execution `status -> sentence` composition is removed; terminal truth
  re-enters Planner as Evidence/current-state context.
- Host body-recovery Plan/prompt synthesis is removed; bounded provider retryability facts
  remain Evidence and Planner owns retry/alternative/clarification/wait/no-new-Work.
- Runtime/Soridormi still own confirmation enforcement, authorization, physical safety,
  preflight, and execution.

This is implementation/source closure only. Current-revision bilingual/provider/simulator
and live evidence remains open.

## Phase 2 documentation convergence

Current documentation now matches the maintained authority line:

- `docs/chromie_mind.md` is rewritten around owner-approved MindProfile context and the
  current Gateway -> GI -> GA/Planner -> Runtime/Evidence loop; deleted conversation/
  capability/deepthinking agents and route hints are no longer described as current.
- The duplicated tail of `docs/CONFIGURATION.md` is removed, retaining one canonical H2
  section for each configuration area.
- `docs/COGNITIVE_TURN_LOOP.md` and `docs/GOAL_DRIVEN_COGNITIVE_ARCHITECTURE.md` no longer
  describe Host speech-only outcome fallback, no-planner response branches, route/intent GI
  branches, or a bounded realizer that owns Planner wording.
- `docs/API_REFERENCE.md` names the current Fast/Deep Planner authority rather than an
  obsolete Agent capability planner.
- `ROADMAP.md` and `docs/STATUS.md` now separate implemented source closure from later
  target qualification and put Phase 4/5/6 in one consistent order after Phase 3 closure.
- `scripts/check_docs.py` rejects duplicate Configuration H2 sections and reviewed stale
  semantic phrases so this drift cannot silently return.

No new architecture document or semantic owner was added.

## Phase 3 WorkDAG / DAGEngine convergence

Chromie-level planned Work now has an explicit execution-only graph boundary:

- Planner is the sole ordinary semantic author and modifier of `WorkDAG` topology.
- `dag_id` remains stable across one coherent line of planned Work; Planner-authored
  semantic changes advance `revision` exactly once and bind `parent_revision`.
- Goal Association never edits a WorkDAG. GA changes canonical Goal continuity; that
  changed Goal truth creates a Planner opportunity. Planner may choose NO_CHANGE by
  retaining/reusing the current WorkDAG Activity, or author the next/new WorkDAG.
- DAGEngine owns only graph validation, ready-node calculation, bounded parallel dispatch,
  dependency/blocked/cancellation state, execution trace, and already-completed-node
  inheritance across a valid next revision. Normal node completion returns to DAGEngine
  and does not pay a Planner round trip.
- Completed/skipped nodes are immutable execution history. The next revision cannot remove
  or rewrite them, and DAGEngine does not dispatch them again.
- `residual_replan`, engine-authored next-action recommendations, and deterministic DAG
  outcome narration are removed. Material failure or changed reality returns facts through
  Evidence to the same Planner.
- Provider-local DAG/controllers such as Soridormi internals remain provider implementation
  details and are not renamed into Chromie WorkDAG.

The current `chromie.work_dag.execute` Capability is an execution boundary for a fully
Planner-authored DAG, not delegation of planning to DAGEngine. A future first-class
`CanonicalPlan.work_dag` representation would be a representation-only change and must
retain the same authority split.

## Repository hygiene after WorkDAG convergence

Phase 4 retains the verified cleanup inventory: orphan legacy-agent prompt assets, dead
`ToolClient`, missing async test dependency, repeated whitespace normalizers, three
JSON-schema/type validator copies, stale naming, and compatibility residue. Consolidate
small deterministic mechanisms; do not create a framework merely to remove duplication.

## Required execution order

1. Execute **Phase 4** repository hygiene and deterministic-mechanism deduplication.
2. Continue **Phase 5** structural simplification only across existing ownership seams.
3. Execute **Phase 6** current-revision qualification and retain bilingual/provider/
   simulator/live evidence.
4. Keep source implementation, automated verification, target validation, and release
   readiness as separate claims.

Detailed phase order and exit criteria live in `ROADMAP.md`; current facts live in
`docs/STATUS.md`.

## Verification for this slice

Phase 3 changes source contracts, DAGEngine mechanics, APIs, tests, and documentation. Run:

```bash
python scripts/check_docs.py
python scripts/check_repository_policies.py
python scripts/semantic_authority_audit.py
python scripts/check_runtime_structure.py
python scripts/check_test_ownership.py
python -m compileall -q agent orchestrator shared scripts tests
```

Also run the Mind/Planner documentation-adjacent focused tests and the canonical
`./scripts/run_tests.sh` in the pinned dependency environment. Do not claim microphone,
audible speaker, GPU/model, MuJoCo, or physical-robot behavior from source/docs tests.
