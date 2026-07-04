#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from orchestrator.runtime.episode import EpisodeEvaluation, EpisodeOfflineReview, EpisodeRecord
from shared.chromie_contracts.mind import MindUpdateProposal


SOCIAL_FALLBACK_SKILLS = {
    "soridormi.nod_yes",
    "soridormi.look_at_person",
    "soridormi.express_attention",
}
LOCOMOTION_SKILL_PREFIXES = (
    "soridormi.walk",
    "soridormi.step",
    "soridormi.turn",
    "soridormi.task.submit",
)
LOCOMOTION_HINTS = (
    "walk",
    "forward",
    "ahead",
    "move",
    "step",
    "go ",
    "走",
    "前",
)
GREETING_HINTS = ("hello", "hi", "hey", "你好")
EYE_ACTION_SKILL_PREFIXES = (
    "soridormi.blink",
    "soridormi.eye",
)
EYE_ACTION_HINTS = (
    "blink",
    "eye",
    "eyes",
    "眨",
    "眨眼",
)
ACTION_CLAIM_HINTS = (
    "i will",
    "i'll",
    "i am",
    "i'm",
    "now",
    "done",
    "finished",
    "blinked",
    "walked",
    "moved",
    "stepped",
    "turned",
    "了",
)


def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line_no, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_no}: invalid JSONL row: {exc}") from exc
        if not isinstance(item, dict):
            raise ValueError(f"{path}:{line_no}: expected object row")
        rows.append(item)
    return rows


def load_latest_episodes(path: Path) -> list[EpisodeRecord]:
    latest: dict[str, EpisodeRecord] = {}
    for item in _read_jsonl(path):
        episode = EpisodeRecord.model_validate(item)
        latest[episode.episode_id] = episode
    return [latest[key] for key in sorted(latest)]


