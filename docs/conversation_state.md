# Conversation State

## Status

Implemented, bounded, and covered by automated tests. It is process-local by
default. An optional local task-context store can persist unfinished compact
task contexts across Orchestrator restart, but it is not a general durable
memory service.

## Vocabulary and identity model

Chromie uses related identifiers with different lifetimes:

- `sid`: a per-utterance session identifier used for tracing one VAD/ASR
  input and the immediate robot response work;
- `turn`: one user utterance or one assistant reply inside a conversation;
- `conversation_id`: a longer-lived dialogue identifier shared across related
  turns;
- `task_id`: a user goal/work item that may span many sessions and turns;
- `task_context`: the prompt-facing working memory for one task.

A new SID does not automatically start a new conversation. The store keeps the
conversation identifier until a reset phrase, configured topic boundary, hard
idle expiry, or process restart.

A new task is not the same thing as a new SID. One task can include many
sessions, for example a command followed by "quickly please", "not that far",
"did it finish?", and "continue". The Goal Interpreter model should propose whether a new
input creates a new task, continues a task, modifies a task, closes a task, or
is side conversation. The host task manager owns the final task write and safety
state.

## Stored state

The host store can retain bounded representations of:

- recent user and assistant turns;
- active interaction metadata;
- pending task hints;
- task contexts for open or recently completed user goals;
- bounded scoped discourse referents and an LLM-authored focus stack;
- a provenance-only index of verified prior tool results;
- session working memory for the current task or topic;
- follow-up context;
- the current conversation identifier and timestamps.

Limits are enforced for turn count, text length, context size, pending tasks,
and idle age. Older content is trimmed rather than allowed to grow without
bound.

The state is intended to improve short conversational continuity. It should not
be treated as authoritative robot state, a durable user profile, or a database
of completed side effects.

The Orchestrator exposes a compact `session_memory` object to Goal Interpretation and downstream Agent
prompts. It summarizes the current task, active pending tasks, extracted memory
entries, a compact `memory_summary`, and the current forgetting policy. This is
the prompt-facing working memory for the current session, not a permanent
memory store.

Conversation state does not expose one global `current_location`. Multiple
task-, Goal-, and conversation-scoped referents can coexist, so a navigation
destination, a Chongqing weather task, and a Neixiang place discussion do not
overwrite one another. Goal Association resolves expressions such as `那边`
from current user meaning, scoped referents/focus, active Goal bindings, and
recent dialogue. The Host only validates and stores the typed model result.
Verified tool evidence is not allowed to decide reference meaning.

Operational reset/follow-up phrase settings affect only whether bounded context is
retained across an idle boundary. They never resolve a pronoun, choose a task, or
associate a Goal. Expressions such as “the last task I told you” are resolved by
Goal Association from active/recoverable Goals and dialogue semantics.

Prior tool results are reused only through the explicit read-only
`chromie.memory.retrieve_verified_tool_result` capability. Planners receive a
result-free index of exact original arguments and provenance; the capability
returns data only when the already-resolved Goal bindings match exactly and the
record is fresh enough. See
[`DISCOURSE_REFERENTS_AND_VERIFIED_MEMORY.md`](DISCOURSE_REFERENTS_AND_VERIFIED_MEMORY.md).
Goal Interpretation can hand complex requests to `deepthinking_agent`, which uses this
same bounded memory to split tasks, plan, debug, and produce unified robot
skill tasks without treating memory as authorization.
Deep-thinking prompts should consume extracted task context, claims, entities,
constraints, pending questions, and pending-task summaries rather than
injecting raw conversation transcript turns. The next memory architecture is
defined in [`MEMORY_EXTRACTION.md`](MEMORY_EXTRACTION.md): raw turns are
evidence/debug data, while model-facing memory should be compact extracted
meaning selected by a prompt builder. The first deterministic slice is
implemented for session/task memory, Goal Interpreter prompt sanitization, direct
fallback context, ordinary conversation prompts, capability planning/review
prompts, and deepthinking prompts.

Each task context should preserve the information that later sessions need:

- stable `task_id`, status, task type, and goal;
- task relation for the latest user turn (`new_task`, `continue_task`,
  `modify_task`, `close_task`, `side_conversation`, or `clarify_task`);
- important claims or facts extracted from user turns;
- salient entities, constraints, and unresolved questions;
- last meaningful user turn and last assistant response;
- related SIDs and timestamps;
- persistence policy for restart recovery.

