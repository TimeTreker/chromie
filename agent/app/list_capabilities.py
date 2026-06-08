from __future__ import annotations

import argparse
import json

from .capabilities.loader import build_configured_registry


def main() -> None:
    parser = argparse.ArgumentParser(description="List Chromie's global MCP-ready capabilities.")
    parser.add_argument("--manifest", action="append", default=[], help="External capability bundle JSON, e.g. Soridormi export. May be repeated.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable registry JSON.")
    parser.add_argument("--llm-context", action="store_true", help="Emit concise LLM capability context.")
    parser.add_argument("--language", default="en", help="Language for --llm-context, e.g. en or zh.")
    args = parser.parse_args()

    configured = build_configured_registry(args.manifest)
    registry = configured.registry
    if args.json:
        print(json.dumps(registry.model_dump(), ensure_ascii=False, indent=2))
        return
    if args.llm_context:
        print(registry.llm_context(language=args.language))
        return

    print("Agents:")
    for agent in registry.list_agents():
        status = "available" if agent.status.available else f"unavailable: {agent.status.reason or 'unspecified'}"
        print(f"- {agent.agent_id}: {status}")
    print("\nLLM-visible tools:")
    for tool in registry.tools_for_llm():
        confirm = "requires confirmation" if tool.confirmation.required else "no confirmation"
        print(f"- {tool.name} [{tool.safety_class}; {confirm}]")


if __name__ == "__main__":
    main()
