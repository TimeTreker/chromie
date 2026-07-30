# Security and Safety Policy

## Supported versions

The repository is an active development snapshot with no declared release
version. Security and safety fixes target the latest `main` revision. Any
future supported-version policy must be added explicitly rather than inferred
from the current source tree.

## Reporting a vulnerability

Do not publish exploitable security issues, execution tokens, unsafe robot
procedures, or private device details in a public issue. Use GitHub private
vulnerability reporting when it is enabled for the repository. If it is not
available, contact the maintainer privately through the repository owner’s
GitHub profile and provide only the minimum reproduction material needed.

Include:

- affected revision and deployment mode;
- whether the issue is remote, local, simulator-only, or hardware-affecting;
- required feature gates and privileges;
- impact and a safe reproduction procedure;
- logs with secrets and personal data removed.

## High-risk areas

- guarded TaskGraph bearer-token handling;
- capability-manifest substitution and remote MCP endpoints;
- confirmation grants and replay resistance;
- interruption, cancellation, stop, and emergency fallback;
- audio files, speaker profiles, and local recordings;
- Docker/socket/device permissions;
- any path that could convert model output into physical motion.

## Local runtime network boundary

The maintained Docker Compose profile is a single-host development and
qualification profile. Its host-published services are reachable only through
IPv4 loopback:

- ASR WebSocket: `127.0.0.1:9001`;
- maintained TTS WebSocket: `127.0.0.1:5000`;
- optional local TTS evaluation endpoints: `127.0.0.1:5001` and
  `127.0.0.1:5002`;
- Ollama HTTP: `127.0.0.1:11434`;
- Agent HTTP: `127.0.0.1:8092`.

No maintained Chromie service is intentionally published to the LAN. A remote
or multi-host deployment requires a separate reviewed profile with explicit
authentication, transport protection, endpoint authorization, and deployment
documentation; changing a local port to `0.0.0.0` is not such a design.

Service processes still listen on `0.0.0.0` *inside their containers*. That is
required for Docker bridge-network traffic and is distinct from the host-side
publication address. Agent-to-LLM and Agent self-catalog traffic continues to
use Docker service names, while the host Orchestrator uses `127.0.0.1`.

`scripts/check_local_runtime_exposure.py` rejects wildcard publications and
host networking. The supported service launcher audits Docker Compose's fully
resolved configuration before starting containers, so local override files
cannot silently broaden the host boundary.

## Safety boundary

Chromie must not expose raw motor, joint, torque, or actuator commands to the
LLM. Physical execution belongs behind Soridormi’s named, schema-validated
skills and its own safety/commissioning boundary. The host hardware daemon is a
legacy mock compatibility service and must not be treated as production robot
safety infrastructure.

## Secret handling

- Do not commit `AGENT_TASK_GRAPH_EXECUTION_TOKEN`.
- Do not publish `.env.local`, `.env.runtime`, private model credentials, raw
  acceptance recordings, JSONL speech events, or unredacted evidence archives.
- Treat MCP endpoints as privileged when they expose side effects.
- Rotate a token immediately if it appears in logs, shell history, screenshots,
  or issue content.

## Physical testing

Run physical tests only with a safety operator, a verified stop path, bounded
workspace, and Soridormi’s documented recovery procedure. Simulator evidence
must never be presented as hardware evidence.