def evaluate_episode_contract_precheck(episode: EpisodeRecord) -> EpisodeEvaluation:
    failure_tags: list[str] = []
    summaries: list[str] = []
    scores = {
        "intent_preservation": 90,
        "route_correctness": 90,
        "skill_correctness": 90,
        "safety_confirmation": 90,
        "memory_continuity": 80,
        "speech_quality": 80,
        "latency": 85,
    }
    cap = 100

    for turn in episode.turns:
        text = turn.user_text.lower()
        skills = [item.skill_id for item in turn.agent.selected_skills]
        skill_set = set(skills)
        route = turn.router.route
        speech = " ".join(turn.agent.speech).strip()

        looks_like_locomotion = any(hint in text for hint in LOCOMOTION_HINTS)
        selected_social_fallback = sorted(skill_set & SOCIAL_FALLBACK_SKILLS)
        selected_locomotion = any(
            any(skill.startswith(prefix) for prefix in LOCOMOTION_SKILL_PREFIXES)
            for skill in skills
        )
        looks_like_eye_action = any(hint in text for hint in EYE_ACTION_HINTS)
        selected_eye_action = _has_skill_prefix(skills, EYE_ACTION_SKILL_PREFIXES)

        if looks_like_locomotion and selected_social_fallback and not selected_locomotion:
            _add_tag(failure_tags, "wrong_action_class")
            _add_tag(failure_tags, "social_fallback_for_locomotion")
            summaries.append(
                f"Turn {turn.turn_index} looks like locomotion but selected {', '.join(selected_social_fallback)}."
            )
            scores["intent_preservation"] = min(scores["intent_preservation"], 10)
            scores["skill_correctness"] = min(scores["skill_correctness"], 0)
            scores["speech_quality"] = min(scores["speech_quality"], 35)
            cap = min(cap, 35)

        if any(hint in text for hint in GREETING_HINTS) and selected_social_fallback:
            _add_tag(failure_tags, "body_skill_for_chat")
            summaries.append(
                f"Turn {turn.turn_index} is greeting-like but selected body skill {', '.join(selected_social_fallback)}."
            )
            scores["route_correctness"] = min(scores["route_correctness"], 60)
            scores["skill_correctness"] = min(scores["skill_correctness"], 20)
            cap = min(cap, 45)

        if route == "robot_action" and looks_like_locomotion and not selected_locomotion and not selected_social_fallback:
            _add_tag(failure_tags, "missing_locomotion_skill")
            scores["skill_correctness"] = min(scores["skill_correctness"], 55)
            cap = min(cap, 65)

        if looks_like_locomotion and route != "robot_action" and not selected_locomotion:
            _add_tag(failure_tags, "action_request_as_chat")
            _add_tag(failure_tags, "missing_locomotion_skill")
            summaries.append(
                f"Turn {turn.turn_index} looks like locomotion but route={route!r} emitted no locomotion skill."
            )
            scores["route_correctness"] = min(scores["route_correctness"], 45)
            scores["skill_correctness"] = min(scores["skill_correctness"], 25)
            cap = min(cap, 45)

        if looks_like_locomotion and not selected_locomotion and _speech_claims_action(
            speech, LOCOMOTION_HINTS
        ):
            _add_tag(failure_tags, "claimed_action_without_skill")
            scores["speech_quality"] = min(scores["speech_quality"], 20)
            cap = min(cap, 40)

        if looks_like_eye_action and not selected_eye_action:
            _add_tag(failure_tags, "missing_eye_skill")
            summaries.append(
                f"Turn {turn.turn_index} looks like an eye/blink request but emitted no eye/blink skill."
            )
            scores["intent_preservation"] = min(scores["intent_preservation"], 35)
            scores["skill_correctness"] = min(scores["skill_correctness"], 15)
            cap = min(cap, 45)
            if route != "robot_action":
                _add_tag(failure_tags, "action_request_as_chat")
                scores["route_correctness"] = min(scores["route_correctness"], 45)
            if selected_locomotion or selected_social_fallback:
                _add_tag(failure_tags, "wrong_action_class")
                cap = min(cap, 40)
            if _speech_claims_action(speech, EYE_ACTION_HINTS):
                _add_tag(failure_tags, "claimed_action_without_skill")
                scores["speech_quality"] = min(scores["speech_quality"], 20)
                cap = min(cap, 40)

        if turn.agent.requires_confirmation and not skills:
            _add_tag(failure_tags, "confirmation_without_skill")
            scores["safety_confirmation"] = min(scores["safety_confirmation"], 55)

        if not speech and route not in {"ignore", "interrupt"}:
            _add_tag(failure_tags, "missing_speech")
            scores["speech_quality"] = min(scores["speech_quality"], 20)
            cap = min(cap, 50)

        if turn.agent.latency_ms is not None and turn.agent.latency_ms > 8000:
            _add_tag(failure_tags, "slow_agent")
            scores["latency"] = min(scores["latency"], 35)
        if turn.router.latency_ms is not None and turn.router.latency_ms > 2000:
            _add_tag(failure_tags, "slow_router")
            scores["latency"] = min(scores["latency"], 55)

    base_score = int(round(sum(scores.values()) / len(scores)))
    overall = max(0, min(cap, base_score))
    severity = "pass"
    if overall < 30:
        severity = "critical"
    elif overall < 70:
        severity = "major"
    elif overall < 85:
        severity = "minor"
    summary = " ".join(summaries) if summaries else "No contract-level episode failure found."
    recommended = overall < 70 or bool(
        {
            "wrong_action_class",
            "body_skill_for_chat",
            "claimed_action_without_skill",
            "missing_eye_skill",
        }
        & set(failure_tags)
    )
    return EpisodeEvaluation(
        episode_id=episode.episode_id,
        conversation_id=episode.conversation_id,
        overall_score=overall,
        passed=overall >= 70,
        severity=severity,
        summary=summary,
        scores=scores,
        failure_tags=failure_tags,
        candidate_scenario={
            "recommended": recommended,
            "suite": "dialogue" if len(episode.turns) > 1 else "interaction",
            "reason": summary if recommended else "",
        },
        evaluator="contract_precheck",
    )


