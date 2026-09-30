# Chromie Development Checkpoint

## Non-model live workflow repair — 2026-09-30

Pre-delivery Chromie base `e1f4a446860852cfc7f95eae6ab3c6c84f16c496`
on `main` matched fetched `origin/main`. Paired Soridormi remains at pushed
`2af3034a91842ecb9964a45ce24e9bdc18fcde58`; preserve its unrelated dirty
`README.md`, `scripts/run_scenario.sh`, `tests/test_run_scenario_restart.py`, and
`workspace/Open_Duck_Playground` work. Resume from the newest Chromie revision
containing this checkpoint and Handoff, fetch both remotes, and keep the default
target-evidence qualification line open.

The retained patch fixes four non-semantic boundaries exposed by the water-offer
and complete-cohort traces:

- reconcile actually delivered direct SC speech to a newly materialized
  speech-only Goal after concurrent Goal Association supplies canonical IDs;
- treat already observed playback of reused required speech as the prepared-start
  boundary and drop optional body decoration whose common onset is no longer
  provable;
- split independent prepared-start coordination IDs into ordered runtime batches
  instead of rejecting them as simultaneous voice owners; and
- preserve the exact Host-owned optional-decoration tuple on terminal results so
  the live scorer does not turn a dropped optional gesture into required-work
  failure. Required body failures remain hard failures.

The live scenario inventory regression now expects 56 must-pass, 16 core, 8
challenge, and 80 total cases. No prompt, model, semantic Schema, Goal/Planner
authority, capability contract, or deterministic phrase rule changed.

Focused current-source evidence: the prepared-start body-truth case passed 1/1;
the two-expression English identity case no longer reports multiple voice owners
or optional gesture failure, while still failing for model latency and missing
Planner Goal outcome. The focused unit set passed 565 tests with 5 environment
skips and 39 subtests.

The final unchanged-source aggregate at
`.chromie/acceptance/non-llm-system-fixes-20260930/full-candidate-bound/` attempted
all 80 cases and scored 26/80 (32.5%): must-pass 14/56, core 9/16, challenge 3/8.
Runtime identity is
`9e0e4d01530d3b1d32db8792463fafaebb0b4b1e94f9e7021528da3fcc365295`;
it binds dirty source-tree digest
`7466a5f015fd409d2595094176c6076078bc00c8c7c7b1663716a854174f1014`
to base revision `e1f4a446860852cfc7f95eae6ab3c6c84f16c496` and the deployed
`chromie-qwen35-4b` profile. The post-cohort bundle is
`/home/chromie/Downloads/chromie_debug_bundle_20260930_123419.tar.gz`. This is
injected-text, TTS, and MuJoCo evidence, not physical audio, camera, grasp, or
robot proof. This checkpoint and Handoff were finalized after the run; those
documentation-only edits are not part of the retained source-tree digest.

All repaired signatures are absent from the full result. The 31 hard failures are
18 model Goal omissions, 5 invalid Fast streams, 5 UMI/SC contract failures
reported as harness exceptions, and 3 post-run status gaps after hard turn failure.
The dominant remaining failures are model-produced meaning, activation, Goal
segmentation, planning, provenance, and latency errors. Do not add Host inference,
phrase routing, or a second semantic writer to conceal them. Qualify a later LoRA
or model profile against this frozen cohort.

Repository policy and test ownership pass. The focused suite passes as above. The
canonical `./scripts/run_tests.sh` passes policy, ownership, static analysis,
configuration, documentation, and scenario stages, then stops at the already
recorded generated benchmark drift (`6 failed, 147 passed`). Semantic review is
pending for all 80 live cases, `cohort_complete=false` because dependent turns are
not run after hard first-turn failures, and default qualification remains open.

Next work is model-profile/LoRA qualification or independent semantic review of
the retained bundle. If another non-model symptom appears, reproduce its earliest
boundary on the unchanged cohort before editing; do not tune against a single
utterance. Re-run the canonical gates after the existing benchmark fixtures are
reconciled by their owning delivery line.

## Full water-offer diagnosis and console-noise repair — 2026-09-30

Pre-delivery Chromie base `1ed1e1f0eade2f620e0ccafa1323790ae88ff477`
on `main` matched fetched `origin/main`. Paired Soridormi scenario revision
`2af3034a91842ecb9964a45ce24e9bdc18fcde58` is pushed on `origin/main`;
its unrelated dirty checkout files were not included. Resume from the latest
Chromie revision containing this checkpoint and Handoff, fetch both remotes,
and preserve the active default target-evidence qualification line.

The reported three-turn water-offer episode is now a maintained must-pass live
scenario. The matching simulator scene supplies a person 1.5 m to Chromie's
right, one water bottle 3 m to its left, and a milk-bottle contrast 10 m ahead.
The live text console keeps semantic/runtime records at their configured level
while suppressing repetitive `httpx`, `httpcore`, and `mcp` transport polling
lines. This delivery does not change a semantic prompt, model, Schema, DTO, or
runtime decision authority.

