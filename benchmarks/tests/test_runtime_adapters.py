from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from benchmarks.runtime_adapters.adapter import RuntimeAdapter, RuntimeAdapterError
from benchmarks.runtime_adapters.profiles import get_component_profile


def _request(*, layer: str = "module") -> dict:
    return {
        "schema_version": 1,
        "scenario": {"id": "scenario-1", "layer": layer, "input": {"text": "hello"}},
        "run": {"mode": "live_model", "evidence_level": "component"},
    }


def test_requires_exactly_one_transport_configuration() -> None:
    profile = get_component_profile("cognitive_gateway")
    with pytest.raises(RuntimeAdapterError, match="exactly one"):
        RuntimeAdapter.from_environment(profile, environment={})
    with pytest.raises(RuntimeAdapterError, match="exactly one"):
        RuntimeAdapter.from_environment(
            profile,
            environment={profile.url_env: "http://localhost", profile.callable_env: "x:y"},
        )


def test_python_callable_transport_preserves_component_evidence(tmp_path: Path, monkeypatch) -> None:
    module = tmp_path / "planner_component.py"
    module.write_text(
        "def invoke(payload):\n"
        "    assert payload['component'] == 'planner'\n"
        "    return {'observation': {'scenario_id': payload['scenario']['id'], "
        "'primary_task_passed': True, 'invariant_results': {}}}\n",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    profile = get_component_profile("planner")
    adapter = RuntimeAdapter.from_environment(
        profile, environment={profile.callable_env: "planner_component:invoke"}
    )
    observation = adapter.execute(_request())
    assert observation["scenario_id"] == "scenario-1"
    assert observation["primary_task_passed"] is True
    assert observation["evidence"][-1]["component"] == "planner"
    assert observation["evidence"][-1]["transport"] == "PythonCallableTransport"
    assert observation["latency_ms"] >= 0


def test_rejects_wrong_layer(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "layer_component.py").write_text(
        "def invoke(payload): return {'primary_task_passed': True}\n", encoding="utf-8"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    profile = get_component_profile("cognitive_gateway")
    adapter = RuntimeAdapter.from_environment(
        profile, environment={profile.callable_env: "layer_component:invoke"}
    )
    with pytest.raises(RuntimeAdapterError, match="does not accept"):
        adapter.execute(_request(layer="e2e"))


def test_rejects_unstructured_component_response(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "unstructured_component.py").write_text(
        "def invoke(payload): return {'route': 'chat'}\n", encoding="utf-8"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    profile = get_component_profile("cognitive_gateway")
    adapter = RuntimeAdapter.from_environment(
        profile, environment={profile.callable_env: "unstructured_component:invoke"}
    )
    with pytest.raises(RuntimeAdapterError, match="benchmark observation"):
        adapter.execute(_request())


def test_http_transport_round_trip() -> None:
    received: list[dict] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers["Content-Length"])
            payload = json.loads(self.rfile.read(length))
            received.append(payload)
            response = json.dumps(
                {
                    "observation": {
                        "scenario_id": payload["scenario"]["id"],
                        "primary_task_passed": True,
                        "invariant_results": {},
                    }
                }
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        profile = get_component_profile("social_attention")
        adapter = RuntimeAdapter.from_environment(
            profile,
            timeout_s=2.0,
            environment={profile.url_env: f"http://127.0.0.1:{server.server_port}/benchmark"},
        )
        observation = adapter.execute(_request(layer="integration"))
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()
    assert received[0]["component"] == "social_attention"
    assert observation["primary_task_passed"] is True
    assert observation["evidence"][-1]["transport"] == "HttpJsonTransport"


def test_manifest_matches_profiles() -> None:
    root = Path(__file__).resolve().parents[2]
    manifest = json.loads(
        (root / "benchmarks/manifests/runtime_adapters.json").read_text(encoding="utf-8")
    )
    declared = {item["name"]: item for item in manifest["components"]}
    assert set(declared) == {
        "cognitive_gateway",
        "planner",
        "mind_profile",
        "capability_projection",
        "social_attention",
    }
    for name, item in declared.items():
        profile = get_component_profile(name)
        assert item["layers"] == list(profile.layers)
        assert item["url_env"] == profile.url_env
        assert item["callable_env"] == profile.callable_env
