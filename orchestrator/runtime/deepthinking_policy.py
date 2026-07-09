from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

try:
    from orchestrator.schemas.route import RouteDecision
except ImportError:  # pragma: no cover - repository development path
    from schemas.route import RouteDecision


TERMINAL_ROUTES = {"interrupt", "ignore", "clarify"}
DELEGATED_ROUTE = "deep_thought"
CLARIFICATION_INTENTS = {
    "clarify_insufficient_information",
    "insufficient_information",
    "ambiguous_tool_or_asr",
}


@dataclass(frozen=True)
class DeepThinkingDelegation:
    """Result of evaluating whether Orchestrator should involve deepthinking.

    This policy only decides whether to include the semantic deep-thinking path.
    It is not an execution authorization and never bypasses SkillRuntime or the
    Soridormi physical safety boundary.
    """

    should_delegate: bool
    reasons: tuple[str, ...] = ()
    original_route: str = ""
    original_intent: str = ""
    original_confidence: float = 0.0
    threshold: float | None = None
    high_risk_physical: bool = False
    compound_action: bool = False

    def to_metadata(self) -> dict[str, Any]:
        return {
            "should_delegate": self.should_delegate,
            "reasons": list(self.reasons),
            "original_route": self.original_route,
            "original_intent": self.original_intent,
            "original_confidence": self.original_confidence,
            "threshold": self.threshold,
            "high_risk_physical": self.high_risk_physical,
            "compound_action": self.compound_action,
            "policy": "conditional_deepthinking_v1",
            "note": (
                "semantic delegation only; physical execution still requires "
                "SkillRuntime and Soridormi validation"
            ),
        }


@dataclass(frozen=True)
class DeepThinkingPolicyConfig:
    enabled: bool = True
    thresholds: Mapping[str, float] = field(
        default_factory=lambda: {
            "chat": 0.75,
            "memory": 0.85,
            "tool": 0.82,
            "robot_action_single_exact": 0.70,
            "robot_action_compound": 0.82,
            "navigation_or_manipulation": 0.95,
        }
    )
    ambiguous_user_states: tuple[str, ...] = (
        "ambiguous",
        "confused",
        "frustrated",
        "upset",
        "correcting",
        "uncertain",
    )
    partial_capability_statuses: tuple[str, ...] = (
        "partial",
        "weak",
        "missing",
        "missing_ability",
        "known_missing",
        "not_executable",
        "non_executable",
        "unsupported",
        "unavailable",
        "contradictory",
        "conflict",
    )
    high_risk_physical_terms: tuple[str, ...] = (
        "approach",
        "carry",
        "close",
        "drive",
        "find_object",
        "follow",
        "go_to",
        "grab",
        "grasp",
        "hold",
        "locate",
        "locomotion",
        "manipulate",
        "move_to",
        "navigate",
        "navigation",
        "open",
        "pick",
        "place",
        "pull",
        "push",
        "scan",
        "search",
        "walk",
    )

    @classmethod
    def from_env(cls) -> "DeepThinkingPolicyConfig":
        enabled = _env_bool("ORCH_CONDITIONAL_DEEPTHINK_ENABLED", True)
        defaults = cls().thresholds
        thresholds = {
            "chat": _env_float(
                "ORCH_DEEPTHINK_CONFIDENCE_CHAT",
                defaults["chat"],
            ),
            "memory": _env_float(
                "ORCH_DEEPTHINK_CONFIDENCE_MEMORY",
                defaults["memory"],
            ),
            "tool": _env_float(
                "ORCH_DEEPTHINK_CONFIDENCE_TOOL",
                defaults["tool"],
            ),
            "robot_action_single_exact": _env_float(
                "ORCH_DEEPTHINK_CONFIDENCE_ROBOT_ACTION_SINGLE_EXACT",
                defaults["robot_action_single_exact"],
            ),
            "robot_action_compound": _env_float(
                "ORCH_DEEPTHINK_CONFIDENCE_ROBOT_ACTION_COMPOUND",
                defaults["robot_action_compound"],
            ),
            "navigation_or_manipulation": _env_float(
                "ORCH_DEEPTHINK_CONFIDENCE_NAVIGATION_OR_MANIPULATION",
                defaults["navigation_or_manipulation"],
            ),
        }
        return cls(enabled=enabled, thresholds=thresholds)


