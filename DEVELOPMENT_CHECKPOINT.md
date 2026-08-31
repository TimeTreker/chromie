# Chromie Development Checkpoint

Status: Fast Planner prompt qualification authoring checkpoint is incomplete; 10 of
the intended 1,000 model-authored scenarios are tracked, the corpus is not frozen,
and no current-tree qualification or optimization claim exists

Updated: 2026-08-31

Pre-delivery baseline: `codex/ga-prompt-qualification-1500` at
`ac83e4677d67014f3d547823d9568abf95c09834`

Expected resume revision: latest
`origin/codex/ga-prompt-qualification-1500` commit containing this checkpoint and
`HANDOFF.md`

Active Issue: [#35 — Fast/Deep Planner prompt qualification and optimization](https://github.com/TimeTreker/chromie/issues/35)

## Stable authority boundary

Planner owns HOW: complete per-Goal Activity planning, Capability and argument
selection, parameter provenance, ordering/concurrency, exact Communicative Acts,
truth/Evidence scope, satisfaction, and bounded revision. Fast and Deep are depth
passes of that one authority.

Planner must not reinterpret GI-owned WHAT, commit GA-owned Goal continuity,
authorize its own effects, invent Runtime/Evidence truth, or use Fast/Deep as mutual
reviewers or semantic repair calls. Identity, worldview, values, and stable Mind were
not changed.

The production transaction under qualification remains:

```text
accepted GI Responsibilities + exact source provenance
  + GA Goals / current Plan and Work / Evidence / Situation / re-entry scope
  + Capability and Agent Skill projections / safety and resource state
  -> global truth projection + Planner-local prompt
  -> runtime-variant dynamic Schema
  -> one declared Fast Planner call
  -> stream parser or canonical DTO parser
  -> deterministic Planner and Host validation
  -> accepted presentation/Plan, Deep delegation for genuine complex HOW, or fail closed
```

Fast variants in scope are `streaming_advance`, `canonical_primary`, and
`canonical_reentry`. Deep qualification has not started.

## Implemented checkpoint scope

- Added an in-progress Fast Planner daily-life work area with a catalog fixture and
  qualification/validation harness scaffolding.
- Added 10 independently reviewable `streaming_advance` direct-conversation probes:
  five family/home conditions paired in `en-US` and `zh-CN`. They were authored in
  one retained `gpt-5.6-sol` high-reasoning call, not by a scenario generator.
- Kept targets and semantic review material outside the candidate-input portion of
  each scenario and marked every tracked probe non-independent and
  `training_eligible=false`.
- Indexed the work area in existing benchmark/documentation owners.
- Removed the premature 1,000-case completion test and corrected documentation that
  had described the unfinished corpus as frozen and complete.
- Stopped the interrupted background authoring process. Seventy-eight additional
  completed model-call envelopes remain ignored local material; they are not
  reviewed, split into tracked scenario files, frozen, validated, or transferred by
  Git.
- No production Planner prompt, context projection, DTO, Schema, validator, Host
  workflow, model profile, or runtime architecture was changed.

Tracked project surface grows by 15 files under
`benchmarks/datasets/fast_planner_daily_life/` (10 scenarios and five support
files) and updates two existing indexes plus the two required delivery owners. No
environment variable, runtime switch, compatibility path, semantic authority, or
architectural term was added. The intended consolidation point is the existing
cross-role qualification method and existing Planner owners; do not add a parallel
reviewer or benchmark framework.

## Evidence ledger

| Evidence | Result | Qualification limit |
|---|---|---|
| Retained probe authoring | One `gpt-5.6-sol` high-reasoning envelope materialized as 10 tracked bilingual scenarios | Model-authored candidate material only; no independent review or current-tree validation |
| Interrupted authoring batch | 78 additional completed envelopes retained locally; 21 assigned calls did not complete before the batch was stopped | Incomplete authoring output only; no aggregate execution record, review, manifest, or Git transfer |
| Current tracked corpus | 10/1,000 intended cases; no `dataset.json` manifest or scenario-tree digest | Not frozen and not runnable as a qualification cohort |
| Earlier script-generated corpus check | A discarded script-generated corpus previously reached a local validator and 3-test pass, then was removed from the tracked work after the owner rejected script-generated semantics | Invalidated and must not be cited for the current model-authored corpus |
| Current final tree tests and gates | Not run at the owner's explicit request | Source, docs, harness, corpus, and behavior are unverified on this checkpoint |
| Baseline inference/adjudication | Not run | No prompt, contract, workflow, architecture, or model diagnosis exists yet |

## Ordered resume work

1. On the same machine, review the retained authoring contract, the tracked 10-case
   contrast set, and each completed envelope under
   `.chromie/benchmarks/fast-planner/llm-authoring-v1/`. Reject semantic repetition,
   malformed production inputs, oracle leakage, or authority drift before tracking
   any additional case.
2. Complete the missing model-authored contrast sets with direct LLM authorship; do
   not use a script or semantic template to generate scenarios. Mechanical tooling
   may only retain and split accepted model output unchanged.
3. Materialize exactly one reviewed scenario per file, keep whole contrast sets in
   one split, then create `dataset.json` with final counts, provenance, coverage,
   and deterministic tree digest. Add the completion/contract test only after the
   corpus actually satisfies it.
4. Validate every reference through the exact production prompt, runtime-variant
   dynamic Schema, DTO, and Host boundary. Fix scenario or harness defects before
   freezing.
5. Freeze source/corpus/prompt/Schema/model identities and run one immutable,
   target-blind Fast baseline without edits between cases. Adjudicate every case and
   cluster failures by earliest boundary.
6. Only then make one evidenced minimal workflow, contract, architecture, prompt,
   context, provider/profile, model, or oracle fix. Run the focused failure cohort,
   the full frozen Fast cohort, applicable ability class, and canonical gates.
7. Qualify Deep complex/blocked/degraded/unsafe/revision paths separately, then rerun
   both Fast and Deep cohorts before any Planner-level claim.

## Claim boundary

This commit is a recoverable work-in-progress checkpoint, not a qualification
delivery. Fast Planner workflow, contract, architecture, prompt, model quality, and
behavior remain unqualified. No production model/profile was promoted, no user-visible
behavior was changed, and no live service, voice, simulator, robot, physical safety,
or release evidence was established.
