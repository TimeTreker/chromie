from __future__ import annotations

import importlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol

from .capability_runtime import CapabilityDefinition


@dataclass(frozen=True)
class DBOSDurableSubmission:
    """Serializable input for a durable provider execution experiment.

    This is deliberately *not* a Chromie cognitive identity contract.  The
    Runtime-owned request/capability/interaction fields are copied into the
    durable carrier so a recovered workflow can be correlated back to Host
    state.  ``workflow_id`` remains backend-local implementation state.
    """

    workflow_id: str
    interaction_id: str
    request_id: str
    capability_id: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class DBOSDurableHandle:
    workflow_id: str


class DBOSWorkflowHandle(Protocol):
    async def get_result(self) -> Any: ...


class DBOSWorkflowDriver(Protocol):
    """Small DBOS surface used by the qualification backend.

    Keeping this protocol tiny makes DBOS optional and lets repository tests
    validate Chromie's authority/policy boundary without importing DBOS.
    """

    async def start(
        self,
        submission: DBOSDurableSubmission,
    ) -> DBOSWorkflowHandle: ...

    async def retrieve(self, workflow_id: str) -> DBOSWorkflowHandle: ...

    async def cancel(self, workflow_id: str) -> None: ...


class DBOSCapabilityRuntimeBackend:
    """Qualified durable carrier for explicitly safe Capability executions.

    This is intentionally not installed as CapabilityRuntime's default backend.
    A durable workflow may only be used when the canonical CapabilityDefinition
    explicitly opts in *and* remains idempotent, side-effect-free, and outside
    physical/safety authority.  DBOS never creates Chromie request/Goal IDs.

    Full process-restart activation additionally requires the host to rehydrate
    CapabilityRuntime ownership and restart terminal-event cognitive consumers.
    Until that startup integration exists, this class is a qualification
    boundary rather than a drop-in replacement for InProcessAsyncioBackend.
    """

    backend_id = "dbos_durable"

    def __init__(self, driver: DBOSWorkflowDriver) -> None:
        self._driver = driver

    @staticmethod
    def assert_definition_eligible(definition: CapabilityDefinition) -> None:
        if not definition.durable_runtime_eligible:
            raise ValueError(
                f"capability {definition.capability_id!r} is not opted into durable execution"
            )
        if not definition.idempotent:
            raise ValueError(
                f"capability {definition.capability_id!r} is not idempotent"
            )
        if not bool(definition.metadata.get("side_effect_free")):
            raise ValueError(
                f"capability {definition.capability_id!r} is not side-effect-free"
            )
        safety_class = str(definition.metadata.get("safety_class") or "").strip()
        if safety_class and safety_class != "safe_read":
            raise ValueError(
                f"capability {definition.capability_id!r} has non-read safety class {safety_class!r}"
            )

    async def start(
        self,
        submission: DBOSDurableSubmission,
        *,
        definition: CapabilityDefinition,
    ) -> DBOSDurableHandle:
        self.assert_definition_eligible(definition)
        await self._driver.start(submission)
        return DBOSDurableHandle(workflow_id=submission.workflow_id)

    async def wait(self, handle: DBOSDurableHandle) -> Any:
        workflow = await self._driver.retrieve(handle.workflow_id)
        return await workflow.get_result()

    async def cancel(self, handle: DBOSDurableHandle) -> None:
        await self._driver.cancel(handle.workflow_id)


class RealDBOSWorkflowDriver:
    """Lazy adapter for DBOS Python.

    ``workflow`` must be a DBOS-decorated async workflow accepting one plain
    dict.  The import is deliberately lazy so DBOS is an optional qualification
    dependency and cannot affect the default Chromie runtime.
    """

    def __init__(self, workflow: Callable[[dict[str, Any]], Awaitable[Any]]) -> None:
        self._workflow = workflow
        try:
            module = importlib.import_module("dbos")
        except ImportError as exc:  # pragma: no cover - optional dependency path
            raise RuntimeError(
                "DBOS durable backend requires the optional 'dbos' package"
            ) from exc
        self._dbos = module.DBOS
        self._set_workflow_id = module.SetWorkflowID

    async def start(self, submission: DBOSDurableSubmission) -> DBOSWorkflowHandle:
        with self._set_workflow_id(submission.workflow_id):
            return await self._dbos.start_workflow_async(
                self._workflow,
                {
                    "interaction_id": submission.interaction_id,
                    "request_id": submission.request_id,
                    "capability_id": submission.capability_id,
                    "payload": submission.payload,
                },
            )

    async def retrieve(self, workflow_id: str) -> DBOSWorkflowHandle:
        return await self._dbos.retrieve_workflow_async(workflow_id)

    async def cancel(self, workflow_id: str) -> None:
        self._dbos.cancel_workflow(workflow_id)


__all__ = [
    "DBOSCapabilityRuntimeBackend",
    "DBOSDurableHandle",
    "DBOSDurableSubmission",
    "DBOSWorkflowDriver",
    "RealDBOSWorkflowDriver",
]
