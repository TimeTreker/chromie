from __future__ import annotations

GOAL_PROGRESS_COMMUNICATION_PRINCIPLE = (
    "Goal Progress Communication is user-facing task-process communication across the full "
    "Goal lifecycle. Its first common form is a brief acknowledgement after Chromie has "
    "understood a nontrivial user Goal and is taking it forward; later forms may report a "
    "meaningful new milestone, limitation, wait state, failure, correction, or completion. "
    "It is not Social Attention, and it is not clarification or confirmation of an unclear "
    "Goal. Any cognitive stage that has a new, trustworthy, user-relevant progress delta may "
    "propose concise speech, but no stage is required to speak. Use Interaction Context as the "
    "shared continuity source: do not repeat an equivalent act that the user already heard or "
    "that is already pending, and do not mistake generated/planned work for delivered speech "
    "or completed effects. Prefer silence when there is no new user-relevant delta, when a "
    "substantive answer is already immediate, or when another update would be filler or "
    "verbosity. Never narrate internal modules, schemas, planning mechanics, or implementation "
    "steps merely because they occurred."
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
