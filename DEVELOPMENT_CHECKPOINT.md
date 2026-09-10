# Chromie Development Checkpoint

## Current repair — Deep failure containment and repetition validation

The Goal-driven single-authority architecture remains binding. Active Issue #35,
branch `codex/ga-request-format`, baseline `0f5d3988` (audit) / runtime source
`3c70093e`. Owner requested implementation after the root-cause audit. Commit/push
remain authorized; main promotion is not authorized by a count of preview passes.
Resume from the latest delivery containing both checkpoint and handoff. Preserve
unrelated Soridormi work and the fixed RTX 5090 / Gemma4-12B FP8/SGLang profile.

## Root cause and implemented boundaries

| Actual workflow | Evidence / earliest wrong boundary | Implemented result |
| --- | --- | --- |
| GI count=1 -> Fast turn Activity duration=2/yaw=.12 -> Host | Numeric values from unrelated fields were pooled; changing only duration to1 made the count check pass | A count-bound Capability without a count input is rejected independently of other numeric args. Existing same-name numeric validation remains; no Host inference of repeated action meaning |
| GI unresolved object -> concurrent GA/Fast -> Deep | GI omitted referent ambiguity; GA retained unknown physical source, Fast escalated, Skill discovery returned zero candidates; Deep proposed duplicate parallel deliveries | No upstream semantic rewrite or second selection/model call added |
| Deep parallel-resource validation -> failure producer -> Runtime | Resource conflict correctly rejected, but empty Plan omitted execution_allowed=False; adapter then raised missing exact text | Both Deep failure producers force execution_allowed=False and preserve original error/feedback, empty steps/text; existing adapter returns zero speech and zero capabilities |

The failure producer owns mechanical containment, not a clarification sentence.
Both semantic rejection and exception paths use the corrected producer; unavailable
also obeys this invariant. Caller metadata cannot accidentally mark these empty
failure results executable. Unmarked successful Plans still cannot omit required
communication or confirmation. No adapter weakening, new flag, public DTO, current
document, Capability, model call, runtime switch or architecture layer was added.

Repetition validation now closes the demonstrated false acceptance; it does not
claim that a turn with no count parameter can realize count through node cardinality.
That representation remains a contract gap. Allowing repeated or composite Activity
structures must be justified against existing responsibility/cardinality authority
before implementation; do not assume one arbitrary node always means one repetition.
The model-visible turn catalog lacks an explicit yaw sign convention, so direction
error attribution remains incomplete. Neither gap is an LLM-only limitation.

The previous audit's Deep raw-schema failure (confirmation False where True was
required) is separate from the observed Host parallel-resource rejection. Do not
replace original error provenance with the later response-text symptom. Both are
retained in the real `ambiguous_object_bring_that` episode.

## Evidence and qualification

Prior immutable baseline: `.chromie/acceptance/skill-single-call-20260910/`, 51 cases,
28 mechanical /17 reviewed acceptable initial previews, all159 linked calls inspected.
Prior audit: `.chromie/acceptance/root-cause-audit-20260910/`, four numeric counterfactuals
and original/marked failure adapter replay; no model call or execution.
New repair evidence: `.chromie/acceptance/root-cause-repair-20260910/` (private,
transfer separately across machines). Focused Fast/Deep/Runtime tests pass 248 tests /
26 subtests, including eight count/duration/yaw contrasts and four failure-producer
integration contrasts. Level A:19/19 across stable grounding, natural uncertainty and
evidence discipline. Full canonical gates pass:2326 tests /411 subtests, 140 benchmarks,
20 legacy Agent tests, repository policy, ownership, static analysis and documentation.
`canonical.log` retains the observed run; later changes are documentation only.
The immutable deployed cohort completed51 cases:28 mechanical /17 reviewed acceptable
initial previews, all154 linked calls reviewed (GI53, Fast49, GA48 Schema passes/1 failure,
Skill1, Deep2). All154 transport calls completed; transport acceptance is not semantic
or Host acceptance. Exactly one bundle followed:
`/home/chromie/Downloads/chromie_debug_bundle_20260910_181025.tar.gz`.
`cohort-exits.json`:exit1, bundle0, source_stable=true. `behavior-review.json` contains
all cases. Continuation and tired support recovered; polite walk gained an extra
thanks Goal and outside-people response invented absent visual sensors. Other residual
failures remain. No causal claim attributes those unchanged-model output variations
to these two Host/fallback changes.

The current live ambiguous-object case failed in Fast before Deep (missing resource
kind); right-turn failed at GI duration provenance. Consequently the cohort does not
prove those exact repaired branches were entered. `focused-replay.py` / `results.json`
replay the original packet through current Host and current Deep failure producer:
all four count/duration/yaw variants now reject unrelated-number evidence; regenerated
Deep failure passes the existing Runtime adapter with zero speech/capabilities and
original feedback. The unchanged historical unmarked failure still errors, as intended.
Focused producer-to-adapter tests also cover rejection, exception, unavailable and
conflicting caller metadata. No Runtime acceptance weakening is used.
No full behavior, model-only, physical voice/robot or promotion claim is made.

## Runtime and resume commands

Agent tag `chromie-agent:root-cause-repair-20260910`;
image `sha256:78f877a18712ef307a77166df21a0a59e621c372ab6b30d7167302fb6e88175a`,
container `8cdd1cbc6b6324537f04c01b05e3074214f0849526e073fa9cebc9d85186bb10`.
`runtime-identity.json` retains identity; `source-verification.json` verifies all112
Python files match source. The final running implementation is the aggregate version.
Fixed model `chromie-gemma4-12b`, revision `707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7`,
65536 context/cache, two requests. SGLang/ASR/TTS/Soridormi remain unchanged.
Canonical: `./scripts/run_tests.sh`; explicit policies/docs/ownership checks remain
required. Cohort: this root's `run-cohort.py` runs all directory-discovered must-pass
live-text previews once, with no source/runtime changes, then exactly one debug bundle.
Inspect every raw transaction and mechanical pass before another broad source change.
Unsafe previews are not physical execution; supervised voice/robot evidence is absent.

Compose prefix: `docker compose --env-file .env.runtime -f docker-compose.yml -f docker-compose.sglang.yml -f .chromie/voice-runtime/compose.voice-mujoco.yaml`.
Never edit generated `.env.runtime`. Identity:
`python scripts/capture_runtime_identity.py --allow-dirty --orchestrator-env .chromie/voice-runtime/orchestrator.env --compose-override docker-compose.sglang.yml --compose-override .chromie/voice-runtime/compose.voice-mujoco.yaml --output NEW/runtime-identity.json`.
Delivery checks and all-case review are complete; commit/push include both handoff
owners. A separate owner question is pending: extend Soridormi turn Capability with
bounded count (default1), Planner authors count once, provider performs sequential
repetition, Host only validates. No reply is authorization; that expansion is not
implemented in this delivery. The semantic qualification Skill requires owner approval
before making a previously unrepresentable valid outcome expressible. Continue only
after that approval, auditing Soridormi's contract and preserving unrelated changes.
Retain the repetition-representation and catalog-direction evidence gaps,
GI ambiguity/prohibition/omission, GA continuity, Planner integrity/progress/truth,
and target-evidence blockers instead of declaring residual failures model-only.
