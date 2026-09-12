# Chromie project principles and implementation audit

**Updated:** 2026-09-13. **Pre-delivery base:** `6f726ce32f2d69d6fd167ad600cfb7f9eb599536`, `main`. The exact resume revision is the delivery commit containing this report, [checkpoint](DEVELOPMENT_CHECKPOINT.md), and [handoff](HANDOFF.md).

**Audience:** project owner and maintainers reviewing or continuing the Issues. **Owner:** the project owner owns principle decisions; each linked Issue owns its acceptance. This report records evidence and decisions under the existing [Charter](docs/PROJECT_CHARTER.md), [Status](docs/STATUS.md), and [Roadmap](ROADMAP.md).

The owner explicitly authorized implementation, principle decisions, bounded maintenance, publication and closure of solved Issues in this session. The repairs preserve GI ownership of WHAT, GA ownership of Goal continuity, Planner ownership of HOW/speech, and Runtime ownership of execution and Evidence. Three decisions follow natural, grounded behavior: reporting a cancellation does not fulfill the original request; remembering a future intention is different from doing it now; optional learning follows the ready response. None needs another semantic reviewer or a phrase-based router.

Earlier source repairs and deterministic verification are implemented; their revision-bound evidence is retained below. The latest owner-approved work adds offline architecture replay and repairs the prerequisite/count contract under #59. New-request readiness remains #60; #24/#32 remain open. The preceding native GI investigation retained 226 executions/254 calls without a qualified repair. No new native model, aggregate live, streaming, audio or physical proof is claimed by the replay work.

## Offline workflow replay — #59

The owner explicitly requested architecture/workflow/contract tests excluding model
ability. Five cases use GPT-6 Astra-authored reference replies, reviewed in the same
task, through a strict loopback model HTTP service. They exercise GI → GA → Fast or
Deep → real Schema/DTO/Host → state/Capability Runtime, plus result/due re-entry.
Initial admission and role scheduling are explicit driver inputs. Providers, speech
receipts, wall time and UUIDs are controlled. No native inference or keyword-based
semantic simulator runs. References and whole request packets are frozen separately
from executable expectations; unchanged requests are required to receive a reply.

The initiating probe is “Blink twice if rain is forecast in Hangzhou.” Its authoritative
Goal has body-action mode, count 2 and location Hangzhou. Deep's correct current Work
is a weather query, with both satisfaction assessments retaining the deferred blink.
The first incorrect contract boundary was the dynamic Schema: its generic count
filter removed the weather candidate because it has no repetition argument. The
scripted reply was independently Schema-invalid; when supplied to the actual parser,
the Host count guard rejected it too. Removing only that guard exposed the generic
numeric guard's same demand. This is one stage-vs-effect obligation ownership defect,
not evidence of bad model reasoning. Runtime never ran the rejected initial Plan.

| Actual episode boundary / owner | Authoritative input → observed output before fix | Expected output / correlation / verdict |
| --- | --- | --- |
| Test admission → GI WHAT | Exact synthetic turn/source tokens; reference emits one conditional body effect, count 2, Hangzhou | Complete WHAT, no Capability/HOW. Final reviewed source span t0–t7 includes condition/place. Correct fixture; initial short span was a reference defect corrected before final freeze. |
| GI → GA continuity | Accepted responsibility r1 → one new Goal carrying count/location | Exactly-once mapping and same meaning; real committed Goal ID binds the replay placeholder. Correct. |
| Catalog/Goal → Deep dynamic Schema | Weather is declared safe_read; blink accepts count; generic count filter excludes weather for this Goal | Retain a representable prerequisite query. Earliest incorrect contract. |
| Primary reply → parser/DTO/Host | Weather lookup `{location: Hangzhou}`, acquire_information, partial 0.5, both unmet obligations → count rejection, then numeric rejection when isolated | Accept complete acquisition Work while keeping Goal open. Original containment prevents execution but rejects valid progress. |
| Accepted Plan → Runtime/provider, after fix | Same query is admitted; controlled forecast returns rain true/false with request/Goal/Plan provenance | Exactly one weather call, no blink before Evidence. Real result reconciliation retains open Goal. Correct. |
| Terminal Evidence → actual Host re-entry → Fast | Trusted forecast and exact source Plan → blink count 2 when true; delivered no-effect response when false | Same Goal/scope; wrong forecast content fails frozen request matching. Correct; semantic choice itself is supplied by the reference. |
| Runtime execution/speech receipt → state | True branch executes exactly two blinks; false branch has no blink and a controlled delivered response | Goal satisfied only after terminal execution/delivery. Correct within controlled-provider Level A scope. |