class DeepThinkingDelegationPolicy:
    """Conditional Route2 -> deepthinking handoff policy.

    A positive decision changes only semantic routing. It never means a skill is
    executable, confirmed, physically safe, or committed.
    """

    def __init__(self, config: DeepThinkingPolicyConfig | None = None) -> None:
        self.config = config or DeepThinkingPolicyConfig()

    def evaluate(
        self,
        decision: RouteDecision,
        *,
        context: Mapping[str, Any] | None = None,
    ) -> DeepThinkingDelegation:
        if not self.config.enabled:
            return self._result(decision, should_delegate=False)
        if decision.route == DELEGATED_ROUTE:
            return self._result(decision, should_delegate=False)
        if decision.route in TERMINAL_ROUTES or decision.interrupt_current:
            return self._result(decision, should_delegate=False)
        if _is_clarification_intent(decision.intent):
            return self._result(decision, should_delegate=False)

        context = context or {}
        reasons: list[str] = []
        route_items = _route_item_dicts(decision)
        actions = _action_dicts(decision, route_items)
        compound_action = len(actions) > 1 or len(
            [item for item in route_items if item.get("route") == "robot_action"]
        ) > 1
        high_risk_physical = self._high_risk_physical(decision, route_items, actions)
        threshold = self._threshold(decision, compound_action, high_risk_physical)

        if self._route_items_request_deepthinking(route_items):
            reasons.append("route_item_requests_deepthinking")
        if self._has_desired_abilities(decision):
            reasons.append("missing_or_desired_ability")
        if self._has_partial_capability_match(decision, route_items):
            reasons.append("partial_capability_match")
        if self._context_user_state_needs_deepthinking(context):
            reasons.append("ambiguous_or_frustrated_user_state")
        if self._metadata_flag(decision, "requires_live_perception") or self._actions_flag(
            actions,
            "requires_live_perception",
        ):
            reasons.append("requires_live_perception")
        if high_risk_physical and not self._exact_capability_selection_without_actions(
            decision,
            route_items,
            actions,
        ):
            reasons.append("high_risk_physical_goal")
        if threshold is not None and decision.confidence < threshold:
            reasons.append(f"confidence_below_{threshold:.2f}")

        return self._result(
            decision,
            should_delegate=bool(reasons),
            reasons=tuple(dict.fromkeys(reasons)),
            threshold=threshold,
            high_risk_physical=high_risk_physical,
            compound_action=compound_action,
        )

    def delegate_decision(
        self,
        decision: RouteDecision,
        delegation: DeepThinkingDelegation,
    ) -> RouteDecision:
        if not delegation.should_delegate:
            return decision
        metadata = dict(decision.metadata or {})
        metadata["orchestrator_deepthinking_delegation"] = delegation.to_metadata()
        metadata.setdefault(
            "orchestrator_original_route",
            {
                "route": decision.route,
                "intent": decision.intent,
                "confidence": decision.confidence,
                "agents": list(decision.agents or []),
                "source": decision.source,
                "reason": decision.reason,
            },
        )
        metadata.setdefault("thinking_ack_allowed", bool(decision.speak_first))
        reason = "orchestrator conditional deepthinking delegation: " + ", ".join(
            delegation.reasons
        )
        if decision.reason:
            reason = f"{reason}; original_reason={decision.reason}"
        return decision.model_copy(
            deep=True,
            update={
                "route": DELEGATED_ROUTE,
                "agents": ["deepthinking_agent", "speaker_agent"],
                "intent": "deep_thought_policy_delegate",
                "needs_agent": True,
                "should_speak": True,
                "metadata": metadata,
                "reason": reason,
            },
        )

    def _result(
        self,
        decision: RouteDecision,
        *,
        should_delegate: bool,
        reasons: tuple[str, ...] = (),
        threshold: float | None = None,
        high_risk_physical: bool = False,
        compound_action: bool = False,
    ) -> DeepThinkingDelegation:
        return DeepThinkingDelegation(
            should_delegate=should_delegate,
            reasons=reasons,
            original_route=decision.route,
            original_intent=decision.intent,
            original_confidence=decision.confidence,
            threshold=threshold,
            high_risk_physical=high_risk_physical,
            compound_action=compound_action,
        )

    def _threshold(
        self,
        decision: RouteDecision,
        compound_action: bool,
        high_risk_physical: bool,
    ) -> float | None:
        if decision.route == "robot_action":
            if self._exact_capability_selection_without_actions(
                decision,
                _route_item_dicts(decision),
                _action_dicts(decision, _route_item_dicts(decision)),
            ):
                return self.config.thresholds["robot_action_single_exact"]
            if high_risk_physical:
                return self.config.thresholds["navigation_or_manipulation"]
            if compound_action:
                return self.config.thresholds["robot_action_compound"]
            return self.config.thresholds["robot_action_single_exact"]
        return self.config.thresholds.get(decision.route)

    def _exact_capability_selection_without_actions(
        self,
        decision: RouteDecision,
        route_items: Iterable[dict[str, Any]],
        actions: Iterable[dict[str, Any]],
    ) -> bool:
        """Let SkillRuntime/Soridormi adjudicate simple exact physical proposals.

        An exact catalog intent such as ``capability:soridormi.walk_forward`` with
        no router-authored action args is already grounded to an available
        affordance, but it is still only a proposal.  Sending that through
        deepthinking solely because it is physical can discard the proposal and
        produce a confusing speech-only fallback.  CapabilityAgent,
        SkillRuntime, and Soridormi remain the validation and safety boundary.

        Route merge metadata often repeats the selected skill_id inside a
        route item.  That route-item skill_id is *not* an executable action
        with args; it is just the catalog selection.  Do not count it as an
        authored action that requires deepthinking.
        """

        if decision.route != "robot_action":
            return False
        selected_id = _capability_intent_id(decision.intent)
        if not selected_id:
            return False

        route_items_list = list(route_items)
        for action in actions:
            if not _is_unparameterized_selected_skill_marker(action, selected_id):
                return False

        robot_items = [item for item in route_items_list if item.get("route") == "robot_action"]
        if len(robot_items) > 1:
            return False
        for item in robot_items:
            if item.get("requires_mind") is True:
                return False
            if str(item.get("lane") or "") == "deepthought":
                return False
            item_skill_id = str(item.get("skill_id") or item.get("capability_id") or "").strip()
            if item_skill_id and item_skill_id != selected_id:
                return False
            item_actions = item.get("actions")
            if isinstance(item_actions, list):
                for action in item_actions:
                    if not isinstance(action, Mapping):
                        return False
                    if not _is_unparameterized_selected_skill_marker(action, selected_id):
                        return False
        return True

    def _route_items_request_deepthinking(self, route_items: Iterable[dict[str, Any]]) -> bool:
        for item in route_items:
            route = str(item.get("route") or "")
            lane = str(item.get("lane") or "")
            if route == DELEGATED_ROUTE or lane == "deepthought":
                return True
            if item.get("requires_mind") is True:
                return True
        return False

    def _has_desired_abilities(self, decision: RouteDecision) -> bool:
        metadata = decision.metadata if isinstance(decision.metadata, dict) else {}
        for key in ("desired_abilities", "ability_proposals"):
            value = metadata.get(key)
            if isinstance(value, list) and value:
                return True
        return False

    def _has_partial_capability_match(
        self,
        decision: RouteDecision,
        route_items: Iterable[dict[str, Any]],
    ) -> bool:
        metadata_containers: list[Any] = [decision.metadata]
        metadata_containers.extend(item.get("metadata") for item in route_items)
        for value in metadata_containers:
            if self._value_has_partial_capability_status(value):
                return True

        candidate_sets: list[Any] = [decision.candidate_capabilities]
        candidate_sets.extend(item.get("candidate_capabilities") for item in route_items)
        return any(self._candidate_set_needs_deepthinking(value) for value in candidate_sets)

    def _candidate_set_needs_deepthinking(self, value: Any) -> bool:
        if not isinstance(value, list) or not value:
            return False
        candidates = [item for item in value if isinstance(item, Mapping)]
        if not candidates:
            return False
        for item in candidates:
            if self._explicit_partial_status(item):
                return True
        executable = [
            item
            for item in candidates
            if item.get("available") is not False
            and item.get("interaction_executable") is not False
        ]
        return not executable

    def _explicit_partial_status(self, value: Mapping[str, Any]) -> bool:
        for key in (
            "match_status",
            "capability_match_status",
            "status",
            "ability_status",
            "catalog_match_status",
        ):
            status = _normalized_status(value.get(key))
            if status in self.config.partial_capability_statuses:
                return True
        return False

    def _value_has_partial_capability_status(self, value: Any) -> bool:
        if isinstance(value, Mapping):
            if self._explicit_partial_status(value):
                return True
            return any(
                self._value_has_partial_capability_status(child)
                for child in value.values()
                if isinstance(child, (Mapping, list, tuple))
            )
        if isinstance(value, (list, tuple)):
            return any(self._value_has_partial_capability_status(item) for item in value)
        return False

    def _context_user_state_needs_deepthinking(
        self,
        context: Mapping[str, Any],
    ) -> bool:
        candidates: list[Any] = [context.get("user_state")]
        for key in ("dialogue_state", "affect", "user", "metadata"):
            value = context.get(key)
            if isinstance(value, Mapping):
                candidates.extend(
                    [
                        value.get("user_state"),
                        value.get("emotion"),
                        value.get("sentiment"),
                    ]
                )
        normalized = {_normalized_status(item) for item in candidates if item}
        return bool(normalized.intersection(self.config.ambiguous_user_states))

    def _metadata_flag(self, decision: RouteDecision, key: str) -> bool:
        metadata = decision.metadata if isinstance(decision.metadata, dict) else {}
        if metadata.get(key) is True:
            return True
        for item in _route_item_dicts(decision):
            if item.get(key) is True:
                return True
            item_metadata = item.get("metadata")
            if isinstance(item_metadata, Mapping) and item_metadata.get(key) is True:
                return True
        return False

    def _actions_flag(self, actions: Iterable[dict[str, Any]], key: str) -> bool:
        for action in actions:
            if action.get(key) is True:
                return True
            action_metadata = action.get("metadata")
            if isinstance(action_metadata, Mapping) and action_metadata.get(key) is True:
                return True
        return False

    def _high_risk_physical(
        self,
        decision: RouteDecision,
        route_items: Iterable[dict[str, Any]],
        actions: Iterable[dict[str, Any]],
    ) -> bool:
        if decision.route != "robot_action" and not any(
            item.get("route") == "robot_action" for item in route_items
        ):
            return False
        text_parts = [decision.intent, decision.reason]
        for action in actions:
            text_parts.extend(
                [
                    str(action.get("capability_id") or ""),
                    str(action.get("skill_id") or ""),
                    str(action.get("intent") or ""),
                    str(action.get("tool") or ""),
                    str(action.get("reason") or ""),
                ]
            )
            if self._action_metadata_is_high_risk(action):
                return True
        for item in route_items:
            text_parts.extend(
                [
                    str(item.get("intent") or ""),
                    str(item.get("capability_id") or ""),
                    str(item.get("skill_id") or ""),
                    str(item.get("reason") or ""),
                ]
            )
        for candidate in decision.candidate_capabilities or []:
            if isinstance(candidate, Mapping) and self._selected_candidate_is_high_risk(
                candidate,
                actions,
            ):
                return True
        text = " ".join(part for part in text_parts if part).casefold().replace("-", "_")
        return any(term in text for term in self.config.high_risk_physical_terms)

    def _action_metadata_is_high_risk(self, action: Mapping[str, Any]) -> bool:
        safety_class = _normalized_status(action.get("safety_class"))
        if safety_class in {"high_risk_action", "restricted", "safety_critical", "guarded_operation"}:
            return True
        effects = action.get("effects")
        if isinstance(effects, Iterable) and not isinstance(effects, (str, bytes, Mapping)):
            normalized_effects = {_normalized_status(effect) for effect in effects}
            if normalized_effects.intersection(
                {
                    "navigation",
                    "locomotion",
                    "manipulation",
                    "object_manipulation",
                    "mobile_base_motion",
                }
            ):
                return True
        return False

    def _selected_candidate_is_high_risk(
        self,
        candidate: Mapping[str, Any],
        actions: Iterable[dict[str, Any]],
    ) -> bool:
        candidate_id = str(candidate.get("capability_id") or candidate.get("skill_id") or "").strip()
        if not candidate_id:
            return False
        selected_ids = {
            str(action.get("capability_id") or action.get("skill_id") or "").strip()
            for action in actions
        }
        if candidate_id not in selected_ids:
            return False
        return self._action_metadata_is_high_risk(candidate)


