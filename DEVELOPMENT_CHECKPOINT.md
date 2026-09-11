# Development Checkpoint

## Current delivery boundary — Issue #41 speech authority and delivery truth

Updated 2026-09-11. The owner authorized returning ordinary speech necessity,
correction and repetition to Planner. Host no longer deletes valid speech by
body-Work category, sibling speech, or equal text. Same-turn sibling speech is
read-only Planner context; exact Goal/Work scope and execution guards remain.
Runtime atomically reuses one Activity's delivery, rejects changed wording under
that identity and retains separate scheduled/started/completed/interrupted facts.
Every chunk must complete before whole speech becomes history or completes a Fast
speech Goal. Start barriers remain separate; interrupted Activities do not replay
automatically. Deferred playback retains original ownership and transport identity.

Delivery base: `main` at `4a1364028d6e59b09ac83ca470733f792a771f62`, tracking
`origin/main`. Continue the standing commit/push authorization. Resume from the
latest commit containing this checkpoint and HANDOFF; do not predict its hash.
Evidence: `.chromie/acceptance/issue41-speech-authority-20260911/`.
Focused 301 tests/44 subtests and Level A 30/30 passed. Final canonical passed
2,442 tests/723 subtests, 140 benchmarks and 20 legacy Agent tests.
The first full gate failed seven tests through stale start-as-delivered fixtures;
its failed cohort and first Level A 28/30 remain retained, not promoted to passes.
Real transport code was tested with mocked audio writes, including interruption,
partial chunks, early receipts, retries, concurrent submissions and deferred output.
No model inference, service deployment, physical voice or target proof was run.
Ignored artifacts need separate transfer; tracked commands/workflow are in HANDOFF.

Prior #37–#40 changes are in the delivery base; their historical evidence remains
below/in HANDOFF. Other GI normalizers, numeric source extraction beside a period,
#42–#48, full merge/split, model optimization and deployment remain unapproved.
No corpus inputs/reference outputs, provider profiles, config keys or runtime
switches changed. Existing owners hold this amendment; no new architecture layer.
Historical #37 implementation/evidence follows; use this top entry for current resume.

## Prior local implementation — Issue #37, 2026-09-11

Active Issue #35; Goal-driven single-authority architecture. The owner explicitly
authorized the discussed Charter and
implementation amendments: independent GI-/GA-triggered Planner calls, scoped
Work revision, actual Runtime/Evidence continuity, and existing Memory role
projections. The owner separately confirmed that existing Capability contracts
may admit safe reads before GA; other Work may only be prepared. This specific
amendment is authorized despite the prior evidence-only delivery constraint.
Other audit findings and the separate Fast tagged-stream wire proposal remain
outside scope. No additional optimization iteration, model/provider change,
deployment, commit or push was performed.

Checkout: `/home/chromie/github/chromie`, branch `main`, uncommitted patch over
`a0c5d09fbb18fca8660aa43abb55bccca18924cc`. Source and tests were initially clean.
Implementation/test/harness patch SHA-256 (documentation excluded):
`16354fd4b0e52c96a30b7077675c2a344a99340b9fa86fe3f9b7f070409efcc6`.
Exact patch, identity and evidence are retained locally under
`.chromie/acceptance/independent-planning-memory-20260911/`.
Ignored artifacts do not transfer with Git; preserve them separately.

## Implemented scope and earliest responsible boundaries

| Boundary | Former mismatch and current mechanism |
| --- | --- |
| Charter -> Planner contract | Principle 25 prohibited all pre-GA Capability execution while architecture/principle 34 allowed safe reads. The authorized rule now permits only complete, validated preparation and available, explicitly side-effect-free safe reads without confirmation; all ordinary Runtime barriers remain. |
| GI/GA -> Planner invocation | GI output starts GA and its own Planner task concurrently. Material committed Goal/Work changes start a distinct Planner call without waiting for the first. Identity-only association remains a mechanical join; neither GI nor GA owns planning. |
| Planner -> Work contract | Complete-group reuse/implicit replacement could not express the agreed partial revision. Planner can reuse a subset, add Work and explicitly select cancel_activity_ids. Omission means unchanged. DTO, dynamic Schema, prompts and Host validation agree. |
| Planner result -> Runtime/Host publication | Scoped snapshots, serialized intersecting commits, exact Plan/fingerprint and single-use version guards reject obsolete submissions before publication and again before dispatch. Shared requests retain one execution identity and require every owning Goal for mutation. |
| Pre-GA read -> canonical execution | Integration exposed different provisional/canonical interaction IDs, losing seeded result reuse. Exact shared identity now binds the original result; real local Runtime regression observes one provider call, before GA. |
| Plan revision -> Goal progress/Evidence | A single latest-Plan binding lost preserved older progress/Evidence and Goal-stop coverage. Existing execution records retain original bindings; Goal views aggregate retained/current Work, accept only exact preserved old Evidence, and stop all owned Plan groups. |
| Memory -> role context | Existing activated, privacy-filtered entries now reach GI, GA and Planner with source, consent and lifetime fields. Cognitive relevance and persistence remain separate; Memory cannot replace current Goal, Work or Evidence truth. |

