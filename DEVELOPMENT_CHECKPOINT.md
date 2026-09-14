# Development Checkpoint

## Integration delivery — 2026-09-15

Owner authorization: integrate the newest remote SC design, resolve conflicts,
rerun validation, commit and push both repositories. Chromie was fast-forwarded
from `d5a7985e` to `2e18f86a` on `main`; Soridormi from `284273b` to `0af3d09`
on `codex/turn-count`. The paired provider integration is now committed and
pushed as `fa6331f1344ce26154b197ca7d7c49badea292ad`. Resume at the latest
Chromie delivery commit containing both handoffs. Original local changes remain
in recovery stashes; do not reapply them over this integration. Both repositories now require fetching/checking upstream
before development and again before push, preserving dirty work during integration.

The upstream SC design is authoritative: SC alone authors ordinary communication;
Planner authors Work and planning facts. Preserve SC > GI > GA > Fast scheduling,
separate Vocal/Activity waiting queues, prepared-start alignment and all remote
weather/evidence/catalog/argument-validation repairs. The old Planner wording
prompts were not restored. Complete catalog projection now uses the existing
transport budget at the new common Work prompt owner and layered projections.
Applicable local Schema/DTO, technical re-entry containment, typed diagnostics,
preflight/integrity collection and post-failure status regressions are integrated.
Soridormi keeps its new manifest validator and existing resource mappings,
adding only route-to-source realization and structured-input regression coverage.
Unrelated submodule content remains untouched.

Combined canonical passes 3,382 tests / 1,139 subtests, 145 benchmarks and 20
legacy tests, including policy, ownership, pinned static/configuration/docs gates.
Two existing FastAPI warnings remain. Full 6,000 SC-aware workflow replay passes
with source unchanged: 1,400 workflows, 1,800 expected states, 2,580 expected
rejections and 220 expected nonexecution outcomes. Level A passes 45/45.
Focused SC/Planner/acceptance: 785 tests / 364 subtests; rebound workflow: 104/104;
final re-entry: 15 tests / three subtests. Provider: 798 tests / two skips, body
165, task 147, governance, compile and manifest pass. The initial 68 failures were
exact Schema mismatches; only input-format snapshots and hashes were rebound on
the remote SC-aware corpus. The provider automatic merge also hid upstream mapping
keys; the existing regression caught it and all upstream declarations were restored.
Large corpus manifest: `3ba46381bf230f7a930982b05f8cebd9cb672ccd4efbfbdee14d0c4994084f04`.

Evidence: `.chromie/acceptance/sc-integration-20260915/` retains source recovery,
focused/failing/final logs, Schema rebind accounting and the aggregate replay.
The prior `.chromie/acceptance/engineering-18-20260914/` twelve-iteration Qwen
proof is historical pre-SC evidence only: 3,296 tests / 1,071 subtests and 6,000
replays passed there, but its native cohorts were incomplete. It cannot qualify
this SC integration. See the audit for original root causes and changed ownership.
No model weights, production model profile or decoding defaults are changed in
this integration; retain upstream's single-Gemma configuration. Local services
still package the pre-integration revision and are not fresh SC target evidence.
The earlier simulator/MCP were safely stopped; no new physical proof is claimed.
Fine-tuning/release readiness remains false; #24/#32, independent reference review,
hidden semantic-family evaluation and current target closure remain open.

Cross-machine resume: fetch and fast-forward both named branches, initialize
Soridormi submodules and follow CHROMIE_RUNBOOK.md for that machine's generated
profile and rebuild. Never copy another machine's PIDs or edit `.env.runtime`.
Run `./scripts/run_tests.sh`, `python scripts/general_ability_acceptance.py --mode
level-a --evidence-dir <new-path>`, and `python scripts/run_workflow_replay.py
--workers 4 --evidence-dir <new-path>`. Before native evaluation verify packaged
Agent source and capture a fresh runtime identity using the current CLI. Run a
complete discovered cohort with one revision and retain one bundle at its end;
judge every case and leave unrun coverage explicit. Private traces/scripts and
recovery archives are ignored/local and do not accompany a fresh clone.

## Delivery — 2026-09-14

Owner authorization: commit all accumulated project changes and push both paired
repositories. Chromie base is `ec4a5c268a557ac0f4281c668b1404edb96c57cc` on `main`,
remote `origin/main`; resume at the latest commit containing this checkpoint and
handoff. Paired Soridormi commit is `0af3d09` on `codex/turn-count`, containing
provider argument-realization contracts, manifest validation and tests.

This delivery includes single-Gemma priority scheduling (SC > GI > GA > Fast),
SC verbal/nonverbal Runtime handoff, separate Vocal/Activity waiting queues and
prepared-start alignment, token-budget verification and existing Schema invariants,
plus the reproduced catalog, weather, terminal-evidence and argument-serialization
repairs. The detailed module I/O and failure workflows below remain authoritative.
No case-specific semantic rules, extra model reviewer or Qwen promotion is included.

Latest unchanged-code gate: `.chromie/acceptance/qwen9b-comparison-20260914/canonical.log`
records 145 benchmarks, 3,303 tests / 886 subtests and 20 legacy tests passing,
including policy/ownership/static checks; two existing FastAPI warnings remain.
Documentation checks passed after comparison updates and are rerun for this delivery.
Earlier same-source evidence: 6,000 workflows and 45 Level A cases pass; paired
Soridormi full suite 790 passed / 2 skipped, governance and body concurrency pass.
Both executable patches were compared to their retained tested snapshots before
commit; full tests are not rerun solely for this delivery-document update.

Release readiness remains blocked: the 51-case native cohort stopped on wrong-sign
turning during its first case; focused right-turn/weather pass 2/2 does not replace
it. GI/GA/Planner semantic failures and #24/#32 remain open. The 44-request-per-model
Qwen comparison found lower latency but no qualified replacement; SC/Deep/physical
proof was not obtained. The failed and passing evidence below retains those limits.

Runtime stays on the restored single Gemma and existing operator Host (PID 854858,
launcher 852382, preserved text client 400841); details below are a local snapshot,
not a portable process identity. Commit metadata changes do not rebuild running
images. Before live validation, verify packaged source and capture a fresh identity.

Cross-machine resume: fast-forward Chromie `main` and Soridormi `codex/turn-count`,
initialize Soridormi submodules, read this delivery and the current comparison,
then follow `CHROMIE_RUNBOOK.md` to generate the machine profile and rebuild services.
Use `python scripts/capture_runtime_identity.py --verify-agent-source chromie-agent`
and `python scripts/capture_runtime_identity.py --allow-dirty --output <path>`
as separate checks before an authorized full native cohort. Preserve single Gemma,
non-thinking, Soridormi safety ownership and supervised physical-evidence limits.

