# Chromie Latest Handoff

## Root-cause audit — 2026-09-10, after 3c70093e

Owner requested continued root-cause finding. This iteration is Audit mode: no
production source, prompt, model, Schema, runtime or scenario changes. Baseline
`3c70093e9ff7460b1f20af7cf0cbf0f71b6dd56d` remains deployed as recorded below.
Active Issue #35 and branch `codex/ga-request-format` are unchanged. Root-cause
findings below supersede provisional attribution in the previous evidence ledger.

Evidence: `.chromie/acceptance/root-cause-audit-20260910/probe.py`, per-variant JSON
packets, `results.json`, `probe.log`, and `existing-tests.log`. Replays use retained
real transaction inputs from `skill-single-call-20260910/reviewed-cases/`, current
production validators and Runtime adapter; there are no model/provider calls or
physical dispatches. Prompt catalog `args_schema` is restored to Host `input_schema`
without changing the schema. Three existing regressions / seven subtests pass;
they do not cover the newly reproduced cross-boundary gaps. Earlier full canonical
2324 / 399 results remain the unchanged-code baseline, not a new run this iteration.

| Actual episode boundary | Input -> actual output | Verdict / expected contract |
| --- | --- | --- |
| Turn GI -> Fast, walk_then_turn_right | Retained Chinese walk-three-seconds then turn-right-once; GI r2 count=1, direction=向右, location=原地 | Supplied repetition reaches Fast; it is not lost at handoff |
| Fast -> Host numeric check | One turn Activity, duration_s=2, yaw_radps=.12; turn input schema has duration/yaw but no count | Host rejects because number 1 is absent from all args; changing only duration to 1 makes it pass |
| Host numeric implementation | All numeric binding values compared against a set of numbers from all matching Activity args | Confirmed field/quantity identity loss: seconds can witness a repetition count. Negative yaw alone does not change rejection. Acceptance in this probe is only Host validation, never proof of correct direction/execution |
| Object GI -> concurrent GA/Fast | 那个 has no resolved referent; GI unresolved=[]; GA retains unknown physical source; Fast escalates without Work | Earliest semantic omission remains GI; no Skill model call occurs because discovery has zero candidates |
| Deep -> plan validation, ambiguous_object_bring_that | Two duplicate delivery steps marked parallel, same Goal and exclusive body/carried-object resources | Host correctly rejects parallel_exclusive_group_conflict and parallel_resource_claim_conflict; no delivery is authorized |
| Deep fallback -> Runtime response adapter | materialize_deep_clarify produces clarify, empty steps/text, but no execution_allowed=False | Confirmed failure-contract omission: adapter requires that marker for safe silent failure, then raises missing exact text instead |
| Counterfactual adapter replay | Same retained rejected plan, only execution_allowed=False supplied | Zero speech and zero capabilities, no secondary exception; original rejection feedback retained |

The numeric defect is in `planner_fast_validation.py`'s value-set conservation,
not proof that repetition semantics should be deleted or arbitrary arguments added.
The later field-name equality check protects count only when the chosen Capability
has a numeric count field; it cannot repair this case where that field is absent.
A future repair must preserve quantity identity and explicitly justify representation
of repetition through Activity structure; do not weaken the gate or add Host semantic
inference. The supplied model catalog also lacks a documented yaw sign convention;
previous claims that the sign failure is solely model inference remain unproven.

The failure-path defect is in the Deep fallback producer, not a requirement for the
Runtime to invent a clarification sentence. The existing adapter already supports
marked silent non-executable failures. Next minimal repair should enforce that
existing producer contract and test producer-to-adapter integration, retaining the
original failure and no second model invocation. Audit both Deep rejection and
exception paths. Do not broaden silent acceptance for unmarked successful plans.
This requires no change to semantic ownership; if subsequent work changes canonical
repetition meaning or authority, obtain owner authorization before that change.

Attribution correction: the raw Deep output also fails the retained dynamic Schema
(`user_confirmation_required=False`, schema permits True), but the observed runtime
rejection feedback is parallel-resource validation, not that Schema error. Schema,
DTO and runtime verdicts must remain separate. The model's bad proposal initiated the
episode; the missing failure marker caused the secondary exception. These confirmed
project defects rule out an all-model-only explanation. Main promotion remains blocked.
No fix or new live/robot qualification is claimed by this audit delivery.

## Current resume point — owner-authorized single-call Skill selection

The Goal-driven single-authority architecture remains binding. Active Issue #35;
branch `codex/ga-request-format`; pre-delivery baseline
`c829ff29bf8be2519a8aaf672eb913e2b76bf3ed`. On 2026-09-10 the owner explicitly
authorized the necessary removal of semantic Skill reselection after the workflow
and impact explanation. This supersedes the earlier pending-authorization state.
Commit/push remain authorized; main merge still requires unresolved behavior and
current target-evidence closure. Resume at the latest commit containing both handoff
owners. Preserve unrelated Soridormi work.

## Implemented workflow and authority

`AgentSkillSelectionService.select` makes zero model calls for no candidates,
otherwise exactly one primary call. Its primary prompt, candidate discovery, model,
Schema, token budget and valid-result validation remain unchanged from c829ff29.
Any malformed output, semantic/identity/Goal/confidence rejection returns
`model_contract_failed` with the original error and an empty selected list.
Provider failures remain `model_unavailable`. No rejected result becomes a new
semantic selection. Existing deterministic JSON parsing remains unchanged.

| Owner / handoff | Reproduced old output -> new behavior | Why this fixes the boundary |
| --- | --- | --- |
| Candidate discovery -> model | Approved weather Skill, exact version/projection/Goal -> one primary selection | Discovery remains typed and model-independent; no Host choice of method |
| Model -> Skill Host | Primary selects an unlisted ID; a queued second result selects the listed ID | Old code accepted the replacement after two calls; new code rejects the first result and never consumes the queued result |
| Host -> disclosure | Failed selection with original error, no selected Skills -> zero loaded projections/characters | No invented method provenance, no content loaded from an invalid selection |
| Disclosure -> downstream Planner | Optional method omitted -> normal existing Planner input/authority | No new Capability, permission, Plan or execution authority; this boundary does not repair upstream meaning |

The general failure matrix covers wrong Skill/version/projection/Goal IDs, low item
or aggregate confidence, empty rationale, inconsistent decision/list, malformed list,
missing list, non-object result and JSON parse error. Every case retains exactly one
call and the original failure; the valid second result remains unused. The second
model repair prompt and call were removed. No model-based format regeneration remains:
the previous flow could not guarantee preservation of every authored semantic claim.
Public repair-history fields remain false. Charter principle 30 is enforced, not
weakened; the canonical Skill architecture and API/configuration documents now agree.

Repository policy rejects extra model-call sites, second selection helpers and retry
loops. The broad-handler inventory was re-audited: the removed repair handler is
removed from the inventory; the remaining provider-failure handler still logs and
returns typed failure. No blanket ignore or exception was added. No new runtime flag,
public contract field, architecture layer or current document was introduced.

## Evidence and current claim boundary

Local evidence root: `.chromie/acceptance/skill-single-call-20260910/` (private,
not committed; transfer separately across machines). New regression assertions against
the old code failed as expected: 14 failures / 15 passes, including 12 invalid-result
contrasts and the retained unlisted-to-listed episode. After repair, focused selection,
disclosure, runtime-surface, provenance and repository-policy tests pass:
53 tests / 15 subtests. Level A passes 19/19 distinct cases in natural uncertainty,
stable capability grounding and evidence coverage. These are not live model or robot
claims. Full canonical checks passed: 2324 tests / 399 subtests, 20 legacy tests,
140 benchmarks and the included policy, static-analysis, ownership and docs gates.
The repaired semantic revision completed all 51 preview cases with unchanged source
and runtime: 28 mechanical passes / 17 reviewed acceptable initial previews. All 159
linked calls were inspected: GI 53 Schema passes, Fast 51 wire-Schema passes, GA 50
passes / 1 failure, Skill 1 pass, Deep 2 passes / 1 failure. Transport acceptance is
not Schema/Host/semantic acceptance. Skill selected once in 4139.127 ms with valid
identity/Goal references; its rationale incorrectly interpreted Tianxin as weather.
Deep asked a referent clarification with no actions; upstream ambiguity remains.
`behavior-review.json` contains every case and raw transaction path. Exactly one
bundle followed the aggregate:
`/home/chromie/Downloads/chromie_debug_bundle_20260910_160447.tar.gz`.
`cohort-exits.json` records cohort exit 1, bundle exit 0, source_stable true.

Compared with the previous 19 reviewed previews, blink-plus-joke and gaze-then-blink
recovered; capability inventory, current date, recent-walk continuation and tired
social response regressed. The first now asks/answers intended future actions;
date and walk reasons contain channel/frame markup inside otherwise valid JSON;
tired response uses an incompatible auxiliary anchor. These are observed changes,
not causal evidence that the Skill retry removal changed the unchanged GI/Fast calls.
The newly reachable ambiguous-object Deep result invents duplicate parallel delivery
steps; Schema rejection is followed by missing exact communicative text in Runtime.
The walking-completion case now passes mechanics but preauthors a completion claim
without execution evidence. Neither is counted acceptable. Other known failures below
remain blockers, regardless of overall count.

`host-proof.json` retains 11 frozen invalid-primary/valid-second fixture pairs replayed
against c829ff29 and repaired Host: identical first packets, old two-call selection
versus new one-call rejection, zero invalid disclosures. These are mock Host proofs,
not 11 successful live model decisions.

After the immutable aggregate, a diagnostic-only shared-client defect was corrected:
inside a caller's already-handled exception, successful `OllamaClient.generate`
(inherited by SGLang) read the outer `sys.exc_info()` and marked its prefix probe failed.
`wrapper-probe-before.json` reproduces successful output with a false ValueError;
`wrapper-probe-after.json` records completed. A local completion marker now distinguishes
this invocation's result from its caller's exception. Model requests/results and
exception propagation are unchanged; public-call tests cover success, actual failure
and cancellation, each with one underlying invocation. Focused client/probe tests pass
30 / 3 subtests; final canonical results above include this correction. No second model
call or semantic repair was introduced. The full aggregate belongs to the preceding
semantic source; final deployed diagnostic correction receives separate narrow proof.

The previous complete 51-case aggregate at
`skill-prompt-field-20260910/behavior-review.json` is the unchanged semantic baseline:
27 mechanical / 19 reviewed acceptable initial previews, all 157 linked calls reviewed.
Its subsequent final diagnostic-only Tianxin probe retained five complete calls and
still failed semantic review. The prior decoder/format and failed-call evidence fixes
remain implemented. Rejected GI prohibition candidate remains reverted; neither GI
nor its input contract is changed by this single-call Skill repair.

Known semantic, provenance, omitted-Goal, unsupported-motion, false-reminder, continuity,
rationale-integrity and progress/latency failures remain. Do not claim they are all
model-only, raise a numeric promotion threshold, or convert preview containment into
successful behavior. Four deterministic-reflex cases require execution evidence;
physical voice/robot and default target-evidence closure remain unproven. Main is not
merged. Scope of this change is removal of an unauthorized same-authority retry.

## Runtime and next commands

Fixed RTX 5090 / Gemma4-12B FP8/SGLang, served as `chromie-gemma4-12b`, model revision
`707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7`; 65536 context/cache and two requests.
Aggregate Agent image: `sha256:351209df29ed2c666df161f1ba218a0609a8db8d984286b5c8072491073aed8b`,
container `ce3371bb6a79dc07f776df14f9f83aab386b038bbbb643bd6f37a6a4ffdd9c2d`.
Final diagnostic correction image tag: `chromie-agent:single-skill-call-final-20260910`,
image `sha256:6791ac7283f2bd781c03cf80664c6c52b3033261e1f83431b5915d019bffd857`,
container `69ac8e6b3d49e1fb2a4e131cf7c58541eb7bff8e3b96c8220eda8854fbe0aeb9`.
ASR/TTS/Soridormi and SGLang are unchanged. Both `source-verification.json` and
`final-source-verification.json` verify all 112 deployed Python files against source;
`runtime-identity.json` and `final-runtime-identity.json` retain their separate identities.
Final narrow proof under `final-focused/` mechanically passes 1/1 but fails semantic
review: GI leaves ambiguity empty, GA invents person type, Skill rationale guesses
weather. Its one primary call completes in 3812.630 ms; Deep asks clarification and
emits zero actions. All five linked calls are retained, Schema-valid and transport
accepted with no call error. This proves final deployed path operation, not semantic
qualification or physical voice/robot behavior. `final-focused/behavior-review.json`
retains the adjudication. Resume with the numeric-binding and invalid-Deep failure
presentation audits before assigning residual failures exclusively to the model.

