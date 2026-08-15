from __future__ import annotations

import unittest
from urllib.parse import parse_qs

import httpx

from agent.app.clients.weather_client import (
    OpenMeteoWeatherClient,
    WeatherLocationContext,
    WeatherLookupError,
    WeatherQuery,
)


class WeatherLocationResolutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_tonight_query_returns_hourly_period_evidence(self) -> None:
        forecast_requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/search"):
                return httpx.Response(
                    200,
                    json={
                        "results": [
                            {
                                "name": "Chongqing",
                                "country": "China",
                                "latitude": 29.56,
                                "longitude": 106.55,
                            }
                        ]
                    },
                )
            forecast_requests.append(request)
            return httpx.Response(
                200,
                json={
                    "timezone": "Asia/Shanghai",
                    "current": {
                        "time": "2026-08-13T17:00",
                        "temperature_2m": 33.0,
                        "apparent_temperature": 37.0,
                        "weather_code": 2,
                    },
                    "daily": {
                        "time": ["2026-08-13", "2026-08-14"],
                        "weather_code": [2, 3],
                        "temperature_2m_max": [35.0, 34.0],
                        "temperature_2m_min": [27.0, 26.0],
                        "precipitation_sum": [1.0, 2.0],
                        "precipitation_probability_max": [60.0, 70.0],
                    },
                    "hourly": {
                        "time": [
                            "2026-08-13T17:00",
                            "2026-08-13T18:00",
                            "2026-08-13T20:00",
                            "2026-08-13T23:00",
                            "2026-08-14T18:00",
                        ],
                        "temperature_2m": [33.0, 32.0, 30.0, 28.0, 29.0],
                        "apparent_temperature": [37.0, 36.0, 33.0, 30.0, 32.0],
                        "precipitation_probability": [20.0, 40.0, 70.0, 30.0, 50.0],
                        "weather_code": [2, 2, 61, 3, 3],
                    },
                },
            )

        client = OpenMeteoWeatherClient(
            geocoding_url="https://example.test/v1/search",
            forecast_url="https://example.test/v1/forecast",
            transport=httpx.MockTransport(handler),
        )

        report = await client.lookup(
            WeatherQuery(location="Chongqing", period="tonight")
        )

        params = parse_qs(forecast_requests[0].url.query.decode())
        self.assertIn("hourly", params)
        self.assertIsNotNone(report.forecast_period)
        period = report.forecast_period
        assert period is not None
        self.assertEqual(period.scope, "tonight")
        self.assertEqual(period.start_local, "2026-08-13T18:00")
        self.assertEqual(period.end_local, "2026-08-13T23:00")
        self.assertEqual(period.temperature_min_c, 28.0)
        self.assertEqual(period.temperature_max_c, 32.0)
        self.assertEqual(period.apparent_temperature_max_c, 36.0)
        self.assertEqual(period.precipitation_probability_max, 70.0)
        self.assertEqual(period.weather_code, 61)

    async def test_afternoon_query_returns_exact_hourly_period_evidence(self) -> None:
        forecast_requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/search"):
                return httpx.Response(
                    200,
                    json={
                        "results": [
                            {
                                "name": "Chongqing",
                                "country": "China",
                                "latitude": 29.56,
                                "longitude": 106.55,
                            }
                        ]
                    },
                )
            forecast_requests.append(request)
            return httpx.Response(
                200,
                json={
                    "timezone": "Asia/Shanghai",
                    "current": {
                        "time": "2026-08-15T10:00",
                        "temperature_2m": 31.0,
                        "apparent_temperature": 34.0,
                        "weather_code": 2,
                    },
                    "daily": {
                        "time": ["2026-08-15", "2026-08-16"],
                        "weather_code": [2, 3],
                        "temperature_2m_max": [36.0, 35.0],
                        "temperature_2m_min": [27.0, 26.0],
                        "precipitation_sum": [2.0, 1.0],
                        "precipitation_probability_max": [70.0, 40.0],
                    },
                    "hourly": {
                        "time": [
                            "2026-08-15T11:00",
                            "2026-08-15T12:00",
                            "2026-08-15T15:00",
                            "2026-08-15T17:00",
                            "2026-08-15T18:00",
                        ],
                        "temperature_2m": [32.0, 33.0, 35.0, 34.0, 32.0],
                        "apparent_temperature": [35.0, 36.0, 39.0, 37.0, 35.0],
                        "precipitation_probability": [10.0, 20.0, 65.0, 40.0, 30.0],
                        "weather_code": [2, 2, 61, 3, 3],
                    },
                },
            )

        client = OpenMeteoWeatherClient(
            geocoding_url="https://example.test/v1/search",
            forecast_url="https://example.test/v1/forecast",
            transport=httpx.MockTransport(handler),
        )
        report = await client.lookup(
            WeatherQuery(location="Chongqing", period="afternoon")
        )

        params = parse_qs(forecast_requests[0].url.query.decode())
        self.assertIn("hourly", params)
        period = report.forecast_period
        self.assertIsNotNone(period)
        assert period is not None
        self.assertEqual(period.scope, "afternoon")
        self.assertEqual(period.start_local, "2026-08-15T12:00")
        self.assertEqual(period.end_local, "2026-08-15T17:00")
        self.assertEqual(period.temperature_min_c, 33.0)
        self.assertEqual(period.temperature_max_c, 35.0)
        self.assertEqual(period.apparent_temperature_max_c, 39.0)
        self.assertEqual(period.precipitation_probability_max, 65.0)
        self.assertEqual(period.weather_code, 61)

    async def test_hierarchical_chinese_location_retries_locality_and_qualifies_admin1(self) -> None:
        geocode_queries: list[str] = []
        forecast_requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/search"):
                query = parse_qs(request.url.query.decode())["name"][0]
                geocode_queries.append(query)
                if query == "河南省内乡县":
                    return httpx.Response(200, json={"results": []})
                if query == "内乡县":
                    return httpx.Response(
                        200,
                        json={
                            "results": [
                                {
                                    "name": "内乡县",
                                    "admin1": "河北省",
                                    "country": "中国",
                                    "latitude": 37.0,
                                    "longitude": 114.0,
                                },
                                {
                                    "name": "内乡县",
                                    "admin1": "河南省",
                                    "country": "中国",
                                    "latitude": 33.046,
                                    "longitude": 111.849,
                                },
                            ]
                        },
                    )
                return httpx.Response(200, json={"results": []})
            if request.url.path.endswith("/forecast"):
                forecast_requests.append(request)
                return httpx.Response(
                    200,
                    json={
                        "timezone": "Asia/Shanghai",
                        "current": {
                            "temperature_2m": 30.1,
                            "apparent_temperature": 34.2,
                            "precipitation": 0.0,
                            "weather_code": 3,
                            "wind_speed_10m": 7.0,
                        },
                        "daily": {
                            "time": ["2026-07-29", "2026-07-30"],
                            "weather_code": [3, 61],
                            "temperature_2m_max": [31.0, 29.0],
                            "temperature_2m_min": [24.0, 23.0],
                            "precipitation_sum": [0.0, 2.4],
                            "precipitation_probability_max": [20.0, 70.0],
                        },
                    },
                )
            raise AssertionError(f"unexpected request: {request.url}")

        client = OpenMeteoWeatherClient(
            geocoding_url="https://example.test/v1/search",
            forecast_url="https://example.test/v1/forecast",
            transport=httpx.MockTransport(handler),
        )

        report = await client.lookup(
            WeatherQuery(
                location="河南省内乡县",
                date="today",
                language="zh-CN",
            )
        )

        self.assertEqual(geocode_queries[:2], ["河南省内乡县", "内乡县"])
        self.assertEqual(len(forecast_requests), 1)
        forecast_params = parse_qs(forecast_requests[0].url.query.decode())
        self.assertEqual(forecast_params["latitude"], ["33.046"])
        self.assertEqual(forecast_params["longitude"], ["111.849"])
        self.assertEqual(report.location_name, "内乡县")
        self.assertEqual(report.country, "中国")
        self.assertEqual(report.current_temperature_c, 30.1)

    async def test_explicit_location_context_is_used_without_changing_canonical_location(self) -> None:
        geocode_queries: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/search"):
                query = parse_qs(request.url.query.decode())["name"][0]
                geocode_queries.append(query)
                if query == "Neixiang County, Henan Province":
                    return httpx.Response(200, json={"results": []})
                if query == "Neixiang":
                    return httpx.Response(
                        200,
                        json={
                            "results": [
                                {
                                    "name": "Neixiang",
                                    "admin1": "Henan",
                                    "country": "China",
                                    "latitude": 33.046,
                                    "longitude": 111.849,
                                }
                            ]
                        },
                    )
                return httpx.Response(200, json={"results": []})
            return httpx.Response(
                200,
                json={
                    "timezone": "Asia/Shanghai",
                    "current": {},
                    "daily": {
                        "time": ["2026-07-29", "2026-07-30"],
                        "weather_code": [3, 3],
                        "temperature_2m_max": [31.0, 31.0],
                        "temperature_2m_min": [24.0, 24.0],
                        "precipitation_sum": [0.0, 0.0],
                        "precipitation_probability_max": [20.0, 20.0],
                    },
                },
            )

        client = OpenMeteoWeatherClient(
            geocoding_url="https://example.test/v1/search",
            forecast_url="https://example.test/v1/forecast",
            transport=httpx.MockTransport(handler),
        )
        query = WeatherQuery(
            location="Neixiang County, Henan Province",
            language="en-US",
            location_context=WeatherLocationContext(
                locality="Neixiang",
                admin1="Henan",
                country="China",
            ),
        )

        report = await client.lookup(query)

        self.assertEqual(
            geocode_queries[:2],
            ["Neixiang County, Henan Province", "Neixiang"],
        )
        self.assertEqual(query.location, "Neixiang County, Henan Province")
        self.assertEqual(report.location_name, "Neixiang")

    async def test_fallback_rejects_same_named_locality_from_wrong_admin1(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/search"):
                query = parse_qs(request.url.query.decode())["name"][0]
                if query == "河南省内乡县":
                    return httpx.Response(200, json={"results": []})
                return httpx.Response(
                    200,
                    json={
                        "results": [
                            {
                                "name": "内乡县",
                                "admin1": "河北省",
                                "country": "中国",
                                "latitude": 37.0,
                                "longitude": 114.0,
                            }
                        ]
                    },
                )
            raise AssertionError("forecast must not run for a mismatched province")

        client = OpenMeteoWeatherClient(
            geocoding_url="https://example.test/v1/search",
            forecast_url="https://example.test/v1/forecast",
            transport=httpx.MockTransport(handler),
        )

        with self.assertRaises(WeatherLookupError) as captured:
            await client.lookup(
                WeatherQuery(location="河南省内乡县", language="zh-CN")
            )

        self.assertEqual(captured.exception.reason_code, "location_not_found")


    async def test_chinese_location_can_resolve_through_latin_provider_index(self) -> None:
        geocode_queries: list[tuple[str, str]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/search"):
                params = parse_qs(request.url.query.decode())
                query = params["name"][0]
                language = params["language"][0]
                geocode_queries.append((query, language))
                if query == "neixiang":
                    return httpx.Response(
                        200,
                        json={
                            "results": [
                                {
                                    "name": "Neixiang",
                                    "admin1": "Henan",
                                    "country": "China",
                                    "latitude": 33.046,
                                    "longitude": 111.849,
                                }
                            ]
                        },
                    )
                return httpx.Response(200, json={"results": []})
            return httpx.Response(
                200,
                json={
                    "timezone": "Asia/Shanghai",
                    "current": {"temperature_2m": 28.0},
                    "daily": {
                        "time": ["2026-07-30", "2026-07-31"],
                        "weather_code": [3, 3],
                        "temperature_2m_max": [30.0, 30.0],
                        "temperature_2m_min": [22.0, 22.0],
                        "precipitation_sum": [0.0, 0.0],
                        "precipitation_probability_max": [10.0, 10.0],
                    },
                },
            )

        client = OpenMeteoWeatherClient(
            geocoding_url="https://example.test/v1/search",
            forecast_url="https://example.test/v1/forecast",
            transport=httpx.MockTransport(handler),
        )
        report = await client.lookup(
            WeatherQuery(location="河南省内乡县", language="zh-CN")
        )

        self.assertIn(("neixiang", "en"), geocode_queries)
        self.assertNotIn(("Neixiang", "en"), geocode_queries)
        self.assertEqual(report.location_name, "Neixiang")
        self.assertEqual(report.current_temperature_c, 28.0)
        self.assertEqual(report.requested_location, "河南省内乡县")
        self.assertEqual(report.provider_query, "neixiang")
        self.assertEqual(report.provider_admin1, "Henan")

    async def test_location_not_found_is_typed_after_all_equivalent_queries_fail(self) -> None:
        queries: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            queries.append(parse_qs(request.url.query.decode())["name"][0])
            return httpx.Response(200, json={"results": []})

        client = OpenMeteoWeatherClient(
            geocoding_url="https://example.test/v1/search",
            forecast_url="https://example.test/v1/forecast",
            transport=httpx.MockTransport(handler),
        )

        with self.assertRaises(WeatherLookupError) as captured:
            await client.lookup(
                WeatherQuery(location="河南省内乡县", language="zh-CN")
            )

        self.assertEqual(captured.exception.reason_code, "location_not_found")
        self.assertEqual(
            captured.exception.attempted_queries,
            (
                "河南省内乡县",
                "内乡县",
                "内乡",
                "neixiang",
                "Neixiang County",
                "Neixiang, Henan",
                "Neixiang County, Henan",
            ),
        )
        self.assertEqual(queries, list(captured.exception.attempted_queries))


if __name__ == "__main__":
    unittest.main()
