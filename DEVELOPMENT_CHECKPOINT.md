# Chromie Development Checkpoint

## Authorized repair — bounded turn count and lossless evidence

The Goal-driven single-authority architecture remains binding.
Active Issue #35; Chromie branch `codex/ga-request-format`, pre-delivery base
`156720b543644f6b448272fa3cb231799da1cb82`. The owner explicitly authorized the
previously proposed turn-count contract expansion ("you have my authorization
now, please go on"). Commit/push remain authorized. Resume from the latest commit
containing both checkpoint and handoff; this is not a main-promotion approval.
The paired Soridormi base is `d03c7e3b7da73b777b1e923044340fa9c8d66fa7`;
its delivered branch is `codex/turn-count`, commit
`578198ad1d52f4b5d2f9b63cacf87a23c3b5b224`, pushed to origin. Its unrelated dirty
work is preserved and excluded from that commit.

### Reconstructed workflow and implemented repair

| Boundary / owner | Actual evidence and expected contract | Result |
| --- | --- | --- |
| GI -> Planner | Originating right-turn episode had count=1, but the provider exposed only yaw/duration. GI must own WHAT without a Capability catalog | GI prompt/context unchanged; no catalog or second semantic call added |
| GI -> GA and Fast (parallel) | GI Responsibility supplies continuity and planning independently; results join at Host | Focused turns used no Deep Planner or Skill Selection; GA retains Goal ownership |
| Soridormi catalog -> Planner | Count could not be represented and yaw direction lacked explicit guidance | Add integer count 1-8/default1; duration is per repetition; total count × duration <=20 seconds. Positive yaw is left, negative is right |
| Planner -> Host | A matching duration formerly masqueraded as count | Keep same-name count validation and legacy no-count rejection. Planner authors count once; Host does not infer repetitions from node count |
| Provider -> body runtime | Count must be realized, not merely admitted by schema | Validate finite integer/bounds, expand sequential segments, retain existing locomotion lock, stop, cancellation, timeout and safe hold. No implied pause, heading reset or full revolution |
| Runtime -> acceptance observations | All three focused MuJoCo requests completed, but the observation map discarded count and falsely failed matching | Preserve count beside yaw/duration; re-adjudicate retained executions without changing the expected counts or original failed reports |
| Model client -> container logs -> reviewer | Three raw-copy digests disagreed; intact provider copies matched. Corruption starts at byte98303, crossing a16KiB frame | Emit ASCII JSON escapes only at the log boundary. Parsing recovers original Unicode and hashes; model packets and responses are unchanged |

The source logger supplied identical original text to both evidence copies; the
framed transport corrupted one occurrence. A deterministic replay produced24
replacement characters before the fix and zero afterwards. This is a project
logging defect, not a model-generation error. No new architecture layer, runtime
flag, document, Capability or model call was added. The existing turn Capability
has one additional argument (2 ->3); the existing observation map is extended.
Soridormi's single-segment shell export still rejects repeated multi-segment plans;
the maintained runtime MCP path realizes them. `turn_to_heading` forwards count.

### Observed evidence and limits

First repaired-provider aggregate: `.chromie/acceptance/turn-count-20260910/`.
All51 scenarios completed on stable Chromie/provider source:27 mechanical passes,
18 reviewed acceptable initial previews; all154 linked calls reviewed. Three
raw-output digest mismatches exposed the logging defect. Exactly one debug bundle:
`/home/chromie/Downloads/chromie_debug_bundle_20260910_190114.tar.gz`.
The original walk-then-right-turn case still failed upstream at GI (`三秒` -> `3秒`),
while the compound left-turn primary Planner packet used the new count=1 contract.

Implementation, local gates and focused evidence root:
`.chromie/acceptance/turn-count-evidence-20260910/`.
Canonical gates pass2329 tests /420 subtests,140 benchmarks and20 legacy Agent tests;
repository policy, test ownership, static analysis and documentation checks pass.
Soridormi governance/body-concurrency/compile pass; full suite788 passed /2 skipped,
body-focused155 passed. An isolated delivery snapshot excluding pre-existing
Soridormi changes passes80 focused tests. Relevant Level A:13 distinct scenarios
pass across grounding, composition and deterministic safety (memberships overlap).

Three frozen direction/count contrasts executed through GI -> GA/Fast -> Host ->
Soridormi in MuJoCo: left2, right1, right2, each segment1 second; all completed and
returned safe_idle=true. Nine model-call request/output digests match. The original
runner0/3 was an observation-map omission; corrected replay is3/3 for bounded
motion realization (`focused/motion-review.json`), preserving original reports.
Right-turn reason strings contain markup/channel fragments: these are not erased
and this motion proof is not whole-transaction qualification or measured physical
hardware/voice proof. A separate direct MCP count2/0.5-second smoke also completed.

A later aggregate in that root was stopped after 4 completed cases because
its identity capture finished one second after the first case initialized; the
documentation focus check also failed. It is incomplete, not a qualification run.
One bundle was collected at that stop:
`/home/chromie/Downloads/chromie_debug_bundle_20260910_191129.tar.gz`.
Both defects in collection setup are corrected before the final run.

The final lossless51-case aggregate root is
`.chromie/acceptance/turn-count-final-20260910/`. All 51 cases and 155 linked
calls were reviewed: 26 mechanical passes and 16 acceptable initial previews.
All request/output digests match; both repositories remained stable throughout.
Exactly one bundle: `/home/chromie/Downloads/chromie_debug_bundle_20260910_192333.tar.gz`.
Compared with the first aggregate, joke composition recovered; look-then-blink,
tired-social and three-second gaze regressed. These are observed run-to-run
differences, not proven effects of the logging/observation repair.

The look-then-blink case exposes an unresolved provider/Host grounding gap: GI
preserved `duration: two seconds`, Fast omitted `duration_s`, and Host admitted the
provider default of four seconds. Provider-owned argument-realization metadata
and deterministic validation need further audit; do not introduce Host semantic
inference or claim this is exclusively a model defect. Tianxin used one explicitly
designated deep GI delegation from source after unresolved meaning, not a
same-stage semantic retry. See `behavior-review.json` for every case and exact
raw-transaction references.

### Runtime, delivery and next boundary

Fixed RTX5090 / Gemma4-12B FP8/SGLang model and role budgets remain unchanged.
Agent tag `chromie-agent:turn-count-evidence-20260910`; image `sha256:2a514a24145165fe8d0b279457567f36462fbd20641d059ce73a56740185433f`,
container `517df9a934b0eb1715743d97fd2462ec6a402bd3dd5c28c54f9caa80b7d9393d`. All112 deployed Agent/shared Python files match source.
Soridormi source is live-mounted and was restarted before the aggregate; its
advertised source revision remains the pre-delivery base plus the retained dirty
patch. Do not equate that base string alone with the evaluated source tree.

Evidence is private and retained locally; transfer it separately across machines.
Provider pre-existing edits to manifest argument-realization metadata, taxonomy,
manifest validation/tests and the Open Duck submodule are outside this patch.
The own-only staged patch must leave those edits intact. Do not merge main: GI
ambiguity/prohibition/segmentation, GA continuity/source preservation, Planner
progress/grounding/reason quality and supervised target-evidence closure remain
unqualified. Remaining failures have not all been proven model-only.

Commands: `./scripts/run_tests.sh`; `python scripts/check_repository_policies.py`;
`python scripts/check_test_ownership.py`; `python scripts/check_docs.py`.
Capture with `python scripts/capture_runtime_identity.py --allow-dirty --orchestrator-env .chromie/voice-runtime/orchestrator.env --compose-override docker-compose.sglang.yml --compose-override .chromie/voice-runtime/compose.voice-mujoco.yaml --output NEW/runtime-identity.json`.
The final evidence root's `run-cohort.py` runs the whole directory-discovered
must-pass preview cohort and collects exactly one debug bundle afterwards.
Review every linked raw request/output, recompute its recorded digests, and inspect
semantic failures before any next broad source change. Never edit `.env.runtime`.
