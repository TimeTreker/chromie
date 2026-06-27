from __future__ import annotations

import asyncio
import unittest
from typing import Any

from agent.app.tool_invocation import ToolCallOutcome, ToolInvocationContext
from orchestrator.runtime.interaction_coordinator import (
    InteractionRuntimeCoordinator,
)
from shared.chromie_contracts.interaction import InteractionResponse


class _SoridormiInvoker:
    def __init__(
        self,
        *,
        execute_outcome: ToolCallOutcome | None = None,
        monitor_outcome: ToolCallOutcome | None = None,
        execute_delay_s: float = 0,
    ) -> None:
        self.calls: list[tuple[str, dict[str, Any], ToolInvocationContext | None]] = []
        self.execute_outcome = execute_outcome
        self.monitor_outcome = monitor_outcome
        self.execute_delay_s = execute_delay_s

    async def invoke(
        self,
        tool_name: str,
        args: dict[str, Any],
        *,
        context: ToolInvocationContext | None = None,
    ) -> ToolCallOutcome:
        self.calls.append((tool_name, args, context))
        if tool_name == "soridormi.skill.list":
            return ToolCallOutcome.success(
                {
                    "mode": "sim",
                    "skills": [
                        {
                            "skill_id": "nod_yes",
                            "available": True,
                            "parameters_schema": {
                                "type": "object",
                                "properties": {
                                    "count": {
                                        "type": "integer",
                                        "minimum": 1,
                                        "maximum": 3,
                                    }
                                },
                                "additionalProperties": False,
                            },
                            "interruptible": True,
                        }
                    ],
                }
            )
        if tool_name == "soridormi.skill.create_plan":
            return ToolCallOutcome.success({"plan_id": "plan-1"})
        if tool_name == "soridormi.safety.monitor_motion":
            if self.monitor_outcome is not None:
                return self.monitor_outcome
            return ToolCallOutcome.success({"ok": True, "event": None})
        if tool_name == "soridormi.skill.execute_plan":
            if self.execute_delay_s:
                await asyncio.sleep(self.execute_delay_s)
            if self.execute_outcome is not None:
                return self.execute_outcome
            return ToolCallOutcome.success(
                {"completed": True, "skill_id": "nod_yes"}
            )
        if tool_name == "soridormi.motion.cancel":
            return ToolCallOutcome.success({"cancelled": True})
        return ToolCallOutcome.failed(f"unexpected tool {tool_name}")