One frozen, revision-bound `--keep-going --assertion-scope full --execute`
aggregate attempted all 80 discovered cases: 19 passed, 61 failed, 0 skipped
(23.75% automated pass rate). Must-pass was 9/56, core 7/16, and challenge
3/8. Thirty-six hard integrity failures comprised 20 model-contract failures
(17 Goal omissions and 3 invalid Fast streams), 9 harness/runtime exceptions,
6 unavailable per-case post-run status records, and 1 cognitive-runtime
exception. Diagnostic earliest-boundary clustering across all failures was:
31 response/user-outcome, 15 Planner contract, 5 live harness, 5 cognitive
runtime, 3 Fast stream, and 2 Goal Association. A same-session, non-independent
semantic review judged 7/80 pass and 73/80 fail (8.75%); it is diagnostic only,
not independent semantic closure. The cohort is complete for case attempts but
qualification remains failed because hard failures cannot be averaged away.

For the exact water episode, turn 2 preserved some thirst/help meaning but Social
Cognition answered as if Chromie were thirsty; turn 3 failed to bind `sure` to
Chromie's water offer, Goal Association returned to the greeting, and no
`soridormi.acquire_and_deliver_resource` request was committed. Six bounded
prompt candidates were screened. The furthest candidate reached Planner, which
invented two duplicate clarification actions with the same InformationGap ID
instead of executing the accepted offer. Every candidate regressed a frozen
contrast or failed end to end, so all semantic candidates were rejected and
reverted. Current evidence therefore supports model-inference weakness under
the deployed 4B profile as the dominant semantic limitation, with separate
harness/status evidence defects; it does not prove the model is the only cause.

Retained aggregate evidence is
`.chromie/acceptance/full-water-diagnosis-20260930-0956/`; runtime identity hash
`6027768ce3fbe1c03b4e52719817c1751c543d05e652039836faf3b5e2c878cf`
records SGLang `chromie-qwen35-4b` for Agent and all cognitive roles. The one
post-cohort bundle is
`/home/chromie/Downloads/chromie_debug_bundle_20260930_100809.tar.gz`.
This is live text plus MuJoCo evidence, not microphone, speaker, camera, or
physical-robot proof. After the aggregate, the simulator was reset and observed
standing and safe idle with no active task or execution lanes.

Focused console tests passed 18. Scenario discovery/check passed 15 ability
classes, 45 Level A cases, and 80 live-text cases. Repository policy, test
ownership, and docs checks passed. The canonical `./scripts/run_tests.sh` still
failed at the known benchmark-contract drift (`6 failed, 147 passed`), so the
canonical gate remains open. Soridormi scenario validation and focused runtime
tests passed; its host-wide gates remain limited by missing host `zmq`, while the
runtime-container full suite had 15 checkout-mount/path failures after 818 passes
and 7 skips.

Next work is to separate model-profile qualification from the five harness and
status evidence boundaries, repair the earliest reproducible non-semantic
boundary without phrase routing or a second semantic authority, then rerun a
focused case and the complete cohort on one unchanged revision. Do not promote
any of the six rejected prompt candidates. A larger/different model may be
qualified later as an explicit profile change; no such model change is retained
or claimed here.

## Nine-turn owner conversation repair — 2026-09-30

Pre-delivery Chromie base `6b83a8496d5b3dd9b2a7f78824250eb117f6fb19`
on `main` matched fetched `origin/main`; paired Soridormi remained at
`fc8c6f61013640e09bb5de978c59e9ce04423f6d` with its pre-existing dirty work
untouched. Resume from the latest revision containing this checkpoint and Handoff,
fetch both remotes, and preserve the active aggregate qualification line.

The owner-supplied nine-turn episode is now a maintained live scenario. Retained
source repairs scene-tool registration, native fresh communication-ID decoding,
cross-turn activity-ID rebinding, and nested stale-task projection into Social
Cognition. Six whole-conversation iterations completed all nine turns. The retained
revision scored 2/9; a raw-history candidate scored 0/9 and a final current-scope
prompt candidate remained 2/9 with semantic regressions, so both were rejected.

Open earliest boundaries are UMI speaker perspective and overlap, missing useful
Planner activation for the water request, GA association to a stale identity Goal,
and SC session-language enactment. Do not claim the conversation fixed or broaden
the retained mechanical repairs into phrase routing, a second semantic call, or a
model change. Resume by qualifying those boundaries independently against the frozen
nine-turn contrast before another aggregate edit.

Retained live evidence is under
`.chromie/acceptance/conversation-repair-20260930/nested-fixed/`; its bundle is
`/home/chromie/Downloads/chromie_debug_bundle_20260930_085555.tar.gz`.
This is silent text plus MuJoCo simulation evidence, not physical audio/camera/robot
proof. The final simulator status was safe idle with no active task.
Focused Social Cognition/scene/manifest validation passed 183 tests with 5
environmental XGrammar skips; the equivalent 20 native checks passed in the serving
image. Scenario discovery and test ownership passed. Selected Level A evidence was
16/19; four assertions in three scenarios retain the known missing
`body_effect_family` fixture drift. The canonical gate again stopped at the same six
benchmark dataset/fixture failures after 147 passes; later test stages did not run.

## Thirst confirmation, provider source, and water route — 2026-09-25

