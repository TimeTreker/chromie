# Chromie Latest Handoff

Audience: coding agent or operator resuming GA global-contract review or deployed-model qualification.
Owner: project owner. Replace this snapshot when `DEVELOPMENT_CHECKPOINT.md` advances.
Authority: operational snapshot only; current source, tests, retained evidence, the
checkpoint, and Issue #34 win.

## Repository state

- Repository: `https://github.com/TimeTreker/chromie.git`
- Delivery branch: `codex/ga-prompt-qualification-1500`
- Pre-delivery base: `main` at
  `7596ee06f693b08918fde99063fbf24018a4e2dc`
- Expected resume revision: latest
  `origin/codex/ga-prompt-qualification-1500` commit containing this handoff and
  `DEVELOPMENT_CHECKPOINT.md`
- Active Issue: [#34](https://github.com/TimeTreker/chromie/issues/34)
- Delivery scope: GA prompt/dynamic-Schema alignment, 1,500-file bilingual corpus,
  deterministic validation/tests, benchmark documentation, and retained evidence
- No provider, model profile, deployment, Runtime switch, Capability, voice, simulator,
  or hardware behavior changed

The local worktree also contains pre-existing, unrelated architecture-diagram work in
`README.md` and `docs/assets/`. Those paths are deliberately excluded from this
delivery commit and remain the project owner's uncommitted work.

## Delivered authority flow

```text
accepted GI Responsibilities + existing/recent Goal candidates
  -> one primary GA invocation
       -> exact dynamic decoder Schema
            modify/clarify must carry structured semantic update
       -> GoalAssociationModelOutput validation
       -> GoalAssociationResolver
  -> canonical Goal continuity -> Planner owns HOW
```

The fix does not add a same-authority repair, reviewer, scorer, or semantic retry.
`reason_summary` stays non-authoritative rationale. The current decision discriminant
is still exclusive: `associate` carries associations and `create_goals` carries new
Goals. It cannot truthfully carry both in one result.

## Material changes

- `agent/app/goal_association_prompt.py`: places modify/clarify structured-update
  requirements next to relationship selection.
- `agent/app/goal_association_schema.py`: exposes the existing DTO/Host update invariant
  at the earliest decoder boundary with conditional JSON Schema.
- `tests/test_goal_association_pr2.py`: rejects a modify association whose meaning is
  present only in `reason_summary` and accepts the structured update.
- `benchmarks/datasets/goal_association_daily_life/`: 1,500 separate scenario JSON
  files plus README, static manifest, validator, and package marker. There is no
  generator or combined scenario file.
- `benchmarks/tests/test_goal_association_daily_life_dataset.py`: checks counts,
  per-file identity/path alignment, manifest digest, references, real Schema, and Host.
- `benchmarks/README.md` and `docs/README.md`: index the new corpus in existing owners.

Repository surface delta for this delivery: 1,505 new tracked files (1,500 scenarios,
four corpus support files, one dataset test) and five existing implementation/test/doc
owners plus the two required delivery owners modified. No environment variable, public
switch, first-class architecture term, compatibility path, or evidence format was added.
Consolidation opportunity: if the global mixed decision is authorized, evolve the existing
GA result discriminant rather than adding a parallel model stage or new association service.

## Actual defect and repaired workflow

| Module/owner | Material input | Baseline actual output | Required/final output | Correlation/judgment |
|---|---|---|---|---|
| Primary GA | Accepted GI refs plus candidate Goals | 36 ordinary modify decisions described the change only in `reason_summary` | Structured, complete Goal update in the same primary decision | Prompt exposed decoder mismatch |
| Dynamic Schema | Exact allowed refs/Goal IDs | Accepted missing update fields | Reject modify/clarify unless structured update exists | Earliest wrong mechanical boundary fixed |
| DTO/Host | Primary structured result | Failed closed on all 36 incomplete updates | Resolve complete update without another LLM call | Correct containment retained |
| Canonical Goal/Planner | Host-accepted continuity | Not invoked for failures | Receives accepted Goal truth; Planner alone authors HOW | Downstream ownership unchanged |

The prompt was not treated as the only cause. The generated Schema contradicted the
already stricter DTO/Host contract, so the fix aligns both earliest input surfaces. No
Host reconstruction or downstream semantic reinterpretation was added.

## Frozen cohort and model identity

- Dataset: `chromie.goal_association_daily_life.v1`
- Cases: 1,500; languages: 750 `en-US`, 750 `zh-CN`
- Contrast construction: 100 semantic seeds × 15 continuity families
- Current-contract references: 1,400
- Known global-contract probes: 100
- Scenario-tree SHA-256:
  `264ca6eb41b15d86f3a9906eeec37576df584b1a7b113c3590f06f3adc39d2ab`
- Model: Codex `gpt-5.6-sol`, reasoning effort `high`, invoked with `codex exec`
- Reference targets were excluded from inference packets
- Changed prompt SHA-256:
  `3d68272a0612a4a7079ba15c272c5ea17d2101bc27e98c6a15975d70628c3a26`
- Changed Schema SHA-256:
  `5162f8d03c74e339eeffec7312cccc3fadcc8da1d07a6bc931224593f96fb482`

## Retained local evidence

Baseline full Codex cohort:

```text
.chromie/benchmarks/goal-association/20260831T023604Z_ga_daily_v1_codex-gpt-5.6-sol/
.chromie/benchmarks/goal-association/20260831T023604Z_ga_daily_v1_codex-gpt-5.6-sol/adjudication-summary.json
```

- 1,364/1,400 current-contract passes
- 36 Host failures, all `modify_active`
- 1,500/1,500 passed the baseline dynamic Schema

Exact focused rerun:

```text
.chromie/benchmarks/goal-association/20260831T045338Z_ga_modify_local_prompt_codex-gpt-5.6-sol/
.chromie/benchmarks/goal-association/20260831T045338Z_ga_modify_local_prompt_codex-gpt-5.6-sol/summary.json
```

- exact baseline failures: 36/36 changed-Schema and Host passes
- contract repair attempts: 0

Full changed-prompt rerun:

```text
.chromie/benchmarks/goal-association/20260831T045812Z_ga_daily_v1_local-prompt-v2_codex-gpt-5.6-sol/
.chromie/benchmarks/goal-association/20260831T045812Z_ga_daily_v1_local-prompt-v2_codex-gpt-5.6-sol/adjudication-summary.json
```

- current-contract cases: 1,400/1,400
- English supported cases: 700/700; Chinese supported cases: 700/700
- changed dynamic Schema: 1,500/1,500
- `modify_active`: 100/100, up from 64/100
- unexpected failures: 0; contract repair attempts: 0
- source stable during the batch
- 100 mixed association-plus-creation probes retain `known_contract_gap`

An early local Gemma run was stopped after the user corrected the inference authority:

```text
.chromie/benchmarks/goal-association/20260831T023009Z_ga_daily_v1_gemma4-12b/
```

It is aborted diagnostic residue only and must never be cited as qualification evidence.
All `.chromie` artifacts are ignored by Git and do not transfer with the push.

## Automated gates

Final observed pre-commit results:

```text
python benchmarks/datasets/goal_association_daily_life/validate.py --json
1,500 validated; 1,400 Host accepted; 100 known contract gaps; 0 errors

python -m pytest -q \
  benchmarks/tests/test_goal_association_daily_life_dataset.py \
  tests/test_goal_association_pr2.py
78 passed

python scripts/check_repository_policies.py
15 rule families, 0 reviewed exceptions; passed

./scripts/run_tests.sh
2,048 main tests and 20 legacy Agent tests; passed

python scripts/check_docs.py
99 Markdown files; passed

git diff --check
passed
```

The first complete gate attempt stopped because `docs/README.md` did not index the new
corpus README. The missing existing-owner index was added; the complete gate was rerun
and passed. No failing gate is hidden.

## Cross-machine resume

```bash
git fetch origin codex/ga-prompt-qualification-1500
git switch codex/ga-prompt-qualification-1500
git pull --ff-only
python scripts/check_repository_policies.py
./scripts/run_tests.sh
python scripts/check_docs.py
python benchmarks/datasets/goal_association_daily_life/validate.py
```

Review Issue #34 before changing the 100 global contract-gap cases. A mixed complete
result must preserve one semantic authority and Responsibility conservation; do not add
a second GA call, split the turn into unrelated authorities, or make Host infer missing
meaning. Obtain explicit project-owner authorization before changing the canonical DTO.

For deployed-provider qualification, retain the exact model digest, transport, strict
decoder, prompt/Schema hashes, parameters, revision, runtime profile, latency, and
GPU/TTS coexistence evidence. Run the complete frozen directory-discovered cohort without
source edits between cases.

## Claim boundary

The local GA prompt/schema is qualified only for the 1,400 cases expressible by the
current contract. No production model/profile, live service, microphone, audible voice,
simulator, target robot, physical safety, or release claim was established. The 100
global mixed-decision cases remain open.
