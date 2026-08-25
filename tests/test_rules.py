from __future__ import annotations

import unittest

from weathertag.config import RuleConfig
from weathertag.models import ReminderKind, WeatherAlert
from weathertag.rules import build_reminder, has_material_change

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


if __name__ == "__main__":
    unittest.main()
