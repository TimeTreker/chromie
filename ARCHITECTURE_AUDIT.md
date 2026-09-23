# Chromie project principles and implementation audit

**Updated:** 2026-09-16. **Pre-delivery base:** `f90dff450357cd49358bb49f03a4930a4d33a8d4`, `main`, fetched and equal to upstream before development. The delivery revision is the commit containing this report, [checkpoint](DEVELOPMENT_CHECKPOINT.md) and [handoff](HANDOFF.md).

**Audience:** project owner and maintainers. **Owner:** the project owner owns principle decisions; implementation and evidence remain with their existing component owners. The owner explicitly authorized a project-wide audit, design/implementation repairs, up to 18 full-test iterations, commit and push. This authorizes reconciliation of obsolete wording ownership, not weakening safety or declaring unobserved success.

## Current conclusion and scope

The implemented authority split is coherent at maintained ingress boundaries: **UMI preserves complete intent; GA owns Goal continuity; Planner owns Work and scheduling; SC owns communication and optional expression; Host/Runtime owns admission, authorization, delivery and Evidence.** A compound intent can remain one Responsibility and one Goal while Planner creates several Activities. New UMI parameter tables and Planner-authored ordinary speech are forbidden.

The audit reproduced and repaired a mixed future/ready Goal contract gap, removed a dead wording-authority export and reconciled current architecture/API/interaction documentation. A Planner prompt cleanup was evaluated and rejected after new truncation failures; its original instructions remain an open finding. Native model reliability remains a release blocker. A structurally accepted result can still map right to left; source citations and JSON validation are not semantic proof. No model or release profile is promoted by this audit.

This is a cross-component source, authority and executable-workflow audit, not an assertion that every line, every model utterance, every external dependency or physical deployment has been proved correct. Existing owner-reported microphone/ASR acceptance remains separate. No physical microphone, audible speaker or robot test is fabricated.

## Coverage and findings

| Area and reviewed owners | Evidence and finding | Disposition |
| --- | --- | --- |
| Governance: Charter, Human-Like Interaction Contract, semantic authority, architecture, turn loop, API and component READMEs | Current paragraphs simultaneously assigned words to Planner and SC, timestamps/parameters to UMI and Planner, and treated implemented SC as unimplemented. An old HLIC paragraph forbade source quotations required by the newer intent-only contract. | Reconciled in existing owners. Current source-bound quotations remain required where declared; retired typed resource authoring is explicitly retained-state history. No new semantic owner/document/runtime switch. |
| Gateway/admission/reflex | Distinct pre-semantic protective controls, immutable admitted envelope, no Host semantic phrase routing; covered by canonical Gateway/reflex, cancellation and unusable-audio tests. | No new reproduced defect in inspected paths; native addressedness and physical input quality are separate qualification. |
| UMI | Closed intent/source/result-type wire rejects parameter/relationship fields. Baseline compound case preserves all three actions and has no false actor uncertainty. | Intent-only design preserved. Prior 19/24 native semantic result remains historical; this audit does not qualify the whole UMI role. |
| GA and Goal state | New Goal meaning/type inherited from exact UMI ref; continuity and retained typed-state conservation remain Host checked. Concurrent baseline GA commits the intact compound Goal. | No new writer introduced. Retained typed corrections must use a source-bound replacement when an intent-only update would leave contradictory typed state. Existing 200 rejected legacy-update references are not new successful continuity evidence. |
| Fast Planner Schema / Deep validation | Two independently accepted intents, one future and one ready: Fast Schema forbids the correct mixed result; Deep admits the JSON but rejects honest unmet future satisfaction. | Fixed at these two boundaries; new tests cover Schema, Host, actual controlled Runtime dispatch, completed acknowledgement, durable restart and one-shot wake. |
| Planner prompt and catalog | Fast inherited canonical `source_quote`/strategy instructions inside an `argument_sources` transaction. Another sentence implied one Activity per Responsibility despite compositional Work. Full turn-sign contract was present in retained packets. | Tested separate provenance instructions and clarified Activity/ref cardinality, then rejected that candidate: two new truncations fail non-regression. Original prompt retained; wording ambiguity and native failures remain open. No phrase-to-action rules or second semantic reviewer. |
| SC and interaction | Complete snapshot/identity/Need validation exists; SC independently sees UMI and actual Work facts. Baseline SC chooses silence partly because Needs are empty despite the standing interaction duty. | Native relevance/latency remains open. No forced acknowledgement template or Planner wording fallback. Removing the unused `PLANNER_COMMUNICATION_AUTHORITY_PROMPT` prevents accidental restoration of the retired writer. |
| Runtime, WorkDAG and provider boundary | Registry availability/version, input/output schema, confirmation, monitor, exact Plan/request/result ownership, resource arbitration and scoped cancellation checked in source and canonical suites. Paired Soridormi owns physical execution/safety. | No new reproduced safety/provenance bypass in reviewed paths. Wrong model semantics can pass mechanical checks; no universal safety proof is claimed. |
| Voice / TTS / delivery | Ordered playback and generation, cancellation generations, interruption and completion-qualified speech ledger remain Host-owned; relevant playback/TTS/VAD/barge-in suites run in canonical gates. | No new source defect reproduced. Discarded TTS in live text is not audible delivery evidence. |
| Memory / stable Mind / Reflection | Disclosure gate precedes model context; private/unknown relational memory stays hidden, audience-limited memory requires supplied audience, ordinary proposals cannot grant disclosure. Durable personal facts require explicit consent. Reflection is advisory and cannot rewrite policy/history. | No new reproduced defect in inspected/tested boundaries. No live multi-person privacy or perceptual-identity qualification claim. |
| Configuration / deployment / CI | Generated runtime env, source/image identity, pinned static checks, test ownership and GitHub Python 3.11/3.12 workflow inspected. Deployed Agent/ASR/LLM/TTS bind host ports to `127.0.0.1`. | Local source/image matching is required for each live candidate. Local Python 3.13 execution does not claim those CI jobs ran remotely. Ollama priority metadata does not prove SGLang scheduling or latency. |
| Evidence and regression corpus | Baseline strict 6,000 passes. Readiness Schema change exposes 400 frozen-request mismatches, including four canonical test failures. | Retained failures, then explicit request-only refreeze; a second refreeze removes the rejected prompt candidate. Final diff: 400 workflow cases, zero prototype cases. All 6,000 scenario inputs, reference replies, fault injections and behavior oracles stay unchanged. Strict replay remains strict; final counts/hashes are in the handoff. |

## Actual baseline workflow and earliest failures

Originating admitted input: “walk ahead at 0.2 speed for 10 seconds and then nod your head twice, then turn left”. Loop 1 SID `c0c5a0b6`; loop 2 SID `84b2e74d`. Each is a complete cohort invocation stopped at its first hard contract failure, not a successful aggregate.

```text
admitted source -> UMI complete intent
                    |-> SC independent interaction -> silence
                    |-> GA continuity -> one canonical compound Goal
                    `-> Fast Work -> source/provenance rejection
                                      `-> no body dispatch; retained Goal; safe idle
```

| Module / role | Authoritative input and actual output | Expected output / verdict |
| --- | --- | --- |
| Gateway/source | Original admitted text and exact source identity | Correct for the exercised text ingress; no ASR was invoked. |
| UMI / WHAT | Full source -> one body-action Responsibility containing walking speed/duration, two nods and left turn; unresolved empty | Correct in these two traces. Three Activities do not require three UMI Responsibilities. |
| Concurrent SC / interaction | Same accepted UMI; Work pending; no external Needs -> silence, with absence of Needs included in its rationale | Mechanically accepted. Relevance rationale is not qualified; absence of Needs alone is not permission to ignore its standing interaction duty. No claimed physical progress. |
| Concurrent GA / continuity | Exact `r1` -> one new Goal with inherited complete text/type | Correct; preserved canonical state is not proof that Work ran. |
| Fast / HOW | All required Capability contracts supplied, including positive yaw = left. Loop 1 returns three steps with decorated/unsupported source strings and negative yaw for left. Loop 2 returns mostly valid quotes but omits speed provenance and again selects negative yaw. | First wrong semantic output is Fast. Prompt wire/cardinality contradictions were contributing contract defects; correcting them alone did not qualify the model. |
| Host / containment | Exact owned-source and argument-grounding checks reject before Capability dispatch | Correct rejection. Host does not strip decorations, invent a missing quote, flip yaw or ask another model to repair the Plan. |
| Deep / execution / post-effect evidence | Deep not invoked to repair invalid Fast; body provider never called | Correct containment. Safe idle observed in headless simulator; no physical effect evidence. |

## Mixed timing: reproduced contract failure and repair

The retained probe has two current UMI Responsibilities: “Nod twice at 2099-09-04T19:00:00+08:00” and “Blink three times now”. GA inherits two Goals without typed UMI time fields. One authored primary Planner reply proposes a blink step owned only by the ready Goal, one exact source-bound future condition, an unmet future outcome, and partial aggregate satisfaction.

| Boundary | Before | After / regression |
| --- | --- | --- |
| Fast dynamic Schema | Ordinary alternative requires execution outcomes; waiting alternative requires all Goals waiting. Correct mixed reply is unrepresentable. Host alone can accept it when the test bypasses decoder enforcement. | Alternative preserves the already compiled Capability/argument/Work constraints and independently constrains each timed Goal. Linear per-Goal conditions avoid enumerating all ready/future subsets. |
| Deep Schema → DTO/Host | Correct mixed reply is schema-valid; deterministic adequacy rejects future outcome score 0 as below 0.75. | Only already provenance-validated new readiness conditions join existing nonfulfilling reporting scope. A deliberately unmet future effect is not failed planning. No score is raised. |
| SC / adapter / Runtime | Required acknowledgement still belongs to SC; Work and timer must retain independent Goal ownership. | Explicit controlled SC receipt plus real adapter/runtime dispatches exactly the ready blink; completed receipt does not close the future Goal. This is test-fixture speech, not native-model evidence. |
| Goal store / restart / wake | Original future effect must remain open and cannot execute early. | Durable restart retains the timer; due−1 produces no opportunity, due produces only the future Goal, subsequent drain produces none. |
| Negative controls | Early Work, fabricated fulfillment, foreign source time, duplicate timer | All remain rejected before dispatch for both planning depths, with one primary call. |

Initial focused proof: **2 failing positive cases, 8 passing negative cases**, then **99/99** related tests. The extended Runtime fixture initially selected an execution-only adapter for a Plan with communication Needs and then supplied an incomplete mock output schema; those harness defects were corrected to the maintained SC join and strict provider contract. They are not reported as production defects. The final integrated mixed-timing controls pass.

