from __future__ import annotations

import copy
import json
import unittest
from unittest import mock

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError
from pydantic import ValidationError

from agent.app.clients.ollama_client import OllamaGenerationError
from shared.chromie_contracts.core_interpretation import CognitiveResponsibilityProposal
from agent.app.cognitive_core.goal_interpreter.engine import interpret_goal
from agent.app.cognitive_core.goal_interpreter.errors import InterpretationUnavailableError
from agent.app.cognitive_core.goal_interpreter.model_interpreter import (
    OllamaGoalInterpreter,
    _GoalInterpretationSemanticStructureViolation,
    _extract_json_object,
    _coverage_source_tokens,
    _payload_message_texts,
    _project_audited_atomic_contract,
    _reject_canonical_goal_identity_refs,
    _reject_hidden_effect_or_how_bindings,
    _reject_noncanonical_count_bindings,
    _reject_planner_shaped_goal_interpretation,
    _reject_unavailable_or_mismatched_prior_assistant_utterance,
    _reject_unprovenanced_location_bindings,
    _reject_unprovenanced_speed_bindings,
    _reject_untyped_coordination_bindings,
    _strip_bound_values_from_unresolved,
    _without_goal_interpretation_authority,
)
from agent.app.cognitive_core.goal_interpreter.schema import (
    GoalInterpretationCoverageCertificate,
    GoalInterpretationDecision,
    GoalInterpretationRequest,
)


def _valid_output(*, local_ref: str = "r1") -> dict[str, object]:
    return {
        "confidence": 0.93,
        "responsibilities": [
            {
                "local_ref": local_ref,
                "outcome": "provide today's weather for Chongqing",
                "bindings": {"location": "Chongqing", "time": "today"},
                "output_mode": "information",
                "confidence": 0.95,
            }
        ],
        "unresolved": [],
    }


class GoalInterpreterContractTests(unittest.TestCase):
    def test_hidden_effect_and_how_binding_names_are_rejected(self) -> None:
        for binding_name in ("concurrent_action", "capability", "agent_skill"):
            with self.subTest(binding_name=binding_name):
                parsed = _valid_output()
                parsed["responsibilities"][0]["bindings"] = {binding_name: "blink"}  # type: ignore[index]
                with self.assertRaises(
                    _GoalInterpretationSemanticStructureViolation
                ):
                    _reject_hidden_effect_or_how_bindings(parsed)

    def test_duration_and_location_bindings_remain_scalar(self) -> None:
        base = {
            "confidence": 1.0,
            "responsibilities": [
                {
                    "local_ref": "r1",
                    "outcome": "move forward for 15 seconds",
                    "bindings": {},
                    "output_mode": "body_action",
                    "confidence": 1.0,
                }
            ],
            "unresolved": [],
        }
        nested_duration = copy.deepcopy(base)
        nested_duration["responsibilities"][0]["bindings"] = {
            "duration": {"value": "15", "unit": "seconds"}
        }
        with self.assertRaisesRegex(ValueError, "duration binding must remain one scalar"):
            OllamaGoalInterpreter._validate_interpretation_content(
                GoalInterpretationRequest(text="move forward for 15 seconds"),
                json.dumps(nested_duration),
            )

        nested_location = copy.deepcopy(base)
        nested_location["responsibilities"][0]["bindings"] = {
            "location": {"value": "forward"}
        }
        with self.assertRaisesRegex(ValueError, "location binding must be one exact"):
            OllamaGoalInterpreter._validate_interpretation_content(
                GoalInterpretationRequest(text="move forward for 15 seconds"),
                json.dumps(nested_location),
            )

    def test_speed_requires_authoritative_source_or_context_provenance(self) -> None:
        with self.assertRaisesRegex(
            ValueError, "speed binding has no authoritative surface provenance"
        ):
            _reject_unprovenanced_speed_bindings(
                GoalInterpretationRequest(text="run forward for 15 seconds"),
                {
                    "responsibilities": [
                        {
                            "bindings": {
                                "location": "forward",
                                "duration": "15 seconds",
                                "speed": "none",
                            }
                        }
                    ]
                },
            )

    def test_speed_cannot_retype_the_same_spatial_surface(self) -> None:
        with self.assertRaisesRegex(
            ValueError, "conflicting typed dimensions.*Direction/location is never speed"
        ):
            _reject_unprovenanced_speed_bindings(
                GoalInterpretationRequest(text="你往前走 10 秒。", language="zh-CN"),
                {
                    "responsibilities": [
                        {
                            "bindings": {
                                "location": "往前",
                                "duration": "10 秒",
                                "speed": "往前",
                            }
                        }
                    ]
                },
            )

    def test_interpretation_drops_mechanically_spatial_speed_noise(self) -> None:
        decision = OllamaGoalInterpreter._validate_interpretation_content(
            GoalInterpretationRequest(text="你往前走 10 秒。", language="zh-CN"),
            json.dumps(
                {
                    "confidence": 0.99,
                    "responsibilities": [
                        {
                            "local_ref": "r1",
                            "outcome": "你往前走 10 秒。",
                            "bindings": {
                                "location": "往前",
                                "duration": "10 秒",
                                "speed": "往前",
                            },
                            "output_mode": "body_action",
                            "confidence": 0.99,
                        }
                    ],
                    "unresolved": [],
                },
                ensure_ascii=False,
            ),
        )

        self.assertEqual(
            decision.responsibilities[0].bindings,
            {"location": "往前", "duration": "10 秒"},
        )

    def test_atomic_coverage_collapses_exact_duplicate_positive_rows(self) -> None:
        request = GoalInterpretationRequest(text="你刚才说什么？", language="zh-CN")
        tokens = _coverage_source_tokens(request.text)
        decision = GoalInterpretationDecision.model_validate(
            {
                "confidence": 0.99,
                "responsibilities": [
                    {
                        "local_ref": "r1",
                        "outcome": "重复刚才的回答",
                        "bindings": {
                            "prior_assistant_utterance": "你好呀，人类！"
                        },
                        "output_mode": "speech",
                        "confidence": 0.99,
                    }
                ],
                "unresolved": [],
            }
        )
        row = {
            "source_start_token_ref": tokens[0]["ref"],
            "source_end_token_ref": tokens[-1]["ref"],
            "role": "responsibility",
            "coverage": "covered",
            "independently_satisfiable": True,
            "responsibility_refs": ["r1"],
            "required_output_mode": "speech",
        }
        raw = {
            "responsibility_items": [
                {**row, "audit_ref": "a1"},
                {**row, "audit_ref": "a2"},
            ],
            "supporting_items": [],
            "reason_summary": "One request was duplicated mechanically.",
        }

        certificate, problems = (
            OllamaGoalInterpreter._validate_responsibility_coverage_content(
                request,
                decision,
                json.dumps(raw, ensure_ascii=False),
            )
        )

        self.assertEqual(problems, [])
        self.assertEqual(len(certificate.responsibility_items), 1)

    def test_speed_alias_cannot_bypass_canonical_provenance_field(self) -> None:
        with self.assertRaisesRegex(
            ValueError, "speed meaning must use the canonical bindings.speed field"
        ):
            _reject_unprovenanced_speed_bindings(
                GoalInterpretationRequest(
                    text="你往前跑15秒，然后在边跑边唱歌。", language="zh-CN"
                ),
                {
                    "responsibilities": [
                        {
                            "bindings": {
                                "duration": "15",
                                "location": "往前",
                                "speed_mode": "none",
                            }
                        }
                    ]
                },
            )

    def test_explicit_speed_surface_remains_what_evidence(self) -> None:
        parsed = {
            "responsibilities": [
                {"bindings": {"location": "forward", "speed": "quickly"}}
            ]
        }

        _reject_unprovenanced_speed_bindings(
            GoalInterpretationRequest(text="walk forward quickly"), parsed
        )

        self.assertEqual(parsed["responsibilities"][0]["bindings"]["speed"], "quickly")

    def test_coverage_contract_structurally_partitions_outcomes_and_constraints(self) -> None:
        with self.assertRaisesRegex(ValidationError, "responsibility"):
            GoalInterpretationCoverageCertificate.model_validate(
                {
                    "responsibility_items": [
                        {
                            "source_excerpt": "for two seconds",
                            "role": "constraint",
                            "coverage": "covered",
                            "independently_satisfiable": False,
                            "responsibility_refs": ["look"],
                            "required_output_mode": "body_action",
                        }
                    ],
                    "supporting_items": [],
                    "reason_summary": "The duration is a constraint.",
                }
            )

    def test_uncovered_constraint_requires_owner_and_coordination_requires_siblings(self) -> None:
        base = {
            "responsibility_items": [
                {
                    "source_excerpt": "walk",
                    "role": "responsibility",
                    "coverage": "missing",
                    "independently_satisfiable": True,
                    "responsibility_refs": [],
                    "required_output_mode": "body_action",
                    "audit_ref": "a1",
                }
            ],
            "reason_summary": "One source outcome needs fresh segmentation.",
        }
        with self.assertRaisesRegex(ValidationError, "positive audit owner"):
            GoalInterpretationCoverageCertificate.model_validate(
                {
                    **base,
                    "supporting_items": [
                        {
                            "source_excerpt": "again",
                            "role": "constraint",
                            "coverage": "missing",
                            "independently_satisfiable": False,
                            "responsibility_refs": [],
                            "required_output_mode": "none",
                            "relation_kind": "none",
                            "related_audit_refs": [],
                        }
                    ],
                }
            )
        with self.assertRaisesRegex(ValidationError, "at least two positive audit refs"):
            GoalInterpretationCoverageCertificate.model_validate(
                {
                    **base,
                    "supporting_items": [
                        {
                            "source_excerpt": "then",
                            "role": "constraint",
                            "coverage": "missing",
                            "independently_satisfiable": False,
                            "responsibility_refs": [],
                            "required_output_mode": "none",
                            "relation_kind": "ordered",
                            "related_audit_refs": ["a1"],
                        }
                    ],
                }
            )
        with self.assertRaisesRegex(ValidationError, "True"):
            GoalInterpretationCoverageCertificate.model_validate(
                {
                    "responsibility_items": [
                        {
                            "source_excerpt": "look at me",
                            "role": "responsibility",
                            "coverage": "covered",
                            "independently_satisfiable": False,
                            "responsibility_refs": ["look"],
                            "required_output_mode": "body_action",
                        }
                    ],
                    "supporting_items": [],
                    "reason_summary": "A positive outcome is independently satisfiable.",
                }
            )

    def test_responsibility_rejects_planner_owned_information_gap(self) -> None:
        with self.assertRaisesRegex(ValidationError, "Extra inputs are not permitted"):
            CognitiveResponsibilityProposal(
                local_ref="weather",
                outcome="report today's weather at the user's location",
                bindings={"date": "today"},
                information_gaps=[
                    {
                        "gap_id": "weather_location",
                        "description": "The requested location is missing.",
                        "blocking": True,
                        "required_for": ["location"],
                        "preferred_resolution": "ask_user",
                    }
                ],
                confidence=0.95,
            )

    def test_responsibility_rejects_planner_owned_bindings(self) -> None:
        with self.assertRaisesRegex(ValueError, "Planner-owned field"):
            CognitiveResponsibilityProposal(
                local_ref="r1",
                outcome="provide today's Chongqing weather",
                bindings={
                    "location": "Chongqing",
                    "capability_id": "chromie.weather.lookup",
                },
                confidence=0.95,
            )

    def test_external_information_is_what_not_readiness(self) -> None:
        decision = GoalInterpretationDecision.model_validate(
            {
                "confidence": 0.95,
                "responsibilities": [
                    {
                        "local_ref": "weather",
                        "outcome": "Describe today's daytime weather in Chongqing.",
                        "bindings": {
                            "location": "重庆",
                            "date": "today",
                            "time_of_day": "白天",
                        },
                        "output_mode": "information",
                        "confidence": 0.95,
                    }
                ],
                "unresolved": [],
            }
        )
        responsibility = decision.responsibilities[0]
        self.assertEqual(responsibility.output_mode, "information")
        self.assertNotIn("completion_requires_work", type(responsibility).model_fields)
        self.assertNotIn("completion_requires_fresh_evidence", type(responsibility).model_fields)
        self.assertEqual(decision.unresolved, [])

    def test_responsibility_rejects_removed_readiness_fields(self) -> None:
        with self.assertRaisesRegex(ValidationError, "Extra inputs are not permitted"):
            CognitiveResponsibilityProposal.model_validate(
                {
                    "local_ref": "weather",
                    "outcome": "determine whether it rains in Chongqing this afternoon",
                    "bindings": {"location": "重庆", "time": "afternoon"},
                    "output_mode": "information",
                    "completion_requires_work": True,
                    "confidence": 0.95,
                }
            )

    def test_already_bound_values_are_not_top_level_uncertainty(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "already-bound semantic values are not unresolved",
        ):
            GoalInterpretationDecision.model_validate(
                {
                    **_valid_output(),
                    "responsibilities": [
                        {
                            **_valid_output()["responsibilities"][0],
                            "bindings": {"location": "重庆", "time": "今天上午"},
                        }
                    ],
                    "unresolved": ["重庆", "今天上午"],
                }
            )

    def test_exact_bound_unresolved_duplicate_is_mechanically_removed(self) -> None:
        parsed = {
            **_valid_output(),
            "responsibilities": [
                {
                    **_valid_output()["responsibilities"][0],
                    "bindings": {"candidate_name": "天信"},
                }
            ],
            "unresolved": ["天信", "which intended referent"],
        }

        _strip_bound_values_from_unresolved(parsed)

        self.assertEqual(parsed["unresolved"], ["which intended referent"])

    def test_decision_contract_is_what_only(self) -> None:
        schema = GoalInterpretationDecision.model_json_schema()
        self.assertEqual(
            set(schema["properties"]),
            {"confidence", "responsibilities", "unresolved"},
        )
        serialized = json.dumps(schema, sort_keys=True)
        for forbidden in (
            '"route"',
            '"intent"',
            '"progress"',
            '"actions"',
            '"candidate_capabilities"',
        ):
            self.assertNotIn(forbidden, serialized)

    def test_goal_interpretation_request_normalizes_text(self) -> None:
        request = GoalInterpretationRequest(text="  bring   me water  ")
        self.assertEqual(request.text, "bring me water")

    def test_route_and_how_fields_fail_closed_before_typed_validation(self) -> None:
        for field, value in (
            ("route", "tool"),
            ("intent", "weather_lookup"),
            ("actions", []),
            ("plan", {"steps": []}),
            ("capability_id", "chromie.weather.lookup"),
            ("response_text", "I'll check."),
        ):
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, "downstream-owned field"):
                    _reject_planner_shaped_goal_interpretation(
                        {**_valid_output(), field: value}
                    )

    def test_local_ref_cannot_reuse_canonical_goal_identity(self) -> None:
        request = GoalInterpretationRequest(
            text="Bring me the bottle.",
            context={"recent_goal_snapshots": [{"goal_id": "goal-previous"}]},
        )
        parsed = _valid_output(local_ref="goal-previous")
        with self.assertRaisesRegex(ValueError, "reused canonical Goal identity"):
            _reject_canonical_goal_identity_refs(request, parsed)

    def test_context_projection_removes_route_and_downstream_identity_recursively(self) -> None:
        projected = _without_goal_interpretation_authority(
            {
                "route": "robot_action",
                "intent": "walk_forward",
                "goal_id": "goal-1",
                "nested": {
                    "capability_id": "soridormi.walk_forward",
                    "meaning": "walk forward for ten seconds",
                },
            }
        )
        self.assertEqual(
            projected,
            {
                "goal_id": "goal-1",
                "nested": {"meaning": "walk forward for ten seconds"},
            },
        )

    def test_extract_json_object_accepts_fenced_json(self) -> None:
        self.assertEqual(
            _extract_json_object('```json\n{"confidence": 1}\n```'),
            {"confidence": 1},
        )


