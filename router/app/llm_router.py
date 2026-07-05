from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import httpx
from pydantic import ValidationError

from .fallback import fallback_decision
from .schema import RouteDecision, RouteRequest, finalize_decision


logger = logging.getLogger("chromie.router.llm")


ROUTE_NAMES = {
    "chat",
    "deep_thought",
    "robot_action",
    "tool",
    "memory",
    "clarify",
    "interrupt",
    "ignore",
}

DETERMINISTIC_ONLY_ROUTES = {"interrupt", "ignore"}
ROUTE_ITEM_PRIMARY_RANK = {
    "interrupt": 0,
    "robot_action": 1,
    "deep_thought": 2,
    "tool": 3,
    "memory": 4,
    "clarify": 5,
    "chat": 6,
    "ignore": 7,
}
PLACEHOLDER_CAPABILITY_INTENTS = {
    "capability",
    "capability:",
    "capability_id",
    "<capability_id>",
    "<exact capability_id>",
    "<exact skill_id>",
    "capability:<capability_id>",
    "capability:<exact capability_id>",
    "capability:<exact skill_id>",
}
_ROUTER_CONTEXT_OMIT_KEYS = {
    "candidate_capabilities",
    "common_ability_catalog",
    "common_ability_ids",
    "full_ability_catalog",
    "prompt_capabilities_common",
    "prompt_capabilities_all",
    "prompt_catalog_scope",
    "mind",
    "core_principles",
    "long_term_goals",
    "experience_tuning_policy",
    "conversation",
    "history",
}


def _extract_json_object(text: str) -> dict[str, Any]:
    """Parse JSON object from raw model text, tolerating markdown fences."""

    text = (text or "").strip()
    if not text:
        raise ValueError("empty model response")

    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)

    try:
        value = json.loads(text)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        raise ValueError("no JSON object in model response")

    value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise ValueError("model response JSON is not an object")
    return value


def _compact_candidate_capabilities(candidates: Any, *, limit: int = 8) -> list[dict[str, Any]]:
    if not isinstance(candidates, list):
        return []
    compact: list[dict[str, Any]] = []
    for item in candidates[:limit]:
        if not isinstance(item, dict):
            continue
        description = " ".join(str(item.get("description") or "").split())
        if len(description) > 160:
            description = description[:160].rstrip() + "..."
        compact.append(
            {
                "capability_id": str(item.get("capability_id") or ""),
                "route": str(item.get("route") or ""),
                "interaction_executable": bool(item.get("interaction_executable")),
                "available": item.get("available") is not False,
                "effects": list(item.get("effects") or [])[:4],
                "score": item.get("score"),
                "description": description,
            }
        )
    return compact


def _review_capabilities_from_request(request: RouteRequest) -> list[dict[str, Any]]:
    for key in (
        "common_ability_catalog",
        "prompt_capabilities_common",
        "full_ability_catalog",
        "prompt_capabilities_all",
    ):
        value = request.context.get(key, [])
        if isinstance(value, list) and value:
            return value
    return []


def _capability_ids_from_request(request: RouteRequest) -> set[str]:
    capability_ids: set[str] = set()
    for key in (
        "common_ability_catalog",
        "prompt_capabilities_common",
        "full_ability_catalog",
        "prompt_capabilities_all",
    ):
        value = request.context.get(key, [])
        if not isinstance(value, list):
            continue
        for item in value:
            if not isinstance(item, dict):
                continue
            capability_id = str(item.get("capability_id") or item.get("skill_id") or "").strip()
            if capability_id:
                capability_ids.add(capability_id)
    return capability_ids


def _known_capability_id(text: Any, capability_ids: set[str]) -> str:
    value = str(text or "").strip()
    if not value:
        return ""
    if value.startswith("capability:"):
        value = value.split(":", 1)[1].strip()
    return value if value in capability_ids else ""


def _capability_contract(item: dict[str, Any]) -> str:
    explicit = str(item.get("contract") or "").strip()
    if explicit:
        return explicit
    route = str(item.get("route") or "tool").strip() or "tool"
    effects = [str(effect) for effect in list(item.get("effects") or [])[:3] if effect]
    safety = str(item.get("safety_class") or "").strip()
    parts = [route]
    if effects:
        parts.append("+".join(effects))
    if safety:
        parts.append(safety)
    return ".".join(parts)


def _compact_prompt_capabilities(candidates: Any, *, limit: int = 96) -> list[dict[str, Any]]:
    if not isinstance(candidates, list):
        return []
    compact: list[dict[str, Any]] = []
    for item in candidates[:limit]:
        if not isinstance(item, dict):
            continue
        if item.get("prompt_tier_locked") is True:
            continue
        capability_id = str(item.get("capability_id") or item.get("skill_id") or "").strip()
        if not capability_id:
            continue
        description = " ".join(str(item.get("description") or "").split())
        if len(description) > 180:
            description = description[:180].rstrip() + "..."
        schema = item.get("input_schema") if isinstance(item.get("input_schema"), dict) else {}
        args: dict[str, Any] = {}
        properties = schema.get("properties") if isinstance(schema, dict) else {}
        if isinstance(properties, dict):
            for name, prop in list(properties.items())[:6]:
                if not isinstance(prop, dict):
                    continue
                arg: dict[str, Any] = {}
                for key in ("type", "enum", "minimum", "maximum", "default"):
                    if key in prop:
                        arg[key] = prop[key]
                args[str(name)] = arg
        compact.append(
            {
                "skill_id": capability_id,
                "contract": _capability_contract(item),
                "description": description,
                "safety": str(item.get("safety_class") or ""),
                "confirmation": bool(item.get("requires_confirmation", False)),
                "executable": bool(item.get("interaction_executable")),
                "args": args,
            }
        )
    return compact


def _bounded_json(value: Any, *, max_chars: int = 4000) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except TypeError:
        text = json.dumps(str(value), ensure_ascii=False)
    if len(text) > max_chars:
        return text[:max_chars].rstrip() + "..."
    return text


def _context_without_prompt_globals(context: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in (context or {}).items()
        if key not in _ROUTER_CONTEXT_OMIT_KEYS
    }


