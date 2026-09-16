# -*- coding: utf-8 -*-
"""
xl9535.py — H1 开发板(ESP32-S3 N16R8) 板级支持单文件
=====================================================
一个文件搞定三件事，其他代码只需 `from xl9535 import ...`：

  1. XL9535 引脚定义（统一线性编号 pin = port*8 + bit，见 XP()）
  2. XL9535 完整驱动（影子寄存器、端口级读写、极性反转）
  3. MatrixKeys —— 2x3 矩阵键盘扫描（含 RC 充放电修复）
  4. 音频电源域上电/下电 —— audio_power_up() / audio_power_down()

引脚编号约定（唯一标准）：
  - ESP32-S3 原生引脚：直接用 GPIO 编号
  - XL9535 扩展引脚：线性编号 0~15，用 XP(port, bit) 从原理图 P0x/P1x 换算，
    例如原理图标 P14 -> AUDIO_PWR = XP(1, 4) -> 12
"""

from machine import Pin
from micropython import const
import time

# ==================================================================
# 1. 引脚 / 地址定义
# ==================================================================

def XP(port, bit):
    """XL9535 引脚换算：XP(1, 4) 表示原理图上的 P14，返回线性编号 12。"""
    assert 0 <= port <= 1 and 0 <= bit <= 7, "XL9535 只有 P0.0~P1.7"
    return port * 8 + bit


# ---- I2C1 总线（挂 XL9535 / ES8311 / ES7210）----
I2C1_SCL = 7
I2C1_SDA = 12

# ---- I2S0（ES8311 播放 / ES7210 录音）----
I2S_MCLK = 15
I2S_BCLK = 16
I2S_WS   = 17
I2S_DOUT = 13          # ESP32 -> ES8311（喇叭）
I2S_DIN  = 18          # ES7210 -> ESP32（麦克风）

# ---- I2C 设备地址 ----
XL9535_ADDR = 0x20
ES8311_ADDR = 0x18
ES7210_ADDR = 0x43

# ---- XL9535 引脚（线性编号，经 XP() 定义）----
# P0 端口
KEY_COL0  = XP(0, 0)   # pin0   键盘列 0
AMP_EN    = XP(0, 3)   # pin3   功放使能
KEY_COL1  = XP(0, 4)   # pin4   键盘列 1
KEY_COL2  = XP(0, 6)   # pin6   键盘列 2
LDO_EN    = XP(0, 7)   # pin7   LDO 使能
# P1 端口
LCD_RST   = XP(1, 2)   # pin10  LCD 复位
AUDIO_PWR = XP(1, 4)   # pin12  音频电源域使能
LED_BLUE  = XP(1, 7)   # pin15  蓝灯
LED_GREEN = XP(1, 6)   # pin14  绿灯

# ---- 2x3 矩阵键盘 ----
KEY_ROW0 = 0           # 行 0（原生 GPIO）
KEY_ROW1 = 46          # 行 1（原生 GPIO）
KEY_ROWS = (KEY_ROW0, KEY_ROW1)
KEY_COLS = (KEY_COL0, KEY_COL1, KEY_COL2)
KEY_MAP = {            # (行GPIO, 列XL9535线性编号) -> 键名
    (KEY_ROW0, KEY_COL0): 'A',
    (KEY_ROW0, KEY_COL1): 'RIGHT',
    (KEY_ROW0, KEY_COL2): 'UP',
    (KEY_ROW1, KEY_COL0): 'DOWN',
    (KEY_ROW1, KEY_COL1): 'B',
    (KEY_ROW1, KEY_COL2): 'LEFT',
}


# ==================================================================
# 2. XL9535 驱动
# ==================================================================

_REG_INPUT0  = const(0x00)
_REG_INPUT1  = const(0x01)
_REG_OUTPUT0 = const(0x02)
_REG_OUTPUT1 = const(0x03)
_REG_POL0    = const(0x04)   # 输入极性反转，1=反转
_REG_POL1    = const(0x05)
_REG_CONFIG0 = const(0x06)   # 方向，1=输入(默认)，0=输出
_REG_CONFIG1 = const(0x07)


