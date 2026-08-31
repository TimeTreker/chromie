# Chromie Latest Handoff

Audience: coding agent or operator resuming provider qualification and target-evidence closure.
Owner: project owner. Replace this snapshot when `DEVELOPMENT_CHECKPOINT.md` advances.
Authority: operational snapshot only; current source, tests, retained evidence, and the
checkpoint win.

## Repository state

- Repository: `https://github.com/TimeTreker/chromie.git`
- Pre-delivery branch/base: `main` at
  `c07dc3e4baa76b73008907d3d1fefb0e39178d68`
- Expected resume revision: latest `origin/main` commit containing this handoff and
  `DEVELOPMENT_CHECKPOINT.md`
- Delivery scope: GI authority/prompt/data/test/documentation corrections only; no model,
  runtime profile, provider integration, deployment, feature, or hardware change
- Active line: reproduce the canonical local gate, qualify an exact deployed provider/model,
  then retain current-revision live evidence; do not add unrelated architecture

## Current authority flow

```text
Gateway admitted source
  -> one primary GI WHAT DTO
       -> deterministic Schema/source/reference validation
       -> accept resolved meaning
       -> or one source-based Deep GI for genuine unresolved meaning
            -> deterministic validation -> accept or fail closed
  -> GA preserves Responsibilities/output_mode and owns Goal identity/continuity
  -> Host derives execution projections; Planner owns HOW
```

GI has only two model stages in source: `goal_interpretation` and the conditional
`goal_interpretation_deep`. There is no primary/Deep contract-repair call. Repository policy
guards reject restoration of the removed repair payload and stage markers. Do not restore a
semantic reviewer, resegmentation call, Host source interpretation, or phrase-rule lane.

## Delivered changes

- Removed source-based primary DTO regeneration and the Deep location retry. Invalid primary
  or Deep output now fails closed after that authority's single invocation.
- Preserved explicit measured values and units as one exact source/context surface. The
  candidate corpus pins 406 digit measurement surfaces; final inference retained all 406.
- Reconciled standalone social acts with the required non-empty Responsibility inventory:
  greetings, thanks, feelings, evaluations, practical decisions, and reassurance requests
  are one speech Responsibility when they stand alone.
- Made unfamiliar-name uncertainty materiality-based. A clear `look up X` or `tell X ...`
  role does not become unresolved merely because the name is unfamiliar.
- Corrected Charter principle 31: Goal Interpretation is the sole `output_mode` author;
  Goal Association preserves it under decoder `const` and conservation validation; Host
  derives responsibility kind, execution lane, and provider requirement afterwards.
- Corrected 338 existing bilingual corpus scenarios: 270 unit representations, 34 minimal
  cancellation source spans, and 34 unfamiliar-name unresolved references. The dataset
  remains 1,496 cases, 68 genuinely unresolved cases, and not training eligible.
- Replaced three Level-A fixtures that expected the removed GI repair with one valid primary
  result; updated the dataset coverage test and current owner documents.

Repository surface delta: zero new tracked files; 338 modified corpus scenario files and
24 other existing source/test/config/document/scenario files (362 total). No new environment
variable, public switch, architecture term, compatibility path, provider, runtime profile,
or evidence format. Consolidation opportunity: if an exact deployed decoder proves prompt
length is a blocker, reduce duplicated field descriptions inside the existing prompt/schema
owners; do not create another prompt authority or repair stage.

## Actual defect workflow and root cause

Representative probes: invalid primary DTO, `Walk forward for 5 seconds`, `Thank you`,
`I am tired`, `Tell Nova the meeting moved`, and lifecycle cancel/resume turns.

| Module/owner | Authoritative input/material values | Actual output before fix | Required/final output | Correlation and judgment |
|---|---|---|---|---|
| Gateway | Exact admitted text, source token table, bounded semantic Context | Immutable handoff | Same | Correct; source refs identify each GI Responsibility |
| Primary GI | Gateway source + 15,212-char base/conditional prompt + exact decoder Schema | Could emit `duration: 5`, omit standalone social Responsibility, or mark every unfamiliar name unresolved | Preserve `5 seconds`; one social speech Responsibility; unresolved only for consequential meaning | Earliest semantic-contract boundary fixed |
| GI validator | One raw DTO + exact source/reference/order mechanics | Invalid DTO could start a second full source interpretation mislabeled repair | Accept one DTO or fail closed | Earliest authority violation fixed; no model handoff follows rejection |
| Deep GI | Same source/Context, only after accepted primary `unresolved`; prior DTO absent | Invalid location provenance could start a third GI call | One Deep decision, then accept or terminal failure | Retry chain removed |
| GA | Accepted immutable Responsibilities, local refs, source evidence, GI mode | Runtime already constrained mode, but Charter said GA authored it | Preserve exact GI mode; own only Goal identity/continuity | Canonical wording corrected |
| Host/Planner | Accepted Responsibilities + canonical Goals | No defect observed here; offline cohort does not invoke them | Host projects mechanics; Planner authors HOW | Not invoked by primary/Deep model cohort; Level A checks conservation only |

Initiating triggers exposed four root causes: same-authority source regeneration, unit-dropping
scalar instructions, conflicting social/name contracts, and contradictory `output_mode`
documentation. Downstream symptoms were unit loss, missing natural conversation, unnecessary
Deep/clarification, and ambiguous semantic ownership. The patch fixes the first wrong
GI/document/data boundaries; GA, Planner, and Host do not recover or reinterpret missing WHAT.

## Final prompt and cohort identity

- Base revision at cohort preparation:
  `c07dc3e4baa76b73008907d3d1fefb0e39178d68` plus dirty delivery patch
