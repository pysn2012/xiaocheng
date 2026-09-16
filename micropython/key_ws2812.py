# -*- coding: utf-8 -*-
"""
test_key_led.py — 6 按键切换 WS2812 灯光效果
========================================================================
按键映射（按下即切换效果）：
  A      -> 彩虹循环
  B      -> 呼吸灯（洋红）
  UP     -> 追逐效果（黄）
  DOWN   -> 随机闪烁
  LEFT   -> 剧院追逐（绿）
  RIGHT  -> 逐个点亮（青）
"""

from machine import I2C, Pin
import time
import random
import neopixel

from xl9535 import XL9535, MatrixKeys, I2C1_SCL, I2C1_SDA

# ---------- 常量 ----------
WS2812_PIN = 42
NUM_LEDS = 10

# 颜色表
BLACK   = (0, 0, 0)
RED     = (255, 0, 0)
GREEN   = (0, 255, 0)
BLUE    = (0, 0, 255)
YELLOW  = (255, 255, 0)
CYAN    = (0, 255, 255)
MAGENTA = (255, 0, 255)
WHITE   = (255, 255, 255)

# 按键 -> 效果名称
KEY_EFFECT_MAP = {
    'A':      'rainbow',
    'B':      'breathe',
    'UP':     'chase',
    'DOWN':   'sparkle',
    'LEFT':   'theater',
    'RIGHT':  'wipe',
}


# ---------- 工具函数 ----------
def wheel(pos):
    """彩虹色轮 0-255 -> (R, G, B)"""
    if pos < 85:
        return (pos * 3, 255 - pos * 3, 0)
    elif pos < 170:
        pos -= 85
        return (255 - pos * 3, 0, pos * 3)
    else:
        pos -= 170
        return (0, pos * 3, 255 - pos * 3)


# ---------- WS2812 效果管理器（非阻塞） ----------
class Effects:
    def __init__(self, pin, num):
        self.np = neopixel.NeoPixel(Pin(pin), num)
        self.num = num
        self.mode = 'off'      # 当前效果名
        self.tick = 0          # 主循环计数（每 5ms +1）
        self.clear()

    def clear(self):
        self.np.fill(BLACK)
        self.np.write()

    def set_mode(self, mode):
        """切换效果，重置内部状态"""
        if self.mode != mode:
            self.mode = mode
            self.tick = 0
            self.clear()
            print(f"  => 切换到效果: {mode}")

    def update(self):
        """每 5ms 由主循环调用一次，推进一帧动画"""
        self.tick += 1
        if self.mode == 'rainbow':
            self._rainbow()
        elif self.mode == 'breathe':
            self._breathe()
        elif self.mode == 'chase':
            self._chase()
        elif self.mode == 'sparkle':
            self._sparkle()
        elif self.mode == 'theater':
            self._theater()
        elif self.mode == 'wipe':
            self._wipe()
        # 'off' 时什么都不做

    # ---- 各效果的单帧更新（通过 tick 控制速度）----
    def _rainbow(self):
        if self.tick % 6 != 0:          # 30 ms 一帧
            return
        j = (self.tick // 6) % 256
        for i in range(self.num):
            pixel_index = (i * 256 // self.num) + j
            self.np[i] = wheel(pixel_index & 255)
        self.np.write()

    def _breathe(self):
        if self.tick % 8 != 0:          # 40 ms 一帧
            return
        step = (self.tick // 8) % 100
        if step < 50:
            brightness = int(step / 50 * 255)
        else:
            brightness = int((100 - step) / 50 * 255)
        self.np.fill((MAGENTA[0] * brightness // 255,
                      MAGENTA[1] * brightness // 255,
                      MAGENTA[2] * brightness // 255))
        self.np.write()

    def _chase(self):
        if self.tick % 20 != 0:         # 100 ms 一帧
            return
        idx = (self.tick // 20) % self.num
        self.np.fill(BLACK)
        self.np[idx] = YELLOW
        self.np.write()

    def _sparkle(self):
        if self.tick % 16 != 0:         # 80 ms 一帧
            return
        self.np.fill(BLACK)
        idx = random.randint(0, self.num - 1)
        self.np[idx] = (random.randint(0, 255),
                        random.randint(0, 255),
                        random.randint(0, 255))
        self.np.write()

    def _theater(self):
        if self.tick % 30 != 0:         # 150 ms 一帧
            return
        q = (self.tick // 30) % 3
        self.np.fill(BLACK)
        for i in range(q, self.num, 3):
            self.np[i] = GREEN
        self.np.write()

    def _wipe(self):
        if self.tick % 16 != 0:         # 80 ms 一帧
            return
        idx = (self.tick // 16) % (self.num + 1)
        self.np.fill(BLACK)
        for i in range(idx):
            self.np[i] = CYAN
        self.np.write()


# ---------- 主程序 ----------
def main():
    print("=" * 50)
    print("6 按键切换 WS2812 灯光效果")
    print("=" * 50)

    # I2C + XL9535
    i2c = I2C(1, scl=Pin(I2C1_SCL), sda=Pin(I2C1_SDA), freq=400000)
    xl = XL9535(i2c)

    # WS2812 效果器
    fx = Effects(WS2812_PIN, NUM_LEDS)

    # ---- 按键回调 ----
    def on_press(key):
        print(f"[按下] {key}")
        if key in KEY_EFFECT_MAP:
            fx.set_mode(KEY_EFFECT_MAP[key])

    def on_release(key):
        print(f"[释放] {key}")

    keys = MatrixKeys(xl, on_press=on_press, on_release=on_release)

    print("\n按键映射:")
    for k, v in KEY_EFFECT_MAP.items():
        print(f"  {k:6s} -> {v}")
    print("\nCtrl+C 停止\n")

    try:
        while True:
            keys.scan()      # 扫描按键（含消抖）
            fx.update()      # 推进一帧 WS2812 动画
            time.sleep_ms(5) # 主循环 5ms
    except KeyboardInterrupt:
        fx.clear()
        print("\n已停止，灯已熄灭")


if __name__ == "__main__":
    main()