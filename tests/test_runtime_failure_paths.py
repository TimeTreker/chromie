from __future__ import annotations

import ast
import tempfile
import unittest
from pathlib import Path

from agent.app.agents import AgentServices, ConversationAgent
from orchestrator.runtime.conversation_state import ConversationStateManager
from shared.chromie_runtime.runtime_trace import TraceCheckpointStore


ROOT = Path(__file__).resolve().parents[1]
MAINTAINED_RUNTIME_ROOTS = (
    ROOT / "agent" / "app",
    ROOT / "orchestrator",
    ROOT / "shared" / "chromie_runtime",
    ROOT / "shared" / "chromie_contracts",
)


class RuntimeFailurePathTests(unittest.TestCase):
    def test_model_client_invariant_is_explicit(self) -> None:
        agent = ConversationAgent(AgentServices(ollama=None, use_llm=True))

        with self.assertRaisesRegex(
            RuntimeError,
            "conversation_agent requires an Ollama client",
        ):
            agent.require_ollama()

    def test_non_atomic_semantic_operations_fail_before_mutation(self) -> None:
        manager = ConversationStateManager(base_conversation_id="failure-paths")

        with self.assertRaisesRegex(ValueError, "invalid semantic operation at index 1"):
            manager.apply_semantic_task_operations(
                [
                    {
                        "operation_id": "create-a",
                        "operation": "create",
                        "goal": {
                            "goal_id": "goal-a",
                            "description": "Handle goal A.",
                            "source_text": "Handle goal A.",
                        },
                    },
                    {"operation_id": "invalid-modify", "operation": "modify"},
                ],
                sid="sid-1",
                user_text="Handle A.",
            )

        self.assertEqual(manager.active_goal_snapshots(), [])

    def test_corrupt_runtime_trace_checkpoint_is_archived_and_visible(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = TraceCheckpointStore(root)
            checkpoint = root / "active" / "trace-corrupt.json"
            checkpoint.write_text("{not-json", encoding="utf-8")

            with self.assertLogs("chromie.runtime.trace", level="WARNING") as logs:
                pending = store.pending()

            self.assertEqual(pending, [])
            archived = list((root / "corrupt").glob("trace-corrupt*.json"))
            self.assertEqual(len(archived), 1)
            self.assertIn("Archived corrupt runtime trace checkpoint", "\n".join(logs.output))

    def test_maintained_runtime_has_no_assert_statements(self) -> None:
        violations: list[str] = []
        for source_root in MAINTAINED_RUNTIME_ROOTS:
            for path in source_root.rglob("*.py"):
                if any(
                    part in {"__pycache__", ".git", ".venv", "venv"}
                    for part in path.parts
                ):
                    continue
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Assert):
                        violations.append(
                            f"{path.relative_to(ROOT)}:{node.lineno}"
                        )
        env_script = ROOT / "scripts" / "generate_runtime_env.py"
        tree = ast.parse(env_script.read_text(encoding="utf-8"), filename=str(env_script))
        for node in ast.walk(tree):
            if isinstance(node, ast.Assert):
                violations.append(f"scripts/generate_runtime_env.py:{node.lineno}")

        self.assertEqual(violations, [])

    def test_failure_path_audit_document_is_machine_readable(self) -> None:
        audit_path = ROOT / "docs" / "RUNTIME_FAILURE_PATHS.md"
        self.assertTrue(audit_path.exists())
        text = audit_path.read_text(encoding="utf-8")
        self.assertIn("## Failure classification", text)
        self.assertIn("expected cleanup", text)
        self.assertIn("defined degradation", text)
        self.assertIn("operational failure", text)
        self.assertIn("evidence failure", text)
        self.assertIn("impossible invariant", text)


if __name__ == "__main__":
    unittest.main()