Raw traces, model weights, `.env.runtime`, `.chromie/acceptance/` and debug bundles
are local/generated or ignored artifacts, not included in Git. Their exact paths and
summaries are retained below; a new clone does not itself contain raw proof. Generated
social-eyes XML inside Soridormi's Open_Duck_Playground submodule also stays local;
no third-party submodule revision is changed. No tracked project edits are excluded.

## Qwen3.5-9B comparison — retained 2026-09-14

The owner authorized model comparison after the failed-case repair. Both frozen
44-request cohorts completed: GI 30, GA 6, Fast 8. Messages, dynamic Schema,
sampling, stream mode and non-thinking were identical except served model ID.
Official Qwen3.5-9B and Gemma-4-12B-it both used online FP8 in the same pinned
SGLang image, context 65,536; architecture-specific templates/parsers/cache differ.
The comparison made no production model replacement, semantic code/prompt change
or retry/judge call. Its preceding implementation is included in the delivery above.

Evidence: `.chromie/acceptance/qwen9b-comparison-20260914/`.
`report.md` owns this experiment's readable comparison; `adjudication.json` retains
all 88 reviewed outputs, module input/output evidence, earliest divergence and
containment. `manifest.json` freezes 44 case hashes; paired request equality was
verified with only model ID excluded. `source-before.patch`, exact raw requests,
responses, engine/model identities and offline validation are retained.

Both models pass 44/44 Schema checks. Corrected DTO/Host results: Gemma GI 30/30,
GA 6/6, Fast 5/8; Qwen GI 28/30, GA 6/6, Fast 6/8. A missing GI validator constructor
argument was a harness error, corrected offline for both complete raw cohorts;
there was no repeat inference or changed criterion. Reviewed Fast plans acceptable:
Gemma 3/8, Qwen 1/8. GA stage results: 4/6 versus 5/6, including required conservation
of invalid upstream WHAT, not successful originating episodes. GI strict oracle
5/24 versus 2/24 includes lexical/span false positives; no GI semantic accuracy
claim is derived from it. Uncertain manual GI judgments remain explicitly review.

Sequential request latency medians (Gemma/Qwen): GI 4.54/2.80 s, GA 6.81/4.01 s,
Fast 5.57/3.42 s. Qwen improves latency and one acquisition/handover classification,
but retains wrong turn direction, incomplete work claimed complete, misbound values
and invented semantic uncertainty. Both candidates remain unqualified. No SC, Deep,
whole-runtime, physical voice/robot or real-time scheduling proof was obtained.
Do not promote Qwen or infer a role split from this failure-focused sample.

Production restored to single `chromie-gemma4-12b`; temporary Qwen container is
stopped. Launcher PID 852382, text Host PID 854858, PTY 39865; existing client
PID 400841 preserved. Host evidence: `.chromie/acceptance/psm-live-text/20260914T120750Z/`.
Soridormi and configured speaker remain enabled; startup synthesis discarded PCM,
and no audible or embodied test was submitted. `restored-source-verification.json`
confirms packaged Agent matches source; `restored-models.json` confirms Gemma.

Current comparison follow-up gates pass: `canonical.log` records 145 benchmarks,
3,303 tests / 886 subtests and 20 legacy tests, with two existing FastAPI warnings.
Repository policy, test ownership, documentation and incremental static gates pass.
The comparison changed only retained evidence and existing status/handoff documents;
the preceding 6,000-workflow/45-Level-A and Soridormi results were not rerun here.

Next: retain the engineering patch and compare the remaining semantic failure clusters
at their earliest owner under the frozen-cohort method. No case rules, downstream WHAT
repair, or extra semantic-review call. #24/#32 and physical evidence gaps remain open.
Before another live cohort, gracefully stop the current Host, verify/capture fresh
runtime identity, run the whole discovered cohort, adjudicate every case and retain
one debug bundle per aggregate stop; restore the operator afterward.

## Failed native cases — preceding 2026-09-14

The requested root-cause repair is implemented for reproduced engineering boundaries,
but native semantic qualification remains **failed**. No commit/push, model replacement,
case-specific semantic routing, or additional model reviewer was made. Earlier dirty
work is preserved. Current evidence root:
`.chromie/acceptance/failed-case-repair-20260914/`.

The original six-case aggregate and exact native transactions remain under
`.chromie/acceptance/lane-coordination-20260914/`. Investigation refined the earlier
triage: the milk case already loses its acquisition/handover resource shape in GA,
before Fast incorrectly offers walking as complete delivery. SC did run in the weather
case; the acceptance projection had removed its structural ownership fields.

| Actual episode / responsible owner | Authoritative input → actual wrong output | Repair and remaining boundary |
|---|---|---|
| Compound motion / Fast argument serialization | Catalog shows sorted argument keys; decoder enforces provider insertion order → later-needed keys become unreachable and numeric output repeats until truncation | Align recursive argument-property order and add one generic serialization instruction. Frozen request: about 53 s/truncated → about 10 s/complete. Full semantic correctness remains separate. |
| Concurrent SC + Fast / capability catalog | First refresh publishes TTL before awaiting provider → another reader sees only static tools | Join existing refresh lock and publish freshness after the complete result/error. Cancellation leaves it stale. Cold native rerun receives full Soridormi catalog. |
| Right turn / provider realization declaration | GI/GA retain right; Fast emits count alone → positive default turns left | Provider now declares direction→yaw and duration→seconds; existing Host checks require supplied arguments. Correct right-turn execution proven. Wrong signed values remain a native semantic blocker. |
| Weather / provider identity | Requested 重庆 → transliteration search candidate Zhongqing, Guizhou accepted as identity | Transliteration remains retrieval-only; requested locality and supplied admin/country must match. Ambiguous/unmatched candidates fail closed. |
| Weather / early safe-read handoff | Admitted zh-CN lost before provider; terminal provider failure disappears from running Work → stale-plan rejection | Preserve admitted language; completed/failed/refused/timed-out results are terminal evidence, not competing commits. Cancellation/Goal revision guards remain. |
| Weather SC / evidence projection | Asynchronous accepted SC result → owner/function removed by redaction → acceptance reports no SC | Retain structural owner/function/delivery/truth enums; private utterance text stays redacted. Native final answer and actual playback remain independently inspected. |
| Gaze+blink; walk+sing / GI and Fast | Independent obligations merged; unsupported count or vocal mode then assigned to body capability | Unresolved semantic failures. Existing Host rejection is containment, not successful interaction; no word rules or downstream WHAT repair added. |
| Milk delivery / GA then Fast | Complete bring obligation → resource_kind=none; Fast then claims complete from one short walk | Unresolved semantic classification/coverage failure. Canonical resource validation cannot check a resource contract that GA failed to author. |

