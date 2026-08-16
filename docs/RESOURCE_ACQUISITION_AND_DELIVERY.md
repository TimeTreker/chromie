# Resource Acquisition and Delivery

## Status

The provider-neutral semantic contract is implemented in
`shared.chromie_contracts.resource`. Goal Association may attach one
`resource_responsibility` to a `SemanticGoal`. Fast Planner and Deep Planner
select an exact registered capability later; neither Goal Association nor the
Host chooses a provider from resource kind, keywords, or hardcoded routing.

The information-provider adapter `chromie.external_information.retrieve` is
implemented but disabled until `AGENT_EXTERNAL_INFORMATION_ENABLED=1` and an
exact provider endpoint is configured. Soridormi physical resource delivery is
a live named-skill contract: Chromie imports it automatically when Soridormi
advertises `acquire_and_deliver_resource` with a matching physical-resource semantic scope through `soridormi.skill.list`.

## Human responsibility

Many apparently different requests share one human-level responsibility:

```text
acquire something the user needs
→ make it available to the intended recipient
→ prove the complete outcome
```

The requested resource may be physical or informational. The stable top-level
contract is **only** `AcquireAndDeliverResource`. `physical_object` and
`information` are resource kinds inside that responsibility, not separate
capability concepts and not separate planning authorities:

```text
AcquireAndDeliverResource Goal
└── resource.kind
    ├── physical_object
    └── information
               │
               ▼
      Goal-driven Planner
               │
      exact capability selection
               │
               ▼
  Trusted Capability Runtime
               │
               ▼
       Capability Provider
       ├── Soridormi
       ├── External Information
       ├── Weather
       ├── Memory
       └── future peer providers
```

Soridormi is a capability provider. It is not a special architectural layer and
is not selected by a Host rule such as `resource.kind == physical_object`.
External-information, weather, memory, home automation, and future services are
peer providers behind the same trusted boundary.

## Chromie's self-concept

Provider backend, simulator/hardware mode, transport, source engine, and test
configuration are engineering evidence. They do not belong in Chromie's
ordinary self-concept or conversation.

Chromie reasons about the user-visible responsibility:

- find and bring the bottle;
- find and explain the restaurant information;
- check and explain the weather.

The runtime may retain provider mode for audit and safety, but normal speech
must not announce that Chromie is in a simulation or hardware world. An
explicit engineering diagnostic request may expose provider evidence through a
separate technical surface without changing Chromie's Mind.

## Semantic contract

`AcquireAndDeliverResource` contains only user-semantic fields:

```json
{
  "responsibility_type": "acquire_and_deliver_resource",
  "resource": {
    "kind": "physical_object",
    "description": "a bottle of water",
    "quantity": "1",
    "attributes": {}
  },
  "source": {
    "status": "known",
    "description": "100 meters ahead",
    "bindings": {
      "distance": {
        "name": "distance",
        "entity_type": "distance",
        "value": "100",
        "confidence": 1.0
      },
      "direction": {
        "name": "direction",
        "entity_type": "direction",
        "value": "ahead",
        "confidence": 1.0
      }
    }
  },
  "recipient": {
    "description": "requester",
    "referent_id": null
  },
  "delivery_mode": "physical_handover"
}
```

Information example:

```json
{
  "responsibility_type": "acquire_and_deliver_resource",
  "resource": {
    "kind": "information",
    "description": "good nearby restaurant recommendations",
    "quantity": "",
    "attributes": {
      "location": {
        "name": "location",
        "entity_type": "place",
        "value": "重庆龙兴天街附近",
        "confidence": 1.0
      }
    }
  },
  "source": {
    "status": "provider_resolved",
    "description": "current external information",
    "bindings": {}
  },
  "recipient": {
    "description": "requester",
    "referent_id": null
  },
  "delivery_mode": "spoken_explanation"
}
```

`responsibility_type=acquire_and_deliver_resource` plus `resource.kind` is the
canonical semantic discriminator. The removed `responsibility_variant` field is not
accepted as an input alias; old names such as `fetch_and_deliver_object` and
`fetch_and_deliver_information` are rejected instead of translated.

The semantic contract forbids provider IDs, capability IDs, coordinates, grasp
poses, websites, search engines, execution mode, and implementation plans.
Those belong downstream.

