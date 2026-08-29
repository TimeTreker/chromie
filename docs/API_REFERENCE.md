# API and Protocol Reference

This document describes interfaces implemented in this repository. Soridormi
is a separate deployment; only its checked-in capability contract is summarized
here. Current revision and verification status are maintained in
[STATUS.md](STATUS.md).

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

`POST /cognitive-gateway/attention-review` accepts only normalized turn identity,
text, language, and bounded host engagement evidence. Suppression is limited to
high-confidence inactive ambient speech. An internally contradictory
`addressed=false` result with a directed or unclear speech act receives one
schema-constrained model repair; direct, unresolved unclear, malformed,
unavailable, or failed review admits the turn.

`POST /cognitive-core/interpret` accepts only a schema-valid admitted
`CoreTurnRequest`. Bare text, a suppressed envelope, mismatched context identity,
or a context digest mismatch is rejected before Goal Interpretation. The result
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
| `GET` | `/semantic-authority` | Return the machine-readable maintained single-authority matrix for Goal-driven `apply` and `report_only`. |
| `POST` | `/cognitive-gateway/attention-review` | Focused pre-Core admission review; returns addressedness evidence only and fails open. |
| `POST` | `/cognitive-core/interpret` | Envelope-first ordinary semantic Goal Interpretation inside the Core. |
| `GET` | `/agent-skills` | Return bounded owner-approved Agent Skill metadata summaries and configured package provenance only; no Skill body or projection text. |
| `POST` | `/agent-skills/select` | Let the declared responsible Agent role make a typed model-authored no/one/multi-Skill decision from bounded approved summaries; this endpoint does not load projections, mutate Plans, or execute Capabilities. |
| `POST` | `/agent-skills/disclose` | Load only exact projections from a validated selection under digest and prompt-budget checks; it does not mutate Plans or execute Capabilities. |
| `GET` | `/capabilities` | Return the active merged static capability registry and manifest sources. |
| `GET` | `/capabilities/catalog` | Return the shared catalog, including last-known live named capabilities and refresh status. |
| `POST` | `/capabilities/search` | Return a bounded model-neutral catalog view for inspection; it never scores language, suggests an ordinary route, or selects agents. |
| `GET` | `/capabilities/llm-context?language=en&text=...` | Return concise full-catalog LLM context; `text` is accepted at the interface but does not filter capabilities. |
| `POST` | `/goal-association` | Resolve continuity-before-creation and independent Goal segmentation for the unified runtime; the endpoint itself does not mutate host state. |
| `POST` | `/fast-plan` | Produce a complete common-catalog `CanonicalPlan` or terminal Deep Planner escalation. |
| `POST` | `/deep-plan` | Produce a terminal full-catalog `CanonicalPlan`; only one mechanical DTO regeneration is permitted. |
| `POST` | `/reflection` | Run selective slow-cognition Reflection for one trusted evidence-bound `CognitiveOpportunity`; it may propose future replan, clarification, correction, or bounded task/session Memory for still-open Responsibility but cannot reopen completed outcomes, execution authority, or history. |
| `POST` | `/tools/execute` | Execute one exact planner-selected, explicitly interaction-executable safe read-only local capability and return structured evidence only. |

`GET /agent-skills` reports the passive read-only cognitive-content registry.
The maintained repository root is mounted read-only and contains the approved
`chromie.grounded-external-information` and `chromie.weather-information`
packages. Startup validates safe YAML, explicit
`authority=agent_method_only`, explicit `execution_authority=none`, owner
approval, semantic version, deterministic package digest, projection paths,
duplicate IDs, parent references, inheritance cycles, and normalized
package applicability metadata. The endpoint exposes only immutable bounded summaries. The
two packages expose projections for all three maintained Agent roles; the
weather package declares the grounded method as its parent and remains passive
despite referencing required/optional Capabilities.

