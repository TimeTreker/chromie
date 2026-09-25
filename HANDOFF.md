# Chromie Handoff

## Text console continuous-input delivery — 2026-09-25

Chromie checkout `/home/chromie/github/chromie`, branch `main`, pre-delivery
base `618569ab430df7981ed08fb7b4ae4599cc36180b`; fetched
`origin/main` matched before editing. Resume from the latest commit containing
this Handoff and Checkpoint. Soridormi checkout is on `main` at
`2bf8d67fc6aa755a6359b32358e592e1afad0b71`; no Soridormi source was
changed for this Chromie console repair.

The client previously blocked keyboard reads until `{"done":true}`; the Host
console also blocked socket reads until `_run_text_turn` and session closure.
New text could not reach Gateway while a long task ran. The client now watches
stdin and socket together; the Host starts each text turn in the existing
InputSessionRuntime routed-turn lifecycle, reads the next line immediately,
and emits per-turn completion. Protective stop still uses deterministic
Gateway cancellation. Assistant-history forwarding filters by session ID to
avoid duplicate/cross-client replies. Interactive `/quit` and Ctrl+C disconnect
the client without canceling admitted robot Work. The owned contract and user
instructions were updated in `docs/API_REFERENCE.md` and `docs/USER_MANUAL.md`.

Observed commands/results: final-source focused `pytest -q
tests/test_psm_live_text_console.py tests/test_cognitive_gateway_reflex.py
tests/test_orchestrator_barge_in_queue.py tests/test_shutdown_lifecycle.py
tests/test_social_identity_schema.py tests/test_input_session_runtime_extraction.py`
→ 65 passed/42 subtests. Level A
`deterministic_safety_controls` 3/3 and
`evidence_bound_cognitive_turn_closure` 6/6. Level A
`human_like_cognitive_continuity` 3/4, with the existing missing
`body_effect_family` UMI fixture in `weather_then_repeated_walk_stays_grounded`.
`python scripts/check_repository_policies.py`,
`python scripts/check_test_ownership.py`, and `python scripts/check_docs.py`
passed. Canonical `./scripts/run_tests.sh` stopped in benchmark validation:
6 failed/147 passed, before its main-test stage. Separate `pytest -q tests`
started before the final reply-filter edit and returned 125 failed/3713
passed/1009 subtests, 2 warnings; the broad failures have not all been
adjudicated for this patch. No new live evidence bundle or
target qualification artifact was produced.

At inspection, the user's old `./scripts/start_chromie.sh --text-console --build`
launcher and `chromie_psm_live_text_console.py --serve --capabilities --speaker`
Host were still running on loaded pre-patch Python code; do not treat this
source patch as active there. Soridormi MCP reported `safe_idle=true`,
`active_task=null`, `emergency_stop=false`. The Host was not restarted and no
live long-task/stop, physical microphone/speaker, or robot proof was run.

Resume on the same host: after any desired current work completes, press
Ctrl+C in the old Host launcher terminal, then run
`cd /home/chromie/github/chromie && ./scripts/start_chromie.sh --text-console`
there. In another terminal run
`cd /home/chromie/github/chromie && python scripts/chromie_psm_live_text_console.py`.
Submit a bounded long task and type `stop` before it finishes; inspect Gateway
cancellation, Runtime/provider receipt, session outcome, and Soridormi safe
idle in one retained live case before asserting end-to-end interruption.
Then resume the prior aggregate compound-planning failure and canonical/target
gates. `/quit` exits only the client; for an emergency use the independent
Soridormi emergency-stop path.

## Reported milk and detached-dispatch delivery — 2026-09-25

Chromie `/home/chromie/github/chromie` is on `main`, pre-delivery base
`b0c2dfec004a082702f71d14148791aefd67a5bf`, fetched and equal to
`origin/main` before editing. Resume from the latest commit containing this
Handoff and Checkpoint, then fetch before further development. Paired Soridormi
`/home/chromie/github/soridormi` is clean on `main` at
`531268c53c1029ab4875ddeb623046314e48ab4b`; the MCP service reports
source `5d235b8aee35efd4788b0dd1de791753275618f9`. This delivery changes
Chromie only. The Soridormi default scenario was reset to its initial bottle
10 m ahead/user 1.5 m right before each physical rerun and after the final
delivery; no scene asset or Soridormi source was modified.

Implementation: UMI now explicitly preserves reported relative source place
and measured distance separately, including across a pronoun. SC receives a
report-only truth guard for visual/auditory claims. Planner's resource-role
mapping recognizes `source_location`/`source_distance`, its dynamic Schema
requires the exact typed distance and withholds a provider-owned resource from
the missing-user-input clarification choices, while Host validation rejects
current-turn citation for binding-grounded arguments. The common Work contract
omits routine idle cleanup because Soridormi already ends standing/safe idle.
The execute-plan MCP manifest timeout is 660 s and Host capability definition
and request bounds admit it up to 900 s. `SessionTracker` protects a session
from the 120 s idle sweeper while its accepted detached capability result task
is unresolved; normal idle finalization resumes when that task ends. New live
general-ability case:
`scenarios/general_ability/must_pass/truthful_embodied_speech/reported_milk_then_delivery.json`.

