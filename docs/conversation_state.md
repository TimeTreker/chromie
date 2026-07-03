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
"did it finish?", and "continue". The Router model should propose whether a new
input creates a new task, continues a task, modifies a task, closes a task, or
is side conversation. The host task manager owns the final task write and safety
state.

## Stored state

The host store can retain bounded representations of:

- recent user and assistant turns;
- active interaction metadata;
- pending task hints;
- task contexts for open or recently completed user goals;
- session working memory for the current task or topic;
- follow-up context;
- the current conversation identifier and timestamps.

Limits are enforced for turn count, text length, context size, pending tasks,
and idle age. Older content is trimmed rather than allowed to grow without
bound.

The state is intended to improve short conversational continuity. It should not
be treated as authoritative robot state, a durable user profile, or a database
of completed side effects.

The Orchestrator exposes a compact `session_memory` object to Router and Agent
prompts. It summarizes the current task, active pending tasks, extracted memory
entries, a compact `memory_summary`, and the current forgetting policy. This is
the prompt-facing working memory for the current session, not a permanent
memory store.
The Router can hand complex requests to `deepthinking_agent`, which uses this
same bounded memory to split tasks, plan, debug, and produce unified robot
skill tasks without treating memory as authorization.
Deep-thinking prompts should consume extracted task context, claims, entities,
constraints, pending questions, and pending-task summaries rather than
injecting raw conversation transcript turns. The next memory architecture is
defined in [`MEMORY_EXTRACTION.md`](MEMORY_EXTRACTION.md): raw turns are
evidence/debug data, while model-facing memory should be compact extracted
meaning selected by a prompt builder. The first deterministic slice is
implemented for session/task memory, Router prompt sanitization, direct
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

When a request routes to `memory`, `memory_agent` emits a refined
`extracted_memory` update. The host records that entry in process-local
`session_memory.memory_summary` and `session_memory.extracted_memory`; the
legacy raw `user_statement` remains compatibility evidence only.
Structured updates with the same `scope`, `kind`, and `key` replace the prior
entry, which lets explicit corrections revise prompt memory without stacking
stale statements.

This is separate from the durable mind and experience layer documented in
[`chromie_mind.md`](chromie_mind.md). Session memory tracks the current
conversation; the mind profile carries owner-approved principles and long-term
goals, and the experience journal records outcomes for human-reviewed tuning.

## Boundaries and reset behavior

Configured reset phrases clear the active conversational context. New-topic
starters and idle thresholds can cause a fresh conversation boundary. Follow-up
phrases help preserve context for short dependent questions.

Operational interruption does not erase the entire conversation by default,
but active interaction and pending execution metadata must be updated so an
interrupted action is not later represented as completed.

Chromie starts a new conversation when:

- the user says an explicit reset phrase such as `new session`, `start over`,
  `forget that`, `新的会话`, or `换个话题`;
- the hard idle timeout expires while any context exists;
- the soft idle timeout expires and the next utterance looks like a new topic,
  as long as no active task is still pending;
- the Orchestrator process restarts, because this memory is process-local.

Task context is closed or forgotten when:

- the conversation boundary resets;
- the Router or user explicitly closes/cancels the task;
- the Skill Runtime reports the associated request IDs as completed, failed,
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
ORCH_CONVERSATION_IDLE_TIMEOUT_SEC=300
ORCH_CONVERSATION_HARD_IDLE_TIMEOUT_SEC=1800
ORCH_CONVERSATION_RESET_PHRASES=
ORCH_CONVERSATION_NEW_TOPIC_STARTERS=
ORCH_CONVERSATION_FOLLOWUP_PHRASES=
ORCH_CONVERSATION_COMPLETED_TASK_RETENTION_SEC=180
ORCH_ENABLE_TASK_CONTEXT_STORE=0
ORCH_TASK_CONTEXT_STORE_PATH=.chromie/conversation/task_contexts.json
```

Legacy `ORCH_CONTEXT_*` aliases remain accepted for compatibility. Use the
current names in new deployments. Exact defaults and precedence are documented
in [`CONFIGURATION.md`](CONFIGURATION.md).

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
