from __future__ import annotations

import hashlib
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .interaction import reject_forbidden_low_level_fields
from .semantic_artifact import (
    SemanticArtifactLineage,
    semantic_artifact_ref,
)
from .user_turn import UserTurnEnvelope, UserTurnSourceSpan, normalize_turn_text


_UMI_BINDING_PROVENANCE_KEYS = frozenset({
    "source_evidence",
    "source_ref",
    "source_token_ref",
    "source_start_token_ref",
    "source_end_token_ref",
    "confidence",
})


def _matches_json_primitive_type(value: Any, declared_type: Any) -> bool:
    """Recognize representation-only JSON type annotations on UMI binding values."""

    kind = str(declared_type or "").strip().casefold()
    if kind == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if kind == "string":
        return isinstance(value, str)
    if kind == "boolean":
        return isinstance(value, bool)
    if kind == "array":
        return isinstance(value, list)
    if kind == "object":
        return isinstance(value, dict)
    if kind == "null":
        return value is None
    return False


def responsibility_binding_material_value(value: Any) -> Any:
    """Return the semantic value of one UMI binding.

    UMI bindings own WHAT, not a second provenance envelope. Some model outputs
    wrap a scalar as ``{"value": ..., "source_evidence": ...}`` even though the
    Responsibility already carries authoritative source evidence. Treat only that
    narrow evidence-only wrapper as representation noise. Structured semantic
    values (for example a region object or a measured value with ``unit``) remain
    intact.
    """

    if isinstance(value, dict) and "value" in value:
        metadata_keys = set(value) - {"value"}
        if metadata_keys.issubset(_UMI_BINDING_PROVENANCE_KEYS):
            return value["value"]
        # Some constrained models redundantly emit a JSON-schema primitive type
        # beside a scalar, for example {"value": 6, "type": "integer"}. JSON
        # already carries that type, so this is representation noise rather than
        # semantic structure. Only unwrap when the declared primitive exactly
        # matches the value and every other field is provenance-only. Semantic
        # typed objects such as {"value": 50, "unit": "m", "type": "distance"}
        # therefore remain intact.
        declared_type = value.get("type")
        non_type_metadata = metadata_keys - {"type"}
        if (
            "type" in metadata_keys
            and non_type_metadata.issubset(_UMI_BINDING_PROVENANCE_KEYS)
            and _matches_json_primitive_type(value["value"], declared_type)
        ):
            return value["value"]
    return value


