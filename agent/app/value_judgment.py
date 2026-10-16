"""Value Judgment resolver: whether Chromie should act, never how (owner amendment 2026-10-10).

One bounded model call. Inputs: the person's words, the accepted Responsibilities, what Chromie
currently perceives, and the full owner-approved Stable Mind. The output states who is affected
and the concern before the decision. The prompt is the v2 version qualified on frozen
production requests (`.chromie/acceptance/value-judgment-20261010/`: 11/11 risky unseen
requests stopped).
"""
from __future__ import annotations

import json
import logging
from typing import Any

from .clients.ollama_client import OllamaClient, OllamaGenerationError, llm_failure_metadata

from shared.chromie_contracts.core_interpretation import CognitiveWorkRequest
from shared.chromie_contracts.value_judgment import ValueJudgmentModelOutput, ValueJudgmentResult

logger = logging.getLogger("chromie.agent.value_judgment")

VALUE_JUDGMENT_SYSTEM_PROMPT = (
    "You are Chromie's conscience: the part of Chromie that decides whether Chromie should act on "
    "a request at all, before anyone decides how. You never plan, choose skills or write what "
    "Chromie says. Judge from Chromie's own identity, worldview, core principles and household "
    "values, the person's exact words, what Chromie understood they want, and what Chromie "
    "perceives. Write three facts in order before the decision. affected: who besides the person "
    "asking the action would touch - nobody_else; family_member; another_adult; child; stranger; "
    "or owner_unknown when it uses or moves something whose owner is not clear. concern: the main "
    "value concern, or none - others_property (using or taking what belongs to someone else), "
    "privacy (watching, following, recording or entering someone's space), consent (touching or "
    "approaching someone who has not agreed), deception (lying, pretending, hiding something from "
    "someone), harm_risk (risk to a person's body or health, especially a child's), "
    "irreversible, rules_or_law, family_conflict. decision: proceed when there is no concern or "
    "the words and context already settle it, such as the person's own or family belongings or a "
    "family member who wants it - most requests are ordinary and proceed. ask when acting could "
    "be fine but one missing fact decides it, such as whose it is or whether someone agreed; "
    "Chromie asks before acting. decline when the request itself asks for something wrong that no "
    "answer could make right: deceiving or manipulating someone, taking or using someone else's "
    "things without permission or in secret, frightening or endangering a person, putting a child "
    "at risk, or intruding on someone's privacy. reason: one short sentence in English. Return only "
    "the JSON object."
)


def value_judgment_facts(request: CognitiveWorkRequest) -> dict[str, Any]:
    context = request.context if isinstance(request.context, dict) else {}
    situation = context.get("situation") if isinstance(context.get("situation"), dict) else {}
    perceived = [
        item.get("value") for item in situation.get("interpretations") or []
        if isinstance(item, dict) and item.get("epistemic_status") == "established" and item.get("value")
    ]
    return {
        "person_said": request.text,
        "understood_requests": [
            item.model_dump(mode="json", include={"local_ref", "outcome", "output_mode", "body_effect_family", "bindings"})
            for item in request.responsibilities
        ],
        "chromie_perceives": perceived[:12],
    }


class ValueJudgmentResolver:
    def __init__(self, ollama: OllamaClient, *, num_ctx: int = 32768, num_predict: int = 256) -> None:
        self.ollama = ollama
        self.num_ctx = max(4096, int(num_ctx))
        self.num_predict = max(64, int(num_predict))

    def prompt(self, request: CognitiveWorkRequest) -> str:
        context = request.context if isinstance(request.context, dict) else {}
        mind = context.get("mind")
        if not isinstance(mind, dict) or mind.get("owner_approved") is not True:
            raise ValueError("Value Judgment requires the owner-approved Stable Mind")
        return (
            "Chromie's owner-approved Stable Mind JSON:\n" + json.dumps(mind, ensure_ascii=False)
            + "\n\nCurrent request facts JSON:\n" + json.dumps(value_judgment_facts(request), ensure_ascii=False)
            + "\n\nShould Chromie act on this request?"
        )

    async def resolve(self, request: CognitiveWorkRequest) -> ValueJudgmentResult:
        try:
            raw = await self.ollama.generate(
                self.prompt(request),
                system=VALUE_JUDGMENT_SYSTEM_PROMPT,
                options={"temperature": 0, "top_p": 0.9, "num_ctx": self.num_ctx, "num_predict": self.num_predict},
                response_format=ValueJudgmentModelOutput.model_json_schema(),
                prompt_family="value_judgment.primary",
                turn_id=request.sid,
                attempt=1,
            )
            judgment = ValueJudgmentModelOutput.model_validate(raw)
        except Exception as exc:  # noqa: BLE001 - every failure withholds reviewed effects
            failure = llm_failure_metadata(exc) if isinstance(exc, OllamaGenerationError) else {
                "failure_class": "value_judgment_contract_invalid", "failure_domain": "model_contract"}
            logger.warning("value_judgment_fail_closed sid=%s error_type=%s error=%s",
                           request.sid, type(exc).__name__, str(exc)[:300])
            return ValueJudgmentResult(status="failed", failure_class=str(failure["failure_class"]),
                                       reason=str(exc)[:500], metadata={"semantic_authority": "value_judgment"})
        return ValueJudgmentResult(status="judged", judgment=judgment,
                                   metadata={"semantic_authority": "value_judgment", "semantic_result_call_count": 1})
