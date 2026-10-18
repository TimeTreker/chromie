from __future__ import annotations

import json
import os
import sys
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

from agent.app import list_capabilities

ROOT = Path(__file__).resolve().parents[1]
SORIDORMI_MANIFEST = str(ROOT / "capabilities" / "soridormi.json")


def _run(*args: str) -> str:
    output = StringIO()
    with mock.patch.object(sys, "argv", ["list_capabilities", *args]), mock.patch.dict(
        os.environ, {"SORIDORMI_MCP_URL": "http://127.0.0.1:8000/mcp"}
    ), redirect_stdout(output):
        list_capabilities.main()
    return output.getvalue()


def test_runbook_listing_names_agents_and_model_visible_tools() -> None:
    text = _run("--manifest", SORIDORMI_MANIFEST)
    assert text.startswith("Agents:\n")
    assert "\nLLM-visible tools:\n" in text
    assert "soridormi." in text


def test_json_listing_is_the_registry_document() -> None:
    payload = json.loads(_run("--manifest", SORIDORMI_MANIFEST, "--json"))
    assert isinstance(payload, dict)
    assert payload


def test_llm_context_listing_is_nonempty() -> None:
    assert _run("--manifest", SORIDORMI_MANIFEST, "--llm-context", "--language", "en").strip()
