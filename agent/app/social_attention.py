from __future__ import annotations

import copy
import json
import logging
import time
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from .clients.ollama_client import llm_failure_metadata

try:
    from chromie_contracts.social_attention import (
        SocialAttentionPlan,
        SocialAttentionRequest,
        normalize_social_attention_mode,
    )
except ImportError:  # pragma: no cover - repository development path
    from shared.chromie_contracts.social_attention import (
        SocialAttentionPlan,
        SocialAttentionRequest,
        normalize_social_attention_mode,
    )

logger = logging.getLogger("chromie.agent.social_attention")


_SOCIAL_ATTENTION_PROVIDER_OWNED_FIELDS = frozenset(
    {
        "head_yaw_rad",
        "head_pitch_rad",
        "yaw_rad",
        "pitch_rad",
        "target_yaw_rad",
        "target_pitch_rad",
        "suggested_args",
        "installation_calibration",
        "mode",
        "backend",
        "provider_backend",
        "provider_mode",
    }
)


def _contains_provider_owned_field(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).strip().lower() in _SOCIAL_ATTENTION_PROVIDER_OWNED_FIELDS:
                return True
            if _contains_provider_owned_field(item):
                return True
    elif isinstance(value, list):
        return any(_contains_provider_owned_field(item) for item in value)
    return False


def _semantic_target_projection(value: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value[key]
        for key in ("target_ref", "relative_direction", "label", "confidence")
        if key in value
    }


