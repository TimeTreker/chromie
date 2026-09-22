# Chromie Current Status

## Full-case diagnostic and delivery pause — 2026-09-23

The owner-requested simulator diagnostic now uses `--keep-going`: it attempts every
independent case and stage under unchanged preflight/dispatch guards, retaining all
failures and the full-set score. Default fail-fast qualification is unchanged;
physical mode is rejected with this option. Six new regressions pass; focused suite
**80 passed**. Latest canonical gate: **145 benchmark; 3,795 main/1,092 subtests;
20 legacy tests passed**, including policy, ownership, static, configuration and docs.

**75/75 cases attempted; 1 passed, 74 failed; score 1.33%, attempt coverage 100%.**
The one passing case is `walk_then_turn_right`. Case 23 caused XGrammar 0.2.1 to
segfault in native grammar compilation before model output; cases 24–75 failed
service availability. Those 52 cases do not establish semantic ability. Blocked
dependent turns also remain incomplete. The aggregate fails qualification and
returns failure; exactly one debug bundle follows it. Automatic LLM restart means
this is not stable-service qualification. All retained simulator final probes are
safe-idle; no physical microphone/speaker/robot claim.

The native crash reproduces with the exact schema/Qwen vocabulary at one and eight
compiler threads, without OOM. A grammar-roundtrip candidate regresses another
request and is reverted. New compiler diagnostics remain private and undeployed;
SGLang dependency compatibility and empty-enum schemas require further work. Three
cases also reveal a pre-dispatch oracle bug: omitted optional defaults are not read
from their exact retained Capability contracts. No repair to either owner is promoted.

The owner authorized up to **six new repair loops**, then requested immediate delivery
for relocation. **Zero loops completed**; retain the diagnosis and resume instructions
in Checkpoint/Handoff. Four axes: **earlier projection/decoder and diagnostic runner
implemented; canonical automatic verification passed; native target failing/incomplete;
development delivery only**. Evidence: `.chromie/acceptance/all75-20260923/`.

## Historical bounded 18-iteration optimization — 2026-09-23

The owner's 18-iteration batch is complete: **two additional mechanical production
fixes retained; no semantic prompt candidate promoted**. Long UMI source-token tables
are now projected in full, with existing preflight budget rejection before HTTP;
the previous 5,000-character serializer silently lost material tails. UMI and Fast
now share the existing ordered-source-span grammar, preventing backward endpoints
already forbidden by Host. Neither change selects meaning or widens model spans.
Four bilingual primary/deep omissions and fifteen reversed endpoint pairs failed
before repair. Focused verification: **45 tests/28 subtests** for projection,
**192/118** for schema; installed XGrammar rejects reversed and accepts ordered spans.

Final canonical gate: **145 benchmark tests; 3,789 main tests/1,092 subtests;
20 legacy Agent tests passed**, including policy, test ownership, pinned static,
configuration and documentation checks. Two FastAPI warnings remain. All **6,000**
strict replay cases match expected verdicts with unchanged source/zero native calls;
all **45 Level A** cases across 15 classes pass. Replay migration changes only the
UMI source schema in five seeds, 23 shared artifacts and 6,000 request references;
source inputs, responses, faults and oracles are unchanged.

Sixteen isolated native candidate experiments accompany the two retained fix iterations;
these are not eighteen complete live auditions. Best UMI screens preserve 7/9 meanings
but fail quotation/current-question contrasts. Fast timing/effect improvements regress
acquisition or other contrast cases; final candidates invent extra or duplicate Work.
Iteration 15 emits catalog requests, whose continuation was not run in the private
primary-only screen; its Work DTO diagnostics are not production lookup rejections.
Fixed SGLang/Qwen3.5-4B model/profile remains unchanged. No second semantic critic,
phrase routing, new setting, architecture layer or maintained document was added.

Three full-directory live-text/MuJoCo invocations select all75: baseline **0/4**, then
**0/3** after each fix, hard-stopped with **71/72/72 unrun**. One runtime identity and
one debug bundle per invocation; all attempted cases safely idle. Latest compound
`5e9ad597` selects sidestep for turn; simultaneous `286d246d` executes sequentially;
milk `e6a7dc3d` changes approximate robot-relative meaning and narrows provenance,
then Fast adds unsupported Work and Host correctly rejects `act_1.speed` before dispatch.
Earlier walking+singing also loses its body result domain in UMI. Earliest wrong
boundaries are proven; a unique model-only root cause is not established.

Four axes: **projection/decoder implementation repaired; canonical automatic verification
passed; native target failing/incomplete; deployment development only**. Agent package
matches host. Task-owned simulator/MCP stopped after final standing/safe-idle proof;
Agent/LLM/TTS remain healthy. No physical microphone/speaker/robot, supervised voice,
default target closure or release claim. These changes are included in the later owner-requested delivery. Historical evidence:
`.chromie/acceptance/iterate18-20260922/REPORT.md`; Checkpoint/Handoff own resume details.

## Historical full audit repair and live baseline — 2026-09-22

The owner resumed full local and live-scenario testing after the repository audit.
On clean `542aefd08d4ca017e5ae11815dbf39ee8e2bae36`, the 75-case discovered
live-text/simulator cohort stopped after three failures: Fast selected sidestep for
turning, serialized simultaneous gaze/blink, and rejected milk delivery because UMI
excluded the recipient from its source span. UMI also changed robot-relative,
approximate distance to exact user-relative distance. All three final provider probes
reported safe idle; the other 72 cases remain unrun. This is an incomplete cohort,
not a whole-library ability score. The earlier launch without a complete runtime
identity was interrupted and is excluded from qualification.

The required Plan-to-SC path now refreshes owned Goal/task/history context after
waiting for previous same-turn speech, before reading the InteractionLedger. This
repairs the same stale-input mechanism already repaired in optional state SC; it
preserves the exact Plan, accepted meaning and causal history. Three required-path
transition regressions failed before the change and pass afterward. SC/Situation
tests: **192 passed**; truthful-speech Level A: **6/6**. These checks establish input
freshness at this boundary, not native semantic correctness or physical delivery.

Four axes: **input implementation repaired; canonical automatic verification passed;
full live target failing/incomplete; development only**. Private evidence is retained under
`.chromie/acceptance/full-repair-20260922/`; no physical microphone/speaker/robot or
release claim. Historical deferred-scope statements below describe earlier work.

Activation now preserves the existing re-entry capacity of 16 Goals/32 source refs,
retains every projected lifecycle row and the caller's disclosure-safe social context,
and rejects oversized scope before any model call. The selection validator also enforces
the exact source scope already required by the decoder. Thirteen regressions reproduced
the old omissions; **53 activation/Situation tests pass** after repair, including
transport-budget rejection without generation. Relevant Level A classes pass **8 distinct
cases** (four continuity and six truthful-speech memberships overlap). No new semantic
decision, prompt, model, setting or lifecycle was introduced. Whole-runtime native
qualification remains blocked by the earlier UMI/Planner failures.

The canonical local gate now passes: **145 benchmark tests; 3,786 main tests and
1,039 subtests; 20 legacy Agent tests**, with repository policy, test ownership,
pinned static analysis and documentation checks. Complete frozen offline replay is
**6,000/6,000 expected verdicts**, unchanged source throughout and zero native calls:
1,400 passes, 1,800 expected lifecycle states, 2,500 expected rejections and 300 expected
nonexecuting rejections. General Ability Level A passes **45/45** distinct cases across
15 classes. Replay drift was repaired by migrating only the current UMI GA-scope
system paragraph in two shared request artifacts and their references; scenario inputs,
reference outputs, faults, oracles and strict matching remain unchanged. Two stale test
expectations now respect independent silent SC and avoid an incidental wording assertion.

All three source-bound directory-discovered live iterations (baseline, required-SC,
activation) attempted the full 75-case library and stopped at the same hard failure:
**0/3 passed, 72 unrun**, all attempted cases safely idle. The last Agent source matches
the host; no production change follows that live iteration. Native high-cardinality
activation and required-SC branch qualification remain unproven. Latest correlations:
compound `8b8a6aad`, simultaneous `c79faec9`, milk `6bd3abbe`. Wrong native meaning,
effect selection and temporal coverage remain open; prior rejected wording/order
candidates were not promoted. This does not establish a model-only root cause.
The simulator/MCP started for this task were stopped after a final safe-idle probe;
Agent/LLM/TTS remain healthy. Current work is uncommitted. No release, supervised voice
or default target-evidence closure is claimed. Checkpoint/Handoff own the next steps.

## Historical continuation: temporal acceptance evidence — 2026-09-22

Based on `4a1606fd0fc546601b38e664a5428c6a79ad489b`, the acceptance oracle now checks
actual completed Runtime interval overlap for simultaneous gaze/blink. Previously,
`collect_observations` discarded receipt timestamps, and the scenario checked only
both effects/counts; sequential execution therefore mechanically passed. Correlated
request/Capability/version intervals now reach the oracle; missing, malformed, failed,
reversed, timezone-ambiguous or same-request records cannot prove overlap. This is a
necessary execution-lifetime check, not physical-onset proof or complete semantic review.

Current focused tests: **90 passed /20 subtests**, scenario library 75 live/45 Level A
cases validates, composable Level A **5/5**. Regrading the unchanged retained four-case
live evidence changes only simultaneous from pass to fail: **mechanical 1/4**, matching
its previous manual requested-Work verdict. No new live run or product behavior repair
is claimed. Full suite/replay/live cohort and latency remain deferred.

The nine-case UMI field-order experiment improves some quoted referents but still loses
qualifiers, source coverage or source language. The four-case Fast temporal-wording
experiment still emits one sequential and one parallel member; existing Host validation
correctly rejects that singleton group. Neither candidate is promoted. A further UMI
source-order diagnostic was interrupted by the owner's explicit service restart;
SIGTERM/Docker stop evidence is retained, with no OOM attribution. After authorized
service recovery, complete nine-case UMI example and four-case Fast timing-first screens
also fail semantic contrasts; neither changes production. The former still switches the
addressee frame; the latter retains serialized simultaneity and invents invalid walking.

Existing Charter authority permits independent Activities to overlap under declared
provider/resource/dependency contracts; physical WorkDAG nodes remain sequential.
Current production failures remain: turn selected as sidestep, simultaneous effects
serialized, and acquisition meaning losing reference frame/qualifier/source coverage.
Four axes: **acceptance implementation repaired; focused automated verification passed;
production semantic target still failing; development only**. Exact evidence, service
state and strengthened bounded resume scenarios are in HANDOFF.md. The previous delivery
and historical observations below retain their original oracle/revision limits.

## Planner contracts and inference retention — 2026-09-22 (previous delivery)

This owner-authorized development delivery, based on
`0129915dbd57913be15661f9b7f38aff81b48c68`, retains
Host SC continuity and clarification/lookup-decoder repairs, and fixes three additional
reproduced boundaries. The Fast prompt's terminal-effect definition contradicted the
Host's provider-owned acquisition purpose; prompt and per-Capability Schema now use that
existing contract. Ordered source-span branches exclude reversed endpoints before Host
admission. Native `$defs` share identical span grammars, reducing ~2.5 MB unshared
candidate packets to ~148–151 KB. No semantic authority or physical scheduling changed.

Pinned SGLang retained dynamic grammars in two unlimited caches. The maintained image
now gives the compiler a 512 MiB retained-cache budget and removes the second backend
cache owner. Its build exercises 64 distinct schemas against the actual patched backend.
This is a retained-grammar limit, not an active/peak/process-memory bound. The preceding
purpose-only live iteration reached 23.44 GiB and timed out; the final rebuilt-service
four-case run had no timeout/disconnect and memory 12.31 →12.05 GiB. Long-run stability
remains unqualified. Configuration ownership is documented in `docs/CONFIGURATION.md`.

Automatic verification: **376 focused tests /143 subtests**, composable planning
Level A **5/5**, repository policy, test ownership, pinned Ruff/mypy pass. Actual installed
XGrammar rejects the original reversed-source output and accepts a structurally corrected
probe. Frozen final native replay: 4/4 normal stop and Schema/DTO/purpose checks; full
Host 3/4, milk correctly rejected on its UMI-owned source boundary. Previous replay's
missing target-context reconstruction is fixed in the private adjudicator.

Final live cohort: **4/4 attempted, mechanical 2/4, requested Work semantic 1/4**:

| Case / correlation | Actual boundary and result |
| --- | --- |
| Compound `8cec7b59` | UMI preserves walk/nod/turn; Fast picks sidestep for turn. Host structural admission and simulator faithfully execute the wrong selected effect. SC silent; required-speech oracle also fails. |
| Sequential `28429ba9` | Requested gaze 3 s then blink twice executes correctly. No purpose/source-order rejection. |
| Simultaneous `708b6dc7` | UMI preserves “while”; Fast emits sequential gaze/blink and complete coverage. Mechanical pass is manually rejected as temporal semantic failure. SC emits no speech; internal execution-state rationale remains unqualified. |
| Milk `f19f15c7` | UMI changes approximate robot-relative location to exact user-relative location and narrows source to t3..t15. Fast cites recipient t16..t17; Host rejects before Work. SC not invoked. |

All cases returned safe idle. Final runtime identity, raw transactions, exact I/O audit,
rejected candidates and one bundle per aggregate are in
`.chromie/acceptance/planner-purpose-root-cause-20260922/REVIEW.md` and HANDOFF.md.
A new six-case source-wording UMI experiment improves the original robot-relative case
but fails four contrasts; rejected with no production UMI edit. Activity-ID and catalog
ordering experiments also remain rejected. Do not weaken source containment or serialize
concurrency silently to manufacture a pass.

No new maintained document, environment variable, runtime mode or architecture term.
Four axes: **implementation source repaired; automatic verification partial; target
validation failing; deployment development only**. #24/#32, deferred full suite/replay/
cohort, memory soak, supervised voice and default target-evidence closure remain open.
Owned simulator stopped after safe idle; core services remain healthy. No physical audio,
robot acquisition or release claim. Earlier pre-delivery “uncommitted/no push” entries
below describe their historical evidence snapshots; this owner-authorized delivery and
current results above take precedence.

## SC continuity refresh — 2026-09-22

Current uncommitted continuation on `0129915dbd57913be15661f9b7f38aff81b48c68` repairs
the Host input boundary for optional state-triggered Social Cognition. After awaiting
prior same-turn speech, it refreshes existing owned continuity, preserves admitted
meaning/Plan, removes the fixed pending-admission assertion, and uses the same current
context for expression. Scoped execution freshness remains. No model, prompt, Schema,
semantic authority, Work lifecycle, setting or new current document changed.

Native baseline packets combined old planning/evaluating Task/Goal state with fresh
committed ledger events. Candidate packets now show scheduled/accepted state and
current execution bindings. Three delayed-speech regressions fail on original source
and pass after repair. **158 SC tests pass**; broader focused checks **248 pass,
1 pre-existing failure, 17 subtests pass** (same failure proven on baseline).
Truthful embodied speech Level A **6/6**, policy/ownership/Ruff/mypy pass.

The unchanged four-case bounded live aggregate remains mechanical **2/4**, requested
Work semantic **1/4**; hard model-contract stop on the last case. Fast still serializes
“while” and substitutes sidestepping for turning. Milk UMI still shifts reference frame
and omits relevant source coverage; Planner clarification fails closed. One SC raw
silence rationale still mistakes committed Work for completion even with corrected
input; existing freshness suppresses it. All four provider snapshots show safe idle.

Evidence and exact module workflow: `.chromie/acceptance/sc-context-refresh-20260922/REVIEW.md`.
One bundle: `/home/chromie/Downloads/chromie_debug_bundle_20260922_205334.tar.gz`.
Three-packet private native Schema-order experiment also failed and was rejected.
Four axes: **source locally implemented**, **local validation partial**, **target
validation failing for original behaviors**, **development support only**. Full
tests/replay/cohort and latency remain owner-deferred; physical voice/robot unproved.
Current checkpoint/handoff supersede the preceding audit's unchanged-source status.

## Laptop bounded continuation — 2026-09-22

Resumed clean `0129915dbd57913be15661f9b7f38aff81b48c68` after fetching upstream.
The current machine is RTX 4090 Laptop / SGLang `chromie-qwen35-4b`, not the preceding
Gemma deployment. Its stale Agent was rebuilt to current source and verified before
and after live checks. No production prompt, model, Schema or code repair was retained.
Previous September 22 private repair roots are absent from this checkout; their evidence
has not been recovered or rerun. See the current checkpoint/handoff for identities.

| Actual episode / earliest boundary | Observed result and claim |
| --- | --- |
| Sequential gaze/blink contrast, `d6ceefdc` | UMI preserves order; Fast selects gaze 3 s then blink twice; Runtime completes both in order. Requested Work passes this bounded semantic review. |
| Simultaneous gaze/blink original, `5b3acc0a` | UMI preserves “while,” but Fast authors sequential actions and complete coverage. Runtime executes that incorrect Plan; Goal satisfaction inherits the bad coverage claim. Mechanical action/argument checks pass, but temporal semantics fail. |
| Compound walk/nod/turn original, `ad2b903f` | UMI preserves the request; Fast selects sidestep for turning left despite distinct supplied turn/sidestep contracts. Walking/nodding/sidestepping complete; the requested turn is missing. Required speech also absent. Case fails. |
| Milk acquisition original, `79b49022` | UMI changes “ahead of you about 50 meters” to “50 meters ahead of the user” and incompletely cites the source. Fast then asks for exact distance with an invalid context-consideration record. Host rejects before execution. UMI semantic failure is earlier than the contained DTO failure. |

All four provider post-case snapshots report safe idle, with no active task/lanes,
fall or emergency stop. Exact raw prompts/replies and workflow I/O are retained in
`.chromie/acceptance/resume-bounded-20260922/REVIEW.md` and its evidence root. The native
catalog advertises a scripted/mock acquisition provider; this run does not establish
unavailability or real object acquisition. No microphone, audible speaker or robot proof.

One private two-packet timing-prompt candidate was rejected: sequential contrast remains
correct, while the simultaneous result labels only the blink parallel. Native Schema/DTO
accept both packets, but the production Host scheduling invariant rejects the singleton
parallel group. This is not a retained fix or authority amendment. Raw semantic inference
failures are established; broader prompt/projection contributions remain unqualified.

Focused timing/schema tests pass **13**; composable-action Level A passes **5/5**.
Two live invocations retain mechanical **2/2** (temporal pair, only one semantic Work
pass) and **0/2** (original compound/acquisition pair; integrity stop on final case).
One debug bundle per invocation: `chromie_debug_bundle_20260922_200558.tar.gz` and
`chromie_debug_bundle_20260922_200757.tar.gz`, under `/home/chromie/Downloads/`.
Full tests/replay/cohort, latency and physical voice remain owner-deferred. Simulator
stopped; current-source Agent retained. No commit/push. No new current document,
configuration, architecture term or behavior fixture was added.

Four axes: **source unchanged** from prior repair delivery; **local validation partial**;
**target validation failing for the original cases on this laptop**; **support development
only**. #24/#32 remain open, as do SC mixed-time context and retired Planner speech fields.

## Pending SC Work-state freshness repair — 2026-09-22

The owner deferred failure-cause wording where it does not affect main Work. It remains
unqualified; execution failures and their evidence are still handled normally. This repair
addresses the independent Host defect that admitted obsolete optional Plan-state SC results.

`start_state_interaction` previously checked only the active SC request ID, so Work could
finish while the same request remained current. It now captures the existing Goal/turn-scoped
Runtime snapshot and checks its execution facts after inference and expression preparation.
Provider start, termination and relevant Goal/Work changes expire that pending result.
Independent interpretation-time acknowledgement and already submitted delivery retain their
existing ownership. No semantic phrase filter, rewording, retry, new model call or state store.

