# 小程 ESP32S3 掌机

搭载 ESP32-S3（N16R8，8M PSRAM + 16M Flash）主控，自带外壳、电池、2 寸 ST7789 彩屏、6 个实体按键，同时集成麦克风、功放、喇叭、三轴传感器、光线传感器，整体配置相比小喵掌机强上不少。

| 项目 | 规格 |
|---|---|
| 主控 | ESP32-S3，240MHz，16MB Flash + 8MB Octal PSRAM |
| IO 扩展 | XL9535，I2C 地址 0x20，16 路 |
| 屏幕 | 2.0" ST7789，320×240，SPI |
| 音频 | ES7210（MIC ADC）+ ES8311（DAC）+ NS4152（D 类功放） |
| 按键 | 2×3 矩阵 = 2 路原生 GPIO + 3 路 IO 扩展（行输出 / 列输入） |
| 灯光 | WS2812 ×10 + 绿色 / 蓝色状态 LED |
| 传感器 | 光敏、电池电压（ADC 采样） |

> 下面的硬件说明对各项目通用（MicroPython、ESPHome、Arduino 等），按模块查询即可；**全量引脚映射见 [`docs/pinout.md`](docs/pinout.md)**。ESPHome 语音助手的配置说明见文末。

---

## ① IO 扩展：XL9535

ESP32-S3 原生 GPIO 数量有限，设备用 XL9535 做 IO 扩展（I2C 地址 0x20，16 路）。

XL9535 与 PCA9555 寄存器兼容。引脚有两套记法，本 README 统一使用：

| 记法 | 范围 | 来源 |
|---|---|---|
| 端口.位 | P0.0 ~ P0.7、P1.0 ~ P1.7 | 芯片手册 |
| ESPHome number | 0 ~ 17（P0 组 0~7，P1 组 10~17） | ESPHome `xl9535` 组件编号 |

对照表（P1 组不是 8~15，配 ESPHome 时注意）：

| 端口.位 | ESPHome | 端口.位 | ESPHome |
|---|---|---|---|
| P0.0 | 0 | P1.0 | 10 |
| P0.1 | 1 | P1.1 | 11 |
| P0.2 | 2 | P1.2 | 12 |
| P0.3 | 3 | P1.3 | 13 |
| P0.4 | 4 | P1.4 | 14 |
| P0.5 | 5 | P1.5 | 15 |
| P0.6 | 6 | P1.6 | 16 |
| P0.7 | 7 | P1.7 | 17 |

## ② 屏幕

搭载 2.0 寸 ST7789 驱动 LCD 彩屏，分辨率 320×240，屏幕清晰度比小喵 ESP32 掌机高一个档次。

| 信号 | 引脚 |
|---|---|
| SPI SCK | GPIO47 |
| SPI MOSI | GPIO45 |
| DC（数据/命令） | GPIO48 |
| CS（片选） | GPIO21 |
| BL（背光） | GPIO14（PWM 可调） |
| RST（复位） | XL9535 P1.2（ESPHome 编号 12） |

## ③ 音频

采用 ES7210 / ES8311 / NS4152 芯片组合，板载麦克风与喇叭，可以完美打造为小智、Home Assistant 语音助手等产品。

| 总线 / 引脚 | 说明 |
|---|---|
| I2C1：SCL=7、SDA=12 | 挂载 XL9535 / ES8311 / ES7210 |
| I2S0：MCLK=15、BCLK=16、WS=17 | 音频主时钟与位/帧时钟 |
| I2S0 DOUT=13 | ESP32 → ES8311 → 功放 → 喇叭 |
| I2S0 DIN=18 | 麦克风 → ES7210 → ESP32 |

| 芯片 | 角色 | I2C 地址 |
|---|---|---|
| ES7210 | 4 通道 ADC（麦克风输入） | 0x43（按小程实测跳线，非默认 0x40） |
| ES8311 | DAC（喇叭输出） | 0x18 |
| NS4152 | D 类功放 | 无地址，使能脚 = XL9535 P0.3 |

**电源与使能（都在 XL9535 上，上电顺序有讲究）**：

