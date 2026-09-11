# Development Checkpoint

## Current delivery — remaining Issues, 2026-09-12

The owner authorized project decisions, remaining-Issue implementation and qualification,
normal commit/push, and closure of solved main-delivered Issues. Older approval/budget
statements below are historical. Base: main/origin at
`a4e7c3df5aa663b324a4a06ae13fbd37502ff67a`. Resume from the latest main commit containing
this checkpoint and HANDOFF; no predicted delivery hash is recorded.

Implemented: #40 rejects lossy GI preprocessing and preserves sentence-final decimal
provenance; #28's current information-resource contract carries exact city/date/period
through GA into Planner and keeps requested-provider evidence separate from speech;
#46 separates stable semantic/safety invariants from API-owned serialization; #47
records actual deployment scheduling limits; #48 reconciles source/status drift.
Fast streaming now emits one native, ordered JSON object containing its early immutable
presentation and complete terminal result. Rejected/cancelled streams close promptly.
Provider diagnostics retain original responses; GA qualification distinguishes raw
wire acceptance from parsed replay. A small Planner disposition clarification fixes
the reproduced clarification-only/mixed error. No semantic authority, execution barrier,
model profile, new runtime switch or physical permission changed.

After the final cohorts, one stale internal docstring in planner_prompt.py was
corrected. `delivery-comment-only-proof.json` proves identical non-docstring AST;
all executable code and prompt literals are unchanged. Frozen/deployed byte hashes
bind the pre-docstring source, with this explicit delivery-only textual difference.

Evidence root: `.chromie/acceptance/open-issue-closure-20260911/`. Exact workflows,
artifacts, source/runtime/model identities and next commands are in HANDOFF. Ignored
private evidence must be transferred separately; Git alone does not retain it.

| Implementation | Automated verification | Target validation | Release readiness |
| --- | --- | --- | --- |
| GI/provenance, native streaming, provider lifecycle/evidence and documentation corrections implemented. | Final source gate: 2,480 tests/771 subtests,145 benchmarks,20 legacy tests; policies/static/config/docs pass. Level A30/30. Frozen Fast final204/204 Schema/Host and assisted semantic review. Deep final: 40/40 Schema,39/40 Host,35/40 frozen hard passes; five failures retained after full review. | Unqualified. All compared local model profiles retain hard semantic/contract failures. Final51-case preview stopped at GI:1 complete failure,1 partial startup,49 unrun. No current physical microphone, audible speaker or robot proof. | Development only; no target/profile/release promotion. |

Fast baseline203/204 -> first JSON rerun204/204 -> final-source rerun204/204, all retained.
Fast source corpus is204 cases (17 design capacities, bilingual,52 streaming/72 primary/
80 re-entry). Deep corpus of 40 covers 10 capacities; these replace the older 600-case proposal
under the maintained coverage-first method. Codex gpt-5.6-sol/high, one invocation per
case, no runtime semantic reviewer or repair. Offline surrogate evidence is non-independent
and bypasses deployed provider/Agent HTTP skill disclosure; it does not qualify local
models or live robot behavior.

The final laptop aggregate uses a rebuilt Agent matching all 113 evaluated source files
before the documented docstring-only edit.
SID 4800df1d / llmcall_goal_interpreter_4d9954acf7ff4523 merges the ordered walk0.2/10s,
nod2 and left-turn request into one body Responsibility with a whole-turn subtype.
GI correctly rejects; GA, Planner and requested provider dispatch do not run. One bundle
at the hard stop: `/home/chromie/Downloads/chromie_debug_bundle_20260912_012522.tar.gz`.
Text input, discarded audio and dry-run preview are not physical evidence.

