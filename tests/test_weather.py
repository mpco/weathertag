from __future__ import annotations

import base64
import json
import unittest

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from weathertag.config import QWeatherConfig
from weathertag.weather import JWTProvider, QWeatherClient, WeatherAPIError, parse_snapshot

from .helpers import NOW


class WeatherParsingTest(unittest.TestCase):
    def test_parse_current_forecasts_minutely_and_new_warning_api(self) -> None:
        current = {
            "code": "200",
            "updateTime": NOW.isoformat(),
            "now": {
                "obsTime": NOW.isoformat(), "temp": "28", "feelsLike": "30", "icon": "101",
                "text": "多云", "windDir": "东南风", "windScale": "3", "humidity": "60", "precip": "0.0",
            },
        }
        daily_item = {
            "fxDate": NOW.date().isoformat(), "tempMin": "24", "tempMax": "32", "iconDay": "101",
            "textDay": "多云", "windDirDay": "东南风", "windScaleDay": "3", "humidity": "60", "uvIndex": "7",
        }
        hourly_item = {
            "fxTime": NOW.isoformat(), "temp": "28", "icon": "101", "text": "多云",
            "pop": None, "precip": "0.0",
        }
        minute_item = {"fxTime": NOW.isoformat(), "precip": "0.1", "type": "rain"}
        warning = {
            "id": "w1", "messageType": {"code": "alert"}, "eventType": {"name": "大风"},
            "severity": "moderate", "effectiveTime": NOW.isoformat(), "headline": "大风蓝色预警",
        }
        result = parse_snapshot(
            current,
            {"daily": [daily_item] * 3},
            {"hourly": [hourly_item]},
            {"summary": "有雨", "minutely": [minute_item]},
            {"metadata": {"zeroResult": False}, "alerts": [warning]},
            fetched_at=NOW,
        )
        self.assertEqual(result.current.temperature, 28)
        self.assertEqual(len(result.daily), 3)
        self.assertEqual(result.daily[0].uv_index, 7)
        self.assertEqual(result.alerts[0].title, "大风")
        self.assertEqual(result.minutely[0].precipitation, 0.1)

    def test_missing_required_data_is_reported(self) -> None:
        with self.assertRaises(WeatherAPIError):
            parse_snapshot({}, {}, {}, {}, {}, fetched_at=NOW)

    def test_jwt_has_only_required_claims_and_valid_signature(self) -> None:
        key = Ed25519PrivateKey.generate()
        pem = key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode()
        config = QWeatherConfig(
            project_id="project-id",
            credential_id="credential-id",
            private_key_pem=pem,
        )
        token = JWTProvider(config, clock=lambda: 1_000).token()
        header_raw, payload_raw, signature_raw = token.split(".")
        header = json.loads(_decode(header_raw))
        payload = json.loads(_decode(payload_raw))
        self.assertEqual(header, {"alg": "EdDSA", "kid": "credential-id"})
        self.assertEqual(payload, {"sub": "project-id", "iat": 970, "exp": 2200})
        key.public_key().verify(_decode_bytes(signature_raw), f"{header_raw}.{payload_raw}".encode())


class QWeatherClientTest(unittest.IsolatedAsyncioTestCase):
    async def test_fetches_all_five_documented_endpoints(self) -> None:
        key = Ed25519PrivateKey.generate()
        pem = key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode()
        paths: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            paths.append(request.url.path)
            self.assertTrue(request.headers["Authorization"].startswith("Bearer "))
            base_item = {
                "fxDate": NOW.date().isoformat(), "tempMin": "24", "tempMax": "32", "iconDay": "101",
                "textDay": "多云", "windDirDay": "东南风", "windScaleDay": "3", "humidity": "60",
            }
            responses = {
                "/v7/weather/now": {"code": "200", "updateTime": NOW.isoformat(), "now": {
                    "obsTime": NOW.isoformat(), "temp": "28", "feelsLike": "30", "icon": "101",
                    "text": "多云", "windDir": "东南风", "windScale": "3", "humidity": "60", "precip": "0",
                }},
                "/v7/weather/3d": {"code": "200", "daily": [base_item] * 3},
                "/v7/weather/24h": {"code": "200", "hourly": []},
                "/v7/minutely/5m": {"code": "200", "minutely": [], "summary": "无降雨"},
                "/weatheralert/v1/current/39.92/116.41": {"metadata": {"zeroResult": True}, "alerts": []},
            }
            return httpx.Response(200, json=responses[request.url.path])

        config = QWeatherConfig(
            api_host="test.qweatherapi.com",
            project_id="project",
            credential_id="credential",
            private_key_pem=pem,
            longitude=116.41,
            latitude=39.92,
            retry_attempts=1,
        )
        async with QWeatherClient(config, transport=httpx.MockTransport(handler)) as client:
            result = await client.fetch(NOW)
        self.assertEqual(result.current.temperature, 28)
        self.assertCountEqual(paths, [
            "/v7/weather/now", "/v7/weather/3d", "/v7/weather/24h", "/v7/minutely/5m",
            "/weatheralert/v1/current/39.92/116.41",
        ])


def _decode(value: str) -> str:
    return _decode_bytes(value).decode()


def _decode_bytes(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


if __name__ == "__main__":
    unittest.main()
