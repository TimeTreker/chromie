import unittest
from pydantic import ValidationError

from scripts.semantic_authority_audit import audit
from shared.chromie_contracts.semantic_authority import (
    SemanticAuthorityClaim,
    context_with_semantic_authority,
    semantic_authority_from_context,
    semantic_authority_route_matrix,
)


class SemanticAuthorityTests(unittest.TestCase):
    def test_only_goal_driven_runtime_is_a_valid_owner(self) -> None:
        with self.assertRaises(ValidationError):
            SemanticAuthorityClaim.model_validate(
                {"owner": "legacy_capability_fallback", "role": "authoritative", "turn_id": "t1"}
            )

    def test_authority_context_round_trip(self) -> None:
        claim = SemanticAuthorityClaim(owner="goal_driven_runtime", role="authoritative", turn_id="t1")
        context = context_with_semantic_authority({"x": 1}, claim)
        self.assertEqual(semantic_authority_from_context(context), claim)
        self.assertEqual(context["x"], 1)

    def test_route_matrix_contains_only_current_entrypoints(self) -> None:
        matrix = semantic_authority_route_matrix()
        self.assertEqual(
            {row["entrypoint"] for row in matrix},
            {"orchestrator.handle_routed_text/apply", "orchestrator.handle_routed_text/report_only"},
        )
        self.assertEqual({row["owner"] for row in matrix}, {"goal_driven_runtime"})

    def test_machine_audit_rejects_second_authority_architecture(self) -> None:
        report = audit()
        self.assertEqual(report["status"], "pass", report["errors"])
        self.assertTrue(report["single_semantic_authority_enforced"])


if __name__ == "__main__":
    unittest.main()
