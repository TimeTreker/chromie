from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import patch

from agent.app.agents import AgentServices, ConversationAgent
from agent.app.schema import AgentResult, AgentRunRequest
from shared.chromie_contracts.mind import default_mind_profile


class _CapturingOllama:
    def __init__(self, response: Any | list[Any] = "Here is a little song I made for you.") -> None:
        self.responses = response if isinstance(response, list) else [response]
        self.calls: list[dict[str, Any]] = []

    async def generate(self, prompt: str, **kwargs: Any) -> Any:
        self.calls.append({"prompt": prompt, **kwargs})
        index = min(len(self.calls) - 1, len(self.responses) - 1)
        return self.responses[index]


class ConversationAgentPromptTests(unittest.IsolatedAsyncioTestCase):
    async def test_identity_question_uses_owner_approved_mind_profile(self) -> None:
        ollama = _CapturingOllama("I'm Chromie.")
        agent = ConversationAgent(
            AgentServices(
                ollama=ollama,  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=220,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "identity-test",
                "text": "Who are you?",
                "context": {"mind": default_mind_profile().prompt_context()},
                "route_decision": {
                    "route": "chat",
                    "agents": ["conversation_agent", "speaker_agent"],
                    "intent": "general_conversation",
                    "confidence": 0.45,
                    "language": "en-US",
                    "source": "fallback",
                },
            }
        )

        with patch.dict("os.environ", {}, clear=True):
            result = await agent.run(request, AgentResult())

        self.assertEqual(result.speak_immediate[0].text, "I'm Chromie.")
        self.assertEqual(len(ollama.calls), 1)
        self.assertIn("Self model, owner-approved", ollama.calls[0]["prompt"])
        self.assertIn("speaker entity: chromie", ollama.calls[0]["prompt"])
        self.assertIn("social_presentation", ollama.calls[0]["prompt"])
        self.assertIn("natural, warm, person-like conversational presence", ollama.calls[0]["prompt"])
        self.assertIn("language_reasoner", ollama.calls[0]["prompt"])
        self.assertNotIn("embodied robot", ollama.calls[0]["prompt"])
        self.assertNotIn("6 years old", ollama.calls[0]["prompt"])
        self.assertIn("First-person words refer to Self model.speaker_entity", ollama.calls[0]["system"])
        self.assertIn("Internal components are resources", ollama.calls[0]["system"])
        self.assertNotIn("If the user asks who you are", ollama.calls[0]["system"])
        self.assertNotIn("never say you are a large language model", ollama.calls[0]["system"])
        self.assertEqual(ollama.calls[0]["options"]["num_ctx"], 4096)
        self.assertEqual(ollama.calls[0]["options"]["num_predict"], 128)

    async def test_identity_age_question_keeps_internal_age_out_of_ordinary_prompt(self) -> None:
        ollama = _CapturingOllama("I'm Chromie; I don't usually introduce myself by an age.")
        agent = ConversationAgent(
            AgentServices(
                ollama=ollama,  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=220,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "identity-age-test",
                "text": "How old are you?",
                "context": {"mind": default_mind_profile().prompt_context()},
                "route_decision": {
                    "route": "chat",
                    "agents": ["conversation_agent", "speaker_agent"],
                    "intent": "general_conversation",
                    "confidence": 0.45,
                    "language": "en-US",
                    "source": "fallback",
                },
            }
        )

        result = await agent.run(request, AgentResult())

        self.assertEqual(
            result.speak_immediate[0].text,
            "I'm Chromie; I don't usually introduce myself by an age.",
        )
        self.assertEqual(len(ollama.calls), 1)
        self.assertIn("social_presentation", ollama.calls[0]["prompt"])
        self.assertNotIn("age: 6 years old", ollama.calls[0]["prompt"])
        self.assertNotIn("not a human biological age", ollama.calls[0]["prompt"])

    async def test_identity_gender_question_uses_she_her_pronouns(self) -> None:
        ollama = _CapturingOllama("I'm female and use she/her pronouns.")
        agent = ConversationAgent(
            AgentServices(
                ollama=ollama,  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=220,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "identity-gender-test",
                "text": "Are you female?",
                "context": {"mind": default_mind_profile().prompt_context()},
                "route_decision": {
                    "route": "chat",
                    "agents": ["conversation_agent", "speaker_agent"],
                    "intent": "general_conversation",
                    "confidence": 0.45,
                    "language": "en-US",
                    "source": "fallback",
                },
            }
        )

        result = await agent.run(request, AgentResult())

        self.assertEqual(result.speak_immediate[0].text, "I'm female and use she/her pronouns.")
        self.assertEqual(len(ollama.calls), 1)
        self.assertIn("pronouns: she, her", ollama.calls[0]["prompt"])


    async def test_capability_inquiry_is_grounded_by_prompt_without_executing(self) -> None:
        ollama = _CapturingOllama("会，我可以眨眼。")
        agent = ConversationAgent(
            AgentServices(
                ollama=ollama,  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=220,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "prompt-capability-inquiry-test",
                "text": "你会眨眼吗？",
                "context": {"mind": default_mind_profile().prompt_context()},
                "route_decision": {
                    "route": "chat",
                    "agents": ["conversation_agent", "speaker_agent"],
                    "intent": "capability_inquiry",
                    "confidence": 0.93,
                    "language": "zh-CN",
                    "source": "llm",
                    "candidate_capabilities": [
                        {
                            "capability_id": "soridormi.blink_eyes",
                            "description": "Blink the robot's eyes a bounded number of times.",
                            "interaction_executable": True,
                            "available": True,
                            "input_schema": {
                                "type": "object",
                                "properties": {"count": {"type": "integer"}},
                            },
                        },
                        {
                            "capability_id": "soridormi.nod_yes",
                            "description": "Nod the robot head.",
                            "interaction_executable": True,
                            "available": True,
                        },
                    ],
                },
            }
        )

        result = await agent.run(request, AgentResult())

        self.assertEqual(result.speak_immediate[0].text, "会，我可以眨眼。")
        self.assertEqual(result.actions, [])
        self.assertEqual(len(ollama.calls), 1)
        call = ollama.calls[0]
        self.assertIn("Semantically distinguish an information inquiry", call["system"])
        self.assertIn("only an executable action route", call["system"])
        self.assertIn("soridormi.blink_eyes", call["prompt"])
        self.assertIn("soridormi.nod_yes", call["prompt"])
        self.assertIn("capability_inquiry", call["prompt"])

    async def test_simple_social_question_uses_llm_conversation_path(self) -> None:
        ollama = _CapturingOllama("Hello, I'm doing well and listening.")
        agent = ConversationAgent(
            AgentServices(
                ollama=ollama,  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=220,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "hello-llm-test",
                "text": "Hello, how are you doing?",
                "route_decision": {
                    "route": "chat",
                    "agents": ["conversation_agent", "speaker_agent"],
                    "intent": "general_conversation",
                    "confidence": 0.45,
                    "language": "en-US",
                    "source": "fallback",
                },
            }
        )

        result = await agent.run(request, AgentResult())

        self.assertEqual(result.speak_immediate[0].text, "Hello, I'm doing well and listening.")
        self.assertEqual(len(ollama.calls), 1)
        self.assertIn("Generalization-first is a core principle", ollama.calls[0]["system"])
        self.assertIn("Do not treat prompt examples as keyword rules", ollama.calls[0]["system"])
        self.assertIn("Target spoken language: en-US", ollama.calls[0]["prompt"])

    async def test_social_checkin_fragment_is_repaired_by_compact_second_pass(self) -> None:
        ollama = _CapturingOllama(["Hello.", "Hello, I am doing well and ready to help."])
        agent = ConversationAgent(
            AgentServices(
                ollama=ollama,  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=220,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "hello-repair-test",
                "text": "Helello, how are you.",
                "route_decision": {
                    "route": "chat",
                    "agents": ["conversation_agent", "speaker_agent"],
                    "intent": "greeting",
                    "confidence": 0.45,
                    "language": "en-US",
                    "source": "llm",
                },
            }
        )

        result = await agent.run(request, AgentResult())

        self.assertEqual(
            result.speak_immediate[0].text,
            "Hello, I am doing well and ready to help.",
        )
        self.assertEqual(len(ollama.calls), 2)
        self.assertIn("For plain social check-ins", ollama.calls[0]["system"])
        self.assertIn("compact spoken-response repairer", ollama.calls[1]["system"])

    async def test_obvious_sun_claim_goes_through_llm_with_factual_prompt(self) -> None:
        ollama = _CapturingOllama("No. The Sun is extremely hot, not cold.")
        agent = ConversationAgent(
            AgentServices(
                ollama=ollama,  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=220,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "sun-llm-test",
                "text": "In my opinion, the sun is cold. Do you agree with me?",
                "route_decision": {
                    "route": "chat",
                    "agents": ["conversation_agent", "speaker_agent"],
                    "intent": "general_conversation",
                    "confidence": 0.45,
                    "language": "en-US",
                    "source": "fallback",
                },
            }
        )

        result = await agent.run(request, AgentResult())

        self.assertEqual(result.speak_immediate[0].text, "No. The Sun is extremely hot, not cold.")
        self.assertEqual(len(ollama.calls), 1)
        self.assertIn("correct obvious false premises", ollama.calls[0]["system"])
        self.assertIn("Current user said: In my opinion, the sun is cold.", ollama.calls[0]["prompt"])

    async def test_sun_shape_reply_names_subject_even_when_model_uses_pronoun(self) -> None:
        ollama = _CapturingOllama("It is indeed a massive, nearly perfect sphere.")
        agent = ConversationAgent(
            AgentServices(
                ollama=ollama,  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=220,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "sun-shape-anchor-test",
                "text": "I think the sun is not a round sphere, do you think so?",
                "route_decision": {
                    "route": "chat",
                    "agents": ["conversation_agent", "speaker_agent"],
                    "intent": "general_conversation",
                    "confidence": 0.45,
                    "language": "en-US",
                    "source": "fallback",
                },
            }
        )

        result = await agent.run(request, AgentResult())

        self.assertEqual(
            result.speak_immediate[0].text,
            "The Sun is roughly spherical. It is indeed a massive, nearly perfect sphere.",
        )

    async def test_response_review_auto_skips_low_risk_greeting(self) -> None:
        ollama = _CapturingOllama(
            [
                "Hello! I'm doing great, thanks for asking.",
                {
                    "decision": "revise",
                    "reason": "Should not be called for speech-only greeting.",
                    "spoken_response": "Unexpected reviewer rewrite.",
                },
            ]
        )
        agent = ConversationAgent(
            AgentServices(
                ollama=ollama,  # type: ignore[arg-type]
                response_reviewer=ollama,  # type: ignore[arg-type]
                response_review_mode="auto",
                use_llm=True,
                max_speak_chars=220,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "review-auto-greeting-test",
                "text": "Hello, how are you?",
                "route_decision": {
                    "route": "chat",
                    "agents": ["conversation_agent", "speaker_agent"],
                    "intent": "general_conversation",
                    "confidence": 0.45,
                    "language": "en-US",
                    "source": "fallback",
                },
            }
        )

        result = await agent.run(request, AgentResult())

        self.assertEqual(
            result.speak_immediate[0].text,
            "Hello! I'm doing great, thanks for asking.",
        )
        self.assertEqual(len(ollama.calls), 1)

    async def test_response_review_auto_reviews_robot_action_context(self) -> None:
        ollama = _CapturingOllama(
            [
                "I am checking that action.",
                {
                    "decision": "accept",
                    "reason": "Physical action context should be audited.",
                    "spoken_response": "",
                },
            ]
        )
        agent = ConversationAgent(
            AgentServices(
                ollama=ollama,  # type: ignore[arg-type]
                response_reviewer=ollama,  # type: ignore[arg-type]
                response_review_mode="auto",
                use_llm=True,
                max_speak_chars=220,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "review-auto-robot-action-test",
                "text": "Walk forward.",
                "route_decision": {
                    "route": "robot_action",
                    "agents": ["conversation_agent", "speaker_agent"],
                    "intent": "robot_action",
                    "confidence": 0.80,
                    "language": "en-US",
                    "source": "llm",
                },
            }
        )

        result = await agent.run(request, AgentResult())

        self.assertEqual(result.speak_immediate[0].text, "I am checking that action.")
        self.assertEqual(len(ollama.calls), 2)
        self.assertIn("semantic spoken-response reviewer", ollama.calls[1]["system"])
        self.assertIn("first-person speaker or body ownership", ollama.calls[1]["system"])

    async def test_response_review_auto_skips_speech_only_model_disclaimer(self) -> None:
        ollama = _CapturingOllama(
            [
                "I do not have personal opinions on whether the sun is hot.",
                {
                    "decision": "revise",
                    "reason": "Should not be called for speech-only content.",
                    "spoken_response": "Unexpected reviewer rewrite.",
                },
            ]
        )
        agent = ConversationAgent(
            AgentServices(
                ollama=ollama,  # type: ignore[arg-type]
                response_reviewer=ollama,  # type: ignore[arg-type]
                response_review_mode="auto",
                use_llm=True,
                max_speak_chars=220,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "sun-hot-retry-test",
                "text": "Do you think the sun is hot?",
                "route_decision": {
                    "route": "chat",
                    "agents": ["conversation_agent", "speaker_agent"],
                    "intent": "general_conversation",
                    "confidence": 0.45,
                    "language": "en-US",
                    "source": "fallback",
                },
            }
        )

        result = await agent.run(request, AgentResult())

        self.assertEqual(
            result.speak_immediate[0].text,
            "I do not have personal opinions on whether the sun is hot.",
        )
        self.assertEqual(len(ollama.calls), 1)
        self.assertIn("First-person words refer to Self model.speaker_entity", ollama.calls[0]["system"])

    async def test_chat_route_action_promise_is_revised_to_safe_action_clarification(self) -> None:
        ollama = _CapturingOllama(
            [
                "好的，这就为你往前走 15 秒。",
                {
                    "decision": "revise",
                    "reason": "Chat route cannot promise physical movement without a robot_action skill.",
                    "spoken_response": "我需要把这个作为机器人动作来确认，不能只用对话执行移动。",
                },
            ]
        )
        agent = ConversationAgent(
            AgentServices(
                ollama=ollama,  # type: ignore[arg-type]
                response_reviewer=ollama,  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=220,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "chat-action-promise-test",
                "text": "往前走个15秒。",
                "route_decision": {
                    "route": "chat",
                    "agents": ["conversation_agent", "speaker_agent"],
                    "intent": "general_conversation",
                    "confidence": 0.45,
                    "language": "zh-CN",
                    "source": "fallback",
                },
            }
        )

        result = await agent.run(request, AgentResult())

        self.assertEqual(
            result.speak_immediate[0].text,
            "我需要把这个作为机器人动作来确认，不能只用对话执行移动。",
        )
        self.assertEqual(len(ollama.calls), 2)
        self.assertIn("Route context:", ollama.calls[1]["prompt"])
        self.assertIn('"route":"chat"', ollama.calls[1]["prompt"])
        self.assertIn("no robot_action route or skill request is present", ollama.calls[1]["prompt"])
        self.assertIn("claims Chromie will now execute movement", ollama.calls[1]["system"])

    async def test_chat_route_stage_direction_action_is_blocked_without_reviewer(self) -> None:
        ollama = _CapturingOllama("好的，没问题！(眨了眨眼睛) 👁️👁️")
        agent = ConversationAgent(
            AgentServices(
                ollama=ollama,  # type: ignore[arg-type]
                response_reviewer=None,
                use_llm=True,
                max_speak_chars=220,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "chat-stage-action-guard-test",
                "text": "眨两小眼睛。",
                "route_decision": {
                    "route": "chat",
                    "agents": ["conversation_agent", "speaker_agent"],
                    "intent": "general_conversation",
                    "confidence": 0.90,
                    "language": "zh-CN",
                    "source": "llm",
                },
            }
        )

        result = await agent.run(request, AgentResult())

        self.assertEqual(len(ollama.calls), 1)
        self.assertIn("没有生成可执行动作", result.speak_immediate[0].text)
        self.assertIn("不会假装", result.speak_immediate[0].text)
        self.assertNotIn("眨了眨眼睛", result.speak_immediate[0].text)
        self.assertNotIn("👁️", result.speak_immediate[0].text)

    async def test_subjective_preference_disclaimer_is_retried_as_robot_persona(self) -> None:
        ollama = _CapturingOllama(
            [
                "I do not have personal opinions about favorite colors.",
                {
                    "decision": "revise",
                    "reason": "Chromie can answer with a simple robot-persona preference.",
                    "spoken_response": "I like bright yellow; it feels cheerful and easy to see.",
                },
            ]
        )
        agent = ConversationAgent(
            AgentServices(
                ollama=ollama,  # type: ignore[arg-type]
                response_reviewer=ollama,  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=220,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "preference-retry-test",
                "text": "What color do you like?",
                "context": {"mind": default_mind_profile().prompt_context()},
                "route_decision": {
                    "route": "chat",
                    "agents": ["conversation_agent", "speaker_agent"],
                    "intent": "general_conversation",
                    "confidence": 0.45,
                    "language": "en-US",
                    "source": "fallback",
                },
            }
        )

        result = await agent.run(request, AgentResult())

        self.assertEqual(
            result.speak_immediate[0].text,
            "I like bright yellow; it feels cheerful and easy to see.",
        )
        self.assertEqual(len(ollama.calls), 2)
        self.assertIn("semantic spoken-response reviewer", ollama.calls[1]["system"])

    async def test_harmless_joke_refusal_is_retried_as_original_joke(self) -> None:
        ollama = _CapturingOllama(
            [
                "I do not have a joke right now.",
                {
                    "decision": "revise",
                    "reason": "The user asked for harmless creative content.",
                    "spoken_response": "Here is one: my battery joined a gym, but it only did power cycles.",
                },
            ]
        )
        agent = ConversationAgent(
            AgentServices(
                ollama=ollama,  # type: ignore[arg-type]
                response_reviewer=ollama,  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=220,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "joke-retry-test",
                "text": "Tell me a joke please, I'm a little tired.",
                "route_decision": {
                    "route": "chat",
                    "agents": ["conversation_agent", "speaker_agent"],
                    "intent": "general_conversation",
                    "confidence": 0.45,
                    "language": "en-US",
                    "source": "fallback",
                },
            }
        )

        result = await agent.run(request, AgentResult())

        self.assertEqual(
            result.speak_immediate[0].text,
            "Here is one: my battery joined a gym, but it only did power cycles.",
        )
        self.assertEqual(len(ollama.calls), 2)
        self.assertIn("harmless creative speech requests", ollama.calls[0]["system"])
        self.assertIn("semantic spoken-response reviewer", ollama.calls[1]["system"])
        self.assertIn("Candidate spoken response", ollama.calls[1]["prompt"])

    async def test_empty_joke_acknowledgement_is_retried_as_original_joke(self) -> None:
        ollama = _CapturingOllama(
            [
                "I can tell you a joke.",
                {
                    "decision": "revise",
                    "reason": "The candidate only promised a joke instead of telling one.",
                    "spoken_response": "Why did the robot bring a blanket? Its circuits felt a little chilly.",
                },
            ]
        )
        agent = ConversationAgent(
            AgentServices(
                ollama=ollama,  # type: ignore[arg-type]
                response_reviewer=ollama,  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=220,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "joke-empty-ack-test",
                "text": "Hey, can you tell me a joke?",
                "route_decision": {
                    "route": "chat",
                    "agents": ["conversation_agent", "speaker_agent"],
                    "intent": "general_conversation",
                    "confidence": 0.45,
                    "language": "en-US",
                    "source": "fallback",
                },
            }
        )

        result = await agent.run(request, AgentResult())

        self.assertEqual(
            result.speak_immediate[0].text,
            "Why did the robot bring a blanket? Its circuits felt a little chilly.",
        )
        self.assertEqual(len(ollama.calls), 2)
        self.assertIn("Interpret harmless creative speech requests as speech acts", ollama.calls[0]["system"])
        self.assertIn("do not only announce readiness", ollama.calls[0]["system"])
        self.assertIn("When a greeting and a request appear together", ollama.calls[0]["system"])
        self.assertIn("Hey, can you tell me a joke?", ollama.calls[1]["prompt"])
        self.assertIn("rather than only promising readiness or ability", ollama.calls[1]["prompt"])
        self.assertNotIn("Original system prompt", ollama.calls[1]["prompt"])
        self.assertNotIn("Original task prompt", ollama.calls[1]["prompt"])

    async def test_empty_model_response_gets_one_compact_retry(self) -> None:
        ollama = _CapturingOllama(["", "I am sorry, I could not form the joke yet. Please ask me again."])
        agent = ConversationAgent(
            AgentServices(
                ollama=ollama,  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=220,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "joke-empty-model-response-test",
                "text": "Tell me a short joke.",
                "route_decision": {
                    "route": "chat",
                    "agents": ["conversation_agent", "speaker_agent"],
                    "intent": "factual_agreement",
                    "confidence": 0.90,
                    "language": "en-US",
                    "source": "llm",
                },
            }
        )

        result = await agent.run(request, AgentResult())

        self.assertEqual(
            result.speak_immediate[0].text,
            "I am sorry, I could not form the joke yet. Please ask me again.",
        )
        self.assertEqual(len(ollama.calls), 2)
        self.assertIn("empty_generation", ollama.calls[1]["prompt"])

    async def test_empty_model_and_empty_retry_use_honest_fallback(self) -> None:
        ollama = _CapturingOllama(["", ""])
        agent = ConversationAgent(
            AgentServices(
                ollama=ollama,  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=220,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "empty-model-and-retry-test",
                "text": "How are you going?",
                "route_decision": {
                    "route": "chat",
                    "agents": ["conversation_agent", "speaker_agent"],
                    "intent": "greeting",
                    "confidence": 0.95,
                    "language": "en-US",
                    "source": "llm",
                },
            }
        )

        result = await agent.run(request, AgentResult())

        self.assertEqual(
            result.speak_immediate[0].text,
            "I did not catch that. Could you say it again?",
        )
        self.assertEqual(len(ollama.calls), 2)

    async def test_false_missing_body_ability_is_retried_from_capability_context(self) -> None:
        ollama = _CapturingOllama(
            [
                "我没有执行“摇头”的动作能力，但我可以帮你做其他事情。",
                {
                    "decision": "revise",
                    "reason": "The capability context lists a matching head-shake skill.",
                    "spoken_response": "可以，我能摇头。",
                },
            ]
        )
        agent = ConversationAgent(
            AgentServices(
                ollama=ollama,  # type: ignore[arg-type]
                response_reviewer=ollama,  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=220,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "zh-body-capability-review-test",
                "text": "你能摇头吗？",
                "route_decision": {
                    "route": "chat",
                    "agents": ["conversation_agent", "speaker_agent"],
                    "intent": "general_conversation",
                    "confidence": 0.45,
                    "language": "zh-CN",
                    "source": "llm",
                    "candidate_capabilities": [
                        {
                            "capability_id": "soridormi.shake_no",
                            "description": "Shake the robot head no.",
                            "interaction_executable": True,
                            "available": True,
                        }
                    ],
                },
            }
        )

        result = await agent.run(request, AgentResult())

        self.assertEqual(result.speak_immediate[0].text, "可以，我能摇头。")
        self.assertEqual(len(ollama.calls), 2)
        self.assertIn("Target spoken language: zh-CN", ollama.calls[0]["prompt"])
        self.assertIn("Capability catalog and runtime availability", ollama.calls[0]["prompt"])
        self.assertIn("Current user said: 你能摇头吗？", ollama.calls[0]["prompt"])
        self.assertIn("The user text and context may be multilingual", ollama.calls[0]["system"])
        self.assertIn("every capability statement consistent with the supplied capability catalog", ollama.calls[0]["system"])
        self.assertIn("Capability context", ollama.calls[1]["prompt"])
        self.assertIn("soridormi.shake_no", ollama.calls[0]["prompt"])
        self.assertIn("soridormi.shake_no", ollama.calls[1]["prompt"])
        self.assertIn("falsely says Chromie cannot perform", ollama.calls[1]["system"])

    async def test_chinese_review_uses_unified_multilingual_prompt(self) -> None:
        ollama = _CapturingOllama(
            [
                "我可以讲一个笑话。",
                {
                    "decision": "revise",
                    "reason": "The candidate only promises a joke instead of telling one.",
                    "spoken_response": "审核器提供了实际内容。",
                },
            ]
        )
        agent = ConversationAgent(
            AgentServices(
                ollama=ollama,  # type: ignore[arg-type]
                response_reviewer=ollama,  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=220,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "zh-joke-review-test",
                "text": "你能讲个笑话吗？",
                "route_decision": {
                    "route": "chat",
                    "agents": ["conversation_agent", "speaker_agent"],
                    "intent": "general_conversation",
                    "confidence": 0.45,
                    "language": "zh-CN",
                    "source": "fallback",
                },
            }
        )

        result = await agent.run(request, AgentResult())

        self.assertEqual(
            result.speak_immediate[0].text,
            "审核器提供了实际内容。",
        )
        self.assertEqual(len(ollama.calls), 2)
        self.assertIn("single reviewer prompt is multilingual", ollama.calls[1]["system"])
        self.assertIn("Judge meaning, not keyword rules", ollama.calls[1]["system"])
        self.assertIn("Target spoken language: zh-CN", ollama.calls[1]["prompt"])
        self.assertIn("Current user input: 你能讲个笑话吗？", ollama.calls[1]["prompt"])
        self.assertNotIn("只输出 JSON", ollama.calls[1]["system"])

    async def test_joke_followup_empty_acknowledgement_is_retried(self) -> None:
        ollama = _CapturingOllama(
            [
                "I can tell you a joke.",
                {
                    "decision": "revise",
                    "reason": "The user is following up on a joke request and the candidate only promises.",
                    "spoken_response": "Reviewer supplied actual creative content.",
                },
            ]
        )
        agent = ConversationAgent(
            AgentServices(
                ollama=ollama,  # type: ignore[arg-type]
                response_reviewer=ollama,  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=220,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "joke-followup-empty-ack-test",
                "text": "I know you can. Tell me, please.",
                "history": [
                    {"role": "user", "text": "Please tell me a joke."},
                    {"role": "assistant", "text": "I can tell you a joke."},
                ],
                "route_decision": {
                    "route": "chat",
                    "agents": ["conversation_agent", "speaker_agent"],
                    "intent": "general_conversation",
                    "confidence": 0.45,
                    "language": "en-US",
                    "source": "fallback",
                },
            }
        )

        result = await agent.run(request, AgentResult())

        self.assertEqual(
            result.speak_immediate[0].text,
            "Reviewer supplied actual creative content.",
        )
        self.assertEqual(len(ollama.calls), 2)
        self.assertIn("Use short-term context to resolve references and pending work", ollama.calls[0]["system"])
        self.assertIn("pending work", ollama.calls[0]["system"])
        self.assertIn("provide the requested original content", ollama.calls[0]["system"])
        self.assertIn("If Chromie already promised the content", ollama.calls[1]["prompt"])

    async def test_repeated_user_utterance_is_revised_by_semantic_reviewer(self) -> None:
        ollama = _CapturingOllama(
            [
                'I heard you say, "Can you tell me a joke?"',
                {
                    "decision": "revise",
                    "reason": "The candidate repeats the user instead of answering.",
                    "spoken_response": "Why did Chromie bring a notebook? To keep track of her bright ideas.",
                },
            ]
        )
        agent = ConversationAgent(
            AgentServices(
                ollama=ollama,  # type: ignore[arg-type]
                response_reviewer=ollama,  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=220,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "repeat-user-retry-test",
                "text": "Can you tell me a joke?",
                "route_decision": {
                    "route": "chat",
                    "agents": ["conversation_agent", "speaker_agent"],
                    "intent": "general_conversation",
                    "confidence": 0.91,
                    "language": "en-US",
                    "source": "llm",
                },
            }
        )

        result = await agent.run(request, AgentResult())

        self.assertEqual(
            result.speak_immediate[0].text,
            "Why did Chromie bring a notebook? To keep track of her bright ideas.",
        )
        self.assertEqual(len(ollama.calls), 2)
        self.assertIn(
            "Normally do not repeat or paraphrase",
            ollama.calls[0]["system"],
        )
        self.assertIn(
            "Normally Chromie should not repeat, quote, or paraphrase",
            ollama.calls[1]["prompt"],
        )
        self.assertIn(
            "Repeating the user's words is acceptable only when confirmation",
            ollama.calls[1]["system"],
        )

    async def test_short_agreement_followup_uses_task_context_on_retry(self) -> None:
        ollama = _CapturingOllama(
            [
                "I do not have information to agree or disagree with you.",
                {
                    "decision": "revise",
                    "reason": "Task context already provides the claim.",
                    "spoken_response": "Yes, I agree. The Moon is round.",
                },
            ]
        )
        agent = ConversationAgent(
            AgentServices(
                ollama=ollama,  # type: ignore[arg-type]
                response_reviewer=ollama,  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=220,
            )
        )
        task_context = {
            "task_id": "task-moon",
            "status": "open",
            "task_type": "conversation",
            "goal": "Discuss whether the Moon is round",
            "important_claims": ["The user thinks the Moon is round."],
            "entities": ["Moon"],
            "last_meaningful_user_turn": "I think the moon is round. Do you think so?",
            "last_assistant_response": "The moon is round.",
        }
        request = AgentRunRequest.model_validate(
            {
                "sid": "agree-followup-test",
                "text": "Do you agree with me?",
                "context": {
                    "current_task_context": task_context,
                    "history": [
                        {
                            "role": "user",
                            "text": "I think the moon is round. Do you think so?",
                        },
                        {"role": "assistant", "text": "The moon is round."},
                    ],
                },
                "route_decision": {
                    "route": "chat",
                    "agents": ["conversation_agent", "speaker_agent"],
                    "intent": "general_conversation",
                    "confidence": 0.45,
                    "language": "en-US",
                    "source": "fallback",
                },
            }
        )

        result = await agent.run(request, AgentResult())

        self.assertEqual(result.speak_immediate[0].text, "Yes, I agree. The Moon is round.")
        self.assertEqual(len(ollama.calls), 2)
        self.assertIn("Task context", ollama.calls[0]["prompt"])
        self.assertIn("The user thinks the Moon is round.", ollama.calls[0]["prompt"])
        self.assertIn("The user thinks the Moon is round.", ollama.calls[1]["prompt"])

    async def test_sun_shape_question_goes_through_llm_with_factual_prompt(self) -> None:
        ollama = _CapturingOllama("The Sun is roughly spherical, not rectangular.")
        agent = ConversationAgent(
            AgentServices(
                ollama=ollama,  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=220,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "sun-shape-llm-test",
                "text": "I mean, do you know if the sun is round or rectangular?",
                "route_decision": {
                    "route": "chat",
                    "agents": ["conversation_agent", "speaker_agent"],
                    "intent": "general_conversation",
                    "confidence": 0.45,
                    "language": "en-US",
                    "source": "fallback",
                },
            }
        )

        result = await agent.run(request, AgentResult())

        self.assertEqual(result.speak_immediate[0].text, "The Sun is roughly spherical, not rectangular.")
        self.assertEqual(len(ollama.calls), 1)
        self.assertIn("correct obvious false premises", ollama.calls[0]["system"])
        self.assertIn("Current user said: I mean, do you know if the sun is round", ollama.calls[0]["prompt"])

    async def test_moon_shape_question_goes_through_llm_with_factual_prompt(self) -> None:
        ollama = _CapturingOllama("Yes. The Moon is roughly spherical, so it is round.")
        agent = ConversationAgent(
            AgentServices(
                ollama=ollama,  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=220,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "moon-round-llm-test",
                "text": "I think the moon is round. Do you agree with me?",
                "route_decision": {
                    "route": "chat",
                    "agents": ["conversation_agent", "speaker_agent"],
                    "intent": "general_conversation",
                    "confidence": 0.45,
                    "language": "en-US",
                    "source": "fallback",
                },
            }
        )

        result = await agent.run(request, AgentResult())

        self.assertEqual(result.speak_immediate[0].text, "Yes. The Moon is roughly spherical, so it is round.")
        self.assertEqual(len(ollama.calls), 1)
        self.assertIn("correct obvious false premises", ollama.calls[0]["system"])
        self.assertIn("common factual claims", ollama.calls[0]["system"])
        self.assertIn("Current user said: I think the moon is round.", ollama.calls[0]["prompt"])

    async def test_false_moon_shape_claim_goes_through_llm_with_factual_prompt(self) -> None:
        ollama = _CapturingOllama("No. The Moon is roughly spherical, so it is round.")
        agent = ConversationAgent(
            AgentServices(
                ollama=ollama,  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=220,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "moon-not-round-llm-test",
                "text": "I think the moon is not round. Do you agree with me?",
                "route_decision": {
                    "route": "chat",
                    "agents": ["conversation_agent", "speaker_agent"],
                    "intent": "general_conversation",
                    "confidence": 0.45,
                    "language": "en-US",
                    "source": "fallback",
                },
            }
        )

        result = await agent.run(request, AgentResult())

        self.assertEqual(result.speak_immediate[0].text, "No. The Moon is roughly spherical, so it is round.")
        self.assertEqual(len(ollama.calls), 1)
        self.assertIn("correct obvious false premises", ollama.calls[0]["system"])
        self.assertIn("Current user said: I think the moon is not round.", ollama.calls[0]["prompt"])

    async def test_moon_temperature_claim_goes_through_llm_with_factual_prompt(self) -> None:
        ollama = _CapturingOllama("No. The Moon's surface temperature varies widely.")
        agent = ConversationAgent(
            AgentServices(
                ollama=ollama,  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=220,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "moon-hot-llm-test",
                "text": "I think the moon is very hot. Do you agree with me?",
                "route_decision": {
                    "route": "chat",
                    "agents": ["conversation_agent", "speaker_agent"],
                    "intent": "general_conversation",
                    "confidence": 0.45,
                    "language": "en-US",
                    "source": "fallback",
                },
            }
        )

        result = await agent.run(request, AgentResult())

        self.assertEqual(result.speak_immediate[0].text, "No. The Moon's surface temperature varies widely.")
        self.assertEqual(len(ollama.calls), 1)
        self.assertIn("correct obvious false premises", ollama.calls[0]["system"])

    async def test_short_follow_up_uses_recent_sun_context_in_llm_prompt(self) -> None:
        ollama = _CapturingOllama("The Sun is extremely hot.")
        agent = ConversationAgent(
            AgentServices(
                ollama=ollama,  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=220,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "sun-follow-up-test",
                "text": "Is it cold or warm?",
                "history": [
                    {
                        "role": "user",
                        "text": "In my opinion, the sun is cold. Do you agree with me?",
                    },
                    {
                        "role": "assistant",
                        "text": "Nope, very hot. The Sun is not cold.",
                    },
                ],
                "route_decision": {
                    "route": "chat",
                    "agents": ["conversation_agent", "speaker_agent"],
                    "intent": "general_conversation",
                    "confidence": 0.45,
                    "language": "en-US",
                    "source": "fallback",
                },
            }
        )

        result = await agent.run(request, AgentResult())

        self.assertEqual(result.speak_immediate[0].text, "The Sun is extremely hot.")
        self.assertEqual(len(ollama.calls), 1)
        self.assertIn("Extracted memory:", ollama.calls[0]["prompt"])
        self.assertIn("Recent turn fallback", ollama.calls[0]["prompt"])
        self.assertIn("The Sun is not cold.", ollama.calls[0]["prompt"])

    async def test_song_requests_are_left_to_llm_as_original_spoken_creativity(self) -> None:
        ollama = _CapturingOllama()
        agent = ConversationAgent(
            AgentServices(
                ollama=ollama,  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=220,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "song-test",
                "text": "Go ahead and sing a song for me.",
                "context": {
                    "mind": {
                        "prompt_summary": (
                            "Core principles, owner-approved and not experience-mutable: "
                            "protect humans; be honest about abilities."
                        )
                    }
                },
                "route_decision": {
                    "route": "chat",
                    "agents": ["conversation_agent", "speaker_agent"],
                    "intent": "general_conversation",
                    "confidence": 0.91,
                    "language": "en-US",
                    "source": "llm",
                },
            }
        )

        result = await agent.run(request, AgentResult())

        self.assertEqual(result.speak_immediate[0].text, "Here is a little song I made for you.")
        self.assertEqual(len(ollama.calls), 1)
        system = ollama.calls[0]["system"]
        prompt = ollama.calls[0]["prompt"]
        self.assertIn("harmless creative speech requests", system)
        self.assertIn("provide the requested original content", system)
        self.assertIn("Never output internal skill identifiers", system)
        self.assertIn("Return only the spoken response text", system)
        self.assertIn("do not only announce readiness", system)
        self.assertIn("correct obvious false premises", system)
        self.assertIn("owner-approved mind context", system)
        self.assertIn("Mind principles and long-term goals", prompt)
        self.assertIn("owner-approved", prompt)

    async def test_completed_pending_tasks_are_not_fed_as_active_context(self) -> None:
        ollama = _CapturingOllama("Sand can be cold, depending on the environment.")
        agent = ConversationAgent(
            AgentServices(
                ollama=ollama,  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=220,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "completed-task-context-test",
                "text": "Tell me about cold sand.",
                "context": {
                    "active_pending_tasks": [],
                    "pending_tasks": [
                        {
                            "type": "robot_action",
                            "status": "done",
                            "summary": "soridormi.walk_forward",
                        }
                    ],
                },
                "route_decision": {
                    "route": "chat",
                    "agents": ["conversation_agent", "speaker_agent"],
                    "intent": "general_conversation",
                    "confidence": 0.91,
                    "language": "en-US",
                    "source": "llm",
                },
            }
        )

        await agent.run(request, AgentResult())

        self.assertEqual(len(ollama.calls), 1)
        prompt = ollama.calls[0]["prompt"]
        self.assertIn("Pending tasks:\nNone", prompt)
        self.assertNotIn("soridormi.walk_forward", prompt)

    async def test_long_song_response_is_split_into_tts_sized_sections(self) -> None:
        response = (
            "Verse one glows softly under a friendly moon. "
            "Verse two keeps walking through a field of tiny lights. "
            "Verse three comes home with a bright little chorus for you."
        )
        ollama = _CapturingOllama(response)
        agent = ConversationAgent(
            AgentServices(
                ollama=ollama,  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=70,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "long-song-test",
                "text": "Please sing a long song for me.",
                "route_decision": {
                    "route": "chat",
                    "agents": ["conversation_agent", "speaker_agent"],
                    "intent": "general_conversation",
                    "confidence": 0.91,
                    "language": "en-US",
                    "source": "llm",
                },
            }
        )

        result = await agent.run(request, AgentResult())

        self.assertGreater(len(result.speak_immediate), 1)
        self.assertTrue(all(len(item.text) <= 70 for item in result.speak_immediate))
        self.assertIn("Verse three", " ".join(item.text for item in result.speak_immediate))


if __name__ == "__main__":
    unittest.main()
