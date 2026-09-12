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
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


def encoded(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def load_case(path: Path) -> dict[str, Any]:
    """Resolve hash-checked frozen packet parts, never regenerate expectations."""
    def expand(value: Any) -> Any:
        if isinstance(value, dict) and set(value) == {"$artifact"}:
            digest = value['$artifact']
            if not isinstance(digest, str) or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
                raise ReplayMismatch('invalid frozen artifact identity')
            raw = (path.parent/'artifacts'/f'{digest}.json').read_bytes()
            if hashlib.sha256(raw).hexdigest() != digest:
                raise ReplayMismatch('frozen artifact hash mismatch')
            return json.loads(raw)
        if isinstance(value, dict):
            return {key:expand(item) for key,item in value.items()}
        if isinstance(value, list):
            return [expand(item) for item in value]
        return value
    return expand(json.loads(path.read_text()))


class ReplayMismatch(RuntimeError):
    pass


class ModelReplay:
    def __init__(self, case: dict[str, Any], *, candidate: dict[str, Any] | None = None):
        self.case = copy.deepcopy(case)
        self.steps = self.case["model_steps"]
        self.candidate = copy.deepcopy(candidate)
        if candidate:
            parsed = urllib.parse.urlsplit(candidate['url'])
            if candidate['role'] not in {'gi', 'ga', 'fast', 'deep'} or not candidate['model']:
                raise ValueError('select one supported candidate role and model')
            if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
                raise ValueError('candidate URL must be an explicit HTTP(S) model service')
            if not 0 < candidate.get('timeout', 60) <= 600:
                raise ValueError('candidate timeout must be within (0, 600] seconds')
            if any(step.get('fixture_kind', 'authored_reference') != 'authored_reference' for step in self.steps):
                raise ValueError('candidate mode cannot substitute intentional model faults or contract-gap answers')
        self.candidate_calls = 0
        self.candidate_changed_result = False
        self.position = 0
        self.bindings: dict[str, str] = {}
        self.records: list[dict[str, Any]] = []
        self.mismatches: list[dict[str, Any]] = []
        self.errors: list[str] = []
        self.lock = threading.RLock()

    def candidate_reply(self, request: dict[str, Any]) -> dict[str, Any]:
        """Send only the actual role packet, never the case, reference or rubric."""
        if self.candidate is None:
            raise ReplayMismatch('candidate service was not selected')
        payload = copy.deepcopy(request)
        payload['model'] = self.candidate['model']
        self.candidate_calls += 1
        submission = urllib.request.Request(
            self.candidate['url'].rstrip('/') + '/api/chat', data=encoded(payload),
            headers={'Content-Type': 'application/json'}, method='POST',
        )
        try:
            with urllib.request.urlopen(submission, timeout=self.candidate.get('timeout', 60)) as response:
                raw = response.read().decode()
        except urllib.error.HTTPError as exc:
            self.records.append({'source': 'candidate', 'submitted_request': self.normalize(payload),
                                 'http_status': exc.code, 'raw_transport_response': exc.read().decode(errors='replace')})
            raise ReplayMismatch(f'candidate returned HTTP {exc.code}') from exc
        except (OSError, urllib.error.URLError) as exc:
            self.records.append({'source': 'candidate', 'submitted_request': self.normalize(payload),
                                 'transport_error': str(exc)})
            raise ReplayMismatch(f'candidate transport failed: {exc}') from exc
        self.records.append({'source': 'candidate', 'submitted_request': self.normalize(payload),
                             'raw_transport_response': raw})
        envelope = json.loads(raw)
        if not isinstance(envelope, dict):
            raise ReplayMismatch('candidate response envelope must be an object')
        return envelope

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
                        "verdict": 'uncovered_replay_branch' if self.candidate_changed_result else 'request_mismatch',
                        "expected_request_sha256":hashlib.sha256(encoded(step['request'])).hexdigest()})
                    raise ReplayMismatch(f"request mismatch at {step['name']}")
                messages = '\n'.join(str(item.get('content','')) for item in normalized.get('messages',[]))
                for required in step.get('required_prompt_fragments',[]):
                    if required not in messages and json.dumps(required,ensure_ascii=False)[1:-1] not in messages:
                        raise ReplayMismatch(f'authoritative input missing at {step["name"]}: {required}')
                use_candidate = self.candidate and self.candidate['role'] == step.get('role', step['name'].split('-')[0])
                if use_candidate:
                    envelope = self.candidate_reply(request)
                    try:
                        raw = json.loads(envelope.get('message', {}).get('content', ''))
                    except (ValueError, TypeError, AttributeError):
                        raw = None  # Preserve the malformed envelope for the actual role parser.
                    self.candidate_changed_result |= self.normalize(raw) != step['response']
                    record = self.records[-1]
                else:
                    raw = self.materialize(step["response"])
                    envelope = {"model": request["model"], "message": {"role": "assistant", "content": json.dumps(raw, ensure_ascii=False)},
                                "done": True, "done_reason": "stop"}
                    record = {'source': 'replay'}
                    self.records.append(record)
                schema_errors = [e.message for e in Draft202012Validator(request["format"]).iter_errors(raw)]
                record.update({
                    "step": step["name"], "request": normalized,
                    "request_sha256": hashlib.sha256(encoded(normalized)).hexdigest(),
                    "response": self.normalize(raw), "schema_errors": schema_errors,
                })
                self.position += 1
                return envelope
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
        self.thread = threading.Thread(target=lambda: self.server.serve_forever(poll_interval=0.01), daemon=True)
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
    replay = ModelReplay(load_case(args.case))
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
