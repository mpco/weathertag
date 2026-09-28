from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .config import RenderConfig, RuleConfig
from .models import Reminder, ReminderKind, WeatherSnapshot
from .rules import icon_category

BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
RED = (220, 0, 0)
WEEKDAYS = "一二三四五六日"
PRECIPITATION_TERMS = (
    "特大暴雨",
    "大暴雨",
    "雨夹雪",
    "雷阵雨",
    "暴雨",
    "阵雨",
    "大雨",
    "中雨",
    "小雨",
    "暴雪",
    "大雪",
    "中雪",
    "小雪",
    "冻雨",
)


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
    battery_empty_millivolts: int
    battery_full_millivolts: int
    battery_unknown_fill_ratio: float
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
    today_detail_anchor: str
    today_detail_font: int
    today_detail_max_width: int
    current_accent_bar: tuple[int, int, int, int]
    chart_left: int
    chart_right: int
    chart_top: int
    chart_bottom: int
    chart_label_y: int
    chart_label_font: int
    reminder_top_rule: tuple[int, int, int, int]


# 手动微调入口：修改这里后运行 `weathertag render-demo` 生成预览。
LAYOUT = ScreenLayout(
    text_stroke_width=0,  # 全局文字描边像素；1-bit 屏建议保持 0。
    use_current_accent=True,  # 是否用红色强调当前天气。
    header_date_position=(8, 16),  # 顶栏日期的（x, y）中线位置。
    header_date_font=17,  # 顶栏日期字号。
    header_update_position=(225, 16),  # 顶栏更新时间的中心位置。
    header_update_font=15,  # 顶栏更新时间字号。
    battery_voltage_position=(362, 16),  # 电压文字的右中对齐位置。
    battery_voltage_font=13,  # 电压文字字号。
    battery_outline=(369, 10, 389, 21),  # 电池主体外框（左、上、右、下）。
    battery_terminal=(390, 13, 392, 18),  # 电池右侧正极小块边界。
    battery_empty_millivolts=2200,  # 电池填充比例视为 0% 的电压。
    battery_full_millivolts=3000,  # 电池填充比例视为 100% 的电压。
    battery_unknown_fill_ratio=0.5,  # 尚未读到电压时的默认填充比例。
    header_rule=(8, 31, 392, 31),  # 顶栏下方水平分隔线。
    main_rule=(197, 39, 197, 201),  # 当前天气与三日预报之间的竖线。
    current_icon_center=(43, 83),  # 左侧当前天气图标中心。
    current_icon_radius=34,  # 左侧当前天气图标半径。
    current_temperature_position=(108, 48),  # 当前温度数字的中上对齐位置。
    current_temperature_font=58,  # 当前温度数字字号。
    current_unit_position=(142, 57),  # 当前温度单位的左上位置。
    current_unit_font=24,  # 当前温度单位字号。
    current_summary_position=(102, 141),  # 天气文字与体感温度的中心位置。
    current_summary_font=22,  # 天气文字与体感温度字号。
    current_summary_max_width=184,  # 天气文字与体感温度最大宽度。
    forecast_label_x=211,  # “今/明/后”标签的左边 x 坐标。
    forecast_label_font=17,  # “今/明/后”标签字号。
    forecast_icon_x=251,  # 三日预报图标中心 x 坐标。
    forecast_icon_radius=15,  # 三日预报图标半径。
    forecast_weather_x=273,  # 三日预报天气文字左边 x 坐标。
    forecast_weather_font=15,  # 三日预报天气文字字号。
    forecast_weather_max_width=58,  # 三日预报天气文字最大宽度。
    forecast_temperature_x=392,  # 三日高低温的右边 x 坐标。
    forecast_temperature_font=17,  # 三日高低温字号。
    forecast_row_y=(56, 121, 175),  # 今天、明天、后天三行的中线 y 坐标。
    forecast_rule_y=(94, 148),  # 三日预报两条水平分隔线的 y 坐标。
    today_detail_position=(392, 77),  # 今日风力/湿度的右中对齐位置。
    today_detail_anchor="rm",  # 今日风力/湿度的 Pillow 文字锚点。
    today_detail_font=13,  # 今日风力/湿度/紫外线字号。
    today_detail_max_width=181,  # 今日风力/湿度最大宽度。
    current_accent_bar=(201, 41, 204, 92),  # “今”行左侧红色强调条边界。
    chart_left=10,  # 当前天气区降水趋势图左边界。
    chart_right=188,  # 当前天气区降水趋势图右边界。
    chart_top=173,  # 小型降水柱状图最高点。
    chart_bottom=187,  # 小型降水柱状图基线。
    chart_label_y=189,  # 降水图固定文字“此刻 → 降雨信息 → 2小时”的顶部 y 坐标。
    chart_label_font=12,  # 降水图时间标签字号，界面最小字号。
    reminder_top_rule=(8, 205, 392, 205),  # 底部三行提醒区上方分割线。
)


