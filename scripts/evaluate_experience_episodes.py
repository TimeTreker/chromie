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

from orchestrator.runtime.episode import EpisodeEvaluation, EpisodeRecord


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
    recommended = overall < 70 or bool({"wrong_action_class", "body_skill_for_chat"} & set(failure_tags))
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate Chromie episode records and optionally mine scenario candidates.")
    parser.add_argument("--episodes", type=Path, default=ROOT / ".chromie" / "experience" / "episodes.jsonl")
    parser.add_argument("--output", type=Path, default=ROOT / ".chromie" / "experience" / "evaluations.jsonl")
    parser.add_argument("--candidate-dir", type=Path, default=None)
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
