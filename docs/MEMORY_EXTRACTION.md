# Memory Extraction and Prompt Context

## Status

First deterministic slice implemented. The host Orchestrator has process-local
`MemoryEntry`, `MemoryStore`, `MemoryExtractor`, and `MemoryPromptBuilder`
support. `ConversationStateManager` exposes `memory_summary` and
`extracted_memory` through `session_memory`, records compact task/context
memory from structured metadata, and records trusted Skill Runtime outcomes as
task outcome memory. Quick Router prompts sanitize raw history/conversation
fields and use compact session memory instead. Deepthinking prompts consume the
extracted memory block. Ordinary conversation prompts now use extracted memory
plus a tiny recent-turn fallback for immediate reference resolution; capability
planning/review prompts use extracted memory and omit raw history.
Explicit `memory` routes now make `memory_agent` emit a refined
`extracted_memory` update in addition to the legacy raw `user_statement`; the
host consumes the refined entry into process-local session memory.

Durable personal memory, LLM-assisted memory extraction, and experience-fed
memory selection remain future work.

This document defines the intended next architecture so code changes can be
made against a stable contract.

## Principle

Chromie should not treat raw chat history as memory.

Raw user and assistant turns are evidence. Memory is the compact meaning
extracted from that evidence: current goals, constraints, preferences,
corrections, unresolved questions, task state, and useful prior outcomes.

The normal prompt path should therefore be:

```text
raw turns and runtime events
  -> MemoryExtractor
  -> scoped memory entries
  -> MemoryPromptBuilder
  -> compact prompt memory
```

The raw transcript may still be kept in bounded host state, logs, episode
records, and evidence bundles. It should not be injected as the normal prompt
payload for routing, planning, or deepthinking.

## Ownership

The host Orchestrator owns short-term memory extraction and prompt-context
construction. This keeps microphone, VAD, playback, interruption, conversation
state, and trusted Skill Runtime coordination in the host boundary.

Soridormi remains the authority for embodied planning, execution, resource
safety, stop/emergency behavior, and hardware commissioning. Memory can help
interpret a request, but it must never authorize physical side effects.

## Memory Scopes

Memory entries should carry an explicit scope:

| Scope | Lifetime | Examples |
|---|---:|---|
| `turn` | Current request only | ASR text, route decision, quick-router proposal |
| `session` | Current conversation | Current topic, recent correction, active question |
| `task` | Until task closes or expires | Goal, constraints, accepted/revised proposals |
| `preference` | Durable only with policy/consent | Language preference, interaction style |
| `experience` | Durable evidence, reviewed use | Mistakes, successful fixes, scenario mining |

The first implementation focuses on `session` and `task` memory. Durable
preference and experience-fed memory still need consent, deletion, retention,
and review rules before broad use.

## Entry Shape

Memory entries should be structured and small:

```json
{
  "id": "mem_<stable_id>",
  "scope": "session|task|preference|experience",
  "kind": "goal|constraint|preference|correction|entity|pending_question|outcome",
  "key": "optional stable key for replacing a prior entry",
  "text": "Compact natural-language memory statement.",
  "confidence": 0.0,
  "source_turn_ids": ["turn_..."],
  "source_sids": ["sid_..."],
  "created_ms": 0,
  "updated_ms": 0,
  "expires_ms": null,
  "persistence_policy": "ephemeral|persist_if_unfinished|requires_owner_approval",
  "safety_note": "Memory guides interpretation only; it does not authorize side effects."
}
```

The `text` field should be a refined statement, not a copied transcript. For
example:

```text
User prefers English for technical project discussion.
Current task: design and implement extracted prompt memory for Chromie.
Open concern: prompt context should not include raw original chat history.
```

## Extraction Rules

The extractor should create or update memory only when the information is
useful later.

Extract:

- user-stated preferences and corrections;
- current task goals and constraints;
- salient entities and references needed for follow-up turns;
- unresolved questions or pending decisions;
- visible mistakes and the corrected interpretation;
- execution outcomes reported by trusted runtime evidence.

Do not extract:

