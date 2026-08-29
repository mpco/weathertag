from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from weathertag.config import DEFAULT_FONT_PATH, RenderConfig, RuleConfig
from weathertag.models import RuntimeState, WeatherSnapshot
from weathertag.renderer import LAYOUT, RED, WeatherRenderer
from weathertag.rules import build_reminder
from weathertag.state import StateStore

from .helpers import snapshot


class ModelsAndRendererTest(unittest.TestCase):
    def test_snapshot_json_round_trip(self) -> None:
        original = snapshot(rain_after=30)
        self.assertEqual(WeatherSnapshot.from_dict(original.to_dict()), original)

    def test_renderer_produces_target_image(self) -> None:
        weather = snapshot(rain_after=30)
        rules = RuleConfig()
        renderer = WeatherRenderer(RenderConfig(font_path=DEFAULT_FONT_PATH))
        image = renderer.render(
            weather,
            build_reminder(weather, rules),
            rules,
            battery_millivolts=2987,
        )
        self.assertEqual(image.size, (400, 300))
        self.assertEqual(image.mode, "RGB")
        self.assertEqual(LAYOUT.text_stroke_width, 0)
        self.assertIn(RED, set(image.get_flattened_data()))
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "screen.png"
            renderer.save(image, target)
            self.assertGreater(target.stat().st_size, 1_000)

    def test_battery_voltage_survives_state_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = StateStore(Path(directory) / "state.json")
            store.save(RuntimeState(battery_millivolts=2987))
            self.assertEqual(store.load().battery_millivolts, 2987)


if __name__ == "__main__":
    unittest.main()
