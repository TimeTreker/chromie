from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from benchmarks.runtime_adapters.transports import (
    HttpJsonTransport,
    JsonTransport,
    PythonCallableTransport,
    TransportError,
)

from .evidence import load_partial_evidence
from .executor import E2EExecutionRecord, _response_record
from .profiles import EvidenceProfile, EvidenceProfileError


@dataclass(frozen=True)
class FirstPartyAdapterProfile:
    id: str
    evidence_profiles: tuple[str, ...]
    url_env: str
    callable_env: str
    description: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "FirstPartyAdapterProfile":
        adapter_id = value.get("id")
        evidence_profiles = value.get("evidence_profiles")
        url_env = value.get("url_env")
        callable_env = value.get("callable_env")
        description = value.get("description", "")
        if not isinstance(adapter_id, str) or not adapter_id.strip():
            raise EvidenceProfileError("E2E adapter id must be a non-empty string")
        if not isinstance(evidence_profiles, list) or not evidence_profiles or not all(
            isinstance(item, str) and item.strip() for item in evidence_profiles
        ):
            raise EvidenceProfileError(
                f"E2E adapter {adapter_id!r} evidence_profiles must be non-empty strings"
            )
        if not isinstance(url_env, str) or not url_env.strip():
            raise EvidenceProfileError(f"E2E adapter {adapter_id!r} url_env is required")
        if not isinstance(callable_env, str) or not callable_env.strip():
            raise EvidenceProfileError(
                f"E2E adapter {adapter_id!r} callable_env is required"
            )
        if not isinstance(description, str):
            raise EvidenceProfileError(
                f"E2E adapter {adapter_id!r} description must be a string"
            )
        return cls(
            id=adapter_id.strip(),
            evidence_profiles=tuple(item.strip() for item in evidence_profiles),
            url_env=url_env.strip(),
            callable_env=callable_env.strip(),
            description=description.strip(),
        )


@dataclass(frozen=True)
class FirstPartyAdapterManifest:
    profiles: tuple[FirstPartyAdapterProfile, ...]

    @classmethod
    def from_file(cls, path: Path) -> "FirstPartyAdapterManifest":
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise EvidenceProfileError(f"cannot load E2E adapter manifest {path}: {exc}") from exc
        if not isinstance(payload, Mapping) or payload.get("schema_version") != 1:
            raise EvidenceProfileError("E2E adapter manifest must use schema_version 1")
        values = payload.get("adapters")
        if not isinstance(values, list):
            raise EvidenceProfileError("E2E adapter manifest must contain adapters")
        profiles = tuple(FirstPartyAdapterProfile.from_mapping(item) for item in values)
        ids = [item.id for item in profiles]
        if len(ids) != len(set(ids)):
            raise EvidenceProfileError("E2E adapter manifest contains duplicate ids")
        return cls(profiles=profiles)

    def get(self, adapter_id: str) -> FirstPartyAdapterProfile:
        for profile in self.profiles:
            if profile.id == adapter_id:
                return profile
        supported = ", ".join(item.id for item in self.profiles)
        raise EvidenceProfileError(
            f"unknown first-party E2E adapter {adapter_id!r}; choose one of: {supported}"
        )


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)[:180]


@dataclass(frozen=True)
class FirstPartyE2EExecutor:
    adapter_profile: FirstPartyAdapterProfile
    transport: JsonTransport
    artifact_root: Path

    @classmethod
    def from_environment(
        cls,
        adapter_profile: FirstPartyAdapterProfile,
        *,
        timeout_s: float,
        artifact_root: Path,
        environment: Mapping[str, str] | None = None,
    ) -> "FirstPartyE2EExecutor":
        env = os.environ if environment is None else environment
        url = env.get(adapter_profile.url_env, "").strip()
        callable_spec = env.get(adapter_profile.callable_env, "").strip()
        if bool(url) == bool(callable_spec):
            raise EvidenceProfileError(
                f"configure exactly one of {adapter_profile.url_env} or "
                f"{adapter_profile.callable_env} for adapter {adapter_profile.id!r}"
            )
        try:
            transport: JsonTransport
            if url:
                transport = HttpJsonTransport(url=url, timeout_s=timeout_s)
            else:
                transport = PythonCallableTransport(callable_spec=callable_spec)
        except TransportError as exc:
            raise EvidenceProfileError(str(exc)) from exc
        return cls(
            adapter_profile=adapter_profile,
            transport=transport,
            artifact_root=artifact_root,
        )

    def execute(
        self,
        scenario: Mapping[str, Any],
        run: Mapping[str, Any],
        profile: EvidenceProfile,
    ) -> E2EExecutionRecord:
        scenario_id = str(scenario["id"])
        correlation_id = str(run["correlation_id"])
        if profile.id not in self.adapter_profile.evidence_profiles:
            return E2EExecutionRecord(
                scenario_id=scenario_id,
                correlation_id=correlation_id,
                execution_state="adapter_error",
                observation=None,
                evidence=(),
                timing={},
                execution_claims=(),
                artifacts=(),
                error=(
                    f"first-party adapter {self.adapter_profile.id!r} does not support "
                    f"evidence profile {profile.id!r}"
                ),
            )

        scenario_dir = self.artifact_root / _safe_name(scenario_id)
        scenario_dir.mkdir(parents=True, exist_ok=True)
        partial_path = scenario_dir / "partial_evidence.jsonl"
        request_path = scenario_dir / "adapter_request.json"
        response_path = scenario_dir / "adapter_response.json"
        request_payload = {
            "schema_version": 1,
            "adapter": {
                "id": self.adapter_profile.id,
                "description": self.adapter_profile.description,
            },
            "scenario": scenario,
            "run": dict(run),
            "evidence_profile": profile.to_dict(),
            "artifact_dir": str(scenario_dir.resolve()),
            "partial_evidence_path": str(partial_path.resolve()),
        }
        request_path.write_text(
            json.dumps(request_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        try:
            response = self.transport.invoke(request_payload)
            response_path.write_text(
                json.dumps(response, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            partial = load_partial_evidence(partial_path)
            return _response_record(
                scenario_id=scenario_id,
                correlation_id=correlation_id,
                payload=response,
                partial=partial,
                artifacts=(str(request_path), str(response_path), str(partial_path)),
            )
        except (TransportError, EvidenceProfileError, OSError) as exc:
            try:
                partial = load_partial_evidence(partial_path)
            except EvidenceProfileError:
                partial = ()
            return E2EExecutionRecord(
                scenario_id=scenario_id,
                correlation_id=correlation_id,
                execution_state="adapter_error",
                observation=None,
                evidence=partial,
                timing={},
                execution_claims=(),
                artifacts=(str(request_path), str(response_path), str(partial_path)),
                error=str(exc),
                partial_evidence_retained=bool(partial),
            )