| Actual boundary | Input → output / judgment |
| --- | --- |
| UMI → parallel SC1 / Planner | Live SID `ce58f1d8`: greeting r1 → `你好！`; r2 → one left turn. Correct independent ownership. |
| Runtime → pending SC2 | SC2 starts at 17:47:25.339 from a planned-state snapshot; turn completes at 17:47:27.433. The old request identity alone would remain valid. |
| SC2 → Host | At 17:47:31.267 the changed execution snapshot yields `stale`, no response dispatch. Raw rationale still blends “planning/execution”; it is retained but not counted as semantic qualification. |
| Session / delivery | TTS 1/1 discarded segment, zero failed/skipped delivery, safe idle; session completes after SC settles. No added model invocation. |

Regression: before repair, held SC still submitted speech after its Work completed; after
repair, 22 focused social tests and 3 Runtime tests / 4 subtests pass, including actual start,
completion/cancellation, unrelated Work, independent greeting and social-delivery exclusions.
Truthful embodied speech Level A 6/6 and selected live simulator case 1/1 pass. Repository
policy, test ownership, pinned Ruff/mypy and docs pass. No full suite/cohort, physical audio,
hardware or latency qualification. Evidence: `.chromie/acceptance/sc-stale-work-20260922/`
(`review.json`, raw calls, workflow and source identity). One run bundle:
`/home/chromie/Downloads/chromie_debug_bundle_20260922_174753.tar.gz`. The combined log split
SC2's record; its complete raw JSON was recovered from separately retained Docker stderr.

Four axes: **source implemented** for pending Plan-state result suppression; **local validation
partial**; **target validation partial**; **support development only**. Mixed-time input views
and overall SC semantic reliability remain open; failure wording is deferred, not passed.
No new fixtures/configuration/current documents; simulator stopped; no commit/push.

## Bounded SC committed-state prompt repair — 2026-09-22

The owner requested a simple prompt repair with the current model and small common-case
checks. The unchanged original packet again called committed/scheduled Work “in progress.”
The retained prompt now explicitly distinguishes `activity_committed`/`scheduled` from an
observed start, allows prospective plan/intention wording, and separates the Work fact from
the social reason for speaking or silence. This replaces the old state paragraph and follows
the input/output-contract prose. A first placement near the authority instructions failed
and was rejected. No model, Schema, context, semantic filter or extra model call changed.

Three independent retained committed snapshots plus running/completed contrasts pass this
state check (5/5). All six packets pass mechanical validation; **the six-case semantic cohort
does not pass**: the controlled failed-result case still invents a cause and misuses speech
repair. Earlier context inconsistency and asynchronous snapshot freshness also remain open.

Fresh live SID `f37ee74a` passes the selected greeting/left-turn check: SC greets and adds an
independently intended wave; Planner/Runtime complete one left turn; SC2 describes a resolved
plan preparing for action without claiming execution. Its snapshot precedes the left-turn
commit, so fresh live evidence covers planned-versus-running; direct committed-state proof
comes from the three retained native inputs. TTS 2/2 discarded segments, no failed delivery,
and safe idle. Both raw SC calls match the new prompt; packaged Agent source matches before
and after (`4012bd77d185af8dbb83a754981fad944edbc6bd55c6cb355d442c6a72439991`).

Validation: 17 focused tests; truthful embodied speech Level A 6/6; pinned Ruff/mypy,
repository policy, test ownership and docs pass. No full suite/live cohort, physical audio,
hardware or latency qualification. Evidence and per-boundary review:
`.chromie/acceptance/sc-committed-prompt-20260922/review.json`; one completed-run bundle:
`/home/chromie/Downloads/chromie_debug_bundle_20260922_172813.tar.gz`. No tracked fixtures or
new configuration; simulator stopped; no commit/push. Four axes: **source implemented** for
this bounded prompt repair; **local validation partial**; **target validation partial**;
**support development only**. Next address failure reporting and snapshot freshness separately.

## Continued SC state diagnosis — 2026-09-22 (no production change)

The owner requested continuation of the committed-versus-running defect. It remains
open. Six frozen inputs cover three actual committed-state snapshots and controlled
running/completed/failed contrasts. Consistent Task/Goal projections, reduced duplicate
context, fact/output ordering, a consolidated authority prompt, and explicit Runtime-shaped
Work/start fields did not produce a reliable repair. All trials remain private diagnostic
artifacts; production prompts, context, Schema and code are unchanged from the preceding
identity repair. No new tracked fixtures or benchmark expansion.

The actual handoff contains old planning snapshots alongside newer scheduled Task records;
SC also receives the planning-time empty `existing_work_activities`, rather than a fresh
Runtime Work view. These are context-quality gaps, but correcting them in controlled
inputs did not eliminate the bad raw SC result. Even a controlled `started=false` Work
view was followed by an execution claim. That field was reconstructed for the contrast,
not recovered as historical provider-start evidence. Do not claim a missing-field-only
root cause or a proven model-wide inability from these experiments.

A same-model thinking-mode diagnostic also failed: the existing 1,024-token bound
truncated outputs; with a 4,096-token diagnostic bound, the original case still claimed
execution and the failed-state case timed out. Thinking output also violates the current
production transport contract. No parser, reasoning profile or service configuration was
changed, and the interrupted diagnostic batch is incomplete.

Evidence: `.chromie/acceptance/social-state-grounding-20260922b/review.json` retains
the episode workflow, per-case verdicts, rejected hypotheses, exact packets/replies,
source identity and limits. The initial order experiment had a harness-order defect and
is explicitly unqualified. No live execution, full suite, physical audio or latency
qualification ran. A six-input offline comparison with the already-cached Qwen3.5-9B
was proposed to the owner; no model switch or comparison has been performed.
Four axes remain **source implemented** only for earlier accepted repairs;
**local validation partial**; **target validation partial, SC state/reporting open**;
**support development only**. No commit/push.

## SC state investigation and native identity repair — 2026-09-22 (current worktree)

The owner resumed audit repairs with small common-case checks, no behavioral rules
and no latency work. **The committed-versus-running SC defect is still open.**
Prompt changes, foregrounded task state, planned-satisfaction labels, output ordering
and removal of duplicate Schema prose were tested and rejected. Two candidates that
improved retained inputs still failed a fresh live snapshot. All these production
changes were reverted; the earlier accepted repairs remain intact. No missing state
fact or context-only root cause was established. The earliest observed semantic
divergence remains SC's primary result over committed/scheduled Work.

One separate, reproduced **native identity-contract defect is repaired**. With a
retained speech identity, the fresh-ID regex admitted empty strings and unlimited
length, while sibling Schema keywords required 1–24 characters. The native decoder
could ignore those sibling bounds when applying the pattern. A retained native call
generated the 27-character `failure_acknowledgement_001`; strict validation rejected
the entire result. The regex now directly enforces the existing length bound and
excludes reserved identities. Longer historical identities retain their exact-wording
reuse alternatives. No expression quota, semantic rule, output truncation, extra model
call, relaxed validator or new setting was added. The SC authority prompt, full state
projection and output-Schema prose are restored to their turn-start versions.

| Actual episode / owner | Authoritative input → actual output | Verdict / retained change |
| --- | --- | --- |
| UMI → parallel SC / GA / Planner | Greeting r1 and left-turn r2 retain separate owners. SC delivers the greeting; Planner/Runtime commit requested left-turn Work. | Common interaction remains functional; no ownership change in this patch. |
| Runtime/task view → SC primary | Original `bc6f276f` and new `02ec8361` / `cffc6162` snapshots contain `activity_committed`, task `scheduled`, and no start/result evidence. SC calls the action executing or mixes in-progress/committed. | Incorrect semantic state grounding. Prompt/input candidates are not qualified by isolated improvements; both live candidate runs remain semantic failures despite automated passes. |
| Native SC decoder → strict Schema / Host | Controlled failed-result contrast generates a 27-character fresh ID under a regex that permits it; declared maximum is 24. | Earliest mechanical gap is decoder realization of the existing Schema bound (`contract_or_schema`). Host rejection is correct; no effect was dispatched by this isolated probe. |
| Revised regex → exact failed native transaction | Identical retained experimental prompt/context/model; only native response Schema changes. Model generates a 24-character ID and the wire Schema passes. | Decoder now contains the malformed-ID trigger before Host admission, without rewriting model output. This does not qualify the experimental prompt or its failure-report semantics. |
| Retained revision → Runtime / TTS / session | SID `15ec0b11`: `你好呀！`, one completed left turn, 1/1 discarded TTS segment, zero failed TTS/pending SC and safe idle. | Selected automated live check 1/1 passes; session joins delivery and Work. Later SC rationale still claims execution from committed/scheduled state, so the semantic audit remains open. |

Regression: four boundary assertions fail before the identity change; afterward
**27 focused tests pass**, including empty/overlong IDs, reserved prefixes, the
24-character boundary, longer retained-ID reuse, native Need constraints and strict
validation. Six small native packets pass Schema/DTO/Host checks, but only **2/6**
pass the full semantic rubric: three committed snapshots still overclaim execution,
and the controlled failed-result case invents a cause and misuses speech repair.
The failed-result input is a controlled role contrast, not a live failed-provider
qualification. The exact malformed-ID replay is separate mechanical evidence.
`truthful_embodied_speech` Level A passes **6/6**. Pinned Ruff/mypy, repository policy,
test ownership and documentation checks pass. No full suite or full live cohort ran;
no microphone, audible speaker, physical robot or latency claim is made.

Evidence: `.chromie/acceptance/social-work-state-focused-20260922/` retains all
baselines, failed candidates, three live runs, raw calls, frozen contrast extensions,
the exact ID replay and `retained-repair.patch`. `repair-review.json` is the final
adjudication; earlier files naming a selected candidate are superseded. Retained Agent
source matches before/after live:
`85c93ea4b66be154b214dbe83970696b9472771edf6ffd8b66bffa5fc588764d`.
One bundle per ended live run: `/home/chromie/Downloads/chromie_debug_bundle_20260922_141411.tar.gz`,
`/home/chromie/Downloads/chromie_debug_bundle_20260922_142843.tar.gz`, and
`/home/chromie/Downloads/chromie_debug_bundle_20260922_144127.tar.gz`.
The owned simulators were stopped; the Agent runs the retained identity repair.
No new current document, environment variable or architectural term; no commit/push.

Four axes: **source implemented** for native fresh-ID bounds only; **local validation
partial**; **target validation partial, semantic state/reporting failures remain**;
**support development only**. Next investigate SC's use of authoritative execution
state and real failed-result Evidence; do not repeat rejected candidates or present
the identifier repair as closure of the originating semantic defect.

## Focused SC context and turn-observation repairs — 2026-09-22 (current worktree)

The owner requested both remaining defects be fixed without behavioral rules.
The originating episode is `86d7f313`: left-turn execution and greeting delivery
completed, but SC unnecessarily asked `你要我向左转吗？` and acceptance lost the
direction. The two earliest wrong boundaries were different:

- The observation map still retained `yaw_radps` although the current turn contract
  supplies `direction` and `turn_rate_radps`. It now preserves those semantic fields
  directly. Two current turn scenarios and the matching acceptance command use the
  requested direction rather than a fixed provider speed. Completed status remains
  required; wrong/missing direction and failed execution cannot pass. Historical
  artifacts are untouched, and no sign conversion or invented telemetry was added.
- The SC model projection unconditionally discarded `core_interpretation`. Host
  already held UMI's full accepted meaning and cognitive routing, while SC's own
  Responsibility list contained only the greeting. SC saw the full original request
  and pending planning without the sibling task's established ownership. The existing
  projection now retains current-turn UMI authority, turn ID, Responsibilities,
  uncertainties and cognitive requests as read-only context. Stale UMI and generic
  dialogue history remain excluded. SC's own fulfillment scope is unchanged.

Two prompt-only trials were unstable and were rejected without deployment. **The
final SC authority prompt is byte-for-byte unchanged**, as are its model, native
Schema, DTO, validator and invocation budget. No keyword routing, fixed response,
question filter, output rewrite or expression-count rule was added. Independent SC
questions and extra social expression remain available.

| Actual workflow / owner | Material input → output | Assessment |
| --- | --- | --- |
| UMI / Host admission | Greeting r1 → SC; body r2 → Planner; Host closes Planner's turn-wide GA dependency. | Correct accepted meaning and routing; current live raw calls retained. |
| SC context projection → primary model | Before: r1 plus original full turn, but full UMI removed. After: same source plus exact current UMI sibling meaning/routing, still only r1 in SC fulfillment scope. | Earliest missing-context boundary repaired without re-authoring meaning or widening act provenance. |
| Frozen primary SC contrasts → validation | Chinese greeting+turn, English greeting+blink, genuine missing location and genuine Runtime confirmation. | Baseline 2/4 → context-only candidate 4/4; wire/full Schema, DTO, Agent and reconstructed Host projection pass. Genuine questions remain; optional expression count is unrestricted. |
| Deployed SC → TTS | SID `bc6f276f`, SC call `llmcall_agent_1eef986876dc465b`: `你好呀！很高兴见到你。` | No redundant task question or claimed execution; 2/2 segments delivered to discard sink. |
| Planner → Runtime → observation | Exactly one left turn, owned direction span t8; provider completed; observation retains `direction=left`, `turn_rate_radps=0.01`, matching optional defaults and completed status. | Both requested repairs observed; automated selected live case **1/1 passes**, safe idle true. |
| Session lifecycle / later SC | Pending SC = 0, failed TTS = 0; session completes after playback and motion. Later Work-state SC chooses silence. | Lifecycle remains correct. Its internal rationale calls committed Work “in progress” without a started event in that snapshot; this remains an unqualified state-distinction issue, with no additional speech or action. |

Validation: observation regression fails six subcases before repair; afterward **28
focused tests / 10 subtests** pass. Level A `composable_action_planning` **5/5** and
`speech_identity_latency` **4/4** pass without latency qualification. Pinned Ruff,
repository policy, test ownership and documentation checks pass. Scenario-library
validation is structural only; no full test suite or full live cohort was executed.
The Runtime-confirmation contrast is controlled SC input, not a claim that the actual
turn provider requires consent. Physical microphone/speaker evidence remains open.

Evidence: `.chromie/acceptance/social-confirmation-observation-focused-20260922/`.
`freeze.json`, `context-freeze.json`, `comparison.json`, `semantic-review.json` and
`review.json` preserve the unchanged baseline, rejected trials, restored Host context,
final native packets, immutable re-adjudication and selected live run. Agent source
matches before/after live: `08143de66fd08772118f1bd4ef15b6c5eb7f01ad20f10904d56f061be07abefa`.
Exactly one bundle: `/home/chromie/Downloads/chromie_debug_bundle_20260922_133807.tar.gz`.
The owned simulator was stopped. No new current document, setting or architectural
term, and no Git delivery; earlier dirty work is preserved.

Four axes: **source implemented** for these two defects; **local validation partial**;
**target validation partial, selected interaction passes**; **support development only**.
Next audit the retained Work-state rationale against committed/started/completed
evidence before extending any SC state-truth claim. Full target qualification remains
open; this bounded success does not close the whole communication migration.

## Focused Fast Work-scope repair — 2026-09-22 (current worktree)

The retained `你好，Chromie！然后向左转一下。` episode (`ed4fc9a4`) gave
Fast only body Responsibility r2. Fast nevertheless added
`chromie.weather.lookup(location=current_location)` under r2 to handle the greeting,
which already belonged to independent SC. The earliest wrong boundary was Fast's
primary semantic result; the scoped DTO, complete source tokens and catalog were
available. Host correctly rejected the invented location before dispatch.

The existing Fast streaming prompt now makes the supplied Responsibility array the
complete scope of this invocation. Each Activity must realize its cited outcome or
supply a necessary prerequisite. Immutable source/history/identity ground HOW without
creating new tasks. Unique coverage refs are distinguished from multiple necessary
Activities for one outcome, and responses dependent on unavailable results are deferred.
This clarifies existing authority; it changes no model, Schema, DTO, validator, catalog,
SC expression permission or invocation count. No benchmark reference was rewritten.

| Actual workflow / owner | Input → observed output | Assessment |
| --- | --- | --- |
| UMI / admission → GA, SC and Fast | Full turn → greeting r1 to SC, body r2 to Fast, both refs to GA; GA creates only the body Goal. | Correct scope in retained live DTOs; raw UMI call was unavailable in the recovered bundle. |
| Fast native primary → Host | Unchanged frozen origin again adds weather; a requested-weather contrast also adds a premature final response. | Baseline 2/4 passes. Scope confusion is reproduced; Host grounding contains the invented argument. |
| Revised Fast primary → Host | Same four packets except operating-contract prose: greeting+turn, turn alone, requested weather+turn, and compound turn+blink. | 4/4 Schema, DTO, Host and inspected semantic passes. Genuine acquisition and multi-Activity composition remain available; casual blink count is unrestricted by the oracle. |
| Deployed Fast → Runtime | SID `86d7f313`, call `llmcall_agent_793899fde9f74bd6`: only left-turn Work, direction grounded in t8; no Deep or capability lookup. | Provider reports completed motion; realization trace contains `yaw_radps=0.01`; body Goal becomes satisfied and simulator safe idle is true. |
| Independent SC → TTS → session | `你好！我准备好啦。你要我向左转吗？` reaches the discard sink in 2/2 segments; later Work-state SC chooses silence. | Delivery complete, pending SC = 0, failed TTS = 0; session completes after speech and motion. The redundant confirmation question remains a separate semantic defect. |
| Acceptance observation projection → case verdict | Semantic `direction` / `turn_rate_radps` are omitted by the legacy turn map, which retains `yaw_radps`; the focused scenario expects positive `yaw_radps`. | **Live case remains 0/1 failed**, despite provider completion. Do not convert the retained failed verdict into a pass or claim fully natural interaction. |

Validation: **10 focused checks** and `stable_capability_grounding` Level A **7/7**
passed. Pinned Ruff, repository policy, test ownership and documentation checks passed.
Four native primary contrasts are bounded model evidence, not full-role qualification;
the weather contrast does not prove later acquisition/result delivery. Full tests and
full live cohort remain owner-deferred, as do latency and supervised physical audio.

Evidence: `.chromie/acceptance/planner-work-scope-focused-20260922/` contains frozen
inputs/hashes, unchanged baseline, candidate raw outputs, separate adjudication,
`comparison.json`, `review.json` and the one current-revision live run. Agent packaged
source matches before/after that run:
`61571b82b1687b83359fce68d79c5be8ee1140c8d024d9dbcf028c1afc2c8368`.
One bundle was collected: `/home/chromie/Downloads/chromie_debug_bundle_20260922_121346.tar.gz`.
The owned simulator was stopped. No new current document, setting or architectural
term was added; no commit/push was requested.

Four axes: **source implemented** for Fast invocation scope; **local validation
partial**; **target validation partial, complete live acceptance still failing**;
**support development only**. Next repair the stale turn-observation contract with a
focused regression, then qualify SC's redundant reconfirmation from this same episode.

## Focused Fast enum-argument provenance repair — 2026-09-22 (current worktree)

The next bounded repair addresses the missing direction source in the retained
`你好，Chromie！然后向左转一下。` episode. Fast emitted `direction=left` without
`argument_sources.direction`; the native Schema accepted that shape, while the
unchanged Host correctly rejected the translated value. Its string exception permits
literal copies, not translation: UMI's Chinese body intent and immutable source
contain no literal `left`. All required source tokens were present.

The native Schema now requires parameter-level source spans for required unbound
string enums when no offered label could be a literal copy from any compatible owning
outcome. This is a conservative necessary condition, including the existing case-only
allowance; Host still verifies the actual source and selected ownership. Typed bindings,
declared realizations, trusted targets/memory and literal strings remain supported.
The change selects no argument value and adds no translation table. **Prompts, model,
DTO and Host validation are unchanged.** No benchmark reference was rewritten.

