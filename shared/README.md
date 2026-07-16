# Chromie Shared Packages

`shared/` contains dependency-light contracts and process-local runtime
primitives used across Chromie's control plane.

## `chromie_contracts`

The contract package keeps JSON boundaries consistent between the host
Orchestrator, Router, Agent, compatibility hardware daemon, tests, and
acceptance tools. It includes:

- route requests and `RouteDecision`;
- agent requests, `AgentResult`, speech, memory, and compatibility actions;
- strict `InteractionResponse`, `InteractionSpeech`, `SkillRequest`,
  `SkillResult`, and `SkillTrace` contracts;
- shared `TaskProposal`, `TaskProposalLedger`, and preflight-summary contracts
  for Router/Agent/Orchestrator proposal merge diagnostics;
- Goal, Goal Association, semantic task-operation, and active-goal contracts;
- immutable `CanonicalPlan`, goal-satisfaction, response-composition, and
  single-semantic-authority contracts;
- hardware action and robot-state contracts;
- conversation-state structures.

Interaction models use `extra="forbid"` and recursively reject known low-level
motor, joint, torque, actuator, and raw-control field names. This prevents a
model or adapter from smuggling low-level embodiment commands through metadata
or nested skill arguments.

Contract validation is necessary but not sufficient authorization. A valid
`SkillRequest` must still resolve through the trusted Skill Registry and pass
provider, confirmation, resource, timeout, and cancellation policy.

## `chromie_runtime`

The runtime package provides the shared asyncio `ResourceArbiter` used by:

- Agent TaskGraph execution;
- host Skill Runtime scheduling.

It enforces bounded concurrency and named exclusive groups within one Python
process. Each process has its own arbiter. It is not a distributed lock and
cannot coordinate Agent and Orchestrator processes by itself. Cross-process
robot exclusivity remains Soridormi's responsibility.

## Development install

From the repository root:

```bash
pip install -e shared
```

Example imports:

```python
from chromie_contracts.interaction import InteractionResponse, SkillRequest
from chromie_contracts.route import RouteDecision
from chromie_runtime import ResourceArbiter
```

Run the repository test suite after changing a contract because compatibility,
serialization, API, Skill Runtime, and TaskGraph tests all depend on this
package:

```bash
./scripts/run_tests.sh
```
