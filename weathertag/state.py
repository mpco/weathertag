from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .models import DailyForecast, RuntimeState, WeatherSnapshot


class StateStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> RuntimeState:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return RuntimeState()
        except (OSError, json.JSONDecodeError, TypeError, KeyError, ValueError):
            # Corrupt state must not prevent a fresh weather update.
            return RuntimeState()
        return RuntimeState(
            last_snapshot=WeatherSnapshot.from_dict(raw["last_snapshot"])
            if raw.get("last_snapshot")
            else None,
            yesterday_forecast=_optional_daily(raw.get("yesterday_forecast")),
            last_screen_update=_optional_datetime(raw.get("last_screen_update")),
            last_failure_screen=_optional_datetime(raw.get("last_failure_screen")),
            battery_millivolts=_optional_int(raw.get("battery_millivolts")),
            notification_times={
                key: datetime.fromisoformat(value) for key, value in raw.get("notification_times", {}).items()
            },
        )

    def save(self, state: RuntimeState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data: dict[str, Any] = {
            "last_snapshot": state.last_snapshot.to_dict() if state.last_snapshot else None,
            "yesterday_forecast": {
                **asdict(state.yesterday_forecast),
                "day": state.yesterday_forecast.day.isoformat(),
            } if state.yesterday_forecast else None,
            "last_screen_update": _encode_datetime(state.last_screen_update),
            "last_failure_screen": _encode_datetime(state.last_failure_screen),
            "battery_millivolts": state.battery_millivolts,
            "notification_times": {
                key: value.isoformat() for key, value in state.notification_times.items()
            },
        }
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, self.path)


def _optional_datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _optional_daily(value: object) -> DailyForecast | None:
    if not isinstance(value, dict):
        return None
    try:
        return DailyForecast(**{**value, "day": date.fromisoformat(value["day"])})
    except (KeyError, TypeError, ValueError):
        return None


def _encode_datetime(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