Current candidate identity:
`/tmp/chromie-live-candidate9-identity-20260925.json` verified equal Agent
container/host source digest `ab35edfe8c3fa20251bf5a0d505dbe49d1db889689e127b9f82c55ecaef7dedb`.
Focused live command used:
`python scripts/general_ability_acceptance.py --mode live-text --only-case reported_milk_then_delivery --execute --capability-timeout-s 0 --timeout-s 420 --case-timeout-s 700 --soridormi-repo /home/chromie/github/soridormi --runtime-identity /tmp/chromie-live-candidate9-identity-20260925.json --evidence-dir .chromie/acceptance/reported-milk-fix9-20260925 --json`.
Result: one case mechanically passed, semantic reviewer pending. Manual review
found the first `Got it.`, the later UMI bindings
`entity=bottle of milk`, `recipient=user`, `source_location=in front of you`,
`source_distance={value:50,unit:meters}`, one Planner acquire/deliver Activity,
empty `argument_sources`, Soridormi `completed`, post-status `safe_idle=true`
and `active_task_present=false`, and `session_done: state=complete` at
340,408.8 ms. No `stand_idle` Activity. Evidence and one post-run bundle:
`.chromie/acceptance/reported-milk-fix9-20260925`,
`/home/chromie/Downloads/chromie_debug_bundle_20260925_135912.tar.gz`.

Same-candidate complete live invocation (without `--only-case`) stopped at
case 1/76, `compound_walk_nod_turn`: Fast Planner omitted terminal Activities
for `r4,r5`, so Host rejected the plan and no robot Work ran. The cohort is
incomplete; retain `.chromie/acceptance/aggregate-candidate9-20260925` and
`/home/chromie/Downloads/chromie_debug_bundle_20260925_140141.tar.gz`.
The earlier unchanged baseline also stopped at case 1/75 on the 300 s Host
capability-definition ceiling; the candidate closes that mechanical timeout
for the milk skill but not this separate compound-planning defect.

Observed local checks: `PYTHONPATH=agent:. python -m pytest -q
tests/test_user_meaning_interpreter_material_context.py
tests/test_user_meaning_interpreter_llm_prompt.py
tests/test_fast_planner_streaming_commit.py tests/test_fast_planner_pr3.py
tests/test_session_runtime_trace.py tests/test_soridormi_capability_provider.py
agent/tests/test_capability_registry.py` → 364 passed/165 subtests; `python
scripts/check_repository_policies.py`, `python scripts/check_test_ownership.py`,
`python scripts/check_docs.py`, and
`python scripts/general_ability_acceptance.py --mode check` passed.
`python scripts/general_ability_acceptance.py --mode level-a --ability-class
truthful_embodied_speech --ability-class composable_action_planning` passed
8/11; three older body-action references omit the now-required UMI
`body_effect_family` and fail before the intended ability assertion.
`./scripts/run_tests.sh` failed at maintained benchmark dataset validation,
6 failed/147 passed, before main tests. A physical voice run was not performed.
Next resume:
inspect the aggregate compound case's accepted UMI Responsibilities and raw
Fast Planner result; fix its earliest owner, then rerun the focused ability,
the full same-revision cohort, canonical gates, and current-revision target
profile before a broader correctness claim. The simulator's
`soridormi.robot.observe_scene` remains an explicit simulation-only adapter;
ordinary conversation still does not automatically call it.

## Simulation object-set adapter delivery — 2026-09-25

Chromie checkout `/home/chromie/github/chromie`, branch `main`, pre-delivery
base `6e51ad2a443e0bc7d6dcf47f8f109a8f6ad33e69`; fetched `origin/main`
matched before editing. Paired Soridormi checkout `/home/chromie/github/soridormi`
has source commit `5d235b8aee35efd4788b0dd1de791753275618f9` and proof
record commit `531268c53c1029ab4875ddeb623046314e48ab4b` pushed on `main`;
its standing-user/return-walk patch is separate.
Resume from the latest commits containing these handoffs after fetching both
repositories, rather than from the pre-delivery hashes.

Soridormi's default MuJoCo scenario now adds a named non-contact user actor 1.5 m
right of Chromie. A direct isolated simulator run on the dirty Soridormi source
walked to the milk (10.006→0.844 m, 156.08 s), returned to the user
(9.412→0.892 m, 159.17 s), reported mocked pickup/handover, and ended standing,
safe idle, with no active task. The runtime's `source_revision` remained
`06d5d4f` during that dirty-source probe, so do not use the revision field to
claim this run as committed-revision proof. The isolated simulator was stopped.
The default scenario and MCP service were restarted from committed `5d235b8`;
MCP `get_status` reported that source revision, `safe_idle=true`, and no active
task, while `observe_scene` reported milk at 10.006 m and the simulated user
1.5 m to Chromie's right. Soridormi's dependency-complete container suite
passed 819 tests/4 skipped and body concurrency passed 177 tests; host Python
lacks `pyzmq` and cannot collect the full suite.
The full public MCP call on code revision `5d235b8` then reported bottle
10.008→0.834 m in 155.26 s, return to user 9.425→0.883 m in 158.45 s,
mocked handover, standing/safe idle, and no active task. Direct simulator reset
restored milk about 10 m ahead and user 1.5 m right; subsequent MCP status
again reported safe idle and those scene markers. The public call output was
observed in the terminal; no separate ignored bundle was retained.

Chromie now validates multiple `soridormi_mock_*` scene markers in one
`soridormi.robot.observe_scene` result and projects each into Goal-free
Situation with `source_refs=[observation_id]` and `(simulated)` wording. It
rejects wrong source provenance, duplicate/malformed markers, directions and
distances outside the 60 m observation bound. It does not call the tool on
ordinary turns or seed objects from user text. No actual water object, automatic
perception-triggered planning, scene-to-speech, physical camera, or hardware
proof is included.