`POST /agent-skills/select` accepts the responsible Agent projection name, the
current user text, bounded Goal context, optional bounded context summaries, and
an optional explicit candidate-ID set. The Host performs only structural
discovery: it filters by declared projection, validates explicit IDs, sorts and
caps the candidate summaries, then lets the configured model author an explicit
`no_skill` or ordered one/multi-Skill decision. The closed output is validated
against the exact disclosed IDs, versions, projection, Goal IDs, confidence,
and registry digest. One invalid result may receive one same-boundary repair;
model or contract failure returns an optional no-Skill resolution rather than
fabricating method provenance. No `SKILL.md` or projection text is loaded, no
Canonical Plan is changed, and no Capability is registered, authorized, or
executed. Candidate discovery is bounded by the declared Agent role and package metadata;
semantic selection remains model-authored from the current Goal and Responsibility
context rather than a retired GI route/intent classification. `/health` reports
whether this independent selection boundary is enabled plus its model and candidate limits.

Catalog entries include `prompt_tier=common|rare`, plus
`prompt_tier_locked`, `prompt_tier_source`, and `prompt_tier_reason`. The
Fast Planner uses unlocked `common` entries for its bounded low-latency catalog;
Deep Planner may use the full qualified catalog. Goal Interpretation remains WHAT-only
and does not gain Capability-selection authority from catalog projection. Safety-locked
entries remain visible in the full catalog but are excluded from the fast
common prompt even when an experience overlay requests `common`. The initial
preset is data in `capabilities/prompt_tiers.json`, not a Python skill list.
`chromie.speak` remains a trusted Vocal transport capability, but the Goal-driven
Fast and Deep Planner schemas exclude it as a task-plan response-transport leaf. A mixed
conversational/body turn may use a goal-scoped `respond` outcome plus executable
body steps, and executable planner outcomes may carry prospective
`response_text` for a new conversational delta. The Planner's Communicative
Activity coordinates final delivery against Interaction Context; none of that speech authorizes or
proves the body effect. Search scores are relevance signals for catalog
inspection endpoints, not Goal Interpretation execution authorization.

`POST /agent-skills/disclose` accepts a previously validated selection and loads
only its exact matching role projections. The Loader rechecks package content,
applies per-projection/aggregate/count budgets, omits rather than truncates
oversized content, and returns typed failures plus a disclosure digest. The three
maintained semantic model endpoints perform this selection/disclosure automatically;
caller-supplied disclosure context is removed before trusted injection.

### Cognitive planning and interaction support

