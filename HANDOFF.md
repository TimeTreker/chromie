# Chromie Latest Handoff

Audience: coding agent beginning Fast/Deep Planner prompt qualification, or operator resuming GA global-contract/deployed-model review.
Owner: project owner. Replace this snapshot when `DEVELOPMENT_CHECKPOINT.md` advances.
Authority: operational snapshot only; current source, tests, retained evidence, the
checkpoint, and Issue #34 win.

## Repository state

- Repository: `https://github.com/TimeTreker/chromie.git`
- Integration parents: `codex/ga-prompt-qualification-1500` at `ac83e467` and
  `origin/main` at `f3d14792`
- Expected resume revision: latest `origin/main` commit containing this handoff and
  `DEVELOPMENT_CHECKPOINT.md`
- Active completed-evidence Issue: [#34](https://github.com/TimeTreker/chromie/issues/34)
- Next Issue: create a separate Fast/Deep Planner prompt-qualification Issue; do not
  reuse #34 or silently combine the GA global DTO decision with Planner work
- Integrated scope: GA prompt/Schema qualification and 1,500-file corpus; required
  project-level prompt-qualification method; reusable repository Skill; README
  architecture overview/detail assets; and truthful combined handoff
- No provider, model profile, deployment, Runtime switch, Capability, voice, simulator,
  or hardware behavior changed

## Prompt-qualification method delivered

`docs/LLM_PROMPT_QUALIFICATION_METHOD.md` is the single method owner distilled from
the GI and GA investigations. It requires:

- explicit semantic authority and global-versus-role-local prompt ownership;
- reconstruction of the real production prompt/context/Schema/model/Host transaction;
- one independently reviewable scenario per file in a frozen digest-bound contrast corpus;
- target-blind immutable full-batch inference with the owner-declared model authority;
- deterministic hard gates before retained semantic judgment;
- earliest-boundary classification across scenario/oracle, prompt/profile,
  context/harness, contract/schema, runtime/provider, model inference, mixed, and
  unresolved causes;
- one minimal general fix, exact focused proof, then complete frozen-cohort rerun;
- explicit stop conditions, evidence ceiling, blockers, and cross-session delivery.

The method includes a copy-ready Planner session protocol. Fast and Deep remain depth
passes of the same Planner HOW authority; qualify Fast primary/streaming/re-entry first,
then Deep complex/blocked/revision paths, then rerun both cohorts. Neither may review or
semantically repair the other.

## Reusable Skill delivered

- `.agents/skills/optimize-chromie-llm-prompt/SKILL.md` turns the committed method into
  an executable Codex workflow for audit, qualification, optimization, model comparison,
  and global-change review.
- `.agents/skills/optimize-chromie-llm-prompt/agents/openai.yaml` provides the
  user-facing Skill metadata and invocation example.
- The Skill points back to `docs/LLM_PROMPT_QUALIFICATION_METHOD.md` as authority; it does
  not create another project method owner, prompt authority, model call, or Runtime path.

## Homepage architecture visualization delivery

- `README.md` now displays the sparse overview in its Architecture section. The PNG is
  the robust GitHub preview and links to the editable scalable SVG.
- The complete original ASCII diagram remains immediately below in a collapsible
  `Text fallback: canonical ownership path` block.
- The README links a detailed reference that expands the same canonical flow into
  Runtime events, Current Work, Host validation, trusted Evidence, Protective Reflex,
  bounded state, and Planner re-entry.
- `docs/assets/chromie-cognitive-diagrams-manifest.json` binds the two SVG sources and
  two PNG exports to dimensions, SHA-256 hashes, authority sources, and provenance notes.

Repository surface delta for this delivery: five new asset files under `docs/assets/`
and three modified existing documentation owners (`README.md`,
`DEVELOPMENT_CHECKPOINT.md`, and `HANDOFF.md`). No new architectural term,
environment variable, runtime switch, compatibility path, provider, or evidence format was
added. Consolidation opportunity: keep future homepage architecture visuals in this same
overview/detailed pair and manifest rather than adding a third diagram owner.

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

Methodology-only delivery additions:

- `docs/LLM_PROMPT_QUALIFICATION_METHOD.md`: new required owner for the complete
  prompt-qualification method and Planner new-session protocol.
- `AGENTS.md`: makes the method required reading before model-role prompt optimization.
- `CONTRIBUTING.md`: links the method to the existing authoritative LLM-versus-workflow
  root-cause categories.
- `docs/README.md`: indexes the new owner and its governance question.

Prior GI delivery surface delta: zero new tracked files; 338 modified corpus scenario files and
24 other existing source/test/config/document/scenario files (362 total). No new environment
variable, public switch, architecture term, compatibility path, provider, runtime profile,
or evidence format. Consolidation opportunity: if an exact deployed decoder proves prompt
length is a blocker, reduce duplicated field descriptions inside the existing prompt/schema
owners; do not create another prompt authority or repair stage.

The previously delivered GA scope remains unchanged:

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

Prior GA delivery surface delta: 1,505 new tracked files (1,500 scenarios,
four corpus support files, one dataset test) and five existing implementation/test/doc
owners plus the two required delivery owners modified. No environment variable, public
switch, first-class architecture term, compatibility path, or evidence format was added.
Consolidation opportunity: if the global mixed decision is authorized, evolve the existing
GA result discriminant rather than adding a parallel model stage or new association service.

Methodology-delivery surface delta: current Markdown-document count grows from 99 to
100; one method owner is added, three existing governance/index documents are updated,
and the two required delivery owners advance. The new document is necessary because no
existing owner composes authority audit, frozen target-blind inference, adjudication,
iteration, stop, and Planner handoff into one protocol. Consolidation opportunity: keep
all role-independent prompt method changes in this owner and replace any future duplicate
component procedure with a link rather than adding another methodology document.

Skill-delivery surface delta: two new agent-tooling files under one existing Skill owner
surface. No product document, environment variable, Runtime switch, compatibility path,
semantic authority, evidence format, or model call was added. Consolidation opportunity:
keep role-specific procedures in the method/Skill pair rather than adding sibling Skills.

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

Previously delivered GA qualification evidence at `7d314cbd`:

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

The first GA complete gate attempt stopped because `docs/README.md` did not index the new
corpus README. The missing existing-owner index was added; the complete gate was rerun
and passed. No failing gate is hidden.

Final observed methodology-delivery pre-commit results at `b9f5550a`:

```text
python scripts/check_repository_policies.py
15 rule families, 0 reviewed exceptions; passed

./scripts/run_tests.sh
2,048 main tests and 20 legacy Agent tests; passed

python scripts/check_docs.py
100 Markdown files; passed

git diff --check
passed
```

Previously observed architecture-documentation gate at `f3d14792`:

```text
manifest/XML verification
2 SVG files valid; 4 asset hashes match manifest

python scripts/check_repository_policies.py
15 rule families, 0 reviewed exceptions; passed

./scripts/run_tests.sh
2,048 main tests and 20 legacy Agent tests; passed

python scripts/check_docs.py
98 Markdown files; passed

git diff --check
passed
```

No tests or validation commands were run for the repository Skill commit or this `main`
integration, by explicit project-owner instruction. The prior gates above remain historical
evidence on their exact revisions and are not claimed as current-run evidence.

## Cross-machine resume

```bash
git fetch origin main
git switch main
git pull --ff-only origin main
python scripts/check_repository_policies.py
./scripts/run_tests.sh
python scripts/check_docs.py
python benchmarks/datasets/goal_association_daily_life/validate.py
```

Start Planner prompt work by reading `docs/LLM_PROMPT_QUALIFICATION_METHOD.md`, then
audit these real owners before editing:

```text
agent/app/planner_prompt.py
agent/app/planner_context.py
agent/app/planner_model_contract.py
agent/app/planner_validation.py
agent/app/fast_planner.py
agent/app/deep_planner.py
tests/test_planner_prompt_module.py
tests/test_fast_planner_pr3.py
tests/test_deep_planner_pr4.py
tests/test_fast_planner_streaming_commit.py
tests/test_planner_reentry_policy.py
```

Create a new Issue and a new `codex/` branch after preserving any unrelated dirty
worktree state. Before implementation, report Planner authority/non-authority, every
Fast/Deep invocation variant, the real boundary workflow, proposed bilingual contrast
matrix/count/splits, adjudication dimensions, evidence level, and any global decision
requiring owner authorization. Use Codex `gpt-5.6-sol` high reasoning for offline
inference unless the owner explicitly selects another model; never silently substitute
Gemma/Ollama. Store one scenario per file, hide targets from inference, complete one
immutable baseline before editing, and do not commit/push without explicit authorization.

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
current contract. The methodology and Skill are process/agent-tooling evidence and do not
qualify Fast/Deep Planner behavior. The homepage assets are explanatory views of existing
authority truth. No production model/profile, live service, audible voice, microphone,
simulator, target robot, physical safety, or release evidence was established. The 100
global mixed-decision cases remain open.