Commands/results on Chromie: `python -m pytest -q
tests/test_soridormi_scene_perception.py` → 3 passed;
`python scripts/check_repository_policies.py`,
`python scripts/check_test_ownership.py`, and `python scripts/check_docs.py` →
passed. `./scripts/run_tests.sh` → benchmark stage 6 failed/147 passed on the
maintained semantic corpora; it stopped before main tests. No ignored live
artifact was retained for the direct Soridormi probe; its measurements were
observed in the run output. The committed-revision public MCP proof above
qualifies Soridormi's simulated round trip, not Chromie's dialogue or hardware.

Next: fetch both repos, start the current Soridormi scenario and MCP provider,
admit an explicit fresh scene read into Chromie's information-acquisition
Work path, and run focused tests plus frozen model-role and live simulation
qualification. Keep first-turn perceptual speech and inherited Planner argument
provenance as separate open repairs. Complete the canonical local gate before
any release claim.

## Simulation milk-scene observation delivery — 2026-09-24

Checkouts: `/home/chromie/github/chromie` at `main` base
`08e40d2eebbc03d962895d5bb32cfa832adf69bf`, and
`/home/chromie/github/soridormi` at `codex/turn-count` base
`013f46d19ec5101c4392532ab848e0b0819c2a50`. Both matched their fetched
`origin` branches before editing. Preserve Soridormi's pre-existing untracked
`workspace/Open_Duck_Playground` submodule directory; it is outside this patch.
Paired Soridormi source commit:
`f9cf6ac14e63e2c69caca7665b7ed9d16e4861df`.

Soridormi's `./scripts/run_sim_server.sh --backend mujoco --profile open_duck_forward
--no-viewer --milk-bottle` generates a non-contact scene marker 50 m ahead.
`soridormi.robot.observe_scene` reads current MuJoCo geometry and pose and returns
simulation-marked, source-identified observations or an empty list. Chromie's
`observe_soridormi_sim_scene` validates that output and constructs a Goal-free
Situation observation. No ordinary-turn call site exists yet, and neither the
first-turn “I see” wording nor the inherited-location Planner citation is fixed.

Observed checks: Chromie focused adapter 2 passed; policy, test ownership and docs
passed; full benchmark 6 failed/147 passed and main tests 120 failed/3708 passed.
Soridormi container full suite 803 passed/5 skipped before the final cap/output
tidying; post-tidying focused 70 passed, body concurrency 164 passed/4 skipped,
governance and compile passed. Generated XML compiled in MuJoCo and direct backend
observation returned 50.0 m. Host-only body test could not import `zmq`; the
dependency-complete container passed. No retained live run, service restart,
microphone/speaker, physical robot, or real-camera evidence is claimed.

Local commands used for the relevant source checks: Chromie
`python -m pytest -q tests/test_soridormi_scene_perception.py`,
`python scripts/check_repository_policies.py`,
`python scripts/check_test_ownership.py`, and `python scripts/check_docs.py`.
Soridormi `python scripts/validate_repository_governance.py` and
`python -m compileall -q src tests` passed. Its full `pytest -q`, focused pytest,
and `./scripts/validate_body_concurrency.sh` ran inside the dependency-complete
container as recorded above; no live scenario command was run.

Resume: fetch both upstream branches; preserve dirty work; run the focused tests,
then wire fresh scene observation into an explicitly source-attributed cognition
opportunity and exercise the milk dialogue in a safe live simulation. Qualify and
repair first-turn speech and Planner inherited-location provenance separately;
inspect whether Soridormi's completion posture requires an explicit `stand_idle`.
Run `python scripts/check_repository_policies.py`, `./scripts/run_tests.sh`, and
`python scripts/check_docs.py` in Chromie before a revision-level claim. Expected
resume revision after delivery is the latest commit containing this Handoff and
Checkpoint pair, not either pre-delivery base above.

## Responsibility association + natural interaction patch — pending application 2026-09-24

Base revision: `cc4276625ffde7d3dd786b99cf48729e0edc49b4` on `main`. The owner clarified the
intended semantic hierarchy after the foreground-turn patch: UMI emits current Responsibilities;
GA only associates them with retained Goal history; trusted lifecycle code materializes new Goal
identity mechanically from UMI when no retained match exists. `turn` is interaction lifetime, not
absence of a Goal or Planner. Joke/chat Responsibilities may have short-lived interaction Goals and
Planner HOW cognition; SC still owns exact words.

The patch additionally prevents late independent GA failure from turning an already delivered joke
into user-visible failure/apology/second joke, adds natural conversational economy to SC/Mind, and
keeps ordinary identity person-first (`Chromie`, twelve-year-old girl) without volunteering robot/AI
labels. Robotic embodiment remains a truthful direct-answer fact. Soridormi per-execution reset
evidence is deliberately not folded into this patch and remains a separate provider-fidelity task.

## Foreground-turn continuity containment — pending application 2026-09-24

Base revision: `1e10bc825cee8d72a1f139b25a82e3492edc75b8` on `main`, including the
owner-applied working-conversation and tiered-memory patches. Reproducer:
`chromie_debug_bundle_20260924_003802.tar.gz` / `Pasted text.txt`. The episode starts
with a weather Goal, then independent turns (`can you speak chinese?`, `can me tell me a
joke?`) are correctly understood by UMI but are overridden downstream by retained weather
state. The initial weather SC also speaks an unverified forecast before any weather
Capability/Evidence transaction.

Pending patch repairs four boundaries: current UMI meaning is foreground; initial SC does
not receive broad unbound Goal/Work memory; turn-local speech is mechanically GA `non_goal`;
and Runtime drops turn-local refs from an accidentally requested Planner activation. Initial
non-speech task SC is pre-Evidence acknowledgement-only. Do not weaken these guards to make
the old episode pass. Goal-scoped refinements such as `add ice to it` remain eligible for
normal GA continuity against working/long-term Goal candidates.

Retained local source validation: focused **277 tests + 107 subtests**; expanded
**727 tests + 564 subtests**; two existing FastAPI warnings. After applying, run the
canonical repository gate where the full benchmark fixture archive is available, then rerun
the exact weather sequence. Do not claim the weather lookup itself is fixed unless Planner
actually schedules the weather Capability and trusted Evidence returns; this patch fixes
topic capture and premature result speech, not model-driven Planner activation policy.

Updated 2026-09-24. Audience: the owner and next development session. This file owns
volatile identities, evidence paths and resume commands. [Checkpoint](DEVELOPMENT_CHECKPOINT.md)
owns priorities; [Status](docs/STATUS.md) owns claim limits. This is the owner-requested
delivery handoff; resume from the latest `main` commit containing this file.

## Local archive repair pending application — 2026-09-23

Source basis: owner-supplied `chromie_20260923_archive.zip`; paired debug source identity
`af5e11eb4e86a0bde18dfdc0d0b2f48494b01066`. This environment has no archive `.git` metadata
and has not pushed anything. The generated patch closes the active Chromie-side boundaries for
standing SC activation, Planner social-expression isolation, concurrent timing realization,
SC-owned terminal failure communication, sanitized fallback speech, and reported embodied safety
postconditions. Fast/Deep Planner now receive target-only realization evidence rather than the
old `planner_auxiliary_social_context`; optional expression candidates remain exclusively on the
Social Cognition path.

Do not mark the milk-delivery reset case closed until Soridormi exposes a per-execution reset,
recovery, interruption, or equivalent terminal safety fact. In the supplied run MuJoCo reset at
tilt 1.298 rad while Chromie's provider-facing result later said `completed`; no reset counter or
epoch crosses the interface, so a Chromie-only patch cannot recover that truth without guessing.
After applying to a full checkout, run the canonical repository gate and current prompt/model
qualification, then repeat the exact weather, milk delivery, and concurrent walk+wave sequence.

## Delivery revision and validation boundary — 2026-09-23

Owner requested commit and push **without tests**. Repository:
`/home/chromie/github/chromie`; branch `main`, remote `origin` at
`https://github.com/TimeTreker/chromie.git`. Pre-delivery baseline:
`ac4e56274ecac59cff51e84d734dee05d04f7da9`; delivery fetch confirmed 0 ahead/behind.
The expected resume revision is the latest `main` commit containing this pair of
handoff owners, not that baseline. Delivery includes all RTX5090 mechanical repairs
and benchmark cleanup described below; no history rewrite or release approval.