Pre-delivery Chromie base `c97aab36eb97217b15b7d9932157da55180caaeb`
on `main` and paired Soridormi base `2d8296ee61ac1d4383310680db25109c84aba5e5`
on `main` matched their fetched upstream before editing. Resume from the
latest delivery commit containing this checkpoint and Handoff; fetch both
remotes before further development. The active aggregate compound-planning
Issue and default target-evidence gate remain open.
The paired Soridormi delivery is `df74003230f0104784823d74cd066adb6fc84597`
on pushed `origin/main`.

The retained 16:02 thirst episode's first turn correctly offered water; the
second UMI/GA/SC path produced a water body Responsibility and a neutral
acknowledgment. Fast Planner's dynamic Schema then misclassified the
provider-owned `source` as a missing user location and demanded a current-turn
token citation. It emitted one acquire/deliver Activity plus contradictory
source/recipient clarification and falsely cited `water` for the source. The
Host rejected the Plan before Soridormi dispatch. The repair projects the
existing Soridormi source-resolution/perception contract into Fast Schema and
Host: unbound source can be only `status=unknown` or `provider_resolved`, with
no current-turn citation or location clarification. A production-shaped
Gemma replay emitted one schema/DTO/Host-valid acquire/deliver Activity with
unknown source, no citation, and no clarification. Two new scenarios retain
the two-turn confirmation and a direct water request.

Paired Soridormi now resolves `water` against the three equivalent observed
`bottle of water` markers, holds the selected object reference, and requires
a unique recipient. Three 300-second normal-command MuJoCo attempts timed out
without pickup or delivery; a fast bounded command completed the route.
The provider defaults to normal and uses observed progress to recover a
non-slow command within its advertised speed presets. Isolated default-scene
MuJoCo proof: water 5.0→0.899 m in 144.13 s, user 5.738→0.900 m in 198.85 s,
both legs recording bounded recovery, mock handover completed, final
`safe_idle=true` and no active task. The scene mock is not camera or hardware
proof.

Chromie focused Planner tests passed 162 tests/82 subtests; scene discovery,
repository policy, test ownership, and docs checks passed. The canonical
`./scripts/run_tests.sh` still stops at the pre-existing benchmark drift,
6 failed/147 passed. Level A robust-intent/composable planning passed 9/13;
four older UMI body-action fixtures omit `body_effect_family`. The user's
running text Host holds `/tmp/chromie-orchestrator.lock`, so the attempted
aggregate live baseline could not start; no changed-revision end-to-end
Chromie text/voice proof is claimed. Soridormi focused runtime/manifest tests
passed 124; the full suite with the checkout mounted at `/app` and the
isolated scene stopped passed 825 tests/8 skips. Governance and compile pass.
Its body-concurrency gate passed 179 tests/4 skips.

Next: after the operator text Host can be restarted, rebuild/verify the
current Chromie Agent and Soridormi MCP source, run the retained thirst and
direct-water live-text cases (five or fewer utterances with the milk contrast),
inspect one debug bundle, then the complete cohort if the active gate allows.
Keep the existing compound-planning blocker and canonical benchmark drift
separate. Physical microphone, speaker, camera, and robot proof remain open.

## Live text console interruption path — 2026-09-25

Pre-delivery Chromie base `618569ab430df7981ed08fb7b4ae4599cc36180b`
on `main` matched fetched `origin/main`; resume from the latest `main` commit
containing this checkpoint and Handoff. Paired Soridormi is now on `main` at
`2bf8d67` (scenario launcher restart), but this Chromie patch changes no
Soridormi source or physical Skill. The active aggregate compound-planning
Issue and target-evidence gate remain open.

The user's running text client could not submit `stop` during a long task:
client input waited for a `done` frame, and the Host console waited for complete
turn/session closure before reading another socket line. The console now reads
input and replies independently, runs each admitted text turn through Host's
existing routed-turn lifecycle, keeps protective reflex priority and text
channel provenance, and sends turn completion separately. Session-bound
history forwarding prevents two overlapping turn workers from printing the
same reply. Interactive `/quit` and Ctrl+C close the client; neither is a
robot cancellation. Type `stop` for scoped work cancellation, then verify
the resulting state; use the independent emergency-stop path in an emergency.

Focused console, reflex, barge-in, shutdown, identity and input-runtime tests
pass 65 tests/42 subtests on the final source, with explicit ordinary-follow-up
and stop while prior input remains active. Level A safety and overlapping
turn closure passed 3/3 and 6/6. Continuity passed 3/4 because one older UMI
body-action fixture omits required `body_effect_family`. Policy, ownership
and docs checks passed. `./scripts/run_tests.sh` still fails in the benchmark
stage at 6 failed/147 passed; a separate main suite started before the final
reply-filter edit had 125 failed/3713 passed, and its failures have not all
been attributed. No rebuilt Host or
current-revision live text/voice/robot proof exists: the user's running
`--text-console` Host was intentionally left running on its old loaded code.
Soridormi status was `safe_idle=true`, `active_task=null` at inspection.

Next: stop the old Host in its launcher terminal when convenient, restart
`./scripts/start_chromie.sh --text-console`, reconnect the text client, and
run a supervised long-task → immediate `stop` → cancellation/safe-idle probe
before claiming live interruption latency. Then return to the retained
aggregate `compound_walk_nod_turn` failure in the prior checkpoint, complete
the canonical gate and full target-evidence profile. This source result does
not qualify microphone, speaker, camera or physical robot behavior.

