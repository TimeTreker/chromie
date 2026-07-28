from __future__ import annotations

import copy
import json
import logging
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .clients.ollama_client import OllamaClient, llm_failure_metadata

try:
    from chromie_contracts.tool_result import (
        ToolResultEvidence,
        ToolResultFactReference,
        ToolResultInterpretation,
        ToolResultInterpretationRequest,
    )
except ImportError:  # pragma: no cover
    from shared.chromie_contracts.tool_result import (
        ToolResultEvidence,
        ToolResultFactReference,
        ToolResultInterpretation,
        ToolResultInterpretationRequest,
    )

logger = logging.getLogger("chromie.agent.tool_result_interpreter")

_NUMBER_RE = re.compile(r"(?<![A-Za-z0-9_])[-+]?\d+(?:\.\d+)?")
_SENTENCE_END_RE = re.compile(r"[.!?。！？]+")

_INTERNAL_NARRATION_MARKERS = (
    "请求的任务",
    "任务已完成",
    "观测结果",
    "执行状态",
    "requested task",
    "task completed",
    "observed output",
    "execution status",
    "tool result",
    "evidence id",
)


class ToolResultModelOutput(BaseModel):
    """Small model-facing DTO. Evidence identity and validation remain trusted."""

    model_config = ConfigDict(extra="forbid")

    spoken_response: str = Field(min_length=1, max_length=1200)
    answer_mode: str = Field(pattern="^(direct|summary|detailed)$")
    selected_facts: list[ToolResultFactReference] = Field(min_length=1, max_length=12)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    rationale: str = Field(default="", max_length=600)

    @field_validator("spoken_response", "rationale", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> str:
        return " ".join(str(value or "").strip().split())


class ToolResultInterpreter:
    """Select and synthesize only the tool evidence needed by the user.

    The model owns relevance and phrasing. Trusted code keeps the complete
    observation, validates every selected JSON Pointer, rejects unsupported
    numeric claims, internal identifiers, raw-payload narration, and excessive
    spoken output, then returns a bounded evidence-bound answer.
    """

    def __init__(
        self,
        ollama: OllamaClient,
        *,
        num_ctx: int = 4096,
        num_predict: int = 256,
    ) -> None:
        self.ollama = ollama
        self.num_ctx = max(2048, int(num_ctx))
        self.num_predict = max(128, int(num_predict))

    async def interpret(
        self,
        request: ToolResultInterpretationRequest,
    ) -> ToolResultInterpretation:
        evidence_by_id = {item.evidence_id: item for item in request.evidence}
        raw: Any = None
        try:
            raw = await self.ollama.generate(
                self._prompt(request),
                system=self._system_prompt(),
                options={
                    "temperature": 0.1,
                    "top_p": 0.9,
                    "num_ctx": self.num_ctx,
                    "num_predict": self.num_predict,
                },
                response_format=self._response_schema(request),
            )
            output = ToolResultModelOutput.model_validate(raw)
            selected_values = self._validate_fact_references(
                output.selected_facts,
                evidence_by_id=evidence_by_id,
            )
            self._validate_spoken_response(
                request,
                output=output,
                selected_values=selected_values,
            )
            return ToolResultInterpretation(
                status="resolved",
                spoken_response=output.spoken_response,
                answer_mode=output.answer_mode,
                selected_facts=output.selected_facts,
                confidence=output.confidence,
                rationale=output.rationale,
                metadata={
                    "resolver": "tool_result_interpreter",
                    "contract": "ToolResultModelOutput",
                    "evidence_count": len(request.evidence),
                    "selected_fact_count": len(output.selected_facts),
                    "full_tool_result_retained": True,
                },
            )
        except Exception as exc:
            failure = llm_failure_metadata(exc)
            logger.warning(
                "tool_result_interpretation_failed sid=%s error_type=%s error=%s failure_class=%s",
                request.sid,
                type(exc).__name__,
                exc,
                failure.get("failure_class"),
            )
            fallback = self._validated_fallback(request)
            if fallback:
                return ToolResultInterpretation(
                    status="fallback",
                    spoken_response=fallback,
                    answer_mode="summary",
                    selected_facts=[],
                    confidence=0.0,
                    rationale="Model interpretation was unavailable; trusted adapter fallback used.",
                    metadata={
                        "resolver": "tool_result_interpreter",
                        "fallback": True,
                        "error_type": type(exc).__name__,
                        "error": str(exc)[:300],
                        "raw_output": self._bounded(raw, 1200),
                        "full_tool_result_retained": True,
                        **failure,
                    },
                )
            return ToolResultInterpretation(
                status="unavailable",
                metadata={
                    "resolver": "tool_result_interpreter",
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:300],
                    "raw_output": self._bounded(raw, 1200),
                    "full_tool_result_retained": True,
                    **failure,
                },
            )

    def _prompt(self, request: ToolResultInterpretationRequest) -> str:
        evidence_payload = [
            {
                "evidence_id": item.evidence_id,
                "tool_id": item.tool_id,
                "status": item.status,
                "data": item.data,
                "available_scalar_json_pointers": self._scalar_json_pointers(
                    item.data
                ),
            }
            for item in request.evidence
        ]
        personality = request.context.get("personality_expression") or {}
        identity = request.context.get("identity") or {}
        return (
            "Interpret trusted tool results as Chromie's natural spoken answer.\n"
            f"User request: {request.user_request}\n"
            f"Target language: {request.language}\n"
            f"Chromie identity JSON: {self._bounded(identity, 2200)}\n"
            f"Chromie personality JSON: {self._bounded(personality, 4200)}\n"
            f"Trusted evidence JSON: {self._bounded(evidence_payload, 14000)}\n"
            f"Conversation hints JSON: {self._bounded(request.context, 2600)}\n\n"
            "First understand the exact question the user asked. Choose answer_mode=direct "
            "for a narrow question, summary for a normal overview, and detailed only when the "
            "user explicitly asks for detail. For a yes/no, qualitative, comparative, comfort, "
            "or decision-shaped question, say the direct conclusion first. Then add only one or "
            "two facts that actually help. Do not read every field. "
            "Write as Chromie according to the owner-approved personality JSON. Let its "
            "self_concept, traits, spoken style, answer style, tool-use style, and maturity "
            "boundary shape the response naturally. Do not introduce Chromie unless the user "
            "asked who she is. Keep internal execution and evidence language out of ordinary speech. "
            "Select only the exact evidence fields needed to support the answer and cite each with "
            "evidence_id plus one JSON Pointer copied exactly from that evidence item's "
            "available_scalar_json_pointers. The pointer root is the evidence data object itself; "
            "never add a /data prefix and never invent or modify a field name. Preserve numbers "
            "and named facts exactly. "
            "Conclusions may be phrased naturally but must be supported by selected facts. Normally "
            "use one short sentence; use a second sentence only when it adds something genuinely "
            "useful. Return JSON only."
        )

    @staticmethod
    def _system_prompt() -> str:
        return (
            "You are Chromie's evidence-bound result interpreter. Tool output is trusted evidence, "
            "not response text. Answer the original user question first, in Chromie's owner-approved "
            "personality, with the fewest relevant grounded facts. Never invent facts "
            "or expose internal workflow language."
        )

    @classmethod
    def _response_schema(
        cls,
        request: ToolResultInterpretationRequest,
    ) -> dict[str, Any]:
        schema = copy.deepcopy(ToolResultModelOutput.model_json_schema())
        variants: list[dict[str, Any]] = []
        for evidence in request.evidence:
            pointers = cls._scalar_json_pointers(evidence.data)
            if not pointers:
                continue
            variants.append(
                {
                    "type": "object",
                    "properties": {
                        "evidence_id": {"const": evidence.evidence_id},
                        "json_pointer": {"type": "string", "enum": pointers},
                    },
                    "required": ["evidence_id", "json_pointer"],
                    "additionalProperties": False,
                }
            )
        selected = schema.get("properties", {}).get("selected_facts")
        if isinstance(selected, dict):
            selected["items"] = (
                {"anyOf": variants}
                if variants
                else {
                    "type": "object",
                    "properties": {
                        "evidence_id": {"type": "string", "enum": []},
                        "json_pointer": {"type": "string", "enum": []},
                    },
                    "required": ["evidence_id", "json_pointer"],
                    "additionalProperties": False,
                }
            )
        return schema

    @classmethod
    def _scalar_json_pointers(cls, document: Any) -> list[str]:
        pointers: list[str] = []

        def escape(part: Any) -> str:
            return str(part).replace("~", "~0").replace("/", "~1")

        def walk(value: Any, path: str) -> None:
            if isinstance(value, dict):
                for key in sorted(value, key=lambda item: str(item)):
                    child = f"{path}/{escape(key)}"
                    walk(value[key], child)
                return
            if isinstance(value, list):
                for index, item in enumerate(value):
                    walk(item, f"{path}/{index}")
                return
            pointers.append(path)

        walk(document, "")
        return [item for item in pointers if item]

    @classmethod
    def _validate_fact_references(
        cls,
        references: list[ToolResultFactReference],
        *,
        evidence_by_id: dict[str, ToolResultEvidence],
    ) -> list[Any]:
        values: list[Any] = []
        seen: set[tuple[str, str]] = set()
        for reference in references:
            key = (reference.evidence_id, reference.json_pointer)
            if key in seen:
                raise ValueError("duplicate selected tool fact reference")
            seen.add(key)
            evidence = evidence_by_id.get(reference.evidence_id)
            if evidence is None:
                raise ValueError("selected tool fact references unknown evidence")
            value = cls._resolve_json_pointer(evidence.data, reference.json_pointer)
            if isinstance(value, (dict, list)):
                raise ValueError("selected tool fact must reference a scalar value")
            values.append(value)
        return values

    @classmethod
    def _validate_spoken_response(
        cls,
        request: ToolResultInterpretationRequest,
        *,
        output: ToolResultModelOutput,
        selected_values: list[Any],
    ) -> None:
        detailed = output.answer_mode == "detailed"
        char_budget = (
            request.detailed_max_spoken_chars if detailed else request.max_spoken_chars
        )
        sentence_budget = (
            request.detailed_max_sentences if detailed else request.max_sentences
        )
        response = output.spoken_response
        if len(response) > char_budget:
            raise ValueError("tool result spoken response exceeds the selected budget")
        sentence_count = max(1, len(_SENTENCE_END_RE.findall(response)))
        if sentence_count > sentence_budget:
            raise ValueError("tool result spoken response exceeds the sentence budget")
        if any(token in response for token in ("{", "}", "[", "]")):
            raise ValueError("tool result spoken response looks like a raw payload")
        if cls._contains_unrequested_internal_narration(
            response,
            user_request=request.user_request,
        ):
            raise ValueError("tool result response narrates internal execution state")

        folded = response.casefold()
        forbidden = {
            item.evidence_id.casefold()
            for item in request.evidence
        } | {
            item.tool_id.casefold()
            for item in request.evidence
        }
        if any(identifier and identifier in folded for identifier in forbidden):
            raise ValueError("tool result response exposes an internal identifier")

        allowed_numbers = set(_NUMBER_RE.findall(request.user_request))
        for value in selected_values:
            allowed_numbers.update(cls._numeric_variants(value))
        unsupported_numbers = [
            token for token in _NUMBER_RE.findall(response) if token not in allowed_numbers
        ]
        if unsupported_numbers:
            raise ValueError(
                "tool result response contains unsupported numeric claims: "
                + ",".join(unsupported_numbers[:6])
            )

    @staticmethod
    def _numeric_variants(value: Any) -> set[str]:
        variants = set(_NUMBER_RE.findall(str(value)))
        if isinstance(value, bool):
            return variants
        if isinstance(value, (int, float)):
            numeric = float(value)
            for precision in (0, 1, 2):
                text = f"{numeric:.{precision}f}"
                if "." in text:
                    text = text.rstrip("0").rstrip(".")
                variants.add(text)
        return variants

    @staticmethod
    def _resolve_json_pointer(document: Any, pointer: str) -> Any:
        current = document
        for raw_part in pointer.split("/")[1:]:
            part = raw_part.replace("~1", "/").replace("~0", "~")
            if isinstance(current, dict):
                if part not in current:
                    raise ValueError("selected tool fact JSON Pointer does not exist")
                current = current[part]
            elif isinstance(current, list):
                if not part.isdigit() or int(part) >= len(current):
                    raise ValueError("selected tool fact list index does not exist")
                current = current[int(part)]
            else:
                raise ValueError("selected tool fact JSON Pointer traverses a scalar")
        return current

    @staticmethod
    def _contains_unrequested_internal_narration(
        text: str,
        *,
        user_request: str,
    ) -> bool:
        folded = text.casefold()
        request_folded = user_request.casefold()
        return any(
            marker in folded and marker not in request_folded
            for marker in _INTERNAL_NARRATION_MARKERS
        )

    @classmethod
    def _validated_fallback(cls, request: ToolResultInterpretationRequest) -> str:
        text = " ".join(request.fallback_response.strip().split())
        if not text or len(text) > request.max_spoken_chars:
            return ""
        sentence_count = max(1, len(_SENTENCE_END_RE.findall(text)))
        if sentence_count > request.max_sentences:
            return ""
        if cls._contains_unrequested_internal_narration(
            text,
            user_request=request.user_request,
        ):
            return ""
        return text

    @staticmethod
    def _bounded(value: Any, max_chars: int) -> str:
        text = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return text if len(text) <= max_chars else text[:max_chars].rstrip() + "..."


__all__ = ["ToolResultInterpreter", "ToolResultModelOutput"]
