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

Separate Goals are still required for independently requested outcomes. For
example, “bring the book and tell me a joke” contains one physical resource Goal
and one spoken-response Goal.

When the source is unknown, Goal Association retains the clear Goal with
`source.status=unknown`; the Planner may request the specific missing binding.
A later location reply is associated semantically with that retained Goal. The
Host does not attach turns by recency or a phrase rule.

## Planner ownership

The Planner compares the complete Goal against exact available capability
semantics.

It must never use a partial primitive as proof of the complete outcome:

```text
walk_forward completed        ≠ object delivered
web search started            ≠ grounded answer delivered
grip command completed        ≠ object acquired and handed over
one candidate retrieved       ≠ recommendation evaluated for the user
```

The Planner may choose:

- `soridormi.acquire_and_deliver_resource` when Soridormi advertises
  `responsibility_type=acquire_and_deliver_resource`,
  `resource_kinds=[physical_object]`, and `delivery_modes=[physical_handover]`;
- `chromie.weather.lookup` for its exact structured weather scope;
- `chromie.external_information.retrieve` for grounded places, restaurants,
  recommendations, news, how-to research, and general external information;
- another future exact provider capability whose declared scope covers the
  complete responsibility.

These examples are capability contracts, not Host routing rules.

## Soridormi named-skill contract

Soridormi should advertise one provider-scoped implementation of the shared
resource responsibility rather than inventing a second top-level semantic
concept or one skill per object type. The capability ID is provider-specific;
the matching contract is the semantic scope:

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
  "resource_claims": [
    "locomotion",
    "right_gripper",
    "carried_object"
  ],
  "metadata": {
    "semantic_scope": {
      "responsibility_type": "acquire_and_deliver_resource",
      "resource_kinds": ["physical_object"],
      "acquisition": "provider_owned",
      "delivery_modes": ["physical_handover"],
    },
    "resource_contract": {
      "result_field": "resource_outcome",
      "completion_requires": [
        "resource_acquired",
        "resource_delivered"
      ],
      "provider_owns": [
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

Soridormi may initially implement navigation, grasp, carrying, and handover with
scripted or idealized behavior. That is a provider implementation detail. The
provider must still return a coherent world-state result and may claim
completion only when the complete contract is satisfied.

Successful provider evidence may include:

```json
{
  "completed": true,
  "skill_id": "acquire_and_deliver_resource",
  "summary": "The requested bottle was acquired and delivered.",
  "resource_outcome": {
    "responsibility_type": "acquire_and_deliver_resource",
    "resource_kind": "physical_object",
    "resource_description": "a bottle of water",
    "resource_acquired": true,
    "resource_delivered": true,
    "recipient_description": "requester",
    "evidence_summary": "Object attachment and delivery state were verified by Soridormi."
  }
}
```

Chromie's adapter retains the bounded `resource_outcome` as provider evidence.
For a capability whose semantic scope declares
`acquire_and_deliver_resource`, `completed=true` is rejected unless both
`resource_acquired=true` and `resource_delivered=true` are present. The response
layer does not expose provider mode in ordinary speech.

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


## Semantic planning versus provider-local planning

There is one semantic planning authority. Chromie decides which user-visible
responsibilities exist, which exact capability can satisfy each responsibility, and
the ordering/dependencies between independent responsibilities. A selected provider
may then plan *inside* that bounded capability contract.

For example, after Chromie selects `soridormi.acquire_and_deliver_resource`,
Soridormi may internally resolve a source, navigate, perceive, grasp, carry, recover,
and hand over the object. Those provider-local stages are not new Chromie Goals and
do not reinterpret the user's intent. Likewise, a weather provider may acquire and
normalize forecast evidence while Chromie still owns evidence interpretation and
conversational delivery. Shared abstraction does not imply a shared provider.

A useful boundary test is: if a step can be independently requested, changed,
cancelled, or judged by the user, it belongs in Chromie's semantic plan. If it exists
only because a selected capability needs it to satisfy its own contract, it belongs
inside the provider.

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
