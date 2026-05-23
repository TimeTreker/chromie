from __future__ import annotations

import json
import os
from typing import Any

from schema import ActionCommand


class SerialRobotDriver:
    """Small serial adapter skeleton for a real robot controller.

    It intentionally keeps protocol details simple. Replace `_encode_command`
    with the protocol your motor/servo controller expects.
    """

    name = "serial"

    def __init__(self, port: str | None = None, baud: int | None = None) -> None:
        self.port = port or os.getenv("HARDWARE_SERIAL_PORT", "/dev/ttyUSB0")
        self.baud = baud or int(os.getenv("HARDWARE_SERIAL_BAUD", "115200"))
        self._serial = None

    def connect(self) -> None:
        import serial  # imported lazily so mock mode does not require hardware

        if self._serial is None:
            self._serial = serial.Serial(self.port, self.baud, timeout=1)

    def close(self) -> None:
        if self._serial is not None:
            self._serial.close()
            self._serial = None

    def send_command(self, command: ActionCommand) -> dict[str, Any]:
        self.connect()
        payload = self._encode_command(command)
        assert self._serial is not None
        self._serial.write(payload)
        self._serial.flush()
        return {"sent": payload.decode("utf-8", errors="replace").strip()}

    def _encode_command(self, command: ActionCommand) -> bytes:
        return (json.dumps(command.model_dump(mode="json"), ensure_ascii=False) + "\n").encode("utf-8")
