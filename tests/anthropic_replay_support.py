"""Recorded-reference Anthropic Messages endpoint for offline architecture replay.

It speaks the Messages API streaming wire format and answers each request with
the frozen reference response of the replay step being served. It is a transport
fixture, never a semantic model: it proves the Claude path end to end at no cost.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable


def _sse(event: str, data: dict[str, Any]) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode()


def message_stream(text: str, *, model: str, stop_reason: str = "end_turn", input_tokens: int = 0) -> bytes:
    usage = {"input_tokens": input_tokens, "output_tokens": max(1, len(text) // 4),
             "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
    return b"".join((
        _sse("message_start", {"type": "message_start", "message": {
            "id": "msg_replay", "type": "message", "role": "assistant", "model": model,
            "content": [], "stop_reason": None, "stop_sequence": None,
            "usage": {**usage, "output_tokens": 0}}}),
        _sse("content_block_start", {"type": "content_block_start", "index": 0,
                                     "content_block": {"type": "thinking", "thinking": "", "signature": ""}}),
        _sse("content_block_delta", {"type": "content_block_delta", "index": 0,
                                     "delta": {"type": "signature_delta", "signature": "replay"}}),
        _sse("content_block_stop", {"type": "content_block_stop", "index": 0}),
        _sse("content_block_start", {"type": "content_block_start", "index": 1,
                                     "content_block": {"type": "text", "text": ""}}),
        _sse("content_block_delta", {"type": "content_block_delta", "index": 1,
                                     "delta": {"type": "text_delta", "text": text}}),
        _sse("content_block_stop", {"type": "content_block_stop", "index": 1}),
        _sse("message_delta", {"type": "message_delta",
                               "delta": {"stop_reason": stop_reason, "stop_sequence": None},
                               "usage": usage}),
        _sse("message_stop", {"type": "message_stop"}),
    ))


class RecordedAnthropicServer:
    """Serve ``answer(request_body) -> (text, stop_reason)`` over /v1/messages."""

    def __init__(self, answer: Callable[[dict[str, Any]], tuple[str, str]]):
        self.answer = answer
        self.requests: list[dict[str, Any]] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args: Any) -> None:
                return

            def do_POST(self) -> None:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
                outer.requests.append({"path": self.path, "headers": dict(self.headers), "body": body})
                text, stop_reason = outer.answer(body)
                payload = message_stream(text, model=body.get("model", ""), stop_reason=stop_reason,
                                         input_tokens=len(json.dumps(body)) // 4)
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self) -> "RecordedAnthropicServer":
        self.thread.start()
        return self

    def __exit__(self, *_args: Any) -> None:
        self.server.shutdown()
        self.server.server_close()
