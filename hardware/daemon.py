from __future__ import annotations

import os
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import ORJSONResponse

from schema import ActionCommand, ActionResult, ActionStatus, HealthResponse, RobotState
from drivers.mock_robot import MockRobotDriver

SERVICE_NAME = "chromie-hardware"
HARDWARE_DRIVER = os.getenv("HARDWARE_DRIVER", "mock").strip().lower()
HARDWARE_HOST = os.getenv("HARDWARE_HOST", "127.0.0.1")
HARDWARE_PORT = int(os.getenv("HARDWARE_PORT", "8095"))

app = FastAPI(
    title="Chromie Hardware Daemon",
    version="0.1.0",
    default_response_class=ORJSONResponse,
)

# In v1, only mock is enabled by default. Keep real driver wiring explicit.
driver = MockRobotDriver()
action_results: dict[str, ActionResult] = {}


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
    if command.type.startswith("unsafe."):
        result = ActionResult(
            id=command.id,
            status=ActionStatus.REJECTED,
            target=command.target,
            type=command.type,
            error="unsafe action namespace is rejected",
        )
        action_results[command.id] = result
        return result

    result = await driver.execute(command)
    action_results[command.id] = result
    return result


@app.get("/actions/{action_id}", response_model=ActionResult)
async def get_action(action_id: str) -> ActionResult:
    result = action_results.get(action_id)
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
