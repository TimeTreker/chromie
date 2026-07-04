from __future__ import annotations

import unittest
from typing import Any

from agent.app.agents import AgentServices
from agent.app.capabilities.catalog import CapabilityCatalog, CapabilityMatch, CapabilitySearchResult, CatalogCapability
from agent.app.capabilities.models import (
    AgentManifest,
    CapabilityBundle,
    CapabilityRegistry,
    ToolCapability,
)
from agent.app.runtime import InteractionRuntime
from agent.app.schema import AgentRunRequest


class _Outcome:
    status = "success"
    error = None
    output = {
        "mode": "sim",
        "skills": [
            {
                "skill_id": "walk_forward",
                "description": "Walk forward for a bounded duration.",
                "parameters_schema": {
                    "type": "object",
                    "properties": {
                        "duration_s": {"type": "number", "minimum": 0.1, "maximum": 5.0},
                        "speed": {
                            "type": "string",
                            "enum": ["slow", "normal", "medium", "quick", "fast_limited"],
                        },
                    },
                    "required": ["duration_s"],
                },
                "available": True,
                "requires_confirmation": True,
            }
        ],
    }


class _StrictWalkOutcome:
    status = "success"
    error = None
    output = {
        "mode": "sim",
        "skills": [
            {
                "skill_id": "walk_velocity",
                "description": "Walk forward by tracking a bounded body velocity command.",
                "parameters_schema": {
                    "type": "object",
                    "properties": {
                        "vx_mps": {"type": "number", "minimum": 0.01, "maximum": 0.25},
                        "duration_s": {"type": "number", "minimum": 0.5, "maximum": 20.0},
                    },
                    "required": ["vx_mps", "duration_s"],
                    "additionalProperties": False,
                },
                "available": True,
                "requires_confirmation": True,
            },
            {
                "skill_id": "walk_forward",
                "description": "Walk forward a short distance at a safe speed.",
                "parameters_schema": {
                    "type": "object",
                    "properties": {"speed": {"type": "string", "enum": ["normal"]}},
                    "additionalProperties": False,
                },
                "available": True,
                "requires_confirmation": True,
            },
            {
                "skill_id": "blink_eyes",
                "description": "Blink the robot eyes.",
                "parameters_schema": {
                    "type": "object",
                    "properties": {"count": {"type": "number"}},
                    "additionalProperties": False,
                },
                "available": True,
                "requires_confirmation": False,
            },
        ],
    }


class _LookForwardOutcome:
    status = "success"
    error = None
    output = {
        "mode": "sim",
        "skills": [
            {
                "skill_id": "look_at_person",
                "description": "Look, face, or gaze forward toward the user for a bounded time.",
                "parameters_schema": {
                    "type": "object",
                    "properties": {"duration_s": {"type": "number", "minimum": 0.1, "maximum": 10.0}},
                    "additionalProperties": False,
                },
                "available": True,
                "requires_confirmation": False,
            },
            {
                "skill_id": "blink_eyes",
                "description": "Blink the robot eyes.",
                "parameters_schema": {
                    "type": "object",
                    "properties": {"count": {"type": "number"}},
                    "additionalProperties": False,
                },
                "available": True,
                "requires_confirmation": False,
            },
            {
                "skill_id": "walk_forward",
                "description": "Walk forward a short distance at a safe speed.",
                "parameters_schema": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
                "available": True,
                "requires_confirmation": True,
            },
        ],
    }


class _HeadGestureOutcome:
    status = "success"
    error = None
    output = {
        "mode": "sim",
        "skills": [
            {
                "skill_id": "shake_no",
                "description": "Shake the robot head no.",
                "parameters_schema": {
                    "type": "object",
                    "properties": {"count": {"type": "number", "minimum": 2, "maximum": 8}},
                    "additionalProperties": False,
                },
                "available": True,
                "requires_confirmation": False,
            },
            {
                "skill_id": "nod_yes",
                "description": "Nod the robot head yes.",
                "parameters_schema": {
                    "type": "object",
                    "properties": {"count": {"type": "number", "minimum": 2, "maximum": 8}},
                    "additionalProperties": False,
                },
                "available": True,
                "requires_confirmation": False,
            },
        ],
    }


class _BlinkLimitOutcome:
    status = "success"
    error = None
    output = {
        "mode": "sim",
        "skills": [
            {
                "skill_id": "blink_eyes",
                "description": "Blink the robot eyes visibly.",
                "parameters_schema": {
                    "type": "object",
                    "properties": {"count": {"type": "integer", "minimum": 1, "maximum": 6}},
                    "required": ["count"],
                    "additionalProperties": False,
                },
                "effects": ["visual_expression"],
                "safety_class": "low_risk_action",
                "available": True,
                "requires_confirmation": False,
            }
        ],
    }


class _BlinkDefaultOutcome:
    status = "success"
    error = None
    output = {
        "mode": "sim",
        "skills": [
            {
                "skill_id": "blink_eyes",
                "description": "Blink the robot eyes visibly.",
                "parameters_schema": {
                    "type": "object",
                    "properties": {
                        "closed_duration_s": {
                            "type": "number",
                            "minimum": 0.05,
                            "maximum": 0.5,
                            "default": 0.12,
                        },
                        "count": {
                            "type": "number",
                            "minimum": 1,
                            "maximum": 6,
                            "default": 2,
                        },
                        "intensity": {
                            "type": "number",
                            "minimum": 0.0,
                            "maximum": 1.0,
                            "default": 1.0,
                        },
                        "open_duration_s": {
                            "type": "number",
                            "minimum": 0.05,
                            "maximum": 1.0,
                            "default": 0.18,
                        },
                    },
                    "additionalProperties": False,
                },
                "effects": ["visual_expression"],
                "safety_class": "low_risk_action",
                "available": True,
                "requires_confirmation": False,
            }
        ],
    }


class _WalkChoiceOutcome:
    status = "success"
    error = None
    output = {
        "mode": "sim",
        "skills": [
            {
                "skill_id": "walk_velocity",
                "description": "Track a bounded body velocity command vx, vy, and yaw.",
                "parameters_schema": {
                    "type": "object",
                    "properties": {
                        "vx_mps": {"type": "number", "default": 0.12},
                        "duration_s": {"type": "number", "minimum": 0.5, "maximum": 20.0},
                    },
                    "additionalProperties": False,
                },
                "available": True,
                "requires_confirmation": True,
            },
            {
                "skill_id": "walk_forward",
                "description": "Human-facing wrapper for natural walk forward speed labels.",
                "parameters_schema": {
                    "type": "object",
                    "properties": {
                        "duration_s": {"type": "number", "minimum": 0.5, "maximum": 20.0},
                        "speed": {"type": "string", "enum": ["slow", "normal", "quick"]},
                    },
                    "additionalProperties": False,
                },
                "available": True,
                "requires_confirmation": True,
            },
        ],
    }


