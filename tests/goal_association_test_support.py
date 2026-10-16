"""Shared fakes and goal builders for Goal Association tests."""

from __future__ import annotations


class FakeOllama:
    def __init__(self, payload):
        self.payload = payload
        self.prompts = []

    async def generate(self, prompt, **kwargs):
        self.prompts.append((prompt, kwargs))
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


def intent_goal(description: str, output_mode: str, **extra) -> dict:
    """GA fixture selects intent identities; descriptions/types come from UMI."""
    return {"source_responsibility_refs": ["r1"], "related_goal_ids": [],
            "supersedes_goal_ids": [], **extra}


def create_goals(*goals: dict) -> dict:
    return {
        "new_goals": [
            {"source_responsibility_refs": [ref],
             "related_goal_ids": item.get("related_goal_ids", []),
             "supersedes_goal_ids": item.get("supersedes_goal_ids", [])}
            for item in goals for ref in item.get("source_responsibility_refs", [])
        ],
        "cognitive_requests": [],
        "confidence": 1.0,
        "reason_summary": "No retained Goal matches the current Responsibility.",
    }
