# Chromie Development Checkpoint

Status: current resume point; incomplete development snapshot
Updated: 2026-08-22
Patch baseline: user-supplied `chromie_2026082206.zip` plus the applied Phase 1C,
Phase 1D, Phase 2, Phase 3, Phase 4, and Phase 5 patches. The archive already contained the user's
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

Phase 5 is source-closed. GA representation/schema/validation and shared/Fast/Deep Planner
validation mechanics are separated without changing semantic owners or retaining compatibility
re-export facades. Host/runtime hotspots were reviewed but not split merely for size; future
extraction still requires a concrete mechanical ownership seam. No Planner, GA reviewer,
reconciliation manager, state store, or response owner was added.

## Required execution order

1. Commit the exact Phase 6 source, start maintained services/Soridormi `sim`, then initialize
   `run_target_evidence_closure.py --profile current_revision_qualification`.
2. Capture the deployed runtime identity and collect the source, interaction-behavior, live
   provider-fault, Gateway/Core, Agent Skill/weather, Social Attention, and LAN tracks.
3. Finalize only on the unchanged clean revision. `target_evidence_closure_eligible=true` is
   the Phase 6 target-evidence exit condition; physical voice/robot remain separate optional
   claims and `release_qualified` remains false.
4. Keep source implementation, automated verification, target validation, and release
   readiness as separate claims. Reopen structural work only for a demonstrated defect or
   ownership seam.

Detailed phase order and exit criteria live in `ROADMAP.md`; current facts live in
`docs/STATUS.md`.

## Phase 6 qualification infrastructure

Phase 6 reuses existing evidence owners rather than creating another benchmark.
`config/source_qualification.json` now retains semantic-authority, focused Phase 1-5
regressions, complete Level-A General Ability, and deterministic provider-fault evidence even
when the optional long full-suite run is being diagnosed separately.

`benchmarks/manifests/target_evidence_closure_v1.json` adds the
`current_revision_qualification` profile. Its required current-revision tracks are source
qualification, Gateway/Core, Agent Skill/weather, eight manifest-owned executed General
Ability cases under full assertions, the live provider fault matrix, Social Attention, and
LAN evidence. General Ability summaries and provider-fault reports now retain explicit
Chromie revision/dirty provenance. The closure rejects preview-only interaction evidence,
local-stub provider faults, dirty reports, or different revisions.

This is qualification **infrastructure**, not a fabricated live result. The operator must run
the profile on the committed target after applying this patch.

## Verification for this slice

Phase 6 changes qualification/evidence plumbing, manifests, provenance, retained scenarios,
tests, and current qualification documentation; it does not change the cognitive authority
backbone. The deterministic/current-source side has been exercised with:

```bash
python scripts/check_docs.py
python scripts/check_repository_policies.py
python scripts/semantic_authority_audit.py
python scripts/check_runtime_structure.py
python scripts/check_test_ownership.py
python scripts/check_runtime_exception_boundaries.py
python scripts/check_host_configuration_ownership.py
python scripts/check_service_configuration_ownership.py
python scripts/runtime_configuration_inventory.py --check
python scripts/general_ability_acceptance.py --mode level-a --no-write
python scripts/provider_fault_matrix.py
python -m compileall -q agent orchestrator shared scripts tests
```

Retained verification in the patch workspace passes `123 tests + 14 subtests`; Level-A
General Ability passes `43/43`, and the deterministic provider-fault matrix passes `16/16`
with safe idle behavior. All listed architecture/documentation/configuration guards pass.
A clean-revision source-qualification run reports no failed gate, but is correctly
`blocked` in this environment because the pinned Ruff and mypy executables are not installed
(and the long full suite was intentionally skipped for that probe). Therefore
`source_qualified=true` is not claimed here.

No Phase 6 target evidence is fabricated by this patch. The committed target still must run
the `current_revision_qualification` profile with executed/full live-text cases, live provider
faults, Gateway/Core, Agent Skill/weather, Social Attention, and LAN evidence on the same clean
revision. Do not claim microphone, audible speaker, GPU/model, MuJoCo, physical-robot, or
`target_evidence_closure_eligible=true` until the corresponding retained artifacts exist.
