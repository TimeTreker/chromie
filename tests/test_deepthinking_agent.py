from __future__ import annotations

import unittest
from typing import Any

from agent.app.agents import AgentServices, DeepThinkingAgent
from agent.app.interaction import InteractionDraft
from agent.app.schema import AgentResult, AgentRunRequest
from shared.chromie_contracts.task_proposal import TaskProposal


class _CapturingOllama:
    def __init__(self, response: Any | list[Any] = "Here is the architecture I recommend.") -> None:
        self.responses = response if isinstance(response, list) else [response]
        self.calls: list[dict[str, Any]] = []

    async def generate(self, prompt: str, **kwargs: Any) -> Any:
        self.calls.append({"prompt": prompt, **kwargs})
        index = min(len(self.calls) - 1, len(self.responses) - 1)
        return self.responses[index]


class DeepThinkingAgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_deep_thinking_prompt_uses_session_memory_and_larger_budget(self) -> None:
        ollama = _CapturingOllama()
        agent = DeepThinkingAgent(
            AgentServices(
                ollama=ollama,  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=220,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "deep-test",
                "text": "Let's design the session memory architecture carefully.",
                "context": {
                    "mind": {
                        "prompt_summary": (
                            "Core principles, owner-approved and not experience-mutable: "
                            "protect humans; no raw low-level body commands."
                        )
                    },
                    "session_memory": {
                        "conversation_id": "local_default",
                        "current_task": {"summary": "design session memory"},
                        "memory_summary": "- Current task: design extracted prompt memory",
                        "extracted_memory": [
                            {
                                "scope": "task",
                                "kind": "goal",
                                "text": "Current task: design extracted prompt memory",
                                "confidence": 0.9,
                            }
                        ],
                        "forgetting_policy": {"hard_idle_timeout_sec": 900},
                    }
                },
                "route_decision": {
                    "route": "deep_thought",
                    "agents": ["deepthinking_agent", "speaker_agent"],
                    "intent": "session_memory_design",
                    "confidence": 0.91,
                    "language": "en-US",
                    "source": "llm",
                },
            }
        )

        result = await agent.run(request, AgentResult())

        self.assertEqual(result.speak_immediate[0].text, "Here is the architecture I recommend.")
        self.assertIn("deepthinking_agent", result.handled_by)
        self.assertEqual(len(ollama.calls), 1)
        call = ollama.calls[0]
        self.assertIn("Priority Rule 1", call["system"])
        self.assertIn("deepthinking agent", call["system"])
        self.assertIn("split complex requests", call["system"])
        self.assertIn("Generalization-first is a core principle", call["system"])
        self.assertIn("Do not turn examples into keyword rules", call["system"])
        self.assertIn("Bad keyword-rule", call["system"])
        self.assertIn("All spoken output must be in the target language", call["system"])
        self.assertIn("Never output bullet points, labels, or numbered lists", call["system"])
        self.assertIn("Speech is not a special final text channel", call["system"])
        self.assertIn("Return compact JSON only with keys tasks, quick_review, and reason", call["system"])
        self.assertIn("chromie.speak", call["system"])
        self.assertIn("human owner approval", call["system"])
        self.assertIn("Normally do not repeat, quote, or paraphrase", call["system"])
        self.assertIn("interpret it as a request to do it now", call["system"])
        self.assertIn("Do not answer only with ability, willingness, or readiness", call["system"])
        self.assertIn("Session working memory", call["prompt"])
        self.assertIn("Extracted conversation context", call["prompt"])
        self.assertIn("Output Contract:", call["prompt"])
        self.assertIn("Top-level keys: tasks, quick_review, reason only", call["prompt"])
        self.assertIn("\"skill_id\":\"chromie.speak\"", call["prompt"])
        self.assertIn("Do not output spoken_response, speech_tasks, action_tasks", call["prompt"])
        self.assertIn("Mind principles, long-term goals, and experience boundaries", call["prompt"])
        self.assertIn("owner-approved", call["prompt"])
        self.assertIn("design session memory", call["prompt"])
        self.assertIn("memory.goal: Current task: design extracted prompt memory", call["prompt"])
        self.assertIn("Apply the Priority Rules strictly", call["prompt"])
        self.assertEqual(call["options"]["num_ctx"], 8192)
        self.assertEqual(call["options"]["num_predict"], 384)

    async def test_conversation_agent_is_not_required_for_deep_thought(self) -> None:
        ollama = _CapturingOllama("First, split the work into memory, routing, and validation.")
        agent = DeepThinkingAgent(
            AgentServices(
                ollama=ollama,  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=70,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "deep-test",
                "text": "Please split this implementation task.",
                "route_decision": {
                    "route": "deep_thought",
                    "agents": ["deepthinking_agent", "speaker_agent"],
                    "intent": "implementation_planning",
                    "confidence": 0.91,
                    "language": "en-US",
                    "source": "llm",
                },
            }
        )

        result = await agent.run(request, AgentResult())

        self.assertEqual(len(ollama.calls), 1)
        self.assertIn("deepthinking_agent", result.handled_by)
        self.assertNotIn("conversation_agent", result.handled_by)
        self.assertGreater(len(result.speak_immediate), 0)

    async def test_chinese_deep_thought_uses_english_internal_prompt_with_target_language(self) -> None:
        ollama = _CapturingOllama("我会用中文回答。")
        agent = DeepThinkingAgent(
            AgentServices(
                ollama=ollama,  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=220,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "deep-zh-prompt-test",
                "text": "请认真想一下这个架构问题。",
                "history": [
                    {"role": "user", "text": "我们要减少提示词漂移。"},
                    {"role": "assistant", "text": "我会检查深度思考提示词。"},
                ],
                "route_decision": {
                    "route": "deep_thought",
                    "agents": ["deepthinking_agent", "speaker_agent"],
                    "intent": "architecture_review",
                    "confidence": 0.91,
                    "language": "zh-CN",
                    "source": "llm",
                },
            }
        )

        result = await agent.run(request, AgentResult())

        self.assertEqual(result.speak_immediate[0].text, "我会用中文回答。")
        self.assertEqual(len(ollama.calls), 1)
        call = ollama.calls[0]
        self.assertIn("You are Chromie's deepthinking agent", call["system"])
        self.assertIn("All spoken output must be in the target language", call["system"])
        self.assertNotIn("你是 Chromie 的 deepthinking agent", call["system"])
        self.assertIn("Target spoken language: zh-CN", call["prompt"])
        self.assertIn("Extracted conversation context", call["prompt"])
        self.assertNotIn("Recent conversation", call["prompt"])
        self.assertNotIn("User:", call["prompt"])
        self.assertNotIn("我们要减少提示词漂移", call["prompt"])
        self.assertNotIn("最近对话", call["prompt"])

    async def test_deep_thought_uses_extracted_context_not_raw_history(self) -> None:
        ollama = _CapturingOllama("Yes, the Moon is round.")
        agent = DeepThinkingAgent(
            AgentServices(
                ollama=ollama,  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=220,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "deep-extracted-context-test",
                "text": "Do you agree?",
                "history": [
                    {
                        "role": "user",
                        "text": "I think the moon is round. Do you think so?",
                    },
                    {"role": "assistant", "text": "The moon is round."},
                ],
                "context": {
                    "session_memory": {
                        "kind": "short_term_session_memory",
                        "conversation_id": "local_default",
                        "recent_user_request": "I think the moon is round. Do you think so?",
                        "recent_assistant_response": "The moon is round.",
                        "current_task_context": {
                            "task_id": "task-moon",
                            "status": "open",
                            "task_relation": "continue_task",
                            "task_type": "conversation",
                            "goal": "Discuss whether the Moon is round",
                            "important_claims": ["The user thinks the Moon is round."],
                            "entities": ["Moon"],
                            "last_meaningful_user_turn": (
                                "I think the moon is round. Do you think so?"
                            ),
                            "last_assistant_response": "The moon is round.",
                        },
                    }
                },
                "route_decision": {
                    "route": "deep_thought",
                    "agents": ["deepthinking_agent", "speaker_agent"],
                    "intent": "deep_thought_low_confidence",
                    "confidence": 0.55,
                    "language": "en-US",
                    "source": "llm",
                },
            }
        )

        await agent.run(request, AgentResult())

        prompt = ollama.calls[0]["prompt"]
        self.assertIn("Extracted conversation context", prompt)
        self.assertIn("Discuss whether the Moon is round", prompt)
        self.assertIn("The user thinks the Moon is round.", prompt)
        self.assertNotIn("I think the moon is round. Do you think so?", prompt)
        self.assertNotIn("The moon is round.", prompt)
        self.assertNotIn("Recent conversation", prompt)

    async def test_completed_pending_tasks_are_not_fed_as_active_context(self) -> None:
        ollama = _CapturingOllama("Let's reason about the claim directly.")
        agent = DeepThinkingAgent(
            AgentServices(
                ollama=ollama,  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=220,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "deep-completed-task-context-test",
                "text": "Think carefully about whether the sun is cold.",
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
                    "route": "deep_thought",
                    "agents": ["deepthinking_agent", "speaker_agent"],
                    "intent": "reasoning",
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

    async def test_structured_deep_thought_emits_unified_skill_tasks(self) -> None:
        ollama = _CapturingOllama(
            {
                "tasks": [
                    {
                        "skill_id": "chromie.speak",
                        "args": {
                            "text": "Moving now.",
                            "style": "brief",
                            "priority": "normal",
                        },
                        "timing": "immediate",
                        "reason": "Acknowledge the direct body request.",
                    },
                    {
                        "skill_id": "soridormi.walk_forward",
                        "args": {"duration_s": 15, "speed": "quickly"},
                        "timing": "sequential",
                        "reason": "The user asked Chromie to walk forward.",
                    }
                ],
                "reason": "Direct body action with supplied capability.",
            }
        )
        agent = DeepThinkingAgent(
            AgentServices(
                ollama=ollama,  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=220,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "deep-structured-action-test",
                "text": "Walk forward for 15 seconds, quickly.",
                "route_decision": {
                    "route": "deep_thought",
                    "agents": ["deepthinking_agent", "speaker_agent"],
                    "intent": "deep_thought_complex_reasoning",
                    "confidence": 0.74,
                    "language": "en-US",
                    "source": "llm",
                    "candidate_capabilities": [
                        {
                            "capability_id": "soridormi.walk_forward",
                            "description": "Walk forward for a bounded duration.",
                            "available": True,
                            "interaction_executable": True,
                            "requires_confirmation": True,
                            "input_schema": {
                                "type": "object",
                                "properties": {
                                    "duration_s": {
                                        "type": "number",
                                        "minimum": 0.1,
                                        "maximum": 30,
                                    },
                                    "speed": {
                                        "type": "string",
                                        "enum": ["slow", "normal", "quick"],
                                    },
                                },
                                "required": ["duration_s"],
                                "additionalProperties": False,
                            },
                        }
                    ],
                },
            }
        )
        draft = InteractionDraft()

        result = await agent.run(request, draft)
        response = result.to_response()

        self.assertEqual(response.speech[0].text, "Moving now.")
        self.assertEqual(len(response.skills), 1)
        skill = response.skills[0]
        self.assertEqual(skill.skill_id, "soridormi.walk_forward")
        self.assertEqual(skill.args, {"duration_s": 15, "speed": "quick"})
        self.assertEqual(skill.timing, "sequential")
        self.assertTrue(skill.requires_confirmation)
        self.assertEqual(skill.metadata["source"], "deepthinking_skill_task")
        self.assertEqual(response.metadata["deepthinking_output_mode"], "skill_tasks")
        self.assertEqual(response.metadata["deepthinking_proposed_task_count"], 2)
        self.assertEqual(response.metadata["deepthinking_valid_task_count"], 2)
        self.assertEqual(response.metadata["deepthinking_proposed_effect_task_count"], 1)
        self.assertEqual(response.metadata["deepthinking_valid_effect_task_count"], 1)
        self.assertEqual(response.metadata["deepthinking_proposed_action_count"], 1)
        self.assertEqual(response.metadata["deepthinking_valid_action_count"], 1)
        self.assertEqual(response.metadata["language"], "en-US")
        proposals = [
            TaskProposal.model_validate(item)
            for item in response.metadata["deepthinking_task_proposals"]
        ]
        self.assertEqual([item.task_type for item in proposals], ["speech.speak", "task.execute_skill"])
        self.assertEqual(proposals[0].state, "committed")
        self.assertEqual(proposals[1].state, "advisory")
        self.assertEqual(proposals[1].skill_id, "soridormi.walk_forward")
        self.assertEqual(ollama.calls[0]["response_format"], "json")

    async def test_quick_router_review_supersedes_route_proposals(self) -> None:
        ollama = _CapturingOllama(
            {
                "tasks": [
                    {
                        "skill_id": "chromie.speak",
                        "args": {
                            "text": "Thanks for the warning. I will hold still.",
                            "style": "warning",
                            "priority": "normal",
                        },
                        "timing": "immediate",
                        "reason": "Correct the quick window-gaze interpretation.",
                    }
                ],
                "quick_review": {
                    "decision": "supersede",
                    "reason": "The quick router treated a warning as a gaze command.",
                    "superseded_task_ids": ["quick_intent:0:task.execute_skill"],
                },
                "reason": "Warning semantics replace quick proposal.",
            }
        )
        agent = DeepThinkingAgent(
            AgentServices(
                ollama=ollama,  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=220,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "deep-quick-review-test",
                "text": "Look out!",
                "route_decision": {
                    "route": "deep_thought",
                    "agents": ["deepthinking_agent", "speaker_agent"],
                    "intent": "deep_thought_low_confidence",
                    "confidence": 0.55,
                    "language": "en-US",
                    "source": "llm",
                    "metadata": {
                        "quick_router_review_request": {
                            "schema_version": 1,
                            "execution_state": "not_committed",
                            "quick_route": "robot_action",
                            "quick_intent": "compound_common_catalog_task",
                            "quick_task_proposals": [
                                {
                                    "id": "quick_intent:0:task.execute_skill",
                                    "source": "quick_intent",
                                    "proposal_kind": "action",
                                    "task_type": "task.execute_skill",
                                    "state": "advisory",
                                    "effectful": True,
                                    "priority": "normal",
                                    "sequence": 0,
                                    "skill_id": "soridormi.look_at_window",
                                }
                            ],
                        }
                    },
                },
            }
        )
        draft = InteractionDraft()

        result = await agent.run(request, draft)
        response = result.to_response()

        self.assertEqual(response.speech[0].text, "Thanks for the warning. I will hold still.")
        self.assertEqual(response.metadata["quick_router_review_decision"], "supersede")
        self.assertIn("quick_router_review_request", ollama.calls[0]["prompt"])
        self.assertIn("soridormi.look_at_window", ollama.calls[0]["prompt"])
        proposals = [
            TaskProposal.model_validate(item)
            for item in response.metadata["superseded_task_proposals"]
        ]
        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0].state, "superseded")
        self.assertEqual(proposals[0].skill_id, "soridormi.look_at_window")
        self.assertEqual(
            proposals[0].superseded_by,
            "deepthinking:0:speech.speak",
        )

    async def test_stock_model_disclaimer_is_retried_as_chromie(self) -> None:
        ollama = _CapturingOllama(
            [
                "I do not have personal opinions on whether the sun is hot.",
                {
                    "decision": "revise",
                    "reason": "Objective fact should be answered directly.",
                    "spoken_response": "Yes. The Sun is extremely hot.",
                },
            ]
        )
        agent = DeepThinkingAgent(
            AgentServices(
                ollama=ollama,  # type: ignore[arg-type]
                response_reviewer=ollama,  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=220,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "deep-sun-hot-retry-test",
                "text": "Do you think the sun is hot?",
                "route_decision": {
                    "route": "deep_thought",
                    "agents": ["deepthinking_agent", "speaker_agent"],
                    "intent": "deep_thought_low_confidence",
                    "confidence": 0.55,
                    "language": "en-US",
                    "source": "llm",
                },
            }
        )

        result = await agent.run(request, AgentResult())

        self.assertEqual(result.speak_immediate[0].text, "Yes. The Sun is extremely hot.")
        self.assertEqual(len(ollama.calls), 2)
        self.assertIn("Chromie's first-person robot persona", ollama.calls[0]["system"])
        self.assertIn("Candidate spoken response", ollama.calls[1]["prompt"])
        self.assertIn("Judge meaning, not keyword rules", ollama.calls[1]["system"])

    async def test_empty_joke_acknowledgement_is_retried_in_deep_thought(self) -> None:
        ollama = _CapturingOllama(
            [
                "I can tell you a joke. Why not?",
                {
                    "decision": "revise",
                    "reason": "The candidate repeats an empty promise instead of telling the joke.",
                    "spoken_response": "Why did Chromie take a nap? To reboot her sparkle.",
                },
            ]
        )
        agent = DeepThinkingAgent(
            AgentServices(
                ollama=ollama,  # type: ignore[arg-type]
                response_reviewer=ollama,  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=220,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "deep-joke-empty-ack-test",
                "text": "If you can, just tell me. Why not?",
                "context": {
                    "history": [
                        {"role": "user", "text": "Hey, can you tell me a joke?"},
                        {"role": "assistant", "text": "I can tell you a joke."},
                    ],
                    "current_task_context": {
                        "task_id": "task-joke",
                        "task_type": "conversation",
                        "goal": "Tell the user a joke.",
                        "last_meaningful_user_turn": "Hey, can you tell me a joke?",
                        "last_assistant_response": "I can tell you a joke.",
                    },
                },
                "route_decision": {
                    "route": "deep_thought",
                    "agents": ["deepthinking_agent", "speaker_agent"],
                    "intent": "deep_thought_low_confidence",
                    "confidence": 0.55,
                    "language": "en-US",
                    "source": "llm",
                },
            }
        )

        result = await agent.run(request, AgentResult())

        self.assertEqual(
            result.speak_immediate[0].text,
            "Why did Chromie take a nap? To reboot her sparkle.",
        )
        self.assertEqual(len(ollama.calls), 2)
        self.assertIn("If recent context shows Chromie already promised", ollama.calls[0]["system"])
        self.assertIn("the user says they are waiting", ollama.calls[0]["system"])
        self.assertIn("deliver the promised content now", ollama.calls[0]["system"])
        self.assertIn("Tell the user a joke.", ollama.calls[1]["prompt"])

    async def test_truncated_one_character_response_is_replaced_before_tts(self) -> None:
        ollama = _CapturingOllama(
            [
                "I",
                {
                    "decision": "accept",
                    "reason": "bad reviewer accepted a fragment",
                    "spoken_response": "",
                },
            ]
        )
        agent = DeepThinkingAgent(
            AgentServices(
                ollama=ollama,  # type: ignore[arg-type]
                response_reviewer=ollama,  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=220,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "deep-truncated-output-test",
                "text": "Can you walk forward for 15 minutes?",
                "route_decision": {
                    "route": "deep_thought",
                    "agents": ["deepthinking_agent", "speaker_agent"],
                    "intent": "deep_thought_low_confidence",
                    "confidence": 0.0,
                    "language": "en-US",
                    "source": "llm",
                },
            }
        )

        result = await agent.run(request, AgentResult())

        self.assertEqual(
            result.speak_immediate[0].text,
            "I got stuck forming that answer. Please say it again.",
        )
        self.assertEqual(len(ollama.calls), 2)


if __name__ == "__main__":
    unittest.main()