class InteractionRuntimeCoordinatorTests(unittest.IsolatedAsyncioTestCase):
    async def test_speech_only_does_not_require_soridormi(self) -> None:
        scheduled: list[dict[str, Any]] = []
        coordinator = InteractionRuntimeCoordinator(
            lambda args: scheduled.append(args) or {"scheduled": True}
        )

        result = await coordinator.execute(
            InteractionResponse(speech=[{"text": "Hello."}]),
            session_id="sid-1",
        )

        self.assertEqual(result.status, "completed")
        self.assertEqual(scheduled[0]["text"], "Hello.")
        self.assertEqual(scheduled[0]["metadata"]["session_id"], "sid-1")

    async def test_session_interrupt_completes_as_local_control(self) -> None:
        scheduled: list[dict[str, Any]] = []
        coordinator = InteractionRuntimeCoordinator(
            lambda args: scheduled.append(args) or {"scheduled": True}
        )

        result = await coordinator.execute(
            InteractionResponse(
                skills=[
                    {
                        "request_id": "interrupt-1",
                        "skill_id": "session.interrupt",
                    }
                ]
            ),
            session_id="sid-1",
        )

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.results[0].skill_id, "session.interrupt")
        self.assertEqual(result.results[0].provider_id, "chromie.session_control")
        self.assertEqual(
            result.results[0].output,
            {"control": "interrupt_acknowledged"},
        )
        self.assertEqual(scheduled, [])

    async def test_sim_body_skill_discovers_catalog_and_executes(self) -> None:
        invoker = _SoridormiInvoker()
        coordinator = InteractionRuntimeCoordinator(
            lambda args: {"scheduled": True},
            soridormi_invoker=invoker,
        )

        result = await coordinator.execute(
            InteractionResponse(
                skills=[
                    {
                        "request_id": "nod-1",
                        "skill_id": "soridormi.nod_yes",
                        "args": {"count": 2},
                    }
                ]
            ),
            session_id="sid-1",
        )

        self.assertEqual(result.status, "completed")
        self.assertEqual(
            [call[0] for call in invoker.calls],
            [
                "soridormi.skill.list",
                "soridormi.skill.create_plan",
                "soridormi.safety.monitor_motion",
                "soridormi.skill.execute_plan",
            ],
        )
        self.assertTrue(invoker.calls[-1][2].confirmed)

    async def test_body_skill_fails_closed_when_provider_is_disabled(self) -> None:
        coordinator = InteractionRuntimeCoordinator(
            lambda args: {"scheduled": True}
        )

        with self.assertRaisesRegex(RuntimeError, "disabled"):
            await coordinator.execute(
                InteractionResponse(
                    skills=[{"skill_id": "soridormi.nod_yes"}]
                ),
                session_id="sid-1",
            )

    async def test_optional_body_cue_disabled_provider_stays_silent(self) -> None:
        spoken: list[str] = []
        coordinator = InteractionRuntimeCoordinator(
            lambda args: spoken.append(str(args["text"])) or {"scheduled": True}
        )

        result = await coordinator.execute(
            InteractionResponse(
                skills=[{"skill_id": "soridormi.express_attention"}],
                metadata={"optional_body_cue": True},
            ),
            session_id="sid-optional-disabled",
        )

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.results[0].reason_code, "provider_disabled")
        self.assertEqual(spoken, [])

    async def test_catalog_failure_becomes_terminal_safe_fallback(self) -> None:
        class CatalogFailureInvoker(_SoridormiInvoker):
            async def invoke(self, tool_name, args, *, context=None):  # type: ignore[no-untyped-def]
                self.calls.append((tool_name, args, context))
                if tool_name == "soridormi.skill.list":
                    return ToolCallOutcome.failed(
                        "provider restarting",
                        retryable=True,
                    )
                return ToolCallOutcome.failed(f"unexpected tool {tool_name}")

        spoken: list[str] = []
        coordinator = InteractionRuntimeCoordinator(
            lambda args: spoken.append(str(args["text"])) or {"scheduled": True},
            soridormi_invoker=CatalogFailureInvoker(),
        )

        result = await coordinator.execute(
            InteractionResponse(
                skills=[
                    {
                        "request_id": "nod-1",
                        "skill_id": "soridormi.nod_yes",
                    }
                ]
            ),
            session_id="sid-1",
        )

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.results[0].reason_code, "catalog_unavailable")
        self.assertEqual(
            spoken,
            ["I could not complete that movement safely."],
        )

    async def test_optional_body_cue_catalog_failure_stays_silent(self) -> None:
        class CatalogFailureInvoker(_SoridormiInvoker):
            async def invoke(self, tool_name, args, *, context=None):  # type: ignore[no-untyped-def]
                self.calls.append((tool_name, args, context))
                if tool_name == "soridormi.skill.list":
                    return ToolCallOutcome.failed(
                        "provider restarting",
                        retryable=True,
                    )
                return ToolCallOutcome.failed(f"unexpected tool {tool_name}")

        spoken: list[str] = []
        coordinator = InteractionRuntimeCoordinator(
            lambda args: spoken.append(str(args["text"])) or {"scheduled": True},
            soridormi_invoker=CatalogFailureInvoker(),
        )

        result = await coordinator.execute(
            InteractionResponse(
                skills=[
                    {
                        "request_id": "attention-1",
                        "skill_id": "soridormi.express_attention",
                    }
                ],
                metadata={"optional_body_cue": True},
            ),
            session_id="sid-1",
        )

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.results[0].reason_code, "catalog_unavailable")
        self.assertEqual(spoken, [])

    async def test_optional_body_cue_confirmation_requirement_stays_silent(self) -> None:
        class AttentionInvoker(_SoridormiInvoker):
            async def invoke(self, tool_name, args, *, context=None):  # type: ignore[no-untyped-def]
                self.calls.append((tool_name, args, context))
                if tool_name == "soridormi.skill.list":
                    return ToolCallOutcome.success(
                        {
                            "mode": "hardware",
                            "skills": [
                                {
                                    "skill_id": "express_attention",
                                    "available": True,
                                    "requires_confirmation": True,
                                    "parameters_schema": {"type": "object"},
                                }
                            ],
                        }
                    )
                return ToolCallOutcome.failed(f"unexpected tool {tool_name}")

        spoken: list[str] = []
        coordinator = InteractionRuntimeCoordinator(
            lambda args: spoken.append(str(args["text"])) or {"scheduled": True},
            soridormi_invoker=AttentionInvoker(),
        )

        result = await coordinator.execute(
            InteractionResponse(
                skills=[
                    {
                        "request_id": "attention-1",
                        "skill_id": "soridormi.express_attention",
                        "requires_confirmation": True,
                    }
                ],
                metadata={"optional_body_cue": True},
            ),
            session_id="sid-optional-confirmation",
        )

        self.assertEqual(result.status, "failed")
        self.assertEqual(
            result.results[0].reason_code,
            "optional_body_cue_unavailable",
        )
        self.assertIn("requires confirmation", result.results[0].message)
        self.assertEqual(spoken, [])

    async def test_unavailable_catalog_skill_becomes_terminal_safe_fallback(
        self,
    ) -> None:
        class UnavailableSkillInvoker(_SoridormiInvoker):
            async def invoke(self, tool_name, args, *, context=None):  # type: ignore[no-untyped-def]
                self.calls.append((tool_name, args, context))
                if tool_name == "soridormi.skill.list":
                    return ToolCallOutcome.success(
                        {
                            "mode": "sim",
                            "skills": [
                                {
                                    "skill_id": "nod_yes",
                                    "available": False,
                                    "unavailable_reason": "provider not calibrated",
                                    "parameters_schema": {"type": "object"},
                                }
                            ],
                        }
                    )
                return ToolCallOutcome.failed(f"unexpected tool {tool_name}")

        spoken: list[str] = []
        invoker = UnavailableSkillInvoker()
        coordinator = InteractionRuntimeCoordinator(
            lambda args: spoken.append(str(args["text"])) or {"scheduled": True},
            soridormi_invoker=invoker,
        )

        result = await coordinator.execute(
            InteractionResponse(
                skills=[
                    {
                        "request_id": "nod-1",
                        "skill_id": "soridormi.nod_yes",
                    }
                ]
            ),
            session_id="sid-1",
        )

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.results[0].reason_code, "skill_unavailable")
        self.assertEqual(
            spoken,
            ["I could not complete that movement safely."],
        )
        self.assertEqual(
            [call[0] for call in invoker.calls],
            ["soridormi.skill.list"],
        )

    async def test_request_bound_confirmation_authorizes_only_exact_request(self) -> None:
        invoker = _SoridormiInvoker()
        coordinator = InteractionRuntimeCoordinator(
            lambda args: {"scheduled": True},
            soridormi_invoker=invoker,
            auto_confirm_sim=False,
        )
        response = InteractionResponse(
            skills=[
                {
                    "request_id": "nod-1",
                    "skill_id": "soridormi.nod_yes",
                    "args": {"count": 2},
                }
            ]
        )

        request_ids = await coordinator.confirmation_request_ids(response)
        self.assertEqual(request_ids, {"nod-1"})

        with self.assertRaisesRegex(ValueError, "requires confirmation"):
            await coordinator.execute(response, session_id="sid-1")

        result = await coordinator.execute(
            response,
            session_id="sid-2",
            confirmed_request_ids=request_ids,
        )

        self.assertEqual(result.status, "completed")
        self.assertTrue(invoker.calls[-1][2].confirmed)

    async def test_failed_body_skill_replaces_completion_speech_with_safe_fallback(
        self,
    ) -> None:
        spoken: list[dict[str, Any]] = []
        invoker = _SoridormiInvoker(
            execute_outcome=ToolCallOutcome.success(
                {"completed": False, "skill_id": "nod_yes"}
            )
        )
        coordinator = InteractionRuntimeCoordinator(
            lambda args: spoken.append(args) or {"scheduled": True},
            soridormi_invoker=invoker,
        )

        result = await coordinator.execute(
            InteractionResponse(
                speech=[
                    {"text": "Starting.", "timing": "immediate"},
                    {"text": "Done.", "timing": "after_skills"},
                ],
                skills=[
                    {
                        "request_id": "nod-1",
                        "skill_id": "soridormi.nod_yes",
                    }
                ],
                metadata={"language": "en-US"},
            ),
            session_id="sid-failure",
        )

        self.assertEqual(result.status, "failed")
        self.assertEqual(
            [item["text"] for item in spoken],
            ["Starting.", "I could not complete that movement safely."],
        )
        self.assertEqual(
            spoken[-1]["metadata"]["source"],
            "host_body_failure_fallback",
        )
        self.assertNotIn("Done.", [item["text"] for item in spoken])

    async def test_timed_out_body_skill_uses_language_matched_fallback(self) -> None:
        spoken: list[str] = []
        coordinator = InteractionRuntimeCoordinator(
            lambda args: spoken.append(str(args["text"])) or {"scheduled": True},
            soridormi_invoker=_SoridormiInvoker(
                execute_outcome=ToolCallOutcome(
                    status="timeout",
                    error="simulated timeout",
                )
            ),
        )

        result = await coordinator.execute(
            InteractionResponse(
                skills=[{"skill_id": "soridormi.nod_yes"}],
                metadata={"language": "zh-CN"},
            ),
            session_id="sid-timeout",
        )

        self.assertEqual(result.status, "failed")
        self.assertEqual(
            spoken,
            ["动作执行超时，我无法确认它已安全完成。"],
        )
        self.assertEqual(result.results[0].status, "timed_out")

    async def test_refused_body_skill_reports_failed_safety_check(self) -> None:
        spoken: list[str] = []
        coordinator = InteractionRuntimeCoordinator(
            lambda args: spoken.append(str(args["text"])) or {"scheduled": True},
            soridormi_invoker=_SoridormiInvoker(
                monitor_outcome=ToolCallOutcome.success(
                    {"ok": False, "event": "workspace blocked"}
                )
            ),
        )

        result = await coordinator.execute(
            InteractionResponse(
                skills=[{"skill_id": "soridormi.nod_yes"}],
                metadata={"language": "en-US"},
            ),
            session_id="sid-refused",
        )

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.results[0].status, "refused")
        self.assertEqual(
            spoken,
            [
                "The safety check did not pass, so I did not perform that movement."
            ],
        )

    async def test_successful_body_skill_keeps_after_skills_speech(self) -> None:
        spoken: list[str] = []
        coordinator = InteractionRuntimeCoordinator(
            lambda args: spoken.append(str(args["text"])) or {"scheduled": True},
            soridormi_invoker=_SoridormiInvoker(),
        )

        result = await coordinator.execute(
            InteractionResponse(
                speech=[{"text": "Done.", "timing": "after_skills"}],
                skills=[{"skill_id": "soridormi.nod_yes"}],
            ),
            session_id="sid-success",
        )

        self.assertEqual(result.status, "completed")
        self.assertEqual(spoken, ["Done."])

    async def test_task_graph_skill_executes_planning_handler_and_keeps_success_speech(
        self,
    ) -> None:
        spoken: list[str] = []
        graphs: list[dict[str, Any]] = []

        async def execute_graph(graph: dict[str, Any]) -> dict[str, Any]:
            graphs.append(graph)
            return {
                "graph_id": graph["graph_id"],
                "status": "success",
                "outcome_summary": "TaskGraph completed successfully.",
                "node_results": [],
                "events": [],
            }

        coordinator = InteractionRuntimeCoordinator(
            lambda args: spoken.append(str(args["text"])) or {"scheduled": True},
            task_graph_handler=execute_graph,
        )

        result = await coordinator.execute(
            InteractionResponse(
                speech=[{"text": "Done.", "timing": "after_skills"}],
                skills=[
                    {
                        "request_id": "graph-1",
                        "skill_id": "chromie.task_graph.execute",
                        "args": {"graph": {"graph_id": "nav", "nodes": []}},
                        "timing": "sequential",
                    }
                ],
            ),
            session_id="sid-graph-success",
        )

        self.assertEqual(result.status, "completed")
        self.assertEqual(graphs, [{"graph_id": "nav", "nodes": []}])
        self.assertEqual(spoken, ["Done."])
        self.assertEqual(result.results[0].skill_id, "chromie.task_graph.execute")
        self.assertEqual(result.results[0].status, "completed")

    async def test_failed_task_graph_suppresses_completion_speech_and_falls_back(
        self,
    ) -> None:
        spoken: list[str] = []

        async def execute_graph(graph: dict[str, Any]) -> dict[str, Any]:
            return {
                "graph_id": graph["graph_id"],
                "status": "failed",
                "outcome_summary": (
                    "TaskGraph failed at node go: "
                    "reason code: missing_navigation_pipeline"
                ),
                "node_results": [],
                "events": [],
            }

        coordinator = InteractionRuntimeCoordinator(
            lambda args: spoken.append(str(args["text"])) or {"scheduled": True},
            task_graph_handler=execute_graph,
        )

        result = await coordinator.execute(
            InteractionResponse(
                speech=[{"text": "Done.", "timing": "after_skills"}],
                skills=[
                    {
                        "request_id": "graph-1",
                        "skill_id": "chromie.task_graph.execute",
                        "args": {"graph": {"graph_id": "nav", "nodes": []}},
                        "timing": "sequential",
                    }
                ],
                metadata={"language": "en-US"},
            ),
            session_id="sid-graph-failure",
        )

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.results[0].status, "failed")
        self.assertEqual(result.results[0].reason_code, "task_graph_failed")
        self.assertIn("missing_navigation_pipeline", result.results[0].message)
        self.assertEqual(spoken, ["I could not complete that task safely."])

    async def test_cancelled_task_graph_suppresses_completion_speech_and_falls_back(
        self,
    ) -> None:
        spoken: list[str] = []

        async def execute_graph(graph: dict[str, Any]) -> dict[str, Any]:
            return {
                "graph_id": graph["graph_id"],
                "status": "cancelled",
                "outcome_summary": "TaskGraph was cancelled at node monitor.",
                "node_results": [],
                "events": [],
            }

        coordinator = InteractionRuntimeCoordinator(
            lambda args: spoken.append(str(args["text"])) or {"scheduled": True},
            task_graph_handler=execute_graph,
        )

        result = await coordinator.execute(
            InteractionResponse(
                speech=[{"text": "Done.", "timing": "after_skills"}],
                skills=[
                    {
                        "request_id": "graph-1",
                        "skill_id": "chromie.task_graph.execute",
                        "args": {"graph": {"graph_id": "nav", "nodes": []}},
                        "timing": "sequential",
                    }
                ],
                metadata={"language": "en-US"},
            ),
            session_id="sid-graph-cancelled",
        )

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.results[0].status, "cancelled")
        self.assertEqual(result.results[0].reason_code, "task_graph_cancelled")
        self.assertEqual(spoken, ["The task was cancelled, so I did not continue."])

    async def test_task_graph_skill_fails_closed_when_handler_is_disabled(
        self,
    ) -> None:
        spoken: list[str] = []
        coordinator = InteractionRuntimeCoordinator(
            lambda args: spoken.append(str(args["text"])) or {"scheduled": True},
        )

        result = await coordinator.execute(
            InteractionResponse(
                skills=[
                    {
                        "request_id": "graph-1",
                        "skill_id": "chromie.task_graph.execute",
                        "args": {"graph": {"graph_id": "nav", "nodes": []}},
                        "timing": "sequential",
                    }
                ],
                metadata={"language": "en-US"},
            ),
            session_id="sid-graph-disabled",
        )

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.results[0].reason_code, "task_graph_execution_disabled")
        self.assertEqual(spoken, ["I could not complete that task safely."])

    async def test_cancelled_body_skill_suppresses_all_terminal_speech(self) -> None:
        spoken: list[str] = []
        invoker = _SoridormiInvoker(execute_delay_s=5)
        coordinator = InteractionRuntimeCoordinator(
            lambda args: spoken.append(str(args["text"])) or {"scheduled": True},
            soridormi_invoker=invoker,
        )
        task = asyncio.create_task(
            coordinator.execute(
                InteractionResponse(
                    speech=[
                        {"text": "Starting.", "timing": "immediate"},
                        {"text": "Done.", "timing": "after_skills"},
                    ],
                    skills=[{"skill_id": "soridormi.nod_yes"}],
                ),
                session_id="sid-cancelled",
            )
        )
        while not any(
            call[0] == "soridormi.skill.execute_plan" for call in invoker.calls
        ):
            await asyncio.sleep(0)

        task.cancel()
        result = await task

        self.assertEqual(result.status, "cancelled")
        self.assertEqual(spoken, ["Starting."])


if __name__ == "__main__":
    unittest.main()