def _route_item_key(index: int, item: Mapping[str, Any]) -> str:
    metadata = item.get("metadata")
    nested = item.get("route_item_metadata")
    for value in (
        item.get("id"),
        item.get("route_item_id"),
        metadata.get("route_item_id") if isinstance(metadata, Mapping) else None,
        nested.get("route_item_id") if isinstance(nested, Mapping) else None,
    ):
        if value:
            return str(value)
    return f"{index}:{item.get('route')}:{item.get('intent')}:{item.get('text')}"



def _is_clarification_intent(intent: Any) -> bool:
    normalized = str(intent or "").strip().casefold()
    return normalized in CLARIFICATION_INTENTS or normalized.startswith("clarify_")


def _capability_intent_id(intent: Any) -> str:
    value = str(intent or "").strip()
    if not value.startswith("capability:"):
        return ""
    return value.split(":", 1)[1].strip()


def _is_unparameterized_selected_skill_marker(
    action: Mapping[str, Any],
    selected_id: str,
) -> bool:
    skill_id = str(action.get("skill_id") or action.get("capability_id") or "").strip()
    if skill_id != selected_id:
        return False
    args = action.get("args")
    if isinstance(args, Mapping) and args:
        return False
    # A route item contributes only skill_id + intent when _action_dicts flattens
    # it.  Treat that as a selected-catalog marker, not an executable action.
    effectful_keys = {
        "timeout_ms",
        "requires_confirmation",
        "cancellable",
        "timing",
        "effects",
        "safety_class",
        "requires_live_perception",
    }
    return not any(key in action for key in effectful_keys)