Short ASR fragments such as "or" or "then, the" should not overwrite the latest
meaningful task context. They may remain in trace logs, but prompt-facing task
memory should privilege meaningful claims and goals over accidental fragments.
The same rule applies to ordinary chat history: bounded raw turns may be
retained for traceability, but they should not become the default memory block
for future prompts.

When a request routes to `memory`, Goal Interpretation must author a typed
`MemoryUpdateProposal` containing normalized session content, kind, optional
key, ephemeral persistence policy, and confidence. `memory_agent` validates and
applies that exact proposal; it does not infer memory kind or content from raw
user text, keywords, or regular expressions. A missing proposal produces a
clarification rather than a Host-authored guess. The Host records the resulting
`extracted_memory` entry in process-local `session_memory.memory_summary` and
`session_memory.extracted_memory`; the bounded `user_statement` entry remains
compatibility evidence derived from the same proposal. Structured updates with
the same `scope`, `kind`, and `key` replace the prior entry.

This is separate from the durable mind and experience layer documented in
[`chromie_mind.md`](chromie_mind.md). Session memory tracks the current
conversation; the mind profile carries owner-approved principles and long-term
goals, and the experience journal records outcomes for human-reviewed tuning.

## Boundaries and reset behavior

The Host does not infer reset, new-topic, or follow-up meaning from phrases.
Those turns reach the Cognitive Core with the bounded conversation and Goal
state. Automatic conversation boundaries remain mechanical.

Operational interruption does not erase the entire conversation by default,
but active interaction and pending execution metadata must be updated so an
interrupted action is not later represented as completed.

Chromie starts a new conversation when:

- the hard idle timeout expires while context exists and no active Goal or
  pending work remains;
- a typed, model-owned conversation-control path explicitly requests the
  boundary once such a path is enabled;
- the Orchestrator process restarts, because this memory is process-local.

Task context is closed or forgotten when:

- the conversation boundary resets;
- the Cognitive Core or user explicitly closes/cancels the task;
- the Trusted Capability Runtime reports the associated request IDs as completed, failed,
  cancelled, or expired, and the completed-task retention window elapses;
- pending-task capacity trims older entries.

Recent completed tasks are retained briefly so follow-up questions such as
"did it finish?" can still be answered, then pruned from prompt context.

If durable task memory is enabled, unfinished task contexts are saved locally
and restored as `recoverable` task contexts. Physical or robot-action tasks must
require fresh user confirmation after restart; Chromie must never resume body
motion blindly after power loss.

## Configuration

Preferred names:

```env
ORCH_ENABLE_CONVERSATION_STATE=1
ORCH_CONVERSATION_ID=
ORCH_CONVERSATION_MAX_TURNS=12
ORCH_CONVERSATION_TURN_MAX_TEXT_CHARS=1200
ORCH_CONVERSATION_MAX_CONTEXT_CHARS=6000
ORCH_CONVERSATION_MAX_PENDING_TASKS=8
ORCH_CONVERSATION_MAX_TOOL_EVIDENCE=8
ORCH_CONVERSATION_MAX_DISCOURSE_REFERENTS=24
ORCH_CONVERSATION_MAX_DISCOURSE_FOCUS=8
ORCH_CONVERSATION_IDLE_TIMEOUT_SEC=300
ORCH_CONVERSATION_HARD_IDLE_TIMEOUT_SEC=1800
ORCH_CONVERSATION_COMPLETED_TASK_RETENTION_SEC=180
ORCH_ENABLE_TASK_CONTEXT_STORE=0
ORCH_TASK_CONTEXT_STORE_PATH=.chromie/conversation/task_contexts.json
```


Conversation boundaries are deliberately non-semantic in the Host. It applies
the hard-idle timeout and typed control state; it does not use reset or follow-up
phrases, pronoun lists, or new-topic starters. Goal Association owns those
meanings. `ORCH_CONVERSATION_IDLE_TIMEOUT_SEC` remains a bounded conversation-state value but does not authorize phrase-based soft-idle splitting.

The former `ORCH_CONTEXT_*` aliases are removed. Exact maintained settings and defaults are documented in [`CONFIGURATION.md`](CONFIGURATION.md).

## Privacy and durability

The default state lives only in memory, which reduces accidental long-term
retention but does not make the content non-sensitive. Logs, optional audio
recordings, acceptance artifacts, and external service logs may still contain
user text or voice data.

Before expanding durable memory beyond compact unfinished task contexts:

- define explicit user consent and deletion behavior;
- separate conversational hints from verified system state;
- encrypt and scope stored data;
- avoid allowing model-written memory to authorize future side effects;
- add migration, retention, and redaction tests.
