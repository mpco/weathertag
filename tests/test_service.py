from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

from weathertag.config import AppConfig, DEFAULT_FONT_PATH, GotifyConfig, RenderConfig
from weathertag.renderer import WeatherRenderer
from weathertag.service import WeatherTagService
from weathertag.state import StateStore

from .helpers import NOW, snapshot


class FakeWeather:
    def __init__(self, values: list[object]) -> None:
        self.values = values

    async def fetch(self, now=None):
        value = self.values.pop(0)
        if isinstance(value, Exception):
            raise value
        return replace(value, fetched_at=now)


class FakeDisplay:
    def __init__(self) -> None:
        self.images = []

    async def send_image(self, image):
        self.images.append(image.copy())


class FakeNotifier:
    def __init__(self) -> None:
        self.messages = []

    async def send(self, title, message):
        self.messages.append((title, message))
        return True


class ServiceTest(unittest.IsolatedAsyncioTestCase):
    async def test_scheduled_and_material_refreshes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = AppConfig(
                render=RenderConfig(font_path=DEFAULT_FONT_PATH),
                output_path=root / "latest.png",
                state_path=root / "state.json",
            )
            display = FakeDisplay()
            service = WeatherTagService(
                config,
                FakeWeather([snapshot(), snapshot(), snapshot(current_precip=0.2)]),
                WeatherRenderer(config.render),
                display,
                FakeNotifier(),
                StateStore(config.state_path),
            )
            self.assertTrue(await service.run_once(now=NOW))
            self.assertTrue(await service.run_once(now=NOW + timedelta(minutes=10)))
            self.assertTrue(await service.run_once(now=NOW + timedelta(minutes=20)))
            self.assertEqual(len(display.images), 2)
            self.assertTrue(config.output_path.is_file())

    async def test_failure_screen_and_notification_are_rate_limited(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = AppConfig(
                render=RenderConfig(font_path=DEFAULT_FONT_PATH),
                gotify=GotifyConfig(enabled=True, base_url="https://example.test", token="x"),
                output_path=root / "latest.png",
                state_path=root / "state.json",
            )
            display = FakeDisplay()
            notifier = FakeNotifier()
            service = WeatherTagService(
                config,
                FakeWeather([RuntimeError("API down"), RuntimeError("API down")]),
                WeatherRenderer(config.render),
                display,
                notifier,
                StateStore(config.state_path),
            )
            self.assertFalse(await service.run_once(now=NOW))
            self.assertFalse(await service.run_once(now=NOW + timedelta(minutes=10)))
            self.assertEqual(len(display.images), 1)
            self.assertEqual(len(notifier.messages), 1)


if __name__ == "__main__":
    unittest.main()