Fix: the Schema retains declared information-acquisition candidates. Host reuses the
existing whole-Plan acquisition validator (available executable information provider,
valid arguments, expected outcome and both unmet assessments) to scope the deferred
effect count/numeric exception. Supplied argument/provenance checks still run; the
actual blink still requires count 2. Merely labeling a state-changing action as an
acquisition or claiming completion cannot obtain the exception. Fast's direct catalog
remains bounded; cross-domain composition stays with Deep. No prompt, model profile,
extra semantic call, runtime flag or semantic authority is added. The existing #51
Charter rule is clarified rather than replaced.

Coverage is five episodes/18 local model-shaped HTTP calls: normal, conditional true,
conditional false, retained scheduled Goal across restart/due/once-only wake, and
in-flight cancellation. Cancellation stops current execution and leaves its unmet
Goal open. The delayed case starts from an explicitly seeded prior Goal: GI's current
Schema rejects `ready_at`, while Planner consumes that exact typed binding. This is
the separately open [#60](https://github.com/TimeTreker/chromie/issues/60) new-request
contract gap; a successful seeded timer is not new-request scheduling evidence.

Verification: canonical gate passed 3,131 tests/794 subtests, 145 benchmarks and 20
legacy tests, with pinned static/policy/config/ownership checks. Level A remains
45/45 cases across 15 classes. The 26 added tests exercise frozen HTTP episodes,
request/order/Schema/options mismatch, unused/extra/unbound replies, wrong terminal
Evidence, rejected missing/wrong action count, acquisition counterexamples and the
documented readiness gap. Final reference-span correction is rerun in the focused
suite and full replay. No model-ability or live qualification follows from these results.
Preparation failures and harness/oracle corrections are retained separately from
production defects; async due wake has no session ID, which the driver now preserves.

Commands and fixture ownership are in [benchmarks](benchmarks/README.md#offline-workflow-replay).
Private evidence is `.chromie/acceptance/workflow-replay-20260913/`; tracked raw packets,
responses and corpus hashes are in `benchmarks/integration/scenarios/`. Current source
and corpus hashes, per-call observations, state snapshots and failures accompany each
run. #59 may close on delivery; #24, #32 and #60 remain open. New current Markdown
owners: 0 (102 → 102); core reading path: 15 → 15; no environment-variable growth.

## Native Goal Interpretation boundary investigation — #24

The owner agreed to investigate the retained walk/nod/turn failure before continuing streaming qualification. The complete transaction was audited against the Charter, interaction contract and qualification method before changing an experimental packet. GI must identify every independent WHAT, preserve material modifiers and exact source provenance, and express explicit ordering. It cannot select Goals, Capabilities or HOW. The current prompt already requires this complete primary decision; the dynamic Schema admits a correct three-effect result. All 44 frozen reference outputs pass the current Schema and Host, and all 88 original primary/deep packets match the earlier retained Qwen4b packets exactly.

The production request uses Ollama 0.33.2, `qwen3.5:4b`, top-level `think:false`, `stream:false`, temperature 0, top-p 0.9, **16,384 request context and 512 output tokens**. The generated environment's 32k label does not override those actual packet values. Model metadata also supplies presence penalty 1.5 and top-k 20; native sampler logs confirm the tested penalty settings. The original live failure stopped normally after 212 output tokens. Missing source input or output truncation does not explain that particular failure.

| Order / owner | Actual input, output and handoff | Boundary judgment / expected result |
| --- | --- | --- |
| Gateway provenance → GI request | Admitted walk at 0.2 speed for 10 seconds, then nod twice, then turn left; complete original text and ordered tokens `t0`–`t19` reach the primary packet. The direct diagnostic starts from this retained request, not a new Gateway admission. | Correct retained input for this case. Preserve all three predicates and their modifiers. |
| GI prompt/context → dynamic Schema → native provider | Complete WHAT instructions, bounded Mind/context and exact current-token Schema are sent. No reference answer, score or expected decomposition enters the candidate messages. | Reference three-effect output is representable and passes both Schema and Host. Successful representation alone does not prove the model follows it. |
| Primary GI semantic result | Original live call emits one responsibility with the whole turn in `subtype`. Fresh unchanged baseline emits one responsibility with only the later nod/turn clauses in `subtype`; no count or coordination. Both are complete provider responses. | **First observed wrong output:** independent effects are merged into a modifier. Expected three responsibilities, correct speed/duration/count/direction, separate predicate provenance and explicit sequence. |
| Parser / normalization / DTO / Host | Original whole-turn echo is rejected before downstream admission. Fresh partial echo passes Schema and Host and returns a decision. Mechanical normalization does not create the missing effects. | Correct containment of the literal whole-turn case; incomplete containment of semantic omission. A returned decision is not proof of complete meaning. |
| Designated deep cognition | Primary compound outputs declare no unresolved meaning, so no deep call occurs. Other cohort cases may invoke the existing one source-based deep authority once. | The current uncertainty branch is followed. Confidence alone cannot replace material uncertainty or justify a semantic critic under Charter principles 30–31 and 34. |
| Host endpoint → GA / Planner / Runtime | Original live call `llmcall_goal_interpreter_d2278e1d3bfa4a1b` ends HTTP 503 `goal_interpreter_unavailable`. GA, Planner and Runtime are not invoked. Direct-role experiments stop at the GI return/error and never enter those modules, even when Host accepts. | Original live containment prevents execution. Downstream behavior for the newly accepted wrong decisions is unproven, not a live result. |

```text
retained admitted request -> exact GI packet -> native primary result
                                              |
                         +--------------------+--------------------+
                         |                                         |
                 whole-turn hidden effects                 partial hidden effects
                         |                                         |
                   Host rejection                         Host returns wrong meaning
                         |                                         |
                 original live HTTP 503                     diagnostic ends here
                 no GA / Planner / Runtime                 no downstream invocation
```

Five complete 44-case cohorts and six cold controls ran sequentially against unchanged source. Each experiment's packets were frozen before inference. Each case uses one primary call, with at most the existing source-based deep delegation for an accepted unresolved primary result; there are no retries, critics or semantic repair calls. Every raw output was reviewed after inference. Reviews are post-hoc and non-independent. The 44 cases cover independent/single effects, modifiers, mode contrasts, bilingual/mixed-language inputs, explicit source bindings and material ambiguity; they do not constitute full GI continuity/lifecycle qualification.

| Experiment / exact comparison | Cases / calls | Final Host decisions | Meaning finding |
| --- | --- | --- | --- |
| Unchanged Qwen3.5:4b baseline | 44 / 66 | 43 | Compound and concurrent effects still merge; mode, binding and provenance failures remain. Partial hidden clauses evade the whole-turn guard. |
| Append a derived Schema structure to baseline messages; full decoder Schema unchanged | 44 / 44 | 44 | Structure acceptance improves without complete meaning. Compound effects remain merged and modifiers move into incorrect fields. |
| Baseline with only presence penalty 1.5 → 0 | 44 / 47 | 43 | Merging, missing count, incorrect modes and bindings remain. Some individual decompositions improve, others regress. |
| Structure experiment with only decoder format changed to plain JSON; adjudicate against original full Schema/Host | 44 / 44 | 0 | Every output omits per-responsibility confidence; raw compound output still merges nod and turn. Removing constrained decoding does not produce a correct transaction. Diagnostic only; no proposed validation relaxation. |
| Presence-zero experiment with only model changed to installed `qwen3:4b-instruct-2507-q4_K_M` | 44 / 44 | 43 | Three compound effects appear, but ordering is missing and speed becomes distance; invented/misassigned bindings remain. One reversed source span is correctly rejected. |
| Six representative baseline cases with model absent before every call and `keep_alive=0` | 6 / 9 | 6 | Fresh model loads still merge effects, confuse query mode and invent obligations. Reused resident state is not required for these failures. This is not a claim that all provider/cache defects are excluded. |

All 254 calls finish normally, with top-level `think:false` and no separate thinking response field. Original full-Schema validation passes 210 calls; plain-JSON's 44 failures remain failures. Strict dimension counts are 5, 2, 5, 0, 0 and 0 respectively, **not semantic pass rates**: lexical/span oracle limitations and missed extra bindings were separately reviewed. No candidate qualifies regardless of those counts. Some schema-valid outputs put self-deliberation in `unresolved`; absence of a separate thinking field does not certify semantic discipline.

The structure experiment was motivated by [Ollama's structured-output guidance](https://docs.ollama.com/capabilities/structured-outputs). Appending the full source-enumerated Schema would fail the actual conservative preflight for all 88 packets; that oversized variant was never inferred. Only a derived structural outline was tested, with exact lexical constraints preserved in the decoder. Native responses use 16k request context throughout. Sampled peak GPU use was 9,029 MiB with at least 6,917 MiB free and at most one resident model. These are sampled direct-role observations, not streaming latency, proven cache hits, concurrent TTS qualification or a combined-profile pass. The original development Qwen3.5:4b resident was restored afterward.

**Disposition:** the confirmed failure mechanism is incorrect raw semantic decomposition/binding followed by incomplete mechanical containment. Attribution among the remaining primary prompt/context representation, model and provider behavior is unresolved; these experiments do not establish a model intelligence ceiling. There is no qualified production repair to deliver. Keep #24 open, and keep #32 open for native typed-stream/terminal consistency, cancellation, latency, TTS and shared-resource evidence. No principle amendment, phrase-based semantic splitter, confidence-threshold routing or second semantic reviewer is justified by this evidence.

Next, test one predeclared primary-packet/context or native-provider hypothesis while preserving the complete meaning contract. Retain these 44 cases as regressions, add independent coverage for the chosen hypothesis and missing GI continuity/lifecycle boundaries, and qualify the whole role before downstream/combined-profile promotion. After a qualified repair, rebuild/verify the revision and rerun the full live cohort, then the narrow supervised voice/default target sequence. Repeating the already failed controls or weakening admission is not acceptance.

Evidence: `.chromie/acceptance/issue24-gi-boundary-20260912/`, including frozen driver versions, packets/raw replies, per-case reviews, model digests, sampling, comparison summary and explicit metadata corrections. No raw private Mind/provider payload is published. The [handoff](HANDOFF.md) records the separately transferable archive and exact resume commands. The canonical source gate passed again: 3,105 tests/794 subtests, 145 benchmarks, 20 legacy tests, pinned static/config/policy/ownership checks. Prior Level A and live results below remain prior evidence; no behavior changed or new general-ability/live result is claimed by this investigation.

## Issue disposition

| Finding | Implemented resolution | Qualification boundary |
| --- | --- | --- |
| <a id="a01"></a>A01 — [#49](https://github.com/TimeTreker/chromie/issues/49) | Previously delivered at `c1585e78`: atomic complete-resource acquisition. | Closed; preserve cancellation while waiting and cross-interaction exclusion. |
| <a id="a02"></a>A02 — [#50](https://github.com/TimeTreker/chromie/issues/50) | Previously delivered at `9be7b23f`: complete required Planner context or rejection before inference. | Closed; complete retained Goal meaning remains required. |
| <a id="a03"></a>A03 — [#51](https://github.com/TimeTreker/chromie/issues/51) | Previously delivered at `f5522f87`: complete acquisition stage with honest unmet downstream obligations. | Closed; this delivery strengthens serialization and duplicate-response regressions. |
| <a id="a04"></a>A04 — [#52](https://github.com/TimeTreker/chromie/issues/52) | Separate exact cancellation status, original Goal satisfaction, and read-only capability availability. Fast and Deep admit truthful zero-work reports. | Bilingual four-status/provider/depth contrasts, token revocation and independent-sibling tests; final Fast 204/Deep 40 and cancellation16 per tier pass. |
| <a id="a05"></a>A05 — [#53](https://github.com/TimeTreker/chromie/issues/53) | Result planning precedes bounded optional Reflection. Existing background lifecycle owns cancellation, timeout and shutdown. | Event-order and lifecycle proof; no target latency claim. |
| <a id="a06"></a>A06 — [#54](https://github.com/TimeTreker/chromie/issues/54) | Actual Host requests supply approved Mind. Retire current-turn advisory re-entry and its handled-Evidence bypass. | Advisory records cannot cause another Planner decision; only applied Memory counts as adaptation. |
| <a id="a07"></a>A07 — [#35](https://github.com/TimeTreker/chromie/issues/35) | Reconcile staged/readiness reference regions; remove invented unspecified subjects; qualify complete roles in Fast-then-Deep order. | Offline fixed `gpt-5.6-sol/high` surrogate only; native-provider and target claims remain #24/#32. |
| <a id="a08"></a>A08 — [#55](https://github.com/TimeTreker/chromie/issues/55) | Acceptance labels old voice evidence by revision; capability README derives counts and uses current registry ownership. Current status and handoff are consolidated. | Historical evidence retained, four status axes kept separate. |
| Process — [#56](https://github.com/TimeTreker/chromie/issues/56) | Existing strict Mypy gate covers the whole contract package, including future files. | 30 contract files plus three tooling files locally; Python 3.11/3.12 CI passes on implementation commit `8aa3f499`. |
| Process — [#57](https://github.com/TimeTreker/chromie/issues/57) | Review actual acquisition → outcome → continuation → delivery seam; keep its existing atomic owner. Add derived-property/Host-projection and duplicate-suppression regressions. | No extraction justified by current evidence; size remains a review measurement. |
| New — [#58](https://github.com/TimeTreker/chromie/issues/58) | Future-bound Goals wait with zero current Work and an exact timer. A trusted wake can recover its persisted open Goal without a fresh GA decision. | Before/at/after due, restart, one-shot dispatch, cancellation, stale scope and ready sibling tests; final Fast 204/Deep 40, six due cases per tier and six additional Deep waiting cases pass. |

The owner's authorization permits these bounded repairs and maintenance alongside the existing evidence-delivery line. It does not change the requirement for current live voice/default target evidence. No new product feature, runtime flag, architectural layer, standing document, or semantic owner was introduced.

## Cancellation workflow — #52

The retained episode is an 8 p.m. reminder request. Its canonical stateful-effect Goal remains the same across `cancelled`, `not_cancelled`, `uncertain`, and released stale confirmation; the provider may independently be available or unavailable. These are fixture dates and capabilities, not newly scheduled user reminders.

| Order / owner | Material input and prior wrong output | Repaired output and downstream contract |
| --- | --- | --- |
| Trusted control + Goal state | Exact scoped status and original unmet reminder Goal. | Inputs remain authoritative; control reporting grants no Work or new confirmation. |
| Planner context / catalog | Response-only permission emptied the catalog and described the original effect as provider-free speech. **First wrong boundary.** | Preserve WHAT and full read-only capability facts while exposing no effectful choices for the control scope. |
| Prompt / dynamic Schema | Correct Fast `respond` at satisfaction 0 was rejected; Deep could report false provider absence. | Both tiers can author exact status with explicit original unmet obligations. Independent Goals retain ordinary execution/satisfaction checks. |
| Host validation | Restricted scope and global capability absence were conflated. | Reject owned Work, auxiliary actions, timers, cancellation commands, new confirmation and false fulfillment for that scope. Do not rewrite the model's meaning. |
| Confirmation / Runtime / state | Audit-only probe did not prove token revocation or delivery. | Tests dispatch actual named cancellation, revoke the old token, preserve an independent sibling, and replay the real adapter/Runtime with fake providers. Speech completion does not create the cancelled reminder. |

The four control statuses × two languages × two provider states are frozen independently of the original four cases. Original outputs and oracle identities remain retained. Reports about unavailable confirmation are factual prerequisites, not new confirmation requests. Some candidate wording remains technical; no live naturalness or audible delivery claim is inferred.

## Reflection workflow — #53/#54

| Order / owner | Before | After / evidence |
| --- | --- | --- |
| Runtime outcome / Host closure | Exact completed/failed results produce a slow opportunity. | Immutable outcome, exact Goal scope and source Plan retained. |
| Host scheduling | Awaited optional Reflection before calling the ready result Planner. **First wrong scheduling boundary.** | Await result planning first; then schedule one bounded Reflection worker using the existing task owner. A blocked stub cannot delay Planner entry or completion. |
| Host Mind projection | Actual Reflection request omitted approved Mind. **First wrong input boundary.** | Only approved profile identity/version, worldview, household values and core principles enter the request; arbitrary private material stays out. |
| Reflection result / state | Advisory presence could bypass handled-Evidence suppression although the prompt omitted it. | Remove the current-turn consumer and bypass. Diagnostic replan/clarify/correct proposals cannot trigger another Planner invocation. Only an actually applied bounded Memory proposal counts as adaptation. |
| Cancellation / shutdown | Optional learning shared the response dependency. | Busy-worker suppression, bounded deadline, cancellation propagation, shutdown draining and stale-generation rejection are tested. Terminal outcomes cannot reopen. |

```text
trusted execution outcome -> eligible result Planner -> response delivery
                                      |
                                      +-> bounded optional Reflection -> allowed future Memory
```

The event-order proof uses real aggregate closure with controlled model dependencies. Physical latency and provider preemption when a new user turn arrives during background inference remain target-profile evidence under #24; logical scheduling alone does not qualify the shared GPU.

## Future intention and restart workflow — #58

The six original English/Chinese weather cases bind `ready_at=2099-09-04T19:00:00+08:00` (`4092202800000` ms) and explicitly prohibit an early query. The previous contract required current executable Work alongside a timer. All six exact model outputs passed Schema/Host checks yet dispatched an immediate weather lookup through the real adapter/Runtime with a fake provider. Goal reconciliation correctly kept the information Goal open; it could not undo early dispatch.

| Order / owner | Actual boundary and evidence | Repaired contract |
| --- | --- | --- |
| Canonical Goal | Exact future time, place/date/period and Responsibility provenance. | Preserve original WHAT; catalog availability does not make the Goal ready. |
| Planner contract / Schema | Required an executable step even when the requested work was not ready. **Earliest timing conflict.** | `respond` plus one exact Goal/time condition, original Goal unmet, no current owned Work. Ready independent siblings and monitors of already-running Work retain their meanings. |
| Resolver / Host | Prompt, Schema and validation could observe different clock instants. | Capture readiness once for the primary transaction; a clock tick during inference cannot reinterpret its output. Host independently rejects early Work or fake satisfaction. |
| Runtime / speech state | Old lookup dispatched now; timer only woke cognition later. | Fresh Fast outputs replay with zero provider dispatch, original Goal open after speech, and exactly one due opportunity. |
| Durable state / wake loop | Timer and Goal survive restart and wake once, but Planner rejected the wake because it expected a fresh GA result. **Second reproduced handoff defect.** | Bind matching trusted opportunity to exactly one current open snapshot per Goal. Reuse the existing Goal projection; do not synthesize a GA decision. |
| Host re-entry / Planner / Runtime | Restart regression originally failed before inference despite valid saved Goal provenance. | Real Host re-entry now admits one fresh lookup at due, preserves Responsibility and source Plan, and does not redispatch on repeated wake or another restart. Missing, mismatched, duplicate or terminal snapshots fail before any model call. |
| Primary clock projection | Six actual persisted-wake model packets omitted the fact that the time had arrived; all models waited again. The first helper-only patch still omitted that text in actual packets. **Third reproduced input defect.** | Both tiers now render the captured Host already-arrived Goal/time map in the primary prompt. Two actual-packet tests distinguish before/at due; six fresh Fast and six Deep outputs each perform one exact acquisition, retain final delivery as unmet and create no replacement timer. |

The bilingual restart regression uses real persistence, wake-loop entry, Host request construction, Planner Schema/Host validation and Runtime dispatch with scripted models/providers. The injected clock is explicit; no year-2099 live or physical evidence is claimed. Six actual Host requests are additionally frozen for target-blind role inference. This closes the demonstrated authority gap without adding a scheduler, retry chain, or new Goal identity.

## Lifecycle ownership and the external review — #56/#57

The friend's review was read before continuing. Its in-flight #51 test counts and proposed numeric ceilings are historical suggestions, not current project authority. The useful concerns were evaluated against source and observed workflows:

| Review point | Decision and evidence |
| --- | --- |
| Reading burden | Use existing report/status/checkpoint/handoff owners, with immutable links to previous records. There are still 102 tracked Markdown documents and a 15-document core reading path; no extra current document was added. |
| Numeric size limits | Preserve owner-approved #45: file/method counts inform review, but do not decide correctness or force extraction. |
| Runtime class size | `VoiceAssistant`: 7,549 → 7,524 file lines, 104 → 105 methods in the reviewed Reflection change. `ConversationStateManager`: 6,172 lines / 105 methods unchanged. These measurements do not prove a defect or a need for a new manager. |
| Real lifecycle seam | The conditional-weather episode moves through acquisition, immutable outcome, derived continuation, exact Host re-entry, and confirmed effect or delivered explanation. Goal reconciliation, outcome attachment and pending bookkeeping must remain atomic. Existing closure/reconciler/state owners already separate responsibilities; extraction would add handoffs without an independently owned invariant. |
| Derived continuation | A new executable regression serializes the outcome, proves the derived property is omitted on wire, recomputes it on decode, and checks both Host projections. A model-supplied override is rejected. |
| Narrow typing | Expand the existing gate to the complete `shared/chromie_contracts` package. All 33 enforced files pass locally; no blanket ignore or checked-path removal. CI verifies supported Python versions. |
| Qualification last | Keep live qualification active. The unchanged baseline and repaired-source aggregate both stop at GI; downstream source repairs do not hide that failed prerequisite. |
| Ruff families / large test files | No evidence justified unrelated rule changes or mechanical splitting. Review scenario and owner boundaries when touching those files. |

The retained lifecycle episode's module I/O is: admitted conditional Goal → Planner authors a complete prerequisite read with the condition/effect unmet → fake provider returns correlated forecast → Runtime closes only that Work → outcome reconciliation keeps the Goal open and derives continuation → Host forwards exact immutable Evidence once → the same Planner decides the conditional effect or truthful no-effect explanation → confirmation/execution or complete speech delivery closes the appropriate obligation. Already handled or delivered Evidence cannot bypass suppression merely because legacy Reflection advice exists.

## Evidence ledger and remaining qualification blockers

R = `.chromie/acceptance/remaining-issues-20260912/` (private, ignored; transfer separately). Source, corpus and packets were frozen for each model cohort. The fixed offline candidate is `gpt-5.6-sol/high`, one target-blind primary call per case, no retry, output repair, case substitution or production critic. Reviews are post-hoc and non-independent.

| Evidence | Observed result | Claim limit |
| --- | --- | --- |
| Canonical source gate after persisted-Goal repair | 3,105 tests / 794 subtests, 145 benchmarks, 20 legacy tests; pinned static/config/policy/ownership pass. | Final delivery gate recorded in handoff; two existing FastAPI warnings. |
| Future-readiness module | 50 passing cases, including bilingual real Host restart, 14 pre-inference rejection contrasts and two actual primary packet clock contrasts. | Scripted models, fake providers and explicit clock; source evidence. |
| Level A ability suite | Final source run passes 45 distinct cases across all 15 classes. | No live behavior inferred. |
| Fast full 1 | 203 Schema/Host; semantic review: 197 pass, six early-work failures, one malformed JSON reply. | All original results retained. |
| Fast full 2, unchanged replication | 204 Schema/Host; semantic review: 198 pass, six early-work failures. | A replication, not a claimed fix for the isolated JSON failure. |
| Fast full 3, waiting repair | 204 Schema/Host/frozen hard and semantic review; six waiting outputs pass Runtime replay. | Predates persisted-Goal wake repair. |
| Deep full 1 | 40 Schema/Host/frozen hard and semantic review; 16 cancellation and six waiting contrasts reviewed. | Predates persisted-Goal wake repair; supplemental waiting oracle invocation was corrected separately after a harness nesting mistake. |
| Persisted-wake Fast contrast 1 | Six Schema passes, zero Host/semantic passes: every raw result waits again at the already-consumed time. | Missing primary prompt projection of the Host’s already-reached readiness fact; the first incomplete helper-hook repair also fails six. Both failed batches retained. |
| Final Fast cohort | `fast-full-5`:204 Schema/Host/frozen hard/semantic passes;16 cancellation and 6 persisted-due passes. | One allowed parameter-provenance normalization, zero disallowed semantic normalization. Final Fast source is unchanged through Deep qualification. |
| Final Deep cohort and supplements | `deep-full-2`:40 Schema/Host/frozen hard/semantic passes;16 cancellation, 6 future-waiting and 6 persisted-due cases also pass. | Original future reference regions used correctly; all raw outputs reviewed, no retry or normalization. |
| Local Qwen9b GI output-budget contrast | 44 cases / 63 calls, source stable; 34 final decisions returned, only two pass all strict dimensions; still one 2,048-token truncation. | Strict literal span/wording failures are separate from concrete missing effects and wrong binding/mode failures. All 44 outputs reviewed; no profile promotion. |
| Final behavior-source aggregate live preview | 51 must-pass cases; first GI case fails, second startup interrupted, 49 unrun. Exactly one bundle; final simulator safe idle. | Incomplete failed cohort. GA, Planner and execution not reached in the failed case. |

The 9b experiment changes only the output budget from 512 to 2,048 against the same complete-Mind corpus and prior exact packets; `think:false` stays fixed. The blink case's `unresolved` field contains extended self-deliberation until truncation. Other outputs collapse walk/nod/turn or speech/body siblings into one responsibility, confuse duration with time scope, or turn an information query into speech. The budget-only hypothesis does not resolve these failures. Two-second GPU samples show at most 11,549 MiB used and at least 4,397 MiB free with one resident model; TTS was healthy but concurrent TTS load was not tested. This is neither a model intelligence ceiling nor a qualified combined profile.

The live request is “walk ahead at 0.2 speed for 10 seconds and then nod your head twice, then turn left.” At final behavior-source runtime identity `ccb85b7e47fd86467f143fa6c7cbc4f2cd596494724659c779ccf4ba985c9470`, GI call `llmcall_goal_interpreter_d2278e1d3bfa4a1b` emits one body-action responsibility and copies the whole turn into `subtype`. Host rejects `invalid_primary_goal_interpretation_semantics` with HTTP 503; GA/Planner/Runtime are not invoked. All 113 deployed Agent/shared files match the local source. Source and provider identity stay stable through that incomplete cohort; final simulator safe idle is verified and owned services stopped. The single debug bundle is `chromie_debug_bundle_20260912_193424.tar.gz`. This dirty-source diagnostic precedes final documentation/commit and is not clean-revision or physical evidence. Earlier unchanged and repaired-source failures remain separately retained.

The coverage-designed tracked corpora contain 204 Fast cases (17 capacities × three families × two conditions × two languages) and 40 Deep cases (ten capacities × two conditions × two languages), replacing earlier scale-based proposals. Cancellation and persisted-wake contrasts cover the newly reproduced boundaries. #35's offline evidence does not include GI, GA, native stream/provider behavior, automatic Agent Skill selection, physical voice or target qualification. These remain separately scoped evidence; none is inherited from surrogate passes.

## Publication and reproducibility

The [preceding audit](https://github.com/TimeTreker/chromie/blob/c142f16c6993ed60a93e2155c93906930c2fa445/ARCHITECTURE_AUDIT.md), [checkpoint](https://github.com/TimeTreker/chromie/blob/c142f16c6993ed60a93e2155c93906930c2fa445/DEVELOPMENT_CHECKPOINT.md), and [handoff](https://github.com/TimeTreker/chromie/blob/c142f16c6993ed60a93e2155c93906930c2fa445/HANDOFF.md) retain the friend's review context, original probes, #49–#51 deliveries and earlier exact evidence. Historical failures remain immutable; amended oracles require new inference and never relabel old results.

GitHub closure is verified for #35 and #52–#58, including the supported-version CI evidence linked on #56. #24/#32 remain the only open Issues, with the failed native-model/live evidence above.

A fresh clone can run the tracked source gates and full Planner corpus. Exact candidate raw replay, local-model comparison, captured persisted-wake requests and live evidence require the private archive identified in HANDOFF. Physical microphone/speaker/robot evidence remains absent. Close Issues only against delivered acceptance; keep #24/#32 and any still-failing qualification open with concrete evidence and resume commands.