Tests/check suites: **not run for this delivery, at owner request**. Latest retained
local gate: **153 benchmark,3823 main/1096 subtests,20 legacy**, exit0 with two existing
warnings, from the storage-cleanup run. Only delivery documentation changed after
that gate. Live evidence is the prior runtime-bound 75-case run, still failing and
incomplete; no fresh deployment or qualification is claimed for the delivery commit.
All `.chromie/acceptance/` evidence and debug bundles below remain private ignored
local files. Transfer them separately before cross-machine diagnosis; Git carries
the source, manifests and resume record, not those live artifacts or runtime images.

## Benchmark storage cleanup — included in this delivery

Owner requested removal of unnecessary benchmark bulk after reviewing its ownership.
**6,076 expanded files/288,195,530 bytes** are removed from the tracked tree; their
verified local copies remain ignored. Tracked benchmark files:9,691→3,615. Required
code, authored datasets, five prototype episodes and the complete hash manifest
remain. No generated report was newly added to Git; the reports directory was
already ignored. Existing history is not rewritten or compacted.

`benchmarks/integration/workflow_scenarios/manifest.json` binds all6,000 case and76
packet hashes to Git revision `ac4e56274ecac59cff51e84d734dee05d04f7da9`, path
`benchmarks/integration/workflow_scenarios`, original manifest SHA256
`d1ea729df9e35c1b1e6e8025406aba18dfe4448512c2abf810bcd94ad048a5fb`.
The existing regression archive owner restores missing files after checking every
archive hash. It never invokes authoring or records current model outputs. Existing
modified cache files fail closed. Local full-history setup is automatic through
`./scripts/run_tests.sh` and the replay runner; for shallow checkouts use:

```bash
python -m benchmarks.regression restore-fixtures --fetch
```

CI runs that explicit preparation before the canonical gate. Direct pytest users
can prepare offline with `python -m benchmarks.regression restore-fixtures` first.
Do not remove the source pin, skip missing tests or regenerate expected answers to
work around a missing archive. Future freezes must retain exact reviewed bytes at
an immutable revision and update the pin/hashes together.

Evidence root `.chromie/acceptance/benchmark-storage-20260923/`: `before.json`,
`after.json`, `storage-tests.log` (12 focused tests), `canonical.log`/`canonical-exit.txt`
(cold-cache **153 benchmark,3823 main/1096 subtests,20 legacy**, exit0), and `REVIEW.md`.
All6,076 restored files match preserved originals; temporary duplicate removed.
The60 family regressions now collect from the manifest even with an absent cache.
No changed runtime or new live evidence. Earlier RTX5090 fixes/evidence remain intact.
Expanded files are removed only from version control; their verified local cache
is retained. The delivery includes the removals together with their setup, manifest,
ignore rules, CI changes and prior runtime repairs.