Canonical: `./scripts/run_tests.sh`; explicit checks:
`python scripts/check_repository_policies.py`, `python scripts/check_test_ownership.py`,
`python scripts/check_docs.py`. Read focused and all-case evidence before continuing
any semantic optimization. Investigate earliest responsible boundaries, including
numeric repetition validation, without Host meaning repair or a second semantic judge.
Update both handoff owners before delivery. A new aggregate uses a fresh evidence
root, complete directory-discovered cohort, unchanged source/runtime throughout,
exactly one debug bundle after completion, then review of every case/raw output.
Compose prefix: `docker compose --env-file .env.runtime -f docker-compose.yml -f docker-compose.sglang.yml -f .chromie/voice-runtime/compose.voice-mujoco.yaml`.
Never edit generated `.env.runtime`. Identity capture:
`python scripts/capture_runtime_identity.py --allow-dirty --orchestrator-env .chromie/voice-runtime/orchestrator.env --compose-override docker-compose.sglang.yml --compose-override .chromie/voice-runtime/compose.voice-mujoco.yaml --output NEW/runtime-identity.json`.

## Historical iterations — superseded by the current resume point above


## Current resume point — Deep/Skill decoder repairs; semantic qualification still blocked

The Goal-driven single-authority architecture remains binding.
Active Issue #35; delivery branch `codex/ga-request-format`; pre-delivery baseline
`849f31230fcb1101c18553c0b481bd9654e8deeb`. The owner authorized repairs and commit/push,
but requires explicit authorization for architecture changes and evidence that remaining
failures are solely model limitations before merging main. That condition is NOT met.
No main merge, model replacement, semantic Host fallback, or acceptance-threshold change.
Resume at the latest commit containing both checkpoint and handoff. Preserve unrelated
Soridormi changes. Earlier scoped Fast-whitespace acceptance remains historical and scoped.

## Implemented repairs and responsible boundaries

- `sglang_protocol.py` exposes existing Deep/Skill object/array shapes beside native
  intersections. Original Schema/DTO/Host constraints remain authoritative.
- Deep and Skill requests now use the existing request-local compact JSON annotation.
  Both roles reproduced outside-string whitespace loops; no token/timeout increase,
  new configuration switch, provider rebuild, or change to string content is required.
- Skill selection's primary prompt now names `selected_agent_skills`, matching the actual
  output contract, instead of the conflicting `selected_items` instruction.
- Non-stream SGLang calls retain their exact request and available response on failure,
  timeout, truncation, parse failure, or cancellation. An absent response is not invented.
  Final diagnostic corrections retain non-object provider bodies and prevent an outer
  handled exception from contaminating successful stream/non-stream call evidence.
- A GI prohibition prompt candidate was tested and rejected. GI source is unchanged;
  no Capability catalog is added to GI. All 53 GI requests in the intermediate aggregate
  lacked the known catalog keys and concrete namespaced capability IDs.

| Actual episode / owner | Input -> actual output and downstream handoff | Contract and result |
| --- | --- | --- |
| Native decoder -> original validators | Frozen Deep/Skill schemas with intersections admitted invalid object/array shapes | Redundant existing shapes close reproduced decoding gaps; validators retain authority |
| Skill client -> SGLang | Exact retained primary packet, 512-token budget -> list followed by 517 trailing whitespace characters, length finish after 12.5 s | Compact annotation rejects this prefix; corrected prompt alone also exhausted the budget |
| Compact Skill -> Host | Same retained identity/Goal contract -> completed JSON in 4.33 s | Original Schema and Skill Host identity validation pass; rationale still guesses an external platform and is not semantically qualified |
| Latest full-cohort GI -> Deep GI | Tianxin primary output guesses platform and marks ambiguity; Deep GI removes uncertainty without new referent evidence | First semantic boundary remains wrong; GI owns WHAT, never Capability selection |
| Concurrent GA/Fast -> Skill -> Deep | GA creates an external-information Goal; Fast escalates; Skill selects a listed method in 4478.99 ms; Deep returns unavailable | Skill IDs/version/Goal binding and Deep output shape valid; platform/permission assumptions remain ungrounded |
| Host -> Runtime/provider | Complete unavailable Plan with no steps -> initial response only | No Capability execution, physical sensor/voice proof, or successful request fulfillment is claimed |

The previously unretained Skill timeout `llmcall_agent_909fb4e1c6664e6c` lasted
10020 ms. A later exact retained request reproduces a whitespace loop lasting more than
10 seconds, but the missing original timeout packet prevents identifying that earlier
call's cause conclusively. This gap is not converted into a model-only finding.

## Evidence actually observed

All evidence roots below are private local artifacts under `.chromie/acceptance/` and
are not included in Git. Transfer them separately when changing machines.

`deep-skill-shape-20260910/`: 344 native contrasts (293 invalid Deep / 38 invalid
Skill rejected; 9 valid Deep / 4 valid Skill preserved). Four frozen old packets initially
fail original Schema. Shape-only fixes complete both Skill packets but both Deep calls
reach 4096 tokens on whitespace. Compact Deep completes all four packets with valid
original Schema (Deep about 14 seconds). Intermediate immutable 51-case preview:
26 mechanical / 18 reviewed acceptable initial previews, 155 linked raw calls plus
one unretained Skill timeout. All cases reviewed. Exactly one bundle:
`/home/chromie/Downloads/chromie_debug_bundle_20260910_150231.tar.gz`.

`gi-constraint-20260910/`: 16 frozen bilingual positive/negative primary-GI contrasts;
all references were Schema/Host-valid before inference. Baseline and candidate each
have 16/16 Schema and 14/16 Host passes, but only 2/8 negative cases preserve the limiting
prohibition in the owning outcome; those two still have binding defects. Candidate
rejected, original prompt restored. No full-GI or model-only qualification.

`skill-prompt-field-20260910/`: field-name-only before/after replays both exhaust 512
tokens (12.50/12.40 s); adding compact formatting completes in 4.33 s. All 344 native
contrasts preserve expected verdicts; captured loop rejected and 100 spaces inside a
string preserved. Latest immutable 51-case preview: **27 mechanical / 19 reviewed
acceptable initial previews**. All cases and 157 linked calls reviewed: GI 54 valid
(including Deep GI), Fast 50 complete valid frames, GA 49 valid / 1 invalid, Deep 2
valid, Skill 1 valid. One warm-up call is outside linkage. Exactly one bundle:
`/home/chromie/Downloads/chromie_debug_bundle_20260910_152934.tar.gz`.
Read `behavior-review.json`, `reviewed-cases/`, `raw-calls.jsonl`, `source.patch`,
`runtime-identity.json`, `cohort-exits.json`, `native/compact-summary.json` and
`compact/host-review.json`. Native/wire shape validity is not semantic correctness.

Latest full-cohort changes: single blink, polite walk, and date preview recover;
two-second gaze is omitted again, and short-joke length becomes a spurious time_scope.
Incorrect prohibited/unrelated motion, lost Goal meaning, false reminder promises,
GI provenance/continuity, GA duplicate ownership, and Fast rationale markup remain.
Four reflex cases require actual execution evidence and remain preview-limited.
The full aggregate ended before two final diagnostic-only corrections; those changes
modify evidence status/serialization only, not packets, model outputs or validators.
Final focused live proof is retained separately and never replaces the aggregate.
The final Tianxin preview is mechanically 1/1 with five complete call records and
Skill completion in 4300.177 ms, but semantic review fails: GA guesses person and
Deep invents a personal-data permission premise. No Capability executes.

Local canonical before those final diagnostic corrections: 2321 tests / 379 subtests,
20 legacy tests and 140 benchmarks passed. Final canonical validation also passed:
2321 tests / 381 subtests, 20 legacy tests, 140 benchmarks and all included policy,
static-analysis, ownership and documentation checks. The first final gate stopped
on missing architecture-focus wording in two updated documents; wording was corrected
and the full gate rerun successfully. Log: `skill-prompt-field-20260910/canonical-final-corrected.log`.
Two existing FastAPI deprecation warnings remain. Remote delivery branch matched
the pre-delivery baseline; remote main remains `ab5caeab` and is not merged.
Final focused client/Skill tests: 30 tests / 23 subtests passed. Level A: 19/19 distinct
cases across evidence coverage, natural uncertainty and stable capability grounding.
Physical microphone/speaker/robot, complete provider execution, current-revision live
voice and default target-evidence closure remain unproven. Main promotion stays blocked.

## Runtime identity and next work

RTX 5090 profile; fixed Gemma4-12B FP8/SGLang served as `chromie-gemma4-12b`, model
revision `707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7`, 65536 context/cache and two requests.
ASR/TTS/Soridormi were not replaced. Final Agent image
`sha256:cffbc8c7e1ca56f3adb4b5b5f56b2421d37ff21e669849f448d64bc694b0aea5`, container
`8fdb47be59e0a63693585b67c63e7cd4f718a0becd513e8471998a6df0af1635`;
all 112 Python files in the checked Agent/shared image scope match local source.
SGLang remains image `sha256:41fbd910662483a125184a00611029225ee102a928421eaeaec70ab27a844edf`,
container `a67606112fd19eb895a6be6d3e1a057d6771b9255bb6bb2bf60072a7863fbfdc`.
Final diagnostic revision identity/source proof: `final-runtime-identity.json` and
`final-source-verification.json` in the latest evidence root. These do not relabel the
full cohort as having run after the final diagnostic-only corrections.

Pending owner authorization: Skill selection currently retries semantic/identity/Goal
validation errors through a second model selection. The maintained unknown-selection
unit test demonstrates unlisted -> listed reselection; this conflicts with Charter 30.
The owner requested workflow/impact explanation, which was provided, but has not yet
explicitly authorized changing that architecture flow. Proposed behavior: reject
semantic/identity errors without reselection; only demonstrably meaning-preserving
mechanical format repair could remain. Do not silently change this pending boundary.
Other semantic clusters remain unresolved/mixed; do not certify them all as LLM-only.

Continue with the pending architecture decision and earliest-boundary semantic audits,
including the generic numeric-binding guard's handling of a single turn Activity.
Do not increase a pass count with keyword meaning repair, an extra judge, weakened
assertions or omission of failed cases. Keep unsafe candidates in preview.
Canonical command: `./scripts/run_tests.sh`; explicit checks:
`python scripts/check_repository_policies.py`, `python scripts/check_test_ownership.py`,
`python scripts/check_docs.py`. Update both handoff owners before every delivery.
For another aggregate, copy the latest `run-cohort.py` into a fresh evidence directory,
capture identity there, run all discovered cases unchanged, then retain exactly one
bundle and review every case before editing behavior again.
Compose prefix: `docker compose --env-file .env.runtime -f docker-compose.yml -f docker-compose.sglang.yml -f .chromie/voice-runtime/compose.voice-mujoco.yaml`.
Never edit generated `.env.runtime`. Capture with
`python scripts/capture_runtime_identity.py --allow-dirty --orchestrator-env .chromie/voice-runtime/orchestrator.env --compose-override docker-compose.sglang.yml --compose-override .chromie/voice-runtime/compose.voice-mujoco.yaml --output NEW/runtime-identity.json`.

## Historical iterations — superseded by the current resume point above


## Current resume point — scoped whitespace repair accepted; release qualification open

Active Issue #35; delivery branch `codex/ga-request-format`; pre-delivery baseline
`9a4b73a160e2ef1337026b5149cf039f8257145a`. On 2026-09-10 the owner approved
accepting the scoped code repair separately from whole-runtime qualification,
with documented model limitations where established. Commit and push remain authorized.
Resume at the latest commit containing both checkpoint and handoff.
The bounded-whitespace implementation is accepted for its demonstrated mechanical
scope on this delivery branch. This decision does not merge main or qualify a release.
Preserve unrelated Soridormi edits. The Goal-driven single-authority architecture
and fixed candidate model remain binding; no Host meaning repair or extra judge.

## Implemented scope and actual failure workflow

Retained prior repairs cover GA/GI decoder shapes, GI visible-dialogue provenance,
complete Fast Goal context, two-frame decoding and exact failed-stream evidence.
The new change bounds only Fast structural-decoder whitespace. It changes no prompt,
model, token budget, semantic fields, original schemas, retry or Host acceptance.

| Owner / handoff | Actual observed input and output | Assessment |
| --- | --- | --- |
| GI -> concurrent GA/Fast | Chongqing tonight rain question -> weather Responsibility; GA preserves weather Goal | Question retained; invented polarity/duplicated temporal bindings are separate semantic failures |
| Fast -> SGLang | Exact two-frame request at 2048 tokens -> weather action plus markup inside reason_summary, then whitespace after its closing quote | Native grammar permits unlimited whitespace, enabling budget exhaustion |
| Client -> parser/Host | length finish, exact 3474-character partial output -> output_truncated | Correct containment and evidence retention; no complete terminal Plan/provider dispatch |
| Bounded decoder | Same schema meaning; maximum eight whitespace characters at each JSON boundary and frame separator | Captured loop rejected at character 641; strings untouched |

