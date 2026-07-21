from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from agent.app.goal_association import GoalAssociationResolver
from agent.app.schema import AgentRunRequest, RouteDecision
from shared.chromie_runtime.runtime_trace import (
    TRACE_CARRIER_KEY,
    TRACE_FRAGMENT_KEY,
    TraceModule,
    runtime_tracer,
)


ROOT = TraceModule(
    name="tests.root",
    component_type="test",
    implementation="RuntimeTraceTests",
)
CHILD = TraceModule(
    name="tests.child",
    component_type="test_worker",
    implementation="child_operation",
)


class RuntimeTraceTests(unittest.TestCase):
    def test_nested_spans_use_monotonic_duration_and_summary(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"CHROMIE_RUNTIME_TRACE_MODE": "basic"},
            clear=False,
        ):
            scope = runtime_tracer.start_trace(
                correlations={"session_id": "sid-1"},
                attributes={"route": "chat"},
            )
            with scope:
                with runtime_tracer.span(
                    module=ROOT,
                    operation="interaction",
                    kind="interaction",
                ) as root:
                    time.sleep(0.002)
                    with runtime_tracer.span(
                        module=CHILD,
                        operation="work",
                        attributes={"count": 2},
                    ) as child:
                        time.sleep(0.002)
                        child.set_attribute("result_count", 1)
                    root.set_attribute("status", "done")
            snapshot = scope.finish()

        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertEqual(snapshot.trace["state"], "complete")
        self.assertEqual(snapshot.trace["correlations"]["session_id"], "sid-1")
        self.assertEqual(snapshot.summary["item_count"], 2)
        self.assertGreater(snapshot.summary["total_duration_ms"], 0)
        root_item, child_item = snapshot.trace["items"]
        self.assertEqual(child_item["parent_item_id"], root_item["item_id"])
        self.assertGreater(root_item["duration_ms"], child_item["duration_ms"])
        self.assertEqual(snapshot.summary["max_parallel_items"], 1)
        aggregates = {
            item["module"]["name"]: item
            for item in snapshot.summary["module_aggregates"]
        }
        self.assertIn("tests.root", aggregates)
        self.assertIn("tests.child", aggregates)
        self.assertLess(
            aggregates["tests.root"]["exclusive_duration_ms"],
            aggregates["tests.root"]["inclusive_duration_ms"],
        )

    def test_async_context_propagates_parent_and_records_error_classification(self) -> None:
        class Failure(RuntimeError):
            failure_class = "contract_invalid"

        async def run():
            with mock.patch.dict(
                os.environ,
                {"CHROMIE_RUNTIME_TRACE_MODE": "debug"},
                clear=False,
            ):
                scope = runtime_tracer.start_trace()
                async with scope:
                    async with runtime_tracer.span(
                        module=ROOT,
                        operation="parent",
                    ):
                        try:
                            async with runtime_tracer.span(
                                module=CHILD,
                                operation="failing_child",
                            ):
                                raise Failure("sensitive message")
                        except Failure:
                            pass
                return scope.finish()

        snapshot = asyncio.run(run())
        assert snapshot is not None
        failing = next(
            item
            for item in snapshot.trace["items"]
            if item["operation"] == "failing_child"
        )
        self.assertEqual(failing["status"], "error")
        self.assertEqual(failing["error"]["classification"], "contract_invalid")
        self.assertNotIn("sensitive message", json.dumps(failing))


    def test_parallel_async_children_are_counted_without_counting_parent_wrapper(self) -> None:
        async def worker(delay: float) -> None:
            async with runtime_tracer.span(module=CHILD, operation="parallel_work"):
                await asyncio.sleep(delay)

        async def run():
            with mock.patch.dict(
                os.environ,
                {"CHROMIE_RUNTIME_TRACE_MODE": "basic"},
                clear=False,
            ):
                scope = runtime_tracer.start_trace()
                async with scope:
                    async with runtime_tracer.span(module=ROOT, operation="parent"):
                        await asyncio.gather(worker(0.003), worker(0.003))
                return scope.finish()

        snapshot = asyncio.run(run())
        assert snapshot is not None
        self.assertEqual(snapshot.summary["max_parallel_items"], 2)

    def test_carrier_continuation_fragment_merges_into_parent_trace(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"CHROMIE_RUNTIME_TRACE_MODE": "basic"},
            clear=False,
        ):
            parent_scope = runtime_tracer.start_trace(
                correlations={"interaction_id": "turn-1"}
            )
            metadata = {}
            with parent_scope:
                with runtime_tracer.span(
                    module=ROOT,
                    operation="remote_call",
                    kind="tool_call",
                ):
                    carrier_context = runtime_tracer.inject_carrier({})
                    self.assertIn(TRACE_CARRIER_KEY, carrier_context)
                    continuation = runtime_tracer.continue_from_context(carrier_context)
                    with continuation:
                        with runtime_tracer.span(
                            module=CHILD,
                            operation="remote_work",
                        ):
                            pass
                    continuation.finish()
                    runtime_tracer.attach_fragment(metadata, continuation)
                    self.assertIn(TRACE_FRAGMENT_KEY, metadata)
                    self.assertTrue(
                        runtime_tracer.merge_fragment_from_metadata(metadata)
                    )
                    self.assertNotIn(TRACE_FRAGMENT_KEY, metadata)
            snapshot = parent_scope.finish()

        assert snapshot is not None
        operations = [item["operation"] for item in snapshot.trace["items"]]
        self.assertEqual(operations, ["remote_call", "remote_work"])
        remote_call = snapshot.trace["items"][0]
        remote_work = snapshot.trace["items"][1]
        self.assertEqual(remote_work["parent_item_id"], remote_call["item_id"])

    def test_mark_records_user_observable_latency(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"CHROMIE_RUNTIME_TRACE_MODE": "basic"},
            clear=False,
        ):
            scope = runtime_tracer.start_trace()
            with scope:
                runtime_tracer.mark(
                    module=ROOT,
                    name="first_audio",
                    kind="user_observable",
                )
            snapshot = scope.finish()
        assert snapshot is not None
        self.assertIsNotNone(snapshot.summary["first_user_observable_latency_ms"])

    def test_persist_snapshot_uses_runtime_event_package(self) -> None:
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(
            os.environ,
            {"CHROMIE_RUNTIME_TRACE_MODE": "basic"},
            clear=False,
        ):
            scope = runtime_tracer.start_trace(correlations={"session_id": "sid"})
            with scope:
                with runtime_tracer.span(module=ROOT, operation="work"):
                    pass
            snapshot = scope.finish()
            assert snapshot is not None
            result = runtime_tracer.persist_snapshot(
                snapshot,
                event_subtype="test_trace",
                producer="chromie.tests",
                event_root=Path(directory) / "events",
                trigger_root=Path(directory) / "inbox",
            )
            self.assertEqual(result["capture_status"], "complete")
            ready = Path(result["payload_root"])
            self.assertTrue((ready / "trace.json").is_file())
            self.assertTrue((ready / "trace-summary.json").is_file())


    def test_goal_association_continuation_emits_module_fragment(self) -> None:
        class FakeOllama:
            async def generate(self, prompt, **kwargs):
                return {
                    "new_goals": [{"description": "Respond to the user."}],
                    "clarification": "",
                    "confidence": 0.95,
                    "reason_summary": "One independent conversational goal.",
                }

        async def run():
            with mock.patch.dict(
                os.environ,
                {"CHROMIE_RUNTIME_TRACE_MODE": "basic"},
                clear=False,
            ):
                parent = runtime_tracer.start_trace(
                    correlations={"session_id": "sid-distributed"}
                )
                async with parent:
                    async with runtime_tracer.span(
                        module=ROOT,
                        operation="agent_request",
                        kind="tool_call",
                    ):
                        context = runtime_tracer.inject_carrier(
                            {"active_goal_snapshots": [], "history": []}
                        )
                        result = await GoalAssociationResolver(FakeOllama()).resolve(
                            AgentRunRequest(
                                sid="sid-distributed",
                                text="hello",
                                language="en-US",
                                route_decision=RouteDecision(
                                    route="chat",
                                    intent="conversation",
                                    confidence=0.9,
                                    source="llm",
                                ),
                                context=context,
                            )
                        )
                        self.assertIn(TRACE_FRAGMENT_KEY, result.metadata)
                        self.assertTrue(
                            runtime_tracer.merge_fragment_from_metadata(result.metadata)
                        )
                return parent.finish()

        snapshot = asyncio.run(run())
        assert snapshot is not None
        modules = {
            item["module"]["name"] for item in snapshot.trace["items"]
        }
        self.assertIn("tests.root", modules)
        self.assertIn("agent.goal_association", modules)
        remote = next(
            item
            for item in snapshot.trace["items"]
            if item["module"]["name"] == "agent.goal_association"
        )
        parent = next(
            item
            for item in snapshot.trace["items"]
            if item["operation"] == "agent_request"
        )
        self.assertEqual(remote["parent_item_id"], parent["item_id"])

    def test_off_mode_has_no_trace(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"CHROMIE_RUNTIME_TRACE_MODE": "off"},
            clear=False,
        ):
            scope = runtime_tracer.start_trace()
            self.assertFalse(scope.enabled)
            with scope:
                with runtime_tracer.span(module=ROOT, operation="ignored"):
                    pass
            self.assertIsNone(scope.finish())


if __name__ == "__main__":
    unittest.main()
