from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Awaitable, Callable, Protocol

from PIL import Image

from .config import BleConfig

LOGGER = logging.getLogger(__name__)

SERVICE_UUID = "62750001-d828-918d-fb46-b6c11c675aec"
IMAGE_CHARACTERISTIC_UUID = "62750002-d828-918d-fb46-b6c11c675aec"
VERSION_CHARACTERISTIC_UUID = "62750003-d828-918d-fb46-b6c11c675aec"

CMD_INIT = 0x01
CMD_REFRESH = 0x05
CMD_WRITE_IMAGE = 0x30
MIN_WRITE_IMAGE_VERSION = 0x16


class EPDConnectionError(RuntimeError):
    """The electronic shelf label could not be updated."""


class Display(Protocol):
    async def send_image(self, image: Image.Image) -> None: ...


class DisabledDisplay:
    async def send_image(self, image: Image.Image) -> None:
        LOGGER.info("BLE 已禁用，仅保存渲染图片")


class BleEPDDisplay:
    """Send a 400x300 B/W/red image to EPD-nRF5 firmware v1.6+."""

    def __init__(self, config: BleConfig) -> None:
        self.config = config

    async def send_image(self, image: Image.Image) -> None:
        black, red = encode_three_color(image)
        last_error: Exception | None = None
        last_reason = "未知错误"
        for attempt in range(1, self.config.retry_attempts + 1):
            try:
                await self._send_planes(black, red)
                return
            except Exception as exc:  # Bleak backend errors vary by platform.
                last_error = exc
                last_reason = describe_ble_error(exc, self.config.connect_timeout_seconds)
                LOGGER.warning(
                    "BLE 更新第 %d/%d 次失败: %s",
                    attempt,
                    self.config.retry_attempts,
                    last_reason,
                )
                if attempt < self.config.retry_attempts:
                    await asyncio.sleep(min(2 ** (attempt - 1), 4))
        raise EPDConnectionError(f"BLE 更新连续失败: {last_reason}") from last_error

    async def _send_planes(self, black: bytes, red: bytes) -> None:
        try:
            from bleak import BleakClient, BleakScanner
        except ImportError as exc:
            raise EPDConnectionError("未安装 bleak，无法使用 BLE") from exc

        if self.config.address:
            device = await BleakScanner.find_device_by_address(
                self.config.address,
                timeout=self.config.connect_timeout_seconds,
            )
        else:
            expected = self.config.name.casefold()
            device = await BleakScanner.find_device_by_filter(
                lambda found, advertisement: (found.name or advertisement.local_name or "").casefold() == expected,
                timeout=self.config.connect_timeout_seconds,
            )
        if device is None:
            identity = self.config.address or self.config.name
            raise EPDConnectionError(f"未发现电子价签: {identity}")

        notification_event = asyncio.Event()
        transfer = TransferCapabilities()

        def notification(_: object, payload: bytearray) -> None:
            try:
                text = bytes(payload).decode("ascii")
            except UnicodeDecodeError:
                return  # The first notification is normally binary device configuration.
            match = re.search(r"mtu=(\d+)", text)
            if match:
                transfer.max_write_length = max(20, int(match.group(1)))
                transfer.rle = "rle=1" in text
                notification_event.set()

        async with BleakClient(device, timeout=self.config.connect_timeout_seconds) as client:
            try:
                version_raw = await client.read_gatt_char(VERSION_CHARACTERISTIC_UUID)
                version = version_raw[0]
            except Exception as exc:
                raise EPDConnectionError("无法读取 EPD-nRF5 固件版本") from exc
            if version < MIN_WRITE_IMAGE_VERSION:
                raise EPDConnectionError(
                    f"EPD-nRF5 固件版本 0x{version:02x} 过旧；需要 v1.6 (0x16) 或更新版本"
                )

            await client.start_notify(IMAGE_CHARACTERISTIC_UUID, notification)
            await client.write_gatt_char(IMAGE_CHARACTERISTIC_UUID, bytes((CMD_INIT,)), response=True)
            try:
                await asyncio.wait_for(notification_event.wait(), timeout=2)
            except TimeoutError:
                transfer.max_write_length = max(20, getattr(client, "mtu_size", 23) - 3)
                transfer.rle = False
                LOGGER.warning("设备未报告 MTU，使用 %d 字节并关闭 RLE", transfer.max_write_length)

            await self._write_plane(client.write_gatt_char, black, black_plane=True, capabilities=transfer)
            await self._write_plane(client.write_gatt_char, red, black_plane=False, capabilities=transfer)
            await self._refresh_and_wait(client.write_gatt_char)

    async def _refresh_and_wait(self, writer: Callable[..., Awaitable[None]]) -> None:
        await writer(IMAGE_CHARACTERISTIC_UUID, bytes((CMD_REFRESH,)), response=True)
        if self.config.refresh_wait_seconds > 0:
            LOGGER.info(
                "刷新命令已发送，保持 BLE 连接 %.1f 秒等待屏幕完成物理刷新",
                self.config.refresh_wait_seconds,
            )
            await asyncio.sleep(self.config.refresh_wait_seconds)

    async def _write_plane(
        self,
        writer: Callable[..., Awaitable[None]],
        data: bytes,
        *,
        black_plane: bool,
        capabilities: "TransferCapabilities",
    ) -> None:
        max_data = capabilities.max_write_length - 2  # command + image flags
        if max_data < 1:
            raise EPDConnectionError(f"设备报告的 MTU 无效: {capabilities.max_write_length}")
        compressed = rle_compress_chunks(data, max_data) if capabilities.rle else []
        use_rle = capabilities.rle and sum(map(len, compressed)) < len(data)
        chunks = compressed if use_rle else [data[index : index + max_data] for index in range(0, len(data), max_data)]
        for index, chunk in enumerate(chunks):
            flags = (0 if black_plane else 1) | (2 if index == 0 else 0) | (4 if use_rle else 0)
            payload = bytes((CMD_WRITE_IMAGE, flags)) + bytes(chunk)
            last = index == len(chunks) - 1
            response = last or self.config.write_ack_interval <= 0 or (
                (index + 1) % self.config.write_ack_interval == 0
            )
            await writer(IMAGE_CHARACTERISTIC_UUID, payload, response=response)


