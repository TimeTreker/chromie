from __future__ import annotations

import asyncio
from typing import Any

import pytest

from orchestrator.runtime.capability_runtime import (
    CapabilityDefinition,
    CapabilityExecutionContext,
    CapabilityRegistry,
    CapabilityRuntime,
)
from orchestrator.runtime.capability_runtime_backend import (
    CapabilityRuntimeBackendHandle,
    InProcessAsyncioBackend,
)
from shared.chromie_contracts.interaction import (
    CapabilityRequest,
    CapabilityResult,
    InteractionResponse,
)


class _Provider:
    provider_id = "test.backend.provider"

    async def execute(
        self,
        request: CapabilityRequest,
        definition: CapabilityDefinition,
        context: CapabilityExecutionContext,
    ) -> CapabilityResult:
        del definition, context
        await asyncio.sleep(0)
        return CapabilityResult(
            request_id=request.request_id,
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            status="completed",
            output={"ok": True},
        )

    async def cancel(self, request, definition, context) -> None:
        del request, definition, context


class _RecordingBackend(InProcessAsyncioBackend):
    backend_id = "opaque_test_backend"

    def __init__(self) -> None:
        super().__init__()
        self.started_names: list[str] = []
        self.handles: list[CapabilityRuntimeBackendHandle] = []

    def start_submission(self, runner, *, name: str):
        self.started_names.append(name)
        handle = super().start_submission(runner, name=name)
        self.handles.append(handle)
        return handle


def _runtime(*, backend=None) -> CapabilityRuntime:
    registry = CapabilityRegistry()
    registry.register(
        CapabilityDefinition(
            capability_id="chromie.backend_probe",
            provider_id=_Provider.provider_id,
            output_schema={
                "type": "object",
                "properties": {"ok": {"type": "boolean"}},
                "required": ["ok"],
                "additionalProperties": False,
            },
        )
    )
    runtime = CapabilityRuntime(registry, backend=backend)
    runtime.register_provider(_Provider())
    return runtime


def _response() -> InteractionResponse:
    return InteractionResponse(
        interaction_id="interaction-backend-spi",
        capabilities=[
            CapabilityRequest(
                request_id="request-backend-spi",
                capability_id="chromie.backend_probe",
            )
        ],
    )


@pytest.mark.asyncio
async def test_backend_handle_is_not_exposed_by_dispatch_or_runtime_event() -> None:
    backend = _RecordingBackend()
    runtime = _runtime(backend=backend)

    receipt = await runtime.submit(_response())
    assert len(backend.handles) == 1
    assert backend.handles[0].opaque_id
    assert "backend" not in receipt.model_dump(mode="json")
    assert "opaque_id" not in receipt.model_dump(mode="json")

    result = await runtime.wait_terminal(receipt)
    assert result.status == "completed"
    events = await runtime.runtime_events_after(
        receipt.event_cursor,
        dispatch_id=receipt.dispatch_id,
    )
    assert events
    assert all("backend" not in event.model_dump(mode="json") for event in events)
    assert all("opaque_id" not in event.model_dump(mode="json") for event in events)


@pytest.mark.asyncio
async def test_inprocess_backend_refuses_to_release_live_submission() -> None:
    backend = InProcessAsyncioBackend()
    release = asyncio.Event()

    async def run() -> Any:
        await release.wait()
        return "done"

    handle = backend.start_submission(run, name="backend-live-release-test")
    with pytest.raises(RuntimeError, match="cannot release a live"):
        backend.release_submission(handle)
    release.set()
    assert await backend.wait_submission(handle) == "done"
    backend.release_submission(handle)