## Goal Association ownership

Goal Association decides whether the current turn creates, continues, modifies,
or supplies missing information for a resource responsibility.

`SemanticGoal.resource_responsibility` is the resource domain's sole persisted
semantic authority. Resource identity, kind, quantity, source, recipient, and
delivery mode are authored exactly once there. The Goal-Association model-facing
schema also has one writable owner per fact: information requests put location,
time, requested aspect, and similar query facts only in `query_scope`; the narrow
information `source` carries source status/identity only. Physical requests put
spatial/acquisition facts only in `source.acquisition_bindings`. The Host then
materializes one canonical `resource_responsibility`; it does not persist a second
flat `SemanticGoal.object.bindings` copy. Generic Planner checks may derive a
transient flat view from the canonical object, but that view is never written back.
A Goal description is a
human-readable summary: it may be checked for material contradiction but never
supplies, overrides, or repairs a typed resource fact. Generic Goal bindings and
Planner argument views must not be separately model-authored copies of resource
facts. When an existing consumer needs a flat quantity, source, recipient, or
other resource parameter view, trusted code constructs a frozen deterministic
projection from the canonical resource object and retains exact field provenance.
The projection is absent from every model response schema and has no mutation or
persistence authority.

Resource source bindings live inside the canonical `ResourceSource.bindings`
object. Information query-scope attributes live inside the canonical resource
descriptor rather than masquerading as source evidence. Any temporary adapter for
an older consumer is output-only, mechanically derived, and removed with that
consumer; it is never accepted back as semantic input.

At the Goal Association model boundary, a physical object's complete identity is
written in `resource.description` and its normalized count in `quantity`;
physical `resource.attributes` is closed. This makes acquisition location,
distance, direction, and route structurally writable only in `source.bindings`,
and recipient meaning writable only in `recipient`. Information resources keep
`resource.attributes` as the typed owner for query location, time, aspects, and
other provider-neutral query scope.

`source.description` is a human-readable summary rather than typed source truth.
Consequently, `source.status=known` requires at least one typed `source.bindings`
entry. `unknown` carries neither description nor bindings, while
`provider_resolved` delegates source selection without inventing a known source.
Canonical validation also rejects an identical typed `(entity_type, value)` fact
when it appears under both `resource.attributes` and `source.bindings`, even if
the model gives the two copies different names. Normalized measurement aliases
are equivalent for this check, so `100m` and `100 meters ahead` cannot evade the
one-owner rule while unrelated units remain distinct. This enforces one writable
owner without using field-name rules to decide which semantic role is correct.
Likewise, an explicit numeric literal in `source.description` must appear in at
least one typed source-binding value. This is a provenance check over the source
classification the model already made; it does not infer source meaning from the
user's words or move facts between owners.

A fetch-and-deliver request is one Goal when navigation, locating, grasping,
carrying, returning, and handover are provider-owned stages of one user outcome.
Likewise, external search, evidence retrieval, evaluation, and natural
explanation remain one information-resource responsibility. Weather therefore has
`resource.kind=information`, while the Planner still selects the exact
`chromie.weather.lookup` Capability rather than a generic hidden router.
When the canonical information attributes include a day part such as `tonight`,
the Planner must preserve that exact scope in the Capability arguments. A date
like `today` is not equivalent. Exact completion requires provider output scoped
to the requested period; daily or current observations cannot be promoted into
narrower day-part evidence by response wording.

A query-scope binding is not source evidence. A place, date, person, product, or other
entity that tells a provider *what to search for* remains a canonical
`resource.attributes` binding; it does not make `source.status=known`. `known`
requires an actual user/discourse-supplied information source.
Otherwise Goal Association uses `unknown` or `provider_resolved` according to the intended
contract. This prevents a location such as a neighborhood or city from being misrepresented as
the source that supplied the requested information.

Physical-resource spatial bindings require an explicit semantic home. A direction,
distance, or location may describe the resource/acquisition route, the recipient, the
delivery destination, or an independent requested effect; its type alone does not decide
which. Goal Association's model owns that classification. Trusted code may detect that a
typed spatial fact is unowned and reject the DTO, but it must not infer the role from a
phrase or field name. The final DTO represents the fact once in the matching
source/recipient/delivery contract. A `reason_summary` cannot substitute for the actual
field, and a repeated contradiction fails closed before planning rather than starting an
alignment or residual-repair workflow.

