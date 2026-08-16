from __future__ import annotations

from collections.abc import Awaitable
from typing import Any, Literal, Protocol

from pydantic import ValidationError

try:
    from chromie_contracts.interaction import (
        InteractionResponse,
        InteractionSpeech,
        CapabilityRequest,
    )
    from chromie_contracts.task_proposal import TaskProposal
except ImportError:  # pragma: no cover - repository development path
    from shared.chromie_contracts.interaction import (
        InteractionResponse,
        InteractionSpeech,
        CapabilityRequest,
    )
    from shared.chromie_contracts.task_proposal import TaskProposal

from .schema import (
    ActionCommand,
    ActionTarget,
    AgentResult,
    AgentRunRequest,
    AgentStatus,
    MemoryUpdate,
    Priority,
    SpeakItem,
    SpeakStyle,
)

InteractionOutputMode = Literal["native", "legacy-adapter"]


def _validation_error_summary(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        parts: list[str] = []
        for item in exc.errors(include_url=False, include_input=False)[:4]:
            location = ".".join(str(part) for part in item.get("loc", ())) or "$"
            parts.append(f"{location}: {item.get('msg', 'invalid value')}")
        suffix = "" if len(exc.errors()) <= 4 else f"; +{len(exc.errors()) - 4} more"
        return "; ".join(parts) + suffix
    message = " ".join(str(exc).split())
    return message[:500] or type(exc).__name__


class LegacyActionCapabilityMapper:
    """Map the established ActionCommand contract to trusted CapabilityRequest values."""

    _RESERVED_METADATA_KEYS = frozenset(
        {
            "legacy_target",
            "legacy_action_type",
            "legacy_params",
            "legacy_blocking",
            "legacy_timeout_ms",
            "legacy_reason",
        }
    )

    def to_capability(self, action: ActionCommand) -> CapabilityRequest:
        capability_id, args = self._named_capability(action)
        translated_named_capability = capability_id != action.type
        return CapabilityRequest(
            request_id=action.id,
            capability_id=capability_id,
            capability_version=action.metadata.get("capability_version"),
            args=args,
            timing="sequential" if action.blocking else "parallel",
            timeout_ms=None if translated_named_capability else action.timeout_ms,
            requires_confirmation=action.requires_confirmation,
            metadata={
                **action.metadata,
                "legacy_target": action.target,
                "legacy_action_type": action.type,
                "legacy_params": dict(action.params),
                "legacy_blocking": action.blocking,
                "legacy_timeout_ms": action.timeout_ms,
                "legacy_reason": action.reason,
            },
        )

    def to_action(self, request: CapabilityRequest) -> ActionCommand:
        metadata = request.metadata
        action_type = str(metadata.get("legacy_action_type") or request.capability_id)
        target = str(metadata.get("legacy_target") or "tool_executor")
        raw_params = metadata.get("legacy_params")
        params = (
            dict(raw_params)
            if isinstance(raw_params, dict)
            else self._legacy_params_from_named_capability(request)
        )
        action_metadata = {
            key: value
            for key, value in metadata.items()
            if key not in self._RESERVED_METADATA_KEYS
        }
        return ActionCommand(
            id=request.request_id,
            target=target,  # type: ignore[arg-type]
            type=action_type,
            params=params,
            blocking=bool(metadata.get("legacy_blocking", request.timing == "sequential")),
            timeout_ms=metadata.get("legacy_timeout_ms", request.timeout_ms),
            requires_confirmation=request.requires_confirmation,
            reason=metadata.get("legacy_reason"),
            metadata=action_metadata,
        )

    def is_legacy_action_capability(self, request: CapabilityRequest) -> bool:
        return "legacy_action_type" in request.metadata

    def _named_capability(self, action: ActionCommand) -> tuple[str, dict[str, Any]]:
        if action.type == "head.nod":
            return "soridormi.nod_yes", {
                "count": max(2, int(action.params.get("times", 1))),
            }
        if action.type == "head.shake":
            return "soridormi.shake_no", {
                "count": max(2, int(action.params.get("times", 1))),
            }
        if action.type == "head.look_at_user":
            duration_ms = action.params.get("duration_ms")
            args: dict[str, Any] = {}
            if isinstance(duration_ms, (int, float)) and duration_ms > 0:
                args["duration_s"] = duration_ms / 1000.0
            return "soridormi.look_at_person", args
        return str(action.metadata.get("capability_id") or action.type), dict(action.params)

    def _legacy_params_from_named_capability(self, request: CapabilityRequest) -> dict[str, Any]:
        if request.capability_id == "soridormi.nod_yes":
            return {"times": int(request.args.get("count", 2))}
        if request.capability_id == "soridormi.shake_no":
            return {"times": int(request.args.get("count", 2))}
        if request.capability_id == "soridormi.look_at_person":
            duration_s = request.args.get("duration_s")
            if isinstance(duration_s, (int, float)) and duration_s > 0:
                return {"duration_ms": int(duration_s * 1000)}
            return {}
        return dict(request.args)


class InteractionDraft:
    """Native InteractionResponse accumulator used by the Agent pipeline.

    Existing specialized agents still use the established helper surface
    (`add_action`, `speak_immediate`, and so on), but those operations are
    projected into InteractionSpeech and CapabilityRequest objects immediately.
    There is no AgentResult-to-InteractionResponse conversion at the end of the
    native pipeline.
    """

    def __init__(self) -> None:
        self.status: AgentStatus = "ok"
        self.reason: str | None = None
        self.requires_confirmation = False
        self.memory_updates: list[MemoryUpdate] = []
        self.handled_by: list[str] = []
        self.trace: list[str] = []
        self.metadata: dict[str, Any] = {}
        self._speech: list[InteractionSpeech] = []
        self._capabilities: list[CapabilityRequest] = []
        self._mapper = LegacyActionCapabilityMapper()

    @property
    def speak_immediate(self) -> list[SpeakItem]:
        return [
            self._to_speak_item(item)
            for item in self._speech
            if item.timing != "after_capabilities"
        ]

    @speak_immediate.setter
    def speak_immediate(self, items: list[SpeakItem]) -> None:
        after = [item for item in self._speech if item.timing == "after_capabilities"]
        self._speech = [self._to_interaction_speech(item, timing="immediate") for item in items]
        self._speech.extend(after)

    @property
    def speak_after(self) -> list[SpeakItem]:
        return [
            self._to_speak_item(item)
            for item in self._speech
            if item.timing == "after_capabilities"
        ]

    @speak_after.setter
    def speak_after(self, items: list[SpeakItem]) -> None:
        immediate = [item for item in self._speech if item.timing != "after_capabilities"]
        self._speech = immediate + [
            self._to_interaction_speech(item, timing="after_capabilities") for item in items
        ]

    @property
    def actions(self) -> list[ActionCommand]:
        return [
            self._mapper.to_action(item)
            for item in self._capabilities
            if self._mapper.is_legacy_action_capability(item)
        ]

    @actions.setter
    def actions(self, actions: list[ActionCommand]) -> None:
        native_only = [
            item
            for item in self._capabilities
            if not self._mapper.is_legacy_action_capability(item)
        ]
        self._capabilities = native_only + [self._mapper.to_capability(action) for action in actions]
        self.requires_confirmation = any(
            item.requires_confirmation for item in self._capabilities
        )

    def add_speak_immediate(
        self,
        text: str | None,
        *,
        style: SpeakStyle = "brief",
        priority: Priority = "normal",
        timing: Literal["immediate", "parallel", "sequential"] = "immediate",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        normalized = (text or "").strip()
        if normalized:
            self._speech.append(
                InteractionSpeech(
                    text=normalized,
                    timing=timing,
                    style=style,
                    priority=priority,
                    metadata=metadata or {},
                )
            )

    def add_speak_after(
        self,
        text: str | None,
        *,
        style: SpeakStyle = "brief",
        priority: Priority = "normal",
        after_action_id: str | None = None,
    ) -> None:
        normalized = (text or "").strip()
        if normalized:
            metadata: dict[str, Any] = {}
            if after_action_id:
                metadata["after_action_id"] = after_action_id
            self._speech.append(
                InteractionSpeech(
                    text=normalized,
                    timing="after_capabilities",
                    style=style,
                    priority=priority,
                    metadata=metadata,
                )
            )

    def normalize_speech(self, max_chars: int) -> None:
        immediate = [item for item in self._speech if item.timing != "after_capabilities"]
        after = [item for item in self._speech if item.timing == "after_capabilities"]
        self._speech = [
            *self._dedupe_and_trim_speech(immediate, max_chars),
            *self._dedupe_and_trim_speech(after, max_chars),
        ]

    def add_action(
        self,
        target: ActionTarget,
        action_type: str,
        *,
        params: dict[str, Any] | None = None,
        blocking: bool = False,
        timeout_ms: int | None = None,
        requires_confirmation: bool = False,
        reason: str | None = None,
    ) -> ActionCommand:
        action = ActionCommand(
            target=target,
            type=action_type,
            params=params or {},
            blocking=blocking,
            timeout_ms=timeout_ms,
            requires_confirmation=requires_confirmation,
            reason=reason,
        )
        self._capabilities.append(self._mapper.to_capability(action))
        if requires_confirmation:
            self.requires_confirmation = True
        return action

    def add_capability(self, request: CapabilityRequest) -> CapabilityRequest:
        self._capabilities.append(request)
        if request.requires_confirmation:
            self.requires_confirmation = True
        return request

    def add_task_graph(self, graph: dict[str, Any]) -> CapabilityRequest:
        requires_confirmation = self.requires_confirmation or bool(
            graph.get("requires_confirmation")
        )
        request = CapabilityRequest(
            capability_id="chromie.task_graph.execute",
            args={"graph": graph},
            timing="sequential",
            requires_confirmation=requires_confirmation,
            metadata={"source": "task_graph_planner"},
        )
        self._capabilities.append(request)
        if requires_confirmation:
            self.requires_confirmation = True
        return request

    def to_response(self) -> InteractionResponse:
        status = "refused" if self.status == "blocked" else self.status
        agent_task_proposals = _agent_task_proposals(
            self._speech,
            self._capabilities,
        )
        return InteractionResponse.model_validate(
            {
                "status": status,
                "speech": [item.model_dump(mode="json") for item in self._speech],
                "capabilities": [item.model_dump(mode="json") for item in self._capabilities],
                "requires_confirmation": self.requires_confirmation,
                "reason": self.reason,
                "metadata": {
                    **self.metadata,
                    "interaction_output_mode": "native",
                    "handled_by": list(self.handled_by),
                    "trace": list(self.trace),
                    "memory_updates": [
                        update.model_dump(mode="json") for update in self.memory_updates
                    ],
                    "agent_task_proposals": agent_task_proposals,
                },
            }
        )

    def _to_speak_item(self, item: InteractionSpeech) -> SpeakItem:
        return SpeakItem(
            text=item.text,
            style=item.style,  # type: ignore[arg-type]
            priority=item.priority,  # type: ignore[arg-type]
            interruptible=item.interruptible,
            after_action_id=item.metadata.get("after_action_id"),
            metadata={
                key: value
                for key, value in item.metadata.items()
                if key != "after_action_id"
            },
        )

    def _to_interaction_speech(
        self,
        item: SpeakItem,
        *,
        timing: Literal["immediate", "after_capabilities"],
    ) -> InteractionSpeech:
        metadata = dict(item.metadata)
        if item.after_action_id:
            metadata["after_action_id"] = item.after_action_id
        return InteractionSpeech(
            text=item.text,
            timing=timing,
            style=item.style,
            priority=item.priority,
            interruptible=item.interruptible,
            metadata=metadata,
        )

    def _dedupe_and_trim_speech(
        self,
        items: list[InteractionSpeech],
        max_chars: int,
    ) -> list[InteractionSpeech]:
        seen: set[str] = set()
        out: list[InteractionSpeech] = []
        for item in items:
            text = " ".join(item.text.strip().split())
            if not text or text in seen:
                continue
            if len(text) > max_chars:
                text = text[:max_chars].rstrip("，,。.!！?？ ")
                text += "。" if any("\u4e00" <= ch <= "\u9fff" for ch in text) else "."
            seen.add(text)
            out.append(item.model_copy(update={"text": text}))
        return out


class AgentResultInteractionAdapter:
    """Convert the established AgentResult into InteractionResponse.

    This adapter is retained for explicit compatibility mode and opt-in native
    validation fallback. The default `/interaction` path does not use it.
    """

    def __init__(self) -> None:
        self._mapper = LegacyActionCapabilityMapper()

    def convert(self, result: AgentResult) -> InteractionResponse:
        speech = [
            InteractionSpeech(
                text=item.text,
                timing="immediate",
                style=item.style,
                priority=item.priority,
                interruptible=item.interruptible,
                metadata=item.metadata,
            )
            for item in result.speak_immediate
        ]
        speech.extend(
            InteractionSpeech(
                text=item.text,
                timing="after_capabilities",
                style=item.style,
                priority=item.priority,
                interruptible=item.interruptible,
                metadata=item.metadata,
            )
            for item in result.speak_after
        )
        capabilities = [self._mapper.to_capability(action) for action in result.actions]
        capabilities.extend(
            CapabilityRequest(
                capability_id="chromie.task_graph.execute",
                args={"graph": graph},
                timing="sequential",
                requires_confirmation=result.requires_confirmation
                or bool(graph.get("requires_confirmation")),
            )
            for graph in result.task_graphs
        )
        agent_task_proposals = _agent_task_proposals(speech, capabilities)
        return InteractionResponse(
            status="refused" if result.status == "blocked" else result.status,
            speech=speech,
            capabilities=capabilities,
            requires_confirmation=result.requires_confirmation,
            reason=result.reason,
            metadata={
                "interaction_output_mode": "legacy-adapter",
                "handled_by": result.handled_by,
                "legacy_trace": result.trace,
                "memory_updates": [
                    update.model_dump(mode="json") for update in result.memory_updates
                ],
                "agent_task_proposals": agent_task_proposals,
            },
        )


class NativeInteractionRuntime(Protocol):
    def run(
        self, request: AgentRunRequest
    ) -> Awaitable[InteractionResponse | dict[str, Any]]: ...


class LegacyAgentRuntime(Protocol):
    def run(self, request: AgentRunRequest) -> Awaitable[AgentResult]: ...


class NativeInteractionOutputError(RuntimeError):
    """Raised when native Agent output does not satisfy InteractionResponse."""


def _agent_task_proposals(
    speech: list[InteractionSpeech],
    capabilities: list[CapabilityRequest],
) -> list[dict[str, Any]]:
    proposals: list[dict[str, Any]] = []
    for index, item in enumerate(speech):
        proposals.append(
            TaskProposal(
                id=f"agent:speech:{item.id}",
                source=str(item.metadata.get("source") or "agent"),
                proposal_kind="speech",
                task_type="speech.speak",
                capability_id="chromie.speak",
                state="committed",
                reason="Agent speech committed to InteractionResponse",
                effectful=False,
                priority=item.priority,
                sequence=index,
                speech_id=item.id,
                timing=item.timing,
                text_chars=len(item.text),
            ).model_dump(mode="json", exclude_none=True)
        )
    offset = len(proposals)
    for index, item in enumerate(capabilities):
        if item.metadata.get("auxiliary_social_attention") is True:
            continue
        capability_id = item.capability_id
        proposals.append(
            TaskProposal(
                id=f"agent:skill:{item.request_id}",
                source=str(item.metadata.get("source") or "agent"),
                proposal_kind="skill",
                task_type=_task_type_for_capability(capability_id),
                state="committed",
                reason="Agent skill committed to InteractionResponse",
                effectful=_is_effectful_skill(capability_id),
                priority="normal",
                sequence=offset + index,
                capability_id=capability_id,
                request_id=item.request_id,
                timing=item.timing,
                requires_confirmation=item.requires_confirmation,
            ).model_dump(mode="json", exclude_none=True)
        )
    return proposals


def _task_type_for_capability(capability_id: str) -> str:
    if capability_id == "chromie.speak":
        return "speech.speak"
    if capability_id == "session.interrupt":
        return "task.cancel_current_action"
    if capability_id == "chromie.task_graph.execute":
        return "task.execute_task_graph"
    return "task.execute_capability"


def _is_effectful_skill(capability_id: str) -> bool:
    return (
        capability_id.startswith("soridormi.")
        or capability_id == "session.interrupt"
        or capability_id == "chromie.task_graph.execute"
        or (
            capability_id.startswith("chromie.")
            and capability_id != "chromie.speak"
        )
    )


class InteractionOutputCoordinator:
    """Select and validate the native or compatibility interaction path."""

    def __init__(
        self,
        native_runtime: NativeInteractionRuntime,
        legacy_runtime: LegacyAgentRuntime,
        *,
        mode: InteractionOutputMode = "native",
        fallback_to_legacy: bool = False,
        adapter: AgentResultInteractionAdapter | None = None,
    ) -> None:
        if mode not in {"native", "legacy-adapter"}:
            raise ValueError(f"unsupported interaction output mode: {mode!r}")
        self.native_runtime = native_runtime
        self.legacy_runtime = legacy_runtime
        self.mode = mode
        self.fallback_to_legacy = fallback_to_legacy
        self.adapter = adapter or AgentResultInteractionAdapter()

    async def run(self, request: AgentRunRequest) -> InteractionResponse:
        if self.mode == "legacy-adapter":
            return await self._run_legacy(request, output_mode="legacy-adapter")

        try:
            candidate = await self.native_runtime.run(request)
            return self._validate_native(candidate)
        except NativeInteractionOutputError as exc:
            if not self.fallback_to_legacy:
                raise
            response = await self._run_legacy(
                request,
                output_mode="legacy-fallback",
            )
            return response.model_copy(
                deep=True,
                update={
                    "metadata": {
                        **response.metadata,
                        "native_validation_error": f"{type(exc).__name__}: {exc}",
                    }
                },
            )

    def _validate_native(
        self,
        candidate: InteractionResponse | dict[str, Any],
    ) -> InteractionResponse:
        raw = (
            candidate.model_dump(mode="json")
            if isinstance(candidate, InteractionResponse)
            else candidate
        )
        try:
            response = InteractionResponse.model_validate(raw)
        except (ValidationError, TypeError, ValueError) as exc:
            raise NativeInteractionOutputError(
                "native InteractionResponse validation failed: "
                + _validation_error_summary(exc)
            ) from exc
        return response.model_copy(
            deep=True,
            update={
                "metadata": {
                    **response.metadata,
                    "interaction_output_mode": "native",
                }
            },
        )

    async def _run_legacy(
        self,
        request: AgentRunRequest,
        *,
        output_mode: str,
    ) -> InteractionResponse:
        response = self.adapter.convert(await self.legacy_runtime.run(request))
        return response.model_copy(
            deep=True,
            update={
                "metadata": {
                    **response.metadata,
                    "interaction_output_mode": output_mode,
                }
            },
        )
