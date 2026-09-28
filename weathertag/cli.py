from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
from datetime import datetime, timedelta
from pathlib import Path

from .config import DEFAULT_FONT_PATH, ConfigError, RenderConfig, load_config
from .demo import demo_snapshot
from .epd import BleEPDDisplay, DisabledDisplay, scan_devices
from .notifier import Notifier
from .renderer import WeatherRenderer
from .rules import build_reminders
from .service import WeatherTagService
from .state import StateStore
from .weather import JWTProvider, QWeatherClient


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="weathertag", description="家庭电子墨水屏天气提醒服务")
    sub = parser.add_subparsers(dest="command", required=True)

    demo = sub.add_parser("render-demo", help="渲染无需 API 或硬件的示例图片")
    demo.add_argument(
        "--scenario",
        choices=("normal", "night", "upcoming", "rain", "warning", "multi", "failure"),
        default="normal",
    )
    demo.add_argument("--output", type=Path, default=Path("var/demo.png"))
    demo.add_argument("--font", type=Path, default=DEFAULT_FONT_PATH)
    demo.add_argument("--small-font", type=Path, default=None)
    demo.add_argument("--battery-millivolts", type=int, default=2987, help="示例电池电压，单位 mV")

    validate = sub.add_parser("validate-config", help="检查配置和 JWT 私钥")
    validate.add_argument("--config", type=Path, default=Path("config.toml"))

    once = sub.add_parser("run-once", help="获取天气并执行一次更新")
    once.add_argument("--config", type=Path, default=Path("config.toml"))
    once.add_argument("--force", action="store_true", help="忽略变化检测并强制刷新屏幕")

    serve = sub.add_parser("serve", help="持续运行天气更新服务")
    serve.add_argument("--config", type=Path, default=Path("config.toml"))

    scan = sub.add_parser("scan-ble", help="扫描附近 BLE 设备")
    scan.add_argument("--timeout", type=float, default=8)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "render-demo":
            return _render_demo(args)
        if args.command == "validate-config":
            return _validate(args.config)
        if args.command == "scan-ble":
            return asyncio.run(_scan(args.timeout))
        return asyncio.run(_run_service(args))
    except (ConfigError, FileNotFoundError, ValueError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


def _render_demo(args: argparse.Namespace) -> int:
    renderer = WeatherRenderer(RenderConfig(font_path=args.font, small_font_path=args.small_font))
    now = datetime.now().astimezone()
    if args.scenario == "failure":
        image = renderer.render_failure(now, rendered_at=now)
    else:
        snapshot = demo_snapshot(args.scenario, now)
        from .config import RuleConfig
        from .models import DailyForecast

        rules = RuleConfig()
        yesterday = None
        if args.scenario == "multi":
            today = snapshot.daily[0]
            yesterday = DailyForecast(
                day=today.day - timedelta(days=1),
                min_temperature=30,
                max_temperature=38,
                icon_day="100",
                text_day="晴",
                wind_direction="东南风",
                wind_scale="3",
                humidity=55,
            )
        image = renderer.render(
            snapshot,
            build_reminders(snapshot, rules, yesterday),
            rules,
            rendered_at=now,
            battery_millivolts=args.battery_millivolts,
        )
    renderer.save(image, args.output.resolve())
    print(args.output.resolve())
    return 0


def _validate(path: Path) -> int:
    config = load_config(path)
    config.validate()
    if not config.render.font_path.is_file():
        raise ConfigError(f"字体文件不存在: {config.render.font_path}")
    if config.render.small_font_path is not None and not config.render.small_font_path.is_file():
        raise ConfigError(f"小字号字体文件不存在: {config.render.small_font_path}")
    JWTProvider(config.qweather).token()
    print("配置有效")
    return 0


async def _scan(timeout: float) -> int:
    devices = await scan_devices(timeout)
    if not devices:
        print("未发现 BLE 设备")
    for address, name in devices:
        print(f"{address}\t{name}")
    return 0


async def _run_service(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    config.validate()
    logging.basicConfig(
        level=getattr(logging, config.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    renderer = WeatherRenderer(config.render)
    display = BleEPDDisplay(config.ble) if config.ble.enabled else DisabledDisplay()
    notifier = Notifier(config.gotify)
    async with QWeatherClient(config.qweather) as weather:
        service = WeatherTagService(
            config,
            weather,
            renderer,
            display,
            notifier,
            StateStore(config.state_path),
        )
        if args.command == "run-once":
            success = await service.run_once(force=args.force)
            return 0 if success else 1

        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for signum in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(signum, stop.set)
            except NotImplementedError:
                pass
        await service.serve(stop)
        return 0