The acquisition and its evidence-dependent explanation also stay one semantic responsibility.
Goal Association must not duplicate one information request into one capability Goal that
retrieves evidence and another capability Goal whose only purpose is to answer from that same
evidence. Response/Tool Result Interpretation owns the natural delivery after acquisition. If a model promotes an evidence-dependent answer into another provider-required Goal with no
independent bindings/resource contract, the bounded coverage proof rejects that
candidate set and permits one fresh interpretation from the authoritative user
turn rather than allowing duplicate provider calls.

Separate Goals are still required for independently requested outcomes. For
example, “bring the book and tell me a joke” contains one physical resource Goal
and one spoken-response Goal.

When the source is unknown, Goal Association retains the clear Goal with
`source.status=unknown`; the Planner may request the specific missing binding.
A later location reply is associated semantically with that retained Goal. The
Host does not attach turns by recency or a phrase rule.

## Continuous progress across resource responsibilities

`AcquireAndDeliverResource` describes the human responsibility; it is **not** an
early-execution mechanism. Do not add semantic fields such as `early_execute`,
`speculative`, `wait_for_goal_association`, or provider-specific fast-path flags
to the Goal. Whether some part of the responsibility may advance now is a
runtime/cognitive readiness question over the current understanding, evidence,
dependencies, effects, confirmation state, authorization, hard-boundary
principles, and resources.

This distinction allows one semantic responsibility to cover both responsive
information acquisition and carefully gated physical acquisition without a
provider- or resource-kind router. It does **not** let Fast Goal Interpretation
perform the acquisition.

For information, Fast Goal Interpretation may resolve the provider-neutral human
need and material bindings early, while Goal Association decides continuity and
canonical ownership. The provider request begins only after that Goal exists and
Planner selects the exact acquisition method:

```text
existing Goal: go out for dinner tonight

user: "Will Chongqing get heavy rain today?"

Fast Goal Interpretation
  |-- Responsibility: provide today's Chongqing weather
  |-- bindings: location=Chongqing, time=today
  `-- optional acknowledgement speech

Goal Association
  `-- associate/create canonical weather Goal and relate it to dinner

Fast Planner
  `-- exact weather read Capability + executable args

Trusted Capability Runtime
  `-- weather evidence

weather evidence + Goal relationship
  -> Chromie answers the rain question in the context that actually matters
```

The semantic interpretation can be useful before relationship analysis completes,
but provider acquisition is Planner-owned work after canonical Goal binding. This
is not a second information Goal and does not change the
`AcquireAndDeliverResource` contract.

Physical resource delivery demonstrates the opposite readiness boundary. For
"bring me a bottle of water", understanding the human responsibility does not
by itself authorize locomotion or manipulation. Canonical planning, capability
coverage, confirmation when required, resource arbitration, and provider safety
must reach their normal barriers before the physical Activity branch advances.
Cognition, clarification, and Social Attention may continue meanwhile.

Risk and prohibition are orthogonal to the Goal type. A request such as "bring
me that knife so I can hurt someone" may still be correctly understood as an
`AcquireAndDeliverResource` responsibility at the semantic level. That valid Goal
shape does not authorize the effect. Compact always-on hard-boundary principles
in Chromie's stable Mind are sufficient to keep the harmful Activity branch
closed; Chromie does not need the text of an applicable criminal statute in her
prompt to know that she must not carry out the harmful request. Goal reasoning,
Social Attention, a truthful refusal, and safe alternative reasoning may
continue.

If the user instead asks a concrete legal question, such as whether a particular
act is lawful in a specific jurisdiction, that law is itself dynamic
information-resource acquisition. The relevant current statutes, regulations,
jurisdiction, effective dates, and exceptions must be obtained from suitable
trusted sources with freshness/provenance and then interpreted for the Goal.
They are not worldview, values, personality, or cached Mind content.

