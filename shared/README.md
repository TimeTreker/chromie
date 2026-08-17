# Chromie Shared Packages

`shared/` contains dependency-light contracts and process-local runtime
primitives used across Chromie's control plane.

## `chromie_contracts`

The contract package keeps JSON boundaries consistent between the host
Orchestrator, Goal Interpretation, Agent, compatibility hardware daemon, tests, and
acceptance tools. It includes:

- Goal/Core interpretation requests and typed `CognitiveWorkRequest` handoff contracts;
- agent requests, `AgentResult`, speech, memory, and compatibility actions;
- strict `InteractionResponse`, `InteractionSpeech`, `CapabilityRequest`,
  `CapabilityResult`, and `CapabilityTrace` contracts;
- deterministic `ReflexOutcome`, `CancellationDirective`, and
  `CancellationDispatchReceipt` contracts. Runtime request identity in cancellation
  receipts is always interaction-qualified (`interaction_id` + `request_id`); bare
  request-ID compatibility fields are not part of the canonical contract. Fixed
  reflex scopes remain separate from exact plan/fingerprint-bound goal cancellation,
  while both paths reconcile trusted receipts into canonical Goal state; dispatch,
  provider, and dedicated E-stop/safe-idle evidence remain separately represented;
- shared `TaskProposal`, `TaskProposalLedger`, and preflight-summary contracts
  for Goal Interpretation/Cognitive Core/Orchestrator proposal merge diagnostics;
- Goal, Goal Association, semantic task-operation, and active-goal contracts;
- immutable `CanonicalPlan`, goal-satisfaction, response-composition, and
  single-semantic-authority contracts;
- hardware action and robot-state contracts;
- conversation-state structures.

Interaction models use `extra="forbid"` and recursively reject known low-level
motor, joint, torque, actuator, and raw-control field names. This prevents a
model or adapter from smuggling low-level embodiment commands through metadata
or nested capability arguments.

Contract validation is necessary but not sufficient authorization. A valid
`CapabilityRequest` must still resolve through the trusted Capability Registry and pass
provider, confirmation, resource, timeout, and cancellation policy.

## `chromie_runtime`

The runtime package provides the shared asyncio `ResourceArbiter` used by:

- Agent TaskGraph execution;
- host Trusted Capability Runtime scheduling.

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
from chromie_contracts.interaction import InteractionResponse, CapabilityRequest
from chromie_contracts.core_interpretation import CognitiveWorkRequest
from chromie_runtime import ResourceArbiter
```

Run the repository test suite after changing a contract because compatibility,
serialization, API, Trusted Capability Runtime, and TaskGraph tests all depend on this
package:

```bash
./scripts/run_tests.sh
```

Cognitive truncation and integrity incident packages are defined in
[Cognitive Integrity Events](../docs/COGNITIVE_INTEGRITY_EVENTS.md).