| Actual episode boundary / owner | Material input → output | Assessment |
| --- | --- | --- |
| UMI → independent SC / Fast / GA | Replay baseline `7302b3f3`: greeting r1, Chinese left-turn r2; SC owns the greeting and Fast receives body Responsibility r2 plus immutable full-turn source. | Scope/source available; native role inputs and admitted DTO retained. |
| Native Fast Schema → primary output → Host | Baseline allows absent string provenance; Fast omits direction span and Host rejects before commit. | Decoder/Host contract gap reproduced by a failing focused regression. Native isolated baseline is 1/3 after corrected Host adjudication: both translated directions fail, literal English passes. |
| Revised native Schema → primary output | Three frozen contrasts retain identical prompt/model/options; Chinese left/right now include valid owned spans, English literal remains accepted. | 3/3 Schema, DTO/Host and semantic checks pass. Only required-field lists differ in the native packets; field order is retained. |
| Deployed Fast → canonical validation | Replay `ed4fc9a4`: actual wire Schema requires `argument_sources.direction`; Fast cites t8..t8 (`左`) for `direction=left`. It also invents `chromie.weather.lookup(location=current_location)` as a greeting response. | Direction provenance repaired. Unrequested Work remains a separate semantic failure; the full Plan is rejected on unbound weather location before action dispatch. No Deep repair call. |
| Independent SC → TTS / final session | Greeting reaches the discard sink in 2/2 segments; pending SC = 0, terminal session = `failed`, simulator safe idle = true. | Earlier SC-survival repair retained. No successful turn, physical audio or complete mixed-command pass is claimed. |

Two prompt trials were rejected for adding unrelated weather Work and fully reverted;
they were never deployed. A diagnostic adapter initially failed to rename projected
`args_schema` to the Host's `input_schema`, giving incorrect isolated Host-pass labels.
All original packets/output remain retained; `corrected-adjudication.json` supersedes
those labels. Final inference and adjudication use the corrected adapter. A preliminary
schema replay had equivalent values but different keyword order; only `schema-final/`
and `comparison-final.json` establish the final frozen native evidence.

Validation: **19 focused tests / 15 subtests passed**; `stable_capability_grounding`
Level A **7/7** passed. Pinned Ruff, repository policy, test ownership and documentation
checks passed. Full tests/cohort and latency remain owner-deferred. The production
change is confined to the existing Schema owner; no document, setting, architectural
term or model invocation was added to the product.

The unchanged live baseline and changed live replay each attempted one case and each
failed (**0/1**); they qualify only the repaired boundary, not the whole interaction.
Agent source was verified before/after; final packaged digest is
`54b65aeceb84bdc12b6d293ff7a507cf03bd5b1614a36d432c489a4f1e973fd6`.
Evidence: `.chromie/acceptance/planner-argument-source-focused-20260922/`.
One bundle per ended live run:
`/home/chromie/Downloads/chromie_debug_bundle_20260922_112808.tar.gz` and
`/home/chromie/Downloads/chromie_debug_bundle_20260922_113713.tar.gz`.
The owned simulator was stopped after collection; no commit/push was requested.

Four axes: **source implemented** for missing nonliteral enum provenance;
**local validation partial**; **target validation partial, mixed command still failing**;
**support development only**. Next diagnose why Fast adds unrequested Work for a greeting
already assigned to SC. Current cases do not qualify free-form string translation,
all enum/context combinations, Deep/re-entry, full live coverage or physical voice.

## Focused independent SC survival on Work failure — 2026-09-22 (current worktree)

This iteration fixes the Host cancellation defect retained in the mixed-turn audit
below. The originating turn was `你好，Chromie！然后向左转一下。` (`d06f3a6a`):
UMI independently requested greeting SC and turn Planner; Fast's rejected direction
argument then caused coordinator cleanup to cancel the still-generating greeting.
The rejected Plan is the trigger; cancelling independent SC is the earliest wrong
boundary for the lost greeting. The Planner semantic defect remains separate.

The coordinator now discards uncommitted Work before joining this turn's admitted
SC task. It returns the original Work failure plus the exact independently delivered
SC response; secondary SC/provider failures remain diagnostics. Host preserves that
response without replay or a generic apology, and SessionTracker records failed
completion after all same-session social tasks and speech are terminal. Explicit
interruption and the outer deadline retain cancellation authority. No semantic
prompt, Schema, validator, model invocation, benchmark reference or setting changed.

| Episode boundary / owner | Actual input → output and expected contract | Evidence / assessment |
| --- | --- | --- |
| Gateway → UMI → concurrent authorities | Current replay `9b0f29b7`: greeting r1 + left-turn r2; SC r1, Planner r2, GA r1+r2. GA commits only body Goal continuity. | Correct admission/scope, correlated by the same turn/SID; native calls retained. |
| Fast → Host validation | `soridormi.turn_in_place(direction=left)` lacks argument-source binding; Host returns `fast_stream_contract_invalid` before requested Work dispatch. | Planner output remains incorrect; fail-closed validation is correct and unchanged. Deep is not invoked. |
| Failed Work cleanup → independent SC | Previously cancelled SC and returned with zero TTS. Replay now retains SC through Runtime and playback completion, then returns the original error. | Focused before/after regression and live replay confirm this lifecycle boundary is repaired. |
| SC → Runtime/TTS → session report | SC returns a greeting plus `你要我向左转吗？` and a wave; all 3 speech segments reach the discard sink, pending SC = 0, no speech failure, terminal report = `failed`, safe idle = true. | Delivery is observed; the unnecessary reconfirmation remains a separate semantic concern. No successful left turn or physical audio evidence is claimed. |
| Returned failed resolution → normal Host | Exact delivered response enters history once; no second dispatch; session remains failed. | Controlled Host regression. Live replay uses the maintained text/simulator harness, not this Host entry method. |

```text
UMI ──→ SC greeting ─────────→ Runtime / playback ──→ terminal
  └──→ GA / Planner → rejected → stop uncommitted Work ──┐
                                    join SC delivery ←─┘ → failed session
```

Validation: **31 focused checks passed** (Planner contract/transport failure,
SC/service/playback failure, interruption, delivery bookkeeping and session isolation);
`speech_identity_latency` Level A **4/4** passed, without claiming latency qualification.
Pinned Ruff, repository policy, test ownership and documentation checks passed.
The existing broad-handler classification was re-audited for preserving independent
SC while retaining fail-closed Work containment; no exception was added.

One unchanged-source live case was replayed; it remains **0/1 passed**, stopped on
Planner contract failure. This is narrow evidence for SC survival, not end-to-end or
revision qualification. Agent digest matched
`feed9d772b73743d437f295202e55958da3f28830157d89d147b77efaa48980a`
before/after. Evidence and exact native calls are under
`.chromie/acceptance/independent-social-failure-focused-20260922/`; the one post-run
bundle is `/home/chromie/Downloads/chromie_debug_bundle_20260922_111601.tar.gz`.
The owned simulator was stopped after evidence collection.

Four axes: **source implemented** for independent-SC failure containment;
**local validation partial**; **target validation partial, mixed command still failing**;
**support development only**. Full tests/cohort, latency and physical microphone/speaker
proof remain owner-deferred. Next repair Fast's missing argument provenance and
separately diagnose SC's unnecessary reconfirmation. No commit/push was requested;
current documents, environment settings and architecture terms have no net growth.

## Focused mixed-turn activation repair — 2026-09-22 (current worktree)

The next audit iteration preserves the owner's small-case scope and defers latency.
An unchanged native UMI baseline accepted a greeting but rejected both greeting +
turn and silent turn: each mixed result requested GA for only its body Responsibility,
omitting its turn-local speech Responsibility. The existing Host correctly requires
initial GA to consider the entire turn. This is an activation-scope error, not evidence
that all physical requests need speech or that every turn must activate SC.

The UMI prompt now explicitly says that requested GA includes every Responsibility,
including turn-local speech, without thereby creating a Goal for each one. SC and
Planner keep independently selected scopes. Model, context projection, Schema, DTO,
validator and runtime scheduling are unchanged; no benchmark references were rewritten.

| Boundary / owner | Actual input → output | Verdict and evidence |
| --- | --- | --- |
| UMI primary → activation DTO | `你好，Chromie！然后向左转一下。`: correct greeting/body meanings, SC r1 and Planner r2, but GA r2 only → whole interpretation rejected. Silent-turn contrast similarly omits its speech restriction from GA scope. | Earliest wrong output is UMI's GA reference set; Schema accepts it and DTO correctly rejects it. No downstream SC/Planner was reached in these role probes. |
| Same three frozen inputs → revised UMI prompt | GA now includes both authored refs when requested; greeting still activates SC alone, quiet turn does not request SC. | All three native transactions pass separate wire-Schema and production DTO/Host checks, one invocation each. Exact wire comparison differs only in the declared system prompt. This qualifies only the selected activation contrasts. |
| Current deployment → greeting `0407e6c0` | SC says `你好呀！很高兴见到你。`; both TTS segments reach the discard sink and the session completes with no pending social work. | Narrow service/text pass; no physical microphone/speaker evidence. |
| Current deployment → mixed turn `d06f3a6a` | UMI passes with GA r1+r2, SC r1 and Planner r2; GA commits only body Work. Fast then omits direction provenance and also invents an unrelated weather lookup. | Host rejects the unbound direction before any Capability dispatch. Pending SC is cancelled by the failure path, so the greeting is not delivered. Both downstream defects remain open. |

The three-case live cohort stopped at case 2 on that hard Planner contract failure:
**one pass, one failure, one unrun**; both attempted cases retained safe idle. It is
incomplete, not a passing revision. Agent source matched digest
`feed9d772b73743d437f295202e55958da3f28830157d89d147b77efaa48980a`
before/after; one debug bundle was collected at the stop:
`/home/chromie/Downloads/chromie_debug_bundle_20260922_110209.tar.gz`.

Focused validation passed **11 tests / 2 subtests**, including the unchanged strict
GA-scope guard and independent SC/Planner subsets; `robust_intent_understanding`
Level A passed **8/8**. Evidence, frozen inputs, exact native requests, boundary
reviews, deployment identity and live results are retained under
`.chromie/acceptance/communication-activation-focused-20260922/`.
Four axes: **source implemented** for the bounded activation clarification;
**local validation partial**; **target validation failing/incomplete** beyond UMI;
**support development only**. Full tests/cohort, latency and physical evidence remain
deferred. Next investigate Fast argument provenance/unrequested Work and the Host
failure path cancelling an independent greeting. No commit/push was requested.

