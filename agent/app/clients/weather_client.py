from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Literal

import httpx

logger = logging.getLogger("chromie.agent.weather")

WeatherDate = Literal["today", "tomorrow"]
WeatherUnits = Literal["metric", "imperial", "auto"]


@dataclass(slots=True)
class WeatherQuery:
    location: str
    date: WeatherDate = "today"
    units: WeatherUnits = "metric"
    language: str = "en-US"


@dataclass(slots=True)
class WeatherReport:
    location_name: str
    country: str | None
    timezone: str | None
    date: str | None
    current_temperature_c: float | None
    apparent_temperature_c: float | None
    daily_high_c: float | None
    daily_low_c: float | None
    precipitation_probability_max: float | None
    precipitation_sum_mm: float | None
    weather_code: int | None
    wind_speed_kmh: float | None
    source: str = "open-meteo"


class WeatherLookupError(RuntimeError):
    """Raised when a weather lookup cannot produce a user-safe report."""


_WEATHER_CODE_EN = {
    0: "clear",
    1: "mostly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "foggy",
    48: "foggy with rime",
    51: "light drizzle",
    53: "moderate drizzle",
    55: "dense drizzle",
    56: "light freezing drizzle",
    57: "dense freezing drizzle",
    61: "light rain",
    63: "moderate rain",
    65: "heavy rain",
    66: "light freezing rain",
    67: "heavy freezing rain",
    71: "light snow",
    73: "moderate snow",
    75: "heavy snow",
    77: "snow grains",
    80: "light showers",
    81: "moderate showers",
    82: "violent showers",
    85: "light snow showers",
    86: "heavy snow showers",
    95: "thunderstorms",
    96: "thunderstorms with hail",
    99: "severe thunderstorms with hail",
}

_WEATHER_CODE_ZH = {
    0: "晴朗",
    1: "大致晴朗",
    2: "局部多云",
    3: "阴天",
    45: "有雾",
    48: "雾凇",
    51: "小毛毛雨",
    53: "中等毛毛雨",
    55: "较强毛毛雨",
    56: "轻微冻毛毛雨",
    57: "较强冻毛毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    66: "轻微冻雨",
    67: "较强冻雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    77: "雪粒",
    80: "小阵雨",
    81: "中等阵雨",
    82: "强阵雨",
    85: "小阵雪",
    86: "强阵雪",
    95: "雷雨",
    96: "雷雨伴冰雹",
    99: "强雷雨伴冰雹",
}


def weather_code_text(code: int | None, *, zh: bool) -> str:
    if code is None:
        return "天气状况未知" if zh else "unknown conditions"
    table = _WEATHER_CODE_ZH if zh else _WEATHER_CODE_EN
    return table.get(code, f"天气代码 {code}" if zh else f"weather code {code}")


def _fmt_number(value: float | None, *, digits: int = 0) -> str | None:
    if value is None:
        return None
    return f"{value:.{digits}f}" if digits > 0 else f"{value:.0f}"


