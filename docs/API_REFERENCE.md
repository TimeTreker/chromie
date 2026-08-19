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
| `GET` | `/health` | Return model/runtime state, loaded capability sources, feature gates, scheduler counters, and the legacy CapabilityAgent emergency gate. |
| `GET` | `/semantic-authority` | Return the machine-readable single-authority route matrix and current Agent emergency-fallback gate. |
| `GET` | `/agents` | List specialized agents and ownership notes. |
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
| `POST` | `/social-attention/plan` | Produce one event-scoped auxiliary `SocialAttentionPlan` from the reviewed live social-capability set; it has no Goal, speech, or execution authority. |
| `POST` | `/tools/execute` | Execute one exact planner-selected, explicitly interaction-executable safe read-only local capability and return structured evidence only. |

`GET /agent-skills` reports the passive read-only cognitive-content registry.
The maintained repository root is mounted read-only and contains the approved
`chromie.grounded-external-information` and `chromie.weather-information`
packages. Startup validates safe YAML, explicit
`authority=agent_method_only`, explicit `execution_authority=none`, owner
approval, semantic version, deterministic package digest, projection paths,
duplicate IDs, parent references, inheritance cycles, and normalized
`applicable_routes`. The endpoint exposes only immutable bounded summaries. The
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
executed. Before disclosure, a non-empty package-owned `applicable_routes`
list removes that package from the candidate set when the current structured
route does not match; an empty list remains unrestricted. This is a structural
applicability boundary, not Host semantic selection. `/health` reports whether
this independent selection boundary is enabled plus its model and candidate
limits.

Catalog entries include `prompt_tier=common|rare`, plus
`prompt_tier_locked`, `prompt_tier_source`, and `prompt_tier_reason`. The
Goal Interpretation uses unlocked `common` entries for the fast compact Qwen prompt as
`common_ability_catalog`; deepthinking may use the full catalog. Safety-locked
entries remain visible in the full catalog but are excluded from the fast
common prompt even when an experience overlay requests `common`. The initial
preset is data in `capabilities/prompt_tiers.json`, not a Python skill list.
`chromie.speak` remains common and interaction-executable for legacy/native
`InteractionResponse` compatibility, but the Goal-driven Fast and Deep Planner
schemas exclude it as a task-plan response-transport leaf. A mixed
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

