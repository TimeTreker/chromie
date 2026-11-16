"""Replay through the current production resolvers, without a Capability Runtime."""
from __future__ import annotations

import copy
import hashlib
import json
import time
from typing import Any

from jsonschema import Draft202012Validator

from .common import Rejected, digest, loads

STAGES = {
    "planner": {"fast_planner.primary", "fast_planner.evidence_reentry", "fast_planner.streaming_advance"},
    "social_cognition": {"social_cognition.primary", "social_cognition.deep", "social_cognition.startup_greeting"},
}
DECODING = {"temperature": "temperature", "top_p": "top_p", "num_predict": "max_tokens",
            "seed": "seed", "frequency_penalty": "frequency_penalty",
            "presence_penalty": "presence_penalty", "stop": "stop"}


def schema_order_hash(schema: dict[str, Any]) -> str:
    # Native decoder property order matters operationally. Artifact JSON is
    # canonicalized for storage, so preserve this additional ordered identity.
    return hashlib.sha256(json.dumps(schema, ensure_ascii=False, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def receipt_packet(receipt: dict[str, Any]) -> dict[str, Any]:
    if (receipt.get("event") != "chromie.llm_call_evidence" or receipt.get("schema_version") != 1
            or receipt.get("status") != "accepted" or receipt.get("error")):
        raise Rejected("unaccepted_receipt")
    request = receipt["request"]
    transport = receipt["transport"]
    if transport in {"sglang.chat", "sglang.chat_stream"}:
        schema = request.get("response_format", {}).get("json_schema", {}).get("schema")
        provider = receipt["response"]["provider_response"]
        from agent.app.clients.sglang_protocol import sglang_completion_content
        raw, finish = sglang_completion_content(provider)
        if finish != "stop":
            raise Rejected("incomplete_provider_output")
    elif transport in {"ollama.chat", "ollama.chat_stream"}:
        schema = request.get("format")
        provider = receipt["response"]["provider_response"]
        if provider.get("done") is not True or provider.get("done_reason") != "stop":
            raise Rejected("incomplete_provider_output")
        if provider.get("message", {}).get("thinking"):
            raise Rejected("thinking_not_training_target")
        raw = provider.get("message", {}).get("content")
    else:
        raise Rejected("unsupported_receipt_transport")
    if not isinstance(schema, dict) or not isinstance(raw, str):
        raise Rejected("complete_schema_and_raw_output_required")
    if raw != receipt["response"]["raw_model_output"]:
        raise Rejected("raw_output_mismatch")
    messages = request.get("messages")
    if (not isinstance(messages, list) or not messages
            or any(set(item) != {"role", "content"} or item["role"] not in {"system", "user"}
                   or not isinstance(item["content"], str) for item in messages)):
        raise Rejected("text_only_system_user_messages_required")
    output = loads(raw)
    Draft202012Validator.check_schema(schema)
    if not isinstance(output, dict) or not Draft202012Validator(schema).is_valid(output):
        raise Rejected("receipt_schema_failed")
    decoding = ({key: request[key] for key in DECODING.values() if key in request}
                if transport.startswith("sglang.") else
                {wire: request.get("options", {})[key] for key, wire in DECODING.items() if key in request.get("options", {})})
    return {"stage": receipt["stage"], "transport": transport, "messages": messages, "decoding": decoding,
            "schema": schema, "schema_order_sha256": schema_order_hash(schema), "completion": raw}


class SnapshotCatalog:
    def __init__(self, snapshot: dict[str, Any]):
        from agent.app.capabilities.catalog import CatalogCapability
        if set(snapshot) != {"all", "common", "index"}:
            raise Rejected("three_catalog_scopes_required")
        self.scopes = {scope: [CatalogCapability.model_validate(row) for row in rows]
                       for scope, rows in snapshot.items()}

    async def prompt_entries(self, *, scope: str, refresh: bool = False) -> list[Any]:
        if refresh:
            raise Rejected("live_catalog_refresh_forbidden")
        return copy.deepcopy(self.scopes[scope])


class BoundModel:
    """Verify inputs before reading a target or contacting an isolated candidate."""
    def __init__(self, calls: list[dict[str, Any]], candidate: Any = None):
        self.calls = calls
        self.candidate = candidate
        self.position = 0
        self.records: list[dict[str, Any]] = []

    def bind(self, prompt: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
        if self.position >= len(self.calls):
            raise Rejected("unexpected_model_call")
        expected = self.calls[self.position]
        self.position += 1
        rendered = prompt.render() if hasattr(prompt, "render") else str(prompt)
        messages = ([{"role": "system", "content": kwargs["system"]}] if kwargs.get("system") else [])
        messages.append({"role": "user", "content": rendered})
        schema = kwargs["response_format"]
        if expected["transport"].startswith("sglang."):
            from agent.app.clients.sglang_protocol import _openai_response_format
            schema = _openai_response_format(schema)["json_schema"]["schema"]
        if (messages != expected["messages"] or schema != expected["schema"]
                or schema_order_hash(schema) != expected["schema_order_sha256"]
                or kwargs.get("prompt_family") != expected["stage"]):
            raise Rejected("current_prompt_or_schema_mismatch")
        options = kwargs.get("options", {})
        decoding = {wire: options[key] for key, wire in DECODING.items() if key in options}
        if decoding != expected["decoding"]:
            raise Rejected("current_decoding_parameters_mismatch")
        if self.candidate is not None and hasattr(self.candidate, "compute_class"):
            from agent.app.inference_compute import compute_class_for_purpose
            purpose = ("fast_planner" if expected["stage"].startswith("fast_planner.") else
                       "social_cognition_deep" if expected["stage"] == "social_cognition.deep" else "social_cognition")
            self.candidate.purpose = purpose
            self.candidate.compute_class = compute_class_for_purpose(purpose)
        return expected

    async def generate(self, prompt: Any, **kwargs: Any) -> Any:
        expected = self.bind(prompt, kwargs)
        started = time.perf_counter()
        # Candidate receives only production arguments; never completion/review/rubric.
        output = (await self.candidate.generate(prompt, **kwargs) if self.candidate is not None
                  else loads(expected["completion"]))
        self.records.append({"input_sha256": digest({key: expected[key] for key in ("stage", "messages", "schema")}),
                             "output": output, "elapsed_ms": (time.perf_counter() - started) * 1000})
        return output

    async def generate_stream(self, prompt: Any, **kwargs: Any):
        expected = self.bind(prompt, kwargs)
        started = time.perf_counter()
        raw = ""
        if self.candidate is None:
            raw = expected["completion"]
            yield raw
        else:
            async for chunk in self.candidate.generate_stream(prompt, **kwargs):
                raw += chunk
                yield chunk
        self.records.append({"input_sha256": digest({key: expected[key] for key in ("stage", "messages", "schema")}),
                             "raw_output": raw, "elapsed_ms": (time.perf_counter() - started) * 1000})


async def replay(case: dict[str, Any], candidate: Any = None) -> dict[str, Any]:
    from agent.app.planner import PlannerResolver
    from agent.app.social_cognition import SocialCognitionResolver
    from shared.chromie_contracts.core_interpretation import CognitiveWorkRequest
    from shared.chromie_contracts.social_cognition import SocialCognitionRequest, SocialStartupGreetingRequest

    transaction = case["transaction"]
    role = transaction["role"]
    calls = case["calls"]
    if role not in STAGES or not calls or any(row["stage"] not in STAGES[role] for row in calls):
        raise Rejected("unsupported_current_role")
    model = BoundModel(calls, candidate)
    catalog = SnapshotCatalog(transaction["catalog"])
    settings = transaction.get("settings", {})
    if set(settings) - {"num_ctx", "num_predict"}:
        raise Rejected("unsupported_resolver_setting")
    if role == "planner":
        request = CognitiveWorkRequest.model_validate(transaction["request"])
        resolver = PlannerResolver(model, catalog, **settings)
        if transaction["variant"] == "streaming":
            frames = [frame async for frame in resolver.stream_advance(request)]
            if not frames or any(frame.frame_type == "failure" for frame in frames):
                raise Rejected("planner_stream_host_failed")
            result = [frame.model_dump(mode="json") for frame in frames]
            # The final frame must represent a complete validated decision.
            if frames[-1].frame_type != "terminal":
                raise Rejected("planner_stream_incomplete")
        elif transaction["variant"] == "canonical":
            plan = await resolver.resolve(request)
            if plan.metadata.get("path_classification") == "contract_failure":
                raise Rejected("planner_host_failed")
            result = plan.model_dump(mode="json")
        else:
            raise Rejected("unsupported_planner_variant")
    else:
        resolver = SocialCognitionResolver(model, catalog, deep_model=model, **settings)
        if transaction["variant"] == "startup":
            result = await resolver.resolve_startup_greeting(SocialStartupGreetingRequest.model_validate(transaction["request"]))
        elif transaction["variant"] == "interaction":
            result = await resolver.resolve(SocialCognitionRequest.model_validate(transaction["request"]))
        else:
            raise Rejected("unsupported_social_variant")
        result = result.model_dump(mode="json")
    if model.position != len(calls):
        raise Rejected("unused_or_changed_model_branch")
    # An offline resolver pass establishes DTO/Agent validation only. Host dispatch,
    # delivery and real effects remain separate workflow/live gates.
    return {"result": result, "calls": model.records, "verdict": "pass",
            "evidence_level": "offline_resolver_contract", "physical_evidence": False}
