# Scoped Discourse Referents and Verified Tool Memory

## Status

Implemented for bounded conversation state, Goal Association, Planning,
Social Cognition Communicative Activities, and host-runtime
verified-result retrieval.

This design exists to prevent one task's structured evidence from silently
resolving another task's pronouns or parameters. It deliberately does not use a
single global field such as `current_location`.

## Authority model

Chromie's cognitive stages have distinct responsibilities:

1. **Cognitive Gateway** normalizes/admit-suppresses the turn, applies only
   deterministic protective reflexes, and supplies bounded context evidence. It
   does not choose semantic work or decide what `那边`, `那里`, `there`, or another
   reference means.
2. **User Meaning Interpretation (UMI)** resolves what an indirect expression
   means at human level from recent accepted dialogue, salient discourse
   entities, active Goal meaning and Memory, and states the resolved value in the
   Responsibility's complete WHAT outcome (for example a weather question about
   内乡). UMI never authors `bindings`: `CoreInterpretationResult` rejects a
   Responsibility that carries them. It sees no canonical Goal or referent IDs.
3. **Goal Association** links that resolution to canonical identity: for an
   indirect expression it copies the supplied `referent_id` into
   `resolved_references`, whose value must equal that referent's canonical value
   (a mismatch rejects), and it associates the Responsibility with open Goals.
   GA does not author or change the resolved value and authors no Goal bindings;
   trusted code materializes a new Goal's WHAT from the UMI Responsibility.
4. **Host conversation state** validates and stores the LLM-authored typed
   referent/focus mutations, IDs, provenance, and bounded persistence. It does
   not contain phrase rules or choose a semantic referent.
5. **Planner** receives the Goal WHAT and GA's resolved references, extracts the
   Capability parameters (for example `location=内乡`), and decides whether to
   retrieve one exact verified prior result or execute a fresh read.
6. **Social Cognition** authors the exact natural pre-result Communicative
   Activity from the Planner's communication Need. It may say that Chromie is checking a source or retrieving a
   recently checked result, but cannot state the result before trusted Evidence.
7. **Host Evidence binding** joins the exact request/result to its existing
   Goal and reactivates Planner for any further Work and Social Cognition, which
   authors any still-useful grounded answer, without fabricating another user turn.

Tool-result memory is never reference-resolution authority.

An ordinary explicit entity mention is not a resolved reference. For example,
`今天晚上重庆热不热？` keeps `重庆` directly in the Responsibility's WHAT and may introduce
a salient scoped referent for later dialogue. `resolved_references` is reserved for
indirect expressions such as `那边`, pronouns, ellipsis, aliases, corrections, or
task mentions that the LLM links to an already supplied discourse referent or active
Goal meaning. Every such indirect resolution carries the copied referent ID and an
explicit confidence; omitted confidence is a contract error rather than an implicit
low- or high-confidence decision.

Goal references are generic, not location-specific. A phrase such as “the last
task I told you” is associated by the same Goal Association LLM against bounded
open Goals (including restored ones) and dialogue context. The Host
does not contain a phrase map for “last task,” “that one,” “那里,” or any other
normal semantic reference. Recent terminal Goals are history only: they are
never association targets, so a follow-up about one becomes a new Goal that
names it in `related_goal_ids`, and its terminal lifecycle state is unchanged. Operational follow-up phrase settings may preserve context across idle
time, but they never select a Goal.

## Why there is no global `current_location`

One robot can simultaneously hold locations for independent scopes:

- physical robot position or navigation destination;
- a weather Goal about Chongqing;
- a travel discussion about Neixiang;
- another remembered event associated with Beijing.

These values must coexist. A discourse referent therefore carries:

