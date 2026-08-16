from __future__ import annotations

from shared.chromie_contracts.interaction import InteractionResponse
from orchestrator.runtime.capability_runtime import (
    CapabilityRuntime,
    CapabilityRuntimeResult,
    RuntimeAuthorization,
)


async def submit_and_wait_terminal(
    runtime: CapabilityRuntime,
    response: InteractionResponse,
    *,
    authorization: RuntimeAuthorization | None = None,
) -> CapabilityRuntimeResult:
    """Test-only explicit join for cases that exercise terminal runtime behavior."""

    receipt = await runtime.submit(response, authorization=authorization)
    return await runtime.wait_terminal(receipt)
