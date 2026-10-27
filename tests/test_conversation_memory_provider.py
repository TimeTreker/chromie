from __future__ import annotations

import asyncio
import unittest

from agent.app.capabilities.validator import validate_value_for_schema
from orchestrator.runtime.conversation_memory_provider import (
    ConversationMemoryCapabilityProvider,
    host_runtime_memory_definitions,
    keep_person_fact,
)
from orchestrator.runtime.conversation_state import ConversationStateManager
from orchestrator.runtime.memory import PRIMARY_PERSON_REF
from orchestrator.runtime.capability_runtime import CapabilityExecutionContext
from shared.chromie_contracts.interaction import (
    CapabilityRequest,
    CapabilityTrace,
    validate_output_schema_declaration,
)


class ConversationMemoryProviderTests(unittest.TestCase):
    def test_definition_is_read_only_and_not_reference_authority(self) -> None:
        definitions = {
            item.capability_id: item for item in host_runtime_memory_definitions()
        }
        self.assertEqual(
            set(definitions),
            {"chromie.memory.retrieve_verified_tool_result", "chromie.memory.keep"},
        )
        self.assertEqual(definitions["chromie.memory.keep"].metadata["effects"], ["memory_write"])
        definition = definitions["chromie.memory.retrieve_verified_tool_result"]
        self.assertEqual(definition.metadata["safety_class"], "safe_read")
        self.assertFalse(definition.metadata["reference_resolution_authority"])
        self.assertTrue(definition.can_run_parallel)
        self.assertIs(
            validate_output_schema_declaration(definition.output_schema),
            definition.output_schema,
        )

    def test_provider_returns_only_exact_handler_result(self) -> None:
        provider = ConversationMemoryCapabilityProvider(
            lambda args: {
                "found": args["material_args"]["location"] == "内乡",
                "reason": "exact_verified_match",
                "evidence_id": args["evidence_id"],
                "tool_id": args["tool_id"],
                "request_args": dict(args["material_args"]),
                "data": {"location": "内乡", "condition": "多云"},
            }
        )
        definition = {
            item.capability_id: item for item in host_runtime_memory_definitions()
        }["chromie.memory.retrieve_verified_tool_result"]
        request = CapabilityRequest(
            request_id="memory-1",
            capability_id=definition.capability_id,
            args={
                "evidence_id": "evidence-neixiang",
                "tool_id": "chromie.weather.lookup",
                "material_args": {"location": "内乡", "date": "today"},
            },
            metadata={"source_goal_ids": ["goal-neixiang-weather"]},
        )
        result = asyncio.run(
            provider.execute(
                request,
                definition,
                CapabilityExecutionContext(
                    interaction_id="interaction-memory",
                    trace=CapabilityTrace(
                        interaction_id="interaction-memory",
                        request_id=request.request_id,
                        capability_id=request.capability_id,
                        provider_id=provider.provider_id,
                    ),
                ),
            )
        )
        self.assertEqual(result.status, "completed")
        self.assertEqual(
            result.output["result_json"],
            '{"condition":"多云","location":"内乡"}',
        )
        self.assertEqual(
            result.output["request_args_json"],
            '{"date":"today","location":"内乡"}',
        )
        self.assertEqual(set(result.output), set(definition.output_schema["required"]))
        self.assertEqual(
            validate_value_for_schema(
                result.output,
                definition.output_schema,
                path="output",
            ),
            [],
        )

    def test_keep_holds_what_the_person_asked_as_their_memory(self) -> None:
        """Owner decision 2026-10-27: "帮我记一下，要买鸡蛋和面包。" is kept, for now, as the speaker's."""
        state = ConversationStateManager(enabled=True)
        provider = ConversationMemoryCapabilityProvider(lambda args: {}, lambda args: keep_person_fact(state, args))
        definition = {item.capability_id: item for item in host_runtime_memory_definitions()}["chromie.memory.keep"]

        def keep(args):
            request = CapabilityRequest(request_id="keep-1", capability_id=definition.capability_id, args=args)
            return asyncio.run(provider.execute(request, definition, CapabilityExecutionContext(
                interaction_id="interaction-keep", trace=CapabilityTrace(
                    interaction_id="interaction-keep", request_id=request.request_id,
                    capability_id=request.capability_id, provider_id=provider.provider_id))))

        result = keep({"holds": "for_now", "key": "shopping_list", "text": "要买鸡蛋和面包"})
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.output, {"kept": True, "key": "shopping_list", "text": "要买鸡蛋和面包",
                                         "kept_for": "for_now"})
        self.assertEqual(validate_value_for_schema(result.output, definition.output_schema, path="output"), [])
        entry = next(item for item in state.session_memory()["active_memory"]["entries"]
                     if item.get("key") == "shopping_list")
        self.assertEqual(entry["subject_refs"], [PRIMARY_PERSON_REF])
        # Said by the person: a kept "I'm allergic to peanuts." is never read as Chromie's own.
        self.assertEqual(entry["text"], 'The person said: "要买鸡蛋和面包"')
        self.assertEqual(keep({"holds": "lasting", "key": "dog_name", "text": "我家小狗叫豆豆"}).output["kept_for"],
                         "this_conversation")
        self.assertEqual(keep({"holds": "for_now", "key": "Bad Key", "text": "x y z"}).status, "failed")


if __name__ == "__main__":
    unittest.main()
