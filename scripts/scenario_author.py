#!/usr/bin/env python3
"""Author and validate file-backed Chromie behavior scenarios."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from string import Template
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from scripts.behavior_scenarios import (
        DEFAULT_SCENARIO_ROOT,
        SUPPORTED_SUITES,
        load_scenario_file,
        load_scenarios,
    )
except ModuleNotFoundError:
    from behavior_scenarios import (
        DEFAULT_SCENARIO_ROOT,
        SUPPORTED_SUITES,
        load_scenario_file,
        load_scenarios,
    )

TEMPLATE_ROOT = DEFAULT_SCENARIO_ROOT / "templates"
ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


def _scenario_path(root: Path, suite: str, scenario_id: str) -> Path:
    return root / suite / f"{scenario_id}.json"


def _load_template(suite: str, *, root: Path = TEMPLATE_ROOT) -> dict[str, Any]:
    path = root / f"{suite}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: template must be a JSON object")
    return payload


def _render_template(
    suite: str,
    *,
    scenario_id: str,
    text: str,
    description: str,
    tags: list[str],
    root: Path = TEMPLATE_ROOT,
) -> dict[str, Any]:
    raw = json.dumps(_load_template(suite, root=root), ensure_ascii=False)
    rendered = Template(raw).safe_substitute(
        id=scenario_id,
        text=text,
        description=description or f"Draft {suite} scenario {scenario_id}.",
    )
    payload = json.loads(rendered)
    if tags:
        payload["tags"] = tags
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def validate_id(scenario_id: str) -> None:
    if not ID_PATTERN.fullmatch(scenario_id):
        raise ValueError(
            "scenario id must start with a lowercase letter and contain only "
            "lowercase letters, digits, and underscores"
        )


def command_new(args: argparse.Namespace) -> int:
    try:
        validate_id(args.id)
        payload = _render_template(
            args.suite,
            scenario_id=args.id,
            text=args.text or f"Draft text for {args.id}.",
            description=args.description or "",
            tags=args.tag,
        )
        path = _scenario_path(args.scenario_root, args.suite, args.id)
        if path.exists() and not args.force:
            print(f"scenario already exists: {path}", file=sys.stderr)
            return 2
        if args.stdout:
            print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))
        else:
            _write_json(path, payload)
            load_scenario_file(path)
            print(f"wrote {path}")
    except Exception as exc:
        print(f"scenario new failed: {exc}", file=sys.stderr)
        return 2
    return 0


def _validate_paths(paths: list[Path]) -> tuple[int, int]:
    passed = 0
    failed = 0
    for path in paths:
        try:
            scenario = load_scenario_file(path)
        except Exception as exc:
            failed += 1
            print(f"FAIL {path}: {exc}")
        else:
            passed += 1
            print(f"PASS {scenario.key}: {path}")
    return passed, failed


def command_validate(args: argparse.Namespace) -> int:
    paths = [Path(item) for item in args.paths]
    passed, failed = _validate_paths(paths)
    print(f"Validated {passed + failed} scenario file(s): {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


def command_validate_all(args: argparse.Namespace) -> int:
    try:
        scenarios = load_scenarios(
            args.scenario_root,
            suites=set(args.suite) if args.suite else None,
        )
    except Exception as exc:
        print(f"scenario discovery failed: {exc}", file=sys.stderr)
        return 1
    paths = [scenario.path for scenario in scenarios]
    passed, failed = _validate_paths(paths)
    print(f"Validated {passed + failed} scenario file(s): {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


def command_templates(args: argparse.Namespace) -> int:
    for suite in sorted(SUPPORTED_SUITES):
        path = args.template_root / f"{suite}.json"
        print(f"{suite}\t{path}")
        if args.show:
            print(path.read_text(encoding="utf-8").rstrip())
    return 0


def command_edit(args: argparse.Namespace) -> int:
    try:
        validate_id(args.id)
        path = _scenario_path(args.scenario_root, args.suite, args.id)
        if not path.exists():
            print(f"scenario does not exist: {path}", file=sys.stderr)
            return 2
        editor = args.editor or os.environ.get("EDITOR")
        if not editor:
            print("set EDITOR or pass --editor to edit a scenario", file=sys.stderr)
            return 2
        command = [*shlex.split(editor), str(path)]
        if args.dry_run:
            print("+ " + " ".join(command))
            return 0
        completed = subprocess.run(command, check=False)
        if completed.returncode != 0:
            return completed.returncode
        load_scenario_file(path)
        print(f"validated {path}")
        return 0
    except Exception as exc:
        print(f"scenario edit failed: {exc}", file=sys.stderr)
        return 1


def _scenario_schema_summary(suite: str) -> str:
    if suite == "router":
        return (
            "Router scenarios must set stub.router_mode, optional stub.catalog, "
            "optional stub.llm_decision, and expect route/intent/source/task_types/"
            "metadata/llm_calls. Use task_types_forbid for unsafe motion checks."
        )
    if suite == "dialogue":
        return (
            "Dialogue scenarios must set turns[], where each turn has id, ask, "
            "stub.route_decision, optional stub.ollama_reply/catalog_capabilities, "
            "and expect fields. Expect speech_any/speech_all, forbidden_speech_any, "
            "skills, forbidden_skills, no_skills, requires_confirmation, status, "
            "skill_args, history_contains, session_memory_contains, "
            "post_history_contains, post_session_memory_contains, "
            "extracted_memory_contains, post_extracted_memory_contains, "
            "memory_summary_contains, post_memory_summary_contains, and "
            "current_task_context_contains. Prefer extracted_memory_contains "
            "when checking refined memory rather than raw transcript context."
        )
    return (
        "Interaction scenarios must set stub.route_decision and optional "
        "stub.ollama_reply/catalog_capabilities. Expect speech_any/speech_all, "
        "forbidden_speech_any, skills, forbidden_skills, no_skills, "
        "skill_args, status, metadata booleans, and requires_confirmation."
    )


def command_prompt(args: argparse.Namespace) -> int:
    existing = load_scenarios(args.scenario_root, suites={args.suite})
    existing_ids = ", ".join(scenario.scenario_id for scenario in existing) or "<none>"
    template = _render_template(
        args.suite,
        scenario_id="example_new_scenario",
        text="Example user utterance.",
        description="Example deterministic scenario.",
        tags=["draft", args.focus] if args.focus else ["draft"],
    )
    focus = args.focus or "normal and difficult robot interaction behavior"
    prompt = f"""You are helping author Chromie behavior regression scenarios.

