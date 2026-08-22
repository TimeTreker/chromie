# Chromie Development Checkpoint

Status: current resume point; incomplete development snapshot
Updated: 2026-08-22
Patch baseline: user-supplied `chromie_2026082206.zip` plus the applied Phase 1C,
Phase 1D, Phase 2, Phase 3, and Phase 4 patches. The archive already contained the user's
applied Phase 1A/1B state. No archive-wide Git identity is claimed.

## Read first

Canonical owners remain [Project Charter](docs/PROJECT_CHARTER.md),
[Human-Like Interaction Contract](docs/HUMAN_LIKE_INTERACTION_CONTRACT.md),
[Current Status](docs/STATUS.md), [Roadmap](ROADMAP.md), and
[Acceptance](docs/ACCEPTANCE.md). Source and executable evidence win over stale prose.

Current focus: **Phase 6 current-revision qualification**, after source-closing the bounded
Phase 5 structural simplification slice. Do not redesign the Goal-driven backbone, put DAG
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
`planner_schema.py`, shared `planner_validation.py`, pass-specific
`planner_fast_validation.py` / `planner_deep_validation.py`, `planner_fallback.py`,
`planner_audit.py`, and `planner_prompt.py` are implementation layers of that same owner.
Goal Association likewise separates model DTOs (`goal_association_contract.py`), constrained
decoder schemas (`goal_association_schema.py`), deterministic normalization/coverage checks
(`goal_association_validation.py`), and prompt projection (`goal_association_prompt.py`) while
`GoalAssociationResolver` remains the sole continuity transaction.

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

## Prior source closures

- Phase 2 aligned current authority docs with the maintained Goal-driven architecture and
  added documentation anti-drift guards.
- Phase 3 established Planner-authored revisioned WorkDAG plus deterministic DAGEngine; GA
  changes Goal continuity only, completed nodes remain immutable history, and engine-authored
  replanning meaning is removed.
- Phase 4 removed verified orphan/dead artifacts, pinned the async test plugin, consolidated
  shared whitespace/JSON-Schema mechanisms, and removed reviewed compatibility residue.

These phases are source-closed implementation work, not current-revision target qualification.

## Phase 5 structural simplification

Phase 5 is source-closed as a bounded reconstructability slice rather than a line-count campaign:

- `goal_association_contract.py` now owns only GA model DTO/typed representation; constrained
  decoder construction lives in `goal_association_schema.py`, and deterministic normalization,
  grounding/conflict, and coverage mechanics live in `goal_association_validation.py`. The
  Resolver remains the only GA model invocation and Goal-continuity transaction.
- shared Planner contract validation remains in `planner_validation.py`; Fast-specific
  qualification/fail-safe mechanics live in `planner_fast_validation.py`, and Deep-specific
  repair/safety/diagnostic mechanics live in `planner_deep_validation.py`. Fast/Deep Resolver
  method counts and semantic authority are unchanged.
- the former hotspots fall from roughly 4.2K lines in one Planner validation module to a
  2.8K shared core plus bounded pass-specific layers, and from roughly 2.9K lines in one GA
  contract module to three roughly 1K-line representation/schema/validation layers. No
  compatibility re-export facade is retained.
- the Host/runtime hotspots were reviewed but not split merely for size: the remaining large
  `VoiceAssistant`, Conversation State, Cognitive Runtime, and Capability Runtime methods own
  real lifecycle/state/runtime transactions. Future extraction still requires a concrete
  mechanical ownership seam; file or method count alone is not sufficient.

This slice adds no Planner, GA reviewer, reconciliation manager, state store, or response owner.

## Required execution order

1. Execute **Phase 6** current-revision qualification and retain bilingual/provider/
   simulator/live evidence.
2. Keep source implementation, automated verification, target validation, and release
   readiness as separate claims.
3. Reopen structural work only for a demonstrated concrete ownership seam or defect; do not
   resume decomposition merely because a file remains large.

Detailed phase order and exit criteria live in `ROADMAP.md`; current facts live in
`docs/STATUS.md`.

## Verification for this slice

Phase 5 changes only Planner/GA mechanical module ownership, imports, tests, and current architecture documentation. Run:

```bash
python scripts/check_docs.py
python scripts/check_repository_policies.py
python scripts/semantic_authority_audit.py
python scripts/check_runtime_structure.py
python scripts/check_test_ownership.py
python -m compileall -q agent orchestrator shared scripts tests
```

Retained source verification for this slice: the focused Planner/GA contract set passes
`397 tests + 13 subtests`; the broader Planner/GA/Cognitive Runtime plus Agent set passes
`427 tests + 5 subtests`; all listed architecture/configuration guards pass. A larger
`tests + agent/tests` run reached about 61% with no failure before the current execution
window expired. `./scripts/run_tests.sh` still stops at the environment's missing pinned
Ruff executable, so canonical full-suite completion is not claimed here. Do not claim
microphone, audible speaker, GPU/model, MuJoCo, or physical-robot behavior from source tests.