Fast sends `x-guidance.max_whitespace_cnt=8`. The existing pinned SGLang bridge uses
XGrammar's bounded JSON-to-grammar conversion only for annotated structural nodes;
unannotated requests keep their existing formatting. Runs over eight whitespace
characters outside strings are intentionally excluded. The bridge is necessary for
this reproduced integrity blocker because the pinned structural API lacks the option;
remove it when that API supports the option. No new source/current document, environment
variable, ordinary behavior flag or semantic authority is introduced.

## Evidence and qualification limits

Automated verification: canonical gate passes 2319 tests / 368 subtests, 20 legacy
tests and 140 benchmarks, including policies, static analysis, docs and test ownership.
Focused production tests: 40 / 10 subtests; applicable Level A: 11 distinct cases.
All 198 frozen native framing contrasts pass. Built-image tests preserve 100 spaces
and quoted frame markers inside strings, reject nine boundary spaces and invalid
limits, and leave unannotated input unchanged. Twelve frozen model packets complete
with original-Schema-valid frames. One date replay still contains markup in its
rationale but closes, proving completion only; semantic content remains defective.

Target validation before change: complete immutable 51-case preview on 26fe1cee,
25 mechanical / 20 reviewed acceptable initial previews. All raw cases reviewed.
158 linked calls include 49 completed valid Fast streams and one logged truncation.
Exactly one bundle: `/home/chromie/Downloads/chromie_debug_bundle_20260910_134729.tar.gz`.
Three separate unchanged contextless-request probes complete with incorrect stand_idle
choices; valid escalation is representable. The older unlogged truncation remains unknown.

Target validation after change: complete immutable 51-case preview, 25 mechanical /
19 reviewed acceptable initial previews. Every case/raw transaction reviewed; 160
linked calls: GI 54 valid (one Deep GI), GA 50 valid / 1 invalid, Fast 51 complete valid,
Deep Planner 2 invalid, skill selection 2 invalid. One warm-up record is outside linkage.
No Fast truncation in this cohort; local-time rationale still contains markup/frame
markers. Exactly one bundle: `/home/chromie/Downloads/chromie_debug_bundle_20260910_140820.tar.gz`.
Both walk-continuation cases pass. Four reflex cases remain preview-limited.

Full-cohort regressions are retained: look-then-blink omits two-second gaze duration;
compound motion uses wrong left-turn yaw. Both exact origin packets per case replay
correctly with bounded and unbounded formatting (eight replays). Causes remain unproven;
isolated replay success does not erase the full-cohort regression. No complete
transaction/nonregression or LLM-integrity closure is claimed. The owner-approved
scoped acceptance retains this regression uncertainty explicitly; it is not a
retrospective semantic pass or a finding that the model alone caused the failures.

Release readiness remains blocked by GI prohibition/ambiguity/provenance, invented
motions, resource meaning, false reminder/completion promises, omitted Goals, GI/GA
continuity, Deep/skill contracts, progress and latency. Physical voice/provider/robot
and default target-evidence closure are missing. Preview is not execution evidence.

## Scoped acceptance decision and remaining attribution

Accepted scope: the request-local bound excludes the captured outside-string whitespace
loop while preserving string content, semantic ownership and original Host validation.
Evidence: captured-prefix rejection at character 641, 198 native contrasts, 12 frozen
completed packets, all 51 Fast streams complete in the full candidate preview, and the
retained canonical gate. No scene expectation, test result or safety gate is waived.
The 20-to-19 preview change is a retained diagnostic, not a numeric code-acceptance
threshold. This decision accepts the limited repair with unresolved regression risk;
it does not establish general behavioral nonregression or qualify the complete model role.

| Remaining observation / earliest visible boundary | Attribution supported now | Disposition |
| --- | --- | --- |
| Captured weather stream stalls on grammar-valid whitespace after a closed string | runtime_or_provider: reproduced decoder mechanism | Scoped repair accepted; rationale markup and all other truncation causes remain outside the claim |
| Gaze duration omitted / left yaw negative in candidate Fast output | unresolved: eight exact bounded/unbounded replays are correct | Preserve both cohort failures; investigate aggregate variability before whole-runtime qualification |
| GI guesses ambiguous meaning, creates a separate prohibition Responsibility, or changes provenance; GA duplicates ownership | unresolved at GI/GA primary transaction; wrong outputs observed, exact prompt/context/contract soundness not fully established | Freeze contrasts at the earliest owner; do not label all of these model_inference |
| Fast substitutes unrelated motion or promises unperformed/future work | unresolved or mixed: wrong model decisions observed; upstream meaning and supplied contracts also require audit | Deployment blockers remain; preview containment is not successful behavior |
| Deep/skill malformed results | contract_or_schema candidate plus unresolved inference; native intersection-shape evidence exists, qualification/implementation incomplete | Repair and prove the decoder/DTO boundary before attributing remaining failures solely to the model |
| Missing progress, latency, four reflex preview limits and physical evidence | Mixed behavioral/performance gaps and missing execution evidence | Keep required target profiles open; no inference from preview to execution |

A confirmed model_inference limitation may be retained without more prompt changes
when exact prompt, context, representability, provider and oracle are shown sound.
Only safely contained limitations within the declared acceptance scope can be accepted;
unsafe movement, provenance, Goal omission, fabricated success and service-integrity
failures still block the affected deployment. No residual cluster here is newly certified
as exclusively a model limitation. Original reports and scores remain historical evidence;
this owner-approved decision supersedes their blanket rejection of the scoped repair.

This delivery changes acceptance/status documentation only; runtime source, prompts,
model and deployed images are unchanged from 9a4b73a1. No new GPU or live cohort was run
for this decision. The documentation revision passed `./scripts/run_tests.sh`:
2319 tests / 368 subtests, 140 benchmark tests, 20 legacy tests, and all included
policy, static-analysis, ownership and documentation checks. Two existing FastAPI
deprecation warnings remain. Retained log:
`.chromie/acceptance/scoped-acceptance-20260910/canonical.log`.
Remote delivery branch matched the pre-delivery baseline at preflight.

## Current runtime and artifact locations

RTX 5090, 32607 MiB, driver 595.84 (CUDA 13.2 support reported by driver). Fixed
Gemma4-12B FP8/SGLang, served `chromie-gemma4-12b`, model revision
`707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7`, 65536 context/cache and two requests.
ASR/TTS retain their models. Agent, SGLang, speech and headless Soridormi are running;
maintained-main restoration has NOT occurred. Verify health before resuming.
Agent `chromie-agent:bounded-stream-20260910`, image
`sha256:fd462a11e9f95617eaa10eb7ab79fc334888c89ee9721fffc013a76d54ad7be9`,
container `f3dec9267a3df211af9099ec80a766909d726c348f0030c31983d4662514b568`.
SGLang `chromie-sglang:bounded-stream-20260910`, image
`sha256:41fbd910662483a125184a00611029225ee102a928421eaeaec70ab27a844edf`,
container `a67606112fd19eb895a6be6d3e1a057d6771b9255bb6bb2bf60072a7863fbfdc`.
All 113 Agent/shared source files match the image. Runtime identity and source patch
bind the cohort; later documentation updates do not imply a rerun on a clean commit.

Evidence is local, not included in Git; transfer it separately across machines.
Under `.chromie/acceptance/`, read `stream-length-20260910/report.md`, its all-case
behavior-review.json, regression-replay/, source.patch, runtime-identity.json and
source-verification.json. Pre-change full baseline: `stream-baseline-20260910/`;
natural repeatability probes: `stream-natural-20260910/`. Earlier GA, GI provenance,
GI shape, Fast context/framing and stream diagnostics roots remain retained:
`ga-array-20260910/`, `gi-referents-20260910/`, `gi-followup-shape-20260910/`,
`fast-continuity-20260910/`, `fast-tagged-20260910/`, `stream-evidence-20260910/`.
Deep/skill native preparation in `decoder-shapes-20260910/` is not implemented.

## Next work and exact operational commands

The scoped repair is accepted; do not reopen it solely to increase an aggregate pass
count. Continue Issue #35 evidence closure. First read the full-cohort regressions
and prohibition-audit.md in the pre-change baseline. Freeze bilingual primary GI
positive/negative constraint contrasts and establish representability before any semantic edit. Investigate full-cohort variability;
do not infer that formatting fixes unsupported meaning. Keep the fixed model and
primary semantic ownership. No keyword semantic routing or second same-authority judge.

Canonical: `./scripts/run_tests.sh`, `python scripts/check_repository_policies.py`,
`python scripts/check_test_ownership.py`, `python scripts/check_docs.py`.
For a new immutable preview, copy the retained run-cohort.py into a fresh directory,
capture fresh identity, run the complete directory-discovered cohort, then collect
exactly one debug bundle and judge every case. Do not edit/rebuild/restart between cases.
Keep unsafe candidates in preview. Retain all failures, including mechanical passes
that fail semantic review, and update both delivery owners before commit/push.

Compose prefix: `docker compose --env-file .env.runtime -f docker-compose.yml -f docker-compose.sglang.yml -f .chromie/voice-runtime/compose.voice-mujoco.yaml`.
Use service names `chromie-llm`, `chromie-agent`, `chromie-asr`, `chromie-tts`.
Stop speech before replacing SGLang; restart it after model health. Never edit generated
`.env.runtime`. Capture with `python scripts/capture_runtime_identity.py --allow-dirty --orchestrator-env .chromie/voice-runtime/orchestrator.env --compose-override docker-compose.sglang.yml --compose-override .chromie/voice-runtime/compose.voice-mujoco.yaml --output NEW/runtime-identity.json`.
Historical recovery images/commands in HANDOFF.md are context, not current runtime claims.

## Historical iterations — superseded by the current resume point above

Earlier pending, runtime, HEAD and release statements below belong to their historical
iteration. The current section above is authoritative.


## Current resume point — promotion blocked by retained evidence

Active Issue #35; delivery branch `codex/ga-request-format`; pre-delivery baseline
`4dd7685d93d1bb530f7e186994497c8c7c7adc5c`. Owner authorized commit and push of
the completed repairs. Resume at the latest commit containing this checkpoint and
handoff. This is a development delivery; promotion remains blocked.
Remote delivery branch matched the baseline at preflight. Remote main advanced to
`ab5caeab`; this delivery neither merges into main nor qualifies that revision.
The Goal-driven single-authority architecture remains binding. Preserve unrelated
Soridormi edits. No model replacement, extra semantic judge or Host meaning repair.

Implementation: retained repairs cover GA decoder object shapes, GI visible-dialogue
location provenance and continuity shapes, complete required Fast Goal context,
SGLang two-frame decoding, and failed-stream evidence with schema property order.
The Fast context defect dropped a 1322+ character Goal snapshot through a 600-character
optional projection; the repair preserves semantic fields and fails explicitly on
required-context overflow. Decoder projection leaves original acceptance schemas
unchanged; omitted string-pattern/fractional-range hints address demonstrated native
grammar defects. This is mechanical repair, not full semantic qualification.

Automated verification: latest canonical gate passes 2319 tests / 368 subtests,
20 legacy tests and 140 benchmarks, including repository policies, static analysis,
documentation and test ownership. Latest focused diagnostics tests: 41 / 10 subtests.
Fast framing frozen exact packets improve 5/11 to 11/11 original-Schema-valid;
198/198 native framing contrasts pass. Fast context contrasts improve 4/12 to 12/12.
GI production-order replays improve 8/12 to 12/12; all 98 valid and 724 invalid
mechanical contrasts receive the intended decoder verdict. These counts are scoped.

Target validation: latest immutable full 51-case preview (framing Agent) has
28 mechanical passes and 19 reviewed acceptable initial previews; every case and
available raw call reviewed. Both continuation cases pass. Fifty completed Fast
streams are original-Schema-valid, but the 51st truncates and old success-only
logging omitted its request and partial output. Thus full stream integrity remains
open. GI: 53 valid; GA: 50 valid / 1 invalid; Deep: 3 invalid; skill: 2 invalid.
160 retained calls / 159 linked. Exactly one post-cohort bundle:
`/home/chromie/Downloads/chromie_debug_bundle_20260910_122434.tar.gz`.
Four deterministic reflex cases need execution evidence beyond preview.

The diagnostic candidate is deployed; 113 Agent/shared files matched at verification.
Final cleanup removes one extra EOF blank line in shared json_schema.py only;
the deployed code is behaviorally identical, with this byte-level difference recorded.
Its focused `contextless_turn_it_up` replay completes, but wrongly selects walking
for an ambiguous increase request; it does not reproduce or explain the original
2048-token truncation. A separate exact-request fault test changes only max_tokens
to 16 and proves one failed record retains exact partial output, request order,
length finish reason and output_truncated classification. No dispatch occurs in
that fault test. No full 51-case rerun of this diagnostics-only image is claimed.

