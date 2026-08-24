# Chromie Development Checkpoint

Status: current resume point; audit remediation in progress
Updated: 2026-08-24
Remote baseline: `47dbfbcc22eb8d008af1b31d414d17d64b080c4f` (`Restore cognitive authority boundaries`)
Archive baseline: user-supplied `chromie_20260825.zip`, verified against the same current source shape.

## Read first

Canonical owners remain [Project Charter](docs/PROJECT_CHARTER.md),
[Goal-Driven Cognitive Architecture](docs/GOAL_DRIVEN_COGNITIVE_ARCHITECTURE.md),
[Human-Like Interaction Contract](docs/HUMAN_LIKE_INTERACTION_CONTRACT.md),
[Current Status](docs/STATUS.md), [Roadmap](ROADMAP.md), and
[Acceptance](docs/ACCEPTANCE.md). Source, tests, and executable evidence win over stale prose.

This checkpoint supersedes the August 22 Phase-6-only resume note. Four later audit-remediation
commits changed the cognitive boundary after that note, so Git history plus current source is the
resume authority.

## Current architecture boundary

```text
person -> Gateway -> Goal Interpretation -> Responsibility / WHAT
                                      |-> Goal Association -> canonical Goal continuity
                                      `-> Planner fast/deep -> HOW / Communicative + effectful Activities
                                                           -> optional WorkDAG
                                                           -> Runtime -> Provider -> Evidence
Goal + Responsibility + Situation + Work + Evidence
                                      -> CognitiveOpportunity -> same Planner
                                      -> 0..N Activity changes or none
```

- Goal Interpretation owns provider-neutral WHAT only.
- Goal Association owns canonical Goal identity, semantic bindings, and continuity only.
- Fast/Deep are cognition depths of one Planner authority; Planner owns HOW and ordinary speech.
- Runtime/Providers own execution facts; Evidence is trusted truth, not semantic interpretation.
- Social Attention is optional subordinate expression and never Goal completion authority.

## Last committed checkpoint

`47dbfbcc` correctly removed work/fresh-evidence readiness flags from Goal Interpretation,
introduced provider-neutral `information` and `stateful_effect`, moved the first Communicative
Activity to Fast Planner, removed confidence-only depth gates, and returned Reflection to an
internal evidence-bound advisory path.

The subsequent P3 audit found that this boundary was not yet end-to-end: Goal Association still
translated `information` and `stateful_effect` into the old `capability_work` execution category,
then persisted `responsibility_kind`, `execution_lane`, and `provider_required`. Planner/runtime
code still consumed some of those projections. That recreated HOW inside Goal Association and
made stateful Goals vulnerable to information-only Capability filtering.

## P3 source corrections in this patch

1. **Canonical WHAT survives Goal Association unchanged.** Goal Association accepts and persists
   `information` / `stateful_effect` directly and no longer derives or stores execution kind,
   execution lane, provider requirement, or `capability_work`.
2. **Planner is the first HOW owner.** Shared Planner context derives only the mechanical decoder
   constraints that follow from WHAT. `stateful_effect` cannot be completed by immediate text;
   `information` remains context-sensitive and may either be answered from trusted state/Evidence
   or require exact information Work.
3. **Information evidence remains fail-closed.** A typed information
   `resource_responsibility` is treated as acquisition/delivery semantics. A factual response for
   it requires trusted terminal/retrieved evidence or already evidence-bound dialogue; model
   memory and index metadata alone are not evidence.
4. **Capability applicability is typed, not lane-derived.** Information, body, media, vocal, and
   stateful applicability comes from canonical WHAT plus advertised semantic scope. Runtime
   execution lanes remain properties of selected Capability/Activity realization, not Goals.
5. **No legacy bridge remains in maintained cognition.** Goal Interpreter continuity no longer
   converts old `capability_work` Goals, Agent Skills advertise `information`, and current API /
   architecture / execution-lane docs describe the same contract.
6. **Host structure ratchet is restored.** The remote baseline had `108` `VoiceAssistant` methods
   against a maximum of `105`. Fresh capability-state projection now lives in the existing pure
   Planner re-entry policy module; restart revalidation uses one Host orchestration method and the
   run lifecycle schedules it directly. The structural check returns to `105` methods.

## Verification expected before the next checkpoint

Run at minimum:

```bash
python scripts/check_docs.py
python scripts/check_repository_policies.py
python scripts/semantic_authority_audit.py
python scripts/check_runtime_structure.py
python scripts/check_test_ownership.py
python scripts/check_runtime_exception_boundaries.py
python -m compileall -q agent orchestrator shared scripts tests
pytest -q
```

Current-revision target qualification remains a separate claim. Do not treat deterministic source
closure as proof of live bilingual behavior, provider fault handling, GPU/model quality, MuJoCo,
or physical robot behavior. After P3 source/tests are clean, resume the existing
`current_revision_qualification` evidence profile on the exact committed revision.
