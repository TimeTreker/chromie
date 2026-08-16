from __future__ import annotations

import unittest

from agent.app.capabilities.local import chromie_capability_bundle
from agent.app.capabilities.models import CapabilityRegistry
from agent.app.clients.weather_client import WeatherLookupError, WeatherReport
from agent.app.local_tool_execution import LocalToolExecutor
from orchestrator.runtime.interaction_coordinator import InteractionRuntimeCoordinator
from shared.chromie_contracts.interaction import InteractionResponse, CapabilityRequest
from shared.chromie_contracts.tool_result import ToolExecutionRequest, ToolExecutionResponse


class _WeatherClient:
    def __init__(self) -> None:
        self.queries = []

    async def lookup(self, query):
        self.queries.append(query)
        return WeatherReport(
            location_name="Beijing",
            country="China",
            timezone="Asia/Shanghai",
            date="2026-07-27",
            current_temperature_c=29.0,
            apparent_temperature_c=35.0,
            daily_high_c=33.0,
            daily_low_c=25.0,
            precipitation_probability_max=60.0,
            precipitation_sum_mm=1.2,
            weather_code=51,
            wind_speed_kmh=8.0,
            requested_location="北京",
            provider_query="beijing",
            provider_admin1="Beijing",
        )


class _MissingLocationWeatherClient:
    async def lookup(self, query):
        raise WeatherLookupError(
            f"weather location was not found: {query.location}",
            reason_code="location_not_found",
            attempted_queries=(query.location,),
        )


class LocalToolExecutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_executor_runs_exact_planned_weather_tool_and_returns_evidence(self) -> None:
        client = _WeatherClient()
        executor = LocalToolExecutor(
            CapabilityRegistry.from_bundles([chromie_capability_bundle()]),
            weather_client=client,
        )

        result = await executor.execute(
            ToolExecutionRequest(
                request_id="weather-1",
                tool_id="chromie.weather.lookup",
                args={"location": "北京", "date": "today", "units": "metric"},
                language="zh-CN",
            )
        )

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.output["location"], "Beijing")
        self.assertEqual(result.output["apparent_temperature_c"], 35.0)
        self.assertEqual(result.output["source"], "open-meteo")
        self.assertEqual(
            result.metadata["provider_resolution"],
            {
                "requested_location": "北京",
                "provider_query": "beijing",
                "matched_location": "Beijing",
                "matched_admin1": "Beijing",
                "matched_country": "China",
            },
        )
        self.assertEqual(
            result.output["summary"],
            "Beijing今天小毛毛雨，现在约29℃，体感约35℃。",
        )
        self.assertNotIn("最高", result.output["summary"])
        self.assertNotIn("降水概率", result.output["summary"])
        self.assertEqual(client.queries[0].location, "北京")
        self.assertEqual(client.queries[0].language, "zh-CN")
        self.assertEqual(client.queries[0].period, "day")
        self.assertIsNone(result.output["forecast_period"])

    async def test_executor_preserves_typed_location_not_found_failure(self) -> None:
        executor = LocalToolExecutor(
            CapabilityRegistry.from_bundles([chromie_capability_bundle()]),
            weather_client=_MissingLocationWeatherClient(),
        )

        result = await executor.execute(
            ToolExecutionRequest(
                request_id="weather-neixiang-missing",
                tool_id="chromie.weather.lookup",
                args={
                    "location": "河南省内乡县",
                    "location_context": {
                        "locality": "内乡县",
                        "admin1": "河南省",
                        "country": "中国",
                        "aliases": ["内乡"],
                    },
                    "date": "today",
                },
                language="zh-CN",
            )
        )

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.reason_code, "location_not_found")
        self.assertIn("河南省内乡县", result.message)
        self.assertEqual(result.output, {})

    async def test_executor_fails_closed_on_schema_invalid_arguments(self) -> None:
        executor = LocalToolExecutor(
            CapabilityRegistry.from_bundles([chromie_capability_bundle()]),
            weather_client=_WeatherClient(),
        )

        result = await executor.execute(
            ToolExecutionRequest(
                request_id="weather-invalid",
                tool_id="chromie.weather.lookup",
                args={"date": "today"},
            )
        )

        self.assertEqual(result.status, "refused")
        self.assertEqual(result.reason_code, "contract_invalid")
        self.assertEqual(result.output, {})

    async def test_host_runtime_registers_and_executes_local_tool_provider(self) -> None:
        requests: list[ToolExecutionRequest] = []

        async def handler(request: ToolExecutionRequest, timeout_ms: int) -> ToolExecutionResponse:
            requests.append(request)
            self.assertEqual(timeout_ms, 8000)
            return ToolExecutionResponse(
                request_id=request.request_id,
                tool_id=request.tool_id,
                status="completed",
                output={
                    "location": "Beijing",
                    "country": "China",
                    "timezone": "Asia/Shanghai",
                    "date": "2026-07-27",
                    "condition": "light drizzle",
                    "weather_code": 51,
                    "current_temperature_c": 29.0,
                    "apparent_temperature_c": 35.0,
                    "high_c": 33.0,
                    "low_c": 25.0,
                    "precipitation_probability_max": 60.0,
                    "precipitation_sum_mm": 1.2,
                    "wind_speed_kmh": 8.0,
                    "summary": "Today in Beijing, it is about 29°C now.",
                    "source": "open-meteo",
                },
                metadata={
                    "provider_resolution": {
                        "requested_location": "北京",
                        "provider_query": "beijing",
                    }
                },
            )

        coordinator = InteractionRuntimeCoordinator(
            lambda args: {"spoken": True},
            agent_tool_handler=handler,
        )
        dispatch = await coordinator.submit_response(
            InteractionResponse(
                interaction_id="interaction-weather",
                capabilities=[
                    CapabilityRequest(
                        request_id="weather-host-1",
                        capability_id="chromie.weather.lookup",
                        args={"location": "北京", "date": "today", "units": "metric"},
                        metadata={
                            "language": "zh-CN",
                            "effects": ["read_only", "external_read"],
                            "safety_class": "safe_read",
                            "effectful": False,
                        },
                    )
                ],
            ),
            session_id="sid-weather",
        )
        result = await coordinator.wait_dispatch(dispatch)

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.results[0].status, "completed")
        self.assertEqual(result.results[0].output["apparent_temperature_c"], 35.0)
        self.assertEqual(
            result.results[0].metadata["provider_resolution"]["provider_query"],
            "beijing",
        )
        self.assertEqual(requests[0].tool_id, "chromie.weather.lookup")
        self.assertEqual(requests[0].language, "zh-CN")


if __name__ == "__main__":
    unittest.main()
