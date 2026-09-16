import machine
import neopixel
import time
import random

# ========== 配置 ==========
PIN = 42          # GPIO42
NUM_LEDS = 10     # 10个灯

# 初始化NeoPixel
np = neopixel.NeoPixel(machine.Pin(PIN), NUM_LEDS)

# ========== 颜色定义 (R, G, B) ==========
BLACK  = (0, 0, 0)
RED    = (255, 0, 0)
GREEN  = (0, 255, 0)
BLUE   = (0, 0, 255)
YELLOW = (255, 255, 0)
CYAN   = (0, 255, 255)
MAGENTA= (255, 0, 255)
WHITE  = (255, 255, 255)

# ========== 基础函数 ==========
def clear():
    """全部熄灭"""
    np.fill(BLACK)
    np.write()

def solid(color, delay_ms=1000):
    """全亮某种颜色"""
    np.fill(color)
    np.write()
    time.sleep_ms(delay_ms)

def color_wipe(color, delay_ms=100):
    """逐个点亮"""
    for i in range(NUM_LEDS):
        np[i] = color
        np.write()
        time.sleep_ms(delay_ms)

def rainbow_cycle(delay_ms=50):
    """彩虹循环效果"""
    def wheel(pos):
        if pos < 85:
            return (pos * 3, 255 - pos * 3, 0)
        elif pos < 170:
            pos -= 85
            return (255 - pos * 3, 0, pos * 3)
        else:
            pos -= 170
            return (0, pos * 3, 255 - pos * 3)
    
    for j in range(256):
        for i in range(NUM_LEDS):
            pixel_index = (i * 256 // NUM_LEDS) + j
            np[i] = wheel(pixel_index & 255)
        np.write()
        time.sleep_ms(delay_ms)

def chase(color, delay_ms=100):
    """追逐效果（一个亮灯跑动）"""
    for i in range(NUM_LEDS * 3):
        clear()
        np[i % NUM_LEDS] = color
        np.write()
        time.sleep_ms(delay_ms)

def breathe(color, steps=50, delay_ms=30):
    """呼吸灯效果"""
    for i in range(steps):
        brightness = int((i / steps) * 255)
        np.fill((color[0] * brightness // 255,
                 color[1] * brightness // 255,
                 color[2] * brightness // 255))
        np.write()
        time.sleep_ms(delay_ms)
    for i in range(steps, 0, -1):
        brightness = int((i / steps) * 255)
        np.fill((color[0] * brightness // 255,
                 color[1] * brightness // 255,
                 color[2] * brightness // 255))
        np.write()
        time.sleep_ms(delay_ms)

def random_sparkle(delay_ms=100, count=50):
    """随机闪烁"""
    for _ in range(count):
        clear()
        idx = random.randint(0, NUM_LEDS - 1)
        np[idx] = (random.randint(0, 255),
                   random.randint(0, 255),
                   random.randint(0, 255))
        np.write()
        time.sleep_ms(delay_ms)

def theater_chase(color, delay_ms=100, cycles=10):
    """剧院追逐效果"""
    for _ in range(cycles):
        for q in range(3):
            clear()
            for i in range(0, NUM_LEDS, 3):
                if i + q < NUM_LEDS:
                    np[i + q] = color
            np.write()
            time.sleep_ms(delay_ms)

# ========== 主测试程序 ==========
def run_tests():
    print("=" * 40)
    print("WS2812 测试程序 - ESP32-S3 GPIO42")
    print("=" * 40)
    
    # 1. 全亮基础色测试
    print("[1/7] 基础颜色测试...")
    for color, name in [(RED, "红"), (GREEN, "绿"), (BLUE, "蓝"), (WHITE, "白")]:
        print(f"  -> {name}")
        solid(color, 800)
    
    # 2. 逐个点亮
    print("[2/7] 逐个点亮...")
    color_wipe(CYAN, 80)
    clear()
    time.sleep_ms(200)
    
    # 3. 追逐效果
    print("[3/7] 追逐效果...")
    chase(YELLOW, 120)
    clear()
    time.sleep_ms(200)
    
    # 4. 呼吸灯
    print("[4/7] 呼吸灯...")
    breathe(MAGENTA, 40, 40)
    clear()
    time.sleep_ms(200)
    
    # 5. 彩虹循环
    print("[5/7] 彩虹循环...")
    for _ in range(3):
        rainbow_cycle(30)
    clear()
    time.sleep_ms(200)
    
    # 6. 随机闪烁
    print("[6/7] 随机闪烁...")
    random_sparkle(80, 30)
    clear()
    time.sleep_ms(200)
    
    # 7. 剧院追逐
    print("[7/7] 剧院追逐...")
    theater_chase(GREEN, 150, 6)
    
    clear()
    print("测试完成！")

# ========== 运行 ==========
if __name__ == "__main__":
    clear()
    try:
        while True:
            run_tests()
            time.sleep(1)
    except KeyboardInterrupt:
        clear()
        print("程序已停止，灯已熄灭")