class _WalkAndSocialOutcome:
    status = "success"
    error = None
    output = {
        "mode": "sim",
        "skills": [
            {
                "skill_id": "walk_velocity",
                "description": "Walk forward by tracking a bounded body velocity command.",
                "parameters_schema": {
                    "type": "object",
                    "properties": {
                        "vx_mps": {"type": "number", "minimum": 0.01, "maximum": 0.25},
                        "duration_s": {"type": "number", "minimum": 0.5, "maximum": 20.0},
                    },
                    "required": ["vx_mps", "duration_s"],
                    "additionalProperties": False,
                },
                "available": True,
                "requires_confirmation": True,
            },
            {
                "skill_id": "nod_yes",
                "description": "Nod the robot head yes as a social acknowledgement.",
                "parameters_schema": {
                    "type": "object",
                    "properties": {"count": {"type": "number", "minimum": 2, "maximum": 8}},
                    "additionalProperties": False,
                },
                "available": True,
                "requires_confirmation": False,
            },
            {
                "skill_id": "look_at_person",
                "description": "Look at the user for a bounded time.",
                "parameters_schema": {
                    "type": "object",
                    "properties": {"duration_s": {"type": "number", "minimum": 0.1, "maximum": 10.0}},
                    "additionalProperties": False,
                },
                "available": True,
                "requires_confirmation": False,
            },
            {
                "skill_id": "look_at_person",
                "description": "Look at the user for a bounded time.",
                "parameters_schema": {
                    "type": "object",
                    "properties": {"duration_s": {"type": "number", "minimum": 0.1, "maximum": 10.0}},
                    "additionalProperties": False,
                },
                "available": True,
                "requires_confirmation": False,
            },
        ],
    }


class _ForwardAndSocialOutcome:
    status = "success"
    error = None
    output = {
        "mode": "sim",
        "skills": [
            {
                "skill_id": "walk_forward",
                "description": "Walk forward a short distance at a safe speed.",
                "parameters_schema": {
                    "type": "object",
                    "properties": {
                        "duration_s": {"type": "number", "minimum": 0.5, "maximum": 20.0},
                        "speed": {"type": "string", "enum": ["slow", "normal", "quick"]},
                    },
                    "additionalProperties": False,
                },
                "available": True,
                "requires_confirmation": True,
            },
            {
                "skill_id": "nod_yes",
                "description": "Nod the robot head yes as a social acknowledgement.",
                "parameters_schema": {
                    "type": "object",
                    "properties": {"count": {"type": "number", "minimum": 2, "maximum": 8}},
                    "additionalProperties": False,
                },
                "available": True,
                "requires_confirmation": False,
            },
        ],
    }


class _Invoker:
    async def invoke(self, tool_name: str, arguments: dict[str, Any], *, context=None) -> _Outcome:
        del arguments, context
        assert tool_name == "soridormi.skill.list"
        return _Outcome()


class _StrictWalkInvoker:
    async def invoke(self, tool_name: str, arguments: dict[str, Any], *, context=None) -> _StrictWalkOutcome:
        del arguments, context
        assert tool_name == "soridormi.skill.list"
        return _StrictWalkOutcome()


class _LookForwardInvoker:
    async def invoke(self, tool_name: str, arguments: dict[str, Any], *, context=None) -> _LookForwardOutcome:
        del arguments, context
        assert tool_name == "soridormi.skill.list"
        return _LookForwardOutcome()


class _HeadGestureInvoker:
    async def invoke(self, tool_name: str, arguments: dict[str, Any], *, context=None) -> _HeadGestureOutcome:
        del arguments, context
        assert tool_name == "soridormi.skill.list"
        return _HeadGestureOutcome()


class _BlinkLimitInvoker:
    async def invoke(self, tool_name: str, arguments: dict[str, Any], *, context=None) -> _BlinkLimitOutcome:
        del arguments, context
        assert tool_name == "soridormi.skill.list"
        return _BlinkLimitOutcome()


class _BlinkDefaultInvoker:
    async def invoke(self, tool_name: str, arguments: dict[str, Any], *, context=None) -> _BlinkDefaultOutcome:
        del arguments, context
        assert tool_name == "soridormi.skill.list"
        return _BlinkDefaultOutcome()


class _WalkChoiceInvoker:
    async def invoke(self, tool_name: str, arguments: dict[str, Any], *, context=None) -> _WalkChoiceOutcome:
        del arguments, context
        assert tool_name == "soridormi.skill.list"
        return _WalkChoiceOutcome()


class _WalkAndSocialInvoker:
    async def invoke(self, tool_name: str, arguments: dict[str, Any], *, context=None) -> _WalkAndSocialOutcome:
        del arguments, context
        assert tool_name == "soridormi.skill.list"
        return _WalkAndSocialOutcome()


class _ForwardAndSocialInvoker:
    async def invoke(self, tool_name: str, arguments: dict[str, Any], *, context=None) -> _ForwardAndSocialOutcome:
        del arguments, context
        assert tool_name == "soridormi.skill.list"
        return _ForwardAndSocialOutcome()


