# Chromie Shared Packages

Dependency-light contracts and runtime primitives shared by Chromie processes.

Use this package to keep JSON contracts consistent between:

- host `chromie-orchestrator`
- Docker `chromie-router`
- Docker `chromie-agent`
- host `chromie-hardware-daemon`

The directory currently provides:

- `chromie_contracts`: Pydantic control-plane schemas;
- `chromie_runtime`: asyncio scheduling primitives used by Agent TaskGraph and
  host Skill Runtime.

Each process owns its own `ResourceArbiter` instance. This is not a distributed
lock; Soridormi remains responsible for cross-process robot exclusivity.

## Install locally during development

```bash
cd shared
pip install -e .
```

Then import:

```python
from chromie_contracts.route import RouteDecision
from chromie_contracts.agent import AgentResult
from chromie_contracts.action import ActionCommand
from chromie_runtime import ResourceArbiter
```
