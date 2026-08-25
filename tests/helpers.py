from __future__ import annotations

from datetime import datetime, timedelta

from weathertag.models import (
    CurrentWeather,
    DailyForecast,
    HourlyForecast,
    MinutePrecipitation,
    WeatherAlert,
    WeatherSnapshot,
)


NOW = datetime.fromisoformat("2026-08-24T08:30:00+08:00")


def snapshot(
    *,
    current_precip: float = 0,
    rain_after: int | None = None,
    temperature: int = 28,
    minimum: int = 24,
    maximum: int = 32,
    icon: str = "101",
    alerts: tuple[WeatherAlert, ...] = (),
) -> WeatherSnapshot:
    minutes = tuple(
        MinutePrecipitation(
            NOW + timedelta(minutes=index * 5),
            0.1 if rain_after is not None and index * 5 >= rain_after else 0,
            "rain",
        )
        for index in range(24)
    )
    return WeatherSnapshot(
        fetched_at=NOW,
        api_updated_at=NOW,
        current=CurrentWeather(
            NOW,
            temperature,
            temperature + 2,
            icon,
            "多云",
            "东南风",
            "3",
            60,
            current_precip,
        ),
        daily=tuple(
            DailyForecast(
                (NOW + timedelta(days=index)).date(),
                minimum - index,
                maximum - index,
                ("101", "100", "305")[index],
                ("多云", "晴", "小雨")[index],
                "东南风",
                "3",
                60,
            )
            for index in range(3)
        ),
        hourly=(HourlyForecast(NOW + timedelta(hours=1), 28, "101", "多云", 10, 0),),
        minutely=minutes,
        alerts=alerts,
    )