## Native transaction comparisons

Twelve individually frozen source cases cover six bilingual contrasts: compound sequence, reversed sequence, left, right, explicit walking speed/duration and counted nodding. The same complete captured production catalog, primary streaming transaction, context/output budgets (49,152 / 4,096), temperature 0, top-p 0.9 and `think:false` were used. Targets stayed outside inference. This is controlled accepted-UMI → native Fast evidence with no Runtime effects, not full pipeline qualification.

| Candidate | Schema / Host accepted | Reviewed semantic pass | Decision |
| --- | --- | --- | --- |
| Existing Qwen3.5 4B prompt | 12/12 Schema, 1/12 Host | 1/12 | Baseline retained. |
| Role-specific provenance/cardinality instructions, same 4B | 10/12 Schema, 2/12 Host | 2/12 | Rejected: left-turn EN/ZH now truncate at 4,096 tokens. One additional semantic pass does not offset new hard failures. |
| Same candidate transaction, installed Qwen3.5 9B | 12/12 Schema, 3/12 Host | 2/12 | No promotion. “Turn right” mechanically passes with positive/left yaw. |

Every raw result, including mechanical passes, was reviewed. Remaining defects include source-map omission, ungrounded count, inappropriate clarification/escalation, wrong direction and candidate truncation. A bigger model did not establish semantic improvement. The candidate's active prompt changes were reverted; only its unused import cleanup remains. Further example-specific prompt additions would not be an evidenced general repair, so this audit stops that local optimization and retains the open qualification blocker. No online critic, Host direction rule or model/profile change was added.

## Validation ledger and delivery boundary

Final loop 3 passes **3,471 tests / 1,017 subtests, 145 benchmarks, 20 legacy,
6,000 strict replay outcomes and 45 Level A cases**. All required static/policy,
ownership, configuration and docs gates pass; two existing FastAPI deprecations.
The first loop passed local gates; loop 2 retained four canonical/400 replay request
mismatches that the explicit refreeze corrected. Three of at most eighteen loops
were used; rejected role comparisons are separate.

Final rebuilt/source-verified live SID `9a5a54b0` selects all 74 cases but stops at
the first Fast contract failure: **0/1, 73 unrun**, safe idle, zero body calls. UMI
and GA preserve the complete intent. Fast still decorates exact source strings,
omits speed/yaw citations and chooses negative yaw for left. SC independently
mistakes the high-level request for forbidden low-level body control, invents a
capability/safety limitation and returns silence. The log's one speech item is an
acceptance-harness error diagnostic, not SC output. Deep is not invoked to repair
the invalid Fast result. Every attempted case and all twelve native calls across
the three aggregates are reviewed in `loop-*/adjudication.json`.

The exact final test counts, source/image identities, final cohort stop and commands are recorded in the current [checkpoint](DEVELOPMENT_CHECKPOINT.md) and [handoff](HANDOFF.md). The maximum was 18 complete candidate loops; focused tests and role-only comparisons are separately labelled. An incomplete native cohort is never counted as a pass.

Private evidence root: `.chromie/acceptance/full-audit-20260916-f90dff450/`.
`iterations.json`, each `loop-*/`, `fast-corpus/`, `fast-{baseline,candidate,qwen9b}/`, `packet-migration.json`, and retained red/green logs preserve the evidence. These artifacts are local and private, not fabricated remote attachments. Reference scenarios remain `training_eligible=false` and same-agent/non-independent evidence.

No new current Markdown document, runtime environment variable, product flag, architecture layer or semantic authority was introduced. Existing documentation owners were consolidated: Markdown files 102 → 102, docs-root Markdown 58 → 58, core reading path 15 → 15, checked by `check_docs.py`. Retired HLIC communication/result sections were merged into current SC ownership instead of adding another design document. File size is a review measurement, not the reason for the changes. This audit does not close native UMI/GA/Planner/SC coverage, foreground latency, concrete perception/audience adapters, remote target evidence, #24/#32, or physical commissioning.

## Historical audit records

The sections below retain their original revisions and superseded contracts. In particular, older UMI binding/`ready_at`, Planner wording and live-pass claims are historical evidence, not current implementation instructions.

## Native UMI continuation and distance containment — #24/#32/#67

The existing qwen3.5:4b candidate was held fixed on Ollama 0.33.2, context 16,384,
512 output tokens, `think:false`. The unchanged 44-case diagnostic cohort has
frozen references, exact request packets and source/model identities. Expected
answers were never supplied to inference. One primary owns complete WHAT; only
accepted genuine unresolved meaning may invoke its designated source-based deeper
UMI once. No critic or repair invocation was introduced.

| Native diagnostic before repair | Calls / normal stops / Schema and Host accepts | Complete primary-transaction review |
| --- | --- | --- |
| Unchanged production baseline | 71 / 71 / 71 | 3 pass, 2 meaning-correct but provenance extent unqualified, 39 fail |
| Source-first ordering experiment | 87 / 87 / 87 | 44 fail; also moved confidence, so not a clean single-variable control |
| Source-only ordering experiment | 84 / 84 / 84 | 1 pass, 43 fail; only source_evidence property position moved |

All 242 calls used `think:false` and returned no separate thinking content; this
does not prove that every model role meets #24's resource/non-thinking contract.
Every raw primary and deeper result was reviewed. The two ordering candidates are
rejected: compound decomposition improves in one case, but invalid unitless numeric
representation persists and previously good simple requests regress into false
uncertainty. No production prompt or Schema ordering changes are adopted. A valid
JSON/Host result is not proof of complete or correct meaning. Remaining native
failures include lost independent effects, wrong information/speech mode, borrowed
identity/operational values, and planning-input uncertainty incorrectly owned by UMI.
These experiments do not establish a model-only root cause or a full UMI-role score.

### Reproduced case and earliest enforceable defect

| Owner / correlation | Authoritative input → actual output | Expected result / verdict |
| --- | --- | --- |
| Admitted UMI request | `context-ambiguous_deictic_object`: `把那个拿给我。`; context `{}` | Correct input; object is unresolved and no distance is supplied |
| Prompt/Schema projection | Current tokens plus static worked example; distance scalar shape | Example remains instructional, not factual source; representable exact positive references pass Schema/Host |
| Native primary WHAT | Body responsibility with `distance="twenty meters"`, `direction="behind you"`, `entity="A parcel"`, `recipient="me"`; unresolved empty | Incorrect inference: the first three values occur in the prompt example, not admitted text/context |
| Parser/DTO/Host admission | Original raw reply accepted despite unsupported distance | Incorrect containment: duration/speed/location had provenance checks, distance had none |
| Deeper UMI / GA / Planner / Runtime | Not invoked in this direct-role case | No downstream or physical outcome demonstrated |

The initiating failure is model-authored meaning. The bounded production repair
extends the existing duration scalar validator to distance, rejecting unsupported
strings and non-scalar values before admission. It does not remove invented values,
guess the referent, repair meaning or delegate an invalid result. Primary rejection
uses one call; rejection after genuine unresolved primary uses two total calls and
stops. Numeric number-word normalization remains UMI-owned; this patch does not
certify numerical semantics or every entity/direction binding.

The original failure is retained unchanged. Revalidating all 242 original raw
replies through the patched ordinary Host rejects exactly six previously accepted
distance violations: the copied example once and translated measured surfaces five
times. The other 236 admission outcomes are unchanged. Nine focused negative
subcases fail before repair and pass after; valid English/Chinese, cross-clause,
continuity and numeric-normalization controls retain their exact values. Focused
UMI suite: 91 tests / 115 subtests pass. Broader and live delivery evidence is recorded
in the current checkpoint/handoff; it must not be inferred from these focused tests.

The patched production-order native rerun completes all 44 cases / 71 calls with
unchanged source/model identity. All parsed raw replies equal the reviewed original
baseline replies. The unsupported translated-distance primary now rejects; 43 final
decisions remain. This proves containment, not improved model understanding. The
full local gate passes 3,217 tests / 818 subtests, 145 benchmarks and 20 legacy tests;
Level A passes 45/45 and the unchanged 6,000-case corpus passes every expected outcome.

### Rebuilt deployment and stopped aggregate

Seven stale deployed files exactly matched known historical revisions; they had no
container-only changes. Agent was rebuilt and all 113 Agent/shared source files
matched local source. The old acceptance environment's qualification budgets did
not match the currently generated interactive profile. Identity capture correctly
rejected that mixture before any case. A new diagnostic text environment uses the
current profile budgets through their existing synchronizer, with stdin/discard
transport. Runtime identity is diagnostic-only because the patch was uncommitted:
`b078a0b56709653f160d5c6bb805281cb4cac59a4ab0cddd11db17ea76d9c190`.

One directory-discovered 51-case must-pass invocation used real Agent/LLM/TTS and
headless Soridormi/MuJoCo with execution enabled, no microphone/ASR or audible output.
It is **incomplete: two complete failures, one interrupted case, 48 unrun**. The
older evidence watcher's stop set missed `model_contract`; reviewer inspection
stopped the process on the first retained numeric-provenance failure after the next
case had completed and a third had started. Exactly one debug bundle was collected.
The original runner is frozen; its next-run copy now includes that hard-failure
domain. Neither case is averaged into a pass. Both source trees were unchanged
through the invocation. No same-stage retry or Deep Planner repair was attempted.

| Actual episode / owner | Input → output and handoff | Verdict / downstream result |
| --- | --- | --- |
| Compound `cbe8a87b`: primary UMI | Walk at 0.2 for 10 seconds, then nod twice, then turn left → one fused Responsibility plus false `actor` uncertainty | First wrong boundary: native primary completeness/uncertainty; current Host admits |
| Compound: source-based deeper UMI → GA | Three distinct effects/order; speed string `0.2 speed` → three canonical Goals with exact source bindings | Decomposition improves downstream but primary remains unqualified; noncanonical unitless speed survives; GA conserves values |
| Compound: native Fast stream → Host | Empty presentation commit; terminal claims complete coverage but walking `vx_mps=0.02` instead of explicit 0.2 | Native value violation; existing numeric conservation correctly rejects before Capability execution |
| Gaze/blink `8a11295e`: primary UMI → GA | Look at me three seconds while blinking twice → one fused gaze Responsibility, blink hidden in time_scope → one Goal | First wrong boundary: missing independent blink Responsibility; no deeper UMI invoked |
| Gaze/blink: native Fast stream → Host | Gaze Capability plus blink as social decoration; auxiliary anchor_kind=communicative_act points to Capability Activity | Invalid anchor rejected; independently requested blink was also downgraded semantically; no body execution |
| Milk `5b7a0a66`: interrupted Host request / late Agent UMI | Retained primary/deeper replies put `ahead of you about 50 meters` entirely in direction and invent then clear actor uncertainty | Partial only; typed distance omission remains a UMI defect. No completed Host outcome or downstream GA/Planner invocation observed |
| Runtime / Soridormi | Applied body Activities absent; error speech uses discard transport. Post-stop status: sim, safe_idle=true, active_task=null, active_lanes={}, fallen=false, emergency_stop=false | Safe containment observed in simulator. Owned simulator/MCP stopped; no physical evidence |

