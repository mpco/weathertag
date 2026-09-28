from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime, timedelta
from typing import TypeVar

from .config import RuleConfig
from .models import DailyForecast, HourlyForecast, MinutePrecipitation, Reminder, ReminderKind, WeatherSnapshot


_SEVERITY = {"unknown": 0, "minor": 1, "moderate": 2, "severe": 3, "extreme": 4}


def build_reminder(snapshot: WeatherSnapshot, config: RuleConfig) -> Reminder:
    return build_reminders(snapshot, config)[0]


def build_reminders(
    snapshot: WeatherSnapshot,
    config: RuleConfig,
    yesterday: DailyForecast | None = None,
) -> tuple[Reminder, ...]:
    reminders: list[Reminder] = []
    if snapshot.alerts:
        alert = max(snapshot.alerts, key=lambda item: _SEVERITY.get(item.severity, 0))
        reminders.append(Reminder(ReminderKind.ALERT, f"{alert.title}预警，注意出行安全", True))

    if is_currently_raining(snapshot, config):
        reminders.append(Reminder(ReminderKind.RAINING, "正在下雨，建议带伞", True))
    else:
        rain_period = upcoming_rain_period(snapshot, config)
        if rain_period is not None:
            reminders.append(Reminder(
                ReminderKind.UPCOMING_RAIN,
                f"{format_rain_period(rain_period)}，建议带伞",
                True,
            ))

    today = snapshot.daily[0]
    if today.max_temperature >= config.high_temperature_c:
        reminders.append(Reminder(ReminderKind.EXTREME_TEMPERATURE, "今日高温，注意防暑", True))
    elif min(today.min_temperature, snapshot.current.temperature) <= config.cold_temperature_c:
        reminders.append(Reminder(ReminderKind.EXTREME_TEMPERATURE, "天气寒冷，注意添衣", True))

    changes = temperature_change_text(snapshot, config, yesterday)
    if changes:
        reminders.append(Reminder(ReminderKind.TEMPERATURE_CHANGE, "，".join(changes), True))

    if today.uv_index is not None and today.uv_index >= config.uv_reminder_index and snapshot.current.observed_at.hour < 18:
        reminders.append(Reminder(ReminderKind.UV, f"紫外线{today.uv_index}，外出注意防晒", True))
    if today.max_temperature - today.min_temperature >= config.temperature_gap_c:
        reminders.append(Reminder(ReminderKind.TEMPERATURE_GAP, "昼夜温差较大，注意增减衣物", False))
    return tuple(reminders) or (Reminder(ReminderKind.NORMAL, "天气良好，适宜出行", False),)


def temperature_change_text(
    snapshot: WeatherSnapshot,
    config: RuleConfig,
    yesterday: DailyForecast | None = None,
) -> tuple[str, ...]:
    today = snapshot.daily[0]
    parts: list[str] = []
    if yesterday is not None and (today.day - yesterday.day).days == 1:
        change = _daily_change("今日", yesterday, today, config)
        if change:
            parts.append(change)
    tomorrow = next((day for day in snapshot.daily if (day.day - today.day).days == 1), None)
    if tomorrow is not None:
        change = _daily_change("明日", today, tomorrow, config)
        if change:
            parts.append(change)
    return tuple(parts)


def _daily_change(label: str, before: DailyForecast, after: DailyForecast, config: RuleConfig) -> str:
    maximum = after.max_temperature - before.max_temperature
    minimum = after.min_temperature - before.min_temperature
    significant = [value for value in (maximum, minimum) if abs(value) >= config.daily_temperature_change_c]
    if not significant:
        return ""
    if all(value > 0 for value in significant):
        return f"{label}大幅升温"
    if all(value < 0 for value in significant):
        return f"{label}大幅降温"
    return f"{label}气温波动大"


def is_currently_raining(snapshot: WeatherSnapshot, config: RuleConfig) -> bool:
    current = snapshot.current
    return (
        current.precipitation >= config.rain_threshold_mm
        or icon_category(current.icon) in {"rain", "storm", "snow"}
        or any(word in current.text for word in ("雨", "雪", "冰雹"))
    )


def upcoming_rain_minutes(snapshot: WeatherSnapshot, config: RuleConfig) -> int | None:
    """返回距下一段降雨开始的分钟数，保留作为兼容接口。"""
    period = upcoming_rain_period(snapshot, config)
    if period is None:
        return None
    return max(
        0,
        round((period[0] - snapshot.current.observed_at).total_seconds() / 60),
    )