Generate {args.count} candidate JSON scenario files for the `{args.suite}` suite.
Focus: {focus}

Hard rules:
- Return one JSON object per scenario; do not wrap multiple scenarios in one file.
- Each scenario id must be unique and use lowercase snake_case.
- Do not use existing ids: {existing_ids}
- Use deterministic expectations only. Do not make the LLM the test judge.
- Avoid low-level motor, joint, torque, actuator, or controller-array fields.
- Stop, cancel, emergency, silence, and unusable-audio paths must stay deterministic.
- Physical execution must remain default-off; these are Level A fixtures only.

Suite guidance:
{_scenario_schema_summary(args.suite)}

Template shape:
{json.dumps(template, indent=2, ensure_ascii=False, sort_keys=True)}

After generation, the human will save each object as:
scenarios/{args.suite}/<id>.json

Then validate and run:
python scripts/scenario_author.py validate-all --suite {args.suite}
Add representative cases to scenarios/general_ability_acceptance.json.
python scripts/general_ability_acceptance.py --mode check --no-write
python scripts/general_ability_acceptance.py --mode level-a --no-write
"""
    print(prompt)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    new_parser = subparsers.add_parser("new", help="Create a scenario from a template.")
    new_parser.add_argument("--suite", required=True, choices=sorted(SUPPORTED_SUITES))
    new_parser.add_argument("--id", required=True, help="Lowercase snake_case scenario id.")
    new_parser.add_argument("--text", default="", help="User utterance for input.text.")
    new_parser.add_argument("--description", default="")
    new_parser.add_argument("--tag", action="append", default=[])
    new_parser.add_argument("--scenario-root", type=Path, default=DEFAULT_SCENARIO_ROOT)
    new_parser.add_argument("--stdout", action="store_true", help="Print JSON instead of writing a file.")
    new_parser.add_argument("--force", action="store_true", help="Overwrite an existing file.")
    new_parser.set_defaults(func=command_new)

    validate_parser = subparsers.add_parser("validate", help="Validate scenario JSON files.")
    validate_parser.add_argument("paths", nargs="+")
    validate_parser.set_defaults(func=command_validate)

    validate_all_parser = subparsers.add_parser("validate-all", help="Validate discovered scenario files.")
    validate_all_parser.add_argument("--suite", action="append", choices=sorted(SUPPORTED_SUITES))
    validate_all_parser.add_argument("--scenario-root", type=Path, default=DEFAULT_SCENARIO_ROOT)
    validate_all_parser.set_defaults(func=command_validate_all)

    templates_parser = subparsers.add_parser("templates", help="List scenario templates.")
    templates_parser.add_argument("--template-root", type=Path, default=TEMPLATE_ROOT)
    templates_parser.add_argument("--show", action="store_true")
    templates_parser.set_defaults(func=command_templates)

    edit_parser = subparsers.add_parser("edit", help="Open an existing scenario in an editor.")
    edit_parser.add_argument("--suite", required=True, choices=sorted(SUPPORTED_SUITES))
    edit_parser.add_argument("--id", required=True)
    edit_parser.add_argument("--scenario-root", type=Path, default=DEFAULT_SCENARIO_ROOT)
    edit_parser.add_argument("--editor", help="Editor command. Defaults to $EDITOR.")
    edit_parser.add_argument("--dry-run", action="store_true", help="Print the editor command without running it.")
    edit_parser.set_defaults(func=command_edit)

    prompt_parser = subparsers.add_parser("prompt", help="Print an LLM prompt for candidate scenarios.")
    prompt_parser.add_argument("--suite", required=True, choices=sorted(SUPPORTED_SUITES))
    prompt_parser.add_argument("--count", type=int, default=10)
    prompt_parser.add_argument("--focus", default="")
    prompt_parser.add_argument("--scenario-root", type=Path, default=DEFAULT_SCENARIO_ROOT)
    prompt_parser.set_defaults(func=command_prompt)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