class GoalInterpreterPromptTests(unittest.TestCase):
    def _interpreter(self) -> OllamaGoalInterpreter:
        return OllamaGoalInterpreter(
            ollama_url="http://example.invalid",
            model="test-model",
            timeout_ms=800,
        )

    def test_coverage_prompt_uses_distinct_structural_item_contracts(self) -> None:
        interpreter = self._interpreter()
        payload = interpreter.build_responsibility_coverage_payload(
            GoalInterpretationRequest(text="walk while singing"),
            GoalInterpretationDecision.model_validate(
                {
                    "confidence": 0.95,
                    "responsibilities": [
                        {
                            "local_ref": "walk",
                            "outcome": "walk",
                            "bindings": {},
                            "output_mode": "body_action",
                            "confidence": 0.95,
                        },
                        {
                            "local_ref": "sing",
                            "outcome": "sing",
                            "bindings": {},
                            "output_mode": "singing",
                            "confidence": 0.95,
                        },
                    ],
                    "unresolved": [],
                }
            ),
        )

        schema = payload["format"]
        responsibility_ref = schema["properties"]["responsibility_items"][
            "items"
        ]["$ref"]
        supporting_ref = schema["properties"]["supporting_items"]["items"][
            "$ref"
        ]
        self.assertNotEqual(responsibility_ref, supporting_ref)
        _, _, prompt = _payload_message_texts(payload)
        self.assertIn("only in responsibility_items", prompt)
        self.assertIn("only in supporting_items", prompt)
        self.assertIn("musical vocal performance is always singing", prompt)
        self.assertIn("singing or a song is singing", prompt)
        self.assertIn("Content genre alone never creates", prompt)
        self.assertIn("A shared broad mode never merges effects", prompt)
        self.assertIn("Ordering and concurrency words", prompt)
        self.assertIn("source_start_token_ref", prompt)
        self.assertIn("relation_kind=ordered", prompt)
        self.assertIn("ordinary constraint uses relation_kind=none", prompt)
        self.assertIn("negative clause is not automatically", prompt)
        candidate_prompt = payload["messages"][1]["content"]
        candidate_section = candidate_prompt.split(
            "Candidate Responsibility DTOs (claims to audit, not source):\n",
            1,
        )[1]
        self.assertIn('"output_mode"', candidate_section)
        self.assertIn("Final atomicity check", candidate_section)
        self.assertIn("MODALITY COUNT IS AUTHORITATIVE", candidate_section)
        self.assertIn("AUTHORITATIVE SOURCE TOKENS", candidate_prompt)
        responsibility_item = schema["$defs"][
            "GoalInterpretationResponsibilityCoverageItem"
        ]
        self.assertEqual(
            responsibility_item["properties"]["independently_satisfiable"]["const"],
            True,
        )
        self.assertIn("source_start_token_ref", responsibility_item["properties"])
        self.assertIn("source_end_token_ref", responsibility_item["properties"])
        self.assertNotIn("source_token_refs", responsibility_item["properties"])
        self.assertNotIn("source_excerpt", responsibility_item["properties"])
        supporting_item = schema["$defs"][
            "GoalInterpretationSupportingCoverageItem"
        ]
        relation_clause = next(
            clause
            for clause in supporting_item["allOf"]
            if clause.get("if", {})
            .get("properties", {})
            .get("relation_kind", {})
            .get("enum")
            == ["ordered", "parallel"]
        )
        self.assertEqual(
            relation_clause["then"]["properties"]["related_audit_refs"][
                "minItems"
            ],
            2,
        )

    def test_coverage_prompt_supplies_bounded_context_for_deictic_continuation(
        self,
    ) -> None:
        interpreter = self._interpreter()
        request = GoalInterpretationRequest(
            text="刚才那个事情继续。",
            context={
                "recent_goal_snapshots": [
                    {
                        "goal_id": "goal-walk",
                        "responsibility_status": "open",
                        "goal": {
                            "description": "你往前走 10 秒",
                            "metadata": {"output_mode": "body_action"},
                        },
                    }
                ]
            },
        )
        decision = GoalInterpretationDecision.model_validate(
            {
                "confidence": 1.0,
                "responsibilities": [
                    {
                        "local_ref": "r1",
                        "outcome": "你往前走 10 秒",
                        "bindings": {"duration": "10 秒"},
                        "output_mode": "body_action",
                        "relationship": "continue",
                        "target_goal_ids": ["goal-walk"],
                        "confidence": 1.0,
                    }
                ],
                "unresolved": [],
            }
        )

        payload = interpreter.build_responsibility_coverage_payload(request, decision)
        prompt = payload["messages"][1]["content"]
        self.assertIn("BOUNDED SEMANTIC CONTINUITY CONTEXT", prompt)
        self.assertIn('"goal_id":"goal-walk"', prompt)
        self.assertIn('"output_mode":"body_action"', prompt)
        self.assertIn("reference resolution only", prompt)

    def test_coverage_materializes_exact_typo_from_reversed_source_token_refs(self) -> None:
        request = GoalInterpretationRequest(
            text="walk ahead for 15 seconds quickly, singing and blinking eyes simulatiously"
        )
        decision = GoalInterpretationDecision.model_validate(
            {
                "confidence": 0.95,
                "responsibilities": [
                    {
                        "local_ref": "blink",
                        "outcome": "blink eyes",
                        "bindings": {},
                        "output_mode": "body_action",
                        "confidence": 0.95,
                    }
                ],
                "unresolved": [],
            }
        )
        certificate, problems = (
            OllamaGoalInterpreter._validate_responsibility_coverage_content(
                request,
                decision,
                json.dumps(
                    {
                        "responsibility_items": [
                            {
                                "source_start_token_ref": "t11",
                                "source_end_token_ref": "t9",
                                "role": "responsibility",
                                "coverage": "covered",
                                "independently_satisfiable": True,
                                "responsibility_refs": ["blink"],
                                "required_output_mode": "body_action",
                            }
                        ],
                        "supporting_items": [
                            {
                                "source_start_token_ref": "t0",
                                "source_end_token_ref": "t0",
                                "role": "context",
                                "coverage": "missing",
                                "independently_satisfiable": False,
                                "responsibility_refs": ["blink"],
                                "required_output_mode": "none",
                                "relation_kind": "ordered",
                                "related_audit_refs": ["a1"],
                            }
                        ],
                        "reason_summary": "The cited source owns the blink outcome.",
                    }
                ),
            )
        )

        self.assertEqual(problems, [])
        self.assertEqual(
            certificate.responsibility_items[0].source_excerpt,
            "blinking eyes simulatiously",
        )
        self.assertEqual(certificate.supporting_items[0].coverage, "covered")
        self.assertEqual(certificate.supporting_items[0].responsibility_refs, [])
        self.assertEqual(certificate.supporting_items[0].relation_kind, "none")
        self.assertEqual(certificate.supporting_items[0].related_audit_refs, [])

    def test_coverage_derives_relation_audit_refs_when_model_returns_empty_list(self) -> None:
        request = GoalInterpretationRequest(text="walk, then blink")
        decision = GoalInterpretationDecision.model_validate(
            {
                "confidence": 0.95,
                "responsibilities": [
                    {
                        "local_ref": "walk",
                        "outcome": "walk",
                        "bindings": {},
                        "output_mode": "body_action",
                        "confidence": 0.95,
                    },
                    {
                        "local_ref": "blink",
                        "outcome": "blink",
                        "bindings": {"after": "walk"},
                        "output_mode": "body_action",
                        "confidence": 0.95,
                    },
                ],
                "unresolved": [],
            }
        )
        certificate, problems = (
            OllamaGoalInterpreter._validate_responsibility_coverage_content(
                request,
                decision,
                json.dumps(
                    {
                        "responsibility_items": [
                            {
                                "source_start_token_ref": "t0",
                                "source_end_token_ref": "t0",
                                "audit_ref": "a1",
                                "role": "responsibility",
                                "coverage": "covered",
                                "independently_satisfiable": True,
                                "responsibility_refs": ["walk"],
                                "required_output_mode": "body_action",
                            },
                            {
                                "source_start_token_ref": "t3",
                                "source_end_token_ref": "t3",
                                "audit_ref": "a2",
                                "role": "responsibility",
                                "coverage": "covered",
                                "independently_satisfiable": True,
                                "responsibility_refs": ["blink"],
                                "required_output_mode": "body_action",
                            },
                        ],
                        "supporting_items": [
                            {
                                "source_start_token_ref": "t2",
                                "source_end_token_ref": "t2",
                                "role": "constraint",
                                "coverage": "covered",
                                "independently_satisfiable": False,
                                "responsibility_refs": ["walk", "blink"],
                                "required_output_mode": "none",
                                "relation_kind": "ordered",
                                "related_audit_refs": [],
                            }
                        ],
                        "reason_summary": "Two body outcomes are ordered.",
                    }
                ),
            )
        )

        self.assertEqual(problems, [])
        self.assertEqual(
            certificate.supporting_items[0].related_audit_refs,
            ["a1", "a2"],
        )

    def test_coverage_projects_relation_candidate_owners_from_audit_refs(self) -> None:
        request = GoalInterpretationRequest(text="run while singing")
        decision = GoalInterpretationDecision.model_validate(
            {
                "confidence": 0.95,
                "responsibilities": [
                    {
                        "local_ref": "run",
                        "outcome": "run",
                        "bindings": {"parallel_with": ["sing"]},
                        "output_mode": "body_action",
                        "confidence": 0.95,
                    },
                    {
                        "local_ref": "sing",
                        "outcome": "sing",
                        "bindings": {"parallel_with": ["run"]},
                        "output_mode": "singing",
                        "confidence": 0.95,
                    },
                ],
                "unresolved": [],
            }
        )
        certificate, problems = (
            OllamaGoalInterpreter._validate_responsibility_coverage_content(
                request,
                decision,
                json.dumps(
                    {
                        "responsibility_items": [
                            {
                                "source_start_token_ref": "t0",
                                "source_end_token_ref": "t0",
                                "audit_ref": "a1",
                                "role": "responsibility",
                                "coverage": "covered",
                                "independently_satisfiable": True,
                                "responsibility_refs": ["run"],
                                "required_output_mode": "body_action",
                            },
                            {
                                "source_start_token_ref": "t2",
                                "source_end_token_ref": "t2",
                                "audit_ref": "a2",
                                "role": "responsibility",
                                "coverage": "covered",
                                "independently_satisfiable": True,
                                "responsibility_refs": ["sing"],
                                "required_output_mode": "singing",
                            },
                        ],
                        "supporting_items": [
                            {
                                "source_start_token_ref": "t1",
                                "source_end_token_ref": "t1",
                                "role": "constraint",
                                "coverage": "covered",
                                "independently_satisfiable": False,
                                "responsibility_refs": ["wrong-owner"],
                                "required_output_mode": "none",
                                "relation_kind": "parallel",
                                "related_audit_refs": ["a1", "a2"],
                            }
                        ],
                        "reason_summary": "Two outcomes are simultaneous.",
                    }
                ),
            )
        )

        self.assertEqual(problems, [])
        self.assertEqual(
            certificate.supporting_items[0].responsibility_refs,
            ["run", "sing"],
        )

    def test_coverage_recovers_separate_exact_candidate_from_swallowed_span(self) -> None:
        request = GoalInterpretationRequest(text="run while singing")
        decision = GoalInterpretationDecision.model_validate(
            {
                "confidence": 1.0,
                "responsibilities": [
                    {
                        "local_ref": "run",
                        "outcome": "run",
                        "bindings": {},
                        "output_mode": "body_action",
                        "confidence": 1.0,
                    },
                    {
                        "local_ref": "sing",
                        "outcome": "sing",
                        "bindings": {},
                        "output_mode": "singing",
                        "confidence": 1.0,
                    },
                ],
                "unresolved": [],
            }
        )
        raw = {
            "responsibility_items": [
                {
                    "source_start_token_ref": "t0",
                    "source_end_token_ref": "t2",
                    "audit_ref": "a1",
                    "role": "responsibility",
                    "coverage": "covered",
                    "independently_satisfiable": True,
                    "responsibility_refs": ["run"],
                    "required_output_mode": "body_action",
                },
                {
                    "source_start_token_ref": "t2",
                    "source_end_token_ref": "t2",
                    "audit_ref": "a2",
                    "role": "responsibility",
                    "coverage": "covered",
                    "independently_satisfiable": True,
                    "responsibility_refs": ["sing"],
                    "required_output_mode": "singing",
                },
            ],
            "supporting_items": [],
            "reason_summary": "Two effects.",
        }

        certificate, problems = (
            OllamaGoalInterpreter._validate_responsibility_coverage_content(
                request, decision, json.dumps(raw)
            )
        )

        self.assertEqual(
            [item.source_excerpt for item in certificate.responsibility_items],
            ["run", "singing"],
        )
        self.assertEqual(problems, [])

    def test_coverage_prefers_unique_exact_candidate_spans_and_restores_typed_relation(self) -> None:
        request = GoalInterpretationRequest(text="Nod twice, then blink once.")
        decision = GoalInterpretationDecision.model_validate(
            {
                "confidence": 0.95,
                "responsibilities": [
                    {
                        "local_ref": "r1",
                        "outcome": "Nod twice",
                        "bindings": {"count": 2},
                        "output_mode": "body_action",
                        "confidence": 0.95,
                    },
                    {
                        "local_ref": "r2",
                        "outcome": "Blink once",
                        "bindings": {"count": 1},
                        "output_mode": "body_action",
                        "confidence": 0.95,
                    },
                ],
                "unresolved": [],
            }
        )
        raw = {
            "responsibility_items": [
                {
                    "source_start_token_ref": "t0",
                    "source_end_token_ref": "t5",
                    "audit_ref": "a1",
                    "role": "responsibility",
                    "coverage": "covered",
                    "independently_satisfiable": True,
                    "responsibility_refs": ["r1"],
                    "required_output_mode": "body_action",
                },
                {
                    "source_start_token_ref": "t4",
                    "source_end_token_ref": "t6",
                    "audit_ref": "a2",
                    "role": "responsibility",
                    "coverage": "covered",
                    "independently_satisfiable": True,
                    "responsibility_refs": ["r2"],
                    "required_output_mode": "body_action",
                },
            ],
            "supporting_items": [
                {
                    "source_start_token_ref": "t3",
                    "source_end_token_ref": "t3",
                    "role": "constraint",
                    "coverage": "covered",
                    "independently_satisfiable": False,
                    "responsibility_refs": ["r1"],
                    "required_output_mode": "none",
                    "relation_kind": "ordered",
                    "related_audit_refs": ["a2"],
                }
            ],
            "reason_summary": "Two ordered effects.",
        }

        certificate, problems = (
            OllamaGoalInterpreter._validate_responsibility_coverage_content(
                request, decision, json.dumps(raw)
            )
        )

        self.assertEqual(
            [item.source_excerpt for item in certificate.responsibility_items],
            ["Nod twice", "blink once"],
        )
        self.assertEqual(
            certificate.supporting_items[0].related_audit_refs,
            ["a1", "a2"],
        )
        self.assertIn(
            "ordered_relation_not_preserved:r1:r2:then",
            problems,
        )

    def test_uncovered_constraint_copy_gets_unique_positive_audit_owner(self) -> None:
        request = GoalInterpretationRequest(text="Who are you?")
        decision = GoalInterpretationDecision.model_validate(
            {
                "confidence": 0.95,
                "responsibilities": [
                    {
                        "local_ref": "r1",
                        "outcome": "Who are you?",
                        "bindings": {},
                        "output_mode": "speech",
                        "confidence": 0.95,
                    }
                ],
                "unresolved": [],
            }
        )
        raw = {
            "responsibility_items": [
                {
                    "source_start_token_ref": "t0",
                    "source_end_token_ref": "t3",
                    "audit_ref": "a1",
                    "role": "responsibility",
                    "coverage": "representation_mismatch",
                    "independently_satisfiable": True,
                    "responsibility_refs": [],
                    "required_output_mode": "speech",
                }
            ],
            "supporting_items": [
                {
                    "source_start_token_ref": "t0",
                    "source_end_token_ref": "t3",
                    "role": "constraint",
                    "coverage": "representation_mismatch",
                    "independently_satisfiable": False,
                    "responsibility_refs": [],
                    "required_output_mode": "none",
                    "relation_kind": "none",
                    "related_audit_refs": [],
                }
            ],
            "reason_summary": "The candidate needs re-expression.",
        }

        certificate, problems = (
            OllamaGoalInterpreter._validate_responsibility_coverage_content(
                request, decision, json.dumps(raw)
            )
        )

        self.assertEqual(certificate.supporting_items[0].related_audit_refs, ["a1"])
        self.assertTrue(any(problem.startswith("representation_mismatch:") for problem in problems))

    def test_coverage_canonicalizes_cited_spans_and_relation_refs_to_source_order(self) -> None:
        request = GoalInterpretationRequest(text="walk then sing while blinking")
        decision = GoalInterpretationDecision.model_validate(
            {
                "confidence": 1.0,
                "responsibilities": [
                    {
                        "local_ref": "walk",
                        "outcome": "walk",
                        "bindings": {"before": "sing"},
                        "output_mode": "body_action",
                        "confidence": 1.0,
                    },
                    {
                        "local_ref": "sing",
                        "outcome": "sing",
                        "bindings": {
                            "after": "walk",
                            "parallel_with": ["blink"],
                        },
                        "output_mode": "singing",
                        "confidence": 1.0,
                    },
                    {
                        "local_ref": "blink",
                        "outcome": "blink",
                        "bindings": {"parallel_with": ["sing"]},
                        "output_mode": "body_action",
                        "confidence": 1.0,
                    },
                ],
                "unresolved": [],
            }
        )
        raw = {
            "responsibility_items": [
                {
                    "source_start_token_ref": "t0",
                    "source_end_token_ref": "t0",
                    "audit_ref": "a1",
                    "role": "responsibility",
                    "coverage": "covered",
                    "independently_satisfiable": True,
                    "responsibility_refs": ["walk"],
                    "required_output_mode": "body_action",
                },
                {
                    "source_start_token_ref": "t4",
                    "source_end_token_ref": "t4",
                    "audit_ref": "a2",
                    "role": "responsibility",
                    "coverage": "covered",
                    "independently_satisfiable": True,
                    "responsibility_refs": ["blink"],
                    "required_output_mode": "body_action",
                },
                {
                    "source_start_token_ref": "t2",
                    "source_end_token_ref": "t2",
                    "audit_ref": "a3",
                    "role": "responsibility",
                    "coverage": "covered",
                    "independently_satisfiable": True,
                    "responsibility_refs": ["sing"],
                    "required_output_mode": "singing",
                },
            ],
            "supporting_items": [
                {
                    "source_start_token_ref": "t1",
                    "source_end_token_ref": "t1",
                    "role": "constraint",
                    "coverage": "covered",
                    "independently_satisfiable": False,
                    "responsibility_refs": ["walk", "sing"],
                    "required_output_mode": "none",
                    "relation_kind": "ordered",
                    "related_audit_refs": ["a1", "a3"],
                },
                {
                    "source_start_token_ref": "t3",
                    "source_end_token_ref": "t3",
                    "role": "constraint",
                    "coverage": "covered",
                    "independently_satisfiable": False,
                    "responsibility_refs": ["sing", "blink"],
                    "required_output_mode": "none",
                    "relation_kind": "parallel",
                    "related_audit_refs": ["a3", "a2"],
                },
            ],
            "reason_summary": "Three outcomes retain source-grounded relations.",
        }

        certificate, problems = (
            OllamaGoalInterpreter._validate_responsibility_coverage_content(
                request,
                decision,
                json.dumps(raw),
            )
        )

        self.assertEqual(problems, [])
        self.assertEqual(
            [item.responsibility_refs for item in certificate.responsibility_items],
            [["walk"], ["sing"], ["blink"]],
        )
        self.assertEqual(
            [item.audit_ref for item in certificate.responsibility_items],
            ["a1", "a2", "a3"],
        )
        self.assertEqual(
            [item.related_audit_refs for item in certificate.supporting_items],
            [["a1", "a2"], ["a2", "a3"]],
        )

    def test_interpretation_strips_free_form_outcome_echo_bindings(self) -> None:
        decision = OllamaGoalInterpreter._validate_interpretation_content(
            GoalInterpretationRequest(text="run for 15 seconds"),
            json.dumps(
                {
                    "confidence": 1.0,
                    "responsibilities": [
                        {
                            "local_ref": "r1",
                            "outcome": "run for 15 seconds",
                            "bindings": {
                                "action": "run",
                                "activity": "run for 15 seconds",
                                "duration": "15 seconds",
                            },
                            "output_mode": "body_action",
                            "confidence": 1.0,
                        }
                    ],
                    "unresolved": [],
                }
            ),
        )

        self.assertEqual(decision.responsibilities[0].bindings, {"duration": "15 seconds"})

    def test_interpretation_recovers_count_fused_into_binding_name(self) -> None:
        request = GoalInterpretationRequest(
            sid="binding-key-corruption",
            text="Nod your head twice.",
            language="en-US",
        )

        decision = OllamaGoalInterpreter._validate_interpretation_content(
            request,
            json.dumps(
                {
                    "confidence": 1.0,
                    "responsibilities": [
                        {
                            "local_ref": "r1",
                            "outcome": "nod your head twice",
                            "bindings": {
                                'count\": 2,  // preserved from input': None
                            },
                            "output_mode": "body_action",
                            "confidence": 1.0,
                        }
                    ],
                    "unresolved": [],
                }
            ),
        )

        self.assertEqual(decision.responsibilities[0].bindings, {"count": 2})

    def test_interpretation_rejects_non_count_comment_leaked_into_binding_name(self) -> None:
        with self.assertRaisesRegex(ValueError, "malformed Goal Interpretation binding name"):
            OllamaGoalInterpreter._validate_interpretation_content(
                GoalInterpretationRequest(text="Nod twice."),
                json.dumps(
                    {
                        "confidence": 1.0,
                        "responsibilities": [
                            {
                                "local_ref": "r1",
                                "outcome": "nod twice",
                                "bindings": {'tempo\": fast // comment': None},
                                "output_mode": "body_action",
                                "confidence": 1.0,
                            }
                        ],
                        "unresolved": [],
                    }
                ),
            )

    def test_interpretation_rejects_serialized_field_syntax_in_binding_value(self) -> None:
        with self.assertRaisesRegex(
            ValueError, "malformed Goal Interpretation binding value"
        ):
            OllamaGoalInterpreter._validate_interpretation_content(
                GoalInterpretationRequest(text="Nod twice."),
                json.dumps(
                    {
                        "confidence": 1.0,
                        "responsibilities": [
                            {
                                "local_ref": "r1",
                                "outcome": "nod twice",
                                "bindings": {
                                    "count": 2,
                                    "nod twice": 'sequence": ',
                                },
                                "output_mode": "body_action",
                                "confidence": 1.0,
                            }
                        ],
                        "unresolved": [],
                    }
                ),
            )

    def test_audited_resegmentation_discards_provisional_free_form_coordination(self) -> None:
        decision = OllamaGoalInterpreter._validate_interpretation_content(
            GoalInterpretationRequest(text="walk and sing"),
            json.dumps(
                {
                    "confidence": 1.0,
                    "responsibilities": [
                        {
                            "local_ref": "a1",
                            "outcome": "walk",
                            "bindings": {"parallel_with": "sing at the same time"},
                            "output_mode": "body_action",
                            "confidence": 1.0,
                        },
                        {
                            "local_ref": "a2",
                            "outcome": "sing",
                            "bindings": {"coordinate_with": "walking"},
                            "output_mode": "singing",
                            "confidence": 1.0,
                        },
                    ],
                    "unresolved": [],
                }
            ),
            certificate_owns_coordination=True,
        )

        self.assertEqual(decision.responsibilities[0].bindings, {})
        self.assertEqual(decision.responsibilities[1].bindings, {})

    def test_coverage_rejects_impossible_single_outcome_typed_relation(self) -> None:
        request = GoalInterpretationRequest(text="walk for 10 seconds")
        decision = GoalInterpretationDecision.model_validate(
            {
                "confidence": 0.95,
                "responsibilities": [
                    {
                        "local_ref": "walk",
                        "outcome": "walk for 10 seconds",
                        "bindings": {"duration": "10 seconds"},
                        "output_mode": "body_action",
                        "confidence": 0.95,
                    }
                ],
                "unresolved": [],
            }
        )
        with self.assertRaisesRegex(ValidationError, "at least two positive audit refs"):
            OllamaGoalInterpreter._validate_responsibility_coverage_content(
                request,
                decision,
                json.dumps(
                    {
                        "responsibility_items": [
                            {
                                "source_start_token_ref": "t0",
                                "source_end_token_ref": "t3",
                                "audit_ref": "a1",
                                "role": "responsibility",
                                "coverage": "covered",
                                "independently_satisfiable": True,
                                "responsibility_refs": ["walk"],
                                "required_output_mode": "body_action",
                            }
                        ],
                        "supporting_items": [
                            {
                                "source_start_token_ref": "t2",
                                "source_end_token_ref": "t3",
                                "role": "constraint",
                                "coverage": "covered",
                                "independently_satisfiable": False,
                                "responsibility_refs": ["walk"],
                                "required_output_mode": "none",
                                "relation_kind": "ordered",
                                "related_audit_refs": ["a1"],
                            }
                        ],
                        "reason_summary": "The duration modifies one action.",
                    }
                ),
            )

    def test_singleton_relation_is_not_expanded_through_merged_candidate(self) -> None:
        request = GoalInterpretationRequest(text="run and sing")
        decision = GoalInterpretationDecision.model_validate(
            {
                "confidence": 1.0,
                "responsibilities": [
                    {
                        "local_ref": "merged",
                        "outcome": "run and sing",
                        "bindings": {},
                        "output_mode": "body_action",
                        "confidence": 1.0,
                    }
                ],
                "unresolved": [],
            }
        )
        with self.assertRaisesRegex(ValidationError, "at least two positive audit refs"):
            OllamaGoalInterpreter._validate_responsibility_coverage_content(
                request,
                decision,
                json.dumps(
                    {
                    "responsibility_items": [
                        {
                            "source_start_token_ref": "t0",
                            "source_end_token_ref": "t0",
                            "audit_ref": "a1",
                            "role": "responsibility",
                            "coverage": "covered",
                            "independently_satisfiable": True,
                            "responsibility_refs": ["merged"],
                            "required_output_mode": "body_action",
                        },
                        {
                            "source_start_token_ref": "t2",
                            "source_end_token_ref": "t2",
                            "audit_ref": "a2",
                            "role": "responsibility",
                            "coverage": "covered",
                            "independently_satisfiable": True,
                            "responsibility_refs": ["merged"],
                            "required_output_mode": "singing",
                        },
                    ],
                    "supporting_items": [
                        {
                            "source_start_token_ref": "t1",
                            "source_end_token_ref": "t1",
                            "role": "constraint",
                            "coverage": "covered",
                            "independently_satisfiable": False,
                            "responsibility_refs": ["merged"],
                            "required_output_mode": "none",
                            "relation_kind": "ordered",
                            "related_audit_refs": ["a1"],
                        }
                    ],
                    "reason_summary": "The candidate merged two effects.",
                    }
                ),
            )

    def test_one_repaired_singleton_relation_becomes_owned_nonrelation(self) -> None:
        request = GoalInterpretationRequest(text="run while sing")
        decision = GoalInterpretationDecision.model_validate(
            {
                "confidence": 0.95,
                "responsibilities": [
                    {
                        "local_ref": "r1",
                        "outcome": "run",
                        "bindings": {"parallel_with": ["r2"]},
                        "output_mode": "body_action",
                        "confidence": 0.95,
                    },
                    {
                        "local_ref": "r2",
                        "outcome": "sing",
                        "bindings": {"parallel_with": ["r1"]},
                        "output_mode": "singing",
                        "confidence": 0.95,
                    },
                ],
                "unresolved": [],
            }
        )
        repaired = {
            "independent_outcome_count": 2,
            "responsibility_items": [
                {
                    "source_start_token_ref": "t0",
                    "source_end_token_ref": "t0",
                    "audit_ref": "a1",
                    "role": "responsibility",
                    "coverage": "covered",
                    "independently_satisfiable": True,
                    "responsibility_refs": ["r1"],
                    "required_output_mode": "body_action",
                },
                {
                    "source_start_token_ref": "t2",
                    "source_end_token_ref": "t2",
                    "audit_ref": "a2",
                    "role": "responsibility",
                    "coverage": "covered",
                    "independently_satisfiable": True,
                    "responsibility_refs": ["r2"],
                    "required_output_mode": "singing",
                },
            ],
            "supporting_items": [
                {
                    "source_start_token_ref": "t1",
                    "source_end_token_ref": "t1",
                    "role": "constraint",
                    "coverage": "covered",
                    "independently_satisfiable": False,
                    "responsibility_refs": ["r1"],
                    "required_output_mode": "none",
                    "relation_kind": "ordered",
                    "related_audit_refs": ["a2"],
                },
                {
                    "source_start_token_ref": "t1",
                    "source_end_token_ref": "t1",
                    "role": "constraint",
                    "coverage": "covered",
                    "independently_satisfiable": False,
                    "responsibility_refs": ["r1", "r2"],
                    "required_output_mode": "none",
                    "relation_kind": "parallel",
                    "related_audit_refs": ["a1", "a2"],
                },
            ],
            "reason_summary": "Two parallel outcomes and one onset modifier.",
        }

        with self.assertRaisesRegex(
            _GoalInterpretationSemanticStructureViolation,
            "same outcome set as both ordered and parallel",
        ):
            OllamaGoalInterpreter._validate_responsibility_coverage_content(
                request,
                decision,
                json.dumps(repaired),
            )

        certificate, problems = (
            OllamaGoalInterpreter._validate_responsibility_coverage_content(
                request,
                decision,
                json.dumps(repaired),
                normalize_repaired_singleton_relations=True,
            )
        )

        self.assertEqual(
            [item.relation_kind for item in certificate.supporting_items],
            ["none", "parallel"],
        )
        self.assertEqual(
            certificate.supporting_items[0].related_audit_refs,
            ["a2"],
        )
        self.assertEqual(problems, [])

    def test_audited_atomic_contract_projects_modes_and_order(self) -> None:
        decision = GoalInterpretationDecision.model_validate(
            {
                "confidence": 0.95,
                "responsibilities": [
                    {
                        "local_ref": "a1",
                        "outcome": "walk",
                        "bindings": {"after": "a2"},
                        "output_mode": "speech",
                        "confidence": 0.95,
                    },
                    {
                        "local_ref": "a2",
                        "outcome": "sing",
                        "bindings": {},
                        "output_mode": "speech",
                        "confidence": 0.95,
                    },
                ],
                "unresolved": [],
            }
        )
        certificate = GoalInterpretationCoverageCertificate.model_validate(
            {
                "responsibility_items": [
                    {
                        "source_excerpt": "walk",
                        "audit_ref": "a1",
                        "role": "responsibility",
                        "coverage": "covered",
                        "independently_satisfiable": True,
                        "responsibility_refs": ["combined"],
                        "required_output_mode": "body_action",
                    },
                    {
                        "source_excerpt": "sing",
                        "audit_ref": "a2",
                        "role": "responsibility",
                        "coverage": "covered",
                        "independently_satisfiable": True,
                        "responsibility_refs": ["combined"],
                        "required_output_mode": "singing",
                    },
                ],
                "supporting_items": [
                    {
                        "source_excerpt": "then",
                        "role": "constraint",
                        "coverage": "covered",
                        "independently_satisfiable": False,
                        "responsibility_refs": ["combined"],
                        "required_output_mode": "none",
                        "relation_kind": "ordered",
                        "related_audit_refs": ["a1", "a2"],
                    }
                ],
                "reason_summary": "Two outcomes are ordered.",
            }
        )

        projected = _project_audited_atomic_contract(decision, certificate)

        self.assertEqual(
            [item.output_mode for item in projected.responsibilities],
            ["body_action", "singing"],
        )
        self.assertNotIn("after", projected.responsibilities[0].bindings)
        self.assertEqual(projected.responsibilities[1].bindings["after"], "a1")

    def test_deep_schema_projects_audited_order_for_distinct_candidate_owners(self) -> None:
        interpreter = self._interpreter()
        certificate = GoalInterpretationCoverageCertificate.model_validate(
            {
                "responsibility_items": [
                    {
                        "source_excerpt": "look at me",
                        "audit_ref": "a1",
                        "role": "responsibility",
                        "coverage": "covered",
                        "independently_satisfiable": True,
                        "responsibility_refs": ["look"],
                        "required_output_mode": "body_action",
                    },
                    {
                        "source_excerpt": "blink twice",
                        "audit_ref": "a2",
                        "role": "responsibility",
                        "coverage": "covered",
                        "independently_satisfiable": True,
                        "responsibility_refs": ["blink"],
                        "required_output_mode": "body_action",
                    },
                ],
                "supporting_items": [
                    {
                        "source_excerpt": "then",
                        "role": "constraint",
                        "coverage": "covered",
                        "independently_satisfiable": False,
                        "responsibility_refs": ["look", "blink"],
                        "required_output_mode": "none",
                        "relation_kind": "ordered",
                        "related_audit_refs": ["a1", "a2"],
                    }
                ],
                "reason_summary": "Two body outcomes are explicitly ordered.",
            }
        )
        payload = interpreter.build_deep_interpretation_payload(
            GoalInterpretationRequest(text="Look at me, then blink twice."),
            atomic_coverage_certificate=certificate,
            constrain_speed_provenance=True,
            constrained_binding_names=["duration"],
        )
        responsibility_model = payload["format"]["$defs"][
            "CognitiveResponsibilityProposal"
        ]

        self.assertEqual(
            responsibility_model["properties"]["local_ref"]["enum"],
            ["a1", "a2"],
        )
        blink_constraint = next(
            item
            for item in responsibility_model["allOf"]
            if item["if"]["properties"]["local_ref"]["const"] == "a2"
        )
        self.assertEqual(
            blink_constraint["then"]["properties"]["bindings"]["properties"][
                "after"
            ]["const"],
            "a1",
        )
        binding_contract = responsibility_model["properties"]["bindings"]
        self.assertNotIn("speed", binding_contract["properties"])
        self.assertNotIn("count", binding_contract["properties"])
        self.assertNotIn("item_count", binding_contract["properties"])
        self.assertNotIn("repetition_count", binding_contract["properties"])
        with self.assertRaises(JsonSchemaValidationError):
            Draft202012Validator(binding_contract).validate({"speed": "blink"})
        with self.assertRaises(JsonSchemaValidationError):
            Draft202012Validator(binding_contract).validate({"repetition_count": 1})
        with self.assertRaises(JsonSchemaValidationError):
            Draft202012Validator(binding_contract).validate({"speed_mode": "none"})
        self.assertNotIn("speed_mode", binding_contract["properties"])
        self.assertFalse(binding_contract["additionalProperties"])
        Draft202012Validator(binding_contract).validate({"duration": "twice"})
        with self.assertRaises(JsonSchemaValidationError):
            Draft202012Validator(binding_contract).validate(
                {"speed_mode_value": "none"}
            )

        count_payload = interpreter.build_deep_interpretation_payload(
            GoalInterpretationRequest(text="Look at me, then blink twice."),
            atomic_coverage_certificate=certificate,
            constrain_speed_provenance=True,
            constrained_binding_names=["repetition_count"],
        )
        count_contract = count_payload["format"]["$defs"][
            "CognitiveResponsibilityProposal"
        ]["properties"]["bindings"]
        self.assertIn("count", count_contract["properties"])
        self.assertNotIn("repetition_count", count_contract["properties"])
        Draft202012Validator(count_contract).validate({"count": 2})

    def test_system_prompt_names_what_only_boundary(self) -> None:
        prompt = self._interpreter().load_system_prompt()
        self.assertIn("only authority is to understand WHAT", prompt)
        self.assertIn("provider-neutral Responsibility evidence", prompt)
        self.assertIn("route or intent labels", prompt)
        self.assertIn("ability catalog is intentionally not supplied", prompt)
        self.assertIn("state change outside embodiment", prompt)
        self.assertIn("handover remain body_action", prompt)
        self.assertNotIn("Route Taxonomy", prompt)
        self.assertNotIn("Compatibility Framing", prompt)
        self.assertIn(
            "typed `count` binding whose value is the canonical positive JSON integer",
            prompt,
        )
        self.assertIn("A pace modifier is never a `time_modifier`", prompt)

        schema = self._interpreter()._goal_interpretation_response_schema(
            prior_assistant_utterance="你好呀！",
            admitted_turn="你刚才说什么？",
        )
        responsibility = schema["$defs"]["CognitiveResponsibilityProposal"]
        self.assertIn(
            "Never combine coordinated positive effects",
            responsibility["properties"]["outcome"]["description"],
        )
        bindings_schema = responsibility["properties"]["bindings"]
        self.assertIn("propertyNames", bindings_schema)
        self.assertNotRegex(
            'count”: 2, // commentary',
            bindings_schema["propertyNames"]["allOf"][0]["pattern"],
        )
        count_schema = bindings_schema["properties"]["count"]
        self.assertEqual(count_schema["type"], "integer")
        self.assertEqual(count_schema["minimum"], 1)
        for alias in ("item_count", "repetition_count"):
            self.assertIn(alias, bindings_schema["properties"])
            with self.assertRaises(JsonSchemaValidationError):
                Draft202012Validator(bindings_schema).validate({alias: 2})

        Draft202012Validator(bindings_schema).validate(
            {"prior_assistant_utterance": "你好呀！"}
        )
        with self.assertRaises(JsonSchemaValidationError):
            Draft202012Validator(bindings_schema).validate(
                {"prior_assistant_utterance": "你好"}
            )
        with self.assertRaises(JsonSchemaValidationError):
            Draft202012Validator(bindings_schema).validate({"speed": None})
        Draft202012Validator(bindings_schema).validate({"speed": "quickly"})
        with self.assertRaises(JsonSchemaValidationError):
            Draft202012Validator(bindings_schema).validate(
                {"parallel_with": "sing at the same time"}
            )
        Draft202012Validator(bindings_schema).validate({"parallel_with": "r2"})
        self.assertEqual(
            responsibility["properties"]["local_ref"]["enum"][:2],
            ["r1", "r2"],
        )

        no_history_schema = self._interpreter()._goal_interpretation_response_schema(
            admitted_turn="边走边唱歌。"
        )
        no_history_bindings = no_history_schema["$defs"][
            "CognitiveResponsibilityProposal"
        ]["properties"]["bindings"]
        with self.assertRaises(JsonSchemaValidationError):
            Draft202012Validator(no_history_bindings).validate(
                {"prior_assistant_utterance": "unavailable"}
            )
        with self.assertRaises(JsonSchemaValidationError):
            Draft202012Validator(no_history_bindings).validate(
                {"location": "边走边唱歌。"}
            )
        Draft202012Validator(no_history_bindings).validate({"location": "边"})

        constrained_location = self._interpreter().build_deep_interpretation_payload(
            GoalInterpretationRequest(text="边走边唱歌。", language="zh-CN"),
            constrain_location_provenance=True,
        )["format"]["$defs"]["CognitiveResponsibilityProposal"]["properties"][
            "bindings"
        ]["properties"]["location"]
        self.assertIn("边", constrained_location["enum"])
        self.assertNotIn("边走边唱歌。", constrained_location["enum"])
        self.assertNotIn("边走边唱歌", constrained_location["enum"])
        self.assertNotIn(
            "Nod twice, then blink once",
            self._interpreter()
            .build_deep_interpretation_payload(
                GoalInterpretationRequest(text="Nod twice, then blink once."),
                constrain_location_provenance=True,
            )["format"]["$defs"]["CognitiveResponsibilityProposal"]["properties"][
                "bindings"
            ]["properties"]["location"]["enum"],
        )

    def test_typed_count_contract_requires_canonical_positive_integer(self) -> None:
        _reject_noncanonical_count_bindings(
            {"responsibilities": [{"bindings": {"count": 2}}]}
        )
        with self.assertRaisesRegex(ValueError, "canonical positive JSON integer"):
            _reject_noncanonical_count_bindings(
                {"responsibilities": [{"bindings": {"count": "twice"}}]}
            )

        for alias in ("item_count", "repetition_count"):
            with self.assertRaisesRegex(ValueError, "use bindings.count"):
                _reject_noncanonical_count_bindings(
                    {"responsibilities": [{"bindings": {alias: 2}}]}
                )

    def test_prior_assistant_binding_requires_exact_available_evidence(self) -> None:
        unavailable_request = GoalInterpretationRequest(
            text="你是谁？", language="zh-CN"
        )
        unavailable = {
            "responsibilities": [
                {"bindings": {"prior_assistant_utterance": "unavailable"}}
            ]
        }
        with self.assertRaisesRegex(ValueError, "without an accepted prior"):
            _reject_unavailable_or_mismatched_prior_assistant_utterance(
                unavailable_request, unavailable
            )

        available_request = GoalInterpretationRequest(
            text="你刚才说什么？",
            language="zh-CN",
            context={"history": [{"role": "assistant", "text": "你好呀！"}]},
        )
        _reject_unavailable_or_mismatched_prior_assistant_utterance(
            available_request,
            {"responsibilities": [{"bindings": {"prior_assistant_utterance": "你好呀！"}}]},
        )
        with self.assertRaisesRegex(ValueError, "exact supplied prior text"):
            _reject_unavailable_or_mismatched_prior_assistant_utterance(
                available_request,
                {"responsibilities": [{"bindings": {"prior_assistant_utterance": "你好"}}]},
            )

    def test_system_prompt_preserves_speaker_and_immediate_conversation_boundaries(self) -> None:
        prompt = self._interpreter().load_system_prompt()
        self.assertIn("Do not decide whether downstream work", prompt)
        self.assertIn("Preserve speaker, experiencer, actor, addressee", prompt)
        self.assertIn("most recent accepted assistant/Chromie utterance", prompt)
        self.assertIn("vocative, not an independently satisfiable outcome", prompt)
        self.assertIn("prior_assistant_utterance", prompt)
        self.assertIn("standalone letter, symbol", prompt)
        self.assertIn("currently present in the surroundings", prompt)
        self.assertIn("does not continue, resume, or modify the old Goal", prompt)
        self.assertIn("Coordination does not merge independently observable effects", prompt)
        self.assertIn("Coordination grammar in any language", prompt)
        self.assertIn("one Responsibility per effect", prompt)
        self.assertIn("Each outcome describes only its own effect", prompt)
        self.assertIn("exactly one canonical JSON token", prompt)
        self.assertIn("`new`, `continue`, `modify`", prompt)
        self.assertIn("never inflect, pluralize, conjugate", prompt)
        self.assertNotIn("new or continues, modifies", prompt)

        turn_prompt = self._interpreter().build_interpretation_user_prompt(
            GoalInterpretationRequest(text="边走边唱歌。", language="zh-CN")
        )
        self.assertIn("Planner alone authors the exact utterance", turn_prompt)
        self.assertIn("Recent accepted dialogue JSON:[]", turn_prompt)
        self.assertNotIn("Most recent accepted Chromie/assistant utterance JSON", turn_prompt)
        self.assertNotIn('"status":"unavailable"', turn_prompt)

        turn_prompt = self._interpreter().build_interpretation_user_prompt(
            GoalInterpretationRequest(
                text="你刚才说什么？",
                language="zh-CN",
                context={
                    "history": [
                        {"role": "user", "text": "你好，Chromie。"},
                        {"role": "assistant", "text": "你好呀！"},
                    ]
                },
            )
        )
        self.assertIn("prior_assistant_utterance", turn_prompt)
        self.assertIn("Most recent accepted Chromie/assistant utterance JSON", turn_prompt)
        self.assertIn('"role":"assistant"', turn_prompt)
        self.assertIn('"text":"你好呀！"', turn_prompt)

    def test_system_prompt_preserves_direct_entity_surface_and_rejects_provider_time_uncertainty(self) -> None:
        prompt = self._interpreter().load_system_prompt()
        self.assertIn("exact contiguous surface", prompt)
        self.assertIn("Never translate, transliterate", prompt)
        self.assertIn("deictic spatial language", prompt)
        self.assertIn("one canonical binding name `location`", prompt)
        self.assertIn("verbatim contiguous span", prompt)
        self.assertIn("Never translate, transliterate, shorten, expand", prompt)
        self.assertIn("Preserve temporal scope as human semantic meaning", prompt)
        self.assertIn("Never derive provider-facing temporal dimensions", prompt)
        self.assertIn("timezone conversions", prompt)
        self.assertIn("does not become unresolved WHAT", prompt)
        self.assertNotIn("day_part", prompt)
        self.assertNotIn("date=today", prompt)

        turn_prompt = self._interpreter().build_interpretation_user_prompt(
            GoalInterpretationRequest(
                text="今天晚上重庆热不热？",
                language="zh-CN",
            )
        )
        self.assertIn("exact current-turn surfaces", turn_prompt)
        self.assertIn('"今天晚上重庆热不热？"', turn_prompt)
        self.assertIn("one contiguous substring", turn_prompt)

    def test_system_prompt_preserves_requested_judgment_without_asserting_the_answer(self) -> None:
        prompt = self._interpreter().load_system_prompt().casefold()
        self.assertIn("preserve the requested judgment", prompt)
        self.assertIn("whether the proposition is true", prompt)
        self.assertIn("must not become an assertion", prompt)
        self.assertIn("does not become unresolved merely because its answer is unknown", prompt)
        self.assertIn("unknown answer evidence is downstream evidence/readiness", prompt)
        self.assertIn("do not create, copy, or resolve an informationgap", prompt)
        self.assertIn("external or changing information", prompt)
        self.assertIn("declarative statement", prompt)
        self.assertIn("states a future plan is context", prompt)
        self.assertIn("do not invent a responsibility to confirm", prompt)

    def test_current_turn_prompt_distinguishes_missing_binding_from_requested_evidence(self) -> None:
        interpreter = self._interpreter()
        system_prompt = interpreter.load_system_prompt()
        prompt = interpreter.build_interpretation_user_prompt(
            GoalInterpretationRequest(
                text="哎，今天上午重庆会不会下雨？",
                language="zh-CN",
            )
        )

        self.assertIn("A missing execution input does not make", system_prompt)
        self.assertIn("External or changing information", system_prompt)
        self.assertIn("only genuine unresolved user meaning", prompt)
        self.assertIn("HOW fields", prompt)

    def test_deep_payload_reasons_from_source_without_prior_dto(self) -> None:
        interpreter = OllamaGoalInterpreter(
            ollama_url="http://example.invalid",
            model="fast-model",
            deep_model="deep-model",
            timeout_ms=800,
        )
        payload = interpreter.build_deep_interpretation_payload(
            GoalInterpretationRequest(
                text="哎，今天上午重庆会不会下雨？",
                language="zh-CN",
            )
        )

        system_text, user_text, all_text = _payload_message_texts(payload)
        self.assertFalse(payload["think"])
        self.assertEqual(payload["model"], "deep-model")
        self.assertIn("Deep Goal Interpretation", system_text)
        self.assertIn("genuine consequential ambiguity", system_text)
        self.assertIn("atomicity audit", system_text)
        self.assertIn("responsibilities must contain N sibling items", system_text)
        self.assertIn("No prior interpretation DTO is supplied", user_text)
        self.assertIn("final number of responsibilities must equal that count", user_text)
        self.assertNotIn("previous output", all_text.casefold())

    def test_decision_confidence_is_required_model_evidence(self) -> None:
        schema = GoalInterpretationDecision.model_json_schema()
        self.assertIn("confidence", schema["required"])

    def test_payload_omits_capability_catalog_and_route_contract(self) -> None:
        interpreter = self._interpreter()
        request = GoalInterpretationRequest(
            sid="weather-sid",
            text="今天重庆天气怎么样？",
            language="zh-CN",
            context={
                "prompt_capabilities_common": [
                    {
                        "capability_id": "soridormi.blink_eyes",
                        "description": "Blink the robot eyes.",
                        "route": "robot_action",
                    }
                ]
            },
        )
        payload = interpreter.build_interpretation_payload(request)
        system_text, user_text, all_text = _payload_message_texts(payload)
        self.assertIn("今天重庆天气怎么样？", user_text)
        self.assertIn("provider-neutral", system_text)
        self.assertNotIn("soridormi.blink_eyes", all_text)
        self.assertNotIn("Common Ability Catalog", all_text)
        self.assertEqual(
            set(payload["format"]["properties"]),
            {"confidence", "responsibilities", "unresolved"},
        )
        responsibility_schema = payload["format"]["$defs"][
            "CognitiveResponsibilityProposal"
        ]
        self.assertEqual(
            set(responsibility_schema["required"]),
            {"local_ref", "outcome", "bindings", "output_mode", "confidence"},
        )
        properties = responsibility_schema["properties"]
        self.assertNotIn("relationship", properties)
        self.assertNotIn("target_goal_ids", properties)
        self.assertNotIn("completion_requires_work", properties)
        self.assertNotIn("completion_requires_fresh_evidence", properties)
        self.assertNotIn("InformationGap", payload["format"]["$defs"])
        output_modes = {
            item["const"]
            for item in properties["output_mode"]["oneOf"]
        }
        self.assertIn("information", output_modes)
        self.assertIn("stateful_effect", output_modes)
        self.assertIn("speech", output_modes)
        self.assertIn("body_action", output_modes)
        self.assertNotIn("capability_work", output_modes)
        nonverbal = next(
            item
            for item in properties["output_mode"]["oneOf"]
            if item.get("const") == "nonverbal_vocalization"
        )
        self.assertIn("excludes singing", nonverbal["description"])
        media_playback = next(
            item
            for item in properties["output_mode"]["oneOf"]
            if item.get("const") == "media_playback"
        )
        self.assertIn("existing recorded media", media_playback["description"])
        self.assertIn("Never use this for Chromie to sing", media_playback["description"])

    def test_coverage_schema_describes_vocal_performance_modes_per_enum_value(
        self,
    ) -> None:
        interpreter = self._interpreter()
        request = GoalInterpretationRequest(
            text="run while singing",
            language="en-US",
        )
        decision = GoalInterpretationDecision.model_validate(
            {
                "confidence": 0.95,
                "responsibilities": [
                    {
                        "local_ref": "r1",
                        "outcome": "run forward",
                        "bindings": {},
                        "output_mode": "body_action",
                        "confidence": 0.95,
                    },
                    {
                        "local_ref": "r2",
                        "outcome": "sing while running",
                        "bindings": {"parallel_with": ["r1"]},
                        "output_mode": "singing",
                        "confidence": 0.95,
                    },
                ],
                "unresolved": [],
            }
        )

        schema = interpreter.build_responsibility_coverage_payload(
            request,
            decision,
        )["format"]
        required_mode = schema["$defs"][
            "GoalInterpretationResponsibilityCoverageItem"
        ]["properties"]["required_output_mode"]
        variants = {item["const"]: item for item in required_mode["oneOf"]}

        self.assertNotIn("enum", required_mode)
        self.assertEqual(set(variants), {
            "speech",
            "styled_speech",
            "recitation",
            "singing",
            "humming",
            "nonverbal_vocalization",
            "body_action",
            "media_playback",
            "information",
            "stateful_effect",
        })
        self.assertIn("never media playback", variants["singing"]["description"])
        self.assertIn(
            "existing recorded media",
            variants["media_playback"]["description"],
        )
        self.assertIn(
            "Never use this when Chromie is asked to sing",
            variants["media_playback"]["description"],
        )

    def test_decoder_schema_structurally_rejects_removed_readiness_fields(self) -> None:
        responsibility_schema = self._interpreter()._goal_interpretation_response_schema(
            new_relationship_only=True
        )["$defs"]["CognitiveResponsibilityProposal"]
        Draft202012Validator.check_schema(responsibility_schema)
        validator = Draft202012Validator(responsibility_schema)
        invalid = {
            "local_ref": "weather",
            "outcome": "provide today's weather",
            "bindings": {"location": "重庆"},
            "output_mode": "information",
            "completion_requires_fresh_evidence": True,
            "confidence": 0.95,
        }
        self.assertTrue(list(validator.iter_errors(invalid)))

    def test_output_mode_prompt_distinguishes_work_from_response_transport(self) -> None:
        prompt = self._interpreter().load_system_prompt()
        self.assertIn("not the eventual response transport", prompt)
        self.assertIn("Use output_mode=speech when", prompt)
        self.assertIn("not fixed by that semantic context", prompt)
        self.assertIn("Do not decide whether downstream work", prompt)
        self.assertIn("Planner owns that judgment", prompt)
        user_prompt = self._interpreter().build_interpretation_user_prompt(
            GoalInterpretationRequest(
                text="Is the external state current?",
                language="en-US",
            )
        )
        self.assertIn("Planner alone authors the exact utterance", user_prompt)
        self.assertIn("only genuine unresolved user meaning", user_prompt)

    def test_configured_goal_interpretation_output_budget_is_not_silently_capped(self) -> None:
        interpreter = OllamaGoalInterpreter(
            ollama_url="http://example.invalid",
            model="test-model",
            timeout_ms=800,
            num_predict=2048,
        )
        request = GoalInterpretationRequest(text="Walk forward, then blink twice.")
        decision = GoalInterpretationDecision.model_validate(
            {
                "confidence": 0.95,
                "responsibilities": [
                    {
                        "local_ref": "walk",
                        "outcome": "walk forward, then blink twice",
                        "bindings": {"count": 2},
                        "output_mode": "body_action",
                        "confidence": 0.95,
                    }
                ],
                "unresolved": [],
            }
        )

        self.assertEqual(
            interpreter.build_interpretation_payload(request)["options"]["num_predict"],
            2048,
        )
        self.assertEqual(
            interpreter.build_responsibility_coverage_payload(request, decision)[
                "options"
            ]["num_predict"],
            2048,
        )

    def test_repair_schema_does_not_reintroduce_planning_gap_contract(self) -> None:
        interpreter = self._interpreter()
        request = GoalInterpretationRequest(
            text="你好，今天重庆白天天气怎么样啊？",
            language="zh-CN",
        )
        try:
            CognitiveResponsibilityProposal(
                local_ref="weather",
                outcome="report today's daytime weather in Chongqing",
                bindings={"location": "重庆", "date": "today"},
                information_gaps=[
                    {
                        "gap_id": "weather_result",
                        "description": "Current weather has not been queried.",
                        "required_for": ["location", "date"],
                        "preferred_resolution": "ask_user",
                    }
                ],
                confidence=0.95,
            )
        except ValidationError as exc:
            payload = interpreter.build_interpretation_repair_payload(
                request,
                previous_content="rejected",
                validation_error=exc,
            )
        else:  # pragma: no cover - protects the regression setup itself
            self.fail("invalid ask_user gap unexpectedly passed validation")

        self.assertNotIn("InformationGap", payload["format"]["$defs"])
        system_text, _, _ = _payload_message_texts(payload)
        self.assertIn("Never create/resolve an InformationGap", system_text)

    def test_goal_relationship_fields_remain_model_owned_when_goal_context_exists(self) -> None:
        interpreter = self._interpreter()
        payload = interpreter.build_interpretation_payload(
            GoalInterpretationRequest(
                text="那就继续吧",
                language="zh-CN",
                context={
                    "active_goal_snapshots": [
                        {
                            "goal_id": "goal-existing",
                            "goal": {
                                "goal_id": "goal-existing",
                                "description": "continue the existing request",
                            },
                        }
                    ]
                },
            )
        )

        responsibility = payload["format"]["$defs"][
            "CognitiveResponsibilityProposal"
        ]
        self.assertIn("relationship", responsibility["properties"])
        self.assertIn("target_goal_ids", responsibility["properties"])
        self.assertIn("relationship", responsibility["required"])
        self.assertIn("target_goal_ids", responsibility["required"])
        relationship = responsibility["properties"]["relationship"]
        self.assertNotIn("enum", relationship)
        self.assertEqual(
            {item["const"] for item in relationship["oneOf"]},
            {
                "continue",
                "modify",
                "clarify",
                "confirm",
                "reject",
                "cancel",
                "pause",
                "resume",
                "merge",
                "split",
                "reference",
                "new",
            },
        )
        self.assertIn("never inflect", relationship["description"])
        self.assertNotIn("continues", json.dumps(relationship))
        self.assertNotIn("resumes", json.dumps(relationship))
        self.assertEqual(
            responsibility["properties"]["target_goal_ids"]["items"]["enum"],
            ["goal-existing"],
        )
        relationship_targets = responsibility["allOf"][-1]
        self.assertEqual(
            relationship_targets["if"]["properties"]["relationship"],
            {"const": "new"},
        )
        self.assertEqual(
            relationship_targets["then"]["properties"]["target_goal_ids"][
                "maxItems"
            ],
            0,
        )
        self.assertEqual(
            relationship_targets["else"]["properties"]["target_goal_ids"][
                "minItems"
            ],
            1,
        )
        _, user_prompt, _ = _payload_message_texts(payload)
        self.assertIn("canonical relationship tokens", user_prompt)
        self.assertIn("supplied target Goal IDs", user_prompt)

        repair = interpreter.build_interpretation_repair_payload(
            GoalInterpretationRequest(
                text="刚才那个事情继续。",
                language="zh-CN",
                context={
                    "active_goal_snapshots": [
                        {"goal_id": "goal-existing", "goal": {"goal_id": "goal-existing"}}
                    ]
                },
            ),
            previous_content='{"relationship":"continues"}',
            validation_error=ValueError("invalid relationship token"),
        )
        repair_responsibility = repair["format"]["$defs"][
            "CognitiveResponsibilityProposal"
        ]
        self.assertEqual(
            repair_responsibility["properties"]["target_goal_ids"]["items"]["enum"],
            ["goal-existing"],
        )
        self.assertIn(
            "continue",
            {
                item["const"]
                for item in repair_responsibility["properties"]["relationship"]["oneOf"]
            },
        )
        repair_system, _, _ = _payload_message_texts(repair)
        self.assertIn("copy one exact protocol token", repair_system)

    def test_recent_terminal_goal_semantics_are_available_for_continuation(self) -> None:
        interpreter = self._interpreter()
        request = GoalInterpretationRequest(
            text="刚才那个事情继续。",
            language="zh-CN",
            context={
                "active_goal_snapshots": [],
                "recent_goal_snapshots": [
                    {
                        "goal_id": "goal-walk",
                        "responsibility_status": "satisfied",
                        "last_user_update": "你往前走 10 秒。",
                        "goal": {
                            "goal_id": "goal-walk",
                            "description": "move forward for ten seconds",
                            "metadata": {
                                "output_mode": "body_action",
                            },
                        },
                    }
                ],
            },
        )

        payload = interpreter.build_interpretation_payload(request)
        _, user_prompt, _ = _payload_message_texts(payload)

        self.assertIn("Retained active/recent Goal semantics", user_prompt)
        self.assertIn('"goal_id":"goal-walk"', user_prompt)
        self.assertIn("move forward for ten seconds", user_prompt)
        responsibility = payload["format"]["$defs"][
            "CognitiveResponsibilityProposal"
        ]
        self.assertEqual(
            responsibility["properties"]["target_goal_ids"]["items"]["enum"],
            ["goal-walk"],
        )

    def test_repair_schema_excludes_bound_values_from_unresolved(self) -> None:
        interpreter = self._interpreter()
        request = GoalInterpretationRequest(
            text="哎，今天上午重庆会不会下雨？",
            language="zh-CN",
        )
        try:
            GoalInterpretationDecision.model_validate(
                {
                    **_valid_output(),
                    "responsibilities": [
                        {
                            **_valid_output()["responsibilities"][0],
                            "bindings": {"location": "重庆", "time": "今天上午"},
                        }
                    ],
                    "unresolved": ["重庆", "今天上午"],
                }
            )
        except ValidationError as exc:
            payload = interpreter.build_interpretation_repair_payload(
                request,
                previous_content="rejected",
                validation_error=exc,
            )
        else:  # pragma: no cover - protects the regression setup itself
            self.fail("bound unresolved values unexpectedly passed validation")

        unresolved_items = payload["format"]["properties"]["unresolved"]["items"]
        self.assertEqual(
            set(unresolved_items["not"]["enum"]),
            {"重庆", "今天上午"},
        )
        system_text, _, _ = _payload_message_texts(payload)
        self.assertIn("already-resolved binding values", system_text)

    def test_prompt_keeps_semantic_continuity_with_context_goal_identity_but_no_route(self) -> None:
        prompt = self._interpreter().build_interpretation_user_prompt(
            GoalInterpretationRequest(
                sid="s1",
                text="Make that one iced.",
                context={
                    "history": [
                        {
                            "role": "user",
                            "text": "Bring me a coffee.",
                            "route": "tool",
                            "intent": "coffee",
                        }
                    ],
                    "active_goal_snapshots": [
                        {
                            "goal_id": "goal-coffee",
                            "responsibility_status": "open",
                            "goal": {"description": "obtain coffee for the user"},
                        }
                    ],
                },
            )
        )
        self.assertIn("Bring me a coffee", prompt)
        self.assertIn("obtain coffee for the user", prompt)
        self.assertIn("goal-coffee", prompt)
        self.assertNotIn('"route"', prompt)
        self.assertNotIn('"intent"', prompt)

    def test_prompt_exposes_retained_goal_completion_modality_for_continuation(self) -> None:
        prompt = self._interpreter().build_interpretation_user_prompt(
            GoalInterpretationRequest(
                sid="continue-walk",
                text="刚才那个事情继续。",
                language="zh-CN",
                context={
                    "active_goal_snapshots": [
                        {
                            "goal_id": "goal-walk",
                            "goal": {
                                "goal_id": "goal-walk",
                                "description": "move forward 10 seconds",
                                "metadata": {
                                    "output_mode": "body_action",
                                },
                            },
                        }
                    ]
                },
            )
        )

        self.assertIn('"output_mode":"body_action"', prompt)
        self.assertNotIn("completion_requires_work", prompt)
        self.assertIn("exact source-grounded modality", prompt)

    def test_repair_prompt_does_not_replay_rejected_output(self) -> None:
        interpreter = self._interpreter()
        request = GoalInterpretationRequest(text="Bring me water.")
        payload = interpreter.build_interpretation_repair_payload(
            request,
            previous_content='{"capability_id":"soridormi.acquire_water"}',
            validation_error=ValueError("forbidden capability"),
        )
        _, user_text, all_text = _payload_message_texts(payload)
        self.assertIn("Regenerate from the authoritative user meaning", user_text)
        self.assertNotIn("soridormi.acquire_water", all_text)
        self.assertNotIn("forbidden capability", all_text)


