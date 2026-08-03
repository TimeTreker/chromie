from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import time
from typing import Any, Callable, Mapping
from urllib import error, request

from benchmarks.contracts import ContractError

VALID_PROTOCOLS = frozenset(
    {"openai_responses", "openai_chat_completions", "anthropic_messages"}
)
VALID_CONSENSUS_POLICIES = frozenset({"majority", "unanimous", "conservative"})
_RESERVED_BODY_KEYS = frozenset(
    {"model", "input", "instructions", "messages", "system", "stream"}
)
_RESERVED_HEADER_KEYS = frozenset(
    {"authorization", "content-type", "x-api-key", "anthropic-version"}
)


@dataclass(frozen=True)
class ReviewerProfile:
    reviewer_id: str
    protocol: str
    base_url: str
    model: str
    model_family: str
    api_key_env: str
    enabled: bool = True
    timeout_s: float = 180.0
    max_output_tokens: int = 4096
    temperature: float | None = None
    anthropic_version: str = "2023-06-01"
    extra_headers: Mapping[str, str] = field(default_factory=dict)
    extra_body: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.reviewer_id.strip():
            raise ContractError("semantic reviewer id must not be empty")
        safe_characters = (
            "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_."
        )
        if any(char not in safe_characters for char in self.reviewer_id):
            raise ContractError(
                f"semantic reviewer id contains unsafe characters: {self.reviewer_id!r}"
            )
        if self.protocol not in VALID_PROTOCOLS:
            raise ContractError(
                f"semantic reviewer {self.reviewer_id!r} has unknown protocol "
                f"{self.protocol!r}"
            )
        if not self.base_url.startswith(("https://", "http://")):
            raise ContractError(
                f"semantic reviewer {self.reviewer_id!r} base_url must be HTTP(S)"
            )
        if not self.model.strip():
            raise ContractError(
                f"semantic reviewer {self.reviewer_id!r} requires a model"
            )
        if not self.model_family.strip():
            raise ContractError(
                f"semantic reviewer {self.reviewer_id!r} requires model_family"
            )
        if not self.api_key_env.strip():
            raise ContractError(
                f"semantic reviewer {self.reviewer_id!r} requires api_key_env"
            )
        if self.timeout_s <= 0:
            raise ContractError(
                f"semantic reviewer {self.reviewer_id!r} timeout_s must be positive"
            )
        if self.max_output_tokens <= 0:
            raise ContractError(
                f"semantic reviewer {self.reviewer_id!r} max_output_tokens "
                "must be positive"
            )
        if self.temperature is not None and not 0 <= self.temperature <= 2:
            raise ContractError(
                f"semantic reviewer {self.reviewer_id!r} temperature must be in [0, 2]"
            )
        forbidden_headers = sorted(
            key for key in self.extra_headers if key.lower() in _RESERVED_HEADER_KEYS
        )
        if forbidden_headers:
            raise ContractError(
                f"semantic reviewer {self.reviewer_id!r} extra_headers override "
                f"reserved keys: {', '.join(forbidden_headers)}"
            )
        forbidden_body = sorted(set(self.extra_body) & _RESERVED_BODY_KEYS)
        if forbidden_body:
            raise ContractError(
                f"semantic reviewer {self.reviewer_id!r} extra_body overrides "
                f"reserved keys: {', '.join(forbidden_body)}"
            )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ReviewerProfile":
        allowed = {
            "id",
            "enabled",
            "protocol",
            "base_url",
            "model",
            "model_family",
            "api_key_env",
            "timeout_s",
            "max_output_tokens",
            "temperature",
            "anthropic_version",
            "extra_headers",
            "extra_body",
        }
        unknown = sorted(set(value) - allowed)
        if unknown:
            raise ContractError(
                "semantic reviewer contains unknown keys: " + ", ".join(unknown)
            )
        extra_headers = value.get("extra_headers") or {}
        extra_body = value.get("extra_body") or {}
        if not isinstance(extra_headers, Mapping):
            raise ContractError("semantic reviewer extra_headers must be an object")
        if not isinstance(extra_body, Mapping):
            raise ContractError("semantic reviewer extra_body must be an object")
        enabled = value.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ContractError("semantic reviewer enabled must be boolean")
        temperature = value.get("temperature")
        if temperature is not None and not isinstance(temperature, (int, float)):
            raise ContractError("semantic reviewer temperature must be numeric or null")
        return cls(
            reviewer_id=str(value.get("id") or "").strip(),
            protocol=str(value.get("protocol") or "").strip(),
            base_url=str(value.get("base_url") or "").rstrip("/"),
            model=str(value.get("model") or "").strip(),
            model_family=str(value.get("model_family") or "").strip(),
            api_key_env=str(value.get("api_key_env") or "").strip(),
            enabled=enabled,
            timeout_s=float(value.get("timeout_s", 180.0)),
            max_output_tokens=int(value.get("max_output_tokens", 4096)),
            temperature=float(temperature) if temperature is not None else None,
            anthropic_version=str(
                value.get("anthropic_version") or "2023-06-01"
            ).strip(),
            extra_headers={str(key): str(item) for key, item in extra_headers.items()},
            extra_body=dict(extra_body),
        )

    def public_metadata(self) -> dict[str, Any]:
        return {
            "reviewer_id": self.reviewer_id,
            "protocol": self.protocol,
            "base_url": self.base_url,
            "model": self.model,
            "model_family": self.model_family,
            "api_key_env": self.api_key_env,
            "timeout_s": self.timeout_s,
            "max_output_tokens": self.max_output_tokens,
            "temperature": self.temperature,
        }


