from __future__ import annotations

from enum import Enum


class CognitionComputeClass(str, Enum):
    """Provider-neutral relative scheduling class for LLM work.

    This is an operational resource hint only.  It never carries Goal meaning,
    Capability selection, plan semantics, response wording, or execution truth.
    Provider adapters may translate this relative class into their own scheduling
    controls; semantic owners must not depend on provider-specific priority values.
    """

    REALTIME = "realtime"
    INTERPRETATION = "interpretation"
    INTERACTIVE = "interactive"
    CONTINUITY = "continuity"
    DELIBERATIVE = "deliberative"
    BACKGROUND = "background"


# A small ordinal is useful to qualification tooling and provider adapters when
# translating Chromie's relative classes.  These ranks are NOT provider request
# priorities and are deliberately not sent over any transport by this module.
_COMPUTE_RANK: dict[CognitionComputeClass, int] = {
    CognitionComputeClass.REALTIME: 5,
    CognitionComputeClass.INTERPRETATION: 4,
    CognitionComputeClass.CONTINUITY: 3,
    CognitionComputeClass.INTERACTIVE: 2,
    CognitionComputeClass.DELIBERATIVE: 1,
    CognitionComputeClass.BACKGROUND: 0,
}


_PURPOSE_COMPUTE_CLASS: dict[str, CognitionComputeClass] = {
    "cognitive_gateway_attention_review": CognitionComputeClass.REALTIME,
    "cognitive_activation": CognitionComputeClass.INTERPRETATION,
    "agent_default": CognitionComputeClass.INTERACTIVE,
    "agent_skill_selection": CognitionComputeClass.INTERACTIVE,
    "user_meaning_interpreter_fast": CognitionComputeClass.INTERPRETATION,
    "fast_planner": CognitionComputeClass.INTERACTIVE,
    "social_cognition": CognitionComputeClass.REALTIME,
    "social_cognition_deep": CognitionComputeClass.REALTIME,
    "situational_cognition": CognitionComputeClass.INTERACTIVE,
    "goal_association": CognitionComputeClass.CONTINUITY,
    "user_meaning_interpreter_deep": CognitionComputeClass.INTERPRETATION,
    "situational_deliberative_cognition": CognitionComputeClass.DELIBERATIVE,
    "deep_planner": CognitionComputeClass.DELIBERATIVE,
    "reflection": CognitionComputeClass.BACKGROUND,
    "startup_warm": CognitionComputeClass.BACKGROUND,
}


def compute_rank(compute_class: CognitionComputeClass) -> int:
    """Return Chromie's relative urgency rank, independent of provider syntax."""

    return _COMPUTE_RANK[compute_class]


def compute_class_for_purpose(
    purpose: str | None,
    *,
    default: CognitionComputeClass = CognitionComputeClass.INTERACTIVE,
) -> CognitionComputeClass:
    """Resolve an already-known transaction purpose to its operational class.

    This is intentionally a closed operational mapping.  It does not inspect user
    text or infer semantics.  Unknown purposes use the caller-supplied default so
    adding observability cannot silently suppress existing cognition.
    """

    normalized = str(purpose or "").strip().casefold()
    return _PURPOSE_COMPUTE_CLASS.get(normalized, default)


def user_meaning_interpreter_compute_class(stage: str) -> CognitionComputeClass:
    """Map the UMI stage depth to compute scheduling without changing UMI authority."""

    normalized = str(stage or "").strip().casefold()
    if normalized == "startup_warm":
        return CognitionComputeClass.BACKGROUND
    return CognitionComputeClass.INTERPRETATION
