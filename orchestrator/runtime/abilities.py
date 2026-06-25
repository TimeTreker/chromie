from __future__ import annotations

from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import Any, Literal, Mapping

AbilityStatus = Literal["available", "stub", "disabled", "sim_only", "hardware_only"]

DEFAULT_UNAVAILABLE_EN = "Sorry, I don't have that ability yet."
DEFAULT_UNAVAILABLE_ZH = "抱歉，我现在还没有这个能力。"


@dataclass(frozen=True)
class AbilitySpec:
    ability_id: str
    category: str
    description: str
    status: AbilityStatus = "stub"
    implementation: str = "stub"
    optional_by_default: bool = False
    speech_templates: Mapping[str, str] = field(default_factory=dict)
    unavailable_en: str = DEFAULT_UNAVAILABLE_EN
    unavailable_zh: str = DEFAULT_UNAVAILABLE_ZH
    soridormi_skill_id: str | None = None
    default_args: Mapping[str, Any] = field(default_factory=dict)
    timeout_ms: int | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def can_execute(self) -> bool:
        return self.status in {"available", "sim_only", "hardware_only"} and (
            self.implementation != "stub"
        )

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

    def localized_speech(
        self,
        ability_id: str,
        *,
        language: str | None = None,
        user_text: str = "",
    ) -> str | None:
        ability = self.get(ability_id)
        lang = _language_key(language, user_text)
        return ability.speech_templates.get(lang) or ability.speech_templates.get("en")

    def unavailable_message(
        self,
        ability_id: str,
        *,
        language: str | None = None,
        user_text: str = "",
    ) -> str:
        ability = self.get(ability_id)
        if _language_key(language, user_text) == "zh":
            return ability.unavailable_zh
        return ability.unavailable_en


def build_default_ability_registry(
    *,
    enable_agent: bool = True,
    enable_interaction_response: bool = False,
    enable_soridormi_skills: bool = False,
    auto_confirm_sim_skills: bool = True,
    action_dry_run: bool = True,
) -> AbilityRegistry:
    sim_expressive_body = (
        enable_interaction_response
        and enable_soridormi_skills
        and auto_confirm_sim_skills
        and action_dry_run
    )
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

    for ability_id, skill_id, args, timeout_ms in (
        (
            "social.thinking_pose",
            "soridormi.express_attention",
            {"style": "neutral", "duration_s": 2.4, "hold_fraction": 0.35},
            10000,
        ),
        (
            "social.listen_pose",
            "soridormi.express_attention",
            {"style": "neutral", "duration_s": 2.4, "hold_fraction": 0.35},
            10000,
        ),
        (
            "social.express_attention",
            "soridormi.express_attention",
            {"style": "neutral", "duration_s": 2.4, "hold_fraction": 0.35},
            10000,
        ),
        (
            "social.micro_nod",
            "soridormi.nod_yes",
            {"count": 1, "amplitude": "small", "duration_s": 0.9},
            10000,
        ),
        (
            "social.nod_yes",
            "soridormi.nod_yes",
            {"count": 2, "amplitude": "small", "duration_s": 1.4},
            10000,
        ),
    ):
        _set_status(
            abilities,
            ability_id,
            status="sim_only" if sim_expressive_body else "stub",
            implementation=skill_id if sim_expressive_body else "stub",
            soridormi_skill_id=skill_id if sim_expressive_body else None,
            default_args=args if sim_expressive_body else {},
            timeout_ms=timeout_ms if sim_expressive_body else None,
        )

    if enable_soridormi_skills and auto_confirm_sim_skills and action_dry_run:
        for ability_id, skill_id in (
            ("body.walk_forward", "soridormi.walk_velocity"),
            ("body.walk_backward", "soridormi.walk_velocity"),
            ("body.turn_left", "soridormi.turn_in_place"),
            ("body.turn_right", "soridormi.turn_in_place"),
            ("body.stop_motion", "soridormi.stop"),
        ):
            _set_status(
                abilities,
                ability_id,
                status="sim_only",
                implementation=skill_id,
                soridormi_skill_id=skill_id,
            )

    return AbilityRegistry(list(abilities.values()))


def _base_abilities() -> dict[str, AbilitySpec]:
    specs = [
        AbilitySpec(
            "cognition.quick_route",
            "cognition",
            "Choose a fast route for the current utterance.",
            status="available",
            implementation="router",
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
            implementation="host_speech",
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
            implementation="host_tts",
            speech_templates={
                "en": "Okay, let me think about that.",
                "zh": "好的，我想一下。",
            },
        ),
        AbilitySpec(
            "speech.answer",
            "speech",
            "Speak the final answer to the user.",
            status="available",
            implementation="host_tts",
        ),
        AbilitySpec(
            "speech.confirm",
            "speech",
            "Confirm before executing a risky or physical request.",
            status="available",
            implementation="host_tts",
        ),
        AbilitySpec(
            "speech.apologize_unavailable",
            "speech",
            "Explain that a requested ability is not available yet.",
            status="available",
            implementation="host_tts",
            speech_templates={
                "en": DEFAULT_UNAVAILABLE_EN,
                "zh": DEFAULT_UNAVAILABLE_ZH,
            },
        ),
        AbilitySpec(
            "speech.report_progress",
            "speech",
            "Report progress during a long task.",
            status="available",
            implementation="host_tts",
        ),
        AbilitySpec(
            "speech.report_done",
            "speech",
            "Report that a task finished.",
            status="available",
            implementation="host_tts",
        ),
        AbilitySpec(
            "speech.report_failure",
            "speech",
            "Report that a task failed or was refused.",
            status="available",
            implementation="host_tts",
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
            "social.look_at_user",
            "social",
            "Orient attention toward the user.",
            optional_by_default=True,
        ),
        AbilitySpec(
            "social.listen_pose",
            "social",
            "Hold a small listening posture.",
            optional_by_default=True,
        ),
        AbilitySpec(
            "social.thinking_pose",
            "social",
            "Use a small human-like pose while thinking.",
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
        ),
        AbilitySpec(
            "social.greet",
            "social",
            "Greet the user.",
            status="available",
            implementation="host_tts",
        ),
        AbilitySpec(
            "social.goodbye",
            "social",
            "Close a conversation politely.",
            status="available",
            implementation="host_tts",
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
        ),
        AbilitySpec(
            "body.relax",
            "body",
            "Relax out of a ready posture.",
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
            implementation="host_speech",
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
            implementation="host_speech",
        ),
        AbilitySpec(
            "state.report_robot_status",
            "state",
            "Report current robot/runtime status.",
        ),
        AbilitySpec(
            "state.report_sim_or_hardware_mode",
            "state",
            "Report whether Chromie is connected to simulation or hardware.",
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


def _language_key(language: str | None, user_text: str) -> str:
    normalized = (language or "").lower()
    if normalized.startswith("zh"):
        return "zh"
    if any("\u4e00" <= ch <= "\u9fff" for ch in user_text):
        return "zh"
    return "en"
