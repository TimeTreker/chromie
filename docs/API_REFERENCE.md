# API and Protocol Reference

The [Social Cognition target](PROJECT_CHARTER.md#social-cognition--accepted-target-2026-09-14)
is source-implemented. The dedicated transaction below owns communication;
maintained Planner model outputs reject writable wording and decoration.
See [migration inventory](COGNITIVE_TURN_LOOP.md#source-migration-inventory).

This document describes interfaces implemented in this repository. Soridormi
is a separate deployment; only its checked-in capability contract is summarized
here. Current revision and verification status are maintained in
[STATUS.md](STATUS.md).

## Social Cognition transaction

`POST /social-cognition` accepts `SocialCognitionRequest` from a trusted state
owner. Triggers are interpretation, Goal state, Work state, Evidence or Situation;
UMI is optional for non-turn triggers. Input includes exact source references,
read-only Goal/Responsibility/Evidence scope, communication needs, trusted
Situation and disclosure-safe shared context. An optional typed `CognitiveOpportunity` preserves existing source, subject, Situation and depth readiness; local mechanical readiness never calls the model. No synthetic user turn is required.
For an interpretation-triggered call, the projection removes unbound retained
task state from both the outer context and its `session_memory` mirror. This keeps
historical Goals and delivery evidence available for their owned uses without
letting them replace the current reply. A Communicative Activity ID from
`prior_delivered_speech` may be cited by a new repair act, but cannot be rebound as
the new turn's act; same-turn delivery accounting may still reuse an unchanged ID.

`SocialCognitionResolution` contains request identity and snapshot digest, a
complete communication/silence decision, exact acts and bounded eligible social
expression proposals. One source-only deeper call is allowed for unresolved
cognition; trusted slow readiness enters that same deeper scope directly. Missing
required cognition is reported as a failure, never a fabricated silence decision. Goals, task Work and effect authorization are not writable fields.
The Host client rechecks identity/provenance; the runtime entrypoint requires the
state owner's freshness predicate before and after inference. Expression execution
uses the existing catalog/target/resource/duplicate-dispatch validators. Empty
nonverbal text creates no speech delivery or Goal-completion evidence.

Foreground calls use purpose `social_cognition` with the existing realtime compute
class; `social_cognition_deep` uses deliberative. Both reuse the configured model
transport and fast/deep profile settings. No new environment variable or service
is introduced. This endpoint alone does not establish default-turn integration,
native-model qualification, physical evidence or measured latency improvement.

## Local text console

### Dialogue transport

Owner: `scripts/chromie_psm_live_text_console.py`, the maintained post-ASR text
runner and its dialogue client. `./scripts/start_chromie.sh --text-console` runs
the runner's `--serve` entrypoint through `start_orchestrator.sh`; the latter
retains its generated profile, Soridormi/speaker configuration and exclusive
`ORCH_LOCK_FILE`. The client starts no Host and has no authority to configure
providers, author replies, or call cognitive roles directly. Default startup
without `--text-console` retains the voice path.

The local Unix socket is `.chromie/text-console/dialogue.sock` under the selected
checkout. Its directory is owned by the current user with mode `0700`; the socket
has mode `0600`. No TCP port is opened. Only one client is admitted at a time.
The server holds the existing Host lock before replacing a stale socket, rejects
non-socket paths, and removes its socket on shutdown. A second Host fails the lock
before constructing runtime state.

Each request is one UTF-8 JSON string followed by a newline, bounded to 65,536
encoded bytes including framing. Objects, malformed JSON/UTF-8 and oversized
requests are rejected before text admission; no client-supplied roles, session
IDs or semantic metadata are accepted. The Host creates the session and calls
`handle_routed_text(..., channel="text")`, retaining normal protective controls,
Goal/Planner authorities, confirmation and Soridormi safety.

Each response is one newline-delimited JSON object: `{"reply":"..."}` carries
exact newly recorded assistant dialogue; `{"done":true}` closes that admitted
turn. The client can send another line before the previous turn completes, and
replies may arrive while the next line is being typed.
The client renders only replies and its input prompt. Diagnostics, exceptions,
timings and development-command output remain in the startup terminal. An error
does not become an invented Chromie reply. The client displays a plain connection
notice if transport is unavailable. A client disconnect does not cancel admitted
Work or shut down the Host; reconnecting retains the same Host/conversation state.
The Host tracks each text turn through its normal routed-turn lifecycle, including
deterministic protective interruption. `/quit` disconnects the client but is not a
robot stop command; send `stop` for current-interaction cancellation or
`Stop moving.` for embodied-motion cancellation through the Gateway. Use the
Soridormi emergency-stop path for an emergency. The bounded completion
wait runs independently for each turn. This does not qualify native cognition or physical
delivery. Evidence levels and deployment closure remain owned by Status/Acceptance.

## Cognitive Core turn-interpretation API — Agent port 8092

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/cognitive-gateway/attention-review` | Return only bounded addressedness admission evidence for one inactive turn; it cannot author route, intent, capability, action, plan, or response. |
| `POST` | `/cognitive-core/interpret` | Interpret one admitted `CoreTurnRequest` containing an immutable `UserTurnEnvelope` and digest-bound `GatewayContextSnapshot`. |

The Cognitive Gateway remains an embedded Host boundary and does not expose a
separate semantic-routing service. It owns input normalization, protective
reflexes, attention review, bounded context assembly, and turn admission. The
Goal-Driven Cognitive Core owns ordinary meaning, goal interpretation, task
continuity proposals, capability intent, planning handoff, and response intent.

Host context may report robot state only from observed provider/runtime facts.
`VoiceAssistant.build_context` does not synthesize `robot_state.available` from
`action_dry_run`: permission to execute and observed availability are different
inputs. Without a provider observation, the base context omits that state claim;
execution authorization and provider safety checks remain independently enforced.

`POST /cognitive-gateway/attention-review` accepts only normalized turn identity,
text, language, and bounded host engagement evidence. It makes one model call.
Suppression is limited to high-confidence unaddressed ambient speech while engagement
is inactive. Direct, unclear, low-confidence, contradictory, malformed, unavailable or
failed review admits the turn without a second call
([Gateway §4.3](COGNITIVE_GATEWAY.md#43-attention-review--注意审查)).

`POST /cognitive-core/interpret` accepts only a schema-valid admitted
`CoreTurnRequest`. Bare text, a suppressed envelope, mismatched context identity,
or a context digest mismatch is rejected before User Meaning Interpretation. The result
is a `CoreInterpretationResult` bound to the turn. It contains only
provider-neutral Responsibility evidence, bounded confidence/language, and unresolved
meaning. It has no `route`, `intent`, Capability identity, response wording, or
compatibility projection and does not authorize side effects. The Orchestrator still
validates schemas, authorization, confirmation, resource conflicts, commitment,
and trusted execution evidence before any effectful request runs.

A successful interpretation returns HTTP `200` with `CoreInterpretationResult`.
When a non-empty admitted turn cannot be interpreted after the bounded model
path, the endpoint returns HTTP `503` with
`CoreInterpretationUnavailable`. That result carries turn identity and a typed
failure reason but no invented route, intent, action, or compatibility
projection. Callers must surface or handle that unavailable result; they must
not reinterpret it as generic chat.

The implementation may use fast and review models, but it must reason from
meaning, context, active goals, and capability descriptions. Production code
must not use phrase tables, regular-expression intent routing, scenario IDs, or
fixed input-to-action mappings.

## Agent HTTP API — port 8092

FastAPI also exposes its generated OpenAPI UI at `/docs` while the service is
running.

### Runtime and capability inspection

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Return current model/runtime state, loaded capability sources, Planner availability, and WorkDAG diagnostic counters. |
| `POST` | `/cognitive-gateway/attention-review` | Focused pre-Core admission review; returns addressedness evidence only and fails open. |
| `POST` | `/cognitive-core/interpret` | Envelope-first ordinary semantic User Meaning Interpretation inside the Core. |
| `GET` | `/agent-skills` | Return bounded owner-approved Agent Skill metadata summaries and configured package provenance only; no Skill body or projection text. |
| `GET` | `/capabilities` | Return the active merged static capability registry and manifest sources. |
| `GET` | `/capabilities/catalog` | Return the shared catalog, including last-known live named capabilities and refresh status. |
| `GET` | `/capabilities/llm-context?language=en&text=...` | Return concise LLM context for at most `limit` catalog entries (default `20`, capped at `64`); `text` is accepted at the interface but does not filter capabilities. |
| `POST` | `/goal-association` | Resolve continuity-before-creation and independent Goal segmentation for the unified runtime; the endpoint itself does not mutate host state. |
| `POST` | `/cognitive-activation` | Decide whether a trusted internal state transition should wake one of the exact existing authorities allowed by the Host scope. It cannot author Goal meaning, Work, wording, Capability selection, execution, or completion truth. |
| `POST` | `/plan` | Produce the one Planner's complete `CanonicalPlan` (need-first: an unmet ability loads library contracts and the Planner plans once with them); a limitation is an honest `unavailable` outcome whose every Goal carries a Planner `result` communication need, so Social Cognition says it in the same turn. `/deep-plan` was removed on 2026-10-11; there is no second planner. |
| `POST` | `/value-judgment` | VALUE-JUDGMENT-001: one call returning `ValueJudgmentResult` (`affected`, `concern`, `decision` proceed/ask/decline, `reason`) for a `CognitiveWorkRequest` whose context carries the owner-approved Stable Mind. Never plans or words. Any failure returns `status=failed`, which withholds reviewed effects. |
| `POST` | `/social-cognition` | One interaction-planning transaction for trusted UMI, Goal, Work, Evidence and Situation snapshots. Preserves pending communication obligations, exact acts and optional eligible expression; no task Work or Goal mutation. |
| `POST` | `/social-cognition/startup-greeting` | Social Cognition's optional wake-up line from the owner-approved Mind and trusted local clock facts (`SocialStartupGreetingRequest`); returns `communicate` with exact words or `silence`. One model call, no Goal, Work or Evidence. |
| `POST` | `/reflection` | Run selective slow-cognition Reflection for one trusted evidence-bound `CognitiveOpportunity`; it may propose future replan, clarification, correction, or bounded task/session Memory for still-open Responsibility but cannot reopen completed outcomes, execution authority, or history. |
| `POST` | `/tools/execute` | Execute one exact planner-selected, explicitly interaction-executable safe read-only local capability and return structured evidence only. |

`POST /cognitive-activation` preserves the entire trusted re-entry scope (up to
16 Goals, 32 source refs and 12 Responsibilities), matching the existing re-entry
Goal/Evidence bounds. Every selected authority must retain the exact supplied
scope. Host projection removes non-owned envelope fields, but never slices scoped
lifecycle rows or discards the caller's disclosure-safe Memory and Interaction
context. Oversized contracts and model-context budgets fail before inference;
they do not authorize a partial-scope wake.

For planning, an accepted `media_playback` Goal does not require UMI or
GA to pre-extract `media_operation`. Missing/`none` leaves this HOW choice to the
Planner primary result. A retained explicit operation constrains the exact media
Capability; unsupported retained values reject. Availability is checked against
the disclosed media catalog, with no speech/vocal substitution or implicit
provider enablement. Goal coverage, argument provenance and provider safety
validation continue to apply.

`GET /agent-skills` reports the passive read-only cognitive-content registry.
The maintained repository root is mounted read-only and contains the approved
`chromie.grounded-external-information` and `chromie.weather-information`
packages. Startup validates safe YAML, explicit
`authority=agent_method_only`, explicit `execution_authority=none`, owner
approval, semantic version, deterministic package digest, projection paths,
duplicate IDs, parent references, inheritance cycles, and normalized
package applicability metadata. The endpoint exposes only immutable bounded summaries. The
two packages expose only the `fast_planner` projection, the single Agent role the
contract accepts (`AgentSkillProjectionName`); the
weather package declares the grounded method as its parent and remains passive
despite referencing required/optional Capabilities.

The Agent Skill selection service accepts the responsible Agent projection name, the
current user text, bounded Goal context, optional bounded context summaries, and
an optional explicit candidate-ID set. The Host performs only structural
discovery: it filters by declared projection, validates explicit IDs, sorts and
caps the candidate summaries, then lets the configured model author an explicit
`no_skill` or ordered one/multi-Skill decision. The closed output is validated
against the exact disclosed IDs, versions, projection, Goal IDs, confidence,
and registry digest. There is at most one primary model call and no model repair or
reselection. Invalid output returns `model_contract_failed` with the original error;
the existing repair-history flags are false. Deterministic JSON parsing is unchanged;
model or contract failure returns an optional no-Skill resolution rather than
fabricating method provenance. No `SKILL.md` or projection text is loaded, no
Canonical Plan is changed, and no Capability is registered, authorized, or
executed. Candidate discovery is bounded by the declared Agent role and package metadata;
semantic selection remains model-authored from the current Goal and Responsibility
context rather than a retired UMI route/intent classification. `/health` reports
whether this independent selection boundary is enabled plus its model and candidate limits.

Catalog entries include `prompt_tier=common|rare`, plus
`prompt_tier_locked`, `prompt_tier_source`, and `prompt_tier_reason`. The
Planner receives full unlocked `common` contracts and an index of every
entry, including unavailable and locked entries. Its Work begins with
`ability_needs`: each needed ability once, its closest loaded Capability, a
restatement of what that Capability does, and `fits`. When an ability does not fit,
the Host stops reading, searches the library with the Planner's need wording
(BM25 over ID, description and when-to-use) and reruns the original context once
with at most eight usable contracts. Search never returns unavailable, restricted,
non-executable or turn-ineligible entries, and the first pass contributes no Plan. Search
covers every contract the Planner did not see, including a common contract the Goal
applicability filter hid; loaded contracts are composition components and are not
filtered against the whole Goal again. A speech-only turn loads nothing. A provider media,
vocal, information or resource Goal without a loaded provider is decoded as `unavailable`
until a search loads one. User Meaning Interpretation remains WHAT-only
and does not gain Capability-selection authority from catalog projection. Safety-locked
entries are excluded from the common prompt even when an experience overlay requests
`common`, and search never returns them. The initial
preset is data in `capabilities/prompt_tiers.json`, not a Python skill list.
`chromie.speak` remains a trusted Vocal transport capability, but the Goal-driven
Planner schemas exclude it as a task-plan response-transport leaf. A mixed
conversational/body turn may use a goal-scoped `respond` outcome plus executable
body steps, and executable planner outcomes carry word-free communication Needs. SC owns
exact wording and Social Attention expression, including whether to speak, act
nonverbally or stay silent; neither communication nor catalogue visibility proves
or authorizes the requested effect. Search scores are relevance signals for catalog
inspection endpoints, not User Meaning Interpretation execution authorization.

The disclosure service accepts a previously validated selection and loads
only its exact matching role projections. The Loader rechecks package content,
applies per-projection/aggregate/count budgets, omits rather than truncates
oversized content, and returns typed failures plus a disclosure digest. Only the
Planner endpoint (`/plan`) performs this selection/disclosure automatically;
Goal Association, Fast-advance and Value Judgment receive no Agent Skill methods.
Caller-supplied disclosure context is removed before trusted injection.

### Cognitive planning and interaction support

The retired Agent `/run`, `/interaction`, and `/agents` endpoints are not part of
the maintained service. User-turn orchestration is Host-owned; the Agent service
exposes bounded cognitive module endpoints plus trusted tool/WorkDAG support.
Important interaction-related endpoints are:

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/plan-advance` | Stream one complete Planner Work result or typed failure as NDJSON; no presentation prefix. One bounded catalog lookup may precede the Work decision. |
| `POST` | `/goal-association` | Commit no Host state; return the model-authored canonical Goal association/segmentation proposal for Host application. |
| `POST` | `/tools/execute` | Trusted execution boundary for exact local safe-read capability requests already selected by the Goal-driven planner. |

The maintained Goal-driven planning endpoints (`/plan-advance`, `/goal-association`,
`/plan`, `/value-judgment`, and `/reflection`) accept a typed
`CognitiveWorkRequest`: `sid`, original `text`, optional `language`, first-class
`responsibilities`, interpretation confidence/unresolved meaning, bounded `context`, and
`history`. Re-entry requests additionally carry an immutable `planner_reentry_scope`;
ordinary initial requests omit it. They do not accept a Goal-Interpreter `route_decision`.

The maintained Cognitive Core interpretation result contains first-class
`responsibilities` as provider-neutral Goal-Interpretation evidence: a local reference,
complete human outcome, requested result type (`output_mode`), and
the primary-result source evidence required for mechanical coverage validation.
Effectful or multi-Responsibility results do not cross a second LLM coverage reviewer.
Responsibility evidence is the authoritative WHAT handoff
for downstream cognition; it is not a Goal, Plan, or Goal-Association-only DTO.
Parameter bindings, Goal relationships, activation timestamps, Capability IDs,
executable args/actions, provider identity, execution methods,
Activities, response wording, `route`, and `intent` are forbidden.

UMI primary and depth use the same closed intent-only wire. Exact source spans are
validated for identity and ordering; Responsibilities may share source words. Both variants receive the complete
authoritative token table; the existing transport budget rejects oversized input
instead of silently dropping its tail. UMI and Fast share the ordered source-span
decoder contract; backward endpoints are excluded before Host validation. This does
not select a span or prove that its material meaning is complete. UMI does not receive Capability
argument schemas or normalize duration, speed, direction or activation time into
execution fields. GA inherits new Goal meaning and result type from the accepted
source ref; Planner realizes inputs and scheduling. Source membership alone does
not establish semantic completeness or correct conversion.

Planning `InformationGap` creation/resolution, execution-input completeness, blocking
status, source/default selection, and clarification selection belong to Planner.
UMI carries complete Responsibility meaning, requested result type, source evidence
and bounded unresolved meaning. GA owns Goal relations;
its maintained schema contains no planning-gap or resolution-policy fields.

`POST /plan-advance` consumes the authoritative user turn plus contextual Responsibility
evidence and makes one complete planning invocation, optionally preceded by a
need-first pass that stops at `ability_needs` when a library search is needed.
Neither call receives a candidate Plan to repair. The response media type is
`application/x-ndjson`. Its ordered typed frames are:

One `FastPlannerStreamTerminal` (`frame_type=terminal`) is emitted only after the
complete Work JSON, end of stream, raw Schema, DTO and Host validation succeed.
Otherwise one `FastPlannerStreamFailure` (`frame_type=failure`) grants no Work.
There is no presentation frame or partial dispatch. `FastPlannerWorkAdvanceOutput`
first decides every Responsibility in `responsibility_decisions` (`work`, `answer`,
`clarify`, or `unavailable` with up to four `missing` facts), states `activity_count`, then
realizes each non-limitation decision with its own Capability Activity or word-free
response/input Need. The decoder fixes `activities` to exactly `activity_count` items and
the Host takes the count before the DTO (it must equal the Activities written), so a
value-closing token can no longer open an extra, copied Activity. A limitation is that decision, not a model-authored Activity: the Host binds it
as the unavailable Activity (a terminal Activity for that Responsibility) and the
Planner's result need. An `answer` decision whose word-free response Need was omitted
is bound the same way (the Need names only its Responsibility); `work` and `clarify`
carry content only the model authors and fail closed without their Activity, so the decoder
requires a `clarify` state's Activity, and an `unresolved_meaning` gap cites the exact UMI
uncertainty wording. A mixed
state may therefore hold only a response or an input Need beside a limitation.
Ordinary speech is always answered, never decided unavailable. An information
Responsibility that current established perception already answers first names those
`situation.interpretations` IDs in its decision's `observed_refs`, then decides
`answer_from_perception`; only a non-empty `observed_refs` opens that decision, which
carries no authored Activity: the Host binds it as a word-free response Need whose
`situation_interpretation_refs` are those IDs (it admits only current established
perception). Every other decision of such a Responsibility states `observed_refs: []`. Each uniform disposition
state admits only its matching decision; the authored disposition must equal the one
the decisions imply, and a contradiction fails closed without rewriting. An
acquire-information read serving a non-information Responsibility (for example a
conditional action) states the decision its result settles in `deferred_requirement`.
The dependent action rides in the same Work with `deferred: true` and `depends_on` that
read (owner choice B, 2026-10-12): when a read is on offer every effect states `deferred`,
and a deferred effect waits only on reads of its own Responsibility. A uniform decision
state offers only the roles its decision realizes (no clarification beside `work`). The Host keeps it out
of execution groups and executable steps, carries it as the Plan's `deferred_steps`, and
Runtime never starts it; the evidence re-entry sees it and performs it through `new_work`
only when the Evidence settles the condition in favour. Canonical and re-entry
steps likewise offer only their provider's purpose, and `acquire_information` requires
`expected_outcome`. In a mixed turn the decoder fixes each Responsibility's decision before
Activities (every decision pair with two Responsibilities; each set of `unavailable` ones with
three) and offers an Activity only to a Responsibility whose decision it realizes. The Host binds
accepted Responsibility references to canonical Goals and materializes exact
`communication_needs`; `/social-cognition` supplies any actual communication.

The single primary invocation cannot retry, review or rewrite its semantic decision.
Duplicate object keys, non-finite numbers, incomplete JSON and out-of-scope references
fail closed. Neither raw provider tokens nor an incomplete DTO reaches playback or
a Capability. Independently delivered SC acknowledgement remains an actual delivery
fact even when Work planning later fails; it does not authorize that failed Work.

A clarification Need owns one
or more typed Planner `InformationGap` records and no `response_text`. A semantic gap
must cite one exact UMI `unresolved` string; an execution-input gap must cite one exact
available Capability ID and its genuinely absent, required, non-defaulted schema input.
Before accepting terminal work, Host validation requires every supplied UMI unresolved
meaning to appear in an exact semantic-gap citation. A clarification blocks completion
and Capability execution for its own Responsibility refs; a mixed result may execute
independent refs. The request Schema excludes pure `execute`/`respond` when UMI meaning
is unresolved and permits enough gap records for the supplied meanings, within the
existing eight-gap DTO bound. Cross-Activity conservation is enforced by Host validation;
omission fails closed without a semantic repair call. A limitation itself authorizes no Work.
The gap records which authorized context, observation/query, preference, schema, or
safe-default sources were considered. Goal Association starts concurrently from the same
UMI result and remains the sole canonical
Goal commit owner; it does not author clarification wording. After deterministic
Responsibility-to-Goal binding, the Host atomically attaches Planner gaps to the exact
canonical Goal before clarification wording may be delivered. No Capability Activity,
including a safe read, starts before the complete terminal
result, canonical Goal binding, and full trusted Plan validation. GA emits no
replan or compatibility flag. `/plan` receives the Canonical Goal plus a bounded
`existing_work_activities` projection of relevant retained Runtime
Work and active task bindings without cancelling
first. The Planner explicitly sets `CanonicalPlanStep.reuse_activity_id` to an existing
stable Activity identity when it wants reuse and authors the complete desired Plan;
omission means no reuse selection. Runtime reuses the task only after Host
validation proves exact request/version/state, Capability IDs, arguments, Goal ownership,
and multi-Activity timing; otherwise it cancels pending/cancellable retained Work
after the Planner decision and executes the corrected Plan.

SC Communicative Activities carry exact text, truth stage, supplied provenance and
Evidence references. The decoder has each act state the needs it fulfills and their phase
before its words; one act may fulfill several needs, and an answer Value Judgment withheld
is never offered for binding. The Host validates and transports
their words unchanged. A handover close requested after the handover completed is an
`immediate` need (its ordering is already met).
Planner records answer/input/result obligations and exact `before_step_ids` /
`after_step_ids`. The response projection joins SC acts to immutable Work without
copying speech back into the Plan. Required confirmation and communication ordered
before Work wait for the appropriate delivery/consent barrier; optional progress
cannot delay task Work. Only an actually delivered covered answer can complete a
responding Goal. A progress report cannot complete an executable Goal.

On terminal Evidence re-entry, `/plan` receives the bounded current Responsibility/Goal/Situation/Work/Evidence state and an immutable `PlannerReentryScope`. The scope binds the exact trigger, affected Goal IDs, Evidence refs or opportunity identity, and originating Plan identity/fingerprint when available. Prompt projection, response schema, and final validation use only that Goal set; scope disagreement fails closed. The Planner may answer or author genuinely new follow-up Work for those Goals. Planner establishes the Work outcome and required communication facts. SC independently authors any post-Evidence words against that exact Goal/Evidence scope, execution status and epistemic strength. Trusted validation checks only closed schema and provenance mechanics; it cannot call a second model to qualify, review, or repair the response. The re-entry decoder offers only what that validation accepts: `next_action` is `respond`, `execute`, `clarify` or `unavailable` (a failed or silent provider is `unavailable`; refusing is Value Judgment's, never a Planner next action on any pass), `respond` cites completed Evidence only, `respond`/`execute` keep no unresolved needs, `clarify` names at least one as a short fact the person can supply (never wording), and with no new Work the relation is `exact` without confirmation (adjusted or alternative Work is confirmed). New Work may cite completed Work in `depends_on` by its step_id or evidence_ref.
Satisfaction is prospective (the Goal once the selected action succeeds); outside
reporting re-entries the decoder offers `respond` only at substantial or exact. Failure at this boundary fails closed; the Host never rewrites the sentence, and the person hears the Host's operational failure notice instead of silence.

`POST /plan` is the bounded re-entrant canonical Planner endpoint, available only when `AGENT_PLANNER_ENABLED=1` and Agent LLM use is enabled. A valid `/plan-advance` may finish an easy turn directly after its terminal result is mechanically bound to GA's conserved Responsibility-to-Goal mapping. Creating a new resource Goal from that unchanged Responsibility does not call `/plan` again. Actual provisional or retained Work, a GA-authored change to retained Goal meaning, trusted Evidence/result re-entry, or another material open-Responsibility event calls `/plan` with a bounded current Work snapshot. It decides whether existing Work remains in the complete desired Plan; GA and Orchestrator do not make that semantic choice. The endpoint never executes by itself, and trusted Runtime revalidates exact identity, version, authorization, resources, and safety before applying the Plan.

`existing_work_activities` is the single bounded Planner input projection for same-turn provisional and retained Runtime Work. A Planner step selects
reuse only by setting `reuse_activity_id` to one supplied stable identity while
preserving Capability, arguments, Goal ownership, and timing. Retained-work reuse is
currently atomic and reuse-only: it selects the complete retained set with no
additional step, preserves the original Runtime submission/Goal execution binding, and
dispatches nothing twice. A replacement Plan omits reuse IDs; Host validation and exact
cancellation receipts must close cancellable old Work before replacement dispatch.

Executable identity is canonicalized as `capability_id` in planner schemas,
Canonical Plan steps, Interaction Capability requests/results/traces, and
execution evidence. Live Chromie contracts do not accept or emit executable
`skill_id` aliases, and `InteractionResponse.capabilities` contains canonical
`CapabilityRequest` objects. Provider-local identity such as Soridormi wire
`skill_id` is translated only inside the owning adapter boundary.

Planner responses also expose `CanonicalPlan.selected_agent_skills`. Each item is
a content-free provenance record containing the exact selection/disclosure IDs,
selecting planner role, Agent Skill ID/version, package/projection/disclosure
digests, explicit relevant Goal IDs, rationale, and confidence. A Plan may contain
only Planner (`fast_planner` projection) provenance; a rejected provenance join is a
contract failure that fails closed. This field
is included in Plan fingerprints and replay serialization but is ignored by
Capability authorization and execution.

Planner failure results (`path_classification=contract_failure`) contain no executable
steps or invented response text and explicitly set `metadata.execution_allowed=False`;
original rejection evidence is retained for the Runtime’s existing silent failure path. Planner repetition validation
rejects a count-bound Capability without a count input: an unrelated duration or
intensity value cannot witness repetition. Node-based repetition is not implied. The
owner-authorized Soridormi `turn_in_place` catalog now supplies integer `count`
(1-8, default 1), per-repetition `duration_s`, and a 20-second aggregate limit.
The Planner authors count; Soridormi expands sequential segments under its existing
safety lifecycle. Positive yaw means left, negative means right. Host validation
still requires an explicit matching argument for a UMI-bound count; unrelated
numeric arguments remain invalid witnesses. Acceptance observations retain count
alongside duration and yaw, without deriving it from node cardinality.

A fully specified acquisition stage may use complete coverage with partial whole-Goal
satisfaction. Both assessments retain deferred requirements. `GoalExecutionOutcome`
now carries `acquisition_step_ids` and `planned_satisfaction` copied from its source
Plan. Its terminal `status` still describes Work; derived continuation requirements
keep the Goal open. Re-entry must bind the source Plan ID/fingerprint, exact acquisition
steps, and matching completed, schema-valid observations before the next conditional
decision. A response settles the Goal only after delivered speech; a proposed effect
still requires ordinary confirmation and terminal evidence. A Plan that needs the
person's consent carries a word-free confirmation Need; Social Cognition authors the
question, and the Host rejects blank confirmation speech for any selected
confirmation-gated Capability. Other Goal outcomes retain
independent adequacy and completion checks.

`POST /value-judgment` is available when Agent LLM use and the Planner are enabled; it uses the Planner model service and deadline with prompt family `value_judgment.primary`. The Orchestrator calls it in apply mode, before confirmation and dispatch, for the turn's first Plan and for any later Plan of the same turn (Planner state re-entry) that uses a Capability listed in `capabilities/value_review.json`, or realizes `value_review` speech, not yet judged in that turn; a verdict already given in the turn for the same Capability or Responsibility is reused without another call. Planner-authored copies of verdict annotations are discarded. The request is the turn's `CognitiveWorkRequest` with the planning context, including `context.mind`. The resolver refuses to judge without an owner-approved Stable Mind. Verdicts annotate only the reviewed steps: `proceed` leaves them unchanged; `ask` sets `requires_confirmation` and adds a runtime confirmation need whose facts carry `value_question`; `decline`, `failed`, or an unreachable endpoint marks them `value_withheld`, and Runtime refuses them before provider start with `reason_code=value_judgment_declined` and the verdict reason as the result message; a withheld request never joins a prepared or provider-local group. A decline also adds a Runtime-owned `result` communication need (facts `value_declined`, `withheld_capability_ids`), so Social Cognition declines in the same turn, and value-declined Evidence never re-enters the Planner. Social Cognition receives a value guard only when a need carries `value_question`, `value_declined` or `value_withheld`, or a `value_review` Responsibility has no reviewed need yet. Unreviewed steps in the same Plan are unaffected. UMI marks a speech Responsibility `value_review` when it asks Chromie to tell someone something untrue as if true, or to deceive or manipulate a person (owner choice B, 2026-10-12). Runtime then includes it in the Planner scope, and Value Judgment reviews the answer needs and steps that realize it. `proceed` leaves the answer free. `ask` marks the answer need `value_withheld` and adds a Runtime-owned `input` need with `value_question`. `decline` or a failed judgment marks it withheld and adds the `value_declined` result need. Conversation state records that Goal as `clarify` (ask) or `value_declined` (decline; it ends like a limitation, without a pre-dispatch responsibility change). Social Cognition never covers a withheld answer, and before a reviewed need exists it may only acknowledge such speech neutrally.

Canonical Plan contract (`/plan`, `planner_tier=fast`; the only tier). The one Planner may execute, respond, clarify, or report unavailable; it never refuses (whether Chromie should act is Value Judgment's, and a body the provider cannot drive safely is an `unavailable` limitation), and its model DTOs reject a `refused` disposition. A per-Goal `unavailable` outcome may sit beside sibling Work in a `mixed` Plan for up to four Goals. Each Goal outcome is decoded as native per-disposition branches (coverage, `step_ids`, `unresolved` and communication ordering allowed by that disposition); an effectful Goal is never offered `respond` (for one Goal as for several, as Host enforces), and `time_conditions` follow `ability_needs` so future readiness is stated before any outcome; the top-level disposition and coverage remain model-authored and a contradiction with the Goal outcomes fails closed. Complete multi-goal model output uses `goal_outcomes` as an exact object keyed once by every authoritative Goal ID; the host materializes the canonical outcome list in authoritative order. Satisfaction is a prospective plan-adequacy assessment, not execution evidence, and the model writes it once per Goal: every `goal_outcomes[*].satisfaction` is required on every `/plan` answer (single-Goal included). The Plan-level `goal_satisfaction` is not model-writable (the decoder schema and the DTO reject it); Host folds it mechanically from the per-Goal judgments (lowest score, worst status, unions of satisfied/unmet Goal IDs and unmet requirements, joined rationales) and records `model_authored_goal_satisfaction: false` / `host_derived_goal_satisfaction: true` in the Plan metadata. A supplied low per-goal score remains authoritative. Ordinary speech Goals use `respond` only when their requested content can be supplied truthfully; they may instead clarify or report unavailable; Social Cognition communicates a Value Judgment decline. An independent completed speech Goal may coexist with such a limitation in a zero-step `mixed` Plan. Every unmet Goal must remain unmet in its per-Goal satisfaction, which the folded aggregate conserves; complete coverage is accounting, not fulfillment. Zero-step mixed speech grants no executable work or confirmation authority. An explicit future `ready_at` may instead receive a scoped waiting acknowledgement with its exact Planner-authored time condition and original Goal still unmet. That condition wakes cognition later; it does not delay a step listed in the current Plan. New intent-only scheduling uses a Planner-authored exact `source_quote` and future time condition, without a UMI timer field. A newly waiting Goal may coexist with independently ready sibling Work; it remains unmet, owns no current executable step and wakes only at its validated time. Ready independent siblings and a timer for monitoring already-running Work retain their normal contracts. A trusted state wake with no new Goal Association result resolves only its exact persisted open Goal snapshots, bound to the matching CognitiveOpportunity. Missing, duplicated, mismatched or terminal snapshots fail before inference; no new Goal or association is authored by this projection. The primary request carries the captured Host clock comparison, including exact already-reached readiness times; old future-tense source wording cannot reschedule that same instant. Readiness itself grants no execution or completion authority. Canonical and streamed planning may combine an independent response with clarification or an honest limitation without a Capability Activity. Runtime preserves the question/waiting lifecycle or final limitation speech instead of labeling every mixed response pre-action. Parallel timing is accepted only from provider catalog entries that explicitly declare compatible parallel safety and resources. Otherwise the planner must fail closed or author a typed `safe_adjustment`/`alternative`; `plan_relation` and `user_confirmation_required` enforce user confirmation before the host transfers that judgment to canonical metadata. The Planner uses one primary model invocation (plus at most one need-first pass with loaded contracts) and fails closed on invalid output. Its commitment bar is 0.75 prospective satisfaction; a Plan it judges below the bar becomes an honest limitation. Structural, grounding, coverage, applicability and safety rejections fail closed and are never rewritten by another model pass.

The retired `escalation_reason` field is rejected by Schema and Host. The Planner
receives exact bounded UMI unresolved evidence and the requested response language.
It receives first-class `CognitiveWorkRequest.history` through
at most six retained user/assistant records with exact text and delivery-source
metadata. The history records are not truncated and have no separate character
budget; the transport admits the complete prompt against the configured model
context budget (token preflight). Historical dialogue does not establish current
world truth, and authored assistant text is not automatically audible-delivery
Evidence. Native canonical speech schemas expose complete aggregate branches,
while full Schema/DTO/Host validation remains required.

Trusted Goal-free Situation uses `POST /social-cognition`; the former dedicated
Situation endpoint and DTOs have been removed. The request binds its
`situation_revision` opportunity to the exact Situation digest, sources, subjects
and audience. Host activates only disclosure-safe Memory and supplies the current
Interaction Ledger. SC may choose silence, several exact verbal acts, or a wordless
eligible expression. No UserTurn, Responsibility or task Goal is fabricated.

The Host rechecks complete result provenance, immutable wording, delivered repair
references and every Memory candidate before any Memory write. A newer admitted
revision from the same source suppresses an in-flight older decision. Speech and
optional expression share the same decision; expression still passes existing
catalog, target, confirmation, resource and deduplication gates. Playback receipts
retain SC ownership, addressed communication needs and Responsibility references;
queued or interrupted output is never completed delivery. Concrete perception
adapters and current end-to-end model/interaction quality remain unqualified.

`CanonicalPlan.communication_needs` records Planner-established answer, input,
confirmation or result obligations with exact Plan/Goal provenance and optional
`delivery_phase` ordering. SC accounts for each as covered or pending. A Planner
result need whose Goal is `unavailable` or `refused`, a Runtime value-decline need,
and a Runtime value-question input need must be covered by a new verbal act in the same decision (no silence, and an
earlier acknowledgement cannot cover it) unless an earlier act already addressed it
or the turn carries a protective silence request. The Host
joins exact SC acts and immutable Work in `PlannerResponseProjection`; multiple
acts may share a phase without merging their commitments or coverage. Only an
explicitly covered answer need for a responding Goal may bind its actual speech
delivery to Goal completion. Progress and silence cannot complete that Goal.
Optional progress has no playback-start barrier for task Work; required input,
confirmation and before-action ordering retain their barriers. The ordinary turn, confirmation and result re-entry paths use this join.

`POST /reflection` reuses the deliberative model (`AGENT_DELIBERATIVE_MODEL`) only for a trusted `CognitiveOpportunity` whose `recommended_cognition` is `slow`. The Host supplies the exact affected Goal IDs and evidence references and binds those identities into the returned `ReflectionResolution`; the model cannot widen them. Reflection is optional post-outcome cognition. The Host starts it only after eligible result planning has settled, under one bounded existing background task. Requests carry the privacy-filtered owner-approved Mind. Replan/clarification/correction proposals are retained as diagnostics without current Planner re-entry; only actually applied bounded Memory counts as future adaptation. **Current endpoint semantics remain open-Responsibility-only:** applied actions require runtime-bound trusted evidence and a completed outcome is terminal to this API path. Reflection may propose future replan, clarification, a future user correction candidate, or bounded `task`/`session` Memory candidates. It cannot authorize effects, reopen the current turn, rewrite `ExecutionOutcome`/Evidence/history, change Stable Mind, or create provider capabilities. A Memory proposal is not durable by itself: the Host promotes only matching repeated-evidence candidates to ephemeral task/session Memory, while durable profile Memory retains the existing explicit-current-turn-consent boundary. The accepted architecture now specifies a later contract split in which terminal evidence may support bounded `experience`/`calibration` without reopening Responsibility; that design is not implemented by this endpoint yet.

Only `/social-cognition` exposes optional `auxiliary_activities[]`, nested under its
exact communicative act. Requested gestures remain ordinary Planner Work. SC receives
eligible catalog candidates and trusted target evidence; a Capability the current or
source Plan selected or deferred is never a candidate. Runtime can execute the exact
validated expression or suppress it without replacing its meaning or blocking Work. A
gesture paired with speech that waits for result Evidence waits with it; only
result-producing Work, never decoration, defers such speech.

`POST /tools/execute` is a trusted provider boundary, not a semantic router. It accepts an exact `capability_id` and schema-valid arguments already produced by the Goal-driven planner. The Agent rejects unknown, unavailable, non-local, side-effecting, confirmation-gated, or non-`safe_read` capabilities and returns structured output without composing user speech. The Trusted Capability Runtime (`CapabilityRuntime`) remains responsible for provider registration, input validation, timing, cancellation, and correlated execution evidence. The first maintained binding is `chromie.weather.lookup`; additional local tools require an explicit manifest declaration and trusted provider binding rather than phrase rules.

`chromie.weather.lookup` accepts the canonical place plus Capability-local
`date=today|tomorrow` and `period=day|morning|afternoon|evening|night`. UMI and GA
retain human temporal scope; the Capability's model-visible `argument_realization`
contract tells Planner how to map that scope into these provider arguments. For this
Capability, a current-local-night scope realizes as `date=today` plus `period=night`.
Its completed output therefore includes a
non-null `forecast_period` with local start/end timestamps and period-scoped
temperature, apparent-temperature, precipitation-probability, and condition
evidence. When `forecast_period` is present, the top-level `condition`,
`weather_code`, `high_c`, `low_c`, `precipitation_probability_max`, and `summary`
are projections of that same requested period; explicitly named `current_*` fields
remain current observations and cannot support a future-period claim. If the provider cannot supply that hourly slice, execution fails with
`forecast_period_unavailable`; daily or current values are never relabeled as
night evidence. For a day-wide request, `forecast_period` is null.

Live provider Capabilities may publish the same model-visible
`metadata.argument_realization` contract when human semantic names differ from
provider-local parameter names. The provider owns that mapping; Chromie validates
that every declared target exists in the exact input schema and then projects it
unchanged to Planner. A `walk_velocity` provider can declare human
`speed -> vx_mps` and `duration -> duration_s`; applicability depends on the exact
live catalog, not a historical declaration. An explicit numeric request must
not be replaced by a provider default. The Host does not invent or repair the
semantic transformation. Both streaming Planner advance and canonical Planner validation
require `minimum_arguments` from every applicable realization contract whenever
an owned Responsibility/Goal explicitly binds its `source_entity_type`, including
optional and defaulted inputs. Other arguments and sibling Activities cannot
witness that presence. The provider declares gaze `duration -> duration_s` as well;
omitting it cannot silently select the four-second default. This is a presence
check; interpretation and unit conversion remain Planner-owned.

Canonical Planner validation also preserves repetition identity when projecting duplicate
parameter provenance. A typed count may support only an exact declared argument
name, a count-typed input, or a provider-declared count realization. Equal numeric
values alone cannot make a count evidence for duration, yaw, or another quantity.
The dynamic response schema excludes count-unrepresentable Goal ownership from
that Capability's step branches while retaining compatible sibling Goals and
nonexecution outcomes. Host validation rejects absent count applicability,
omitted realization, and explicit provenance crossing count identity. It does
not fill arguments or infer repetitions from the number of steps. Structured
resource quantities retain their separate nested grounding contract.

Terminal Capability results do not enter a separate interpretation endpoint. The
Host validates and correlates the result, binds a `ToolResultEvidence` object to
the exact immutable request Goal IDs, updates Goal/task state, and reactivates
`POST /plan` with a bounded Goal/Evidence snapshot. The re-entry Plan cannot
widen the Goal set or schedule duplicate execution. Any spoken answer is a
SC-owned post-evidence Communicative Activity with exact Evidence
references; missing provenance fails closed rather than inferring a Goal from
provider data.

`POST /goal-association` is available only when
`AGENT_GOAL_ASSOCIATION_ENABLED=1` and Agent LLM use is enabled. It applies
continuity before creation: each accepted UMI Responsibility is represented exactly
once by an existing-Goal association or a new-Goal identity/relationship row. GA
does not author clarification wording or revise accepted UMI meaning. Existing goal IDs must be copied
from the supplied active-goal snapshots; unknown or below-threshold associations
are rejected. Every validated new Goal retains provider-neutral WHAT semantics. `output_mode`
distinguishes ordinary speech, expressive speech, recitation, singing, humming,
nonverbal vocalization, body action, media playback, information, stateful effect,
or other. A complete media intention does not require a pre-extracted operation:
Planner derives the operation and Capability arguments from the accepted intention. The live model-facing and canonical Goal contracts do not contain
`responsibility_kind`, `execution_lane`, `provider_required`, or `capability_work`.
Those concepts are not reconstructed by the Host. Planner decides HOW from the
canonical Goal, current trusted state/Evidence, and the available Capability catalog;
selected Capability/Activity records carry Runtime execution facts separately. This
keeps Goal identity stable across provider changes and prevents Goal Association from
quietly taking back planning authority.
The live GA new-Goal schema contains only source Responsibility refs, related Goal
IDs and superseded Goal IDs. Description, criteria and result type are inherited
mechanically from UMI. Every identity row explicitly supplies all three arrays;
`related_goal_ids` can reference retained terminal history, while `supersedes_goal_ids`
can reference only supplied open Goals. Unknown, duplicate or overlapping IDs reject;
Host copies these GA choices unchanged and never infers a missing relationship.
The primary collections are `associations` and `new_goals`; the incomplete
`unassociated_responsibility_refs` field is retired with no compatibility path.
Resource details remain in that complete intention for Planner. UMI owns initial
Planner activation; Host does not invent it from the new-Goal result.

Existing typed resource Goals retain one nested authority:
`resource_responsibility.resource`, `.source`, `.recipient`, and `.delivery_mode`.
These are retained-state contracts, not writable fields of the current GA new-Goal
wire. A retained resource Goal's generic `bindings` must be empty. The Host creates an
output-only frozen flat grounding view for Planner consumers and records exact
canonical-field provenance; neither the model nor a downstream consumer may
write that view back into Goal semantics. Goal descriptions remain summaries and
cannot override these typed fields.
For a physical object, the canonical identity is the complete
`resource.description` plus `quantity`; `resource.attributes` is decoder-closed.
Acquisition location, distance, direction, and route are typed only in
`source.bindings`, while recipient meaning is typed only in `recipient`.
`resource.attributes` remains the typed query-scope owner for information
resources such as weather location, time, and requested aspects.

The target bounded transaction has one primary Goal Association semantic result
and at most one same-stage regeneration for a mechanically malformed DTO. It
mechanically conserves the authoritative UMI Responsibilities and their integrated
source/coverage evidence; it does not invoke a coverage reviewer, critic, fresh
interpretation, or final semantic recheck. A semantic, grounding, or conservation
rejection fails closed and cannot be repaired at the same authority. The current
repair gate accepts only extra-field and list/dictionary-shape errors. Missing
semantic fields, invalid values, semantic validator failures, and mixed failures
are terminal after the primary call; unknown validation error types fail closed.
Repository policy rejects restoration of the older certificate/reconsideration path. Live model quality
still requires current-revision qualification.

`GoalAssociationResolution.resolution_status` is the terminal contract:
`resolved` or `fail_closed`. `fail_closed` contains no associations, new Goals,
discourse mutations, progress bindings, clarification, or confidence and cannot be
committed or passed to a Planner. When UMI retains genuine semantic ambiguity, GA may
commit the narrowest source-grounded provisional Goal without deciding the missing
meaning; Planner alone decides whether to create a question-bearing gap. Model,
schema, audit, and retry failures never masquerade as user-resolvable ambiguity.
Mode-specific vocal output remains Vocal but requires provider evidence; a
generic `respond` outcome or ordinary TTS cannot close it. The eventual spoken
delivery of a capability result remains part of that capability-dependent Goal
rather than becoming a duplicate response Goal. The endpoint itself does not mutate task state,
authorize side effects, alter Cognitive Core interpretation output, or execute plans. The unified host uses its result
in `report_only` observation or authoritative `apply`, and only the host may
atomically commit the validated association.

User Meaning Interpretation decision as advisory context, replaces model-provided operation IDs with
stable request-bound IDs, rejects below-threshold or unknown-task operations,
and may return an immediate `ResponsePlan`. It never applies task changes,
authorizes side effects, or claims execution. The host decides whether to call
it in `off`, `report_only`, or `apply` mode and remains the authority for task
versions, confirmation validity, commitment, scheduling, and evidence.

The host context now includes compact prompt-memory fields:
`session_memory.memory_summary`, `session_memory.extracted_memory`, and
top-level `extracted_memory`. These are process-local session/task memory
summaries, not durable user-profile memory and not authorization for side
effects. User Meaning Interpretation projects accepted dialogue and retained Goal semantics
separately from ambient context. Root `conversation_id`, `session_id`, `turn_id`,
and `sid` are excluded from its primary and Deep semantic prompts; they remain
on the authoritative request for host correlation and logging. These bookkeeping
labels cannot supply user meaning. Raw `history` and `conversation` containers
remain excluded from the ambient context payload.
The separate identity projection preserves the configured
`identity.model_identity_boundary` alongside self-reference facts in both
interpretation prompts. Its required JSON fails explicitly above 1,200 characters
instead of dropping identity truth. Robotic embodiment does not establish any
particular Capability's availability.
Durable or session memory is not a User Meaning Interpretation route. Explicit memory
changes flow through typed, consent-bound memory proposals and the existing
Conversation State / memory capability boundary. The Host validates persistence
scope and explicit-current-turn consent mechanically; no separate memory semantic
agent or route label owns memory semantics. Retrieved verified tool results remain typed
Capability/Evidence work and cannot become factual speech without Planner and
Evidence qualification.

`InteractionResponse` can contain speech items and executable Capability requests.
Shared contracts reject unknown fields and recursively reject low-level motor,
joint, torque, and actuator fields. The maintained response is projected from
SC-owned Communicative Acts and Planner-owned Capability Activities. SC may include advisory
`auxiliary_activities[]` selected from the reviewed `social_attention` behavior
domain. They cannot author or adapt response text independently. Applied decoration requests carry
`metadata.source=social_cognition_auxiliary_activity`,
`metadata.auxiliary_plan_activity=true`,
`metadata.execution_lane=activity`, and
`metadata.execution_role=social_decoration`; they are excluded from user task
proposals and Goal completion. Runtime validation checks exact catalog
membership, schemas, target evidence, resource conflicts, confirmation policy,
and a bounded latency budget. Target evidence is semantic only; installation calibration and body-specific
coordinates are never part of the Chromie planning contract. Soridormi calls describe
targets in the [body target format](EXECUTION_LANES_AND_COORDINATION.md#body-target-descriptions):
the current speaker is `referent_id`/`target_ref` `"requester"`, objects by description
and places by cited name. The reserved `"requester"` names the current speaker and
needs no further target evidence: Soridormi resolves where that person is. The Soridormi
adapter maps an explicit speaker reference in a gaze `target_ref` (`me`, `user`,
`speaker`, `current_speaker`, `the requester`, case-insensitive) to `"requester"`; an
empty or missing `target_ref` is never defaulted to the speaker and fails as
`missing_target`. Any other look target is copied only from trusted target evidence. The Soridormi adapter hides `target_yaw_rad`/`target_pitch_rad`
from the catalog and refuses requests carrying them (`body_frame_target_not_semantic`).
Soridormi resolves the target from perception; a target it cannot find returns
`completed: false`, surfaced as a failed result with Soridormi's typed reason (or
`execution_incomplete`), never as completion. SC decoration gestures such as a nod,
look or bow are eligible when Soridormi declares them low-risk expressive skills;
locomotion is not. Concrete user-requested actions remain primary
CanonicalPlan goals and cannot be replaced by auxiliary expression. Body and tool requests flow through model-assisted User Meaning Interpretation, the live
capability catalog, the single Planner authority, schemas, and Trusted Capability
Runtime validation rather than hidden phrase parsers or a retired routing layer. Plain walking requests
use the default forward speed Soridormi declares in its `walk_velocity` schema. An explicit speed or other numeric value
the person states is sent unchanged; Soridormi may reject a value outside its limits,
which Chromie reports as a limitation, or run the nearest supported value and report it in
`value_adjustments`, but neither side silently runs a different value.
Requests to joke or otherwise talk while walking use a `speech` Goal
coordinated with the walking step; `chromie.speak` is a Host speech transport
and is never a planner step. Requests to recite, sing, hum, or speak in a
requested style use the `recitation`, `singing`, `humming`, or `styled_speech`
output modes. They still belong to the Vocal lane, but they may be claimed only
when a registered vocal-performance capability can provide that evidence. The planner
must otherwise report the limitation or propose an explicit alternative rather
than substituting a body action or ordinary TTS. The same motion limits still
apply to the walking step. When
native speech metadata includes `wait_for_playback_start=true`, the host speech
provider completes that speech request only after playback has started or the
configured wait times out; this lets the following sequential body skill begin
with audible speech instead of merely queued TTS.

### Exact vocal-performance provider contract

`chromie.vocal.perform` is the single public Capability identity for qualified
provider-backed vocal performance. Backend identity is trusted runtime
metadata; it is not copied into semantic Goals and does not replace the public
Capability ID during proposal, validation, authorization, execution,
cancellation, or evidence collection.

The request schema requires authored `text` and one exact `mode` from
`speech`, `styled_speech`, `recitation`, `singing`, `humming`, or
`nonverbal_vocalization`. A qualified provider declaration names its supported
modes, text/audio streaming support, request-cancellation support, timing-mark
types, sample formats and rates, concurrency limit, immutable software/model
provenance, and retained evidence for every advertised mode. The default Agent
catalog retains this contract as unavailable and advertises no supported modes;
only a declaration with mode-specific evidence makes it planner-visible.

The Trusted Capability Runtime rejects an unsupported requested mode with the
correlated `vocal_mode_unavailable` outcome before invoking the backend. A
completed result requires the delivered mode to equal the requested mode,
completed playback evidence, a declared sample format and rate, and no
undeclared timing marks. A mode mismatch or malformed delivery evidence fails
as `invalid_vocal_delivery_evidence`; it is never repaired into ordinary TTS or
another vocal mode. Cancellation retains the original request identity. These
results prove only the evidence level and artifacts recorded by the provider
declaration. Source-test evidence from a fake provider is not singing, speaker,
or physical-audio target evidence.

### Exact peer-media provider contract

Existing music, recordings, streams, and sound effects use seven stable public
Activity capabilities: `chromie.media.play`, `chromie.media.pause`,
`chromie.media.resume`, `chromie.media.seek`, `chromie.media.stop`,
`chromie.media.volume`, and `chromie.media.status`. Backend identity remains
trusted runtime metadata and never replaces these IDs in a Goal, Plan, request,
result, or retained trace. The default catalog keeps every operation visible but
unavailable until a qualified peer provider declares exact supported operations,
media kinds, persistent-state and progress support, request cancellation,
concurrency, mixer parameters, immutable provenance, and retained evidence for
every advertised operation.

`play` accepts only a provider-declared media kind plus a provider-neutral media
reference and optional start position or volume. Lifecycle controls require the
persistent `playback_id`; `seek` and `volume` add their exact value. Completed
results preserve the requested operation and public capability ID, playback
identity and state, bounded position/duration/volume, delivery evidence ID,
evidence level, and declared mixer policy. A different operation, incompatible
state, undeclared media kind, or malformed progress fails as
`invalid_media_lifecycle_evidence`; an unsupported input kind is rejected before
backend invocation.

Speech may overlap media only through an explicit `LaneCoordinationGroup`. The
Host then materializes the provider declaration's
`duck_media_during_vocal` gain, attack, and release values onto both the
Vocal item and media request without changing either Goal. Deterministic
`output_only`, `media_output`, and `current_interaction` scopes respectively
mean stop talking, stop media across retained interactions, and stop all work in
the foreground interaction. Their cancellation receipts retain exact selected
request identities and provider/dispatch failures; a receipt is not audible
silence or provider-safe-state proof.

### WorkDAG validation and DAGEngine execution

WorkDAG is Planner-authored planned-Work topology. DAGEngine validates and advances
that topology mechanically; it does not create replacement Work or user-facing meaning.

| Method | Path | Gate or authorization | Purpose |
|---|---|---|---|
| `POST` | `/work-dags/execute-planning` | `AGENT_ENABLE_PLANNING_DAG_EXECUTION=1` | Execute safe reads and `planning_only` provider operations in an already-authored WorkDAG. |
| `POST` | `/work-dags/{dag_id}/cancel` | DAGEngine execution bearer token | Cancel an active DAG or reserve a bounded cancel-before-start tombstone. |
| `GET` | `/work-dags/engine/status` | Diagnostics bearer token | Return DAGEngine mode, active/waiting counters, and active DAG IDs. |

Bearer format:

```text
Authorization: Bearer <AGENT_DAG_ENGINE_EXECUTION_TOKEN>
```

Engine-status requests use `AGENT_DAG_ENGINE_DIAGNOSTICS_TOKEN`.
When that variable is blank, Agent falls back to `AGENT_DAG_ENGINE_EXECUTION_TOKEN`;
when both are blank, diagnostic endpoints return 503. Invalid or missing credentials
return 401.

`dag_id` is the cancellation/replay identity. It contains 1–128 URL-path-safe letters,
digits, periods, underscores, colons, or hyphens. A cancel-before-start tombstone is
capacity- and TTL-bounded. Retained execution replay for the same revision requires the same `dag_id`, `revision`,
exact DAG fingerprint, and compatible execution lane. A semantic change keeps the same
`dag_id` only when Planner authors the exact next `revision` with
`parent_revision=previous_revision`. DAGEngine rejects skipped revisions and protects each
already-successful/skipped node from removal or semantic rewriting; such nodes are inherited
into the next trace with `inherited_from_revision` and are not dispatched again. Guarded
replay still requires a fresh valid grant for newly executable effectful nodes.

`ExecutionTrace.summary` is the bounded Planner-authored DAG summary. DAGEngine does
not generate an `outcome_summary`. Trace/node records include `dag_revision` plus execution facts such as
node status, Capability id, attempts, errors, blockers, and diagnostic events. The
Planner-visible Capability result also preserves the DAG `goal_ids` and each node's
Planner-authored `source_goal_ids`, so execution facts remain traceable to their DAG and
canonical Goal ownership without DAGEngine inventing semantics. Provider
fields such as `reason_code`, `blocked_subsystems`, or provider next-action suggestions
remain provider-reported facts; they do not become DAGEngine recovery decisions.

The Planner-facing `chromie.work_dag.execute` Capability accepts a fully authored `dag`
argument. Host routes it to DAGEngine execution; the Agent-side execution flag still
controls whether it runs. A disabled execution lane fails closed. Failed, aborted, or
cancelled traces return non-completed Capability results and re-enter the ordinary
Evidence/Planner path. DAGEngine never emits `residual_replan` or replacement Work.

WorkDAG `$ref` arguments may read `<node>.output[.<field>]`, `<node>.error`, or
`<node>.status`. Pre-authored fallback/retry policy remains part of committed WorkDAG
topology; semantic replanning after changed reality belongs to Planner and normally
produces a revised/new WorkDAG. Goal Association never edits the DAG directly; a Goal change is input to Planner. Retaining the current WorkDAG is a valid NO_CHANGE decision.

## ASR WebSocket protocol — port 9001

The ASR service accepts WebSocket connections and two message forms:

- JSON text `{"type":"health"}` or `{"type":"ping"}` ->
  `{"type":"pong","service":"asr",...}` with backend, mode, model revision,
  and bounded-concurrency metadata.
- Binary PCM16 mono audio at `ASR_SAMPLE_RATE` -> one JSON final result:
  `{"type":"final","sequence":<n>,"text":"...","duration":<seconds>}`.

Failures return `{"type":"error","sequence":<n>,"message":"..."}`. `sequence`
numbers the utterances sent on one connection from 1; clients reject a reply
whose sequence is not the utterance they are waiting for and reconnect. The host Orchestrator
performs VAD and sends complete utterance audio; this service does not stream
partial transcripts. Blocking final-backend inference runs in a bounded
executor, so health/ping handling remains responsive while a transcription is
active. The current supported backend and mode are `sherpa_onnx` and `final`. The pong reports `backend`, `mode`, `model`, `model_revision`, and
`max_concurrent_transcriptions`.

## TTS WebSocket protocol — default port 5000

The maintained endpoint on port `5000` is Fun-CosyVoice3 0.5B. Explicit
alternatives use port `5001` for OuteTTS and port `5002` for Qwen3-TTS. All
three expose the same provider contract for health and synthesis.

Supported default-provider JSON messages:

| Request type | Result |
|---|---|
| `health` or `ping` | `pong` with provider contract/declaration, immutable model identity, sample rate, worker readiness, cancellation counters, and `speakers` (`default` plus every catalog profile, currently `["default", "chromie_en", "chromie_mixed", "chromie_zh"]`). |
| `synthesize_stream` | `start`, binary PCM16 chunks, then `end`; or `error`. |

A synthesis request includes `text`, optional `speaker_id`, optional
`language_hint`, and optional `request_id`. The `start` message declares
`sample_rate`, `format=pcm_s16le`, `channels=1`, and a versioned `provider`
object. The terminal `end` repeats the provider declaration and includes audio
duration, comparable timing, and provider metadata.

The provider object includes contract version, provider ID, implementation,
software/model provenance and declared licenses, languages, rates, maximum
concurrency, native streaming, cancellation, speaker-profile, and voice-cloning
capabilities. These are capability declarations, not quality or legal approval.

The default CosyVoice provider reads the source-controlled voice catalog from
`TTS_VOICE_ROOT`; Docker Compose mounts `${TTS_VOICE_ROOT:-./assets/tts/voices}`
at `/voices`. `TTS_DEFAULT_SPEAKER` may select another catalog profile as the
default. See [tts/README.md](../tts/README.md) for the catalog format. A private
reference installed with `scripts/tts_reference.py` is not read by the
maintained runtime.

It does not expose network `create_speaker`. The optional Oute fallback retains
that legacy operation on port `5001` for Oute v3 profiles; its success response
includes transcript-alignment and DAC acoustic-coverage diagnostics.

CosyVoice emits native streamed audio but currently accepts one complete text
request rather than incremental model tokens. Cancellation first attempts a
bounded drain while holding the singleton worker lock; if synchronous inference
does not finish, Chromie restarts the worker before accepting another request.
Health reports drain/restart evidence.

The host Orchestrator may split one logical speech response into multiple
ordered requests, resample provider output, serialize playback, and invalidate
late chunks after interruption. Startup-cached acknowledgements are bound to
provider/model/reference identity and pass duration plus ASR content gates
before playback.

## Soridormi contract snapshot

`capabilities/soridormi.json` contains 28 tools grouped under seven external
agents:

- robot status, scene observation (`soridormi.robot.observe_scene`), mode, and
  battery reads;
- motion plan creation, execution, stop, and cancellation;
- named-skill catalog, plan creation, and execution;
- resource-aware body-activity capability discovery, compilation, execution,
  compatibility aliases, status, and cancellation;
- read-only Soridormi task capability readiness;
- no-motion embodied task preview with non-persistent `preview_id`;
- no-motion embodied task submit, status, events, cancellation, lifecycle phase
  reporting, skill-dry-run metadata, `skill_sequence` dry-run step metadata,
  embodied `plan_steps`/`blocked_subsystems`, and
  `recommended_next_actions`;
- motion monitoring and emergency stop;
- simulator fault injection for tests (`soridormi.testing.configure_fault` and
  `clear_faults`).

The live endpoint URL is supplied by `${SORIDORMI_MCP_URL}`. Probe the endpoint
against the manifest before enabling execution; the checked-in JSON is not proof
that the currently running server has the same schema.
