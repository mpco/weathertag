from __future__ import annotations

from .config import RuleConfig
from .models import Reminder, ReminderKind, WeatherSnapshot


_SEVERITY = {"unknown": 0, "minor": 1, "moderate": 2, "severe": 3, "extreme": 4}


def build_reminder(snapshot: WeatherSnapshot, config: RuleConfig) -> Reminder:
    if snapshot.alerts:
        alert = max(snapshot.alerts, key=lambda item: _SEVERITY.get(item.severity, 0))
        return Reminder(ReminderKind.ALERT, f"{alert.title}预警，注意出行安全", True)

    if is_currently_raining(snapshot, config):
        return Reminder(ReminderKind.RAINING, "正在下雨，建议带伞", True)

    rain_in = upcoming_rain_minutes(snapshot, config)
    if rain_in is not None:
        rounded = max(5, int(round(rain_in / 5) * 5))
        return Reminder(ReminderKind.UPCOMING_RAIN, f"约{rounded}分钟后可能有雨，建议带伞", True)

    today = snapshot.daily[0]
    if today.max_temperature >= config.high_temperature_c:
        return Reminder(ReminderKind.EXTREME_TEMPERATURE, "今日高温，注意防晒", True)
    if min(today.min_temperature, snapshot.current.temperature) <= config.cold_temperature_c:
        return Reminder(ReminderKind.EXTREME_TEMPERATURE, "天气寒冷，注意添衣", True)
    if today.max_temperature - today.min_temperature >= config.temperature_gap_c:
        return Reminder(ReminderKind.TEMPERATURE_GAP, "昼夜温差较大，注意增减衣物", False)
    return Reminder(ReminderKind.NORMAL, "天气良好，适宜出行", False)


def is_currently_raining(snapshot: WeatherSnapshot, config: RuleConfig) -> bool:
    current = snapshot.current
    return (
        current.precipitation >= config.rain_threshold_mm
        or icon_category(current.icon) in {"rain", "storm", "snow"}
        or any(word in current.text for word in ("雨", "雪", "冰雹"))
    )


def upcoming_rain_minutes(snapshot: WeatherSnapshot, config: RuleConfig) -> int | None:
    baseline = snapshot.current.observed_at
    for item in snapshot.minutely:
        if item.precipitation >= config.rain_threshold_mm:
            return max(0, round((item.forecast_at - baseline).total_seconds() / 60))

    # Minutely precipitation is limited to China. Hourly data is a conservative
    # fallback for installations where that endpoint returns no points.
    for item in snapshot.hourly:
        minutes = round((item.forecast_at - baseline).total_seconds() / 60)
        if minutes > 120:
            break
        if item.precipitation >= config.rain_threshold_mm or (
            item.precipitation_probability >= config.hourly_rain_probability
            and icon_category(item.icon) in {"rain", "storm", "snow"}
        ):
            return max(0, minutes)
    return None


def has_material_change(
    previous: WeatherSnapshot | None,
    current: WeatherSnapshot,
    config: RuleConfig,
) -> bool:
    if previous is None:
        return True
    if {item.alert_id for item in previous.alerts} != {item.alert_id for item in current.alerts}:
        return True
    if is_currently_raining(previous, config) != is_currently_raining(current, config):
        return True
    if build_reminder(previous, config).kind != build_reminder(current, config).kind:
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
    if code in {101, 102, 103, 151, 152, 153}:
        return "partly_cloudy"
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
