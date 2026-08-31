# Chromie Development Checkpoint

Status: Goal-driven GI single-authority contract fixed; homepage architecture now has overview and detailed diagrams while retaining the text fallback; exact deployed-provider qualification remains open
Updated: 2026-08-31
Pre-delivery baseline: `main` at `7596ee06f693b08918fde99063fbf24018a4e2dc`
Expected resume revision: latest `origin/main` commit containing this checkpoint and `HANDOFF.md`

## Read first

Read [Project Charter](docs/PROJECT_CHARTER.md),
[Human-Like Interaction Contract](docs/HUMAN_LIKE_INTERACTION_CONTRACT.md),
[Current Status](docs/STATUS.md), [Roadmap](ROADMAP.md),
[Acceptance](docs/ACCEPTANCE.md), and [Latest Handoff](HANDOFF.md).
Current source, tests, and retained executable evidence win.

## Active delivery line

```text
admitted turn -> one primary GI WHAT result
  -> deterministic validation
  -> accept, or one source-based Deep GI for genuine unresolved meaning
  -> GA preserves WHAT/output_mode and owns Goal continuity
  -> Planner owns HOW -> Runtime -> correlated Evidence
```

- Do not restore a GI DTO repair, semantic reviewer, coverage call, Host
  resegmentation, or phrase-based semantic lane selector.
- GI is the sole `output_mode` author. GA may carry only the decoder-constant value
  while committing Goal identity/continuity; the Host derives execution projections.
- Invalid primary or Deep GI output fails closed. Stop/cancel/emergency remain
  deterministic and no downstream owner may reconstruct missing WHAT.

## Completed delivery scope

- Removed the primary GI source-regeneration path and Deep location retry. Added a
  repository-policy guard against all three obsolete repair markers.
- Preserved explicit measured values as exact number-plus-unit source/context surfaces.
  The corpus pins 406 such digit measurement bindings; all final outputs preserve them.
- Made standalone greetings, thanks, feelings, evaluations, and comparable social acts
  one speech Responsibility; politeness attached to another request adds no sibling.
- Limited unfamiliar-name uncertainty to consequential referent/category choices.
- Corrected Charter principle 31: GI authors `output_mode`, GA preserves it, Host
  derives execution lane/provider requirement after validation.
- Updated 338 existing corpus scenarios: 270 unit representations, 34 cancellation
  source spans, and 34 unfamiliar-name unresolved references. Scenario count remains
  1,496; `unresolved_scenarios` is now 68 and training remains prohibited.
- Updated three maintained Level-A scripts that encoded the removed GI repair call.
  No new tracked file, environment variable, architecture term, compatibility path,
  runtime flag, provider integration, or profile was added.

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

| Boundary/owner | Authoritative input and correlation | Observed wrong output | Expected/final output | Judgment |
|---|---|---|---|---|
| Gateway | Exact admitted turn, source tokens, bounded Context | Correct immutable source handoff | Same | Correct |
| Primary GI | Source + static/dynamic prompt + closed Schema | Unit-bearing values could lose units; standalone social turns could be empty; invalid DTO triggered another full interpretation | One complete WHAT DTO with units/social/name materiality; invalid DTO terminal | Earliest semantic/authority boundary fixed |
| Trusted GI validation | Primary DTO + exact source/reference mechanics | Validation failure could start `goal_interpretation_contract_repair` | Validate mechanically, accept or fail closed | Repair authority leak removed |
| Deep GI | Accepted primary result with genuine `unresolved`; source is re-read once, prior DTO absent | Invalid location provenance could trigger another Deep call | One Deep source decision, then accept or fail closed | Recursive retry removed |
| GA | Immutable accepted Responsibilities keyed by `local_ref` | Charter wording implied GA could author mode | Preserve GI mode under decoder `const`; own only Goal identity/continuity | Documentation and runtime agree |
| Host/Planner | Accepted Responsibilities + Goals | No confirmed defect in this episode; not invoked by offline model cohort | Host projects mechanics; Planner alone authors HOW | Authority containment retained |