## Current RTX5090 session — repairs included in this delivery

Owner selected RTX5090/Gemma4-12B. Pre-delivery baseline `ac4e56274`, `main`/origin
0 ahead/behind on the pre-development fetch; resume from this delivery as above.
**Two of six new repair/diagnostic loops complete; qualification remains open.**
Earlier laptop identities below are historical.

Runtime: `google/gemma-4-12B-it@707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7`,
served `chromie-gemma4-12b`, SGLang0.5.19/XGrammar0.2.1, existing FP8/BF16 profile.
Provider context65536, Fast context40960/output4096/margin2048; maintained interactive
budgets unchanged. Generated `.env.runtime` was not edited. No model, prompt, schema,
semantic-authority or dependency-version change.

Case43's valid expression128000 collided with XGrammar's parser marker, causing
rule-1 access. Dockerfile builds source `5b4e9ce9e72524037ae24ecd831b9b6604d2eb48`
with marker-2 and native boundary tests; only the native library is replaced.
Patched image `sha256:33692f02a4e43231e0e9294c0d28ed5eed553e2cfe998cd597b97fc1944eb376`,
tag `chromie-sglang:gemma4-fp8` (also `:gemma4-fp8-sentinel`). Previous image retained
as `:pre-sentinel-20260923` for isolated red reproduction, never normal deployment.
Current LLM container71534641b5e742144855e295072ed5f6f9614b79a2bb2c74e6de9645bbc9faa4,
started2026-09-23T03:51:08.813834733Z; zero restarts/OOM through final verification.

Current aggregate identity:
`80ea780c353c656e4d1db479f173414a1f36ee0cb686a62e9d89b68e180187e6`.
Bound source090529d9e0240b132bd0cfb9c5d6e87c7ae6bbef1da2793f55ba88e42398bbfb stayed
unchanged during all75 cases. Subsequent benchmark-storage and delivery-documentation
changes alter repository identity, not evaluated runtime behavior. Final Agent
host/container digest:
`0fca97608fcd8c47be1e5b92f675ec66fc07bd4cf47ff013c313b78ad17c825f`.
Agent/LLM/TTS/ASR healthy. Task-owned simulator/MCP stopped after fresh standing,
safe-idle, empty-task/lanes proof. Soridormi `013f46d19ec5101c4392532ab848e0b0819c2a50`,
branch `codex/turn-count`; existing untracked Open_Duck_Playground untouched.

Diagnostic runner now waits for bound model identity/health after automatic recovery
before independent input admission. Every restart remains a failure; no inference
retry. Missing/replaced identity or recovery deadline stops admission. Original
case failures and blocked dependent turns remain visible. Earlier exact-default
acceptance projection and non-streaming tokenizer count fixes remain preserved.

`R=.chromie/acceptance/rtx5090-resume-20260923/` (private/ignored, not in Git):

- `crash-llmcall_agent_12fdcd73e7b3429e.json`: exact old Fast request,
  SID5233010a, schema SHA256
  `93554a3ccfaecc39009b9f73b4f88e6bc60328779d645e532c5101c730017cc2`.
  `crash-fast-cpu.log`, `crash-fast-cpu8.log`: original0.2.1 segfaults on CPU;
  concurrent GA schema compiles. `crash-lookahead-native.txt` identifies the valid
  colliding expression; `sentinel-focused-red.log`/`sentinel-focused-green.log`
  prove native rejection/acceptance/reset at127999/128000/128001 before/after.
- `compiler-corpus-manifest.json`, `sentinel-image-corpus-results.json`:81 exact
  wire schemas attempted,76 compile/five handled pre-existing minItems/prefixItems
  errors, zero crashes. `sentinel-image-build.log` retains native parser and64
  backend cache tests. No Qwen crash reproduction claim; historical artifacts absent.
- `sentinel-exact-native-result.json`: original exact request completes HTTP200,
  full stream/stop, JSON and independent Schema validation. No Host semantic approval.
  `sentinel-focused/`: two nods complete, safe idle; legacy speech gate fails.
  `sentinel-startup-readiness.json`: real starting→healthy wait46.51s. Recovery
  after an actual crash is tested with controlled runner states, not induced live.
- `sentinel.patch`, `sentinel-runtime-identity.json`, `sentinel-live/`,
  `sentinel-live.log`, `sentinel-live-exit.txt`: **75/75 attempted,12 mechanical
  passes/63 failures**, exit1, zero service restarts. All75 readiness checks plus
  final continuity check pass. Eight dependent turns remain blocked; raw
  cohort_complete/qualification_complete are false.
- `sentinel-case-review.json`: every case manually judged. Of12 mechanical passes,
  five pass semantic review, three partial, four fail. Raw automatic review-pending
  fields are preserved; companion adjudication does not rewrite the frozen score.
  `sentinel-catalog-snapshot.json` supports capability/body-claim checks.
- Exactly one final bundle `.chromie/debug/debug_bundle_20260923_122848/`, archive
  `/home/chromie/Downloads/chromie_debug_bundle_20260923_122848.tar.gz`.
  `sentinel-native-calls.jsonl`:300 unique cohort calls;600 references verified,
  zero parser gaps/mismatches in `sentinel-native-integrity.json`. Separate Agent
  stdout/stderr avoid access-log interleaving. UMI records can be provider-neutral;
  do not label all300 as exact wire requests.