## Reported-resource dialogue and long dispatch repair — 2026-09-25

Pre-delivery Chromie base `b0c2dfec004a082702f71d14148791aefd67a5bf`
on `main` matched fetched `origin/main`. Resume from the latest `main` commit
containing this checkpoint and Handoff. Soridormi checkout
`531268c53c1029ab4875ddeb623046314e48ab4b` remains unchanged; the running
MCP source identifies `5d235b8aee35efd4788b0dd1de791753275618f9`.

The retained two-turn report → milk delivery exposed four boundaries. Social
Cognition treated a user text report as first-person perception. Fast Planner's
resource argument mapping failed to recognize `source_location` and
`source_distance` bindings, allowing a false current-turn citation; its input-gap
schema similarly offered provider-owned source/recipient coordinates as missing
human input. The checked-in Soridormi execute-plan timeout and Host request
ceilings were shorter than the combined skill's declared bound. Finally, the
Host idle sweeper abandoned the session during a valid long detached dispatch.
This patch strengthens report-only speech/UMI source-role guidance, projects and
validates binding-grounded Planner arguments without current-turn provenance,
constrains the typed source distance, excludes satisfied provider-owned input
gaps, keeps the plan to its sufficient resource-delivery Activity, aligns bounded
timeouts, and keeps sessions live until their accepted dispatch resolves.
Soridormi owns its final safe posture; no extra `stand_idle` Work is needed.

Current-revision focused live text + MuJoCo evidence in
`.chromie/acceptance/reported-milk-fix9-20260925` passed mechanically and was
manually reviewed: first reply `Got it.`, second-turn UMI preserved bottle,
recipient, `source_location=in front of you`, and typed 50 m
`source_distance`; Fast Planner emitted one acquire/deliver Activity with
`argument_sources={}`; Soridormi completed, reported `safe_idle=true` and no
active task; the Host session ended `complete` after 340.4 s. The harness's
semantic reviewer remains pending, so this is a manually adjudicated focused
simulator result, not cohort or physical voice qualification. Its bundle is
`/home/chromie/Downloads/chromie_debug_bundle_20260925_135912.tar.gz`.
The full 76-case live cohort on the same candidate stopped at case 1/76:
`compound_walk_nod_turn` failed Fast Planner Responsibility coverage before
physical execution. Retained evidence:
`.chromie/acceptance/aggregate-candidate9-20260925` and
`/home/chromie/Downloads/chromie_debug_bundle_20260925_140141.tar.gz`.
The cohort is incomplete and the default target-evidence profile remains open.

Final focused UMI/Planner/Session/Provider regressions passed 364 tests/165
subtests. Repository policy, test-ownership, docs and scenario-library checks
passed. The two relevant Level A classes passed 8/11; three older reference
cases fail the current UMI contract because body-action fixtures omit
`body_effect_family`. The canonical
`./scripts/run_tests.sh` still stopped at the pre-existing benchmark fixture
drift (6 failed/147 passed); later stages did not run. Next: diagnose the
compound case from the retained aggregate, rerun its focused general-ability
class and the complete live cohort on one unchanged candidate, then close the
canonical gate and target evidence. Ordinary turns still do not invoke the
simulator observation adapter; this repair does not claim camera, microphone,
speaker, physical robot, or automatic water-finding behavior.

## Simulation scene object-set adapter — 2026-09-25

Pre-delivery Chromie base `6e51ad2a443e0bc7d6dcf47f8f109a8f6ad33e69` on
`main`, matched `origin/main`; expected resume revision is the latest `main`
commit containing this checkpoint and Handoff. Paired Soridormi commit
`5d235b8aee35efd4788b0dd1de791753275618f9` on `main` adds a standing user to the default scene plus a
return walk after milk pickup. Soridormi's direct MuJoCo run observed the milk
10.006→0.844 m and recipient 9.412→0.892 m, mocked handover, and final
standing/safe idle. That run used a dirty successor of `06d5d4f` with the
service source revision still set to that older commit; it is simulator proof,
not a paired committed-revision or Chromie conversation proof.
Soridormi's full dependency-complete container suite passed 819 tests with 4
skips; the focused body suite passed 177 tests. The committed MCP runtime
reported its revision and both scene markers on the restarted default scenario.
Its full public MCP call then walked to milk 10.008→0.834 m and back to the
user 9.425→0.883 m, completed the mock handover, and ended standing/safe idle
with no active task. The scene was reset to its starting pose afterward.

Chromie's explicit Soridormi scene adapter now admits a bounded set of marked
simulator objects under the original observation reference. This closes the
immediate object-set rejection introduced by the simulated user and permits a
future water marker without claiming one exists. Focused adapter tests: 3 passed;
policy, test-ownership, and docs checks passed. The canonical `run_tests.sh`
benchmark stage remains failing at 6 failed/147 passed on the pre-existing
semantic corpora; later stages did not run in that invocation. Ordinary turns
still do not request scene observations. The reported first-turn unsupported
“I see” speech and inherited-location current-turn Planner citation remain open.