| 端口.位 | ESPHome | 作用 |
|---|---|---|
| P1.4 | 14 | 音频电源 |
| P0.7 | 7 | LDO 使能 |
| P0.3 | 3 | 功放 NS4152 使能 |

正确顺序是 **音频电源 / LDO 先接通 → codec 初始化 → 功放最后通电**。功放早通电会在开机时听到明显的 pop 声。

## ④ 按键

配置了 6 个功能按键，采用高阶矩阵扫描方案，仅通过 2 个原生 GPIO + 3 个 XL9535 扩展引脚，实现 2×3 按键矩阵（行输出、列输入）。

按键对应定义：

- A = GPIO0 × P0.0 ｜ RIGHT = GPIO0 × P0.4 ｜ UP = GPIO0 × P0.6
- DOWN = GPIO46 × P0.0 ｜ B = GPIO46 × P0.4 ｜ LEFT = GPIO46 × P0.6

**两个关键硬件特性**（决定了驱动必须怎么写）：

1. **列线是悬空的**，既没有上拉也没有下拉。所以不能「把行拉低、读到低就算按下」—— 松手时列电平不确定，会被误判成按下；必须差分扫描：行拉低读一次、行拉高读一次，取 `low ^ high`。
2. **行线平时保持高阻输入**，只在扫描那一瞬间切成输出。否则同时按下同一列的两个键时，两个强驱动会互相打架。

PS：这套特殊的按键检测逻辑，耗费了我近两周时间才完整测出。

## ⑤ 其他引脚

- 光敏传感器：GPIO3（ADC）
- 电池电压：GPIO10（ADC）采样，XL9535 的 P0.5 高电平使能，**采样值 ×2 = 电池电压**
- 10 个 WS2812 灯：GPIO42
- 绿色 LED：XL9535 P1.6 ｜ 蓝色 LED：XL9535 P1.7

## ⑥ 外接接口

- 外接接线端子：PORT1=4，PORT2=5，PORT3=8，PORT4=9
- PORT5（UART）：TX=43、RX=44
- PORT6（I2C0）：SCL=1、SDA=6
- M1（电机）：GPIO2 / 38
- M2（电机）：GPIO40 / 41

---

## ESPHome 语音助手固件

`xiaocheng-va/` 是基于 ESPHome 的语音助手配置，可按需裁剪或改造。

### 目录结构

```
xiaocheng-va/
├── xiaocheng-va.yaml          # 主配置：substitutions / 芯片 / WiFi / API / OTA / includes
├── display_helpers.h          # 屏幕绘制辅助：电池角标、文本换行、描边框、问候语表
├── key_scan.h                 # 键盘矩阵差分扫描（xiaocheng::key_scan_row）
├── secrets.yaml               # wifi_ssid / wifi_password（本地自建，不入库）
├── casita/                    # 320×240 全屏状态图（idle / listening / thinking / replying / …）
├── fonts/                     # materialdesignicons 图标字体
└── packages/
    ├── hardware.yaml          # 总线 / 屏幕 / 灯光 / 按键 / 音频编解码器
    ├── time.yaml              # Home Assistant 时间（时区 Asia/Shanghai）
    ├── fonts.yaml             # 字体（Noto Sans SC 联网拉取 + 本地 MDI）
    ├── sensor.yaml            # 电池 / 光敏 / WiFi RSSI / 对话文本
    ├── script.yaml            # 页面调度 / 键盘扫描 / 灯效 / 定时器
    └── voice-assistant.yaml   # 麦克风 / 喇叭 / microWakeWord / voice_assistant
```

### 功能

- 唤醒词 **Okay Nabu**，唤醒后语音对话、语音控制 Home Assistant；唤醒词可切换「设备端（microWakeWord）」或「HA 端」
- 屏幕状态页：开机加载 → 待机（日期星期 + 大时钟 + 时段问候语）→ 聆听 / 思考 / 回复，回复页显示问题与回答文字
- 右上角常驻三个小图标：电池电量（含电压）、WiFi、HA 连接状态
- WS2812 随语音阶段变色：聆听白呼吸、思考蓝扫描、回复橙闪烁，回空闲熄灭
- 联网指示：未联网蓝灯闪，联网成功蓝灯灭、绿灯常亮

