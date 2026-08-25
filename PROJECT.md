---
name: WeatherTag
status: active
created: 2026-08-24
stack:
- Python
tags:
- cli
- service
---

# Purpose

把和风天气数据转换为适合门口快速查看的 400×300 黑白红三色界面，并通过 BLE 自动推送到运行 EPD-nRF5 固件的电子价签。

# Current State

完整 Python 服务已经实现：和风 JWT 接入、五类天气数据聚合、优先级提醒规则、Pillow 三色渲染、EPD-nRF5 v1.6+ BLE 传图、Gotify 异常通知、JSON 状态持久化、分时刷新和 systemd 部署文件。

# Next Step

复制 `config.example.toml`，填入实际和风天气凭据、坐标及电子价签地址，然后先执行 `weathertag run-once --force` 做真机联调。

# Notes

无硬件和密钥时可通过 `weathertag render-demo` 验证界面，通过单元测试验证核心逻辑。