Resume by wiring a fresh Soridormi scene read into an explicitly admitted
information-acquisition Work path, then qualify scene-grounded speech and
resource planning on the target model with the frozen contrast method. A water
example additionally requires a real water fixture in a scenario and provider
resource matching. Re-run the full canonical gate and highest safe live profile
before any end-to-end Chromie claim. Camera and hardware perception are unrun.

## Simulation milk-scene observation slice — 2026-09-24

Current base is `08e40d2eebbc03d962895d5bb32cfa832adf69bf` on `main`, paired with
Soridormi `013f46d19ec5101c4392532ab848e0b0819c2a50` on `codex/turn-count`.
The paired Soridormi source commit is
`f9cf6ac14e63e2c69caca7665b7ed9d16e4861df`; Chromie's expected resume
revision is the latest `main` commit containing this checkpoint and Handoff.
This delivery adds a Soridormi-owned optional MuJoCo milk-bottle scene marker,
read-only simulation-only observation tool, and Chromie source-specific adapter into
Goal-free Situation. The adapter preserves the Soridormi observation reference and
cannot turn a user's text into perception. It is explicit; ordinary text turns do
not invoke it. The first-turn ungrounded “I see” response and Fast Planner's false
current-turn citation for inherited location remain open. `stand_idle` necessity
and latency remain unqualified; do not treat the mock as real camera or hardware
evidence.

Focused Chromie adapter tests pass (2); policy, test-ownership and docs gates pass.
The broader Chromie gate remains failing on semantic/workflow fixtures (benchmark:
6 failed/147 passed; main: 120 failed/3708 passed). Soridormi's dependency-complete
container suite passed 803 tests/5 skipped before final visual cap and output-field
tidying; focused post-tidying checks passed 70 tests and body concurrency passed
164 tests/4 skipped. No live scene-to-speech or physical test was run. Resume by
wiring an explicitly admitted fresh observation to the relevant cognition path,
then qualifying grounded first-turn speech and separately repairing Planner
location provenance with a frozen contrast cohort. Run the canonical gates and
highest safe live profile before claiming the two-turn episode fixed.

## Responsibility association + natural interaction patch pending — 2026-09-24

Current base is `cc4276625ffde7d3dd786b99cf48729e0edc49b4` on `main` after the owner-applied
foreground-turn containment patch. Follow-up owner design clarified that a current UMI
Responsibility is not itself GA-authored Goal meaning: UMI owns WHAT; GA only associates that
Responsibility with retained Goal history; trusted lifecycle code mechanically materializes Goal
identity from UMI when no retained Goal matches. `continuity_scope=turn` is interaction lifetime,
not `non_goal` and not a Planner ban. A joke/chat can therefore receive an interaction-lifetime
Goal and Planner HOW cognition while SC remains the sole wording owner.

The patch also contains late GA failure after already delivered conversational success: retained
diagnostics cannot trigger apology/retry/duplicate speech. SC/Mind now default to natural
conversational economy and do not invent user emotion/motive to justify extra speech. Ordinary
first-person identity is Chromie/a twelve-year-old girl; robot/AI labels are not volunteered, while
robotic embodiment remains truthful when directly asked or materially relevant. Expanded focused
validation: 807 tests / 561 subtests before final documentation edits; repository ownership/policy
gates passed. Soridormi hidden reset/recovery evidence remains a separate provider boundary.

## Foreground-turn containment patch pending application — 2026-09-24

Current base is owner-applied `main` revision `1e10bc825cee8d72a1f139b25a82e3492edc75b8`
(after working conversational context and tiered Memory/Goal residency). The retained
RTX4090 bundle `chromie_debug_bundle_20260924_003802.tar.gz` proves the reported
weather-topic fixation predates those two Memory patches. UMI preserved the new utterance
meaning; the earliest wrong boundaries were interpretation-time SC treating unbound active
Goal state as current-turn authority and GA permitting turn-local conversational speech to
acquire old Goal identity. The initial weather turn additionally exposed premature
SC task-result speech before trusted Evidence.

The pending source patch makes current accepted Responsibilities foreground, hides broad
unbound Goal/Work state from initial SC, restricts initial non-speech task communication to
pre-Evidence acknowledgement, forces `continuity_scope=turn` to GA `non_goal`, and narrows
illegal turn-local Planner activation without inventing Planner readiness. Focused
validation is 277/277 tests plus 107 subtests; expanded cognition/runtime validation is
727/727 tests plus 564 subtests. Resume by running repository policy/full/docs gates, then
live-test weather → doubt → Chinese/language question → joke and verify the old weather Goal
remains background rather than capturing independent turns.

Updated 2026-09-24. Audience: the owner and the next development session.
This is the current resume point; [Status](docs/STATUS.md) owns implementation/evidence
claims, [Roadmap](ROADMAP.md) owns delivery order, and [Handoff](HANDOFF.md) owns volatile
identities, retained artifacts and commands. Earlier snapshots remain in Git history.

## Local archive defect-repair patch — 2026-09-23

The owner supplied `chromie_20260923_archive.zip` after a debug run that exposed Planner/SC
authority, concurrency, failure-presentation, and execution-evidence defects. The paired debug
bundle reports source revision `af5e11eb4e86a0bde18dfdc0d0b2f48494b01066`; the archive
itself contains no `.git` metadata, so this patch is source-relative and has not been committed,
pushed, or live-qualified here.