- Cohort-bound worktree diff SHA-256:
  `0659aedfbcf5e12746ff22a6f9e6e7a48eb0855f32c5a9eb9cbb7f27f91063e4`
- Base prompt SHA-256:
  `73729710f5baef12ba690ff13ef949aeef00017643fb188e143ed3cc76626df6`
- Model: `gpt-5.6-sol`, reasoning effort `high`; production payload temperature request
  retained only as metadata because Codex CLI controls decoding
- Partition seed `20260831`; six whole-contrast-set batches:
  `252 / 248 / 248 / 252 / 248 / 248`
- Qualification: `chromie.codex_gi_reference_full_authority_v5_final`

Only the dataset coverage assertion and evidence/current-state/checkpoint/handoff text changed
after the final cohort; prompt, Schema, runtime, corpus inputs/targets, and GI implementation
did not. The assertion change mirrors already cohort-bound manifest truth (`68`, `406`).

## Retained local evidence

Primary final cohort:

```text
.chromie/acceptance/model-qualification/codex-gi-reference-full-authority-v5-final/
.chromie/acceptance/model-qualification/codex-gi-reference-full-authority-v5-final/ANALYSIS.zh-CN.md
```

- 1,496/1,496 calls completed; no call failure/timeout
- generated Schema and production Host: 1,496/1,496
- mechanical full-dimensional matches: 835
- exact decomposition 1,496; output mode 1,490; relationship 1,496; unresolved 1,474
- exact explicit digit measurement surfaces 406/406
- exact Goal-continuity output mode and relationship 136/136
- same-model post-hoc semantic review: 1,366 valid, 130 invalid
- reviewer root causes: candidate oracle 360, grader convention 345, model inference 130
- assistant references judged valid: 1,136; prompt-change recommendations: 0

Deep final subset:

```text
.chromie/acceptance/model-qualification/codex-gi-reference-deep-authority-v5-final/
```

- all 68 candidate-reference genuinely unresolved scenarios
- 68/68 calls, Schema, Host, decomposition, mode, relationship, and source evidence
- mechanical full-dimensional matches 42; same-model semantic review 55 valid/13 invalid
- assistant references judged valid 52; prompt-change recommendations: 0

Focused evidence:

```text
.chromie/acceptance/model-qualification/codex-gi-authority-v1-probes-v2/results.json
.chromie/acceptance/general-ability/20260831-gi-single-authority-final-level-a/
```

- bilingual thanks/feelings/harmless-name/unit probes: 8/8
- Level A: `planner_goal_semantic_quality` 4/4 and
  `robust_intent_understanding` 8/8

The four primary reviewer failures that cite `schema_version` are known reviewer mistakes:
each case's exact decoder Schema allowed `schema_version=1` and Host validation passed. All
evidence is diagnostic and non-independent. Ignored `.chromie` paths remain only on this host
and are not transferred by Git push.

## Prompt/core-principle audit

- Static layer order is clear: authority -> decision procedure -> Responsibilities ->
  output modes -> bindings/dimensions -> coordination/source evidence -> uncertainty ->
  worked example -> result conditions.
- Runtime generated three system variants only: base 15,212 chars/1,292 cases,
  prior-assistant 15,592/34, and Goal-continuity 16,171/170. Projection follows already
  authoritative Context/Schema and does not select a semantic lane.
- Main user payload contains immutable source/tokens and bounded Context only. Schema is a
  closed decoder contract. Deep adds broader reasoning only after genuine unresolved meaning.
- Charter 30/31/33 are satisfied: one primary semantic source, no same-authority audit/repair,
  one permitted source-based Deep delegation, and terminal Deep rejection.
- Iterations stopped at 5 of the authorized maximum 20. Iterations 2 and 3 broadened wording
  and regressed decomposition/source semantics; final primary and Deep audits both recommended
  zero prompt changes. Remaining errors are model inference or imperfect candidate oracles.

## Automated gates

Final observed pre-commit gate:

```text
python scripts/check_repository_policies.py
15 rule families, 0 reviewed exceptions; passed

./scripts/run_tests.sh
2,048 main tests; 20 legacy Agent tests; passed

python scripts/check_docs.py
98 Markdown files; passed

python scripts/check_test_ownership.py
passed

python benchmarks/datasets/goal_interpretation_daily_life/validate.py
1,496 generated-schema and 1,496 Host passes; 68 unresolved; 406 digit measurement surfaces
```

The first full gate run exposed one stale dataset test assertion (`102`); it was corrected to
the manifest/validator truth (`68`) and augmented with `406`, then the complete gate passed.

## Resume commands

Reproduce source truth:

```bash
git fetch origin main
git switch main
git pull --ff-only origin main
python scripts/check_repository_policies.py
./scripts/run_tests.sh
python scripts/check_docs.py
python benchmarks/datasets/goal_interpretation_daily_life/validate.py
```

Next useful evidence is an exact deployed provider/model/strict-decoder transaction, not
another broad prompt edit:

```bash
python scripts/qualify_vllm_provider.py \
  --base-url http://127.0.0.1:8000/v1 \
  --model <exact-model-id> \
  --output .chromie/acceptance/model-qualification/<new-id>.json \
  --goal-interpreter-probe \
  --goal-interpreter-manifest benchmarks/manifests/goal_interpreter_primary_v1.json
```

Bind the exact model digest, prompt, Schema, strict decoder, parameters, revision, latency,
GPU/TTS coexistence, and runtime identity. Do not promote from Codex or Level-A evidence.
After a material deployed change, rebuild/verify the Agent image, run one complete
directory-discovered live-text cohort without source edits between cases, collect exactly one
debug bundle, and inspect every case before another broad change.

## Claim boundary

Development only. No production model/profile was promoted. There is no new deployed-service,
audible voice, microphone, simulator, target robot, physical safety, or release evidence.