@dataclass(frozen=True)
class ReviewerConfiguration:
    profiles: tuple[ReviewerProfile, ...]
    consensus_policy: str = "majority"
    minimum_reviewers: int = 2
    minimum_model_families: int = 1

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ReviewerConfiguration":
        unknown = sorted(set(value) - {"schema_version", "reviewers", "consensus"})
        if unknown:
            raise ContractError(
                "semantic reviewer configuration contains unknown keys: "
                + ", ".join(unknown)
            )
        if value.get("schema_version") != 1:
            raise ContractError(
                "semantic reviewer configuration must use schema_version 1"
            )
        raw_profiles = value.get("reviewers")
        if not isinstance(raw_profiles, list):
            raise ContractError(
                "semantic reviewer configuration requires reviewers array"
            )
        profiles = tuple(
            ReviewerProfile.from_mapping(item)
            for item in raw_profiles
            if isinstance(item, Mapping)
        )
        if len(profiles) != len(raw_profiles):
            raise ContractError("semantic reviewer entries must be objects")
        ids = [profile.reviewer_id for profile in profiles]
        duplicates = sorted({item for item in ids if ids.count(item) > 1})
        if duplicates:
            raise ContractError(
                "duplicate semantic reviewer ids: " + ", ".join(duplicates)
            )
        consensus = value.get("consensus") or {}
        if not isinstance(consensus, Mapping):
            raise ContractError("semantic reviewer consensus must be an object")
        unknown_consensus = sorted(
            set(consensus)
            - {"policy", "minimum_reviewers", "minimum_model_families"}
        )
        if unknown_consensus:
            raise ContractError(
                "semantic reviewer consensus contains unknown keys: "
                + ", ".join(unknown_consensus)
            )
        policy = str(consensus.get("policy") or "majority").strip()
        if policy not in VALID_CONSENSUS_POLICIES:
            raise ContractError(f"unknown semantic consensus policy: {policy}")
        minimum = int(consensus.get("minimum_reviewers", 2))
        if minimum <= 0:
            raise ContractError("consensus.minimum_reviewers must be positive")
        minimum_families = int(consensus.get("minimum_model_families", 1))
        if minimum_families <= 0:
            raise ContractError(
                "consensus.minimum_model_families must be positive"
            )
        if minimum_families > minimum:
            raise ContractError(
                "consensus.minimum_model_families cannot exceed "
                "minimum_reviewers"
            )
        return cls(
            profiles=profiles,
            consensus_policy=policy,
            minimum_reviewers=minimum,
            minimum_model_families=minimum_families,
        )

    @classmethod
    def from_path(cls, path: Path) -> "ReviewerConfiguration":
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ContractError(
                f"cannot load semantic reviewer config {path}: {exc}"
            ) from exc
        if not isinstance(payload, Mapping):
            raise ContractError(f"{path}: expected a JSON object")
        return cls.from_mapping(payload)

    def selected(
        self, reviewer_ids: set[str] | None = None
    ) -> tuple[ReviewerProfile, ...]:
        profiles = tuple(profile for profile in self.profiles if profile.enabled)
        if reviewer_ids:
            known = {profile.reviewer_id for profile in self.profiles}
            unknown = sorted(reviewer_ids - known)
            if unknown:
                raise ContractError(
                    "unknown semantic reviewer ids: " + ", ".join(unknown)
                )
            profiles = tuple(
                profile for profile in profiles if profile.reviewer_id in reviewer_ids
            )
        if not profiles:
            raise ContractError("no enabled semantic reviewers were selected")
        return profiles


@dataclass(frozen=True)
class ProviderResponse:
    text: str
    request_id: str | None
    returned_model: str | None
    latency_ms: int
    raw_payload: Mapping[str, Any]


HttpTransport = Callable[[request.Request, float], tuple[int, Mapping[str, str], bytes]]