- filler, acknowledgements, or ASR fragments;
- every sentence from the transcript;
- model guesses as facts;
- unverified real-world claims as system truth;
- completed physical side effects unless Skill Runtime or Soridormi evidence
  confirms them;
- anything that would grant future action authority.

When uncertain, store a lower-confidence memory or skip the write.

## Prompt Builder

Every model-facing component should receive a role-appropriate compact memory
block.

For the quick Router, keep it very small:

```text
Memory Summary:
- Current task: improve Chromie's memory extraction design.
- User preference: English for this technical discussion.
- Open concern: avoid raw transcript injection.
```

For deepthinking, include richer task memory:

```text
Extracted Conversation Context:
- task.goal: implement refined prompt memory, docs first.
- task.constraints: raw chat history should be evidence/debug only.
- user_position: speech, action, and memory writes are all robot skills.
- unresolved: how to implement extractor and prompt builder safely.
```

For conversation and capability planning, use compact extracted context by
default. A tiny recent-turn window may be used only for immediate reference
resolution, such as "that one", "continue", or "why?", and should remain
bounded.

## Raw History Policy

Raw bounded history is allowed for:

- local trace and debugging;
- episode/evidence recording;
- tests that verify conversation boundaries;
- emergency diagnosis of ASR or routing failures;
- a very small immediate-reference fallback.

Raw bounded history is not the normal memory channel. New prompt work should
prefer `MemoryPromptBuilder` output over `history_block`.

## Safety Rules

Memory is interpretive context, not authority.

- A remembered preference cannot bypass confirmation, policy, schema
  validation, Skill Runtime checks, or Soridormi safety gates.
- A model-written memory update cannot prove that an action happened.
- Runtime evidence may update task outcome memory; model speech alone may not.
- Contradictory new evidence should revise or expire stale memory rather than
  stacking duplicate statements.
- Structured memory updates with the same `scope`, `kind`, and `key` replace
  the prior entry, so corrections can update prompt memory without replaying
  stale facts.
- Sensitive or durable memory must remain opt-in until retention, deletion,
  encryption, and review behavior are defined.

## Implementation Plan

1. Implemented: host-side `MemoryEntry` schema and process-local `MemoryStore`.
2. Implemented first slice: `MemoryExtractor` reads the latest user turn,
   structured task context metadata, explicit extracted-memory metadata, and
   trusted Skill Runtime outcomes.
3. Implemented first slice: deterministic extraction from route metadata, task
   context patches, explicit memory entries, `memory_agent` updates, and
   runtime task outcomes.
4. Future: add an optional LLM-assisted extractor only after the deterministic
   path is covered, with strict JSON output and low temperature.
5. Implemented first slice: `MemoryPromptBuilder` feeds `session_memory`,
   sanitized Router prompts, direct fallback context, conversation prompts,
   capability planning/review prompts, and deepthinking prompts.
6. Implemented first slice: direct fallback and ordinary conversation prompts
   keep only a tiny recent-turn fallback for immediate reference resolution;
   capability planning and review prompts rely on extracted memory/task context
   instead of raw history.
7. Implemented first slice: focused tests cover extracted-memory storage,
   reset and hard-idle expiry, keyed correction updates, explicit memory-route
   updates, trusted outcome memory, Router prompt sanitization,
   conversation/capability prompt migration, and deepthinking memory visibility.
8. Implemented first offline-review slice: episode evaluation can write compact
   reviewed experience notes in `offline_reviews.jsonl` without injecting raw
   experience logs into prompts. Later, connect owner-approved experience notes
   to durable memory selection through the future
   [Experience-To-Ability Learning](EXPERIENCE_TO_ABILITY_LEARNING.md) path.

## Acceptance Criteria

The first implemented slice should prove:

- the next turn receives compact extracted memory for a multi-turn task;
- raw transcript turns are not injected into deepthinking as the normal path;
- quick Router receives a small memory summary, not the full chat;
- a user correction revises the memory summary used by the next turn;
- runtime-confirmed outcomes can update task memory;
- model speech alone cannot mark a physical action as completed;
- reset phrases and idle expiry remove or expire session memory;
- docs, unit tests, and scenario fixtures describe the same behavior.