def upcoming_rain_period(
    snapshot: WeatherSnapshot,
    config: RuleConfig,
) -> tuple[datetime, datetime] | None:
    """返回下一个连续降雨时段的 [开始, 结束) 时间。"""
    period = _first_matching_period(
        snapshot.minutely,
        lambda item: item.precipitation >= config.rain_threshold_mm,
        default_step=timedelta(minutes=5),
    )
    if period is not None:
        return period

    # Minutely precipitation is limited to China. Hourly data is a conservative
    # fallback for installations where that endpoint returns no points.
    cutoff = snapshot.current.observed_at + timedelta(minutes=120)
    hourly = tuple(item for item in snapshot.hourly if item.forecast_at <= cutoff)
    return _first_matching_period(
        hourly,
        lambda item: item.precipitation >= config.rain_threshold_mm
        or (
            item.precipitation_probability >= config.hourly_rain_probability
            and icon_category(item.icon) in {"rain", "storm", "snow"}
        ),
        default_step=timedelta(hours=1),
    )


def format_rain_period(period: tuple[datetime, datetime]) -> str:
    """将降雨时段格式化为在屏幕上不会随查看时间变旧的绝对时间。"""
    start, end = period
    start_text = start.strftime("%H:%M")
    if end.date() == start.date():
        end_text = end.strftime("%H:%M")
    elif end.date() == start.date() + timedelta(days=1):
        end_text = f"次日{end:%H:%M}"
    else:
        end_text = end.strftime("%m月%d日%H:%M")
    return f"{start_text} 〜 {end_text} 有雨"


_Forecast = TypeVar("_Forecast", MinutePrecipitation, HourlyForecast)


def _first_matching_period(
    forecasts: Sequence[_Forecast],
    matches: Callable[[_Forecast], bool],
    *,
    default_step: timedelta,
) -> tuple[datetime, datetime] | None:
    start_index = next((index for index, item in enumerate(forecasts) if matches(item)), None)
    if start_index is None:
        return None

    end_index = start_index + 1
    while end_index < len(forecasts) and matches(forecasts[end_index]):
        end_index += 1

    start = forecasts[start_index].forecast_at
    if end_index < len(forecasts):
        end = forecasts[end_index].forecast_at
    else:
        step = default_step
        if len(forecasts) >= 2:
            inferred = forecasts[-1].forecast_at - forecasts[-2].forecast_at
            if inferred > timedelta(0):
                step = inferred
        end = forecasts[-1].forecast_at + step
    return start, end


def has_material_change(
    previous: WeatherSnapshot | None,
    current: WeatherSnapshot,
    config: RuleConfig,
    yesterday: DailyForecast | None = None,
) -> bool:
    if previous is None:
        return True
    if previous.daily[0].day != current.daily[0].day:
        return True
    if {item.alert_id for item in previous.alerts} != {item.alert_id for item in current.alerts}:
        return True
    if is_currently_raining(previous, config) != is_currently_raining(current, config):
        return True
    if build_reminder(previous, config).kind != build_reminder(current, config).kind:
        return True
    previous_kinds = {item.kind for item in build_reminders(previous, config, yesterday)}
    current_kinds = {item.kind for item in build_reminders(current, config, yesterday)}
    if previous_kinds != current_kinds:
        return True
    if temperature_change_text(previous, config, yesterday) != temperature_change_text(current, config, yesterday):
        return True
    if icon_category(previous.current.icon) != icon_category(current.current.icon):
        return True
    return abs(previous.current.temperature - current.current.temperature) >= config.significant_temperature_change_c


def icon_category(icon: str) -> str:
    try:
        code = int(icon)
    except ValueError:
        return "cloud"
    if code in {100, 150}:
        return "sunny" if code == 100 else "clear_night"
    if code in {101, 102, 103}:
        return "partly_cloudy"
    if code in {151, 152, 153}:
        return "partly_cloudy_night"
    if code in {104, 154}:
        return "cloud"
    if 300 <= code <= 304 or 350 <= code <= 351:
        return "storm"
    if 305 <= code <= 399:
        return "rain"
    if 400 <= code <= 499:
        return "snow"
    if 500 <= code <= 515:
        return "fog"
    if 900 <= code <= 901:
        return "temperature"
    return "cloud"
