# WeatherTag

WeatherTag 是一个运行在 Linux 家庭服务器上的低功耗天气提醒服务。它获取和风天气数据，将预警、降雨、温度和三日趋势整理成 400×300 的黑白红三色界面，并通过 BLE 推送给运行 EPD-nRF5 固件的 4.2 寸电子价签。

## 已实现

- 和风天气 Ed25519 JWT 认证及专属 API Host；
- 实况、24 小时、3 日、分钟降水和新版天气预警 API；
- 预警、降雨、极端温度、跨日温度变化、紫外线和昼夜温差的多行提醒；
- 当前天气区的小型两小时降雨趋势图，以及昨日、今日、明日高低温变化对照；
- 400×300 Pillow 渲染、短时降水趋势和黑白红位面编码；
- 顶栏更新时间、电池图标与上次 BLE 连接读取的电压；
- EPD-nRF5 v1.6+ BLE 协议、MTU 协商、RLE 和分块确认；
- 10 分钟变化轮询，以及 30/60/30/120 分钟分时常规刷屏；
- API/BLE 重试、失败屏幕、Gotify 限频通知和无数据库状态持久化；
- 单次运行、常驻服务、BLE 扫描、离线示例及 systemd 单元。

## 快速开始

要求 Python 3.11+、Linux、BlueZ，以及一块已经刷入 EPD-nRF5 v1.6（应用版本 `0x16`）或更新固件的价签。

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/weathertag render-demo --scenario upcoming --output var/demo.png
cp config.example.toml config.toml
```

`config.example.toml` 使用 Sarasa UI SC Regular 和 Fusion Pixel 12px；首次运行前请按[部署手册中的字体下载命令](docs/部署与运行.md#下载界面字体)安装到项目内的 `var/fonts/`。

和风天气 JWT 使用 Ed25519 密钥。生成密钥并把公钥添加到和风控制台的 JWT 凭据中：

```bash
mkdir -p secrets
openssl genpkey -algorithm ED25519 -out secrets/ed25519-private.pem
openssl pkey -pubout -in secrets/ed25519-private.pem -out secrets/ed25519-public.pem
chmod 600 secrets/ed25519-private.pem
```

编辑 `config.toml`：填写专属 API Host、项目 ID、凭据 ID、经纬度和私钥路径。和风天气从 2026 年起逐步停用旧公共 API 域名，因此必须使用控制台“设置”中的专属 Host。分钟降水仅支持中国地区；没有分钟数据时，服务会用未来两小时的小时预报作保守兜底。

```bash
.venv/bin/weathertag validate-config --config config.toml
.venv/bin/weathertag run-once --config config.toml
```

BLE 默认为关闭，此时命令会生成 `var/latest.png`，不会连接硬件。真机联调：

```bash
.venv/bin/weathertag scan-ble
# 把设备地址或广播名称写入 [ble]，并设置 enabled = true
.venv/bin/weathertag run-once --config config.toml --force
```

固件必须已经正确配置 4.2 寸屏幕驱动和引脚；服务沿用设备已保存的驱动配置，不会远程改写它。目标协议来自 [EPD-nRF5](https://github.com/tsl0922/EPD-nRF5)，服务 UUID 为 `62750001-d828-918d-fb46-b6c11c675aec`。

`REFRESH` 的 GATT 写入确认只代表固件收到了命令，不保证屏幕已经完成物理刷新。WeatherTag 默认在发送刷新命令后继续保持 BLE 连接 25 秒，防止部分异步刷新固件在断连休眠时截断波形。可通过 `[ble] refresh_wait_seconds` 调整；三色屏不建议设为 `0`。

固件通知中的 `bat=2987` 会作为 `2.99V` 保存到运行状态，并在下一次屏幕刷新时显示。这样无需为读取电池额外建立 BLE 连接；首次运行尚无历史读数时显示 `--.--V`。

协议帧、黑白红位面、MTU/RLE 以及连接故障的分阶段排查方法，详见 [EPD-nRF5 蓝牙协议与排障说明](docs/EPD-nRF5蓝牙协议.md)。

## 手动微调界面

400×300 画布的字体大小、坐标、行距、分隔线、电池位置和红色强调开关，集中定义在 `weathertag/renderer.py` 顶部的 `LAYOUT = ScreenLayout(...)` 参数块。修改后先离线生成预览，不会连接或刷新价签：

```bash
.venv/bin/weathertag render-demo --scenario normal --output var/layout-preview.png
.venv/bin/weathertag render-demo --scenario night --output var/layout-night.png
.venv/bin/weathertag render-demo --scenario warning --output var/layout-warning.png
```

`text_stroke_width` 建议保持 `0`。电子价签最终使用 1-bit 位面，无法稳定表现半像素描边；设为 `1` 会明显挤压小字号笔画。界面最小字号为 12px，`small_font_path` 只用于这一尺寸的降水图时间标签；`use_current_accent` 可统一关闭或开启“当前”相关的红色装饰。

## 运行策略

服务默认每 10 分钟查询一次天气，以便发现预警、降雨、天气分类或至少 2℃ 的变化；只有发生这些重要变化，或到达当前时段的常规刷新间隔时才刷新墨水屏。所有阈值和间隔都能在配置中调整。

API 连续重试失败后，屏幕显示故障页并保留最后成功时间；同类 Gotify 通知默认 6 小时内只发一次。失败页每小时最多刷一次。成功恢复后，下次轮询会立即恢复天气界面。

## systemd 部署

完整的 LXC 部署流程详见 [WeatherTag 部署与运行手册](docs/部署与运行.md)，默认以容器内 `root` 运行，所有数据保留在 `/root/weathertag` 项目目录。内容包括：

- 挂载宿主机 BlueZ D-Bus socket；
- 设置 `DBUS_SYSTEM_BUS_ADDRESS=unix:path=/bt-dbus/system_bus_socket`；
- 在项目内管理 `.venv`、`config.toml`、`secrets/` 和 `var/`；
- 验证 API、BLE 扫描和真机刷新；
- 使用 systemd 常驻运行，以及升级、回滚、备份和排障；
- 需要更强进程隔离时，可选创建专用用户。

## 测试

```bash
.venv/bin/python -m unittest discover -v
```

测试不需要天气密钥或 BLE 硬件，覆盖提醒优先级、跨日温度变化、紫外线解析、状态持久化、渲染、三色位面、RLE 与故障限频路径。

## 数据与协议资料

- [和风天气 JWT 认证](https://dev.qweather.com/docs/configuration/authentication/)
- [和风天气专属 API Host](https://dev.qweather.com/docs/configuration/api-host/)
- [和风天气分钟级降水](https://dev.qweather.com/docs/api/minutely/minutely-precipitation/)
- [和风天气实时预警](https://dev.qweather.com/docs/api/warning/weather-alert/)
- [Gotify 推送消息](https://gotify.net/docs/pushmsg)
