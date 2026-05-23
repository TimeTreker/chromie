# Chromie Shared Contracts

Shared Pydantic schemas for Chromie control-plane services.

Use this package to keep JSON contracts consistent between:

- host `chromie-orchestrator`
- Docker `chromie-router`
- Docker `chromie-agent`
- host `chromie-hardware-daemon`

The package is intentionally small and dependency-light.

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
```