Implemented repair: every fresh admitted addressed UMI result must request turn-wide Social
Cognition; independent concurrent effects remain separate Responsibilities; Fast/Deep Planner
receive no optional social-expression candidates/style/history; Fast validation rejects
social-only decoration mixed into unrelated task Work; explicit parallel groups must be encoded
as parallel members; terminal Work failures re-enter SC; raw internal failure labels no longer
reach ordinary TTS; and reported embodied safety faults (`emergency_stop`/`fallen`) now block
success evidence. The hidden MuJoCo auto-reset remains an external contract blocker because
Soridormi reports no per-execution reset/recovery fact to Chromie.

Archive-local focused/runtime validation passed after these changes. The canonical wrapper and
docs gate cannot be fully reproduced from this zip because its benchmark fixture tree is absent;
Ruff is also not installed in this execution environment. Re-run the complete maintained gate on
a full checkout before commit/push, then live-qualify the concurrent walk+wave, milk-delivery, and
weather conversation on the target runtime.

## Owner-requested development delivery — 2026-09-23

Owner requested commit and push **without tests**. Pre-delivery baseline is
`ac4e56274ecac59cff51e84d734dee05d04f7da9` on `main`; the delivery fetch confirmed
0 ahead/behind `origin/main`. Resume from the latest `main` commit containing this
checkpoint and Handoff. Scope includes the RTX5090 compiler/recovery repairs,
earlier acceptance-default/tokenizer repairs, and benchmark storage cleanup below.

Tests and check suites: **not run for this delivery, at owner request**. The latest
observed local gate is the storage-cleanup gate below; subsequent edits only update
delivery documentation. Prior live evidence binds the evaluated runtime and source,
not a fresh qualification of this commit. Active line #24/#32 and all live blockers
remain open. Private ignored evidence must be transferred separately for another
machine; it is not included in Git. Follow the ordered diagnosis and resume commands
below and in Handoff; this delivery does not approve target qualification or release.

## Benchmark storage cleanup — 2026-09-23

Owner authorized removing unnecessary tracked benchmark bulk. Removed **6,076
expanded replay files/288,195,530 bytes (about275 MiB)** from the index; tracked
benchmark files fall from9,691 to3,615. Code, schemas, authored datasets, five
prototype episodes and the checksum manifest remain tracked. Expanded inputs are
ignored local cache, restored from pinned revision `ac4e56274ecac59cff51e84d734dee05d04f7da9`.
Every original case/packet hash, answer, oracle and split is unchanged. Existing Git
history is retained, so this reduces the current tree, not historical clone size.

The canonical gate restores missing inputs offline from local history. Shallow
checkouts/CI explicitly run `python -m benchmarks.regression restore-fixtures --fetch`.
Changed local fixtures fail rather than being overwritten; absent cache cannot
silently skip the60 family regressions. Cold-cache restoration verified all6,076
files. Canonical **153 benchmark,3823 main/1096 subtests,20 legacy tests** pass;
two existing warnings. No production behavior change or new native qualification
claim; RTX5090 failure evidence below remains current for the evaluated runtime.
Evidence: `.chromie/acceptance/benchmark-storage-20260923/`. This delivery includes
the removals with the manifest, restoration code, ignore rules and CI setup.

## RTX5090 continuation — 2026-09-23

Owner selected maintained **RTX5090/Gemma4-12B** qualification. Pre-delivery baseline
is `ac4e56274`; fetched `main`/origin were 0 ahead/behind before development. The
repairs below are included in this delivery. Active delivery line remains #24/#32.
**Two of six new repair/diagnostic loops are complete; qualification remains open.**

The case43 XGrammar crash is now causally reproduced and repaired. Its valid
lookahead expression128000 collided with XGrammar0.2.1's internal marker128000,
causing an invalid rule-1 access. The pinned image now builds exact0.2.1 source
with marker-2, outside the legal expression domain. No dependency-version, model,
semantic prompt/schema or authority change. Actual native parser tests fail before
and pass after at127999/128000/128001. The original exact request now completes
native inference with valid JSON/Schema; that is not semantic approval of its output.

The second defect was recovery admission: Docker already restarted the crashed
service, but the runner immediately attempted the remaining cases during startup.
Identity-bound diagnostic runs now wait for healthy recovery before independent
cases, retaining the original failure and every restart. Missing/replaced identity
or recovery timeout stops admission. No inference retry or semantic repair call.
Earlier optional-default acceptance and tokenizer-transport repairs remain intact.

Current-image corpus: **81 schemas attempted,76 compile, five handled pre-existing
minItems/prefixItems errors, zero crashes**. Focused nod execution completes two
nods and safe idle but still fails a legacy speech requirement. Current full run
attempts **75/75:12 mechanical passes/63 failures**, zero model restarts/OOM, with
unchanged source and service identity throughout. All75 manually reviewed: the12
passes contain five semantic passes, three partials and four failures. Eight
follow-up turns remain unrun; raw cohort/qualification completion remain false.
Case43 now fails an unrelated Fast argument-provenance check, not compilation.
The previously blocked cases44–75 now have independent diagnostic results.

