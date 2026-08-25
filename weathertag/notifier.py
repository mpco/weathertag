from __future__ import annotations

import logging

import httpx

from .config import GotifyConfig

LOGGER = logging.getLogger(__name__)


class Notifier:
    def __init__(self, config: GotifyConfig) -> None:
        self.config = config

    async def send(self, title: str, message: str) -> bool:
        if not self.config.enabled:
            LOGGER.warning("通知未发送（Gotify 未启用）: %s — %s", title, message)
            return False
        try:
            async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as client:
                response = await client.post(
                    f"{self.config.base_url}/message",
                    headers={"X-Gotify-Key": self.config.token},
                    json={"title": title, "message": message, "priority": self.config.priority},
                )
                response.raise_for_status()
            return True
        except httpx.HTTPError as exc:
            LOGGER.error("Gotify 通知发送失败: %s", exc)
            return False
