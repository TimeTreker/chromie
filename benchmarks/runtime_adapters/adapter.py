from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Mapping

from .profiles import ComponentProfile
from .transports import HttpJsonTransport, JsonTransport, PythonCallableTransport, TransportError


class RuntimeAdapterError(RuntimeError):
    pass


_OBSERVATION_FIELDS = frozenset(
    {
        "scenario_id",
        "primary_task_passed",
        "primary_outcome",
        "auxiliary_behavior",
        "behaviors",
        "evidence",
        "invariant_results",
        "latency_ms",
        "artifacts",
    }
)


@dataclass(frozen=True)
class RuntimeAdapter:
    profile: ComponentProfile
    transport: JsonTransport

    @classmethod
    def from_environment(
        cls,
        profile: ComponentProfile,
        *,
        timeout_s: float = 120.0,
        environment: Mapping[str, str] | None = None,
    ) -> "RuntimeAdapter":
        env = os.environ if environment is None else environment
        url = env.get(profile.url_env, "").strip()
        callable_spec = env.get(profile.callable_env, "").strip()
        if bool(url) == bool(callable_spec):
            raise RuntimeAdapterError(
                f"configure exactly one of {profile.url_env} or {profile.callable_env}"
            )
        try:
            transport: JsonTransport
            if url:
                transport = HttpJsonTransport(url=url, timeout_s=timeout_s)
            else:
                transport = PythonCallableTransport(callable_spec=callable_spec)
        except TransportError as exc:
            raise RuntimeAdapterError(str(exc)) from exc
        return cls(profile=profile, transport=transport)

    def execute(self, request_payload: Mapping[str, Any]) -> dict[str, Any]:
        scenario = request_payload.get("scenario")
        run = request_payload.get("run")
        if request_payload.get("schema_version") != 1:
            raise RuntimeAdapterError("adapter request must use schema_version 1")
        if not isinstance(scenario, Mapping) or not isinstance(run, Mapping):
            raise RuntimeAdapterError("adapter request must contain scenario and run objects")
        scenario_id = scenario.get("id")
        if not isinstance(scenario_id, str) or not scenario_id:
            raise RuntimeAdapterError("scenario must declare a non-empty id")
        layer = scenario.get("layer")
        if layer not in self.profile.layers:
            raise RuntimeAdapterError(
                f"component {self.profile.name!r} does not accept benchmark layer {layer!r}"
            )

        component_request = {
            "schema_version": 1,
            "component": self.profile.name,
            "scenario": scenario,
            "run": run,
        }
        started = time.perf_counter()
        try:
            response = self.transport.invoke(component_request)
        except TransportError as exc:
            raise RuntimeAdapterError(str(exc)) from exc
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        observation_value = response.get("observation", response)
        if not isinstance(observation_value, Mapping):
            raise RuntimeAdapterError("component response observation must be an object")
        if not _OBSERVATION_FIELDS.intersection(observation_value):
            raise RuntimeAdapterError(
                "component response must return a benchmark observation or wrap one in 'observation'"
            )
        observation = dict(observation_value)
        observed_id = observation.get("scenario_id", scenario_id)
        if observed_id != scenario_id:
            raise RuntimeAdapterError(
                f"component returned scenario_id {observed_id!r} for {scenario_id!r}"
            )
        observation["scenario_id"] = scenario_id
        observation.setdefault("latency_ms", elapsed_ms)
        evidence = observation.setdefault("evidence", [])
        if not isinstance(evidence, list):
            raise RuntimeAdapterError("observation evidence must be an array")
        evidence.append(
            {
                "kind": "runtime_component",
                "component": self.profile.name,
                "transport": type(self.transport).__name__,
            }
        )
        return observation


def encode_observation(observation: Mapping[str, Any]) -> str:
    return json.dumps(observation, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
