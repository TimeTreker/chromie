from __future__ import annotations

from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import Any, Literal, Mapping

AbilityStatus = Literal[
    "available",
    "stub",
    "planned",
    "known_missing",
    "forbidden",
    "disabled",
]

@dataclass(frozen=True)
class AbilitySpec:
    ability_id: str
    category: str
    description: str
    status: AbilityStatus = "stub"
    implementation: str = "stub"
    optional_by_default: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def can_execute(self) -> bool:
        return self.status == "available" and self.implementation != "stub"

    def with_updates(self, **updates: Any) -> "AbilitySpec":
        return replace(self, **updates)


class AbilityRegistry:
    def __init__(self, abilities: list[AbilitySpec]) -> None:
        indexed: dict[str, AbilitySpec] = {}
        for ability in abilities:
            if ability.ability_id in indexed:
                raise ValueError(f"duplicate ability_id: {ability.ability_id}")
            indexed[ability.ability_id] = ability
        self._abilities = MappingProxyType(indexed)

    def get(self, ability_id: str) -> AbilitySpec:
        try:
            return self._abilities[ability_id]
        except KeyError as exc:
            raise ValueError(f"unknown ability {ability_id!r}") from exc

    def list(self) -> list[AbilitySpec]:
        return [self._abilities[ability_id] for ability_id in sorted(self._abilities)]

    def by_category(self, category: str) -> list[AbilitySpec]:
        return [
            ability
            for ability in self.list()
            if ability.category == category
        ]

    def can_execute(self, ability_id: str) -> bool:
        return self.get(ability_id).can_execute



def build_default_ability_registry(
    *,
    enable_agent: bool = True,
) -> AbilityRegistry:
    """Build Chromie's static cognitive ability inventory.

    Embodied skills are intentionally not activated here. Their availability,
    confirmation policy, and execution contract come from the live provider
    catalog and are validated by Trusted Capability Runtime. The static registry therefore
    cannot infer body capability from simulator, hardware, or dry-run settings.
    """

    abilities = _base_abilities()

    _set_status(
        abilities,
        "cognition.deep_think",
        status="available" if enable_agent else "disabled",
        implementation="deepthinking_agent" if enable_agent else "disabled",
    )
    _set_status(
        abilities,
        "cognition.plan_task",
        status="available" if enable_agent else "disabled",
        implementation="deepthinking_agent" if enable_agent else "disabled",
    )
    _set_status(
        abilities,
        "cognition.split_task",
        status="available" if enable_agent else "disabled",
        implementation="deepthinking_agent" if enable_agent else "disabled",
    )

    return AbilityRegistry(list(abilities.values()))


