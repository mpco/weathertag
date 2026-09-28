from __future__ import annotations

from datetime import datetime, timedelta

from .models import (
    CurrentWeather,
    DailyForecast,
    HourlyForecast,
    MinutePrecipitation,
    WeatherAlert,
    WeatherSnapshot,
)


def demo_snapshot(scenario: str = "normal", now: datetime | None = None) -> WeatherSnapshot:
    now = now or datetime.now().astimezone().replace(second=0, microsecond=0)
    rain = scenario == "rain"
    night = scenario == "night"
    current = CurrentWeather(
        observed_at=now - timedelta(minutes=5),
        temperature=28,
        feels_like=30,
        icon="305" if rain else "150" if night else "101",
        text="小雨" if rain else "晴" if night else "多云",
        wind_direction="东南风",
        wind_scale="3",
        humidity=78 if rain else 60,
        precipitation=0.3 if rain else 0,
    )
    icons = ("101", "100", "305")
    texts = ("多云", "晴", "小雨")
    daily = tuple(
        DailyForecast(
            day=(now + timedelta(days=index)).date(),
            min_temperature=(24, 18, 20)[index] if scenario == "multi" else 24 - index,
            max_temperature=(32, 39, 30)[index] if scenario == "multi" else 32 - index,
            icon_day=icons[index],
            text_day=texts[index],
            wind_direction="东南风",
            wind_scale="3",
            humidity=60 + index * 5,
            uv_index=7 if index == 0 and scenario == "multi" else 3,
        )
        for index in range(3)
    )
    minutely = tuple(
        MinutePrecipitation(
            forecast_at=now + timedelta(minutes=index * 5),
            precipitation=(0.04 + index * 0.015) if (rain or scenario in {"upcoming", "multi"}) and index >= (0 if rain else 6) else 0,
            kind="rain",
        )
        for index in range(24)
    )
    alerts = (
        WeatherAlert("demo-alert", "暴雨红色", "extreme", "alert", now),
    ) if scenario in {"warning", "multi"} else ()
    return WeatherSnapshot(
        fetched_at=now,
        api_updated_at=now,
        current=current,
        daily=daily,
        hourly=tuple(
            HourlyForecast(now + timedelta(hours=index), 28, "101", "多云", 10, 0)
            for index in range(1, 4)
        ),
        minutely=minutely,
        minutely_summary="",
        alerts=alerts,
    )