Release readiness: blocked by semantic/safety errors (negative blink admitted,
ungrounded destination/velocity, wrong capabilities, omitted Goals, false promises,
resource meaning and continuity), Deep/skill contracts, the historical truncation,
and missing current-revision physical voice/default target-evidence closure.
Preview and schema validity do not establish provider execution or robot behavior.

## Current runtime and retained artifacts

RTX 5090, 32607 MiB, driver 595.84 / CUDA 13.2. Fixed Gemma4-12B FP8/SGLang,
served `chromie-gemma4-12b`, revision `707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7`,
65536 context/cache and two requests. Specialized ASR/TTS unchanged.
Agent tag `chromie-agent:stream-evidence-20260910`, image
`sha256:93a76fbf9c172c98ba098aedec300450629875273733cb53bcb510a3ac2196a4`,
container `e253f0e784d23e1763c3cccc7288ef97185495913bac8a61bcea7a4f91e1afa4`.
SGLang image `sha256:6f449f469487fe9f5d4565c2dfb14f62a08ed4f8b581681d3e3fd0bda6df7303`.
Agent, SGLang, ASR/TTS and headless Soridormi remain running; maintained-main
restoration has NOT occurred in this continuation. Verify health before resuming.

Raw evidence is retained locally and is not included in this Git delivery; transfer
these artifacts separately when resuming on another machine. The summary below
remains available from Git. Evidence roots beneath `.chromie/acceptance/`:
- `stream-evidence-20260910/`: latest gate, identity, source verification, natural
  focused replay and controlled failed-stream proof; read report.md first.
- `fast-tagged-20260910/`: latest full cohort, all-case review, ordered frozen
  packets, native grammar experiments, implementation equality and source patch.
- `fast-continuity-20260910/`: dropped-Goal diagnosis, focused proof and prior cohort.
- `gi-followup-shape-20260910/`: corrected production-order GI packets and cohort.
- `gi-referents-20260910/`: retained provenance repair; rejected ambiguity wording.
- `ga-array-20260910/`: GA decoder contrasts and primary-role qualification.
- `decoder-shapes-20260910/`: mechanical Deep/skill preparation, not implemented.

## Next work and commands

Read latest all-case review before selecting another semantic change. Reproduce the
natural failed-stream class with current exact logging; do not infer its historical
cause from the deliberate 16-token test. Use fresh artifact directories and runtime
identity. Freeze contrasts at the earliest responsible boundary; keep the fixed model.
Before another broad change or revision-level claim, run and judge one complete
immutable directory-discovered cohort, then collect exactly one debug bundle. Do not
edit source, rebuild or restart between cases. Keep unsafe candidates in preview.

Canonical checks: `./scripts/run_tests.sh`, `python scripts/check_repository_policies.py`,
`python scripts/check_test_ownership.py`, `python scripts/check_docs.py`.
Use `scripts/capture_runtime_identity.py --help` and the retained latest identity
capture/cohort commands to bind the next fresh directory. Compose uses generated
`.env.runtime`, `docker-compose.yml`, `docker-compose.sglang.yml` and
`.chromie/voice-runtime/compose.voice-mujoco.yaml`; never edit generated env directly.
Stop ASR/TTS before replacing SGLang, then restart speech after model health.
HANDOFF.md retains historical recovery commands; its current section overrides them.

## Historical iterations — not current runtime or resume instructions

The entries below retain earlier evidence and recovery commands. Pending statements
and current-service claims below apply only to their historical iteration; the current
resume section above and DEVELOPMENT_CHECKPOINT.md are authoritative.


## Latest continuation — GI decoder repair retained; Fast continuity under qualification

This section supersedes the earlier runtime-restoration and resume statements below.
Active Issue #35; branch `codex/ga-request-format`, HEAD `4dd7685d93d1bb530f7e186994497c8c7c7adc5c`, dirty candidate. No commit, push or promotion.
Fixed Gemma4-12B FP8/SGLang on RTX 5090 (32607 MiB), 65536 context/cache, two requests.

The retained GI continuity schema exposes the existing required object shape alongside
unchanged allOf constraints. Installed XGrammar preserved all 98 valid contrasts and
rejected all 724 invalid contrasts (previously accepted). Twelve production-order
packet replays improved 8/12 to 12/12 Schema-valid; this is not semantic qualification.
Initial logged-schema replays lost property order in the existing diagnostics and are
retained only as diagnostics; corrected builder-reconstructed packets are authoritative.
No GI prompt, formatting, model or semantic authority changed. Stable canonical gate:
2314 tests / 363 subtests, 20 legacy tests, 140 benchmarks; focused 159 / 97 subtests;
Level A 11 distinct cases. Evidence: `.chromie/acceptance/gi-followup-shape-20260910/`.

The immutable full 51-case preview completed: 23 mechanical, 17 reviewed acceptable
initial previews (previously 19 / 13). Every raw case reviewed; 159 calls retained,
158 linked, no decode errors. GI 52 Schema-valid raw calls, no Deep GI; GA 50 valid
and one invalid, no repair; both skill-selection calls and both Deep Planner calls
invalid. Fast contract and semantic failures remain. Exactly one bundle retained:
`/home/chromie/Downloads/chromie_debug_bundle_20260910_113254.tar.gz`.
Source stable throughout cohort. Four reflex cases remain preview-limited. These
counts do not establish complete semantic, execution, provider, voice or robot evidence.

Next reproduced boundary: in `user_probe_continue_recent_walk`, GI and GA preserve
`goal_dbc54fecb002ea74f55e`, but Fast receives `Active Goal continuity summary only: []`.
The actual snapshot is at least 1322 serialized characters; the optional 600-character
list projection drops it completely. Fast then asks which action to continue and its
wrong disposition fails Host validation. Context assembly and transport retain the
snapshot; planner prompt projection is the first wrong boundary.
The current repair projects complete Goal meaning, status, open gaps and update text
from active and recent snapshots, excluding snapshot diagnostics/task implementation
identity. It preserves entries and versions without interpreting them. A required 16K
character budget fails explicitly rather than deleting Goals or shortening meaning.
Frozen 12 mechanical contrasts improve 4/12 to 12/12; focused tests 152 / 7 subtests.
Full stable canonical gate now passes 2316 tests / 363 subtests, 20 legacy tests and
140 benchmark checks; Level A 11 distinct cases passes. All 70 Agent files match.
Complete immutable 51-case preview: 21 mechanical, 13 reviewed acceptable initial
previews (prior 23 / 17). All raw cases reviewed: 158 calls, 157 linked; GI 52
Schema-valid, GA 49 valid + 1 invalid, 50 Fast calls, three invalid Deep Planner
calls and two invalid skill calls. No Deep GI. Exactly one bundle:
`/home/chromie/Downloads/chromie_debug_bundle_20260910_115712.tar.gz`.
The continue probe now receives full Goal context and selects a ten-second walk,
but forbidden presentation_activity_id still fails Fast DTO. GI also supplies a
more specific outcome in this run, so model-output changes are not isolated causal
proof of the context patch. The duplicate continuation case passes both turns.
Repetition now has exact Fast wording but still fails GI/GA relationship. Thanks
second turn was not reached. Lost prior positives include inventory, three-second
gaze, quick/polite walk, heavy-rain query and joke binding; nod+hello and ten-second
walk recover. Forbidden blink is again admitted in preview; no physical execution.
Retain the projection repair as mechanically verified, not a whole-role promotion.

Next output-format investigation: Fast sends unconstrained text despite retaining
exact two-frame schemas in its prompt. Frozen 11 original streamed packets and
198 native framing/field contrasts are under `.chromie/acceptance/fast-tagged-20260910/`.
No production framing change yet. Candidate model/settings remain fixed. Read its
actual results before selecting implementation; grammar compliance cannot repair
invented motion, false promises, resource meaning or upstream ambiguity.


Current services run the Fast-continuity candidate: Agent image
`sha256:21204fbc06c253d10c25b598c4e63a5fe426d22032bc2d4415559825592f2154`,
SGLang image `sha256:6f449f469487fe9f5d4565c2dfb14f62a08ed4f8b581681d3e3fd0bda6df7303`.
Agent replacement for the new Fast projection completed. ASR/TTS and headless Soridormi
are running. Maintained-main restoration has NOT occurred in this continuation.
Preserve unrelated Soridormi edits. Follow the new iteration artifacts for exact
replacement identity and cohort results before using earlier restoration commands.


## Current continuation — GI location provenance repair; ambiguity still open

The Goal-driven single-authority architecture remains the target. Active Issue #35.
Existing candidate `codex/ga-request-format` at
`4dd7685d93d1bb530f7e186994497c8c7c7adc5c` retains the earlier uncommitted GA array
repair plus a new uncommitted GI location-provenance fix. No commit, push or promotion.
Maintained main is `01145332288857c415cff3d0a4a1fe7ffd9d0ccd`; running services are
restored to that line after testing, not to the dirty candidate. Fixed shared
Gemma4-12B FP8/SGLang on RTX 5090 (32607 MiB), 65536 context/cache, two requests;
ASR/TTS retain their own models. No final prompt, model or canonical DTO change.

Completed 2026-09-10 continuation has two distinct outcomes:

1. **Rejected wording experiment.** A frozen 24-case bilingual referent cohort misses
   all seven materially ambiguous cases before and after proposed wording. Two
   candidate primary calls identify missing referents, then the permitted fresh
   source-based Deep GI removes uncertainty without new grounding. The patch was
   removed, not retained as a claimed improvement. Nonempty unresolved is supported
   by the installed decoder; exact reference outputs also pass Schema and Host.
   The schema annotation was a hypothesis, not a confirmed inference cause: it
   travels in response_format rather than ordinary model messages. Broader GI
   primary/deep interpretation remains unqualified.
2. **Retained mechanical fix.** Location provenance incorrectly compared model values
   against whole raw context strings. It rejected a copied location substring from
   visible dialogue, while accepting exact values found only in metadata, suppressed
   or invisible history. It now reuses the same compact/bounded accepted dialogue
   projection shown to GI. Current-turn surface and typed non-history context checks
   remain; Host does not resolve or rewrite meaning.

| Actual owner / handoff | Material input / expected | Observed before → after |
|---|---|---|
| Admitted turn + dialogue projection | 去那边等我。; prior 这里说的那边是门口。 | Exact accepted dialogue appears in packet; correct |
| GI primary → Host | Model chooses location=门口 from supplied text | Same retained raw response; location choice is grounded |
| Location provenance validator | Accept copied contiguous visible surface | Whole-string comparison rejects → projected-dialogue substring check accepts; earliest defect repaired |
| Inverse history contrasts | 门口 only in hidden metadata/suppressed/old/truncated history | Raw-history acceptance → rejection; no new semantic author |
| Downstream | Role probe only | Planner/physical dispatch not invoked; whole-role meaning separately reviewed |

Fourteen frozen mechanical contrasts improve 5/14 → 14/14. They cover visible
user/assistant text, exact values, typed context, absent context, suppressed turns,
metadata, wrong wire field/role, last-six history, 260-character turn truncation,
1800-character aggregate projection, and translated surfaces. The exact originally
rejected raw response now passes the complete Host path with no further model call.
A first oracle wrongly assumed a six-entry projection overflow; inspection corrected
it to a fitting positive plus an actual omitted-entry negative, and both versions
were rerun. Original evidence is retained, not overwritten.

The restored-prompt 24-case model rerun has identical primary packets in all 24.
The specific location rejection is fixed; another run emits whole-turn intensity
and fails a different validator. Enumerated dimension checks remain 16/24, **not**
16 full semantic passes. Binding roles, source-language conservation, prohibition
representation and ambiguity remain wrong in some outputs. Do not claim the model's
meaning became correct because the validator accepted one grounded location.

Complete fixed-source 51-case live-text preview: 19 mechanical passes, **13 reviewed
initial-preview passes**, versus prior 24 / 16. All 51 raw cases reviewed. Four prior
reviewed positives are lost: capability inventory (GI changes can-do to will-do),
blink+joke and nod+hello (wrong communication roles/source language), continuous
weather (missing pending communication). Colloquial five-second walk is positive
again. GA raw Schema remains clean: 47/47 primary, zero repairs; one fewer invocation
because another GI duration-provenance failure prevents downstream work. 154 raw
calls retained, 153 linked, no JSON-log decode errors. GI Deep ran once in the
full cohort for Tianxin; skill selection primary/repair and all three Deep Planner
calls fail Schema. Do not infer causation from changed model outputs; the mechanical
location patch does not alter primary packets. Whole candidate promotion is rejected.

