# Chromie Development Checkpoint

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