The retired Agent `/run`, `/interaction`, and `/agents` endpoints are not part of
the maintained service. User-turn orchestration is Host-owned; the Agent service
exposes bounded cognitive module endpoints plus trusted tool/WorkDAG support.
Important interaction-related endpoints are:

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/fast-advance` | Stream one Fast Planner semantic result as typed NDJSON: an early presentation commit, then a terminal result or typed failure. |
| `POST` | `/goal-association` | Commit no Host state; return the model-authored canonical Goal association/segmentation proposal for Host application. |
| `POST` | `/agent-skills/select` | Return a typed optional method selection authored for the declared Agent role from bounded approved summaries. |
| `POST` | `/agent-skills/disclose` | Return exact bounded role projections from one validated selection without Plan mutation or execution. |
| `POST` | `/tools/execute` | Trusted execution boundary for exact local safe-read capability requests already selected by the Goal-driven planner. |

The maintained Goal-driven planning endpoints (`/fast-advance`, `/goal-association`,
`/fast-plan`, `/deep-plan`, and `/reflection`) accept a typed
`CognitiveWorkRequest`: `sid`, original `text`, optional `language`, first-class
`responsibilities`, interpretation confidence/unresolved meaning, bounded `context`, and
`history`. Re-entry requests additionally carry an immutable `planner_reentry_scope`;
ordinary initial requests omit it. They do not accept a Goal-Interpreter `route_decision`.

The maintained Cognitive Core interpretation result contains first-class
`responsibilities` as provider-neutral Goal-Interpretation evidence: a local reference,
human outcome, material semantic bindings, Goal relationship, exact output mode, and
the primary-result source evidence required for mechanical coverage validation.
Effectful or multi-Responsibility results do not cross a second LLM coverage reviewer.
Responsibility evidence is the authoritative WHAT handoff
for downstream cognition; it is not a Goal, Plan, or Goal-Association-only DTO.
Capability IDs, executable args/actions, provider identity, execution methods,
Activities, response wording, `route`, and `intent` are forbidden.

Planning `InformationGap` creation/resolution, execution-input completeness, blocking
status, source/default selection, and clarification selection belong to Fast Planner.
GI carries only Responsibility meaning, Goal relation, and bounded unresolved meaning;
its maintained schema contains no planning-gap or resolution-policy fields.

`POST /fast-advance` consumes the authoritative user turn plus contextual Responsibility
evidence and makes exactly one streaming model invocation. The response media type is
`application/x-ndjson`. Its ordered typed frames are:

1. exactly one `PresentationCommit` (`frame_type=presentation_commit`) after the complete
   internal `<presentation_commit>...</presentation_commit>` payload has parsed and
   validated; it contains intentional silence or one
   exact immediately truthful `progress`/`complete_response` Communicative Activity and
   optional auxiliary Activities anchored to that exact Activity;
2. exactly one `FastPlannerStreamTerminal` (`frame_type=terminal`) whose
   `presentation_commit_id` and `advance.metadata.presentation_commit_id` reference the
   same immutable commit and whose `FastPlannerAdvance` contains the complete remaining
   HOW decision; or
3. one `FastPlannerStreamFailure` (`frame_type=failure`) identifying failure before or
   after commit. A pre-commit failure is silent. A post-commit failure preserves only the
   already-launched truthful presentation and authorizes no Goal Work.

The internal model stream is exactly two tagged frames, with the presentation payload
first and the terminal Plan payload second; it is not one top-level JSON document. Raw
provider tokens, unclosed tags, partial payloads, and partial DTOs never reach TTS or a Capability. The
terminal result cannot repeat, reword, translate, contradict, or omit the accepted
communication or decoration. No retry/reviewer call repairs this streamed semantic result.
A clarification Communicative Act owns one
or more typed Planner `InformationGap` records and no `response_text`. A semantic gap
must cite one exact GI `unresolved` string; an execution-input gap must cite one exact
available Capability ID and its genuinely absent, required, non-defaulted schema input.
The gap records which authorized context, observation/query, preference, schema, or
safe-default sources were considered. Goal Association starts concurrently from the same
GI result and remains the sole canonical
Goal commit owner; it does not author clarification wording. After deterministic
Responsibility-to-Goal binding, the Host atomically attaches Planner gaps to the exact
canonical Goal before clarification wording may be delivered. No Capability Activity,
including a safe read, starts from the presentation commit or before the complete terminal
result, canonical Goal binding, and full trusted Plan validation. GA emits no
replan or compatibility flag. `/fast-plan` receives the Canonical Goal plus a bounded
`existing_work_activities` projection of relevant retained Runtime
Work and active task bindings without cancelling
first. The Planner explicitly sets `CanonicalPlanStep.reuse_activity_id` to an existing
stable Activity identity when it wants reuse and authors the complete desired Plan;
omission means no reuse selection. Runtime reuses the task only after Host
validation proves exact request/version/state, Capability IDs, arguments, Goal ownership,
and multi-Activity timing; otherwise it cancels pending/cancellable retained Work
after the Planner decision and executes the corrected Plan.

Fast Planner Communicative Activities carry exact text, truth stage, Goal or
Responsibility provenance, and Evidence references in the Planner result. The
Host mechanically validates those fields and sends accepted text to ordered TTS;
it does not call a second wording model or rewrite the act. A pre-evidence act
cannot cite Evidence or claim a result, while a post-evidence act must cite exact
Host-admitted Evidence.

On terminal Evidence re-entry, `/fast-plan` receives the bounded current Responsibility/Goal/Situation/Work/Evidence state and an immutable `PlannerReentryScope`. The scope binds the exact trigger, affected Goal IDs, Evidence refs or opportunity identity, and originating Plan identity/fingerprint when available. Prompt projection, response schema, and final validation use only that Goal set; scope disagreement fails closed. The Planner may answer or author genuinely new follow-up Work for those Goals. Any post-Evidence wording must establish its exact Goal/Evidence scope, execution status, perspective, and epistemic strength in that same primary Planner result. Trusted validation checks only closed schema and provenance mechanics; it cannot call a second model to qualify, review, or repair the response. Failure at this boundary escalates to the distinct Deep Planner pass when permitted or fails closed; the Host never rewrites the sentence.

`POST /fast-plan` is the bounded re-entrant canonical Fast Planner endpoint, available only when `AGENT_FAST_PLANNER_ENABLED=1` and Agent LLM use is enabled. A valid `/fast-advance` may still finish a provider-free easy turn directly. Canonical Goal commit with provisional Work, association to retained Goal state, trusted Evidence/result re-entry, or another relevant open-Responsibility event calls `/fast-plan` with a bounded current Work snapshot. It decides whether existing Work remains in the complete desired Plan; GA and Orchestrator do not make that semantic choice. The endpoint never executes by itself, and trusted Runtime revalidates exact identity, version, authorization, resources, and safety before applying the Plan.

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
digests, explicit relevant Goal IDs, rationale, and confidence. Fast Plans may
contain only Fast Planner provenance. Deep Plans preserve ordered Fast Planner
provenance from the advisory Plan and append Deep Planner provenance. This field
is included in Plan fingerprints and replay serialization but is ignored by
Capability authorization and execution.

`POST /deep-plan` is available when `AGENT_DEEP_PLANNER_ENABLED=1`. It receives the original turn, active-goal context, Goal Association result, applicable Fast Planner continuation/escalation context, and the full capability catalog. It returns the same `CanonicalPlan` contract with `planner_tier=deep`. Deep planning is terminal: it may execute, respond, clarify, report unavailable, or refuse, but cannot return to Fast Planner. Complete multi-goal model output uses `goal_outcomes` as an exact object keyed once by every authoritative Goal ID; the host materializes the canonical outcome list in authoritative order. Per-goal and aggregate satisfaction are prospective plan-adequacy assessments, not execution evidence. A supplied low per-goal score remains authoritative; runtime validation does not invent a missing duplicate per-goal score when the exact keyed outcomes and aggregate judgment already establish coverage. `vocal_output` Goals must use a response outcome containing the requested authored content and cannot own executable transport steps. Parallel timing is accepted only from provider catalog entries that explicitly declare compatible parallel safety and resources. Otherwise the planner must fail closed or author a typed `safe_adjustment`/`alternative`; `plan_relation` and `user_confirmation_required` enforce user confirmation before the host transfers that judgment to canonical metadata. A mechanically malformed planner DTO may be regenerated once in the same tier. Semantic grounding, responsibility coverage, capability applicability, confidence/satisfaction, and safety rejection are terminal in Deep and are not rewritten by another Deep model pass.

`POST /reflection` reuses the configured Deep Planner model only for a trusted `CognitiveOpportunity` whose `recommended_cognition` is `slow`. The Host supplies the exact affected Goal IDs and evidence references and binds those identities into the returned `ReflectionResolution`; the model cannot widen them. Reflection is optional post-outcome cognition. **Current endpoint semantics remain open-Responsibility-only:** applied actions require runtime-bound trusted evidence and a completed outcome is terminal to this API path. Reflection may propose future replan, clarification, a future user correction candidate, or bounded `task`/`session` Memory candidates. It cannot authorize effects, reopen the current turn, rewrite `ExecutionOutcome`/Evidence/history, change Stable Mind, or create provider capabilities. A Memory proposal is not durable by itself: the Host promotes only matching repeated-evidence candidates to ephemeral task/session Memory, while durable profile Memory retains the existing explicit-current-turn-consent boundary. The accepted architecture now specifies a later contract split in which terminal evidence may support bounded `experience`/`calibration` without reopening Responsibility; that design is not implemented by this endpoint yet.

`PresentationCommit`, terminal Fast Advance, `/fast-plan`, and `/deep-plan` expose
bounded `auxiliary_activities[]` inside their primary Planner output. Each item is anchored
to a Planner-authored Main Activity and decoder-constrained to exact eligible live
catalog candidates. Runtime
validates or suppresses the exact proposal; it cannot reselect. Auxiliary-only
events do not create Goal-scoped cognitive re-entry.

`POST /tools/execute` is a trusted provider boundary, not a semantic router. It accepts an exact `capability_id` and schema-valid arguments already produced by the Goal-driven planner. The Agent rejects unknown, unavailable, non-local, side-effecting, confirmation-gated, or non-`safe_read` capabilities and returns structured output without composing user speech. The Trusted Capability Runtime (`CapabilityRuntime`) remains responsible for provider registration, input validation, timing, cancellation, and correlated execution evidence. The first maintained binding is `chromie.weather.lookup`; additional local tools require an explicit manifest declaration and trusted provider binding rather than phrase rules.

`chromie.weather.lookup` accepts the canonical place plus Capability-local
`date=today|tomorrow` and `period=day|morning|afternoon|evening|night`. GI and GA
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

Terminal Capability results do not enter a separate interpretation endpoint. The
Host validates and correlates the result, binds a `ToolResultEvidence` object to
the exact immutable request Goal IDs, updates Goal/task state, and reactivates
`POST /fast-plan` with a bounded Goal/Evidence snapshot. The re-entry Plan cannot
widen the Goal set or schedule duplicate execution. Any spoken answer is a
Planner-owned post-evidence Communicative Activity with exact Evidence
references; missing provenance fails closed rather than inferring a Goal from
provider data.

`POST /goal-association` is available only when
`AGENT_GOAL_ASSOCIATION_ENABLED=1` and Agent LLM use is enabled. It applies
continuity before creation: each semantic responsibility may associate with
existing active goals, become an independent new goal, or produce one natural
clarification when the reference is ambiguous. Existing goal IDs must be copied
from the supplied active-goal snapshots; unknown or below-threshold associations
are rejected. Every validated new Goal retains provider-neutral WHAT semantics. `output_mode`
distinguishes ordinary speech, expressive speech, recitation, singing, humming,
nonverbal vocalization, body action, media playback, information, stateful effect,
or other; `media_operation` is one exact persistent playback operation only for
`media_playback`. The live model-facing and canonical Goal contracts do not contain
`responsibility_kind`, `execution_lane`, `provider_required`, or `capability_work`.
Those concepts are not reconstructed by the Host. Planner decides HOW from the
canonical Goal, current trusted state/Evidence, and the available Capability catalog;
selected Capability/Activity records carry Runtime execution facts separately. This
keeps Goal identity stable across provider changes and prevents Goal Association from
quietly taking back planning authority.
For a resource responsibility, the live schema likewise has one writable nested
authority: `resource_responsibility.resource`, `.source`, `.recipient`, and
`.delivery_mode`. Resource identity, normalized numeric quantity, query-scope
attributes, source bindings, recipient, and delivery are authored there exactly
once. A resource Goal's generic `bindings` must be empty. The Host creates an
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
mechanically conserves the authoritative GI Responsibilities and their integrated
source/coverage evidence; it does not invoke a coverage reviewer, critic, fresh
interpretation, or final semantic recheck. A semantic, grounding, or conservation
rejection fails closed and cannot be repaired at the same authority. The current
development implementation follows this primary-result contract; repository policy
rejects restoration of the older certificate/reconsideration path. Live model quality
still requires current-revision qualification.

`GoalAssociationResolution.resolution_status` is the terminal contract:
`resolved` or `fail_closed`. `fail_closed` contains no associations, new Goals,
discourse mutations, progress bindings, clarification, or confidence and cannot be
committed or passed to a Planner. When GI retains genuine semantic ambiguity, GA may
commit the narrowest source-grounded provisional Goal without deciding the missing
meaning; Fast Planner alone decides whether to create a question-bearing gap. Model,
schema, audit, and retry failures never masquerade as user-resolvable ambiguity.
Mode-specific vocal output remains Vocal but requires provider evidence; a
generic `respond` outcome or ordinary TTS cannot close it. The eventual spoken
delivery of a capability result remains part of that capability-dependent Goal
rather than becoming a duplicate response Goal. The endpoint itself does not mutate task state,
authorize side effects, alter Cognitive Core interpretation output, or execute plans. The unified host uses its result
in `report_only` observation or authoritative `apply`, and only the host may
atomically commit the validated association.

Goal Interpretation decision as advisory context, replaces model-provided operation IDs with
stable request-bound IDs, rejects below-threshold or unknown-task operations,
and may return an immediate `ResponsePlan`. It never applies task changes,
authorizes side effects, or claims execution. The host decides whether to call
it in `off`, `report_only`, or `apply` mode and remains the authority for task
versions, confirmation validity, commitment, scheduling, and evidence.

The host context now includes compact prompt-memory fields:
`session_memory.memory_summary`, `session_memory.extracted_memory`, and
top-level `extracted_memory`. These are process-local session/task memory
summaries, not durable user-profile memory and not authorization for side
effects. Fast Goal Interpretation prompts sanitize raw `history` and `conversation` fields
from their bounded context payload and rely on these compact memory fields
instead.
Durable or session memory is not a Goal Interpretation route. Explicit memory
changes flow through typed, consent-bound memory proposals and the existing
Conversation State / memory capability boundary. The Host validates persistence
scope and explicit-current-turn consent mechanically; no separate memory semantic
agent or route label owns memory semantics. Retrieved verified tool results remain typed
Capability/Evidence work and cannot become factual speech without Planner and
Evidence qualification.

`InteractionResponse` can contain speech items and executable Capability requests.
Shared contracts reject unknown fields and recursively reject low-level motor,
joint, torque, and actuator fields. The maintained response is projected from
Planner-owned Communicative and Capability Activities; there is no legacy
response-adapter/fallback mode. The primary Planner may include advisory
`auxiliary_activities[]` selected from the reviewed `social_attention` behavior
domain. They cannot author or adapt response text independently. Applied decoration requests carry
`metadata.source=canonical_plan_auxiliary_activity`,
`metadata.auxiliary_plan_activity=true`,
`metadata.execution_lane=activity`, and
`metadata.execution_role=social_decoration`; they are excluded from user task
proposals and Goal completion. Runtime validation checks exact catalog
membership, schemas, target evidence, resource conflicts, confirmation policy,
and a bounded latency budget. Target evidence is semantic only; installation calibration and body-specific
coordinates are never part of the Chromie planning contract. Concrete user-requested actions remain primary
CanonicalPlan goals and cannot be replaced by auxiliary expression. Body and tool requests flow through model-assisted Goal Interpretation, the live
capability catalog, the single Fast/Deep Planner authority, schemas, and Trusted Capability
Runtime validation rather than hidden phrase parsers or a retired routing layer. Plain walking requests
use a normal safe forward speed of `0.18 m/s`;
requested forward speeds above Soridormi's current runtime limit of `0.20 m/s`
are normalized back to the normal speed and surfaced through `speak_first`.
Requests to joke, recite, or otherwise author speech while walking use a
`vocal_output` Goal coordinated with the walking step; `chromie.speak` is a
Host speech transport and is never a planner step. A request to sing still
belongs to the Vocal lane, but it may be claimed as singing only when a
registered vocal-performance capability can provide that evidence. The planner
must otherwise report the limitation or propose an explicit alternative rather
than substituting a body action or ordinary TTS. The same motion safety
normalization still applies to the walking step. When
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
| `POST` | `/work-dags/validate` | Always available | Validate WorkDAG structure, acyclicity, Capability references, and deterministic execution policy. |
| `POST` | `/work-dags/dry-run` | Diagnostics bearer token | Produce a deterministic trace without remote side effects. |
| `POST` | `/work-dags/execute-read-only` | `AGENT_ENABLE_READ_ONLY_DAG_EXECUTION=1` | Execute preflight-approved side-effect-free nodes. |
| `POST` | `/work-dags/execute-planning` | `AGENT_ENABLE_PLANNING_DAG_EXECUTION=1` | Execute safe reads and `planning_only` provider operations in an already-authored WorkDAG. |
| `POST` | `/work-dags/confirmation-grants` | Guarded execution enabled plus bearer token | Issue a short-lived, single-use grant bound to one WorkDAG and confirmed nodes. |
| `POST` | `/work-dags/execute-guarded` | Guarded execution enabled plus bearer token | Execute authorized side effects; physical motion retains separate confirmation/safety proof requirements. |
| `POST` | `/work-dags/{dag_id}/cancel` | DAGEngine execution bearer token | Cancel an active DAG or reserve a bounded cancel-before-start tombstone. |
| `GET` | `/work-dags/{dag_id}/trace` | Diagnostics bearer token | Return the latest non-expired mechanical execution trace. |
| `GET` | `/work-dags/engine/status` | Diagnostics bearer token | Return DAGEngine mode, active/waiting counters, and active DAG IDs. |

Bearer format:

```text
Authorization: Bearer <AGENT_DAG_ENGINE_EXECUTION_TOKEN>
```

Dry-run, trace, and engine-status requests use `AGENT_DAG_ENGINE_DIAGNOSTICS_TOKEN`.
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

## Hardware compatibility HTTP API — port 8095

This is the legacy mock-action daemon, not the Soridormi robot boundary.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Return mock driver and robot state. |
| `GET` | `/state` | Return current mock robot state. |
| `POST` | `/actions` | Execute a namespaced compatibility action. |
| `GET` | `/actions/{action_id}` | Return an in-memory action result. |
| `POST` | `/emergency_stop` | Set mock emergency-stop state. |
| `POST` | `/reset_emergency_stop` | Clear mock emergency-stop state. |

The daemon rejects `unsafe.*` actions and actions that still require
confirmation. In this revision it always constructs `MockRobotDriver`; serial
configuration variables do not select a production backend.

## ASR WebSocket protocol — port 9001

The ASR service accepts WebSocket connections and two message forms:

- JSON text `{"type":"health"}` or `{"type":"ping"}` ->
  `{"type":"pong","service":"asr",...}` with backend, mode, model revision,
  and bounded-concurrency metadata.
- Binary PCM16 mono audio at `ASR_SAMPLE_RATE` -> one JSON final result:
  `{"type":"final","text":"...","duration":<seconds>}`.

Failures return `{"type":"error","message":"..."}`. The host Orchestrator
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
| `health` or `ping` | `pong` with provider contract/declaration, immutable model identity, sample rate, worker readiness, cancellation counters, and `speakers=["default"]`. |
| `list_speakers` | `speakers` with the installed cloned-reference identity. |
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

The default CosyVoice provider consumes a host-installed authorized reference:

```bash
python scripts/tts_reference.py install \
  --source-wav /path/to/reference.wav \
  --transcript '录音中的逐字文本' \
  --license-id 'user-owned-recording'
```

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

`capabilities/soridormi.json` contains 27 tools grouped under seven external
agents:

- robot status, mode, and battery reads;
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
- motion monitoring and emergency stop.

The live endpoint URL is supplied by `${SORIDORMI_MCP_URL}`. Probe the endpoint
against the manifest before enabling execution; the checked-in JSON is not proof
that the currently running server has the same schema.