def _router_prompt_context(context: dict[str, Any]) -> dict[str, Any]:
    prompt_context = _context_without_prompt_globals(context)
    memory = prompt_context.get("session_memory")
    if isinstance(memory, dict):
        prompt_context["session_memory"] = {
            key: value
            for key, value in memory.items()
            if key not in {"recent_user_request", "recent_assistant_response"}
        }
    return prompt_context


def _router_fast_context_section(mind: Any) -> str:
    """Minimal context for the quick Router.

    The quick Router should decide whether a task needs the full mind profile;
    it should not always pay for worldview/lifeview/valueview tokens itself.
    Deepthinking and capability prompts still receive richer mind context.
    """

    identity = {}
    if isinstance(mind, dict) and isinstance(mind.get("identity"), dict):
        raw_identity = mind["identity"]
        identity = {
            "profile_id": mind.get("profile_id"),
            "version": mind.get("version"),
            "name": raw_identity.get("name"),
            "pronouns": raw_identity.get("pronouns"),
            "role": raw_identity.get("role") or raw_identity.get("description"),
        }
    return (
        "Fast Router Context:\n"
        f"{_bounded_json(identity or {'name': 'Chromie'}, max_chars=260)}\n"
        "The full owner-approved mind profile, worldview, lifeview, valueview, "
        "long-term goals, and core principles are available only to downstream "
        "full_mind/deepthought prompts. Do not reproduce or infer those details here.\n"
        "Your job is to mark each route item with the lightest safe context_profile:\n"
        "- fast_minimal for greetings, simple acknowledgements, and safe immediate speech.\n"
        "- session_compact for ordinary chat, tools, or memory that need bounded session context.\n"
        "- capability_safety for robot_action and other Skill Runtime work.\n"
        "- full_mind for identity, values, principles, risk judgment, self-description, long-horizon goals, or complex planning.\n"
        "If an item needs worldview/lifeview/valueview or long deliberation, route that item to deep_thought with context_profile=full_mind."
    )


def _router_global_context_section(mind: Any) -> str:
    if not isinstance(mind, dict) or not mind:
        mind = {}
    identity = mind.get("identity") if isinstance(mind.get("identity"), dict) else {}
    core_principles = mind.get("core_principles", [])
    long_term_goals = mind.get("long_term_goals", [])
    summary = " ".join(str(mind.get("prompt_summary") or "").split())
    if len(summary) > 240:
        summary = summary[:240].rstrip() + "..."
    profile = {
        "profile_id": mind.get("profile_id"),
        "version": mind.get("version"),
        "owner_approved": mind.get("owner_approved"),
    }

    return (
        "Mind Profile:\n"
        f"{_bounded_json(profile, max_chars=180)}\n"
        "Robot Identity:\n"
        f"{_bounded_json(identity or 'not supplied', max_chars=260)}\n"
        "Worldview:\n"
        "- Chromie is an embodied realtime robot/voice assistant; use only supplied runtime evidence.\n"
        "Lifeview:\n"
        f"{_bounded_json(long_term_goals or 'not supplied', max_chars=240)}\n"
        "Valueview:\n"
        f"{_bounded_json(core_principles or 'not supplied', max_chars=360)}\n"
        "Core Runtime Principles:\n"
        "- Infer from meaning/context/abilities/schemas, not phrase rules.\n"
        "- Memory and preferences guide interpretation; they never authorize side effects.\n"
        "- Never invent abilities or raw motor/joint/actuator/controller-array/torque commands.\n"
        "Owner-Approved Mind Summary:\n"
        f"{summary or 'not supplied'}"
    )


