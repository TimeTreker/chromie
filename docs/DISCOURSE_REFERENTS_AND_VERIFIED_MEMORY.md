# Scoped Discourse Referents and Verified Tool Memory

## Status

Implemented for bounded conversation state, Goal Association, Fast/Deep
Planning, Response Composition, and host-runtime verified-result retrieval.

This design exists to prevent one task's structured evidence from silently
resolving another task's pronouns or parameters. It deliberately does not use a
single global field such as `current_location`.

## Authority model

Chromie's cognitive stages have distinct responsibilities:

1. **Cognitive Gateway** admits the turn and selects a broad lane such as
   `chat`, `tool`, or `robot_action`. It does not decide what `那边`, `那里`,
   `there`, or another reference means.
2. **Goal Association** uses the current user meaning, scoped discourse
   referents, focus, active Goal bindings, and recent dialogue to resolve
   references and create explicit Goal bindings.
3. **Host conversation state** validates and stores the LLM-authored typed
   referent/focus mutations, IDs, provenance, and bounded persistence. It does
   not contain phrase rules or choose a semantic referent.
4. **Fast/Deep Planner** receives resolved Goal bindings and decides whether to
   retrieve one exact verified prior result or execute a fresh read.
5. **Response Composer** authors natural pre-result speech. It may say that
   Chromie is checking a source or retrieving a recently checked result, but it
   cannot state the result before trusted evidence returns.
6. **Tool Result Interpreter** produces the final grounded answer from the
   executed memory-retrieval or external-read evidence.

Tool-result memory is never reference-resolution authority.

An ordinary explicit entity mention is not a resolved reference. For example,
`今天晚上重庆热不热？` places `重庆` directly in the Goal binding and may introduce
a salient scoped referent for later dialogue. `resolved_references` is reserved for
indirect expressions such as `那边`, pronouns, ellipsis, aliases, corrections, or
task mentions that the LLM binds to an already supplied discourse referent or active
Goal binding. Every such indirect resolution carries the copied referent ID and an
explicit confidence; omitted confidence is a contract error rather than an implicit
low- or high-confidence decision.

Goal references are generic, not location-specific. A phrase such as “the last
task I told you” is associated by the same Goal Association LLM against bounded
active/recoverable Goals and dialogue context. The Host does not contain a phrase
map for “last task,” “that one,” “那里,” or any other normal semantic reference.
Operational follow-up phrase settings may preserve context across idle time, but
they never select a Goal.

## Why there is no global `current_location`

One robot can simultaneously hold locations for independent scopes:

- physical robot position or navigation destination;
- a weather Goal about Chongqing;
- a travel discussion about Neixiang;
- another remembered event associated with Beijing.

These values must coexist. A discourse referent therefore carries:

- a stable Host-generated `referent_id`;
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

Goal Association may emit a model-authored correction:

```json
{
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
      "description": "确认用户纠正的地点是内乡。",
      "bindings": [
        {
          "name": "location",
          "entity_type": "location",
          "value": "内乡",
          "confidence": 1.0
        }
      ]
    }
  ]
}
```

The Host generates the new referent ID, stores Neixiang as foreground, and
moves only the explicitly superseded Chongqing discourse referent to
background. The old Chongqing task and evidence remain available in their own
scope.

### Dependent question

For:

> 今天那边下雨了没有？

Goal Association receives the foreground Neixiang referent and emits:

```json
{
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
      "description": "查询今天内乡是否下雨。",
      "bindings": [
        {
          "name": "location",
          "entity_type": "location",
          "value": "内乡",
          "referent_id": "ref_neixiang",
          "confidence": 1.0
        },
        {
          "name": "date",
          "entity_type": "date",
          "value": "today",
          "confidence": 1.0
        }
      ]
    }
  ]
}
```

Downstream planners receive `location=内乡`; they do not reinterpret `那边`.
A deterministic provenance validator rejects any executable step that claims
this Goal while sending `location=重庆`.

## Verified memory retrieval

Raw prior result contents are not injected into Goal Association, Planner, or
Response Composer prompts. Instead, the Planner sees a bounded index containing
only:

- `evidence_id`;
- original `tool_id`;
- exact original request arguments;
- age/provenance;
- source Goal and plan IDs.

The index contains no result facts. When one entry exactly matches every
resolved material Goal binding and is fresh enough, the Planner may execute:

```json
{
  "skill_id": "chromie.memory.retrieve_verified_tool_result",
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

The host-runtime provider performs exact value matching and returns the prior
trusted data only after execution. It does not search loosely and does not
resolve references.

If the index contains only `location=重庆`, it is not a match for the Neixiang
Goal. The Planner must use a fresh weather lookup for Neixiang instead.

## Safe-read speech

A pending safe read requires one model-authored immediate acknowledgement, and
the runtime starts speech and retrieval concurrently. The Host enforces the
stage, commitment, and evidence boundaries but does not impose a character,
word, or sentence-count style limit.

Examples of valid model-authored meaning include:

- fresh read: “我查一下内乡今天有没有下雨。”
- exact memory retrieval: “我刚才好像查过内乡，我把结果找出来看看。”

Only the post-execution interpreter may state weather facts.

## Invariants

- No Host keyword, regex, or “latest city wins” reference rule.
- No global location slot shared by unrelated Goals.
- Explicit current user meaning outranks discourse focus; foreground scoped
  referents outrank active Goal bindings and recent dialogue.
- Tool memory cannot decide a reference.
- Goal bindings are immutable planner grounding.
- Memory retrieval must exactly match those bindings.
- Old evidence remains usable only through an explicit executed retrieval.
- Physical robot location remains Soridormi/runtime state, not a discourse
  location referent.

## Provider location recognition does not change discourse authority

After Goal Association has resolved a weather location, the canonical binding is
immutable. For example, `河南省内乡县` stays the tool argument even when a provider
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