Validation: recovery suite **89 passed**; canonical **145 benchmark,3823 main/
1096 subtests,20 legacy tests** passed, two existing warnings; policy/ownership/
static/config/docs included. Level A **45/45**,15 classes. Exactly one final bundle;
300 native-call records/600 references verified, zero gaps/mismatches. No maintained
document, environment variable, runtime switch or semantic-owner growth.

Evidence root `.chromie/acceptance/rtx5090-resume-20260923/`: `REVIEW.md` records
actual module I/O and cause; `sentinel-case-review.json` judges every case. Handoff
owns identities, artifacts and resume commands. Next bounded diagnosis: handled
minItems/prefixItems grammar400s and acceptance mismatches, then retained UMI/GA/
Planner/SC and prepared-start failures. Unresolved-destination motion and false
capability/body/rumor claims remain hard semantic failures. Do not weaken provenance,
force speech for body-only cases, or repeat rejected prompt candidates.

Agent/source matches; Agent/LLM/TTS/ASR healthy. Task-owned simulator/MCP stopped
after fresh standing/safe-idle/empty-work proof. No physical microphone, audible
speaker, robot, supervised-voice, target-closure or release claim. Earlier delivered
snapshots below are historical laptop evidence, not the current RTX5090 result.

## Historical delivered scope

Current focus: Goal-driven single-authority architecture and current-revision evidence closure.

Continue **#24/#32**, communication ownership and evidence closure. The owner's
18-iteration optimization batch is **complete**, with two additional mechanical fixes
and no promoted semantic prompt candidate. The canonical local gate passes. Native
live-text/simulator qualification still fails; supervised voice and default target
evidence closure remain open. A subsequent all-case diagnostic attempted **75/75**
and scored **1/75 (1.33%)**: 74 failures include 52 cases blocked by model-service
unavailability after a native compiler crash on case 23. Attempt coverage is 100%;
complete semantic and dependent-turn coverage is not established.
No architecture expansion, phrase routing, downstream semantic repair or source-span
widening. Physical WorkDAG nodes remain sequential; compatible independent Activities
may overlap under existing contracts. SC remains the sole wording owner.

Branch `main`; HEAD/fetched origin before development:
`542aefd08d4ca017e5ae11815dbf39ee8e2bae36` (0 ahead/behind). This owner-requested
delivery includes the repairs, frozen replay migrations, full-case diagnostic runner
and this handoff. Resume from the latest `main` commit containing this checkpoint
and Handoff; this base is the pre-delivery revision, not the new commit ID. Fetch
and compare upstream before development. No remote Issue was created. This is
development delivery, not semantic or release approval.

## Implemented repairs and actual workflows

| Boundary | Reproduced failure → repair | Claim limit |
| --- | --- | --- |
| Required Plan → SC context (prior batch) | Pending same-turn speech lets Goal/Work owners advance; stale planning tasks were combined with a fresh ledger. Refresh existing continuity after the wait, before assembling ledger/expression context. | Three failing-before transitions; preserves Plan/meaning/history. Native branch and broader SC state truth remain unqualified. |
| Trusted re-entry → Activation (prior batch) | Eight-row truncation loses valid 9/16-Goal scope, source refs and lifecycle tails. Preserve canonical 16 Goals/32 refs and all rows, enforce exact selection scope; retain existing disclosure-safe social context. | Oversized scope/budget fails before inference. Native high-cardinality qualification remains open. |
| Admitted source → UMI prompt (iteration 9) | A 5,000-character serializer silently truncates authoritative token rows, including recipient/negation tail, while schema permits all refs. Project the complete table through existing required JSON; existing transport preflight rejects oversize. | Four bilingual primary/deep regressions fail before/pass after; does not repair short-turn milk semantics. |
| UMI schema → Host (iteration 10) | Native t14..t13 output passes independent endpoint enums but fails Host. Reuse existing Fast ordered-span grammar in shared source owner for UMI and Fast. | Excludes only already-invalid backward spans; never selects or widens source meaning. Native grammar proof and focused tests pass. |
| Failed case → next independent simulator case | Owner-requested `--keep-going` attempts all selected cases/stages under unchanged per-case preflight and execution guards; retains every failure, full-set score and blocked dependent turns. | Diagnostic collection only, simulator-only; default fail-fast and failing exit/qualification remain. |
| Current request → frozen replay | Prior UMI system-paragraph migration plus current ordered-span schema migration updates exact request artifacts/references. | 6,000 expanded packets preserve responses, faults, inputs and oracles; no native reasoning claim. |

No new maintained document, runtime setting, semantic stage or architectural term.
API reference reflects the projection and decoder contracts. Prior README/component/
security ownership corrections and independent-SC assertion fixes remain preserved.
Detailed actual module I/O and correlations are in the two private reports named in Handoff.

## Verification actually observed

- Final canonical `./scripts/run_tests.sh`: **145 benchmark tests; 3,795 main tests,
  1,092 subtests; 20 legacy Agent tests passed**. Repository policy, test ownership,
  pinned Ruff/mypy, configuration and documentation checks pass. Two FastAPI warnings.
- Complete immutable offline replay: **6,000/6,000 expected verdicts**, source unchanged,
  zero native calls (1,400 passes; 1,800 expected lifecycle states; 2,500 expected
  rejections; 300 expected nonexecuting rejections). Level A: **45/45**, 15 classes.