Actual final aggregate flow: admitted compound turn → GI three ordered Responsibilities
→ concurrent SC / GA / Fast (all catalog readers join provider refresh) → GA preserves
left, Fast emits negative yaw → canonical mechanical checks accept bounded args →
Soridormi executes submitted right turn → Runtime marks three Goals complete.
The first wrong boundary for this direction failure is Fast's signed realization;
provider execution and safe idle do not prove the requested left effect. GI separately
still emits the unitless speed as a string. `final-native/adjudication.json` retains
per-module I/O, correlations, expected values, verdicts and downstream consequences.

Final native identity: `cb2a9d0db2b062372758bc9be97d93c009f02b58cf9041233df4b882d0d092ff`.
Agent packaged-source host/container digest both:
`2b0283a4087a081d143a7d0d8bac655808555f7b0c9c0150b60f48bbd996e593`.
The full directory-discovered 51-case cohort was invoked unchanged, then stopped for
that hard signed-direction failure after simulator completion/safe idle, during
remaining first-turn handling: no completed case summary, first interrupted, 50 unrun.
One aggregate bundle:
`/home/chromie/Downloads/chromie_debug_bundle_20260914_194741.tar.gz`.
This is an incomplete failed cohort, never a release pass. Previous intermediate
cohorts and exactly one bundle per stop are retained with their own identities.

Validation: `final-canonical.log` passes 145 benchmarks, 3,303 tests / 886 subtests,
20 legacy tests and repository policy, ownership, static and documentation checks
(two existing FastAPI warnings). `final-workflow/` passes all 6,000 cases with
source unchanged; `final-level-a/` passes 45/45. Catalog focused tests fail before
and pass after, including simultaneous readers, provider failure and cancellation.
Paired Soridormi full tests pass 790 / 2 skipped in an isolated writable container;
body-concurrency/governance checks also pass. Earlier harness attempts failed for
host dependency absence, read-only test writes, or duplicate /app search roots;
those failures remain recorded and are not product passes.

Six exact frozen Fast requests were replayed per variant. Frequency-penalty tuning
was rejected. Argument-order-only was revised after a gaze truncation; the retained
order+format candidate still has semantic omissions/wrong selections. All outputs
and manual verdicts are retained; reconstructed Host checks are explicitly weaker
than full native qualification. The unchanged 24-case GI screen passes mechanical
Schema/DTO/Host checks but includes semantic failures and overstrict oracle judgments;
its 5/24 strict-oracle result is not a reviewed semantic accuracy claim. No GI/GA
prompt changes or model substitution were made in this repair.

No new current document, environment key, semantic authority or first-class runtime
term was added. Existing scheduling work remains intact. The single Gemma 12B engine
and SC > GI > GA > Fast priority remain. #24/#32 delivery closure stays blocked by
native semantic/provenance failures and missing supervised physical evidence.

Post-aggregate focused regressions on the same runtime source pass 2/2:
`final-native/focused-live/` (right turn SID `6878f992`, weather SID `28a14ee0`).
Manual review confirms walk 3 s then negative-yaw right turn; weather uses 重庆/night,
returns matching provider data and SC reports grounded values through discarded PCM.
`final-native/focused-adjudication.json` records both. These focused passes do not
replace the failed complete-cohort attempt or establish prompt nonregression.

Operator restored: launcher PID 838087, Host PID 840376, PTY 28859;
`./scripts/start_chromie.sh --text-console --keep-services`. Existing text client
PID 400841 remains. Host evidence:
`.chromie/acceptance/psm-live-text/20260914T115053Z/`.
Capabilities and configured speaker are enabled; no automatic audible test was sent.
`restored-source-verification.json` confirms packaged Agent matches the checkout.
Documentation updates after runtime capture do not alter the tested executable source.

Next: retain the current engineering patch and review residual semantic failures before
any release claim. The subsequently authorized Qwen comparison is recorded above;
it did not qualify a production replacement. Keep Gemma 12B fixed and preserve the
global non-thinking boundary. The active #24/#32
line remains open; no scoped semantic acceptance or release acceptance is inferred.
Before any live rerun, inspect/stop the operator Host gracefully, verify packaged source
with `python scripts/capture_runtime_identity.py --verify-agent-source chromie-agent`,
then separately capture a fresh identity with `--allow-dirty --output <path>`.
Reuse directory-discovered frozen scenarios, adjudicate every result, retain one debug
bundle per aggregate stop, and restore the operator afterward. Do not use phrase rules,
new semantic judge calls, or Host reinterpretation to repair GI/GA/Planner meaning.

## Scheduler alignment — preceding 2026-09-14

The owner-authorized lane scheduling and prepared-start change is implemented.
Preserve the earlier dirty work below; no commit or push was made. Evidence root:
`.chromie/acceptance/lane-coordination-20260914/`. The preceding SC handoff section
retains baseline/history; this section owns the current validation and operator state.

The reproduced defect was execution starting as soon as each provider returned
from its own preparation: parallel submission alone left an 80 ms start gap
(`baseline.log`). Runtime now maintains separate eligible-FIFO Vocal/Activity
waiting queues under one capacity/resource arbiter. Total capacity is unchanged;
with capacity > 1, one slot is reserved for Vocal and the remainder supports
compatible Activity concurrency. Required prepared members reserve resources
atomically and await one release; optional SC decoration cannot hold ready speech.
Each member releases resources independently after completion/cancellation.

SC's exact anchored verbal/nonverbal result is materialized once before Runtime
submission, including Situation and wordless entry points. Host waits for first
PCM/output readiness, Soridormi waits for plan/monitor/confirmation or existing
trusted SC preflight, and terminal results return to the social ledger. A reproduced
old Planner-only outcome guard now recognizes SC's source/owner without granting
Goal-completion authority. Optional provider loss is retained without suppressing
speech. No new prompt/model call, service, environment key or document was added;
existing `LaneCoordinationGroup.start_policy` adds/defaults to `prepared_start`.

| Actual controlled workflow | Input → observed output | Verdict |
|---|---|---|
| SC / semantic owner | One controlled informative utterance plus one exact anchored blink → unchanged act/anchor IDs | Controlled decision; not native inference |
| Adapter / materialization | Complete SC result → one packet, one coordination ID, no Goal ownership for blink | Correct; no independent expression dispatch |
| Runtime / scheduling | Two accepted members with distinct resources → one common release at monotonic 35952.817652954 | Correct shared Host release |
| Host PCM and Soridormi preparation | Blink ready 719 ms before PCM → neither advances before release; both complete | Correct preparation/transport, no physical-onset claim |
| Ledger / evidence | Real terminal results → speech completed and social decoration completed; simulator safe idle | Correct; admission is not completion |

