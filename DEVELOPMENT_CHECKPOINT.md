# Chromie Development Checkpoint

Status: Goal Association (GA) remains **not qualified** for the configured
`qwen3.5:4b` role after the owner-authorized maximum 10 semantic optimization
iterations. A same-model Codex surrogate had scored 1,500/1,500 strict, but the
first exact Ollama qualification exposed a frozen-Schema ordering defect in the
harness and systematic deployed-model failures. After preserving production
Schema order, the final configured-model focused gate scored 5/9 strict; a
`qwen3.5:9b` comparison scored 4/9. No final 1,500-case run was started because the
required focused gate did not pass.

Updated: 2026-09-02

Delivery branch: `codex/ga-prompt-qualification-paused-20260901`

Worktree base before this delivery:
`5cb6977ab176044d99b1ae9007eca259c6da8377`

Expected resume: the latest normal commit on the delivery branch containing this
checkpoint and `HANDOFF.md`, pushed to
`origin/codex/ga-prompt-qualification-paused-20260901`.

Active Issue: [#34 — Goal Association semantic qualification](https://github.com/TimeTreker/chromie/issues/34)

Issue #35 Fast/Deep Planner qualification remains paused. Do not resume it by
claiming GA is qualified.

## Stable authority and actual workflow

The current focus remains the Goal-driven single-authority architecture. GA owns
canonical Goal identity and continuity, not Planner HOW. One
candidate-aware primary result may associate existing Goals and create independent
Goals together. Every admitted GI Responsibility must appear exactly once across
the union of `associations[]` and `new_goals[]`. The no-candidate segmentation
variant retains its fixed `decision=create_goals` wire shape.

```text
immutable user turn + GI Responsibilities + bounded Goal candidates
  -> exact production GA system/user prompt
  -> request-bound dynamic JSON Schema
  -> one non-thinking Ollama primary invocation
  -> optional one-shot mechanical malformed-DTO repair only
  -> DTO + resolver + canonical Host validation
  -> hidden target-blind Responsibility-map adjudication
```

Planner remains the only HOW authority. No second model call confirms, scores,
audits, or semantically repairs GA. The exact-provider runner uses Chromie's
production `OllamaClient`, prompt, dynamic Schema, and generation options, but
bypasses the deployed Agent HTTP service and establishes no service, voice,
simulator, hardware, independent-review, or release evidence.

## Actual episode and earliest wrong boundary

| Module / owner | Material input and actual output | Expected contract | Judgment |
|---|---|---|---|
| Goal Interpretation | Frozen Responsibilities correctly distinguish targeted continuity from `relationship=new,target_goal_ids=[]` | Preserve each Responsibility and its local ref for GA adjudication | Correct in retained cases |
| GA prompt / primary model | On the configured 4B baseline, all 100 explicit replacements and all 100 unrelated new Goals failed; the model associated new work to a candidate or confused independent work with replacement | Explicit replacement creates a new Goal with only the retired ID in `supersedes_goal_ids`; independent work creates a new Goal with empty related/superseded IDs | Incorrect primary semantic boundary |
| Dynamic Schema / constrained decoder | The first Ollama harness serialized Schema with sorted keys, unlike production. With production order restored, 4B generated mutually exclusive association/new-Goal branches and sometimes classified blinking as a physical resource | Preserve exact production key order and emit one mechanically valid, Responsibility-conserving DTO | Harness fixed; model/Schema interaction still unqualified |
| DTO / resolver | Rejects related/superseded overlap and malformed resource or conservation shapes; at most one mechanical repair is allowed | Validate but never reinterpret model semantics | Correct fail-closed containment |
| Canonical Host | Commits only complete conserved results; otherwise returns fail-closed | Never repair or shift semantic authority downstream | Correct containment |

The configured-model failure is therefore not a Host or persistence defect. The
earliest remaining wrong boundary is the primary model plus its constrained
model-facing contract: the model can state the right continuity rationale and then
emit contradictory ownership/resource fields.

## Implemented candidate scope

- Preserved the existing mixed association-plus-creation authority and exact
  Responsibility conservation.
- Enforced disjoint `related_goal_ids` and `supersedes_goal_ids` in the DTO and
  request-bound Schema, matching the Host's existing fail-closed invariant.
- Clarified replacement, coexistence, relationship precedence, source polarity,
  new-Goal description provenance, and per-ref conservation in the GA prompt.
- Added compact top-level continuity evidence and a bounded `reason_summary` to
  make the decision visible before the payload; this remains a qualification
  candidate, not a proven production improvement.
- Reordered constrained Goal fields to the mechanically more stable order observed
  in the focused configured-model experiment; broad exact-provider qualification
  remains outstanding.
- Extended the frozen qualification runner with `--provider ollama`, exact model
  digest/version binding, production generation options, production-client calls,
  source/model stability checks, and order-preserving Schema freezing.
- Added focused contract, Schema, harness, and production-transport tests.

No new semantic authority, extra model call, runtime switch, environment variable,
compatibility path, architecture layer, standalone design document, or first-class
project term was added. The configured Agent model remains `qwen3.5:4b`; the 9B
model was evaluated only as a local comparison and was not configured or deployed.

## Evidence ledger

| Evidence | Observed result | Qualification limit |
|---|---|---|
| Same-model offline final cohort before exact-provider work | 1,500/1,500 strict, zero repair/timeout | Codex surrogate; not Ollama constrained decoding |
| First complete 4B Ollama cohort | 1,184/1,500 hard, 1,170/1,500 strict; 22 repairs, 15 Host recoveries, four 2,048-token truncations | Later invalidated as an exact-production claim because frozen Schema keys had been sorted |
| First exact-order focused gate | 3/9 hard; five repairs; one truncation | Exact production Schema order; exposed model/Schema mechanical instability |
| Iteration 9 configured 4B focused gate | 5/9 strict, zero repairs/timeouts; source/model/harness stable | Final configured-model focused result; not qualified |
| Iteration 10 9B comparison | 4/9 strict, one repair; source/model/harness stable | Comparison only; model was not configured or deployed |
| Focused Python regression suite | 94/94 passed | Contract/harness regression evidence only |
| Canonical local gate | `./scripts/run_tests.sh` exited 0: 138 pytest, 2,050 unittest, and 20 legacy Agent tests passed after policy, ownership, static-analysis, configuration, structure, documentation, and scenario checks | Current local candidate; does not override the failed model-role qualification gate |
| Direct policy and documentation checks | 15 policy rule families with zero exceptions; 102 Markdown files passed | Static/documentation evidence only |

Configured model identity:

- Ollama `0.32.14`
- `qwen3.5:4b`, 4.7B Q4_K_M
- digest `2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd`
- `num_ctx=32768`, `num_predict=2048`, `temperature=0`, `top_p=0.9`

Comparison identity:

- `qwen3.5:9b`, 9.7B Q4_K_M
- digest `6488c96fa5faab64bb65cbd30d4289e20e6130ef535a93ef9a49f42eda893ea7`

Corpus digest:
`e13861a0a5d963f5f2bb86353c63d6ecd7806128b429a2b4212111f0331023d0`.

Retained paths and exact commands are in `HANDOFF.md`.

## Iteration accounting and stop condition

The owner authorized at most 10 semantic optimization iterations. Iterations 1–3
were the prior clarify, supersession contract, and relationship-precedence work.
Iterations 4–9 refined the deployed-model decision procedure, coexistence polarity,
field-level contract, and constrained output order. Iteration 10 compared the
available 9B profile. The limit is exhausted. Infrastructure corrections to make
the runner reproduce production Schema order were not counted as semantic prompt
iterations.

Because the final focused gate failed, no current-revision full 1,500-case cohort
or live/service proof was run and no qualification pass may be claimed.

## Ordered resume work

1. Treat the current production edits as an unqualified candidate. Do not merge to
   a release line or resume Issue #35 on an inherited GA-green claim.
2. Before another semantic change, obtain owner authorization for a new iteration
   budget and choose one bounded direction: simplify the GA output Schema/role,
   qualify a different model/profile, or change the model-facing resource branch
   without moving semantic authority to the Host.
3. Start with the retained 9-case exact-order gate. Require strict pass with zero
   repair, recovery, timeout, or truncation before expanding to the affected
   categories and then the full immutable 1,500-case cohort.
4. Only after a clean full cohort, run the relevant General Ability classes and
   canonical repository gates, then update both delivery documents again.
5. The remote sibling `origin/codex/ga-prompt-qualification-1500` at `0f525f3a`
   remains unmerged. Inspect it explicitly before any integration and never
   force-push either line.

## Claim boundary

This checkpoint establishes a reproducible exact-Ollama qualification path, fixes
the harness's Schema-order mismatch, retains fail-closed contract improvements, and
proves that the configured `qwen3.5:4b` GA role is **not yet good enough** on the
focused gate. It establishes no deployed service quality, full-corpus qualification,
independent semantic review, Fast/Deep Planner quality, training readiness, voice,
simulator, hardware, physical safety, release, or robot behavior.