Latest refinement: [independent expression and complete delivery](#independent-expression-and-complete-delivery--2026-09-22)
supersedes the earlier equal-Capability duplicate policy and strengthens delivery completion.

The owner's subsequent clarification allows natural repetition for casual gesture
requests. The existing `blink_once_plain_request` case now checks supported blink
execution without requiring count 1; its historical ID and raw evidence are retained.
Earlier count-only failures for “眨一下” are no longer treated as product defects.
No Planner quantity optimization is being pursued.

The next bounded audit repair preserves model-request field order when exporting
`llm_calls.jsonl`. In the retained `20260922_102129` bundle, original service logs
preserve order while the collector sorted 20 of 23 recovered calls' requests;
Schema property order therefore differed in subsequent frozen probes. The collector
now preserves that order. This repairs evidence fidelity, not native model behavior;
the previous sorted-packet probes do not qualify the exact production transaction.
Original ordered records and the failing/passing collector regression are retained
under `.chromie/acceptance/audit-evidence-order-focused-20260922/`. Four focused
checks passed, covering the logger-to-bundle round trip and scenario-library validity.
Four axes: **source implemented** for evidence export and the corrected casual-blink
oracle; **local validation partial**; **target validation not rerun** (historical
runs are not promoted to passes); **support development only**. Full tests, live
cohorts and latency optimization remain owner-deferred. No runtime semantic change,
new fixture, document, setting or model call was added.

## Focused session completion repair — 2026-09-22 (current worktree)

The owner approved beginning the audit repairs with **only a few common cases**;
the full test suite and full 75-case live cohort are explicitly deferred for this
iteration. This section updates audit findings 1 and 7 below for source scope only.
No benchmark reference, semantic prompt, model profile or duplicate-action policy
was changed. No commit/push was requested.

| Boundary / owner | Before → implemented change | Evidence and remaining limit |
| --- | --- | --- |
| SC coordinator → Host SessionTracker | Detached inference/delivery/expression tasks were absent from the completion condition → register each task under its explicit SID; recheck completion after its terminal callback. | Controlled slow-SC/body-Work regression proves Work returns while SC is pending, without early session finalization. |
| Host → playback and workflow reporting | `llm_done` plus zero queued TTS could finalize before SC supplied speech → require zero pending social tasks as well as terminal TTS accounting. | Late-speech regression holds final report creation until playback; failure and cancellation remain terminal facts, never fabricated delivery. |
| Acceptance wait → session state | Wait inspected global auxiliary tasks and inferred SID from task names → read the owning session's pending count and retained failure records. | Cross-session regression excludes unrelated pending/failed work; current-session failures still fail acceptance. |

Focused validation: **13 tests passed**, including ordinary greeting, delayed SC,
late playback/reporting, failure, cancellation, explicit session/turn identity and
session isolation; the `speech_identity_latency` Level A class passed **4/4**.
Pinned Ruff, repository policy and test-ownership checks passed. These tests used
the available Python 3.13 host; the complete supported-environment canonical gate
was not run. No new document, runtime switch or architectural term was added.

The deployed Agent initially differed from this checkout. It was rebuilt/recreated
and verified against packaged-source digest
`715814252afb63b2e3caf8c99da9d291fe26b667778e0d0ff708bb52bdcb2d82` before the baseline.
Both small live runs used the existing RTX 5090 / SGLang `chromie-gemma4-12b`
profile with text admission, real TTS and discarded audio; no simulator or physical
device evidence is claimed. One unchanged-source run per iteration exercised
Chinese identity/greeting and two consecutive English social turns, followed by
one debug bundle per run.

Baseline: English greeting and follow-up delivered; Chinese identity generated a
reply but all four TTS parts were cancelled at the 3.5-second playback-start
deadline. After the lifecycle patch, all three turns delivered and completed with
zero pending social tasks: Chinese identity **11.56 s**, English greeting **11.96 s**,
follow-up **12.42 s** total turn time. This does not qualify latency. Different
generated wording and a warm service prevent attributing the vanished playback
timeout to this lifecycle repair; that delivery failure remains open.

Evidence: `.chromie/acceptance/session-completion-focused-20260922/` retains the
three-turn manifest, baseline/after runtime identities, logs, summaries, bundle
receipts, focused tests and Level A results. The post-change dirty-tree identity
is diagnostic-only. Four axes: **source implemented** for lifecycle/accounting;
**local validation partial** (focused only); **target validation partial** (three
text/TTS turns, no physical audio); **support development only**. Next: investigate
playback-start timeout/response latency and the retained duplicate-action admission
defect in separate bounded iterations. Remaining audit findings stay open.

### Focused TTS readiness follow-up — 2026-09-22

The maintained live-text entry point omitted the synthesis readiness performed by
normal startup. It now uses the effective Host voice for Chinese, English and
mixed no-playback probes before admitting any turn, retaining `tts-readiness.json`.
Failed synthesis or empty audio stops admission; no production timeout, prompt,
model profile or playback policy changed.

| Actual boundary / owner | Observed input → output | Assessment |
| --- | --- | --- |
| Live-text runner → TTS startup | Previously began scenarios after service health alone; now probes effective `chromie_mixed` voice and retains nonempty PCM for all three texts. | Confirmed harness readiness omission repaired; not proof of the original timeout's cause. |
| UMI → concurrent GA / SC | After Chinese text admission, UMI took 6.99 s; GA and SC then took 4.46 / 4.74 s concurrently. Planner and physical Work were not invoked. | Most greeting delay precedes TTS; semantic optimization remains unqualified. |
| SC → Host TTS / completion | Both post-change greetings produced speech, all scheduled audio reached the discard sink, and sessions ended with zero pending social tasks and no speech failures. | Narrow text/service delivery observed; no physical microphone or speaker evidence. |

The restarted-service baseline **also passed both greetings** (Chinese 14.45 s,
English 10.79 s), so the earlier playback-start timeout was not reproduced and
remains unexplained. After the harness repair, Chinese completed in **13.70 s**
and English in **12.55 s**; the three readiness probes took **3.04 s** separately.
These two samples do not establish a latency improvement or release qualification.
The existing RTX 5090 / SGLang profile and source-verified Agent were unchanged.

Five focused tests passed (including two failure subtests); pinned Ruff, repository
policy and test-ownership checks passed. Full tests and the full live cohort remain
deferred by the owner. Evidence, runtime identities, per-session workflows and one
debug-bundle receipt per baseline/after run are retained under
`.chromie/acceptance/tts-readiness-focused-20260922/`. Four axes: **source implemented**
for harness readiness; **local validation partial**; **target validation partial**
(two text/TTS turns, dirty-tree diagnostic only); **support development only**.
Response latency, the unconfirmed playback timeout and duplicate-action admission
remain open. No commit/push was requested.

### Independent expression and complete delivery — 2026-09-22

Owner clarification supersedes the equal-Capability rejection described below:
requested two-blink Work belongs to Planner, while SC may independently select
additional blinks or other expression. Extra count, equal Capability ID and
pre-Plan timing alone establish no defect. SC expression remains Goal-free and
does not discharge requested Work; the whole response must still join its SC
decision and admitted delivery. The canonical interaction contract now states
this distinction. No new benchmark fixtures, document, setting or model call were
added; latency and full tests/cohort remain owner-deferred.

The Host now retains primary Plan visibility for resource checks without treating
equal Capability IDs as semantic duplication. SC's existing prompt clarifies
task ownership while permitting independently intended use of the same Capability.
This is not a claim that native social meaning is fully qualified: recorded SC
rationales still describe fulfilling the request, and rationale alone does not
prove a transfer of Goal-completion authority. Planner quantity prompt candidates
were ineffective and reverted; their failed native outputs are retained.

| Boundary / owner | Actual episode and expected contract | Repair / evidence |
| --- | --- | --- |
| UMI → parallel GA, Planner and SC | `filler_blink_twice`: r1 is requested two-blink body Work. SC may independently acknowledge it; only Planner Work satisfies that action. | Final `10d983a7` retains separate primary and auxiliary request IDs; SC delivery has no Goal IDs. |
| Planner → Runtime / observation oracle | Native Fast emits count 2, then legitimate default normalization leaves `args={}`. The provider's optional default is 2. For `blink_once_plain_request`, the same default is genuinely wrong. | Retain each dispatched Capability's exact ID/version/input schema and use only matching optional defaults when observing results. No production arguments or historical artifacts are rewritten. |
| SC → Runtime → session completion | `d7648112` produced punctuation-only speech; TTS rejected it, but the old join ignored failed delivery and reported complete. Its mechanical case pass was insufficient. | Join Runtime status and actual speech completion; retain failures and report a failed workflow. Controlled provider/playback failures fail truthfully without replaying Work. |
| Same-turn Plan update → existing SC delivery | `f1e4ff74` cancelled the already submitted SC blink on ordinary Work-state re-entry. The new delivery check correctly exposed the cancellation instead of passing it. | Wait for submitted same-turn expression, then build SC's next input from the refreshed interaction ledger. Stale unsubmitted decisions, new turns and explicit interruption retain cancellation. Both independent and Plan-bound SC paths use this join. |
| All same-session work → final report | Final `10d983a7`: primary blink Work and SC blink expression completed; Work ended at about 22.6 s and the final SC decision at 28.1 s. | Session completion follows both, with zero pending social tasks/failures and safe idle. Latency is observed only, not optimized or qualified. |

The final one-case text + headless MuJoCo replay passed. It is narrow service/sim
evidence, without physical microphone, speaker or robot proof. The preceding
two-case run completed with one mechanical pass and one count failure; the
delivery-check-only run stopped on a retained cancellation failure. Neither is
promoted to a passing revision. The simultaneous gaze/blink frozen contrast also
retains invalid parallel scheduling or truncated output; it remains open.

Focused ownership/delivery/cancellation checks passed **24 tests**; separate
session/playback checks passed **5 tests / 2 subtests**. The default-observation
regression passed with explicit, omitted, required and stale-contract contrasts.
The affected `speech_identity_latency` Level A class passed **4/4**, using explicitly
simulated delivery only. Full canonical tests and the full discovered live cohort
were not run. Evidence and all failed candidates are under
`.chromie/acceptance/social-task-ownership-focused-20260922/`, including source
patches, runtime identities, native packets, reviewed case summaries and one bundle
per live run. Four axes: **source implemented** for ownership admission and joined
delivery; **local validation partial**; **target validation partial** (one final
common case passes; once-count and broader semantic failures remain);
**support development only**. No commit/push requested.

### Focused duplicate-primary containment — 2026-09-22 (superseded policy)

The owner explicitly deferred latency optimization and requested the next bounded
repair, retaining the small-test scope. Independent Work-state SC admission now
receives a deep copy of the canonical Plan from its calling coordinator. It checks
the union of primary response and Plan Capability IDs through the existing
duplicate/resource/availability rules; Plan steps never enter the social dispatch.
No model-facing prompt, Schema, profile, benchmark reference or new switch changed.

| Boundary / owner | Actual input → output and change | Evidence / limit |
| --- | --- | --- |
| Committed Work → independent SC coordinator | Canonical blink `count=2`; a separate SC response proposes blink `count=1`, with no task capabilities of its own. Previously the Host passed an empty primary view to admission. | Earliest reproduced defect is Host context handoff; the Plan already existed. |
| Coordinator → auxiliary admission | Pass the same retained Plan snapshot alongside the social response; exact-ID duplicates and shared-body-resource conflicts now suppress the optional proposal. | Before: 4 controlled duplicate/conflict variants dispatched incorrectly. After: all rejected with retained reasons; speech and compatible expression still work, original Plan unchanged. |
| Admission → Runtime | Submit only accepted social expression, without copying or replaying primary Work. | 11 focused tests pass, including spoken/nonverbal contrasts, compatible/no-primary expression, interruption and repeated-dispatch suppression. |

The `composable_action_planning` Level A class passed **5/5**; pinned Ruff,
repository-policy and test-ownership checks passed on the available Python 3.13
host. Full tests/cohort remain deferred; no physical audio or robot proof.

Native text + headless MuJoCo evidence remains **failing**. The two-case baseline
stopped at gaze/blink (`a8b20f88`) on Fast's invalid singleton parallel group;
one of two selected cases was unrun. After the patch both cases ran but failed:
gaze/blink `0ed5a0ab` and plain blink `500fd481` both emitted blink `args={}`,
so count assertions failed; the compound Plan also remained sequential. Providers
returned completed results (blink `no_motion=true`), and every attempted case
returned safe idle. Post-Plan SC chose silence, so these runs do not prove a native
duplicate proposal was rejected. Plain blink also retained an earlier, pre-Plan
SC blink dispatch followed by primary blink Work: that separate premature
task-fulfillment path remains open and must not be called fixed by this patch.

Evidence: `.chromie/acceptance/duplicate-primary-focused-20260922/` retains
before/after tests, native workflows, identities, case reviews and one bundle per
live run. Four axes: **source implemented** for committed-Plan containment;
**local validation partial**; **target validation failing**; **support development
only**. Next: qualify pre-Plan SC task fulfillment and exact blink count grounding
as separate transactions; latency stays deferred. No commit/push requested.

## Local gate closed; live qualification blocked — 2026-09-22 (current)

Resuming `92edd5ba` closed the recorded local validation gap. Benchmark path/import
and frozen-reference contracts were migrated explicitly; a reproduced live harness
completion race now waits for pending Social Cognition before closing service clients.
No production semantic role/prompt/validator was changed. Frozen reference owner review
remains pending, including 100 substantive terminal-history GA oracle corrections.

Four axes: implementation complete for these benchmark/acceptance repairs; local
validation passed (6,000 strict replay outcomes, 45 Level A cases, final canonical
145 benchmark / 3,658 main / 1,015 subtests / 20 legacy tests); target validation
incomplete and failing; support development only. The rebuilt, source-verified
RTX 4090 Laptop SGLang Agent and headless MuJoCo ran the discovered 75-case baseline
before and after the harness repair. Both stopped at case 3: 1 mechanical pass,
2 failures, 72 unrun. Review finds zero qualified semantic passes. Fast substituted
sidestep for turn and authored unsupported acquisition-purpose Work; SC silence,
primary-task expression and spoken-stage-direction failures remain. The harness fix
retains late SC/TTS evidence, while production Host workflow finalization remains
an open boundary. All attempted cases retained safe idle; no new physical evidence
or release qualification. See the current [checkpoint](../DEVELOPMENT_CHECKPOINT.md)
and [handoff](../HANDOFF.md) for exact I/O, identities, case reviews and resume commands.

### Full project audit — 2026-09-22

The current delivery is **not release-qualified**. The local gate is green against
the migrated source and references, but target evidence is both incomplete and
failing: the current-revision aggregate stopped at case 3 of 75, and semantic review
finds zero qualified passes among the three attempted cases. All attempted simulator
cases reached safe idle. No new physical microphone, speaker or robot evidence exists.

The audit followed the complete admitted-turn transaction and the accepted authority
map: UMI owns WHAT and cognitive activation requests; Goal Association owns canonical
Goal continuity; Planner owns HOW without ordinary wording; Social Cognition owns
ordinary communication and optional social expression; Host/Runtime owns mechanical
validation, scheduling, delivery and lifecycle without semantic reinterpretation.

#### Confirmed release blockers

1. **Production session finalization precedes same-turn Social Cognition and TTS.**
   The execution-only path starts `initial_social_task` and returns the primary
   interaction without joining it. Detached Work completion sets `llm_done`; with
   no TTS scheduled yet, `SessionTracker.maybe_done` finalizes the session and its
   workflow report. In rerun `f837523a`, SC started at `01:18:07.677`, production
   recorded `session_done` with zero scheduled/played TTS at `01:18:12.595`, SC
   completed at `01:18:16.417`, and three TTS items then played through
   `01:18:22.241`. The acceptance wait preserves this late evidence but does not
   repair production lifecycle or report finalization.
2. **SC duplicate-primary containment lacks the canonical primary Work view on the
   independent state-interaction route.** SC proposed `soridormi.blink_eyes` three
   times and described it as primary task fulfillment after Planner/Runtime had
   already admitted blink twice as Goal-owned Work. The independent SC response is
   initialized with `capabilities=[]`; auxiliary admission derives
   `primary_capability_ids` from that response, so its apparent exact-ID duplicate
   check cannot see the immutable Plan. One auxiliary blink request was materialized.
   SC also spoke stage directions `（看着你三秒）` and `（眨眼两次）`.
3. **Fast Planner produced a wrong semantic result in every attempted live case.**
   The compound case substituted `sidestep(left)` for `turn_in_place(left)` despite
   both exact Capability descriptions being supplied. The gaze/blink case claimed
   complete coverage of a simultaneous request while authoring sequential physical
   Activities; because physical Work must remain sequential, the transaction needed
   a truthful limitation or clarification rather than a false completion claim. The
   milk case marked locomotion as information acquisition without a provider-declared
   acquisition contract and proposed `0.25 m/s * 20 s` for 50 m. Host correctly
   rejected that last output before effect dispatch.
4. **UMI activation, the UMI prompt and the fresh-interaction SC contract are not
   yet one qualified decision boundary.** All three live UMI outputs requested only
   Planner, so SC started later from Work state. The UMI prompt says to request SC
   when interaction warrants it, while the explicit fresh-addressed-turn duty lives
   inside the downstream SC prompt. The migrated UMI references request SC in all
   1,496 cases, but fixture agreement cannot decide whether that broad activation
   policy is semantically correct. The Charter also states that not every turn needs
   every authority, so Host must not replace the missing qualification with a fixed
   output-mode, keyword or always-invoke rule.
5. **Communication ownership remains split across maintained contracts and prose.**
   Active Planner model DTOs are word-free and the current runtime rejects
   Planner-authored communication before SC, but the shared `CanonicalPlan` still
   accepts `response_text`, `communicative_acts` and `auxiliary_activities`; retained
   classes and validators still describe Planner as exact wording owner. `README.md`,
   `ROADMAP.md`, `orchestrator/README.md`, and runtime comments repeat that retired
   rule despite Charter `SPEECH-OWNER-001`. The documentation gate does not detect
   this authority contradiction.
6. **Passing reference replay is mechanical compatibility evidence, not independent
   semantic qualification.** This worktree migrates 1,496 UMI, 1,500 GA and 152 Fast
   packets, including 100 substantive GA terminal-history oracle changes. The strict
   6,000-case replay proves that source, Schema/Host and the newly authored references
   agree. Frozen-reference owner review, independent semantic review, native inference
   qualification and training promotion remain open.
7. **The repaired acceptance wait is not fully session-scoped.** It filters retained
   `_social_turns` by session task name but also waits on the coordinator's entire
   `_auxiliary_execution_tasks` set. An unrelated session's pending or failed task can
   delay or fail the case being judged. The repair is useful for the current serial
   cohort, but overlapping-session evidence needs a scoped contract and regression.

#### Actual episode workflow and earliest wrong boundaries

| Episode | Authoritative input and ordered path | Actual output | Expected output / verdict |
| --- | --- | --- | --- |
| Compound `630f4c86` | Gateway admits walk at 0.2 m/s for 10 s, nod twice, then turn left → UMI `r1` → GA new Goal → Fast | Fast `act_003` selects sidestep and calls it a turn; canonical validation and Runtime execute walk/nod/sidestep; late SC chooses silence | UMI/GA correct. Fast is the earliest wrong boundary; legal Host admission cannot prove semantic equivalence. SC activation/silence remains independently unqualified. |
| Gaze/blink `f837523a` | Gateway admits look for 3 s while blinking twice → UMI `r1` → GA new Goal → Fast → Host/Runtime, with asynchronous work-state SC | Fast executes sequential gaze then blink while claiming simultaneous completeness. Host finalizes before SC. SC later emits three utterances and one duplicate blink request. | Fast first loses temporal meaning. SC then violates wording/expression ownership, and Host fails duplicate containment and lifecycle joining. |
| Milk `6b116449` | Gateway admits fetch milk 50 m ahead → UMI `r1` → GA new Goal → Fast → Fast Schema/Host validation | Fast authors unsupported acquisition-purpose steps and inconsistent distance realization; validator returns `fast_stream_contract_invalid`; no effect dispatch, Deep Planner or SC | Fast is wrong. Host containment is correct and preserves safe idle; the validator must not be weakened. |

The next implementation order is: repair production session/SC/TTS joining and
workflow-report finalization; give auxiliary admission the immutable canonical Work
view; freeze and qualify UMI activation contrasts; freeze Fast contrasts for semantic
substitution, simultaneity and acquisition grounding; retire the remaining competing
Planner speech surfaces and prose; obtain owner review of migrated references; and
make acceptance task retention session-scoped. Each authorized repair requires its
focused scenario and general-ability class, the canonical gates, then one unchanged-
revision complete 75-case aggregate with one debug bundle. Physical evidence remains
a separate supervised gate.

## RTX 4090 Laptop SGLang source migration — 2026-09-17 (current)

The owner identified that the maintained RTX 4090 Laptop still ran all cognition through
Ollama's one sequence slot while RTX 5090 had already moved to the maintained SGLang
service path. Current source now changes **serving runtime only** for the laptop: every
semantic role remains `qwen3.5:4b` with the existing 16K UMI, 32K ordinary-role and 49K
Fast/Deep request limits, but the hardware profile selects a dedicated
`docker-compose.sglang-rtx4090-laptop.yml` override and `AGENT_LLM_PROVIDER=sglang`.

The laptop override pins the retained AWQ artifact
`cyankiwi/Qwen3.5-4B-AWQ-4bit@ef85d23bebaba87b3c4672ba11c449c79dbdb23e`, uses the same
pinned SGLang image build as the maintained 5090 path, retains priority scheduling and
preemption with at most three running requests so SC, GA and Fast Planner can occupy the
normal post-UMI fan-out together, and keeps the shared token budget at 49152
so one current maximum Planner transaction is representable. The older laptop SGLang
resource evidence proved resident CosyVoice with a 32K cache/two 16K requests only; it
does **not** qualify this new 49K production source topology. First startup may fetch only
the pinned model revision into `hf_cache`; subsequent offline use may set the existing HF
offline variables.

Source/profile/Compose tests prove automatic laptop selection, no active Ollama inference
model, preserved role budgets, pinned model identity and priority/preemption configuration.
Target promotion remains open until the real 16GB machine proves SGLang readiness, Qwen
contract behavior, 49K cache + CosyVoice coexistence, foreground contention/preemption and
the retained text/MuJoCo compound case on one runtime identity. Ollama remains the fallback
transport for other profiles and comparison evidence; it is not deleted.


## Successful semantic-facade E2E and bounded follow-up — 2026-09-16 (current)

The owner-provided `chromie_debug_bundle_20260916_191920.tar.gz` proves the original
compound text case now executes end to end on current source. Session `c9a2a253` keeps
one complete Responsibility/Goal, Social Cognition independently acknowledges with
`Okay, I'm on it!`, and Fast authors three sequential semantic Activities:
`walk_velocity`, `nod_yes`, and `turn_in_place(direction=left)`. All three Runtime
results are `completed` in sim. The turn Plan contains no provider-local yaw sign for
`turn_in_place`; the earlier wrong-direction/Host-rejection failure is therefore closed
at the Core/Runtime semantic boundary.

The same evidence exposes four narrower follow-ups rather than reopening the architecture.
UMI labels the physical-only compound `output_mode=other`; Fast consequently invents a
`complete_response` whose only purpose is to confirm/narrate the Work, causing another SC
pass. Fast also spends one 6.8 s lookup on `soridormi.robot.get_status`, whose provider
hint incorrectly recommends status before movement. The accepted direction provenance is
valid but over-wide (`t7..t19` instead of the unique literal `t19`). Finally, Runtime
already has a trusted `provider_realization` trace, but the debug evidence recorder does
not retain that event body. Initial SC is correct but still expensive (about 9.7 s in the
retained call); aggressive decoder/schema changes remain deferred.

The bounded source follow-up keeps one authority per fact. UMI now states that multiple
physical actions remain `body_action` unless result domains genuinely differ, and Planner
may not create `complete_response` merely to acknowledge/confirm/narrate Capability Work.
Trusted provenance code may narrow an already-valid model-selected argument span only to
one unique exact **string** literal inside that span; numeric spans retain units/modifiers,
and absence/ambiguity preserves the original span. Cognitive outcome evidence now records
diagnostic `provider_realizations[]` from existing Capability traces without exposing
provider args to UMI/GA/Planner/SC or adding them to semantic Evidence. SC receives a bounded
owner-approved Mind projection that preserves identity, personality, worldview/values,
social style, long-term goals and deliberation/experience policy while removing duplicate
`prompt_summary`, reflex-policy and internal self-model material. A paired Soridormi
manifest patch separately makes robot status an explicit observational capability rather
than movement preflight.

Focused source tests pass for each slice; native latency/semantic promotion is not claimed
until the exact compound case is rerun with both repositories rebuilt. The next retained
run must prove: no `get_status` detail lookup for ordinary movement; no confirmation-only
`complete_response`/second SC pass; minimal unique string-literal direction provenance;
`provider_realizations` showing semantic `direction=left` and provider-local signed yaw;
and new initial-SC/Fast timings on one verified revision.


## Native follow-up repair after semantic-facade live success — 2026-09-16 (current)

The owner-provided current-revision text/MuJoCo bundle proves the original compound
walk/nod/left-turn request now reaches completed Work with Planner authoring semantic
`direction=left`, not provider yaw sign. It also exposed three narrower remaining defects:
SC twice justified silence from the absence of Planner communication needs; the live bundle
did not retain the exact semantic-args -> provider-args materialization; and Fast spent one
extra native call requesting `soridormi.activity.get_capabilities` despite already owning a
current Capability index and bounded detail-lookup transaction.

The source repair keeps authority unchanged. SC now receives a compact fresh-interaction
opportunity before its larger snapshot, omits an empty `communication_needs` model field,
and removes the duplicate full UserTurnEnvelope from model context while the trusted request
retains it. A fresh addressed task is explicitly an interaction opportunity; task-oriented
content or lack of a Planner Need is not itself a silence reason. Soridormi semantic-facade
materialization is appended to the existing trusted CapabilityTrace as diagnostic execution
provenance (`semantic_args`, `provider_args`) and never enters Planner/SC inference. Fast
Planner's provider library now excludes `*.get_capabilities` introspection entries because
its own current index/detail lookup already owns that discovery boundary.

Focused verification passes 111 SC tests (one known archive assertion deselected), 21
semantic-facade/provider tests plus 10 subtests, and 157 Fast/Runtime tests plus 17 subtests.
Native requalification is still required: rerun the same compound text/MuJoCo episode and
confirm SC no longer uses missing communication needs as its silence rationale, the trace
records `direction=left` -> provider-local signed yaw, and Fast no longer performs the
redundant catalog-introspection call. These changes reduce avoidable work but do not yet
claim the final interaction-latency target.

## Phase 2B relation-aware generalization qualification — 2026-09-16

**Dependency-light qualification substrate implemented; native relation corpus still open.**
A maintained checker now evaluates retained structured observation pairs against declared
metamorphic invariants, required deltas and side-specific assertions. It deliberately runs
after inference and contains no phrase-to-answer mapping. Focused regressions cover provider-
frame invariance, paraphrase with changed source spans, controlled left/right mutation and
independent semantic drift. This makes relation failure first-class evidence but does not
claim that current native UMI/Planner/SC models pass those relations or that a continuous
episode profile is complete.


## Phase 2A declared semantic Capability facade — 2026-09-16

**Source substrate implemented; paired provider declaration and native qualification remain open.**
Soridormi live named capabilities may now publish a closed `metadata.semantic_facade` whose
Core-facing `input_schema` contains provider-neutral semantic arguments while a trusted adapter
realizes provider-local arguments only immediately before provider planning. The first qualified
realization primitive is signed magnitude: e.g. Planner may author `direction=left|right` plus a
positive turn-rate magnitude while the provider adapter alone maps that meaning to the local yaw
sign. Runtime validates the semantic schema, not the provider encoding; provider-frame reversal
therefore changes adapter realization without changing Planner meaning. Capabilities that do not
declare a facade retain their current schema; Chromie does not infer a facade from names or user
phrases. No current Soridormi deployment is claimed migrated until that provider publishes the
declaration and target evidence is rerun.


## Phase 1E Social Cognition model-view diet — 2026-09-16

**Source implemented; native semantic/latency qualification remains open.** The trusted
`SocialCognitionRequest` still carries the complete validated Plan/context and content-
addressed lineage. Only the model-facing projection is reduced: exact Capability IDs,
provider arguments, parameter-resolution mechanics and selected Agent Skills stay outside
SC inference, while high-level Plan/Goal/Work/Evidence/interaction facts remain. The SC
authority contract now states that its raw motor-control prohibition applies to SC-authored
social expression and is not evidence that high-level Work such as walking or turning is
unavailable or unsafe.

## Semantic transaction simplification design — 2026-09-16 (design approved; source not migrated)

The owner approved the next architecture line against the supplied 2026-09-16 archive:
reduce avoidable Planner/SC model protocol burden, move provider-shaped realization behind
semantic Capability facades, then add metamorphic and continuous-episode qualification
before resuming model/backend/latency optimization. The Charter and canonical cognitive
architecture now define that target.

**Implementation status:** not yet migrated. The current source still uses the existing
Planner provenance/argument wire and current Capability schemas; the current API/turn-loop
documents continue to describe that implemented wire until the corresponding source slice
lands. This design amendment therefore creates no new source pass, native semantic pass,
latency pass or release evidence. The retained Fast source-provenance/wrong-direction and SC
relevance failures remain the initiating evidence for the next audit.

The next source slice is limited to a field-by-field Planner/SC contract-burden audit and
red regressions. Prompt/model changes are explicitly deferred. See the current
[roadmap](../ROADMAP.md), [checkpoint](../DEVELOPMENT_CHECKPOINT.md) and
[handoff](../HANDOFF.md).

## Project audit and mixed readiness — 2026-09-16 (current)

| Implementation | Automated verification | Target validation | Release readiness |
| --- | --- | --- | --- |
| Independent ready and newly scheduled Goals can share one Fast/Deep primary Plan; source-bound future conditions remain unmet and cannot execute early. SC acknowledgement does not complete the future effect. Existing authority documentation reconciled; dead Planner wording export and duplicate SC Protocol method removed. | Final loop: 3,471 tests / 1,017 subtests, 145 benchmarks, 20 legacy; 6,000 strict replay outcomes, source unchanged; Level A 45/45. Ten new timing/negative/Runtime/restart cases pass. Four hundred request-only fixtures refrozen without changing responses or behavior oracles. Three full loops out of maximum eighteen; earlier failures retained. | Three all-74-case live invocations stop at first hard Fast contract failure; 0/1 each, 73 unrun, safe idle. Final UMI/GA correct; Fast citation/direction and SC invented limitation/silence fail. Native 12-case prompt candidate rejected for two new truncations; 9B comparison not promoted. Original prompt retained. | Development delivery only. Native Fast provenance/direction, SC relevance/latency, full current-revision live cohort and #24/#32 target evidence remain open. No physical or release promotion. |

[Audit](../ARCHITECTURE_AUDIT.md), [checkpoint](../DEVELOPMENT_CHECKPOINT.md) and
[handoff](../HANDOFF.md) own findings, exact results and operational identities.
Evidence: `.chromie/acceptance/full-audit-20260916-f90dff450/`. Earlier rows below
are historical; independently timed Goals now have controlled integration proof,
while temporal composition inside a single compound Goal is not qualified here.

## Intent ownership and Fast capability library — 2026-09-16 (historical)

| Implementation | Automated verification | Target validation | Release readiness |
| --- | --- | --- | --- |
| Owner-authorized UMI intent-only contract with existing result type; GA inherits intent through Host and owns continuity; Planner owns parameters/readiness. Fast has full common contracts, all-capability index and one bounded detail lookup. SC owns communication/Social Attention with existing highest foreground priority. | Canonical 3,461 tests / 1,017 subtests, 145 benchmarks and 20 legacy tests pass; 6,000/6,000 strict replay outcomes, source unchanged; Level A 45/45. Numeric source/default/ownership, retained-state rejection and future waiting regressions included. | Native UMI 19/24 semantic (24/24 mechanical); controlled-UMI → native GA 24/24 new Goals. Latest full 51-case text/MuJoCo invocation stops at first case: 0/1, 50 unrun. UMI/GA correct for that compound, Fast quotes/direction wrong, SC silent; Host rejects, zero body calls, safe idle. | Development delivery only. Native semantic/SC latency, #24/#32 and remote target qualification remain open. 200 old typed GA update references explicitly fail closed; mixed new waiting/ready Goals unqualified. No training, physical or release promotion. |

[Checkpoint](../DEVELOPMENT_CHECKPOINT.md) owns exact implemented boundaries and
actual concurrent module I/O; [handoff](../HANDOFF.md) owns reproducible commands,
source/runtime identities, three stopped aggregate bundles and shutdown state.
Evidence: `.chromie/acceptance/intent-authority-20260916/`. One compound UMI
Responsibility may legitimately own several Activities. Earlier claims that merely
combining those actions is a UMI error are superseded by the approved contract.
Earlier sections below are historical; source/prompt are changed in this delivery.


## Cross-machine current-source baseline — 2026-09-15 (historical)

| Implementation | Automated verification | Target validation | Release readiness |
| --- | --- | --- | --- |
| Fetched upstream; current `6fca5be2` executable source unchanged. Stale laptop Agent rebuilt and source verified; existing local Qwen4B profile retained. | Fresh canonical 3,510 tests / 1,164 subtests, 145 benchmarks and 20 legacy pass; Level A 45/45; all 6,000 expected replay outcomes with source unchanged. | Full 51-case must-pass text/MuJoCo invocation stops at first case: 0/1, 50 unrun. UMI primary/Deep merge three effects; GA produces invalid resource quantity and is rejected. No body execution, safe idle retained. This laptop run is not remote Gemma qualification. | Development only. UMI semantics and a separate GA Schema/DTO gap remain; #24/#32 and native qualification stay open. Owner microphone/ASR acceptance unchanged. |

[Checkpoint](../DEVELOPMENT_CHECKPOINT.md) and [handoff](../HANDOFF.md) retain
module I/O, model/source identities and shutdown state. Local evidence:
`.chromie/acceptance/resume-20260915-6fca5be2/`. No prompt, model selection or
training promotion; only operational and evidence state changed in this session.

## Source-backed lightweight UMI handoff — 2026-09-15 (historical)

| Implementation | Automated verification | Target validation | Release readiness |
| --- | --- | --- | --- |
| Complete Host-owned original source accompanies UMI; pre-GA authority label fixed. GA accepts complete queries without duplicate classification; Planner supports owned literal source arguments. Earlier SC/Fast/Schema safeguards included. Default UMI prompt unchanged after rejected candidates. | Canonical 3,510 tests / 1,164 subtests, 145 benchmarks; 6,000 expected workflow outcomes; Level A 45/45. Original-text fidelity and numeric/ownership/contradiction containment verified. | Controlled UMI → native GA 4/4 and pre-GA Fast 4/4. Canonical Fast/Deep 0/8 semantic acceptance. Two UMI candidates rejected; no latency, default-output simplification, deployment or robot improvement claim. | Development delivery only. Full Qualification open; microphone/ASR owner-accepted. Rebuild before owner's personal test, then await their next direction. |

See [checkpoint](../DEVELOPMENT_CHECKPOINT.md) and [handoff](../HANDOFF.md).
Evidence `.chromie/acceptance/umi-source-handoff-20260915/`; rejected prompts are
not delivery source. Earlier sections below are historical.

## UMI intent handoff experiment — 2026-09-15 (previous experiment)

| Implementation | Automated verification | Target validation | Release readiness |
| --- | --- | --- | --- |
| Requested runtime simplification remains unimplemented. Rejected trials restored byte-for-byte; retained sparse-query/numeric-conservation regressions and corrected stale SC wording ownership. Prior Schema deduplication remains. | Canonical 3,481 tests / 1,164 subtests, 145 benchmarks and 20 legacy tests pass. Focused 102 tests / 136 subtests and Level A 45/45 pass. Controlled UMI Host → GA → Planner preserves query scope without duplicate time fields. | 18 frozen cases / 23 transactions; 106 retained native responses across baseline, full and interrupted trials. No candidate met non-regression criteria. Restored host/deployed source digests match. | Development only; Qualification remains open. Owner personal check next; microphone/ASR remain owner-accepted. No deployment, speedup or successful simplification claim. |

See the [checkpoint](../DEVELOPMENT_CHECKPOINT.md) and [handoff](../HANDOFF.md)
for exact I/O, candidate rejection reasons and validation. Evidence:
`.chromie/acceptance/umi-intent-handoff-20260915/`. Do not promote rejected prompts or
turn this evaluated cohort into training data.

## UMI Schema deduplication — 2026-09-15 (preceding)

| Implementation | Automated verification | Target validation | Release readiness |
| --- | --- | --- | --- |
| UMI primary/Deep source-spelling enums share one definition; original allowed values and prompts/models unchanged. Local Agent rebuilt and source verified. | 115 focused tests / 173 subtests; 6,000 expected replay outcomes and Level A 45/45. Final canonical 3,477 tests / 1,161 subtests, 145 benchmarks, 20 legacy pass. Request-only fixture refreeze proves expanded Schema equality; expected outputs unchanged. | Frozen 12-case/16-variant native pairs have identical raw outputs; all 40 calls including repeats pass mechanical checks. Full semantic review remains 1/16 each. Weather wire bytes fall 32.5%; input tokens unchanged and no end-to-end speedup established. | Development only; full Qualification and earlier semantic/live coverage blockers remain open. Bounded schema work ends for the owner's personal check. Microphone/ASR remain owner-accepted. |

[Checkpoint](../DEVELOPMENT_CHECKPOINT.md) and [handoff](../HANDOFF.md) retain the
exact module I/O, comparisons, runtime identity and commands. Evidence:
`.chromie/acceptance/umi-schema-dedup-20260915/`. No prompt rewrite, model change,
training promotion, semantic repair call, new current document or runtime flag.

## Necessary engineering repair — 2026-09-15 (previous pass)

The owner will personally check Chromie before deciding next work. Microphone/ASR
remain closed by owner-reported acceptance. Earlier rows are historical.

| Implementation | Automated verification | Target validation | Release readiness |
| --- | --- | --- | --- |
| Fast native branches preserve typed vocal provider/mode and existing execution/delegation states; full Schema/DTO/Host checks remain. No prompt/weights changes, phrase rules or new semantic calls. Previous SC repairs preserved. | 3,475 tests / 1,143 subtests, 145 benchmarks, 20 legacy; 6,000 expected replay outcomes and Level A 45/45. Five-packet native screen 3/5. | Final fixed-image 51-case text/MuJoCo cohort stops at case four: 1/4 mechanical, 1/4 semantic, 47 unrun; safe idle retained. All 10 SC calls stop normally, max 678 tokens. Direction, whole-resource outcome/satisfaction, UMI decomposition and SC promises remain wrong. | Development only; full Qualification remains open. Aggregate semantic non-regression is not established. Bounded engineering pass ends for the owner's personal check; further optimization/training awaits their next direction. |

[Checkpoint](../DEVELOPMENT_CHECKPOINT.md) and [handoff](../HANDOFF.md) retain exact
I/O, image identity, commands and evidence in
`.chromie/acceptance/necessary-engineering-20260915/`. Final evidence is injected
text and simulation, not physical resource acquisition. The current Agent is rebuilt.

## Qualification repair — 2026-09-15 (previous pass)

Microphone/ASR remain closed by owner-reported personal acceptance. Earlier
sections retain historical evidence and are superseded by this row.

| Implementation | Automated verification | Target validation | Release readiness |
| --- | --- | --- | --- |
| General SC native completion, question-kind, immutable identity and full raw Schema checks; delivery-ledger projection; Fast disposition/timing/shared Work bounds and whole-outcome selection; retired UMI wording descriptions corrected to SC. No phrase rules, model weights/budget changes or second semantic repair call. | Canonical 3,449 tests / 1,143 subtests, 145 benchmarks, 20 legacy; 6,000 replays and Level A 45/45 pass. SC native screens 10/10 and 12/12 reviewed passes. | Final verified Agent full 51-case text/MuJoCo aggregate stops at case four: 3/4 mechanical, 2/4 semantic, 47 unrun. All ten SC calls complete (max 654 tokens); original compound, parallel action and simulated delivery reach final speech. UMI collapses walking/singing; Fast picks wrong mode; SC premature promise/question remains. | Development only; qualification and fine-tuning readiness remain open. Earlier directional variation, unrun coverage, references/hidden families and #24/#32 are not closed by local passes. Microphone/ASR do not block this work. |

[Checkpoint](../DEVELOPMENT_CHECKPOINT.md) and [handoff](../HANDOFF.md) own exact
module I/O, identities, safe-idle state and commands. Evidence:
`.chromie/acceptance/qualification-closure-20260915/`. Previous queued-speech and
pending-Need review mistakes are explicitly corrected there; no candidate or
frozen expected answer was changed. Final delivery evidence is a scripted
simulation mock, not physical resource acquisition.

## SC completion repair — 2026-09-15

Microphone/ASR remain closed by owner-reported personal acceptance.

| Implementation | Automated verification | Target validation | Release readiness |
| --- | --- | --- | --- |
| Existing SC native Schema presents finite decision/Need accounting before acts; non-Situation Memory proposals excluded consistently with Host. Same prompt, weights, budget and multi-act contract. | Canonical 3,414 tests / 1,141 subtests, 145 benchmarks, 20 legacy; 6,000 replays and Level A 45/45 pass. Native 10/10 mechanical passes; original repeated-ID truncation becomes one complete act/747 tokens. Semantic screen only 5/10. | Rebuilt Agent verified. Original Agent replay completes silently, leaving its Need unresolved. Full 51-case injected-text/MuJoCo cohort stops at first Fast result contradiction: 0/1, 50 unrun; post-completion SC not invoked. Safe idle retained. | Development only. Targeted completion repair has empirical support; fresh-Need silence, queued-speech duplication and Fast result consistency remain open. No fine-tuning/release promotion. |

[Checkpoint](../DEVELOPMENT_CHECKPOINT.md) and [handoff](../HANDOFF.md) retain exact
workflow, identities, limits and resume commands. Evidence:
`.chromie/acceptance/sc-completion-20260915/`; earlier sections are historical.

## Engineering qualification — 2026-09-15

Microphone and ASR: **accepted by the owner after personal testing**, reported
2026-09-15; closed for the current work. They are not a pending prerequisite for
engineering/fine-tuning preparation. The automated failure below used injected
text and bypassed both components; model/Runtime qualification remains separate.

| Implementation | Automated verification | Target validation | Release readiness |
| --- | --- | --- | --- |
| Uncommitted general repairs: whole-request Planner budget admission, compact Fast JSON, SC context ownership projection, evidence-bound completed Work ordering and native SC decision-state invariants. Model weights and semantic prompts unchanged; no case rules. | Canonical 3,402 tests / 1,141 subtests, 145 benchmarks, 20 legacy; full 6,000 frozen replays with unchanged source and Level A 45/45 pass. SC native decision-state contrasts 14/14; these establish only their mechanical contract. | Current Agent rebuilt and source verified. Full 51-case simulator/text aggregate stopped after first case: 0/1, 50 unrun. Actions completed safely; SC repeated an Activity ID and exhausted its 1,024-token output cap. No physical-robot proof. | Development only; fine-tuning/release readiness remains false. SC primary completion, broader native coverage, independent references/hidden families and #24/#32 remain open. |

[Checkpoint](../DEVELOPMENT_CHECKPOINT.md) and [handoff](../HANDOFF.md) own exact
revision identities, module I/O, failed experiments, retained evidence, safe-idle
state and resume commands. Evidence root:
`.chromie/acceptance/engineering-readiness-20260915/`. Earlier sections are historical.

## SC integration — 2026-09-15

| Implementation | Automated verification | Target validation | Release readiness |
| --- | --- | --- | --- |
| Newest upstream SC/Work separation, priority scheduling and execution lanes preserved. Local catalog, Schema/DTO, failure containment/evidence and paired resource mappings integrated; fetch-before-development guidance added. | Canonical 3,382 tests / 1,139 subtests, 145 benchmarks and 20 legacy pass. Full 6,000 SC-aware replay and Level A 45/45 pass. Provider 798 / two skips, body 165, task 147 plus governance/compile/manifest pass. | Previous Qwen/native evidence is pre-SC, not current-revision proof. Local service images are not rebuilt by committing source; no new native SC or physical claim. | Development only; fine-tuning readiness false. Reference review, hidden-family evaluation and #24/#32 target closure remain open. |

## Frozen model comparison — 2026-09-14

| Implementation | Automated verification | Target validation | Release readiness |
|---|---|---|---|
| Owner-authorized official Qwen3.5-9B versus Gemma-4-12B-it experiment completed; semantic source/config unchanged; single Gemma and operator text Host restored. | Same 44 requests per model, online FP8/non-thinking. Schema 44/44 each; DTO/Host 41/44 Gemma and 40/44 Qwen. Reviewed Fast stage 3/8 versus 1/8; GA stage 4/6 versus 5/6. | Isolated native inference only, with bounded reconstructed Host inputs. Qwen request medians about 38%–41% lower but wrong direction and incomplete-work coverage remain. No SC, Deep, whole-runtime or physical proof. | Neither model qualified by this screen; no Qwen promotion. Existing semantic and #24/#32 blockers remain. |

Artifacts: `.chromie/acceptance/qwen9b-comparison-20260914/`, including all 88
reviewed responses and paired input hashes. GA stage results preserve upstream
WHAT even where defective; they are not end-to-end passes. UMI strict-oracle results
contain known lexical/span issues and are not semantic accuracy. A harness-only
constructor error was corrected by common offline revalidation without rerunning
inference. Checkpoint/handoff own exact model/runtime identities and resume state.

## Failed-case root-cause follow-up — 2026-09-14

| Implementation | Automated verification | Target validation | Release readiness |
|---|---|---|---|
| Weather identity and early-result handoff, SC evidence ownership, Fast argument ordering, provider argument declarations and concurrent catalog publication repaired; text Host restored. | Canonical: 3,303 tests / 886 subtests, 145 benchmarks, 20 legacy tests; 6,000 workflows and 45 Level A cases pass. Paired Soridormi: 790 passed / 2 skipped. | Native focused right-turn and weather regressions pass 2/2 after manual review. Cold-start catalog complete; compound Plan still reverses left/right. Full 51-case aggregate stopped during first case after simulator safe idle: no completed summary, 1 interrupted, 50 unrun. No physical proof. | Development only. UMI decomposition, GA resource classification, Fast semantic coverage and signed direction remain blockers; #24/#32 open. |

Current evidence: `.chromie/acceptance/failed-case-repair-20260914/`.
Checkpoint/handoff retain the module I/O, exact identities, failed experiments, full
cohort interruption, focused evidence and operator state. No case-specific prompt or
workflow rules, extra model judge or model replacement were added. Earlier sections
retain historical evidence; they do not override these current qualification limits.

## Scheduler alignment follow-up — 2026-09-14

Vocal and Activity now have separate waiting queues and capacity guarantees under
one resource/safety arbiter. SC's anchored modalities enter Runtime together;
prepared-start adapters coordinate Host PCM readiness and Soridormi preflight,
with independent terminal release and fail-soft optional expression.

| Implementation | Automated verification | Target validation | Release readiness |
|---|---|---|---|
| Separate lane admission, exact prepared groups, SC materialization and terminal ledger implemented; operator Host restored. | Canonical: 3,295 tests / 876 subtests, 145 benchmarks, 20 legacy tests; 6,000 workflows and 45 Level A cases pass. | Bound controlled speech+blink completes through real TTS/discarded PCM and simulator with a common release and safe idle. Native aggregate: six failures, seventh interrupted, 44 unrun. No physical proof. | Development only. UMI/Planner Goal coverage, parameter grounding, weather entity resolution and acceptance SC projection remain unresolved; #24/#32 are open. |

Current evidence: `.chromie/acceptance/lane-coordination-20260914/`.
Prepared synchronization currently covers speech and a single Soridormi plan;
unsupported compound preparation fails closed. Common Host release does not prove
identical physical onset or atomic rollback. Checkpoint/handoff own exact module
workflows, identities, limitations and restored operator state. Following entries
retain prior evidence rather than claiming current native qualification.

## SC Runtime handoff follow-up — 2026-09-14

Independent SC verbal/nonverbal results now retain their exact source snapshot
through existing Runtime admission. Source-turn correlation preserves early speech
across Goal binding, expression terminal results return to the ledger, and the
Soridormi provider recognizes SC's reviewed auxiliary ownership while preserving
confirmation and safety requirements. No new model/semantic authority was added.

| Implementation | Automated verification | Target validation | Release readiness |
|---|---|---|---|
| SC handoff, correlation, terminal feedback and Soridormi source-owner repair implemented; operator text Host restored. | Final canonical: 3,284 tests / 868 subtests, 145 benchmarks, 20 legacy tests; 6,000 workflows and 45 Level A cases pass. | Controlled SC blink completes through real Runtime and deployed simulator, with terminal ledger and safe idle. Native aggregate: 0/3 completed cases pass; fourth stops on UMI source validation, 47 unrun. Both weather results delivered in about 83–84 s; early speech is now visible but greetings still repeat. No physical proof. | Development only; early-act/communication-Need linkage, model/Planner coverage, latency and #24/#32 remain open. |

Current evidence: `.chromie/acceptance/sc-runtime-handoff-20260914/`;
checkpoint/handoff contain actual module I/O, runtime identity, retained failures,
operator state and resume instructions. The following single-engine entries retain
preceding evidence, not a claim that the current full live cohort passes.

## Single-engine priority scheduling — 2026-09-14

The owner selected one resident Gemma 12B SGLang instance after the dual-engine
resource probes. SC, UMI, GA and Planner share weights but keep independent context
and semantic authority. SC > UMI > GA > Fast Planner priority is implemented without
adding an inference service, model, environment key or compatibility path. The
Qwen/Gemma dual-instance and Qwen prompt/schema experiments are retained only as
unqualified evidence; their configuration and semantic edits were withdrawn.

The prior repairs were rebuilt for an immutable baseline. The live must-pass cohort was
stopped on SC HTTP 500 after 12 completed cases (three mechanical passes); case 13 was
interrupted. Every completed case was inspected. Model/plan coverage and silence failures
remain; two SC result reentries failed at estimated prompt-budget checks before inference.
A retained focused replay reproduces that boundary. The unchanged complete packet needs
53,132 actual tokens including output/margin, versus 65,536 available, although the
character estimate rejects it. SGLang client preflight now verifies estimated overflows
with the serving tokenizer, preserving all input and failing closed if verification fails.
The original packet is retained even for a preflight failure; SC reports typed provider
unavailability instead of an unhandled exception. No second semantic invocation is added.

| Implementation | Automated verification | Target validation | Release readiness |
|---|---|---|---|
| Single-engine priorities, exact budget verification and existing SC decoder invariants implemented; packaged Agent and text Host deployed with verified source. | Canonical gate: 3,274 tests / 860 subtests, 145 benchmarks, 20 legacy tests pass. All 6,000 frozen workflows and 45 Level A cases pass. | Native Gemma priority preemption/resumption proved; exact budget replay passes. SC cohort 12/13; weather output truncates. Current live aggregate: 0/3 completed cases pass, fourth stopped on UMI binding validation; 47 unrun. Milk plan omitted acquisition/delivery but executed a walk in simulation. Both weather lookups/final replies complete in 78–83 s, with duplicate greetings. No physical proof. | Development only; semantic stability, latency and #24/#32 closure remain open. |

Current artifacts: `.chromie/acceptance/dual-inference-20260914/`. Checkpoint/handoff
own exact service state and resume commands. Earlier paragraphs below are historical
repair evidence, not the present operator-Host or deployment state.

## Social Cognition migration

**Updated:** 2026-09-14. The owner-authorized
[interaction-planning responsibility](PROJECT_CHARTER.md#social-cognition--accepted-target-2026-09-14)
is implemented on the maintained ordinary-turn, result and trusted Situation
paths. SC and Work Planner share existing state and retain distinct authority.

| Implementation | Automated verification | Target validation | Release readiness |
|---|---|---|---|
| Source-complete: shared SC transaction, independent UMI fan-out, word-free Work/communication needs, exact confirmation/order joins, delivery-qualified dialogue, cancellation/freshness, trusted environment initiative and qualified optional expression. Retired presentation and executable Planner-wording paths removed. | Canonical `canonical-sc-closed.log` exits 0: 3,245 tests / 820 subtests, 145 benchmarks and 20 legacy tests pass; pinned static, policy, ownership, config and docs checks pass. Strict final 6,000 workflows and all 45 Level A scenarios pass. | Earlier native SC 12/12 and Work 8/8 pass Schema/DTO/Host plus implementer semantic review; current production packets match those exact native packets and recorded replies replay successfully. A later fresh native attempt failed to connect, with zero outputs. No current deployed full-chain, contention/latency or physical proof. | Implementation ready for review; development only. Current-target deployment and existing #24/#32 evidence closure remain open. Owner-authorized Git delivery; no service restart/deployment performed. |

Latest GA/Host follow-up on 2026-09-14: the user loaded the preceding fixes and
SC successfully acknowledged a weather request. GA failed a different existing
source-status invariant; Host then omitted both the failure notice and terminal
dispatch because early speech existed. Local source repairs use explicit source
decoder alternatives and ordered terminal failure dispatch. Four frozen native
requests pass Schema/DTO/Host after repair; focused completion/silence tests pass.
Canonical gate passes 3,262 tests / 849 subtests, 145 benchmarks and 20 legacy tests;
all 6,000 frozen workflows and 45 Level A scenarios pass. The operator Host remains active;
independent headless deployment/aggregate proof and response latency are unqualified.
Exact current evidence and resume state are in checkpoint/handoff.

Earlier SC/GA follow-up on 2026-09-14: the newly deployed user turn exposed two decoder
contract gaps (SC progress kind and GA location type), plus omitted SC failure
telemetry. Local source repairs pass the two original native-role transactions,
the paired frozen 12-case SC cohort and 45 Level A cases. These are bounded
transaction checks: operator-Host pause/rebuild permission and independent
headless whole-turn/live-cohort validation remain pending. Exact evidence and
failed iterations are retained in the latest checkpoint/handoff; no deployed
completion or rapid-response improvement is claimed.

Deployment follow-up on 2026-09-14 (source baseline `ec4a5c26`, local repair):
a reported SC 404 and retired stream frame were traced to a reused old Agent
image. Startup now verifies packaged Agent source using the same identity owner
as closed-loop qualification. The user's subsequent `--build` produced matching
Host/container source and the current SC API. An observed `hello` turn completed
through SC without that failure, but first playback took 32.04 s and total time
34.84 s; rapid-response and full live-cohort validation remain open. This is
user-initiated runtime-log evidence, not automated exact replay or physical audio
qualification. Repair evidence, checks and resume details are in the current
[checkpoint](../DEVELOPMENT_CHECKPOINT.md) and [handoff](../HANDOFF.md). The earlier
“no restart/deployment” statement above applies to the original Git delivery.

Delivery is from `main` to `origin/main`, with pre-delivery base
`d5a7985ec74b02cd01c11b0d538fca7ae13a3498`. SC receives shared history,
Memory/Mind, Goals and task/Work/Evidence state. It may speak, ask, select an
eligible expression or remain silent. Trusted environment initiative does not
require synthetic UMI or a task Goal. Required needs and communication ordering
remain exact; optional SC does not block independent Work. Only actual correlated
completed playback enters heard dialogue or speech completion. Soridormi retains
embodied execution and safety ownership.

The final strict aggregate (`workflow-sc-closed/`) retains unchanged source and
all 6,000 declared outcomes: 1,400 successful workflows, 1,800 observed state/fault/
permission outcomes, 2,580 expected rejections and 220 safe nonexecuting replies.
These are 60 authored contrast families with controlled providers and scripted SC,
not 6,000 independent native inferences. Expected outcomes were preserved during
explicit request recapture, then frozen and strictly replayed; no replay hook
substitutes candidate decisions or updates expected requests. Existing splits and
training-ineligible status remain.

Native evidence root is
`.chromie/acceptance/social-cognition-mainline-20260914/`:
`native-final-sc/` and `native-work-roles-complete-order/` retain actual packets,
raw outputs, complete Schema/DTO/Host results and per-case semantic adjudication.
The Work corpus covers greeting, grounded numeric action, precise weather period,
unsupported capability and both communication/action orders. The SC corpus covers
bilingual conversation, missing-input/confirmation needs, independent failure,
trusted arrival, completed/interrupted speech and scheduled/running distinctions.
Native upstream inputs/catalog are controlled; expression execution is qualified
by controlled Runtime tests rather than the empty-catalog native SC cohort.
`recorded-sc-final/` and `recorded-work-final/` prove exact current-packet equality
and successful replay; they are not new native inference.

A subsequent native availability attempt (`native-sc-retired/`) retained 12
connection errors and zero model outputs. Read-only `docker ps` then showed no
running containers; the cause of the stop is unknown and no restart was attempted.
Before that, SGLang 0.5.19 / `chromie-gemma4-12b` was observed with higher-first
priority scheduling, two running-request slots and preemption threshold 10.
That earlier configuration used SC foreground/deep priorities 400/100 and Planner 300. No speedup,
starvation prevention, paired contention or audible latency result follows from
that configuration. Isolated earlier SC calls were roughly 2–5 seconds, excluding
UMI, TTS and playback. Live acceptance now reads SC decisions and completed
playback, with separate decision and decision-to-playback intervals; silence or
missing SC output cannot satisfy a speaking-latency bound.

The [source inventory](COGNITIVE_TURN_LOOP.md#source-migration-inventory),
[checkpoint](../DEVELOPMENT_CHECKPOINT.md) and [handoff](../HANDOFF.md) retain
exact evidence, root-cause workflow, remaining target work and resume commands.
No new document, environment variable or service was introduced; current Markdown
and core-reading counts remain 102 and 15. Earlier text-console work remains
preserved: separate dialogue terminal, ASR bypass, Soridormi retained, backend logs
in the startup terminal.

## Existing implementation and retained qualification

**Current focus:** native #24/#32 qualification and bounded #67 distance containment.
Pre-delivery base `d7c7f277`; resume from the latest commit containing both handoffs.
The owner authorized continued fixes, reports, commit/push and solved-Issue closure.
#67 closes with delivery; #24/#32 remain open. No LoRA training or profile promotion.

| Implementation | Automated verification | Target validation | Release readiness |
| --- | --- | --- | --- |
| Existing UMI duration scalar guard now covers distance; invented/source-translated strings and non-scalars reject. Production prompts/Schema unchanged. | Canonical 3,217 tests / 818 subtests, 145 benchmarks, 20 legacy pass. UMI focused 91 / 115. Level A 45/45. Full unchanged 6,000 replay passes: 1,400 workflows, 1,800 state/fault/permission outcomes, 2,580 rejections, 220 safe nonexecuting replies. | Four 44-case native UMI cohorts / 313 calls remain unqualified. Rebuilt Agent matches 113 source files. Current-profile text/MuJoCo aggregate incomplete: 2 failures, 1 interrupted, 48 unrun. Safe idle observed; owned simulator/MCP stopped. | Development only. #24/#32 open; no native model, streaming target, training-data or physical promotion. |

The native ordering experiments are rejected. The patched production-order rerun
returns the same 71 raw JSON replies as baseline; the unsupported distance now
rejects. Mechanical containment does not certify correct meaning. Revalidating all
242 original baseline/experimental replies rejects exactly six distance violations
and leaves the other 236 admission results unchanged. Full workflow/module I/O and
remaining live failures are in the [audit](../ARCHITECTURE_AUDIT.md#native-umi-continuation-and-distance-containment--243267).
The live identity is explicitly dirty-source diagnostic evidence. Source/profile
identity, matching current interactive budgets, raw late replies after cancellation,
one stop bundle and no-physical-evidence limits are retained in the handoffs.

### Prior 6,000-case workflow audit — d7c7f277

#60 was a contract representability gap: the simulator already returned the authored
`ready_at`, but the UMI Schema/Host rejected it. Primary UMI now authors exact temporal
WHAT and preserves source-time provenance; GA conserves it and Planner owns waiting.
The trusted Gateway receipt anchors elapsed time, not user-local timezone. Missing
calendar/timezone meaning stays unresolved. Tests start with a new request and prove
waiting, restart, no early action, scoped single wake and exact controlled execution.
Separate prior-Goal timers, semantic cancellation and terminal-before-due fixtures remain.

#66's raw Schema rejected empty/absent/foreign single-Goal maps while Host validation
allowed them. The shared validator now requires exact Goal key coverage for either
tier before adaptation. The initial full strict baseline retained 100 empty-map
failures; a later focused contrast retained 40 absent-map failures after the partial
repair. Both variants pass the final rejection oracle. Original errors, reference
corrections and qualification limits remain in the [audit](../ARCHITECTURE_AUDIT.md#broader-workflow-audit--606566).

The current-task GPT-6 Astra references are 60 authored contrasts expanded across
four actions, five values and five language forms, not 6,000 independent inferences.
Review is non-independent and all outputs are training-ineligible. The 3,600/1,200/1,200
splits keep action/value contrast groups together, not unseen semantic families.
One-role candidate mode sends only actual requests; uncovered continuations stop for
separate review. No automatic reference substitution or extra semantic reviewer.

The driver supplies initial admission/scheduling, receipt/clock/UUID facts, controlled
provider observations and local speech receipts. Coverage includes real UMI depth,
GA conservation, Fast/Deep transactions, conditional result re-entry, resource
conflict rejection and Runtime authorization. It does not cover autonomous initial
scheduling, Fast-to-Deep delegation, native streaming, attention/reflection/skill
selection, full Gateway/audio, timeout expiry, confirmation dialogue interpretation,
live registry/service compatibility or embodied execution. Timeout status and one
terminal-Goal state are explicitly injected facts, not proofs of their producers.

Use [benchmark commands](../benchmarks/README.md#offline-workflow-replay), the
[checkpoint](../DEVELOPMENT_CHECKPOINT.md) and [handoff](../HANDOFF.md) for final gates,
identities, archive and resume instructions. No new current Markdown owner,
environment variable, profile or architecture layer: 102 current / 15 core-path
documents. Previous native UMI work (226 executions/254 calls, no qualified repair)
and the preceding 51-case live result (1 failure, 1 startup interrupted, 49 unrun)
remain historical evidence; the current continuation is described above.

### Prior remaining-Issue delivery — 191083dc

The preceding delivery completed the owner-authorized remaining-Issue fixes and retained
failed qualification under #24, #32 and #35. The owner authorized project decisions,
implementation, normal commit/push and closure of solved main-delivered Issues.
Older per-iteration approval and budget statements below are historical.

The current patch rejects lossy UMI preprocessing, preserves sentence-final decimal
provenance, and replaces tagged Fast output with one native structured JSON stream.
Rejected or cancelled streams close promptly. Original provider responses are retained
separately from parsed replay, including exact GA call correlation. Weather information
bindings are covered through GA and Planner. Charter/interface ownership, deployment
concurrency limits and PSM-6/8 source status are reconciled.

| Implementation | Automated verification | Target validation | Release readiness |
| --- | --- | --- | --- |
| UMI/provenance, native Fast streaming, provider lifecycle/evidence and #46–#48 documentation corrections implemented. Earlier independent Planner tasks, scoped Work and Memory projections remain. | Final source gate: 2,480 tests/771 subtests,145 benchmarks,20 legacy tests; policy/static/config/docs and ownership pass. Level A:30/30 distinct cases. Frozen Fast: 204/204 Schema/Host and assisted semantic review. Deep: 40/40 Schema,39/40 Host,35/40 frozen hard passes; all five failures retained after review. | Unqualified. Three local profiles and a fourth UMI-only candidate retain semantic failures. Final rebuilt-Agent 51-case preview stops at UMI integrity:1 complete failure, 1 partial startup,49 unrun. Native Fast has2/8 Host acceptances per local model. No current physical microphone, audible speaker or robot proof. | Development only; no model profile or target/release promotion. |

Fast/Deep offline results use gpt-5.6-sol/high as a Codex surrogate, one invocation per
case, and non-independent assisted review. Deep exposes a read-first satisfaction
contract conflict plus contradictory cancellation scope/capability projection and
oracle ambiguity. These are unresolved #35 failures, not evidence that the cohort
passed. The source corpus remains unchanged. Native-provider comparisons retain
separate raw Schema, Host and semantic results; they do not inherit surrogate passes.
The development Agent was rebuilt and its deployed source verified. Production model
profile defaults remain unchanged. #24 and #32 still require successful role/profile,
stream integrity, responsiveness and live evidence.

Evidence is private under `.chromie/acceptance/open-issue-closure-20260911/`.
The [checkpoint](../DEVELOPMENT_CHECKPOINT.md) and [handoff](https://github.com/TimeTreker/chromie/blob/f5522f874671ff1b8bd42553a22793eaad0b1f51/HANDOFF.md) own exact
workflow diagnoses, identities, artifact paths and resume commands. Source/audit Issues
#28, #40, #46–#48 and index #36 may close after remote main verification; #24, #32 and
#35 remain open. Historical counts below describe their own revisions only.

### Pre-merge evidence (not merged-revision qualification)

**Pre-merge branch focus:** Goal-driven single-authority architecture, Issue #35. The first requested batch was pushed as 9e3d3971; all 18 further RTX 4090 Laptop iterations 29–46 are complete and unqualified. Final source retains31/32 UMI projection repairs and 43 GA retry eligibility. Branch codex/ga-request-format, pre-delivery base9e3d3971; Soridormi codex/turn-count at 284273bc. Fixed Qwen3.5:4b Q4_K_M/Ollama. Budget exhausted; no further candidate iteration, model substitution or main promotion. Speech-outcome amendment implemented; separate tagged-stream wire amendment pending/unimplemented.

| Implementation | Automated verification | Target validation | Release readiness |
| --- | --- | --- | --- |
| Existing delivered speech/provenance/Schema/history repairs remain. UMI omits four root correlation labels and preserves configured robotic identity; GA permits one structural-only repair and rejects semantic/mixed errors after one call. | Exact final pre-doc tree equals passing43:2366 tests/601 subtests/140 benchmarks/20 legacy; pinned gates pass. Focused 165/120; LevelA8/8; frozen GA 11/11. Final docs checks retained separately. | Unqualified. UMI 46: 44 cases / 61 calls; 61 complete Schema-valid / 60 Host-admitted; 5 mechanical / 3 reviewed qualified. Identical32 packets still vary. Earlier unchanged Fast 2/8, Deep speech7/16/history4/12. Final 51live: 1 complete failure, 1 partial case with one retained UMI response and unproven Host/terminal outcome, 49 unrun; 2 retained calls reviewed, 2 Schema-valid, zero qualified. Host blocks Work. | Development only; no main promotion. Current-revision supervised voice/default target-evidence closure open. No physical microphone/audible speaker/robot or executed-motion proof. |

Correct source projection and Schema validity do not establish correct meaning.
UMI still merges effects, invents bindings/uncertainty and confuses unknown facts with
speech; tagged Fast can return invalid or repeated unrelated Activities. Deep history
and independent-response failures remain. Playback-generation contamination remains
open after the38 experiment was unselected. Rejected41's failed local gate is retained;
final source did not weaken its test. All 88final UMI packets match32 byte for byte, so
repeat differences cannot be credited to unchanged UMI code. The
[checkpoint](../DEVELOPMENT_CHECKPOINT.md) owns the current resume boundary; the
[handoff](https://github.com/TimeTreker/chromie/blob/f5522f874671ff1b8bd42553a22793eaad0b1f51/HANDOFF.md) owns all 18 iterations, workflows, actual evidence, commands
and identities. Text-preview failure containment is not robot qualification.

Previous RTX 5090 evidence (2026-09-10; different model/provider and local tree): Goal-driven single-authority architecture, Issue #35, fixed RTX 5090 / Gemma4-12B. Explicit provider argument realizations now enforce minimum argument presence in Fast advance and canonical Fast/Deep validation; gaze duration is declared instead of silently using its default. Canonical Fast single/multiple-Goal decoder schemas now expose existing intersection shapes, closing a native decoder omission. Two focused MuJoCo episodes complete exact gaze2/blink2 and gaze3 with valid primary Fast result DTOs and zero Deep calls. Canonical gates pass2331 tests /437 subtests,140 benchmarks,20 legacy tests; Soridormi789 passed /2 skipped. Final stable51-case preview:27 mechanical /19 reviewed acceptable,154 call digests intact. UMI/GA/Planner semantic defects, headless speech and supervised target-evidence gaps remain; no model-only or main-promotion claim. Checkpoint/handoff own exact workflows, paired commits and evidence.
Earlier different-model comparison: three canary trials showed lower SGLang foreground latency, but model/precision/topology differed. The 51-case preview produced zero reviewer-qualified complete transactions on either deployment. The sole SGLang mechanical pass dropped GA bindings and admitted unresolved UMI actor meaning downstream; preview prevented dispatch. See the [checkpoint](../DEVELOPMENT_CHECKPOINT.md) and [handoff](https://github.com/TimeTreker/chromie/blob/f5522f874671ff1b8bd42553a22793eaad0b1f51/HANDOFF.md) for retained evidence. Error containment is not successful behavior.
## 2026-09-06 transaction-fidelity source closure
The archive audit did not reopen the authority architecture; it found six implementation mismatches at the existing GA/Fast/Runtime boundaries. The current worktree closes them as follows:
- **A01 / source-closed — GA semantic repair:** the live GA normalization chain no longer deletes ungrounded resource-query locations or reclassifies model-authored semantic binding types before acceptance. Semantic/grounding conflicts remain visible to fail-closed validation; repository policy guards reject reconnecting those repair calls to the live transaction.
- **A02 / source-closed — Fast re-decision without new state:** streamed `unavailable`/`refused` are legitimate terminal Fast outcomes and can materialize directly as canonical limitation/refusal outcomes. A second Fast pass now requires `canonical_fast_revision_reason`, i.e. a material canonical Goal/Work state change.
- **A03 / source-closed — early observable speech validation:** request-specific commit checks run before `PresentationCommit` is yielded. Unresolved UMI meaning and typed cross-Responsibility ordering/concurrency constraints that prohibit early delivery cannot reach Host vocal realization first and fail only at the terminal frame.
- **A04 / source-closed — incomplete main-test collection:** `scripts/run_tests.sh` now executes `python -m pytest -q tests`. Previously hidden top-level pytest tests were migrated to the maintained architecture, including successful sibling batch-closure behavior and current prompt APIs. Level-A `multi_goal_daily_life` now exercises the streamed Fast fixture directly rather than an `unavailable -> /fast-plan` sentinel.
- **A05 / source-closed — lossful authoritative GA input:** both active GA prompt paths use a required lossless UMI Responsibility projection with an explicit 16K character transaction budget. If authoritative input exceeds that bound, prompt construction fails explicitly rather than silently dropping a list suffix; optional/background context remains bounded separately.
- **A06 / source-closed — committed GA truth omitted on downstream failure:** failure cleanup consumes a completed `_GoalAssociationStageResult` and restores its association, planning context, Situation, Goal-state results, commit stage, and lifecycle facts before the public error resolution is built. A Planner failure therefore does not erase already-established Goal truth.
Focused current-worktree evidence: `tests/test_cognitive_runtime_pr7.py` passes 71 tests plus 2 subtests; `tests/test_prompt_projection.py`, `tests/test_goal_association_pr2.py`, and PR7 together pass 153 tests plus 2 subtests; the migrated prompt/re-entry/API focused set passes 94 tests plus 2 subtests; `multi_goal_daily_life` Level A passes 10/10; one broad pytest partition passes 475 tests plus 50 subtests. A second very large partition exceeded this audit environment's single-command timeout, so no complete canonical-gate pass is claimed here. The next required evidence is a clean checkout with pinned dependencies running the documented full gate and recording the actual pytest collection count.
Corrective order is now: (1) retain a clean revision-bound full source qualification with the new complete test collection; (2) re-run frozen-transaction model/provider qualification on that exact source; (3) then resume live voice/simulator/provider qualification and latency work. No new cognitive authority or product feature is justified by these fixes.

## Approved model-driven cognitive orchestration target — 2026-09-20

Owner-approved architecture now distinguishes model-authored **cognitive orchestration**
from trusted **execution/compute scheduling**. A cognitive model may request GA, SC,
Planner, or a bounded later re-entry when current meaning/state makes that cognition
useful. Runtime validates and schedules those requests under identity, version, dependency,
compute, authorization, confirmation, safety and resource constraints; it must not decide
semantic cognitive need from output modes, keywords, task classes, or fixed routing rules.
The governing principle is progressive cognitive commitment: cognition that is sufficiently
grounded for its own next step should not wait for unrelated cognition. Early reasoning does
not bypass the effect boundary; safe reads may be qualified for pre-GA execution while
effectful Work remains prepared. Later GA/Evidence/Situation changes re-enter Planner over
actual queued/running/completed/cancelled/provisional Work so the model decides the delta.

**Implementation status — Slice 1 implemented in source.** UMI now emits required
`cognitive_requests[]` on the live model wire. Each request names one existing authority
(`goal_association`, `social_cognition`, or `planner`) plus exact Responsibility refs. The
initial Runtime fan-out schedules only those requests; `continuity_scope`/`output_mode` no
longer decide initial Fast activation. Runtime still owns mechanical validation, stale-result
containment, compute/effect admission, authorization, confirmation, resources and provider
execution. The previous terminal-history GA constrained-decoder repair is folded into this
slice as well. Focused source verification covers UMI schema/validation, social-only turns,
mixed social+Work scope, GA decoder conservation and SGLang schema transport.

**Implementation status — Slice 2 implemented in source.** Goal Association now emits its
own bounded downstream `cognitive_requests[]` after continuity resolution. Runtime no longer
infers a second Planner pass from relationship type, Goal replacement, retained Work, or
Planner-scope differences; it validates and schedules only the GA-authored Planner/SC request.
Focused GA/Runtime tests cover retained continuity, new Goal ownership, no-op activation,
and exact Responsibility conservation.

**Implementation status — Slice 3 implemented in source.** Trusted internal state transitions
now enter one narrow `CognitiveActivationDecision` before Goal-bound Planner or Goal-free SC
re-entry. Host supplies only trusted trigger/provenance, exact legal authority set, current
Goal/Responsibility scope, Situation and Work/Evidence snapshot; the Activation model may
request an existing authority or request nothing, but cannot author Goals, Work, wording,
Capabilities, execution or completion truth. Goal-bound re-entry begins with Fast Planner and
lets Planner itself escalate to Deep; Goal-free Situation begins with primary SC and lets SC
request its own deeper pass. `CognitiveOpportunity.recommended_cognition` is no longer used
to select Planner/SC depth. This closes the planned orchestration migration; no Slice 4 is
required. Native model/provider/latency qualification remains open.

## Current architecture

The maintained authority line is:

```text
Person / World
      ↓
Cognitive Gateway
      ↓
User Meaning Interpretation                 WHAT
      ↓
Responsibility
      ├──────────────────────┐
      ↓                      ↓
Planner                  Goal Association
fast / deep passes       Goal continuity
      ↓                      ↓
Plan / Activities        Canonical Goals
  + optional auxiliary Activities
      └──────────┬───────────┘
                 ↓
       Trusted Capability Runtime
                 ↓
              Provider
                 ↓
       Async Runtime Event             what happened
                 ↓
        Host-bound Evidence            what is true
                 ↓
Responsibility + Goal + Situation + actual Work + Evidence
                 ↓
        CognitiveOpportunity           ephemeral readiness trigger
                 ↓
              Planner                  what to do now
                 ↓
       0..N Activity changes
       or no new Activity
```

The authoritative definitions live in `docs/PROJECT_CHARTER.md`. In particular:

- User Meaning Interpretation owns provider-neutral Responsibility meaning, not Work or speech.
- Goal Association owns canonical Goal identity and continuity, not replanning.
- Planner is one HOW authority; fast and deep are cognition passes of that same owner.
- SC owns ordinary Communicative Acts and exact wording.
- The target cognitive-orchestration contract lets models request which existing cognitive
  authorities should work next; Runtime owns mechanical scheduling/admission, not semantic
  routing. This target is not yet fully implemented.
- The same primary SC result may own bounded `auxiliary_activities[]`; these remain
  interaction expression, never Goal-owned Work or task-completion Evidence.
- Trusted Capability Runtime and Providers own effect realization/lifecycle, not Goal
  interpretation.
- Progressive cognitive commitment permits independent grounded cognition to advance without
  waiting for unrelated branches; effectful execution still obeys canonical/safety boundaries.
- Runtime events report what happened. Host-correlated Evidence records what is true.
- `CognitiveOpportunity` is an ephemeral readiness carrier, not Goal/Evidence/Situation/response/execution truth. Goal-bound readiness may re-enter Planner; exact trusted Goal-free Situation readiness may enter the shared SC transaction; either path may do nothing.
- Auxiliary-only events cannot create a `CognitiveOpportunity`; Goal-free readiness requires independently trusted primary Situation/source provenance.
- Existing-Work comparison, reuse, cancellation, replacement, or supplementation are
  Planner operations, not a mandatory Work-Reconciliation stage.

The 2026-08-22 source audit found live Host semantic-authority leaks; Phase 1A-1D now
close the verified confirmation, cancellation, ordinary result-meaning, and body-recovery
source paths. Confirmation owns authorization facts only; named cancellation returns typed
Evidence to Planner; deterministic `status -> sentence` outcome composition is removed; and
recoverable body failure exposes bounded provider retryability facts without Host retry
planning. This is **source closure**, not target qualification: current-revision
bilingual/provider/simulator/live evidence is still required before `SPEECH-OWNER-001` or
human-facing behavior is considered qualified.

## Current implementation and verification state

Charter principles 30–31 now require semantic grounding/coverage evidence to be
authored in each authority's primary result and prohibit same-authority LLM
reviewer/semantic-repair chains. UMI source now follows that contract: its primary
result carries per-Responsibility source-token evidence, resolved valid meaning uses
one model call, genuine unresolved meaning may delegate once to source-based Deep UMI,
and every invalid primary or Deep DTO fails closed without a same-authority repair.
Goal Association now follows the same single-authority rule: its primary result owns the complete continuity transaction, trusted conservation/grounding checks cannot trigger another semantic model call, and semantic/grounding conflicts remain visible instead of being repaired by the trusted normalization layer. When retained candidates exist, associations and independent
new Goals are non-exclusive collections in that one result, with every accepted UMI
Responsibility conserved exactly once across their union; the obsolete exclusive branch
discriminant is removed. Fast and Deep Planner now also close truth, Goal coverage,
evidence scope, wording, and satisfaction in their primary results; the former
same-owner qualification/coverage calls and dedicated truth-model role are removed.
The existing frozen `UserTurnEnvelope` now remains the sole stored source of admitted
wording. The current original-turn path also references that same envelope through typed
semantic-owner boundaries: UMI receives the admitted envelope directly, while GA and Planner
resolve the full already-transported envelope from `CognitiveWorkRequest` through one typed
accessor without adding another Work-request wire field. Text/session/language correlation is
validated fail-closed. Their compact model-facing source projections are derived from that same
envelope; trusted Work provenance retains the turn identity, exact original text and digest.
Scoped Planner re-entry may instead carry the previously validated source projection while
keeping `request.text`, Responsibilities, Goals,
Plan, and Evidence restricted to the affected Goal subset. The source is visible for fidelity
and correlation but grants no downstream authority to reinterpret or repair WHAT. Fast `argument_sources` now use closed token spans on the same immutable source instead of
model-retyped quotes. The Fast prompt receives deterministic source tokens, Host validates each
span is inside an owning Responsibility source span, and canonical Plan materialization
dereferences it to the exact source quote. Unknown/reversed/foreign spans fail closed. This
removes transcription bookkeeping without weakening source access or Goal ownership. The owner
also generalized the same anti-loss requirement to accepted semantic outputs. The source now
contains a model-neutral `SemanticArtifactEnvelope` / packet contract: existing artifact ID,
canonical payload SHA-256, existing authority/correlation and immutable parent refs around the
exact typed payload. `CognitiveEvidenceRecorder` always archives immutable envelopes for admitted
UserTurn, UMI and each Responsibility, GA/new Goals, canonical Planner Plans,
SC/Communicative Activities when present, and trusted execution outcomes; exact packets are
retained only when configured text retention permits. Payload mutation fails digest validation.
Execution-outcome envelopes land as terminal history. Phase 1C now carries the same
content-bound refs through the live original-turn path: UserTurn/UMI/Responsibility refs enter the
existing Work-request context; GA/new-Goal refs are appended after continuity; Plan refs are
attached before SC and Capability Runtime; accepted SC/Communicative-Activity refs continue into
interaction/capability metadata; and Cognitive Evidence checks transported refs against archived
packets. The bookkeeping is omitted from model prompts and introduces no new semantic authority
or frozen top-level Work-request field. Envelope-span `argument_sources` materialization is implemented for Fast current-turn Work;
canonical time-condition `source_quote` remains a separate Planner semantic/time contract.
This is source and automated-contract closure, not qualified target behavior. The current
source starts Goal Association and one Fast Planner stream
concurrently from the immutable UMI result. The internal model output is one JSON object
with a complete `presentation_commit` member followed by `terminal_result`. The Agent exposes only a fully parsed typed
`PresentationCommit`, then a terminal frame or typed pre/post-commit failure from the same
model invocation. Raw tokens never reach TTS. Complete validated Work may be prepared
before GA; only available contract-declared side-effect-free safe reads without
confirmation may execute then. Remaining Work requires GA binding and ordinary
Runtime prerequisites. Material Goal/Work changes can trigger a separate Planner call. The accepted commit and terminal
CanonicalPlan carry the same commit identity and cannot duplicate or re-author speech.
The separate post-resolution Social Attention bridge has now been removed:
`PresentationCommit`, terminal Fast output, and canonical Fast/Deep primary outputs own
optional `auxiliary_activities[]` directly under exact primary anchors.
The streaming architecture, early request-scope commit validation, and terminal validation are implemented. The first released `PresentationCommit` is now checked against every request-specific pre-terminal constraint before Host vocal realization can start. This is therefore **not yet complete source/contract closure**; target behavior, audible voice, simulation, and hardware qualification remain separately open.
Core/challenge did not start; release readiness remains development only.

The RTX 4090 Laptop profile now assigns every LLM role to one `qwen3.5:4b` runner.
For the current laptop run, UMI retains 16,384 context / 512 output, GA 32,768 /
2,048, and canonical Fast/Deep 40,960 / 4,096; streamed Fast still applies its
existing 2,048 output clamp. Historical 32K measurements below are separate. Ollama 0.32.14 reports that `qwen35` does not support
parallel requests and creates `n_seq_max=1` even when `OLLAMA_NUM_PARALLEL=2`; the
maintained profile therefore declares one provider slot and one resident model. This
fits beside CosyVoice on the 16 GB laptop GPU, but it cannot realize the architecture's
concurrent GA/Fast inference.

Earlier laptop/provider diagnostics remain unqualified: the August29 Ollama
aggregate passed0/50; isolated vLLM transport checks did not qualify model meaning,
concurrent long decoding delayed TTS, and the subsequent alternate-model screens
promoted no candidate. Simplified RTX5090 prompts and assistant-reference tests
also did not qualify the production transaction. Exact historical counts,
identities, artifacts and prompt hashes now live in the handoff's
[historical provider diagnostics](https://github.com/TimeTreker/chromie/blob/f5522f874671ff1b8bd42553a22793eaad0b1f51/HANDOFF.md#L4000).
They are not current-source or current-model claims.

An assistant-reference audit applied that prompt and each exact decoder schema to all 16 primary UMI manifest cases without an external model/provider call. All 16 passed schema, Host validation, and six semantic dimensions. This proves only strong-reference prompt clarity, not deployed-model qualification: any candidate result measures the combined model + prompt + schema + decoder transaction and cannot alone prove the prompt correct or defective. Runtime contracts remain unchanged; no model was promoted.

A full offline Codex UMI diagnostic exercised all 1,496 bilingual daily-life scenarios on fixed source/prompt identities through five bounded iterations. The selected final target-blind iteration completed 1,496/1,496 calls and generated-schema/production-Host checks; mechanical candidate equality was 835, including 1,496 decomposition, 1,490 output-mode, and 1,474 unresolved matches. A post-hoc one-reviewer, same-model self-audit judged 1,366 raw outputs valid and 130 invalid, recommended no prompt change, and judged only 1,136 assistant-authored references valid. Broader decision-procedure and source-span wording experiments regressed decomposition or semantic quality and were rejected. The current prompt preserves 406/406 explicit digit-plus-unit measurement bindings and exact Goal relationship/`output_mode` in 136/136 continuity scenarios. The separate source-based Deep-UMI diagnostic covered all 68 genuinely unresolved reference cases: 68/68 calls/schema/Host and 55/68 same-model semantic passes, again with no prompt-change recommendation. Because Codex collapses production roles and carries the schema as prompt text, and because the reviewer is the same non-independent model and misread four schema-valid `schema_version` fields, these are diagnostic lower-bound counts rather than provider qualification, independent review, or training approval.

The contract defects found by the call-path audit are now fixed. Primary and Deep UMI no longer have a same-stage repair call; the repository policy checker rejects restoration of those call markers. Measured values retain an exact number-and-unit source/context surface, standalone social acts remain speech Responsibilities, and unfamiliar names become unresolved only when the category/referent choice materially changes WHAT. Charter principle 31 now agrees with runtime: UMI authors `output_mode`, GA preserves it under decoder `const` plus conservation checks, and the Host derives execution projections after validation. The 1,496-case candidate corpus passes generated schema and Host validation with 68 genuine unresolved cases and a pinned 406 digit-measurement-surface count. The final changed-worktree primary and Deep diagnostics are retained under ignored `.chromie/acceptance/model-qualification/` paths; no model/profile was promoted.

The Planner audit is source-closed: Fast and Deep each produce one complete primary result; Deep receives authoritative Goals/context, and Host validation cannot rewrite semantics. The design-derived Fast corpus covers 17 capacities in 51 bilingual supported/boundary contrasts across primary, re-entry, and streaming forms. Fast v33 passed 204/204 process, Schema, Host, and hidden-target checks; its same-model review reports 201 pass, one partial, and two fail, all retained as model-inference findings against already-explicit contracts. Deep v15 passed 40/40 plus 40/40 non-independent semantic review. Codex `gpt-5.6-sol` was fixed as the candidate Planner; no local Qwen/Ollama/vLLM model was used as a Planner proxy. Both corpora remain training-ineligible and do not qualify deployed models, voice, or robot behavior.

The 2026-09-04 RTX 5090 `voice_mujoco` bundle retained two admitted turns that both failed at User Meaning Interpretation after about 5.4 seconds. ASR and Gateway Attention were correct; GA, Planner, and weather handling were never invoked. The earliest wrong boundary was the interactive Agent UMI watchdog, which cancelled a still-running `gemma4:12b` primary transaction. A second latent boundary was the declared but previously unconsumed Host UMI deadline. Interactive modes now use 60000 ms Agent and 65000 ms Host UMI watchdogs, and `AgentClient.interpret_turn()` consumes the dedicated Host value. These values protect transaction completion and do not qualify human-facing latency. The startup launcher also no longer promises a wake-up greeting when startup speech is disabled. Automated wiring evidence passes.

Current-revision RTX 4090 investigation then exposed two additional deployed-path boundaries. Generic Agent semantic roles used Ollama `/api/generate`; with runtime Ollama 0.33.2 and `think:false`, that endpoint emitted no response before the client deadline, while `/api/chat` completed immediately and supported the required structured and streaming outputs. The Agent client and warm-up script now use `/api/chat` with separate system/user messages, and focused transport regressions cover complete, structured, streaming, and non-thinking response enforcement. The old warm-up path had also left `qwen3.5:4b` resident at 16K while GA/Fast requested 32K; the repaired warm-up established a 32K runner and unblocked both roles. No prompt, Schema, DTO, model, profile, semantic authority, or execution policy changed.

After that repair, an exact `你好。` Level-C-preview run reached UMI, GA, and Fast Planner on the deployed `qwen3.5:4b`. UMI correctly produced one greeting speech Responsibility in about 5.50 seconds and GA preserved it in about 6.08 seconds. Fast Planner emitted its validated empty presentation commit about 8.246 seconds after UMI handoff, then incorrectly mapped the speech-only Responsibility to `chromie.clock.local` and proposed `现在的时间是。`; Host validation rejected the terminal Plan before execution. The retained case scored 40 and hard-failed. This is current deployed-model evidence that the transport path now works but the single-slot Qwen Fast transaction is both semantically invalid for the greeting and outside the two-second commit target. The fixed-Codex v33 evidence did not qualify this Qwen profile, so no prompt or model is promoted from the isolated probe.

The subsequent unchanged, directory-discovered RTX 4090 must-pass aggregate hard-passed only 5/51 cases. A non-overlapping primary-failure classification has 5 UMI failures, 2 Goal Association failures, 34 Fast pipeline failures, one additional Fast communicative-coverage failure, one Deep Planner failure, and three deterministic-reflex cases that require non-preview execution evidence; five cases passed. Among the 39 case turns with retained Fast timing, every UMI-handoff-to-commit duration missed the two-second target: 9.795–14.586 seconds, median 12.228 seconds. The aggregate greeting repeated the clock-Capability error with a 10.685-second commit. Semantic review remains pending, runtime identity is incomplete, and the source was dirty, so this is diagnostic Level-C-preview evidence rather than qualification. It is nevertheless sufficient to reject greeting-specific prompt tuning and the current all-Qwen/single-slot profile as a release candidate.
A later supervised device-mode session retained two admitted turns on the same dirty source. Exact `你好。` reached a greeting speech Responsibility, then Fast again emitted `chromie.clock.local` and `现在的时间是。`; the Host rejected that invalid mapping and spoke the fixed failure utterance. A Chongqing-rain request failed earlier because UMI translated the explicit source location `重庆` to `Chongqing`, which the provenance validator rejected before GA, Planner, or weather execution. Both raw model calls terminated normally, so these are distinct deployed-model inference failures rather than transport, timeout, TTS, or fallback-selection defects. The shared fallback makes them sound identical. The same Qwen slot alternated 16K UMI and 32K Fast requests and recorded multi-second provider load durations, a measured latency contributor whose internal Ollama reload mechanism remains unproven. This is diagnostic microphone/speaker evidence, not a formal acceptance or normal-behavior qualification.
| Area | Implementation | Automated verification | Target validation | Release readiness |
|---|---|---|---|---|
| Cognitive Gateway / Attention | Maintained configuration controls Attention Review; deterministic protective reflex remains separate. Disabled or unavailable semantic review fails open without fabricating high-confidence addressedness. | Source and focused contract regressions cover admission, fail-open behavior, temporary addressedness rules, and schema boundaries. | Current-revision open-room microphone behavior still requires live evidence. | Development only. |
| User Meaning Interpretation / Goal Association | UMI owns complete natural-language intentions, requested output modes and per-item source-token evidence. A compound intent may remain one Responsibility. GA owns continuity; Planner owns argument and Activity decomposition. Invalid primary/Deep DTOs fail closed; only genuine unresolved meaning may delegate once to source-based Deep UMI. Trusted code validates mechanics and cannot resegment, source-repair, or call a semantic reviewer. Explicit units remain human-semantic source surfaces. Standalone social acts remain speech Responsibilities and harmless unfamiliar names remain resolved. GA separately owns canonical Goal identity and continuity, preserves UMI `output_mode` under a decoder constant, and may use only its existing Pydantic-only mechanical repair; grounding or conservation rejection is terminal. Candidate-aware GA may associate retained Goals and create independent Goals together, with exact union conservation and no exclusive branch decision. | Focused UMI/GA regressions cover one-call resolved meaning, terminal invalid DTOs, one Deep delegation, units, social acts, name materiality, source evidence, atomic siblings, GA conservation, and policy guards. The 1,496-case candidate corpus passes generated schema and Host validation with 68 genuine unresolved cases and 406 pinned digit-measurement surfaces; it remains ineligible for training and lacks independent semantic review. The selected final target-blind diagnostic completed 1,496/1,496 schema/Host checks and retained 1,366/1,496 non-independent same-model semantic passes with no prompt-change recommendation; the 68-case Deep subset retained 55 semantic passes and the same no-change judgment. The separate 1,500-case GA continuity corpus mechanically validates all references, including 100 mixed association-plus-creation regressions. The relevant Level-A classes pass 12/12. | Current provider/model compatibility remains unqualified. A candidate run binds prompt, schema, decoder transport, profile, and revision; no model/profile was promoted. | Development only. |
| Planner / communication | One Planner authority owns HOW, exact Communicative Activities, Capability choice, args, realization, per-Goal satisfaction, and optional auxiliary social Activities. The model-side `/fast-advance` invocation is one structured JSON stream with exactly two ordered members: `presentation_commit`, then `terminal_result`. The Agent validates those payloads and exposes typed NDJSON: validated `PresentationCommit`, then terminal result or typed failure from that same invocation. GA starts concurrently. Complete validated Work may enter preparation; only contract-declared side-effect-free safe reads without confirmation may execute before GA binding. Remaining Work waits for binding and Runtime prerequisites. Material Goal/Work changes trigger a distinct Planner task. The terminal Fast result and CanonicalPlan reference the same immutable commit. Canonical Communicative Acts retain immediate/pre-action/progress/final delivery phase; mixed Response Projection covers only communicative Goal IDs, and an independent context-grounded final speech Goal may remain ordered after Work without becoming completion evidence for an executable Goal. `CanonicalPlan.auxiliary_activities[]` remains fingerprinted but structurally outside Goal-owned `steps[]`; Runtime validates, executes, or suppresses exact proposals and cannot reselect. The independent Social Attention and separate Fast First Response endpoint/model/config paths are removed. | Focused protocol, Planner, client, Runtime, scenario, and repository-policy tests cover one-call ownership, ordered typed frames, exact commit reference, before/after-commit failure, safe-read admission versus prepared held Work, auxiliary anchor/catalog/Goal isolation, post-primary scheduling, communicative-only mixed-Goal coverage, context-grounded after-Work speech, provenance, cancellation, and terminal Evidence. Historical tagged-stream probes cannot qualify the current ordered JSON wire path. | Current structured-stream provider protocol, semantic quality, accepted-commit latency, TTS first PCM, playback start, complete-Plan latency, commit/terminal consistency under load, GPU residency/contention, target validity, restraint, and live execution require current-revision qualification. | Development only. |
| WorkDAG / DAGEngine | Planner is the sole ordinary semantic author/modifier of revisioned WorkDAG topology. GA changes Goal continuity only. DAGEngine owns acyclicity/contract checks, readiness, bounded parallel dispatch, dependency/blocked/cancellation state, trace, and immutable completed-node inheritance; normal completion advances mechanically while material change returns Evidence to Planner. Provider-local DAGs remain provider internals. | Focused WorkDAG revision tests prove exact `revision + 1`, stable `dag_id`, completed-node immutability and no redispatch; DAGEngine/Planner/capability tests guard removal of `residual_replan` and engine-authored outcome meaning. | Current-model quality of Planner-authored DAG topology and live multi-Goal revision/merge behavior still requires target qualification. | Development only. |
| Async Runtime / Evidence/Situation re-entry | Terminal Runtime events are correlated into Evidence and may create bounded `CognitiveOpportunity` re-entry. Every Planner re-entry now carries an immutable `PlannerReentryScope` with exact trigger, affected Goals, Evidence refs/opportunity, and optional source Plan fingerprint; Fast/Deep prompt projection and decoder Goal sets are restricted to that scope, so closed siblings are not silently reintroduced. `SituationProjection` v3 carries bounded current interpretations plus exact authority-owned source refs. Meaningful live provider progress is the first production trusted Situation ingress: blocked/waiting/degraded/paused/recovering or material phase/member-state transitions become typed `SituationRevisionObservation` input and may raise `situation_revision`; running heartbeats and percentage churn are ignored. Provider Runtime state is explicitly **not Evidence**, so provider-state and restart revalidation no longer fabricate Evidence refs or `post_evidence` speech truth. Restored open Goals retain exact Responsibility provenance and may re-enter from fresh provider truth without replaying the old Plan or fabricating a UserTurn. Structured Goal/Plan-bound `time_condition` state is production-wired to a mechanical wall-clock wake loop and likewise may re-enter with zero Evidence refs. A Situation-digest opportunity is accepted only with the exact validated Situation/source binding and, when Goal-bound, the exact Goal scope. The generic typed Goal-free ingress is implemented, while concrete camera/person/scene/body/environment source adapters remain an **implementation gap**. Planner-authored structured time conditions are part of the canonical Plan: Planner supplies exact Goal/time semantics, while ConversationState adds current Plan identity plus original Responsibility provenance before durable registration. Host never polls the world semantically or parses free-form deadlines into timers. Situation re-entry readiness no longer uses Host domain-value routing: no semantic delta creates no opportunity, source-specific mechanical churn may be filtered below cognition, and every admitted meaningful Situation revision begins with one bounded Fast semantic pass whose owner may remain silent/no-change or escalate when deeper reasoning is actually warranted. | Focused regressions cover exact two-of-three Goal re-entry projection, incremental terminal Evidence, Situation v3 reconstruction/source binding, provider Runtime-state Situation ingress without Evidence promotion, follow-up Work while siblings continue, cancellation/supersession containment, duplicate-execution prevention, missing-provenance rejection, durable restart revalidation, one-shot due-time wake/re-entry, and shutdown cancellation of the long-lived mechanical wake task. | Provider-backed weather/body episodes should be retained on the exact current revision; live blocked/waiting Situation-revision and restart-revalidation episodes still require target qualification. Generic camera/scene/body/environment ingress cannot be qualified until its production source adapters exist; Planner-authored time-condition quality still needs current-model target qualification. | Development only. |
| Memory activation | Existing session/profile Memory remains the sole retained-meaning owner. Prompt selection now uses bounded current-context cues from the latest user turn, open task/Goal context, and discourse focus so an older relevant Memory can outrank unrelated recent entries; recency remains fallback/fill. Selection does not create Evidence, change Goal meaning, authorize effects, or add a retrieval model/vector store. | Focused MemoryStore/ConversationState regressions prove older relevant activation, CJK phrase activation, recent fallback, durable-memory compatibility, and bounded prompt projection. | Current-model usefulness of activated Memory across longer bilingual episodes still requires target qualification. | Development only. |
| Semantic expectations / Active Perception | Canonical executable steps now distinguish ordinary effect Work from `acquire_information` Work and may carry a bounded Planner-authored `expected_outcome`. Information-seeking gaze/tool/body behavior remains normal Capability Work under existing safety/provider authority. On trusted terminal re-entry, the prior expectation is projected beside actual Evidence for the same Planner; Host never treats the expectation as Evidence or performs semantic mismatch inference itself. | Focused contract/re-entry regressions prove non-empty observation expectation for acquisition Work, canonical prompt preservation, and terminal re-entry exposure without Evidence promotion. | Current-model choice of useful observation Work and live expectation-mismatch recovery require target qualification with actual providers. | Development only. |
| Stable Mind / customer personalization | Chromie's factory social identity is a twelve-year-old girl and persistent social individual whose everyday life happens primarily with her family. Family is a relationship/living context rather than a service role or assistant mode. That is not a biological-human claim; truthful robotic embodiment remains available when relevant. Stable Mind now represents identity, personality, worldview, household values, and locked Core principles as independent fields under one owner. A local customer setup command previews and atomically versions display name, pronouns, household role, a reviewed social-style preset, bounded household worldview perspectives, and bounded household values. Runtime automatically selects the active customer profile on restart, while deterministic derivation rejects any customer-marked change to Core principles, safety/reflex policy, identity category/age, permissions, providers, prompts, models, or other non-personalizable fields. Planner and selective Reflection receive the worldview/value projection; narrow cognition roles receive only authority-relevant identity context. | Mind-profile, prompt-context, identity/body, customer apply/preview/reset, automatic runtime selection, private file mode, recoverable archive, and locked-foundation tamper regressions guard the source behavior. | Bilingual live identity/worldview conversation and restart activation remain to be requalified on the current model/profile; no customer-facing graphical onboarding or household authentication UI is implemented. | Development only. |
| Persistent Social Mind / relational life | Architecture approved; Goal-free cognition backbone, relational-Memory/privacy, semantic situational relevance, and the first source-neutral social-world ingress are source-implemented. Person-first twelve-year-old identity remains implemented. Trusted Goal-free Situation invokes Planner through the existing `/situational-cognition` contract without fabricated UserTurn/Responsibility/Goal/Work or safe-read permission. Relational Memory carries bounded subject/source-person/audience/disclosure provenance and exact Situation subject refs activate disclosure-safe context. The former PSM-3 Host social keyword/category salience table has been removed: changed trusted Goal-free Situation now receives one bounded semantic cognition judgment, while Runtime only validates provenance/no-change/privacy/safety/delivery mechanics. `SituationProjection.audience_refs` carries an exact audience only when a trusted source adapter resolved it; it changes semantic Situation identity and feeds Memory disclosure, and missing/partial audience is never guessed. `build_trusted_goal_free_situation_observation(...)` is the generic in-process adapter boundary and performs no person recognition, relationship inference, scene semantics, or audience inference. Existing social feedback and bounded private Memory candidates remain; unresolved Fast may delegate once without an Activity/Memory result, and direct slow readiness uses the same restricted Deep scope. Complete decisions receive no second review and Deep cannot recurse. All provenance/subject/identity/repair and candidate checks precede Memory writes. Concrete perception/identity adapters and live/model qualification remain open. | Focused source regressions cover Goal-free provenance/no-op/restricted-Planner/no-Work behavior, model-owned silence for routine presence, relational Memory/privacy projection, exact trusted audience propagation, source-neutral ingress validation, audience-sensitive Situation signature, preservation of Goal-bound paths, zero/one/two-call variants, shared immutable Activity identity and delivered repair refs, and zero Memory writes for invalid results. | Wire one concrete trusted person/presence/audience adapter and qualify family/new-person/friend/privacy/initiative behavior without adding Host semantic behavior rules. | Development only; no live social perception or multi-person identity claim. |
| Social Attention behavior domain | Optional embodied decoration remains subordinate to a concrete Planner-authored Main Activity, has no speech or Goal-completion authority, and may validly be empty. A `PresentationCommit`, terminal Fast result, or canonical Fast/Deep Plan may author it under an exact primary anchor; Runtime only validates, suppresses, or executes after primary launch. Explicitly requested gestures remain Goal-owned steps. | Focused source contracts cover candidate filtering, decoder-bound capability/args, canonical fingerprinting, anchor validity, exact execution, Goal isolation, post-primary scheduling, confirmation-held suppression, and suppression without reselection. Repository guards reject restoration of the retired second writer. | Historical independent-planner probes are diagnostic only. Current Planner prompt/model behavior and physical expression remain unqualified. | Development only. |
| Host structural boundary | Pure Planner-reentry policy lives in `orchestrator/runtime/planner_reentry.py`; TTS text segmentation lives in `orchestrator/runtime/tts_text.py`; Goal-list console projection lives in `orchestrator/runtime/goal_list_console.py`; fail-soft observability recording policy lives in `orchestrator/runtime/observability_recording.py`; fixed-reflex confirmation-token revocation/audit bookkeeping lives with the existing `ConfirmationDialogue` owner in `orchestrator/runtime/confirmation.py`; OS-default audio-device detection/queue/apply lifecycle lives in `orchestrator/runtime/audio_device_lifecycle.py`; top-level process teardown now lives in stateless `orchestrator/runtime/shutdown_lifecycle.py`, reusing the existing InputTurn/Playback/Session owners rather than reimplementing their task or transport truth in `VoiceAssistant`; accelerator sample scheduling, detached task tracking, and trace attachment now live with the existing fail-soft observability policy in `orchestrator/runtime/observability_recording.py`; PlaybackTransport now owns its provider/output methods directly, so the seven `VoiceAssistant` playback/TTS compatibility delegates have been removed while the same session trace spans live on the transport owner; `InputSessionRuntime` now likewise calls its own microphone/VAD/ASR/routed-turn/session-idle operations directly, removing twelve input/session compatibility delegates from `VoiceAssistant` while `InputTurnLifecycle` remains the task-state owner. These are existing Host concerns extracted without adding semantic owners, managers, or state stores. The audited CognitiveRuntime closure also extracts the former nested Fast-advance phase into a typed helper on the same owner; `_resolve()` drops from 1117 to about 1036 lines while preserving concurrent provisional-work cancellation. | Focused regressions pass. Historical method counts moved `159 -> 150 -> 142 -> 139 -> 136 -> 129 -> 127 -> 124 -> 117 -> 105 -> 104`. Current measured baseline: `104 methods / 1 property / 304 init lines / 108 initialized attributes`; size deltas are review inputs. Direct legacy Host model calls remain forbidden (zero sites). | Not a runtime target; full Host decomposition remains separate from behavior qualification. | Development only. |
| Static quality gates | Repository policy, documentation, configuration ownership/inventory, Runtime ownership checks, and selected static-analysis scopes are maintained. Approved #45 makes all ten Runtime/documentation size ceilings informational in every phase, with revision-bound measured baselines and signed deltas; ownership and safety gates still block. Documentation authority now explicitly includes the canonical cognitive architecture, human-interaction contract, and acceptance contract; the docs gate rejects retired positive deepthinking/memory-route claims. Phase 2 guards documentation authority; Phase 4 additionally rejects verified obsolete prompt/client artifacts and direct re-copying of shared whitespace/JSON-Schema mechanisms. The pinned test environment now includes `pytest-asyncio`. | Size-growth and ownership-violation regressions pass. Dependency-free gates can run without GPU. The incremental Ruff/Mypy ratchet now also owns `scripts/run_mypy.py`; further widening remains one verified slice at a time rather than a blanket repo-wide switch. | Not a runtime target. | Development only. |
## Current open work

1. **Complete foreground-priority inference-runtime qualification before provider promotion.** Run the isolated SGLang candidate and vLLM control with the same target model/source/TTS environment and retain the deep-load contention evidence. The provider harness now also has an explicit `ollama --contention-only` deployed-baseline mode that sends no fabricated request priority and retains the same saturated-deliberation timing slice even when foreground work is blocked behind Deep. Repeated provider samples can now be summarized into retained p50/p90/p95/p99 distributions only when provider/model/runtime/source/scheduler/workload identity remains stable. Run all three on the same revision/model/context/TTS conditions, compare retained foreground P95/P99 evidence, then carry the winning provider-neutral compute class through a production-capable client and re-run the real Agent UMI -> Fast Planner -> `PresentationCommit` -> TTS/playback latency contract. Do not switch production merely because the provider canary passes.
2. **Replace or revise the unqualified deployed semantic transaction based on the retained aggregate, not the pasted greeting.** The unchanged 51-case must-pass
   aggregate hard-passed 5 cases and placed 35 primary failures at Fast Planner
   output/coverage, with additional UMI, GA, and Deep failures. Qualify a deployable
   model/resource profile against the frozen corpus while preserving one semantic
   authority and the validated contracts. The single-slot all-`qwen3.5:4b` profile cannot meet the designed GA/Fast concurrency or observed latency target. Do not add
   phrase rules, semantic repair calls, or present fixed-Codex results as target proof.
3. **Close Issue #32 source gates and target evidence before final Fast-Planner
   Prompt/model promotion.** The one typed production path is implemented and the
   superseded endpoint/DTO/model/config surface is removed. Retain ordered-frame,
   commit/terminal identity, pre/post-commit failure, and no-early-Work regressions; then
   measure the exact target provider/model under the real single-slot resource profile.
   Do not stream raw tokens to TTS or add another semantic writer/repair call.
4. **Run the `current_revision_qualification` evidence profile on the committed target.**
   The profile requires the canonical source report, the directory-discovered retained live
   interaction cases, the live provider fault matrix, Gateway/Core, Agent Skill/weather,
   Social Attention, and LAN evidence on the same clean revision. WorkDAG revision/no-redispatch
   remains an explicit source gate; selected live cases cover bilingual effectful speech,
   cancellation, provider-backed Evidence re-entry, multi-goal behavior, follow-up continuity,
   duplicate-effect cardinality, and declared warm Planner/playback budgets. Physical voice
   and physical robot remain separate optional evidence tracks.
5. **Retain the structural rule during qualification and later maintenance.** Reopen
   decomposition only for a concrete ownership seam or defect; file size alone is not
   permission to add a Speech Manager, Reconciliation Manager, Meta Planner, or one manager
   per cognitive term. Source
   implementation, automated verification, target validation, and release readiness remain
   separate axes.

Phase 2 documentation convergence is source-closed: `docs/chromie_mind.md` now describes
MindProfile as bounded context rather than deleted agents/routes; the duplicated
`docs/CONFIGURATION.md` tail is removed; current architecture docs no longer retain the
reviewed Host-result-fallback or route/intent-UMI contradictions; and the docs gate protects
those boundaries mechanically.

Phase 6 qualification infrastructure is source-complete, but Phase 6 itself is not closed by
that source change. `target_evidence_closure_eligible=true` from a
`current_revision_qualification` bundle is the retained target-evidence exit condition. A
source report alone, preview-only General Ability run, local-stub provider fault matrix, or
older revision remains insufficient.

## Evidence interpretation

Source implementation, automated verification, target validation, and release readiness
are separate axes. A passing unit/integration suite does not prove microphone, audible
speaker, GPU latency, simulator, or physical-provider behavior. Likewise, retained live
evidence from an older revision does not silently qualify the current source after a
material cognition, model, provider, prompt, or timing change.

Chromie remains a development project. No publication or release-readiness claim is made
by this status page.
