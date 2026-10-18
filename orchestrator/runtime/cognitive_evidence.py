"""Cognitive Evidence recording for the goal-driven runtime.

``CognitiveEvidenceRecorder`` keeps bounded per-session records of Gateway,
runtime and outcome stages and their semantic artifact packets.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from pydantic import BaseModel

from shared.chromie_contracts.core_interpretation import (
    CoreInterpretationResult,
)
from shared.chromie_contracts.execution_outcome import (
    ExecutionOutcomeBundle,
    execution_outcome_fingerprint,
)
from shared.chromie_contracts.interaction import (
    InteractionResponse,
    CapabilityTrace,
)
from shared.chromie_contracts.semantic_artifact import (
    SemanticArtifactKind,
    SemanticArtifactLineage,
    SemanticArtifactPacket,
    SemanticArtifactRef,
    semantic_artifact_packet,
)
from shared.chromie_contracts.social_cognition import SocialCognitionResolution
from shared.chromie_contracts.plan import (
    CanonicalPlan,
)
from shared.chromie_contracts.user_turn import (
    AttentionReviewResult,
    GatewayContextSnapshot,
    UserTurnEnvelope,
)

from orchestrator.runtime.evidence_identity import runtime_identity_reference

from orchestrator.runtime.cognitive_runtime import (
    CognitiveRuntimeResolution,
    planner_authored_plan_payload,
)

logger = logging.getLogger(__name__)


class CognitiveEvidenceRecorder:
    """Append-only operational evidence and in-process rollout counters."""

    def __init__(
        self,
        path: Path,
        *,
        enabled: bool = True,
        include_text: bool = False,
        run_identity: dict[str, Any] | None = None,
        run_identity_path: Path | None = None,
    ) -> None:
        self.path = path
        self.enabled = enabled
        self.include_text = include_text
        self.run_identity = dict(run_identity) if run_identity is not None else None
        self.run_identity_path = run_identity_path
        self.counters: Counter[str] = Counter()
        self.total_latency_ms = 0.0

    @staticmethod
    def _text_digest(text: str) -> str:
        return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16]

    def _identity_reference(self) -> dict[str, Any]:
        return runtime_identity_reference(
            self.run_identity,
            path=self.run_identity_path,
        )

    @classmethod
    def semantic_artifact_packets(
        cls,
        resolution: "CognitiveRuntimeResolution",
        *,
        sid: str,
    ) -> list[SemanticArtifactPacket]:
        """Project accepted owner artifacts into immutable archival packets."""

        packets: list[SemanticArtifactPacket] = []
        seen: set[tuple[str, str, str]] = set()
        source = resolution.turn_envelope
        turn_id = source.turn_id if source is not None else str(sid or "")
        session_id = source.session_id if source is not None else str(sid or "")
        conversation_id = source.conversation_id if source is not None else ""

        def pack(
            payload: BaseModel | dict[str, Any],
            *,
            kind: SemanticArtifactKind,
            artifact_id: str,
            authority: str,
            parents: Iterable[SemanticArtifactRef] = (),
            artifact_session_id: str | None = None,
            artifact_turn_id: str | None = None,
        ) -> SemanticArtifactRef:
            packet = semantic_artifact_packet(
                payload,
                artifact_kind=kind,
                artifact_id=artifact_id,
                authority=authority,
                session_id=artifact_session_id or session_id,
                turn_id=artifact_turn_id if artifact_turn_id is not None else turn_id,
                conversation_id=conversation_id,
                parent_refs=parents,
            )
            key = (packet.ref.artifact_kind, packet.ref.artifact_id, packet.ref.payload_sha256)
            if key not in seen:
                seen.add(key)
                packets.append(packet)
            return packet.ref

        turn_ref = (
            pack(
                source,
                kind="user_turn",
                artifact_id=source.turn_id,
                authority="cognitive_gateway",
                artifact_session_id=source.session_id,
                artifact_turn_id=source.turn_id,
            )
            if source is not None
            else None
        )

        response = resolution.interaction_response
        transported_lineage: SemanticArtifactLineage | None = None
        transported_refs: dict[tuple[str, str], SemanticArtifactRef] = {}
        if response is not None and isinstance(response.metadata, dict):
            raw_lineage = response.metadata.get("semantic_artifact_lineage")
            if raw_lineage is not None:
                transported_lineage = SemanticArtifactLineage.model_validate(
                    raw_lineage
                )
                transported_refs = {
                    (ref.artifact_kind, ref.artifact_id): ref
                    for ref in transported_lineage.refs
                }

        def response_lineage_carries(ref: SemanticArtifactRef) -> bool:
            if transported_lineage is None:
                return True
            carried = transported_refs.get((ref.artifact_kind, ref.artifact_id))
            if carried is None:
                return False
            if carried.payload_sha256 != ref.payload_sha256:
                raise ValueError(
                    "semantic artifact lineage digest mismatch for "
                    f"{ref.artifact_kind}:{ref.artifact_id}"
                )
            return True

        metadata = resolution.metadata if isinstance(resolution.metadata, dict) else {}
        raw_core = metadata.get("core_interpretation")
        umi_ref: SemanticArtifactRef | None = None
        responsibility_refs: dict[str, SemanticArtifactRef] = {}
        if isinstance(raw_core, dict):
            core = CoreInterpretationResult.model_validate(raw_core)
            umi_ref = pack(
                core,
                kind="user_meaning_interpretation",
                artifact_id=core.turn_id,
                authority="user_meaning_interpretation",
                parents=[ref for ref in (turn_ref,) if ref is not None],
                artifact_session_id=core.session_id,
                artifact_turn_id=core.turn_id,
            )
            for item in core.responsibilities:
                responsibility_refs[item.local_ref] = pack(
                    item,
                    kind="responsibility",
                    artifact_id=f"{core.turn_id}:{item.local_ref}",
                    authority="user_meaning_interpretation",
                    parents=[ref for ref in (turn_ref, umi_ref) if ref is not None],
                    artifact_session_id=core.session_id,
                    artifact_turn_id=core.turn_id,
                )

        association = resolution.goal_association
        ga_ref: SemanticArtifactRef | None = None
        goal_refs: dict[str, SemanticArtifactRef] = {}
        if association is not None:
            ga_ref = pack(
                association,
                kind="goal_association",
                artifact_id=association.turn_id,
                authority="goal_association",
                parents=[
                    *[ref for ref in (turn_ref, umi_ref) if ref is not None],
                    *responsibility_refs.values(),
                ],
                artifact_turn_id=association.turn_id,
            )
            for index, goal in enumerate(association.new_goals):
                goal_id = str(goal.goal_id or f"{association.turn_id}:new:{index}")
                goal_refs[goal_id] = pack(
                    goal,
                    kind="goal",
                    artifact_id=goal_id,
                    authority="goal_association",
                    parents=[
                        ga_ref,
                        *(
                            responsibility_refs[ref]
                            for ref in goal.source_responsibility_refs
                            if ref in responsibility_refs
                        ),
                    ],
                    artifact_turn_id=association.turn_id,
                )

        plan_refs: list[SemanticArtifactRef] = []
        for plan in (resolution.fast_plan, resolution.terminal_plan):
            if plan is None:
                continue
            plan_ref = pack(
                planner_authored_plan_payload(plan),
                kind="planner_plan",
                artifact_id=plan.plan_id,
                authority="planner",
                parents=[
                    *[ref for ref in (umi_ref, ga_ref) if ref is not None],
                    *goal_refs.values(),
                ],
            )
            if plan_ref not in plan_refs:
                plan_refs.append(plan_ref)

        raw_social = (
            response.metadata.get("social_cognition_resolution")
            if response is not None and isinstance(response.metadata, dict)
            else None
        )
        social_ref: SemanticArtifactRef | None = None
        communicative_act_refs: list[SemanticArtifactRef] = []
        if isinstance(raw_social, dict):
            social = SocialCognitionResolution.model_validate(raw_social)
            social_ref = pack(
                social,
                kind="social_cognition",
                artifact_id=social.request_id,
                authority="social_cognition",
                parents=[
                    *[
                        ref for ref in (umi_ref, ga_ref)
                        if ref is not None and response_lineage_carries(ref)
                    ],
                    *[ref for ref in plan_refs if response_lineage_carries(ref)],
                ],
            )
            for act in social.activities:
                act_ref = pack(
                    act,
                    kind="communicative_act",
                    artifact_id=act.activity_id,
                    authority="social_cognition",
                    parents=[
                        social_ref,
                        *(
                            responsibility_refs[ref]
                            for ref in act.source_responsibility_refs
                            if ref in responsibility_refs
                            and response_lineage_carries(responsibility_refs[ref])
                        ),
                        *(
                            goal_refs[goal_id]
                            for goal_id in act.source_goal_ids
                            if goal_id in goal_refs
                            and response_lineage_carries(goal_refs[goal_id])
                        ),
                    ],
                )
                communicative_act_refs.append(act_ref)

        if transported_lineage is not None:
            # Response lineage is the set that existed when that presentation
            # artifact was authored. Concurrent sibling cognition may finish later
            # and legitimately appear in the final resolution without becoming an
            # ancestor of an already-authored SC response. Validate the immutable
            # refs that the response actually carried; never serialize the DAG by
            # requiring future GA/Planner siblings retroactively.
            for expected in (
                *[ref for ref in (turn_ref, umi_ref) if ref is not None],
                *responsibility_refs.values(),
                *([social_ref] if social_ref is not None else []),
                *communicative_act_refs,
            ):
                transported_lineage.require(expected)
            packet_refs = {
                (packet.ref.artifact_kind, packet.ref.artifact_id): packet.ref
                for packet in packets
            }
            for carried in transported_lineage.refs:
                expected = packet_refs.get(
                    (carried.artifact_kind, carried.artifact_id)
                )
                if (
                    expected is not None
                    and expected.payload_sha256 != carried.payload_sha256
                ):
                    raise ValueError(
                        "semantic artifact lineage digest mismatch for "
                        f"{carried.artifact_kind}:{carried.artifact_id}"
                    )

        return packets

    def record_gateway(
        self,
        envelope: UserTurnEnvelope,
        *,
        text: str,
        context_snapshot: GatewayContextSnapshot | None = None,
        attention_review: AttentionReviewResult | None = None,
    ) -> None:
        """Append the pre-Core admission decision for one received turn."""

        self.counters[f"gateway_admission:{envelope.admission}"] += 1
        self.counters[f"gateway_attention:{envelope.attention.disposition}"] += 1
        if not self.enabled:
            return
        payload: dict[str, Any] = {
            "schema_version": 2,
            "event": "cognitive_gateway_admission",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "sid": envelope.session_id,
            "turn_id": envelope.turn_id,
            "conversation_id": envelope.conversation_id,
            "channel": envelope.channel,
            "admission": envelope.admission,
            "core_eligible": envelope.admission in {"admit", "reflex_and_admit"},
            "quality": envelope.quality.model_dump(mode="json"),
            "reflex": envelope.reflex.model_dump(mode="json"),
            "attention": envelope.attention.model_dump(mode="json"),
            "context_snapshot_digest": (
                context_snapshot.digest if context_snapshot is not None else None
            ),
            "context_reference_types": [item.context_type for item in envelope.context_refs],
            "text_chars": len(text or ""),
            "text_sha256_16": self._text_digest(text),
            "run_identity": self._identity_reference(),
        }
        if attention_review is not None:
            payload["attention_review"] = attention_review.model_dump(mode="json")
        if self.include_text:
            payload["text"] = text
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")

    def record(self, resolution: CognitiveRuntimeResolution, *, sid: str, text: str) -> None:
        self.counters[f"status:{resolution.status}"] += 1
        self.counters[f"mode:{resolution.mode}"] += 1
        failure_class = str(resolution.metadata.get("failure_class") or "").strip()
        attribution = str(resolution.metadata.get("architecture_attribution") or "").strip()
        if failure_class:
            self.counters[f"failure_class:{failure_class}"] += 1
        if attribution:
            self.counters[f"architecture_attribution:{attribution}"] += 1
        fast_path = str(resolution.metadata.get("fast_planner_path") or "").strip()
        if fast_path:
            self.counters[f"fast_planner_path:{fast_path}"] += 1
        if (
            fast_path == "terminal"
            and resolution.fast_plan is not None
            and len(resolution.fast_plan.goal_ids) > 1
        ):
            self.counters["fast_terminal_multi_goal"] += 1
        if fast_path == "contract_failure":
            self.counters["fast_contract_failure"] += 1
        self.counters["turns"] += 1
        total_ms = float(resolution.timings_ms.get("total", 0.0))
        self.total_latency_ms += total_ms
        if not self.enabled:
            return
        artifact_packets = self.semantic_artifact_packets(resolution, sid=sid)
        payload = {
            "schema_version": 2,
            "event": "cognitive_runtime_resolution",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "sid": sid,
            "turn_id": (
                resolution.turn_envelope.turn_id if resolution.turn_envelope is not None else sid
            ),
            "conversation_id": (
                resolution.turn_envelope.conversation_id
                if resolution.turn_envelope is not None
                else None
            ),
            "run_identity": self._identity_reference(),
            "semantic_artifact_envelopes": [
                item.envelope.model_dump(mode="json") for item in artifact_packets
            ],
            "mode": resolution.mode,
            "status": resolution.status,
            "user_turn_envelope": (
                resolution.turn_envelope.model_dump(mode="json")
                if resolution.turn_envelope is not None
                else None
            ),
            "text_chars": len(text or ""),
            "text_sha256_16": self._text_digest(text),
            "goal_association": (
                resolution.goal_association.model_dump(mode="json", exclude_none=True)
                if resolution.goal_association is not None
                else None
            ),
            "fast_advance": (
                resolution.fast_advance.model_dump(mode="json", exclude_none=True)
                if resolution.fast_advance is not None
                else None
            ),
            "fast_plan": self._plan_summary(resolution.fast_plan),
            "terminal_plan": self._plan_summary(resolution.terminal_plan),
            "interaction": self._interaction_summary(resolution.interaction_response),
            "goal_state_results": resolution.goal_state_results,
            "timings_ms": resolution.timings_ms,
            "fallback_reason": resolution.fallback_reason,
            "metadata": resolution.metadata,
            "core_interpretation": (
                resolution.metadata.get("core_interpretation")
                if isinstance(resolution.metadata, dict)
                else None
            ),
        }
        if self.include_text:
            payload["text"] = text
            payload["semantic_artifact_packets"] = [
                item.model_dump(mode="json") for item in artifact_packets
            ]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")

    @staticmethod
    def provider_realization_diagnostics(
        traces: Iterable[CapabilityTrace],
    ) -> list[dict[str, Any]]:
        """Project trusted semantic->provider lowering for diagnostics only."""

        rows: list[dict[str, Any]] = []
        for trace in traces:
            for event in trace.events:
                if event.type != "provider_realization":
                    continue
                data = event.data if isinstance(event.data, dict) else {}
                rows.append({
                    "trace_id": trace.trace_id,
                    "request_id": trace.request_id,
                    "capability_id": trace.capability_id,
                    "provider_id": trace.provider_id,
                    "timestamp": event.timestamp.isoformat(),
                    "semantic_args": dict(data.get("semantic_args") or {}),
                    "provider_args": dict(data.get("provider_args") or {}),
                    "semantic_facade_applied": bool(
                        data.get("semantic_facade_applied")
                    ),
                })
        return rows

    def record_outcome(
        self,
        bundle: ExecutionOutcomeBundle,
        *,
        sid: str,
        final_response: InteractionResponse | None,
        delivery_status: str,
        suppression_reason: str = "",
        goal_state_results: list[dict[str, Any]] | None = None,
        capability_traces: Iterable[CapabilityTrace] = (),
    ) -> None:
        """Append the trusted post-execution half of a cognitive turn."""

        self.counters["outcome_bundles"] += 1
        self.counters[f"outcome_status:{bundle.aggregate_status}"] += 1
        self.counters[f"outcome_delivery:{delivery_status}"] += 1
        if not self.enabled:
            return
        outcome_packet = semantic_artifact_packet(
            bundle,
            artifact_kind="execution_outcome",
            artifact_id=bundle.outcome_id,
            authority="trusted_runtime",
            session_id=sid,
            turn_id=bundle.turn_id,
        )
        payload = {
            "schema_version": 2,
            "event": "cognitive_execution_outcome",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "sid": sid,
            "turn_id": bundle.turn_id,
            "interaction_id": bundle.interaction_id,
            "run_identity": self._identity_reference(),
            "outcome_fingerprint": execution_outcome_fingerprint(bundle),
            "semantic_artifact_envelopes": [
                outcome_packet.envelope.model_dump(mode="json")
            ],
            "outcome_bundle": bundle.model_dump(mode="json", exclude_none=True),
            "goal_state_results": list(goal_state_results or []),
            "final_response": self._interaction_summary(final_response),
            "delivery_status": delivery_status,
            "suppression_reason": suppression_reason,
            "provider_realizations": self.provider_realization_diagnostics(
                capability_traces
            ),
        }
        if self.include_text:
            payload["semantic_artifact_packets"] = [
                outcome_packet.model_dump(mode="json")
            ]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")

    @staticmethod
    def _plan_summary(plan: CanonicalPlan | None) -> dict[str, Any] | None:
        if plan is None:
            return None
        return {
            "plan_id": plan.plan_id,
            "planner_tier": plan.planner_tier,
            "disposition": plan.disposition,
            "coverage": plan.coverage,
            "confidence": plan.confidence,
            "goal_ids": plan.goal_ids,
            "step_ids": [item.step_id for item in plan.steps],
            "capability_ids": [item.capability_id for item in plan.steps],
            "selected_agent_skills": [
                item.model_dump(mode="json") for item in plan.selected_agent_skills
            ],
            "goal_satisfaction": (
                plan.goal_satisfaction.model_dump(mode="json")
                if plan.goal_satisfaction is not None
                else None
            ),
        }

    @staticmethod
    def _interaction_summary(response: InteractionResponse | None) -> dict[str, Any] | None:
        if response is None:
            return None
        return {
            "interaction_id": response.interaction_id,
            "status": response.status,
            "speech_count": len(response.speech),
            "capability_ids": [item.capability_id for item in response.capabilities],
            "requires_confirmation": response.requires_confirmation,
        }

    def snapshot(self) -> dict[str, Any]:
        turns = int(self.counters.get("turns", 0))
        return {
            "turns": turns,
            "mean_total_latency_ms": (round(self.total_latency_ms / turns, 1) if turns else 0.0),
            "counters": dict(sorted(self.counters.items())),
            "path": str(self.path),
            "enabled": self.enabled,
            "include_text": self.include_text,
        }
