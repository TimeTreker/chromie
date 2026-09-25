# Chromie Development Checkpoint

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
