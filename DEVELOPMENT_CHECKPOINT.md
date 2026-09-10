# Chromie Development Checkpoint

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

Implemented Skill repair and shared-client diagnostic correction retain full canonical
2324 tests / 399 subtests, 140 benchmarks, 20 legacy tests; focused Skill 53 / 15,
client 30 / 3, Level A 19/19. These are previous observed runs, not new audit tests.
`skill-single-call-20260910/behavior-review.json`: immutable 51-case aggregate,
28 mechanical / 17 reviewed acceptable initial previews, all 159 linked calls reviewed.
One bundle: `/home/chromie/Downloads/chromie_debug_bundle_20260910_160447.tar.gz`.
Two prior acceptable cases recovered and four regressed. Full per-case changes,
11 frozen before/after Skill Host contrasts, diagnostic evidence and identities
remain in HANDOFF.md and the private evidence root. Transfer artifacts separately.
The aggregate precedes the final diagnostic-only correction; do not relabel it.
Semantic, provenance, Goal coverage, numeric validation, failure presentation,
progress/latency, integrity and physical target-evidence gaps remain. Main is not
merged; the audit above confirms project defects, not an all-model-only residual.

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
