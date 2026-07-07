from __future__ import annotations

from typing import Any

from shared.chromie_contracts.interaction import InteractionResponse, SkillRequest

POST_INTERRUPT_PHYSICAL_LOCK_REASON = "post_interrupt_physical_auto_resume_blocked"
_EFFECTFUL_SKILL_IDS = {"chromie.task_graph.execute"}
_PHYSICAL_EFFECT_TERMS = {
    "body_motion",
    "mobile_base_motion",
    "physical_motion",
    "manipulation",
    "navigation",
    "grasp",
    "locomotion",
}


def is_physical_resume_skill(request: SkillRequest) -> bool:
    """Return True for skills that must not auto-resume after an interrupt.

    This is deliberately broader than only high-risk movement. After an
    emergency stop, the physical world may no longer match the previous plan,
    so any Soridormi named skill and TaskGraph execution must re-enter the
    normal confirmation/preflight/runtime path instead of being auto-resumed by
    a post-interrupt ASR correction.
    """

    if request.skill_id.startswith("soridormi."):
        return True
    if request.skill_id in _EFFECTFUL_SKILL_IDS:
        return True
    metadata = request.metadata if isinstance(request.metadata, dict) else {}
    effects = metadata.get("capability_effects") or metadata.get("effects") or []
    if isinstance(effects, str):
        effects = [effects]
    if isinstance(effects, list):
        normalized = {str(effect).strip().lower() for effect in effects}
        if normalized & _PHYSICAL_EFFECT_TERMS:
            return True
    safety_class = str(metadata.get("capability_safety_class") or "").strip().lower()
    if safety_class in {
        "physical_motion",
        "guarded_operation",
        "high_risk_action",
        "safety_critical",
    }:
        return True
    return False


def lock_post_interrupt_physical_resume(
    response: InteractionResponse,
) -> tuple[InteractionResponse, tuple[str, ...]]:
    """Require explicit confirmation for post-interrupt physical corrections.

    Speech-only corrected decisions can proceed normally. Body or task-graph
    skills are preserved as proposals, but are marked confirmation-required and
    annotated so the host disables simulator auto-confirm for this interaction.
    """

    locked_request_ids: list[str] = []
    locked_skills: list[SkillRequest] = []
    for request in response.skills:
        if not is_physical_resume_skill(request):
            locked_skills.append(request)
            continue
        locked_request_ids.append(request.request_id)
        metadata: dict[str, Any] = {
            **request.metadata,
            "post_interrupt_physical_resume_lock": True,
            "post_interrupt_resume_policy": "requires_fresh_confirmation",
            "post_interrupt_lock_reason": POST_INTERRUPT_PHYSICAL_LOCK_REASON,
            "execution_mode": request.metadata.get("execution_mode") or "proposed",
            "requires_runtime_validation": True,
        }
        locked_skills.append(
            request.model_copy(
                deep=True,
                update={
                    "requires_confirmation": True,
                    "metadata": metadata,
                },
            )
        )

    if not locked_request_ids:
        return response, ()

    metadata = {
        **response.metadata,
        "post_interrupt_physical_resume_lock": True,
        "post_interrupt_resume_policy": "physical_requires_fresh_confirmation",
        "post_interrupt_locked_request_ids": locked_request_ids,
        "disable_body_auto_confirm": True,
    }
    return (
        response.model_copy(
            deep=True,
            update={
                "skills": locked_skills,
                "requires_confirmation": True,
                "metadata": metadata,
            },
        ),
        tuple(locked_request_ids),
    )