Hard blockers remain: unknown 那边 → GI unresolved=[] → Fast invents two-second
normal walk_forward → Host admits preview; contextless volume → unrelated velocity.
Current prohibited-blink case types 不要 as intensity and Fast emits count=0, rejected
by argument validation; prior negative-polarity/forbidden-blink admission remains
retained as a distinct unsafe workflow. Reminder promises, wrong capability meaning,
GI second-turn DTO/source provenance, resource classification, and Fast/Deep contracts
remain open. No physical action, speaker output, live microphone or completed provider
Evidence was run. Four reflex cases are limited by preview. Level C here means
initial live-model preview only, not voice/target closure or release readiness.

Validation: focused 77 tests / 25 subtests; canonical gate 2313 tests / 337 subtests,
20 legacy tests, 140 benchmark checks, policies/docs/ownership/pinned static analysis
passed. Level A natural_uncertainty_handling 6/6 and robust_intent_understanding 8/8
(13 distinct) passed. Final document checks also pass. No new document, environment
variable or architecture term; the existing validator and interaction contract own
the change. Do not claim all prompt/semantic requirements passed.

Evidence root `.chromie/acceptance/gi-referents-20260910/` (local, not uploaded).
Start with `report.md`, `behavior-review.json`, `location-before.json`,
`location-after.json`, `same-output-host-replay.json`, `location-packet-comparison.json`,
and `before-semantic-review.json` / `after-semantic-review.json` /
`location-after-semantic-review.json`. Exact role packets live in `before/`, `after/`
(rejected wording), and `location-after/`; full transactions in `reviewed-cases/`.
Semantic corpus digest `3a13f6f523b99ec7f9228cc2cfa2665a292c26851beecf6d02aac0ac9ad521c3`;
mechanical digest `a4cbfa8ed64143deded119b6610b056a2cf9eb81de20d9977dbd2f0e3e4161fd`.
Setup failures (wrong service URLs, history content/text mismatch, invalid Level A
mode) and stopped preliminary runs are preserved and excluded from qualification.

Exactly one bundle after the complete cohort:
`/home/chromie/Downloads/chromie_debug_bundle_20260910_105727.tar.gz`.
Cohort exit 1, bundle exit 0, source stable; command and patch are retained in
`cohort-command.json`, `cohort-exits.json`, `source.patch`, `runtime-identity.json`.
Tested source-tree SHA256 `4c8db07f7f2e1608f5025a0418f824ae3fba8ad32a481706bf1cdadac46ff88e`
precedes final documentation updates. All 70 packaged Agent source/prompt files match.
Candidate Agent image `sha256:a72c71c573c2534c2d8ee86b6ee6bcafa69a1dcffdc2f04580f4fe4830e62a94`
is retained as `chromie-agent:gi-location-provenance-20260910`; candidate SGLang remains
`chromie-sglang:ga-request-format` (`6f449f469487fe9f5d4565c2dfb14f62a08ed4f8b581681d3e3fd0bda6df7303`).
Restoration uses main Agent `chromie-agent:fast-numeric-guard-20260909`
(`63cabb1e5e863b204aa97e86acbb2f11eb2568dcaa18db2e9fffef4382d4cac7`) and SGLang
`chromie-sglang:guard-baseline-20260909`
(`2f425788c02f2502fd5541455f4917819759352b68e8b8b987bee750204c11ac`). Final observed
health/source verification is in `restoration-verification.json`. Temporary headless
Soridormi services are stopped; unrelated Soridormi edits remain intact. `.env.runtime`
was not edited. No controlled performance comparison is claimed.

Next: diagnose the still-failing primary/deep GI ambiguity transaction using the frozen
referent contrasts, with explicit source/Context evidence and independent validation
of WHAT versus missing execution information. Preserve the two primary→Deep uncertainty
loss traces. Do not retry the rejected wording as a success, add a semantic judge,
copy primary uncertainty into Deep by Host policy, or introduce phrase routing. Keep
Fast negative-polarity and complete positive-Goal coverage blockers visible. A new
repair needs focused proof and a new complete cohort before revision-level claims.

Resume: inspect `git status --short`, this handoff and evidence; then use required
`python scripts/check_repository_policies.py`, `./scripts/run_tests.sh`,
`python scripts/check_docs.py`, `python scripts/check_test_ownership.py` after changes.
For live preview, rebuild intended source, verify packaged files, capture a fresh
runtime identity, and reuse the retained command with a new identity/evidence directory.
Never reuse identity across image changes. Stop ASR/TTS before SGLang replacement,
then restart speech after model health. Compose order remains `.env.runtime`,
`docker-compose.yml`, `docker-compose.sglang.yml`,
`.chromie/voice-runtime/compose.voice-mujoco.yaml`.

Earlier GA proof remains in `.chromie/acceptance/ga-array-20260910/`: 2447 grammar
cases, valid acceptance 229/229 preserved, invalid acceptance 196→13; 18/18 role
primary passes and the earlier complete 51-case review. Do not repeat that diagnosis.


## Delivered migration baseline — SGLang/Gemma, before numeric guard

Active Issue #35; pre-delivery base `67d2b2f867064d59c21c075a8ad0108abc3250da` on `main`.
Expected resume revision: the latest delivery commit containing this checkpoint and handoff.
RTX 5090 auto-detection now selects shared Google Gemma4-12B online FP8 on SGLang,
served as `chromie-gemma4-12b`: 65536 context/shared cache tokens, two request slots,
priority preemption, 0.125 sliding/full cache ratio, and Host speech leases.
ASR SenseVoice int8 and TTS CosyVoice3 0.5B remain specialized. Laptop unchanged.
Normal launcher startup passed, including unplayed zh/en/mixed TTS warmups. All four
services remain healthy; no host Orchestrator/microphone or physical effects were run.

Build owner `llm/sglang/Dockerfile` pins the upstream image and repairs the reproduced
missing `lm_head_is_tied` constructor field. `docker-compose.sglang.yml` overrides the
existing `chromie-llm` owner; the obsolete Qwen validation overlay was removed. SGLang
rejects colons in served aliases, so the profile uses the new alias for the same weights.
Provider-aware startup, health, diagnostics and provenance validation are implemented.
No prompt/Schema/semantic-authority changes. Inventory remains 381 environment keys.

Evidence root `.chromie/acceptance/sglang-gemma12b-migration-20260909/`.
Read `migration-report.md`, then `behavior-review.json` and `reviewed-cases/`.
The real 23,919,549,408-byte checkpoint SHA256 was verified (`model-verified.json`).
Real weights occupy 13.68 GiB; KV allocation is 3.50 GiB. No dummy-weight timing claim.
Provider protocol passed. Saturated two-slot preemption passed 3/3 (foreground first
output 74.69–77.90 ms). Speech pause/resume/revocation/recovery passed 3/3 with generated,
unplayed audio. Actual GI median was 4.35 s; short canaries are not full-workflow latency.

The immutable 51-case preview completed: four mechanical passes, zero fully qualified
transactions. Terminal buckets: 37 GA Schema/DTO, seven Fast contract, one GI duration,
two preview-reflex limitations, four mechanical passes rejected by review. Nod2/blink1
planned correct actions but GA lost count bindings; B. merely echoed; capability inventory
was not answered. No Fast input-budget failures. Earlier shared-Gemma 0/51 was Ollama Q4,
not SGLang; FP8/64K versus Q4/32K is not a controlled backend-only comparison.
All 49 raw GI results passed Schema; all 96 raw GA results violated submitted Schema.
Offline proof: pinned XGrammar permits the exact invalid GA output through unsupported
multi-option allOf; installed LLGuidance rejects contains constraints. These are retained
integration gaps, not proof of intrinsic Gemma incapacity. Host binding conservation after
GA repair also remains open. Preserve SGLang selection; do not silently weaken contracts.

Canonical gate passed 2303 tests/268 subtests, 140 benchmark and 20 legacy tests; Level A
45/45. Later final logs bind diagnostic/documentation consistency checks separately.
Runtime identity: `runtime-identity.json`; complete raw calls: `raw-calls.jsonl` (194).
Exactly one post-cohort bundle:
`/home/chromie/Downloads/chromie_debug_bundle_20260909_141505.tar.gz`.
Owner authorized commit/push of this migration, followed by GA root-cause repair.
Physical voice and default target closure remain open.

### Exact runtime and resume

Google revision `707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7`; source weight SHA256
`5a84cb313260ac447237b890387116dfa8682e49a6b44bc585ae8353abbff18d`.
Deployed image ID `sha256:2f425788c02f2502fd5541455f4917819759352b68e8b8b987bee750204c11ac`.
Normal startup log `startup-alias-fixed.log`; rejected-name log `served-name-failure.log`.
The complete model is cached in `hf_cache/hub/models--google--gemma-4-12B-it/`.
Use the existing cache; no background downloader remains. Historical paused partial
Ollama/BF16 download files are not active and are not the deployed artifact.

```bash
./scripts/start_chromie.sh --build --no-orchestrator --keep-services
./scripts/verify_runtime_profile.sh
```

`cohort-command.json`, `protocol-command.json`, `contention-command.json`, and
`preemption_probe.py` retain exact probes. Use new evidence directories for a rerun;
never overwrite this frozen baseline. Capture a new runtime identity after implementation
changes. The existing 51-case run was bound to `runtime-identity.json`; subsequent changes
only correct launcher diagnostic text and documentation. No service rebuild was needed.

Historical sections below describe earlier deployments, not the current selection.

## Latest 2026-09-09 — shared Gemma RTX 5090 worktree

No new commit. Source remains `67d2b2f867064d59c21c075a8ad0108abc3250da` with owner-requested
profile/test/configuration/status edits. Every RTX 5090 reasoning role now uses `gemma4:12b`;
one resident runner, 32768 context. ASR SenseVoice and TTS CosyVoice3 models are unchanged.
This topology is implemented, not behavior-qualified: all 51 preview cases failed (see report).
Canonical gate passed 2302 tests/268 subtests + 140 benchmark + 20 legacy; Level A 45/45.

Evidence root `.chromie/acceptance/gemma12b-fair-rtx5090-20260909/`.
Read `comparison-report.md` first, then `shared-gemma-review.json` and `reviewed-cases/`.
One bundle: `/home/chromie/Downloads/chromie_debug_bundle_20260909_121448.tar.gz`.
`ollama-q4-runtime-identity.json` binds the frozen baseline worktree before later docs edits.
`recovered-llm-calls.jsonl` has 62 calls; one interleaved Uvicorn fragment removed; original
bundle unchanged. `tests-final.log` is the successful canonical gate (earlier attempts failed).

Fair timing is blocked in the tested setup: native SGLang GGUF loader has no
`gemma4_unified` mapping; BF16 placeholder-weight allocation with ASR/TTS resident failed
at fraction 0.80 and yielded only 2017/32768 cache tokens at 0.99. These are allocation
preflights, never model quality or throughput tests. No matched BF16 inference was run.
Both probes stopped; Ollama shared Q4 model is warmed and all four normal services healthy.
Downloads paused; partial cache files retained. Google artifact revision is
`707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7`; expected safetensors SHA256
`5a84cb313260ac447237b890387116dfa8682e49a6b44bc585ae8353abbff18d`.
Ollama BF16 blob is `a01bdd1527e5daebb520cbb570d32e4074bb94df263743ae733a8ef75bc4778d`.
Only one full norm tensor has been compared (3840 exact matches), not all weights.

Resume downloads only after choosing a viable matched configuration:
`docker exec chromie-llm ollama pull gemma4:12b-it-bf16`.
HF: use cached image `59e11312666e` with `/home/chromie/github/chromie/hf_cache` mounted
to `/root/.cache/huggingface`, and `huggingface_hub.snapshot_download` for the exact Google
revision above (allow JSON/Jinja/model/safetensors/README files). The prior ephemeral
`chromie-gemma-download` container was stopped and removed.
`replay_gi.py` and `gi-freeze.json` retain 24 identical primary GI packets; invoke with
`--provider ollama|sglang --model <verified-id> --url <loopback-base> --output <fresh-dir>`.
Do not claim complete GI qualification from that primary-only probe; permitted depth
delegation/repair and downstream all-role behavior require their own complete transactions.
No performance claim while downloads or unrelated GPU workloads run. Rebind source/runtime
identity after final docs edits and before any new aggregate. Keep one bundle per aggregate.

## 2026-09-09 active handoff — RTX 5090 provider comparison

Owner asked whether to switch to SGLang. Recommendation: pursue its demonstrated scheduling
benefit, but do not promote the current all-role 9B profile. Maintained Ollama is restored;
SGLang is stopped/cached. No source/prompt/model-file changes, commit or push. Source main
`67d2b2f867064d59c21c075a8ad0108abc3250da` with existing documentation-only changes;
comparison timing worktree hash `d95d8948f347f83f3b73fa9b46d62706311846669cd1133a403c0bf70dcb22be`.

