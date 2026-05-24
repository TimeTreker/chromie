# Apply Chromie Conversation Context Update

This package is based on the current GitHub `main` structure:

- `AgentRunRequest`/`AgentRequest` already has `context` and `history` fields.
- The current conversation agent only uses the current text + intent, so it is single-turn.
- The orchestrator already has a `build_context()` hook, so this update extends it with `conversation_id`, `history`, and pending tasks.

Apply:

```bash
cd /home/chromie/github/chromie
unzip /path/to/chromie_conversation_context_update.zip
rsync -av chromie_conversation_context_update/ ./
python scripts/apply_conversation_context_patch.py
chmod +x scripts/*.sh scripts/*.py
./scripts/build_runtime_env.sh
```

Restart agent and orchestrator:

```bash
docker compose --env-file .env.runtime build chromie-agent
docker compose --env-file .env.runtime up -d --force-recreate chromie-agent
./scripts/start_orchestrator.sh
```

Rollback basics:

```bash
git checkout -- orchestrator/orchestrator.py orchestrator/clients/agent_client.py agent/app/agents/conversation.py .env.common .env.local.example
rm -f orchestrator/runtime/conversation_state.py scripts/apply_conversation_context_patch.py CONVERSATION_CONTEXT.md README_APPLY.md
```
