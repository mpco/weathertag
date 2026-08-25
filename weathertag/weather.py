from __future__ import annotations

import asyncio
import base64
import json
import time
from datetime import datetime
from typing import Any, Callable

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .config import QWeatherConfig
from .models import (
    CurrentWeather,
    DailyForecast,
    HourlyForecast,
    MinutePrecipitation,
    WeatherAlert,
    WeatherSnapshot,
)


class WeatherAPIError(RuntimeError):
    """QWeather request or response failure."""


class JWTProvider:
    def __init__(self, config: QWeatherConfig, clock: Callable[[], float] = time.time) -> None:
        self._config = config
        self._clock = clock
        self._token = ""
        self._expires_at = 0
        self._key: Ed25519PrivateKey | None = None

    def token(self) -> str:
        now = int(self._clock())
        if self._token and now < self._expires_at - 60:
            return self._token
        if self._key is None:
            self._key = self._load_key()
        header = {"alg": "EdDSA", "kid": self._config.credential_id}
        payload = {"sub": self._config.project_id, "iat": now - 30, "exp": now + 1200}
        signing_input = f"{_b64json(header)}.{_b64json(payload)}"
        signature = self._key.sign(signing_input.encode("ascii"))
        self._token = f"{signing_input}.{_b64(signature)}"
        self._expires_at = payload["exp"]
        return self._token

    def _load_key(self) -> Ed25519PrivateKey:
        if self._config.private_key_pem:
            pem = self._config.private_key_pem.encode()
        elif self._config.private_key_path:
            try:
                pem = self._config.private_key_path.read_bytes()
            except OSError as exc:
                raise WeatherAPIError(f"无法读取和风天气私钥: {exc}") from exc
        else:
            raise WeatherAPIError("未配置和风天气 JWT 私钥")
        try:
            key = serialization.load_pem_private_key(pem, password=None)
        except (TypeError, ValueError) as exc:
            raise WeatherAPIError("和风天气私钥不是有效的 PEM Ed25519 私钥") from exc
        if not isinstance(key, Ed25519PrivateKey):
            raise WeatherAPIError("和风天气 JWT 私钥必须使用 Ed25519 算法")
        return key