Nine completed native Agent calls are retained, including two late UMI replies after
client cancellation. Transport status `accepted` does not mean semantic acceptance.
The online failures remain #24/#32 evidence, outside #67's bounded string-provenance
repair. No model profile, streaming target or training-data promotion is justified.

Private evidence root: `.chromie/acceptance/issue24-source-order-20260914/`.
`comparison.json`, three `semantic-review.json` files, original `corpus/` and all
request/raw-response packets preserve rejected experiments; `distance-red.log`,
`distance-green.log`, and `retained-host-before-after.json` preserve the regression.
No new document, environment variable, profile, runtime switch or semantic owner.

## Broader workflow audit — #60/#65/#66

The September 13 owner-authorized expansion is **6,000/6,000 expected outcomes**, not
6,000 executed actions or independent model inferences. GPT-6 Astra authored 60
contrast families, expanded over four actions, five values and five language forms.
The strict full baseline retained 100 failures in the single-Goal Planner outcome
map boundary (#66). The final unchanged-source full run passes: 1,400 complete
workflows, 1,800 state/fault/permission outcomes, 2,580 contract rejections and 220
safe nonexecuting responses. All source, corpus and raw packet identities are retained.

The original 1,500-case result at `6bf16ccf` remains historical: 1,450 expected successes
and 50 failed #60 contract-gap probes. Its clean source identity was checked against
retained evidence before editing. Those #60 IDs are preserved in the new corpus and
now run **new input → UMI → GA → wait → restart → due wake → controlled execution**,
without seeding a Goal. `new_readiness_gap` is a historical family identifier, not a
remaining failure label. Separate prior-Goal timer cases remain as complementary tests.

### Responsibility boundaries and fixes

| Episode / owner | Authoritative input and actual output before repair | Expected output / first wrong boundary | Fix and downstream proof |
| --- | --- | --- | --- |
| #60 source → replayed UMI primary | `Blink 1 times at 2099-09-04T19:00:00+08:00.`; the authored model reply **already includes** `ready_at` | The simulator can return the field; UMI's closed Schema and Host vocabulary cannot admit it. This is a representability defect, not evidence of weak model inference | Owner-authorized Charter/architecture amendment: UMI authors requested temporal WHAT in its primary result; no extra semantic call |
| #60 Gateway context → UMI prompt/Schema/Host | Trusted receipt instant was not projected as a usable normalization anchor; no admitted readiness key | Preserve a literal timezone-qualified timestamp, or a normalized instant plus exact source time/time_scope and trusted receipt clock | Schema/prompt expose `ready_at`; Host checks ISO shape, timezone and source/clock provenance. Gateway time anchors elapsed time and never invents the user's local timezone. Host does not parse natural-language time or judge normalization semantics |
| #60 UMI → GA → Goal | Prior failed probes never reached GA | Preserve exactly the accepted temporal binding and all other WHAT values under the new canonical Goal ID | Existing GA conservation carries `ready_at` unchanged. Tests assert no pre-seeded Goal and equality through both owners |
| #60 Planner → state → due re-entry → Runtime | Existing retained-Goal timing path worked, but could not establish fresh UMI admission | Register the exact due time, retain an open Goal, do no early Work, survive restart, wake the same scoped Goal once and execute the exact action | Absolute and relative episodes pass. At due−1 no provider call; at due one call; next drain no duplicate wake. New semantic cancellation survives restart and prevents wake |
| #60 missing time meaning → primary/deeper UMI → Planner | `tomorrow at seven` lacks timezone and AM/PM | Preserve uncertainty, invoke only the designated source-based deeper UMI once, ask a genuine clarification and do no Work | Frozen primary/Deep uncertainty, GA, and Planner clarification complete with Goal open and no timer/provider call. Invalid date, naive timestamp, absent receipt and foreign source-time probes fail closed |
| #66 UMI → GA → Deep primary | Clear action/count becomes one canonical Goal; hostile reply returns an execute step and exact aggregate satisfaction but `goal_outcomes={}` | Raw dynamic Schema rejects the missing Goal key | Deliberate fault injection, never a training reference; valid upstream owners are unchanged |
| #66 shared Planner Host → canonical adapter | Map equality was checked only for multiple Goals or escalation; empty/foreign single-Goal maps were admitted; absence was also exempt | **First wrong production boundary:** a supplied map must exactly cover authoritative Goal IDs regardless of cardinality | Require exact map coverage for every Goal count, including absence, in the existing shared validator. Fast/Deep empty, absent and foreign map tests change from failure to rejection; complete-map controls still pass. All 100 frozen omissions reject before adapter/Runtime; no second call or fallback map is authored |

Broader validation also reproduced the absent-map variant: after the first repair,
60 empty-map contrasts rejected but 40 deliberately omitted-map contrasts still
passed Host admission. Their original raw packets and the failing run are retained
in `missing-map-red/`. The final repair removes the supplied-field exception too;
`missing-map-green/` rejects all 100. Twenty-eight reference DTOs in 27 older unit tests were
updated to include their declared per-Goal result while preserving the same action,
parameter, response, satisfaction claim and intended downstream assertion. Seven
initial failures, sixteen further missing-map failures, and four broader-reference
failures remain retained; no model
mock automatically adds an outcome. The dedicated negative tests keep missing/empty/
foreign maps malformed and verify both primary tiers reject them.

The complete temporal path is `admitted source/receipt → UMI WHAT → GA Goal → Planner
waiting Plan → persisted Host condition → scoped due re-entry → Planner effect Plan
→ controlled Capability Runtime → correlated outcome → satisfied Goal`. Semantic
cancellation follows the same first three owners, removes the pending obligation and
prevents the due re-entry. Operational stop cancels active work while preserving an
unmet Goal. The fixture establishes receipt facts, initial role scheduling and, for
one terminal-timer family, terminal state; it does not prove those facts' producers.

### Coverage and reference review

| Coverage | Concrete contrasts |
| --- | --- |
| Common execution and communication | Blink, walk, nod and head shake; Fast/Deep action plans; explicitly supplied speech content; mixed independent action/speech; exact quote delivery; two-Goal conservation |
| Continuous interaction | Weather acquisition and rain/dry result re-entry; new and retained timers; relative/ambiguous times; restart, no-early-work and single wake; new/retained semantic cancellation; operational and late cancellation |
| Primary authority and integrity | One designated deeper UMI invocation with resolved/unresolved outcomes; sparse binding/source/Goal conservation; duplicate/missing/foreign source maps; forbidden HOW and undeclared keys; parameter, timing and satisfaction errors |
| Execution boundaries | Failure/refusal/invalid output/cancelled/timed-out provider observations; absent provider; required/withheld trusted authorization; duplicate/stale/foreign outcomes; overlapping declared resources |

Review did not accept every mechanical pass. Initial reference/harness failures are
retained in `representatives-v1/` (337/420), `representatives-v2/` (212/240) and
`representatives-v3/` (236/240). Corrections include dictionary-shaped Goal access,
production speech-result correlation, proper supplied-proposition speech modality,
confirmation wording in its allowed aggregate field, and 60 terminal dry-condition
responses that retained blink-specific wording. These are reference/wiring corrections,
not product defect claims or model improvements. Original answers/hashes remain in
`reference-adjudication-notes.md`, `terminal-reference-review.json` and captures.

The resource family originally stopped at a singleton parallel group or numeric
provenance check. Its corrected 100 cases contain two independently sourced Goals,
explicit parameter provenance, both parallel members and a controlled catalog that
allows parallel work except for a shared resource. They now require the specific
`parallel_resource_claim_conflict` diagnostic from Deep validation and no executable
output. Declared fixture resource metadata also reaches Runtime definitions. The
original shallow passes and two unsuccessful refinements remain retained. This tests
catalog-driven conflict containment, not concurrent physical execution.

`benchmarks/integration/workflow_scenarios/manifest.json` retains the 6,000-case
freeze and a pinned source revision. The current 6,000 case JSONs and 76 shared
packet parts (288,195,530 bytes) are ignored local replay inputs, restored from
`ac4e56274ecac59cff51e84d734dee05d04f7da9` with every hash checked. The earlier
382,137,005-byte/898-part snapshot is historical. Existing Git history is preserved;
no current runtime or generator is allowed to reconstruct new expected answers.
Original
five prototype responses are unchanged; only their UMI packets were explicitly
refrozen for the authorized Schema/prompt amendment. Current model replies are
references or labeled faults; none is runtime-generated from a verdict. The runner
never imports the authoring module. Four isolated worker processes speed offline
runs without sharing clock/UUID patches, state or providers; candidate mode requires
one worker. Runtime/authoring source identities and primary prompt text are retained.

All outputs remain training-ineligible and same-model/non-independent reviewed.
3,600/1,200/1,200 splits keep each action/value's languages and contrast relatives
together; they are parameter holdouts, not unseen-family generalization. Fixed peers
support future one-role substitution, but an accepted novel output may reach an
uncovered downstream packet and require a separately reviewed continuation. They do
not establish native model ability or combined-model reliability. No LoRA job ran.

This corpus excludes autonomous initial scheduling, Fast-to-Deep Planner delegation,
native streaming, attention/reflection/skill selection, full Gateway/audio,
wall-clock provider timeout expiry, confirmation dialogue interpretation, deployed
service/registry compatibility, MuJoCo and physical robot evidence. Timeout cases inject
terminal provider status. Nod/shake contracts are reduced qualification fixtures,
using count 2–8 from the paired Soridormi manifest at `284273bc`; they are not its live
registry. Known source speech is not external-information acquisition. #24/#32 remain
open for their native/target evidence requirements.

Final validation: 3,214 tests/804 subtests, 145 benchmarks, 20 legacy tests and
pinned static/configuration/policy/ownership gates pass; Level A is 45/45 across
15 classes. Two pre-existing FastAPI deprecation warnings remain.

Evidence lives in `.chromie/acceptance/workflow-6000-20260913/`. The [checkpoint](DEVELOPMENT_CHECKPOINT.md)
and [handoff](HANDOFF.md) own final canonical checks, archive hashes and resume commands.
The owner authorized #60/#65/#66 closure after verified Git delivery. This change
uses existing owners: no new current Markdown document, environment variable,
model profile or architecture layer; 102 current documents / 15 core-path documents
remain unchanged. The larger authoring/driver files are reviewed as test-owned
assembly and execution boundaries, not an exception to safety/ownership checks.

## Expanded workflow audit — #61/#62/#63/#64

This section records the preceding 1,500-case delivery at `6bf16ccf`; the current
6,000-case result and subsequent repairs are described above.

The owner approved 1,500 architecture/workflow/contract scenarios after the five-case
prototype found a real defect. This is an explicitly authorized evidence expansion;
it does not replace the native #24, streaming/target #32 or temporal-contract #60
work. GPT-6 Astra authored 30 contrast families and their reference rules in this task,
then deterministic expansion produced 2 actions × 5 values × 5 language forms per
family. These are 1,500 executable cases, not 1,500 independent inferences or ability
classes. Reference review is non-independent and every output is ineligible for
training. Synthetic scenario text, exact request packets, reference responses and
independent Runtime/state assertions are tracked in the existing benchmark owner.

| Coverage group | Families | Cases / checked boundary |
| --- | --- | --- |
| Ordinary execution | normal_fast, normal_deep, multi_goal | 150; real primary role clients, Goal coverage, exact arguments and sequential effects |
| Conditional progress | conditional_rain, conditional_dry | 100; acquisition leaves Goal open, correlated result re-entry selects the frozen continuation |
| Retention/cancellation | retained_timer, cancellation, cancel_timer, terminal_timer | 200; persist/restart, once-only wake, cancellation and no later Work; terminal_timer seeds a trusted terminal state |
| Provider and Evidence faults | provider_failed, provider_refused, provider_invalid_output, duplicate_outcome, stale_outcome, foreign_goal_outcome | 300; fail-closed output/identity handling, no false closure or duplicate execution |
| UMI/GA admission | ga_missing_source, ga_foreign_source, ga_duplicate_mapping, umi_forbidden_how, umi_duplicate_ref, umi_bad_source, umi_unknown_binding | 350; source conservation and authority/field boundaries |
| Planner rejection | plan_wrong_parameter, plan_missing_parameter, plan_foreign_goal, plan_unknown_capability, acquisition_false_completion, multi_goal_omission, early_work | 350; argument, scope, acquisition and readiness constraints |
| Unrepresentable new readiness | new_readiness_gap | 50; #60 remains a gap and never counts as passed |

Language surfaces: 600 English, 600 Chinese and 300 mixed. Blink counts are 1/2/3/5/10;
walk durations are 0.1/1/2/15/30 seconds. All language and positive/negative relatives
for one action/value stay in one split: 900 train-candidate, 300 development and
300 held-out. This holds out parameters inside shared families, not unseen semantic
families. It cannot independently establish model generalization or training quality.

The semantic/oracle cohort was frozen before the complete baseline. Invalid model
outputs are labeled `fault_injection`, separate from authored references; the #60
requested result is `desired_unrepresentable_result`. Initial capture observes actual
requests while supplying predetermined answers; subsequent execution is strict replay,
never capture or semantic inference. Hash-checked shared prompt/Schema parts reduce
repetition. The persisted corpus adds 1,500 cases, one manifest and 255 shared parts
(88,054,200 bytes); the original five cases remain reproducible. No new document,
environment variable, model profile or production architecture layer was added.
Current Markdown/core-reading-path counts remain 102/15. Future corpus growth should
reuse these shared packet parts and existing documentation owners.

| Frozen aggregate | Expected successes | Unexpected failures | Known #60 gaps | Interpretation |
| --- | ---: | ---: | ---: | --- |
| Original production `0457db8d` | 1,328 | 122 | 50 | Baseline fails; two earliest-boundary clusters |
| UMI binding-vocabulary repair | 1,378 | 72 | 50 | All 50 unknown-binding probes now reject |
| Deep allocation repair | 1,450 | 0 | 50 | 36 valid multi-Goal cases proceed; 36 omission probes reach the intended rejection boundary |

Final expected successes comprise 350 completed workflows, 400 expected state/fault
outcomes, 675 explicit rejections and 25 nonexecuting clarify/refuse responses. The
whole 1,500-case cohort remains failed/exit 1 because the 50 known gaps remain. A
safe nonexecuting unknown-Capability response is correct containment, not a product
bug. No hard failure is averaged away.

### Actual defects and module I/O

| Episode / owner | Authoritative input → actual output before repair | Expected output, correlation and first wrong boundary | Repair / downstream proof |
| --- | --- | --- | --- |
| #62 test admission → UMI primary HTTP | `Blink 1 times.` and exact source span; frozen primary result carries `count:1` plus `invented_owner_field` in `binding_items` | Raw dynamic Schema rejects the invented key; model output is intentional fault injection | Reference stays invalid; it is never training truth |
| #62 UMI normalization → DTO/Host | Sparse bindings become canonical `bindings`; the open canonical dictionary admits the invented name | **First wrong production boundary:** semantic key admission must agree with the primary role vocabulary | Validate authored wire/canonical names against that request's Schema before returning. Existing canonical relation refs retain their existing validation. Unknown names fail closed after one call |
| #62 UMI → GA/Planner/Runtime | Before repair the test detects acceptance and stops at UMI; downstream owners are not invoked in this probe | Do not infer any downstream execution from this fixture | After repair the same one-call probe rejects, no committed Goal/provider Work. Focused tests cover primary and designated Deep UMI; the 1,500 cohort itself does not cover Deep UMI |
| #63 UMI → GA | `Blink 1 times. Walk forward for 0.1 seconds.` → two separate sourced responsibilities → two canonical Goals | Both boundaries correct; committed Goal IDs bind `${goal}` and `${goal2}` | Same input, outputs, source spans and Goal meanings retained |
| #63 GA/state → Deep prompt projection | Two snapshots total 3,431 characters; a 3,200-character list-wide limit returns `required_context_over_budget`, attempt_count 0 | **First wrong boundary:** a single-Goal fragment allowance prevents a modest admitted multi-Goal request before inference | Association/snapshot allowance scales with authoritative Goal count (6,400 for two). Complete JSON is retained; other fragment and whole-request limits remain enforced |
| #63 Deep primary → Host → Runtime | No Deep call or Work before repair on 72 cases | Valid two-Goal Plan must execute both effects; omission must fail before any provider call | After repair, full Plan executes exact blink/walk sequentially and satisfies both Goals. Omission fixture now reaches Host and is rejected. All 50 cases in each family produce their expected result |
| #60 new turn → UMI → GA/Planner | Desired primary `ready_at` is outside current UMI Schema; Planner consumes that exact typed Goal binding | Contract has no admitted producer-to-consumer path; **known gap**, not repaired here | 50 probes remain failed. GA/Planner/Runtime are not invoked in these probes. Separate retained-timer cases seed the prior Goal explicitly |

The #63 fix made 72 previously unrendered Deep packets available. An explicit second
packet freeze added only these missing packets: every existing packet, authored reply
and oracle was compared unchanged. Original manifest/hash and failed cases remain
retained; neither failures nor expected answers were rewritten to manufacture a pass.
No prompt wording, semantic authority or additional semantic call changed.

Broader regression found one implementation omission in the initial #62 patch:
direct parser validation built a context-free Schema and incorrectly rejected 34
legitimate prior-assistant-utterance references. The fallback now includes the same
accepted prior-speech fact used by the production Schema builder. Existing provenance
validation still rejects absent or changed speech. The production primary/Deep paths
already supply their actual request Schema. Eleven older behavior fixtures used
undeclared aliases (`date`, `question`, `aspects`, `duration_s`, `duration_text`,
`topic`, `order`, `concurrency`). Their reference/expected DTOs now express the same time, requested
property, duration, referent and ordering through declared bindings or validated
Responsibility relations. Source turns and intended success criteria remain; only their test representations
are corrected, with no new production aliases or safety behavior. Original files and exact before/after hashes
remain in `legacy-references/` and `legacy-reference-review.json`. These fixture
migrations are distinct from production defect discoveries. Initial editing/test
failures remain retained and are superseded only by successful reruns.

The same review reproduced [#64](https://github.com/TimeTreker/chromie/issues/64):
`_evaluate_user_meaning_interpretation_expectations` compared declared outcome text and
bindings but ignored explicit `output_mode`. A body-action result against an expected
speech modality produced no oracle error. The focused baseline test failed before
the checker changed. The existing oracle now compares modality; the focused suite
passes 10 tests/4 subtests. In the compound fixture, walk/blink/joke now have correct
body/body/speech expectations, predicate-aligned source spans and only the explicitly
requested joke-while-walking relation. The old fixture had swapped modalities/spans
and invented blink concurrency. This corrects test evidence, not production semantics;
GA/Planner/Runtime are not invoked by this direct oracle test. Semantic span entailment
still requires reference review; adding a modality assertion does not automate it.

### Single-role substitution and remaining limits

The existing replay service can explicitly forward one selected UMI/GA/Fast/Deep role
to an Ollama-compatible candidate endpoint. It forwards only the actual production
request, replacing the model identifier; no reference, case rubric or evaluator
output enters inference. Other roles require exact frozen requests. Raw candidate
transport responses, termination and Schema observations are retained without a
replacement answer or online critic. Intentional model-fault and unrepresentable
reference cases are excluded from this mode, as are cases not invoking the selected
role. There are 750 reference-only candidates before that role filter.

An accepted candidate variation can change the next role's packet. Such a mismatch
stops as `uncovered_replay_branch`; it is neither a semantic failure nor a pass.
A raw candidate Schema violation takes precedence as `candidate_contract_failure`.
Broader semantic judgment and valid alternative continuations require a separately
reviewed branch/corpus. Local fixture services verify isolated routing for all four
roles, altered-trajectory containment, incomplete termination preservation and HTTP
failure without fallback. A 50-case UMI substitution CLI run passed with 50 calls to
a second local fixture server, not native inference. This is plumbing proof only.

LoRA training was not started. Before using these artifacts for training, review
reference correctness independently, exclude fault injections, construct hidden
semantic-family holdouts, match each role's actual prompt/Schema/transport, and judge
candidate outputs at Schema/DTO/Host plus semantic boundaries. After isolated-role
qualification, test the combined real-model system; frozen peers cannot prove its
joint behavior. UMI uncertainty/Deep cognition, autonomous role scheduling, Fast-to-Deep
escalation, native streaming, attention/reflection/skill selection, Gateway/audio,
real services, resource contention and physical effects are outside this corpus's
coverage. Two positive primary planner families do not prove escalation behavior.

The [benchmark instructions](benchmarks/README.md#offline-workflow-replay) own commands;
[Status](docs/STATUS.md), [checkpoint](DEVELOPMENT_CHECKPOINT.md) and [handoff](HANDOFF.md)
own final gates, revision binding, retained archives and ordered remaining work.

## Offline workflow replay — #59

The owner explicitly requested architecture/workflow/contract tests excluding model
ability. Five cases use GPT-6 Astra-authored reference replies, reviewed in the same
task, through a strict loopback model HTTP service. They exercise UMI → GA → Fast or
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
| Test admission → UMI WHAT | Exact synthetic turn/source tokens; reference emits one conditional body effect, count 2, Hangzhou | Complete WHAT, no Capability/HOW. Final reviewed source span t0–t7 includes condition/place. Correct fixture; initial short span was a reference defect corrected before final freeze. |
| UMI → GA continuity | Accepted responsibility r1 → one new Goal carrying count/location | Exactly-once mapping and same meaning; real committed Goal ID binds the replay placeholder. Correct. |
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
Goal open. The delayed case starts from an explicitly seeded prior Goal: UMI's current
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

## Native User Meaning Interpretation boundary investigation — #24

The owner agreed to investigate the retained walk/nod/turn failure before continuing streaming qualification. The complete transaction was audited against the Charter, interaction contract and qualification method before changing an experimental packet. UMI must identify every independent WHAT, preserve material modifiers and exact source provenance, and express explicit ordering. It cannot select Goals, Capabilities or HOW. The current prompt already requires this complete primary decision; the dynamic Schema admits a correct three-effect result. All 44 frozen reference outputs pass the current Schema and Host, and all 88 original primary/deep packets match the earlier retained Qwen4b packets exactly.

The production request uses Ollama 0.33.2, `qwen3.5:4b`, top-level `think:false`, `stream:false`, temperature 0, top-p 0.9, **16,384 request context and 512 output tokens**. The generated environment's 32k label does not override those actual packet values. Model metadata also supplies presence penalty 1.5 and top-k 20; native sampler logs confirm the tested penalty settings. The original live failure stopped normally after 212 output tokens. Missing source input or output truncation does not explain that particular failure.

| Order / owner | Actual input, output and handoff | Boundary judgment / expected result |
| --- | --- | --- |
| Gateway provenance → UMI request | Admitted walk at 0.2 speed for 10 seconds, then nod twice, then turn left; complete original text and ordered tokens `t0`–`t19` reach the primary packet. The direct diagnostic starts from this retained request, not a new Gateway admission. | Correct retained input for this case. Preserve all three predicates and their modifiers. |
| UMI prompt/context → dynamic Schema → native provider | Complete WHAT instructions, bounded Mind/context and exact current-token Schema are sent. No reference answer, score or expected decomposition enters the candidate messages. | Reference three-effect output is representable and passes both Schema and Host. Successful representation alone does not prove the model follows it. |
| Primary UMI semantic result | Original live call emits one responsibility with the whole turn in `subtype`. Fresh unchanged baseline emits one responsibility with only the later nod/turn clauses in `subtype`; no count or coordination. Both are complete provider responses. | **First observed wrong output:** independent effects are merged into a modifier. Expected three responsibilities, correct speed/duration/count/direction, separate predicate provenance and explicit sequence. |
| Parser / normalization / DTO / Host | Original whole-turn echo is rejected before downstream admission. Fresh partial echo passes Schema and Host and returns a decision. Mechanical normalization does not create the missing effects. | Correct containment of the literal whole-turn case; incomplete containment of semantic omission. A returned decision is not proof of complete meaning. |
| Designated deep cognition | Primary compound outputs declare no unresolved meaning, so no deep call occurs. Other cohort cases may invoke the existing one source-based deep authority once. | The current uncertainty branch is followed. Confidence alone cannot replace material uncertainty or justify a semantic critic under Charter principles 30–31 and 34. |
| Host endpoint → GA / Planner / Runtime | Original live call `llmcall_user_meaning_interpreter_d2278e1d3bfa4a1b` ends HTTP 503 `user_meaning_interpreter_unavailable`. GA, Planner and Runtime are not invoked. Direct-role experiments stop at the UMI return/error and never enter those modules, even when Host accepts. | Original live containment prevents execution. Downstream behavior for the newly accepted wrong decisions is unproven, not a live result. |

```text
retained admitted request -> exact UMI packet -> native primary result
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

Five complete 44-case cohorts and six cold controls ran sequentially against unchanged source. Each experiment's packets were frozen before inference. Each case uses one primary call, with at most the existing source-based deep delegation for an accepted unresolved primary result; there are no retries, critics or semantic repair calls. Every raw output was reviewed after inference. Reviews are post-hoc and non-independent. The 44 cases cover independent/single effects, modifiers, mode contrasts, bilingual/mixed-language inputs, explicit source bindings and material ambiguity; they do not constitute full UMI continuity/lifecycle qualification.

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

Next, test one predeclared primary-packet/context or native-provider hypothesis while preserving the complete meaning contract. Retain these 44 cases as regressions, add independent coverage for the chosen hypothesis and missing UMI continuity/lifecycle boundaries, and qualify the whole role before downstream/combined-profile promotion. After a qualified repair, rebuild/verify the revision and rerun the full live cohort, then the narrow supervised voice/default target sequence. Repeating the already failed controls or weakening admission is not acceptance.

Evidence: `.chromie/acceptance/issue24-umi-boundary-20260912/`, including frozen driver versions, packets/raw replies, per-case reviews, model digests, sampling, comparison summary and explicit metadata corrections. No raw private Mind/provider payload is published. The [handoff](HANDOFF.md) records the separately transferable archive and exact resume commands. The canonical source gate passed again: 3,105 tests/794 subtests, 145 benchmarks, 20 legacy tests, pinned static/config/policy/ownership checks. Prior Level A and live results below remain prior evidence; no behavior changed or new general-ability/live result is claimed by this investigation.

## Issue disposition

| Finding | Implemented resolution | Qualification boundary |
| --- | --- | --- |
| [#61](https://github.com/TimeTreker/chromie/issues/61) | 1,500 frozen cases, full baseline/reruns, isolated candidate-role forwarding and reproducible report. | Closes on delivery; 50 #60 gaps remain failed, no native qualification or training. |
| [#62](https://github.com/TimeTreker/chromie/issues/62) | Enforce UMI binding vocabulary, retaining contextual prior-speech and typed relation validation. | 50 original failed probes now reject; primary/Deep and broader reference regressions pass. |
| [#63](https://github.com/TimeTreker/chromie/issues/63) | Allocate complete Deep association/snapshot input for admitted Goal cardinality. | 72 premature failures removed; valid effects complete and omissions fail at Host. |
| [#64](https://github.com/TimeTreker/chromie/issues/64) | Compare declared output modality in the existing behavior oracle; correct the faulty compound reference. | Baseline fails, focused/canonical checks pass; no native semantic claim. |
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
| Qualification last | Keep live qualification active. The unchanged baseline and repaired-source aggregate both stop at UMI; downstream source repairs do not hide that failed prerequisite. |
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
| Local Qwen9b UMI output-budget contrast | 44 cases / 63 calls, source stable; 34 final decisions returned, only two pass all strict dimensions; still one 2,048-token truncation. | Strict literal span/wording failures are separate from concrete missing effects and wrong binding/mode failures. All 44 outputs reviewed; no profile promotion. |
| Final behavior-source aggregate live preview | 51 must-pass cases; first UMI case fails, second startup interrupted, 49 unrun. Exactly one bundle; final simulator safe idle. | Incomplete failed cohort. GA, Planner and execution not reached in the failed case. |

The 9b experiment changes only the output budget from 512 to 2,048 against the same complete-Mind corpus and prior exact packets; `think:false` stays fixed. The blink case's `unresolved` field contains extended self-deliberation until truncation. Other outputs collapse walk/nod/turn or speech/body siblings into one responsibility, confuse duration with time scope, or turn an information query into speech. The budget-only hypothesis does not resolve these failures. Two-second GPU samples show at most 11,549 MiB used and at least 4,397 MiB free with one resident model; TTS was healthy but concurrent TTS load was not tested. This is neither a model intelligence ceiling nor a qualified combined profile.

The live request is “walk ahead at 0.2 speed for 10 seconds and then nod your head twice, then turn left.” At final behavior-source runtime identity `ccb85b7e47fd86467f143fa6c7cbc4f2cd596494724659c779ccf4ba985c9470`, UMI call `llmcall_user_meaning_interpreter_d2278e1d3bfa4a1b` emits one body-action responsibility and copies the whole turn into `subtype`. Host rejects `invalid_primary_user_meaning_interpretation_semantics` with HTTP 503; GA/Planner/Runtime are not invoked. All 113 deployed Agent/shared files match the local source. Source and provider identity stay stable through that incomplete cohort; final simulator safe idle is verified and owned services stopped. The single debug bundle is `chromie_debug_bundle_20260912_193424.tar.gz`. This dirty-source diagnostic precedes final documentation/commit and is not clean-revision or physical evidence. Earlier unchanged and repaired-source failures remain separately retained.

The coverage-designed tracked corpora contain 204 Fast cases (17 capacities × three families × two conditions × two languages) and 40 Deep cases (ten capacities × two conditions × two languages), replacing earlier scale-based proposals. Cancellation and persisted-wake contrasts cover the newly reproduced boundaries. #35's offline evidence does not include UMI, GA, native stream/provider behavior, automatic Agent Skill selection, physical voice or target qualification. These remain separately scoped evidence; none is inherited from surrogate passes.

## Publication and reproducibility

The [preceding audit](https://github.com/TimeTreker/chromie/blob/c142f16c6993ed60a93e2155c93906930c2fa445/ARCHITECTURE_AUDIT.md), [checkpoint](https://github.com/TimeTreker/chromie/blob/c142f16c6993ed60a93e2155c93906930c2fa445/DEVELOPMENT_CHECKPOINT.md), and [handoff](https://github.com/TimeTreker/chromie/blob/c142f16c6993ed60a93e2155c93906930c2fa445/HANDOFF.md) retain the friend's review context, original probes, #49–#51 deliveries and earlier exact evidence. Historical failures remain immutable; amended oracles require new inference and never relabel old results.

GitHub closure is verified for #35 and #52–#58, including the supported-version CI evidence linked on #56. #24/#32 remain the only open Issues, with the failed native-model/live evidence above.

A fresh clone can run the tracked source gates and full Planner corpus. Exact candidate raw replay, local-model comparison, captured persisted-wake requests and live evidence require the private archive identified in HANDOFF. Physical microphone/speaker/robot evidence remains absent. Close Issues only against delivered acceptance; keep #24/#32 and any still-failing qualification open with concrete evidence and resume commands.

## Engineering integrity continuation — #24/#32, 2026-09-14

Scope: acceptance collection and evidence, based on `d5a7985e`; no model, prompt,
semantic Schema, production authority, or provider change. The originating live
workflow is retained in the native UMI continuation section. This diagnosis concerns
why collection continued after a correctly reported hard failure, not why the model
misinterpreted the turn. Model-inference root cause for that separate question remains
unresolved by this slice.

| Order / owner | Authoritative input and actual output | Expected output / verdict |
| --- | --- | --- |
| 1. Native UMI → GA and Fast Planner | Compound walk/nod/turn session `cbe8a87b`: deeper UMI supplied three Responsibilities after primary fusion; GA conserved speed `0.2`; Fast authored `0.02`. Exact native correlations and raw-output review remain in the earlier section. | UMI primary meaning and Fast numeric result failed the semantic contract. This slice does not repair or requalify them. |
| 2. Host validation / Runtime | Fast result rejected with `failure_domain=model_contract`, `failure_class=fast_stream_contract_invalid`, stage `fast_planner_stream`; no capability work started. | Correct containment. No second semantic repair call or substituted argument. |
| 3. Text-check harness | Returned `ok=false`, the structured failure, SID and errors to General Ability. `status_after=null`; a separately retained later query proves post-stop safe idle only. | Correct failure propagation; per-case post-run idle remained unproven. |
| 4. General Ability collection | Received that completed result, appended it, and immediately started the next selected case. It checked failure only after finishing the entire stage. | First wrong collection boundary. Integrity should stop before another case; ordinary scenario mismatches may finish the stage. |
| 5. Private asynchronous watcher | Polled completed summary files; original domain set omitted `model_contract`. Second case `8a11295e` failed; reviewer stopped during the third. | Incorrect/missing automatic stop. Adding the domain alone would still leave a poll/start race. |
| 6. Evidence/report handoff | Live run ended 2 failed / 1 interrupted / 48 unrun with one externally collected bundle. Final aggregate generation was interrupted. | Incomplete diagnostic, not a passing subset or qualification. |

```text
case finishes -> structured hard failure -> synchronous collection check
                                          -> retain failed case + unrun coverage
                                          -> aggregate + reviewer artifacts -> exit
                                                                           -> one debug bundle
ordinary scenario mismatch -> remaining stage cases -> existing stage gate
```

The repair stays in `scripts/general_ability_acceptance.py`: inspect structured
Runtime/model failure, existing LLM-integrity evidence and omission/provenance
metrics, existing safe-idle checks, and typed harness exceptions before launching
another case. Nested episode failure retains the actual runtime turn/SID separately
from scenario-turn identity. Unavailable post-run status in execution mode is a stop,
not fabricated unsafe-state evidence or proof of recovery. Collected records keep
hard failures even when their incoming `ok` is accidentally true. Skipped cases
remain explicit; incomplete episodes also make collection incomplete. Semantic
review remains pending and cannot override the mechanical gate. No error-string
phrase classifier, polling process, new model invocation or production switch.

Primary attribution: `context_or_harness`, specifically an implementation/process
contract mismatch. Lower acceptance documents required unconditional stage completion;
they now agree with the higher-authority integrity exception. The private watcher's
missing domain and poll race contributed. The underlying semantic failure is the
trigger, not an explanation for the collection defect.

Evidence under `.chromie/acceptance/engineering-integrity-20260914/`: 21 new tests
fail on old source; focused runner/text-check suite passes 92 tests; all 45 Level A
scenarios pass. `replay-boundary.py` injects each of the two exact retained failure
summaries independently into the original and patched collection boundary over the
frozen 51-case discovery. Before: 51 attempted slots. After: 1 attempted / 50 unrun.
Repeated fault slots are scheduling probes, not 51 independent model results.
Positive controls collect all selected cases in preview and execution-shaped fixtures;
ordinary failure still exercises the existing stage gate. Final canonical result is
recorded in the checkpoint/handoff after completion.

Evidence ceiling: Level A harness/source validation only. No native call, deployed
change, physical audio, simulator action, model-quality improvement or fine-tuning
readiness is claimed. Existing source/workflow replay cannot replace independent
positive-reference review, injected-fault exclusion, hidden semantic-family holdouts,
or isolated and combined production-role qualification. #24/#32 remain open.

Surface review: no new Markdown document, environment variable, profile, service or
model-facing field. The existing collection owner gains one internal inspection
function; file size grows because it now owns the previously private stop/report
responsibility. A separate watchdog/module would add a handoff and preserve the race,
so no extraction is justified. The private polling watcher is the consolidation
opportunity and must not be used for future launches. Rollback would restore the
proven collection defect; no model/runtime rollback is needed for this patch.


## Preflight admission continuation — #24/#32, 2026-09-14

A controlled dependency reproduction found that the text acceptance checker recorded
failed provider/state checks but still created a session. The triggering probe was
`walk forward`; rejection is independent of its semantics. Models, prompts, runtime
profiles and production semantic authorities are unchanged.

| Order / owner | Authoritative input and actual output before repair | Expected output / verdict |
| --- | --- | --- |
| 1. Agent health / harness | Controlled health has no Soridormi manifest, or healthy manifest for status variants. Health JSON retained; missing manifest adds an error. | Correct detection; capability invocation beyond status must not be admitted after failure. |
| 2. Soridormi status / harness | Controlled status varies simulator mode, safe-idle, active task, fallen or emergency state. Status JSON retained; mode and existing `safe_idle_errors` checks add errors. | Correct detection. The fixture establishes returned state, not physical state. |
| 3. Text-check admission | Nonempty preflight errors still reach `create_session()`. All 28 invalid combinations reproduce this across preview/execution and owned/shared assistant lifecycles. | First wrong boundary: reject before session/Gateway admission. |
| 4. Gateway → Core or reflex → final dispatch | Source inspection shows these paths follow session creation; Core permits early typed presentation before final planning. The outer dispatch guard checks accumulated errors later. Test deliberately stops at session creation. | Late guard cannot establish non-admission. Actual downstream effects were not measured; no physical leak is claimed. |
| 5. Evidence and lifecycle | Before repair the admission sentinel raises; after repair a failed summary with null SID/cognition/execution/post-status returns to the caller, and owned-assistant cleanup runs. Shared cleanup remains with the sequence owner. | Correct repair/containment. Initial status is not relabeled post-run evidence. |
| 6. General Ability collection | Structured preflight rejection reaches the existing synchronous integrity gate. Stage contrasts prove one attempted case and explicit unrun coverage. | Correct stop before another case; no model failure or semantic judgment is invented. |

```text
Agent health -> Soridormi initial status -> existing preflight checks
                                             | failure
                                             v
                                retain rejection -> owner cleanup
                                             -> cohort stop + unrun coverage
                                             | no session/Gateway/Core/dispatch
checks pass -> existing session admission -> unchanged production turn workflow
```

Root cause is a harness control-flow error: preflight validation accumulated errors
without enforcing its admission contract. The later execution guard was a contributing
condition, not an adequate boundary for the complete turn workflow. The repair adds
an early failed result to the existing `run_check` owner. It uses the existing
`harness_failure` channel and safe-idle validator; no additional runtime authority,
semantic classifier, environment variable, flag, or document. Production deterministic
stop/emergency processing remains unchanged; this gate controls acceptance-case
admission only.

Evidence: `.chromie/acceptance/engineering-preflight-20260914/`. Fail-first run has
28 failures and three valid-admission controls passing; final focused runner/checker
suite passes 125 tests. Canonical passes 3,273 tests / 818 subtests, 145 benchmarks
and 20 legacy tests, including policy/static/ownership/configuration/docs checks;
Level A passes 45/45. `replay-admission.py` additionally drives the real checker,
result validation and aggregate with controlled dependencies. Missing manifest
rejects before session creation; one of 74 discovered cases is attempted and 73
remain unrun. `admission-replay.json` retains that scheduling result, not semantic
qualification of 74 cases. The positive
non-simulator override uses controlled dependencies and proves option compatibility,
not supervised hardware validation. No native inference or live target action ran.
This removes a reproduced engineering blocker but does not close #24/#32 or establish
fine-tuning readiness. Surface count remains 102 Markdown documents / 15 core-path;
no new document, profile, service, environment variable or model-facing field.


## Bounded engineering iterations — #24/#32, 2026-09-14

Historical pre-SC checkout evidence. The subsequent integration section supersedes
its Planner communication ownership and runtime/model resume assumptions.

Owner requested up to 18 test/diagnose/repair/retest iterations, keeping models fixed.
Private ledger: `.chromie/acceptance/engineering-18-20260914/iterations.json`.
Iteration 1 is an unchanged deployed baseline: one discovered 74-case live-text
cohort, stdin/discard against headless MuJoCo. It stopped after the first hard failure,
retained 73 unrun cases, and collected exactly one debug bundle. All 113 Agent/shared
files matched source; Chromie and Soridormi identities remained stable. Four native
calls and their exact requests/raw responses are retained and reviewed, with
same-model/non-independent review explicitly recorded in `iteration-01/review.json`.

| Order / owner | Actual input → output | Contract / verdict |
| --- | --- | --- |
| Gateway → UMI primary/deeper | Session `eb404c88`, compound walk/nod/turn source. Primary merges independent outcomes and invents actor uncertainty; designated deeper UMI keeps fusion and introduces speed-unit uncertainty. | WHAT must preserve independent outcomes. Semantic failure remains separate from the budget defect; no downstream resegmentation is authorized. |
| GA and Fast concurrently | Same admitted one-Responsibility result. GA preserves it in one Goal; Fast has null presentation and escalates, with no executable activities. | GA conservation is correct for defective upstream input; Fast does not repair WHAT. Ambiguity sufficiency remains a semantic/oracle question. |
| Deep catalog projection | 23 executable provider contracts serialize to 24,641 characters; fixed 12,000-character check raises `required_context_over_budget`, zero model attempts. | First wrong budget boundary. A catalog-only cap ignores the configured complete-request budget. |
| Runtime → harness | Error is preserved, no Capability Work starts, cohort stops synchronously. Per-case post-status absent; separately queried post-stop state is safe idle. | Correct containment; separate state query cannot backfill per-case evidence. |

Iteration 2 removes only the duplicate catalog character ceiling from both existing
Deep prompt render paths. Exact schema/safety/resource/applicability facts and ordering
are preserved. The existing transport rejects the whole request against model context,
reserved output and safety margin before HTTP; the resolver's count bound remains.
No model, context size, output allowance, semantic authority, Schema or runtime flag
changed. This consolidates budget ownership without truncating the catalog or giving
Host semantic selection. A new regression fails on the original 31,312-character
catalog fixture, passes with complete preservation, and verifies an undersized context
still rejects before HTTP. The captured provider catalog with a controlled Goal
context needs an estimated 35,592 tokens including reserve/margin, below the unchanged
49,152-token window. This controlled projection replay is not native inference.

The full 6,000 workflow replay passes on unchanged source: 1,400 workflows, 1,800
expected state/fault/permission outcomes, 2,580 expected rejections, 220 safe nonexecuting
rejections. No candidate calls. Frozen Fast 204 / Deep 40 reference corpora validate;
focused Deep/projection/Ollama tests pass 89 tests / 108 subtests. Native rerun and
final gate outcomes belong in the checkpoint/handoff after completion. No model or
training-reference qualification is inherited from these mechanical checks.


Iteration 2's full native rerun reached Deep inference (five calls total), proving
the catalog blocker removed. The same first case still fails and 73 remain unrun;
one bundle was collected, both source identities stayed stable, and the separate
post-stop query confirms safe idle. Deep's raw result passes the exact supplied
Schema but fails the existing DTO. It authors an `ask_user` resolution for
`clarification_needed` / `speed_unit`, omits `blocking`, and provides no value.
The DTO defaults `blocking` to false and rejects. It also authors a mixed aggregate for one clarify outcome and speech that omits
turn-left; fixing the first structural failure does not certify those semantics.
The `clarification_needed` reference is prospective: blocking parameter records
may legitimately have no executable step, so that fact alone is not a defect. All five calls are reviewed in `iteration-02/review.json`.

| Iteration 3 boundary | Actual → expected / repair |
| --- | --- |
| Shared `PlanParameterResolution` Schema | Omits the DTO's strategy/blocking/value invariant. Exact retained native raw object passes the full old Schema. Schema must expose the already-binding DTO invariant; this is a mechanical realization, not new meaning. |
| Model → DTO | `ask_user`, omitted blocking → default false → rejection. Host correctly rejects rather than filling blocking or inventing a value. |
| Runtime → acceptance | Error retained as `unclassified_model_failure`; no Work starts, cohort stops. This repair addresses the earlier decoder contract; error taxonomy and missing per-case final status are separate review items. |

The shared DTO's generated Schema now requires explicit blocking for unresolved
strategies, permits only null/absent value for those strategies, and requires a
non-null value for resolved strategies. DTO behavior, valid semantic outcomes and
model identities are unchanged. The Schema/DTO contrast matrix fails 68 subcases
before repair and passes all 146 after, across raw DTO, canonical Fast and Deep.
The exact native row now fails the new Schema at the predicted boundary. Focused
Planner tests pass 200 / 319 subtests; 104 workflow tests pass after a reviewed
mechanical input-schema rebind. Only request-format snapshots/hashes change in five
prototype and 4,600 large-corpus cases, replacing 135 shared Schema artifacts.
References, prompts, decoding options, scenarios, fault labels, splits and training
eligibility are byte-value preserved outside those request-format changes.
`iteration-03/schema-rebind.json` retains old/new manifest hashes and proof scope;
the old 6,000 manifest remains immutable historical evidence. No reference or training
promotion follows from rebinding an executable input contract.


Iterations 3–6 exposed a decoder implementation constraint: partial `anyOf`
branches admitted incomplete native parameter objects when intersected by the
provider. Iteration 3's focused call returned only strategy/value, omitting the
required step/parameter. Iteration 4 repeats every required object property in
both complete branches and propagates Fast/Deep field constraints into them.
The same retained Deep input then passed the full Schema and parameter DTO
invariant, but failed the separate single-Goal `mixed` aggregate invariant.
Iteration 5 removes that invalid aggregate option for a single expected Goal.
Its focused native reply no longer uses `mixed`, but violates already-exposed
execution/unresolved and confirmation constraints; those remain failures.
No Host filling, semantic rewriting or extra model reviewer was introduced.
The final iteration 5 local gate passes 3,275 tests / 988 subtests, 145 benchmarks,
20 legacy and the complete 6,000 workflow replay. All references remain
training-ineligible and non-independent. Rebinding generated input Schemas does
not qualify references or alter frozen expected answers.

Iteration 5's first live run started while the rebuilt service was still warming:
Host admission at 00:14:04 encountered a connection reset; Agent startup completed
at 00:14:06. Only the explicit one-token startup warm call was observed, not a
user semantic transaction. The run remains incomplete (one attempted / 73 unrun).
Iteration 6 is the unchanged-source rerun after Docker reports healthy, not a
silent replacement of that failed run. It attempted two cases and retained 72
unrun. Its eight model-role records, and iteration 4's nine, were reviewed.

| Actual re-entry episode / owner | Material input → actual output | Expected / first divergence |
| --- | --- | --- |
| UMI → GA → Fast primary, iteration 6 SID `51e18a48` | Walk at 0.2 speed for 10 seconds, nod twice, turn left. UMI retains a fused outcome; GA conserves one Goal with degraded subtype binding. Fast admits only `walk_velocity(vx_mps=0.2,duration_s=10)` while claiming complete coverage. | Required nod/turn absent. Complete semantic coverage remains unqualified; no downstream semantic splitting is authorized. |
| Trusted Capability Runtime → Soridormi | The admitted walk runs and completes in headless MuJoCo. Completion Evidence reactivates Planner; post-run safe idle is true. | Correct mechanical execution of the authored Work, not proof that all requested Work was authored. |
| Fast result projection | Current common catalog is 17,041 characters; fixed 9,000-character projection cap rejects before inference with `contract_failure`. | Separate catalog admission blocker; no model attempted. |
| Host `_planner_state_reentry_response` | Returned Fast failure is recorded `resolved`; every `escalate` delegates to Deep without checking failure classification. | Earliest routing defect: technical failure must stop before Deep. Initial planning already enforced this rule, re-entry did not. |
| Deep transport | Complete re-entry request exceeds the fixed context plus reserve/margin and rejects before inference. Iteration 4 required 50,391 against 49,152 tokens. | Correct budget containment; this cannot count as a semantic Deep answer or successful recovery. |
| Host → General Ability | Deep failure also recorded `resolved`. Initial turn summary remains `applied`; collector proceeds to the next case. No TTS was scheduled. | Incorrect failure evidence/collection. Absent speech cannot be attributed only to model wording because re-entry failed. |
| Next case, SID `8b94a64c` | Gaze three seconds with blink twice. Fast authors a Capability primary but a blink auxiliary with `anchor_kind=communicative_act`. | Host correctly rejects anchor-kind mismatch before dispatch; it exposes a raw contract failure and stops the cohort. Required blink as decoration is not independently qualified. |

Iteration 7 restores the existing rule at the shared Host re-entry owner. Both
Fast and Deep calls now pass through one observed boundary: returned technical
failures, exceptions and changed Goal scope record `failed` and re-raise before
adaptation or commitment. A Fast contract failure cannot reach Deep. Semantic
escalation and direct slow readiness retain their existing permitted paths.
Acceptance reads the trusted failed-stage status, including when initial dispatch
was already applied; it does not interpret redacted error prose. Structured
metrics and cohort stopping use the same stage evidence. The existing classified
exception handler moves into this shared boundary, still a diagnostic re-raise;
no broad-exception exemption or blanket ignore was added.

Nine regressions fail at these boundaries on original source after correcting
fixture construction (the earlier fixture failures are retained separately).
The focused suite passes 103 tests / three subtests, including provider, result,
cancellation and turn closure. The full 6,000 replay passes with stable source;
Level A passes 45/45. Final canonical/native evidence remains in the active
checkpoint and iteration ledger. These repairs change routing/evidence, not
semantic authority, model weights/options or physical execution policy.

Iterations 8–12 continued the same fixed-model line. Iteration 7's canonical gate
passed 3,285 tests / 988 subtests and its native cohort attempted two cases / 72
unrun. Its Deep clarification satisfied the repaired parameter and single-Goal
Schema contracts; the second Fast result failed unresolved-meaning conservation.
That run did not reach result re-entry, so iteration 7's routing repair initially
had focused executable evidence only.

| Episode / ordered owner | Material input → actual output | Earliest boundary, repair and evidence |
| --- | --- | --- |
| Iteration 8: Fast catalog projection → transport | Retained result re-entry catalogs exceed the separate 9,000-character cap. Non-streaming initial/layered/re-entry renderers rejected before inference, although complete-request admission owns the actual budget. | Removed the three duplicate limits; preserved complete catalog facts and transport rejection. Streaming projection remains its existing smaller authorized surface. The regression covers each variant, lossless content and rejection by an undersized transport budget. |
| Iteration 8 native aggregate: UMI → GA/Fast → Host | UMI preserves three requested outcomes; Fast changes speed 0.2 to 0.02. Host numeric conservation rejects before execution: one attempted / 73 unrun. | Model numeric error, correctly contained. No numerical default or semantic repair was added. |
| Iteration 8 isolated blink: UMI → GA/Fast → Runtime/provider → Fast re-entry | SID `0fdb87af`: one requested blink, one executed blink. Result re-entry supplies all 10 common contracts / 15,653 characters; Fast returns a grounded completion with no further Work. | Native proof that the Fast catalog obstruction is removed and legitimate re-entry remains operational. Safe idle retained. This one-case pass does not qualify the aggregate or physical hardware. |
| Iteration 9: typed Planner DTO rejection → shared error taxonomy → Runtime/collector | Retained iteration 2 raw reply raises `PlannerDTOContractError`, previously reported as `unclassified_model_failure`. | Existing typed error now supplies `structured_output_validation` / `model_contract`, non-retryable, attribution not evaluated; shared metadata extraction honors the existing exception protocol. Unknown exceptions remain unclassified. Three fail-first subtests, 215 focused tests / 349 subtests and exact native-raw replay prove classification; no semantic diagnosis is invented from error prose. |
| Iteration 9 native gaze/blink: UMI → GA → Fast → provider → Fast re-entry | SID `ff3f04e7`: UMI fuses gaze and blink, GA conserves that input, Fast authors only gaze. Provider executes gaze; Fast result speech claims blinking twice without blink evidence. | Hard semantic failure despite mechanical success and safe idle. The first omission is upstream WHAT fusion; downstream false completion is separately unqualified. No phrase detector, second model critic or Host resegmentation was introduced. |
| Iteration 9 resource: UMI → GA and Fast → Host conservation | SID `bcd2ab86`: accepted recipient `me`; Fast emits `recipient.description="me"`. The live provider declares a structured recipient input but omits its argument realization. Host falls back to comparing the object with the scalar and rejects. Runtime/provider are not invoked. | Earliest responsible declaration belongs to Soridormi. This was a false structural contradiction, not evidence that the model substituted a recipient. |
| Iteration 10: admitted runtime failure → text-check harness → collector | After a handled non-preview runtime failure, the existing dispatch guard skipped the final status probe. The collector could not establish post-case state. | Moved the existing probe outside the success-only dispatch block; rejected Work still cannot dispatch. Six controlled safe/unsafe/unavailable and preview contrasts include three fail-first failures. SID `f427576b` natively rejects malformed Fast meaning and now retains fresh stand/safe-idle/no-active-task status. Preflight rejection and preview still do not imply post-execution evidence. |
| Iteration 11: provider declaration → Agent catalog → Fast/Host → provider → re-entry | Existing resource skill now declares entity/quantity→resource, recipient→recipient, direction/location/distance/route→source. Input Schema and embodied safety policy are unchanged. MCP reload and Agent refresh expose all seven mappings. SID `add2cbb0` preserves milk, source and recipient, executes the scripted resource provider and reaches completion speech with safe idle. | Provider-owned contract repair; Planner still authors values and Host does not infer missing semantics. Exact retained raw result now passes; changing recipient to `someone else` still rejects. The mock resource sequence is not real-world acquisition/delivery evidence, and completion perspective is not independently qualified. |
| Iteration 11 aggregate: UMI → GA/Fast → Deep Schema → DTO → Runtime/harness | SID `cd1b19d7`: fused compound, a speed-unit gap, Fast semantic escalation; Deep authors a nonexecuting clarification with `ask_user`, `blocking=true`, but omits `source_goal_ids`. Exact supplied Schema accepts; CanonicalPlan rejects before Work. Fresh safe-idle status is retained. | Another decoder/DTO mismatch. Iteration 12 requires explicit Goal ownership in Deep's complete unresolved-resolution branches. Existing enum/minimum validation and Host ownership remain; no IDs are filled. Exact raw replay fails under repaired Schema, a controlled correct Goal passes Schema and CanonicalPlan, and foreign ownership rejects. Eight fail-first subtests and 194 focused tests / 423 subtests pass. |

The post-admission failure path is now:
`admitted turn → failed Planner boundary → Runtime error → fresh status probe →
retained failed stage/status → cohort integrity stop`. Successful execution still
follows `Runtime → provider result → owned Fast re-entry → validated response`.
The former success-only status probe and technical Fast-to-Deep delegation are
removed at their original owners. Model failures are retained, not repaired by
another same-authority call.

Iteration 11's paired Soridormi gate passes 792 tests with two target-dependent
skips, 159 body-concurrency tests, 142 task-contract tests, governance, compilation
and manifest validation. Its mounted manifest SHA is
`b12a2d75832ede53efa3107da50af59d507f37201e78b567f56ceefb6107053c`.
The local host lacks the provider dependencies; the full suite ran inside the
existing dependency-complete Compose container against the mounted whole checkout.
No skip is counted as target proof. Provider changes are confined to the existing
manifest, registry execution tests, interface guide and Status; unrelated dirty
workspace content is preserved.

Iteration 12 mechanically rebinds two prototype and 2,000 large-corpus request
Schemas (64 shared artifact replacements). It preserves every expected output,
prompt, decoding option, case, fault label, split and training-eligibility value.
Large manifest: `e67d15d3025667b667f19cfb976eaabd0f610692b3569d2a75399de0bc5db35a`;
prototype: `24cb3921f304643a7d5b422f8866fefbe16f87807660aa621048c0ac8d1ea1fa`.
Earlier rebind manifests remain historical evidence in the retained archives.

Review distinguishes supported contract defects from semantic/oracle uncertainty.
For example, clarification of a unitless speed is not itself proven wrong, even
when the scenario expected execution. Remaining UMI fusion, invented uncertainty,
Planner omission/numeric errors and unsupported completion claims are not repaired
by stronger mechanical pass counts. The 6,000 authored references remain
non-independent, training-ineligible and without hidden semantic-family splits.
Current evidence does not establish fine-tuning or default target-evidence closure.
No model, context/decoding setting, architectural authority, profile, runtime
switch or current document was added; Chromie's surface remains 102 documents /
15 core-path documents. Final gate/native counts and resume commands are recorded
in the checkpoint and handoff; the private per-iteration reviews retain each call,
source identities, exact stopping point, unrun coverage and one bundle per run.

Iteration 12 final canonical passes 3,296 tests / 1,071 subtests, 145 benchmarks
and 20 legacy tests; all pinned checks pass with the two existing FastAPI warnings.
The full 6,000 replay remains source-stable and Level A passes 45/45. Aggregate SID
`fd0a301a` stops after one attempted / 73 unrun: primary UMI fuses the request,
designated deeper UMI recovers three ordered outcomes, GA conserves, and Fast
authors 0.02 speed / six seconds instead of 0.2 / ten, plus head movement instead
of a body turn. Host numeric conservation rejects before dispatch; fresh safe idle
is retained. All four role calls were reviewed; Deep was not invoked in that run.
The isolated exact iteration 11 Deep packet, changing only the ownership Schema,
then natively supplies the correct Goal ID and passes the full supplied Schema and
CanonicalPlan. It is a model-boundary proof without runtime effects, not a full
workflow or independent semantic qualification. One bundle is retained per run.
Final safe idle/no active task was observed, owned simulator/MCP were stopped,
and ports 5555/8000 no longer listen. The twelve-iteration ledger retains six
unused iterations; no further engineering change is justified by this final
failure without a new boundary diagnosis. Fine-tuning readiness remains false.

## Integrating upstream Social Cognition — 2026-09-15

Both upstream branches advanced during the pre-SC experiment. The owner explicitly
authorized integration and required fetch-before-development as a durable rule.
Recovery stashes retain all old source and generated artifacts; integration starts
from Chromie `2e18f86a` and Soridormi `0af3d09`, without rewriting remote history.
The upstream amendment is binding: SC owns words, silence and social expression;
Planner owns Work/facts, never a draft for SC to review. Remote priority scheduling,
Vocal/Activity waiting queues, prepared-start alignment, weather/evidence handling
and manifest validation are preserved.

| Boundary | Conflict and integration decision | Evidence / qualification |
| --- | --- | --- |
| Planner prompt projection | Old local renderers combine planning and wording; remote replaces them with `_canonical_work_prompt`. Keep the new Work owner and port only lossless catalog budgeting there and into layered projections. | Focused Fast/Deep catalog preservation, transport refusal and SC authority tests pass. No old response-writer path restored. |
| Parameter DTO → generated Schema | Shared invariant remains present after SC migration; local complete branches, single-Goal aggregate and blocking ownership constraints remain applicable. | Upstream frozen requests initially mismatch only Schema. Rebind current SC-aware format snapshots; preserve every prompt, response, case, option, fault and training flag. Old pre-SC artifacts are not substituted. |
| Runtime result → Work re-entry / independent SC | Remote adds independent SC fixtures and communication. Local failure handler rejects technical/scope failures before Work adaptation and improper Deep delegation. | Combine both test sets. SC stays a distinct authority; failed Work is not repaired through SC or Host wording. |
| Provider declaration → manifest validator → Host | Remote adds generic validation and primitive argument mappings; local adds composite resource mappings. | Retain upstream validator, add complete resource mapping regressions and rerun the paired provider suite. No raw motor fields or changed embodied policy. |
| Acceptance admission/results | Local preflight rejection, structured asynchronous failure stopping and post-failure state capture apply around current SC-aware runtime. | Focused acceptance/SC suite passes. Original native counts and current target qualification remain separate. |

Initial focused combined suite passes 785 tests / 364 subtests. The first 104-case
workflow suite has 68 exact request-Schema mismatches; this is stale executable
input evidence, not permission to change model answers. Final combined gates,
manifest identities, remote delivery revisions and limitations belong in the two
handoffs. The earlier raw Qwen traces remain historical and cannot prove SC behavior.

The provider auto-merge produced overlapping `argument_realization` objects;
JSON loading selected the later local object and hid upstream named entries.
The upstream manifest regression failed before delivery. Resolution restores
all upstream entries and names, then adds only `physical_resource_route`.
Eight execution-contract cases cover entity/item/quantity/recipient and four
source bindings; the existing manifest tests prove upstream keys remain visible.
Combined provider validation passes 798 tests / two skips, body 165 and task 147,
plus governance, compile and manifest checks. Commit `fa6331f` is pushed to
`origin/codex/turn-count`; unrelated Open_Duck_Playground content is preserved.

The current SC-aware corpus rebind changes five prototype and 4,600 large cases,
replacing 126 Schema artifacts. Each changed case is compared with its original
with only request.format excluded; all other fields are equal. Large manifest:
`9ad69c12b0f60554df1ec5da249cd1cb300e81a79cec9d7d09b8933c6137dba8` →
`3ba46381bf230f7a930982b05f8cebd9cb672ccd4efbfbdee14d0c4994084f04`.
Prototype manifest: `cf242af89fac44494202247c90e5056cc2ac024c252bbb225176f8f84109dc5e`.
The rebound focused workflow suite passes 104/104. Work re-entry diagnostics now
identify the Fast planning pass instead of incorrectly labeling it the wording
owner; regressions assert that SC's ownership is not assigned to Planner metadata.

Final combined canonical passes 3,382 tests / 1,139 subtests, 145 benchmarks and
20 legacy tests; pinned policy, ownership, static/configuration/docs checks pass.
The two existing FastAPI warnings remain. Full SC-aware 6,000 replay passes with
source unchanged, retaining the 1,400 / 1,800 / 2,580 / 220 expected-outcome split.
Level A passes 45/45. No new native SC, deployment, model or physical evidence is
claimed; reference independence, hidden semantic-family evaluation and target
closure remain open. Both handoffs carry the exact integrated scope and resume
boundary; the fetch-before-development rule is committed in both AGENTS.md files.
