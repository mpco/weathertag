from __future__ import annotations

import unittest

from weathertag.config import RuleConfig
from dataclasses import replace
from datetime import timedelta

from weathertag.models import ReminderKind, WeatherAlert
from weathertag.rules import (
    build_reminder,
    build_reminders,
    format_rain_period,
    has_material_change,
    icon_category,
    upcoming_rain_period,
    temperature_change_text,
)

from .helpers import NOW, snapshot


class ReminderRulesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.rules = RuleConfig()

    def test_priority_order(self) -> None:
        warning = WeatherAlert("1", "暴雨", "extreme", "alert", NOW)
        result = build_reminder(
            snapshot(alerts=(warning,), current_precip=1, maximum=38),
            self.rules,
        )
        self.assertEqual(result.kind, ReminderKind.ALERT)
        self.assertIn("暴雨预警", result.text)

        self.assertEqual(
            build_reminder(snapshot(current_precip=0.2, maximum=38), self.rules).kind,
            ReminderKind.RAINING,
        )
        self.assertEqual(
            build_reminder(snapshot(rain_after=30, maximum=38), self.rules).kind,
            ReminderKind.UPCOMING_RAIN,
        )
        self.assertEqual(
            build_reminder(snapshot(rain_after=30), self.rules).text,
            "09:00 〜 10:30 有雨，建议带伞",
        )
        self.assertEqual(
            build_reminder(snapshot(maximum=38), self.rules).kind,
            ReminderKind.EXTREME_TEMPERATURE,
        )
        self.assertEqual(
            build_reminder(snapshot(minimum=18, maximum=30), self.rules).kind,
            ReminderKind.TEMPERATURE_GAP,
        )
        self.assertEqual(
            build_reminder(snapshot(minimum=24, maximum=32), self.rules).kind,
            ReminderKind.NORMAL,
        )

    def test_material_changes(self) -> None:
        before = snapshot()
        self.assertFalse(has_material_change(before, snapshot(), self.rules))
        self.assertTrue(has_material_change(before, snapshot(temperature=30), self.rules))
        self.assertTrue(has_material_change(before, snapshot(current_precip=0.1), self.rules))
        alert = WeatherAlert("new", "高温", "severe", "alert", NOW)
        self.assertTrue(has_material_change(before, snapshot(alerts=(alert,)), self.rules))

    def test_both_day_transitions_and_uv_can_coexist(self) -> None:
        base = snapshot()
        yesterday = replace(base.daily[0], day=base.daily[0].day - timedelta(days=1),
                            max_temperature=38, min_temperature=30)
        tomorrow = replace(base.daily[1], max_temperature=39, min_temperature=18)
        weather = replace(base, daily=(replace(base.daily[0], uv_index=7), tomorrow, base.daily[2]))

        self.assertEqual(temperature_change_text(weather, self.rules, yesterday), (
            "今比昨 高↓6° 低↓6°", "明比今 高↑7° 低↓6°",
        ))
        kinds = {item.kind for item in build_reminders(weather, self.rules, yesterday)}
        self.assertIn(ReminderKind.TEMPERATURE_CHANGE, kinds)
        self.assertIn(ReminderKind.UV, kinds)
        self.assertTrue(has_material_change(base, weather, self.rules, yesterday))

    def test_temperature_change_threshold_and_missing_yesterday(self) -> None:
        base = snapshot()
        yesterday = replace(base.daily[0], day=base.daily[0].day - timedelta(days=1),
                            max_temperature=36, min_temperature=28)
        self.assertEqual(temperature_change_text(base, self.rules, yesterday), ())
        self.assertEqual(temperature_change_text(base, self.rules), ())

    def test_night_icons_keep_their_night_category(self) -> None:
        self.assertEqual(icon_category("150"), "clear_night")
        self.assertEqual(icon_category("151"), "partly_cloudy_night")
        self.assertNotEqual(icon_category("151"), icon_category("101"))

    def test_upcoming_rain_period_ends_at_first_dry_forecast(self) -> None:
        weather = snapshot(rain_after=30)
        minutes = tuple(
            item if index < 10 else type(item)(item.forecast_at, 0, item.kind)
            for index, item in enumerate(weather.minutely)
        )
        weather = type(weather)(
            weather.fetched_at,
            weather.api_updated_at,
            weather.current,
            weather.daily,
            weather.hourly,
            minutes,
            weather.minutely_summary,
            weather.alerts,
        )

        period = upcoming_rain_period(weather, self.rules)

        self.assertIsNotNone(period)
        self.assertEqual(format_rain_period(period), "09:00 〜 09:20 有雨")


if __name__ == "__main__":
    unittest.main()
