from __future__ import annotations

import unittest
from typing import Any

from agent.app.agents import AgentServices
from agent.app.interaction import (
    InteractionOutputCoordinator,
    NativeInteractionOutputError,
)
from agent.app.runtime import AgentRuntime, InteractionRuntime
from agent.app.schema import AgentResult, AgentRunRequest
from agent.app.task_graph.models import TaskGraph, TaskNode


class _FakePlanner:
    async def plan(self, **_: Any) -> TaskGraph:
        return TaskGraph(
            graph_id="graph_native",
            user_request="weather",
            created_by="llm",
            nodes=[
                TaskNode(
                    id="report",
                    tool="chromie.report",
                    type="report",
                    args={"message": "sunny"},
                )
            ],
        )


class _NativeRuntimeStub:
    def __init__(self, response: Any) -> None:
        self.response = response
        self.calls = 0

    async def run(self, request: AgentRunRequest) -> Any:
        self.calls += 1
        return self.response


class _LegacyRuntimeStub:
    def __init__(self, result: AgentResult | None = None) -> None:
        self.result = result or AgentResult()
        self.calls = 0

    async def run(self, request: AgentRunRequest) -> AgentResult:
        self.calls += 1
        return self.result


def _request(
    *,
    text: str = "nod",
    route: str = "robot_action",
    intent: str = "nod",
    agents: list[str] | None = None,
) -> AgentRunRequest:
    return AgentRunRequest.model_validate(
        {
            "sid": "native-interaction",
            "text": text,
            "route_decision": {
                "route": route,
                "agents": agents or [],
                "intent": intent,
                "confidence": 1.0,
                "language": "en-US",
                "source": "rules",
            },
        }
    )


class NativeInteractionRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_runtime_emits_named_skill_without_result_adapter(self) -> None:
        response = await InteractionRuntime(
            AgentServices(ollama=None, use_llm=False, max_speak_chars=160)
        ).run(_request())

        self.assertEqual(response.metadata["interaction_output_mode"], "native")
        self.assertEqual(response.skills[0].skill_id, "soridormi.nod_yes")
        self.assertEqual(response.skills[0].args, {"count": 2})
        self.assertEqual(response.speech[0].text, "Okay.")
        self.assertIn("robot_pose_controller_agent", response.metadata["handled_by"])

    async def test_legacy_run_contract_remains_unchanged(self) -> None:
        result = await AgentRuntime(
            AgentServices(ollama=None, use_llm=False, max_speak_chars=160)
        ).run(_request())

        self.assertEqual(result.actions[0].type, "head.nod")
        self.assertEqual(result.actions[0].params, {"times": 1})
        self.assertEqual(result.speak_immediate[0].text, "Okay.")

    async def test_native_task_graph_is_emitted_as_structured_skill(self) -> None:
        response = await InteractionRuntime(
            AgentServices(
                ollama=None,
                use_llm=True,
                max_speak_chars=160,
                task_graph_planner=_FakePlanner(),  # type: ignore[arg-type]
            )
        ).run(
            _request(
                text="check the weather",
                route="tool",
                intent="weather_query",
                agents=["tool_agent", "speaker_agent"],
            )
        )

        self.assertEqual(len(response.skills), 1)
        self.assertEqual(response.skills[0].skill_id, "chromie.task_graph.execute")
        self.assertEqual(
            response.skills[0].args["graph"]["graph_id"],
            "graph_native",
        )

    async def test_native_validation_failure_is_fail_closed_by_default(self) -> None:
        native = _NativeRuntimeStub(
            {
                "status": "ok",
                "skills": [
                    {
                        "skill_id": "unsafe.test",
                        "args": {"joint_targets": [0.1, 0.2]},
                    }
                ],
            }
        )
        legacy = _LegacyRuntimeStub()
        coordinator = InteractionOutputCoordinator(native, legacy)

        with self.assertRaises(NativeInteractionOutputError):
            await coordinator.run(_request())

        self.assertEqual(native.calls, 1)
        self.assertEqual(legacy.calls, 0)

    async def test_explicit_fallback_uses_legacy_adapter_after_validation_error(self) -> None:
        native = _NativeRuntimeStub(
            {
                "status": "ok",
                "skills": [
                    {
                        "skill_id": "unsafe.test",
                        "args": {"joint_targets": [0.1, 0.2]},
                    }
                ],
            }
        )
        legacy_result = AgentResult()
        legacy_result.add_speak_immediate("Fallback response.")
        legacy_result.add_action(
            "robot_pose_controller",
            "head.nod",
            params={"times": 1},
        )
        legacy = _LegacyRuntimeStub(legacy_result)
        coordinator = InteractionOutputCoordinator(
            native,
            legacy,
            fallback_to_legacy=True,
        )

        response = await coordinator.run(_request())

        self.assertEqual(response.metadata["interaction_output_mode"], "legacy-fallback")
        self.assertIn("native_validation_error", response.metadata)
        self.assertNotIn("[0.1,0.2]", response.model_dump_json())
        self.assertEqual(response.skills[0].skill_id, "soridormi.nod_yes")
        self.assertEqual(legacy.calls, 1)

    async def test_legacy_adapter_mode_skips_native_runtime(self) -> None:
        native = _NativeRuntimeStub({"status": "ok"})
        legacy_result = AgentResult()
        legacy_result.add_speak_immediate("Compatibility response.")
        legacy = _LegacyRuntimeStub(legacy_result)
        coordinator = InteractionOutputCoordinator(
            native,
            legacy,
            mode="legacy-adapter",
        )

        response = await coordinator.run(_request())

        self.assertEqual(response.metadata["interaction_output_mode"], "legacy-adapter")
        self.assertEqual(response.speech[0].text, "Compatibility response.")
        self.assertEqual(native.calls, 0)
        self.assertEqual(legacy.calls, 1)


if __name__ == "__main__":
    unittest.main()