class QWeatherClient:
    def __init__(
        self,
        config: QWeatherConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        sleeper: Callable[[float], Any] = asyncio.sleep,
    ) -> None:
        self.config = config
        self._jwt = JWTProvider(config)
        self._sleeper = sleeper
        self._client = httpx.AsyncClient(
            base_url=f"https://{config.api_host}",
            timeout=config.timeout_seconds,
            transport=transport,
            headers={"Accept-Encoding": "gzip", "User-Agent": "WeatherTag/0.1"},
        )

    async def __aenter__(self) -> "QWeatherClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def fetch(self, now: datetime | None = None) -> WeatherSnapshot:
        location = f"{self.config.longitude:.2f},{self.config.latitude:.2f}"
        common = {"location": location, "lang": self.config.language}
        current_raw, daily_raw, hourly_raw, minutely_raw, alerts_raw = await asyncio.gather(
            self._request("/v7/weather/now", params=common),
            self._request("/v7/weather/3d", params=common),
            self._request("/v7/weather/24h", params=common),
            self._request("/v7/minutely/5m", params=common),
            self._request(
                f"/weatheralert/v1/current/{self.config.latitude:.2f}/{self.config.longitude:.2f}",
                params={"localTime": "true", "lang": self.config.language},
                v7=False,
            ),
        )
        return parse_snapshot(
            current_raw,
            daily_raw,
            hourly_raw,
            minutely_raw,
            alerts_raw,
            fetched_at=now or datetime.now().astimezone(),
        )

    async def _request(
        self,
        path: str,
        *,
        params: dict[str, str],
        v7: bool = True,
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(1, self.config.retry_attempts + 1):
            try:
                response = await self._client.get(
                    path,
                    params=params,
                    headers={"Authorization": f"Bearer {self._jwt.token()}"},
                )
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise WeatherAPIError(f"{path} 返回内容不是 JSON 对象")
                if v7 and payload.get("code") != "200":
                    raise WeatherAPIError(f"{path} 返回和风天气错误码 {payload.get('code', '未知')}")
                return payload
            except (httpx.HTTPError, json.JSONDecodeError, WeatherAPIError) as exc:
                last_error = exc
                if attempt < self.config.retry_attempts:
                    await self._sleeper(min(2 ** (attempt - 1), 4))
        raise WeatherAPIError(f"请求 {path} 连续失败: {last_error}") from last_error


def parse_snapshot(
    current_raw: dict[str, Any],
    daily_raw: dict[str, Any],
    hourly_raw: dict[str, Any],
    minutely_raw: dict[str, Any],
    alerts_raw: dict[str, Any],
    *,
    fetched_at: datetime,
) -> WeatherSnapshot:
    try:
        now = current_raw["now"]
        current = CurrentWeather(
            observed_at=_datetime(now["obsTime"]),
            temperature=int(now["temp"]),
            feels_like=int(now["feelsLike"]),
            icon=str(now["icon"]),
            text=str(now["text"]),
            wind_direction=str(now["windDir"]),
            wind_scale=str(now["windScale"]),
            humidity=int(now["humidity"]),
            precipitation=float(now.get("precip") or 0),
        )
        daily = tuple(
            DailyForecast(
                day=datetime.fromisoformat(item["fxDate"]).date(),
                min_temperature=int(item["tempMin"]),
                max_temperature=int(item["tempMax"]),
                icon_day=str(item["iconDay"]),
                text_day=str(item["textDay"]),
                wind_direction=str(item["windDirDay"]),
                wind_scale=str(item["windScaleDay"]),
                humidity=int(item["humidity"]),
            )
            for item in daily_raw["daily"][:3]
        )
        hourly = tuple(
            HourlyForecast(
                forecast_at=_datetime(item["fxTime"]),
                temperature=int(item["temp"]),
                icon=str(item["icon"]),
                text=str(item["text"]),
                precipitation_probability=int(item.get("pop") or 0),
                precipitation=float(item.get("precip") or 0),
            )
            for item in hourly_raw.get("hourly", [])
        )
        minutely = tuple(
            MinutePrecipitation(
                forecast_at=_datetime(item["fxTime"]),
                precipitation=float(item.get("precip") or 0),
                kind=str(item.get("type") or "rain"),
            )
            for item in minutely_raw.get("minutely", [])
        )
        alerts = tuple(_parse_alert(item) for item in alerts_raw.get("alerts", []) if _active_alert(item))
        if not daily:
            raise KeyError("daily")
        return WeatherSnapshot(
            fetched_at=fetched_at,
            api_updated_at=_datetime(current_raw["updateTime"]),
            current=current,
            daily=daily,
            hourly=hourly,
            minutely=minutely,
            minutely_summary=str(minutely_raw.get("summary") or ""),
            alerts=alerts,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise WeatherAPIError(f"和风天气返回数据结构异常: {exc}") from exc


def _parse_alert(item: dict[str, Any]) -> WeatherAlert:
    event = item.get("eventType") or {}
    title = str(event.get("name") or item.get("headline") or "天气")
    return WeatherAlert(
        alert_id=str(item.get("id") or title),
        title=title,
        severity=str(item.get("severity") or ""),
        status=str((item.get("messageType") or {}).get("code") or ""),
        effective_at=_datetime(item["effectiveTime"]) if item.get("effectiveTime") else None,
    )


def _active_alert(item: dict[str, Any]) -> bool:
    return (item.get("messageType") or {}).get("code") != "cancel"


def _datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64json(data: dict[str, Any]) -> str:
    return _b64(json.dumps(data, ensure_ascii=True, separators=(",", ":")).encode("utf-8"))