The current execution sequence and snapshot contract are owned by
[COGNITIVE_TURN_LOOP](docs/COGNITIVE_TURN_LOOP.md); the exact local proof workflow
is retained in [HANDOFF](HANDOFF.md). No standalone design document, architecture
layer, service or configuration switch was added. Maintained Markdown count is
102 -> 102; configuration keys remain 381, public booleans 1, aliases 0.
Existing Memory, Runtime and Goal-state owners were extended.

## Observed verification and limits

Final `./scripts/run_tests.sh` passed: **2,407 tests, 671 subtests,
140 benchmark tests and 20 legacy Agent tests**. Repository policy, test
ownership, pinned Ruff/MyPy, configuration, runtime-structure and documentation
checks passed. Two existing FastAPI startup deprecation warnings remain.
`canonical.log` binds this result to the retained implementation patch;
`canonical-before-retained-evidence.log` is an earlier intermediate result only.

Focused evidence includes independent Planner completion, real local Runtime
safe-read single execution, scoped partial reuse/cancel/add, stale submission
rejection, shared ownership, preserved progress/Evidence, and multi-Plan Goal
cancellation. Relevant files: `publication.log`, `task-delta.log`,
`retained-evidence.log`, `goal-stop.log`; full final gate includes every regression.
The pre-change focused baseline is `baseline.log` (150 tests, 11 subtests).

Selected Level A general-ability acceptance passed **21/21 distinct cases**:
continuous recovery 4/4, deterministic safety 3/3, human-like continuity 4/4,
multiple Goals 10/10, capability grounding 7/7. Class memberships overlap.
`level-a.log` and `level-a/` retain the final run. These are deterministic local
contracts and scheduling evidence, not model inference or interaction-quality
qualification. Provider stubs and the existing Level A scenario fixtures were used;
no physical actions, microphone, audible speaker or deployed service proof ran.

| Implementation | Automated verification | Target validation | Release readiness |
| --- | --- | --- | --- |
| Authorized architecture/contract amendment implemented locally. | Canonical gate and selected Level A classes pass; final documentation check retained separately. | Current patch unqualified for real model, live voice and target runtime. | Development only; default target-evidence closure remains open. |

## Next resume

The owner requested separate discussion and authorization for each audit finding.
[Audit index #36](https://github.com/TimeTreker/chromie/issues/36) links #37 (this
authorized local implementation) and #38 (completed documentation correction),
#39 (semantic inheritance), #40 (GI speed and GA preservation), and #41 (speech
authority). Remaining #40 work and #42–#48 need separate authorization.

1. Inspect `git status --short --branch`, this checkpoint, current Charter and
   HANDOFF. Preserve any subsequent dirty work and existing evidence.
2. Review the authorized amendment as one change. No unresolved owner decision
   blocks this implemented slice; do not infer authorization for the other
   architecture findings, Fast wire change, model optimization or deployment.
3. For any further authorized source edit, run focused regression and the
   canonical gate; keep evidence bound to the exact patch/revision.
4. For newly authorized model/live qualification, bind fresh production prompt,
   Schema, source, provider and runtime identities and run the full frozen cohort.
   The old 29–46 budget remains exhausted; this local amendment does not renew it.
5. Any later Git delivery must update both handoff owners in the same commit.

## Historical evidence preserved

The prior consolidation at the base revision passed 2,392 tests, 671 subtests,
140 benchmarks and 20 legacy tests; selected Level A was 26/26. Its full resume
record is available with `git show a0c5d09f:DEVELOPMENT_CHECKPOINT.md`, and its
workflow remains below the current entry in HANDOFF. Those are base-only counts.

The 4090 Laptop batch 29–46 remains complete and unqualified. Fixed
Qwen3.5:4b Q4_K_M/Ollama; retained repairs 31/32 (GI context) and 43 (GA repair
eligibility). Final GI 46: 44 cases / 61 calls, 3 reviewed qualified; final live
preview: 1 complete failure, 1 partial, 49 unrun. Final original bundle:
`/home/chromie/Downloads/chromie_debug_bundle_20260911_051238.tar.gz`.
Full failures, rejected candidates and provider identities remain in HANDOFF and
`.chromie/acceptance/laptop-more18-20260911/`; none were requalified here.
Soridormi was not edited. The separate native Fast wire proposal stays pending.
