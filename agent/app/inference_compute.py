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
    INTERACTIVE = "interactive"
    CONTINUITY = "continuity"
    DELIBERATIVE = "deliberative"
    BACKGROUND = "background"


# A small ordinal is useful to qualification tooling and provider adapters when
# translating Chromie's relative classes.  These ranks are NOT provider request
# priorities and are deliberately not sent over any transport by this module.
_COMPUTE_RANK: dict[CognitionComputeClass, int] = {
    CognitionComputeClass.REALTIME: 4,
    CognitionComputeClass.INTERACTIVE: 3,
    CognitionComputeClass.CONTINUITY: 2,
    CognitionComputeClass.DELIBERATIVE: 1,
    CognitionComputeClass.BACKGROUND: 0,
}


_PURPOSE_COMPUTE_CLASS: dict[str, CognitionComputeClass] = {
    "cognitive_gateway_attention_review": CognitionComputeClass.REALTIME,
    "agent_default": CognitionComputeClass.INTERACTIVE,
    "agent_skill_selection": CognitionComputeClass.INTERACTIVE,
    "goal_interpreter_fast": CognitionComputeClass.INTERACTIVE,
    "fast_planner": CognitionComputeClass.INTERACTIVE,
    "situational_cognition": CognitionComputeClass.INTERACTIVE,
    "goal_association": CognitionComputeClass.CONTINUITY,
    "goal_interpreter_deep": CognitionComputeClass.DELIBERATIVE,
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


def goal_interpreter_compute_class(stage: str) -> CognitionComputeClass:
    """Map the GI stage depth to compute scheduling without changing GI authority."""

    normalized = str(stage or "").strip().casefold()
    if "deep" in normalized:
        return CognitionComputeClass.DELIBERATIVE
    if normalized == "startup_warm":
        return CognitionComputeClass.BACKGROUND
    return CognitionComputeClass.INTERACTIVE