def precipitation_detail(
    snapshot: WeatherSnapshot,
    rain_period: tuple[datetime, datetime],
    rules: RuleConfig,
) -> str:
    """使用 API 的降水摘要、类型和定量预报组成简短详情。"""
    start, end = rain_period
    condition = next(
        (term for term in PRECIPITATION_TERMS if term in snapshot.minutely_summary),
        "",
    )
    rainy_minutes = tuple(
        item
        for item in snapshot.minutely
        if start <= item.forecast_at < end
        and item.precipitation >= rules.rain_threshold_mm
    )
    if rainy_minutes:
        if not condition:
            kinds = {item.kind.lower() for item in rainy_minutes}
            if kinds == {"snow"}:
                condition = "雪"
            elif "snow" in kinds:
                condition = "雨雪"
            else:
                condition = "雨"
        peak = max(item.precipitation for item in rainy_minutes)
        peak_text = f"{peak:.2f}".rstrip("0").rstrip(".")
        return f"{condition} · 峰值{peak_text}mm"

    rainy_hours = tuple(
        item for item in snapshot.hourly if start <= item.forecast_at < end
    )
    if rainy_hours:
        weather = next((item.text for item in rainy_hours if item.text), condition or "有雨")
        probability = max(item.precipitation_probability for item in rainy_hours)
        return f"{weather} · 降水概率{probability}%"
    return condition


