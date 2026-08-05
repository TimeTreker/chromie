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
advertises `fetch_and_deliver_object` through `soridormi.skill.list`.

## Human responsibility

Many apparently different requests share one human-level responsibility:

```text
acquire something the user needs
→ make it available to the intended recipient
→ prove the complete outcome
```

The requested resource may be physical or informational. The stable top-level
contract remains `AcquireAndDeliverResource`; an explicit semantic variant makes
the two user-facing responsibilities visible without changing provider matching:

```text
AcquireAndDeliverResource Goal
├── fetch_and_deliver_object
└── fetch_and_deliver_information
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
  "responsibility_variant": "fetch_and_deliver_object",
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
  "responsibility_variant": "fetch_and_deliver_information",
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

The stable `responsibility_type` preserves compatibility with existing Capability
semantic scopes. `responsibility_variant` is a semantic subtype, not a Provider,
Capability ID, or hidden routing instruction. Legacy payloads that omit it are
normalized from `resource.kind`; an explicit mismatched variant is rejected.

The semantic contract forbids provider IDs, capability IDs, coordinates, grasp
poses, websites, search engines, execution mode, and implementation plans.
Those belong downstream.

## Goal Association ownership

Goal Association decides whether the current turn creates, continues, modifies,
or supplies missing information for a resource responsibility.

A fetch-and-deliver request is one Goal when navigation, locating, grasping,
carrying, returning, and handover are provider-owned stages of one user outcome.
Likewise, external search, evidence retrieval, evaluation, and natural
explanation are one `fetch_and_deliver_information` Goal. Weather is in this
variant, while the Planner still selects the exact `chromie.weather.lookup`
Capability rather than a generic hidden router.

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

- `soridormi.fetch_and_deliver_object` when Soridormi advertises complete
  physical resource acquisition and handover;
- `chromie.weather.lookup` for its exact structured weather scope;
- `chromie.external_information.retrieve` for grounded places, restaurants,
  recommendations, news, how-to research, and general external information;
- another future exact provider capability whose declared scope covers the
  complete responsibility.

These examples are capability contracts, not Host routing rules.

## Soridormi named-skill contract

Soridormi should advertise one generic named skill rather than one skill per
object type:

```json
{
  "skill_id": "fetch_and_deliver_object",
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
      "object": {
        "type": "object",
        "properties": {
          "description": {"type": "string", "minLength": 1},
          "quantity": {"type": "string"},
          "attributes": {"type": "object"}
        },
        "required": ["description"],
        "additionalProperties": false
      },
      "source": {
        "type": "object",
        "properties": {
          "status": {
            "type": "string",
            "enum": ["known", "provider_resolved"]
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
    "required": ["object", "source", "recipient"],
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
      "delivery": "physical_handover",
      "completion_requires": [
        "resource_acquired",
        "resource_delivered"
      ]
    },
    "resource_contract": {
      "result_field": "resource_outcome",
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
  "skill_id": "fetch_and_deliver_object",
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