- `recovery-focused.log`:89 tests. `canonical-sentinel.log`:145 benchmark,
  **3823 main/1096 subtests,20 legacy** pass, two existing warnings; policy/ownership/
  static/config/docs included. `sentinel-level-a/`:45/45,15 classes.
  `sentinel-final-agent-source.json`, `sentinel-final-source.json`,
  `sentinel-final-services.txt`, `sentinel-final-provider-status.json`: final proof.
- Earlier `live/` baseline and `rerun/` tokenizer loop each scored6/75; each has
  its own all-case review and one bundle (093159 and095650). Old rerun case43 crashed,
  cases44–75 raced restart. Those are historical failures, not current availability.
  `REVIEW.md` contains actual module I/O, root cause, all-case clusters and limits.

No physical microphone, audible speaker, robot, supervised voice, target closure
or release claim. No new maintained document, environment variable, runtime switch
or semantic stage. Remaining priority: handled grammar400 boundary, acceptance
mismatches, UMI/GA/Planner/SC semantics and speech prepared-start coordination.
Do not weaken source provenance, force body-only speech or retry rejected prompts.

For the next reviewed repair, rebuild the pinned image if its source changes, start
Chromie with `./scripts/start_chromie.sh --architecture-validation --no-orchestrator
--keep-services`, and launch `./scripts/start_soridormi_mujoco.sh --no-viewer` from
`/home/chromie/github/soridormi` in its own terminal. Use Python3.12 for native runs.
From Chromie root, choose a fresh evidence directory and bind the actual revision:

```bash
export PATH=/home/chromie/miniconda3/envs/Chromie/bin:$PATH
set -a
source .chromie/voice-runtime/orchestrator.env
set +a
python scripts/capture_runtime_identity.py --verify-agent-source chromie-agent
python scripts/capture_runtime_identity.py --allow-dirty \
  --compose-override .chromie/voice-runtime/compose.voice-mujoco.yaml \
  --output "$NEXT_EVIDENCE/runtime-identity.json"
python scripts/general_ability_acceptance.py --mode live-text --keep-going \
  --assertion-scope full --execute --soridormi-repo /home/chromie/github/soridormi \
  --runtime-identity "$NEXT_EVIDENCE/runtime-identity.json" \
  --evidence-dir "$NEXT_EVIDENCE/live"
./scripts/collect_debug_bundle.sh
```

Set `NEXT_EVIDENCE` to a new directory first. Retain the failing exit code and run
that final collector exactly once even on failure. Do not edit/restart between
cases; review every case before selecting another broad repair. Re-capture identity
after any source/service change. Fetch upstream before development and before push.

## Historical laptop checkout and runtime

- Chromie `/home/chromie/github/chromie`, `main`, remote
  `https://github.com/TimeTreker/chromie.git`; HEAD/fetched origin before editing
  `542aefd08d4ca017e5ae11815dbf39ee8e2bae36`, 0 ahead/behind. This delivery includes all repairs/tests/request-artifact
  migrations and the all-case diagnostic runner. No remote Issue was created.
  The new delivery hash is intentionally not self-embedded; use the latest commit
  containing both handoff owners.
- Live launcher Python: `/home/chromie/miniconda3/envs/Chromie/bin/python` (3.12).
  Final canonical/replay/Level A commands used `/home/chromie/miniconda3/bin/python`
  (3.13.13); both are local test runtimes, not model changes.
- Fixed RTX4090 Laptop / SGLang `chromie-qwen35-4b`, host
  `http://127.0.0.1:30000/v1`. This does not requalify RTX5090/Gemma.
- Generated profile `.chromie/voice-runtime/orchestrator.env`, maintained
  `scripts/start_voice_mujoco.sh`. Never edit `.env.runtime` directly. Containers
  use service names; host tools use loopback.
- Soridormi `/home/chromie/github/soridormi`, branch `codex/turn-count`, revision
  `013f46d19ec5101c4392532ab848e0b0819c2a50`. Existing untracked
  Open_Duck_Playground preserved; no source changes.
- Agent package and host both hash
  `a88ffaeb7781a3753d134cc9534d73a1fc61ac653d30d1511c3594ac6eff9487`.
  Rebuilt after each retained production fix with resolved service configuration
  preserved. LLM/model/profile configuration unchanged throughout live cohorts. The latest
  all75 run caused one automatic LLM restart; stable-service qualification fails.
- Final Agent/LLM/TTS healthy; ASR off. Existing TTS cached model and supported
  `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1` options remain from earlier startup.
  No audible playback claim. Task-owned simulator/MCP stopped after standing,
  safe-idle, empty active tasks/lanes proof. Launcher “stopped unexpectedly” text
  followed our explicit shutdown signal, not a cohort crash.

Latest all75 live identity: `b15ae287f34f78201ac51380d985290b06f1eecae801cd5a1c10eaf367c29d1c`.
Later fixture/doc changes alter repository identity, but not deployed Agent source.
Capture a new identity for future runs; never reuse it after source/service changes.

## Latest all75 diagnostic and six-loop resume

`R=.chromie/acceptance/all75-20260923/`. Raw evidence is private/ignored and is
**not in Git or available automatically on another machine**. The committed facts
below are sufficient to reproduce the originating scenarios; transfer raw evidence
separately only with an appropriate private channel. No raw logs/payloads are pushed.

- `live/summary.json`: all75 attempted, 1 passed/74 failed, **1.33%**; zero skipped
  independent cases. Case 5 `walk_then_turn_right` passes. Dependent turns blocked by
  failed prerequisites remain unrun; `cohort_complete` and qualification are false.