The same readiness rule therefore generalizes beyond resources: ordinary
provider-free conversation may respond as soon as its answer is complete;
Capability work may advance as soon as canonical Goal grounding, Planner
selection, and its own authorization/dependency boundaries are sufficient; drafts
or other reversible preparation may advance only within the authority of their
owning stage; and committed external or physical effects retain the stronger
confirmation, authorization, prohibition, and safety dependencies they require.

## Planner ownership and dynamic capability granularity

The Planner compares the complete Goal against the **current** capability catalog.
`AcquireAndDeliverResource` remains one Goal whether its execution plan has one
capability step or several. Capability atomicity is relative to the planner that
consumes the catalog, not a permanent property of the user Goal.

The decomposition rule is:

1. Prefer one exact capability when its declared resource contract covers the
   complete required outcome. Chromie treats that capability as one atomic plan leaf.
2. If no single capability covers the Goal, compose multiple **advertised**
   capabilities when their declared `plan_requires` / `plan_provides` resource-state
   contracts form a valid ordered chain whose union covers the Goal.
3. Never invent provider-internal navigation, perception, grasp, search, retry, or
   handover stages that are not exposed as capabilities. Those remain inside the
   selected provider capability.
4. Never accept a partial capability or partial chain as proof of complete Goal
   satisfaction.

For physical handover, plan-level completion requires the resource state to establish
both `resource_acquired` and `resource_delivered`. For information resources, the
provider plan must establish acquisition of trusted information evidence; the
resource contract may declare `final_delivery_owner=chromie_response_layer`, in
which case Tool Result Interpretation and Response Composition own the final human
delivery.

This makes the boundary evolve naturally. If Soridormi currently advertises only
`acquire_resource` and `deliver_resource`, Deep Planning may compose them. If a later
Soridormi version can reliably guarantee the complete workflow and advertises
`acquire_and_deliver_resource`, Chromie may use that one capability instead. No Goal
schema, phrase rule, or provider-specific route needs to change.

A provider capability that contributes to a resource Goal declares a provider-neutral
plan contract such as:

```json
{
  "semantic_scope": {
    "responsibility_type": "acquire_and_deliver_resource",
    "resource_kinds": ["physical_object"]
  },
  "resource_contract": {
    "plan_requires": [],
    "plan_provides": ["resource_acquired"],
    "completion_requires": ["resource_acquired"]
  }
}
```

A later delivery capability may declare:

```json
{
  "semantic_scope": {
    "responsibility_type": "acquire_and_deliver_resource",
    "resource_kinds": ["physical_object"],
    "delivery_modes": ["physical_handover"]
  },
  "resource_contract": {
    "plan_requires": ["resource_acquired"],
    "plan_provides": ["resource_delivered"],
    "completion_requires": ["resource_delivered"]
  }
}
```

The state labels are capability-contract facts, not new Goals. They let deterministic
validation prove that the selected capability chain is coherent without making the
Host a semantic planner.

## Soridormi capability contracts

Soridormi may advertise capabilities at whatever semantic granularity its current
body/runtime can **truthfully guarantee**. It may expose a complete composite, smaller
resource capabilities, or both. Higher-level capabilities are optimizations and
stronger provider promises; they are not hardcoded mappings from the Goal type.

A complete provider-scoped capability may advertise:

