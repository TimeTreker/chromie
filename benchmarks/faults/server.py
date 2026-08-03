from __future__ import annotations

from collections import deque
from contextlib import AbstractContextManager
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import socket
import threading
import time
from typing import Any, Mapping, Sequence

from benchmarks.contracts import ContractError


class _State:
    def __init__(self, responses: Sequence[Mapping[str, Any]]) -> None:
        if not responses:
            raise ContractError("fault server requires at least one response")
        self.responses = deque(dict(item) for item in responses)
        self.last = dict(responses[-1])
        self.requests: list[dict[str, Any]] = []
        self.lock = threading.Lock()

    def next(self, request: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            self.requests.append(request)
            if self.responses:
                self.last = self.responses.popleft()
            return dict(self.last)


class FaultHttpServer(AbstractContextManager["FaultHttpServer"]):
    """Small deterministic HTTP fault source for real client boundaries."""

    def __init__(self, responses: Sequence[Mapping[str, Any]]) -> None:
        self.state = _State(responses)
        state = self.state

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length) if length else b""
                action = state.next(
                    {
                        "method": "POST",
                        "path": self.path,
                        "body": body.decode("utf-8", errors="replace"),
                    }
                )
                kind = str(action.get("action") or "success")
                delay_ms = int(action.get("delay_ms") or 0)
                if delay_ms > 0:
                    time.sleep(delay_ms / 1000.0)
                if kind == "disconnect":
                    try:
                        self.connection.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
                    self.connection.close()
                    return
                if kind == "malformed_json":
                    payload = b"{not-json"
                    status = int(action.get("status") or 200)
                    content_type = "application/json"
                elif kind == "status":
                    status = int(action.get("status") or 500)
                    payload = json.dumps(action.get("body") or {"error": "injected"}).encode()
                    content_type = "application/json"
                else:
                    status = int(action.get("status") or 200)
                    body_value = action.get("body")
                    if body_value is None:
                        body_value = {
                            "response": str(action.get("response") or "fault server success"),
                            "done": True,
                            "done_reason": "stop",
                        }
                    payload = json.dumps(body_value).encode()
                    content_type = "application/json"
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                try:
                    self.wfile.write(payload)
                except (BrokenPipeError, ConnectionResetError):
                    return

            def log_message(self, format: str, *args: Any) -> None:
                del format, args

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    def __enter__(self) -> "FaultHttpServer":
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2.0)
