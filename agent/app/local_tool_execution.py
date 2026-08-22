from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .capabilities.models import CapabilityRegistry, ToolCapability
from .clients.external_information_client import (
    ExternalInformationError,
    ExternalInformationQuery,
    HttpExternalInformationClient,
)
from .clients.weather_client import (
    OpenMeteoWeatherClient,
    WeatherLocationContext,
    WeatherLookupError,
    WeatherQuery,
    WeatherReport,
    format_weather_brief,
    weather_code_text,
)

try:
    from chromie_contracts.json_schema import json_schema_validation_errors
    from chromie_contracts.tool_result import ToolExecutionRequest, ToolExecutionResponse
except ImportError:  # pragma: no cover - repository development path
    from shared.chromie_contracts.json_schema import json_schema_validation_errors
    from shared.chromie_contracts.tool_result import ToolExecutionRequest, ToolExecutionResponse

logger = logging.getLogger("chromie.agent.local_tool_execution")


@dataclass(frozen=True, slots=True)
class LocalToolResult:
    output: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)


ToolHandler = Callable[[dict[str, Any]], Awaitable[LocalToolResult]]


class LocalToolExecutor:
    """Execute an already-planned, explicitly trusted local capability.

    This boundary owns no semantic routing.  It accepts an exact capability ID
    and structured arguments produced by the cognitive planner, validates the
    registered capability contract, invokes the bound provider, and returns
    structured evidence only.
    """

    def __init__(
        self,
        registry: CapabilityRegistry,
        *,
        weather_client: OpenMeteoWeatherClient | None = None,
        external_information_client: HttpExternalInformationClient | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.registry = registry
        self.weather_client = weather_client
        self.external_information_client = external_information_client
        self.clock = clock or (lambda: datetime.now().astimezone())
        self._handlers: dict[str, ToolHandler] = {
            "chromie.weather.lookup": self._execute_weather,
            "chromie.clock.local": self._execute_local_clock,
            "chromie.external_information.retrieve": self._execute_external_information,
        }

    async def execute(self, request: ToolExecutionRequest) -> ToolExecutionResponse:
        try:
            tool = self.registry.get_tool(request.tool_id)
        except KeyError:
            return self._result(request, "unavailable", "unknown_tool", "Unknown local tool")

        denial = self._execution_denial(tool)
        if denial is not None:
            return self._result(request, "refused", denial[0], denial[1])

        handler = self._handlers.get(tool.name)
        if handler is None:
            return self._result(
                request,
                "unavailable",
                "provider_not_bound",
                "No trusted local provider is bound for this capability",
            )

        try:
            _validate_json_schema(request.args, tool.input_schema, path="args")
            handler_args = dict(request.args)
            handler_args["__request_language"] = request.language
            handler_result = await asyncio.wait_for(
                handler(handler_args),
                timeout=max(0.001, float(tool.execution.timeout_s or 30.0)),
            )
            _validate_json_schema(
                handler_result.output, tool.output_schema, path="output"
            )
        except asyncio.TimeoutError:
            return self._result(request, "timed_out", "provider_timeout", "Local tool timed out")
        except (ValueError, TypeError) as exc:
            return self._result(request, "refused", "contract_invalid", str(exc))
        except (WeatherLookupError, ExternalInformationError) as exc:
            return self._result(
                request,
                "failed",
                exc.reason_code or "local_tool_failed",
                str(exc),
            )
        except Exception as exc:  # pragma: no cover - final provider boundary
            logger.exception(
                "local_tool_execution_failed request_id=%s tool_id=%s",
                request.request_id,
                request.tool_id,
            )
            return self._result(
                request,
                "failed",
                "provider_error",
                f"{type(exc).__name__}: {exc}",
            )

        return ToolExecutionResponse(
            request_id=request.request_id,
            tool_id=request.tool_id,
            status="completed",
            output=handler_result.output,
            metadata=handler_result.metadata,
        )

    def _execution_denial(self, tool: ToolCapability) -> tuple[str, str] | None:
        manifest = self.registry.get_agent(tool.agent_id)
        if manifest.transport.kind != "local_python":
            return "transport_not_local", "Capability is not a local Python tool"
        if not _truthy(tool.llm_hints.get("interaction_executable")):
            return "not_interaction_executable", "Capability is not approved for interaction execution"
        if tool.safety_class != "safe_read":
            return "unsafe_local_tool", "Only safe read-only local tools are accepted"
        if not tool.execution.side_effect_free:
            return "side_effecting_local_tool", "Local interaction tool must be side-effect free"
        if tool.confirmation.required:
            return "confirmation_required", "Confirmed tools require a dedicated trusted provider"
        if not manifest.status.available or not tool.availability.available:
            reason = tool.availability.reason or manifest.status.reason or "unavailable"
            return "tool_unavailable", reason
        return None

    async def _execute_weather(self, args: dict[str, Any]) -> LocalToolResult:
        if self.weather_client is None:
            raise WeatherLookupError("weather provider is disabled")
        units = str(args.get("units") or "metric")
        language = str(args.pop("__request_language", "en-US") or "en-US")
        report = await self.weather_client.lookup(
            WeatherQuery(
                location=str(args.get("location") or ""),
                date=str(args.get("date") or "today"),
                period=str(args.get("period") or "day"),
                units=units,
                language=language,
                location_context=WeatherLocationContext.from_mapping(
                    args.get("location_context")
                ),
            )
        )
        return LocalToolResult(
            output=_weather_output(report, units=units, language=language),
            metadata={
                "provider_resolution": {
                    "requested_location": report.requested_location,
                    "provider_query": report.provider_query,
                    "matched_location": report.location_name,
                    "matched_admin1": report.provider_admin1,
                    "matched_country": report.country,
                }
            },
        )

    async def _execute_local_clock(self, args: dict[str, Any]) -> LocalToolResult:
        args.pop("__request_language", None)
        if args:
            raise ValueError("local clock accepts no arguments")
        now = self.clock()
        if not isinstance(now, datetime):
            raise TypeError("local clock provider must return datetime")
        if now.tzinfo is None or now.utcoffset() is None:
            now = now.astimezone()
        offset = now.strftime("%z")
        formatted_offset = (
            f"{offset[:3]}:{offset[3:]}" if len(offset) == 5 else offset
        )
        timezone_name = now.tzname() or formatted_offset
        output = {
            "local_iso": now.isoformat(timespec="seconds"),
            "local_date": now.date().isoformat(),
            "local_time": now.strftime("%H:%M:%S"),
            "weekday": now.strftime("%A"),
            "timezone": timezone_name,
            "utc_offset": formatted_offset,
            "precision": "second",
            "source": "host_local_clock",
        }
        return LocalToolResult(
            output=output,
            metadata={
                "provider_resolution": {
                    "provider": "host_local_clock",
                    "timezone": timezone_name,
                    "utc_offset": formatted_offset,
                }
            },
        )

    async def _execute_external_information(
        self,
        args: dict[str, Any],
    ) -> LocalToolResult:
        if self.external_information_client is None:
            raise ExternalInformationError(
                "external-information provider is disabled",
                reason_code="provider_disabled",
            )
        language = str(args.pop("__request_language", "en-US") or "en-US")
        output = await self.external_information_client.retrieve(
            ExternalInformationQuery(
                question=str(args.get("question") or ""),
                request_kind=str(args.get("request_kind") or "general_research"),
                location=str(args.get("location") or ""),
                time_scope=str(args.get("time_scope") or ""),
                freshness=str(args.get("freshness") or "current"),
                max_results=int(args.get("max_results") or 8),
                constraints=(
                    dict(args["constraints"])
                    if isinstance(args.get("constraints"), dict)
                    else None
                ),
                language=language,
            )
        )
        return LocalToolResult(
            output=output,
            metadata={
                "provider_resolution": {
                    "provider": output.get("provider"),
                    "source_count": len(output.get("sources") or []),
                    "retrieved_at": output.get("retrieved_at"),
                }
            },
        )

    @staticmethod
    def _result(
        request: ToolExecutionRequest,
        status: str,
        reason_code: str,
        message: str,
    ) -> ToolExecutionResponse:
        return ToolExecutionResponse(
            request_id=request.request_id,
            tool_id=request.tool_id,
            status=status,
            reason_code=" ".join(str(reason_code or "").split())[:160],
            message=" ".join(str(message or "").split())[:600],
        )


def _weather_output(
    report: WeatherReport,
    *,
    units: str,
    language: str,
) -> dict[str, Any]:
    period = report.forecast_period
    period_output = None
    if period is not None:
        period_output = {
            "scope": period.scope,
            "start_local": period.start_local,
            "end_local": period.end_local,
            "condition": weather_code_text(
                period.weather_code,
                zh=language.lower().startswith("zh"),
            ),
            "weather_code": period.weather_code,
            "temperature_min_c": period.temperature_min_c,
            "temperature_max_c": period.temperature_max_c,
            "apparent_temperature_min_c": period.apparent_temperature_min_c,
            "apparent_temperature_max_c": period.apparent_temperature_max_c,
            "precipitation_probability_max": period.precipitation_probability_max,
        }
    primary_weather_code = (
        period.weather_code if period is not None else report.weather_code
    )
    primary_probability = (
        period.precipitation_probability_max
        if period is not None
        else report.precipitation_probability_max
    )
    primary_high = (
        period.temperature_max_c if period is not None else report.daily_high_c
    )
    primary_low = (
        period.temperature_min_c if period is not None else report.daily_low_c
    )
    return {
        "location": report.location_name,
        "country": report.country,
        "timezone": report.timezone,
        "date": report.date,
        "condition": weather_code_text(
            primary_weather_code,
            zh=language.lower().startswith("zh"),
        ),
        "weather_code": primary_weather_code,
        "current_temperature_c": report.current_temperature_c,
        "apparent_temperature_c": report.apparent_temperature_c,
        "high_c": primary_high,
        "low_c": primary_low,
        "precipitation_probability_max": primary_probability,
        "precipitation_sum_mm": (
            None if period is not None else report.precipitation_sum_mm
        ),
        "wind_speed_kmh": report.wind_speed_kmh,
        "forecast_period": period_output,
        # This is an exceptional user-safe fallback.  The normal answer is
        # composed later by the evidence-bound interpreter from the original
        # question and the complete structured observation below.
        "summary": format_weather_brief(report, language=language, units=units),
        "source": report.source,
    }


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _validate_json_schema(value: Any, schema: dict[str, Any], *, path: str) -> None:
    errors = json_schema_validation_errors(
        value,
        schema,
        path=path,
        validate_array_bounds=False,
    )
    if errors:
        raise ValueError(errors[0])


__all__ = ["LocalToolExecutor"]