def format_weather_report(report: WeatherReport, *, language: str, units: WeatherUnits = "metric") -> str:
    zh = language.lower().startswith("zh")
    condition = weather_code_text(report.weather_code, zh=zh)
    imperial = units == "imperial"

    def temp(value: float | None) -> float | None:
        if value is None:
            return None
        return value * 9.0 / 5.0 + 32.0 if imperial else value

    def rain_amount(value: float | None) -> float | None:
        if value is None:
            return None
        return value / 25.4 if imperial else value

    def wind_speed(value: float | None) -> float | None:
        if value is None:
            return None
        return value / 1.609344 if imperial else value

    temp_unit = "℉" if imperial else "℃"
    temp_unit_en = "°F" if imperial else "°C"
    rain_unit_zh = "英寸" if imperial else "毫米"
    rain_unit_en = "in" if imperial else "mm"
    wind_unit_zh = "英里每小时" if imperial else "公里每小时"
    wind_unit_en = "mph" if imperial else "km/h"

    current = _fmt_number(temp(report.current_temperature_c))
    high = _fmt_number(temp(report.daily_high_c))
    low = _fmt_number(temp(report.daily_low_c))
    feels = _fmt_number(temp(report.apparent_temperature_c))
    precip = _fmt_number(report.precipitation_probability_max)
    rain = _fmt_number(rain_amount(report.precipitation_sum_mm), digits=1)
    wind = _fmt_number(wind_speed(report.wind_speed_kmh))

    if zh:
        parts = [f"{report.location_name}今天{condition}"]
        if current is not None:
            parts.append(f"当前约 {current}{temp_unit}")
        if high is not None and low is not None:
            parts.append(f"最高 {high}{temp_unit}、最低 {low}{temp_unit}")
        if feels is not None:
            parts.append(f"体感约 {feels}{temp_unit}")
        if precip is not None:
            parts.append(f"降水概率最高约 {precip}%")
        elif rain is not None:
            parts.append(f"预计降水量约 {rain} {rain_unit_zh}")
        if wind is not None:
            parts.append(f"风速约 {wind} {wind_unit_zh}")
        return "，".join(parts) + "。"

    parts = [f"Today in {report.location_name}, conditions are {condition}"]
    if current is not None:
        parts.append(f"it is about {current}{temp_unit_en} now")
    if high is not None and low is not None:
        parts.append(f"with a high of {high}{temp_unit_en} and a low of {low}{temp_unit_en}")
    if feels is not None:
        parts.append(f"feels like {feels}{temp_unit_en}")
    if precip is not None:
        parts.append(f"the peak precipitation chance is about {precip}%")
    elif rain is not None:
        parts.append(f"expected precipitation is about {rain} {rain_unit_en}")
    if wind is not None:
        parts.append(f"wind is around {wind} {wind_unit_en}")
    return ", ".join(parts) + "."


