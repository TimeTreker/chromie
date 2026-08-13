from __future__ import annotations

import asyncio
import unittest
from typing import Any

from agent.app.agents.base import AgentServices
from agent.app.capabilities.catalog import CapabilityMatch, CapabilitySearchResult
from agent.app.clients.ollama_client import OllamaGenerationError
from agent.app.interaction import InteractionDraft
from agent.app.runtime import InteractionRuntime
from agent.app.social_attention import SocialAttentionPlanner
from agent.app.schema import AgentRunRequest
from shared.chromie_contracts.interaction import FORBIDDEN_LOW_LEVEL_FIELDS, SkillRequest
from shared.chromie_contracts.social_attention import (
    SocialAttentionPlan,
    SocialAttentionRequest,
)


class _ConversationOllama:
    async def generate(self, prompt: str, **kwargs: Any) -> str:
        del prompt, kwargs
        return "I am here with you."


class _AttentionOllama:
    def __init__(self, reply: dict[str, Any], *, delay_s: float = 0.0) -> None:
        self.reply = reply
        self.delay_s = delay_s
        self.prompts: list[str] = []

    async def generate(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        schema = kwargs["response_format"]
        assert isinstance(schema, dict)
        behavior = schema["$defs"]["SocialAttentionBehavior"]
        assert "enum" in behavior["properties"]["capability_id"]
        self.prompts.append(prompt)
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        return self.reply


class _ScriptedAttentionOllama:
    timeout_ms = 120000

    def __init__(self, replies: list[dict[str, Any]]) -> None:
        self.replies = list(replies)
        self.prompts: list[tuple[str, dict[str, Any]]] = []

    async def generate(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        schema = kwargs["response_format"]
        assert isinstance(schema, dict)
        assert len(schema.get("allOf") or []) >= 2
        self.prompts.append((prompt, kwargs))
        if not self.replies:
            raise AssertionError("unexpected Social Attention model call")
        return self.replies.pop(0)


class _FailingAttentionOllama:
    timeout_ms = 120000

    async def generate(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        del prompt, kwargs
        raise OllamaGenerationError(
            "structured JSON output was truncated",
            failure_class="output_truncated",
            failure_domain="llm_budget",
            architecture_attribution="not_evaluated",
            retryable=True,
            details={
                "purpose": "social_attention",
                "done_reason": "length",
                "num_ctx": 32768,
                "num_predict": 4096,
            },
        )


class _Catalog:
    def __init__(self, capabilities: list[CapabilityMatch]) -> None:
        self.capabilities = capabilities

    async def search(self, text: str, **kwargs: Any) -> CapabilitySearchResult:
        del kwargs
        return CapabilitySearchResult(
            query=text,
            matched=bool(self.capabilities),
            suggested_route="chat",
            suggested_agents=[],
            catalog_version=71,
            matches=self.capabilities,
        )

    async def get_capability(self, capability_id: str, **kwargs: Any) -> CapabilityMatch | None:
        del kwargs
        return next(
            (item for item in self.capabilities if item.capability_id == capability_id),
            None,
        )


class _DomainCatalog(_Catalog):
    async def refresh_live_named_skills(self) -> None:
        return None

    def entries(self) -> list[CapabilityMatch]:
        return list(self.capabilities)


class SocialAttentionPlanningTests(unittest.IsolatedAsyncioTestCase):
    def _request(self, *, route: str = "chat", intent: str = "general_conversation") -> AgentRunRequest:
        return AgentRunRequest.model_validate(
            {
                "sid": "social-attention-test",
                "text": "Hello, Chromie.",
                "language": "en-US",
                "route_decision": {
                    "route": route,
                    "intent": intent,
                    "agents": ["conversation_agent", "speaker_agent"],
                    "confidence": 0.95,
                    "source": "llm",
                },
            }
        )

    def _express_attention(self) -> CapabilityMatch:
        return CapabilityMatch(
            capability_id="soridormi.express_attention",
            agent_id="soridormi.skill",
            description="Use a subtle bounded attention gesture.",
            input_schema={
                "type": "object",
                "properties": {
                    "style": {"type": "string", "enum": ["neutral"]},
                    "duration_s": {"type": "number", "minimum": 0.5, "maximum": 4.0},
                    "hold_fraction": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                },
                "required": ["style", "duration_s", "hold_fraction"],
                "additionalProperties": False,
            },
            effects=["physical_motion"],
            safety_class="physical_motion",
            requires_confirmation=False,
            available=True,
            route="robot_action",
            interaction_executable=True,
            score=0.5,
            metadata={"provider_backend": "opaque"},
            can_run_parallel=True,
            parallel_metadata_declared=True,
            exclusive_group="head_expression",
            resource_claims=["head_expression"],
        )

    def _blink(self) -> CapabilityMatch:
        return CapabilityMatch(
            capability_id="soridormi.blink_eyes",
            agent_id="soridormi.skill",
            description="Blink the visible social eyes.",
            input_schema={
                "type": "object",
                "properties": {"count": {"type": "integer", "minimum": 1, "maximum": 6}},
                "required": ["count"],
                "additionalProperties": False,
            },
            effects=["visual_expression"],
            safety_class="low_risk_action",
            requires_confirmation=False,
            available=True,
            route="robot_action",
            interaction_executable=True,
            score=0.4,
            metadata={"provider_backend": "opaque"},
            can_run_parallel=True,
            parallel_metadata_declared=True,
            exclusive_group="face_expression",
            resource_claims=["face_expression"],
        )

    def test_background_prompt_preserves_primary_action_and_social_context(self) -> None:
        planner = SocialAttentionPlanner(
            AgentServices(
                social_attention_mode="on",
                social_attention_capability_ids=("soridormi.blink_eyes",),
            )
        )
        request = SocialAttentionRequest(
            session_id="social-attention-test",
            turn_id="turn-explicit-blink",
            event="understanding_ready",
            text="Blink twice, and be cute.",
            language="en-US",
            intent="semantic_capability_planning",
            context={
                "social_attention_interaction_state": {
                    "primary_capability_ids": ["soridormi.blink_eyes"],
                    "primary_progress": [
                        {
                            "capability_id": "soridormi.blink_eyes",
                            "args": {"count": 2},
                        }
                    ],
                },
                "social_interaction_style": {
                    "owner_approved": True,
                    "warmth": "warm",
                },
                "recent_auxiliary_behavior_evidence": [
                    {"skill_id": "soridormi.nod_yes", "event": "speaking"}
                ],
            },
        )

        prompt = planner._prompt(
            request,
            [self._blink().model_dump(mode="json")],
        )

        self.assertIn('"social_interaction_style"', prompt)
        self.assertIn('"recent_auxiliary_behavior_evidence"', prompt)
        self.assertIn('"count": 2', prompt)
        self.assertIn("explicit user action remains mandatory", prompt)
        self.assertIn("different compatible cue", prompt)

    def test_background_prompt_does_not_mistake_direct_work_for_exact_only(self) -> None:
        planner = SocialAttentionPlanner(
            AgentServices(
                social_attention_mode="on",
                social_attention_capability_ids=("soridormi.blink_eyes",),
            )
        )
        request = SocialAttentionRequest(
            session_id="voice-log-water",
            turn_id="turn-fetch-water",
            event="understanding_ready",
            text="去往前走个100米，帮我拿杯水过来。",
            language="zh-CN",
            intent="semantic_capability_planning",
            context={
                "social_attention_interaction_state": {
                    "primary_capability_ids": [],
                    "primary_progress": [],
                    "primary_work_known": False,
                },
                "social_interaction_style": {
                    "owner_approved": True,
                    "preset": "courteous",
                },
                "recent_auxiliary_behavior_evidence": [],
                "social_attention_target_evidence": {"available": False},
            },
        )

        prompt = planner._prompt(
            request,
            [self._blink().model_dump(mode="json")],
        )

        self.assertIn("Ordinary cooperative engagement", prompt)
        self.assertIn("playful or explicitly emotional wording is not required", prompt)
        self.assertIn("A clear or direct task is not evidence", prompt)
        self.assertIn("only when it is actually supplied", prompt)
        self.assertIn("independent-output candidate declared parallel-safe", prompt)
        self.assertIn("Do not default to decision=none merely because speech", prompt)

    async def test_background_request_uses_session_id_when_live_candidates_exist(self) -> None:
        attention = _AttentionOllama(
            {
                "decision": "none",
                "target": {
                    "target_ref": "none",
                    "source": "none",
                    "confidence": 0.0,
                    "metadata": {},
                },
                "behaviors": [],
                "confidence": 0.86,
                "reason": "The exact primary blink should remain unembellished.",
            }
        )
        planner = SocialAttentionPlanner(
            AgentServices(
                social_attention_mode="on",
                social_attention_ollama=attention,  # type: ignore[arg-type]
                social_attention_capability_ids=("soridormi.blink_eyes",),
            )
        )
        request = SocialAttentionRequest(
            session_id="social-attention-background-session",
            turn_id="turn-explicit-blink",
            event="understanding_ready",
            text="Blink twice.",
            language="en-US",
            intent="semantic_capability_planning",
            context={
                "social_attention_candidates": [
                    self._blink().model_dump(mode="json")
                ],
                "social_attention_interaction_state": {
                    "primary_capability_ids": ["soridormi.blink_eyes"],
                    "primary_progress": [
                        {
                            "capability_id": "soridormi.blink_eyes",
                            "args": {"count": 2},
                        }
                    ],
                },
            },
        )

        plan = await planner.plan(request)

        self.assertIsNotNone(plan)
        assert plan is not None
        self.assertEqual(plan.decision, "none")
        self.assertEqual(len(attention.prompts), 1)

    async def test_contradictory_none_with_blink_gets_bounded_model_repair(self) -> None:
        target = {
            "target_ref": "none",
            "source": "none",
            "confidence": 0.0,
            "metadata": {},
        }
        behavior = {
            "capability_id": "soridormi.blink_eyes",
            "args": {"count": 2},
            "timing": "parallel",
            "reason": "A small blink supports the warm work-start cue.",
        }
        attention = _ScriptedAttentionOllama(
            [
                {
                    "decision": "none",
                    "target": target,
                    "behaviors": [behavior],
                    "confidence": 0.82,
                    "reason": "A small blink would make the interaction warmer.",
                },
                {
                    "decision": "express",
                    "target": target,
                    "behaviors": [behavior],
                    "confidence": 0.82,
                    "reason": "A small blink would make the interaction warmer.",
                },
            ]
        )
        planner = SocialAttentionPlanner(
            AgentServices(
                social_attention_mode="on",
                social_attention_ollama=attention,  # type: ignore[arg-type]
                social_attention_capability_ids=("soridormi.blink_eyes",),
            )
        )
        request = SocialAttentionRequest(
            session_id="voice-log-water",
            turn_id="turn-work-started",
            event="work_started",
            text="去往前走个100米，帮我拿杯水过来。",
            language="zh-CN",
            intent="semantic_capability_planning",
            context={
                "social_attention_candidates": [
                    self._blink().model_dump(mode="json")
                ],
                "social_attention_interaction_state": {
                    "primary_capability_ids": [
                        "soridormi.acquire_and_deliver_resource"
                    ]
                },
                "social_interaction_style": {
                    "owner_approved": True,
                    "warmth": "warm",
                },
            },
        )

        plan = await planner.plan(request)

        self.assertIsNotNone(plan)
        assert plan is not None
        self.assertEqual(plan.decision, "express")
        self.assertEqual(plan.behaviors[0].capability_id, "soridormi.blink_eyes")
        self.assertTrue(plan.metadata["contract_repair"]["succeeded"])
        self.assertEqual(len(attention.prompts), 2)
        self.assertEqual(
            attention.prompts[1][1]["prompt_family"],
            "social_attention.contract_repair",
        )
        self.assertIn("decision=none with behaviors=[]", attention.prompts[1][0])

    async def test_fresh_courteous_none_gets_independent_semantic_review(self) -> None:
        target = {
            "target_ref": "none",
            "source": "none",
            "confidence": 0.0,
            "metadata": {},
        }
        attention = _ScriptedAttentionOllama(
            [
                {
                    "decision": "none",
                    "target": target,
                    "behaviors": [],
                    "confidence": 0.95,
                    "reason": "The physical task is direct and needs no social context.",
                },
                {
                    "purpose": "acknowledge",
                    "decision": "express",
                    "target": target,
                    "behaviors": [
                        {
                            "capability_id": "soridormi.blink_eyes",
                            "args": {"count": 1},
                            "timing": "parallel",
                            "reason": "A subtle blink acknowledges the fresh request.",
                        }
                    ],
                    "confidence": 0.84,
                    "reason": "Courteous acknowledgement is useful and non-disruptive.",
                },
            ]
        )
        planner = SocialAttentionPlanner(
            AgentServices(
                social_attention_mode="on",
                social_attention_ollama=attention,  # type: ignore[arg-type]
                social_attention_capability_ids=("soridormi.blink_eyes",),
            )
        )
        request = SocialAttentionRequest(
            session_id="voice-log-water",
            turn_id="turn-fetch-water",
            event="understanding_ready",
            text="去往前走个100米，帮我拿杯水过来。",
            language="zh-CN",
            intent="semantic_capability_planning",
            context={
                "social_attention_candidates": [
                    self._blink().model_dump(mode="json")
                ],
                "social_attention_interaction_state": {
                    "primary_capability_ids": [],
                    "primary_progress": [],
                },
                "social_interaction_style": {
                    "owner_approved": True,
                    "preset": "courteous",
                },
                "recent_auxiliary_behavior_evidence": [],
            },
        )

        plan = await planner.plan(request)

        self.assertIsNotNone(plan)
        assert plan is not None
        self.assertEqual(plan.decision, "express")
        self.assertEqual(plan.behaviors[0].skill_id, "soridormi.blink_eyes")
        self.assertTrue(plan.metadata["none_semantic_review"]["succeeded"])
        self.assertEqual(len(attention.prompts), 2)
        self.assertEqual(
            attention.prompts[1][1]["prompt_family"],
            "social_attention.none_semantic_review",
        )
        self.assertIn("expected default for this fresh acknowledgement", attention.prompts[1][0])
        self.assertNotIn(
            "The physical task is direct and needs no social context.",
            attention.prompts[1][0],
        )

    async def test_none_review_invalid_expression_gets_one_contract_repair(self) -> None:
        target = {
            "target_ref": "none",
            "source": "none",
            "confidence": 0.0,
            "metadata": {},
        }
        valid_behavior = {
            "capability_id": "soridormi.blink_eyes",
            "args": {"count": 1},
            "timing": "parallel",
            "reason": "A subtle fresh-turn acknowledgement.",
        }
        attention = _ScriptedAttentionOllama(
            [
                {
                    "decision": "none",
                    "target": target,
                    "behaviors": [],
                    "confidence": 0.9,
                    "reason": "No cue selected initially.",
                },
                {
                    "decision": "express",
                    "target": target,
                    "behaviors": [],
                    "confidence": 0.84,
                    "reason": "A cue is socially useful.",
                },
                {
                    "purpose": "acknowledge",
                    "decision": "express",
                    "target": target,
                    "behaviors": [valid_behavior],
                    "confidence": 0.84,
                    "reason": "A cue is socially useful.",
                },
            ]
        )
        planner = SocialAttentionPlanner(
            AgentServices(
                social_attention_mode="on",
                social_attention_ollama=attention,  # type: ignore[arg-type]
            )
        )
        request = SocialAttentionRequest(
            session_id="review-contract-repair",
            turn_id="review-contract-repair",
            event="understanding_ready",
            text="Please handle that.",
            language="en-US",
            intent="semantic_capability_planning",
            context={
                "social_attention_candidates": [
                    self._blink().model_dump(mode="json")
                ],
                "social_interaction_style": {
                    "owner_approved": True,
                    "preset": "courteous",
                },
                "recent_auxiliary_behavior_evidence": [],
            },
        )

        plan = await planner.plan(request)

        self.assertIsNotNone(plan)
        assert plan is not None
        self.assertEqual(plan.decision, "express")
        self.assertEqual(plan.behaviors[0].skill_id, "soridormi.blink_eyes")
        self.assertTrue(plan.metadata["none_semantic_review"]["succeeded"])
        self.assertEqual(len(attention.prompts), 3)
        self.assertEqual(
            attention.prompts[2][1]["prompt_family"],
            "social_attention.none_semantic_review_contract_repair",
        )
        required = attention.prompts[0][1]["response_format"]["required"]
        self.assertTrue(
            {"decision", "target", "behaviors", "confidence", "reason"}.issubset(
                required
            )
        )

    async def test_background_candidates_exclude_explicit_primary_activity(self) -> None:
        blink = self._blink().model_copy(
            update={"behavior_domains": ["social_attention", "facial_expression"]}
        )
        attention = self._express_attention().model_copy(
            update={"behavior_domains": ["social_attention", "head_expression"]}
        )
        runtime = InteractionRuntime(
            AgentServices(
                capability_catalog=_DomainCatalog([blink, attention]),  # type: ignore[arg-type]
                social_attention_mode="on",
            )
        )
        request = SocialAttentionRequest(
            session_id="social-attention-background-session",
            turn_id="turn-explicit-blink-cute",
            event="understanding_ready",
            text="Blink twice and be cute.",
            language="en-US",
            intent="semantic_capability_planning",
            context={
                "social_attention_interaction_state": {
                    "primary_capability_ids": ["soridormi.blink_eyes"],
                    "primary_progress": [
                        {
                            "capability_id": "soridormi.blink_eyes",
                            "args": {"count": 2},
                        }
                    ],
                },
            },
        )

        await runtime.prepare_social_attention_context(request)

        candidate_ids = {
            item["capability_id"]
            for item in request.context["social_attention_candidates"]
        }
        self.assertEqual(candidate_ids, {"soridormi.express_attention"})

    async def test_model_selects_subtle_attention_with_provider_target_evidence(self) -> None:
        attention = _AttentionOllama(
            {
                "decision": "express",
                "target": {
                    "target_ref": "known_right_side",
                    "source": "conversation_context",
                    "relative_direction": "right",
                    "confidence": 0.7,
                    "metadata": {},
                },
                "behaviors": [
                    {
                        "skill_id": "soridormi.express_attention",
                        "args": {"style": "neutral", "duration_s": 1.8, "hold_fraction": 0.3},
                        "timing": "parallel",
                        "reason": "A subtle cue supports the greeting.",
                    }
                ],
                "confidence": 0.9,
                "reason": "The user directly engaged Chromie.",
            }
        )
        request = self._request()
        request.context["social_attention_target"] = {
            "source": "conversation_context",
            "target": {
                "target_ref": "known_right_side",
                "relative_direction": "right",
                "confidence": 0.7,
            },
        }
        response = await InteractionRuntime(
            AgentServices(
                ollama=_ConversationOllama(),  # type: ignore[arg-type]
                use_llm=True,
                capability_catalog=_Catalog([self._express_attention()]),  # type: ignore[arg-type]
                social_attention_mode="on",
                social_attention_ollama=attention,  # type: ignore[arg-type]
                social_attention_capability_ids=("soridormi.express_attention",),
            )
        ).run(request)

        self.assertEqual(response.skills[0].skill_id, "soridormi.express_attention")
        self.assertEqual(response.skills[0].timing, "parallel")
        self.assertTrue(response.skills[0].metadata["auxiliary_social_attention"])
        self.assertEqual(response.metadata["social_attention_status"], "applied")
        self.assertIn("known_right_side", attention.prompts[0])
        proposals = response.metadata["agent_task_proposals"]
        self.assertTrue(all(item.get("skill_id") != "soridormi.express_attention" for item in proposals))

    async def test_truncated_social_attention_is_kept_and_attributed_to_llm_budget(self) -> None:
        response = await InteractionRuntime(
            AgentServices(
                ollama=_ConversationOllama(),  # type: ignore[arg-type]
                use_llm=True,
                capability_catalog=_Catalog([self._blink()]),  # type: ignore[arg-type]
                social_attention_mode="on",
                social_attention_ollama=_FailingAttentionOllama(),  # type: ignore[arg-type]
                social_attention_capability_ids=("soridormi.blink_eyes",),
                social_attention_num_ctx=32768,
                social_attention_num_predict=4096,
                social_attention_wait_after_response_ms=120000,
            )
        ).run(self._request())

        self.assertEqual(response.speech[0].text, "I am here with you.")
        self.assertEqual(response.metadata["social_attention_status"], "output_truncated")
        self.assertEqual(
            response.metadata["social_attention_failure_class"],
            "output_truncated",
        )
        self.assertEqual(
            response.metadata["social_attention_failure_domain"],
            "llm_budget",
        )
        self.assertEqual(
            response.metadata["social_attention_architecture_attribution"],
            "not_evaluated",
        )
        self.assertEqual(
            response.metadata["social_attention_failure"]["done_reason"],
            "length",
        )

    async def test_model_can_choose_no_gesture(self) -> None:
        attention = _AttentionOllama(
            {
                "decision": "none",
                "target": {
                    "target_ref": "none",
                    "source": "none",
                    "confidence": 0.0,
                    "metadata": {},
                },
                "behaviors": [],
                "confidence": 0.8,
                "reason": "Speech alone is natural.",
            }
        )
        response = await InteractionRuntime(
            AgentServices(
                ollama=_ConversationOllama(),  # type: ignore[arg-type]
                use_llm=True,
                capability_catalog=_Catalog([self._blink()]),  # type: ignore[arg-type]
                social_attention_mode="on",
                social_attention_ollama=attention,  # type: ignore[arg-type]
                social_attention_capability_ids=("soridormi.blink_eyes",),
            )
        ).run(self._request())

        self.assertEqual(response.skills, [])
        self.assertEqual(response.metadata["social_attention_status"], "not_selected")

    async def test_invalid_social_args_do_not_change_primary_response(self) -> None:
        attention = _AttentionOllama(
            {
                "decision": "express",
                "target": {
                    "target_ref": "none",
                    "source": "none",
                    "confidence": 0.0,
                    "metadata": {},
                },
                "behaviors": [
                    {
                        "skill_id": "soridormi.blink_eyes",
                        "args": {"count": 99},
                        "timing": "parallel",
                        "reason": "Optional blink.",
                    }
                ],
                "confidence": 0.7,
                "reason": "Optional cue.",
            }
        )
        response = await InteractionRuntime(
            AgentServices(
                ollama=_ConversationOllama(),  # type: ignore[arg-type]
                use_llm=True,
                capability_catalog=_Catalog([self._blink()]),  # type: ignore[arg-type]
                social_attention_mode="on",
                social_attention_ollama=attention,  # type: ignore[arg-type]
                social_attention_capability_ids=("soridormi.blink_eyes",),
            )
        ).run(self._request())

        self.assertEqual(response.speech[0].text, "I am here with you.")
        self.assertEqual(response.skills, [])
        self.assertEqual(response.metadata["social_attention_status"], "not_applied")
        self.assertIn("invalid_args:soridormi.blink_eyes", response.metadata["social_attention_validation_reasons"][0])

    async def test_configured_social_attention_wait_allows_bounded_completion(self) -> None:
        attention = _AttentionOllama(
            {
                "decision": "express",
                "target": {
                    "target_ref": "none",
                    "source": "none",
                    "confidence": 0.0,
                    "metadata": {},
                },
                "behaviors": [
                    {
                        "skill_id": "soridormi.blink_eyes",
                        "args": {"count": 2},
                        "timing": "parallel",
                        "reason": "Optional blink.",
                    }
                ],
                "confidence": 0.7,
                "reason": "Optional cue.",
            },
            delay_s=0.05,
        )
        response = await InteractionRuntime(
            AgentServices(
                ollama=_ConversationOllama(),  # type: ignore[arg-type]
                use_llm=True,
                capability_catalog=_Catalog([self._blink()]),  # type: ignore[arg-type]
                social_attention_mode="on",
                social_attention_ollama=attention,  # type: ignore[arg-type]
                social_attention_capability_ids=("soridormi.blink_eyes",),
                social_attention_wait_after_response_ms=200,
            )
        ).run(self._request())

        self.assertEqual(
            [item.skill_id for item in response.skills],
            ["soridormi.blink_eyes"],
        )
        self.assertEqual(response.metadata["social_attention_status"], "applied")

    async def test_zero_social_attention_wait_preserves_non_blocking_skip(self) -> None:
        attention = _AttentionOllama(
            {
                "decision": "express",
                "target": {
                    "target_ref": "none",
                    "source": "none",
                    "confidence": 0.0,
                    "metadata": {},
                },
                "behaviors": [
                    {
                        "skill_id": "soridormi.blink_eyes",
                        "args": {"count": 2},
                        "timing": "parallel",
                        "reason": "Optional blink.",
                    }
                ],
                "confidence": 0.7,
                "reason": "Optional cue.",
            },
            delay_s=0.05,
        )
        response = await InteractionRuntime(
            AgentServices(
                ollama=_ConversationOllama(),  # type: ignore[arg-type]
                use_llm=True,
                capability_catalog=_Catalog([self._blink()]),  # type: ignore[arg-type]
                social_attention_mode="on",
                social_attention_ollama=attention,  # type: ignore[arg-type]
                social_attention_capability_ids=("soridormi.blink_eyes",),
                social_attention_wait_after_response_ms=0,
            )
        ).run(self._request())

        self.assertEqual(response.skills, [])
        self.assertEqual(
            response.metadata["social_attention_status"],
            "skipped_latency_budget",
        )
        failure = response.metadata["social_attention_failure"]
        self.assertEqual(failure["configured_wait_after_response_ms"], 0)
        self.assertEqual(failure["effective_wait_after_response_ms"], 0)


    async def test_live_target_evidence_is_used_when_supplied(self) -> None:
        attention = _AttentionOllama(
            {
                "decision": "express",
                "target": {
                    "target_ref": "tracked_user_7",
                    "source": "live_perception",
                    "relative_direction": "left",
                    "confidence": 0.94,
                    "metadata": {},
                },
                "behaviors": [
                    {
                        "skill_id": "soridormi.express_attention",
                        "args": {"style": "neutral", "duration_s": 1.4, "hold_fraction": 0.25},
                        "timing": "parallel",
                        "reason": "Maintain attention toward the tracked user.",
                    }
                ],
                "confidence": 0.9,
                "reason": "Live perception provides the active user target.",
            }
        )
        request = self._request()
        request.context["perceived_user_target"] = {
            "target_ref": "tracked_user_7",
            "relative_direction": "left",
            "confidence": 0.94,
        }
        response = await InteractionRuntime(
            AgentServices(
                ollama=_ConversationOllama(),  # type: ignore[arg-type]
                use_llm=True,
                capability_catalog=_Catalog([self._express_attention()]),  # type: ignore[arg-type]
                social_attention_mode="on",
                social_attention_ollama=attention,  # type: ignore[arg-type]
                social_attention_capability_ids=("soridormi.express_attention",),
            )
        ).run(request)

        self.assertEqual(response.metadata["social_attention_status"], "applied")
        target = response.skills[0].metadata["attention_target"]
        self.assertEqual(target["source"], "live_perception")
        self.assertEqual(target["target_ref"], "tracked_user_7")
        self.assertNotIn("known_right_side", attention.prompts[0].split('attention_target_evidence', 1)[1].split('eligible_social_capabilities', 1)[0])

    async def test_provider_target_mismatch_is_rejected(self) -> None:
        attention = _AttentionOllama(
            {
                "decision": "express",
                "target": {
                    "target_ref": "invented_left_side",
                    "source": "conversation_context",
                    "relative_direction": "left",
                    "confidence": 0.9,
                    "metadata": {},
                },
                "behaviors": [
                    {
                        "skill_id": "soridormi.express_attention",
                        "args": {"style": "neutral", "duration_s": 1.5, "hold_fraction": 0.3},
                        "timing": "parallel",
                        "reason": "Look toward the invented target.",
                    }
                ],
                "confidence": 0.9,
                "reason": "Optional attention.",
            }
        )
        request = self._request()
        request.context["social_attention_target"] = {
            "source": "conversation_context",
            "target": {
                "target_ref": "known_right_side",
                "relative_direction": "right",
                "confidence": 0.7,
            },
        }
        response = await InteractionRuntime(
            AgentServices(
                ollama=_ConversationOllama(),  # type: ignore[arg-type]
                use_llm=True,
                capability_catalog=_Catalog([self._express_attention()]),  # type: ignore[arg-type]
                social_attention_mode="on",
                social_attention_ollama=attention,  # type: ignore[arg-type]
                social_attention_capability_ids=("soridormi.express_attention",),
            )
        ).run(request)

        self.assertEqual(response.skills, [])
        self.assertEqual(response.metadata["social_attention_status"], "not_applied")
        self.assertIn(
            "attention_target_ref_mismatch",
            response.metadata["social_attention_validation_reasons"],
        )

    def test_parallel_social_behavior_is_rejected_on_resource_conflict(self) -> None:
        services = AgentServices(
            social_attention_mode="on",
            social_attention_capability_ids=("soridormi.blink_eyes",),
        )
        planner = SocialAttentionPlanner(services)
        request = self._request(route="robot_action", intent="semantic_capability_planning")
        blink = self._blink().model_dump(mode="json")
        primary = {
            "capability_id": "soridormi.walk_forward",
            "available": True,
            "interaction_executable": True,
            "can_run_parallel": True,
            "parallel_metadata_declared": True,
            "exclusive_group": "face_expression",
            "resource_claims": ["face_expression"],
        }
        request.context["social_attention_candidates"] = [blink]
        request.context["social_attention_target_evidence"] = {"available": False}
        request.context["capability_candidates"] = [primary]
        result = InteractionDraft()
        result.add_speak_immediate("I will handle that safely.")
        result.add_skill(
            SkillRequest(
                skill_id="soridormi.walk_forward",
                args={"duration_s": 2},
                timing="parallel",
            )
        )
        plan = SocialAttentionPlan.model_validate(
            {
                "decision": "express",
                "target": {
                    "target_ref": "none",
                    "source": "none",
                    "confidence": 0.0,
                },
                "behaviors": [
                    {
                        "skill_id": "soridormi.blink_eyes",
                        "args": {"count": 2},
                        "timing": "parallel",
                    }
                ],
                "confidence": 0.8,
            }
        )

        skills, reasons = planner.validate_and_materialize(request, result, plan)

        self.assertEqual(skills, [])
        self.assertIn("resource_conflict:soridormi.blink_eyes", reasons)

    def test_contract_rejects_low_level_fields(self) -> None:
        forbidden = next(iter(FORBIDDEN_LOW_LEVEL_FIELDS))
        with self.assertRaises(ValueError):
            SocialAttentionPlan.model_validate(
                {
                    "decision": "express",
                    "target": {
                        "target_ref": "active_user",
                        "source": "live_perception",
                        "confidence": 1.0,
                    },
                    "behaviors": [
                        {
                            "skill_id": "soridormi.express_attention",
                            "args": {forbidden: [0.0]},
                            "timing": "parallel",
                        }
                    ],
                    "confidence": 1.0,
                }
            )



    async def test_domain_discovery_does_not_require_fixed_capability_ids(self) -> None:
        blink = self._blink().model_copy(
            update={"behavior_domains": ["social_attention", "facial_expression"]}
        )
        attention = _AttentionOllama(
            {
                "behavior_domain": "social_attention",
                "interaction_role": "auxiliary_expression",
                "purpose": "acknowledge",
                "decision": "express",
                "target": {"target_ref": "none", "source": "none"},
                "behaviors": [
                    {
                        "skill_id": "soridormi.blink_eyes",
                        "args": {"count": 1},
                        "timing": "parallel",
                        "social_function": "acknowledge_presence",
                    }
                ],
                "confidence": 0.8,
            }
        )
        response = await InteractionRuntime(
            AgentServices(
                ollama=_ConversationOllama(),  # type: ignore[arg-type]
                use_llm=True,
                capability_catalog=_DomainCatalog([blink]),  # type: ignore[arg-type]
                social_attention_mode="on",
                social_attention_ollama=attention,  # type: ignore[arg-type]
                social_attention_capability_ids=(),
            )
        ).run(self._request())

        self.assertEqual(response.metadata["social_attention_status"], "applied")
        self.assertEqual(response.skills[0].skill_id, "soridormi.blink_eyes")
        self.assertEqual(
            response.skills[0].metadata["behavior_domain"],
            "social_attention",
        )



class SocialAttentionDomainContractTests(unittest.TestCase):
    def test_social_attention_rejects_speech_expression(self) -> None:
        with self.assertRaises(ValueError):
            SocialAttentionPlan.model_validate(
                {
                    "behavior_domain": "social_attention",
                    "interaction_role": "auxiliary_expression",
                    "purpose": "empathy",
                    "decision": "express",
                    "speech_expression": {
                        "mode": "adapt",
                        "style": "empathetic",
                    },
                    "behaviors": [],
                    "confidence": 0.9,
                }
            )

    def test_express_requires_decorative_body_behavior(self) -> None:
        with self.assertRaises(ValueError):
            SocialAttentionPlan.model_validate(
                {
                    "decision": "express",
                    "purpose": "engagement",
                    "behaviors": [],
                }
            )


if __name__ == "__main__":
    unittest.main()
