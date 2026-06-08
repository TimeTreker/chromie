# Chromie Agent

`chromie-agent` is a CPU-only multi-agent runtime for Chromie.

It receives a `RouteDecision` from `chromie-router`, runs one or more specialized agents, and returns a unified `AgentResult` for the host orchestrator to execute.

The agent service does **not** talk to ASR or TTS directly. The host orchestrator remains the only component that calls ASR, TTS, playback, and hardware execution.

## Responsibilities

- Convert a route decision into a speech/action plan.
- Host multiple specialized agents in one small Docker service.
- Keep model/environment compatibility separate from ASR/TTS.
- Return JSON only; do not touch microphone, speakers, or robot hardware directly.

## Agents included

- `conversation_agent`: short spoken chat responses.
- `speaker_agent`: normalizes wording, brevity, and speech style.
- `robot_pose_controller_agent`: head/body/gesture pose plans.
- `motion_planner_agent`: simple high-level movement plans.
- `safety_agent`: validates and clamps robot actions.
- `tool_agent`: returns tool actions for a future executor.
- `memory_agent`: returns memory updates/actions.
- `vision_agent`: placeholder for future vision requests.

## API

### `GET /health`

Returns service status and available agents.

### `GET /agents`

Lists known agents.

### `POST /run`

Input:

```json
{
  "sid": "abc123",
  "text": "转过来看着我",
  "route_decision": {
    "route": "robot_action",
    "agents": ["robot_pose_controller_agent", "safety_agent", "speaker_agent"],
    "intent": "look_at_user",
    "confidence": 0.94,
    "language": "zh-CN"
  },
  "context": {
    "robot_state": {"is_moving": false},
    "user_state": {"distance_m": 1.2}
  }
}
```

Output:

```json
{
  "status": "ok",
  "speak_immediate": [
    {"text": "好的，我看着你。", "style": "brief", "priority": "normal", "interruptible": true}
  ],
  "actions": [
    {
      "target": "robot_pose_controller",
      "type": "head.look_at_user",
      "params": {"duration_ms": 3000},
      "blocking": false
    }
  ],
  "speak_after": [],
  "memory_updates": []
}
```

### TaskGraph endpoints

- `POST /task-graphs/validate`: validate a graph against the active capability registry.
- `POST /task-graphs/dry-run`: simulate a validated graph without calling hardware or MCP tools.
- `GET /task-graphs/{graph_id}/trace`: return the most recent in-memory dry-run trace for a graph.

These endpoints are the first production-facing slice of
[M4 - TaskGraph production integration](../ROADMAP.md). Real tool execution
remains behind the transport-neutral `ToolInvoker` boundary.

### External capabilities

Set `AGENT_CAPABILITY_MANIFESTS` to a comma-separated list of JSON files or
directories mounted inside the Agent container. The root Compose file mounts
`./capabilities` read-only at `/app/capabilities`.

Configured manifests are loaded at startup. Missing, malformed, or duplicate
capabilities stop startup so the active registry cannot silently diverge from
deployment configuration.

### TaskGraph planning

Set `AGENT_ENABLE_TASK_GRAPH_PLANNING=1` to let `tool` routes ask the configured
LLM for a structured plan. The Agent replaces model-provided graph identity,
marks the graph as LLM-authored, validates it against the active capability
registry, and returns it in `AgentResult.task_graphs`.

Planning does not execute tools. Invalid model output falls back to the existing
single `tool_executor` action path.

The MCP Streamable HTTP adapter is available behind the async `ToolInvoker`
boundary. It derives endpoints from loaded manifests and enforces side-effect,
confirmation, safety-monitor, and safety-control authorization before making a
remote call. Automatic graph execution is still disabled.

## Run locally

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8092
```

## Docker

```bash
docker build -t chromie-agent ./agent
docker run --rm -p 8092:8092 \
  -e AGENT_OLLAMA_URL=http://host.docker.internal:11434 \
  chromie-agent
```

## Compose

The service is already integrated into the root `docker-compose.yml`. Use the root startup and generated runtime configuration:

```bash
./scripts/start_services.sh
```

## Notes

- `speaker_agent` decides wording only. It does not play audio.
- Real hardware execution should stay in the host orchestrator or a host hardware daemon.
- The service can work without Ollama. It will fall back to deterministic short replies.
- Model and timeout defaults should normally come from the selected hardware profile, not component-local hardcoded values.
