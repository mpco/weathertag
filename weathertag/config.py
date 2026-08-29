from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping


class ConfigError(ValueError):
    """Raised when required configuration is missing or invalid."""


DEFAULT_FONT_PATH = Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc")


@dataclass(frozen=True, slots=True)
class QWeatherConfig:
    api_host: str = ""
    project_id: str = ""
    credential_id: str = ""
    private_key_path: Path | None = None
    private_key_pem: str = ""
    longitude: float = 0.0
    latitude: float = 0.0
    language: str = "zh"
    timeout_seconds: float = 15.0
    retry_attempts: int = 3


@dataclass(frozen=True, slots=True)
class BleConfig:
    enabled: bool = False
    address: str = ""
    name: str = ""
    connect_timeout_seconds: float = 20.0
    retry_attempts: int = 3
    write_ack_interval: int = 20
    refresh_wait_seconds: float = 25.0


@dataclass(frozen=True, slots=True)
class GotifyConfig:
    enabled: bool = False
    base_url: str = ""
    token: str = ""
    priority: int = 7
    timeout_seconds: float = 10.0
    cooldown_minutes: int = 360


@dataclass(frozen=True, slots=True)
class ScheduleConfig:
    poll_minutes: int = 10
    morning_minutes: int = 30
    daytime_minutes: int = 60
    evening_minutes: int = 30
    overnight_minutes: int = 120

    def display_interval_minutes(self, hour: int) -> int:
        if 6 <= hour < 9:
            return self.morning_minutes
        if 9 <= hour < 18:
            return self.daytime_minutes
        if 18 <= hour < 23:
            return self.evening_minutes
        return self.overnight_minutes


@dataclass(frozen=True, slots=True)
class RuleConfig:
    rain_threshold_mm: float = 0.01
    high_temperature_c: int = 35
    cold_temperature_c: int = 5
    temperature_gap_c: int = 10
    significant_temperature_change_c: int = 2
    hourly_rain_probability: int = 50


@dataclass(frozen=True, slots=True)
class RenderConfig:
    width: int = 400
    height: int = 300
    font_path: Path = DEFAULT_FONT_PATH


@dataclass(frozen=True, slots=True)
class AppConfig:
    qweather: QWeatherConfig = field(default_factory=QWeatherConfig)
    ble: BleConfig = field(default_factory=BleConfig)
    gotify: GotifyConfig = field(default_factory=GotifyConfig)
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)
    rules: RuleConfig = field(default_factory=RuleConfig)
    render: RenderConfig = field(default_factory=RenderConfig)
    state_path: Path = Path("var/state.json")
    output_path: Path = Path("var/latest.png")
    log_level: str = "INFO"

    def validate(self, *, require_weather: bool = True) -> None:
        errors: list[str] = []
        if require_weather:
            if not self.qweather.api_host:
                errors.append("qweather.api_host 未配置")
            if not self.qweather.project_id:
                errors.append("qweather.project_id 未配置")
            if not self.qweather.credential_id:
                errors.append("qweather.credential_id 未配置")
            if not self.qweather.private_key_pem and not self.qweather.private_key_path:
                errors.append("qweather.private_key_path 或 WEATHERTAG_QWEATHER_PRIVATE_KEY_PEM 未配置")
            if not (-180 <= self.qweather.longitude <= 180):
                errors.append("qweather.longitude 必须在 -180 到 180 之间")
            if not (-90 <= self.qweather.latitude <= 90):
                errors.append("qweather.latitude 必须在 -90 到 90 之间")
        if self.render.width != 400 or self.render.height != 300:
            errors.append("当前硬件仅支持 render.width=400、render.height=300")
        if self.ble.enabled and not (self.ble.address or self.ble.name):
            errors.append("启用 BLE 时必须配置 ble.address 或 ble.name")
        if self.ble.refresh_wait_seconds < 0:
            errors.append("ble.refresh_wait_seconds 不能小于 0")
        if self.gotify.enabled and not (self.gotify.base_url and self.gotify.token):
            errors.append("启用 Gotify 时必须配置 gotify.base_url 和 gotify.token")
        if self.schedule.poll_minutes < 1:
            errors.append("schedule.poll_minutes 必须大于 0")
        if errors:
            raise ConfigError("；".join(errors))


