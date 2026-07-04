# Dream Broadly, Execute Honestly

This document records the routing and planning contract for human-like robot
abilities that Chromie can understand before they are executable.

## Principle

Chromie's language stages should understand the user's intent broadly, like a
human listener. Understanding must not be limited to the current executable
skill catalog.

Execution is different. Any task that can affect speech output, tools, memory,
the simulator, or a robot must be honest about the current catalog and runtime
authority.

```text
Understand broadly -> propose honestly -> execute only catalog-backed skills
```

The Router and deepthinking Agent may reason about human-like desired
abilities, such as blinking, picking up an object, following a user, opening a
door, or turning on a light. They must not claim those abilities are executable
unless the current executable skill catalog supplies an exact skill and the
trusted runtime later validates it.

## Two Catalogs

Chromie uses two related but different ability surfaces.

| Surface | Purpose | Execution authority |
|---|---|---|
| Ability ontology | Broad human-like ability IDs Chromie can understand, discuss, and learn toward. | No direct execution authority. |
| Executable skill catalog | Exact `skill_id` entries currently available from Chromie, Agent, and Soridormi providers. | Can be proposed for runtime validation and execution. |

The ability ontology may contain `known_missing` or `planned` entries. The
executable skill catalog contains only concrete runtime skills such as
`chromie.speak` or a Soridormi named skill that the provider declares.

## Status Model

Ability ontology entries use these meanings:

| Status | Meaning |
|---|---|
| `available` | Fulfilled by the current host runtime. |
| `sim_only` | Fulfilled only in the simulator-safe path. |
| `hardware_only` | Reserved for a commissioned hardware implementation. |
| `stub` | Placeholder entry without a reviewed roadmap decision. |
| `planned` | A reviewed roadmap ability, not executable yet. |
| `known_missing` | Chromie understands the ability, but no trusted implementation exists now. |
| `forbidden` | The ability should not be implemented or offered for safety/policy reasons. |
| `disabled` | An implementation exists but is disabled by runtime flags or provider state. |

Only `available`, `sim_only`, and `hardware_only` can become executable, and
only when their implementation is not a stub and a matching runtime skill is
present.

## Router Contract

The quick Router receives the common compact skill catalog. It should:

- infer the user's desired ability from meaning, context, memory, and catalog
  descriptions;
- use `actions[]` only for exact common catalog skill IDs;
- never put missing or planned abilities in `actions[]`;
- when useful, put understood but non-executable abilities in
  `metadata.desired_abilities`;
- delegate to `deep_thought` or clarify when the desired ability is not safely
  representable by common executable skills.

Example:

```json
{
  "route": "deep_thought",
  "intent": "deep_thought_missing_common_skill",
  "confidence": 0.72,
  "speak_first": "Give me a moment to check that.",
  "metadata": {
    "desired_abilities": [
      {
        "ability_id": "manipulation.pick_up_object",
        "intent": "pick up the bottle",
        "status": "missing_ability",
        "confidence": 0.93,
        "reason": "No executable grasping skill is in the common catalog."
      }
    ]
  }
}
```

This is a proposal and learning signal only. It cannot execute.

## Deepthinking Contract

Deepthinking receives richer context and the fuller executable catalog. It
should:

- understand desired abilities without forcing them into current skills;
- emit `tasks[]` only for executable catalog skill IDs, including
  `chromie.speak`;
- emit `task_proposals[]` for understood desired abilities that cannot execute;
- speak honestly when the robot lacks the requested ability;
- revise or supersede quick-router proposals when later reasoning finds a
  mismatch.

Example:

```json
{
  "tasks": [
    {
      "skill_id": "chromie.speak",
      "args": {
        "text": "I understand you want me to pick up the bottle, but I do not have a trusted grasping ability yet.",
        "style": "brief",
        "priority": "normal"
      },
      "timing": "immediate",
      "timeout_ms": null,
      "cancellable": true,
      "requires_confirmation": null,
      "reason": "Explain the missing manipulation ability."
    }
  ],
  "task_proposals": [
    {
      "ability_id": "manipulation.pick_up_object",
      "intent": "pick up the bottle",
      "status": "missing_ability",
      "matched_skill_id": null,
      "confidence": 0.93,
      "reason": "No executable manipulation skill was supplied."
    }
  ],
  "quick_review": {
    "decision": "none",
    "reason": "",
    "superseded_task_ids": []
  },
  "reason": "The desired ability is understood but unavailable."
}
```

## Orchestrator Contract

The Orchestrator treats router and deepthinking outputs as proposals until a
final `InteractionResponse` contains committed speech or skills.

- `actions[]` and `tasks[]` can become committed only after Agent and Skill
  Runtime validation.
- `metadata.desired_abilities` and deepthinking `task_proposals[]` become
  shared `TaskProposal` ledger entries with `state=missing_ability`.
- Missing-ability proposals are never executable and are not forwarded to the
  Skill Runtime.
- Experience evaluation may mine these proposals into owner-review-only
  ability backlog items or future scenario candidates.

## Non-Goals

- Do not make Chromie claim it can execute all human abilities.
- Do not make lexical catalog search choose normal intent by itself.
- Do not auto-create Soridormi skills from missing-ability proposals.
- Do not bypass confirmation, preflight, provider validation, or safety gates.
