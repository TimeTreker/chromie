# Dream Broadly, Execute Honestly

This document records the interpretation and planning contract for human-like robot
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

The Goal Interpreter and deepthinking Agent may reason about human-like desired
abilities, such as blinking, picking up an object, following a user, opening a
door, or turning on a light. They must not claim those abilities are executable
unless the current executable capability catalog supplies an exact capability and the
trusted runtime later validates it.

## Two Catalogs

Chromie uses two related but different ability surfaces.

| Surface | Purpose | Execution authority |
|---|---|---|
| Ability ontology | Broad human-like ability IDs Chromie can understand, discuss, and learn toward. | No direct execution authority. |
| Executable capability catalog | Exact canonical `capability_id` entries currently available from Chromie, Agent, and Soridormi providers. | Can be proposed for runtime validation and execution. |

The ability ontology may contain `known_missing` or `planned` entries. The
executable capability catalog contains only concrete runtime capabilities such as
`chromie.speak` or a Soridormi named skill that the provider declares.

## Status Model

Ability ontology entries use these meanings:

| Status | Meaning |
|---|---|
| `available` | Fulfilled by a trusted Chromie-local implementation. |
| `stub` | Placeholder entry without a reviewed roadmap decision. |
| `planned` | A reviewed roadmap ability, not executable yet. |
| `known_missing` | Chromie understands the ability, but no trusted implementation exists now. |
| `forbidden` | The ability should not be implemented or offered for safety/policy reasons. |
| `disabled` | An implementation exists but is disabled by runtime flags or provider state. |

Only `available` ontology entries with a non-stub Chromie-local implementation
can execute through the static registry. Provider-backed embodied work requires
an exact skill from the live provider catalog; the ontology never infers
execution from simulator or hardware identity.

## Fast Goal Interpretation Contract

The quick Goal Interpreter receives the unlocked common compact capability catalog. It should:

- infer the user's desired ability from meaning, context, memory, and catalog
  descriptions;
- use `actions[]` only for exact unlocked common catalog skill IDs;
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
- revise or supersede quick-goal interpreter proposals when later reasoning finds a
  mismatch.

Example:

```json
{
  "tasks": [
    {
      "capability_id": "chromie.speak",
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
      "matched_capability_id": null,
      "confidence": 0.93,
      "reason": "No executable manipulation capability was supplied."
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

The Orchestrator does not maintain a second proposal ledger beside the canonical
Plan. Goal Interpretation supplies WHAT, the Planner authors HOW, static preflight
checks only the committed Capability requests the Host can validate before runtime,
and Capability Runtime / Evidence own execution truth.

- unavailable desired abilities remain Goal/Planner semantics; the Orchestrator does
  not invent executable substitutes or a parallel `TaskProposal` authority;
- `preflight_validation` is diagnostic metadata for committed Capability requests,
  not execution evidence and not a second Plan;
- missing or unavailable capabilities must remain explicit in canonical planning or
  terminal Evidence instead of being converted into executable work;
- Experience may summarize preflight/runtime failures for owner review, but it does
  not reconstruct semantic proposals from transcripts or compatibility metadata.

## Non-Goals

- Do not make Chromie claim it can execute all human abilities.
- Do not rank or filter capabilities from user-text lexical overlap; give the declared catalog to the responsible model.
- Do not auto-create Soridormi skills from missing-ability proposals.
- Do not bypass confirmation, preflight, provider validation, or safety gates.