def _normalize_umi_binding_values(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    return {
        key: responsibility_binding_material_value(item)
        for key, item in value.items()
    }


_PLANNER_OWNED_BINDING_FIELDS = frozenset({
    "capability_id",
    "tool_name",
    "provider_id",
    "execution_method",
    "executable_args",
    "args",
    "action",
    "actions",
    "user_input",
    "raw_input",
    "primary_activity",
    "activity_id",
    "work_item_id",
    "plan_step_id",
    "execution_lane",
    "realization",
    "vocal_mode",
    "coordination_id",
    "execution_item_ids",
})

def _reject_planner_owned_bindings(value: Any, *, path: str = "bindings") -> Any:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key or "").strip().casefold()
            if normalized in _PLANNER_OWNED_BINDING_FIELDS:
                raise ValueError(
                    f"Planner-owned field {key!r} is forbidden in responsibility {path}"
                )
            _reject_planner_owned_bindings(item, path=f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_planner_owned_bindings(item, path=f"{path}[{index}]")
    return value


class CoreInterpretationUnavailable(BaseModel):
    """Typed non-semantic outcome when User Meaning Interpretation is unavailable."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[2] = 2
    status: Literal["interpretation_unavailable"] = "interpretation_unavailable"
    turn_id: str = Field(min_length=1, max_length=160)
    session_id: str = Field(min_length=1, max_length=160)
    authority: Literal["goal_driven_cognitive_core"] = "goal_driven_cognitive_core"
    failure_class: str = Field(min_length=1, max_length=120)
    retryable: bool = True
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("turn_id", "session_id", "failure_class", mode="before")
    @classmethod
    def normalize_unavailable_fields(cls, value: str) -> str:
        return normalize_turn_text(str(value or ""))

    @field_validator("reason", mode="before")
    @classmethod
    def normalize_bounded_reason(cls, value: str) -> str:
        # A nested validation report can be large. Keep the public failure DTO
        # bounded so the intended HTTP 503 path cannot become an unrelated 500.
        return normalize_turn_text(str(value or ""))[:500]


class ResponsibilitySourceEvidence(UserTurnSourceSpan):
    """UMI-owned semantic span into the authoritative admitted UserTurnEnvelope.

    The shared span contract keeps all later semantic owners on the same immutable
    source coordinate system. Trusted code resolves refs; UMI selects only WHAT.
    """


class CognitiveResponsibilityProposal(BaseModel):
    """Complete human intention and expected result type understood by UMI.

    Live UMI supplies natural-language meaning and current-turn provenance only.
    Planner selects Capabilities, realizes parameters and decomposes Activities.
    GA alone selects canonical Goal relationships; SC owns communication wording.
    The DTO deliberately contains no Goal identity/relationship or HOW fields.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    local_ref: str = Field(min_length=1, max_length=80)
    outcome: str = Field(
        min_length=1,
        max_length=500,
        description=(
            "Complete provider-neutral user meaning/outcome, including every material detail, "
            "condition and relation. A compound request may remain one outcome; "
            "Planner owns its Activity decomposition. Preserve the "
            "requested answer or judgment and proposition polarity: a question about "
            "whether P is true must not be rewritten as the assertion that P is true. "
            "For conversational speech, describe the communicative obligation or "
            "proposition to convey; never write the exact words Chromie will say. "
            "Social Cognition alone authors the utterance."
        ),
    )
    bindings: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Sparse material user-semantic facts from the authoritative turn or bounded "
            "semantic context only; never runtime/session identifiers or HOW fields. "
            "Counts, measurements, activation and field-specific Goal updates retain "
            "typed evidence; other details may remain solely in the complete outcome. "
            "Use native JSON scalar types directly; do not wrap a primitive as value+type "
            "merely to restate its JSON type. Preserve an explicitly measured value and "
            "its semantic unit together as one exact "
            "source/context surface; execution-unit normalization belongs downstream. "
            "Cross-Responsibility order uses before/after with exact sibling local_ref "
            "values; requested concurrency uses parallel_with with exact sibling "
            "local_ref values."
        ),
    )
    output_mode: Literal[
        "unspecified",
        "speech",
        "styled_speech",
        "recitation",
        "singing",
        "humming",
        "nonverbal_vocalization",
        "body_action",
        "media_playback",
        "information",
        "stateful_effect",
        "other",
    ] = Field(
        default="unspecified",
        description=(
            "User Meaning Interpretation's provider-neutral WHAT category for this one human "
            "outcome. Goal Association preserves the accepted value and must not "
            "re-author it. information "
            "means the person wants Chromie to determine or provide information; "
            "stateful_effect means the person wants a durable or future state change "
            "outside embodiment. Physical locomotion, posture, gaze, gesture, manipulation, "
            "carrying, and handover are body_action even when they change location or "
            "another lasting physical state. "
            "These categories do not say whether work, fresh evidence, a Capability, "
            "provider, Activity, executable argument, or later speech is required. "
            "Requested physical-object acquisition/carrying/handover remains "
            "body_action because the human-level outcome is an embodied effect."
        ),
    )
    continuity_scope: Literal["goal", "turn"] = Field(
        default="goal",
        description=(
            "Whether this understood human outcome needs canonical Goal/Planner continuity "
            "after the UMI handoff. goal does not mean long-term or cross-session: it is "
            "required whenever the requested result still needs information/evidence, "
            "embodied/media/stateful work, or changes/answers pending Goal meaning, even "
            "when that work can finish before the next user turn. turn is reserved for "
            "ordinary current-conversation speech that Social Cognition can complete "
            "directly and that leaves no separate user/world objective. This is a semantic "
            "property of WHAT in context, never a keyword or hardware rule. It is not a GA "
            "bypass flag: GA may still inspect conversational continuity and associate a terse "
            "re-engagement with retained Goal state when evidence supports it. Planner readiness "
            "is derived from substantive output domains/relations and later canonical Goal "
            "ownership, not from continuity_scope alone."
        ),
    )
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source_evidence: ResponsibilitySourceEvidence | None = Field(
        default=None,
        description=(
            "Primary User-Meaning evidence citing the exact inclusive token "
            "span in the authoritative admitted turn that grounds this one "
            "Responsibility. The live UMI contract requires it; the optional model "
            "default preserves construction of bounded downstream/test projections "
            "that do not themselves author UMI meaning."
        ),
    )

    @field_validator("local_ref", "outcome", mode="before")
    @classmethod
    def normalize_responsibility_text(cls, value: str) -> str:
        return normalize_turn_text(str(value or ""))

    @field_validator("bindings", mode="before")
    @classmethod
    def normalize_and_reject_low_level_bindings(
        cls, value: Any,
    ) -> dict[str, Any]:
        normalized = _normalize_umi_binding_values(value)
        if not isinstance(normalized, dict):
            return normalized
        reject_forbidden_low_level_fields(normalized)
        _reject_planner_owned_bindings(normalized)
        return normalized

    @model_validator(mode="after")
    def validate_continuity_scope(self) -> "CognitiveResponsibilityProposal":
        if self.continuity_scope == "turn" and self.output_mode != "speech":
            raise ValueError(
                "turn-local Responsibility must be ordinary conversational speech"
            )
        return self