- a stable Host-generated `referent_id` (distinct from the reserved literal
  `"requester"` that a physical body target uses for the current speaker; see
  [body target descriptions](EXECUTION_LANES_AND_COORDINATION.md#body-target-descriptions));
- `entity_type` and canonical value;
- `conversation`, `task`, or `goal` scope;
- scoped IDs and source Goal IDs;
- foreground/background/retired status;
- confidence and source turn provenance;
- explicit supersession provenance for corrections.

A bounded focus stack orders currently salient referents without deleting
background task-scoped referents.

## Neixiang and Chongqing example

### Existing Chongqing task

A completed weather Goal may retain both:

```json
{
  "referent_id": "ref_chongqing",
  "entity_type": "location",
  "canonical_value": "重庆",
  "scope_kind": "goal",
  "scope_ids": ["goal_chongqing_weather"],
  "status": "foreground"
}
```

and verified tool evidence whose exact request arguments include
`location=重庆`.

### Explicit correction

For:

> 不是重庆，是一个地名叫内乡。

UMI carries the corrected meaning in its Responsibility `r1` (a WHAT outcome about
内乡, with no bindings). Because the Chongqing Goal is terminal, Goal Association reports
`r1` as a new Goal related to it and emits a model-authored referent correction:

```json
{
  "associations": [],
  "referent_updates": [
    {
      "operation": "correct",
      "entity_type": "location",
      "canonical_value": "内乡",
      "target_referent_ids": ["ref_chongqing"],
      "confidence": 1.0
    }
  ],
  "new_goals": [
    {
      "source_responsibility_refs": ["r1"],
      "related_goal_ids": ["goal_chongqing_weather"],
      "supersedes_goal_ids": []
    }
  ]
}
```

New Goal rows carry only source refs and Goal relationships; trusted code copies
the Goal's description from the UMI Responsibility. Live UMI authors no bindings,
so the new Goal inherits none.

The Host generates the new referent ID, stores Neixiang as foreground, and
moves only the explicitly superseded Chongqing discourse referent to
background. The old Chongqing task and evidence remain available in their own
scope.

### Dependent question

For:

> 今天那边下雨了没有？

UMI resolves `那边` from the foreground Neixiang context and emits Responsibility
`r1` whose WHAT outcome asks whether it rained in 内乡 today (no bindings). Goal Association receives
the foreground Neixiang referent and links the indirect expression to it:

```json
{
  "associations": [],
  "referent_updates": [],
  "resolved_references": [
    {
      "surface_form": "那边",
      "entity_type": "location",
      "resolved_value": "内乡",
      "source": "discourse_referent",
      "referent_id": "ref_neixiang",
      "confidence": 1.0
    }
  ],
  "new_goals": [
    {
      "source_responsibility_refs": ["r1"],
      "related_goal_ids": [],
      "supersedes_goal_ids": []
    }
  ]
}
```

If UMI's value and the referent's canonical value disagree, GA cannot link them:
a `resolved_references` value that does not match the supplied referent rejects
the GA result rather than choosing between the two.

The Planner receives that WHAT and the resolved reference and extracts
`location=内乡`; it does not reinterpret `那边`.
A deterministic provenance validator rejects any executable step that claims
this Goal while sending `location=重庆`.

## Verified memory retrieval

Memory is a shared cognitive substrate, not another semantic decision owner. UMI,
GA, Social Cognition and Planner receive role-bounded activated Memory projections;
Planner combines the current canonical Goal, actual Runtime Work/Evidence, relevant
activated Memory and the verified-tool-memory index before authoring new Work.
Memory may make reuse relevant, but it never establishes execution, completion or
authorization by itself.

The committed `ExecutionOutcomeBundle` is the authoritative write boundary for
verified tool-result Memory. Once a provider observation is schema-valid, exact-bound
to committed Work and accepted into ExecutionOutcome, conversation state immediately
retains its bounded evidence ID, tool ID, original material arguments, age/provenance
and result payload. Reuse therefore does not depend on a later spoken response carrying
the outcome bundle again. Only completed observations are advertised for retrieval.

Raw prior result contents are not injected into Goal Association or ordinary
Planner prompts. Instead, the Planner sees a bounded index containing
only:

- `evidence_id`;
- original `tool_id`;
- exact original request arguments;
- age/provenance;
- source Goal and plan IDs.

The index contains no result facts. When one entry matches every resolved
material Goal binding and is fresh enough, the Planner may execute:

```json
{
  "capability_id": "chromie.memory.retrieve_verified_tool_result",
  "args": {
    "evidence_id": "evidence_neixiang_weather",
    "tool_id": "chromie.weather.lookup",
    "material_args": {
      "location": "内乡",
      "date": "today"
    },
    "max_age_s": 900
  }
}
```

Planner validation requires `material_args` to contain every authoritative Goal
binding without contradicting it, and to select exactly one index entry with the
same `evidence_id` and `tool_id`. The host-runtime provider then checks that each
`material_args` key is present in the stored request arguments with an equal
value (strings compared after case-folding and whitespace collapse; stored
arguments not named in `material_args` are not compared), that the stored
result completed, and that its age is within `max_age_s` (Planner-chosen, schema
range 1-86400 s, default 900). It returns the prior trusted data only after
execution. It does not search loosely and does not resolve references.

If the index contains only `location=重庆`, it is not a match for the Neixiang
Goal. The Planner must use a fresh weather lookup for Neixiang instead.

## Completed-Goal conversational continuity

The verified-memory index proves only identity, arguments, freshness, and
provenance. It is never answer evidence. Separately, conversation state may
retain a bounded assistant turn only when Social Cognition's post-Evidence
speech was actually delivered and the Host marks it with its source Goal and
Canonical Plan IDs. Planner and SC may use this delivered
evidence-bound dialogue to interpret or restate the same completed Goal without
reopening it or repeating the external read.

When Social Cognition delivers the final evidence-bound answer, playback completion is
also the lifecycle boundary for the covered information Goal. The delivered dialogue is
recorded with its exact source Goal, Plan and Evidence references, and the Goal is closed
only when those references match committed completed execution Evidence. Progress speech,
undelivered speech, or an answer lacking matching Evidence cannot close an information
Goal. This keeps conversation continuity, Memory reuse and Goal lifecycle consistent.

This projection is deliberately narrower than raw result memory:

- it contains only user-visible text that was already delivered;
- it is accepted only from the Host's post-execution evidence boundary;
- it remains scoped to the recorded source Goal IDs;
- measurements and conditions must be preserved exactly; and
- it cannot supply a new fact, changed binding, fresher time scope, or detail
  absent from the delivered dialogue.

If a response Goal is represented only by the verified-memory index and has no
matching delivered evidence-bound dialogue, validation rejects a direct factual
response. The Planner must execute exact verified-memory retrieval, perform a
fresh read, or report an honest limitation. This preserves ordinary follow-up conversation without
turning provenance metadata or general chat history into external-fact
authority.

## Safe-read speech

A pending safe read requires one model-authored immediate acknowledgement, and
the runtime starts speech and retrieval concurrently. The Host enforces the
stage, commitment, and evidence boundaries but does not impose a character,
word, or sentence-count style limit.

Examples of valid model-authored meaning include:

- fresh read: “我查一下内乡今天有没有下雨。”
- exact memory retrieval: “我刚才好像查过内乡，我把结果找出来看看。”

Only Social Cognition's post-Evidence Communicative Activity may state weather
facts, and only from trusted Evidence.

## Invariants

- No Host keyword, regex, or “latest city wins” reference rule.
- No global location slot shared by unrelated Goals.
- Explicit current user meaning outranks discourse focus; foreground scoped
  referents outrank candidate Goal bindings and recent dialogue.
- Tool memory cannot decide a reference.
- Goal bindings are immutable planner grounding.
- Memory retrieval must exactly match those bindings.
- Old result contents remain usable only through explicit executed retrieval;
  already-delivered evidence-bound dialogue may be restated only for its exact
  completed Goal.
- Physical robot location remains Soridormi/runtime state, not a discourse
  location referent.

## Provider location recognition does not change discourse authority

Once a weather location is grounded for the canonical Goal (resolved by UMI, linked to
its referent by Goal Association, extracted as the Capability argument by the Planner),
it is immutable. For example, `河南省内乡县` stays the tool argument even when a provider
geocoder cannot match that full administrative string. The weather adapter may
query bounded equivalent forms such as the locality name and may use supplied
province/country fields to qualify candidates. These are retrieval mechanics for
the same place, not a new semantic decision.

The adapter must:

- query the canonical location first;
- retain the canonical location as the request target;
- reject a same-named candidate whose administrative context contradicts the
  resolved place;
- return typed `location_not_found` when no qualified candidate exists; and
- never use geocoder results to resolve `那边`, select an active Goal, or replace
  a discourse referent.

The maintained `chongqing_then_neixiang_weather_stays_grounded` scenario protects
the multi-turn semantic boundary, while provider tests protect the full-name to
locality fallback and wrong-province rejection.