Validation: `final-canonical.log` passes policy, ownership, static analysis, docs,
145 benchmarks, 3,295 tests / 876 subtests and 20 legacy tests (two existing FastAPI
warnings). `final-workflow/` passes all 6,000 cases with source unchanged;
`final-level-a/` passes 45/45. Focused scheduling/playback/SC matrix passes 107 tests /
32 subtests; broader Runtime checks pass 71 tests / 15 subtests. Negative cases cover
required preparation failure/timeout, optional lateness/resource conflict/provider
loss, unsupported compound preparation, cancellation, lane fairness and resource drain.

`queue-sim-bound/` proves real Host/TTS (discarded PCM) plus deployed Soridormi
simulator execution for controlled speech+blink. Identity SHA-256:
`e5462d3261e19898aa18f2f4153e63ff409c2ca093db368adce0f8360fa13f93`.
Agent packaged-source host/container digest both:
`5c335cd307cce67c8047b11721378b857a9c39a272caf0421f8321bbb7ee4ef0`.
The full directory-discovered native cohort was invoked once on this bound source,
without edits/restarts between cases, then manually stopped for confirmed hard
Goal-coverage/provenance failures: 0/6 completed cases pass, seventh interrupted,
44 unrun. `final-live-adjudication.json` records every completed module workflow,
actual inputs/outputs, expected contract, first wrong boundary and containment.
All 33 native call records are retained in `final-live-transactions/`; separated
Docker stderr avoids two interleaved records in the combined monitoring log.
One bundle for this aggregate:
`/home/chromie/Downloads/chromie_debug_bundle_20260914_190044.tar.gz`.

Remaining native failures are outside this scheduler repair: Fast output truncation;
GI merging independent gaze/blink or walk/sing responsibilities; Fast claiming full
milk acquisition/delivery from one 10-second walk; right-turn intent lost to an
omitted direction parameter; and weather resolving 重庆 to Zhongqing, Guizhou then
SC reporting those values as Chongqing weather. Case 6's separate missing-SC check
is an evidence-projection gap: SC actually returned an utterance and three PCM
segments completed. These failures are not averaged into a passing revision.

Evidence limits: initial adapters cover Host speech and a single Soridormi plan per
prepared group. Unsupported compound body preparation fails closed (optional
members may be omitted); ordinary same-provider batches retain embodied compilation.
There is no guarantee of identical physical onset, word/gesture alignment, atomic
cross-provider rollback or physical microphone/speaker/robot behavior. Physical
WorkDAG nodes remain sequential. Current release readiness remains development-only.

Retained harness failures are not production passes: initial build raced old Host
shutdown; the first identity command verified source but did not write an identity.
`queue-sim/` and `unbound-harness-run/` therefore do not establish bound evidence.
That incomplete native attempt was stopped and has one bundle,
`/home/chromie/Downloads/chromie_debug_bundle_20260914_185559.tar.gz`.
The corrected bound proof/cohort above replaces those claims. Early full-test runs
exposed fixtures assuming two Activity slots at total capacity two; those fixtures
now request capacity three while preserving their original concurrency assertions.

Operator restored: launcher PID 719138, Host PID 721389, PTY 27611;
`./scripts/start_chromie.sh --text-console --keep-services`. Existing user client
PID 400841 remains. New Host evidence:
`.chromie/acceptance/psm-live-text/20260914T110210Z/`. Source verification passed;
one resident Gemma 12B, capabilities and configured speaker remain enabled.
No automated physical playback was performed. Final documentation edits follow
runtime evidence capture and do not alter tested runtime source.

