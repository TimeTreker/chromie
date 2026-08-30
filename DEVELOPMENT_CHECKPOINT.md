# Chromie Development Checkpoint

Status: fixed-v4 passes the 1,496-case offline diagnostic, but a post-delivery audit found unresolved GI contract/principle blockers before further prompt tuning
Updated: 2026-08-31
Pre-delivery baseline: `main` at `8300702fd84a32f0d6358393c6651b898c10f380`
Expected resume revision: the latest `origin/main` commit containing this checkpoint and `HANDOFF.md`

## Read first

Read [Project Charter](docs/PROJECT_CHARTER.md), [Human-Like Interaction Contract](docs/HUMAN_LIKE_INTERACTION_CONTRACT.md),
[Current Status](docs/STATUS.md), [Roadmap](ROADMAP.md), [Acceptance](docs/ACCEPTANCE.md),
and [Latest Handoff](HANDOFF.md). Source, tests, and retained executable evidence win.

## Active delivery line

Keep the current Goal-driven single-authority path intact:

```text
admitted turn -> GI WHAT/Responsibilities -> concurrent GA + Fast Planner
  -> immutable presentation commit + terminal Plan -> canonical validation
  -> confirmation/Work -> Runtime Evidence -> scoped Planner re-entry
```

- One semantic authority produces its complete primary result. Do not restore semantic
  reviewers, Host resegmentation, or same-owner repair calls.
- GI owns current-turn WHAT; GA owns Goal identity/continuity; Planner owns HOW and exact
  Communicative/Capability Activities.
- Raw model tokens never reach TTS. Goal Work waits for the terminal Planner result,
  GA binding, and canonical validation.
- Keep validation fail-closed and keep stop/cancel/emergency deterministic.

## Current delivery scope

- This is a documentation-only delivery. Prompt, schema, runtime, tests, Charter,
  model/profile, deployment, and retained evidence remain unchanged from fixed-v4.
- A full call-path audit found two reachable source-based semantic retries: primary DTO repair
  discards the rejected content/error and asks from the source turn again; Deep location repair
  likewise omits the rejected Deep DTO. Both conflict with Charter principles 30, 31, and 33.
- Fixed-v4 drops units from Arabic-digit measured scalars (`5 seconds` becomes bare
  `duration: 5`), although downstream Goal conservation requires value and unit.
- The base prompt ignores thanks/declarative circumstances, the response schema requires at
  least one Responsibility, and GA requires standalone thanks/personal states to remain
  conversational Goals. The 1,496-case corpus lacks exact standalone probes for those classes.
- Charter principle 31 still says GA authors `output_mode`, while principle 30 and runtime make
  GI the author and GA the preserving projection. Amendment requires explicit owner approval.
- The static prompt is 14,059 characters; a representative full primary payload is about
  34,000-37,000 characters. Field rules repeat across base prompt, dynamic schema, conditional,
  Deep, and repair layers. Pause broad wording iteration until the authority/data blockers close.
- Retained fixed-v4 evidence: 1,496/1,496 calls and schema/Host passes, 789 mechanical matches,
  and 1,355 non-independent same-model semantic self-passes. Fixed-v5 regressed and was rejected.

## Root-cause workflow

| Boundary | Authoritative input | Actual output/transition | Expected contract | Judgment |
|---|---|---|---|---|
| Primary GI | Admitted turn, bounded Context, fixed-v4 prompt, request schema | One complete DTO; valid resolved cases use one call | One WHAT authority with complete bindings and provenance | Structurally coherent, but scalar-unit and social-turn coverage are incomplete |
| DTO repair | Original source turn; prior content is explicitly discarded | A second fresh complete semantic interpretation | Prior DTO plus exact mechanical errors only; preserve every semantic claim or fail closed | Incorrect; earliest confirmed principle violation |
| Deep GI | Genuine non-empty `unresolved` from accepted primary DTO | One fresh source-based deeper WHAT decision | One designated deeper-cognition delegation | Correct first delegation boundary |
| Deep location retry | Deep source turn plus a narrower decoder enum; rejected Deep DTO absent | Another fresh Deep interpretation | Preserve the Deep semantic decision mechanically or fail closed | Incorrect same-stage retry shape |
| Goal Association | Immutable GI Responsibilities and current-turn provenance | `output_mode` is decoder-const from the GI value | Preserve GI WHAT while committing Goal continuity | Runtime is coherent; Charter principle 31 sentence is contradictory |

## Evidence ledger

| Evidence | Result | Limit |
|---|---|---|
| Current docs-only delivery canonical gate | repository/static/docs gates passed; 2,045 main tests; 20 legacy Agent tests | Automated source evidence on the pre-commit docs-only tree |
| Fixed-v4 target-blind Codex cohort | 1,496/1,496 calls; 789 mechanical; 1,496 schema/Host; 1,355 same-model semantic self-passes | Codex text envelope, not exact production roles/decoder; reviewer non-independent |
| Fixed-v5 rejection cohort | 1,496/1,496 calls; 761 mechanical; 1,338 semantic self-passes; one unstable prompt-gap judgment | Rejected experiment; source restored to v4 |
| Post-delivery GI prompt/authority audit | 3 focused current-source tests passed; repository policies passed 15 families; prompt/payload sizes and call paths inspected | Read-only source evidence; passing tests currently encode the source-based repair behavior and do not prove principle compliance |
| Current-source live-text must-pass cohort | 0/50; core 15 and challenge 8 gated off | Diagnostic C-preview; no execution/audio/hardware claim |

Artifact paths, hashes, historical provider screens, and deployed-cohort failure clusters are
retained in `HANDOFF.md`; do not append to either complete cohort.

## Exact resume point

1. Obtain explicit owner authorization before correcting Charter principle 31 so
   `output_mode` has one canonical GI author and GA only preserves it.
2. Fix primary and Deep same-stage repair: supply only rejected DTO plus exact mechanical
   errors, preserve semantic claims, or fail closed; replace tests that require regeneration.
3. Preserve measured value plus unit across GI, corpus references, GA conservation, and
   Planner input. Do not reconstruct missing GI semantics downstream.
4. Reconcile standalone social acts with non-empty Responsibilities; make unfamiliar-name
   uncertainty materiality-based; add bilingual focused unit/social/name/repair regressions.
5. Then establish one new complete target-blind baseline and iterate within the authorized
   limit. Keep splits non-training and require independent semantic review before promotion.
6. After contract coherence, run the exact deployed provider/model/strict-decoder cohort on
   the committed identity; after material deployment changes, retain one fresh complete live
   cohort and one bundle. Never append to the retained cohorts.

## Claim boundary

This remains development-only. Local tests and C-preview evidence do not qualify audible
voice, microphone, simulator execution, target robot behavior, or release readiness.
