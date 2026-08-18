from __future__ import annotations

GOAL_PROGRESS_COMMUNICATION_PRINCIPLE = (
    "Goal Progress Communication is user-facing task-process communication across the full "
    "Goal lifecycle. Goal Interpretation owns only provider-neutral Responsibility meaning "
    "and never authors speech or a progress Activity. Fast Planner is the first HOW owner: "
    "after Responsibility meaning is sufficient, it may choose one tiny immediately-ready "
    "prospective Communicative Act when downstream work remains. Before trusted result "
    "Evidence exists, that Activity may acknowledge work, say that Chromie will check, say "
    "that Chromie will act, or say that Chromie will think; it must not state, imply, preview, "
    "or paraphrase an unverified result. The Planner authors the exact bounded progress "
    "wording together with its typed progress kind; the Host validates truth stage and "
    "provenance but never rewrites the sentence. Omit a "
    "separate progress act when the substantive answer is immediate, an equivalent act "
    "is already delivered or pending, the user asked for silence, or another line would only "
    "repeat or add empty chatter. Later cognitive stages may communicate a meaningful new "
    "milestone, limitation, wait state, failure, correction, or completion only when it is "
    "trustworthy and useful to the person. Use Interaction Context as the shared continuity "
    "source: do not repeat an equivalent act that the user already heard or that is already "
    "pending, and do not mistake generated or planned work for delivered speech or completed "
    "effects. Internal modules, schemas, planning mechanics, provider plumbing, and ordinary "
    "low-level steps are not milestones merely because they occurred. Social Attention and "
    "clarification/confirmation are separate responsibilities."
)


def goal_progress_communication_prompt(stage: str) -> str:
    stage_name = " ".join(str(stage or "cognitive stage").strip().split())
    return (
        "Goal Progress Communication principle (shared across cognitive stages): "
        + GOAL_PROGRESS_COMMUNICATION_PRINCIPLE
        + f" At this boundary, {stage_name} must preserve this communication responsibility. "
        "A Planner stage may choose a Communicative Act only from facts and authority "
        "already available there and owns its exact natural wording. Runtime may only "
        "realize that immutable selected act. Other stages preserve the milestone for the "
        "next qualified Planner. Later "
        "Evidence must not be anticipated."
    )