class GoalInterpreterExecutionTests(unittest.IsolatedAsyncioTestCase):
    def _interpreter(self) -> OllamaGoalInterpreter:
        return OllamaGoalInterpreter(
            ollama_url="http://example.invalid",
            model="test-model",
            timeout_ms=800,
        )

    async def test_spatial_value_mistyped_as_speed_is_removed_before_audit(self) -> None:
        interpreter = self._interpreter()
        invalid = {
            "confidence": 0.96,
            "responsibilities": [
                {
                    "local_ref": "r1",
                    "outcome": "你往前走 10 秒",
                    "bindings": {
                        "duration": "10 秒",
                        "location": "往前",
                        "speed": "往前",
                    },
                    "output_mode": "body_action",
                    "relationship": "new",
                    "target_goal_ids": [],
                    "confidence": 0.96,
                }
            ],
            "unresolved": [],
        }
        coverage = {
            "responsibility_items": [
                {
                    "source_excerpt": "你往前走 10 秒",
                    "role": "responsibility",
                    "coverage": "covered",
                    "independently_satisfiable": True,
                    "responsibility_refs": ["r1"],
                    "required_output_mode": "body_action",
                }
            ],
            "supporting_items": [],
            "reason_summary": "One body outcome preserves direction and duration.",
        }
        interpreter._chat = mock.AsyncMock(  # type: ignore[method-assign]
            side_effect=[
                {"message": {"content": json.dumps(invalid, ensure_ascii=False)}},
                {"message": {"content": json.dumps(coverage, ensure_ascii=False)}},
            ]
        )

        result = await interpreter.interpret_goal(
            GoalInterpretationRequest(text="你往前走 10 秒。", language="zh-CN")
        )

        self.assertNotIn("speed", result.responsibilities[0].bindings)
        self.assertEqual(
            [call.kwargs["stage"] for call in interpreter._chat.await_args_list],
            [
                "goal_interpretation",
                "goal_interpretation_responsibility_coverage",
            ],
        )

    async def test_independent_coverage_resegments_collapsed_effects_from_source(self) -> None:
        interpreter = self._interpreter()
        collapsed = {
            "confidence": 0.96,
            "responsibilities": [
                {
                    "local_ref": "combined",
                    "outcome": "walk forward for two seconds, then blink twice",
                    "bindings": {"duration": 2, "count": 2},
                    "output_mode": "body_action",
                    "relationship": "new",
                    "target_goal_ids": [],
                    "confidence": 0.96,
                }
            ],
            "unresolved": [],
        }
        rejected_coverage = {
            "responsibility_items": [
                {
                    "source_excerpt": "walk forward for two seconds",
                    "audit_ref": "a1",
                    "role": "responsibility",
                    "coverage": "covered",
                    "independently_satisfiable": True,
                    "responsibility_refs": ["combined"],
                    "required_output_mode": "body_action",
                },
                {
                    "source_excerpt": "blink twice",
                    "audit_ref": "a2",
                    "role": "responsibility",
                    "coverage": "covered",
                    "independently_satisfiable": True,
                    "responsibility_refs": ["combined"],
                    "required_output_mode": "body_action",
                },
            ],
            "supporting_items": [
                {
                    "source_excerpt": "then",
                    "role": "constraint",
                    "coverage": "covered",
                    "independently_satisfiable": False,
                    "responsibility_refs": ["combined"],
                    "required_output_mode": "none",
                    "relation_kind": "ordered",
                    "related_audit_refs": ["a1", "a2"],
                }
            ],
            "reason_summary": "The source requests two independently checkable effects.",
        }
        corrected = {
            "confidence": 0.96,
            "responsibilities": [
                {
                    "local_ref": "a1",
                    "outcome": "walk forward for two seconds",
                    "bindings": {"duration": 2},
                    "output_mode": "body_action",
                    "relationship": "new",
                    "target_goal_ids": [],
                    "confidence": 0.96,
                },
                {
                    "local_ref": "a2",
                    "outcome": "blink twice",
                    "bindings": {"after": "a1", "count": 2},
                    "output_mode": "body_action",
                    "relationship": "new",
                    "target_goal_ids": [],
                    "confidence": 0.96,
                },
            ],
            "unresolved": [],
        }
        interpreter._chat = mock.AsyncMock(  # type: ignore[method-assign]
            side_effect=[
                {"message": {"content": json.dumps(collapsed)}},
                {"message": {"content": json.dumps(rejected_coverage)}},
                {"message": {"content": json.dumps(corrected)}},
            ]
        )

        result = await interpreter.interpret_goal(
            GoalInterpretationRequest(
                text="walk forward for two seconds, then blink twice"
            )
        )

        self.assertEqual([item.local_ref for item in result.responsibilities], ["a1", "a2"])
        self.assertEqual(result.responsibilities[1].bindings["after"], "a1")
        self.assertEqual(
            [call.kwargs["stage"] for call in interpreter._chat.await_args_list],
            [
                "goal_interpretation",
                "goal_interpretation_responsibility_coverage",
                "goal_interpretation_deep",
            ],
        )
        deep_payload = interpreter._chat.await_args_list[2].args[0]
        _, _, deep_prompt = _payload_message_texts(deep_payload)
        self.assertIn(
            "independent source-based atomic coverage audit",
            deep_prompt,
        )
        self.assertIn("walk forward for two seconds", deep_prompt)
        self.assertIn("blink twice", deep_prompt)
        self.assertIn("before/after sibling-local-ref bindings", deep_prompt)
        self.assertIn('"source_excerpt":"then"', deep_prompt)
        responsibilities_schema = deep_payload["format"]["properties"][
            "responsibilities"
        ]
        self.assertEqual(responsibilities_schema["minItems"], 2)
        self.assertEqual(responsibilities_schema["maxItems"], 2)
        GoalInterpretationCoverageCertificate.model_validate(rejected_coverage)

    async def test_missing_pre_resegmentation_owner_becomes_covered_by_fresh_candidate(self) -> None:
        interpreter = self._interpreter()
        initial = {
            "confidence": 0.7,
            "responsibilities": [
                {
                    "local_ref": "r1",
                    "outcome": "walk forward",
                    "bindings": {},
                    "output_mode": "body_action",
                    "relationship": "new",
                    "target_goal_ids": [],
                    "confidence": 0.7,
                }
            ],
            "unresolved": [],
        }
        missing_coverage = {
            "responsibility_items": [
                {
                    "source_excerpt": "walk",
                    "role": "responsibility",
                    "coverage": "covered",
                    "independently_satisfiable": True,
                    "responsibility_refs": ["r1"],
                    "required_output_mode": "body_action",
                },
                {
                    "source_excerpt": "blink",
                    "role": "responsibility",
                    "coverage": "missing",
                    "independently_satisfiable": True,
                    "responsibility_refs": [],
                    "required_output_mode": "body_action",
                }
            ],
            "supporting_items": [],
            "reason_summary": "The blink effect has no candidate owner.",
        }
        corrected = {
            "confidence": 0.96,
            "responsibilities": [
                {
                    "local_ref": "a1",
                    "outcome": "walk forward",
                    "bindings": {},
                    "output_mode": "body_action",
                    "relationship": "new",
                    "target_goal_ids": [],
                    "confidence": 0.96,
                },
                {
                    "local_ref": "a2",
                    "outcome": "blink",
                    "bindings": {},
                    "output_mode": "body_action",
                    "relationship": "new",
                    "target_goal_ids": [],
                    "confidence": 0.96,
                }
            ],
            "unresolved": [],
        }
        interpreter._chat = mock.AsyncMock(  # type: ignore[method-assign]
            side_effect=[
                {"message": {"content": json.dumps(initial)}},
                {"message": {"content": json.dumps(missing_coverage)}},
                {"message": {"content": json.dumps(corrected)}},
            ]
        )

        result = await interpreter.interpret_goal(
            GoalInterpretationRequest(text="walk and blink")
        )

        self.assertEqual(
            [item.local_ref for item in result.responsibilities], ["a1", "a2"]
        )
        self.assertEqual(result.responsibilities[1].outcome, "blink")
        self.assertEqual(interpreter._chat.await_count, 3)
        deep_schema = interpreter._chat.await_args_list[2].args[0]["format"]
        self.assertEqual(
            deep_schema["properties"]["responsibilities"]["minItems"], 2
        )
        self.assertEqual(
            deep_schema["$defs"]["CognitiveResponsibilityProposal"]["properties"]
            ["local_ref"]["enum"],
            ["a1", "a2"],
        )

    async def test_mechanically_invalid_coverage_certificate_gets_one_dto_repair(self) -> None:
        interpreter = self._interpreter()
        decision = GoalInterpretationDecision.model_validate(
            {
                "confidence": 0.95,
                "responsibilities": [
                    {
                        "local_ref": "r1",
                        "outcome": "walk forward",
                        "bindings": {},
                        "output_mode": "body_action",
                        "confidence": 0.95,
                    }
                ],
                "unresolved": [],
            }
        )
        invalid = {
            "responsibility_items": [
                {
                    "source_excerpt": "walk forward",
                    "role": "responsibility",
                    "coverage": "missing",
                    "independently_satisfiable": True,
                    "responsibility_refs": ["r1"],
                    "required_output_mode": "body_action",
                }
            ],
            "supporting_items": [],
            "reason_summary": "Invalid missing ownership.",
        }
        repaired = copy.deepcopy(invalid)
        repaired["responsibility_items"][0]["coverage"] = "covered"
        interpreter._chat = mock.AsyncMock(  # type: ignore[method-assign]
            side_effect=[
                {"message": {"content": json.dumps(invalid)}},
                {"message": {"content": json.dumps(repaired)}},
            ]
        )

        result = await interpreter._ensure_atomic_responsibility_coverage(
            GoalInterpretationRequest(text="walk forward"),
            decision,
        )

        self.assertEqual(result, decision)
        self.assertEqual(
            [call.kwargs["stage"] for call in interpreter._chat.await_args_list],
            [
                "goal_interpretation_responsibility_coverage",
                "goal_interpretation_responsibility_coverage_repair",
            ],
        )
        coverage_item_schema = interpreter._chat.await_args_list[0].args[0][
            "format"
        ]["$defs"]["GoalInterpretationResponsibilityCoverageItem"]
        self.assertTrue(
            any(
                clause.get("if", {})
                .get("properties", {})
                .get("coverage", {})
                .get("const")
                == "missing"
                and clause.get("then", {})
                .get("properties", {})
                .get("responsibility_refs", {})
                .get("maxItems")
                == 0
                for clause in coverage_item_schema["allOf"]
            )
        )

    async def test_coverage_repair_preserves_explicit_atomic_count(self) -> None:
        interpreter = self._interpreter()
        request = GoalInterpretationRequest(text="Nod twice, then blink once.")
        merged = GoalInterpretationDecision.model_validate(
            {
                "confidence": 0.95,
                "responsibilities": [
                    {
                        "local_ref": "r1",
                        "outcome": "Nod twice, then blink once.",
                        "bindings": {"count": 2},
                        "output_mode": "body_action",
                        "confidence": 0.95,
                    }
                ],
                "unresolved": [],
            }
        )
        invalid_singleton = {
            "independent_outcome_count": 2,
            "responsibility_items": [
                {
                    "source_start_token_ref": "t0",
                    "source_end_token_ref": "t5",
                    "audit_ref": "a1",
                    "role": "responsibility",
                    "coverage": "covered",
                    "independently_satisfiable": True,
                    "responsibility_refs": ["r1"],
                    "required_output_mode": "body_action",
                }
            ],
            "supporting_items": [
                {
                    "source_start_token_ref": "t3",
                    "source_end_token_ref": "t3",
                    "role": "constraint",
                    "coverage": "covered",
                    "independently_satisfiable": False,
                    "responsibility_refs": ["r1"],
                    "required_output_mode": "none",
                    "relation_kind": "ordered",
                    "related_audit_refs": ["a1"],
                }
            ],
            "reason_summary": "Two independently satisfiable outcomes are present.",
        }
        repaired_atomic = {
            "independent_outcome_count": 2,
            "responsibility_items": [
                {
                    "source_start_token_ref": "t0",
                    "source_end_token_ref": "t1",
                    "audit_ref": "a1",
                    "role": "responsibility",
                    "coverage": "covered",
                    "independently_satisfiable": True,
                    "responsibility_refs": ["r1"],
                    "required_output_mode": "body_action",
                },
                {
                    "source_start_token_ref": "t4",
                    "source_end_token_ref": "t5",
                    "audit_ref": "a2",
                    "role": "responsibility",
                    "coverage": "covered",
                    "independently_satisfiable": True,
                    "responsibility_refs": ["r1"],
                    "required_output_mode": "body_action",
                },
            ],
            "supporting_items": [
                {
                    "source_start_token_ref": "t3",
                    "source_end_token_ref": "t3",
                    "role": "constraint",
                    "coverage": "covered",
                    "independently_satisfiable": False,
                    "responsibility_refs": ["r1"],
                    "required_output_mode": "none",
                    "relation_kind": "ordered",
                    "related_audit_refs": ["a1", "a2"],
                }
            ],
            "reason_summary": "Two atomic outcomes are ordered.",
        }
        resegmented = {
            "confidence": 0.95,
            "responsibilities": [
                {
                    "local_ref": "a1",
                    "outcome": "Nod twice",
                    "bindings": {"count": 2},
                    "output_mode": "body_action",
                    "relationship": "new",
                    "target_goal_ids": [],
                    "confidence": 0.95,
                },
                {
                    "local_ref": "a2",
                    "outcome": "Blink once",
                    "bindings": {"count": 1},
                    "output_mode": "body_action",
                    "relationship": "new",
                    "target_goal_ids": [],
                    "confidence": 0.95,
                },
            ],
            "unresolved": [],
        }
        interpreter._chat = mock.AsyncMock(  # type: ignore[method-assign]
            side_effect=[
                {"message": {"content": json.dumps(invalid_singleton)}},
                {"message": {"content": json.dumps(repaired_atomic)}},
                {"message": {"content": json.dumps(resegmented)}},
            ]
        )

        result = await interpreter._ensure_atomic_responsibility_coverage(
            request,
            merged,
        )

        self.assertEqual(
            [item.local_ref for item in result.responsibilities], ["a1", "a2"]
        )
        self.assertEqual(result.responsibilities[1].bindings["after"], "a1")
        repair_schema = interpreter._chat.await_args_list[1].args[0]["format"]
        self.assertEqual(
            repair_schema["properties"]["independent_outcome_count"]["const"],
            2,
        )
        self.assertEqual(
            repair_schema["properties"]["responsibility_items"]["minItems"],
            2,
        )
        self.assertEqual(
            repair_schema["properties"]["responsibility_items"]["maxItems"],
            2,
        )

    async def test_smaller_audit_cannot_erase_validated_consequential_effect(self) -> None:
        interpreter = self._interpreter()
        decision = GoalInterpretationDecision.model_validate(
            {
                "confidence": 0.95,
                "responsibilities": [
                    {
                        "local_ref": "r1",
                        "outcome": "walk ahead quickly for 15 seconds",
                        "bindings": {"duration": 15, "speed": "quickly"},
                        "output_mode": "body_action",
                        "confidence": 0.95,
                    },
                    {
                        "local_ref": "r2",
                        "outcome": "sing while walking",
                        "bindings": {},
                        "output_mode": "singing",
                        "confidence": 0.95,
                    },
                    {
                        "local_ref": "r3",
                        "outcome": "blink eyes simultaneously",
                        "bindings": {},
                        "output_mode": "body_action",
                        "confidence": 0.95,
                    },
                ],
                "unresolved": [],
            }
        )
        smaller_audit = {
            "independent_outcome_count": 2,
            "responsibility_items": [
                {
                    "source_excerpt": "walk ahead for 15 seconds quickly",
                    "audit_ref": "a1",
                    "role": "responsibility",
                    "coverage": "covered",
                    "independently_satisfiable": True,
                    "responsibility_refs": ["r1"],
                    "required_output_mode": "body_action",
                },
                {
                    "source_excerpt": "singing",
                    "audit_ref": "a2",
                    "role": "responsibility",
                    "coverage": "covered",
                    "independently_satisfiable": True,
                    "responsibility_refs": ["r2"],
                    "required_output_mode": "singing",
                },
            ],
            "supporting_items": [
                {
                    "source_excerpt": "singing and blinking eyes simultaneously",
                    "role": "constraint",
                    "coverage": "covered",
                    "independently_satisfiable": False,
                    "responsibility_refs": ["r1", "r2"],
                    "required_output_mode": "none",
                    "relation_kind": "parallel",
                    "related_audit_refs": ["a1", "a2"],
                }
            ],
            "reason_summary": "The smaller audit omitted one effect candidate.",
        }
        interpreter._chat = mock.AsyncMock(  # type: ignore[method-assign]
            return_value={"message": {"content": json.dumps(smaller_audit)}}
        )

        result = await interpreter._ensure_atomic_responsibility_coverage(
            GoalInterpretationRequest(
                text=(
                    "walk ahead for 15 seconds quickly, singing and blinking eyes "
                    "simultaneously"
                )
            ),
            decision,
        )

        self.assertEqual(len(result.responsibilities), 3)
        self.assertEqual(result.responsibilities[2].local_ref, "r3")
        self.assertEqual(result.responsibilities[2].output_mode, "body_action")
        self.assertEqual(result.responsibilities[0].bindings["parallel_with"], ["r2"])
        self.assertEqual(result.responsibilities[1].bindings["parallel_with"], ["r1"])
        self.assertEqual(interpreter._chat.await_count, 1)

    async def test_resegmentation_preserves_unowned_effect_sibling(self) -> None:
        interpreter = self._interpreter()
        decision = GoalInterpretationDecision.model_validate(
            {
                "confidence": 0.9,
                "responsibilities": [
                    {
                        "local_ref": "r1",
                        "outcome": "run forward for 15 seconds while blinking eyes",
                        "bindings": {"duration": 15},
                        "output_mode": "body_action",
                        "confidence": 0.9,
                    },
                    {
                        "local_ref": "r2",
                        "outcome": "sing a song",
                        "bindings": {},
                        "output_mode": "singing",
                        "confidence": 0.9,
                    },
                ],
                "unresolved": [],
            }
        )
        split_audit = {
            "independent_outcome_count": 2,
            "responsibility_items": [
                {
                    "source_excerpt": "run forward for 15 seconds",
                    "audit_ref": "a1",
                    "role": "responsibility",
                    "coverage": "covered",
                    "independently_satisfiable": True,
                    "responsibility_refs": ["r1"],
                    "required_output_mode": "body_action",
                },
                {
                    "source_excerpt": "blinking eyes",
                    "audit_ref": "a2",
                    "role": "responsibility",
                    "coverage": "covered",
                    "independently_satisfiable": True,
                    "responsibility_refs": ["r1"],
                    "required_output_mode": "body_action",
                },
            ],
            "supporting_items": [
                {
                    "source_excerpt": "while blinking eyes",
                    "role": "constraint",
                    "coverage": "covered",
                    "independently_satisfiable": False,
                    "responsibility_refs": ["r1"],
                    "required_output_mode": "none",
                    "relation_kind": "parallel",
                    "related_audit_refs": ["a1", "a2"],
                }
            ],
            "reason_summary": "The first candidate merged two body effects.",
        }
        resegmented = {
            "confidence": 0.95,
            "responsibilities": [
                {
                    "local_ref": "a1",
                    "outcome": "run forward for 15 seconds",
                    "bindings": {"duration": 15},
                    "output_mode": "body_action",
                    "relationship": "new",
                    "target_goal_ids": [],
                    "confidence": 0.95,
                },
                {
                    "local_ref": "a2",
                    "outcome": "blink eyes while running",
                    "bindings": {},
                    "output_mode": "body_action",
                    "relationship": "new",
                    "target_goal_ids": [],
                    "confidence": 0.95,
                },
            ],
            "unresolved": [],
        }
        interpreter._chat = mock.AsyncMock(  # type: ignore[method-assign]
            side_effect=[
                {"message": {"content": json.dumps(split_audit)}},
                {"message": {"content": json.dumps(resegmented)}},
            ]
        )

        result = await interpreter._ensure_atomic_responsibility_coverage(
            GoalInterpretationRequest(
                text=(
                    "run forward for 15 seconds while blinking eyes, then sing a song"
                )
            ),
            decision,
        )

        self.assertEqual(
            [item.output_mode for item in result.responsibilities],
            ["body_action", "body_action", "singing"],
        )
        self.assertEqual(result.responsibilities[2].outcome, "sing a song")
        self.assertEqual(result.responsibilities[0].bindings["parallel_with"], ["a2"])
        self.assertEqual(result.responsibilities[1].bindings["parallel_with"], ["a1"])
        self.assertEqual(interpreter._chat.await_count, 2)

    async def test_hidden_concurrent_action_deepens_before_coverage(self) -> None:
        interpreter = self._interpreter()
        invalid = {
            "confidence": 0.9,
            "responsibilities": [
                {
                    "local_ref": "r1",
                    "outcome": "run forward for 15 seconds while blinking eyes",
                    "bindings": {
                        "duration": 15,
                        "concurrent_action": "blink_eyes",
                    },
                    "output_mode": "body_action",
                    "relationship": "new",
                    "target_goal_ids": [],
                    "confidence": 0.9,
                },
                {
                    "local_ref": "r2",
                    "outcome": "sing a song",
                    "bindings": {"capability": "sing"},
                    "output_mode": "singing",
                    "relationship": "new",
                    "target_goal_ids": [],
                    "confidence": 0.9,
                },
            ],
            "unresolved": [],
        }
        corrected = {
            "confidence": 0.95,
            "responsibilities": [
                {
                    "local_ref": "r1",
                    "outcome": "run forward for 15 seconds",
                    "bindings": {"duration": 15},
                    "output_mode": "body_action",
                    "relationship": "new",
                    "target_goal_ids": [],
                    "confidence": 0.95,
                },
                {
                    "local_ref": "r2",
                    "outcome": "blink eyes while running",
                    "bindings": {},
                    "output_mode": "body_action",
                    "relationship": "new",
                    "target_goal_ids": [],
                    "confidence": 0.95,
                },
                {
                    "local_ref": "r3",
                    "outcome": "sing a song",
                    "bindings": {},
                    "output_mode": "singing",
                    "relationship": "new",
                    "target_goal_ids": [],
                    "confidence": 0.95,
                },
            ],
            "unresolved": [],
        }
        coverage = {
            "independent_outcome_count": 3,
            "responsibility_items": [
                {
                    "source_excerpt": "往前跑个15秒",
                    "audit_ref": "a1",
                    "role": "responsibility",
                    "coverage": "covered",
                    "independently_satisfiable": True,
                    "responsibility_refs": ["r1"],
                    "required_output_mode": "body_action",
                },
                {
                    "source_excerpt": "眨眼睛",
                    "audit_ref": "a2",
                    "role": "responsibility",
                    "coverage": "covered",
                    "independently_satisfiable": True,
                    "responsibility_refs": ["r2"],
                    "required_output_mode": "body_action",
                },
                {
                    "source_excerpt": "唱个歌",
                    "audit_ref": "a3",
                    "role": "responsibility",
                    "coverage": "covered",
                    "independently_satisfiable": True,
                    "responsibility_refs": ["r3"],
                    "required_output_mode": "singing",
                },
            ],
            "supporting_items": [],
            "reason_summary": "Three observable effects are independently covered.",
        }
        interpreter._chat = mock.AsyncMock(  # type: ignore[method-assign]
            side_effect=[
                {"message": {"content": json.dumps(invalid)}},
                {"message": {"content": json.dumps(corrected)}},
                {"message": {"content": json.dumps(coverage)}},
            ]
        )

        result = await interpreter.interpret_goal(
            GoalInterpretationRequest(
                text="你给我往前跑个15秒，边跑边眨眼睛，能唱歌，你给我唱个歌。",
                language="zh-CN",
            )
        )

        self.assertEqual(len(result.responsibilities), 3)
        deep_binding_schema = interpreter._chat.await_args_list[1].args[0][
            "format"
        ]["$defs"]["CognitiveResponsibilityProposal"]["properties"]["bindings"]
        self.assertFalse(deep_binding_schema["additionalProperties"])
        self.assertEqual(
            set(deep_binding_schema["properties"]),
            {"before", "after", "parallel_with", "location", "duration"},
        )
        self.assertEqual(
            interpreter._chat.await_args_list[1].args[0]["format"]["properties"]
            ["responsibilities"]["minItems"],
            3,
        )
        self.assertEqual(
            [call.kwargs["stage"] for call in interpreter._chat.await_args_list],
            [
                "goal_interpretation",
                "goal_interpretation_deep",
                "goal_interpretation_responsibility_coverage",
            ],
        )

    def test_dynamic_schema_forbids_common_hidden_effect_binding_names(self) -> None:
        payload = self._interpreter().build_interpretation_payload(
            GoalInterpretationRequest(text="walk and blink")
        )
        property_name_contract = payload["format"]["$defs"][
            "CognitiveResponsibilityProposal"
        ]["properties"]["bindings"]["propertyNames"]
        forbidden = set(property_name_contract["allOf"][1]["not"]["enum"])
        self.assertTrue(
            {"concurrent_action", "capability", "agent_skill"}.issubset(forbidden)
        )
        binding_properties = payload["format"]["$defs"][
            "CognitiveResponsibilityProposal"
        ]["properties"]["bindings"]["properties"]
        for forbidden_name in ("action", "concurrent_action", "capability"):
            self.assertEqual(
                binding_properties[forbidden_name]["const"],
                "__forbidden_hidden_effect_or_how_binding__",
            )

    async def test_interpret_goal_accepts_valid_what_only_output(self) -> None:
        interpreter = self._interpreter()
        interpreter._chat = mock.AsyncMock(  # type: ignore[method-assign]
            return_value={"message": {"content": json.dumps(_valid_output())}}
        )
        result = await interpreter.interpret_goal(
            GoalInterpretationRequest(text="What's the weather in Chongqing today?")
        )
        self.assertEqual(result.responsibilities[0].local_ref, "r1")
        self.assertEqual(result.responsibilities[0].output_mode, "information")
        self.assertEqual(interpreter._chat.await_count, 1)

    async def test_provider_key_value_bindings_are_mechanically_normalized(self) -> None:
        interpreter = self._interpreter()
        output = {
            "responsibilities": [
                {
                    "local_ref": "r1",
                    "outcome": "move forward for ten seconds",
                    "bindings": [
                        {"name": "direction", "value": "forward"},
                        {"key": "duration", "value": "10 秒"},
                    ],
                    "output_mode": "body_action",
                    "relationship": "new",
                    "target_goal_ids": [],
                    "confidence": 0.95,
                }
            ],
            "unresolved": [],
        }
        interpreter._chat = mock.AsyncMock(  # type: ignore[method-assign]
            side_effect=[
                {"message": {"content": json.dumps(output)}},
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "responsibility_items": [
                                    {
                                        "source_excerpt": "你往前走 10 秒。",
                                        "role": "responsibility",
                                        "coverage": "covered",
                                        "independently_satisfiable": True,
                                        "responsibility_refs": ["r1"],
                                        "required_output_mode": "body_action",
                                    }
                                ],
                                "supporting_items": [],
                                "reason_summary": "The requested motion has one owner.",
                            },
                            ensure_ascii=False,
                        )
                    }
                },
            ]
        )

        result = await interpreter.interpret_goal(
            GoalInterpretationRequest(text="你往前走 10 秒。", language="zh-CN")
        )

        self.assertEqual(result.confidence, 0.95)
        self.assertEqual(
            result.responsibilities[0].bindings,
            {"direction": "forward", "duration": "10 秒"},
        )
        self.assertEqual(interpreter._chat.await_count, 2)

    async def test_rewritten_explicit_number_escalates_once_from_source(self) -> None:
        interpreter = self._interpreter()
        invalid = {
            "responsibilities": [
                {
                    "local_ref": "r1",
                    "outcome": "move forward for ten seconds",
                    "bindings": [
                        {"name": "direction", "value": "forward"},
                        {"name": "duration", "value": "ten seconds"},
                    ],
                    "output_mode": "body_action",
                    "relationship": "new",
                    "target_goal_ids": [],
                    "confidence": 0.95,
                }
            ],
            "unresolved": [],
        }
        repaired = copy.deepcopy(invalid)
        repaired["responsibilities"][0]["bindings"][1]["value"] = "10 秒"
        interpreter._chat = mock.AsyncMock(  # type: ignore[method-assign]
            side_effect=[
                {"message": {"content": json.dumps(invalid)}},
                {"message": {"content": json.dumps(repaired)}},
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "responsibility_items": [
                                    {
                                        "source_excerpt": "你往前走 10 秒。",
                                        "role": "responsibility",
                                        "coverage": "covered",
                                        "independently_satisfiable": True,
                                        "responsibility_refs": ["r1"],
                                        "required_output_mode": "body_action",
                                    }
                                ],
                                "supporting_items": [],
                                "reason_summary": "The requested motion has one owner.",
                            },
                            ensure_ascii=False,
                        )
                    }
                },
            ]
        )

        result = await interpreter.interpret_goal(
            GoalInterpretationRequest(text="你往前走 10 秒。", language="zh-CN")
        )

        self.assertEqual(result.responsibilities[0].bindings["duration"], "10 秒")
        self.assertEqual(interpreter._chat.await_count, 3)
        self.assertEqual(
            interpreter._chat.await_args_list[1].kwargs["stage"],
            "goal_interpretation_deep",
        )
        deep_payload = interpreter._chat.await_args_list[1].args[0]
        system_text, user_text, _all_text = _payload_message_texts(deep_payload)
        self.assertIn("Audit declarative context before counting outcomes", system_text)
        self.assertIn("states a future plan is context", system_text)

    async def test_numeric_source_recovery_can_add_missing_typed_dimension(self) -> None:
        interpreter = self._interpreter()
        invalid = {
            "confidence": 0.95,
            "responsibilities": [
                {
                    "local_ref": "r1",
                    "outcome": "move forward for 10 seconds",
                    "bindings": {"location": "你往前走 10 秒。"},
                    "output_mode": "body_action",
                    "confidence": 0.95,
                }
            ],
            "unresolved": [],
        }
        recovered = copy.deepcopy(invalid)
        recovered["responsibilities"][0]["bindings"] = {
            "location": "往前",
            "duration": 10,
        }
        interpreter._chat = mock.AsyncMock(  # type: ignore[method-assign]
            side_effect=[
                {"message": {"content": json.dumps(invalid, ensure_ascii=False)}},
                {"message": {"content": json.dumps(recovered, ensure_ascii=False)}},
            ]
        )
        interpreter._ensure_atomic_responsibility_coverage = mock.AsyncMock(  # type: ignore[method-assign]
            side_effect=lambda _request, decision, **_kwargs: decision
        )

        result = await interpreter.interpret_goal(
            GoalInterpretationRequest(text="你往前走 10 秒。", language="zh-CN")
        )

        self.assertEqual(
            result.responsibilities[0].bindings,
            {"location": "往前", "duration": 10},
        )
        deep_payload = interpreter._chat.await_args_list[1].args[0]
        binding_contract = deep_payload["format"]["$defs"][
            "CognitiveResponsibilityProposal"
        ]["properties"]["bindings"]
        self.assertIn("duration", binding_contract["properties"])
        self.assertNotEqual(binding_contract.get("additionalProperties"), False)

    async def test_transport_echo_uses_atomic_audit_before_fresh_resegmentation(self) -> None:
        interpreter = self._interpreter()
        invalid = {
            "confidence": 0.95,
            "responsibilities": [
                {
                    "local_ref": "r1",
                    "outcome": "sing while walking",
                    "bindings": {"location": "边走边唱歌。"},
                    "output_mode": "singing",
                    "confidence": 0.95,
                }
            ],
            "unresolved": [],
        }
        certificate = {
            "responsibility_items": [
                {
                    "audit_ref": "a1",
                    "source_excerpt": "走",
                    "role": "responsibility",
                    "coverage": "covered",
                    "independently_satisfiable": True,
                    "responsibility_refs": ["r1"],
                    "required_output_mode": "body_action",
                },
                {
                    "audit_ref": "a2",
                    "source_excerpt": "唱歌",
                    "role": "responsibility",
                    "coverage": "covered",
                    "independently_satisfiable": True,
                    "responsibility_refs": ["r1"],
                    "required_output_mode": "singing",
                },
            ],
            "supporting_items": [
                {
                    "source_excerpt": "边走边",
                    "role": "constraint",
                    "coverage": "covered",
                    "independently_satisfiable": False,
                    "responsibility_refs": ["r1"],
                    "required_output_mode": "none",
                    "relation_kind": "parallel",
                    "related_audit_refs": ["a1", "a2"],
                }
            ],
            "reason_summary": "Walking and singing are independent parallel effects.",
        }
        resegmented = {
            "confidence": 0.98,
            "responsibilities": [
                {
                    "local_ref": "a1",
                    "outcome": "walk",
                    "bindings": {},
                    "output_mode": "body_action",
                    "confidence": 0.98,
                },
                {
                    "local_ref": "a2",
                    "outcome": "sing a song",
                    "bindings": {},
                    "output_mode": "singing",
                    "confidence": 0.98,
                },
            ],
            "unresolved": [],
        }
        interpreter._chat = mock.AsyncMock(  # type: ignore[method-assign]
            side_effect=[
                {"message": {"content": json.dumps(invalid, ensure_ascii=False)}},
                {"message": {"content": json.dumps(certificate, ensure_ascii=False)}},
                {"message": {"content": json.dumps(resegmented, ensure_ascii=False)}},
            ]
        )

        result = await interpreter.interpret_goal(
            GoalInterpretationRequest(text="边走边唱歌。", language="zh-CN")
        )

        self.assertEqual(
            [item.output_mode for item in result.responsibilities],
            ["body_action", "singing"],
        )
        self.assertEqual(
            result.responsibilities[0].bindings["parallel_with"], ["a2"]
        )
        self.assertEqual(
            result.responsibilities[1].bindings["parallel_with"], ["a1"]
        )
        self.assertEqual(
            [call.kwargs["stage"] for call in interpreter._chat.await_args_list],
            [
                "goal_interpretation",
                "goal_interpretation_responsibility_coverage",
                "goal_interpretation_deep",
            ],
        )

    def test_body_action_remains_a_what_modality_not_readiness(self) -> None:
        responsibility = CognitiveResponsibilityProposal.model_validate(
            {
                "local_ref": "walk",
                "outcome": "move forward for ten seconds",
                "bindings": {"duration": "10 seconds"},
                "output_mode": "body_action",
                "confidence": 0.95,
            }
        )
        self.assertEqual(responsibility.output_mode, "body_action")
        self.assertNotIn("completion_requires_fresh_evidence", type(responsibility).model_fields)

    async def test_continuation_cannot_turn_retained_body_work_into_speech(self) -> None:
        interpreter = self._interpreter()
        wrong = {
            "confidence": 0.95,
            "responsibilities": [
                {
                    "local_ref": "r1",
                    "outcome": "continue the previous action",
                    "bindings": {"previous_action": "你往前走 10 秒。"},
                    "output_mode": "speech",
                    "relationship": "continue",
                    "target_goal_ids": ["goal-walk"],
                    "confidence": 0.95,
                }
            ],
            "unresolved": [],
        }
        corrected = copy.deepcopy(wrong)
        corrected["responsibilities"][0]["output_mode"] = "body_action"
        interpreter._chat = mock.AsyncMock(  # type: ignore[method-assign]
            side_effect=[
                {"message": {"content": json.dumps(wrong, ensure_ascii=False)}},
                {
                    "message": {
                        "content": json.dumps(corrected, ensure_ascii=False)
                    }
                },
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "responsibility_items": [
                                    {
                                        "source_excerpt": "刚才那个事情继续。",
                                        "role": "responsibility",
                                        "coverage": "covered",
                                        "independently_satisfiable": True,
                                        "responsibility_refs": ["r1"],
                                        "required_output_mode": "body_action",
                                    }
                                ],
                                "supporting_items": [],
                                "reason_summary": "The continuation preserves one body action.",
                            },
                            ensure_ascii=False,
                        )
                    }
                },
            ]
        )
        request = GoalInterpretationRequest(
            sid="continue-walk",
            text="刚才那个事情继续。",
            language="zh-CN",
            context={
                "active_goal_snapshots": [
                    {
                        "goal_id": "goal-walk",
                        "goal": {
                            "goal_id": "goal-walk",
                            "description": "move forward 10 seconds",
                            "metadata": {
                                "output_mode": "body_action",
                            },
                        },
                    }
                ]
            },
        )

        result = await interpreter.interpret_goal(request)

        responsibility = result.responsibilities[0]
        self.assertEqual(responsibility.output_mode, "body_action")
        self.assertEqual(interpreter._chat.await_count, 3)
        self.assertEqual(
            interpreter._chat.await_args_list[1].kwargs["stage"],
            "goal_interpretation_deep",
        )

    async def test_bundle_beijing_translation_escalates_from_source(self) -> None:
        interpreter = self._interpreter()
        translated = {
            **_valid_output(),
            "responsibilities": [
                {
                    **_valid_output()["responsibilities"][0],
                    "outcome": "determine whether it will rain in Beijing tomorrow",
                    "bindings": {"location": "Beijing", "date": "tomorrow"},
                }
            ],
        }
        corrected = {
            **translated,
            "responsibilities": [
                {
                    **translated["responsibilities"][0],
                    "bindings": {"location": "北京", "date": "tomorrow"},
                }
            ],
        }
        interpreter._chat = mock.AsyncMock(  # type: ignore[method-assign]
            side_effect=[
                {"message": {"content": json.dumps(translated)}},
                {"message": {"content": json.dumps(corrected, ensure_ascii=False)}},
            ]
        )
        result = await interpreter.interpret_goal(
            GoalInterpretationRequest(
                text="明天北京下雨吗？我明天要去北京出差。",
                language="zh-CN",
            )
        )
        self.assertEqual(result.responsibilities[0].bindings["location"], "北京")
        self.assertEqual(interpreter._chat.await_count, 2)
        self.assertEqual(
            interpreter._chat.await_args_list[1].kwargs["stage"],
            "goal_interpretation_deep",
        )
        deep_payload = interpreter._chat.await_args_list[1].args[0]
        _system_text, user_text, all_text = _payload_message_texts(deep_payload)
        self.assertIn("No prior interpretation DTO is supplied", user_text)
        self.assertNotIn(json.dumps(translated), all_text)
        responsibility_contract = deep_payload["format"]["$defs"][
            "CognitiveResponsibilityProposal"
        ]
        location_contract = responsibility_contract["properties"]["bindings"]["properties"][
            "location"
        ]
        self.assertIn("北京", location_contract["enum"])
        self.assertNotIn("Beijing", location_contract["enum"])

    async def test_planned_deep_location_translation_gets_one_constrained_dto_repair(self) -> None:
        interpreter = self._interpreter()
        initial = {
            **_valid_output(),
            "responsibilities": [
                {
                    **_valid_output()["responsibilities"][0],
                    "outcome": "今天晚上重庆热不热？",
                    "bindings": {"location": "重庆", "time": "tonight"},
                    "output_mode": "information",
                }
            ],
            "unresolved": ["The changing answer needs external evidence."],
        }
        translated = {
            **initial,
            "responsibilities": [
                {
                    **initial["responsibilities"][0],
                    "bindings": {"location": "Chongqing", "time": "tonight"},
                }
            ],
            "unresolved": [],
        }
        corrected = {
            **translated,
            "responsibilities": [
                {
                    **translated["responsibilities"][0],
                    "bindings": {"location": "重庆", "time": "tonight"},
                }
            ],
        }
        interpreter._chat = mock.AsyncMock(  # type: ignore[method-assign]
            side_effect=[
                {"message": {"content": json.dumps(initial, ensure_ascii=False)}},
                {"message": {"content": json.dumps(translated, ensure_ascii=False)}},
                {"message": {"content": json.dumps(corrected, ensure_ascii=False)}},
            ]
        )

        result = await interpreter.interpret_goal(
            GoalInterpretationRequest(
                text="今天晚上重庆热不热？",
                language="zh-CN",
            )
        )

        self.assertEqual(result.responsibilities[0].bindings["location"], "重庆")
        self.assertEqual(interpreter._chat.await_count, 3)
        self.assertEqual(
            interpreter._chat.await_args_list[2].kwargs["stage"],
            "goal_interpretation_deep_contract_repair",
        )
        repair_schema = interpreter._chat.await_args_list[2].args[0]["format"]
        location_contract = repair_schema["$defs"]["CognitiveResponsibilityProposal"][
            "properties"
        ]["bindings"]["properties"]["location"]
        self.assertIn("重庆", location_contract["enum"])
        self.assertNotIn("Chongqing", location_contract["enum"])
        binding_contract = repair_schema["$defs"]["CognitiveResponsibilityProposal"][
            "properties"
        ]["bindings"]
        self.assertEqual(
            binding_contract["propertyNames"]["allOf"][-1]["anyOf"][0],
            {"const": "location"},
        )

    async def test_location_alias_cannot_escape_surface_provenance(self) -> None:
        interpreter = self._interpreter()
        aliased = {
            **_valid_output(),
            "responsibilities": [
                {
                    **_valid_output()["responsibilities"][0],
                    "outcome": "determine whether people are outside",
                    "bindings": {
                        "location_scope": "outside",
                        "question_type": "presence_inquiry",
                    },
                }
            ],
        }
        corrected = {
            **aliased,
            "responsibilities": [
                {
                    **aliased["responsibilities"][0],
                    "bindings": {
                        "location": "外面",
                        "question_type": "presence_inquiry",
                    },
                }
            ],
        }
        interpreter._chat = mock.AsyncMock(  # type: ignore[method-assign]
            side_effect=[
                {"message": {"content": json.dumps(aliased)}},
                {"message": {"content": json.dumps(corrected, ensure_ascii=False)}},
            ]
        )

        result = await interpreter.interpret_goal(
            GoalInterpretationRequest(text="你觉得外面有人吗？", language="zh-CN")
        )

        self.assertEqual(result.responsibilities[0].bindings["location"], "外面")
        self.assertNotIn("location_scope", result.responsibilities[0].bindings)
        self.assertEqual(interpreter._chat.await_count, 2)
        deep_payload = interpreter._chat.await_args_list[1].args[0]
        system_text, user_text, _all_text = _payload_message_texts(deep_payload)
        self.assertIn("canonical binding name `location`", system_text)
        self.assertIn("deictic locations remain exact current-turn surfaces", user_text)

    def test_location_direction_is_not_misclassified_as_location_alias(self) -> None:
        parsed = {
            **_valid_output(),
            "responsibilities": [
                {
                    **_valid_output()["responsibilities"][0],
                    "outcome": "run forward",
                    "bindings": {"location_direction": "forward"},
                }
            ],
        }

        _reject_unprovenanced_location_bindings(
            GoalInterpretationRequest(text="run forward", language="en"),
            parsed,
        )

    async def test_independent_coverage_removes_unrequested_information_responsibility(self) -> None:
        interpreter = self._interpreter()
        weather = _valid_output()
        oversegmented = {
            **weather,
            "responsibilities": [
                weather["responsibilities"][0],
                {
                    **weather["responsibilities"][0],
                    "local_ref": "r2",
                    "outcome": "confirm the user's travel plan",
                },
            ],
        }
        corrected = {
            **weather,
            "responsibilities": [
                {**weather["responsibilities"][0], "local_ref": "a1"}
            ],
        }
        interpreter._chat = mock.AsyncMock(  # type: ignore[method-assign]
            side_effect=[
                {"message": {"content": json.dumps(oversegmented)}},
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "responsibility_items": [
                                    {
                                        "source_excerpt": "Will it rain in Chongqing tomorrow?",
                                        "role": "responsibility",
                                        "coverage": "covered",
                                        "independently_satisfiable": True,
                                        "responsibility_refs": ["r1"],
                                        "required_output_mode": "information",
                                    }
                                ],
                                "supporting_items": [
                                    {
                                        "source_excerpt": "I am traveling for work.",
                                        "role": "context",
                                        "coverage": "covered",
                                        "independently_satisfiable": False,
                                        "responsibility_refs": [],
                                        "required_output_mode": "none",
                                    }
                                ],
                                "reason_summary": "The travel statement is context only.",
                            }
                        )
                    }
                },
                {"message": {"content": json.dumps(corrected)}},
            ]
        )

        result = await interpreter.interpret_goal(
            GoalInterpretationRequest(
                text="Will it rain in Chongqing tomorrow? I am traveling for work.",
                language="en-US",
            )
        )

        self.assertEqual(len(result.responsibilities), 1)
        self.assertEqual(interpreter._chat.await_count, 3)

    async def test_planner_gap_fields_escalate_once_from_source(self) -> None:
        interpreter = self._interpreter()
        invalid = {
            "confidence": 0.95,
            "responsibilities": [
                {
                    "local_ref": "weather",
                    "outcome": "report today's daytime weather in Chongqing",
                    "bindings": {
                        "location": "重庆",
                        "date": "today",
                        "time_of_day": "白天",
                    },
                    "relationship": "new",
                    "target_goal_ids": [],
                    "information_gaps": [
                        {
                            "gap_id": "weather_result",
                            "description": "The current weather result is not known yet.",
                            "blocking": True,
                            "required_for": ["weather data for Chongqing"],
                            "preferred_resolution": "ask_user",
                            "candidate_values": [],
                            "resolved": False,
                            "resolution_value": None,
                            "metadata": {},
                        }
                    ],
                    "resolved_gap_ids": [],
                    "confidence": 0.95,
                }
            ],
            "unresolved": ["The current weather result is not known yet."],
        }
        corrected = {
            "confidence": 0.95,
            "responsibilities": [
                {
                    "local_ref": "weather",
                    "outcome": "report today's daytime weather in Chongqing",
                    "bindings": {
                        "location": "重庆",
                        "date": "today",
                        "time_of_day": "白天",
                    },
                    "relationship": "new",
                    "target_goal_ids": [],
                    "output_mode": "information",
                    "confidence": 0.95,
                }
            ],
            "unresolved": [],
        }
        interpreter._chat = mock.AsyncMock(  # type: ignore[method-assign]
            side_effect=[
                {"message": {"content": json.dumps(invalid, ensure_ascii=False)}},
                {"message": {"content": json.dumps(corrected, ensure_ascii=False)}},
            ]
        )

        result = await interpreter.interpret_goal(
            GoalInterpretationRequest(
                text="你好，今天重庆白天天气怎么样啊？",
                language="zh-CN",
            )
        )

        responsibility = result.responsibilities[0]
        self.assertFalse(hasattr(responsibility, "information_gaps"))
        self.assertEqual(responsibility.output_mode, "information")
        self.assertEqual(interpreter._chat.await_count, 2)
        self.assertEqual(
            interpreter._chat.await_args_list[1].kwargs["stage"],
            "goal_interpretation_deep",
        )

    async def test_genuine_semantic_ambiguity_escalates_once_to_deep(self) -> None:
        interpreter = self._interpreter()
        fast = {
            "confidence": 0.72,
            "responsibilities": [
                {
                    "local_ref": "device_action",
                    "outcome": "turn off the referenced device",
                    "bindings": {},
                    "confidence": 0.72,
                }
            ],
            "unresolved": ["which device the user means"],
        }
        interpreter._chat = mock.AsyncMock(  # type: ignore[method-assign]
            side_effect=[
                {"message": {"content": json.dumps(fast, ensure_ascii=False)}},
                {"message": {"content": json.dumps(fast, ensure_ascii=False)}},
            ]
        )

        result = await interpreter.interpret_goal(
            GoalInterpretationRequest(
                text="把它关掉。",
                language="zh-CN",
            )
        )

        self.assertFalse(hasattr(result.responsibilities[0], "information_gaps"))
        self.assertEqual(result.unresolved, ["which device the user means"])
        self.assertEqual(interpreter._chat.await_count, 2)
        deep_call = interpreter._chat.await_args_list[1]
        self.assertEqual(deep_call.kwargs["stage"], "goal_interpretation_deep")
        self.assertFalse(deep_call.args[0]["think"])

    async def test_missing_execution_location_stays_out_of_gi_uncertainty(self) -> None:
        interpreter = self._interpreter()
        missing_location = {
            "confidence": 0.9,
            "responsibilities": [
                {
                    "local_ref": "weather",
                    "outcome": "provide today's weather for the requested location",
                    "bindings": {"date": "today"},
                    "confidence": 0.9,
                }
            ],
            "unresolved": [],
        }
        interpreter._chat = mock.AsyncMock(  # type: ignore[method-assign]
            return_value={"message": {"content": json.dumps(missing_location)}}
        )

        result = await interpreter.interpret_goal(
            GoalInterpretationRequest(text="What's the weather today?")
        )

        self.assertFalse(hasattr(result.responsibilities[0], "information_gaps"))
        self.assertEqual(result.unresolved, [])
        self.assertEqual(interpreter._chat.await_count, 1)

    async def test_external_query_gap_cannot_be_repeated_as_semantic_uncertainty(self) -> None:
        interpreter = self._interpreter()
        invalid = {
            "confidence": 0.95,
            "responsibilities": [
                {
                    "local_ref": "r1",
                    "outcome": "determine whether Chongqing is sunny today",
                    "bindings": {
                        "location": "重庆",
                        "time": "today",
                        "time_of_day": "daytime",
                    },
                    "relationship": "new",
                    "target_goal_ids": [],
                    "information_gaps": [
                        {
                            "gap_id": "info_gap_1",
                            "description": "current weather data for Chongqing",
                            "preferred_resolution": "query_trusted_service",
                        }
                    ],
                    "resolved_gap_ids": [],
                    "confidence": 0.95,
                }
            ],
            "unresolved": ["current weather data for Chongqing"],
        }
        corrected = {
            "confidence": 0.95,
            "responsibilities": [
                {
                    "local_ref": "r1",
                    "outcome": "describe today's daytime weather in Chongqing",
                    "bindings": {
                        "location": "重庆",
                        "time": "today",
                        "time_of_day": "daytime",
                    },
                    "relationship": "new",
                    "target_goal_ids": [],
                    "confidence": 0.95,
                }
            ],
            "unresolved": [],
        }
        interpreter._chat = mock.AsyncMock(  # type: ignore[method-assign]
            side_effect=[
                {"message": {"content": json.dumps(invalid, ensure_ascii=False)}},
                {"message": {"content": json.dumps(corrected, ensure_ascii=False)}},
            ]
        )

        result = await interpreter.interpret_goal(
            GoalInterpretationRequest(
                text="你好，今天重庆白天天气怎么样啊？",
                language="zh-CN",
            )
        )

        self.assertEqual(
            result.responsibilities[0].outcome,
            "describe today's daytime weather in Chongqing",
        )
        self.assertEqual(result.unresolved, [])
        self.assertEqual(interpreter._chat.await_count, 2)
        self.assertEqual(
            interpreter._chat.await_args_list[1].kwargs["stage"],
            "goal_interpretation_deep",
        )
        deep_payload = interpreter._chat.await_args_list[1].args[0]
        self.assertNotIn("InformationGap", deep_payload["format"]["$defs"])
        system_text, _, _ = _payload_message_texts(deep_payload)
        self.assertIn("Do not create or resolve an InformationGap", system_text)

    async def test_context_backed_indirect_location_does_not_require_current_turn_surface(self) -> None:
        interpreter = self._interpreter()
        contextual = _valid_output()
        interpreter._chat = mock.AsyncMock(  # type: ignore[method-assign]
            return_value={"message": {"content": json.dumps(contextual)}}
        )
        result = await interpreter.interpret_goal(
            GoalInterpretationRequest(
                text="那里今天会下雨吗？",
                language="zh-CN",
                context={
                    "discourse_referents": [
                        {"entity_type": "location", "canonical_value": "Chongqing"}
                    ]
                },
            )
        )
        self.assertEqual(result.responsibilities[0].bindings["location"], "Chongqing")
        self.assertEqual(interpreter._chat.await_count, 1)

    async def test_runtime_session_identity_in_binding_escalates_from_source(self) -> None:
        interpreter = self._interpreter()
        invalid = {
            **_valid_output(),
            "responsibilities": [
                {
                    **_valid_output()["responsibilities"][0],
                    "outcome": "determine whether the washing machine finished",
                    "bindings": {
                        "device": "washing machine",
                        "cycle": "turn-correlation-123",
                    },
                }
            ],
        }
        corrected = {
            **invalid,
            "responsibilities": [
                {
                    **invalid["responsibilities"][0],
                    "bindings": {"device": "washing machine"},
                }
            ],
        }
        interpreter._chat = mock.AsyncMock(  # type: ignore[method-assign]
            side_effect=[
                {"message": {"content": json.dumps(invalid)}},
                {"message": {"content": json.dumps(corrected)}},
            ]
        )

        result = await interpreter.interpret_goal(
            GoalInterpretationRequest(
                sid="turn-correlation-123",
                text="Has the washing machine finished?",
            )
        )

        self.assertEqual(
            result.responsibilities[0].bindings,
            {"device": "washing machine"},
        )
        self.assertEqual(interpreter._chat.await_count, 2)
        self.assertEqual(
            interpreter._chat.await_args_list[1].kwargs["stage"],
            "goal_interpretation_deep",
        )

    async def test_request_language_echo_is_stripped_without_deep_escalation(self) -> None:
        interpreter = self._interpreter()
        greeting = {
            "confidence": 0.95,
            "responsibilities": [
                {
                    "local_ref": "greeting",
                    "outcome": "respond naturally to the greeting",
                    "bindings": {"language": "zh-CN"},
                    "confidence": 0.95,
                }
            ],
            "unresolved": [],
        }
        interpreter._chat = mock.AsyncMock(  # type: ignore[method-assign]
            return_value={
                "message": {"content": json.dumps(greeting, ensure_ascii=False)}
            }
        )

        result = await interpreter.interpret_goal(
            GoalInterpretationRequest(text="你好。", language="zh-CN")
        )

        self.assertEqual(result.responsibilities[0].bindings, {})
        self.assertEqual(interpreter._chat.await_count, 1)
        self.assertEqual(
            interpreter._chat.await_args_list[0].kwargs["stage"],
            "goal_interpretation",
        )

    async def test_atomic_speech_turn_echo_is_stripped_without_deep_escalation(self) -> None:
        interpreter = self._interpreter()
        acknowledgement = {
            "confidence": 0.95,
            "responsibilities": [
                {
                    "local_ref": "reply",
                    "outcome": "respond to the user's acknowledgement",
                    "bindings": {"user_input": "Yeah."},
                    "output_mode": "speech",
                    "confidence": 0.95,
                }
            ],
            "unresolved": [],
        }
        interpreter._chat = mock.AsyncMock(  # type: ignore[method-assign]
            return_value={
                "message": {"content": json.dumps(acknowledgement, ensure_ascii=False)}
            }
        )

        result = await interpreter.interpret_goal(
            GoalInterpretationRequest(text="Yeah.", language="en-US")
        )

        self.assertEqual(result.responsibilities[0].bindings, {})
        self.assertEqual(result.responsibilities[0].output_mode, "speech")
        self.assertEqual(interpreter._chat.await_count, 1)

    async def test_single_exact_speech_echo_survives_isolated_audit_mode_dispute(self) -> None:
        interpreter = self._interpreter()
        exact_echo = {
            "confidence": 0.95,
            "responsibilities": [
                {
                    "local_ref": "reply",
                    "outcome": "Hello.",
                    "bindings": {},
                    "output_mode": "speech",
                    "confidence": 0.95,
                }
            ],
            "unresolved": [],
        }
        isolated_mode_dispute = {
            "responsibility_items": [
                {
                    "source_excerpt": "Hello",
                    "role": "responsibility",
                    "coverage": "covered",
                    "independently_satisfiable": True,
                    "responsibility_refs": ["reply"],
                    "required_output_mode": "singing",
                }
            ],
            "supporting_items": [],
            "reason_summary": "One source outcome was found.",
        }
        interpreter._chat = mock.AsyncMock(  # type: ignore[method-assign]
            side_effect=[
                {"message": {"content": json.dumps(exact_echo)}},
                {"message": {"content": json.dumps(isolated_mode_dispute)}},
            ]
        )

        result = await interpreter.interpret_goal(
            GoalInterpretationRequest(text="Hello.", language="en-US")
        )

        self.assertEqual(result.responsibilities[0].output_mode, "speech")
        self.assertEqual(interpreter._chat.await_count, 2)
        self.assertEqual(
            interpreter._chat.await_args_list[1].kwargs["stage"],
            "goal_interpretation_responsibility_coverage",
        )

    async def test_single_greeting_with_source_message_survives_audit_mode_dispute(self) -> None:
        interpreter = self._interpreter()
        greeting = {
            "confidence": 0.99,
            "responsibilities": [
                {
                    "local_ref": "reply",
                    "outcome": "respond to the user with a Chinese greeting",
                    "bindings": {"message": "你好"},
                    "output_mode": "speech",
                    "confidence": 0.99,
                }
            ],
            "unresolved": [],
        }
        isolated_mode_dispute = {
            "responsibility_items": [
                {
                    "source_excerpt": "你好",
                    "role": "responsibility",
                    "coverage": "covered",
                    "independently_satisfiable": True,
                    "responsibility_refs": ["reply"],
                    "required_output_mode": "singing",
                }
            ],
            "supporting_items": [],
            "reason_summary": "One conversational outcome was found.",
        }
        interpreter._chat = mock.AsyncMock(  # type: ignore[method-assign]
            side_effect=[
                {"message": {"content": json.dumps(greeting, ensure_ascii=False)}},
                {"message": {"content": json.dumps(isolated_mode_dispute)}},
            ]
        )

        result = await interpreter.interpret_goal(
            GoalInterpretationRequest(text="你好，Chromie。", language="zh-CN")
        )

        self.assertEqual(result.responsibilities[0].output_mode, "speech")
        self.assertEqual(result.responsibilities[0].bindings, {"message": "你好"})
        self.assertEqual(interpreter._chat.await_count, 2)

    async def test_transport_echo_bindings_escalate_once_from_source(self) -> None:
        interpreter = self._interpreter()
        invalid = {
            "confidence": 0.95,
            "responsibilities": [
                {
                    "local_ref": "combined",
                    "outcome": "walk while singing",
                    "bindings": {
                        "language": "zh-CN",
                        "text": "边走边唱歌",
                    },
                    "output_mode": "singing",
                    "confidence": 0.95,
                }
            ],
            "unresolved": [],
        }
        corrected = {
            "confidence": 0.95,
            "responsibilities": [
                {
                    "local_ref": "walk",
                    "outcome": "walk forward",
                    "bindings": {},
                    "output_mode": "body_action",
                    "confidence": 0.95,
                },
                {
                    "local_ref": "sing",
                    "outcome": "sing audibly while walking",
                    "bindings": {},
                    "output_mode": "singing",
                    "confidence": 0.95,
                },
            ],
            "unresolved": [],
        }
        interpreter._chat = mock.AsyncMock(  # type: ignore[method-assign]
            side_effect=[
                {"message": {"content": json.dumps(invalid, ensure_ascii=False)}},
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "responsibility_items": [
                                    {
                                        "audit_ref": "walk",
                                        "source_excerpt": "边走",
                                        "role": "responsibility",
                                        "coverage": "covered",
                                        "independently_satisfiable": True,
                                        "responsibility_refs": ["combined"],
                                        "required_output_mode": "body_action",
                                    },
                                    {
                                        "audit_ref": "sing",
                                        "source_excerpt": "唱歌",
                                        "role": "responsibility",
                                        "coverage": "covered",
                                        "independently_satisfiable": True,
                                        "responsibility_refs": ["combined"],
                                        "required_output_mode": "singing",
                                    },
                                ],
                                "supporting_items": [
                                    {
                                        "source_excerpt": "边走边",
                                        "role": "constraint",
                                        "coverage": "covered",
                                        "independently_satisfiable": False,
                                        "responsibility_refs": ["combined"],
                                        "required_output_mode": "none",
                                        "relation_kind": "parallel",
                                        "related_audit_refs": ["walk", "sing"],
                                    }
                                ],
                                "reason_summary": "Walking and singing are separately observable.",
                            },
                            ensure_ascii=False,
                        )
                    }
                },
                {"message": {"content": json.dumps(corrected, ensure_ascii=False)}},
            ]
        )

        result = await interpreter.interpret_goal(
            GoalInterpretationRequest(text="边走边唱歌。", language="zh-CN")
        )

        self.assertEqual(
            [item.local_ref for item in result.responsibilities],
            ["walk", "sing"],
        )
        self.assertEqual(interpreter._chat.await_count, 3)
        self.assertEqual(
            interpreter._chat.await_args_list[1].kwargs["stage"],
            "goal_interpretation_responsibility_coverage",
        )
        deep_call = interpreter._chat.await_args_list[2]
        self.assertEqual(deep_call.kwargs["stage"], "goal_interpretation_deep")
        self.assertIn("No prior interpretation DTO", deep_call.args[0]["messages"][1]["content"])

    async def test_free_form_coordination_effect_escalates_once_from_source(self) -> None:
        interpreter = self._interpreter()
        invalid = {
            "confidence": 0.95,
            "responsibilities": [
                {
                    "local_ref": "r1",
                    "outcome": "walk ahead",
                    "bindings": {},
                    "confidence": 0.95,
                },
                {
                    "local_ref": "r2",
                    "outcome": "sing simultaneously",
                    "bindings": {"simultaneously": "with blinking eyes"},
                    "confidence": 0.95,
                },
            ],
            "unresolved": [],
        }
        corrected = {
            "confidence": 0.95,
            "responsibilities": [
                {
                    "local_ref": "a1",
                    "outcome": "walk ahead",
                    "bindings": {"coordinate_with": ["a2", "a3"]},
                    "output_mode": "body_action",
                    "confidence": 0.95,
                },
                {
                    "local_ref": "a2",
                    "outcome": "sing",
                    "bindings": {"coordinate_with": ["a1", "a3"]},
                    "output_mode": "singing",
                    "confidence": 0.95,
                },
                {
                    "local_ref": "a3",
                    "outcome": "blink eyes",
                    "bindings": {"coordinate_with": ["a1", "a2"]},
                    "output_mode": "body_action",
                    "confidence": 0.95,
                },
            ],
            "unresolved": [],
        }
        interpreter._chat = mock.AsyncMock(  # type: ignore[method-assign]
            side_effect=[
                {"message": {"content": json.dumps(invalid)}},
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "responsibility_items": [
                                    {
                                        "source_excerpt": "walk ahead",
                                        "role": "responsibility",
                                        "coverage": "covered",
                                        "independently_satisfiable": True,
                                        "responsibility_refs": ["r1"],
                                        "required_output_mode": "body_action",
                                    },
                                    {
                                        "source_excerpt": "singing",
                                        "role": "responsibility",
                                        "coverage": "covered",
                                        "independently_satisfiable": True,
                                        "responsibility_refs": ["r2"],
                                        "required_output_mode": "singing",
                                    },
                                    {
                                        "source_excerpt": "blinking eyes",
                                        "role": "responsibility",
                                        "coverage": "covered",
                                        "independently_satisfiable": True,
                                        # The malformed candidate hid blinking
                                        # inside r2's relation wording, so the
                                        # source audit identifies an overmerge
                                        # against the existing owner.
                                        "responsibility_refs": ["r2"],
                                        "required_output_mode": "body_action",
                                    },
                                ],
                                "supporting_items": [],
                                "reason_summary": "All three effects are independently observable.",
                            }
                        )
                    }
                },
                {"message": {"content": json.dumps(corrected)}},
            ]
        )

        result = await interpreter.interpret_goal(
            GoalInterpretationRequest(
                text="walk ahead, singing and blinking eyes simultaneously"
            )
        )

        self.assertEqual(len(result.responsibilities), 3)
        self.assertEqual(interpreter._chat.await_count, 3)
        self.assertEqual(
            interpreter._chat.await_args_list[1].kwargs["stage"],
            "goal_interpretation_responsibility_coverage",
        )
        self.assertEqual(
            interpreter._chat.await_args_list[2].kwargs["stage"],
            "goal_interpretation_deep",
        )

    async def test_valid_atomic_compound_meaning_proceeds_without_deep_pass(self) -> None:
        interpreter = self._interpreter()
        primary = {
            "confidence": 0.95,
            "responsibilities": [
                {
                    "local_ref": "walk",
                    "outcome": "walk",
                    "bindings": {"parallel_with": "sing"},
                    "output_mode": "body_action",
                    "confidence": 0.95,
                },
                {
                    "local_ref": "sing",
                    "outcome": "sing",
                    "bindings": {},
                    "output_mode": "singing",
                    "confidence": 0.95,
                },
            ],
            "unresolved": [],
        }
        coverage = {
            "responsibility_items": [
                {
                    "source_excerpt": "walk",
                    "role": "responsibility",
                    "coverage": "covered",
                    "independently_satisfiable": True,
                    "responsibility_refs": ["walk"],
                    "required_output_mode": "body_action",
                },
                {
                    "source_excerpt": "sing",
                    "role": "responsibility",
                    "coverage": "covered",
                    "independently_satisfiable": True,
                    "responsibility_refs": ["sing"],
                    "required_output_mode": "singing",
                },
            ],
            "supporting_items": [
                {
                    "source_excerpt": "simultaneously",
                    "role": "constraint",
                    "coverage": "covered",
                    "independently_satisfiable": False,
                    "responsibility_refs": ["walk", "sing"],
                    "required_output_mode": "none",
                    "relation_kind": "parallel",
                }
            ],
            "reason_summary": "Both effects are independently represented.",
        }
        interpreter._chat = mock.AsyncMock(  # type: ignore[method-assign]
            side_effect=[
                {"message": {"content": json.dumps(primary)}},
                {"message": {"content": json.dumps(coverage)}},
            ]
        )

        result = await interpreter.interpret_goal(
            GoalInterpretationRequest(text="walk and sing simultaneously")
        )

        self.assertEqual(
            [item.output_mode for item in result.responsibilities],
            ["body_action", "singing"],
        )
        self.assertEqual(interpreter._chat.await_count, 2)
        self.assertEqual(
            interpreter._chat.await_args_list[1].kwargs["stage"],
            "goal_interpretation_responsibility_coverage",
        )

    def test_self_referential_action_combination_is_structural_loss(self) -> None:
        parsed = {
            "confidence": 0.95,
            "responsibilities": [
                {
                    "local_ref": "r1",
                    "outcome": "combined request",
                    "bindings": {"action_combination": ["r1"]},
                    "output_mode": "information",
                    "confidence": 0.95,
                }
            ],
            "unresolved": [],
        }
        with self.assertRaisesRegex(ValueError, "sibling local_ref"):
            _reject_untyped_coordination_bindings(parsed)

    def test_boolean_simultaneity_is_structural_when_siblings_are_atomic(self) -> None:
        parsed = {
            "confidence": 0.95,
            "responsibilities": [
                {
                    "local_ref": "walk",
                    "outcome": "walk forward",
                    "bindings": {"simultaneity": True},
                    "output_mode": "body_action",
                    "confidence": 0.95,
                },
                {
                    "local_ref": "blink",
                    "outcome": "blink twice",
                    "bindings": {"simultaneity": True, "count": 2},
                    "output_mode": "body_action",
                    "confidence": 0.95,
                },
            ],
            "unresolved": [],
        }

        _reject_untyped_coordination_bindings(parsed)

    async def test_route_output_escalates_once_from_source(self) -> None:
        interpreter = self._interpreter()
        invalid = {**_valid_output(), "route": "tool", "intent": "weather"}
        interpreter._chat = mock.AsyncMock(  # type: ignore[method-assign]
            side_effect=[
                {"message": {"content": json.dumps(invalid)}},
                {"message": {"content": json.dumps(_valid_output())}},
            ]
        )
        result = await interpreter.interpret_goal(
            GoalInterpretationRequest(text="What's the weather in Chongqing today?")
        )
        self.assertEqual(result.responsibilities[0].outcome, "provide today's weather for Chongqing")
        self.assertEqual(interpreter._chat.await_count, 2)
        self.assertEqual(
            interpreter._chat.await_args_list[1].kwargs["stage"],
            "goal_interpretation_deep",
        )

    async def test_invalid_authority_output_after_deep_pass_is_unavailable(self) -> None:
        interpreter = self._interpreter()
        invalid = {**_valid_output(), "route": "tool"}
        interpreter._chat = mock.AsyncMock(  # type: ignore[method-assign]
            return_value={"message": {"content": json.dumps(invalid)}}
        )
        with self.assertRaises(InterpretationUnavailableError):
            await interpreter.interpret_goal(
                GoalInterpretationRequest(text="What's the weather today?")
            )
        self.assertEqual(interpreter._chat.await_count, 2)

    async def test_llm_budget_failure_is_typed_interpretation_unavailable(self) -> None:
        interpreter = self._interpreter()
        interpreter._chat = mock.AsyncMock(  # type: ignore[method-assign]
            side_effect=OllamaGenerationError(
                "structured output budget exhausted",
                failure_class="output_truncated",
                failure_domain="llm_budget",
                architecture_attribution="not_evaluated",
                retryable=False,
            )
        )

        with self.assertRaisesRegex(
            InterpretationUnavailableError,
            "structured output budget exhausted",
        ):
            await interpreter.interpret_goal(
                GoalInterpretationRequest(text="What's the weather today?")
            )
        self.assertEqual(interpreter._chat.await_count, 1)

    async def test_engine_rejects_empty_admitted_input(self) -> None:
        with self.assertRaisesRegex(InterpretationUnavailableError, "empty admitted input"):
            await interpret_goal(GoalInterpretationRequest(text="   "))
