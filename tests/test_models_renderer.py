from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from weathertag.config import DEFAULT_FONT_PATH, RenderConfig, RuleConfig
from weathertag.models import RuntimeState, WeatherSnapshot
from weathertag.renderer import (
    BLACK,
    LAYOUT,
    RED,
    WHITE,
    WeatherRenderer,
    draw_battery,
    draw_weather_icon,
    precipitation_detail,
)
from weathertag.rules import build_reminder, upcoming_rain_period
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

    def test_precipitation_detail_uses_api_type_and_peak_amount(self) -> None:
        weather = snapshot(rain_after=30)
        rules = RuleConfig()
        period = upcoming_rain_period(weather, rules)
        self.assertIsNotNone(period)
        self.assertEqual(precipitation_detail(weather, period, rules), "雨 · 峰值0.1mm")

    def test_battery_voltage_survives_state_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = StateStore(Path(directory) / "state.json")
            store.save(RuntimeState(battery_millivolts=2987))
            self.assertEqual(store.load().battery_millivolts, 2987)

    def test_battery_icon_is_filled_from_voltage(self) -> None:
        renderer = WeatherRenderer(RenderConfig(font_path=DEFAULT_FONT_PATH))
        image = Image.new("RGB", (400, 30), WHITE)
        draw_battery(ImageDraw.Draw(image), 2987, renderer.font(LAYOUT.battery_voltage_font))
        self.assertEqual(image.getpixel((386, 15)), BLACK)

        unknown = Image.new("RGB", (400, 30), WHITE)
        draw_battery(ImageDraw.Draw(unknown), None, renderer.font(LAYOUT.battery_voltage_font))
        self.assertEqual(unknown.getpixel((386, 15)), WHITE)

    def test_clear_night_icon_has_a_bold_crescent_and_stars(self) -> None:
        image = Image.new("RGB", (100, 100), WHITE)
        draw_weather_icon(ImageDraw.Draw(image), (50, 50), "clear_night", 30)
        self.assertEqual(image.getpixel((37, 50)), BLACK)
        self.assertEqual(image.getpixel((67, 36)), BLACK)


if __name__ == "__main__":
    unittest.main()