### Conversation and interaction

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/run` | Established `AgentRequest -> AgentResult` compatibility path. CapabilityAgent semantic planning is emergency-only; deprecated caller-supplied exact `actions[]` are adapter input and are not current Fast Goal Interpretation output. |
| `POST` | `/interaction` | Return a natively accumulated and strictly revalidated shared `InteractionResponse`; deprecated caller-supplied exact `actions[]` are materialized without LLM reinterpretation, and the legacy CapabilityAgent planner requires explicit emergency authority. |
| `POST` | `/agent-skills/select` | Return a typed optional method selection authored for the declared Agent role from bounded approved summaries. |
| `POST` | `/agent-skills/disclose` | Return exact bounded role projections from one validated selection without Plan mutation or execution. |
| `POST` | `/social-attention/plan` | Return an event-scoped auxiliary Social-Attention proposal with behavior IDs decoder-constrained to the reviewed live candidate set. |
| `POST` | `/tools/execute` | Trusted execution boundary for exact local safe-read capability requests already selected by the Goal-driven planner. |

The maintained Goal-driven planning endpoints (`/fast-first-response`, `/fast-advance`, `/goal-association`,
`/fast-plan`, `/deep-plan`, and `/reflection`) accept a typed
`CognitiveWorkRequest`: `sid`, original `text`, optional `language`, first-class
`responsibilities`, interpretation confidence/unresolved meaning, bounded `context`, and
`history`. They do not accept a Goal-Interpreter `route_decision`.

The maintained Cognitive Core interpretation result contains first-class
`responsibilities` as provider-neutral Goal-Interpretation evidence: a local reference,
human outcome, material semantic bindings, whether more work is required, and whether
fresh evidence is required. Responsibility evidence is the authoritative WHAT handoff
for downstream cognition; it is not a Goal, Plan, or Goal-Association-only DTO.
Capability IDs, executable args/actions, provider identity, execution methods,
Activities, response wording, `route`, and `intent` are forbidden.

Planning `InformationGap` creation/resolution, execution-input completeness, blocking
status, source/default selection, and clarification selection belong to Fast Planner.
GI carries only Responsibility meaning, Goal relation, and bounded unresolved meaning;
its maintained schema contains no planning-gap or resolution-policy fields.

`POST /fast-first-response` is Fast Planner's bounded latency phase. It consumes the
authoritative turn, GI Responsibilities, response language, bounded interaction state,
and the small owner-approved speaking-style projection. It returns
`FastPlannerFirstResponse`: zero or one exact `progress` or `complete_response`
Communicative Activity. Before returning a non-null Activity, Fast Planner performs
exactly one bounded same-owner Epistemic Qualification and records its accept-only
or reject-only certificate in metadata. The check cannot rewrite text, retry, select a Capability,
resolve an execution input, create a planning InformationGap, or ask a clarification;
rejection or checker failure returns a null Activity. Runtime may then structurally
validate and start accepted exact wording immediately; optional Social Attention
receives that same Activity as its Main-Activity anchor and cannot delay it. This
endpoint is a phase of Fast Planner, not an independent response-composition authority.

`POST /fast-advance` continues the same Fast Planner Activity decision after any first
response commitment. It consumes the authoritative user turn plus contextual
Responsibility evidence and returns `FastPlannerAdvance`: exact Responsibility refs
covered, the already-committed Communicative Act plus remaining Communicative/Capability
Activities with explicit timing, and an optional `deep_planner` continuation for complex
HOW. It must not re-author committed wording. A clarification Communicative Act owns one
or more typed Planner `InformationGap` records and no `response_text`. A semantic gap
must cite one exact GI `unresolved` string; an execution-input gap must cite one exact
available Capability ID and its genuinely absent, required, non-defaulted schema input.
The gap records which authorized context, observation/query, preference, schema, or
safe-default sources were considered. After the first-response commitment, Goal
Association concurrently consumes the same GI result and remains the sole canonical
Goal commit owner; it does not author clarification wording. After deterministic
Responsibility-to-Goal binding, the Host atomically attaches Planner gaps to the exact
canonical Goal before clarification wording may be delivered. The Host may start only
schema-valid, available, side-effect-free safe reads before GA finishes; effects remain
behind canonical Goal, confirmation, authorization, resource, and provider-safety gates.
Parallel-timed early reads additionally require explicit provider parallel-safety
metadata. The same task identity is then bound into applicable per-Goal Runtime task-list
views only after semantic Work reconciliation when provisional Work exists. GA emits no
replan or compatibility flag. `/fast-plan` receives the Canonical Goal plus a bounded
`work_reconciliation_activities` projection of relevant retained/provisional Runtime
Work and active task bindings without cancelling
first. The Planner explicitly sets `CanonicalPlanStep.reuse_activity_id` to an existing
stable Activity identity when it wants reuse and authors the complete desired Plan;
omission means no reuse selection. Runtime reuses the task only after Host
validation proves exact request/version/state, Capability IDs, arguments, Goal ownership,
and multi-Activity timing; otherwise it cancels pending/cancellable provisional Work
after the Planner decision and executes the corrected Plan.

The single same-stage `/fast-advance` mechanical revision preserves the initial
model-authored disposition. For an initial `execute` decision it constrains the repaired
Activity list to Capability work, requires the selected Capability's exact argument
schema, and explicitly materializes schema defaults. It cannot choose the Capability,
reinterpret the Responsibility, or grow into another revision.

Fast Planner Communicative Activities carry exact text, truth stage, Goal or
Responsibility provenance, and Evidence references in the Planner result. The
Host mechanically validates those fields and sends accepted text to ordered TTS;
it does not call a second wording model or rewrite the act. A pre-evidence act
cannot cite Evidence or claim a result, while a post-evidence act must cite exact
Host-admitted Evidence.

On terminal Evidence re-entry, `/fast-plan` also performs one bounded same-owner
accept/reject Epistemic Qualification over immutable result wording. The certificate
has no wording or planning fields. Rejection or checker unavailability returns a
semantic escalation for the existing Deep Planner (or fails closed); the Host never
rewrites the sentence. This prevents a forecast probability below 100% from being
promoted to certainty without adding a Tool Result Interpreter or Response Composer.

`POST /fast-plan` is the bounded re-entrant canonical Fast Planner endpoint, available only when `AGENT_FAST_PLANNER_ENABLED=1` and Agent LLM use is enabled. A valid `/fast-advance` may still finish a provider-free easy turn directly. Canonical Goal commit with provisional Work, association to retained Goal state, trusted Evidence/result re-entry, or another relevant open-Responsibility event calls `/fast-plan` with a bounded current Work snapshot. It decides whether existing Work remains in the complete desired Plan; GA and Orchestrator do not make that semantic choice. The endpoint never executes by itself, and trusted Runtime revalidates exact identity, version, authorization, resources, and safety before applying the Plan.

For Work Reconciliation, `work_reconciliation_activities` is the single bounded input
projection for same-turn provisional and retained Runtime Work. A Planner step selects
reuse only by setting `reuse_activity_id` to one supplied stable identity while
preserving Capability, arguments, Goal ownership, and timing. Retained-work reuse is
currently atomic and reconciliation-only: it selects the complete retained set with no
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

`POST /social-attention/plan` accepts a `SocialAttentionRequest` describing one concrete **semantic** `primary_activity` event in phase `ready` or `started`: what Chromie is doing, such as greeting somebody, telling a joke, walking, singing, handing something over, or showing/playing something. Responsibility/Goal meaning sits above Activity. Canonical Communicative Acts and Plan-step Work provide concrete Activity identity/granularity; one Goal may own several Activities, while a high-level provider capability may keep one behavior atomic. A Fast-Planner scheduled Communicative Act carries its own semantic identity. `primary_activity.realization` separately records how the Activity is currently realized through the Vocal/Activity execution lanes, Vocal Expression modes, execution-item IDs, and Capability IDs. `speech`, `singing`, `humming`, etc. are modes of one Vocal Expression and are not Primary-Activity kinds. Multiple realization items serving one semantic Activity do not create duplicate decoration opportunities. Internal cognition milestones (`understanding_ready`, Goal Association, planning, waiting, evidence arrival), lane transitions, and provider readiness are not valid anchors. Independent semantic Activities are independently eligible for optional decoration. It returns an auxiliary `SocialAttentionPlan`. `SocialAttentionPlanner` is the single semantic owner of that plan. The decoder constrains every behavior `capability_id` to the reviewed live candidate set and excludes provider-owned backend/calibration fields from the model-facing projection. A valid primary `decision=none` is terminal. A malformed primary DTO fails soft to no decoration; there is no second critic or same-stage semantic/DTO repair call. The endpoint only proposes; the Host independently validates target evidence, schemas, confirmation, resources, provider concurrency, and availability before the Trusted Capability Runtime may execute a behavior. The proposal owns no Goal state, speech meaning, or completion evidence.

`POST /tools/execute` is a trusted provider boundary, not a semantic router. It accepts an exact `capability_id` and schema-valid arguments already produced by the Goal-driven planner. The Agent rejects unknown, unavailable, non-local, side-effecting, confirmation-gated, or non-`safe_read` capabilities and returns structured output without composing user speech. The Trusted Capability Runtime (`CapabilityRuntime`) remains responsible for provider registration, input validation, timing, cancellation, and correlated execution evidence. The first maintained binding is `chromie.weather.lookup`; additional local tools require an explicit manifest declaration and trusted provider binding rather than phrase rules.

`chromie.weather.lookup` accepts the canonical place, `date=today|tomorrow`,
and `period=day|morning|afternoon|evening|night`. Natural “tonight” is represented
without conflating two dimensions: `date=today` plus `period=night`. Its completed output therefore includes a
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
are rejected. Every validated new Goal retains five typed completion facts.
`responsibility_kind` is `executable_action`, `vocal_output`,
`capability_dependent`, or `other`; `execution_lane` is `vocal`, `activity`,
or `none`; `output_mode` distinguishes ordinary speech, expressive speech,
recitation, singing, humming, nonverbal vocalization, body action, media
playback, capability work, or other; `provider_required` says whether an
exact registered Capability Provider beyond ordinary authored speech delivery
must return completion evidence; and `media_operation` is one exact persistent
playback operation for `media_playback` or `none` otherwise. The live model-facing Goal schema has exactly one execution discriminant:
`output_mode`, plus `media_operation` only when media lifecycle semantics require
it. `responsibility_kind`, `execution_lane`, and `provider_required` are not model
input fields. The Host exposes them only as deterministic projections of the
validated mode when it materializes canonical Goal metadata. Missing
`output_mode` and model-authored copies of those Host projections are schema
violations; there is no reverse inference or legacy execution-tuple compatibility
path. This keeps one semantic source of truth at the model boundary and makes
contradictory completion tuples structurally unrepresentable.
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

Every newly proposed Goal set crosses the same bounded transaction: primary
interpretation, at most one DTO repair, one responsibility-coverage certificate,
at most one fresh interpretation after certificate rejection, and one final
certificate. The maximum is five logical semantic invocations. A fresh
interpretation receives no DTO repair, and an invalid certificate receives no
repair. Certificate output contains source-grounded item judgments only; the
Host derives `accept`, `reconsider_once`, or `fail_closed` and may retain the
immutable certificate as trace evidence without giving it Goal lifecycle
authority.

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
For explicit `memory` routes, Goal Interpretation must return a typed
`memory_update` proposal. `memory_agent` validates and applies that exact model
decision, emits an `extracted_memory` entry plus a bounded compatibility
`user_statement` derived from it, and clarifies when the proposal is missing.
It never infers memory semantics from raw text. The Orchestrator consumes only
the refined entry into prompt-facing session memory.

`InteractionResponse` can contain speech items and executable Capability requests; the `skills` container name remains a bounded compatibility surface. Shared
contracts reject unknown fields and recursively reject low-level motor, joint,
torque, and actuator fields. Native mode is the Agent default. The response
metadata includes `interaction_output_mode` (`native`, `legacy-adapter`, or
`legacy-fallback`) for operator diagnostics. When `AGENT_SOCIAL_ATTENTION_MODE` allows it, the independent
`SocialAttentionPlanner` may attach its advisory `social_attention_plan`. The plan identifies the
`social_attention` behavior domain, the `auxiliary_expression` role, a social
purpose, and optional small body behaviors selected from the reviewed catalog.
It cannot author or adapt response text. Applied decoration requests carry
`metadata.source=social_attention_plan`,
`metadata.auxiliary_social_attention=true`,
`metadata.execution_lane=activity`, and
`metadata.execution_role=social_decoration`; they are excluded from user task
proposals and Goal completion. Runtime validation checks exact catalog
membership, schemas, target evidence, resource conflicts, confirmation policy,
and a bounded latency budget. Target evidence is semantic only; installation calibration and body-specific
coordinates are never part of the Chromie planning contract. Concrete user-requested actions remain primary
CanonicalPlan goals and cannot be replaced by auxiliary expression. Body and tool requests are routed through the model-assisted
Goal Interpretation, capability catalog, Agent capability planner, schemas, and Trusted Capability
Runtime validation rather than hidden phrase parsers. Plain walking requests
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

### TaskGraph validation and execution

| Method | Path | Gate or authorization | Purpose |
|---|---|---|---|
| `POST` | `/task-graphs/validate` | Always available | Validate graph structure and active capability policy. |
| `POST` | `/task-graphs/dry-run` | Diagnostics bearer token | Produce a deterministic trace without remote calls. |
| `POST` | `/task-graphs/execute-read-only` | `AGENT_ENABLE_READ_ONLY_TASK_GRAPH_EXECUTION=1` | Execute preflight-approved side-effect-free work. |
| `POST` | `/task-graphs/execute-planning` | `AGENT_ENABLE_PLANNING_TASK_GRAPH_EXECUTION=1` | Execute safe reads and stateful `planning_only` tools. |
| `POST` | `/task-graphs/confirmation-grants` | Guarded execution enabled plus bearer token | Issue a short-lived, single-use grant bound to a graph and confirmation nodes. |
| `POST` | `/task-graphs/execute-guarded` | Guarded execution enabled plus bearer token | Execute authorized side effects; physical motion also requires its separate gate and monitor proofs. |
| `POST` | `/task-graphs/{graph_id}/cancel` | Guarded execution bearer token | Cancel an active graph or reserve a bounded cancel-before-start tombstone for a not-yet-arrived execute request. |
| `GET` | `/task-graphs/{graph_id}/trace` | Diagnostics bearer token | Return the latest non-expired in-memory retained trace. |
| `GET` | `/task-graphs/scheduler/status` | Diagnostics bearer token | Return scheduler mode, active/waiting counters, and active graph IDs. |

Bearer format:

```text
Authorization: Bearer <AGENT_TASK_GRAPH_EXECUTION_TOKEN>
```

Dry-run, trace, and scheduler requests use
`AGENT_TASK_GRAPH_DIAGNOSTICS_TOKEN`. When that variable is blank, the Agent
falls back to `AGENT_TASK_GRAPH_EXECUTION_TOKEN`; when both are blank, the
diagnostic endpoints return 503. Invalid or missing credentials return 401.

`graph_id` is also the cancellation-path identity. It must contain 1–128
URL-path-safe letters, digits, periods, underscores, colons, or hyphens. If a
cancel request wins the transport race against execution registration, the
Agent retains a capacity- and TTL-bounded tombstone and returns a cancelled
trace when that graph arrives, without calling its provider. A graph with an
already-retained terminal trace returns `cancellation_requested=false`.
Read-only or planning execution retries with the same retained `graph_id`,
exact graph fingerprint, and execution lane return the retained trace without
invoking providers. Guarded retries must also present a fresh valid
graph-bound grant. Reusing the ID for different graph content or a different
successful execution lane is rejected until retention expires. Dry-run traces
are diagnostics only: they neither satisfy execution replay nor prevent a
later cancellation tombstone.

TaskGraph execution responses return an `ExecutionTrace`. Its `summary` remains
the planner-provided task summary, while `outcome_summary` is generated
deterministically from node results. Failed Soridormi task nodes preserve
`reason_code`, `blocked_subsystems`, and `recommended_next_actions` in that
summary so user-facing report/speech code does not need to infer the refusal.
Planning execution can run `chromie.report` as a trace-only local report node;
it does not play audio. `chromie.speak` remains rejected from planning
execution and should be emitted through `InteractionResponse`/Trusted Capability Runtime when
audible playback is required.
When native `POST /interaction` emits `chromie.task_graph.execute`, the host
Trusted Capability Runtime can route that request to `POST /task-graphs/execute-planning`.
The Agent-side planning execution flag still controls whether the graph runs;
disabled planning execution returns a safe failure instead of falling back to
raw control or guarded execution. Failed, aborted, or cancelled graph traces are
reported back as non-completed capability results so `after_capabilities` speech is not
played as if the task succeeded.
TaskGraph `$ref` arguments may read `<node>.output[.<field>]`, `<node>.error`,
or `<node>.status`; LLM-planned Soridormi task-submit nodes that omit a failure
fallback are normalized with a trace-only report fallback that reads
`<submit_node>.error`.

Traces and grants are process-memory state; they are not durable across Agent
restarts. Traces use configurable TTL/LRU retention (defaults: 900 seconds and
128 entries). Unconsumed grants are capped at 128 entries by default and expired
entries are purged before issue or consume.

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
