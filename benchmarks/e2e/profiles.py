from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


class EvidenceProfileError(ValueError):
    """Raised when an E2E evidence profile is malformed or misused."""


EVIDENCE_LEVELS = frozenset(
    {"replay", "live_model", "live_service", "simulated", "physical"}
)
TRANSPORTS = frozenset({"replay", "command"})
INPUT_MODES = frozenset({"text", "virtual_audio", "physical_audio"})
EMBODIMENTS = frozenset({"none", "simulated", "physical"})
SUPERVISION_MODES = frozenset({"automatic", "operator_required"})
CLAIM_MINIMUM_LEVEL = {
    "replayed_contract": "replay",
    "model_output": "live_model",
    "deployed_service_execution": "live_service",
    "audio_pipeline_execution": "live_service",
    "simulated_provider_execution": "simulated",
    "physical_provider_execution": "physical",
}


@dataclass(frozen=True)
class EvidenceProfile:
    id: str
    evidence_level: str
    transport: str
    input_mode: str
    embodiment: str
    supervision: str
    allowed_execution_claims: tuple[str, ...]
    required_evidence: tuple[str, ...]
    required_timing_markers: tuple[str, ...]
    requires_safe_idle: bool
    human_approval_required: bool
    description: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "EvidenceProfile":
        profile_id = value.get("id")
        if not isinstance(profile_id, str) or not profile_id.strip():
            raise EvidenceProfileError("evidence profile id must be a non-empty string")
        evidence_level = value.get("evidence_level")
        transport = value.get("transport")
        input_mode = value.get("input_mode")
        embodiment = value.get("embodiment")
        supervision = value.get("supervision")
        if evidence_level not in EVIDENCE_LEVELS:
            raise EvidenceProfileError(f"profile {profile_id!r} has invalid evidence_level")
        if transport not in TRANSPORTS:
            raise EvidenceProfileError(f"profile {profile_id!r} has invalid transport")
        if input_mode not in INPUT_MODES:
            raise EvidenceProfileError(f"profile {profile_id!r} has invalid input_mode")
        if embodiment not in EMBODIMENTS:
            raise EvidenceProfileError(f"profile {profile_id!r} has invalid embodiment")
        if supervision not in SUPERVISION_MODES:
            raise EvidenceProfileError(f"profile {profile_id!r} has invalid supervision")

        def string_tuple(key: str) -> tuple[str, ...]:
            raw = value.get(key, [])
            if not isinstance(raw, list) or not all(
                isinstance(item, str) and item.strip() for item in raw
            ):
                raise EvidenceProfileError(
                    f"profile {profile_id!r} field {key} must be an array of strings"
                )
            if len(set(raw)) != len(raw):
                raise EvidenceProfileError(
                    f"profile {profile_id!r} field {key} contains duplicates"
                )
            return tuple(raw)

        claims = string_tuple("allowed_execution_claims")
        for claim in claims:
            minimum = CLAIM_MINIMUM_LEVEL.get(claim)
            if minimum is None:
                raise EvidenceProfileError(
                    f"profile {profile_id!r} declares unknown execution claim {claim!r}"
                )
            if claim == "physical_provider_execution" and evidence_level != "physical":
                raise EvidenceProfileError(
                    f"profile {profile_id!r} cannot make a physical execution claim"
                )
            if claim == "simulated_provider_execution" and evidence_level != "simulated":
                raise EvidenceProfileError(
                    f"profile {profile_id!r} cannot make a simulator execution claim"
                )

        requires_safe_idle = value.get("requires_safe_idle", False)
        human_approval_required = value.get("human_approval_required", True)
        if not isinstance(requires_safe_idle, bool) or not isinstance(
            human_approval_required, bool
        ):
            raise EvidenceProfileError(
                f"profile {profile_id!r} boolean fields are malformed"
            )
        description = value.get("description", "")
        if not isinstance(description, str) or not description.strip():
            raise EvidenceProfileError(
                f"profile {profile_id!r} description must be non-empty"
            )
        profile = cls(
            id=profile_id,
            evidence_level=evidence_level,
            transport=transport,
            input_mode=input_mode,
            embodiment=embodiment,
            supervision=supervision,
            allowed_execution_claims=claims,
            required_evidence=string_tuple("required_evidence"),
            required_timing_markers=string_tuple("required_timing_markers"),
            requires_safe_idle=requires_safe_idle,
            human_approval_required=human_approval_required,
            description=description,
        )
        profile._validate_cross_fields()
        return profile

    def _validate_cross_fields(self) -> None:
        if self.transport == "replay" and self.evidence_level != "replay":
            raise EvidenceProfileError(
                f"replay transport profile {self.id!r} must use replay evidence"
            )
        if self.evidence_level == "physical":
            if self.embodiment != "physical" or self.supervision != "operator_required":
                raise EvidenceProfileError(
                    f"physical profile {self.id!r} requires physical embodiment and operator supervision"
                )
            if not self.human_approval_required:
                raise EvidenceProfileError(
                    f"physical profile {self.id!r} must require human approval"
                )
        if self.evidence_level == "simulated" and self.embodiment != "simulated":
            raise EvidenceProfileError(
                f"simulated profile {self.id!r} must declare simulated embodiment"
            )
        if self.requires_safe_idle and "safe_idle" not in self.required_evidence:
            raise EvidenceProfileError(
                f"profile {self.id!r} requires safe idle but not safe_idle evidence"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "evidence_level": self.evidence_level,
            "transport": self.transport,
            "input_mode": self.input_mode,
            "embodiment": self.embodiment,
            "supervision": self.supervision,
            "allowed_execution_claims": list(self.allowed_execution_claims),
            "required_evidence": list(self.required_evidence),
            "required_timing_markers": list(self.required_timing_markers),
            "requires_safe_idle": self.requires_safe_idle,
            "human_approval_required": self.human_approval_required,
            "description": self.description,
        }


@dataclass(frozen=True)
class EvidenceProfileManifest:
    schema_version: int
    profiles: tuple[EvidenceProfile, ...]

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "EvidenceProfileManifest":
        if value.get("schema_version") != 1:
            raise EvidenceProfileError("E2E evidence profile manifest must use schema_version 1")
        raw_profiles = value.get("profiles")
        if not isinstance(raw_profiles, list) or not raw_profiles:
            raise EvidenceProfileError("E2E evidence profile manifest must contain profiles")
        profiles = tuple(
            EvidenceProfile.from_mapping(item)
            for item in raw_profiles
            if isinstance(item, Mapping)
        )
        if len(profiles) != len(raw_profiles):
            raise EvidenceProfileError("every E2E evidence profile must be an object")
        ids = [item.id for item in profiles]
        if len(set(ids)) != len(ids):
            raise EvidenceProfileError("E2E evidence profile IDs must be unique")
        return cls(schema_version=1, profiles=profiles)

    @classmethod
    def from_file(cls, path: Path) -> "EvidenceProfileManifest":
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise EvidenceProfileError(f"cannot load E2E evidence profile manifest {path}: {exc}") from exc
        if not isinstance(payload, Mapping):
            raise EvidenceProfileError("E2E evidence profile manifest must be an object")
        return cls.from_mapping(payload)

    def get(self, profile_id: str) -> EvidenceProfile:
        for profile in self.profiles:
            if profile.id == profile_id:
                return profile
        choices = ", ".join(item.id for item in self.profiles)
        raise EvidenceProfileError(
            f"unknown E2E evidence profile {profile_id!r}; choose one of: {choices}"
        )
