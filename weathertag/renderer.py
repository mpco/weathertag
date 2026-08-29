from __future__ import annotations

import math
from dataclasses import dataclass
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


@dataclass(frozen=True, slots=True)
class ScreenLayout:
    """All manually tuneable coordinates and font sizes for the 400x300 canvas."""

    text_stroke_width: int
    use_current_accent: bool
    header_date_position: tuple[int, int]
    header_date_font: int
    header_update_position: tuple[int, int]
    header_update_font: int
    battery_voltage_position: tuple[int, int]
    battery_voltage_font: int
    battery_outline: tuple[int, int, int, int]
    battery_terminal: tuple[int, int, int, int]
    header_rule: tuple[int, int, int, int]
    main_rule: tuple[int, int, int, int]
    current_icon_center: tuple[int, int]
    current_icon_radius: int
    current_temperature_position: tuple[int, int]
    current_temperature_font: int
    current_unit_position: tuple[int, int]
    current_unit_font: int
    current_summary_position: tuple[int, int]
    current_summary_font: int
    current_summary_max_width: int
    forecast_label_x: int
    forecast_label_font: int
    forecast_icon_x: int
    forecast_icon_radius: int
    forecast_weather_x: int
    forecast_weather_font: int
    forecast_weather_max_width: int
    forecast_temperature_x: int
    forecast_temperature_font: int
    forecast_row_y: tuple[int, int, int]
    forecast_rule_y: tuple[int, int]
    today_detail_position: tuple[int, int]
    today_detail_font: int
    today_detail_max_width: int
    current_accent_bar: tuple[int, int, int, int]
    precipitation_summary_position: tuple[int, int]
    precipitation_summary_font: int
    chart_left: int
    chart_right: int
    chart_top: int
    chart_bottom: int
    chart_label_y: int
    chart_label_font: int
    reminder_box: tuple[int, int, int, int]
    reminder_position: tuple[int, int]
    reminder_font: int
    reminder_max_width: int