Next resume: inspect the retained native workflows and continue the existing
canonical/target-evidence delivery line (#24/#32), repairing earliest semantic or
provider evidence boundaries under the frozen qualification method. Recheck the
running Agent with `python scripts/capture_runtime_identity.py --verify-agent-source
chromie-agent`; inspect operator state before any further acceptance run. Stop the
Host before immutable live testing; preserve its separate dialogue client and
restore `./scripts/start_chromie.sh --text-console --keep-services` afterward.
Configuration keys 381 → 381; maintained Markdown documents 102 → 102; reading-path
entries 15 → 15. Existing execution-lane prose was consolidated rather than adding
a design document; one existing start-policy enum gained a value, no new architecture
layer or semantic authority.

## SC Runtime handoff — current 2026-09-14

The owner's SC speaking/social-attention queue requirement is implemented through
existing owners. One resident Gemma 12B remains; no prompt, model, semantic DTO,
service, environment key, architecture term or current document was added. Existing
dirty work is preserved; this continuation did not commit or push.
Evidence root: `.chromie/acceptance/sc-runtime-handoff-20260914/`.

Confirmed and repaired boundaries:
- The common independent SC response discarded its resolution, so GI-triggered
  optional expressions never reached Runtime admission. It now carries the exact
  request/snapshot and complete SC result, including wordless and mixed acts.
- SC invocation identity replaced the admitted user-turn ID, hiding early completed
  speech from later Goal-scoped context. Delivery now retains the source turn;
  inference/snapshot identity stays separate. Both weather live packets confirm
  that the later SC request sees the initial completed speech.
- Independent expression execution omitted terminal ledger feedback. The adapter
  now records actual completed/failed/cancelled results through the existing owner;
  admission alone never becomes completion or Goal satisfaction.
- Deployed Soridormi preflight still recognized the retired Planner auxiliary
  source; SC's queued blink therefore failed before execution. The same old source
  check also marked grouped SC decoration mandatory. Both now recognize SC source
  and semantic owner. Low-risk/non-motion restrictions, request/definition/body
  confirmation requirements and safety monitoring remain; no consent is fabricated.
  Situation's redundant resolution assignment was removed, preserving its dedicated
  freshness/concurrent-delivery path.

Validation: `final-canonical.log` passes repository policy, ownership, documentation,
pinned static analysis, 145 benchmarks, 3,284 tests / 868 subtests and 20 legacy tests
(two existing FastAPI warnings). `final-workflow/` passes 6,000 cases with source
unchanged; `final-level-a/` passes 45/45. Earlier focused transport proof is 136 tests /
16 subtests; final provider/SC proof is 100 tests / 12 subtests. Negative preflight
cases cover retired/missing ownership, physical effects/class and all confirmation
sources. These local gates do not establish native-model ability.

`queue-sim/` retains the real queued-but-rejected blink; `provider-baseline.log`
reproduces two source-owner failures. `queue-sim-final/` binds the final runtime
identity and proves the same controlled SC nonverbal decision reaches the real
Runtime queue and deployed Soridormi simulator, then records
`social_decoration_committed` → `social_decoration_completed`, with safe idle.
The SC output is controlled, not a native semantic inference or physical proof.
`queue-sim-provider-focused/` retains the earlier successful focused replay.
Retained harness errors are not production failures: initial empty Responsibility
fixtures, first queue probe's wrong ledger accessor, and a final-cohort CLI typo
that started no case. Corrected failures/proofs have separate artifacts.

Final native/live identity SHA-256:
`b7ceb2c4973bf76e6716a04b4a256fb0021321597075222181c2a222a8ab1043`.
The complete directory-discovered cohort was invoked on each evaluated source,
without changes between cases. Each stopped incomplete at the fourth case's GI
HTTP503; three completed cases failed and 47 were unrun. One bundle per aggregate:
- Before provider-source repair: `live/`, `live-adjudication.json`, bundle
  `/home/chromie/Downloads/chromie_debug_bundle_20260914_173851.tar.gz`.
- Final source: `final-live/`, `final-live-adjudication.json`, 15 retained native
  transactions in `final-live-transactions/`, bundle
  `/home/chromie/Downloads/chromie_debug_bundle_20260914_174407.tar.gz`.

The final failures remain substantive: Fast Planner truncates the compound motion
output; another plan has a singleton parallel member; the milk request falsely
claims complete coverage with only a 10-second walk. Host admits that incomplete
milk Plan and the simulator executes the walk, without acquisition/delivery.
Fast/Deep evidence reentry then rejects required catalog projections (22,097 >
9,000 / 28,410 > 12,000 chars), while SC silence relies on an overbroad completed-task
projection. GI's singing/walking Responsibilities reuse overlapping source spans;
its HTTP503 is validation containment, not an engine outage. The supported
`coordination` wire field is not the defect. SC/GA/Planner were not invoked in that
interrupted fourth case. Do not report overall SC/Planner/robot qualification.

Both original weather probes complete native lookup and final grounded result
speech with discarded audio: 83.89 s / 83.05 s total, first simulated playback ends
at 15.93 s / 14.85 s. `weather-adjudication.json` and `weather-transactions/` retain
all results. Later SC context now contains initial speech, but both cases still
repeat the greeting under a newly created Planner communication Need. Current
Need coverage requires a new explicit verbal act; interpretation-triggered unbound
acts cannot respond/ask. Qualify that early-act/Need linkage as a complete semantic
transaction before changing it. Do not substitute a wording filter, invent Goal
completion, or let acknowledgement discharge an unresolved answer/action Need.
Repetition, latency, prior SC model truncation and #24/#32 release closure remain open.

Operator state restored: text Host PID 654715, launcher PID 652481, PTY session
2104, Host evidence `.chromie/acceptance/psm-live-text/20260914T094729Z/`.
Existing interaction client PID 400841 remains. Startup verified packaged Agent
source digest `62d104f162af5d3bd29046160e46098b60f19d3a4889f46c30cfb02e5fbdbd68`
and the single Gemma profile; capabilities and normal operator speaker are enabled.
Automated dialogue used discarded audio only; no physical microphone/speaker/robot
claim. The app terminal-open request is queued, not confirmed visibly opened.

Resume from `weather-adjudication.json`, the original weather packets and the
active SC exception: audit complete Need/early-act authority with the semantic
qualification skill, freeze the contrast cohort before semantic edits, then run
focused and full qualification. Preserve the current failed aggregate and prior
single-engine evidence below. For operator interaction use
`python scripts/chromie_psm_live_text_console.py`; logs stay with
`./scripts/start_chromie.sh --text-console --keep-services`.
Surface inventory remains 381 configuration keys, 102 Markdown files and a
15-document core reading path; no new current document/configuration surface.

## Single resident Gemma 12B — preceding evidence 2026-09-14

The owner explicitly superseded the dual-instance request with one resident
Gemma 12B SGLang engine. SC/GI/GA/Planner keep independent context and authority:
SC=500 > GI=400 > GA=300 > Fast Planner=200; Deep Work=100, background=0.
Both SC and GI preserve their priority in their permitted deeper pass. No new
model/service/environment key/current document or semantic authority. Existing
uncommitted startup, SC/GA and terminal-dispatch repairs remain intact. Dual
configuration and Qwen prompt experiments were withdrawn. No new commit/push.

Evidence root: `.chromie/acceptance/dual-inference-20260914/`; the historical root
name does not imply the selected topology. Dual Qwen AWQ/Gemma FP8 probes failed
at 18 GiB CPU offload (lazy NCCL CUDA allocation) and at 24 GiB (Deep exceeded its
unchanged 120 s deadline). Probe containers are stopped. The selected engine is
the original pinned Gemma FP8 profile without CPU offload; ASR/TTS and Soridormi
remain enabled. Generated `.env.runtime` is single Gemma again.

`priority-single-gemma/` proves both running priority-200 requests retracted once
for SC/GI and then resumed/completed. Foreground first tokens arrived 77–78 ms
after submission. This is synthetic native scheduling evidence, not whole-turn
response latency or semantic qualification. `single-budget-proof-margin2048/`
replays the complete original SC packet with the production 2,048-token margin:
50,060 input + 1,024 output + 2,048 margin = 53,132 < 65,536; native primary output
passes Schema/DTO/Host in 15.18 s. The provider now confirms estimated overflow
using its own tokenizer, retains full failure packets and returns typed failure.
No content pruning, second semantic call or increased timeout is involved.

Whole-turn evidence remains mixed. The original baseline completed 12/51 cases,
then stopped incomplete on an SC false budget rejection; bundle
`/home/chromie/Downloads/chromie_debug_bundle_20260914_162109.tar.gz`.
The rebuilt single-engine aggregate completed three cases, all failed, and stopped
at case four's GI source-provenance rejection; 47 not run. Its one bundle is
`/home/chromie/Downloads/chromie_debug_bundle_20260914_165712.tar.gz`.
Every completed/interrupted result is adjudicated in `single-live-adjudication.json`.
Independent Planner numeric/coverage/schema failures and GI overlapping source
spans remain unqualified; the GI 503 is validation containment, not engine outage.

The two reported weather episodes were retained separately: `weather-today/`
completed lookup and result speech in 75.93 s headlessly; `weather-rain/` failed
an SC pre-action ordering invariant. Native frozen SC comparisons retain every
iteration, including failed output binding, missing expression and one truncated
output. The bounded decoder repair preserves upstream delivery-phase choices,
authors Need bindings before timing/wording, and requires a real expression for
wordless acts. Prompt, model, Host authority and generation budget are unchanged.
A focused native retry with recording passes, but does not erase the truncation.

Current-source canonical gate `expression-canonical.log` passes 3,274 tests /
860 subtests, 145 benchmarks and 20 legacy tests (two existing FastAPI warnings).
`expression-workflow/` passes all 6,000 cases with source unchanged;
`expression-level-a/` passes 45/45 cases. The earlier interrupted
`final-canonical.log` is not a passing gate. Native `sc-order-expression/` retains
12/13 passes; the weather case repeats acts until truncation. The original phase
and empty-expression shapes are now excluded, but the transaction remains
unqualified. Agent rebuild/source verification completed (digest
`62d104f162af5d3bd29046160e46098b60f19d3a4889f46c30cfb02e5fbdbd68`).
Current diagnostic runtime identity is
`7ac0718629eed501840a27d4f68564f7fb1049dd23af3fa6493cedf85411f79a`
(`expression-runtime-identity.json`, dirty/non-release evidence).
Native/physical stability, rapid interaction and #24/#32 release closure remain open.

The current-source live aggregate (`expression-live/`) again completed three of
51 cases, zero passes, then stopped at case four's GI validation failure (whole
admitted turn copied into `comparison`, not the prior run's overlapping spans).
One bundle: `/home/chromie/Downloads/chromie_debug_bundle_20260914_171846.tar.gz`.
All 15 native calls and all completed/interrupted cases were inspected; see
`expression-live-adjudication.json`. In the milk case, unlike the prior rejection,
Fast claimed complete coverage with only a 10-second walk. Host admitted it and
the simulator completed locomotion, without acquisition/delivery. Later Fast/Deep
reentry hit required Capability-catalog projection limits (22,097>9,000 and
28,410>12,000 chars). Safe idle was observed afterward; the user goal was not met.
This is a real Goal-coverage failure and cannot be averaged into a pass.

Both original weather episodes subsequently completed lookup and grounded final
SC replies on the same revision: `weather-rain-expression/` 83.08 s and
`weather-today-expression/` 77.83 s; first virtual playback 14.79 / 14.04 s.
Both repeated the initial greeting in the later required response. Thus their
mechanical passes do not establish natural interaction or rapid response.
`weather-expression-adjudication.json` binds replies to provider data and retains
the duplication. The old packet has completed early SC speech in
`conversation.history` but no `interaction_context.already_spoken`; projection
and request/user-turn correlation remain an unresolved provenance audit, not a
claimed repair. No semantic same-stage repair call or latency budget increase.

Text Host is restored with `./scripts/start_chromie.sh --text-console --keep-services`;
ASR is bypassed, Soridormi remains enabled, and launcher logs stay separate from
the interaction client. Host PID 584502; retained Host evidence directory
`.chromie/acceptance/psm-live-text/20260914T092337Z`; launcher terminal session 49319.
The original client PID 400841 was left intact. The app terminal open request was
queued. Earlier pause/no-restart statements below are historical. Physical
microphone/speaker proof remains unclaimed; the restored operator Host uses the
normal speaker, while all automated scenarios above used no speaker.

Next resume: audit early SC delivery identity/projection and duplicate need
fulfillment at the existing authority; qualify complete Planner Goal coverage and
required Capability catalog projection, and the GI atomic-binding failure. Keep
one immutable aggregate per deployed revision, retain one bundle per stopped/full
cohort, and never promote focused passes over these failed whole-turn results.
To interact from repository root: `python scripts/chromie_psm_live_text_console.py`.
Do not start a second Host. No new commit or push; branch/base remains
`main` / `ec4a5c268a557ac0f4281c668b1404edb96c57cc` plus the preserved dirty patch.

## GA source status and terminal failure repair — 2026-09-14

Latest user SID `f1c26dc9` (`hello, what's the weather today in chongqing?`)
ran the preceding SC/GA patch: Agent and checkout source digests matched before
this repair. SC resolved and played an acknowledgement; GA then authored
`source.status=unknown, source_name=none` (a literal name), failing its DTO.
Host suppressed the failure response because SC had spoken, also skipping the
dispatch that marks the session complete. The CLI eventually timed out.

Local source now compiles the existing GA source-status/name/referent invariant
into complete decoder alternatives and always dispatches the existing bounded
operational failure response, preserving earlier audio order and speech prohibition.
No prompt, model, semantic authority, retry or execution authorization changed.
No new current document, environment variable, service or architectural term.

Evidence: `.chromie/acceptance/sc-ga-terminal-failure-20260914/`. Original episode,
four model transactions and one debug bundle retained. Four frozen native requests
reproduce the new GA failure before repair and all pass Schema/DTO/Host after;
122 focused tests / 155 subtests and 104 strict workflow tests pass. Full canonical
gate exits 0: 3,262 tests / 849 subtests, 145 benchmarks, 20 legacy tests and two
existing FastAPI warnings. All 6,000 frozen workflows pass with unchanged source
and fixtures; all 45 Level A scenarios pass.
The regression uses real terminal dispatch/session tracking with controlled
delivery for queued/playing/completed SC and explicit silence; no live audio claim.

The operator Host still holds its exclusive lock. Previously requested permission
to pause/rebuild for headless validation remains unanswered; no services were
interrupted or rebuilt by this task. New source is not loaded into that Host/Agent.
Next: after the pending pause authorization, rebuild/verify the current revision,
run/adjudicate the safe aggregate live cohort under one identity, retain one bundle,
and replay both reported weather episodes. Latency and #24/#32 closure remain open.
All follow-up repairs remain uncommitted. [HANDOFF](HANDOFF.md#ga-source-status-and-terminal-failure-repair--2026-09-14)
retains module I/O, exact evidence scope and resume details.

Latest discussion proposes separate resident Fast/Deep inference instances and
SC > GI > GA > Fast scheduling. No topology or priority change was implemented.
Current runtime is one SGLang instance, two running-request slots, with
SC=400, GI/Fast=300 and GA=200. Host stage arrows do not establish serial GPU
execution. Retain the existing measured-evidence gate before topology expansion.

## SC / GA decoder and workflow repair — 2026-09-14

Baseline `ec4a5c26` plus the uncommitted startup verification repair. The user's
SID `1d3e19dc` (`hi, will it rain today in Chongqing?`) did trigger SC concurrently
with GA/Fast. SC omitted a required progress kind and GA mistyped the location;
both outputs crossed permissive decoder schemas and failed stricter downstream
validation. Missing SC failure telemetry and an obsolete owner log obscured this.

The source repair compiles the existing SC truth/progress relation into explicit
decoder alternatives, directly constrains GA location types, preserves Host
validation, reports SC contract errors explicitly and retains failed/cancelled SC
stages. No semantic authority, model, prompt, retry policy or execution permission
changed. No new document, configuration variable, service or architectural term.

Evidence: `.chromie/acceptance/sc-ga-live-failure-20260914/` (local/Git-ignored).
The frozen two-request native baseline reproduces both errors; explicit branches
pass both real primary transactions plus DTO/Host materialization. Conditional-only
schemas failed native decoding and are retained as failed iterations. The frozen
12-case SC corpus passes before/after with bounded semantic review; all 45 Level A
ability scenarios and the unchanged 6,000-case offline workflow aggregate pass. Final canonical gate exits 0:
3,255 tests / 835 subtests, 145 benchmarks and 20 legacy tests; two existing
FastAPI deprecation warnings. [HANDOFF](HANDOFF.md#sc--ga-decoder-and-workflow-repair--2026-09-14)
records exact workflow, evidence scope and remaining validation.

No Agent rebuild or Host interruption was performed. The operator Host holds the
exclusive lock; an async request to pause it for rebuild/headless validation is
pending. Until that permission arrives, do not treat source/native-role checks as
a deployed whole-turn fix. Next: rebuild the Agent with saved operator overrides,
verify source/runtime identity, replay the originating request headlessly, then
run/adjudicate the safe directory-discovered live cohort. Existing #24/#32 closure
and rapid-response latency remain open. This patch remains uncommitted.

## Agent source verification repair — 2026-09-14

Baseline `ec4a5c268a557ac0f4281c668b1404edb96c57cc` on `main` is already pushed;
this follow-up remains local/uncommitted. The user's SID `037d1216` failed because
a reused old Agent image lacked `/social-cognition` and emitted retired
`presentation_commit` frames to the current Host. Startup checked environment
and health but omitted packaged-source agreement.

Startup now shares the existing closed-loop Agent content digest through
`scripts/capture_runtime_identity.py`, rejecting mismatch or unavailability
before Host launch. No semantic behavior, new configuration surface or legacy
compatibility was introduced. The user independently rebuilt while diagnosis
was underway; current Agent/Host source matches, and profile/API checks pass.
The agent did not restart services or interrupt the active Host.

Evidence root: `.chromie/acceptance/agent-source-startup-20260914/` (local and
Git-ignored). Canonical gate passed: 3,248 tests / 832 subtests, 145 benchmarks,
20 legacy tests; two existing FastAPI deprecation warnings. Focused checks:
24 tests / 12 subtests. All 45 Level A ability scenarios passed.
[HANDOFF](HANDOFF.md#agent-source-verification-repair--2026-09-14) records actual
module I/O, image/source identity, artifact paths and resume instructions.

The user's follow-up `hello` completed through SC without the deployment errors,
but first playback was 32.04 s and total time 34.84 s. Rapid response remains
open; this is observed runtime-log evidence, not an automated exact replay or
physical-audio qualification. The active Host lock prevented an independent
headless run. Once that Host is stopped, verify current runtime identity,
replay the originating input and run the safe aggregate live cohort before any
semantic or latency repair. Existing #24/#32 target closure stays open.

## Social Cognition implementation — 2026-09-14

Owner-authorized SC ownership transfer is implemented on `main`, base
`d5a7985ec74b02cd01c11b0d538fca7ae13a3498` as the pre-delivery baseline.
The owner authorized commit and push to `origin/main`. Resume from the latest
commit containing this checkpoint and HANDOFF; no future commit hash is assumed.
SC plans interaction across shared GI/Goal/Work/Evidence/Situation state; Work
Planner plans actions and communication needs. No additional approval is needed
for this agreed implementation. This delivery preserves the validated source;
no service restart or deployment was performed. [STATUS](docs/STATUS.md#social-cognition-migration) owns the four axes.

Implemented: independent GI fan-out; complete word-free Fast/Deep Work results;
exact Need-to-SC joins; confirmation and before/after-step barriers; independent
trusted Situation initiative; shared history/Memory/Mind/Goal/task context;
delivery-qualified dialogue; cancellation/freshness checks; qualified optional
expression; SGLang foreground priority 400 versus ordinary Planner 300. Required
communication remains auditable; optional SC cannot hold independent Work.
The former presentation DTO/schema/stream and executable Planner-wording builders
are removed. SC replaces the former Situation endpoint. Quiet text-console work
is preserved with Soridormi enabled and ASR bypassed.

Evidence root: `.chromie/acceptance/social-cognition-mainline-20260914/`.
These raw artifacts are local and Git-ignored; a clone receives source, frozen
fixtures and the evidence summary in HANDOFF, not the raw runtime records.
Pre-commit comparison against `final-worktree-identity.json` found no intervening
source changes. Only delivery documentation was subsequently refreshed.
The discussion about generalization did not introduce another implementation
change or establish new generalization evidence.

- `canonical-sc-closed.log`: exit 0; 3,245 tests / 820 subtests, 145 benchmarks
  and 20 legacy Agent tests pass, including pinned static, policy, ownership,
  configuration and docs gates. Two existing FastAPI deprecation warnings.
- `workflow-sc-closed/`: final 6,000-case strict aggregate after explicit fixture
  migration: all 6,000 pass and source hashes remain unchanged. Original expected
  outcomes are preserved. This is controlled architecture evidence only.
- `general-ability-sc-complete/`: all 45 Level A scenarios pass.
- `native-final-sc/`: 12/12 Schema/DTO/Host and semantic cases;
  `native-work-roles-complete-order/`: 8/8, including exact causal ordering.
  `recorded-sc-final/` and `recorded-work-final/`: current production packets
  match those native packets exactly; recorded replies pass current resolvers.
- `workflow-adjudication-current.json`: actual owner I/O, earliest wrong boundary,
  repairs, native/frozen-fixture provenance and limits.

Target evidence remains separate from implementation completion. A subsequent
native attempt (`native-sc-retired/`) produced only connection errors; no Docker
services were running on inspection. No stop cause is inferred. Earlier native
role proofs use controlled upstream state/catalog. No deployed-current Agent,
end-to-end native GI→SC/Work cohort, latency/contention improvement, physical
microphone/speaker or robot proof is claimed. Existing #24/#32 target closure
remains open; do not resume with another architecture migration.

Next target-validation work: follow the existing service profile in HANDOFF,
verify deployed source/runtime identity after a deliberate rebuild, then run the
complete safe automated live cohort and retain/adjudicate one debug bundle.
Paired contention and physical evidence require their existing declared profile
and supervision. Do not treat the offline packet replay as fresh inference.

## Previous documentation stage — Social Cognition, 2026-09-14

Repository `main`, base `d5a7985ec74b02cd01c11b0d538fca7ae13a3498`; local changes
remain uncommitted. The owner agreed to Social Cognition as an independently
valuable communication responsibility and requested the related documents.
The [Charter amendment](docs/PROJECT_CHARTER.md#social-cognition--accepted-target-2026-09-14)
now transfers target speech authority from Planner; GI/GA and Planner Work,
Memory, Host and Soridormi responsibilities remain distinct. The canonical
diagrams/principles, lifecycle, acceptance, status and migration order are updated.
This is the authorized documentation exception to the surface freeze, not a
claim that new runtime behavior exists or #24/#32 closed.

| Implementation | Automated verification | Target validation | Release readiness |
|---|---|---|---|
| Target documentation only; current source retains combined Fast speech/Work and Goal-free Planner communication. Earlier text-console transport edits are preserved. | Canonical gate passes 3,223 tests / 818 subtests, 145 benchmarks, 20 legacy; policy/static/config/docs/ownership pass. No Social Cognition implementation or model cohort is tested. | Not run for this amendment; no runtime/provider/model promotion or restart. | Development only; migration and prior #24/#32 evidence blockers remain open. |

Next work follows [Social Cognition migration](ROADMAP.md#social-cognition-migration):
settle exact request/result, coverage, depth, confirmation and auxiliary-anchor
contracts; migrate initial/result/control/Goal-free communication as one coherent
owner transfer; remove Planner's writable reply fields; then qualify both owners
and their combined timing/behavior. Use the
[source inventory](docs/COGNITIVE_TURN_LOOP.md#source-migration-inventory) and
[acceptance matrix](docs/ACCEPTANCE.md#social-cognition-acceptance). Do not add a
new microservice, separate state store, same-authority reviewer or permanent
two-writer switch. Performance benefit remains a hypothesis requiring paired
first-response and task-completion measurements under actual SGLang/TTS contention.

The prior checkpoint below is retained evidence for its revision. Its Planner
speech ownership is the old implementation, not the amended target. Exact
local validation paths and preserved dirty scope are in [HANDOFF](HANDOFF.md).

## Previous delivery boundary — native continuation and #67, 2026-09-14

Current focus: Goal-driven single-authority architecture and current-revision
evidence closure. Repository `main`; pre-delivery base
`d7c7f27767d8e137edbf2aa165a11b81d6282527`.
Resume from the latest main commit containing this checkpoint and [HANDOFF](HANDOFF.md).
The owner authorized continued unfinished work, bounded fixes, project decisions,
GitHub reports/Issue closure, commit and push. No additional permission is needed
for that existing scope. Physical microphone/speaker/robot evidence remains supervised.

#67 closes with this delivery: GI Host now applies the existing duration scalar
provenance boundary to distance. Unsupported strings, nested values, arrays and
booleans reject before downstream admission. It neither invents replacement values
nor invokes another model. GI still owns complete WHAT, GA continuity, Planner
HOW/speech and Runtime execution. No production prompt/Schema order change, new
runtime switch, profile, document or semantic authority. Document counts stay
102 current Markdown / 15 core-path. The [audit](ARCHITECTURE_AUDIT.md#native-gi-continuation-and-distance-containment--243267)
owns actual per-module I/O, triggering failure, containment mechanism and limits.

| Implementation | Automated verification | Target validation | Release readiness |
| --- | --- | --- | --- |
| #67 rejects distance copied from a prompt example absent from admitted text/context; duration behavior preserved. | 91 focused GI tests / 115 subtests. Canonical 3,217 tests / 818 subtests, 145 benchmarks, 20 legacy; pinned checks pass. Level A 45/45; unchanged 6,000 replay passes. | Four 44-case native GI cohorts / 313 calls remain semantically unqualified. Rebuilt Agent matches all 113 source files. One 51-case native text/MuJoCo aggregate stopped: 2 failures, 1 interrupted, 48 unrun. | Development only. #24/#32 remain open. No model/streaming target/LoRA or physical promotion. |

Three pre-fix native cohorts used unchanged qwen3.5:4b on Ollama 0.33.2,
`think:false`: baseline 71 calls, source-first 87, source-only 84. Complete transaction
review: baseline 3 pass / 2 meaning-correct with provenance extent unqualified / 39
fail; candidates 0 and 1 passes. Both order candidates are rejected; neither is
adopted. All 242 original replies passed old Schema/Host. The patch rejects exactly
six unsupported distance strings while the other 236 admission results remain.
The final production-order cohort has the same 71 parsed raw replies as baseline;
one invalid distance now rejects, 43 final decisions remain. Mechanical containment
is proven; general meaning and numeric normalization are not certified.

The native live aggregate uses current generated **interactive** budgets and
stdin/discard transport with execution enabled only against headless MuJoCo. The
first old qualification-env/current-profile identity capture correctly failed;
a fresh diagnostic transport snapshot uses the existing budget synchronizer.
Runtime identity `b078a0b56709653f160d5c6bb805281cb4cac59a4ab0cddd11db17ea76d9c190`
is dirty-source diagnostic evidence, not clean-revision target qualification.
Both source trees stayed unchanged throughout the cohort.

The first primary GI fused walk/nod/turn and invented actor uncertainty; deeper GI
split them, but Fast changed 0.2 to 0.02 and Host rejected numeric provenance. The
second primary GI fused gaze/blink; Fast emitted an invalid auxiliary anchor and
Host rejected it. The third case was interrupted; two late GI replies were retained.
Nine native Agent calls were reviewed. The old private watcher missed model_contract;
reviewer stopped it, retained one bundle and corrected only the next-run watcher.
Post-stop simulator status: safe_idle=true, active_task=null, active_lanes={},
fallen=false, emergency_stop=false. Owned simulator/MCP were stopped. Agent/TTS/LLM
remain healthy; ASR absent. No audible output or physical action was tested.

Evidence: `.chromie/acceptance/issue24-source-order-20260914/`, including all frozen
packets/raw replies/reviews, red/green regression, full gates, 6,000 replay,
iteration-01 identity/source hashes/native calls, the single live-stop bundle and
post-stop status. Transfer archive: `/home/chromie/Downloads/chromie_issue67_native_continuation_20260914.tar.gz` (265,500,309 bytes), SHA256 `22eab7ac1445fbb9f0df183586a9df82d77f0f7ca852f4139e8b74237b027f53`; 11,249 indexed members verified.
Previous immutable 6,000 evidence remains in
`/home/chromie/Downloads/chromie_workflow_6000_20260913.tar.gz`; SHA256
`18295607616d0bef24c484726f4f0b75cf957ca9181e1384cf49f9de26f21e1a`.
Its corpus manifest remains
`1d9f5d3d35cf8b993ea2fe6703ac30adac2838514d8e7a27a9bd5431775a0773`.
All authored simulator references are training-ineligible and not independently
reviewed; 60 families expanded to 6,000 cases are not 6,000 independent inferences.

Next work:

1. Keep #24 native semantic/model-role qualification and #32 stream/target evidence
   open. Use the frozen full-transaction method; do not repeat rejected ordering
   controls or treat deeper repair of false uncertainty as primary correctness.
2. Diagnose the first native boundary for complete atomic meaning, exact typed
   parameters and correct uncertainty; do not weaken conservation/anchor checks,
   add a phrase router, or add a same-authority critic/repair invocation.
3. For new live evidence, regenerate/verify matching current budgets, rebuild and
   verify source, bind one identity and run the full discovered cohort unchanged.
   Stop on hard model_contract/provenance/integrity faults; one bundle; review all
   retained cases. Follow canonical gate → supervised narrow voice → default target
   evidence closure before release claims. HANDOFF owns exact commands.
4. Before LoRA, independently review positive references, exclude injected faults,
   add hidden semantic-family holdouts and qualify isolated then combined real roles.

No follow-up is scheduled. Preserve Soridormi's untracked upstream workspace.