Evidence root: `/home/chromie/github/chromie/.chromie/acceptance/sglang-switch-rtx5090-20260909/`.
Read `switch-decision.md` and `comparison-review.json` for all 51 case decisions, exact
module I/O and the rejected mechanical pass. Three trials/provider: median GI first output
19403 ms Ollama vs 37 ms SGLang; foreground window 19882 vs 209 ms; speech first audio
3504 vs 2180 ms. SGLang finished foreground before Deep and resumed after both speech
leases in 3/3 trials. Maximum observed VRAM 25314 vs 31403 MiB (32607 MiB device).
These are synthetic canaries/unplayed TTS, not physical voice or release percentiles.

Frozen 51-case planning preview: runner 1/51 SGLang vs 0/51 earlier Ollama. Review accepts
zero complete transactions. Candidate terminal buckets: GI duration provenance ten,
Fast input budget eight, output truncation eleven, contract six, GA contract thirteen,
preview-only reflex restrictions two, mechanical pass one rejected on review. Correct
validation rejection is not successful behavior. Original runner summaries remain unchanged.
All scenario files match the Ollama baseline; `cohort-match.json` records each hash check.

Critical case: `shake_head_twice_plain_request`, turn c70cf61a. GI primary and source-only
Deep invent actor ambiguity; Deep also confuses robot self-identity with the human. GA
primary emits malformed count/entity bindings; its repair drops them to bindings=[] and
Host accepts the Goal. Concurrent Fast emits execute/complete shake_no with unresolved=[].
Host constructs an executable interaction despite retained upstream unresolved meaning.
Preview prevents dispatch; the mechanical oracle checks capability/count and misses this
conservation/authority failure. This is a reproduced gap to fix before execution, not a pass.
Look-then-blink also loses duration on SGLang where Ollama retained it (with other errors).
Common model errors and new downstream reachability must remain separate from regressions.

Exact candidate: SGLang 0.5.19/CUDA 12.9.2; Qwen/Qwen3.5-9B BF16 safetensors revision
c202236235762e1c871ad0ccb60c8ee5ba337b9a, served chromie-qwen35-9b-sglang. 32768 context/
shared cache, two requests, ten Mamba slots, .80 memory fraction, breakable prefill graphs.
Candidate fingerprint 5298cb5d35f866eeb5f7ff1a3d52696ee16b3fe4f4d2d384ee232d6fbe28e545.
Ollama 0.32.14 used maintained Gemma4-12B GI/GA/Deep and Qwen3.5-9B Fast, Q4_K_M weights,
32768 context, q8_0 KV. Different artifacts/topologies prevent scheduler-only attribution.
See `*-series-command.json`, `*-contention-summary.json`, `sglang.env`,
`sglang-runtime-command.json`, `sglang-runtime-identity.json`, `ollama-models.json` and
`ollama-cuda-maps.txt`. CUDA was initially unknown in Ollama commands; maps supplement it.

Initial identity capture rejected dirty documentation; the shell nevertheless started a
cohort. It was interrupted/excluded and bundled once:
`/home/chromie/Downloads/chromie_debug_bundle_20260909_114037.tar.gz`.
Then capture used --allow-dirty and explicit candidate services/Compose files. The unchanged
replacement completed and was bundled once:
`/home/chromie/Downloads/chromie_debug_bundle_20260909_115034.tar.gz`.
`sglang-must-pass-preview-bound/` is the complete run; `sglang-must-pass-preview/` is excluded.
`recovered-sglang-calls.jsonl` reconstructs interleaved records from that retained Agent log.
GA/Fast raw content lives in provider_response.choices[0].message.content, despite the generic
raw_model_output field being null. Truncated Fast calls lack a complete retained raw result.

The unchanged source passed the earlier full gate (2302 tests/268 subtests, 140 benchmark,
20 legacy Agent) and 45 Level A cases. This comparison passed 14 focused SGLang tests.
Soridormi remains running headless at port 8000/mcp on pre-existing dirty revision
 d03c7e3b7da73b777b1e923044340fa9c8d66fa7; do not overwrite its skill/config/test edits.
Earlier same-host Ollama baseline: `.chromie/acceptance/resume-67d2b2f8-rtx5090-20260909/`.
Prior laptop comparison directories below are absent on this host.

Next: reproduce c70cf61a conservation/unresolved admission, then shared full Fast payload
preflight. Validate a role-compatible model/profile and actual Host voice continuity before
promotion. No semantic host rewriting or global-authority change is proposed here.
Reproduction commands are retained as structured arrays in `*-series-command.json`;
use fresh output paths. Start candidate from the recorded SGLang Compose env only after
unloading Ollama. Generate the opt-in validation profile, warm services, capture with the
actual service list and --allow-dirty only when truthful, then run general abilities with
--mode live-text --stage must_pass and that identity. Collect once after each full cohort.
Do not reuse old identities or run physical effects from this preview evidence.

## Earlier 2026-09-09 handoff — engineering repairs and paired runtime evidence

Repository `TimeTreker/chromie`, `main`; pre-delivery baseline
`759b5e062cd43ac2cb919e4ca587a682ca673eee`. Resume from the delivery commit containing
this handoff and checkpoint. The owner authorized commit/push to remote main. No runtime
promotion is included: the current candidate shows additional behavior differences, while
existing common LLM deficiencies remain separate future model/LoRA work.

### Delivered changes and causal boundary

