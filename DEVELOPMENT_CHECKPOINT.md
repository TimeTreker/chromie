# Chromie Development Checkpoint

Status: GA local prompt/schema qualified on all 1,400 current-contract cases; 100 mixed continuity-plus-creation cases retain an explicit global DTO gap
Updated: 2026-08-31
Pre-delivery baseline: `main` at `7596ee06f693b08918fde99063fbf24018a4e2dc`
Expected resume revision: latest `origin/codex/ga-prompt-qualification-1500` commit containing this checkpoint and `HANDOFF.md`
Active Issue: [#34 — qualify the Goal Association prompt on 1,500 daily-life scenarios](https://github.com/TimeTreker/chromie/issues/34)

Current focus: preserve Chromie's Goal-driven single-authority architecture while
qualifying GA Goal-continuity inference and exposing, rather than hiding, global
contract limits.

## Read first

Read [Project Charter](docs/PROJECT_CHARTER.md),
[Human-Like Interaction Contract](docs/HUMAN_LIKE_INTERACTION_CONTRACT.md),
[Current Status](docs/STATUS.md), [Roadmap](ROADMAP.md),
[Acceptance](docs/ACCEPTANCE.md), the
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
| Canonical local gate | policy 15 families/0 exceptions; 2,048 main tests and 20 legacy Agent tests; docs 99; passed | Automated pre-commit source evidence |

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

1. Fetch the delivery branch and reproduce source truth:

   ```bash
   git fetch origin codex/ga-prompt-qualification-1500
   git switch codex/ga-prompt-qualification-1500
   git pull --ff-only
   python scripts/check_repository_policies.py
   ./scripts/run_tests.sh
   python scripts/check_docs.py
   python benchmarks/datasets/goal_association_daily_life/validate.py
   ```

2. Review Issue #34 and the 100
   `mixed_continue_and_new_contract_gap` cases. Before changing the global DTO,
   obtain explicit owner authorization for the new complete-result shape, then update
   the canonical authority, dynamic Schema, resolver, corpus references, and tests in
   one change. Do not solve it with a second LLM call or split semantic authority.

3. To make a deployed-model claim, bind an exact provider/model digest, prompt and
   Schema hashes, strict decoder, parameters, revision, latency, GPU/TTS coexistence,
   and runtime identity; rerun the complete frozen cohort without source edits.

## Claim boundary

The GA local prompt/schema is good enough for the declared current-contract offline
qualification boundary. No production model/profile was promoted, and no live service,
microphone, audible voice, simulator, target hardware, physical safety, or release claim
was made. The 100 global DTO cases remain open.