```json
{
  "skill_id": "acquire_and_deliver_resource",
  "description": "Acquire a described physical object from a semantic source and deliver it to the intended recipient.",
  "available": true,
  "requires_confirmation": true,
  "safety_class": "physical_motion",
  "effects": [
    "physical_motion",
    "object_manipulation",
    "resource_delivery"
  ],
  "parameters_schema": {
    "type": "object",
    "properties": {
      "resource": {
        "type": "object",
        "properties": {
          "kind": {"type": "string", "enum": ["physical_object"]},
          "description": {"type": "string", "minLength": 1},
          "quantity": {"type": "string"},
          "attributes": {"type": "object"}
        },
        "required": ["kind", "description"],
        "additionalProperties": false
      },
      "source": {
        "type": "object",
        "properties": {
          "status": {
            "type": "string",
            "enum": ["known", "unknown", "provider_resolved"]
          },
          "description": {"type": "string"},
          "bindings": {"type": "object"}
        },
        "required": ["status"],
        "additionalProperties": false
      },
      "recipient": {
        "type": "object",
        "properties": {
          "description": {"type": "string", "minLength": 1},
          "referent_id": {"type": ["string", "null"]}
        },
        "required": ["description"],
        "additionalProperties": false
      }
    },
    "required": ["resource", "source", "recipient"],
    "additionalProperties": false
  },
  "metadata": {
    "semantic_scope": {
      "responsibility_type": "acquire_and_deliver_resource",
      "resource_kinds": ["physical_object"],
      "delivery_modes": ["physical_handover"]
    },
    "resource_contract": {
      "result_field": "resource_outcome",
      "plan_requires": [],
      "plan_provides": [
        "resource_acquired",
        "resource_delivered"
      ],
      "completion_requires": [
        "resource_acquired",
        "resource_delivered"
      ],
      "provider_owns": [
        "source_resolution",
        "navigation",
        "perception",
        "grasping",
        "carrying",
        "handover",
        "safety",
        "recovery"
      ]
    }
  }
}
```

Soridormi may internally implement that capability with rules, a behavior tree, a
local planner, learned policies, deterministic controllers, or another hierarchy.
Those mechanisms do not become a second Chromie semantic planner because they are
bounded by the already-selected capability contract.

Successful composite-provider evidence may include:

```json
{
  "completed": true,
  "skill_id": "acquire_and_deliver_resource",
  "resource_outcome": {
    "responsibility_type": "acquire_and_deliver_resource",
    "resource_kind": "physical_object",
    "resource_description": "a bottle of water",
    "resource_acquired": true,
    "resource_delivered": true,
    "recipient_description": "requester"
  }
}
```

Chromie's adapter validates only the `completion_requires` declared by the exact
capability that produced a result. Goal completion is stricter: the complete Plan and
subsequent response/evidence path must still establish every state required by the
Goal. A successful `acquire_resource` result therefore proves acquisition only; it
does not by itself close a physical delivery Goal.

## External-information provider contract

`chromie.external_information.retrieve` is the generic information-resource
capability. It accepts a fully specified question plus optional location, time,
freshness, and constraints. It returns evidence material, not Chromie's final
personality speech.

Supported request kinds are:

- `general_research`;
- `fact_lookup`;
- `recommendation`;
- `place_search`;
- `restaurant_search`;
- `how_to`;
- `news`.

The provider response contains:

- normalized query metadata;
- a bounded summary for interpretation;
- structured result items;
- at least one source record;
- a non-empty retrieval time;
- provider identifier for internal evidence.

The adapter rejects a nominally successful response with no source evidence or
no retrieval timestamp. The provider result is evidence material only; it cannot
supply final personality speech.

Tool Result Interpreter verifies the evidence and Response Composer delivers it
naturally. A more exact provider capability remains preferable when its scope
matches, such as the structured weather contract.


## Stable authority, dynamic decomposition boundary

There is one user-semantic planning authority, but there is no permanently fixed
line saying which physical subproblem must be planned in Chromie versus Soridormi.
The live capability catalog negotiates that line.

Chromie owns the Goal and plans **across advertised capabilities**. A provider owns
planning **inside each selected capability**. If the provider exposes a high-level
capability, its internal decomposition is private. If it exposes smaller capabilities
instead, those capabilities become separate leaves that Chromie's Planner may compose.
A provider may expose both granularities simultaneously.

This is analogous to a central SoC and an ECU/domain controller: the central planner
chooses subsystem capabilities and coordinates them with other domains, while the
subsystem may have sophisticated local planning and control. Improving the subsystem
can move the capability boundary upward without transferring user-semantic authority.

The durable rule is therefore: **semantic authority is stable; capability atomicity
is dynamic**.

## Completion and failure

Physical completion requires both acquisition and delivery evidence. Information
completion requires successful retrieval, adequate grounding/freshness, and
user delivery through the response layer.

Typed failures should preserve the failed stage:

- unresolved source or material binding;
- exact capability unavailable;
- source/retrieval/provider failure;
- object not found;
- acquisition/grasp failure;
- transport or delivery failure;
- evidence malformed or insufficient;
- response delivery interrupted.

No stage may be silently converted into complete success.
