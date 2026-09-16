# -*- coding: utf-8 -*-
"""
snake.py — 掌机贪吃蛇
=====================
硬件：ESP32-S3 掌机（ST7789 2寸屏 320x240 横屏 + 2x3 矩阵键盘 + WS2812x10）
依赖：xl9535.py 需上传到设备根目录；st7789 驱动、neopixel 为固件内置。

按键：
  UP/DOWN/LEFT/RIGHT  转向
  A                   暂停 / 继续
  B                   游戏结束后重新开始

规则：撞墙或咬到自己结束；吃到食物 +1 分并变长，分数越高速度越快。
      WS2812 灯随分数逐颗点亮（10 颗封顶）。
"""

from machine import Pin, SPI, I2C
import st7789
import time
import random
import vga2_bold_16x32 as font
import neopixel

from xl9535 import XL9535, MatrixKeys, I2C1_SCL, I2C1_SDA, LCD_RST

# ---------- 引脚（与既有测试代码一致） ----------
SCK_PIN, MOSI_PIN, DC_PIN, CS_PIN, BL_PIN = 47, 45, 48, 21, 14
WS2812_PIN, NUM_LEDS = 42, 10

# ---------- 游戏参数 ----------
CELL = 10                     # 格子边长（像素）
COLS = 32                     # 320 / 10
ROWS = 21                     # (240 - TOP) / 10
TOP = 30                      # 顶部信息栏高度
MOVE_BASE = 3                 # 初始：每 3 次扫描走一步（扫描一轮约 75ms）

DIRS = {'UP': (-1, 0), 'DOWN': (1, 0), 'LEFT': (0, -1), 'RIGHT': (0, 1)}
OPPOSITE = {'UP': 'DOWN', 'DOWN': 'UP', 'LEFT': 'RIGHT', 'RIGHT': 'LEFT'}


def px(col):
    """列 -> 像素 x"""
    return col * CELL


def py(row):
    """行 -> 像素 y"""
    return TOP + row * CELL


# ==================================================================
# 硬件初始化
# ==================================================================

def init_hw():
    # 背光
    bl = Pin(BL_PIN, Pin.OUT)
    bl.value(1)
    time.sleep_ms(50)

    # I2C + XL9535
    i2c = I2C(1, scl=Pin(I2C1_SCL), sda=Pin(I2C1_SDA), freq=400000)
    xl = XL9535(i2c)

    # LCD 硬件复位（LCD_RST 在 XL9535 pin10，不能走 st7789 的 reset 参数）
    xl.output(LCD_RST, 1)
    time.sleep_ms(10)
    xl.write(LCD_RST, 0)
    time.sleep_ms(10)
    xl.write(LCD_RST, 1)
    time.sleep_ms(120)

    # SPI + ST7789 横屏
    spi = SPI(1, baudrate=40000000, polarity=0, phase=0,
              sck=Pin(SCK_PIN), mosi=Pin(MOSI_PIN))
    tft = st7789.ST7789(spi, 240, 320,
                        dc=Pin(DC_PIN, Pin.OUT),
                        cs=Pin(CS_PIN, Pin.OUT),
                        rotation=1)
    tft.init()

    keys = MatrixKeys(xl)

    np = neopixel.NeoPixel(Pin(WS2812_PIN), NUM_LEDS)
    np.fill((0, 0, 0))
    np.write()

    return tft, keys, np


# ==================================================================
# WS2812 计分灯
# ==================================================================

def leds_show_score(np, score):
    n = min(NUM_LEDS, score)
    for i in range(NUM_LEDS):
        np[i] = (0, 60, 0) if i < n else (0, 0, 0)
    np.write()


def leds_flash(np, color, times=3, ms=120):
    for _ in range(times):
        np.fill(color)
        np.write()
        time.sleep_ms(ms)
        np.fill((0, 0, 0))
        np.write()
        time.sleep_ms(ms)


# ==================================================================
# 绘制
# ==================================================================

def draw_cell(tft, cell, color):
    """画一格（9x9，留 1px 缝隙，蛇身有分段感）"""
    tft.fill_rect(px(cell[1]), py(cell[0]), CELL - 1, CELL - 1, color)


def erase_cell(tft, cell):
    """擦一格（整格涂黑）"""
    tft.fill_rect(px(cell[1]), py(cell[0]), CELL, CELL, st7789.BLACK)


