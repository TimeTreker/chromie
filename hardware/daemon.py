from __future__ import annotations

import os
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import ORJSONResponse

try:
    from .schema import ActionCommand, ActionResult, HealthResponse, RobotState
    from .service import HardwareService
except ImportError:  # pragma: no cover - direct script launch
    from schema import ActionCommand, ActionResult, HealthResponse, RobotState
    from service import HardwareService

SERVICE_NAME = "chromie-hardware"
HARDWARE_DRIVER = os.getenv("HARDWARE_DRIVER", "mock").strip().lower()
HARDWARE_HOST = os.getenv("HARDWARE_HOST", "127.0.0.1")
HARDWARE_PORT = int(os.getenv("HARDWARE_PORT", "8095"))

app = FastAPI(
    title="Chromie Hardware Daemon",
    version="0.1.0",
    default_response_class=ORJSONResponse,
)

service = HardwareService()
driver = service.driver
action_results = service.action_results


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(ok=True, driver=driver.name, state=driver.state())


@app.get("/state", response_model=RobotState)
async def state() -> RobotState:
    return driver.state()


@app.post("/actions", response_model=ActionResult)
async def execute_action(command: ActionCommand) -> ActionResult:
    """Execute a low-level action.

    The hardware daemon is intentionally dumb: it validates basic shape and
    executes. Higher-level planning belongs in chromie-agent; scheduling and
    cancellation belong in host chromie-orchestrator.
    """
    return await service.execute(command)


@app.get("/actions/{action_id}", response_model=ActionResult)
async def get_action(action_id: str) -> ActionResult:
    result = service.get_action(action_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"unknown action_id: {action_id}")
    return result


@app.post("/emergency_stop", response_model=RobotState)
async def emergency_stop() -> RobotState:
    return await driver.emergency_stop()


@app.post("/reset_emergency_stop", response_model=RobotState)
async def reset_emergency_stop() -> RobotState:
    return await driver.reset_emergency_stop()


if __name__ == "__main__":
    uvicorn.run("daemon:app", host=HARDWARE_HOST, port=HARDWARE_PORT, reload=False)
