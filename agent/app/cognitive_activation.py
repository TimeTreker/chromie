from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

try:
    from chromie_contracts.cognitive_activation import (
        CognitiveActivationContext,
        CognitiveActivationDecision,
    )
except ImportError:  # pragma: no cover
    from shared.chromie_contracts.cognitive_activation import (
        CognitiveActivationContext,
        CognitiveActivationDecision,
    )

from .clients.ollama_client import OllamaClient


COGNITIVE_ACTIVATION_AUTHORITY_PROMPT = """You are Chromie's Cognitive Activation authority.
You do not interpret a new user utterance, change Goal meaning, plan Work, select a
Capability, author speech, or claim that any effect completed. You receive one trusted
state transition plus bounded current state. Decide only whether one or more of the
explicitly allowed existing cognitive authorities should run now.

Request Planner only when the current Goal/Work/Evidence/Situation state makes a new HOW
or remaining-Work decision useful. Do not request Planner merely because an event happened,
a Goal exists, or an earlier Plan exists. A fresh trusted terminal result for an open
information Responsibility is materially new state: acquisition completion is not the same
as delivering the requested information. Request Planner when it must decide whether that
Evidence satisfies the information Goal, establish the resulting answer obligation, or plan
remaining Work. Do not request it when supplied state already establishes that the Goal is
closed and its required delivery is complete. Request Social Cognition only when the trusted
current situation makes a new human interaction decision useful. Use [] when no further
cognition is warranted. Preserve the exact Goal, Responsibility, and source scopes supplied
by the request. Return only the supplied JSON schema.
"""


class CognitiveActivationResolver:
    def __init__(
        self,
        model: OllamaClient,
        *,
        num_ctx: int = 4096,
        num_predict: int = 384,
    ) -> None:
        self.model = model
        self.num_ctx = max(2048, int(num_ctx))
        self.num_predict = max(128, int(num_predict))

    @staticmethod
    def response_schema(request: CognitiveActivationContext) -> dict[str, Any]:
        schema = CognitiveActivationDecision.model_json_schema()
        props = schema.get("properties", {})
        props["cognitive_requests"]["maxItems"] = len(request.allowed_authorities)
        selection = schema.get("$defs", {}).get("CognitiveActivationSelection")
        if isinstance(selection, dict):
            selection_props = selection.get("properties", {})
            authority = selection_props.get("authority")
            if isinstance(authority, dict):
                authority["enum"] = list(request.allowed_authorities)
            for field, values in (
                ("goal_ids", request.goal_ids),
                ("responsibility_refs", request.responsibility_refs),
                ("source_refs", request.source_refs),
            ):
                node = selection_props.get(field)
                if not isinstance(node, dict):
                    continue
                # Activation may choose whether an existing authority runs, but it
                # may not choose or abbreviate the trusted scope.  Make the exact
                # Host-supplied arrays decoder-visible rather than relying on DTO
                # defaults plus a later Host rejection.
                node.clear()
                node.update({"type": "array", "const": list(values)})
            selection["required"] = [
                "authority",
                "goal_ids",
                "responsibility_refs",
                "source_refs",
                "reason_summary",
            ]
        schema["required"] = ["cognitive_requests", "confidence", "reason_summary"]
        return schema

    async def resolve(
        self, request: CognitiveActivationContext
    ) -> CognitiveActivationDecision:
        request = request.model_copy(deep=True)
        schema = self.response_schema(request)
        prompt = (
            "Trusted activation packet JSON:\n"
            + json.dumps(
                request.model_dump(mode="json"),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\nReturn the cognitive activation decision only."
        )
        raw = await self.model.generate(
            prompt,
            system=COGNITIVE_ACTIVATION_AUTHORITY_PROMPT,
            options={
                "temperature": 0,
                "top_p": 0.9,
                "num_ctx": self.num_ctx,
                "num_predict": self.num_predict,
            },
            response_format=schema,
            prompt_family="cognitive_activation.primary",
            turn_id=request.request_id,
            attempt=1,
        )
        try:
            decision = CognitiveActivationDecision.model_validate(raw)
        except ValidationError as exc:
            raise ValueError(f"Cognitive Activation output invalid: {exc}") from exc
        return decision.validate_request(request)
