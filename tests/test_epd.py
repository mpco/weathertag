from __future__ import annotations

import unittest

from PIL import Image

from weathertag.config import BleConfig
from weathertag.epd import (
    BleEPDDisplay,
    TransferCapabilities,
    encode_three_color,
    rle_compress,
    rle_compress_chunks,
)


def decompress(encoded: bytes) -> bytes:
    result = bytearray()
    index = 0
    while index < len(encoded):
        control = encoded[index]
        index += 1
        if control & 0x80:
            result.extend((encoded[index],) * ((control & 0x7F) + 3))
            index += 1
        else:
            length = control + 1
            result.extend(encoded[index : index + length])
            index += length
    return bytes(result)


class EPDEncodingTest(unittest.TestCase):
    def test_planes_match_reference_polarity(self) -> None:
        image = Image.new("RGB", (400, 300), "white")
        image.putpixel((0, 0), (0, 0, 0))
        image.putpixel((1, 0), (220, 0, 0))
        black, red = encode_three_color(image)
        self.assertEqual(len(black), 15_000)
        self.assertEqual(len(red), 15_000)
        self.assertEqual(black[0], 0b00111111)
        self.assertEqual(red[0], 0b10111111)

    def test_rle_round_trip_and_chunk_boundaries(self) -> None:
        raw = bytes([255] * 300 + list(range(128)) + [0] * 512)
        self.assertEqual(decompress(rle_compress(raw)), raw)
        chunks = rle_compress_chunks(raw, 18)
        self.assertTrue(all(len(chunk) <= 18 for chunk in chunks))
        self.assertEqual(b"".join(decompress(chunk) for chunk in chunks), raw)


class EPDProtocolTest(unittest.IsolatedAsyncioTestCase):
    async def test_image_command_flags_and_ack_interleave(self) -> None:
        writes = []

        async def writer(characteristic, payload, *, response):
            writes.append((characteristic, payload, response))

        display = BleEPDDisplay(BleConfig(write_ack_interval=2))
        capabilities = TransferCapabilities(max_write_length=8, rle=False)
        await display._write_plane(writer, bytes(range(13)), black_plane=True, capabilities=capabilities)
        self.assertEqual([item[1][0] for item in writes], [0x30, 0x30, 0x30])
        self.assertEqual(writes[0][1][1], 0x02)  # black plane + begin
        self.assertEqual(writes[1][1][1], 0x00)
        self.assertEqual([item[2] for item in writes], [False, True, True])

        writes.clear()
        await display._write_plane(writer, b"abc", black_plane=False, capabilities=capabilities)
        self.assertEqual(writes[0][1][1], 0x03)  # red plane + begin


if __name__ == "__main__":
    unittest.main()
