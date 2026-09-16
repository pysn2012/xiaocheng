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

④ 按键

配置了6个功能按键，采用高阶矩阵扫描方案，仅通过 2 个原生 GPIO + 3 个 XL9535 扩展引脚，实现 2*3 按键矩阵（行输出、列输入）。

按键对应定义：

- A = GPIO0 × P0 ｜ RIGHT = GPIO0 × P4 ｜ UP = GPIO0 × P6
- DOWN = GPIO46 × P0 ｜ B = GPIO46 × P4 ｜ LEFT = GPIO46 × P6

PS：这套特殊的按键检测逻辑，耗费了我近两周时间才完整测出。

⑤其他实测引脚

- 光敏传感器：GPIO3（ADC）
- 10个WS2812灯：GPIO42

- 外接接线端子：PORT1=4，PORT2=5，PORT3=8，PORT4=9
- PORT5(UART)：TX=43  RX=44
- PORT6(I2C0)：SCL=1  SDA=6
- M1(电机)：GPIO2/38
- M2(电机)：GPIO40/41