def _compact_social_input_schema(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    raw_properties = value.get("properties")
    required_names = {
        str(item) for item in value.get("required") or [] if str(item).strip()
    }
    properties: dict[str, Any] = {}
    if isinstance(raw_properties, dict):
        for name, raw in raw_properties.items():
            if not isinstance(raw, dict):
                continue
            projected = {
                key: raw[key]
                for key in ("type", "enum", "minimum", "maximum", "default")
                if key in raw
            }
            if str(name) in required_names:
                projected["required"] = True
            properties[str(name)] = projected
    return properties


def _compact_social_candidate(value: dict[str, Any]) -> dict[str, Any]:
    """Project only semantics Social Attention needs to choose a decoration."""

    projected: dict[str, Any] = {
        "capability_id": str(value.get("capability_id") or "").strip(),
        "description": str(value.get("description") or "").strip()[:60],
        "behavior_domains": [
            str(item).strip()
            for item in value.get("behavior_domains") or []
            if str(item).strip()
        ],
        "args_schema": _compact_social_input_schema(value.get("input_schema") or {}),
    }
    return projected


def _compact_social_style(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        key: value[key]
        for key in (
            "expressiveness",
            "repetition_guidance",
            "restraint",
        )
        if key in value
    }


def _compact_recent_auxiliary_evidence(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    projected: list[dict[str, Any]] = []
    for item in value[-12:]:
        if not isinstance(item, dict):
            continue
        compact = {
            key: item[key]
            for key in (
                "capability_id",
                "semantic_args",
                "purpose",
                "primary_activity_id",
                "execution_claim",
            )
            if key in item
        }
        if compact:
            projected.append(compact)
    return projected



@dataclass(slots=True)
class SocialAttentionServices:
    """Narrow dependencies owned by the current Social Attention component."""

    social_attention_mode: str = "on"
    social_attention_ollama: Any | None = None
    social_attention_num_ctx: int = 4096
    social_attention_num_predict: int = 160
    social_attention_max_behaviors: int = 2
    social_attention_capability_ids: tuple[str, ...] = ()
    capability_catalog: Any | None = None

    def effective_social_attention_mode(self) -> str:
        return normalize_social_attention_mode(self.social_attention_mode, default="on")


class SocialAttentionContextBuilder:
    """Build the bounded Host-owned context exposed to Social Attention planning."""

    def __init__(self, services: SocialAttentionServices | Any) -> None:
        self.services = services

    async def prepare(self, request: Any) -> None:
        mind = request.context.get("mind")
        style = mind.get("social_interaction_style") if isinstance(mind, dict) else None
        if isinstance(style, dict) and style.get("owner_approved") is True:
            request.context["social_interaction_style"] = dict(style)
        else:
            request.context.pop("social_interaction_style", None)

        recent = request.context.get("recent_auxiliary_behavior_evidence")
        if isinstance(recent, list):
            request.context["recent_auxiliary_behavior_evidence"] = [
                dict(item)
                for item in recent[-12:]
                if isinstance(item, dict)
            ]
        else:
            request.context["recent_auxiliary_behavior_evidence"] = []

        await self._ensure_candidates(request)

    async def _ensure_candidates(self, request: Any) -> None:
        mode = self.services.effective_social_attention_mode()
        request.context["social_attention_policy"] = {
            "mode": mode,
            "planning_enabled": mode != "off",
            "execution_enabled": mode == "on",
            "embodiment_independent": True,
            "semantic_owner": "social_attention",
        }
        request.context.pop("social_attention_candidates", None)
        request.context.pop("social_attention_candidate_source", None)
        request.context.pop("social_attention_target_evidence", None)
        if mode == "off":
            return
        catalog = self.services.capability_catalog
        if catalog is None:
            return

        if hasattr(catalog, "refresh_live_named_capabilities"):
            try:
                await catalog.refresh_live_named_capabilities()
            except Exception as exc:  # pragma: no cover - defensive service boundary
                logger.warning("social attention catalog refresh failed error=%s", exc)

        configured_ids = {
            capability_id
            for capability_id in self.services.social_attention_capability_ids
            if capability_id
        }
        interaction_state = request.context.get("social_attention_interaction_state")
        raw_primary_ids = (
            interaction_state.get("primary_capability_ids")
            if isinstance(interaction_state, dict)
            else []
        )
        primary_capability_ids = (
            {
                str(capability_id).strip()
                for capability_id in raw_primary_ids
                if str(capability_id).strip()
            }
            if isinstance(raw_primary_ids, list)
            else set()
        )
        candidate_ids: list[str] = []
        seen_ids: set[str] = set()

        entries = catalog.entries() if hasattr(catalog, "entries") else []
        for entry in entries:
            capability_id = str(getattr(entry, "capability_id", "") or "").strip()
            domains = {
                str(value).strip().lower()
                for value in (getattr(entry, "behavior_domains", None) or [])
                if str(value).strip()
            }
            if capability_id and (
                "social_attention" in domains or capability_id in configured_ids
            ):
                if capability_id not in seen_ids:
                    seen_ids.add(capability_id)
                    candidate_ids.append(capability_id)

        for capability_id in sorted(configured_ids):
            if capability_id not in seen_ids:
                seen_ids.add(capability_id)
                candidate_ids.append(capability_id)

        candidates: list[dict[str, Any]] = []
        for capability_id in candidate_ids:
            if capability_id in primary_capability_ids:
                continue
            item = None
            if hasattr(catalog, "get_capability"):
                try:
                    item = await catalog.get_capability(capability_id)
                except Exception as exc:  # pragma: no cover - defensive service boundary
                    logger.warning(
                        "social attention capability lookup failed id=%s error=%s",
                        capability_id,
                        exc,
                    )
                    continue
            if item is None:
                item = next(
                    (
                        entry
                        for entry in entries
                        if str(getattr(entry, "capability_id", "")) == capability_id
                    ),
                    None,
                )
            if item is None:
                continue
            payload = (
                item.model_dump(mode="json")
                if hasattr(item, "model_dump")
                else dict(item)
                if isinstance(item, dict)
                else None
            )
            if not isinstance(payload, dict):
                continue
            if payload.get("available") is False:
                continue
            if payload.get("interaction_executable") is not True:
                continue
            if mode == "on" and (
                bool(payload.get("requires_confirmation"))
                or payload.get("can_run_parallel") is not True
                or payload.get("parallel_metadata_declared") is not True
            ):
                continue
            domains = {
                str(value).strip().lower()
                for value in payload.get("behavior_domains") or []
                if str(value).strip()
            }
            if capability_id not in configured_ids and "social_attention" not in domains:
                continue
            if _contains_provider_owned_field(payload.get("input_schema") or {}):
                logger.info(
                    "social_attention_candidate_hidden_provider_owned_schema id=%s",
                    capability_id,
                )
                continue
            metadata = payload.get("metadata")
            if isinstance(metadata, dict):
                payload["metadata"] = {
                    key: value
                    for key, value in metadata.items()
                    if str(key).strip().lower() not in _SOCIAL_ATTENTION_PROVIDER_OWNED_FIELDS
                    and not _contains_provider_owned_field(value)
                }
            candidates.append(_compact_social_candidate(payload))

        if candidates:
            request.context["social_attention_candidates"] = candidates
            request.context["social_attention_candidate_source"] = "behavior_domain_catalog"
            request.context["social_attention_target_evidence"] = self._target_evidence(request)

    def _target_evidence(self, request: Any) -> dict[str, Any]:
        for key in ("social_attention_target", "active_user_target", "perceived_user_target"):
            value = request.context.get(key)
            if isinstance(value, dict) and value:
                explicit_source = str(value.get("source") or "").strip()
                source = (
                    explicit_source
                    if explicit_source in {"live_perception", "conversation_context"}
                    else "live_perception"
                    if "perception" in key or "perceived" in key
                    else "conversation_context"
                )
                target = value.get("target")
                if not isinstance(target, dict):
                    target = dict(value)
                    target.pop("source", None)
                    target.pop("available", None)
                return {
                    "available": True,
                    "source": source,
                    "target": _semantic_target_projection(target),
                }
        return {"available": False}


class SocialAttentionPlanner:
    """Model-driven auxiliary body-decoration planning.

    Social Attention is background social cognition attached to a real primary
    human-observable Activity. The model decides whether a small body decoration
    would make that Activity more socially natural without changing its Goal, response
    text, or completion, and selects exact
    catalog capabilities for the scene. Response wording remains owned by the normal
    cognitive/Response Composer path; this planner is body-only. Deterministic code validates
    schemas, evidence, safety, and resource conflicts without choosing actions.
    """

    def __init__(self, services: Any) -> None:
        self.services = services

    async def plan(
        self, request: SocialAttentionRequest
    ) -> SocialAttentionPlan | None:
        client = self.services.social_attention_ollama
        candidates = request.context.get("social_attention_candidates")
        if client is None or not isinstance(candidates, list) or not candidates:
            return None

        session_id = request.session_id
        prompt = self._prompt(request, candidates)
        response_schema = self._response_schema(candidates)
        system_prompt = (
            "You are Chromie's background Social Attention planner. Choose only small, "
            "scene-appropriate body decorations for the supplied interaction anchor from "
            "the supplied catalog. Decorations must remain optional, non-disruptive, and "
            "subordinate to the primary behavior. Do not use phrase-to-skill rules, do not "
            "author or alter speech, and return JSON only."
        )
        generation_options = {
            "temperature": 0.2,
            "top_p": 0.9,
            "num_ctx": int(self.services.social_attention_num_ctx),
            "num_predict": int(self.services.social_attention_num_predict),
        }
        started = time.perf_counter()
        logger.info(
            "social_attention_plan_start sid=%s mode=%s timeout_ms=%s num_ctx=%s "
            "num_predict=%s prompt_chars=%s candidates=%s",
            session_id,
            self.services.effective_social_attention_mode(),
            getattr(client, "timeout_ms", None),
            int(self.services.social_attention_num_ctx),
            int(self.services.social_attention_num_predict),
            len(prompt),
            len(candidates),
        )
        try:
            raw = await client.generate(
                prompt,
                system=system_prompt,
                options=generation_options,
                response_format=response_schema,
                prompt_family="social_attention.primary",
                turn_id=session_id,
                attempt=1,
            )
        except Exception as exc:
            planner_ms = (time.perf_counter() - started) * 1000.0
            failure = {
                **llm_failure_metadata(exc),
                "stage": "social_attention",
                "error_type": type(exc).__name__,
                "error": str(exc)[:500],
                "elapsed_ms": round(planner_ms, 1),
            }
            request.context["social_attention_failure"] = failure
            logger.warning(
                "social_attention_plan_failed sid=%s failure_class=%s failure_domain=%s "
                "architecture_attribution=%s retryable=%s elapsed_ms=%.1f "
                "error_type=%s error=%s",
                session_id,
                failure.get("failure_class"),
                failure.get("failure_domain"),
                failure.get("architecture_attribution"),
                str(bool(failure.get("retryable"))).lower(),
                planner_ms,
                type(exc).__name__,
                exc,
            )
            return None
        if not isinstance(raw, dict):
            planner_ms = (time.perf_counter() - started) * 1000.0
            failure = {
                "stage": "social_attention",
                "failure_class": "structured_output_invalid",
                "failure_domain": "model_contract",
                "architecture_attribution": "not_evaluated",
                "retryable": True,
                "error_type": type(raw).__name__,
                "error": "social attention model did not return a JSON object",
                "elapsed_ms": round(planner_ms, 1),
            }
            request.context["social_attention_failure"] = failure
            logger.warning(
                "social_attention_plan_invalid sid=%s failure_class=%s failure_domain=%s "
                "architecture_attribution=%s retryable=true elapsed_ms=%.1f error=%s",
                session_id,
                failure["failure_class"],
                failure["failure_domain"],
                failure["architecture_attribution"],
                planner_ms,
                failure["error"],
            )
            return None
        try:
            plan = SocialAttentionPlan.model_validate(raw)
        except ValidationError as exc:
            planner_ms = (time.perf_counter() - started) * 1000.0
            failure = {
                **llm_failure_metadata(exc),
                "stage": "social_attention",
                "failure_class": "structured_output_invalid",
                "failure_domain": "model_contract",
                "architecture_attribution": "model_output",
                "retryable": False,
                "error_type": type(exc).__name__,
                "error": str(exc)[:500],
                "elapsed_ms": round(planner_ms, 1),
                "semantic_owner": "social_attention",
                "model_call_count": 1,
            }
            request.context["social_attention_failure"] = failure
            logger.warning(
                "social_attention_plan_invalid sid=%s elapsed_ms=%.1f error=%s",
                session_id,
                planner_ms,
                exc,
            )
            return None
        planner_ms = (time.perf_counter() - started) * 1000.0
        request.context.pop("social_attention_failure", None)
        plan.metadata = {
            **plan.metadata,
            "planner_ms": round(planner_ms, 1),
            "architecture_attribution": "not_evaluated",
            "semantic_owner": "social_attention",
            "model_call_count": 1,
            "fail_soft": True,
        }
        logger.info(
            "social_attention_plan_done sid=%s decision=%s behaviors=%s confidence=%.2f "
            "architecture_attribution=not_evaluated ms=%.1f",
            session_id,
            plan.decision,
            len(plan.behaviors),
            plan.confidence,
            planner_ms,
        )
        return plan

    @staticmethod
    def _response_schema(candidates: list[dict[str, Any]]) -> dict[str, Any]:
        """Constrain body identity to the exact reviewed live candidate set."""

        schema = copy.deepcopy(SocialAttentionPlan.model_json_schema())
        candidate_ids = list(
            dict.fromkeys(
                str(item.get("capability_id") or "").strip()
                for item in candidates
                if isinstance(item, dict)
                and str(item.get("capability_id") or "").strip()
            )
        )
        behavior_schema = schema.get("$defs", {}).get("SocialAttentionBehavior")
        if isinstance(behavior_schema, dict):
            properties = behavior_schema.get("properties")
            if isinstance(properties, dict):
                capability_id = properties.get("capability_id")
                if isinstance(capability_id, dict):
                    capability_id["type"] = "string"
                    capability_id["enum"] = candidate_ids
            required = behavior_schema.setdefault("required", [])
            if "capability_id" not in required:
                required.append("capability_id")
        required = schema.setdefault("required", [])
        for field_name in (
            "decision",
            "target",
            "behaviors",
            "confidence",
            "reason",
        ):
            if field_name not in required:
                required.append(field_name)
        schema.setdefault("allOf", []).extend(
            [
                {
                    "if": {
                        "properties": {"decision": {"const": "none"}},
                        "required": ["decision"],
                    },
                    "then": {
                        "properties": {"behaviors": {"maxItems": 0}},
                    },
                },
                {
                    "if": {
                        "properties": {"decision": {"const": "express"}},
                        "required": ["decision"],
                    },
                    "then": {
                        "properties": {"behaviors": {"minItems": 1}},
                    },
                },
            ]
        )
        return schema

    def _prompt(
        self,
        request: SocialAttentionRequest,
        candidates: list[dict[str, Any]],
    ) -> str:
        language = request.language
        event = request.event
        primary_activity = request.primary_activity.model_dump(
            mode="json", exclude_none=True
        )
        payload = {
            "event": event,
            "primary_activity": primary_activity,
            "user_utterance": request.text,
            "language": language,
            "social_interaction_style": _compact_social_style(
                request.context.get("social_interaction_style")
            ),
            "recent_auxiliary_behavior_evidence": _compact_recent_auxiliary_evidence(
                request.context.get("recent_auxiliary_behavior_evidence")
            ),
            "attention_target_evidence": request.context.get("social_attention_target_evidence")
            or {"available": False},
            "eligible_social_capabilities": [
                _compact_social_candidate(item)
                for item in candidates
                if isinstance(item, dict)
            ],
            "max_behaviors": int(self.services.social_attention_max_behaviors),
        }
        return (
            "Choose optional body expression for this Primary Activity. Never change Goal, speech, "
            "completion, or requested action. Internal cognition is not an anchor. Use only supplied "
            "candidate and target semantics; invent no perception, calibration, motor, or provider facts. "
            "Prefer none when expression adds no social value, repeats recent behavior, conflicts, or "
            "stillness is more natural. If expressing, use only listed capability_id, valid args, and "
            "timing=parallel. Return JSON only.\n\n"
            f"Interaction context:\n{json.dumps(payload, ensure_ascii=False, sort_keys=True)}"
        )
