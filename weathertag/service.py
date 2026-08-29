from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Protocol

from .config import AppConfig
from .epd import Display
from .models import RuntimeState, WeatherSnapshot
from .notifier import Notifier
from .renderer import WeatherRenderer
from .rules import build_reminder, has_material_change
from .state import StateStore

LOGGER = logging.getLogger(__name__)


class WeatherSource(Protocol):
    async def fetch(self, now: datetime | None = None) -> WeatherSnapshot: ...


class WeatherTagService:
    def __init__(
        self,
        config: AppConfig,
        weather: WeatherSource,
        renderer: WeatherRenderer,
        display: Display,
        notifier: Notifier,
        state_store: StateStore,
    ) -> None:
        self.config = config
        self.weather = weather
        self.renderer = renderer
        self.display = display
        self.notifier = notifier
        self.state_store = state_store
        self.state = state_store.load()

    async def run_once(self, *, now: datetime | None = None, force: bool = False) -> bool:
        now = now or datetime.now().astimezone()
        previous = self.state.last_snapshot
        try:
            snapshot = await self.weather.fetch(now)
        except Exception as exc:
            await self._weather_failure(now, exc)
            return False

        self.state.last_snapshot = snapshot
        restored_from_failure = self.state.last_failure_screen is not None
        self.state.last_failure_screen = None
        material = has_material_change(previous, snapshot, self.config.rules)
        scheduled = self._scheduled_refresh_due(now)
        should_refresh = force or restored_from_failure or material or scheduled

        reminder = build_reminder(snapshot, self.config.rules)
        image = self.renderer.render(
            snapshot,
            reminder,
            self.config.rules,
            rendered_at=now,
            battery_millivolts=self.state.battery_millivolts,
        )
        self.renderer.save(image, self.config.output_path)
        LOGGER.info(
            "天气更新成功: %s %d℃，提醒=%s，刷屏=%s",
            snapshot.current.text,
            snapshot.current.temperature,
            reminder.kind,
            should_refresh,
        )
        if should_refresh:
            try:
                battery_millivolts = await self.display.send_image(image)
                self._remember_battery(battery_millivolts)
            except Exception as exc:
                await self._display_failure(now, exc)
                self.state_store.save(self.state)
                return False
            self.state.last_screen_update = now
        self.state_store.save(self.state)
        return True

    async def serve(self, stop_event: asyncio.Event) -> None:
        while not stop_event.is_set():
            started = asyncio.get_running_loop().time()
            await self.run_once()
            elapsed = asyncio.get_running_loop().time() - started
            wait_seconds = max(1, self.config.schedule.poll_minutes * 60 - elapsed)
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=wait_seconds)
            except TimeoutError:
                pass

    def _scheduled_refresh_due(self, now: datetime) -> bool:
        if self.state.last_screen_update is None:
            return True
        interval = timedelta(minutes=self.config.schedule.display_interval_minutes(now.hour))
        return now - self.state.last_screen_update >= interval

    async def _weather_failure(self, now: datetime, error: Exception) -> None:
        LOGGER.exception("天气数据获取失败", exc_info=error)
        await self._notify_limited("weather_api", now, "WeatherTag 天气更新失败", str(error))
        last_success = self.state.last_snapshot.fetched_at if self.state.last_snapshot else None
        image = self.renderer.render_failure(last_success, rendered_at=now)
        self.renderer.save(image, self.config.output_path)

        failure_refresh_due = self.state.last_failure_screen is None or (
            now - self.state.last_failure_screen >= timedelta(minutes=60)
        )
        if failure_refresh_due:
            try:
                battery_millivolts = await self.display.send_image(image)
                self._remember_battery(battery_millivolts)
                self.state.last_failure_screen = now
                self.state.last_screen_update = now
            except Exception as display_error:
                await self._display_failure(now, display_error)
        self.state_store.save(self.state)

    def _remember_battery(self, millivolts: int | None) -> None:
        if millivolts is None:
            return
        self.state.battery_millivolts = millivolts
        LOGGER.info("读取价签电池电压: %.2fV（下次刷屏显示）", millivolts / 1000)

    async def _display_failure(self, now: datetime, error: Exception) -> None:
        LOGGER.exception("电子价签更新失败", exc_info=error)
        await self._notify_limited("ble", now, "WeatherTag 电子价签更新失败", str(error))

    async def _notify_limited(self, key: str, now: datetime, title: str, message: str) -> None:
        previous = self.state.notification_times.get(key)
        cooldown = timedelta(minutes=self.config.gotify.cooldown_minutes)
        if previous is not None and now - previous < cooldown:
            return
        if await self.notifier.send(title, message):
            self.state.notification_times[key] = now
