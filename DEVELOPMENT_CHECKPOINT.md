# Chromie Development Checkpoint

Status: GI/GA prompt qualification and its reusable project Skill are delivered; homepage architecture diagrams are retained; Fast then Deep Planner qualification is next, while 100 GA mixed-decision cases remain a global DTO gap
Updated: 2026-08-31
Pre-delivery parents: `codex/ga-prompt-qualification-1500` at `ac83e467` and
`origin/main` at `f3d14792`
Expected resume revision: latest `origin/main` commit containing this checkpoint and
`HANDOFF.md`
Active completed-evidence Issue: [#34 — qualify the Goal Association prompt on 1,500 daily-life scenarios](https://github.com/TimeTreker/chromie/issues/34)

Current focus: preserve Chromie's Goal-driven single-authority architecture while
starting a separately owned Planner qualification Issue with Fast first and Deep
second. The GA global contract limit remains visible and is not Planner work.

## Read first

Read [Project Charter](docs/PROJECT_CHARTER.md),
[Human-Like Interaction Contract](docs/HUMAN_LIKE_INTERACTION_CONTRACT.md),
[Current Status](docs/STATUS.md), [Roadmap](ROADMAP.md),
[Acceptance](docs/ACCEPTANCE.md), the
[LLM Prompt Qualification Method](docs/LLM_PROMPT_QUALIFICATION_METHOD.md), the
[GA corpus guide](benchmarks/datasets/goal_association_daily_life/README.md), and
[Latest Handoff](HANDOFF.md). Current source, tests, retained executable evidence,
and the Issue win.

## Active delivery line

```text
accepted GI Responsibilities + bounded existing/recent Goals
  -> one primary GA semantic decision
  -> generated decoder Schema enforces DTO/Host invariants
  -> deterministic GoalAssociationResolver
  -> canonical Goal continuity, or fail closed
```

- GA remains the sole Goal identity/continuity authority. Do not add a second model
  critic, judge, semantic repair, or phrase-based relationship selector.
- `reason_summary` is rationale only. It cannot carry a Goal mutation that is absent
  from `updated_description` or the supplied `resolved_gap_ids`.
- The current exclusive `associate | create_goals` decision cannot express one turn
  that both continues an existing Goal and creates an independent Goal. The 100
  retained probes are a global contract blocker, not prompt failures to hide.
- Changing that discriminant is a Project Charter semantic-authority boundary and
  requires explicit project-owner authorization plus same-change contract truth.

## Completed delivery scope

- Added 1,500 independently reviewable scenario JSON files: 100 bilingual daily-life
  semantic seeds crossed with 15 Goal-continuity families. Inputs include accepted GI
  Responsibilities and bounded existing/recent Goal state; no generator or combined
  scenario source was added.
- Added a static aggregate manifest, tree digest, validator, corpus README, and focused
  dataset test. All cases remain `training_eligible=false` and lack independent review.
- Used Codex `gpt-5.6-sol` with high reasoning for the frozen target-blind inference
  cohort. No Gemma/Ollama result is qualification evidence.
- Moved the existing modify/clarify semantic-update invariant into the dynamic decoder
  Schema and placed the same rule next to GA relationship selection in the compact
  prompt. No new call, runtime flag, environment variable, compatibility path, or
  semantic authority was introduced.
- Added a regression proving a modify output containing only `reason_summary` is
  rejected by the generated Schema and becomes valid with `updated_description`.
- Indexed the corpus in the existing benchmark and documentation owners.
- Distilled the GI/GA workflow into the required project-level
  `docs/LLM_PROMPT_QUALIFICATION_METHOD.md`: authority audit, global-versus-local
  prompt ownership, frozen target-blind cohorts, deterministic/semantic adjudication,
  root-cause classification, minimal iteration, full rerun, stop conditions, and a
  new-session Fast/Deep Planner protocol. `AGENTS.md`, `CONTRIBUTING.md`, and the
  documentation index point to this single method owner.
- Added `.agents/skills/optimize-chromie-llm-prompt/` as a reusable execution
  entrypoint for the committed method. It adds no independent methodology owner,
  model call, Runtime path, or product behavior.

## Homepage architecture visualization

- Replaced the README's primary ASCII presentation with a sparse light overview
  rendered from a deterministic SVG; the full original text diagram remains in a
  collapsible fallback for accessibility, review, and text-only clients.
- Added a linked detailed reference that expands Runtime events, Work state, Host
  validation, trusted Evidence, Protective Reflex, and Planner re-entry without
  changing the canonical ownership path.
- Retained editable SVG sources, PNG exports, and one hash/provenance manifest under
  `docs/assets/`. This is documentation presentation only: no implementation,
  architecture authority, runtime behavior, provider, evidence claim, active Issue,
  or ordered resume work changed.

## Reconstructed defect workflow

| Boundary/owner | Authoritative input and correlation | Baseline output | Expected/final output | Judgment |
|---|---|---|---|---|
| GI handoff | Accepted immutable Responsibilities keyed by `local_ref`, including output mode and source evidence | Correct frozen GA input | Same | Correct |
| Primary GA | Responsibilities plus bounded existing/recent Goals, compact prompt, dynamic Schema | 36 `modify_active` results put the change only in `reason_summary` | One complete primary decision with structured Goal update | Model exposed an inconsistent decoder boundary |
| Dynamic decoder Schema | Contract generated for the exact candidate Goals/refs | Allowed modify/clarify without a material update | Require non-empty `updated_description` or supplied `resolved_gap_ids` | Earliest responsible mechanical boundary fixed |
| GA DTO/Host resolver | Parsed primary result and exact source/Goal identifiers | Rejected all 36 incomplete modify results and failed closed | Accept structurally complete semantic update without repair | Correct containment retained |
| Canonical Goals/Planner | Only reached after Host acceptance | Not reached for the 36 baseline failures | Receive accepted canonical Goal continuity; Planner still owns HOW | Downstream authority unchanged |

The initiating probes were ordinary Goal refinements. The root cause was a mismatch:
the generated decoder Schema permitted a shape the DTO/Host already rejected, while
the relevant prompt rule was remote from relationship selection. The downstream
symptom was correct intent stranded in non-authoritative rationale. The fix changes
the earliest structured-output boundary and its local instruction, not downstream
Goal reconstruction.

## Evidence ledger

| Evidence | Result | Limit |
|---|---|---|
| Baseline full Codex cohort | 1,364/1,400 current-contract passes; 36 Host failures, all `modify_active`; 1,500/1,500 then-current Schema passes | Offline Codex role/decoder envelope; same-authority adjudication, not deployed provider |
| Exact focused rerun | 36/36 baseline failures passed changed Schema and Host; contract repair attempts 0 | Only the isolated failure cohort |
| Changed-prompt full Codex cohort | 1,400/1,400 current-contract passes; English 700/700; Chinese 700/700; Schema 1,500/1,500; unexpected failures 0; source stable | Offline prompt/Schema/DTO/Host qualification only |
| Retained global probes | 100/100 exposed the exclusive-decision contract gap | Requires global DTO/Schema design and owner authorization |
| Dataset validator | 1,500 discovered and validated; 1,400 Host accepted; 100 known gaps; 0 errors | Candidate corpus, no independent semantic review |
| Focused tests | 78 passed | Source-level regression only |
| Canonical local gate on methodology delivery tree | policy 15 families/0 exceptions; 2,048 main tests and 20 legacy Agent tests; docs 100; passed | Automated pre-commit source/document evidence; no Planner model inference or behavior qualification |
| Final target-blind primary Codex cohort | 1,496/1,496 calls, generated Schema, and Host; 835 mechanical; 1,366 same-model semantic passes; prompt changes recommended: 0 | Codex role/decoder envelope, not deployed provider; reviewer non-independent |
| Final source-based Deep subset | 68/68 calls, Schema, Host, decomposition, mode, relation, and source; 55 semantic passes; prompt changes: 0 | Only genuine-unresolved reference subset; same transport/reviewer limits |
| Critical exact dimensions | Units 406/406; Goal-continuity mode and relationship 136/136 | Offline primary output only |
| Bilingual probes | Thanks, feelings, harmless names, units 8/8 | Codex diagnostic, not live robot |
| Relevant Level A | `planner_goal_semantic_quality` 4/4; `robust_intent_understanding` 8/8 | Evidence level A, not services/audio/hardware |
| Canonical local gate | 2,048 main tests and 20 legacy Agent tests; policy 15 families/0 exceptions; docs 98; test ownership passed | Automated source evidence on pre-commit tree |
| Homepage diagram delivery | Two SVG sources parse; four SVG/PNG hashes match the manifest; README targets exist; canonical gate remains 2,048 main tests plus 20 legacy Agent tests | Documentation/export verification only; no runtime or target evidence |
| Skill/main integration delivery | Tests not run, by explicit owner instruction | Text/agent-tooling and Git integration only; prior evidence is not reclassified as current-run evidence |

Retained local artifacts are listed in `HANDOFF.md`. They are ignored by Git and do
not transfer with the commit.

## Prompt and corpus identity

- Scenario count: 1,500 separate files; `en-US=750`, `zh-CN=750`.
- Scenario-tree SHA-256:
  `264ca6eb41b15d86f3a9906eeec37576df584b1a7b113c3590f06f3adc39d2ab`.
- Changed prompt SHA-256:
  `3d68272a0612a4a7079ba15c272c5ea17d2101bc27e98c6a15975d70628c3a26`.
- Changed dynamic Schema SHA-256:
  `5162f8d03c74e339eeffec7312cccc3fadcc8da1d07a6bc931224593f96fb482`.
- Model: Codex `gpt-5.6-sol`, reasoning effort `high`; references excluded from
  candidate inference packets.

## Exact resume point

1. Fetch `main` and reproduce source truth:

   ```bash
   git fetch origin main
   git switch main
   git pull --ff-only origin main
   python scripts/check_repository_policies.py
   ./scripts/run_tests.sh
   python scripts/check_docs.py
   python benchmarks/datasets/goal_association_daily_life/validate.py
   ```

2. Read `docs/LLM_PROMPT_QUALIFICATION_METHOD.md`, create a separate Planner prompt
   qualification Issue, and audit the real Fast/Deep prompt, context, dynamic Schema,
   model, validator, and downstream boundaries before editing. Propose the bilingual
   contrast corpus count/matrix and evidence ceiling; qualify Fast before Deep. Do not
   reuse GA Issue #34 for Planner work.

3. Review Issue #34 and the 100
   `mixed_continue_and_new_contract_gap` cases. Before changing the global DTO,
   obtain explicit owner authorization for the new complete-result shape, then update
   the canonical authority, dynamic Schema, resolver, corpus references, and tests in
   one change. Do not solve it with a second LLM call or split semantic authority.

4. To make a deployed-model claim, bind an exact provider/model digest, prompt and
   Schema hashes, strict decoder, parameters, revision, latency, GPU/TTS coexistence,
   and runtime identity; rerun the complete frozen cohort without source edits.

## Claim boundary

The GA local prompt/schema remains good enough for the declared current-contract
offline qualification boundary. The reusable Skill operationalizes the committed method;
it does not qualify or change Fast/Deep Planner behavior. The homepage diagrams visualize
already-authoritative architecture only. No production model/profile was promoted, and no
live service, microphone, audible voice, simulator, target hardware, physical safety, or
release claim was made. The 100 global DTO cases remain open.
