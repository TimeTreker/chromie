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
    "quantity": "one",
    "attributes": {}
  },
  "source": {
    "status": "known",
    "description": "100 meters ahead",
    "bindings": {}
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
    "attributes": {}
  },
  "source": {
    "status": "provider_resolved",
    "description": "current external information",
    "bindings": {
      "location": {
        "name": "location",
        "entity_type": "place",
        "value": "重庆龙兴天街附近",
        "confidence": 1.0
      }
    }
  },
  "recipient": {
    "description": "requester",
    "referent_id": null
  },
  "delivery_mode": "spoken_explanation"
}
```

`responsibility_type=acquire_and_deliver_resource` plus `resource.kind` is the
canonical semantic discriminator. The old `responsibility_variant` field is accepted
only as an input-compatibility alias for persisted/older payloads; it is validated
against `resource.kind` and omitted from canonical serialization. Planner matching
therefore never depends on names such as `fetch_and_deliver_object` or
`fetch_and_deliver_information`.

The semantic contract forbids provider IDs, capability IDs, coordinates, grasp
poses, websites, search engines, execution mode, and implementation plans.
Those belong downstream.

## Goal Association ownership

Goal Association decides whether the current turn creates, continues, modifies,
or supplies missing information for a resource responsibility.

A fetch-and-deliver request is one Goal when navigation, locating, grasping,
carrying, returning, and handover are provider-owned stages of one user outcome.
Likewise, external search, evidence retrieval, evaluation, and natural
explanation remain one information-resource responsibility. Weather therefore has
`resource.kind=information`, while the Planner still selects the exact
`chromie.weather.lookup` Capability rather than a generic hidden router.

A query-scope binding is not source evidence. A place, date, person, product, or other
entity that tells a provider *what to search for* remains an ordinary Goal binding; it does not
make `source.status=known`. `known` requires an actual user/discourse-supplied information source.
Otherwise Goal Association uses `unknown` or `provider_resolved` according to the intended
contract. This prevents a location such as a neighborhood or city from being misrepresented as
the source that supplied the requested information.

The acquisition and its evidence-dependent explanation also stay one semantic responsibility.
Goal Association must not duplicate one information request into one capability Goal that
retrieves evidence and another capability Goal whose only purpose is to answer from that same
evidence. Response/Tool Result Interpretation owns the natural delivery after acquisition. If a model promotes an evidence-dependent answer into another provider-required Goal with no
independent bindings/resource contract, semantic review re-segments from the authoritative user
turn rather than allowing duplicate provider calls.

Separate Goals are still required for independently requested outcomes. For
example, “bring the book and tell me a joke” contains one physical resource Goal
and one spoken-response Goal.

When the source is unknown, Goal Association retains the clear Goal with
`source.status=unknown`; the Planner may request the specific missing binding.
A later location reply is associated semantically with that retained Goal. The
Host does not attach turns by recency or a phrase rule.

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