- Token projection: **45 tests/28 subtests**; source schema: **192/118**; replay focused:
  **104**. Installed XGrammar rejects reversed and accepts ordered endpoints.
- Eighteen iterations: 16 isolated native transaction candidates and two retained code
  fixes. UMI's best diagnostic screens preserve 7/9 meanings but fail quotation/current
  question contrasts. Fast improvements regress other effects/timing/acquisition.
  No candidate qualifies for promotion; no change to fixed Qwen3.5-4B model/profile.
- Three full-directory live invocations select all 75 cases. Baseline stops at case 4
  (**0/4, 71 unrun**); after each retained fix, stops at case 3 (**0/3, 72 unrun**).
  Each has one identity and one debug bundle; all attempted cases safely idle.
- Latest SIDs: compound `5e9ad597`, simultaneous `286d246d`, milk `e6a7dc3d`.
  Eleven native calls retained. Compound chooses sidestep for turn; simultaneous
  gaze/blink has completed sequential intervals; milk fails provenance before dispatch.
- Full-case diagnostic: **75 attempted, 1 pass, 74 failures; 1.33%**. Case 5
  `walk_then_turn_right` passes. Cases 1–22 expose semantic/contract and three oracle
  defects; case 23 crashes XGrammar; 24–75 fail service availability. Failed dependent
  turns remain unrun. Exactly one bundle follows the aggregate. Six new harness
  regressions fail before/pass after; focused suite **80 passed**.
- Agent package equals host. Final simulator is standing/safe-idle/no active work and
  task-owned simulator/MCP were stopped. Agent/LLM/TTS remain healthy; ASR off.
  No physical microphone/speaker/robot or release evidence.

Four axes: **projection/decoder implementation repaired; canonical automatic verification
passed; native target failing/incomplete; deployment development only**.

## Remaining first wrong boundaries and ordered work

1. UMI preserves neither complete reference frames/qualifiers nor complete source scope
   reliably. Latest milk changes approximate robot-relative location to exact user-relative
   location and narrows source to t3..t11; walking+singing can collapse to speech-only.
   GA carries accepted meaning forward. Repair primary meaning conservation, never
   compensate through Planner/Host span widening or a second semantic reviewer.
2. Fast receives correct turn/concurrency meaning and supported providers but chooses
   sidestep or serializes concurrent effects with complete coverage. Correct-meaning
   acquisition controls invent travel, decoration or duplicate delivery. Host catches
   provenance/resources but cannot reconstruct lost WHAT/HOW semantics.
3. Confirmed earliest boundaries do not establish a model-only root cause. Retained
   18-iteration contrasts show prompt/schema serialization interactions; best focused
   improvements regress the full diagnostic cohort. Do not rerun rejected candidates
   as newly qualified fixes. Iteration 15 emitted lookup requests; private Work-only
   DTO diagnostics are not production lookup rejections, continuation remains unproven.
4. Independent Goal-bound SC reactivation, broader SC state truth/pending communication,
   native high-cardinality Activation, deeper/re-entry variants and target/voice closure
   remain open. Full-case attempts after the crash do not establish the semantics
   of the 52 unavailable-service cases.

The completed 18-iteration batch remains historical. The owner subsequently authorized
**up to six new repair loops**, then requested immediate commit/push for relocation.
**Zero new repair loops completed**; diagnosis of loop 1 is retained, no compiler or
prompt candidate promoted. Resume these bounded loops, beginning with:

1. **Provider crash:** case 23 `contextless_turn_it_up` (SID `c16f6814`) reaches
   Fast's valid 143,403-byte wire schema. XGrammar 0.2.1 crashes in native lookahead
   compilation with the actual Qwen vocabulary, before model output. Both one/eight
   compiler threads reproduce; byte-only vocabulary passes. This is not a model
   reasoning failure or OOM. Automatic service restart invalidates stable-service proof.
2. A normalized-grammar roundtrip fixes that request but crashes another retained
   request: rejected and reverted. XGrammar 0.2.2/0.2.3/0.2.4 still crash; 0.2.6/0.2.7
   compile the original crash request. **Do not deploy yet:** SGLang 0.5.19 pins 0.2.1;
   0.2.6 also rejects 24 GA schemas containing empty enums. Private diagnostic conversion
   of those impossible enums to false schemas compiles all 120 retained wire requests,
   but is not a production patch or equivalence/behavior qualification. Preserve exact
   meaning and Host validation; qualify compatibility before any upgrade.
3. **Oracle default omission:** cases 15, 18 and 20 fail before dispatch because
   `validate_contract` reads absent `count` as unknown despite a retained matching
   Capability version declaring optional `count=2`. Reuse the exact request/ID/version
   default-realization rule already in `outcome_observations`; test missing/mismatched
   contracts, required properties and explicit overrides. The RTX5090 continuation
   above implements this fix and records the focused and full native rerun results.
4. For each accepted minimal fix, prove focused regression then rerun all75 on one
   unchanged deployed revision, with `--keep-going`, one final bundle and every case
   reviewed. Do not count unavailable services or blocked dependent turns as semantic
   passes. Keep the fixed Qwen model. Physical evidence remains supervised.
