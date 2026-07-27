from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from .capabilities.models import CapabilityRegistry, ToolCapability
from .clients.weather_client import (
    OpenMeteoWeatherClient,
    WeatherLookupError,
    WeatherQuery,
    WeatherReport,
    format_weather_report,
    weather_code_text,
)

try:
    from chromie_contracts.tool_result import ToolExecutionRequest, ToolExecutionResponse
except ImportError:  # pragma: no cover - repository development path
    from shared.chromie_contracts.tool_result import ToolExecutionRequest, ToolExecutionResponse

logger = logging.getLogger("chromie.agent.local_tool_execution")

ToolHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


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
    ) -> None:
        self.registry = registry
        self.weather_client = weather_client
        self._handlers: dict[str, ToolHandler] = {
            "chromie.weather.lookup": self._execute_weather,
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
            output = await asyncio.wait_for(
                handler(handler_args),
                timeout=max(0.001, float(tool.execution.timeout_s or 30.0)),
            )
            _validate_json_schema(output, tool.output_schema, path="output")
        except asyncio.TimeoutError:
            return self._result(request, "timed_out", "provider_timeout", "Local tool timed out")
        except (ValueError, TypeError) as exc:
            return self._result(request, "refused", "contract_invalid", str(exc))
        except WeatherLookupError as exc:
            return self._result(request, "failed", "weather_lookup_failed", str(exc))
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
            output=output,
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

    async def _execute_weather(self, args: dict[str, Any]) -> dict[str, Any]:
        if self.weather_client is None:
            raise WeatherLookupError("weather provider is disabled")
        units = str(args.get("units") or "metric")
        language = str(args.pop("__request_language", "en-US") or "en-US")
        report = await self.weather_client.lookup(
            WeatherQuery(
                location=str(args.get("location") or ""),
                date=str(args.get("date") or "today"),
                units=units,
                language=language,
            )
        )
        return _weather_output(report, units=units, language=language)

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
    return {
        "location": report.location_name,
        "country": report.country,
        "timezone": report.timezone,
        "date": report.date,
        "condition": weather_code_text(
            report.weather_code,
            zh=language.lower().startswith("zh"),
        ),
        "weather_code": report.weather_code,
        "current_temperature_c": report.current_temperature_c,
        "apparent_temperature_c": report.apparent_temperature_c,
        "high_c": report.daily_high_c,
        "low_c": report.daily_low_c,
        "precipitation_probability_max": report.precipitation_probability_max,
        "precipitation_sum_mm": report.precipitation_sum_mm,
        "wind_speed_kmh": report.wind_speed_kmh,
        "summary": format_weather_report(report, language=language, units=units),
        "source": report.source,
    }


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _validate_json_schema(value: Any, schema: dict[str, Any], *, path: str) -> None:
    """Validate the bounded JSON-Schema subset used by capability manifests."""

    if not schema:
        return
    schema_type = schema.get("type")
    allowed_types = (
        schema_type
        if isinstance(schema_type, list)
        else [schema_type]
        if schema_type
        else []
    )
    if allowed_types and not any(_matches_type(value, item) for item in allowed_types):
        raise ValueError(f"{path} expected {allowed_types}, got {type(value).__name__}")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{path} must be one of {schema['enum']}")
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            raise ValueError(f"{path} is shorter than {schema['minLength']}")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            raise ValueError(f"{path} is longer than {schema['maxLength']}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            raise ValueError(f"{path} is below minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            raise ValueError(f"{path} exceeds maximum {schema['maximum']}")
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        for required in schema.get("required", []):
            if required not in value:
                raise ValueError(f"{path} is missing required field {required!r}")
        if schema.get("additionalProperties") is False:
            unknown = sorted(set(value) - set(properties))
            if unknown:
                raise ValueError(f"{path} has unknown fields: {unknown}")
        for key, item in value.items():
            child_schema = properties.get(key)
            if isinstance(child_schema, dict):
                _validate_json_schema(item, child_schema, path=f"{path}.{key}")
    if isinstance(value, list):
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                _validate_json_schema(item, item_schema, path=f"{path}[{index}]")


def _matches_type(value: Any, schema_type: str) -> bool:
    if schema_type == "null":
        return value is None
    if schema_type == "object":
        return isinstance(value, dict)
    if schema_type == "array":
        return isinstance(value, list)
    if schema_type == "string":
        return isinstance(value, str)
    if schema_type == "boolean":
        return isinstance(value, bool)
    if schema_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if schema_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return True


__all__ = ["LocalToolExecutor"]
