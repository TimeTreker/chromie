"""Strict artifact identities and private local I/O for offline training."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


class Rejected(ValueError):
    """A content-free rejection code safe to print beside private evidence."""


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise Rejected("duplicate_json_member")
        result[key] = value
    return result


def loads(text: str) -> Any:
    def constant(_value: str) -> Any:
        raise Rejected("nonfinite_json")
    try:
        return json.loads(text, object_pairs_hook=_unique, parse_constant=constant)
    except (ValueError, TypeError) as exc:
        raise Rejected("invalid_json") from exc


def encoded(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(encoded(value)).hexdigest()


def file_digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=False, mode=0o700)


def write_json(path: Path, value: Any) -> None:
    # Exclusive creation prevents overwriting evidence or following an existing link.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(encoded(value) + b"\n")


def source_identity() -> dict[str, str]:
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    # Include untracked pipeline files too, without retaining private data or diffs.
    paths = subprocess.check_output(["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                                    cwd=ROOT, text=True).splitlines()
    hashes = {name: file_digest(ROOT / name) for name in paths
              if (ROOT / name).is_file() and (name.endswith((".py", ".txt", ".json", ".yml"))
                                             or name == "llm/sglang/Dockerfile")}
    return {"revision": revision, "tree_sha256": digest(hashes)}


def redact(value: Any, replacements: list[dict[str, str]]) -> Any:
    if isinstance(value, str):
        for item in replacements:
            before, after = item["from"], item["to"]
            if not before or not after or before == after:
                raise Rejected("invalid_redaction")
            value = value.replace(before, after)
        return value
    if isinstance(value, list):
        return [redact(item, replacements) for item in value]
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            new_key = redact(key, replacements)
            if new_key in result:
                raise Rejected("redaction_key_collision")
            result[new_key] = redact(item, replacements)
        return result
    return value


_PRIVATE = re.compile(
    r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|\b1[3-9]\d{9}\b|"
    r"(?i:bearer\s+[A-Za-z0-9._-]{8,}|(?:api[_-]?key|password|secret|access[_-]?token)\s*[=:]\s*[\w/+=-]{6,})|"
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----|(?:/home/|/Users/)[^\s\"<>]+|"
    r"\b(?:sk-|hf_)[A-Za-z0-9]{16,}"
)


def privacy_check(value: Any) -> None:
    # A leak backstop, not a claim that arbitrary names/addresses can be detected.
    if _PRIVATE.search(encoded(value).decode()):
        raise Rejected("privacy_scan_rejected")


def local_url(value: str) -> str:
    from urllib.parse import urlsplit
    parsed = urlsplit(value)
    if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise Rejected("loopback_http_endpoint_required")
    return value.rstrip("/")
