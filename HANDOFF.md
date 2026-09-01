# Chromie Latest Handoff

Audience: coding agent integrating the paused Goal Association qualification
delivery, completing its frozen cohort, then resuming Issue #35 Fast/Deep Planner
qualification.

Owner: project owner. Replace this volatile snapshot when the checkpoint advances.
Current source, tests, retained artifacts, `DEVELOPMENT_CHECKPOINT.md`, and the
active Issue win over chat history.

## Repository and delivery state

- Repository: `https://github.com/TimeTreker/chromie.git`
- Delivery branch: `codex/ga-prompt-qualification-paused-20260901`
- Intended remote ref: `origin/codex/ga-prompt-qualification-paused-20260901`
- Pre-delivery base: `15d24416e1199833707d549d944651d50c0440cd`
- Original branch: `codex/ga-prompt-qualification-1500`
- Original upstream advanced independently to `0f525f3a` (`benchmarks: freeze Fast
  Planner qualification corpus`), one commit ahead of the local base.
- No merge, rebase, history rewrite, or force-push was performed. The safe branch
  preserves this worktree so the two lines can be integrated deliberately.
- Expected resume revision: the latest commit on the delivery branch containing both
  this file and `DEVELOPMENT_CHECKPOINT.md`.
- Active Issue: [#35](https://github.com/TimeTreker/chromie/issues/35), paused for the
  owner-authorized Issue #34 GA qualification line.
- Owner instruction at delivery: interrupt the second full GA run, do not run more
  tests, commit, and place the snapshot in the remote repository.

## Material delivered scope

The worktree combines two already-related lines:

1. The complete Fast Planner authoring/harness snapshot: 1,500 scenarios in 150
   bilingual contrast sets; manifest digest
   `f9ef6c1269921c2910285a586c3c4b2725744b6dc4406e0e9be759f512738fc8`.
   Every scenario remains `independent_semantic_review=false` and
   `training_eligible=false`.
2. GA mixed association-plus-creation contract closure plus target-blind prompt
   qualification. Candidate-aware `associations[]` and `new_goals[]` are
   non-exclusive and exactly conserve all request-bound GI Responsibilities.

GA changes are owned by the existing production files under `agent/app/`, the
existing frozen corpus, its tests/docs, and the new
`benchmarks/datasets/goal_association_daily_life/qualification.py` runner. No model,
provider/profile, runtime stage, semantic authority, configuration key, compatibility
path, or production Planner behavior was added.

## Actual GA workflow and diagnosis

```text
GI Responsibilities and retained Goal candidates (correct)
  -> production GA prompt + candidate-aware dynamic Schema
  -> one target-blind primary model result
  -> Schema / DTO / resolver / canonical Host conservation
  -> hidden Responsibility-map adjudication
```

The earlier contract failed before model quality could be judged because an exclusive
candidate-aware `decision` and DTO branch deletion could erase a valid mixed result.
That earliest boundary is repaired: one result can associate and create, and the Host
still rejects missing or duplicate Responsibility ownership before mutation.

The first full candidate run then exposed two semantic clusters:

| Cluster | Actual output | Expected contract | Earliest boundary | State |
|---|---|---|---|---|
| 11 `clarify_open_gap` cases | Correct clarify target and unresolved gap, but confidence 0.62/0.64 caused Host fail-closed | Goal-continuity confidence should stay high when ownership is explicit; unresolved Planner input remains unresolved | Prompt conflated Goal ownership certainty with executability/gap resolution; corpus oracle also falsely marked unspecified details resolved | Prompt and all 100 clarify oracles corrected; original 11 cases passed focused rerun |
| 2 `supersede_existing` cases | Created replacement Goal but omitted `supersedes_goal_ids` | Explicit “forget original; do X instead” must retain supersession linkage | Compact prompt guidance remains insufficient or ambiguous | Open; no fix attempted before owner pause |

The confidence fix says association confidence measures Goal ownership/continuity,
not Planner gap resolution or Goal executability. It also requires
`resolved_gap_ids=[]` when resolution is unproved. Current GA scenario-tree digest:
`e13861a0a5d963f5f2bb86353c63d6ecd7806128b429a2b4212111f0331023d0`.

## Retained GA artifacts

All paths below are ignored, machine-local evidence and are not transported by Git.

### First complete immutable baseline

`.chromie/benchmarks/goal-association/20260901T100547Z-baseline/`

- Label: `codex-ga-mixed-contract-baseline`
- Model/profile: `gpt-5.6-sol`, high reasoning, concurrency 8, no retry
- Corpus digest: `33f9f8b3dbad81b2bbd33f2bc990881b104c15a9a4a832f8d3f322bc9dc7c8ba`
- Prompt identity index: `fc883192bb6757eb98569d5d4807903cda35882cb171b205df49e4e492fdbc47`
- Production files hash: `67368801e6e45df12227f43a629372304da4bdaa2478a67c2f96738707b8cd9e`
- Production dirty diff hash: `307e60ac7a0a81a4c9ceec058de89cf97541c347bbc0e45de6fee176aeff96fc`
- Result: 1,500 primary successes, zero timeout/repair; 1,487 strict passes,
  13 failures; source/harness stable.
- Adjudication: `adjudication-summary.json`.

### Focused clarify proof

`.chromie/benchmarks/goal-association/20260901T113638Z-clarify-focused/`

- Label: `clarify-confidence-focused`
- Selected cases: the original 11 clarify failures
- Corpus digest: `e13861a0a5d963f5f2bb86353c63d6ecd7806128b429a2b4212111f0331023d0`
- Prompt identity index: `b48ba5fb7abfa02767ca005fad3eb787ea702385277fcf6704a2826d8b4a42ad`
- Production files hash: `5ee24135e3d51d67aec780573749d441e401c8877e877d2b9a3867cf7be4a753`
- Production dirty diff hash: `990d6833aa445549ec305dffed1f9e7a18f6751b2f7204a2d3708b76d1badb97`
- Result: 11/11 strict pass, zero timeout/repair, source stable.

### Owner-paused full rerun — incomplete

`.chromie/benchmarks/goal-association/20260901T113813Z-clarify-full/`

- Label: `clarify-confidence-full-rerun`
- Frozen selection: full 1,500-case corpus
- Prompt identity index: `babba229aa5b13f87e7ac8b11559faa572a66b53190915f23240d725d3cd7b53`
- Corpus/source/diff identities match the focused run above.
- Harness hashes: qualification
  `eef575083d042326403d4ba0a673551929f6118b80541562977a0bac2ef8eb12`,
  reference validator
  `6e338511caec361b1f61806f096a21166112bbb75b90538b387aef7dba9b0742`.
- At interruption: 75 call-execution records, all exit 0 and non-timeout; 1,425
  scenarios were not run.
- There is no `source-stability.json` and no adjudication summary. Never resume or
  describe this directory as a complete immutable cohort.
- The process and its Codex children were confirmed stopped.

Fast authoring evidence remains under
`.chromie/benchmarks/fast-planner/llm-authoring-v2/` with the previously retained
213 invocation records. It is also local-only.

## Validation ledger

Observed after the mixed contract and before/through the clarify change:

```text
python benchmarks/datasets/goal_association_daily_life/validate.py --json
# 1,500/1,500 Host accepted after final clarify-oracle correction;
# digest e13861a0a5d963f5f2bb86353c63d6ecd7806128b429a2b4212111f0331023d0

python -m pytest -q benchmarks/tests/test_goal_association_daily_life_dataset.py
# 6 passed

# A selected focused GA benchmark/contract invocation also reported:
# 8 passed, 74 deselected
```

Earlier, before adding the qualification runner and the final confidence/oracle edit:

```text
./scripts/run_tests.sh
# exit 0; included 132 passed, Ran 2050 tests ... OK,
# and 20 legacy Agent tests passed

python scripts/check_repository_policies.py
# passed 15 rule families, 0 exceptions

python scripts/check_docs.py
# passed 102 Markdown files

python scripts/check_test_ownership.py
# passed
```

Those earlier gates do not qualify this delivered tree. Per the owner's explicit
instruction, no policy, documentation, ownership, focused, full, or canonical test
was run after the final handoff edits. Record this delivery as untested at its final
revision, not green by inheritance.

## Resume commands

First integrate without rewriting either remote line:

```bash
git fetch origin
git switch codex/ga-prompt-qualification-paused-20260901
git log --left-right --oneline \
  origin/codex/ga-prompt-qualification-1500...HEAD
git diff --stat origin/codex/ga-prompt-qualification-1500...HEAD
```

Choose and review a normal merge/cherry-pick integration only after inspecting the
overlap. Do not force-push. The original remote tip to preserve is `0f525f3a`.

After integration, do not continue the paused directory. Freeze a fresh full run:

```bash
RUN_DIR=.chromie/benchmarks/goal-association/NEW_RUN_ID
python -m benchmarks.datasets.goal_association_daily_life.qualification prepare \
  --label post-clarify-full \
  --model gpt-5.6-sol \
  --reasoning-effort high \
  --output-dir "$RUN_DIR"
python -m benchmarks.datasets.goal_association_daily_life.qualification run \
  --concurrency 8 \
  --output-dir "$RUN_DIR"
python -m benchmarks.datasets.goal_association_daily_life.qualification adjudicate \
  --output-dir "$RUN_DIR"
```

Adjudicate all 1,500 cases before a prompt claim. If supersede failures remain,
retain their exact outputs, fix only the earliest responsible authority boundary,
run a focused `--only-case` batch, then run another fresh complete cohort. Finally
run the applicable General Ability classes and canonical required checks.

## Claim boundary

The GA prompt itself is not yet “good enough.” The delivered evidence establishes
mixed-result contract closure, a complete 1,487/1,500 baseline, and focused 11/11
clarify repair evidence. The final full rerun is incomplete and two supersession
misses remain open. There is no current-revision full-gate, deployed Ollama/model,
independent-review, training-readiness, service, voice, simulator, hardware, safety,
release, or physical-robot proof.
