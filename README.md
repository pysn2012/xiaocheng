小程ESP32S3掌机

搭载 ESP32-S3（N16R8，8M PSRAM + 16M Flash）主控，自带外壳、电池、2 寸 ST7789 彩屏、6 个实体按键，同时集成麦克风、功放、喇叭、三轴传感器、光线传感器，整体配置相比小喵掌机强上不少。

① IO扩展

ESP32S3原生GPIO不够，数量有限，设备采用 XL9535 进行 IO 扩展（I2C 地址 0x20，16 路，线性编号 0~15，`pin = port×8 + bit`）。

② 屏幕

搭载 2.0 寸 ST7789 驱动 LCD 彩屏，分辨率 320*240，屏幕清晰度比小喵ESP32掌机高一个档次。

引脚配置：

LCD（ST7789，SPI）：SCK=47、MOSI=45、DC=48、CS=21、BL=14

LCD_RST：XL9535 IO扩展的P10

③ 音频

采用 ES7210/ES8311/NS4152 音频芯片组合，板载麦克风与喇叭，可以完美打造为小智、Home Assistant 语音助手等产品。

引脚配置：

I2C1：SCL=7、SDA=12（挂载 XL9535 / ES8311 / ES7210）

I2S0：MCLK=15、BCLK=16、WS=17、DOUT=13（→喇叭）、DIN=18（←麦克风）

XL9535 扩展引脚：P3 功放使能、P7 LDO、P12 音频电源

音频芯片 I2C 地址：ES7210 = 0x43、ES8311 = 0x18

④ 按键

配置了6个功能按键，采用高阶矩阵扫描方案，仅通过 2 个原生 GPIO + 3 个 XL9535 扩展引脚，实现 2*3 按键矩阵（行输出、列输入）。

按键对应定义：

- A = GPIO0 × P0 ｜ RIGHT = GPIO0 × P4 ｜ UP = GPIO0 × P6
- DOWN = GPIO46 × P0 ｜ B = GPIO46 × P4 ｜ LEFT = GPIO46 × P6

PS：这套特殊的按键检测逻辑，耗费了我近两周时间才完整测出。

⑤ 其他实测引脚

- 光敏传感器：GPIO3（ADC）
- 10个WS2812灯：GPIO42
- 绿色LED：XL9535 的 P14 ｜ 蓝色LED：XL9535 的 P15
- 电池电压：GPIO10（ADC）采样，XL9535 的 P0.5 高电平使能，采样值 ×2 = 电池电压

⑥ 外接接口

- 外接接线端子：PORT1=4，PORT2=5，PORT3=8，PORT4=9
- PORT5(UART)：TX=43  RX=44
- PORT6(I2C0)：SCL=1  SDA=6
- M1(电机)：GPIO2/38
- M2(电机)：GPIO40/41

---

## 引脚总表

### 原生 GPIO（ESP32-S3）

| 功能 | GPIO | 备注 |
|---|---|---|
| LCD SPI 时钟 SCK | GPIO47 | |
| LCD SPI 数据 MOSI | GPIO45 | |
| LCD 数据/命令 DC | GPIO48 | |
| LCD 片选 CS | GPIO21 | |
| LCD 背光 BL | GPIO14 | PWM 可调 |
| I2C1 SCL | GPIO7 | XL9535 / ES8311 / ES7210 |
| I2C1 SDA | GPIO12 | |
| I2S0 MCLK | GPIO15 | 音频主时钟 |
| I2S0 BCLK | GPIO16 | |
| I2S0 WS(LRCLK) | GPIO17 | |
| I2S0 DOUT | GPIO13 | ES8311 → 功放 → 喇叭 |
| I2S0 DIN | GPIO18 | 麦克风 → ES7210 → ESP32 |
| 键盘矩阵行 A | GPIO0 | 行输出，扫描时拉低 |
| 键盘矩阵行 B | GPIO46 | 行输出，扫描时拉低 |
| 光敏传感器 | GPIO3 | ADC |
| 电池电压采样 | GPIO10 | ADC，×2 = 电压，P0.5 使能 |
| WS2812 灯带（10 颗） | GPIO42 | GRB 顺序 |
| 外接 PORT1~4 | GPIO4 / 5 / 8 / 9 | |
| PORT5 UART | GPIO43(TX) / 44(RX) | |
| PORT6 I2C0 | GPIO1(SCL) / 6(SDA) | |
| M1 电机 | GPIO2 / 38 | |
| M2 电机 | GPIO40 / 41 | |

### XL9535 IO 扩展（I2C 地址 0x20）

| 线性编号 | 端口.位 | 功能 | ESPHome 编号* |
|---|---|---|---|
| P0 | P0.0 | 键盘列 1（A / DOWN） | 0 |
| P3 | P0.3 | 功放（NS4152）使能 | 3 |
| P4 | P0.4 | 键盘列 2（RIGHT / B） | 4 |
| P5 | P0.5 | 电池 ADC 采样使能（高有效） | 5 |
| P6 | P0.6 | 键盘列 3（UP / LEFT） | 6 |
| P7 | P0.7 | LDO 使能 | 7 |
| P10 | P1.2 | LCD 复位（LCD_RST） | 12 |
| P12 | P1.4 | 音频电源 | 14 |
| P14 | P1.6 | 绿色 LED | 16 |
| P15 | P1.7 | 蓝色 LED | 17 |

\* ESPHome 的 `xl9535` 组件编号规则：P0 组 = 0~7，P1 组 = 10~17，比线性编号（`port×8+bit`）在 P1 组大 2。

### 按键矩阵（2×3，行输出 / 列输入）

| 按键 | 行（GPIO） | 列（XL9535） |
|---|---|---|
| A | GPIO0 | P0 |
| RIGHT | GPIO0 | P4 |
| UP | GPIO0 | P6 |
| DOWN | GPIO46 | P0 |
| B | GPIO46 | P4 |
| LEFT | GPIO46 | P6 |

### 音频芯片

| 芯片 | 角色 | I2C 地址 | 控制总线 |
|---|---|---|---|
| ES7210 | 4 通道 ADC（麦克风输入） | 0x43 | I2C1 |
| ES8311 | DAC（喇叭输出） | 0x18 | I2C1 |
| NS4152 | D 类功放 | — | 使能脚 P3 |

---

## ESPHome 语音助手固件

本仓库 `xiaocheng-va/` 目录为基于 ESPHome 的语音助手配置（模块化：hardware / time / fonts / sensor / script / voice-assistant），功能：

- 唤醒词 "Okay Nabu"，语音对话 / 语音控制 Home Assistant
- 屏幕右上角实时显示电池电压与电量
- A 键关灯，其余 5 键切换 5 种 WS2812 灯效
- 联网前蓝灯闪烁，联网成功蓝灯灭、绿灯常亮

编译：GitHub Actions（`.github/workflows/build-esphome.yml`）手动触发，产物为 OTA / Factory 两个 bin，依赖仓库 Secrets：`WIFI_SSID`、`WIFI_PASSWORD`。
