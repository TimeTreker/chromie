# Chromie Development Checkpoint

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
