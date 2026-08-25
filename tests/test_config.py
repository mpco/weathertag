from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from weathertag.config import ConfigError, load_config


class ConfigTest(unittest.TestCase):
    def test_relative_paths_and_secret_environment_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_file = root / "config.toml"
            config_file.write_text(
                """
[qweather]
api_host = "https://example.qweatherapi.com/"
project_id = "project"
credential_id = "credential"
private_key_path = "secret.pem"
longitude = 116.41
latitude = 39.92
[ble]
enabled = false
""",
                encoding="utf-8",
            )
            config = load_config(config_file, {"WEATHERTAG_BLE_ENABLED": "true", "WEATHERTAG_BLE_NAME": "EPD"})
            self.assertEqual(config.qweather.api_host, "example.qweatherapi.com")
            self.assertEqual(config.qweather.private_key_path, root / "secret.pem")
            self.assertTrue(config.ble.enabled)
            config.validate()

    def test_ble_identity_is_required_when_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "empty.toml"
            path.write_text("[ble]\nenabled=true\n", encoding="utf-8")
            config = load_config(path)
            with self.assertRaises(ConfigError):
                config.validate(require_weather=False)


if __name__ == "__main__":
    unittest.main()