def _route_item_dicts(decision: RouteDecision) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for item in getattr(decision, "routes", []) or []:
        if hasattr(item, "model_dump"):
            dumped = item.model_dump(mode="json", exclude_none=True)
            if isinstance(dumped, dict):
                items.append(dumped)
        elif isinstance(item, dict):
            items.append(item)
    metadata = decision.metadata if isinstance(decision.metadata, dict) else {}
    raw = metadata.get("route_items")
    if isinstance(raw, list):
        items.extend(item for item in raw if isinstance(item, dict))

    # ``finalize_decision`` stores the same route item both in ``decision.routes``
    # and in ``metadata.route_items`` for compatibility/audit.  Treating both as
    # independent route items makes one exact robot-action proposal look
    # compound, which then sends it to deepthinking as a high-risk physical goal.
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        key = _route_item_key(index, item)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _action_dicts(
    decision: RouteDecision,
    route_items: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    actions = [item for item in (decision.actions or []) if isinstance(item, dict)]
    for item in route_items:
        item_actions = item.get("actions")
        if isinstance(item_actions, list):
            actions.extend(action for action in item_actions if isinstance(action, dict))
        skill_id = item.get("skill_id")
        if skill_id:
            actions.append({"skill_id": skill_id, "intent": item.get("intent")})
    return actions


def _normalized_status(value: Any) -> str:
    return "_".join(str(value or "").strip().casefold().split())


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().casefold() not in {"0", "false", "no", "off"}


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return max(0.0, min(1.0, value))