- Cases 1–22: meaning/action/concurrency, contract and oracle failures. Case 23
  `contextless_turn_it_up` (SID `c16f6814`, input “调大一点。”) crashes the model
  service during Fast grammar compilation. Cases 24–75 (52) fail availability,
  not measured semantic inference. No source edits/manual restarts between cases.
- Exactly one bundle: `/home/chromie/Downloads/chromie_debug_bundle_20260923_063530.tar.gz`.
  `native-calls.json` retains 120 call records, including failed requests;
  `llm-crash.log` retains SIGSEGV and `docker inspect` reports no OOM, restart count 1.
- `harness-red.log` → `harness-green.log`: six failing-before regressions, **80 passed**
  after. `canonical.log`: **145 benchmark; 3,795 main/1,092 subtests; 20 legacy pass**,
  plus repository policy, test ownership, Ruff/mypy, configuration/docs; two warnings.
- `crashing-schema.json` / `llmcall_agent_14a9d86fc5a2433b.json`: exact Fast wire
  request, valid 143,403-byte schema without empty enums. UMI call
  `llmcall_user_meaning_interpreter_fe37ff50a467406f`, GA call
  `llmcall_agent_b952fc2b12824b76` precede it.

Actual failure workflow:

| Owner/boundary | Material input → observed output; expected output | Verdict/handoff |
| --- | --- | --- |
| Text Host → UMI | Contextless adjustment admitted under fresh simulator preflight; UMI returns meaning DTO | Admission correct; semantic adequacy still reviewed separately; SID above |
| GA → Fast | Accepted interpretation/Goal context produces the retained Fast schema/request | Request reaches provider; no invented Host repair |
| SGLang/XGrammar | Exact schema + actual Qwen BPE vocabulary → native lookahead compilation SIGSEGV | First confirmed service boundary failure; expected compiled grammar or handled error, not process death |
| Agent → Host | Disconnected model HTTP stream → closed failure/no authorized Work | Containment correct; no model output to adjudicate |
| Diagnostic runner | Failed independent case → next case's fresh preflight/admission | Continues all75; subsequent unavailable-service failures retained rather than skipped/pass |

The user authorized **up to six new repair loops**, then requested immediate
commit/push for relocation. **Zero new repair loops completed.** Compiler diagnosis
is loop 1 in progress; no compiler upgrade, prompt change or oracle repair promoted.
Runtime remains SGLang **0.5.19 / XGrammar 0.2.1**, fixed Qwen3.5-4B AWQ.

Resume at these exact boundaries:

1. Reproduce `contextless_turn_it_up` after a fresh identity/healthy service. Native
   CPU subprocess reproducer `reproduce_grammar.py` compiles the retained schema
   with the actual cached Qwen tokenizer, threads 1 or 8 and 512 MiB cache; both
   segfault. A byte-only vocabulary passes. This excludes GPU/OOM/concurrency as
   necessary triggers, not every possible contributing condition.
2. Normalized EBNF roundtrip passes the original request but aborts another retained
   grammar; `rejected-roundtrip.Dockerfile` is private/reverted. Versions 0.2.2,
   0.2.3 and 0.2.4 still crash; 0.2.6/0.2.7 pass the original. SGLang pins 0.2.1,
   so upgrading requires explicit compatibility proof, not an unqualified install.
   0.2.6 rejects 24 GA wire schemas containing empty enums (99 occurrences).
   Private equivalent-false-schema diagnostic compiles all120 retained requests
   (`grammar-wire026-false-enums.log`), but no equivalence/decoding/live qualification
   or production change exists. Installed candidate packages live only in isolated
   `/tmp/chromie_xgrammar*` container directories, never on the serving import path.
3. Then repair the confirmed oracle bug in `scripts/interaction_text_mujoco_check.py`
   `validate_contract`: cases 15 `thanks_after_completed_blink`, 18
   `multi_goal_look_then_blink`, 20 `nod_then_shake_head` omit optional count in model
   args, but matching retained Capability contracts declare default 2. The precheck
   reads `None`, blocks execution and scores failure. Reuse version/request-bound
   default realization already in `scripts/outcome_observations.py`; preserve explicit
   values and reject missing/mismatched contracts or required-field omissions. No
   outcome was retroactively changed to pass. The RTX5090 repair and focused/full
   native rerun results above supersede this historical unimplemented status.
4. Each accepted minimal repair needs focused proof and an immutable all75 rerun,
   one debug bundle afterward and review of every case. Do not repeat rejected
   prompt candidates from the prior18 batch or substitute another model. Keep
   the six-loop limit and distinguish diagnosis from completed repair/rerun loops.

## Earlier retained private evidence

`R=.chromie/acceptance/iterate18-20260922/` (date remains the batch start date).
Raw payloads and service snapshots are private ignored evidence, absent in a fresh
clone. Review privacy before publication. The owner's 18-iteration batch is complete.