def _base_abilities() -> dict[str, AbilitySpec]:
    specs = [
        AbilitySpec(
            "cognition.interpret_turn",
            "cognition",
            "Interpret the current turn into a bounded cognitive decision.",
            status="available",
            implementation="goal_interpreter",
        ),
        AbilitySpec(
            "cognition.deep_think",
            "cognition",
            "Use a slower reasoning agent for planning, debugging, and task splitting.",
        ),
        AbilitySpec(
            "cognition.plan_task",
            "cognition",
            "Build a high-level plan before acting.",
        ),
        AbilitySpec(
            "cognition.split_task",
            "cognition",
            "Split a complex task into ordered sub-tasks.",
        ),
        AbilitySpec(
            "cognition.ask_clarification",
            "cognition",
            "Ask a clarifying question when a task is underspecified.",
            status="available",
            implementation="response_composer",
        ),
        AbilitySpec(
            "cognition.self_check_ability",
            "cognition",
            "Check whether Chromie can fulfill a requested ability now.",
            status="available",
            implementation="ability_registry",
        ),
        AbilitySpec(
            "speech.thinking_ack",
            "speech",
            "Give an immediate acknowledgement before longer reasoning.",
            status="available",
            implementation="model_authored_speech",
        ),
        AbilitySpec(
            "speech.answer",
            "speech",
            "Speak the final answer to the user.",
            status="available",
            implementation="response_composer_tts",
        ),
        AbilitySpec(
            "speech.confirm",
            "speech",
            "Confirm before executing a risky or physical request.",
            status="available",
            implementation="response_composer_tts",
        ),
        AbilitySpec(
            "speech.apologize_unavailable",
            "speech",
            "Explain that a requested ability is not available yet.",
            status="available",
            implementation="model_authored_speech",
        ),
        AbilitySpec(
            "speech.report_progress",
            "speech",
            "Report progress during a long task.",
            status="available",
            implementation="response_composer_tts",
        ),
        AbilitySpec(
            "speech.report_done",
            "speech",
            "Report that a task finished.",
            status="available",
            implementation="response_composer_tts",
        ),
        AbilitySpec(
            "speech.report_failure",
            "speech",
            "Report that a task failed or was refused.",
            status="available",
            implementation="response_composer_tts",
        ),
        AbilitySpec(
            "memory.remember_session_context",
            "memory",
            "Remember relevant details for the current conversation session.",
            status="available",
            implementation="conversation_state",
        ),
        AbilitySpec(
            "memory.recall_session_context",
            "memory",
            "Read session history and task context for prompts.",
            status="available",
            implementation="conversation_state",
        ),
        AbilitySpec(
            "memory.forget_current_task",
            "memory",
            "Forget or cancel the current task context at a boundary.",
            status="available",
            implementation="conversation_state",
        ),
        AbilitySpec(
            "memory.start_new_session",
            "memory",
            "Start a new conversation session when the boundary rule says to.",
            status="available",
            implementation="conversation_state",
        ),
        AbilitySpec(
            "memory.summarize_task",
            "memory",
            "Summarize active task context for later prompts.",
            status="available",
            implementation="conversation_state",
        ),
        AbilitySpec(
            "memory.track_pending_task",
            "memory",
            "Track a pending confirmation or long-running task.",
            status="available",
            implementation="conversation_state",
        ),
        AbilitySpec(
            "social.blink_eyes",
            "social",
            "Blink Chromie's visible eyes as a social expression.",
            status="known_missing",
            implementation="missing_skill",
        ),
        AbilitySpec(
            "social.look_at_user",
            "social",
            "Orient attention toward the user.",
            status="known_missing",
            implementation="missing_skill",
            optional_by_default=True,
        ),
        AbilitySpec(
            "social.listen_pose",
            "social",
            "Hold a small listening posture.",
            optional_by_default=True,
        ),
        AbilitySpec(
            "social.micro_nod",
            "social",
            "Use a small acknowledgement nod.",
            optional_by_default=True,
        ),
        AbilitySpec(
            "social.nod_yes",
            "social",
            "Nod yes.",
        ),
        AbilitySpec(
            "social.shake_head_no",
            "social",
            "Shake head no.",
            status="known_missing",
            implementation="missing_skill",
        ),
        AbilitySpec(
            "social.idle_alive",
            "social",
            "Use subtle idle motion so the robot feels present.",
            optional_by_default=True,
        ),
        AbilitySpec(
            "social.turn_toward_sound",
            "social",
            "Orient toward a detected speaker or sound source.",
            status="known_missing",
            implementation="missing_skill",
        ),
        AbilitySpec(
            "social.greet",
            "social",
            "Greet the user.",
            status="available",
            implementation="response_composer_tts",
        ),
        AbilitySpec(
            "social.goodbye",
            "social",
            "Close a conversation politely.",
            status="available",
            implementation="response_composer_tts",
        ),
        AbilitySpec(
            "social.express_attention",
            "social",
            "Use a small attention/listening expression.",
            optional_by_default=True,
        ),
        AbilitySpec(
            "body.stand_ready",
            "body",
            "Stand in a ready posture.",
            status="planned",
            implementation="planned_skill",
        ),
        AbilitySpec(
            "body.relax",
            "body",
            "Relax out of a ready posture.",
            status="planned",
            implementation="planned_skill",
        ),
        AbilitySpec(
            "body.walk_forward",
            "body",
            "Walk forward using a structured Soridormi skill.",
        ),
        AbilitySpec(
            "body.walk_backward",
            "body",
            "Walk backward using a structured Soridormi skill.",
        ),
        AbilitySpec(
            "body.turn_left",
            "body",
            "Turn left using a structured Soridormi skill.",
        ),
        AbilitySpec(
            "body.turn_right",
            "body",
            "Turn right using a structured Soridormi skill.",
        ),
        AbilitySpec(
            "body.stop_motion",
            "body",
            "Stop current motion.",
        ),
        AbilitySpec(
            "body.recover_balance",
            "body",
            "Recover balance after a disturbance.",
            status="planned",
            implementation="planned_skill",
        ),
        AbilitySpec(
            "manipulation.pick_up_object",
            "manipulation",
            "Pick up a small object with a trusted manipulation skill.",
            status="known_missing",
            implementation="missing_skill",
        ),
        AbilitySpec(
            "manipulation.place_object",
            "manipulation",
            "Place an object at a requested target location.",
            status="known_missing",
            implementation="missing_skill",
        ),
        AbilitySpec(
            "navigation.follow_user",
            "navigation",
            "Follow the user while maintaining a safe distance.",
            status="known_missing",
            implementation="missing_skill",
        ),
        AbilitySpec(
            "navigation.go_to_location",
            "navigation",
            "Navigate to a named or pointed location.",
            status="known_missing",
            implementation="missing_skill",
        ),
        AbilitySpec(
            "environment.open_door",
            "environment",
            "Open a door through a trusted manipulation or building-control skill.",
            status="known_missing",
            implementation="missing_skill",
        ),
        AbilitySpec(
            "environment.turn_on_light",
            "environment",
            "Turn on a light through a trusted physical or smart-home skill.",
            status="known_missing",
            implementation="missing_skill",
        ),
        AbilitySpec(
            "environment.clean_surface",
            "environment",
            "Clean or wipe a small surface.",
            status="known_missing",
            implementation="missing_skill",
        ),
        AbilitySpec(
            "task.execute_skill",
            "task",
            "Execute a trusted structured skill through the Skill Runtime.",
            status="available",
            implementation="skill_runtime",
        ),
        AbilitySpec(
            "task.confirm_before_action",
            "task",
            "Request confirmation before risky actions.",
            status="available",
            implementation="confirmation_dialogue",
        ),
        AbilitySpec(
            "task.cancel_current_action",
            "task",
            "Cancel the current action or interaction.",
            status="available",
            implementation="host_interrupt",
        ),
        AbilitySpec(
            "task.monitor_action",
            "task",
            "Monitor action completion and failures.",
            status="available",
            implementation="skill_runtime",
        ),
        AbilitySpec(
            "task.report_action_result",
            "task",
            "Report the result of an action.",
            status="available",
            implementation="response_composer",
        ),
        AbilitySpec(
            "safety.check_capability",
            "safety",
            "Check a requested ability before executing it.",
            status="available",
            implementation="ability_registry",
        ),
        AbilitySpec(
            "safety.check_motion_allowed",
            "safety",
            "Check whether a physical motion is allowed.",
            status="available",
            implementation="skill_runtime",
        ),
        AbilitySpec(
            "safety.refuse_unsafe_request",
            "safety",
            "Refuse unsafe or unsupported requests.",
            status="available",
            implementation="response_composer",
        ),
        AbilitySpec(
            "state.report_robot_status",
            "state",
            "Report current robot/runtime status.",
        ),
        AbilitySpec(
            "state.report_missing_ability",
            "state",
            "Report that an ability is known but not fulfilled yet.",
            status="available",
            implementation="ability_registry",
        ),
    ]
    return {spec.ability_id: spec for spec in specs}


def _set_status(
    abilities: dict[str, AbilitySpec],
    ability_id: str,
    **updates: Any,
) -> None:
    abilities[ability_id] = abilities[ability_id].with_updates(**updates)