# 手动微调入口：修改这里后运行 `weathertag render-demo` 生成预览。
LAYOUT = ScreenLayout(
    text_stroke_width=0,
    use_current_accent=True,
    header_date_position=(8, 16),
    header_date_font=17,
    header_update_position=(225, 16),
    header_update_font=15,
    battery_voltage_position=(362, 16),
    battery_voltage_font=13,
    battery_outline=(369, 10, 389, 21),
    battery_terminal=(390, 13, 392, 18),
    header_rule=(8, 31, 392, 31),
    main_rule=(197, 39, 197, 201),
    current_icon_center=(43, 83),
    current_icon_radius=34,
    current_temperature_position=(108, 48),
    current_temperature_font=58,
    current_unit_position=(142, 57),
    current_unit_font=24,
    current_summary_position=(102, 151),
    current_summary_font=17,
    current_summary_max_width=180,
    forecast_label_x=211,
    forecast_label_font=17,
    forecast_icon_x=251,
    forecast_icon_radius=15,
    forecast_weather_x=273,
    forecast_weather_font=15,
    forecast_weather_max_width=58,
    forecast_temperature_x=392,
    forecast_temperature_font=17,
    forecast_row_y=(56, 121, 175),
    forecast_rule_y=(94, 148),
    today_detail_position=(211, 80),
    today_detail_font=14,
    today_detail_max_width=181,
    current_accent_bar=(201, 41, 204, 92),
    precipitation_summary_position=(8, 207),
    precipitation_summary_font=14,
    chart_left=190,
    chart_right=391,
    chart_top=209,
    chart_bottom=243,
    chart_label_y=245,
    chart_label_font=9,
    reminder_box=(8, 258, 392, 293),
    reminder_position=(200, 275),
    reminder_font=20,
    reminder_max_width=346,
)


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
        draw.line(LAYOUT.header_rule, fill=BLACK, width=1)
        draw.line(LAYOUT.main_rule, fill=BLACK, width=1)

        self._current(draw, snapshot)
        self._forecast(draw, snapshot)
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
        draw_text(
            draw,
            LAYOUT.header_date_position,
            left,
            font=self.font(LAYOUT.header_date_font),
            fill=BLACK,
            anchor="lm",
        )
        draw_text(
            draw,
            LAYOUT.header_update_position,
            f"更新 {rendered_at.strftime('%H:%M')}",
            font=self.font(LAYOUT.header_update_font),
            fill=BLACK,
            anchor="mm",
        )
        draw_battery(draw, battery_millivolts, self.font(LAYOUT.battery_voltage_font))

    def _current(self, draw: ImageDraw.ImageDraw, snapshot: WeatherSnapshot) -> None:
        current = snapshot.current
        draw_weather_icon(
            draw,
            LAYOUT.current_icon_center,
            icon_category(current.icon),
            LAYOUT.current_icon_radius,
            BLACK,
        )
        draw_text(
            draw,
            LAYOUT.current_temperature_position,
            f"{current.temperature}",
            font=self.font(LAYOUT.current_temperature_font),
            fill=BLACK,
            anchor="ma",
        )
        accent = RED if LAYOUT.use_current_accent else BLACK
        draw_text(
            draw,
            LAYOUT.current_unit_position,
            "℃",
            font=self.font(LAYOUT.current_unit_font),
            fill=accent,
        )
        summary_font = self.font(LAYOUT.current_summary_font)
        summary = fit_text(
            draw,
            f"{current.text} · 体感{current.feels_like}℃",
            summary_font,
            LAYOUT.current_summary_max_width,
        )
        draw_text(
            draw,
            LAYOUT.current_summary_position,
            summary,
            font=summary_font,
            fill=BLACK,
            anchor="mm",
        )

    def _forecast(self, draw: ImageDraw.ImageDraw, snapshot: WeatherSnapshot) -> None:
        labels = ("今", "明", "后")
        for index, day in enumerate(snapshot.daily[:3]):
            y = LAYOUT.forecast_row_y[index]
            label = labels[index]
            label_color = RED if index == 0 and LAYOUT.use_current_accent else BLACK
            draw_text(
                draw,
                (LAYOUT.forecast_label_x, y),
                label,
                font=self.font(LAYOUT.forecast_label_font),
                fill=label_color,
                anchor="lm",
            )
            draw_weather_icon(
                draw,
                (LAYOUT.forecast_icon_x, y),
                icon_category(day.icon_day),
                LAYOUT.forecast_icon_radius,
                BLACK,
            )
            weather_font = self.font(LAYOUT.forecast_weather_font)
            weather = fit_text(draw, day.text_day, weather_font, LAYOUT.forecast_weather_max_width)
            draw_text(
                draw,
                (LAYOUT.forecast_weather_x, y),
                weather,
                font=weather_font,
                fill=BLACK,
                anchor="lm",
            )
            draw_text(
                draw,
                (LAYOUT.forecast_temperature_x, y),
                f"{day.min_temperature}~{day.max_temperature}°",
                font=self.font(LAYOUT.forecast_temperature_font),
                fill=BLACK,
                anchor="rm",
            )

        today_detail = (
            f"{snapshot.current.wind_direction}{snapshot.current.wind_scale}级"
            f" · 湿度{snapshot.current.humidity}%"
        )
        today_detail_font = self.font(LAYOUT.today_detail_font)
        today_detail = fit_text(
            draw,
            today_detail,
            today_detail_font,
            LAYOUT.today_detail_max_width,
        )
        draw_text(
            draw,
            LAYOUT.today_detail_position,
            today_detail,
            font=today_detail_font,
            fill=BLACK,
        )
        for y in LAYOUT.forecast_rule_y:
            draw.line((207, y, 392, y), fill=BLACK, width=1)
        if LAYOUT.use_current_accent:
            draw.rectangle(LAYOUT.current_accent_bar, fill=RED)

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
        draw_text(
            draw,
            LAYOUT.precipitation_summary_position,
            summary,
            font=self.font(LAYOUT.precipitation_summary_font),
            fill=color,
        )

        values = [item.precipitation for item in snapshot.minutely[:24]]
        if not values:
            values = [0.0] * 24
        maximum = max(max(values), rules.rain_threshold_mm)
        chart_left, chart_right = LAYOUT.chart_left, LAYOUT.chart_right
        bottom, top = LAYOUT.chart_bottom, LAYOUT.chart_top
        draw.line((chart_left, bottom, chart_right, bottom), fill=BLACK, width=1)
        width = max(2, (chart_right - chart_left) // len(values) - 1)
        for index, value in enumerate(values):
            height = 0 if value <= 0 else max(2, round((value / maximum) * (bottom - top)))
            x = chart_left + index * (chart_right - chart_left) / len(values)
            draw.rectangle((round(x), bottom - height, round(x) + width, bottom), fill=color)
        draw_text(
            draw,
            (chart_left, LAYOUT.chart_label_y),
            "现在",
            font=self.font(LAYOUT.chart_label_font),
            fill=BLACK,
        )
        draw_text(
            draw,
            (chart_right, LAYOUT.chart_label_y),
            "2小时",
            font=self.font(LAYOUT.chart_label_font),
            fill=BLACK,
            anchor="ra",
        )

    def _reminder(self, draw: ImageDraw.ImageDraw, reminder: Reminder) -> None:
        color = RED if reminder.use_red else BLACK
        draw.rounded_rectangle(LAYOUT.reminder_box, radius=7, outline=color, width=2)
        if reminder.use_red:
            draw.rectangle((8, 265, 13, 286), fill=RED)
        reminder_font = self.font(LAYOUT.reminder_font)
        message = fit_text(draw, reminder.text, reminder_font, LAYOUT.reminder_max_width)
        draw_text(
            draw,
            LAYOUT.reminder_position,
            message,
            font=reminder_font,
            fill=color,
            anchor="mm",
        )


def draw_text(
    draw: ImageDraw.ImageDraw,
    position: tuple[float, float],
    text: str,
    *,
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int],
    anchor: str | None = None,
) -> None:
    """Render text using the globally tuneable stroke width."""
    draw.text(
        position,
        text,
        font=font,
        fill=fill,
        anchor=anchor,
        stroke_width=LAYOUT.text_stroke_width,
        stroke_fill=fill,
    )


def draw_battery(
    draw: ImageDraw.ImageDraw,
    millivolts: int | None,
    font: ImageFont.FreeTypeFont,
) -> None:
    draw.rounded_rectangle(LAYOUT.battery_outline, radius=2, outline=BLACK, width=1)
    draw.rectangle(LAYOUT.battery_terminal, fill=BLACK)
    voltage = "--.--V" if millivolts is None else f"{millivolts / 1000:.2f}V"
    draw_text(draw, LAYOUT.battery_voltage_position, voltage, font=font, fill=BLACK, anchor="rm")


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