| Under R | Evidence and limit |
| --- | --- |
| `REPORT.md`, `iterations.json` | Eighteen iteration outcomes; actual module I/O, confirmed fixes, open semantics, authority/evidence limits. |
| `starting.patch` | Prior dirty work preserved before this batch; hash in iteration ledger. |
| `design.json`, `cases/`, `01_*` through `08_*`, `10_ordered_source_schema/` | Frozen nine-case bilingual/reference/quotation/timing UMI screens. Best 7/9; no prompt promoted. |
| `fast-design.json`, `fast_extended/`, `11_*` through `18_*` | Seven valid Fast meaning controls plus one upstream-defect control; exact requests/raw streams. All candidate cohorts fail. |
| `screen-reviews.json` | Per-case post-hoc review, request/schema/output hashes, timing/options and primary-only evidence limits. Iteration 15 lookup continuation is unproven; private Work DTO errors are not production errors. |
| `09-token-projection-red.log`, `09-token-projection-green.log` | Four failing-before bilingual primary/deep omissions; 45 tests/28 subtests after, including fail-before-HTTP budget proof. |
| `10-schema-red.log`, `10-schema-green.log`, `10-native-decoder.log` | Fifteen backward-pair failures before; 192 tests/118 subtests after; installed XGrammar ordered/reversed proof. |
| `schema-migration.json`, `replay-capture/`, `replay-focused.log` | Only UMI source schema changed in five seeds/23 shared artifacts/6,000 refs; zero response/oracle changes; 104 focused tests pass. |
| `replay6000/summary.json`, `replay6000.log` | 6,000 expected outcomes, immutable source, zero native calls. |
| `canonical.log`, `docs-final.log`, `level-a/` | 145 benchmark +3,789 main/1,092 subtests +20 legacy pass; policy/static/docs pass; 45 Level A pass. |
| `baseline/`, `09-live/`, `10-live/` | Full75 discovered each: 0/4 then 0/3 then 0/3; hard stops, 71/72/72 unrun. Identities, review, native calls and bundle paths. |
| `final-provider-status.json`, `final-agent-source.json`, `final-services.txt` | Final safe idle, source equality and remaining services. |

One debug bundle per live invocation under `/home/chromie/Downloads/`:

- `chromie_debug_bundle_20260922_234939.tar.gz`: baseline, stops on walking+singing.
- `chromie_debug_bundle_20260923_000503.tar.gz`: complete-token projection fix.
- `chromie_debug_bundle_20260923_001052.tar.gz`: ordered-source decoder/current production.

Latest SIDs: compound `5e9ad597`, simultaneous `286d246d`, milk `e6a7dc3d`.
Fast calls respectively `llmcall_agent_60708faba089408e`,
`llmcall_agent_8479d7b564b94449`, `llmcall_agent_2a8788c797d84a50`;
milk UMI `llmcall_user_meaning_interpreter_52b7fda1cf334eed`.
Native call retention counts: baseline16, after-fix9 11, after-fix10 11.

Prior repairs and their evidence remain at
`.chromie/acceptance/full-repair-20260922/REPORT.md`: required-SC freshness,
Activation scope/social context, prior UMI system-paragraph replay migration and test
oracle corrections. Earlier rejected experiments remain under `meaning-first-20260922`,
`activity-timing-20260922`, `umi-source-wording-20260922` and related acceptance roots.
Do not reclassify historical/isolated improvements as qualification.

## Resume commands and stopping rules

No semantic candidate was promoted. Resume the authorized six-loop batch above,
starting with service integrity and the confirmed oracle boundary. Current native
qualification and supervised voice/default target closure remain open. On another
machine, fetch/pull `main`, read Checkpoint/Handoff, regenerate the owned runtime
profile for that machine and verify the declared model is available; do not copy
`.env.runtime` blindly or claim laptop evidence for a different target.

For focused changes and canonical validation, preserve work and verify fresh upstream:

```bash
cd /home/chromie/github/chromie
export PATH=/home/chromie/miniconda3/bin:$PATH
python scripts/check_repository_policies.py
python scripts/check_test_ownership.py
./scripts/run_tests.sh
python scripts/check_docs.py
python scripts/run_workflow_replay.py --workers 8 --evidence-dir NEW_EVIDENCE_DIRECTORY
python scripts/general_ability_acceptance.py --mode level-a --evidence-dir NEW_LEVEL_A_DIRECTORY
```

For a new live aggregate, rebuild/verify Agent after product changes, start
`./scripts/start_soridormi_mujoco.sh --no-viewer` from Soridormi in a separate terminal,
and wait for health/safe idle. Then from Chromie's root:

```bash
set -e
export PATH=/home/chromie/miniconda3/envs/Chromie/bin:$PATH
set -a
source .chromie/voice-runtime/orchestrator.env
set +a
run_dir=$(mktemp -d "$PWD/.chromie/acceptance/full-resume.XXXXXX")
python scripts/capture_runtime_identity.py --verify-agent-source chromie-agent
python scripts/capture_runtime_identity.py --allow-dirty \
  --service chromie-agent --service chromie-llm --service chromie-tts \
  --output "$run_dir/runtime-identity.json"
live_rc=0
python scripts/general_ability_acceptance.py --mode live-text --keep-going --assertion-scope full \
  --runtime-identity "$run_dir/runtime-identity.json" --evidence-dir "$run_dir/live" \
  --soridormi-repo /home/chromie/github/soridormi --execute || live_rc=$?
./scripts/collect_debug_bundle.sh
printf 'Live runner exit: %s\n' "$live_rc"
```

Discover all75, no source/scenario/service edits between cases. The owner-requested
`--keep-going` diagnostic retains every failure and attempts every independent case
under its existing safety guards. It never authorizes unsafe dispatch or emergency
reset. Retain one bundle afterward; judge every attempted case, mark blocked dependent
turns and unavailable inference unknown. Focused screens cannot close the aggregate.
Preserve safe idle before stopping owned services. Text/simulator/PCM is not physical
voice/robot proof. For later delivery, refresh upstream and update both handoff owners.
