"""Strict offline model transport for architecture tests, never a semantic model.

Only explicitly registered runtime identities may vary. Missing, reordered, changed,
or extra requests fail closed; replay never records a new expectation implicitly.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


def encoded(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


class ReplayMismatch(RuntimeError):
    pass


class ModelReplay:
    def __init__(self, case: dict[str, Any]):
        self.case = copy.deepcopy(case)
        self.steps = self.case["model_steps"]
        self.position = 0
        self.bindings: dict[str, str] = {}
        self.records: list[dict[str, Any]] = []
        self.mismatches: list[dict[str, Any]] = []
        self.errors: list[str] = []
        self.lock = threading.RLock()

    def bind(self, name: str, value: str) -> None:
        """Register a value from a trusted runtime result, never from a model request."""
        with self.lock:
            if not value or (name in self.bindings and self.bindings[name] != value):
                raise ReplayMismatch(f"runtime binding changed: {name}")
            self.bindings[name] = value

    def normalize(self, value: Any) -> Any:
        if isinstance(value, str):
            for name, actual in sorted(self.bindings.items(), key=lambda item: -len(item[1])):
                value = value.replace(actual, "${" + name + "}")
            return value
        if isinstance(value, list):
            return [self.normalize(item) for item in value]
        if isinstance(value, dict):
            return {self.normalize(key): self.normalize(item) for key, item in value.items()}
        return value

    def materialize(self, value: Any) -> Any:
        if isinstance(value, str):
            for name, actual in self.bindings.items():
                value = value.replace("${" + name + "}", actual)
            if "${" in value:
                raise ReplayMismatch("response contains an unbound runtime identity")
            return value
        if isinstance(value, list):
            return [self.materialize(item) for item in value]
        if isinstance(value, dict):
            return {self.materialize(key): self.materialize(item) for key, item in value.items()}
        return value

    def reply(self, path: str, request: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            if self.errors:
                raise ReplayMismatch(self.errors[0])
            try:
                if self.position >= len(self.steps):
                    raise ReplayMismatch("unexpected extra model call")
                step = self.steps[self.position]
                normalized = self.normalize(request)
                if path != "/api/chat" or normalized != step["request"]:
                    self.mismatches.append({"step":step['name'], "path":path, "actual_request":normalized,
                        "expected_request_sha256":hashlib.sha256(encoded(step['request'])).hexdigest()})
                    raise ReplayMismatch(f"request mismatch at {step['name']}")
                raw = self.materialize(step["response"])
                schema_errors = [e.message for e in Draft202012Validator(request["format"]).iter_errors(raw)]
                self.records.append({
                    "step": step["name"], "request": normalized,
                    "request_sha256": hashlib.sha256(encoded(normalized)).hexdigest(),
                    "response": self.normalize(raw), "schema_errors": schema_errors,
                })
                self.position += 1
                return {
                    "model": request["model"], "message": {"role": "assistant", "content": json.dumps(raw, ensure_ascii=False)},
                    "done": True, "done_reason": "stop",
                }
            except (ReplayMismatch, KeyError, TypeError, ValueError) as exc:
                self.errors.append(str(exc))
                raise ReplayMismatch(str(exc)) from exc

    def assert_finished(self) -> None:
        if self.errors:
            raise ReplayMismatch("; ".join(self.errors))
        if self.position != len(self.steps):
            raise ReplayMismatch(f"unused model steps: {len(self.steps) - self.position}")


class ReplayServer:
    def __init__(self, replay: ModelReplay, port: int = 0):
        self.replay = replay
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args: Any) -> None:
                pass

            def do_POST(self) -> None:
                status = 200
                try:
                    size = int(self.headers.get("Content-Length", "0"))
                    if not 0 < size <= 4_000_000:
                        raise ReplayMismatch("invalid request size")
                    payload = json.loads(self.rfile.read(size))
                    result = owner.replay.reply(self.path, payload)
                except (ValueError, ReplayMismatch, TypeError) as exc:
                    status, result = 409, {"error": str(exc)}
                    if not owner.replay.errors:
                        owner.replay.errors.append(str(exc))
                body = encoded(result)
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def __enter__(self) -> "ReplayServer":
        self.thread.start()
        return self

    def __exit__(self, *_args: Any) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", type=Path)
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--bindings", type=Path, help="Explicit trusted runtime identity map, when required")
    args = parser.parse_args()
    replay = ModelReplay(json.loads(args.case.read_text()))
    if args.bindings:
        for name, value in json.loads(args.bindings.read_text()).items():
            replay.bind(name, value)
    with ReplayServer(replay, args.port) as server:
        print(server.url, flush=True)
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            replay.assert_finished()


if __name__ == "__main__":
    main()