class _Ollama:
    async def generate(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        assert "soridormi.walk_forward" in prompt
        assert "Global Context Group" in prompt
        assert "Worldview" in prompt
        assert "Lifeview" in prompt
        assert "Valueview" in prompt
        assert "Session Context Group" in prompt
        assert "Current Job" in prompt
        assert "Task Context Group" in prompt
        assert "Cost Function" in prompt
        assert "Output Contract" in prompt
        assert prompt.index("Global Context Group") < prompt.index("Session Context Group")
        assert prompt.index("Session Context Group") < prompt.index("Current Job")
        assert prompt.index("Current Job") < prompt.index("Task Context Group")
        assert kwargs["response_format"] == "json"
        system = str(kwargs["system"])
        assert "Schema obedience is more important" in system
        assert "Never combine an unrelated spoken answer with a body skill" in prompt
        assert "Generalization-first principle" in system
        assert "do not turn prompt wording into phrase rules" in system
        return {
            "decision": "execute",
            "speech": "Walking ahead for 10 minutes.",
            "skills": [
                {
                    "skill_id": "soridormi.walk_forward",
                    "args": {"duration_s": 1.0},
                }
            ],
        }


class _InvalidWalkOllama:
    async def generate(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        assert "soridormi.walk_forward" in prompt
        assert kwargs["response_format"] == "json"
        return {
            "decision": "execute",
            "speech": "Walking forward for five seconds.",
            "skills": [
                {
                    "skill_id": "soridormi.walk_forward",
                    "args": {"duration_s": 5.0},
                }
            ],
        }


class _OverLimitBlinkClarifyOllama:
    async def generate(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        assert "Brink your eyes for 15 times." in prompt
        assert "Router-selected exact skill_id: soridormi.blink_eyes" in prompt
        assert "soridormi.blink_eyes" in prompt
        assert '"maximum":6' in prompt
        assert kwargs["response_format"] == "json"
        return {
            "decision": "clarify",
            "speech": "I can blink my eyes, but I can only do it up to 6 times at a time.",
            "skills": [],
        }


class _OverLimitBlinkClampedExecuteOllama:
    async def generate(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        assert "Brink your eyes for 15 times." in prompt
        assert "Router-selected exact skill_id: soridormi.blink_eyes" in prompt
        assert "soridormi.blink_eyes" in prompt
        assert '"maximum":6' in prompt
        assert kwargs["response_format"] == "json"
        return {
            "decision": "execute",
            "speech": "Okay, I'll blink my eyes 15 times for you!",
            "skills": [
                {
                    "skill_id": "soridormi.blink_eyes",
                    "args": {"count": 6},
                }
            ],
        }


class _FailIfCalledOllama:
    async def generate(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        del prompt, kwargs
        raise AssertionError("capability planner should not be called")


class _SelectedWalkOllama:
    async def generate(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        assert "soridormi.walk_forward" in prompt
        assert "Router-selected exact skill_id: soridormi.walk_forward" in prompt
        assert kwargs["response_format"] == "json"
        assert "When decision is execute, skills is required" in prompt
        assert "Never return execute with skills omitted" in prompt
        assert "Router-selected exact skill_id is best" in prompt
        return {
            "decision": "execute",
            "speech": "Walking forward for 3 seconds.",
            "skills": [
                {
                    "skill_id": "soridormi.walk_forward",
                    "args": {"duration_s": 3.0, "speed": "quick"},
                }
            ],
        }


class _ExtractedMemoryCapabilityOllama:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def generate(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        self.prompts.append(prompt)
        assert "Extracted memory" in prompt
        assert "Current task: walk forward using extracted memory" in prompt
        assert "RAW_HISTORY_SHOULD_NOT_REACH_CAPABILITY_PROMPT" not in prompt
        assert "RAW_CONTEXT_HISTORY_SHOULD_NOT_REACH_CAPABILITY_PROMPT" not in prompt
        assert "RAW_RECENT_USER_SHOULD_NOT_REACH_CAPABILITY_PROMPT" not in prompt
        assert kwargs["response_format"] == "json"
        return {
            "decision": "execute",
            "speech": "Walking forward.",
            "skills": [
                {
                    "skill_id": "soridormi.walk_forward",
                    "args": {"duration_s": 1.0, "speed": "quick"},
                }
            ],
        }


class _SelectedVelocityBetterForwardOllama:
    async def generate(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        assert "Router-selected exact skill_id: soridormi.walk_velocity" in prompt
        assert "soridormi.walk_velocity" in prompt
        assert "soridormi.walk_forward" in prompt
        assert kwargs["response_format"] == "json"
        return {
            "decision": "execute",
            "speech": "Walking forward quickly for 15 seconds.",
            "skills": [
                {
                    "skill_id": "soridormi.walk_forward",
                    "args": {"duration_s": 15.0, "speed": "quick"},
                }
            ],
        }


class _RecoveredDeepThoughtWalkOllama:
    async def generate(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        assert "soridormi.walk_forward" in prompt
        assert kwargs["response_format"] == "json"
        return {
            "tasks": [
                {
                    "skill_id": "chromie.speak",
                    "args": {"text": "Walking forward quickly for 15 seconds."},
                    "timing": "immediate",
                },
                {
                    "skill_id": "soridormi.walk_forward",
                    "args": {"duration_s": 15.0, "speed": "quick"},
                    "timing": "sequential",
                }
            ],
            "reason": "Deepthinking planned the direct motion from catalog context.",
        }


class _LookForwardOllama:
    async def generate(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        assert "soridormi.look_at_person" in prompt
        assert "soridormi.blink_eyes" in prompt
        assert "soridormi.walk_forward" in prompt
        assert "Task context" in prompt
        assert "Current Job" in prompt
        assert "Can you look forward for some time" in prompt
        assert "distinguish gaze/attention/orientation from locomotion" in prompt
        assert kwargs["response_format"] == "json"
        return {
            "decision": "execute",
            "speech": "Looking forward and blinking.",
            "skills": [
                {
                    "skill_id": "soridormi.look_at_person",
                    "args": {"duration_s": 5.0},
                },
                {
                    "skill_id": "soridormi.blink_eyes",
                    "args": {"count": 2},
                },
            ],
        }


class _PoliteHeadQuestionOllama:
    async def generate(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        assert "你能摇头吗" in prompt
        assert "soridormi.shake_no" in prompt
        assert kwargs["response_format"] == "json"
        assert "Polite ability-shaped requests can be action requests" in prompt
        assert "physical action now" in prompt
        assert "For execute, speech is required" in prompt
        assert "this planner owns the execution speech" in prompt
        return {
            "decision": "execute",
            "speech": "我会摇头。",
            "skills": [
                {
                    "skill_id": "soridormi.shake_no",
                    "args": {"count": 2},
                }
            ],
        }


class _EmptySpeechHeadQuestionOllama:
    async def generate(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        assert "soridormi.shake_no" in prompt
        assert kwargs["response_format"] == "json"
        return {
            "decision": "execute",
            "speech": "",
            "skills": [
                {
                    "skill_id": "soridormi.shake_no",
                    "args": {"count": 2},
                }
            ],
        }


class _AdverbSpeedOllama:
    async def generate(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        assert "soridormi.walk_forward" in prompt
        assert '"quick"' in prompt
        assert "Every enum argument must be copied exactly" in prompt
        assert "Map natural wording to enum tokens by semantic meaning" in prompt
        assert kwargs["response_format"] == "json"
        return {
            "decision": "execute",
            "speech": "Walking ahead quickly.",
            "skills": [
                {
                    "skill_id": "soridormi.walk_forward",
                    "args": {"duration_s": 1.0, "speed": "quickly"},
                }
            ],
        }


class _DuplicateWalkOllama:
    async def generate(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        assert "soridormi.walk_forward" in prompt
        assert kwargs["response_format"] == "json"
        return {
            "decision": "execute",
            "speech": "Walking forward.",
            "skills": [
                {
                    "skill_id": "soridormi.walk_forward",
                    "args": {"duration_s": 1.0, "speed": "quick"},
                },
                {
                    "skill_id": "soridormi.walk_forward",
                    "args": {"speed": "quick", "duration_s": 1.0},
                },
            ],
        }


class _FullApiOllama:
    async def generate(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        assert "Available capability API surface" in prompt
        assert "soridormi.wave_hand" in prompt
        assert "soridormi.nod_yes" in prompt
        assert '"count"' in prompt
        assert kwargs["response_format"] == "json"
        return {
            "decision": "execute",
            "speech": "Waving.",
            "skills": [
                {
                    "skill_id": "soridormi.wave_hand",
                    "args": {"count": 2},
                }
            ],
        }


class _BrokenCapabilityPlannerOllama:
    async def generate(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        assert "Available capability API surface" in prompt
        assert kwargs["response_format"] == "json"
        assert kwargs["options"]["num_ctx"] >= 8192
        assert kwargs["options"]["num_predict"] >= 384
        raise ValueError("truncated JSON from capability planner")


class _PromptBudgetOllama:
    async def generate(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        assert "Global Context Group" in prompt
        assert "Worldview" in prompt
        assert "Lifeview" in prompt
        assert "Valueview" in prompt
        assert "Task Context Group" in prompt
        assert len(prompt) < 9000
        assert kwargs["response_format"] == "json"
        return {
            "decision": "execute",
            "speech": "Walking forward for one second.",
            "skills": [
                {
                    "skill_id": "soridormi.walk_forward",
                    "args": {"duration_s": 1.0},
                }
            ],
        }


class _BadSocialFallbackOllama:
    async def generate(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        assert "Walk forward for 15 seconds, quickly." in prompt
        assert "soridormi.walk_velocity" in prompt
        assert "soridormi.nod_yes" in prompt
        assert "soridormi.look_at_person" in prompt
        assert "Preserve the user's intended action class" in prompt
        assert "Do not use social acknowledgement, gaze, attention, or idle gestures" in prompt
        assert "deeper task decomposition" in prompt
        assert kwargs["response_format"] == "json"
        return {
            "decision": "execute",
            "speech": "I will nod my head to acknowledge you.",
            "skills": [
                {
                    "skill_id": "soridormi.nod_yes",
                    "args": {"count": 2},
                }
            ],
        }


class _ExactBadSocialFallbackOllama:
    async def generate(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        assert "Walk forward for 15 seconds, quickly." in prompt
        assert "Router-selected exact skill_id: soridormi.walk_forward" in prompt
        assert "soridormi.walk_forward" in prompt
        assert "soridormi.nod_yes" in prompt
        assert "Preserve the user's intended action class" in prompt
        assert kwargs["response_format"] == "json"
        return {
            "decision": "execute",
            "speech": "I will nod my head to acknowledge you.",
            "skills": [
                {
                    "skill_id": "soridormi.nod_yes",
                    "args": {"count": 2},
                }
            ],
        }


class _RejectSocialFallbackReviewer:
    async def generate(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        assert "semantic capability-plan reviewer" in prompt
        assert "Walk forward for 15 seconds, quickly." in prompt
        assert "soridormi.walk_velocity" in prompt
        assert "soridormi.nod_yes" in prompt
        assert "substitute a different behavior class" in prompt
        assert "social acknowledgement, gaze, or attention" in prompt
        assert "Proposed capability plan JSON" in prompt
        assert kwargs["response_format"] == "json"
        return {
            "decision": "clarify",
            "reason": "The proposed nod is a social acknowledgement and does not satisfy walking.",
            "speech": "Please confirm a safe bounded walking plan before I move.",
            "skills": [],
        }


class _AcceptCapabilityReviewer:
    async def generate(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        assert "semantic capability-plan reviewer" in prompt
        assert "Proposed capability plan JSON" in prompt
        assert kwargs["response_format"] == "json"
        return {
            "decision": "accept",
            "reason": "The proposed skill preserves the routed action.",
            "speech": "",
            "skills": [],
        }


class _TimeoutCapabilityReviewer:
    async def generate(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        assert "semantic capability-plan reviewer" in prompt
        assert "Walk forward for 15 seconds, quickly." in prompt
        assert kwargs["response_format"] == "json"
        raise TimeoutError("review timeout")


class _AcceptBadSubstitutionReviewer:
    async def generate(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        assert "Router-selected exact skill_id: soridormi.walk_forward" in prompt
        assert "do not use decision=accept" in prompt
        assert "soridormi.walk_forward" in prompt
        assert "soridormi.nod_yes" in prompt
        assert kwargs["response_format"] == "json"
        return {
            "decision": "accept",
            "reason": "Bad review fixture accepting a substitution.",
            "speech": "",
            "skills": [],
        }


class _FullApiCatalog:
    version = 7

    def __init__(self) -> None:
        self.wrong = CatalogCapability(
            capability_id="soridormi.nod_yes",
            agent_id="soridormi.skill",
            description="Nod the robot head yes.",
            input_schema={"type": "object", "properties": {"count": {"type": "number"}}},
            effects=["physical_motion"],
            requires_confirmation=False,
            available=True,
            route="robot_action",
            invocation_kind="named_skill",
            interaction_executable=True,
        )
        self.target = CatalogCapability(
            capability_id="soridormi.wave_hand",
            agent_id="soridormi.skill",
            description="Wave the robot hand to greet someone.",
            input_schema={
                "type": "object",
                "properties": {"count": {"type": "number", "minimum": 1, "maximum": 3}},
                "required": ["count"],
                "additionalProperties": False,
            },
            effects=["physical_motion"],
            requires_confirmation=False,
            available=True,
            route="robot_action",
            invocation_kind="named_skill",
            interaction_executable=True,
        )

    async def search(self, text: str, **kwargs: Any) -> CapabilitySearchResult:
        return CapabilitySearchResult(
            query=text,
            matched=True,
            suggested_route="robot_action",
            suggested_agents=["capability_agent", "speaker_agent"],
            matches=[CapabilityMatch(**self.wrong.model_dump(mode="python"), score=0.9)],
            catalog_version=self.version,
        )

    def entries(self) -> list[CatalogCapability]:
        return [self.wrong, self.target]


def _catalog() -> CapabilityCatalog:
    return _catalog_with_invoker(_Invoker())


def _catalog_with_invoker(invoker: Any) -> CapabilityCatalog:
    registry = CapabilityRegistry.from_bundles(
        [
            CapabilityBundle(
                source="soridormi-test",
                agents=[
                    AgentManifest(
                        agent_id="soridormi.skill",
                        tags=["soridormi", "skill"],
                        tools=[
                            ToolCapability(
                                name="soridormi.skill.list",
                                agent_id="soridormi.skill",
                                description="List named skills.",
                                effects=["read_only"],
                                safety_class="safe_read",
                            )
                        ],
                    )
                ],
            )
        ]
    )
    return CapabilityCatalog(registry, live_invoker=invoker, min_score=0.10)


class CapabilityAwareInteractionTests(unittest.IsolatedAsyncioTestCase):
    async def test_normal_interaction_does_not_self_correct_chat_route_using_catalog(self) -> None:
        runtime = InteractionRuntime(
            AgentServices(
                ollama=None,
                use_llm=False,
                max_speak_chars=160,
                capability_catalog=_catalog(),
                capability_match_limit=8,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "catalog-route",
                "text": "Move forward slowly for one second.",
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

        response = await runtime.run(request)

        self.assertEqual(request.route_decision.source, "fallback")
        self.assertEqual(request.route_decision.route, "chat")
        self.assertEqual(response.skills, [])
        self.assertIn("conversation_agent", response.metadata["handled_by"])
        self.assertNotIn("capability_agent", response.metadata["handled_by"])

    async def test_capability_plan_normalizes_schema_enum_adverbs(self) -> None:
        runtime = InteractionRuntime(
            AgentServices(
                ollama=_AdverbSpeedOllama(),  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=160,
                capability_catalog=_catalog(),
                capability_match_limit=8,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "catalog-speed",
                "text": "Walk forward for 1 second quickly.",
                "route_decision": {
                    "route": "robot_action",
                    "agents": ["capability_agent", "safety_agent", "speaker_agent"],
                    "intent": "robot_action",
                    "confidence": 0.72,
                    "language": "en-US",
                    "source": "llm",
                },
            }
        )

        response = await runtime.run(request)

        self.assertEqual(response.skills[0].skill_id, "soridormi.walk_forward")
        self.assertEqual(response.skills[0].args["speed"], "quick")
        self.assertTrue(response.skills[0].metadata["schema_normalized_args"])

    async def test_capability_plan_dedupes_identical_llm_skill_requests(self) -> None:
        runtime = InteractionRuntime(
            AgentServices(
                ollama=_DuplicateWalkOllama(),  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=160,
                capability_catalog=_catalog(),
                capability_match_limit=8,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "duplicate-walk",
                "text": "Okay, please walk ahead for a few seconds. Please. Quickly.",
                "route_decision": {
                    "route": "robot_action",
                    "agents": ["capability_agent", "safety_agent", "speaker_agent"],
                    "intent": "robot_action",
                    "confidence": 0.95,
                    "language": "en-US",
                    "source": "llm",
                },
            }
        )

        response = await runtime.run(request)

        self.assertEqual(len(response.skills), 1)
        self.assertEqual(response.skills[0].skill_id, "soridormi.walk_forward")
        self.assertEqual(response.skills[0].args, {"duration_s": 1.0, "speed": "quick"})
        self.assertEqual(response.metadata["capability_selected"], ["soridormi.walk_forward"])
        self.assertEqual(response.speech[0].text, "Walking forward.")

    async def test_router_selected_capability_prompt_requires_exact_skill(self) -> None:
        runtime = InteractionRuntime(
            AgentServices(
                ollama=_SelectedWalkOllama(),  # type: ignore[arg-type]
                response_reviewer=_AcceptCapabilityReviewer(),  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=160,
                capability_catalog=_catalog(),
                capability_match_limit=8,
                require_capability_plan_review=True,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "router-selected-omitted-skills",
                "text": "Walk forward quickly for 3 seconds.",
                "route_decision": {
                    "route": "robot_action",
                    "agents": ["capability_agent", "safety_agent", "speaker_agent"],
                    "intent": "capability:soridormi.walk_forward",
                    "confidence": 0.95,
                    "language": "en-US",
                    "source": "llm",
                },
            }
        )

        response = await runtime.run(request)

        self.assertEqual(len(response.skills), 1)
        self.assertEqual(response.skills[0].skill_id, "soridormi.walk_forward")
        self.assertEqual(response.skills[0].args, {"duration_s": 3.0, "speed": "quick"})

    async def test_capability_prompt_uses_extracted_memory_not_raw_history(self) -> None:
        ollama = _ExtractedMemoryCapabilityOllama()
        runtime = InteractionRuntime(
            AgentServices(
                ollama=ollama,  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=160,
                capability_catalog=_catalog(),
                capability_match_limit=8,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "capability-memory-context",
                "text": "Continue with that walking plan.",
                "history": [
                    {
                        "role": "user",
                        "text": "RAW_HISTORY_SHOULD_NOT_REACH_CAPABILITY_PROMPT",
                    }
                ],
                "context": {
                    "history": [
                        {
                            "role": "assistant",
                            "text": "RAW_CONTEXT_HISTORY_SHOULD_NOT_REACH_CAPABILITY_PROMPT",
                        }
                    ],
                    "session_memory": {
                        "kind": "short_term_session_memory",
                        "conversation_id": "session",
                        "recent_user_request": "RAW_RECENT_USER_SHOULD_NOT_REACH_CAPABILITY_PROMPT",
                        "memory_summary": "- Current task: walk forward using extracted memory",
                        "extracted_memory": [
                            {
                                "scope": "task",
                                "kind": "goal",
                                "text": "Current task: walk forward using extracted memory",
                                "confidence": 0.9,
                            }
                        ],
                    },
                },
                "route_decision": {
                    "route": "robot_action",
                    "agents": ["capability_agent", "speaker_agent"],
                    "intent": "capability:soridormi.walk_forward",
                    "confidence": 0.95,
                    "language": "en-US",
                    "source": "llm",
                },
            }
        )

        response = await runtime.run(request)

        self.assertEqual(response.skills[0].skill_id, "soridormi.walk_forward")
        self.assertEqual(len(ollama.prompts), 1)
        self.assertEqual(
            response.skills[0].metadata["source"],
            "capability_catalog",
        )
        self.assertEqual(response.metadata["capability_selected"], ["soridormi.walk_forward"])
        self.assertEqual(response.speech[0].text, "Walking forward.")

    async def test_router_task_list_fast_path_executes_low_risk_blink_without_llm(self) -> None:
        runtime = InteractionRuntime(
            AgentServices(
                ollama=_FailIfCalledOllama(),  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=160,
                capability_catalog=_catalog_with_invoker(_BlinkLimitInvoker()),
                capability_match_limit=8,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "router-fast-blink",
                "text": "Please blink your eyes 5 times.",
                "route_decision": {
                    "route": "robot_action",
                    "agents": ["capability_agent", "safety_agent", "speaker_agent"],
                    "intent": "capability:soridormi.blink_eyes",
                    "confidence": 0.62,
                    "language": "en-US",
                    "source": "llm",
                    "metadata": {
                        "task_list": [
                            {
                                "id": "quick_intent:0:task.execute_skill",
                                "source_stage": "quick_intent",
                                "kind": "action",
                                "task_type": "task.execute_skill",
                                "route": "robot_action",
                                "intent": "capability:soridormi.blink_eyes",
                                "priority": "normal",
                                "status": "proposed",
                                "requires_validation": True,
                                "capability_id": "soridormi.blink_eyes",
                            }
                        ]
                    },
                },
            }
        )

        response = await runtime.run(request)

        self.assertEqual([item.skill_id for item in response.skills], ["soridormi.blink_eyes"])
        self.assertEqual(response.skills[0].args, {"count": 5})
        self.assertEqual(
            response.skills[0].metadata["source"],
            "router_task_list_fast_path",
        )
        self.assertEqual(response.metadata["capability_decision"], "execute")
        self.assertEqual(response.metadata["capability_selected"], ["soridormi.blink_eyes"])
        self.assertEqual(
            response.metadata["capability_fast_path"]["source"],
            "router_task_list_fast_path",
        )
        self.assertEqual(response.speech[0].text, "Okay, I'll blink my eyes 5 times.")

    async def test_router_task_list_fast_path_extracts_chinese_blink_count(self) -> None:
        runtime = InteractionRuntime(
            AgentServices(
                ollama=_FailIfCalledOllama(),  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=160,
                capability_catalog=_catalog_with_invoker(_BlinkLimitInvoker()),
                capability_match_limit=8,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "router-fast-chinese-blink",
                "text": "请眨两小眼睛。",
                "route_decision": {
                    "route": "robot_action",
                    "agents": ["capability_agent", "safety_agent", "speaker_agent"],
                    "intent": "capability:soridormi.blink_eyes",
                    "confidence": 0.87,
                    "language": "zh-CN",
                    "source": "catalog",
                    "metadata": {
                        "task_list": [
                            {
                                "id": "quick_intent:0:task.execute_skill",
                                "source_stage": "quick_intent",
                                "kind": "action",
                                "task_type": "task.execute_skill",
                                "route": "robot_action",
                                "intent": "capability:soridormi.blink_eyes",
                                "priority": "normal",
                                "status": "proposed",
                                "requires_validation": True,
                                "capability_id": "soridormi.blink_eyes",
                            }
                        ]
                    },
                },
            }
        )

        response = await runtime.run(request)

        self.assertEqual([item.skill_id for item in response.skills], ["soridormi.blink_eyes"])
        self.assertEqual(response.skills[0].args, {"count": 2})
        self.assertEqual(
            response.metadata["capability_fast_path"]["source"],
            "router_task_list_fast_path",
        )
        self.assertEqual(response.speech[0].text, "好的，我会眨眼2次。")

    async def test_router_task_list_fast_path_allows_optional_defaulted_blink_fields(self) -> None:
        runtime = InteractionRuntime(
            AgentServices(
                ollama=_FailIfCalledOllama(),  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=160,
                capability_catalog=_catalog_with_invoker(_BlinkDefaultInvoker()),
                capability_match_limit=8,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "router-fast-blink-default-fields",
                "text": "Please blink your eyes 5 times.",
                "route_decision": {
                    "route": "robot_action",
                    "agents": ["capability_agent", "safety_agent", "speaker_agent"],
                    "intent": "capability:soridormi.blink_eyes",
                    "confidence": 0.62,
                    "language": "en-US",
                    "source": "llm",
                    "metadata": {
                        "task_list": [
                            {
                                "id": "quick_intent:0:task.execute_skill",
                                "source_stage": "quick_intent",
                                "kind": "action",
                                "task_type": "task.execute_skill",
                                "route": "robot_action",
                                "intent": "capability:soridormi.blink_eyes",
                                "priority": "normal",
                                "status": "proposed",
                                "requires_validation": True,
                                "capability_id": "soridormi.blink_eyes",
                            }
                        ]
                    },
                },
            }
        )

        response = await runtime.run(request)

        self.assertEqual([item.skill_id for item in response.skills], ["soridormi.blink_eyes"])
        self.assertEqual(response.skills[0].args, {"count": 5})
        self.assertEqual(
            response.skills[0].metadata["source"],
            "router_task_list_fast_path",
        )
        self.assertEqual(
            response.metadata["capability_fast_path"]["source"],
            "router_task_list_fast_path",
        )

    async def test_router_task_list_fast_path_batches_over_limit_blink_without_llm(self) -> None:
        runtime = InteractionRuntime(
            AgentServices(
                ollama=_FailIfCalledOllama(),  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=160,
                capability_catalog=_catalog_with_invoker(_BlinkLimitInvoker()),
                capability_match_limit=8,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "router-fast-blink-over-limit",
                "text": "Please blink your eyes 15 times.",
                "route_decision": {
                    "route": "robot_action",
                    "agents": ["capability_agent", "safety_agent", "speaker_agent"],
                    "intent": "capability:soridormi.blink_eyes",
                    "confidence": 0.62,
                    "language": "en-US",
                    "source": "llm",
                    "metadata": {
                        "task_list": [
                            {
                                "id": "quick_intent:0:task.execute_skill",
                                "source_stage": "quick_intent",
                                "kind": "action",
                                "task_type": "task.execute_skill",
                                "route": "robot_action",
                                "intent": "capability:soridormi.blink_eyes",
                                "priority": "normal",
                                "status": "proposed",
                                "requires_validation": True,
                                "capability_id": "soridormi.blink_eyes",
                            }
                        ]
                    },
                },
            }
        )

        response = await runtime.run(request)

        self.assertEqual(
            [item.skill_id for item in response.skills],
            [
                "soridormi.blink_eyes",
                "soridormi.blink_eyes",
                "soridormi.blink_eyes",
            ],
        )
        self.assertEqual(
            [item.args for item in response.skills],
            [{"count": 6}, {"count": 6}, {"count": 3}],
        )
        self.assertEqual(
            response.metadata["capability_fast_path"]["source"],
            "exact_routed_count_batch_recovery",
        )
        self.assertEqual(
            response.metadata["capability_batched_over_limit"]["source"],
            "exact_routed_count_batch_recovery",
        )
        self.assertIn("15", response.speech[0].text)

    async def test_router_task_list_does_not_fast_path_confirmed_physical_motion(self) -> None:
        runtime = InteractionRuntime(
            AgentServices(
                ollama=_SelectedWalkOllama(),  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=160,
                capability_catalog=_catalog(),
                capability_match_limit=8,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "router-task-list-walk-no-fast-path",
                "text": "Walk forward quickly for 3 seconds.",
                "route_decision": {
                    "route": "robot_action",
                    "agents": ["capability_agent", "safety_agent", "speaker_agent"],
                    "intent": "capability:soridormi.walk_forward",
                    "confidence": 0.95,
                    "language": "en-US",
                    "source": "llm",
                    "metadata": {
                        "task_list": [
                            {
                                "id": "quick_intent:0:task.execute_skill",
                                "source_stage": "quick_intent",
                                "kind": "action",
                                "task_type": "task.execute_skill",
                                "route": "robot_action",
                                "intent": "capability:soridormi.walk_forward",
                                "priority": "normal",
                                "status": "proposed",
                                "requires_validation": True,
                                "capability_id": "soridormi.walk_forward",
                            }
                        ]
                    },
                },
            }
        )

        response = await runtime.run(request)

        self.assertEqual(response.skills[0].skill_id, "soridormi.walk_forward")
        self.assertEqual(
            response.skills[0].metadata["source"],
            "capability_catalog",
        )
        self.assertNotIn("capability_fast_path", response.metadata)

    async def test_router_selected_capability_does_not_hide_better_candidate(self) -> None:
        runtime = InteractionRuntime(
            AgentServices(
                ollama=_SelectedVelocityBetterForwardOllama(),  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=160,
                capability_catalog=_catalog_with_invoker(_WalkChoiceInvoker()),
                capability_match_limit=8,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "router-selected-velocity-better-forward",
                "text": "Walk forward quickly for 15 seconds.",
                "route_decision": {
                    "route": "robot_action",
                    "agents": ["capability_agent", "safety_agent", "speaker_agent"],
                    "intent": "capability:soridormi.walk_velocity",
                    "confidence": 0.9,
                    "language": "en-US",
                    "source": "llm",
                },
            }
        )

        response = await runtime.run(request)

        self.assertEqual(len(response.skills), 1)
        self.assertEqual(response.skills[0].skill_id, "soridormi.walk_forward")
        self.assertEqual(response.skills[0].args, {"duration_s": 15.0, "speed": "quick"})
        self.assertEqual(response.metadata["capability_selected"], ["soridormi.walk_forward"])
        self.assertEqual(response.speech[0].text, "Walking forward quickly for 15 seconds.")

    async def test_deep_thought_direct_motion_plans_with_catalog_context(self) -> None:
        runtime = InteractionRuntime(
            AgentServices(
                ollama=_RecoveredDeepThoughtWalkOllama(),  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=160,
                capability_catalog=_catalog_with_invoker(_WalkChoiceInvoker()),
                capability_match_limit=8,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "deep-thought-direct-motion",
                "text": "Walk forward for 15 seconds, quickly.",
                "route_decision": {
                    "route": "deep_thought",
                    "agents": ["deepthinking_agent", "speaker_agent"],
                    "intent": "deep_thought_complex_reasoning",
                    "confidence": 0.90,
                    "language": "en-US",
                    "source": "llm",
                },
            }
        )

        response = await runtime.run(request)

        self.assertEqual(len(response.skills), 1)
        self.assertEqual(response.skills[0].skill_id, "soridormi.walk_forward")
        self.assertEqual(
            response.skills[0].args,
            {"duration_s": 15.0, "speed": "quick"},
        )
        self.assertEqual(response.metadata["deepthinking_output_mode"], "skill_tasks")
        self.assertEqual(response.metadata["deepthinking_valid_effect_task_count"], 1)
        self.assertEqual(response.speech[0].text, "Walking forward quickly for 15 seconds.")
        spoken = " ".join(item.text for item in response.speech)
        self.assertNotIn("Task Split", spoken)
        self.assertNotIn("soridormi", spoken)

    async def test_polite_chinese_head_ability_question_executes_matching_skill(self) -> None:
        runtime = InteractionRuntime(
            AgentServices(
                ollama=_PoliteHeadQuestionOllama(),  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=160,
                capability_catalog=_catalog_with_invoker(_HeadGestureInvoker()),
                capability_match_limit=8,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "polite-head-question",
                "text": "你能摇头吗",
                "route_decision": {
                    "route": "robot_action",
                    "agents": ["capability_agent", "safety_agent", "speaker_agent"],
                    "intent": "robot_action",
                    "confidence": 0.72,
                    "language": "zh-CN",
                    "source": "llm",
                },
            }
        )

        response = await runtime.run(request)

        self.assertEqual(response.skills[0].skill_id, "soridormi.shake_no")
        self.assertEqual(response.skills[0].args, {"count": 2})
        self.assertEqual(response.speech[0].text, "我会摇头。")

    async def test_capability_plan_rejects_execute_without_llm_speech(self) -> None:
        runtime = InteractionRuntime(
            AgentServices(
                ollama=_EmptySpeechHeadQuestionOllama(),  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=160,
                capability_catalog=_catalog_with_invoker(_HeadGestureInvoker()),
                capability_match_limit=8,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "empty-speech-head-question",
                "text": "你能摇头吗",
                "route_decision": {
                    "route": "robot_action",
                    "agents": ["capability_agent", "safety_agent", "speaker_agent"],
                    "intent": "robot_action",
                    "confidence": 0.72,
                    "language": "zh-CN",
                    "source": "llm",
                },
            }
        )

        response = await runtime.run(request)

        self.assertEqual(response.skills, [])
        self.assertEqual(response.metadata["capability_decision"], "clarify")
        self.assertNotEqual(response.speech[0].text, "Shaking my head.")

    async def test_capability_plan_blocks_schema_invalid_args_before_runtime(self) -> None:
        runtime = InteractionRuntime(
            AgentServices(
                ollama=_InvalidWalkOllama(),  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=160,
                capability_catalog=_catalog_with_invoker(_StrictWalkInvoker()),
                capability_match_limit=8,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "invalid-walk",
                "text": "Walk forward for five seconds.",
                "route_decision": {
                    "route": "robot_action",
                    "agents": ["capability_agent", "safety_agent", "speaker_agent"],
                    "intent": "robot_action",
                    "confidence": 0.72,
                    "language": "en-US",
                    "source": "llm",
                },
            }
        )

        response = await runtime.run(request)

        self.assertEqual(response.skills, [])
        self.assertEqual(response.speech[0].text, "Please clarify the action before I move.")
        self.assertEqual(response.metadata["capability_decision"], "clarify")
        self.assertEqual(
            response.metadata["invalid_capability_args"]["errors"],
            ["args has unknown fields: ['duration_s']"],
        )

    async def test_exact_blink_request_over_limit_batches_valid_visual_skills(self) -> None:
        runtime = InteractionRuntime(
            AgentServices(
                ollama=_OverLimitBlinkClarifyOllama(),  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=160,
                capability_catalog=_catalog_with_invoker(_BlinkLimitInvoker()),
                capability_match_limit=8,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "blink-over-limit",
                "text": "Brink your eyes for 15 times.",
                "route_decision": {
                    "route": "robot_action",
                    "agents": ["capability_agent", "safety_agent", "speaker_agent"],
                    "intent": "capability:soridormi.blink_eyes",
                    "confidence": 0.56,
                    "language": "en-US",
                    "source": "llm",
                },
            }
        )

        response = await runtime.run(request)

        self.assertEqual(
            [item.skill_id for item in response.skills],
            [
                "soridormi.blink_eyes",
                "soridormi.blink_eyes",
                "soridormi.blink_eyes",
            ],
        )
        self.assertEqual(
            [item.args for item in response.skills],
            [{"count": 6}, {"count": 6}, {"count": 3}],
        )
        self.assertFalse(response.requires_confirmation)
        self.assertIn("blink", response.speech[0].text.lower())
        self.assertIn("15", response.speech[0].text)
        self.assertEqual(response.metadata["capability_decision"], "execute")
        self.assertEqual(
            response.metadata["capability_batched_over_limit"],
            {
                "skill_id": "soridormi.blink_eyes",
                "requested_count": 15,
                "max_per_call": 6,
                "batch_count": 3,
                "batches": [6, 6, 3],
                "source": "exact_routed_count_batch_recovery",
            },
        )

    async def test_exact_blink_request_over_limit_batches_silently_clamped_plan(self) -> None:
        runtime = InteractionRuntime(
            AgentServices(
                ollama=_OverLimitBlinkClampedExecuteOllama(),  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=160,
                capability_catalog=_catalog_with_invoker(_BlinkLimitInvoker()),
                capability_match_limit=8,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "blink-over-limit-clamped",
                "text": "Brink your eyes for 15 times.",
                "route_decision": {
                    "route": "robot_action",
                    "agents": ["capability_agent", "safety_agent", "speaker_agent"],
                    "intent": "capability:soridormi.blink_eyes",
                    "confidence": 0.56,
                    "language": "en-US",
                    "source": "llm",
                },
            }
        )

        response = await runtime.run(request)

        self.assertEqual(
            [item.skill_id for item in response.skills],
            [
                "soridormi.blink_eyes",
                "soridormi.blink_eyes",
                "soridormi.blink_eyes",
            ],
        )
        self.assertEqual(
            [item.args for item in response.skills],
            [{"count": 6}, {"count": 6}, {"count": 3}],
        )
        self.assertEqual(response.metadata["capability_decision"], "execute")
        self.assertEqual(
            response.metadata["capability_batched_over_limit"]["source"],
            "exact_routed_count_batch_recovery",
        )

    async def test_capability_planner_failure_returns_clarification_not_exception(self) -> None:
        runtime = InteractionRuntime(
            AgentServices(
                ollama=_BrokenCapabilityPlannerOllama(),  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=160,
                capability_catalog=_catalog(),
                capability_match_limit=8,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "planner-json-failure",
                "text": "Walk forward for 1 second.",
                "route_decision": {
                    "route": "robot_action",
                    "agents": ["capability_agent", "safety_agent", "speaker_agent"],
                    "intent": "robot_action",
                    "confidence": 0.72,
                    "language": "en-US",
                    "source": "llm",
                },
            }
        )

        response = await runtime.run(request)

        self.assertEqual(response.skills, [])
        self.assertEqual(
            response.speech[0].text,
            "I heard the movement request, but I could not produce a valid motion command, so I will not move.",
        )
        self.assertEqual(response.metadata["capability_decision"], "clarify")

    async def test_capability_planner_keeps_large_mind_context_bounded(self) -> None:
        runtime = InteractionRuntime(
            AgentServices(
                ollama=_PromptBudgetOllama(),  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=160,
                capability_catalog=_catalog(),
                capability_match_limit=8,
            )
        )
        large_mind = {
            "profile_id": "chromie_default_mind",
            "version": "0.1.2",
            "owner_approved": True,
            "identity": {
                "name": "Chromie",
                "description": " ".join(["embodied realtime robot"] * 80),
            },
            "long_term_goals": [" ".join(["be useful"] * 120)],
            "core_principles": [" ".join(["be safe and honest"] * 160)],
            "prompt_summary": " ".join(["owner-approved robot mind summary"] * 100),
        }
        request = AgentRunRequest.model_validate(
            {
                "sid": "large-mind-planner",
                "text": "Walk forward for one second.",
                "route_decision": {
                    "route": "robot_action",
                    "agents": ["capability_agent", "safety_agent", "speaker_agent"],
                    "intent": "robot_action",
                    "confidence": 0.72,
                    "language": "en-US",
                    "source": "llm",
                },
                "context": {
                    "mind": large_mind,
                    "history": [
                        {"role": "user", "text": "Hello, how are you."},
                        {"role": "assistant", "text": "Hello."},
                    ],
                },
            }
        )

        response = await runtime.run(request)

        self.assertEqual(response.skills[0].skill_id, "soridormi.walk_forward")
        self.assertEqual(response.speech[0].text, "Walking forward for one second.")

    async def test_capability_plan_reviewer_blocks_social_fallback_for_walking_request(self) -> None:
        runtime = InteractionRuntime(
            AgentServices(
                ollama=_BadSocialFallbackOllama(),  # type: ignore[arg-type]
                response_reviewer=_RejectSocialFallbackReviewer(),  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=160,
                capability_catalog=_catalog_with_invoker(_WalkAndSocialInvoker()),
                capability_match_limit=8,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "walk-not-nod",
                "text": "Walk forward for 15 seconds, quickly.",
                "route_decision": {
                    "route": "robot_action",
                    "agents": ["capability_agent", "safety_agent", "speaker_agent"],
                    "intent": "robot_action",
                    "confidence": 0.72,
                    "language": "en-US",
                    "source": "llm",
                    "metadata": {"thinking_mode": "fast", "task_relation": "new_task"},
                },
                "context": {
                    "current_task_context": {
                        "task_type": "robot_action",
                        "goal": "walk forward only after a safe bounded plan is confirmed",
                    },
                    "recent_action_history": [
                        {
                            "user_request": "Walk forward for 15 seconds, quickly.",
                            "outcome": "planner_misselected_social_gesture",
                        }
                    ],
                },
            }
        )

        response = await runtime.run(request)

        self.assertEqual(response.skills, [])
        self.assertEqual(response.metadata["capability_decision"], "clarify")
        self.assertEqual(
            response.speech[0].text,
            "Please confirm a safe bounded walking plan before I move.",
        )

    async def test_required_robot_action_review_timeout_blocks_social_fallback(self) -> None:
        runtime = InteractionRuntime(
            AgentServices(
                ollama=_BadSocialFallbackOllama(),  # type: ignore[arg-type]
                response_reviewer=_TimeoutCapabilityReviewer(),  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=160,
                capability_catalog=_catalog_with_invoker(_WalkAndSocialInvoker()),
                capability_match_limit=8,
                require_capability_plan_review=True,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "generic-walk-not-nod-timeout",
                "text": "Walk forward for 15 seconds, quickly.",
                "route_decision": {
                    "route": "robot_action",
                    "agents": ["capability_agent", "conversation_agent", "safety_agent", "speaker_agent"],
                    "intent": "robot_action",
                    "confidence": 0.50,
                    "language": "en-US",
                    "source": "catalog",
                },
            }
        )

        response = await runtime.run(request)

        self.assertEqual(response.skills, [])
        self.assertEqual(response.metadata["capability_decision"], "clarify")
        self.assertEqual(
            response.speech[0].text,
            "That motion plan did not get a reliable review result, so I will not move.",
        )

    async def test_exact_router_intent_substitution_fails_closed_without_reviewer(self) -> None:
        runtime = InteractionRuntime(
            AgentServices(
                ollama=_ExactBadSocialFallbackOllama(),  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=160,
                capability_catalog=_catalog_with_invoker(_ForwardAndSocialInvoker()),
                capability_match_limit=8,
                require_capability_plan_review=True,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "exact-walk-not-nod-no-reviewer",
                "text": "Walk forward for 15 seconds, quickly.",
                "route_decision": {
                    "route": "robot_action",
                    "agents": ["capability_agent", "safety_agent", "speaker_agent"],
                    "intent": "capability:soridormi.walk_forward",
                    "confidence": 0.86,
                    "language": "en-US",
                    "source": "llm",
                },
            }
        )

        response = await runtime.run(request)

        self.assertEqual(response.skills, [])
        self.assertEqual(response.metadata["capability_decision"], "clarify")
        self.assertEqual(
            response.speech[0].text,
            "That motion plan did not get a reliable review result, so I will not move.",
        )

    async def test_exact_router_intent_substitution_reviewer_accept_is_not_enough(self) -> None:
        runtime = InteractionRuntime(
            AgentServices(
                ollama=_ExactBadSocialFallbackOllama(),  # type: ignore[arg-type]
                response_reviewer=_AcceptBadSubstitutionReviewer(),  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=160,
                capability_catalog=_catalog_with_invoker(_ForwardAndSocialInvoker()),
                capability_match_limit=8,
                require_capability_plan_review=True,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "exact-walk-not-nod-bad-reviewer",
                "text": "Walk forward for 15 seconds, quickly.",
                "route_decision": {
                    "route": "robot_action",
                    "agents": ["capability_agent", "safety_agent", "speaker_agent"],
                    "intent": "capability:soridormi.walk_forward",
                    "confidence": 0.86,
                    "language": "en-US",
                    "source": "llm",
                },
            }
        )

        response = await runtime.run(request)

        self.assertEqual(response.skills, [])
        self.assertEqual(response.metadata["capability_decision"], "clarify")
        self.assertEqual(
            response.speech[0].text,
            "That motion plan did not get a reliable review result, so I will not move.",
        )

    async def test_capability_plan_uses_task_context_for_look_forward_followup(self) -> None:
        runtime = InteractionRuntime(
            AgentServices(
                ollama=_LookForwardOllama(),  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=160,
                capability_catalog=_catalog_with_invoker(_LookForwardInvoker()),
                capability_match_limit=8,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "look-followup",
                "text": "5 seconds and blink your eyes.",
                "route_decision": {
                    "route": "robot_action",
                    "agents": ["capability_agent", "safety_agent", "speaker_agent"],
                    "intent": "robot_action",
                    "confidence": 0.55,
                    "language": "en-US",
                    "source": "llm",
                },
                "context": {
                    "current_task_context": {
                        "task_id": "task-look",
                        "task_relation": "continue_task",
                        "task_type": "robot_action",
                        "goal": "Can you look forward for some time?",
                        "last_meaningful_user_turn": "Can you look forward for some time?",
                        "last_assistant_response": "Look forward for how long?",
                    }
                },
                "history": [
                    {"role": "user", "text": "Can you look forward for some time?"},
                    {"role": "assistant", "text": "Look forward for how long?"},
                ],
            }
        )

        response = await runtime.run(request)

        self.assertEqual(
            [item.skill_id for item in response.skills],
            ["soridormi.look_at_person", "soridormi.blink_eyes"],
        )
        self.assertEqual(response.skills[0].args, {"duration_s": 5.0})
        self.assertEqual(response.skills[1].args, {"count": 2})
        self.assertEqual(response.speech[0].text, "Looking forward and blinking.")

    async def test_capability_plan_sees_full_api_surface_beyond_search_match(self) -> None:
        runtime = InteractionRuntime(
            AgentServices(
                ollama=_FullApiOllama(),  # type: ignore[arg-type]
                use_llm=True,
                max_speak_chars=160,
                capability_catalog=_FullApiCatalog(),  # type: ignore[arg-type]
                capability_match_limit=1,
            )
        )
        request = AgentRunRequest.model_validate(
            {
                "sid": "full-api-surface",
                "text": "Wave twice.",
                "route_decision": {
                    "route": "robot_action",
                    "agents": ["capability_agent", "safety_agent", "speaker_agent"],
                    "intent": "robot_action",
                    "confidence": 0.72,
                    "language": "en-US",
                    "source": "llm",
                },
            }
        )

        response = await runtime.run(request)

        self.assertEqual([item.skill_id for item in response.skills], ["soridormi.wave_hand"])
        self.assertEqual(response.skills[0].args, {"count": 2})
        self.assertEqual(response.metadata["capability_catalog_version"], 7)


if __name__ == "__main__":
    unittest.main()