class OpenMeteoWeatherClient:
    """Small no-key weather provider for Chromie's read-only weather tool.

    The client intentionally returns structured reports rather than prose. The
    ToolAgent decides how to speak the result while the provider remains a
    read-only data boundary.
    """

    def __init__(
        self,
        *,
        geocoding_url: str | None = None,
        forecast_url: str | None = None,
        timeout_s: float | None = None,
    ) -> None:
        self.geocoding_url = (
            geocoding_url
            or os.getenv("AGENT_WEATHER_GEOCODING_URL")
            or "https://geocoding-api.open-meteo.com/v1/search"
        )
        self.forecast_url = (
            forecast_url
            or os.getenv("AGENT_WEATHER_FORECAST_URL")
            or "https://api.open-meteo.com/v1/forecast"
        )
        self.timeout_s = float(
            timeout_s
            if timeout_s is not None
            else os.getenv("AGENT_WEATHER_TIMEOUT_S", "8")
        )

    async def lookup(self, query: WeatherQuery) -> WeatherReport:
        location = " ".join((query.location or "").strip().split())
        if not location:
            raise WeatherLookupError("weather lookup requires a location")

        async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout_s), trust_env=False) as client:
            logger.info(
                "weather_geocode_start location=%r language=%s url=%s",
                location,
                query.language,
                self.geocoding_url,
            )
            geo_resp = await client.get(
                self.geocoding_url,
                params={
                    "name": location,
                    "count": 1,
                    "language": "zh" if query.language.lower().startswith("zh") else "en",
                    "format": "json",
                },
            )
            geo_resp.raise_for_status()
            geo_data = geo_resp.json()
            result = self._first_geocoding_result(geo_data)
            latitude = result.get("latitude")
            longitude = result.get("longitude")
            if not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
                raise WeatherLookupError(f"could not resolve weather location {location!r}")
            logger.info(
                "weather_geocode_done requested=%r matched=%r country=%r lat=%s lon=%s",
                location,
                result.get("name"),
                result.get("country"),
                latitude,
                longitude,
            )

            logger.info(
                "weather_forecast_start location=%r lat=%s lon=%s url=%s",
                result.get("name") or location,
                latitude,
                longitude,
                self.forecast_url,
            )
            forecast_resp = await client.get(
                self.forecast_url,
                params={
                    "latitude": latitude,
                    "longitude": longitude,
                    "current": ",".join(
                        [
                            "temperature_2m",
                            "apparent_temperature",
                            "precipitation",
                            "weather_code",
                            "wind_speed_10m",
                        ]
                    ),
                    "daily": ",".join(
                        [
                            "weather_code",
                            "temperature_2m_max",
                            "temperature_2m_min",
                            "precipitation_sum",
                            "precipitation_probability_max",
                        ]
                    ),
                    "timezone": "auto",
                    "forecast_days": 2,
                },
            )
            forecast_resp.raise_for_status()
            forecast_data = forecast_resp.json()
            logger.info(
                "weather_forecast_done location=%r timezone=%r daily_keys=%s current_keys=%s",
                result.get("name") or location,
                forecast_data.get("timezone") if isinstance(forecast_data, dict) else None,
                sorted((forecast_data.get("daily") or {}).keys())[:12]
                if isinstance(forecast_data, dict) and isinstance(forecast_data.get("daily"), dict)
                else [],
                sorted((forecast_data.get("current") or {}).keys())[:12]
                if isinstance(forecast_data, dict) and isinstance(forecast_data.get("current"), dict)
                else [],
            )

        day_index = 1 if query.date == "tomorrow" else 0
        report = self._report_from_payload(
            location_name=str(result.get("name") or location),
            country=result.get("country"),
            forecast=forecast_data,
            day_index=day_index,
        )
        logger.info(
            "weather_report_built location=%r date=%r temp_c=%s high_c=%s low_c=%s code=%s",
            report.location_name,
            report.date,
            report.current_temperature_c,
            report.daily_high_c,
            report.daily_low_c,
            report.weather_code,
        )
        return report

    def _first_geocoding_result(self, data: Any) -> dict[str, Any]:
        results = data.get("results") if isinstance(data, dict) else None
        if not isinstance(results, list) or not results:
            raise WeatherLookupError("weather location was not found")
        first = results[0]
        if not isinstance(first, dict):
            raise WeatherLookupError("weather location response was malformed")
        return first

    def _report_from_payload(
        self,
        *,
        location_name: str,
        country: Any,
        forecast: dict[str, Any],
        day_index: int,
    ) -> WeatherReport:
        current = forecast.get("current") if isinstance(forecast, dict) else {}
        daily = forecast.get("daily") if isinstance(forecast, dict) else {}
        if not isinstance(current, dict):
            current = {}
        if not isinstance(daily, dict):
            daily = {}

        def daily_value(key: str) -> Any:
            values = daily.get(key)
            if isinstance(values, list) and len(values) > day_index:
                return values[day_index]
            return None

        weather_code = daily_value("weather_code")
        if not isinstance(weather_code, int):
            raw_current_code = current.get("weather_code")
            weather_code = raw_current_code if isinstance(raw_current_code, int) else None

        return WeatherReport(
            location_name=location_name,
            country=str(country) if country else None,
            timezone=str(forecast.get("timezone")) if forecast.get("timezone") else None,
            date=str(daily_value("time")) if daily_value("time") else None,
            current_temperature_c=self._number(current.get("temperature_2m")),
            apparent_temperature_c=self._number(current.get("apparent_temperature")),
            daily_high_c=self._number(daily_value("temperature_2m_max")),
            daily_low_c=self._number(daily_value("temperature_2m_min")),
            precipitation_probability_max=self._number(daily_value("precipitation_probability_max")),
            precipitation_sum_mm=self._number(daily_value("precipitation_sum")),
            weather_code=weather_code,
            wind_speed_kmh=self._number(current.get("wind_speed_10m")),
        )

    @staticmethod
    def _number(value: Any) -> float | None:
        if isinstance(value, (int, float)):
            return float(value)
        return None