@dataclass(slots=True)
class TransferCapabilities:
    max_write_length: int = 20
    rle: bool = False


def describe_ble_error(error: Exception, timeout_seconds: float) -> str:
    if isinstance(error, TimeoutError):
        return (
            f"TimeoutError: BLE 操作在 {timeout_seconds:g} 秒内未完成"
            "（若堆栈位于 connect()，请检查天线、距离、设备占用和唤醒状态）"
        )
    detail = str(error).strip()
    name = type(error).__name__
    return f"{name}: {detail}" if detail else name


def encode_three_color(image: Image.Image) -> tuple[bytes, bytes]:
    if image.size != (400, 300):
        raise ValueError(f"电子价签图片必须为 400x300，实际为 {image.width}x{image.height}")
    rgb = image.convert("RGB")
    black = bytearray(400 * 300 // 8)
    red = bytearray(400 * 300 // 8)
    pixels = rgb.load()
    for y in range(300):
        for x in range(400):
            r, g, b = pixels[x, y]
            index = y * 50 + x // 8
            bit = 7 - x % 8
            grayscale = round(0.299 * r + 0.587 * g + 0.114 * b)
            if grayscale >= 140:
                black[index] |= 1 << bit
            if not (r > 160 and r > g and r > b):
                red[index] |= 1 << bit
    return bytes(black), bytes(red)


def rle_compress(data: bytes, max_literal_size: int = 128) -> bytes:
    result = bytearray()
    index = 0
    while index < len(data):
        run = 1
        while index + run < len(data) and run < 130 and data[index + run] == data[index]:
            run += 1
        if run >= 3:
            result.extend((0x80 | (run - 3), data[index]))
            index += run
            continue

        start = index
        literal = 0
        while index < len(data) and literal < max_literal_size:
            if index + 2 < len(data) and data[index] == data[index + 1] == data[index + 2]:
                break
            literal += 1
            index += 1
        result.append(literal - 1)
        result.extend(data[start : start + literal])
    return bytes(result)


def rle_compress_chunks(data: bytes, max_chunk_size: int) -> list[bytes]:
    if max_chunk_size < 2:
        raise ValueError("RLE 数据块至少需要 2 字节")
    encoded = rle_compress(data, min(max_chunk_size - 1, 128))
    chunks: list[bytes] = []
    start = 0
    index = 0
    while index < len(encoded):
        control = encoded[index]
        code_length = 2 if control & 0x80 else control + 2
        if index - start + code_length > max_chunk_size and index > start:
            chunks.append(encoded[start:index])
            start = index
        index += code_length
    if index > start:
        chunks.append(encoded[start:index])
    return chunks


async def scan_devices(timeout_seconds: float = 8.0) -> list[tuple[str, str]]:
    try:
        from bleak import BleakScanner
    except ImportError as exc:
        raise EPDConnectionError("未安装 bleak，无法扫描 BLE") from exc
    devices = await BleakScanner.discover(timeout=timeout_seconds)
    return sorted(((item.address, item.name or "<未命名>") for item in devices), key=lambda item: item[1])
