# WeatherTag

WeatherTag 是一个运行在 Linux 家庭服务器上的低功耗天气提醒服务。它获取和风天气数据，将预警、降雨、温度和三日趋势整理成 400×300 的黑白红三色界面，并通过 BLE 推送给运行 EPD-nRF5 固件的 4.2 寸电子价签。

## 已实现

- 和风天气 Ed25519 JWT 认证及专属 API Host；
- 实况、24 小时、3 日、分钟降水和新版天气预警 API；
- 预警 → 当前降雨 → 即将降雨 → 极端温度 → 温差 → 普通天气的单条提醒规则；
- 400×300 Pillow 渲染、短时降水趋势和黑白红位面编码；
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

## 运行策略

服务默认每 10 分钟查询一次天气，以便发现预警、降雨、天气分类或至少 2℃ 的变化；只有发生这些重要变化，或到达当前时段的常规刷新间隔时才刷新墨水屏。所有阈值和间隔都能在配置中调整。

API 连续重试失败后，屏幕显示故障页并保留最后成功时间；同类 Gotify 通知默认 6 小时内只发一次。失败页每小时最多刷一次。成功恢复后，下次轮询会立即恢复天气界面。

## systemd 部署

建议把项目放在 `/opt/weathertag`，配置和私钥放在 `/etc/weathertag`，运行状态放在 `/var/lib/weathertag`。生产配置中的 `state_path` 与 `output_path` 应改为绝对路径：

```toml
[app]
state_path = "/var/lib/weathertag/state.json"
output_path = "/var/lib/weathertag/latest.png"
```

创建不可登录的 `weathertag` 用户，确保其能读取私钥并能通过系统 BlueZ 访问蓝牙，然后安装单元：

```bash
sudo cp deploy/weathertag.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now weathertag
sudo systemctl status weathertag
journalctl -u weathertag -f
```

不同发行版的 BlueZ D-Bus 权限策略不同；如出现 `org.bluez.Error.NotAuthorized`，应在系统策略中只授予 `weathertag` 用户 BLE 客户端权限。

## 测试

```bash
.venv/bin/python -m unittest discover -v
```

测试不需要天气密钥或 BLE 硬件，覆盖提醒优先级、变化触发、API 数据解析、渲染、三色位面、RLE、状态与故障限频路径。

## 数据与协议资料

- [和风天气 JWT 认证](https://dev.qweather.com/docs/configuration/authentication/)
- [和风天气专属 API Host](https://dev.qweather.com/docs/configuration/api-host/)
- [和风天气分钟级降水](https://dev.qweather.com/docs/api/minutely/minutely-precipitation/)
- [和风天气实时预警](https://dev.qweather.com/docs/api/warning/weather-alert/)
- [Gotify 推送消息](https://gotify.net/docs/pushmsg)