GI schema order contradicted its prompt: an ordered decoder could not emit duration after
direction. Sorting the existing property set after context additions fixes that mechanical
contract without changing authority, meaning or model. The v2 primary screen fixes oracle
unit/ambiguity rules, source-span coverage, reference validation, raw retention and completion
integrity. The 32K shared-cache limit is now a supported qualification Compose input instead
of an ignored private override. Earlier checkpoint history was consolidated to restore its
reviewed documentation limit. Detailed actual module I/O, root causes, containment and
remaining inference differences are in
[accelerator evidence](docs/ACCELERATOR_LATENCY_EVIDENCE.md#2026-09-09-contract-repair-and-responsiveness-comparison).

Full gate passed **2302 tests, 268 subtests, 20 legacy Agent tests**, two warnings, plus
140 benchmark tests. Focused set before the final completion-integrity test: 115 tests and
18 subtests. General-ability Level A: robust intent 8/8, composable actions 5/5. All 1496
existing daily-life references still validate. Final documentation/policy/diff checks follow
these documentation updates; no live voice or release closure is implied by local tests.

### Paired evidence

Root: `/home/chromie/github/chromie/.chromie/acceptance/sglang-contract-comparison-20260909/`.
Both complete 24-case GI runs and both three-trial contention series used one source digest:
`fc0d5a0b425f759af72c34fa2bfda0eb1555dbc38e5e1992940331eb63227cb9`.
Later changes add the already-tested cache cap to Compose, defensive grader checks/tests,
and documented post-batch accepted-variation review; original inference reports are intact.
The primary message, ordered schema, temperature and budget match per case. Production
`interpret_goal` made 24 SGLang and 32 Ollama calls: eight Ollama cases invoked source-only
Deep because unresolved was present. Confidence alone never triggers Deep.

Key artifacts:

- `decoder-order-proof.json`, `order-fixed/`: compiled grammar proof and full old-screen rerun.
- `complete-sglang/`, `complete-ollama/`: frozen manifest, raw requests/responses, Schema/Host
  outcomes, per-case decisions, latency, runtime identity and stable-source summaries.
- `paired-packet-audit.json`, `post-batch-rubric-review.json`: matching inputs and explicit
  post-batch review. Mechanical counts remain 2/24 SGLang and 4/24 Ollama; nominal passes
  still require semantic review. No candidate response was repaired.
- `fast-sglang/`, `fast-ollama/`, their `*-summary.json` and `*-command.json`: three trials
  each. Fast GI median 91.294 ms vs 27473.888 ms; complete foreground window 279.363 ms vs
  27686.594 ms. These are synthetic workload timings, not full voice-turn measurements.
- `ollama-identity.json`, `ollama-loaded-cuda.txt`: exact Ollama identity; its command recorded
  CUDA unknown, and supplemental process maps prove loaded runtime 13.0.96.
- `maintained-compose-command.json`, `full-gate.log`, `focused.log`, `abilities.log`,
  `daily-life-reference-validation.log`: rendered resource command and source validation.

The current checked-in v2 scenario tree is
`7b233a6647f20c7c453e6606f70cfeae47f6a592067e8c5c93735d17f2b156b5`;
the inference snapshot tree was
`b434ce62a0b7a55eb08c1a7b1af0d9da1090c6691cccc2d29af31bc264c80c67`.
The difference accepts valid transfer wording/direction translation and is explicitly reviewed
without rewriting or silently rescoring old reports. Historical v1 is unchanged.

```text
SGLang: 0.5.19 / CUDA 12.9.2
image digest: sha256:59e11312666e1c5c155210ea335589b91daa0d70848521b390b93b1b1e8fb0ef
model: cyankiwi/Qwen3.5-4B-AWQ-4bit
revision: ef85d23bebaba87b3c4672ba11c449c79dbdb23e
upstream Qwen revision: unpublished/unknown
weights SHA256: 902477edf53bc6768bd1f212dd1866856fd5a0627def06887780c95900ffb013
format: compressed-tensors AWQ W4A16 group32, BF16 activation/KV
served name: chromie-qwen35-4b-awq-sglang
context/shared cache: 32768/32768; requests: 2; Mamba: 10; fraction: .80
prefill graphs: disabled; decode graphs retained
Ollama: 0.33.2; qwen3.5:4b; GGUF Q4_K_M; one request; q8_0 KV
image digest: sha256:020e4134285e2ef4d8fd801234176de3b4faadc992a3eb06c8e66a2f9d4c4ba2
model digest: 2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd
TTS: ws://127.0.0.1:5000, chromie_mixed, generated audio not played
```

### Operational state and resume

Ollama and TTS are healthy/running; SGLang is stopped to avoid concurrent model residency.
Agent was not started/promoted. SGLang's stopped container/cache and all private raw evidence
remain local. Different quantized artifacts mean this is a deployment comparison, not isolated
scheduler-versus-model causality. Do not hide concrete modality/sequence regressions, and do
not require all common model errors to disappear before further engineering work.

For resource reproduction, use the existing `docker-compose.sglang-qualification.yml` with
the pinned image/model/revision above, warmed resident TTS, prefill disabled, .80 fraction,
32K context, two requests, ten Mamba slots and `SGLANG_MAX_TOTAL_TOKENS=32768`.
Stop/unload Ollama first; do not run both full model pools on this laptop. The rendered
`maintained-compose-command.json` records the exact argument set. No `.env.runtime` edit
was made. `AGENT_LLM_PROVIDER` remains Ollama; the existing validation bridge is opt-in.

The local `compare_gi.py` and `run_series.py` reproduce the retained comparison; they are
private instrumentation, not new maintained APIs. Use fresh output directories and capture
new runtime identities; do not overwrite this run. The maintained primary screen is
`scripts/qualify_inference_provider.py --goal-interpreter-probe`, defaulting to the v2 manifest.
It is primary-only; the full comparison used the production GI entrypoint separately.

Bundles (local, not uploaded by Git):
`/home/chromie/Downloads/chromie_debug_bundle_20260909_060924.tar.gz`,
`/home/chromie/Downloads/chromie_debug_bundle_20260909_061242.tar.gz`,
`/home/chromie/Downloads/chromie_debug_bundle_20260909_061915.tar.gz`,
`/home/chromie/Downloads/chromie_debug_bundle_20260909_062218.tar.gz`.
Earlier resource/OOM artifacts remain under
`.chromie/acceptance/sglang-laptop-quantized-20260909/`; its bundle paths are retained in
accelerator evidence. Copy private artifacts explicitly when changing machines.

Next is owner-directed model/artifact work, followed by matched no-degradation checks and
actual Agent/Host foreground, speech and interruption continuity before changing defaults.
Keep all canonical validation and supervised physical-evidence boundaries intact.

## Historical 2026-09-09 BF16 laptop resource boundary

This historical section is superseded by the active quantized handoff above. Its original base was
repository `TimeTreker/chromie`, branch `main`, base
`7f9d1c019b5be97c664a3a26d88ae00f1376b459` plus the checkpoint patch that contains this text.

### What is already settled

- Keep the Goal-driven single-authority architecture. GI owns WHAT; Planner owns HOW; GA owns Goal
  continuity; runtime/provider owns effect truth; provider scheduling owns only operational compute.
- Keep Ollama as the maintained production/control path. SGLang is still a candidate provider.
- RTX 5090 provider evidence already proved priority/preemption, presentation lease, interruption
  revocation, reacquisition for replacement TTS, and Deep continuity with protocol 5.
- The RTX 5090 SGLang Qwen3.5-9B production-shaped GI semantic cohort passed only 1/16. Treat that
  model-role promotion as rejected; the correct Host fail-closed validators must not be weakened.
- Do not infer semantic quality from the RTX 4090 Laptop Qwen3.5-4B run described below. It is a
  resource canary only.

### RTX 4090 Laptop measured state

The operator switched to the 16 GB RTX 4090 Laptop and kept CosyVoice on the same GPU. The first
TTS restart loop was a container-network proxy error, not CUDA: the host shell exported
`127.0.0.1:7897`, which addresses the container itself. Using
`host.docker.internal:7897` made CosyVoice healthy with zero restarts. The qualification compose in
this patch now exposes the same proxy/offline contract permanently.

With TTS resident, exact SGLang canary identity:

```text
image: lmsysorg/sglang:v0.5.19-cu129
model: Qwen/Qwen3.5-4B
revision: 851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a
served name: chromie-qwen35-4b-sglang
weights: HF safetensors, BF16, unquantized
context_length: 32768
max_running_requests: 2
max_mamba_cache_size: 10
```

Measured sequence:

```text
mem_fraction_static=.70
  weight load: 8.62 GB
  result: fail before KV pool; SGLang minimum viable fraction > .826

mem_fraction_static=.90, default prefill graph
  Mamba ~= .53 GB
  KV = 5,091 tokens
  result: fail during prefill CUDA-graph capture OOM

mem_fraction_static=.90, prefill graph disabled
  decode graphs remain for bs=1,2
  SGLang healthy + TTS healthy
  KV = 5,091 tokens
  total GPU ~= 15.9 / 16.4 GiB

same run + --language-only
  multimodal loading still initialized
  0.10 GB multimodal sizing reservation remained
  weights stayed 8.62 GB
  KV stayed exactly 5,091 tokens
  result: no useful memory gain; do not retain this flag
```

The Numba `inkling` warning (`Numba needs NumPy 2.4 or less; got 2.5`) is an ignored optional
multimodal-processor import warning, not the current blocker. Do not downgrade NumPy merely to
silence it.

### Current decision / do-not-do list

The laptop proves **physical co-residency, not a deployable cognitive topology**. 5,091 tokens is
below the maintained GI 16K request and far below other 32K roles.

Do not:

- run protocol-5 and call it product evidence with this 5K pool;
- reduce `max_running_requests` to 1 and thereby remove the foreground-vs-Deep objective;
- shrink semantic contracts, source provenance, or Host validators to fit VRAM;
- add model-specific semantic repair;
- promote Qwen3.5-4B or Qwen3.5-9B in model lock / Agent profiles from these results;
- keep `--language-only` as a supposed memory optimization;
- copy `.90` or disabled prefill graphs blindly to a future quantized model—the new artifact must
  be resized from its own measured pre-load/weight/pool facts.

### Exact next work

The next comparison target is a **quantized SGLang-served model/artifact** appropriate to the
16 GB shared-GPU laptop. Hold these requirements fixed:

```text
CosyVoice resident and healthy
two simultaneous model requests
priority/preemption enabled
32K target context topology (GI must at least clear 16K)
typed non-thinking / structured-output transport
exact source model + revision + quantization + runtime identity retained
```

First prove resource fit only. Do not run or optimize semantic prompts while the engine cannot
retain the required context. Once a quantized candidate retains a production-sized pool:

1. run one foreground-under-Deep provider canary;
2. run one protocol-5 presentation lease/revocation round-trip with TTS;
3. run the frozen production-shaped 16-case GI semantic cohort with the prompt/Schema/Host
   transaction unchanged;
4. only if semantic failures cluster narrowly at an evidenced prompt/profile boundary, optimize
   that owner and rerun focused + full cohorts;
5. only after GI qualification proceed to Fast/Deep Planner and real Agent/Host end-to-end work.

### Patch/application gate

This patch intentionally does **not** add a laptop SGLang Agent overlay. It only makes
qualification infrastructure reproducible and records the checkpoint.

After apply:

```bash
python3 scripts/runtime_configuration_inventory.py
python3 scripts/runtime_configuration_inventory.py --check

python3 -m pytest -q   tests/test_sglang_qualification_compose.py   tests/test_sglang_runtime_integration.py   tests/test_runtime_configuration_inventory.py

python3 scripts/check_repository_policies.py
python3 scripts/check_docs.py
git diff --check
```

Commit the regenerated `config/runtime_configuration_inventory.json` together with the patch
changes if the inventory generator modifies it.

## Historical handoff retained for provenance

Audience: the project owner or coding agent resuming the current Goal-driven
single-authority focus, deployed Planner qualification, and current-revision
evidence closure for Issue #35.

Owner: project owner. Current source, tests, retained artifacts, this handoff,
and `DEVELOPMENT_CHECKPOINT.md` override chat history.

## Repository and working state

- Repository: `https://github.com/TimeTreker/chromie.git`
- Branch: `main`
- Pre-delivery base: `46b6fe90a36179e63da36f086ac2b04ed8e7b3c1`
  (`main == origin/main` before this continuation).
- Expected resume revision: the latest normal `main` commit containing this
  handoff and `DEVELOPMENT_CHECKPOINT.md` after the authorized fast-forward push.
- Delivery target: fast-forward `main` to `origin/main`, then verify the remote ref.
- Active Issue: [#35](https://github.com/TimeTreker/chromie/issues/35).
- 2026-09-06 transaction-fidelity continuation: A01–A06 are source-closed in the current worktree. The next evidence gate is a clean checkout with pinned dependencies running `./scripts/run_tests.sh` and recording the full pytest collection/pass counts before any model/profile promotion.
- Scope: deliver the transport, warm-up, scenario, test, status, checkpoint,
  and handoff changes listed below in one revision.

Changed paths:

```text
agent/app/clients/ollama_client.py
config/runtime_exception_boundaries.json
docs/CONFIGURATION.md
docs/STATUS.md
scripts/warm_ollama.sh
scenarios/general_ability/must_pass/speech_identity_latency/standalone_greeting_one_natural_reply.json
tests/test_general_ability_acceptance.py
tests/test_ollama_client.py
tests/test_runtime_reliability_stage4.py
DEVELOPMENT_CHECKPOINT.md
HANDOFF.md
```

## 2026-09-06 transaction-fidelity continuation

The archive audit found six implementation mismatches without changing the target authority architecture. The current worktree removes live GA semantic repair, makes terminal Fast limitations/refusals final unless canonical state materially changes, validates request-specific early speech before release, switches the main test tree to pytest collection and migrates stale hidden tests/scenarios, makes authoritative GI Responsibility projection lossless in both GA prompt paths, and reconciles completed GA commit truth into downstream error results.

Focused evidence retained in this work session: PR7 71 passed plus 2 subtests; A05/A06 focused 153 passed plus 2 subtests; migrated hidden-test focused set 94 passed plus 2 subtests; Level-A `multi_goal_daily_life` 10/10; one broad pytest partition 475 passed plus 50 subtests. Another broad partition exceeded this execution environment's command timeout, so this handoff does **not** claim a complete canonical gate. Run the pinned full gate on the destination checkout before delivery/promotion.

Next commands after applying the patch:

```bash
python -m pip install -r requirements-test.txt
./scripts/run_tests.sh
python scripts/general_ability_acceptance.py --mode level-a --ability-class multi_goal_daily_life --no-write
git diff --check
```

## What was reproduced

The exact live greeting did not fail because Goal Interpretation misunderstood
it. On the current RTX 4090 all-Qwen profile, the observed workflow changed as
successive earlier boundaries were repaired:

1. Exact microphone session `fe7a5819`: ASR produced `你好。`; GI returned a
   correct greeting speech Responsibility in about 1.94 s; GA and Fast both
   timed out near 60 s with no output. The session ended before playback.
2. Direct probes showed current Ollama 0.33.2 `/api/generate` with
   `think:false` emitted no bytes before timeout, even for a tiny request.
   `/api/chat` completed immediately, including structured JSON and streaming,
   with no thinking field. GI already used `/api/chat`; generic Agent semantic
   roles used `/api/generate`.
3. After the Agent `/api/chat` repair, a focused greeting still timed out because
   the resident Qwen runner was 16K while GA/Fast requested 32K. An identical
   direct 16K chat completed immediately. The old warm-up had used the broken
   endpoint and had not established production context residency.
4. After restarting Ollama and running the repaired `/api/chat` warm-up, the
   runner reported context length 32768 and direct 32K chat completed. The exact
   greeting then reached GI, GA, and Fast, exposing a repeatable Fast semantic
   failure.

```text
`你好。` -> GI: correct speech Responsibility (~5.50 s)
        -> GA: correct speech Goal (~6.08 s)          [concurrent]
        -> Fast: empty commit (~8.246 s), then        [concurrent]
                 clock Capability + `现在的时间是。`
        -> Host rejects invalid speech-to-clock Plan
        -> no natural greeting response
```

| Module/boundary | Authoritative input and actual output | Expected output | Judgment |
|---|---|---|---|
| Gateway | Exact explicit text; admitted | Admit usable addressed turn | Correct |
| GI | `你好。`; one greeting speech Responsibility | WHAT-only greeting meaning | Correct, slow |
| GA | Immutable GI result; one speech Goal | Exact Goal coverage | Correct, slow |
| Fast commit | Same GI/context; empty commit at ~8.246 s | Natural immediate greeting within 2 s | Late/incomplete |
| Fast terminal | Speech ref `r1`; clock Capability and time-preface text | Speech-only `complete_response`, no Capability | **Earliest remaining wrong semantic boundary** |
| Host validator | Invalid Plan rejected before execution | Validate without semantic rewrite | Correct containment |
| Capability/playback | Not launched as successful work | Launch only from a valid canonical Plan | Correctly absent |

The Fast transaction's printed schema already forbids Capability mapping for a
speech-only source Responsibility. This isolated case therefore does not show a
missing prompt rule and does not justify a greeting-specific patch.

## Unchanged deployed aggregate

The complete directory-discovered must-pass stage then ran once without source,
service, model, or warm-state changes:

```text
.chromie/acceptance/general-ability/qwen-chat-transport-must-pass-aggregate-valid-20260904/
Result: 5/51 hard-passed; 46 hard-failed
Evidence: Level C-preview, dirty source, incomplete runtime identity
Semantic review: pending
```

| Non-overlapping primary result bucket | Cases | Representative evidence |
|---|---:|---|
| Passed | 5 | Three simple body requests, one filler request, one social response |
| Goal Interpretation | 5 | Binding/provenance or relationship/unresolved contract rejection |
| Goal Association | 2 | Structured-output validation failure |
| Fast Planner | 35 | Invalid JSON/DTO, invented fields/Capabilities, timing/resource conflicts, truncation, or missing communication |
| Deep Planner | 1 | Invalid Goal-outcome coverage |
| Preview evidence limitation | 3 | Deterministic reflex requires non-preview execution evidence |

This classification assigns each case once by its primary user-visible failure;
some concurrently running roles also failed. Of 39 retained Fast timings, zero
met the two-second GI-handoff-to-commit target: minimum 9.795 seconds, median
12.228 seconds, maximum 14.586 seconds. The aggregate greeting repeated the
clock-Capability error with GI at 2.676 seconds and Fast commit at 10.685
seconds. This broad distribution rejects the hypothesis that only the greeting
wording is defective.

## Latest supervised voice diagnosis

After that aggregate, the operator ran the dirty source through device
microphone and speaker mode. The latest bundle retains two current-session
turns and their raw model transactions:

```text
SID 97957fa9: `你好。`
  ASR 126.5 ms -> Gateway greeting/admit 2.416 s
  -> GI accepted one greeting speech Responsibility 8.552 s total
  -> GA created one greeting Goal 7.308 s [concurrent with Fast]
  -> Fast empty commit at 9.547 s; terminal result at 10.645 s
  -> raw Plan invented chromie.clock.local + `现在的时间是。`
  -> Host rejection -> fixed failure speech; session total 27.33 s

SID 17c7c47a: Chongqing rain request
  ASR 199.3 ms -> Gateway request/admit 626.1 ms
  -> raw GI output translated exact source `重庆` to `Chongqing`
  -> provenance rejection at 11.572 s; GA/Planner/weather not invoked
  -> same fixed failure speech; session total 18.16 s
```

Both model calls completed with `done_reason=stop`; neither was a timeout,
truncation, HTTP failure, or TTS failure. The GI prompt explicitly requires the
source-language location surface, and the Fast contract requires ordinary
speech to use `complete_response`; the raw Qwen outputs violated those existing
rules. The earliest wrong boundaries are therefore deployed-model inference in
GI and Fast. Deterministic Host validation correctly contained each invalid
result. Its shared failure utterance makes distinct upstream faults sound
identical but is not their cause.

The same model slot alternated 16K GI and 32K Fast requests. Provider records
showed load durations of 3.80 s for greeting GI, 3.87 s for greeting Fast, and
7.81 s for weather GI. This is a measured latency contributor; the exact
internal Ollama eviction/reload mechanism was not independently proven. The
failed greeting Goal also remained active when the weather turn began; whether
failed planning should retain that Goal is an open recovery-state question,
not an authorized change in this delivery.

## Implemented repair

- `OllamaClient.generate_complete()` and `generate_stream()` use `/api/chat`,
  send system/user messages separately, consume `message.content`, and enforce
  non-thinking output. Existing test-fixture response shapes remain accepted at
  the decoder boundary.
- `scripts/warm_ollama.sh` uses the same `/api/chat` path as production.
- `docs/CONFIGURATION.md` owns the updated transport/warm-up statement.
- A discovered must-pass `speech_identity_latency` case now covers exact
  `你好。`, no Capability, one speech Goal/outcome, a Fast communicative act, no
  Fast contract failure, and the existing warm latency budgets.
- The runtime-exception-boundary body hash changed; its reviewed classification
  remains `narrow_reraise`.
- No prompt, Schema, DTO, model, profile, semantic authority, retry, execution
  policy, configuration key, architecture term, or current document was added.

## Why the previous optimization did not fix hello

The Fast v33 and Deep v15 work fixed Codex `gpt-5.6-sol` as the candidate and
measured the prompt + schema + decoder + Host transaction offline. It never used
the local/deployed Qwen model as a Planner proxy. Those strong mechanical and
non-independent same-model results are useful contract evidence, but they are
not evidence that the RTX 4090 `qwen3.5:4b` can follow the transaction.

The target profile uses one Qwen model for every semantic role and
`OLLAMA_NUM_PARALLEL=1`. That serializes the GA/Fast work the architecture starts
concurrently, while the new case proves this Qwen Fast result is also
semantically invalid. The new current run hard-passed only 5/51 must-pass cases;
prior all-Qwen evidence had retained 0/50. The root project gap is qualification of the real
deployable model/resource profile, not absence of a hardcoded greeting rule.

Verdict after the frozen aggregate: **NO PROMPT CHANGE RECOMMENDED**. The next
comparison target is the complete deployable model/resource transaction.

## Retained evidence

Pre-change voice workflow:

```text
.chromie/evidence/cognitive-runtime/session-workflows/20260904T12270788017-fe7a5819.json
.chromie/evidence/cognitive-runtime/session-workflows/20260904T12270788017-fe7a5819.md
```

Pre-change bundle:

```text
/home/chromie/Downloads/chromie_debug_bundle_20260904_212025.tar.gz
SHA-256: 390186fa3f9ffd22d87b429b0454289bd4ebe9a88eeb2b2c0a1dc1edce40145b
```

Post-repair formal greeting:

```text
.chromie/acceptance/general-ability/greeting-chat-transport-postwarm-rerun-20260904/
Result: 0/1, score 40, hard failure
Evidence level: C-preview, private, live text
Workflow SID: 65f84c93
.chromie/acceptance/general-ability/greeting-chat-transport-postwarm-rerun-20260904/01-must_pass-speech_identity_latency-standalone_greeting_one_natural_reply/session-workflows/20260904T14094030079-65f84c93.json
```

Post-change bundle, collected once after the formal case:

```text
/home/chromie/Downloads/chromie_debug_bundle_20260904_221033.tar.gz
SHA-256: 386c50d9bd1844dead9a2e12da71705535c8da74054ea12c5d37dc8841c2660b
```

Unchanged must-pass aggregate and its one post-run bundle:

```text
.chromie/acceptance/general-ability/qwen-chat-transport-must-pass-aggregate-valid-20260904/
/home/chromie/Downloads/chromie_debug_bundle_20260904_230315.tar.gz
SHA-256: e26db4bbaee0bfa9de7374d7ec81564e78a72e77993963e59b5150fde4907f4a
```

Latest supervised device-mode diagnosis (supersedes the preliminary `231903`
collection for these two turns):

```text
/home/chromie/Downloads/chromie_debug_bundle_20260904_232045.tar.gz
SHA-256: 4c8644003dad8f013999f98133bd2493aca52ae5af3a28e6d7cb0515cef3e959
Workflow: session-workflows/20260904T15174264392-97957fa9.json
Workflow: session-workflows/20260904T15191722733-17c7c47a.json
Source: 46b6fe90a36179e63da36f086ac2b04ed8e7b3c1 plus the listed dirty patch
Runtime: Ollama 0.33.2; all roles qwen3.5:4b; GI num_ctx=16384;
Fast num_ctx=32768; think=false; chat/chat_stream transport
```

Do not treat two earlier invocation-error directories as model evidence:
`qwen-chat-transport-must-pass-aggregate-20260904` rejected an unsupported
runtime-identity schema before inference, and
`qwen-chat-transport-must-pass-aggregate-rerun-20260904` used the MCP server
root rather than `/mcp` and received HTTP 404 preflight failures. No debug
bundle was collected for either invalid attempt.

The formal run used a dirty source tree and recorded incomplete runtime identity.
The latest device-mode trace is supervised diagnostic microphone/speaker
evidence, not a formal acceptance run. Neither artifact is clean
committed-revision, simulator, robot, safety, or release evidence.

## Validation

- Focused transport/runtime/scenario suite: 65 passed.
- Repository policy: 15 rule families, zero exceptions.
- Test ownership: passed.
- Canonical `./scripts/run_tests.sh`: passed, including 140 pytest, 2058
  unittest, and 20 legacy Agent tests.
- Unchanged current deployed must-pass aggregate: 5/51 hard-passed; 46
  hard-failed; semantic review pending.
- Latest device-mode diagnosis: two admitted turns, two distinct model-semantic
  failures, both correctly contained and rendered as the same fixed failure
  speech. No post-diagnosis source repair or acceptance rerun was performed.

## Runtime state and exact resume commands

At delivery review, the Host launcher and `python -m orchestrator.orchestrator`
were still running. The four main Compose services (`chromie-agent`,
`chromie-llm`, ASR, and TTS) were healthy, but Ollama `/api/ps` reported no
resident model. The latest retained voice run had also reached
`soridormi-runtime-mcp` and MuJoCo startup checks. Do not infer warm model state
or other service health from the still-running Host process.

Inspect first:

```bash
git status --short --branch
git diff --check
docker compose ps
curl -fsS http://127.0.0.1:11434/api/ps
```

If the Agent image or Ollama process has changed, restore the tested transport
and context state before evidence collection:

```bash
docker compose build chromie-agent
docker compose up -d chromie-agent
docker compose restart chromie-llm
./scripts/warm_ollama.sh qwen3.5:4b
```

Start the Host in the repository root when supervised voice use is intended:

```bash
CHROMIE_OPERATOR_MODE=voice_mujoco ./scripts/start_orchestrator.sh
```

Do not tune the single greeting next. Use the retained 5/51 aggregate to compare
the smallest deployable model/resource-profile change while keeping the frozen
cases and one-authority contracts fixed. Reproduce the dominant Fast failures,
then check the GI, GA, and Deep buckets. Rerun the complete cohort after the
chosen change before broader claims.

Repository-only revalidation:

```bash
python scripts/check_repository_policies.py
python scripts/check_test_ownership.py
./scripts/run_tests.sh
python scripts/check_docs.py
```

## Claim boundary

This delivery repairs the observed Agent endpoint mismatch and the warm-up
context mismatch. Tests verify those source contracts. The formal and later
device-mode cases prove the greeting reaches GI, GA, and Fast and that Host
validation rejects the invalid Plan; the weather turn proves GI can separately
violate explicit source-language provenance. The aggregate proves the current
all-Qwen profile is broadly unqualified—5/51 hard passes, with no retained Fast
timing meeting target—but does not qualify a replacement or normal physical
voice behavior. Clean committed-revision provenance, semantic review,
robot/sim behavior, safety, and release readiness remain open.

## Latest framing continuation — runtime rerun pending

After the completed Fast-continuity aggregate, the next repair constrains the existing
Fast two-frame stream through SGLang. Eleven frozen exact requests improve 5/11 to
11/11 complete, original-Schema-valid streams. The first direct decoder experiment
was rejected: 196/198 mechanical contrasts and a repeated-frame token-limit failure.
Native grammar inspection proves unsafe JSON-string pattern translation and incorrect
fractional bounds. Decoder-only omission of those hints plus existing shape exposure
passes all 198 contrasts. Original schemas and parser/DTO/Host remain unchanged;
not every schema keyword is asserted to be Host-enforced. Semantic blockers persist.
Evidence: `.chromie/acceptance/fast-tagged-20260910/`, including before/after/compatible,
manual report, native contrasts and exact final format equality. No prompt/model change.
Production transport integration is implemented; focused tests 262 / 58 subtests pass.
The GA shape helper was moved unchanged into shared schema utilities for reuse. No
new files, documents, environment settings, runtime switches or semantic authority.
Full canonical gate and complete cohort are pending. Framing Agent is deployed:
`sha256:bad2666cf5a4c123cd3d7f786d1c96fa723dba24def6d702c8dd29d8ce98d16c`,
container `6b2e7dcd14e063ec370d5a1871cc2de4ddfdb5adf0498d09952ecffc947fa370`.
Agent and shared contract files match the worktree; see source-verification.json.
SGLang is unchanged. These latest identities supersede earlier running-image prose.

## Latest evidence closure — failed-stream investigation pending

Framing full gate passes 2317 tests / 363 subtests; full 51-case preview is 28
mechanical / 19 reviewed acceptable initial previews. All cases and available raw
calls reviewed. Both continuation scenarios pass. Of 51 Fast invocations, 50
completed streams pass original schemas; contextless_turn_it_up hits the token
limit and its failed request/partial output was not retained. This is an integrity
and provenance blocker, not a clean 50/50 pass. GI 53 valid; GA 50 valid + 1 invalid;
Deep 3 invalid; skill 2 invalid. 160 retained calls / 159 linked. Exactly one bundle:
`/home/chromie/Downloads/chromie_debug_bundle_20260910_122434.tar.gz`.

The current diagnostic repair logs each SGLang stream once in finally, including
truncation, EOF, timeout and cancellation, with exact request and partial output.
Evidence JSON preserves property order; existing canonical reference hashing is
unchanged. OpenAI single-choice output is now exposed as raw text in the record.
No model input, retry or acceptance behavior changes. Focused tests 41 / 10 subtests
pass. Full gate, deployment and focused reproduction are pending under
`.chromie/acceptance/stream-evidence-20260910/`. The framed Agent image above still
runs until the next identity is recorded. Do not infer the truncation root cause
without the missing stream evidence or promote while semantic/safety failures remain.

## Bounded-whitespace continuation — qualification pending

The next complete immutable preview on source 26fe1ceec19b0c6ffbe7560db0a5b390c75c8bf7
finished with 25 mechanical / 20 reviewed acceptable initial previews. All 51 cases
and available raw calls were reviewed; 158 linked calls include 49 completed valid
Fast streams and one retained failed stream. Both continuation probes still pass.
Exactly one bundle: `/home/chromie/Downloads/chromie_debug_bundle_20260910_134729.tar.gz`.
Evidence: `.chromie/acceptance/stream-baseline-20260910/`; semantic failures remain.
Three unchanged contextless-request probes completed with wrong stand_idle choices;
valid escalation is representable. These do not explain the old missing truncation.

The newly retained weather truncation contains markup inside reason_summary followed
by an unbounded whitespace run after the string closes. Installed grammar accepts
all 3474 characters as an incomplete prefix. Limiting whitespace regions to eight
rejects that captured loop at character 641; 198 existing framing contrasts pass.
This is the selected runtime/decoder boundary, not a semantic prompt change. The
original and bounded exact-request replays both complete; no reproduced model-level
improvement is claimed. New request-local annotation and pinned SGLang bridge are
implemented, with 40 focused tests / 10 subtests passing. Build and canonical gate pass (2319 tests / 368 subtests, 20 legacy tests).
Both candidate services are deployed; 113 Agent/shared files match.
Agent image fd462a11e9f95617eaa10eb7ab79fc334888c89ee9721fffc013a76d54ad7be9;
SGLang image 41fbd910662483a125184a00611029225ee102a928421eaeaec70ab27a844edf.
Frozen replays and the complete changed-revision cohort remain pending. Evidence:
`.chromie/acceptance/stream-length-20260910/`. These running images supersede earlier runtime identities. No Deep/skill, model,
prompt, semantic authority or token-budget change.
