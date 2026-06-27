"""Small output helpers for the Chromie developer CLI."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, TextIO


class ExitCode(IntEnum):
    OK = 0
    WARNING = 1
    FAILURE = 2
    USAGE = 64


@dataclass(frozen=True)
class CommandResult:
    status: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    exit_code: ExitCode = ExitCode.OK


def write_result(
    result: CommandResult,
    *,
    stream: TextIO,
    json_output: bool = False,
) -> None:
    if json_output:
        payload = {
            "status": result.status,
            "message": result.message,
            "details": result.details,
            "exit_code": int(result.exit_code),
        }
        stream.write(json.dumps(payload, sort_keys=True) + "\n")
        return

    stream.write(f"{result.status.upper()}: {result.message}\n")
    _write_plain_mapping(result.details, stream=stream, indent=2)


def _write_plain_mapping(
    values: dict[str, Any],
    *,
    stream: TextIO,
    indent: int,
) -> None:
    prefix = " " * indent
    for name, value in values.items():
        if isinstance(value, dict):
            stream.write(f"{prefix}{name}:\n")
            _write_plain_mapping(value, stream=stream, indent=indent + 2)
        elif isinstance(value, list):
            stream.write(f"{prefix}{name}:\n")
            if not value:
                stream.write(f"{prefix}  []\n")
            for item in value:
                if isinstance(item, dict):
                    stream.write(f"{prefix}  -\n")
                    _write_plain_mapping(item, stream=stream, indent=indent + 4)
                else:
                    stream.write(f"{prefix}  - {item}\n")
        else:
            stream.write(f"{prefix}{name}: {value}\n")
