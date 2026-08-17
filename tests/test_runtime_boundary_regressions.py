from __future__ import annotations

import inspect
import unittest

from orchestrator.orchestrator import VoiceAssistant


class RuntimeBoundaryRegressionTests(unittest.TestCase):
    def test_agent_tool_handler_is_a_bound_instance_method(self) -> None:
        assistant = VoiceAssistant.__new__(VoiceAssistant)
        handler = assistant._execute_agent_tool
        signature = inspect.signature(handler)
        self.assertEqual(list(signature.parameters), ["request", "timeout_ms"])

    def test_experience_logging_no_longer_depends_on_legacy_route(self) -> None:
        source = inspect.getsource(VoiceAssistant._record_experience)
        self.assertNotIn("record.route", source)
        self.assertNotIn(" route=%s", source)


if __name__ == "__main__":
    unittest.main()
