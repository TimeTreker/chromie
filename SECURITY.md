# Security and Safety Policy

## Supported versions

There is no published stable release in this repository snapshot. The tracked
`0.0.1` material is a blocked, unpublished candidate only. Security and safety fixes currently
target the latest `main` revision; a published prerelease must add an explicit
supported-version table here.

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
