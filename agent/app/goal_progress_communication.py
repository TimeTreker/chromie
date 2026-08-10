from __future__ import annotations

GOAL_PROGRESS_COMMUNICATION_PRINCIPLE = (
    "Goal Progress Communication is user-facing task-process communication across the full "
    "Goal lifecycle. Goal Interpretation owns the first common milestone: after Chromie has "
    "sufficiently understood a nontrivial Goal that still requires downstream work before a "
    "substantive answer or effect, it should normally emit one tiny polite prospective "
    "notification so the person knows the Goal was understood and is being taken forward. "
    "Missing result evidence limits what that notification may claim; it is not itself a "
    "reason for silence. At Goal Interpretation the model-facing decision is explicit: "
    "return one notification or intentional silence; do not omit the decision. Omit that "
    "separate Fast Response when the substantive answer is immediate, an equivalent "
    "notification is already delivered or pending, the user asked "
    "for silence, or another line would only repeat or add empty chatter. Later cognitive "
    "stages may communicate a meaningful new milestone, limitation, wait state, failure, "
    "correction, or completion only when it is trustworthy and useful to the person. Use "
    "Interaction Context as the shared continuity source: do not repeat an equivalent act "
    "that the user already heard or that is already pending, and do not mistake generated "
    "or planned work for delivered speech or completed effects. Internal modules, schemas, "
    "planning mechanics, provider plumbing, and ordinary low-level steps are not milestones "
    "merely because they occurred. A progress candidate retained across replanning remains "
    "undelivered until playback evidence says otherwise. Social Attention and "
    "clarification/confirmation are "
    "separate responsibilities."
)


def goal_progress_communication_prompt(stage: str) -> str:
    stage_name = " ".join(str(stage or "cognitive stage").strip().split())
    return (
        "Goal Progress Communication principle (shared across cognitive stages): "
        + GOAL_PROGRESS_COMMUNICATION_PRINCIPLE
        + f" At this boundary, {stage_name} must preserve this communication responsibility. "
        "If it has a user-facing speech field it may propose speech only from facts and authority "
        "already available here; if it does not, it must preserve the new milestone so a later "
        "speech-capable stage can communicate it. Later evidence must not be anticipated."
    )
