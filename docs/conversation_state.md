# Conversation State

Chromie keeps short-term conversation continuity in the host Orchestrator.

## Model

```text
conversation_id = continuous conversation scope
sid             = one VAD utterance and voice turn
task_id         = optional long-running tool or robot task
```

The Orchestrator stores recent turns and pending-task hints in memory, then sends a snapshot to the Agent in `context` and `history`.

## Conversation Boundaries

A new conversation starts when:

- the user explicitly resets the topic;
- the hard idle timeout expires;
- the soft idle timeout expires and the next utterance looks like a new topic.

The current conversation is retained when there is an active pending task or the user uses follow-up language referring to an earlier turn.

## Configuration

Defaults live in `.env.common`; machine-specific overrides belong in `.env.local`.

```env
ORCH_ENABLE_CONVERSATION_STATE=1
ORCH_CONVERSATION_ID=local_default
ORCH_CONVERSATION_MAX_TURNS=12
ORCH_CONVERSATION_IDLE_TIMEOUT_SEC=180
ORCH_CONVERSATION_HARD_IDLE_TIMEOUT_SEC=900
ORCH_CONVERSATION_TURN_MAX_TEXT_CHARS=260
ORCH_CONVERSATION_MAX_CONTEXT_CHARS=2200
ORCH_CONVERSATION_MAX_PENDING_TASKS=8
```

Optional phrase lists use `|` as the separator:

```env
ORCH_CONVERSATION_RESET_PHRASES=new topic|start over|换个话题|重新开始
ORCH_CONVERSATION_FOLLOWUP_PHRASES=when|answer|result|what about|刚才|结果|什么时候
```

## Implementation

- `orchestrator/runtime/conversation_state.py` owns boundaries, turn history, and pending-task state.
- `orchestrator/orchestrator.py` records turns and builds context snapshots.
- `orchestrator/clients/agent_client.py` sends context and history to the Agent.
- `agent/app/agents/conversation.py` incorporates the context into conversation prompts.

Useful logs include `conversation_boundary`, `context_snapshot`, and Agent `history_turns` / `pending_tasks` fields.