Model comparison results remain negative: GI44 strict dimension counts6/1/2 for qwen4b/
e2b/e4b, and2/44 for the qwen9b extension; those counts include lexical/span-oracle
limitations and are not semantic success rates. Confirmed independent-outcome omissions
still reject all profiles. Final GA30 raw-aware strict result18/30 each. Native Fast8
Host result2/8 each, with e4b additionally failing one accepted speech result semantically.
Prefix/residency/contention evidence is retained; observed1 resident model and foreground
first-token delay6.26–6.35s do not establish interactive responsiveness. Production model
profile remains unchanged. Supervised target-evidence closure remains open.

Complete main-delivered source/audit Issues may close after remote hash verification.
#24, #32 and #35 must remain open while their qualification fails; do not check off
those criteria to satisfy an Issue-count target. Next work starts with the reproduced
Deep response-only cancellation projection and
read-first satisfaction contract conflicts in #35, then the remaining GI/model transaction
boundary. Preserve frozen contrasts and explicit oracle limitations; repeat both Planner
cohorts, role/profile qualification and the aggregate live proof after the relevant repairs.
Physical microphone/speaker/robot acceptance remains supervised. The current delivery
constraint allows no unrelated feature expansion before those evidence prerequisites.

## Historical checkpoints

All following records describe prior revisions and prior authorization states.

## Current delivery boundary — Issue #44 validation claims and semantic evidence

Updated 2026-09-11. The owner approved the retained #44 audit and proposed Charter
clarification. Principle 30 requires complete source-grounded Responsibility-coverage
evidence in the primary result; proof at a trusted boundary means only its named
mechanical invariant. Model-authored coverage/confidence/satisfaction are semantic
claims. An observed semantic omission fails even when Schema and Host accept it.
No completeness obligation, hard gate, semantic authority or no-review-chain rule
is relaxed. The current evidence/feature constraint remains binding.

Delivery base: main / origin/main at
`3a0012da10416a2f8b3d0e4c7d8f4f740d7f39ac`; initially clean and synchronized.
Resume from the latest main commit containing this checkpoint and HANDOFF.
Evidence: `.chromie/acceptance/issue44-guarantee-audit-20260911/`.
Existing ACCEPTANCE now owns the check/owner/limit table and separate reporting of
raw Schema validity, normalized DTO/Host acceptance, semantic qualification, target
validation and release readiness. Existing four status axes and A–D levels remain.
SEMANTIC_AUTHORITY links that owner; STATUS records this documentation-only scope.
No runtime, report emitter, prompt, Schema/DTO, model/profile, gate or corpus changed.

The audit retained 12 scripted contrasts, not a live model episode. GI can omit the
joke from a greeting-plus-joke request while satisfying its mechanical checks; GA
conserves that incomplete declared input. With two correct Goals, Planner can claim
complete coverage while saying only Hello. Missing declared refs still fail. Raw
Schema and normalized Host acceptance also differ on an omitted GI confidence field;
this documents their distinction without changing the remaining #40 normalization policy.
Audit-focused: 388 tests/385 subtests plus four Host containment tests passed.
This delivery's canonical result: 2,465 tests/756 subtests, 140 benchmarks
and 20 legacy Agent tests passed; policy/static/config/docs passed.
No model inference, deployment, voice, simulator or physical proof ran. These fixtures
show limits of the validators, not the failure rate of an evaluated model. Detailed
workflow, initial fixture corrections, retained files and claim limits are in HANDOFF.

#45 is delivered in 3a0012da and closed; #43 and the other previously verified source
Issues remain closed. #44 closes after this main delivery is pushed and verified.
#36 remains the open audit index. Next suggested discussion: #46; remaining #40 and
#46–#48 require separate decisions. #24/#28/#32/#35 retain acceptance/qualification
gaps. The 29–46 model budget is exhausted; no further optimization, transport amendment
or deployment is authorized. The prior #42 private evidence folder remains absent on
this machine; Git does not transfer ignored artifacts. Historical workflows remain in HANDOFF.

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
authority). #44 is the current authorized correction; remaining #40 work and
#46–#48 need separate authorization. Solved main-delivered Issues are closed under
the owner's current instruction; historical acceptance wording below is superseded.

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