class UserMeaningUncertainty(BaseModel):
    """One semantic uncertainty that remains after UMI used its bounded context.

    This is not an instruction to ask the user. Goal Association may resolve an
    uncertainty from canonical Goal continuity; only uncertainty that remains after
    continuity resolution may become a Planner/SC clarification need.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    local_ref: str = Field(min_length=1, max_length=80)
    kind: Literal[
        "referent",
        "scope",
        "relation",
        "proposition",
        "communicative_intent",
        "other",
    ] = "other"
    description: str = Field(min_length=1, max_length=320)
    responsibility_refs: list[str] = Field(min_length=1, max_length=8)

    @field_validator("local_ref", "description", mode="before")
    @classmethod
    def normalize_uncertainty_text(cls, value: Any) -> str:
        return normalize_turn_text(str(value or ""))

    @field_validator("responsibility_refs", mode="before")
    @classmethod
    def normalize_responsibility_refs(cls, value: Any) -> list[str]:
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            raise ValueError("responsibility_refs must be an array")
        return list(
            dict.fromkeys(
                text
                for item in value
                if (text := normalize_turn_text(str(item or "")))
            )
        )



CognitiveActivationAuthority = Literal[
    "goal_association",
    "social_cognition",
    "planner",
]


class CognitiveActivationRequest(BaseModel):
    """UMI-authored request to wake an existing cognitive authority.

    The request decides only which already-defined cognitive owner is useful now
    and which accepted Responsibilities motivate that cognition.  It grants none
    of that owner's semantic authority: GA still owns Goal continuity, Planner
    still owns HOW, and SC still owns interaction.  Runtime may validate and
    schedule this request but must not infer an equivalent request from semantic
    labels when it is absent.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    authority: CognitiveActivationAuthority
    responsibility_refs: list[str] = Field(min_length=1, max_length=12)
    reason_summary: str = Field(default="", max_length=320)

    @field_validator("responsibility_refs", mode="before")
    @classmethod
    def normalize_refs(cls, value: Any) -> list[str]:
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            raise ValueError("cognitive activation responsibility_refs must be an array")
        normalized = [
            text
            for item in value
            if (text := normalize_turn_text(str(item or "")))
        ]
        if len(normalized) != len(set(normalized)):
            raise ValueError("cognitive activation responsibility_refs must be unique")
        return normalized

    @field_validator("reason_summary", mode="before")
    @classmethod
    def normalize_reason(cls, value: Any) -> str:
        return normalize_turn_text(str(value or ""))