def draw_score(tft, score):
    tft.fill_rect(0, 0, 320, TOP - 1, st7789.BLACK)
    tft.text(font, "SCORE:%d" % score, 8, 6, st7789.WHITE)
    tft.hline(0, TOP - 1, 320, st7789.BLUE)


def draw_screen(tft, snake, food, score):
    tft.fill(st7789.BLACK)
    draw_score(tft, score)
    for s in snake:
        draw_cell(tft, s, st7789.GREEN)
    draw_cell(tft, snake[0], st7789.YELLOW)
    draw_cell(tft, food, st7789.RED)


# ==================================================================
# 游戏逻辑
# ==================================================================

def place_food(snake):
    """在空白格随机放食物"""
    while True:
        f = (random.randrange(ROWS), random.randrange(COLS))
        if f not in snake:
            return f


def wait_press(keys, name):
    """阻塞等待按下指定键"""
    while True:
        for ev, key in keys.scan():
            if ev == 'PRESS' and key == name:
                return


def pause_game(tft, keys, snake, food, score):
    tft.fill_rect(100, 100, 120, 40, st7789.BLACK)
    tft.text(font, "PAUSE", 120, 104, st7789.CYAN)
    wait_press(keys, 'A')
    draw_screen(tft, snake, food, score)   # 重画，盖掉 PAUSE 字样


def play_round(tft, keys, np):
    """打一局，返回得分（死亡时返回）"""
    r, c = ROWS // 2, COLS // 2
    snake = [(r, c), (r, c - 1), (r, c - 2)]   # 头在前
    d = 'RIGHT'
    pending = None
    food = place_food(snake)
    score = 0
    speed = MOVE_BASE
    step_i = 0

    draw_screen(tft, snake, food, score)
    leds_show_score(np, 0)

    while True:
        # ---- 按键 ----
        for ev, key in keys.scan():
            if ev != 'PRESS':
                continue
            if key in DIRS:
                if key != OPPOSITE[d]:      # 不许 180 度掉头
                    pending = key
            elif key == 'A':
                pause_game(tft, keys, snake, food, score)

        # ---- 按节奏走一步 ----
        step_i += 1
        if step_i % speed:
            continue

        if pending:
            d = pending
            pending = None

        dr, dc = DIRS[d]
        nr, nc = snake[0][0] + dr, snake[0][1] + dc
        eating = (nr == food[0] and nc == food[1])

        # 撞墙 / 咬到自己（不增长时蛇尾那格会让出来，不算撞）
        body = snake if eating else snake[:-1]
        if nr < 0 or nr >= ROWS or nc < 0 or nc >= COLS or (nr, nc) in body:
            return score

        if not eating:
            tail = snake.pop()
            erase_cell(tft, tail)

        snake.insert(0, (nr, nc))
        draw_cell(tft, snake[0], st7789.YELLOW)   # 新头
        draw_cell(tft, snake[1], st7789.GREEN)    # 旧头变身体

        # ---- 吃到食物 ----
        if eating:
            score += 1
            food = place_food(snake)
            draw_cell(tft, food, st7789.RED)
            draw_score(tft, score)
            leds_show_score(np, score)
            speed = max(1, MOVE_BASE - score // 8)   # 越吃越快


def game_over_screen(tft, keys, np, score):
    leds_flash(np, (200, 0, 0))
    tft.fill_rect(50, 80, 224, 90, st7789.BLACK)
    tft.rect(50, 80, 224, 90, st7789.RED)
    tft.text(font, "GAME OVER", 76, 96, st7789.RED)
    tft.text(font, "SCORE: %d" % score, 76, 124, st7789.WHITE)
    tft.text(font, "PRESS B RETRY", 76, 148, st7789.YELLOW)
    wait_press(keys, 'B')


def main():
    tft, keys, np = init_hw()
    print("贪吃蛇启动：方向键转向，A 暂停，B 重开，Ctrl+C 退出")
    try:
        while True:
            score = play_round(tft, keys, np)
            print("本局得分:", score)
            game_over_screen(tft, keys, np, score)
    except KeyboardInterrupt:
        np.fill((0, 0, 0))
        np.write()
        print("\n已退出")


if __name__ == "__main__":
    main()
