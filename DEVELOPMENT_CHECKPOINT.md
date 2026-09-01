# Chromie Development Checkpoint

Status: Goal Association (GA) mixed-result contract is source-closed and a
target-blind same-model qualification workflow is implemented. The first immutable
1,500-case GA baseline scored 1,487/1,500; one clarify-confidence fix passed its
11-case focused cohort, but the changed-prompt full rerun was owner-paused after 75
successful calls and is incomplete. GA prompt quality is therefore not fully
qualified. The completed Fast Planner 1,500-case authoring work remains bundled.

Updated: 2026-09-01

Pre-delivery base: `15d24416e1199833707d549d944651d50c0440cd`

Expected resume: the latest delivery commit containing this checkpoint and
`HANDOFF.md` on `codex/ga-prompt-qualification-paused-20260901`.

Remote divergence: `origin/codex/ga-prompt-qualification-1500` advanced to
`0f525f3a` while this worktree was based on `15d24416`. It was not merged, rebased,
or force-pushed; integrate the two delivered lines explicitly before returning to
the original branch.

Active Issue: [#35 — Fast/Deep Planner prompt qualification and optimization](https://github.com/TimeTreker/chromie/issues/35)

Owner-authorized interruption: Issue #35 remains paused while the retained Issue
#34 GA contract/prompt gap is qualified. The owner stopped the second full run and
waived further tests for this delivery on 2026-09-01.

## Stable authority and workflow

GA owns canonical Goal identity and continuity, not Planner HOW. One candidate-aware
primary result may associate existing Goals and create independent Goals together.
Every admitted GI Responsibility must appear exactly once across the union of
`associations[]` and `new_goals[]`. The no-candidate segmentation variant retains its
fixed `decision=create_goals` wire shape.

Planner remains the sole HOW authority. The GA qualification path is:

```text
frozen production-shaped request
  -> exact production GA system/user prompt + runtime dynamic Schema
  -> one target-blind Codex primary call
  -> optional single mechanical DTO repair only when the real resolver requests it
  -> Schema + DTO + resolver/Host conservation
  -> hidden Responsibility-map adjudication
```

The Codex runner is a same-model, non-independent offline surrogate. It is not the
deployed Ollama constrained-decoding transport and cannot establish live behavior.

## Implemented worktree scope

- Removed the candidate-aware exclusive `decision` discriminant and inactive-branch
  deletion; prompt, DTO, dynamic Schema, resolver, and Host conservation now admit
  association plus creation in one result.
- Migrated the frozen GA wire oracle and made all 100 historical mixed-result cases
  acceptable. Exact Responsibility ownership is still fail-closed.
- Added `benchmarks/datasets/goal_association_daily_life/qualification.py` to freeze,
  execute, retain, and adjudicate target-blind GA batches with bound source, corpus,
  prompt, Schema, model, and harness identities. `--only-case` supports focused proof.
- Diagnosed 11 baseline clarify failures at the earliest prompt boundary: confidence
  ambiguously mixed Goal-continuity certainty with unresolved Planner input gaps.
  The prompt now separates those concepts and keeps `resolved_gap_ids` empty unless
  resolution is proved.
- Corrected all 100 `clarify_open_gap` reference oracles, which had claimed that an
  unspecified detail resolved a gap. The current GA scenario-tree digest is
  `e13861a0a5d963f5f2bb86353c63d6ecd7806128b429a2b4212111f0331023d0`.
- Retained two unresolved baseline `supersede_existing` misses where explicit
  replacement created the new Goal but omitted `supersedes_goal_ids`.
- Retained the Fast Planner corpus: 1,500 directly authored scenarios, 150 bilingual
  contrast sets, manifest digest
  `f9ef6c1269921c2910285a586c3c4b2725744b6dc4406e0e9be759f512738fc8`,
  and no independent semantic-review or training promotion.

Net permanent file growth from the pre-delivery base is 1,493 paths: 1,492 Fast
Planner corpus/harness paths plus the GA qualification runner. Existing production,
test, corpus, method, roadmap, checkpoint, and handoff owners were updated in place.
No environment variable, runtime switch, compatibility path, model change, semantic
authority, standalone design document, or architectural term was added.

## Evidence ledger

| Evidence | Observed result | Qualification limit |
|---|---|---|
| GA reference replay after final oracle correction | 1,500/1,500 Schema/DTO/resolver/Host accepted; digest `e13861a...023d0` | Mechanical Level A; not candidate inference |
| First immutable target-blind baseline | 1,500/1,500 calls completed; 1,487 strict passes, 13 failures; zero repairs/timeouts | Same-model offline surrogate on the pre-confidence-fix prompt/oracle |
| Baseline failure clusters | `clarify_open_gap` 89/100 and `supersede_existing` 98/100; every other category 100/100, including mixed results | Hidden-oracle adjudication; non-independent |
| Clarify focused rerun | Original 11 clarify failures: 11/11 strict pass; zero repairs/timeouts; source stable | Focused mechanism proof only |
| Changed-prompt full rerun | Owner-paused at 75/1,500 successful primary call records; no timeout/nonzero record; no adjudication or terminal source-stability record | Incomplete batch; no revision-level pass claim |
| Latest focused corpus tests | GA benchmark module: 6 passed; selected GA benchmark/contract checks: 8 passed, 74 deselected | Focused only |
| Earlier canonical local gate | `./scripts/run_tests.sh` passed before the qualification runner, oracle correction, and confidence prompt edit | Does not qualify the delivered tree |
| Delivery validation | Not run after the final changes, per owner instruction | Current delivered tree is intentionally untested beyond the focused evidence above |
| Fast corpus mechanical evidence | 1,500/1,500 exact production-transaction validations and four focused corpus tests passed earlier | No candidate inference or independent semantic truth |

Retained ignored evidence paths and exact identities are in `HANDOFF.md`.

## Ordered resume work

1. Fetch both remote branches and explicitly integrate the safe delivery branch with
   `origin/codex/ga-prompt-qualification-1500` at `0f525f3a`; do not force-push or
   treat either divergent snapshot as disposable.
2. Preserve the paused 75-call directory as an incomplete artifact. Prepare a fresh
   immutable 1,500-case batch on the integrated current tree, run it without edits,
   and adjudicate the whole cohort.
3. Verify that clarify has no full-cohort regression. If the two supersede misses
   remain, diagnose that cluster, make one minimal authority-preserving fix, run its
   focused cohort, then another complete frozen cohort.
4. Run the applicable General Ability classes and canonical repository gates that
   were explicitly waived for this delivery; record failures rather than inheriting
   the earlier green gate.
5. Resume Issue #35: independently review Fast scenarios, promote only accepted
   cases, run one immutable target-blind Fast baseline, adjudicate by earliest shared
   boundary, and qualify Deep separately.

## Claim boundary

This checkpoint establishes GA mixed-result source closure, a reproducible
target-blind qualification workflow, a 1,487/1,500 baseline diagnosis, and focused
11/11 evidence for the confidence fix. It does not establish that the current GA
prompt is good enough: its full changed-prompt cohort is incomplete and the two
supersede misses are unresolved. It establishes no deployed provider/model quality,
independent review, training readiness, service, voice, simulator, hardware,
physical-safety, release, or robot-behavior evidence.
