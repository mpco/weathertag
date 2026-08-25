from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from enum import StrEnum
from typing import Any


class ReminderKind(StrEnum):
    NORMAL = "normal"
    TEMPERATURE_GAP = "temperature_gap"
    EXTREME_TEMPERATURE = "extreme_temperature"
    UPCOMING_RAIN = "upcoming_rain"
    RAINING = "raining"
    ALERT = "alert"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class CurrentWeather:
    observed_at: datetime
    temperature: int
    feels_like: int
    icon: str
    text: str
    wind_direction: str
    wind_scale: str
    humidity: int
    precipitation: float = 0.0


@dataclass(frozen=True, slots=True)
class DailyForecast:
    day: date
    min_temperature: int
    max_temperature: int
    icon_day: str
    text_day: str
    wind_direction: str
    wind_scale: str
    humidity: int


@dataclass(frozen=True, slots=True)
class HourlyForecast:
    forecast_at: datetime
    temperature: int
    icon: str
    text: str
    precipitation_probability: int
    precipitation: float


@dataclass(frozen=True, slots=True)
class MinutePrecipitation:
    forecast_at: datetime
    precipitation: float
    kind: str


@dataclass(frozen=True, slots=True)
class WeatherAlert:
    alert_id: str
    title: str
    severity: str = ""
    status: str = ""
    effective_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class WeatherSnapshot:
    fetched_at: datetime
    api_updated_at: datetime
    current: CurrentWeather
    daily: tuple[DailyForecast, ...]
    hourly: tuple[HourlyForecast, ...] = ()
    minutely: tuple[MinutePrecipitation, ...] = ()
    minutely_summary: str = ""
    alerts: tuple[WeatherAlert, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return _encode(asdict(self))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WeatherSnapshot":
        return cls(
            fetched_at=datetime.fromisoformat(data["fetched_at"]),
            api_updated_at=datetime.fromisoformat(data["api_updated_at"]),
            current=CurrentWeather(
                **{**data["current"], "observed_at": datetime.fromisoformat(data["current"]["observed_at"])}
            ),
            daily=tuple(
                DailyForecast(**{**item, "day": date.fromisoformat(item["day"])}) for item in data["daily"]
            ),
            hourly=tuple(
                HourlyForecast(
                    **{**item, "forecast_at": datetime.fromisoformat(item["forecast_at"])}
                )
                for item in data.get("hourly", [])
            ),
            minutely=tuple(
                MinutePrecipitation(
                    **{**item, "forecast_at": datetime.fromisoformat(item["forecast_at"])}
                )
                for item in data.get("minutely", [])
            ),
            minutely_summary=data.get("minutely_summary", ""),
            alerts=tuple(
                WeatherAlert(
                    **{
                        **item,
                        "effective_at": datetime.fromisoformat(item["effective_at"])
                        if item.get("effective_at")
                        else None,
                    }
                )
                for item in data.get("alerts", [])
            ),
        )


@dataclass(frozen=True, slots=True)
class Reminder:
    kind: ReminderKind
    text: str
    use_red: bool


@dataclass(slots=True)
class RuntimeState:
    last_snapshot: WeatherSnapshot | None = None
    last_screen_update: datetime | None = None
    last_failure_screen: datetime | None = None
    notification_times: dict[str, datetime] = field(default_factory=dict)


def _encode(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _encode(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_encode(item) for item in value]
    return value
