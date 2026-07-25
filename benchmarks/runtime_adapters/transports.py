from __future__ import annotations

import importlib
import json
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol
from urllib import error, request


class TransportError(RuntimeError):
    pass


class JsonTransport(Protocol):
    def invoke(self, payload: Mapping[str, Any]) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class HttpJsonTransport:
    url: str
    timeout_s: float = 120.0

    def __post_init__(self) -> None:
        if not self.url.strip():
            raise TransportError("runtime adapter URL must not be empty")
        if self.timeout_s <= 0:
            raise TransportError("runtime adapter timeout must be positive")

    def invoke(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        http_request = request.Request(
            self.url,
            data=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(http_request, timeout=self.timeout_s) as response:
                raw = response.read().decode("utf-8")
        except (error.HTTPError, error.URLError, TimeoutError, OSError) as exc:
            raise TransportError(f"runtime adapter HTTP request failed: {exc}") from exc
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise TransportError(f"runtime adapter returned invalid JSON: {exc}") from exc
        if not isinstance(decoded, Mapping):
            raise TransportError("runtime adapter response must be a JSON object")
        return decoded


@dataclass(frozen=True)
class PythonCallableTransport:
    callable_spec: str

    def __post_init__(self) -> None:
        if ":" not in self.callable_spec:
            raise TransportError("callable must use 'module.path:function' syntax")

    def _load(self) -> Callable[[Mapping[str, Any]], Any]:
        module_name, function_name = self.callable_spec.split(":", 1)
        if not module_name or not function_name:
            raise TransportError("callable must use 'module.path:function' syntax")
        try:
            module = importlib.import_module(module_name)
            function = getattr(module, function_name)
        except (ImportError, AttributeError) as exc:
            raise TransportError(f"cannot load runtime adapter callable {self.callable_spec!r}: {exc}") from exc
        if not callable(function):
            raise TransportError(f"runtime adapter target {self.callable_spec!r} is not callable")
        return function

    def invoke(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        try:
            result = self._load()(payload)
        except TransportError:
            raise
        except Exception as exc:  # production boundary: preserve concise failure evidence
            raise TransportError(f"runtime adapter callable failed: {exc}") from exc
        if not isinstance(result, Mapping):
            raise TransportError("runtime adapter callable must return a mapping")
        return result