def _default_transport(
    outbound: request.Request, timeout_s: float
) -> tuple[int, Mapping[str, str], bytes]:
    try:
        with request.urlopen(outbound, timeout=timeout_s) as response:
            return response.status, dict(response.headers.items()), response.read()
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise ContractError(
            f"semantic reviewer HTTP {exc.code}: {body[:2000]}"
        ) from exc
    except (error.URLError, TimeoutError, OSError) as exc:
        raise ContractError(f"semantic reviewer request failed: {exc}") from exc


def _request_payload(
    profile: ReviewerProfile, *, system_prompt: str, user_prompt: str
) -> tuple[str, dict[str, str], dict[str, Any]]:
    headers = {"Content-Type": "application/json", **dict(profile.extra_headers)}
    if profile.protocol == "openai_responses":
        endpoint = f"{profile.base_url}/responses"
        body: dict[str, Any] = {
            "model": profile.model,
            "instructions": system_prompt,
            "input": user_prompt,
            "max_output_tokens": profile.max_output_tokens,
            **dict(profile.extra_body),
        }
    elif profile.protocol == "openai_chat_completions":
        endpoint = f"{profile.base_url}/chat/completions"
        body = {
            "model": profile.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "max_tokens": profile.max_output_tokens,
            **dict(profile.extra_body),
        }
    else:
        endpoint = f"{profile.base_url}/messages"
        headers["anthropic-version"] = profile.anthropic_version
        body = {
            "model": profile.model,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
            "max_tokens": profile.max_output_tokens,
            **dict(profile.extra_body),
        }
    if profile.temperature is not None:
        body["temperature"] = profile.temperature
    return endpoint, headers, body


def _extract_text(profile: ReviewerProfile, payload: Mapping[str, Any]) -> str:
    if profile.protocol == "openai_responses":
        direct = payload.get("output_text")
        if isinstance(direct, str) and direct.strip():
            return direct.strip()
        fragments: list[str] = []
        output = payload.get("output")
        if isinstance(output, list):
            for item in output:
                if not isinstance(item, Mapping):
                    continue
                content = item.get("content")
                if not isinstance(content, list):
                    continue
                for part in content:
                    if isinstance(part, Mapping) and isinstance(part.get("text"), str):
                        fragments.append(str(part["text"]))
        if fragments:
            return "\n".join(fragments).strip()
    elif profile.protocol == "openai_chat_completions":
        choices = payload.get("choices")
        if isinstance(choices, list) and choices and isinstance(choices[0], Mapping):
            message = choices[0].get("message")
            if isinstance(message, Mapping) and isinstance(message.get("content"), str):
                return str(message["content"]).strip()
    else:
        content = payload.get("content")
        if isinstance(content, list):
            fragments = [
                str(item["text"])
                for item in content
                if isinstance(item, Mapping) and isinstance(item.get("text"), str)
            ]
            if fragments:
                return "\n".join(fragments).strip()
    raise ContractError(
        f"semantic reviewer {profile.reviewer_id!r} returned no textual response"
    )


def invoke_reviewer(
    profile: ReviewerProfile,
    *,
    system_prompt: str,
    user_prompt: str,
    environment: Mapping[str, str] | None = None,
    transport: HttpTransport | None = None,
) -> ProviderResponse:
    env = os.environ if environment is None else environment
    api_key = str(env.get(profile.api_key_env) or "").strip()
    if not api_key:
        raise ContractError(
            f"semantic reviewer {profile.reviewer_id!r} requires environment "
            f"variable {profile.api_key_env}"
        )
    endpoint, headers, body = _request_payload(
        profile, system_prompt=system_prompt, user_prompt=user_prompt
    )
    if profile.protocol == "anthropic_messages":
        headers["x-api-key"] = api_key
    else:
        headers["Authorization"] = f"Bearer {api_key}"
    outbound = request.Request(
        endpoint,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    started = time.monotonic()
    status, response_headers, raw = (transport or _default_transport)(
        outbound, profile.timeout_s
    )
    latency_ms = int((time.monotonic() - started) * 1000)
    if not 200 <= status < 300:
        raise ContractError(
            f"semantic reviewer {profile.reviewer_id!r} returned HTTP {status}"
        )
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractError(
            f"semantic reviewer {profile.reviewer_id!r} returned invalid JSON envelope"
        ) from exc
    if not isinstance(payload, Mapping):
        raise ContractError(
            f"semantic reviewer {profile.reviewer_id!r} response must be an object"
        )
    request_id = response_headers.get("x-request-id") or response_headers.get(
        "request-id"
    )
    returned_model = payload.get("model")
    return ProviderResponse(
        text=_extract_text(profile, payload),
        request_id=str(request_id) if request_id else None,
        returned_model=str(returned_model) if returned_model else None,
        latency_ms=latency_ms,
        raw_payload=dict(payload),
    )
