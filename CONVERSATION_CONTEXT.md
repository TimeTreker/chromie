# Chromie Conversation Context

This update adds short-term conversation continuity to Chromie.

## Problem

Previously, every valid VAD utterance became an independent `sid`. That is good for timing, interruption, and logging, but it means follow-up questions lose context.

Example:

```text
User: check the weather
Chromie: let me check
User: when will you give me the answer?
```

Without short-term context, the second user turn is treated as isolated text.

## New model

```text
conversation_id = a continuous conversation scope
sid             = one VAD utterance / voice turn
task_id         = future long-running tool or robot task
```

The host orchestrator keeps recent turns and pending-task hints in memory and sends them to the agent in `context` and `history`.

## Conversation splitting

A new conversation starts when:

1. The user explicitly resets the topic, for example `new topic`, `start over`, `换个话题`, or `重新开始`.
2. The conversation is idle longer than `ORCH_CONVERSATION_HARD_IDLE_TIMEOUT_SEC`.
3. The conversation is idle longer than `ORCH_CONVERSATION_IDLE_TIMEOUT_SEC` and the next utterance looks like a new topic.

The current conversation is kept when:

1. There is an active pending task.
2. The user uses follow-up language, for example `when`, `what about it`, `result`, `那个`, `刚才`, or `什么时候`.

## Environment variables

```bash
ORCH_ENABLE_CONVERSATION_STATE=1
ORCH_CONVERSATION_ID=local_default
ORCH_CONVERSATION_MAX_TURNS=12
ORCH_CONVERSATION_IDLE_TIMEOUT_SEC=180
ORCH_CONVERSATION_HARD_IDLE_TIMEOUT_SEC=900
ORCH_CONVERSATION_TURN_MAX_TEXT_CHARS=260
ORCH_CONVERSATION_MAX_CONTEXT_CHARS=2200
ORCH_CONVERSATION_MAX_PENDING_TASKS=8
```

Optional phrase overrides use `|` as separator:

```bash
ORCH_CONVERSATION_RESET_PHRASES=new topic|start over|换个话题|重新开始
ORCH_CONVERSATION_FOLLOWUP_PHRASES=when|answer|result|what about|刚才|结果|什么时候
```

## Files changed

```text
orchestrator/runtime/conversation_state.py
orchestrator/clients/agent_client.py
agent/app/agents/conversation.py
scripts/apply_conversation_context_patch.py
.env.common
.env.local.example
```

`orchestrator/orchestrator.py` is patched by `scripts/apply_conversation_context_patch.py` because it is safer than shipping a full orchestrator replacement while the file is changing quickly.

## Apply

```bash
cd /home/chromie/github/chromie
unzip /path/to/chromie_conversation_context_update.zip
rsync -av chromie_conversation_context_update/ ./
python scripts/apply_conversation_context_patch.py
chmod +x scripts/*.sh scripts/*.py
./scripts/build_runtime_env.sh
```

Rebuild/restart the agent service because `agent/app/agents/conversation.py` changed:

```bash
docker compose --env-file .env.runtime build chromie-agent
docker compose --env-file .env.runtime up -d --force-recreate chromie-agent
```

Then restart the host orchestrator:

```bash
./scripts/start_orchestrator.sh
```

## Validate

Host logs should show:

```text
Conversation state: enabled=True conversation_id=local_default ...
context_snapshot: conversation_id=local_default history_turns=... pending_tasks=...
```

Agent logs should show:

```text
conversation_agent_start ... history_turns=... pending_tasks=... conversation_id=...
conversation_agent_llm_start ... history_turns=... pending_tasks=...
```

Test:

```text
You: check the weather
Chromie: let me check
You: when will you give me the answer?
Expected: Chromie refers to the previous weather request instead of treating the second turn as isolated.
```