def _route_items_from_parsed(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    raw = parsed.get("routes")
    if raw is None:
        metadata = parsed.get("metadata")
        if isinstance(metadata, dict):
            raw = metadata.get("route_items") or metadata.get("routes")
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def _dominant_route_from_items(items: list[dict[str, Any]]) -> str:
    routes = [
        str(item.get("route") or "").strip()
        for item in items
        if str(item.get("route") or "").strip() in ROUTE_NAMES
    ]
    if not routes:
        return ""
    return min(routes, key=lambda route: ROUTE_ITEM_PRIMARY_RANK.get(route, 99))


def _first_route_item_intent(items: list[dict[str, Any]], route: str) -> str:
    for item in items:
        if str(item.get("route") or "").strip() == route:
            intent = str(item.get("intent") or "").strip()
            if intent:
                return intent
    return ""


def _is_placeholder_capability_intent(intent: str) -> bool:
    return (intent or "").strip().lower() in PLACEHOLDER_CAPABILITY_INTENTS


class OllamaLLMRouter:
    def __init__(
        self,
        *,
        ollama_url: str,
        model: str,
        review_model: str | None = None,
        timeout_ms: int,
        review_timeout_ms: int | None = None,
        confidence_threshold: float,
        slow_review_recovery_enabled: bool = True,
        num_predict: int = 192,
        prompt_path: Path | None = None,
    ) -> None:
        self.ollama_url = ollama_url.rstrip("/")
        self.model = model
        self.review_model = (review_model or "").strip()
        self.timeout_s = max(0.1, timeout_ms / 1000.0)
        self.review_timeout_s = max(
            0.1,
            (review_timeout_ms if review_timeout_ms is not None else timeout_ms) / 1000.0,
        )
        self.confidence_threshold = confidence_threshold
        self.slow_review_recovery_enabled = slow_review_recovery_enabled
        self.num_predict = max(32, num_predict)
        self.prompt_path = prompt_path or Path(__file__).parent / "prompts" / "router_system.txt"

    def load_system_prompt(self) -> str:
        try:
            return self.prompt_path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            logger.warning("Router system prompt not found: %s", self.prompt_path)
            return (
                "You are Chromie's routing classifier. Return only a JSON object "
                "matching the provided schema."
            )

    def build_user_prompt(self, request: RouteRequest) -> str:
        prompt_capabilities = request.context.get("common_ability_catalog", [])
        if not prompt_capabilities:
            prompt_capabilities = request.context.get("prompt_capabilities_common", [])
        compact_prompt_capabilities = _compact_prompt_capabilities(prompt_capabilities)
        common_ability_ids = [
            item["skill_id"]
            for item in compact_prompt_capabilities
            if item.get("skill_id")
        ]
        common_ability_catalog_json = _bounded_json(
            compact_prompt_capabilities,
            max_chars=7200,
        )
        mind = request.context.get("mind", {})
        session_context = _router_prompt_context(request.context)
        context_json = _bounded_json(session_context, max_chars=500)
        return (
            "Global Context Group:\n"
            f"{_router_fast_context_section(mind)}\n\n"
            "Session Context Group:\n"
            f"language={request.language or 'auto'} sid={request.sid or ''}\n"
            f"Bounded session, memory, task, and robot/world context JSON: {context_json}\n\n"
            "Current Job:\n"
            "Act as Chromie's quick intent router and fast lane splitter. Return one compatibility route plus optional routes[] items; do not answer, execute, or authorize side effects. "
            "Infer from meaning/context/abilities/schemas and understand intent broadly before checking the catalog; the catalog constrains executable actions, not meaning. "
            "Choose route deep_thought for complex reasoning, design, debugging, implementation planning, or when the request needs deeper thought, task-session creation, or task-session continuation. "
            "Choosing route=deep_thought is only delegation; do not perform or reveal reasoning inside the router. "
            "For mixed utterances, split independent work into routes[] items so chat, memory, deep_thought, tools, and robot_action can follow separate policies. "
            "Use context_profile on each item to decide whether the downstream task needs no mind context, compact session context, capability safety context, or full mind/worldview/lifeview/valueview context. "
            "Return calibrated low confidence when uncertain.\n\n"
            "Task Context Group:\n"
            f"Latest user input: {request.text}\n"
            "Output Template Preview:\n"
            "- Chat/fact/greeting: {\"route\":\"chat\",\"intent\":\"general_conversation\",\"confidence\":0.9}\n"
            "- Fast greeting with direct speech: {\"route\":\"chat\",\"intent\":\"greeting\",\"confidence\":0.9,\"routes\":[{\"route\":\"chat\",\"intent\":\"greeting\",\"confidence\":0.9,\"lane\":\"immediate_speech\",\"context_profile\":\"fast_minimal\",\"direct_to_tts\":true,\"text\":\"Hi, I'm here.\"}]}\n"
            "- Mixed chat/memory/deepthought: {\"route\":\"deep_thought\",\"intent\":\"mixed_request\",\"confidence\":0.82,\"routes\":[{\"route\":\"chat\",\"intent\":\"greeting\",\"confidence\":0.95,\"lane\":\"immediate_speech\",\"context_profile\":\"fast_minimal\",\"direct_to_tts\":true,\"text\":\"Hi, I'm here.\"},{\"route\":\"memory\",\"intent\":\"remember_user_preference\",\"confidence\":0.86,\"lane\":\"post_turn\",\"context_profile\":\"session_compact\"},{\"route\":\"deep_thought\",\"intent\":\"plan_complex_task\",\"confidence\":0.78,\"lane\":\"deepthought\",\"context_profile\":\"full_mind\",\"requires_mind\":true}]}\n"
            "- Single listed skill: {\"route\":\"robot_action\",\"intent\":\"capability:<exact skill_id>\",\"confidence\":0.9}\n"
            "- Multiple listed skills: {\"route\":\"robot_action\",\"intent\":\"compound_common_catalog_task\",\"confidence\":0.9,\"actions\":[{\"capability_id\":\"<exact skill_id>\",\"args\":{},\"sequence\":0,\"timing\":\"sequential\",\"confidence\":0.9}]}\n"
            "- Missing ability: {\"route\":\"deep_thought\",\"intent\":\"missing_or_unsupported_ability\",\"confidence\":0.6,\"metadata\":{\"desired_abilities\":[{\"ability_id\":\"...\",\"intent\":\"...\",\"status\":\"missing_ability\",\"confidence\":0.9,\"reason\":\"...\"}]}}\n"
            "- Clarify: {\"route\":\"clarify\",\"intent\":\"clarify_target_or_skill\",\"confidence\":0.7}\n"
            "The top-level route is a compatibility primary route. Use routes[] for multiple independent policy lanes; use actions[] only for ordered listed skills inside a robot_action route item.\n"
            f"Common ability IDs: {_bounded_json(common_ability_ids, max_chars=1400)}\n"
            f"Common Ability Catalog JSON: {common_ability_catalog_json}\n"
            "Decision checks: use semantic meaning, not phrase rules. If the user asks Chromie to physically perform a listed body/head/gaze/motion/expression skill now, return robot_action using that exact skill. "
            "A polite ability-shaped request is still robot_action when it asks for a listed physical skill now. "
            "Speech-only conversation, greetings, identity/status questions, facts, jokes, stories, songs, and spoken performance are chat unless physical/tool action is requested. "
            "Only put direct_to_tts=true on a chat route item when the text is a safe short greeting, acknowledgement, or thinking prelude; do not use it for facts, advice, identity, values, memory writes, tool results, or action completion claims. "
            "When speech is part of a physical request, treat the speech as a skill task with skill_id chromie.speak if it appears in the compact skill catalog. "
            "Factual agreement/disagreement is chat: questions about the Moon, Sun, shape, temperature, or other world knowledge are not deep_thought or robot_action even if ability candidates share words such as round, turn, left, right, walk, or move; the quick router routes common-fact questions to chat. "
            "Use working memory, current task context, and recent action history for follow-ups, but never as authorization for side effects. "
            "Do not return interrupt or ignore for ordinary body commands; the deterministic emergency/noise filter already ran. "
            "If no listed skill fits clearly, choose deep_thought or clarify and include metadata.desired_abilities with status missing_ability when useful.\n\n"
            "Cost Function:\n"
            "Prefer the smallest safe downstream action surface, honest capability boundaries, chat for speech-only/factual claims, deep_thought only for complex planning, and clarify for ambiguity. "
            "Prefer supported interaction-executable skill IDs over generic robot_action. Preserve unsupported desired abilities as non-executable proposals. "
            "For compound listed-skill requests, preserve each requested skill in actions instead of collapsing to the first skill. Each proposed action has its own confidence; if any required action is below confidence threshold, delegate the whole plan to deep_thought with truthful speak_first.\n\n"
            "Semantic Examples:\n"
            "- If the user says hello or simple small talk, return chat with a routes[] item using lane=immediate_speech, context_profile=fast_minimal, direct_to_tts=true, and a short safe text.\n"
            "- If the utterance contains a greeting plus a memory update plus a complex planning request, return top-level route=deep_thought and three routes[] items: immediate chat, post_turn memory, and deepthought full_mind.\n"
            "- If the task needs identity, values, principles, safety judgment, worldview/lifeview/valueview, or long-term goal reasoning, route that item to deep_thought with context_profile=full_mind and requires_mind=true.\n"
            "- If the user asks whether you agree with a common factual claim about the Moon, Sun, shape, heat, or similar world knowledge, return {\"route\":\"chat\",\"intent\":\"factual_agreement\",\"confidence\":0.9}.\n"
            "- If the user asks Chromie to walk, turn, nod, shake her head, blink, or perform another listed physical/expression skill now, return robot_action with intent capability:<exact skill_id>.\n"
            "- If the user asks for several listed skills, such as walking, speaking, and blinking, return robot_action with actions ordered by the requested task sequence; use chromie.speak for the spoken part and include args.text.\n"
            "- If the user asks for a physical/social ability you understand but it is not in the compact skill catalog, return deep_thought or clarify and include metadata.desired_abilities, for example {\"ability_id\":\"social.blink_eyes\",\"intent\":\"blink eyes\",\"status\":\"missing_ability\",\"confidence\":0.9,\"reason\":\"no executable blink skill is in the compact skill catalog\"}.\n"
            "- If no listed skill fits clearly or you are not confident, return deep_thought with a brief speak_first that tells the user you need a moment. The speak_first must be truthful and must not claim execution.\n"
            "- Generalize these examples from meaning; do not make phrase rules.\n\n"
            "Output Contract:\n"
            "Return one compact JSON object matching one of the templates above. Required compatibility keys: route, intent, confidence. You may also output routes[] for independent route items. "
            "Valid routes: chat, deep_thought, robot_action, tool, memory, clarify, interrupt, ignore. "
            "Omit agents, metadata, candidate_capabilities, and explanations unless they change downstream routing. "
            "Each routes[] item may include route, intent, confidence, lane, context_profile, requires_mind, direct_to_tts, text, skill_id, args, actions, reason, and metadata. "
            "Allowed lanes: immediate_speech, conversation, post_turn, deepthought, skill_runtime, tool, deterministic_control, none. "
            "Allowed context_profile values: none, fast_minimal, session_compact, capability_safety, full_mind. "
            "metadata.desired_abilities may contain understood but non-executable ability proposals; these are not executable actions. "
            "Do not output chain-of-thought, hidden reasoning, analysis, progress text, scratchpad text, markdown, or any text outside the JSON object. "
            "For selected robot_action use intent capability:<exact skill_id> copied from the compact skill catalog. Never output placeholder intents such as capability or capability:<exact capability_id>. "
            "For compound or parameterized listed-skill robot_action, include actions as an ordered array of objects: {\"capability_id\":\"<exact skill_id>\",\"args\":{},\"sequence\":0,\"timing\":\"sequential|parallel\",\"confidence\":0.0}. "
            "Each action capability_id must be copied exactly from the compact skill catalog. For chromie.speak, args must include a short natural text field. "
            "Never put missing or planned abilities in actions; put them in metadata.desired_abilities and choose deep_thought or clarify. "
            "Set action confidence from semantic fit and argument confidence. "
            "If you include actions, use a semantic intent such as compound_common_catalog_task instead of a placeholder capability intent. "
            "For uncertain deep_thought handoff, you may include speak_first with one short user-facing sentence in the user's language, such as a natural request for a moment to think. "
            "Speak_first must sound like Chromie herself: an embodied robot with natural, human-like social warmth, not a program, programme, backend, software process, or language model. "
            "Do not use speak_first to claim physical action, tool results, memory writes, or completion. "
            "For chat/clarify/interrupt/ignore, do not set capability intent. For deep_thought, use a short semantic intent such as deep_thought_complex_reasoning. Confidence is 0.0-1.0."
        )

    def build_payload(self, request: RouteRequest, *, relaxed_json: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "stream": False,
            "think": False,
            "messages": [
                {"role": "system", "content": self.load_system_prompt()},
                {"role": "user", "content": self.build_user_prompt(request)},
            ],
            "options": {
                "temperature": 0,
                "top_p": 0.9,
                "num_predict": self.num_predict,
            },
        }
        payload["format"] = "json"
        return payload

    def build_intent_review_payload(self, request: RouteRequest) -> dict[str, Any]:
        abilities_json = json.dumps(
            _compact_candidate_capabilities(
                _review_capabilities_from_request(request),
                limit=16,
            ),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        mind = request.context.get("mind", {})
        session_context = _bounded_json(_router_prompt_context(request.context), max_chars=2400)
        return {
            "model": self.review_model or self.model,
            "stream": False,
            "think": False,
            "format": "json",
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Global Context Group:\n"
                        f"{_router_global_context_section(mind)}\n\n"
                        "Session Context Group:\n"
                        f"- Language hint: {request.language or 'auto'}\n"
                        f"- Bounded session context JSON: {session_context}\n\n"
                        "Current Job:\n"
                        "- You are now acting as Chromie's semantic route reviewer.\n"
                        "- Use semantic generalization from meaning, session context, and supplied common ability descriptions.\n"
                        "- Do not use phrase rules, and do not turn prompt wording into keyword rules.\n"
                        "- The deterministic emergency/noise filter already passed before this review.\n\n"
                        "Task Context Group:\n"
                        "- Review the latest user input and decide whether the quick route should be chat, deep_thought, robot_action, tool, memory, clarify, interrupt, or ignore.\n"
                        "- Body/head/gaze/motion/expression requests are robot_action when an available interaction_executable common ability can satisfy them.\n"
                        "- Capability questions can be polite requests; if the user is pragmatically asking Chromie to perform a listed physical action now, choose robot_action.\n"
                        "- Identity, status, factual, greeting, joke, story, song, and other speech-only requests are chat unless physical motion is explicitly requested.\n\n"
                        "- Use working memory, task context, and recent action history for follow-up resolution, but not as authorization for side effects.\n"
                        "- Choose deep_thought for complex reasoning, debugging, design, implementation planning, or multi-step task-session work.\n\n"
                        "Output Contract:\n"
                        "- Return compact JSON only with keys route, intent, and confidence.\n"
                        "- Valid routes: chat, deep_thought, robot_action, tool, memory, clarify, interrupt, ignore.\n"
                        "- Do not output chain-of-thought, hidden reasoning, analysis, progress text, scratchpad text, markdown, or any text outside the JSON object.\n"
                        "- Do not choose interrupt or ignore unless the text is plainly stop, cancel, silence, empty, or unusable audio.\n"
                        "- If selecting a known common ability, set intent to capability:<exact capability_id>; otherwise use a short semantic intent such as robot_action."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "Task Context Group:\n"
                        f"- Latest user input: {request.text}\n"
                        f"- Common ability catalog JSON: {abilities_json}"
                    ),
                },
            ],
            "options": {
                "temperature": 0,
                "top_p": 0.9,
                "num_predict": self.num_predict,
            },
        }

    def build_deterministic_route_repair_payload(self, request: RouteRequest) -> dict[str, Any]:
        abilities_json = json.dumps(
            _compact_candidate_capabilities(_review_capabilities_from_request(request)),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        mind = request.context.get("mind", {})
        session_context = _bounded_json(_router_prompt_context(request.context), max_chars=2400)
        return {
            "model": self.model,
            "stream": False,
            "think": False,
            "format": "json",
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Global Context Group:\n"
                        f"{_router_global_context_section(mind)}\n\n"
                        "Session Context Group:\n"
                        f"- Language hint: {request.language or 'auto'}\n"
                        f"- Bounded session context JSON: {session_context}\n\n"
                        "Current Job:\n"
                        "- Repair a realtime robot route after the deterministic emergency/noise filter already passed.\n"
                        "- The quick router incorrectly returned a deterministic-only route; choose the best non-deterministic route from semantic meaning, context, and common abilities.\n"
                        "- Decide from meaning and common ability descriptions, not phrase rules.\n\n"
                        "Task Context Group:\n"
                        "- If the user is asking Chromie to perform an available interaction_executable physical capability now, choose robot_action.\n"
                        "- Speech-only requests are chat.\n"
                        "- Use deep_thought for complex reasoning or planning that should leave the quick route path.\n\n"
                        "- Use task context and recent action history for follow-ups, but never as standalone authorization.\n\n"
                        "Output Contract:\n"
                        "- Return compact JSON only with keys route, intent, and confidence.\n"
                        "- Valid routes: chat, deep_thought, robot_action, tool, memory, clarify.\n"
                        "- Do not output chain-of-thought, hidden reasoning, analysis, progress text, scratchpad text, markdown, or any text outside the JSON object.\n"
                        "- Do not use interrupt or ignore.\n"
                        "- For a selected capability, set intent to capability:<exact capability_id>.\n"
                        "- Confidence is semantic routing confidence; use at least 0.72 when the request clearly maps to a common ability."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "Task Context Group:\n"
                        f"- Latest user input: {request.text}\n"
                        f"- Common ability catalog JSON: {abilities_json}"
                    ),
                },
            ],
            "options": {
                "temperature": 0,
                "top_p": 0.9,
                "num_predict": self.num_predict,
            },
        }

    def build_placeholder_capability_repair_payload(self, request: RouteRequest) -> dict[str, Any]:
        abilities_json = _bounded_json(
            _compact_candidate_capabilities(_review_capabilities_from_request(request)),
            max_chars=1800,
        )
        session_context = _bounded_json(_context_without_prompt_globals(request.context), max_chars=1400)
        return {
            "model": self.model,
            "stream": False,
            "think": False,
            "format": "json",
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Current Job:\n"
                        "- Repair a malformed route for Chromie after the emergency/noise filter already passed.\n"
                        "- The quick router returned robot_action with a placeholder capability intent instead of a real capability ID.\n"
                        "- Decide from semantic meaning, bounded context, and common abilities, not phrase rules.\n\n"
                        "Task Context Group:\n"
                        "- Speech-only, greeting, identity/status, factual, joke, story, song, and spoken performance requests are chat unless physical/tool action is explicitly requested.\n"
                        "- If the user is asking Chromie to perform an available interaction_executable physical capability now, choose robot_action.\n"
                        "- Use deep_thought for complex reasoning or planning.\n\n"
                        "- Use working memory, task context, and recent action history to resolve follow-ups, but not to authorize side effects.\n\n"
                        "Output Contract:\n"
                        "- Return compact JSON only with keys route, intent, and confidence.\n"
                        "- Valid routes: chat, deep_thought, robot_action, tool, memory, clarify.\n"
                        "- Do not output chain-of-thought, hidden reasoning, analysis, progress text, scratchpad text, markdown, or any text outside the JSON object.\n"
                        "- For robot_action with a selected skill, set intent to capability:<exact capability_id> from the common ability catalog.\n"
                        "- Never return placeholder intents such as capability or capability:<exact capability_id>.\n"
                        "- Confidence is semantic routing confidence."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Latest user input: {request.text}\n"
                        f"Language hint: {request.language or 'auto'}\n"
                        f"Bounded session context JSON: {session_context}\n"
                        f"Common ability catalog JSON: {abilities_json}"
                    ),
                },
            ],
            "options": {
                "temperature": 0,
                "top_p": 0.9,
                "num_predict": self.num_predict,
            },
        }

    def build_post_interrupt_review_payload(
        self,
        request: RouteRequest,
        interrupt_decision: RouteDecision,
    ) -> dict[str, Any]:
        abilities_json = _bounded_json(
            _compact_candidate_capabilities(_review_capabilities_from_request(request)),
            max_chars=1800,
        )
        mind = request.context.get("mind", {})
        session_context = _bounded_json(_context_without_prompt_globals(request.context), max_chars=1800)
        interrupt_json = _bounded_json(
            {
                "route": interrupt_decision.route,
                "intent": interrupt_decision.intent,
                "confidence": interrupt_decision.confidence,
                "reason": interrupt_decision.reason,
                "source": interrupt_decision.source,
            },
            max_chars=500,
        )
        return {
            "model": self.review_model or self.model,
            "stream": False,
            "think": False,
            "format": "json",
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Global Context Group:\n"
                        f"{_router_global_context_section(mind)}\n\n"
                        "Session Context Group:\n"
                        f"- Language hint: {request.language or 'auto'}\n"
                        f"- Bounded session context JSON: {session_context}\n"
                        f"- Already-applied emergency-filter decision JSON: {interrupt_json}\n\n"
                        "Current Job:\n"
                        "- You are Chromie's post-interrupt semantic reviewer.\n"
                        "- The host has already applied the deterministic interrupt/cancel lane immediately for safety.\n"
                        "- Your job is only to confirm that interpretation or propose the correct non-interrupt route if the text was misheard/misread.\n"
                        "- Decide from meaning, context, and supplied abilities; do not create phrase rules.\n\n"
                        "Task Context Group:\n"
                        "- Choose interrupt when the user truly asked to stop, cancel, pause, be quiet, or halt current work.\n"
                        "- Choose a non-interrupt route when the text merely mentions stop, uses stop in another meaning, or asks for a different chat/tool/memory/body task.\n"
                        "- If correcting to robot_action, use intent capability:<exact capability_id> when a supplied common ability clearly fits.\n"
                        "- Physical actions are still only proposals; downstream Agent and Skill Runtime must validate and confirm them.\n\n"
                        "Output Contract:\n"
                        "- Return one compact RouteDecision JSON object.\n"
                        "- Valid routes: chat, deep_thought, robot_action, tool, memory, clarify, interrupt, ignore.\n"
                        "- Do not output chain-of-thought, hidden reasoning, analysis, progress text, scratchpad text, markdown, or any text outside the JSON object.\n"
                        "- If the emergency interpretation was correct, return route=interrupt and intent=stop_current_output.\n"
                        "- If it was a misunderstanding, return the corrected non-interrupt route with confidence >= 0.72 when clear.\n"
                        "- For a correction, speak_first may contain one brief apology/correction sentence, but must not claim a physical action or tool side effect has executed."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "Task Context Group:\n"
                        f"- Latest user input: {request.text}\n"
                        f"- Common ability catalog JSON: {abilities_json}"
                    ),
                },
            ],
            "options": {
                "temperature": 0,
                "top_p": 0.9,
                "num_predict": max(128, self.num_predict),
            },
        }

    async def _chat(self, payload: dict[str, Any]) -> dict[str, Any]:
        timeout_s = self.timeout_s
        if self.review_model and str(payload.get("model") or "") == self.review_model:
            timeout_s = self.review_timeout_s
        async with httpx.AsyncClient(timeout=timeout_s, trust_env=False) as client:
            response = await client.post(f"{self.ollama_url}/api/chat", json=payload)
            response.raise_for_status()
            return response.json()

    def _decision_from_response(self, request: RouteRequest, data: dict[str, Any]) -> RouteDecision:
        content = data.get("message", {}).get("content", "")
        parsed = _extract_json_object(content)
        route_items = _route_items_from_parsed(parsed)
        dominant_route = _dominant_route_from_items(route_items)
        if "route" not in parsed and dominant_route:
            parsed["route"] = dominant_route
            item_intent = _first_route_item_intent(route_items, dominant_route)
            if item_intent and "intent" not in parsed:
                parsed["intent"] = item_intent
            parsed["reason"] = (
                f"{parsed.get('reason')}; " if parsed.get("reason") else ""
            ) + "LLM returned route_items; router selected compatibility route"
        if route_items:
            metadata = parsed.get("metadata")
            if not isinstance(metadata, dict):
                metadata = {}
            metadata.setdefault("route_items", route_items)
            parsed["metadata"] = metadata
        route_from_intent = str(parsed.get("intent") or "").strip()
        supplied_capability_ids = _capability_ids_from_request(request)
        route_value = str(parsed.get("route") or "").strip()
        routed_capability_id = _known_capability_id(route_value, supplied_capability_ids)
        intent_capability_id = _known_capability_id(route_from_intent, supplied_capability_ids)
        if "route" not in parsed and route_from_intent in ROUTE_NAMES:
            parsed["route"] = route_from_intent
            parsed["reason"] = (
                f"{parsed.get('reason')}; " if parsed.get("reason") else ""
            ) + "LLM returned intent-only route JSON; router normalized route"
        elif "route" not in parsed and intent_capability_id:
            parsed["route"] = "robot_action"
            parsed["intent"] = f"capability:{intent_capability_id}"
            parsed["reason"] = (
                f"{parsed.get('reason')}; " if parsed.get("reason") else ""
            ) + "LLM returned intent-only skill JSON; router normalized skill route"
        elif route_value and route_value not in ROUTE_NAMES and (
            routed_capability_id or intent_capability_id
        ):
            selected_capability_id = routed_capability_id or intent_capability_id
            parsed["route"] = "robot_action"
            parsed["intent"] = f"capability:{selected_capability_id}"
            parsed["reason"] = (
                f"{parsed.get('reason')}; " if parsed.get("reason") else ""
            ) + "LLM returned skill id in route field; router normalized skill route"
        if "confidence" not in parsed and parsed.get("route") not in {"interrupt", "ignore"}:
            parsed["confidence"] = max(0.72, self.confidence_threshold)
            parsed["reason"] = (
                f"{parsed.get('reason')}; " if parsed.get("reason") else ""
            ) + "LLM returned route-only JSON; router applied default confidence"
        decision = RouteDecision.model_validate(parsed)
        return finalize_decision(decision, request, source="llm")

    async def _review_route_only_robot_action(
        self,
        request: RouteRequest,
        decision: RouteDecision,
    ) -> RouteDecision:
        if not self.slow_review_recovery_enabled or not self.review_model:
            return decision
        if decision.route != "robot_action" or decision.intent.startswith("capability:") or decision.actions:
            return decision

        try:
            reviewed = await self._chat(self.build_intent_review_payload(request))
            reviewed_decision = self._decision_from_response(request, reviewed)
        except Exception as exc:
            raw_content = ""
            if isinstance(locals().get("reviewed"), dict):
                raw_content = str(reviewed.get("message", {}).get("content") or "")
            logger.warning(
                "LLM review model intent check failed: %s raw=%r",
                exc,
                raw_content[:240],
            )
            return decision

        if reviewed_decision.route != "robot_action":
            reviewed_decision.reason = (
                f"{reviewed_decision.reason}; " if reviewed_decision.reason else ""
            ) + f"review_model:{self.review_model} overrode underspecified robot_action"
            logger.info(
                "LLM review model changed underspecified robot_action to %s",
                reviewed_decision.route,
            )
            return reviewed_decision
        if (
            reviewed_decision.intent.startswith("capability:")
            or reviewed_decision.actions
            or (
                reviewed_decision.intent
                and reviewed_decision.intent not in {"unknown", "robot_action"}
                and not _is_placeholder_capability_intent(reviewed_decision.intent)
            )
        ):
            reviewed_decision.reason = (
                f"{reviewed_decision.reason}; " if reviewed_decision.reason else ""
            ) + f"review_model:{self.review_model} selected exact skill for underspecified robot_action"
            logger.info(
                "LLM review model completed underspecified robot_action as %s",
                reviewed_decision.intent,
            )
            return reviewed_decision
        return decision

    async def _review_ambiguous_deep_thought(
        self,
        request: RouteRequest,
        decision: RouteDecision,
    ) -> RouteDecision:
        if not self.slow_review_recovery_enabled or not self.review_model:
            return decision
        if decision.route != "deep_thought":
            return decision
        if decision.reason or decision.intent not in {"", "unknown"}:
            return decision
        try:
            reviewed = await self._chat(self.build_intent_review_payload(request))
            reviewed_decision = self._decision_from_response(request, reviewed)
        except Exception as exc:
            logger.warning("LLM review model ambiguous deep_thought check failed: %s", exc)
            return decision
        if (
            reviewed_decision.route == "deep_thought"
            and reviewed_decision.intent in {"", "unknown"}
            and not reviewed_decision.reason
        ):
            return decision
        if reviewed_decision.route not in DETERMINISTIC_ONLY_ROUTES:
            reviewed_decision.reason = (
                f"{reviewed_decision.reason}; " if reviewed_decision.reason else ""
            ) + f"review_model:{self.review_model} reviewed ambiguous deep_thought"
            logger.info(
                "LLM review model changed ambiguous deep_thought to %s/%s",
                reviewed_decision.route,
                reviewed_decision.intent,
            )
            return reviewed_decision
        return decision

    async def _recover_deterministic_only_decision(
        self,
        request: RouteRequest,
        decision: RouteDecision,
    ) -> RouteDecision:
        reason_prefix = (
            f"quick router returned deterministic-only route {decision.route} "
            "after deterministic emergency/noise filter did not match"
        )
        if not self.slow_review_recovery_enabled:
            logger.info("%s; slow repair disabled; using safe chat fallback", reason_prefix)
            return fallback_decision(
                request,
                reason=f"{reason_prefix}; slow repair disabled",
            )
        if self.slow_review_recovery_enabled and self.review_model:
            try:
                reviewed = await self._chat(self.build_intent_review_payload(request))
                reviewed_decision = self._decision_from_response(request, reviewed)
            except Exception as exc:
                logger.warning("LLM review model deterministic-only recovery failed: %s", exc)
            else:
                if reviewed_decision.route not in DETERMINISTIC_ONLY_ROUTES:
                    if reviewed_decision.confidence >= self.confidence_threshold:
                        reviewed_decision.reason = (
                            f"{reviewed_decision.reason}; " if reviewed_decision.reason else ""
                        ) + f"{reason_prefix}; review_model:{self.review_model} recovered quick-router mistake"
                        logger.info(
                            "LLM review model recovered invalid deterministic-only route %s to %s",
                            decision.route,
                            reviewed_decision.route,
                        )
                        return reviewed_decision
                    logger.info(
                        "LLM review model returned low-confidence recovery %.2f for invalid %s; trying fast repair",
                        reviewed_decision.confidence,
                        decision.route,
                    )
        try:
            repaired = await self._chat(self.build_deterministic_route_repair_payload(request))
            repaired_decision = self._decision_from_response(request, repaired)
        except Exception as exc:
            logger.warning("LLM fast route repair failed: %s", exc)
        else:
            if repaired_decision.route not in DETERMINISTIC_ONLY_ROUTES:
                repaired_decision.reason = (
                    f"{repaired_decision.reason}; " if repaired_decision.reason else ""
                ) + f"{reason_prefix}; fast_model:{self.model} repaired quick-router mistake"
                logger.info(
                    "LLM fast repair recovered invalid deterministic-only route %s to %s",
                    decision.route,
                    repaired_decision.route,
                )
                return repaired_decision
        logger.info(
            "LLM router returned invalid deterministic-only route %s after priority filter; using safe chat fallback",
            decision.route,
        )
        return fallback_decision(request, reason=reason_prefix)

    async def _recover_placeholder_capability_decision(
        self,
        request: RouteRequest,
        decision: RouteDecision,
    ) -> RouteDecision:
        reason_prefix = (
            "quick router returned robot_action with placeholder capability intent "
            f"{decision.intent!r}"
        )
        if not self.slow_review_recovery_enabled:
            logger.info("%s; slow repair disabled; using safe chat fallback", reason_prefix)
            return fallback_decision(
                request,
                reason=f"{reason_prefix}; slow repair disabled",
            )
        try:
            repaired = await self._chat(self.build_placeholder_capability_repair_payload(request))
            repaired_decision = self._decision_from_response(request, repaired)
        except Exception as exc:
            logger.warning("LLM placeholder capability repair failed: %s", exc)
        else:
            if (
                repaired_decision.route not in DETERMINISTIC_ONLY_ROUTES
                and not _is_placeholder_capability_intent(repaired_decision.intent)
            ):
                repaired_decision.reason = (
                    f"{repaired_decision.reason}; " if repaired_decision.reason else ""
                ) + f"{reason_prefix}; fast_model:{self.model} repaired placeholder capability intent"
                logger.info(
                    "LLM fast repair recovered placeholder capability intent to %s/%s",
                    repaired_decision.route,
                    repaired_decision.intent,
                )
                return repaired_decision
        logger.info("%s; using safe chat fallback", reason_prefix)
        return fallback_decision(request, reason=reason_prefix)

    async def review_after_priority_interrupt(
        self,
        request: RouteRequest,
        interrupt_decision: RouteDecision,
    ) -> RouteDecision:
        data = await self._chat(
            self.build_post_interrupt_review_payload(request, interrupt_decision)
        )
        decision = self._decision_from_response(request, data)
        if decision.route == "interrupt":
            decision.intent = "stop_current_output"
            decision.reason = (
                f"{decision.reason}; " if decision.reason else ""
            ) + "post-interrupt review confirmed deterministic interrupt"
            return decision
        decision.reason = (
            f"{decision.reason}; " if decision.reason else ""
        ) + "post-interrupt review corrected deterministic interrupt"
        return decision

    def _low_confidence_deep_thought_decision(
        self,
        request: RouteRequest,
        decision: RouteDecision,
        *,
        reason_prefix: str | None = None,
    ) -> RouteDecision:
        candidates = decision.candidate_capabilities
        if not candidates:
            raw_candidates = request.context.get("common_ability_catalog", [])
            if not raw_candidates:
                raw_candidates = request.context.get("prompt_capabilities_common", [])
            if not raw_candidates:
                raw_candidates = request.context.get("full_ability_catalog", [])
            if not raw_candidates:
                raw_candidates = request.context.get("prompt_capabilities_all", [])
            candidates = raw_candidates if isinstance(raw_candidates, list) else []
        reason_parts = [
            reason_prefix
            or f"quick router confidence {decision.confidence:.2f} below threshold {self.confidence_threshold:.2f}",
            f"quick_route={decision.route}",
            f"quick_intent={decision.intent}",
        ]
        if decision.reason:
            reason_parts.append(f"quick_reason={decision.reason}")
        inherited_metadata = {
            key: value
            for key, value in (decision.metadata or {}).items()
            if key
            not in {
                "route_items",
                "route_item_count",
                "route_stage_outputs",
                "task_list",
                "task_proposals",
                "route_merge",
            }
        }
        return finalize_decision(
            RouteDecision(
                route="deep_thought",
                agents=["deepthinking_agent", "speaker_agent"],
                intent="deep_thought_low_confidence",
                confidence=decision.confidence,
                language=decision.language or request.language or "auto",
                priority=decision.priority,
                speak_first=decision.speak_first,
                needs_agent=True,
                should_speak=True,
                candidate_capabilities=candidates,
                reason="; ".join(reason_parts),
                source="llm",
                metadata={
                    **inherited_metadata,
                    "thinking_ack_allowed": bool(decision.speak_first),
                    "thinking_ack_source": (
                        "quick_llm_speak_first" if decision.speak_first else "none"
                    ),
                },
            ),
            request,
            source="llm",
        )

    async def route(self, request: RouteRequest) -> RouteDecision:
        payload = self.build_payload(request)

        try:
            data = await self._chat(payload)
        except Exception as exc:
            logger.warning("Ollama router request failed: %s: %s", type(exc).__name__, exc)
            if self.slow_review_recovery_enabled and self.review_model:
                try:
                    reviewed = await self._chat(self.build_intent_review_payload(request))
                    reviewed_decision = self._decision_from_response(request, reviewed)
                except Exception as review_exc:
                    logger.warning("LLM review model primary-error recovery failed: %s", review_exc)
                else:
                    if reviewed_decision.route not in DETERMINISTIC_ONLY_ROUTES:
                        reviewed_decision.reason = (
                            f"{reviewed_decision.reason}; " if reviewed_decision.reason else ""
                        ) + f"primary router error {type(exc).__name__}; review_model:{self.review_model} recovered route"
                        logger.info(
                            "LLM review model recovered primary router error to %s/%s",
                            reviewed_decision.route,
                            reviewed_decision.intent,
                        )
                        return reviewed_decision
            return fallback_decision(
                request,
                reason=f"llm_router_error:{type(exc).__name__}: {exc}",
            )

        content = ""
        try:
            content = data.get("message", {}).get("content", "")
            decision = self._decision_from_response(request, data)
        except (ValueError, ValidationError) as exc:
            logger.warning("Invalid LLM router response: %s; content=%r", exc, content[:500])
            try:
                relaxed = await self._chat(self.build_payload(request, relaxed_json=True))
                decision = self._decision_from_response(request, relaxed)
                logger.info("LLM router recovered with relaxed JSON response")
            except Exception as relaxed_exc:
                logger.warning("Relaxed LLM router retry failed: %s", relaxed_exc)
                return fallback_decision(request, reason=f"invalid_llm_router_response: {exc}")

        if (
            decision.route == "deep_thought"
            and decision.intent in {"", "unknown"}
            and not decision.reason
        ):
            reviewed = await self._review_ambiguous_deep_thought(request, decision)
            if not (
                reviewed.route == "deep_thought"
                and reviewed.intent in {"", "unknown"}
                and not reviewed.reason
            ):
                decision = reviewed
            else:
                logger.info(
                    "LLM router returned ambiguous deep_thought without intent or reason; using safe fallback"
                )
                return fallback_decision(
                    request,
                    reason="ambiguous_llm_deep_thought_without_intent_or_reason",
                )
        else:
            decision = await self._review_ambiguous_deep_thought(request, decision)
        decision = await self._review_route_only_robot_action(request, decision)

        if decision.route in DETERMINISTIC_ONLY_ROUTES:
            return await self._recover_deterministic_only_decision(request, decision)

        if decision.route == "robot_action" and _is_placeholder_capability_intent(decision.intent):
            return await self._recover_placeholder_capability_decision(request, decision)

        return decision
