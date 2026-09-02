# Chromie Development Checkpoint

Status: Goal Association (GA) is integrated and qualified in this `main`
merge at the same-model offline Codex-surrogate level. The fresh integrated
cohort scored 1,500/1,500 strict with zero repair, recovery, timeout, or process
failure. Fast/Deep Planner qualification and current-revision target evidence
remain open.

Updated: 2026-09-02

Delivery branch: `main`

Pre-delivery baseline: `origin/main` at
`7605466bfe61aba1fbee70df1676d2005136a9e5`.

Expected resume revision: the latest normal merge commit on `origin/main`
containing this checkpoint and `HANDOFF.md`.

Completed delivery Issue: [#34 — Goal Association semantic qualification](https://github.com/TimeTreker/chromie/issues/34).
Close it only after the merge is pushed successfully.

Next active Issue: [#35 — Fast/Deep Planner prompt qualification and optimization](https://github.com/TimeTreker/chromie/issues/35).

The owner corrected the GA qualification target: Qwen/Ollama results are
historical model comparisons, not the authority for deciding whether the GA
prompt, Schema/DTO, and Host transaction are sound. Codex `gpt-5.6-sol` with
high reasoning is the model used for target-blind GA qualification.

Current focus: preserve Chromie's Goal-driven single-authority architecture
while closing GA qualification and resuming Fast Planner first, then Deep
Planner, under Issue #35.

## Integrated authority and workflow

GA owns canonical Goal identity/continuity, new Goal creation, bounded referent
continuity, and exact conservation of every admitted GI Responsibility. It does
not own Planner HOW, Capabilities, executable Plans, response wording,
completion, or Host persistence/lifecycle mechanics.

```text
immutable user turn + GI Responsibilities + bounded candidates/context
  -> exact production GA system/user prompt
  -> request-bound dynamic JSON Schema
  -> one target-blind primary inference
  -> optional one-shot mechanical malformed-DTO repair only
  -> Pydantic DTO + resolver + canonical Host fail-closed validation
  -> hidden Responsibility-map adjudication
```

No second model call confirms, criticizes, scores, or semantically repairs the
primary result. The retained runner projects the exact prompt and Schema through
a strict Codex transport envelope; it does not exercise the deployed Agent
service or an Ollama constrained decoder.

## Earliest boundaries and correction

| Module / owner | Observed defect or result | Expected contract | Judgment |
|---|---|---|---|
| Goal Interpretation | Frozen Responsibilities, refs, relationships, targets, output modes, and bindings were preserved | Supply each admitted Responsibility to GA | Correct in retained corpus |
| GA prompt/primary model | `reason_summary` had been ordered and instructed as a duplicate prior semantic decision | Structured `associations[]`/`new_goals[]` or segmentation `decision` are authoritative; rationale is not | Earliest semantic contract defect fixed |
| Dynamic Schema | A media Goal could omit `media_operation`, requiring mechanical repair | Media playback requires an explicit non-`none` operation at the decoder boundary | Earliest mechanical defect fixed |
| DTO/resolver/Host | Rejected the missing operation, conserved refs, and failed closed | Validate without reinterpreting semantics | Correct containment |

The merge also carries the completed frozen 1,500-case GA corpus and the
already-authored frozen 1,000-case Fast Planner corpus. Customer-configurable
Stable Mind remains integrated from the pre-merge `main` line and supplies only
bounded durable context; it does not move semantic authority.

## Implemented GA scope

- Made the structured semantic collections/decision authoritative before the
  compact non-authoritative `reason_summary`.
- Restored source identity, output mode, and resource discriminator before
  descriptive payload fields.
- Preserved replacement, coexistence, polarity, relationship precedence,
  exact-description, disjoint related/superseded IDs, and Responsibility
  conservation.
- Required an explicit valid non-`none` operation only for `media_playback`;
  non-media Goals retain the safe `none` default.
- Added focused executable assertions for authority order and media operation.

No new semantic authority, model call, runtime switch, environment variable,
compatibility path, architecture layer, standalone design document, or
first-class project term was introduced by the GA correction.

## Evidence ledger

| Evidence | Observed result | Qualification limit |
|---|---|---|
| Source-branch final Codex cohort | **1,500/1,500 strict**; zero repair/recovery/timeout/process failure | Same-model offline evidence for the qualified GA source candidate |
| Focused referent/GA/media/corpus tests | 114/114 passed | Deterministic contract/module evidence on the source branch |
| Relevant General Ability Level A | 28/28 passed | Level A only; no live service or robot claim |
| Source-branch canonical local gate | 138 pytest, 2,050 unittest, and 20 legacy Agent tests passed | Branch-local source/test consistency |
| Integrated Codex cohort | **1,500/1,500 strict**; zero repair/recovery/timeout/process failure; source/harness stable | Exact merge production tree; same-model offline evidence only |
| Integrated focused tests | 114/114 passed | Deterministic GA contract/module evidence |
| Integrated relevant General Ability Level A | 28/28 passed | Level A only; no live service or robot claim |
| Integrated repository policy gate | 15 rule families passed, zero reviewed exceptions | Static architecture/policy evidence |
| Integrated canonical local gate | `./scripts/run_tests.sh` exited 0: 138 pytest, 2,053 unittest, and 20 legacy Agent tests passed | Local source/test consistency only |
| Integrated docs gate | 102 Markdown files passed | Documentation consistency only |

Source-branch final artifact:
`.chromie/benchmarks/goal-association/20260902T-codex-iteration-02-full/`

Integrated final artifact:
`.chromie/benchmarks/goal-association/20260902T-main-integration-full/`

Source-branch production-files digest:
`aedd5ea9322c3f7d7aa277f15ea0b5ae00451e91d8e1ba835ebaf2e87803b5a4`

Corpus digest:
`e13861a0a5d963f5f2bb86353c63d6ecd7806128b429a2b4212111f0331023d0`

The 1,500-case corpus has no independent semantic reviewer and contains no
non-empty discourse-referent or `interpretation_unresolved` cases. Existing
referent/unresolved module tests and relevant Level-A scenarios pass, but that
does not create independent whole-role evidence.

## Iteration accounting and stop condition

Two of the owner-authorized maximum 10 Codex-led iterations were used:

1. restore single semantic authority and discriminator-first output order;
2. align media-operation Schema and DTO invariants.

The previous Qwen-focused iteration count is historical and does not consume
this corrected task budget. The GA stop condition was met; do not continue
tuning without new failing evidence.

## Ordered resume work

1. Pull the latest `main`; confirm it matches `origin/main`, then read this file,
   `HANDOFF.md`, Issue #35, and the frozen Planner corpus manifest.
2. Begin Issue #35 with a fresh immutable Fast Planner target-blind cohort; do
   not reuse or adjudicate the interrupted 349-call historical run.
3. Adjudicate every Fast result, cluster failures by earliest shared boundary,
   make only an evidenced minimal correction, and rerun the complete cohort.
4. Qualify Deep Planner separately, then rerun both Planner cohorts and the
   applicable General Ability and canonical gates.
5. Add independently reviewed GA referent/unresolved contrasts only if a broader
   whole-role or training-readiness claim is needed.
6. Any deployed service, voice, simulator, customer-visible Stable Mind, or
   robot claim requires its own retained current-revision evidence.

## Claim boundary

This delivery integrates the qualified GA source candidate into `main`. Its
Codex evidence is same-model and offline, not independent semantic review. It
does not qualify Qwen/Ollama, a deployed Agent service, Fast/Deep Planner,
customer-visible personalization, voice, simulator, target hardware, physical
safety, release readiness, or robot behavior.