def load_config(path: str | Path, environ: Mapping[str, str] | None = None) -> AppConfig:
    config_path = Path(path).expanduser().resolve()
    try:
        with config_path.open("rb") as handle:
            raw = tomllib.load(handle)
    except FileNotFoundError as exc:
        raise ConfigError(f"配置文件不存在: {config_path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"配置文件格式错误: {exc}") from exc

    env = os.environ if environ is None else environ
    base = config_path.parent
    qw = raw.get("qweather", {})
    ble = raw.get("ble", {})
    gotify = raw.get("gotify", {})
    schedule = raw.get("schedule", {})
    rules = raw.get("rules", {})
    render = raw.get("render", {})
    app = raw.get("app", {})

    private_path_raw = _env(env, "WEATHERTAG_QWEATHER_PRIVATE_KEY_PATH", qw.get("private_key_path", ""))
    private_path = _resolve_path(base, private_path_raw) if private_path_raw else None
    font_path = _resolve_path(base, render.get("font_path", str(DEFAULT_FONT_PATH)))

    return AppConfig(
        qweather=QWeatherConfig(
            api_host=_normalise_host(_env(env, "WEATHERTAG_QWEATHER_API_HOST", qw.get("api_host", ""))),
            project_id=_env(env, "WEATHERTAG_QWEATHER_PROJECT_ID", qw.get("project_id", "")),
            credential_id=_env(env, "WEATHERTAG_QWEATHER_CREDENTIAL_ID", qw.get("credential_id", "")),
            private_key_path=private_path,
            private_key_pem=_env(env, "WEATHERTAG_QWEATHER_PRIVATE_KEY_PEM", ""),
            longitude=float(_env(env, "WEATHERTAG_LONGITUDE", qw.get("longitude", 0.0))),
            latitude=float(_env(env, "WEATHERTAG_LATITUDE", qw.get("latitude", 0.0))),
            language=str(qw.get("language", "zh")),
            timeout_seconds=float(qw.get("timeout_seconds", 15)),
            retry_attempts=int(qw.get("retry_attempts", 3)),
        ),
        ble=BleConfig(
            enabled=_as_bool(_env(env, "WEATHERTAG_BLE_ENABLED", ble.get("enabled", False))),
            address=_env(env, "WEATHERTAG_BLE_ADDRESS", ble.get("address", "")),
            name=_env(env, "WEATHERTAG_BLE_NAME", ble.get("name", "")),
            connect_timeout_seconds=float(ble.get("connect_timeout_seconds", 20)),
            retry_attempts=int(ble.get("retry_attempts", 3)),
            write_ack_interval=int(ble.get("write_ack_interval", 20)),
            refresh_wait_seconds=float(ble.get("refresh_wait_seconds", 25)),
        ),
        gotify=GotifyConfig(
            enabled=_as_bool(_env(env, "WEATHERTAG_GOTIFY_ENABLED", gotify.get("enabled", False))),
            base_url=_env(env, "WEATHERTAG_GOTIFY_URL", gotify.get("base_url", "")).rstrip("/"),
            token=_env(env, "WEATHERTAG_GOTIFY_TOKEN", gotify.get("token", "")),
            priority=int(gotify.get("priority", 7)),
            timeout_seconds=float(gotify.get("timeout_seconds", 10)),
            cooldown_minutes=int(gotify.get("cooldown_minutes", 360)),
        ),
        schedule=ScheduleConfig(**schedule),
        rules=RuleConfig(**rules),
        render=RenderConfig(
            width=int(render.get("width", 400)),
            height=int(render.get("height", 300)),
            font_path=font_path,
        ),
        state_path=_resolve_path(base, app.get("state_path", "var/state.json")),
        output_path=_resolve_path(base, app.get("output_path", "var/latest.png")),
        log_level=str(app.get("log_level", "INFO")).upper(),
    )


def _env(environ: Mapping[str, str], name: str, default: object) -> str:
    value = environ.get(name)
    return str(default if value is None else value)


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    normal = str(value).strip().lower()
    if normal in {"1", "true", "yes", "on"}:
        return True
    if normal in {"0", "false", "no", "off", ""}:
        return False
    raise ConfigError(f"无法识别的布尔值: {value}")


def _resolve_path(base: Path, value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else (base / path).resolve()


def _normalise_host(host: str) -> str:
    host = host.strip().rstrip("/")
    for prefix in ("https://", "http://"):
        if host.startswith(prefix):
            host = host[len(prefix) :]
    return host
