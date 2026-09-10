# Chromie Development Checkpoint

## Current resume point — bounded whitespace tested; promotion rejected

Active Issue #35; delivery branch `codex/ga-request-format`; pre-delivery baseline
`26fe1ceec19b0c6ffbe7560db0a5b390c75c8bf7`. Owner authorized commit and push when
finished. Resume at the latest commit containing both checkpoint and handoff.
This is an unpromoted development delivery, not a merge to main or release claim.
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
transaction/nonregression or LLM-integrity closure is claimed. Whole candidate promotion
is rejected; the whitespace mechanism is retained only as an unpromoted development repair.

Release readiness remains blocked by GI prohibition/ambiguity/provenance, invented
motions, resource meaning, false reminder/completion promises, omitted Goals, GI/GA
continuity, Deep/skill contracts, progress and latency. Physical voice/provider/robot
and default target-evidence closure are missing. Preview is not execution evidence.

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

First read the full-cohort regressions and prohibition-audit.md in the pre-change
baseline. Freeze bilingual primary GI positive/negative constraint contrasts and
establish representability before any semantic edit. Investigate full-cohort variability;
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
