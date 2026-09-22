# Chromie Current Status

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