def evaluate_episode_with_llm(
    episode: EpisodeRecord,
    *,
    ollama_url: str,
    model: str,
    timeout_s: float,
) -> EpisodeEvaluation:
    prompt = _evaluation_prompt(episode)
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "think": False,
        "keep_alive": "24h",
        "options": {
            "num_ctx": 8192,
            "num_predict": 900,
            "temperature": 0.0,
        },
    }
    request = urllib.request.Request(
        f"{ollama_url.rstrip('/')}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        data = json.loads(response.read().decode("utf-8"))
    text = str(data.get("response") or "")
    raw = _extract_json_object(text)
    candidate = json.loads(raw)
    if "passed" not in candidate and "pass" in candidate:
        candidate["passed"] = bool(candidate.pop("pass"))
    candidate.setdefault("episode_id", episode.episode_id)
    candidate.setdefault("conversation_id", episode.conversation_id)
    candidate.setdefault("schema_version", 1)
    candidate.setdefault("scores", {})
    candidate.setdefault("failure_tags", [])
    candidate.setdefault("candidate_scenario", {})
    candidate["evaluator"] = f"deepthinking_llm:{model}"
    return EpisodeEvaluation.model_validate(candidate)


def _evaluation_prompt(episode: EpisodeRecord) -> str:
    episode_json = json.dumps(episode.model_dump(mode="json"), ensure_ascii=False, indent=2)
    return (
        "You are Chromie's deepthinking evaluator. Score this robot dialogue/task episode.\n"
        "Use semantic judgment over the whole episode. Do not create phrase rules.\n"
        "A wrong physical/social skill for the user's action class is a serious failure.\n"
        "Return exactly one JSON object with keys: overall_score integer 0-100, passed boolean, "
        "severity one of pass/minor/major/critical, summary string, scores object, "
        "failure_tags array, candidate_scenario object with recommended boolean, suite string, reason string.\n\n"
        "Scoring axes: intent_preservation, route_correctness, skill_correctness, "
        "safety_confirmation, memory_continuity, speech_quality, latency.\n"
        "Hard caps: social acknowledgement/gaze for unrelated locomotion <=35; "
        "wrong physical action class <=40; unconfirmed physical execution <=30.\n\n"
        f"Episode JSON:\n{episode_json}\n"
    )


def _extract_json_object(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end > start:
        return stripped[start : end + 1]
    raise ValueError("LLM response did not contain a JSON object")


def write_evaluations(path: Path, evaluations: list[EpisodeEvaluation]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for evaluation in evaluations:
            handle.write(json.dumps(evaluation.model_dump(mode="json"), sort_keys=True) + "\n")


def offline_review_from_episode(
    episode: EpisodeRecord,
    evaluation: EpisodeEvaluation,
) -> EpisodeOfflineReview:
    failure_tags = list(evaluation.failure_tags)
    tag_set = set(failure_tags)
    if evaluation.overall_score < 70 or evaluation.severity in {"major", "critical"}:
        case_quality = "bad_case"
    elif evaluation.passed and evaluation.overall_score >= 85 and not failure_tags:
        case_quality = "good_case"
    else:
        case_quality = "needs_review"

    should_create_scenario = bool(evaluation.candidate_scenario.get("recommended"))
    should_create_mind_update = case_quality != "good_case" or bool(
        tag_set
        & {
            "wrong_action_class",
            "claimed_action_without_skill",
            "body_skill_for_chat",
            "missing_eye_skill",
            "missing_locomotion_skill",
        }
    )
    learning_actions: list[str] = []
    if should_create_scenario:
        learning_actions.append("draft_or_promote_regression_scenario")
    if should_create_mind_update:
        learning_actions.append("owner_review_strategy_prompt_or_skill_selection_update")
    if case_quality == "good_case":
        learning_actions.append("retain_as_positive_reference")
    if "slow_agent" in tag_set or "slow_router" in tag_set:
        learning_actions.append("inspect_latency_budget")

    root_cause = _root_cause_from_evaluation(evaluation)
    strengths = _strengths_from_episode(episode, evaluation)
    compact_memory_notes = _compact_memory_notes_from_review(
        evaluation=evaluation,
        root_cause=root_cause,
        case_quality=case_quality,
    )
    selected_skill_count = sum(len(turn.agent.selected_skills) for turn in episode.turns)
    completed_skill_count = sum(
        1
        for turn in episode.turns
        for result in turn.execution.skill_results
        if result.status == "completed"
    )
    return EpisodeOfflineReview(
        episode_id=episode.episode_id,
        conversation_id=episode.conversation_id,
        evaluation_id=evaluation.evaluation_id,
        case_quality=case_quality,
        overall_score=evaluation.overall_score,
        severity=evaluation.severity,
        summary=evaluation.summary,
        root_cause=root_cause,
        strengths=strengths,
        failure_tags=failure_tags,
        learning_actions=learning_actions,
        should_create_scenario=should_create_scenario,
        should_create_mind_update=should_create_mind_update,
        compact_memory_notes=compact_memory_notes,
        training_signal={
            "recommended_use": _training_signal_use(case_quality),
            "turn_count": len(episode.turns),
            "selected_skill_count": selected_skill_count,
            "completed_skill_count": completed_skill_count,
            "evaluator": evaluation.evaluator,
        },
        requires_owner_approval=True,
        auto_apply=False,
        reviewer=f"offline_review:{evaluation.evaluator}",
    )


def write_offline_reviews(path: Path, reviews: list[EpisodeOfflineReview]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for review in reviews:
            handle.write(
                json.dumps(review.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
                + "\n"
            )


def mind_update_proposal_from_review(review: EpisodeOfflineReview) -> MindUpdateProposal | None:
    if not review.should_create_mind_update:
        return None
    return MindUpdateProposal(
        target="experience_tuned_strategy",
        proposed_change=(
            "Review the offline episode review and consider updating prompts, "
            "skill-selection examples, scenario coverage, or model tuning data. "
            "Do not auto-apply changes to core principles or physical safety policy."
        ),
        rationale=(
            f"Offline review {review.review_id} classified episode {review.episode_id} "
            f"as {review.case_quality} with score={review.overall_score}. "
            f"Root cause: {review.root_cause}"
        ),
        evidence_ids=[review.episode_id, review.evaluation_id, review.review_id],
        requires_owner_approval=True,
        auto_apply=False,
    )


def write_mind_update_proposals_from_reviews(
    path: Path,
    reviews: list[EpisodeOfflineReview],
) -> list[MindUpdateProposal]:
    proposals = [
        proposal
        for review in reviews
        if (proposal := mind_update_proposal_from_review(review)) is not None
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for proposal in proposals:
            handle.write(
                json.dumps(proposal.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
                + "\n"
            )
    return proposals


def write_candidate_scenarios(
    *,
    episodes: list[EpisodeRecord],
    evaluations: list[EpisodeEvaluation],
    output_dir: Path,
) -> list[Path]:
    by_id = {episode.episode_id: episode for episode in episodes}
    written: list[Path] = []
    run_dir = output_dir / _now_stamp()
    for evaluation in evaluations:
        if not bool(evaluation.candidate_scenario.get("recommended")):
            continue
        episode = by_id.get(evaluation.episode_id)
        if episode is None:
            continue
        candidate = scenario_candidate_from_episode(episode, evaluation)
        run_dir.mkdir(parents=True, exist_ok=True)
        path = run_dir / f"{candidate['id']}.json"
        path.write_text(json.dumps(candidate, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        written.append(path)
    return written


def scenario_candidate_from_episode(
    episode: EpisodeRecord,
    evaluation: EpisodeEvaluation,
) -> dict[str, Any]:
    scenario_id = _scenario_id_from_episode(episode, evaluation)
    turns = []
    for turn in episode.turns:
        selected_skills = [item.skill_id for item in turn.agent.selected_skills]
        forbidden = sorted(set(selected_skills) & SOCIAL_FALLBACK_SKILLS)
        if "social_fallback_for_locomotion" in evaluation.failure_tags:
            forbidden = sorted(set(forbidden) | SOCIAL_FALLBACK_SKILLS)
        expect: dict[str, Any] = {
            "post_history_contains": [turn.user_text],
        }
        if forbidden:
            expect["forbidden_skills"] = forbidden
        if "body_skill_for_chat" in evaluation.failure_tags and turn.router.route == "chat":
            expect["no_skills"] = True
        if "missing_eye_skill" in evaluation.failure_tags:
            if turn.router.route == "robot_action":
                expect["skills"] = ["soridormi.blink_eyes"]
            else:
                expect["no_skills"] = True
                expect["forbidden_speech_any"] = [
                    "blinked",
                    "blinking",
                    "眨了",
                    "眨眼",
                    "👁",
                ]
        if not forbidden and selected_skills:
            expect["forbidden_skills"] = sorted(set(selected_skills))
        turns.append(
            {
                "id": f"turn_{turn.turn_index}",
                "ask": turn.user_text,
                "stub": {
                    "route_decision": {
                        "route": turn.router.route,
                        "agents": _agents_for_route(turn.router.route),
                        "intent": turn.router.intent,
                        "confidence": turn.router.confidence or 0.5,
                        "source": turn.router.source,
                    }
                },
                "expect": expect,
            }
        )
    return {
        "schema_version": 1,
        "id": scenario_id,
        "suite": "dialogue",
        "level": "integration",
        "description": f"Candidate mined from episode {episode.episode_id}: {evaluation.summary}",
        "tags": ["candidate", "experience-mined", *evaluation.failure_tags],
        "review": {
            "source_episode_id": episode.episode_id,
            "source_evaluation_id": evaluation.evaluation_id,
            "score": evaluation.overall_score,
            "requires_human_review": True,
        },
        "turns": turns,
    }


def _scenario_id_from_episode(episode: EpisodeRecord, evaluation: EpisodeEvaluation) -> str:
    tags = set(evaluation.failure_tags)
    suffix = episode.episode_id.replace("episode_", "")[:12].lower()
    if "social_fallback_for_locomotion" in tags:
        stem = "candidate_walk_not_social_fallback"
    elif "body_skill_for_chat" in tags:
        stem = "candidate_chat_no_body_skill"
    else:
        stem = "candidate_low_score_episode"
    return _slug(f"{stem}_{suffix}")


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9_]+", "_", value.lower()).strip("_")
    if not slug or not slug[0].isalpha():
        slug = f"candidate_{slug}"
    return slug[:80]


def _agents_for_route(route: str) -> list[str]:
    if route == "robot_action":
        return ["capability_agent", "conversation_agent", "safety_agent", "speaker_agent"]
    if route == "deep_thought":
        return ["deepthinking_agent", "speaker_agent"]
    return ["conversation_agent", "speaker_agent"]


def _add_tag(tags: list[str], tag: str) -> None:
    if tag not in tags:
        tags.append(tag)


def _has_skill_prefix(skills: list[str], prefixes: tuple[str, ...]) -> bool:
    return any(any(skill.startswith(prefix) for prefix in prefixes) for skill in skills)


def _speech_claims_action(speech: str, action_hints: tuple[str, ...]) -> bool:
    lowered = speech.lower()
    return any(hint in lowered for hint in action_hints) and any(
        hint in lowered for hint in ACTION_CLAIM_HINTS
    )


def _root_cause_from_evaluation(evaluation: EpisodeEvaluation) -> str:
    tags = set(evaluation.failure_tags)
    if "claimed_action_without_skill" in tags:
        return "The robot spoke as if a body action was happening, but no matching runtime skill was selected."
    if "wrong_action_class" in tags:
        return "The planner preserved a physical-looking request as the wrong action class."
    if "social_fallback_for_locomotion" in tags:
        return "A social fallback skill was used for a locomotion request."
    if "body_skill_for_chat" in tags:
        return "A body skill was selected for a conversation-only turn."
    if "missing_eye_skill" in tags:
        return "An eye or blink request did not produce an eye/blink skill."
    if "missing_locomotion_skill" in tags:
        return "A locomotion request did not produce a locomotion skill."
    if "confirmation_without_skill" in tags:
        return "The response asked for confirmation even though no executable skill was present."
    if "slow_agent" in tags or "slow_router" in tags:
        return "The interaction exceeded the latency budget."
    if evaluation.passed:
        return "No contract-level failure was found."
    return evaluation.summary


def _strengths_from_episode(
    episode: EpisodeRecord,
    evaluation: EpisodeEvaluation,
) -> list[str]:
    strengths: list[str] = []
    completed = sorted(
        {
            result.skill_id
            for turn in episode.turns
            for result in turn.execution.skill_results
            if result.status == "completed"
        }
    )
    if completed:
        strengths.append(f"Runtime reported completed skills: {', '.join(completed[:4])}.")
    if any(turn.agent.speech for turn in episode.turns):
        strengths.append("The robot produced user-facing speech.")
    if evaluation.passed:
        strengths.append("The contract precheck did not find a failure.")
    return strengths


def _compact_memory_notes_from_review(
    *,
    evaluation: EpisodeEvaluation,
    root_cause: str,
    case_quality: str,
) -> list[str]:
    tags = set(evaluation.failure_tags)
    notes: list[str] = []
    if case_quality == "good_case":
        notes.append("Experience positive reference: route, speech, skills, and execution matched the user's intent.")
    if "claimed_action_without_skill" in tags:
        notes.append("Experience correction: do not describe a physical action as done unless a matching runtime skill was selected and executed.")
    if "missing_eye_skill" in tags:
        notes.append("Experience correction: eye or blink requests should map to an eye/blink skill, not speech-only acknowledgement.")
    if "social_fallback_for_locomotion" in tags:
        notes.append("Experience correction: locomotion requests must not degrade into social gaze or nod fallbacks.")
    if not notes and case_quality != "good_case":
        notes.append(f"Experience review needed: {root_cause}")
    return notes


def _training_signal_use(case_quality: str) -> str:
    if case_quality == "good_case":
        return "positive_reference"
    if case_quality == "bad_case":
        return "negative_case"
    return "human_review"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate Chromie episode records and optionally mine scenario candidates.")
    parser.add_argument("--episodes", type=Path, default=ROOT / ".chromie" / "experience" / "episodes.jsonl")
    parser.add_argument("--output", type=Path, default=ROOT / ".chromie" / "experience" / "evaluations.jsonl")
    parser.add_argument("--candidate-dir", type=Path, default=None)
    parser.add_argument("--review-output", type=Path, default=None)
    parser.add_argument("--proposal-output", type=Path, default=None)
    parser.add_argument("--use-llm", action="store_true", help="Ask the deepthinking Ollama model to score episodes.")
    parser.add_argument("--require-llm", action="store_true", help="Fail instead of falling back to contract precheck when LLM scoring fails.")
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--model", default="gemma4:26b")
    parser.add_argument("--timeout-s", type=float, default=120.0)
    args = parser.parse_args(argv)

    episodes = load_latest_episodes(args.episodes)
    evaluations: list[EpisodeEvaluation] = []
    for episode in episodes:
        if args.use_llm:
            try:
                evaluations.append(
                    evaluate_episode_with_llm(
                        episode,
                        ollama_url=args.ollama_url,
                        model=args.model,
                        timeout_s=args.timeout_s,
                    )
                )
                continue
            except (OSError, urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
                if args.require_llm:
                    raise
                print(
                    f"[experience-eval][warn] LLM scoring failed for {episode.episode_id}; "
                    f"using contract precheck: {exc}",
                    file=sys.stderr,
                )
        evaluations.append(evaluate_episode_contract_precheck(episode))

    write_evaluations(args.output, evaluations)
    print(f"Evaluated {len(evaluations)} episode(s): {args.output}")
    reviews = [
        offline_review_from_episode(episode, evaluation)
        for episode, evaluation in zip(episodes, evaluations, strict=True)
    ]
    if args.review_output is not None:
        write_offline_reviews(args.review_output, reviews)
        print(f"Wrote {len(reviews)} offline review record(s): {args.review_output}")
    if args.proposal_output is not None:
        proposals = write_mind_update_proposals_from_reviews(args.proposal_output, reviews)
        print(f"Wrote {len(proposals)} owner-review proposal(s): {args.proposal_output}")
    if args.candidate_dir is not None:
        written = write_candidate_scenarios(
            episodes=episodes,
            evaluations=evaluations,
            output_dir=args.candidate_dir,
        )
        print(f"Wrote {len(written)} candidate scenario file(s).")
        for path in written:
            print(f"  {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
