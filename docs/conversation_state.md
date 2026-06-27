# Conversation State

## Status

Implemented, process-local, bounded, and covered by automated tests. It is not a
durable memory service and does not persist across Orchestrator restart.

## Identity model

Chromie uses two related identifiers:

- `sid`: a per-utterance/session-turn identifier used for tracing requests;
- `conversation_id`: a longer-lived identifier shared across related turns.

A new SID does not automatically start a new conversation. The store keeps the
conversation identifier until a reset phrase, configured topic boundary, hard
idle expiry, or process restart.

## Stored state

The host store can retain bounded representations of:

- recent user and assistant turns;
- active interaction metadata;
- pending task hints;
- session working memory for the current task;
- follow-up context;
- the current conversation identifier and timestamps.

Limits are enforced for turn count, text length, context size, pending tasks,
and idle age. Older content is trimmed rather than allowed to grow without
bound.

The state is intended to improve short conversational continuity. It should not
be treated as authoritative robot state, a durable user profile, or a database
of completed side effects.

The Orchestrator exposes a compact `session_memory` object to Router and Agent
prompts. It summarizes the current task, recent user and assistant turns, active
pending tasks, and the current forgetting policy. This is the prompt-facing
working memory for the current session, not a permanent memory store.
The Router can hand complex requests to `deepthinking_agent`, which uses this
same bounded memory to split tasks, plan, debug, and produce a final spoken
answer without treating memory as authorization.

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

Task context is forgotten when:

- the conversation boundary resets;
- the Skill Runtime reports the associated request IDs as completed, failed,
  cancelled, or expired, and the completed-task retention window elapses;
- pending-task capacity trims older entries.

Recent completed tasks are retained briefly so follow-up questions such as
"did it finish?" can still be answered, then pruned from prompt context.

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
```

Legacy `ORCH_CONTEXT_*` aliases remain accepted for compatibility. Use the
current names in new deployments. Exact defaults and precedence are documented
in [`CONFIGURATION.md`](CONFIGURATION.md).

## Privacy and durability

The default state lives only in memory, which reduces accidental long-term
retention but does not make the content non-sensitive. Logs, optional audio
recordings, acceptance artifacts, and external service logs may still contain
user text or voice data.

Before adding durable memory:

- define explicit user consent and deletion behavior;
- separate conversational hints from verified system state;
- encrypt and scope stored data;
- avoid allowing model-written memory to authorize future side effects;
- add migration, retention, and redaction tests.