class XL9535:
    IN  = 1
    OUT = 0

    def __init__(self, i2c, addr=XL9535_ADDR):
        self._i2c = i2c
        self._addr = addr
        self._b1 = bytearray(1)
        # 影子寄存器：上电回读一次，之后改影子再写芯片，避免读-改-写冲突
        self._out = [self._read_reg(_REG_OUTPUT0), self._read_reg(_REG_OUTPUT1)]
        self._cfg = [self._read_reg(_REG_CONFIG0), self._read_reg(_REG_CONFIG1)]

    # ---- 底层 ----
    def _read_reg(self, reg):
        self._i2c.readfrom_mem_into(self._addr, reg, self._b1)
        return self._b1[0]

    def _write_reg(self, reg, val):
        self._b1[0] = val & 0xFF
        self._i2c.writeto_mem(self._addr, reg, self._b1)

    @staticmethod
    def _pb(pin):
        if not 0 <= pin <= 15:
            raise ValueError("XL9535 引脚范围 0~15, 收到 %r" % pin)
        return (0, pin) if pin < 8 else (1, pin - 8)

    # ---- 引脚级 ----
    def pin_mode(self, pin, mode):
        """mode = XL9535.IN(1) 输入 / XL9535.OUT(0) 输出"""
        port, bit = self._pb(pin)
        if mode:
            self._cfg[port] |= (1 << bit)
        else:
            self._cfg[port] &= ~(1 << bit)
        self._write_reg(_REG_CONFIG0 + port, self._cfg[port])

    def write(self, pin, val):
        port, bit = self._pb(pin)
        if val:
            self._out[port] |= (1 << bit)
        else:
            self._out[port] &= ~(1 << bit)
        self._write_reg(_REG_OUTPUT0 + port, self._out[port])

    def read(self, pin):
        port, bit = self._pb(pin)
        return (self._read_reg(_REG_INPUT0 + port) >> bit) & 1

    def toggle(self, pin):
        port, bit = self._pb(pin)
        self._out[port] ^= (1 << bit)
        self._write_reg(_REG_OUTPUT0 + port, self._out[port])

    def output(self, pin, val):
        """一步到位：设为输出并写电平（最常用）"""
        self.pin_mode(pin, self.OUT)
        self.write(pin, val)

    def set_polarity(self, pin, invert):
        port, bit = self._pb(pin)
        reg = _REG_POL0 + port
        cur = self._read_reg(reg)
        cur = (cur | (1 << bit)) if invert else (cur & ~(1 << bit))
        self._write_reg(reg, cur)

    # ---- 端口级 ----
    def read_port(self, port):
        return self._read_reg(_REG_INPUT0 + port)

    def write_port(self, port, val):
        self._out[port] = val & 0xFF
        self._write_reg(_REG_OUTPUT0 + port, self._out[port])

    def config_port(self, port, val):
        self._cfg[port] = val & 0xFF
        self._write_reg(_REG_CONFIG0 + port, self._cfg[port])

    # ---- 诊断 ----
    def dump(self):
        regs = [self._read_reg(i) for i in range(8)]
        names = ("INPUT0", "INPUT1", "OUTPUT0", "OUTPUT1",
                 "POL0", "POL1", "CONFIG0", "CONFIG1")
        for n, v in zip(names, regs):
            print("  %-8s 0x%02X  %s" % (n, v, format(v, "08b")))
        return regs


# ==================================================================
# 3. 2x3 矩阵键盘（含 RC 充放电修复）
# ==================================================================

class MatrixKeys:
    """
    2x3 矩阵键盘：
      行 = 原生 GPIO0 / GPIO46（推挽输出）
      列 = XL9535 pin0 / pin4 / pin6
    修复要点：读列前先强制放电，非扫描行保持低电平防串扰。
    """

    DEBOUNCE_MS = 50
    REPEAT_MS = 200
    DISCHARGE_MS = 10
    CHARGE_MS = 2

    def __init__(self, xl, on_press=None, on_release=None, on_repeat=None):
        self.xl = xl
        self.on_press = on_press
        self.on_release = on_release
        self.on_repeat = on_repeat

        self._row_pins = []
        for r in KEY_ROWS:
            p = Pin(r, Pin.OUT)
            p.value(0)
            self._row_pins.append(p)

        for c in KEY_COLS:
            self.xl.pin_mode(c, XL9535.IN)

        self._state = {name: False for name in KEY_MAP.values()}
        self._last = {name: 0 for name in KEY_MAP.values()}

    def _discharge(self, col):
        self.xl.pin_mode(col, XL9535.OUT)
        self.xl.write(col, 0)
        time.sleep_ms(self.DISCHARGE_MS)
        self.xl.pin_mode(col, XL9535.IN)
        time.sleep_us(200)

    def _update(self, name, pressed, now, events):
        prev = self._state[name]
        if pressed and not prev:
            if time.ticks_diff(now, self._last[name]) > self.DEBOUNCE_MS:
                self._state[name] = True
                self._last[name] = now
                events.append(('PRESS', name))
                if self.on_press:
                    self.on_press(name)
        elif pressed and prev:
            if time.ticks_diff(now, self._last[name]) > self.REPEAT_MS:
                self._last[name] = now
                events.append(('REPEAT', name))
                if self.on_repeat:
                    self.on_repeat(name)
        elif not pressed and prev:
            self._state[name] = False
            events.append(('RELEASE', name))
            if self.on_release:
                self.on_release(name)

    def scan(self):
        """扫一轮，返回事件列表 [('PRESS'|'RELEASE'|'REPEAT', 键名), ...]"""
        events = []
        now = time.ticks_ms()
        for col in KEY_COLS:
            for row_idx, row_gpio in enumerate(KEY_ROWS):
                self._discharge(col)
                self._row_pins[row_idx].value(1)
                time.sleep_ms(self.CHARGE_MS)
                pressed = (self.xl.read(col) == 1)
                self._row_pins[row_idx].value(0)
                key = (row_gpio, col)
                if key in KEY_MAP:
                    self._update(KEY_MAP[key], pressed, now, events)
            self._discharge(col)
        return events

    def get_pressed(self):
        """返回当前所有按住键的键名列表"""
        result = []
        for col in KEY_COLS:
            for row_idx, row_gpio in enumerate(KEY_ROWS):
                self._discharge(col)
                self._row_pins[row_idx].value(1)
                time.sleep_ms(self.CHARGE_MS)
                if self.xl.read(col) == 1:
                    name = KEY_MAP.get((row_gpio, col))
                    if name:
                        result.append(name)
                self._row_pins[row_idx].value(0)
        return result


# ==================================================================
# 4. 音频板级支持（上电时序）
# ==================================================================

def audio_power_up(xl):
    """音频域上电（电源域 + LDO）。功放(AMP_EN)由播放端按需用 xl.output() 控制。"""
    xl.output(AUDIO_PWR, 1)
    xl.output(LDO_EN, 1)
    time.sleep_ms(120)


def audio_power_down(xl):
    """音频域下电（电源 + LDO + 功放全关）。"""
    xl.output(AUDIO_PWR, 0)
    xl.output(LDO_EN, 0)
    xl.output(AMP_EN, 0)

