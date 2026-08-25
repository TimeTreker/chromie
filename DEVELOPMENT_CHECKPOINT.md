# Chromie Development Checkpoint

Status: current resume point; owner-approved Continuous Mind runtime closure in progress
Updated: 2026-08-25
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

## Audit continuation Patch 1 — topics 1–5

Source support for the first five remaining audit topics is now explicit rather than implied by
a generic live-text pass:

1. `current_revision_qualification` requires one clean revision and exact retained track/case
   coverage.
2. `human_like_cognitive_continuity` measures retained follow-up meaning and rejects exact
   repeated assistant speech on a new turn.
3. `planner_goal_semantic_quality` measures WHAT/continuity/HOW separation with an
   evidence-backed information probe.
4. `workdag_multi_goal_revision_integrity` measures two independent body effects exactly once
   and a follow-up revision that must not replay completed locomotion.
5. `continuous_cognition_recovery` requires evidence-bound Planner re-entry and pins provider
   fault / continuous-cognition source regressions.

These are qualification mechanisms, not fabricated qualification evidence. The topics close only
when a clean committed revision produces an eligible current-revision target bundle.

## Audit continuation Patch 2 — topics 6–10

The next five audit topics are now represented by explicit source/qualification boundaries:

6. `situation_revision` accepts only a typed trusted observation and wakes cognition only for a new Situation digest.
7. `time_condition` uses a durable Goal/Plan-bound structured condition owned by ConversationState; stale conditions fail closed and due conditions emit once. Host never parses a Goal sentence into a deadline.
8. Cognitive Gateway broad fixed-reflex reconciliation is covered by a real multi-Goal global-emergency regression proving every selected Goal/request binding is reconciled.
9. Social Attention target review now explicitly requires subordinate-only expression, no duplicate primary Activity, and fail-soft resource/provider conflict behavior in addition to non-blocking primary work.
10. Current-revision interaction qualification now includes Chinese and English identity turns with backend-leakage guards and the maintained warm Fast-Planner/playback-start budgets.

These mechanisms do not fabricate live evidence. Situation/time producers still need real source episodes, Social Attention still needs human-reviewed target evidence, and speech latency remains an injected-text scheduling claim unless physical voice evidence is separately retained.


## Audit continuation Patch 3 — topics 11–15

The final five source/audit topics are now closed without adding speculative cognitive owners:

11. Epistemic Qualification has executable regressions for freshness, contradiction, independent trust domains, and closed-world negative claims; absence cannot establish a negative claim without complete declared collection coverage.
12. Reflection/forward adaptation remains evidence-bound and ephemeral: task/session lessons can appear in later same-session context, but clear at the conversation boundary, never enter durable profile memory through Reflection, and cannot request Stable Mind/system mutation.
13. Deferred cognition features now have an admission rule in the Charter. Affect simulation, ambient autonomy, multi-user identity, broader autonomy, competence calibration, and similar machinery require an originating episode, authority/irreducibility review, and qualification plan before any production runtime switch is introduced. A repository regression guards the current deferred boundary.
14. Static-analysis maintenance widens incrementally rather than by declaration: `scripts/run_mypy.py` is now covered by both the Ruff and Mypy ratchets while the `VoiceAssistant` structural ceiling remains unchanged.
15. Physical-robot evidence remains optional for `current_revision_qualification`, while the supervised physical-pilot path remains fail-closed: exact Chromie revision, source-clean/provider-bound evidence, safe state before/after, and a named safety operator are required before the claim can be attached.

Patch 3 closed the then-known semantic-authority audit line. The 2026-08-25 full project audit subsequently found a narrower but real mismatch: canonical Continuous Mind design already described Situation/time-driven re-entry, while production wiring existed mainly for user turns, Runtime/Provider outcomes, and provider-state changes. The owner explicitly approved closing those verified implementation gaps in architecture-to-detail order before the next full current-revision qualification. This supersedes the earlier Phase-6-only scheduling sentence without reopening the settled WHAT/HOW authority architecture.

## Continuous Mind runtime closure — Patch 4 / first architecture slice

This patch closes the **wake/re-entry substrate** before adding richer Situation or Memory behavior:

1. Structured due `GoalTimeCondition` records are now consumed by a production mechanical wall-clock wake loop. The loop does no semantic interpretation and invokes no model until an already-structured condition becomes due.
2. Due-time wake re-enters the same Planner from exact retained Goal/current-Plan/original Responsibility provenance. It does not fabricate a UserTurn, Responsibility, response, or Capability decision.
3. Generic Planner state re-entry no longer assumes every meaningful trigger is Evidence. A due clock condition can carry zero Evidence refs and therefore cannot mark Planner speech as `post_evidence`; Evidence-bearing Runtime/Situation paths keep their existing truth semantics.
4. The long-lived mechanical wake task reuses the existing detached Runtime-state task lifecycle and is explicitly cancelled during shutdown rather than creating another Mind manager or Host state owner.
5. Status/architecture/acceptance prose now distinguishes implementation from qualification. Trusted live `SituationRevisionObservation` ingress and Planner-authored time-condition registration remain **implementation work**, not target-evidence gaps.
## Continuous Mind runtime closure — Patch 5 / Situation architecture slice

The second architecture slice closes the first real live Situation path without introducing a world-model service or a new semantic authority:

1. `SituationProjection` v3 is now a bounded **current interpretation**, not only a working-set/reference index. It may carry small revisable `SituationInterpretation` tuples (`subject_ref`, relation, value, epistemic status, relevant Goals) plus exact authority-owned `SituationSourceRef` provenance; source payloads remain outside Situation.
2. Evidence and live state are no longer conflated inside Situation provenance. `SituationSourceRef.kind=evidence` identifies retained Evidence; `kind=runtime_state` identifies independently trusted current provider state. Live Runtime state does not gain Evidence authority merely because it can wake cognition.
3. Meaningful provider progress (blocked/waiting/degraded/paused/recovering, material phase/member-state changes) is the first production trusted Situation ingress. It becomes a typed `SituationRevisionObservation`, changes the Situation digest, and may raise a `situation_revision` CognitiveOpportunity for the same Planner. Heartbeat/percentage churn remains filtered before ingress.
4. Planner state re-entry now verifies that any CognitiveOpportunity carrying a `situation_digest` is paired with the exact validated Situation projection and bound Goal set. A callback cannot substitute a different live interpretation.
5. Provider-state re-entry, including restart catalog revalidation, no longer fabricates `evidence_ref` provenance or accidentally qualify speech as `post_evidence`. Terminal execution/result observations retain the separate Evidence path.
6. This is intentionally **not** full scene/body/world-model closure. Generic trusted camera/scene/body/environment source adapters remain to be implemented only when a source can state its own bounded authority contract; Situation must not infer those facts from desired Goals or Plans.

Planner-authored time readiness, selective Situation re-entry, current-context Memory activation, and bounded Planner-authored information-acquisition expectations are source-closed without new semantic managers. The binding next order is now: (a) mechanically simplify oversized coordinators and stale/compatibility surfaces without moving authority, then (b) run full current-revision qualification on the exact committed tree.
