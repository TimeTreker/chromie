"""Crash-safe file replacement shared by every evidence and state writer."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def json_document_bytes(payload: Any) -> bytes:
    """Return the canonical on-disk JSON form: sorted keys, two-space indent, final newline."""

    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def sync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_write_bytes(path: Path, content: bytes, *, mode: int | None = None) -> None:
    """Write ``content`` to a sibling temporary file, fsync it, then replace ``path``.

    ``mode`` is applied to the temporary file before any byte is written, so
    the replaced file never exists with wider permissions.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            if mode is not None:
                os.fchmod(handle.fileno(), mode)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        sync_directory(path.parent)
    finally:
        temporary_path.unlink(missing_ok=True)


def atomic_write_text(path: Path, text: str, *, mode: int | None = None) -> None:
    atomic_write_bytes(path, text.encode("utf-8"), mode=mode)


def atomic_write_json(path: Path, payload: Any, *, mode: int | None = None) -> None:
    atomic_write_bytes(path, json_document_bytes(payload), mode=mode)