class WeatherRenderer:
    def __init__(self, config: RenderConfig) -> None:
        self.config = config
        if not config.font_path.is_file():
            raise FileNotFoundError(f"中文字体不存在: {config.font_path}")
        if config.small_font_path is not None and not config.small_font_path.is_file():
            raise FileNotFoundError(f"小字号字体不存在: {config.small_font_path}")
        self._fonts: dict[int, ImageFont.FreeTypeFont] = {}
        self._small_fonts: dict[int, ImageFont.FreeTypeFont] = {}

    def render(
        self,
        snapshot: WeatherSnapshot,
        reminder: Reminder | tuple[Reminder, ...],
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
        self._forecast(draw, snapshot, rules)
        self._precipitation(draw, snapshot, rules)
        self._reminder(draw, reminder if isinstance(reminder, tuple) else (reminder,))
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

    def small_font(self, size: int) -> ImageFont.FreeTypeFont:
        if size not in self._small_fonts:
            path = self.config.small_font_path or self.config.font_path
            self._small_fonts[size] = ImageFont.truetype(str(path), size=size)
        return self._small_fonts[size]

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

    def _forecast(self, draw: ImageDraw.ImageDraw, snapshot: WeatherSnapshot, rules: RuleConfig) -> None:
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

        today_detail = f"{snapshot.current.wind_direction}{snapshot.current.wind_scale}级 湿度{snapshot.current.humidity}%"
        today_detail_font = self.font(LAYOUT.today_detail_font)
        detail_x, detail_y = LAYOUT.today_detail_position
        detail_width = LAYOUT.today_detail_max_width
        uv = snapshot.daily[0].uv_index
        if uv is not None:
            uv_text = f"UV{uv}级"
            draw_text(
                draw, LAYOUT.today_detail_position, uv_text, font=today_detail_font,
                fill=RED if uv >= rules.uv_reminder_index else BLACK, anchor=LAYOUT.today_detail_anchor,
            )
            uv_width = round(draw.textlength(uv_text, font=today_detail_font))
            detail_x -= uv_width + 5
            detail_width -= uv_width + 5
        today_detail = fit_text(
            draw,
            today_detail,
            today_detail_font,
            detail_width,
        )
        draw_text(
            draw,
            (detail_x, detail_y),
            today_detail,
            font=today_detail_font,
            fill=BLACK,
            anchor=LAYOUT.today_detail_anchor,
        )
        for y in LAYOUT.forecast_rule_y:
            draw.line((207, y, 392, y), fill=BLACK, width=1)
        if LAYOUT.use_current_accent:
            draw.rectangle(LAYOUT.current_accent_bar, fill=RED)

    def _precipitation(self, draw: ImageDraw.ImageDraw, snapshot: WeatherSnapshot, rules: RuleConfig) -> None:
        has_rain = any(item.precipitation >= rules.rain_threshold_mm for item in snapshot.minutely)
        color = RED if has_rain else BLACK
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
            "此刻",
            font=self.small_font(LAYOUT.chart_label_font),
            fill=BLACK,
        )
        label_font = self.small_font(LAYOUT.chart_label_font)
        draw_text(draw, (42, LAYOUT.chart_label_y), "→", font=label_font, fill=BLACK)
        draw_text(
            draw, (96, LAYOUT.chart_label_y), "降雨信息",
            font=label_font, fill=BLACK, anchor="ma",
        )
        draw_text(draw, (138, LAYOUT.chart_label_y), "→", font=label_font, fill=BLACK)
        draw_text(
            draw,
            (chart_right, LAYOUT.chart_label_y),
            "2小时",
            font=self.small_font(LAYOUT.chart_label_font),
            fill=BLACK,
            anchor="ra",
        )

    def _reminder(self, draw: ImageDraw.ImageDraw, reminders: tuple[Reminder, ...]) -> None:
        change = next((item for item in reminders if item.kind == ReminderKind.TEMPERATURE_CHANGE), None)
        others = [item for item in reminders if item.kind != ReminderKind.TEMPERATURE_CHANGE]
        visible = others[:2]
        if change is not None:
            visible.append(change)
        visible.extend(others[2:2 + (3 - len(visible))])
        if not visible:
            return
        draw.line(LAYOUT.reminder_top_rule, fill=BLACK, width=1)
        font = self.font(20 if len(visible) == 1 else 18)
        for index, item in enumerate(visible):
            y = 224 + index * 29
            fill = RED if item.use_red else BLACK
            draw_text(draw, (10, y), "•", font=font, fill=fill, anchor="lm")
            if item.kind == ReminderKind.TEMPERATURE_CHANGE:
                halves = item.text.split("|", 1)
                if len(halves) == 2:
                    change_font = self.font(16)
                    for x, message in ((31, halves[0]), (210, halves[1])):
                        draw_text(draw, (x, y), fit_text(draw, message, change_font, 173), font=change_font, fill=fill, anchor="lm")
                    continue
            message = fit_text(draw, item.text, font, 358)
            draw_text(draw, (31, y), message, font=font, fill=fill, anchor="lm")


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
    if millivolts is None:
        fill_ratio = LAYOUT.battery_unknown_fill_ratio
    else:
        voltage_range = max(1, LAYOUT.battery_full_millivolts - LAYOUT.battery_empty_millivolts)
        fill_ratio = (millivolts - LAYOUT.battery_empty_millivolts) / voltage_range
        fill_ratio = min(1.0, max(0.0, fill_ratio))
    left, top, right, bottom = LAYOUT.battery_outline
    inner_left, inner_top = left + 2, top + 2
    inner_right, inner_bottom = right - 2, bottom - 2
    fill_right = round(inner_left + (inner_right - inner_left) * fill_ratio)
    if fill_right > inner_left:
        draw.rectangle((inner_left, inner_top, fill_right, inner_bottom), fill=BLACK)
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
    if category == "clear_night":
        draw_moon(draw, center, radius, color, show_stars=True)
        return
    if category == "sunny":
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
    elif category == "partly_cloudy_night":
        draw_moon(
            draw,
            (round(x - radius * .35), round(y - radius * .3)),
            round(radius * .68),
            color,
            show_stars=False,
        )
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


def draw_moon(
    draw: ImageDraw.ImageDraw,
    center: tuple[int, int],
    radius: int,
    color: tuple[int, int, int],
    *,
    show_stars: bool,
) -> None:
    """Draw a bold crescent silhouette that remains legible on a 1-bit plane."""
    x, y = center
    moon_radius = radius * .62
    draw.ellipse(
        (x - moon_radius, y - moon_radius, x + moon_radius, y + moon_radius),
        fill=color,
    )
    draw.ellipse(
        (x - radius * .12, y - radius * .72, x + radius * .65, y + radius * .12),
        fill=WHITE,
    )
    if not show_stars:
        return
    draw_star(draw, (round(x + radius * .58), round(y - radius * .45)), max(2, radius // 9), color)
    draw_star(draw, (round(x + radius * .78), round(y + radius * .02)), max(2, radius // 12), color)


def draw_star(
    draw: ImageDraw.ImageDraw,
    center: tuple[int, int],
    radius: int,
    color: tuple[int, int, int],
) -> None:
    """Draw a compact four-point star without relying on anti-aliasing."""
    x, y = center
    draw.polygon(
        (
            (x, y - radius),
            (x + 1, y - 1),
            (x + radius, y),
            (x + 1, y + 1),
            (x, y + radius),
            (x - 1, y + 1),
            (x - radius, y),
            (x - 1, y - 1),
        ),
        fill=color,
    )
