from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .config import RenderConfig, RuleConfig
from .models import Reminder, WeatherSnapshot
from .rules import icon_category, upcoming_rain_minutes

BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
RED = (220, 0, 0)
WEEKDAYS = "一二三四五六日"


class WeatherRenderer:
    def __init__(self, config: RenderConfig) -> None:
        self.config = config
        if not config.font_path.is_file():
            raise FileNotFoundError(f"中文字体不存在: {config.font_path}")
        self._fonts: dict[int, ImageFont.FreeTypeFont] = {}

    def render(
        self,
        snapshot: WeatherSnapshot,
        reminder: Reminder,
        rules: RuleConfig,
        *,
        rendered_at: datetime | None = None,
        battery_millivolts: int | None = None,
    ) -> Image.Image:
        rendered_at = rendered_at or datetime.now().astimezone()
        image = Image.new("RGB", (self.config.width, self.config.height), WHITE)
        draw = ImageDraw.Draw(image)

        self._header(draw, rendered_at, battery_millivolts)
        draw.line((8, 31, 392, 31), fill=BLACK, width=2)
        draw.line((197, 39, 197, 166), fill=BLACK, width=2)

        self._current(draw, snapshot)
        self._forecast(draw, snapshot)
        self._today(draw, snapshot)
        self._precipitation(draw, snapshot, rules)
        self._reminder(draw, reminder)
        return image

    def render_failure(
        self,
        last_success: datetime | None,
        *,
        rendered_at: datetime | None = None,
    ) -> Image.Image:
        rendered_at = rendered_at or datetime.now().astimezone()
        image = Image.new("RGB", (self.config.width, self.config.height), WHITE)
        draw = ImageDraw.Draw(image)
        draw.rectangle((8, 8, 391, 291), outline=BLACK, width=2)
        draw.polygon(((40, 62), (75, 122), (5, 122)), outline=RED, fill=WHITE)
        draw_text(draw, (40, 101), "!", font=self.font(35), fill=RED, anchor="mm")
        draw_text(draw, (95, 72), "天气数据获取失败", font=self.font(28), fill=RED)
        draw.line((25, 142, 375, 142), fill=BLACK, width=1)
        draw_text(draw, (200, 177), "暂时无法更新天气信息", font=self.font(23), fill=BLACK, anchor="mm")
        if last_success:
            stamp = last_success.astimezone().strftime("%m月%d日 %H:%M")
            message = f"最后成功更新：{stamp}"
        else:
            message = "尚无成功获取记录"
        draw_text(draw, (200, 218), message, font=self.font(18), fill=BLACK, anchor="mm")
        draw_text(
            draw,
            (200, 267),
            f"本次尝试 {rendered_at.strftime('%H:%M')}  ·  WeatherTag",
            font=self.font(13),
            fill=BLACK,
            anchor="mm",
        )
        return image

    def save(self, image: Image.Image, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        image.save(path, format="PNG", optimize=True)

    def font(self, size: int) -> ImageFont.FreeTypeFont:
        if size not in self._fonts:
            self._fonts[size] = ImageFont.truetype(str(self.config.font_path), size=size)
        return self._fonts[size]

    def _header(
        self,
        draw: ImageDraw.ImageDraw,
        rendered_at: datetime,
        battery_millivolts: int | None,
    ) -> None:
        day = rendered_at
        left = f"{day.month}月{day.day}日  星期{WEEKDAYS[day.weekday()]}"
        draw_text(draw, (8, 16), left, font=self.font(16), fill=BLACK, anchor="lm")
        draw_text(
            draw,
            (232, 16),
            f"更新 {rendered_at.strftime('%H:%M')}",
            font=self.font(14),
            fill=BLACK,
            anchor="mm",
        )
        draw_battery(draw, battery_millivolts, self.font(13))

    def _current(self, draw: ImageDraw.ImageDraw, snapshot: WeatherSnapshot) -> None:
        current = snapshot.current
        draw_weather_icon(draw, (49, 82), icon_category(current.icon), 36, BLACK)
        draw_text(draw, (112, 45), f"{current.temperature}", font=self.font(58), fill=BLACK, anchor="ma")
        draw_text(draw, (176, 54), "℃", font=self.font(24), fill=BLACK)
        draw_text(draw, (111, 112), current.text, font=self.font(23), fill=BLACK, anchor="ma")
        draw_text(draw, (111, 141), f"体感 {current.feels_like}℃", font=self.font(16), fill=BLACK, anchor="ma")

    def _forecast(self, draw: ImageDraw.ImageDraw, snapshot: WeatherSnapshot) -> None:
        labels = ("今", "明", "后")
        for index, day in enumerate(snapshot.daily[:3]):
            y = 60 + index * 43
            label = labels[index]
            draw_text(draw, (211, y), label, font=self.font(17), fill=BLACK, anchor="lm")
            draw_weather_icon(draw, (258, y), icon_category(day.icon_day), 15, BLACK)
            weather = fit_text(draw, day.text_day, self.font(15), 61)
            draw_text(draw, (280, y), weather, font=self.font(15), fill=BLACK, anchor="lm")
            draw_text(
                draw,
                (392, y),
                f"{day.min_temperature}~{day.max_temperature}°",
                font=self.font(17),
                fill=BLACK,
                anchor="rm",
            )
            if index < min(2, len(snapshot.daily) - 1):
                draw.line((207, y + 21, 392, y + 21), fill=BLACK, width=1)

    def _today(self, draw: ImageDraw.ImageDraw, snapshot: WeatherSnapshot) -> None:
        today = snapshot.daily[0]
        draw.rounded_rectangle((8, 171, 392, 201), radius=5, outline=BLACK, width=1)
        draw_text(
            draw,
            (17, 186),
            f"今日 {today.min_temperature}℃～{today.max_temperature}℃",
            font=self.font(17),
            fill=BLACK,
            anchor="lm",
        )
        wind = f"{snapshot.current.wind_direction}{snapshot.current.wind_scale}级"
        draw_text(draw, (210, 186), wind, font=self.font(15), fill=BLACK, anchor="mm")
        draw_text(
            draw,
            (382, 186),
            f"湿度 {snapshot.current.humidity}%",
            font=self.font(15),
            fill=BLACK,
            anchor="rm",
        )

    def _precipitation(self, draw: ImageDraw.ImageDraw, snapshot: WeatherSnapshot, rules: RuleConfig) -> None:
        rain_in = upcoming_rain_minutes(snapshot, rules)
        has_rain = any(item.precipitation >= rules.rain_threshold_mm for item in snapshot.minutely)
        color = RED if has_rain else BLACK
        if rain_in is None:
            summary = "未来2小时无明显降雨"
        elif rain_in <= 5:
            summary = "降雨临近"
        else:
            summary = f"约{rain_in}分钟后可能有雨"
        draw_text(draw, (8, 207), summary, font=self.font(14), fill=color)

        values = [item.precipitation for item in snapshot.minutely[:24]]
        if not values:
            values = [0.0] * 24
        maximum = max(max(values), rules.rain_threshold_mm)
        chart_left, chart_right = 190, 391
        bottom, top = 243, 209
        draw.line((chart_left, bottom, chart_right, bottom), fill=BLACK, width=1)
        width = max(2, (chart_right - chart_left) // len(values) - 1)
        for index, value in enumerate(values):
            height = 0 if value <= 0 else max(2, round((value / maximum) * (bottom - top)))
            x = chart_left + index * (chart_right - chart_left) / len(values)
            draw.rectangle((round(x), bottom - height, round(x) + width, bottom), fill=color)
        draw_text(draw, (chart_left, 245), "现在", font=self.font(9), fill=BLACK)
        draw_text(draw, (chart_right, 245), "2小时", font=self.font(9), fill=BLACK, anchor="ra")

    def _reminder(self, draw: ImageDraw.ImageDraw, reminder: Reminder) -> None:
        color = RED if reminder.use_red else BLACK
        draw.rounded_rectangle((8, 258, 392, 293), radius=7, outline=color, width=2)
        if reminder.use_red:
            draw.rectangle((8, 265, 13, 286), fill=RED)
        message = fit_text(draw, reminder.text, self.font(20), 346)
        draw_text(draw, (200, 275), message, font=self.font(20), fill=color, anchor="mm")


def draw_text(
    draw: ImageDraw.ImageDraw,
    position: tuple[float, float],
    text: str,
    *,
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int],
    anchor: str | None = None,
) -> None:
    """Render slightly heavier type without requiring a separate bold font file."""
    draw.text(
        position,
        text,
        font=font,
        fill=fill,
        anchor=anchor,
        stroke_width=1 if font.size >= 13 else 0,
        stroke_fill=fill,
    )


def draw_battery(
    draw: ImageDraw.ImageDraw,
    millivolts: int | None,
    font: ImageFont.FreeTypeFont,
) -> None:
    draw.rounded_rectangle((311, 10, 332, 21), radius=2, outline=BLACK, width=2)
    draw.rectangle((333, 13, 336, 18), fill=BLACK)
    voltage = "--.--V" if millivolts is None else f"{millivolts / 1000:.2f}V"
    draw_text(draw, (392, 16), voltage, font=font, fill=BLACK, anchor="rm")


def fit_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> str:
    if draw.textlength(text, font=font) <= max_width:
        return text
    suffix = "…"
    while text and draw.textlength(text + suffix, font=font) > max_width:
        text = text[:-1]
    return text + suffix


def draw_weather_icon(
    draw: ImageDraw.ImageDraw,
    center: tuple[int, int],
    category: str,
    radius: int,
    color: tuple[int, int, int] = BLACK,
) -> None:
    x, y = center
    width = max(2, radius // 10)
    if category in {"sunny", "clear_night"}:
        if category == "clear_night":
            draw.ellipse((x - radius * .55, y - radius * .55, x + radius * .55, y + radius * .55), outline=color, width=width)
            draw.ellipse((x - radius * .2, y - radius * .7, x + radius * .7, y + radius * .25), fill=WHITE)
            return
        draw.ellipse((x - radius * .45, y - radius * .45, x + radius * .45, y + radius * .45), outline=color, width=width)
        for angle in range(0, 360, 45):
            rad = math.radians(angle)
            draw.line(
                (
                    x + math.cos(rad) * radius * .65,
                    y + math.sin(rad) * radius * .65,
                    x + math.cos(rad) * radius,
                    y + math.sin(rad) * radius,
                ),
                fill=color,
                width=width,
            )
        return

    cloud_y = y + radius * .08
    if category == "partly_cloudy":
        draw.ellipse((x - radius * .8, y - radius * .8, x + radius * .15, y + radius * .15), outline=color, width=width)
    draw.ellipse((x - radius * .72, cloud_y - radius * .18, x - radius * .18, cloud_y + radius * .36), fill=WHITE, outline=color, width=width)
    draw.ellipse((x - radius * .38, cloud_y - radius * .55, x + radius * .37, cloud_y + radius * .28), fill=WHITE, outline=color, width=width)
    draw.ellipse((x + radius * .02, cloud_y - radius * .24, x + radius * .68, cloud_y + radius * .36), fill=WHITE, outline=color, width=width)
    draw.line((x - radius * .47, cloud_y + radius * .36, x + radius * .4, cloud_y + radius * .36), fill=color, width=width)

    if category in {"rain", "storm"}:
        for offset in (-.38, 0, .38):
            draw.line(
                (x + radius * offset, y + radius * .55, x + radius * (offset - .12), y + radius * .92),
                fill=color,
                width=width,
            )
        if category == "storm":
            draw.line((x, y + radius * .43, x - radius * .12, y + radius * .75, x + radius * .05, y + radius * .7, x - radius * .08, y + radius), fill=color, width=width)
    elif category == "snow":
        for offset in (-.38, 0, .38):
            sx, sy = x + radius * offset, y + radius * .72
            draw.line((sx - radius * .12, sy, sx + radius * .12, sy), fill=color, width=width)
            draw.line((sx, sy - radius * .12, sx, sy + radius * .12), fill=color, width=width)
    elif category == "fog":
        for offset in (.58, .78, .98):
            draw.line((x - radius * .65, y + radius * offset, x + radius * .65, y + radius * offset), fill=color, width=width)