Initiating probes were invalid GI DTOs, `5 seconds`, standalone thanks/feelings,
direct unfamiliar names, and Goal lifecycle turns. The root causes were same-authority
source regeneration plus contradictory prompt/schema/document/data contracts. Downstream
symptoms were unit loss, missing conversation, unnecessary clarification, and mode-authority
ambiguity. The fix changes the first wrong GI/document/data boundaries rather than asking
GA, Planner, or Host to reinterpret the turn.

## Evidence ledger

| Evidence | Result | Limit |
|---|---|---|
| Final target-blind primary Codex cohort | 1,496/1,496 calls, generated Schema, and Host; 835 mechanical; 1,366 same-model semantic passes; prompt changes recommended: 0 | Codex role/decoder envelope, not deployed provider; reviewer non-independent |
| Final source-based Deep subset | 68/68 calls, Schema, Host, decomposition, mode, relation, and source; 55 semantic passes; prompt changes: 0 | Only genuine-unresolved reference subset; same transport/reviewer limits |
| Critical exact dimensions | Units 406/406; Goal-continuity mode and relationship 136/136 | Offline primary output only |
| Bilingual probes | Thanks, feelings, harmless names, units 8/8 | Codex diagnostic, not live robot |
| Relevant Level A | `planner_goal_semantic_quality` 4/4; `robust_intent_understanding` 8/8 | Evidence level A, not services/audio/hardware |
| Canonical local gate | 2,048 main tests and 20 legacy Agent tests; policy 15 families/0 exceptions; docs 98; test ownership passed | Automated source evidence on pre-commit tree |
| Homepage diagram delivery | Two SVG sources parse; four SVG/PNG hashes match the manifest; README targets exist; canonical gate remains 2,048 main tests plus 20 legacy Agent tests | Documentation/export verification only; no runtime or target evidence |

Retained local artifacts are listed in `HANDOFF.md`. They are ignored by Git and do not
transfer with the commit.

## Prompt/core-principle audit

- Base prompt: 15,212 characters, SHA-256
  `73729710f5baef12ba690ff13ef949aeef00017643fb188e143ed3cc76626df6`.
- Three system variants only: base, prior-assistant context, Goal-continuity context.
  Context projection adds no semantic classifier and no extra call.
- Layer order is authority -> decision procedure -> Responsibilities -> modes ->
  bindings -> coordination/provenance -> uncertainty -> example -> result conditions.
- Main and Deep paths comply with Charter 30/31/33. Four final reviewer failures that
  cite `schema_version` are reviewer errors: the exact decoder Schema allowed the field
  and production Host accepted it.
- Iteration stopped at 5/20 because iterations 2/3 regressed other abilities and both
  final primary/Deep audits recommended zero prompt changes. Remaining failures are
  model inference or candidate-oracle/grader differences, not a shared prompt boundary.

## Exact resume point

1. Fetch the delivery revision and reproduce the canonical gates:

   ```bash
   python scripts/check_repository_policies.py
   ./scripts/run_tests.sh
   python scripts/check_docs.py
   python benchmarks/datasets/goal_interpretation_daily_life/validate.py
   ```

2. Select an exact candidate provider/model, then run its transport plus current primary
   GI manifest without weakening Schema/Host validation:

   ```bash
   python scripts/qualify_vllm_provider.py \
     --base-url http://127.0.0.1:8000/v1 \
     --model <exact-model-id> \
     --output .chromie/acceptance/model-qualification/<new-id>.json \
     --goal-interpreter-probe \
     --goal-interpreter-manifest benchmarks/manifests/goal_interpreter_primary_v1.json
   ```

3. Do not promote from the offline Codex counts. Bind prompt, schema, strict decoder,
   model digest, parameters, revision, latency, GPU/TTS coexistence, and runtime identity.
   After a material deployment change, run one fresh complete directory-discovered
   live-text cohort and collect exactly one debug bundle.

## Claim boundary

This remains development-only. No new production model/profile was promoted, and no
microphone, audible voice, simulator execution, target hardware, or release claim was made.
The homepage diagrams visualize the already-authoritative architecture and establish no
new runtime, target-validation, or release evidence.