class CoreInterpretationResult(BaseModel):
    """User Meaning Interpretation result in the current architecture.

    User Meaning Interpretation answers WHAT the human means in bounded conversational
    and situational context. It may determine that a Responsibility needs continuity,
    but it never chooses, creates, updates, cancels, or names a canonical Goal. Semantic
    uncertainty is context evidence, not a request to clarify; GA may first resolve it
    from Goal continuity and Planner/SC may clarify only what remains. Fast/Deep depth may change how much
    cognition is used, but not this authority boundary. There is
    deliberately no compatibility RouteDecision projection and no UMI-authored
    response/progress Activity, Capability choice, or Goal-state commit.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[2] = 2
    turn_id: str = Field(min_length=1, max_length=160)
    session_id: str = Field(min_length=1, max_length=160)
    authority: Literal["user_meaning_interpretation"] = "user_meaning_interpretation"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    language: str = Field(default="auto", min_length=1, max_length=64)
    responsibilities: list[CognitiveResponsibilityProposal] = Field(
        min_length=1,
        description=(
            "Complete set of independently satisfiable human outcomes. Emit one item "
            "per requested observable effect, including separate concurrent embodied "
            "and authored-vocal effects; coordination is a relation, not permission "
            "to collapse two effects into one item."
        ),
    )
    meaning_uncertainties: list[UserMeaningUncertainty] = Field(
        default_factory=list, max_length=12,
        description=(
            "Semantic ambiguity that remains only after UMI has used the bounded "
            "conversation, situation, activated-memory and continuity context available "
            "to it. This is evidence for later continuity/clarification resolution, not "
            "an instruction to ask the user."
        ),
    )
    cognitive_requests: list[CognitiveActivationRequest] = Field(
        default_factory=list, max_length=3,
        description=(
            "Model-authored requests to wake existing cognitive authorities. These requests "
            "schedule cognition only; they never author another role's semantic result."
        ),
    )

    @field_validator("turn_id", "session_id", "language", mode="before")
    @classmethod
    def normalize_text_fields(cls, value: str) -> str:
        return normalize_turn_text(str(value or ""))

    @model_validator(mode="after")
    def validate_responsibility_refs(self) -> "CoreInterpretationResult":
        refs = [item.local_ref for item in self.responsibilities]
        if len(refs) != len(set(refs)):
            raise ValueError("User Meaning Interpretation responsibility local_ref values must be unique")
        uncertainty_refs = [item.local_ref for item in self.meaning_uncertainties]
        if len(uncertainty_refs) != len(set(uncertainty_refs)):
            raise ValueError("User Meaning Interpretation uncertainty local_ref values must be unique")
        known = set(refs)
        scope_by_ref = {
            item.local_ref: item.continuity_scope for item in self.responsibilities
        }
        for uncertainty in self.meaning_uncertainties:
            unknown = set(uncertainty.responsibility_refs) - known
            if unknown:
                raise ValueError(
                    "meaning uncertainty references unknown Responsibilities: "
                    + ",".join(sorted(unknown))
                )
            scopes = {scope_by_ref[ref] for ref in uncertainty.responsibility_refs}
            if len(scopes) != 1:
                raise ValueError(
                    "one meaning uncertainty cannot span turn-local and goal-scoped "
                    "Responsibilities; UMI must keep those semantic uncertainties separate"
                )
        authorities = [item.authority for item in self.cognitive_requests]
        if len(authorities) != len(set(authorities)):
            raise ValueError("UMI may request each cognitive authority at most once")
        for request in self.cognitive_requests:
            unknown = set(request.responsibility_refs) - known
            if unknown:
                raise ValueError(
                    "cognitive activation references unknown Responsibilities: "
                    + ",".join(sorted(unknown))
                )
        planner_requested = "planner" in authorities
        ga_requested = "goal_association" in authorities
        if planner_requested and not ga_requested:
            raise ValueError(
                "initial Planner cognition requires a Goal Association request so effectful "
                "Work can reach canonical Goal binding"
            )
        ga_request = next(
            (item for item in self.cognitive_requests if item.authority == "goal_association"),
            None,
        )
        if ga_request is not None and set(ga_request.responsibility_refs) != known:
            raise ValueError(
                "initial Goal Association cognition is turn-wide and must cover every Responsibility"
            )
        return self


class PlannerReentryScope(BaseModel):
    """Immutable state-transition scope for one same-Planner re-entry.

    This is readiness/provenance, not another semantic owner.  It prevents a
    full conversation Goal projection from silently widening the exact Goal set
    affected by terminal Evidence, cancellation, Situation, time, or provider
    revalidation.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    trigger: Literal[
        "capability_result_reentry",
        "post_execution",
        "goal_cancellation_reentry",
        "situation_revision_reentry",
        "time_condition_reentry",
        "restored_provider_state_revalidation",
    ]
    goal_ids: tuple[str, ...] = Field(min_length=1, max_length=16)
    evidence_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=32)
    opportunity_id: str = Field(default="", max_length=200)
    source_plan_id: str = Field(default="", max_length=200)
    source_plan_fingerprint: str = Field(default="", max_length=128)

    @field_validator(
        "goal_ids",
        "evidence_refs",
        mode="before",
    )
    @classmethod
    def normalize_ids(cls, value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            raise ValueError("Planner re-entry identity fields must be arrays")
        return tuple(
            dict.fromkeys(
                text
                for item in value
                if (text := normalize_turn_text(str(item or "")))
            )
        )

    @field_validator(
        "opportunity_id",
        "source_plan_id",
        "source_plan_fingerprint",
        mode="before",
    )
    @classmethod
    def normalize_scalar_ids(cls, value: Any) -> str:
        return normalize_turn_text(str(value or ""))

    @model_validator(mode="after")
    def validate_trigger_evidence(self) -> "PlannerReentryScope":
        evidence_triggers = {
            "capability_result_reentry",
            "post_execution",
            "goal_cancellation_reentry",
        }
        if self.trigger in evidence_triggers and not self.evidence_refs:
            raise ValueError(
                f"Planner re-entry trigger={self.trigger} requires evidence_refs"
            )
        if self.trigger not in evidence_triggers and not self.opportunity_id:
            raise ValueError(
                f"Planner re-entry trigger={self.trigger} requires opportunity_id"
            )
        if bool(self.source_plan_id) != bool(self.source_plan_fingerprint):
            raise ValueError(
                "source_plan_id and source_plan_fingerprint must be supplied together"
            )
        return self


class CognitiveWorkRequest(BaseModel):
    """Typed WHAT→HOW handoff used by maintained cognitive work endpoints.

    This replaces RouteDecision-shaped requests in the Goal-driven runtime.  The
    request carries User Meaning Interpretation responsibilities explicitly together with
    Host-owned immutable source wording. UMI never regenerates that source copy;
    Planner realizes complete intent into arguments without adding omitted outcomes.
    Canonical
    Goal state and later Plan/Capability state remain in their own typed contracts.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    sid: str | None = None
    planning_task_id: str = Field(default="", max_length=200)
    text: str = ""
    language: str | None = None
    responsibilities: list[CognitiveResponsibilityProposal] = Field(min_length=1)
    interpretation_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    meaning_uncertainties: list[UserMeaningUncertainty] = Field(default_factory=list, max_length=12)
    cognitive_requests: list[CognitiveActivationRequest] = Field(default_factory=list, max_length=3)
    planner_reentry_scope: PlannerReentryScope | None = None
    context: dict[str, Any] = Field(default_factory=dict)
    history: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("text", mode="before")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return normalize_turn_text(str(value or ""))

    @property
    def meaning_uncertainty_descriptions(self) -> list[str]:
        return [item.description for item in self.meaning_uncertainties]

    @property
    def meaning_uncertainty_refs(self) -> set[str]:
        return {item.local_ref for item in self.meaning_uncertainties}

    @property
    def semantic_artifact_lineage(self) -> SemanticArtifactLineage:
        """Return trusted transport lineage without exposing it as model meaning."""

        context = self.context if isinstance(self.context, dict) else {}
        raw = context.get("semantic_artifact_lineage")
        if raw is None:
            return SemanticArtifactLineage()
        return SemanticArtifactLineage.model_validate(raw)

    @property
    def turn_envelope(self) -> UserTurnEnvelope | None:
        """Return the full immutable source envelope when this is an original-turn request.

        The envelope remains serialized inside the established context transport so this
        accessor strengthens typing/correlation without changing the frozen Work request
        wire. Re-entry requests may intentionally carry only validated source provenance.
        """

        context = self.context if isinstance(self.context, dict) else {}
        raw = context.get("user_turn_envelope")
        if isinstance(raw, UserTurnEnvelope):
            return raw
        if not isinstance(raw, dict):
            return None
        required = {
            "turn_id", "session_id", "conversation_id", "channel", "received_at",
            "original_input", "normalized_input", "quality", "reflex", "attention",
            "admission",
        }
        if not required.issubset(raw):
            return None
        return UserTurnEnvelope.model_validate(raw)

    @model_validator(mode="after")
    def validate_turn_envelope_reference(self) -> "CognitiveWorkRequest":
        envelope = self.turn_envelope
        if envelope is not None:
            if envelope.admission not in {"admit", "reflex_and_admit"}:
                raise ValueError("Cognitive Work requires an admitted UserTurnEnvelope")
            if envelope.normalized_input.text != self.text:
                raise ValueError("Cognitive Work text does not match UserTurnEnvelope")
            if self.sid is not None and str(self.sid).strip() and self.sid != envelope.session_id:
                raise ValueError("Cognitive Work session does not match UserTurnEnvelope")
            if (
                self.language is not None
                and str(self.language).strip()
                and self.language != envelope.normalized_input.language
            ):
                raise ValueError("Cognitive Work language does not match UserTurnEnvelope")

        lineage = self.semantic_artifact_lineage
        if not lineage.refs:
            return self
        if envelope is not None:
            lineage.require(semantic_artifact_ref(
                envelope, artifact_kind="user_turn", artifact_id=envelope.turn_id,
            ))
        context = self.context if isinstance(self.context, dict) else {}
        raw_core = context.get("core_interpretation")
        if isinstance(raw_core, dict):
            core = CoreInterpretationResult.model_validate(raw_core)
            lineage.require(semantic_artifact_ref(
                core, artifact_kind="user_meaning_interpretation", artifact_id=core.turn_id,
            ))
            for item in core.responsibilities:
                lineage.require(semantic_artifact_ref(
                    item, artifact_kind="responsibility",
                    artifact_id=f"{core.turn_id}:{item.local_ref}",
                ))
        return self

    @property
    def source_turn_provenance(self) -> dict[str, Any]:
        """Project immutable source wording without granting semantic authority.

        ``text`` is transport-normalized so model-facing work can compare turns
        deterministically.  Semantic owners must still be able to inspect the
        exact admitted source wording; the UserTurnEnvelope already owns that
        immutable evidence, so this is a computed prompt projection rather than
        another persisted copy.  A scoped Planner re-entry may supply the same
        projection without replaying the whole UserTurnEnvelope as a fresh turn.
        """

        if self.turn_envelope is not None:
            envelope = self.turn_envelope
            original = envelope.original_input.text
            return {
                "schema_version": 1,
                "turn_id": envelope.turn_id,
                "original_text": original,
                "original_text_sha256": hashlib.sha256(
                    original.encode("utf-8")
                ).hexdigest(),
                "language": envelope.normalized_input.language,
                "authority": "read_only_source_provenance",
            }

        context = self.context if isinstance(self.context, dict) else {}
        projected = context.get("source_turn_provenance")
        if isinstance(projected, dict):
            original = projected.get("original_text")
            digest = str(projected.get("original_text_sha256") or "").strip()
            if (
                projected.get("authority") == "read_only_source_provenance"
                and isinstance(original, str)
                and original
                and digest
                == hashlib.sha256(original.encode("utf-8")).hexdigest()
            ):
                return {
                    "schema_version": 1,
                    "turn_id": str(projected.get("turn_id") or ""),
                    "original_text": original,
                    "original_text_sha256": digest,
                    "language": str(
                        projected.get("language") or self.language or "auto"
                    ),
                    "authority": "read_only_source_provenance",
                }
        envelope = context.get("user_turn_envelope")
        if isinstance(envelope, dict):
            original = envelope.get("original_input")
            if isinstance(original, dict):
                value = original.get("text")
                if (
                    isinstance(value, str)
                    and value
                    and normalize_turn_text(value) == self.text
                ):
                    normalized = envelope.get("normalized_input")
                    language = (
                        normalized.get("language")
                        if isinstance(normalized, dict)
                        else self.language
                    )
                    return {
                        "schema_version": 1,
                        "turn_id": str(envelope.get("turn_id") or ""),
                        "original_text": value,
                        "original_text_sha256": hashlib.sha256(
                            value.encode("utf-8")
                        ).hexdigest(),
                        "language": str(language or self.language or "auto"),
                        "authority": "read_only_source_provenance",
                    }
        value = self.text
        return {
            "schema_version": 1,
            "turn_id": "",
            "original_text": value,
            "original_text_sha256": hashlib.sha256(value.encode("utf-8")).hexdigest(),
            "language": str(self.language or "auto"),
            "authority": "normalized_transport_fallback",
        }

    @property
    def original_user_text(self) -> str:
        """Return exact source wording from the validated provenance projection."""

        return str(self.source_turn_provenance.get("original_text") or self.text)
