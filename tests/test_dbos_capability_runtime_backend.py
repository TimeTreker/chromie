from __future__ import annotations

import asyncio

import pytest

from orchestrator.runtime.capability_runtime import CapabilityDefinition
from orchestrator.runtime.dbos_capability_runtime_backend import (
    DBOSCapabilityRuntimeBackend,
    DBOSDurableSubmission,
)


class _FakeHandle:
    def __init__(self, result):
        self._result = result

    async def get_result(self):
        return self._result


class _FakeDBOSDriver:
    def __init__(self):
        self.results = {}
        self.cancelled = []
        self.started = []

    async def start(self, submission):
        self.started.append(submission)
        self.results.setdefault(submission.workflow_id, {"ok": True})
        return _FakeHandle(self.results[submission.workflow_id])

    async def retrieve(self, workflow_id):
        if workflow_id not in self.results:
            raise ValueError("unknown workflow")
        return _FakeHandle(self.results[workflow_id])

    async def cancel(self, workflow_id):
        self.cancelled.append(workflow_id)


def _definition(**updates):
    values = {
        "capability_id": "chromie.weather.lookup",
        "provider_id": "chromie.agent_tool",
        "idempotent": True,
        "durable_runtime_eligible": True,
        "metadata": {"side_effect_free": True, "safety_class": "safe_read"},
    }
    values.update(updates)
    return CapabilityDefinition(**values)


def test_dbos_durable_carrier_can_be_retrieved_by_a_new_backend_instance():
    driver = _FakeDBOSDriver()
    first = DBOSCapabilityRuntimeBackend(driver)
    submission = DBOSDurableSubmission(
        workflow_id="dbos-request-weather-1",
        interaction_id="interaction-1",
        request_id="request-weather-1",
        capability_id="chromie.weather.lookup",
        payload={"location": "Shanghai"},
    )

    handle = asyncio.run(first.start(submission, definition=_definition()))
    # Simulate a host-process restart at the adapter boundary: a fresh backend
    # instance owns no in-memory handle registry and resolves by durable ID.
    recovered = DBOSCapabilityRuntimeBackend(driver)
    assert asyncio.run(recovered.wait(handle)) == {"ok": True}


def test_dbos_backend_fails_closed_for_non_idempotent_or_effectful_capabilities():
    safe = _definition()
    physical = _definition(
        capability_id="soridormi.motion.walk",
        idempotent=False,
        durable_runtime_eligible=True,
        metadata={"side_effect_free": False, "safety_class": "physical_motion"},
    )
    not_opted_in = safe.model_copy(update={"durable_runtime_eligible": False})

    DBOSCapabilityRuntimeBackend.assert_definition_eligible(safe)
    with pytest.raises(ValueError, match="not idempotent"):
        DBOSCapabilityRuntimeBackend.assert_definition_eligible(physical)
    with pytest.raises(ValueError, match="not opted"):
        DBOSCapabilityRuntimeBackend.assert_definition_eligible(not_opted_in)


def test_dbos_cancel_uses_backend_workflow_identity_only():
    driver = _FakeDBOSDriver()
    backend = DBOSCapabilityRuntimeBackend(driver)
    submission = DBOSDurableSubmission(
        workflow_id="dbos-weather-cancel",
        interaction_id="interaction-2",
        request_id="request-weather-2",
        capability_id="chromie.weather.lookup",
        payload={"location": "Chongqing"},
    )
    handle = asyncio.run(backend.start(submission, definition=_definition()))
    asyncio.run(backend.cancel(handle))
    assert driver.cancelled == ["dbos-weather-cancel"]
    assert handle.workflow_id != submission.request_id
