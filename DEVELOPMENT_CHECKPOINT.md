# Chromie Development Checkpoint

Status: Goal Association (GA) is **qualified for the exact current branch
candidate at the same-model offline Codex-surrogate level**. The final frozen
Codex cohort scored 1,500/1,500 strict with zero repair, recovery, timeout, or
process failure. This is not deployed-provider, service, voice, simulator,
hardware, independent-review, release, or main-branch evidence.

Updated: 2026-09-02

Delivery branch: `codex/ga-prompt-qualification-paused-20260901`

Pre-delivery baseline before the qualification patch:
`ec34652f29f7957182b0104cc1fa57a3d0050cf3`

Expected resume: the latest normal delivery commit on this branch containing this
checkpoint and `HANDOFF.md`, pushed to
`origin/codex/ga-prompt-qualification-paused-20260901`.

Active Issue: [#34 — Goal Association semantic qualification](https://github.com/TimeTreker/chromie/issues/34)

The owner corrected the qualification target: Qwen/Ollama results are historical
model comparisons, not the authority for deciding whether the GA prompt,
Schema/DTO, and Host transaction are sound. Codex `gpt-5.6-sol` with high
reasoning is the model used for the current target-blind qualification.

## Stable authority and actual workflow

The current focus remains the Goal-driven single-authority architecture.
GA owns canonical Goal identity/continuity, new Goal creation, bounded referent
continuity, and exact conservation of every admitted GI Responsibility. It does
not own Planner HOW, Capabilities, executable Plans, response wording, completion,
or Host persistence/lifecycle mechanics.

```text
immutable user turn + GI Responsibilities + bounded candidates/context
  -> exact production GA system/user prompt
  -> request-bound dynamic JSON Schema
  -> one target-blind Codex primary inference
  -> optional one-shot mechanical malformed-DTO repair only
  -> Pydantic DTO + resolver + canonical Host fail-closed validation
  -> hidden Responsibility-map adjudication
```

No second model call confirms, criticizes, scores, or semantically repairs the
primary result. The retained runner projects the exact prompt and Schema through a
strict Codex transport envelope; it does not exercise the deployed Agent service or
Ollama constrained decoder.

## Actual episode and earliest boundaries

| Module / owner | Material input and observed output | Expected contract | Judgment |
|---|---|---|---|
| Goal Interpretation | Frozen Responsibilities, local refs, relationships, targets, output modes, and bindings | Preserve each admitted Responsibility for GA | Correct in retained corpus |
| GA prompt/primary model | Baseline Codex run scored 1,500/1,500 strict, but `reason_summary` was instructed and ordered as a prior duplicate semantic decision | `associations[]`/`new_goals[]` (or segmentation `decision`) are the sole semantic result; rationale is non-authoritative | Contract authority defect fixed in iteration 1 |
| Dynamic Schema | Iteration-1 full run allowed one media Goal to omit `media_operation`; DTO requested mechanical repair to add `play` | Decoder Schema must expose the DTO invariant: media playback requires an explicit non-`none` operation | Earliest mechanical defect fixed in iteration 2 |
| Codex transport | Two iteration-1 processes returned no output with `Selected model is at capacity` | Retain service failure separately from semantic quality | Transient; clean at concurrency 8 and in focused replay |
| DTO/resolver/Host | Rejected the missing media operation, allowed one mechanical repair, conserved refs, and failed closed on absent outputs | Validate without reinterpreting semantics | Correct containment |

The final changed workflow makes the structured collections authoritative before
the rationale and prevents a media Goal from crossing the decoder boundary without
an explicit valid media operation.

## Implemented scope

- Removed the Qwen-specific instruction and Schema ordering that made
  `reason_summary` a duplicate semantic source of truth.
- Defined top-level rationale as compact, non-authoritative evidence and restored
  collections/decision plus semantic discriminators before descriptive payloads.
- Preserved the already-successful replacement, coexistence, polarity,
  relationship-precedence, exact-description, disjoint related/superseded IDs, and
  Responsibility-conservation rules.
- Aligned the dynamic Schema with the existing DTO invariant by requiring a
  non-`none` `media_operation` only for `media_playback`; non-media Goals retain
  the safe `none` default.
- Updated focused executable assertions for authority order and media operation.

No new semantic authority, model call, runtime switch, environment variable,
compatibility path, architecture layer, standalone design document, or first-class
project term was added.

## Evidence ledger

| Evidence | Observed result | Qualification limit |
|---|---|---|
| Frozen current-branch Codex baseline | 1,500/1,500 strict; zero repair/timeout/process failure | Exact pre-change branch transaction; same-model, non-independent offline evidence |
| Iteration-1 focused contrasts | 6/6 strict; zero repair | Mixed continuity+creation, segmentation, replacement, coexistence, merge, split |
| Iteration-1 full cohort | 1,498/1,500 hard; 1,497/1,500 strict | Two Codex capacity failures; one media-operation repair; no semantic-map drift among returned outputs |
| Iteration-2 focused replay | 3/3 strict; zero repair | Missing-media-operation case plus both capacity-failed cases |
| Final iteration-2 full cohort | **1,500/1,500 strict**; zero repair/recovery/timeout/process failure; source/harness stable | Exact current candidate; Codex surrogate only |
| Focused referent/GA/media/corpus tests | 114/114 passed | Deterministic contract and module evidence |
| Relevant General Ability Level A | 28/28 passed across semantic quality, intent, continuity, multi-goal, and uncertainty classes | Level A only; no live service/robot claim |
| Canonical local gate | 138 pytest, 2,050 unittest, 20 legacy Agent tests passed | Local code/test consistency only |
| Policy and docs checks | 15 policy families, zero exceptions; 102 Markdown files passed | Static/documentation evidence only |

Final artifact:
`.chromie/benchmarks/goal-association/20260902T-codex-iteration-02-full/`

Final production-files digest:
`aedd5ea9322c3f7d7aa277f15ea0b5ae00451e91d8e1ba835ebaf2e87803b5a4`

Corpus digest:
`e13861a0a5d963f5f2bb86353c63d6ecd7806128b429a2b4212111f0331023d0`

The 1,500-case corpus has no independent semantic reviewer and contains no
non-empty discourse-referent or `interpretation_unresolved` cases. Existing
referent/unresolved module tests and relevant Level-A scenarios pass, but that does
not turn the frozen cohort into independent whole-role evidence.

## Iteration accounting and stop condition

The corrected owner-authorized budget was at most 10 Codex-led semantic/contract
iterations. Two were used:

1. restore single semantic authority and discriminator-first output order;
2. align media-operation Schema and DTO invariants.

The previous Qwen-focused iteration count is historical and does not consume this
corrected task budget. The current stop condition is satisfied: focused proofs,
the complete immutable cohort, relevant Level-A checks, and canonical local gates
are green. No evidence justifies another iteration.

## Ordered resume work

1. Resume from the latest normal delivery commit containing this checkpoint and
   `HANDOFF.md`; verify the branch is clean and matches its upstream.
2. Integrate deliberately with the selected delivery line. `main` and this branch
   have diverged, so do not inherit this evidence across a merge/rebase without
   rerunning the transaction on the integrated revision.
3. Issue #35 Planner qualification may resume only after the chosen revision
   contains this GA candidate or equivalent and its GA evidence is re-bound to that
   revision.
4. Add independently reviewed referent/unresolved contrast coverage in a later
   corpus revision if a broader whole-role or training-readiness claim is needed.
5. Any deployed service, voice, simulator, or robot claim requires its own retained
   current-revision evidence.

## Claim boundary

This checkpoint qualifies the exact current GA prompt/Schema/DTO/Host candidate for
the frozen 1,500-case Goal-continuity corpus under target-blind Codex inference. It
does not qualify Qwen/Ollama, a deployed Agent service, the divergent `main` branch,
independent semantic truth, training readiness, Fast/Deep Planner quality, voice,
simulator, hardware, physical safety, release, or robot behavior.