### 按键功能

| 键 | 功能 |
|---|---|
| A | 息屏 / 亮屏 toggle（背光 `light.toggle`，300ms 渐变） |
| B | 静音开关（关闭麦克风收音） |
| UP / DOWN | 音量 + / −（步进 0.02） |
| RIGHT | 切下一句问候语（空闲页） |
| LEFT | 关 WS2812 环境灯 |

息屏后要亮屏有两条路：**按 A**，或**直接喊唤醒词**。

### 编译与烧录

**CI（推荐）**：仓库根目录的 `build-esphome.yml` 是 GitHub Actions 工作流（`workflow_dispatch` 手动触发）。

- 流程：`pip install esphome==2026.9.0` → 动态生成 `secrets.yaml` → `esphome compile`
- 产物：`firmware.ota.bin`（OTA 升级用）、`firmware.factory.bin`（首次 USB 烧录用），打包为 artifact `xiaocheng-esphome-<sha>`
- 所需仓库 Secrets：`WIFI_SSID`、`WIFI_PASSWORD`

**本地**：

```bash
cd xiaocheng-va
esphome config xiaocheng-va.yaml    # 只做配置校验，需同目录有 secrets.yaml
esphome run xiaocheng-va.yaml       # 本地编译+烧录（会自动下载 ESP32 平台与 xtensa 工具链，首次较慢）
```



首次配网：设备会开热点 `xiaocheng-va-setup`（密码 `12345678`），连上后填 WiFi；或用 HA 的 ESPHome 集成通过 USB 直接配置。

### 几个必须知道的实现约定

| 事项 | 结论 |
|---|---|
| XL9535 编号 | 全部集中在主配置的 `substitutions`（`xl_pin_*`），改一处全局生效。注意 P1 组的 ESPHome 编号是 10~17，不是 8~15 |
| 键盘扫描 | 列线悬空 → 必须差分扫描（`low ^ high`）；行线平时高阻，扫描瞬间才切输出。见 `key_scan.h` |
| I2C 速率 | 必须 **400kHz**。默认 50kHz 太慢，键盘轮询会超时告警 |
| 上电时序 | 音频电源 / LDO 用 `restore_mode: ALWAYS_ON` 先接通；功放在 `on_boot`（priority 600）里延迟 1s 再开，消除开机 pop |
| 音量上限 | ES8311 音量寄存器 REG32 是线性 0~255：**0.75 = 0dB，1.0 = +32dB**。所以 `volume_max: 0.75`，给到 1.0 会「声音很大且噪声明显」 |
| 采样率 | 收发统一 16kHz（microWakeWord 锁死麦克风 16k，喇叭跟麦走），MCLK 恒 4.096MHz 不换频，避免阶段切换时 codec 重新同步产生哒声 |
| 收发半双工 | 播放前显式 `microphone.stop_capture`，播放期间独占总线，杜绝回环串进功放的电流声 |
| 屏幕文字 | 白底状态图上只描边框、**不填底色**，填色会把图片挡住 |
| WiFi | `power_save_mode: none`，语音设备必须关省电，否则 I2S 收音不稳 |
| 新增本地头文件 | ① 主配置 `esphome.includes` 要列出（该机制只拷贝列出的文件，否则编译报 `xxx.h: No such file or directory`）；② 顺手加进 `build-esphome.yml` 的 artifact 清单 |

### Home Assistant 侧要求

- HA 需配置 Assist 管道：语音转文字（STT）、文字转语音（TTS）、对话代理
- 若把唤醒词放到 HA 端，需安装对应唤醒词资源；设备端则用内置的 `okay_nabu` 模型
- 设备通过 ESPHome 原生 API 接入 HA，实体包括：LCD Backlight、Ambient Light、Mute、Amp Enable、Battery Voltage / Percent、Light Level、WiFi RSSI、Uptime、IP Address、Factory Reset
