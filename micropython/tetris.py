# -*- coding: utf-8 -*-
"""
tetris.py — 掌机俄罗斯方块
==========================
硬件：ESP32-S3 掌机（ST7789 2寸屏 320x240 横屏 + 2x3 矩阵键盘 + WS2812x10）
依赖：xl9535.py 需上传到设备根目录；st7789 驱动、neopixel 为固件内置。

按键：
  LEFT/RIGHT  左右移动（长按连续）
  UP          旋转（顺时针，带左右踢墙）
  DOWN        软降（长按连续，每格 +1 分）
  A           硬降（直接落底，每格 +2 分）
  B           暂停 / 继续

规则：标准 10x20 场地；消行得分 100/300/500/800 x 等级；
      每消 10 行升一级、下落加快；WS2812 显示当前等级（10 颗封顶）。
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

# ---------- 棋盘 / 布局 ----------
COLS, ROWS = 10, 20
CELL = 11                  # 格子边长（像素，画 10x10 留 1px 缝）
X0, Y0 = 4, 10             # 棋盘左上角
PX0 = 136                  # 右侧信息栏起点

GREY = 0x7BEF
ORANGE = 0xFD20

# ---------- 方块定义：n 为包围盒边长，cells 为初始朝向 ----------
PIECES = {
    'I': (4, [(0, 1), (1, 1), (2, 1), (3, 1)], st7789.CYAN),
    'O': (2, [(0, 0), (0, 1), (1, 0), (1, 1)], st7789.YELLOW),
    'T': (3, [(0, 1), (1, 0), (1, 1), (1, 2)], st7789.MAGENTA),
    'S': (3, [(0, 1), (0, 2), (1, 0), (1, 1)], st7789.GREEN),
    'Z': (3, [(0, 0), (0, 1), (1, 1), (1, 2)], st7789.RED),
    'J': (3, [(0, 0), (1, 0), (1, 1), (1, 2)], st7789.BLUE),
    'L': (3, [(0, 2), (1, 0), (1, 1), (1, 2)], ORANGE),
}

# 预计算每个方块的 4 个旋转态：box 内顺时针 (r,c) -> (c, n-1-r)
ROTS = {}
for _t, (_n, _cells, _col) in PIECES.items():
    rots = [_cells]
    for _ in range(3):
        prev = rots[-1]
        rots.append([(c, _n - 1 - r) for (r, c) in prev])
    ROTS[_t] = rots

LINE_SCORES = (0, 100, 300, 500, 800)


# ==================================================================
# 硬件初始化（与 snake.py 相同的时序）
# ==================================================================

def init_hw():
    bl = Pin(BL_PIN, Pin.OUT)
    bl.value(1)
    time.sleep_ms(50)

    i2c = I2C(1, scl=Pin(I2C1_SCL), sda=Pin(I2C1_SDA), freq=400000)
    xl = XL9535(i2c)

    # LCD 硬件复位（LCD_RST 在 XL9535 pin10）
    xl.output(LCD_RST, 1)
    time.sleep_ms(10)
    xl.write(LCD_RST, 0)
    time.sleep_ms(10)
    xl.write(LCD_RST, 1)
    time.sleep_ms(120)

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
# 绘制
# ==================================================================

def draw_board_cell(tft, r, c, color):
    x = X0 + c * CELL
    y = Y0 + r * CELL
    tft.fill_rect(x + 1, y + 1, CELL - 1, CELL - 1, color)


def erase_board_cell(tft, r, c):
    x = X0 + c * CELL
    y = Y0 + r * CELL
    tft.fill_rect(x, y, CELL, CELL, st7789.BLACK)


def redraw_board(tft, board):
    tft.fill_rect(X0, Y0, COLS * CELL, ROWS * CELL, st7789.BLACK)
    for r in range(ROWS):
        for c in range(COLS):
            if board[r][c]:
                draw_board_cell(tft, r, c, board[r][c])


def draw_piece(tft, cells, r, c, color):
    for dr, dc in cells:
        if r + dr >= 0:
            draw_board_cell(tft, r + dr, c + dc, color)


def move_piece(tft, old_cells, orow, ocol, new_cells, nrow, ncol, color):
    """先整块擦旧的，再整块画新的"""
    for dr, dc in old_cells:
        if orow + dr >= 0:
            erase_board_cell(tft, orow + dr, ocol + dc)
    for dr, dc in new_cells:
        if nrow + dr >= 0:
            draw_board_cell(tft, nrow + dr, ncol + dc, color)


def panel_value(tft, x, y, text):
    tft.fill_rect(x, y, 96, 32, st7789.BLACK)
    tft.text(font, text, x, y, st7789.YELLOW)


def draw_panel(tft, score, lines, level, next_t):
    tft.fill_rect(PX0 - 4, 0, 320 - PX0 + 4, 240, st7789.BLACK)
    tft.text(font, "NEXT", PX0, 6, st7789.WHITE)
    # 预览块（归一化到左上角后居中）
    _, cells, color = PIECES[next_t]
    minr = min(dr for dr, _ in cells)
    minc = min(dc for _, dc in cells)
    ox = PX0 + 8 - minc * CELL
    oy = 40 - minr * CELL
    for dr, dc in cells:
        tft.fill_rect(ox + dc * CELL + 1, oy + dr * CELL + 1,
                      CELL - 1, CELL - 1, color)
    tft.text(font, "SCORE", PX0, 96, st7789.WHITE)
    tft.text(font, "LINES", PX0, 132, st7789.WHITE)
    tft.text(font, "LEVEL", PX0, 168, st7789.WHITE)
    tft.text(font, "B=PAUSE", PX0, 208, GREY)
    panel_value(tft, PX0 + 88, 96, str(score))
    panel_value(tft, PX0 + 88, 132, str(lines))
    panel_value(tft, PX0 + 88, 168, str(level))


# ==================================================================
# WS2812
# ==================================================================

def leds_show_level(np, level):
    n = min(NUM_LEDS, level)
    for i in range(NUM_LEDS):
        np[i] = (80, 40, 0) if i < n else (0, 0, 0)
    np.write()


def leds_flash(np, color, times=1, ms=80):
    for _ in range(times):
        np.fill(color)
        np.write()
        time.sleep_ms(ms)
        np.fill((0, 0, 0))
        np.write()
        time.sleep_ms(ms)


# ==================================================================
# 游戏逻辑
# ==================================================================

def collide(board, cells, r, c):
    """方块放在 (r,c) 是否冲突（rr<0 视为场上方，允许）"""
    for dr, dc in cells:
        rr, cc = r + dr, c + dc
        if cc < 0 or cc >= COLS or rr >= ROWS:
            return True
        if rr >= 0 and board[rr][cc]:
            return True
    return False


def lock_piece(tft, board, cells, r, c, color):
    """锁定方块到场地，返回是否有格锁在顶部之上（即游戏结束）"""
    top_out = False
    for dr, dc in cells:
        rr, cc = r + dr, c + dc
        if rr < 0:
            top_out = True
        else:
            board[rr][cc] = color
            draw_board_cell(tft, rr, cc, color)
    return top_out


def clear_full_lines(tft, board, np):
    """消行：闪白 -> 收拢 -> 重画。返回消掉行数。"""
    full = [r for r in range(ROWS) if 0 not in board[r]]
    if not full:
        return 0
    for r in full:
        for c in range(COLS):
            draw_board_cell(tft, r, c, st7789.WHITE)
    leds_flash(np, (0, 200, 0))
    for r in full:
        for c in range(COLS):
            erase_board_cell(tft, r, c)
    kept = [row for row in board if 0 in row]
    board[:] = [[0] * COLS for _ in range(ROWS - len(kept))] + kept
    redraw_board(tft, board)
    return len(full)


def wait_press(keys, name):
    while True:
        for ev, key in keys.scan():
            if ev == 'PRESS' and key == name:
                return


def pause_game(tft, keys, board, cells, r, c, color, score, lines, level, next_t):
    tft.fill_rect(100, 100, 120, 40, st7789.BLACK)
    tft.text(font, "PAUSE", 120, 104, st7789.CYAN)
    wait_press(keys, 'B')
    redraw_board(tft, board)
    draw_piece(tft, cells, r, c, color)
    draw_panel(tft, score, lines, level, next_t)


def play_round(tft, keys, np):
    """打一局，返回得分"""
    board = [[0] * COLS for _ in range(ROWS)]
    score = 0
    lines = 0
    level = 1
    next_t = random.choice(tuple(PIECES))

    tft.fill(st7789.BLACK)
    tft.rect(X0 - 1, Y0 - 1, COLS * CELL + 2, ROWS * CELL + 2, GREY)

    while True:                                  # 每次循环出一个新块
        t = next_t
        next_t = random.choice(tuple(PIECES))
        rot = 0
        cells = ROTS[t][rot]
        color = PIECES[t][2]
        r, c = 0, 3

        draw_panel(tft, score, lines, level, next_t)
        leds_show_level(np, level)

        if collide(board, cells, r, c):          # 出生点被占 -> 结束
            break
        draw_piece(tft, cells, r, c, color)

        drop_frames = max(1, 7 - (level - 1))    # 每 level 级下落节奏（帧=扫描轮）
        frame = 0
        locked = False
        top_out = False

        while not locked:
            # ---- 按键 ----
            for ev, key in keys.scan():
                if ev == 'PRESS' and key == 'B':
                    pause_game(tft, keys, board, cells, r, c, color,
                               score, lines, level, next_t)
                elif key == 'LEFT' and ev in ('PRESS', 'REPEAT'):
                    if not collide(board, cells, r, c - 1):
                        move_piece(tft, cells, r, c, cells, r, c - 1, color)
                        c -= 1
                elif key == 'RIGHT' and ev in ('PRESS', 'REPEAT'):
                    if not collide(board, cells, r, c + 1):
                        move_piece(tft, cells, r, c, cells, r, c + 1, color)
                        c += 1
                elif ev == 'PRESS' and key == 'UP':
                    nrot = (rot + 1) % 4
                    ncells = ROTS[t][nrot]
                    for dx in (0, -1, 1, -2, 2):  # 简单踢墙
                        if not collide(board, ncells, r, c + dx):
                            move_piece(tft, cells, r, c, ncells, r, c + dx, color)
                            rot, cells, c = nrot, ncells, c + dx
                            break
                elif key == 'DOWN' and ev in ('PRESS', 'REPEAT'):
                    if not collide(board, cells, r + 1, c):
                        move_piece(tft, cells, r, c, cells, r + 1, c, color)
                        r += 1
                        score += 1
                        panel_value(tft, PX0 + 88, 96, str(score))
                        frame = 0
                    else:                         # 已到底，锁定
                        top_out = lock_piece(tft, board, cells, r, c, color)
                        locked = True
                elif ev == 'PRESS' and key == 'A':  # 硬降
                    while not collide(board, cells, r + 1, c):
                        r += 1
                        score += 2
                    panel_value(tft, PX0 + 88, 96, str(score))
                    top_out = lock_piece(tft, board, cells, r, c, color)
                    locked = True
                if locked:
                    break

            # ---- 重力 ----
            if locked:
                break
            frame += 1
            if frame >= drop_frames:
                frame = 0
                if not collide(board, cells, r + 1, c):
                    move_piece(tft, cells, r, c, cells, r + 1, c, color)
                    r += 1
                else:
                    top_out = lock_piece(tft, board, cells, r, c, color)
                    locked = True

        if top_out:
            break

        # ---- 消行计分 ----
        n = clear_full_lines(tft, board, np)
        if n:
            score += LINE_SCORES[n] * level
            lines += n
            panel_value(tft, PX0 + 88, 96, str(score))
            panel_value(tft, PX0 + 88, 132, str(lines))
            if lines // 10 + 1 > level:
                level = lines // 10 + 1
                panel_value(tft, PX0 + 88, 168, str(level))

    return score


def game_over_screen(tft, keys, np, score):
    leds_flash(np, (200, 0, 0), times=3, ms=120)
    tft.fill_rect(50, 80, 224, 90, st7789.BLACK)
    tft.rect(50, 80, 224, 90, st7789.RED)
    tft.text(font, "GAME OVER", 76, 96, st7789.RED)
    tft.text(font, "SCORE: %d" % score, 76, 124, st7789.WHITE)
    tft.text(font, "PRESS B RETRY", 76, 148, st7789.YELLOW)
    wait_press(keys, 'B')


def main():
    tft, keys, np = init_hw()
    print("俄罗斯方块：LEFT/RIGHT 移动，UP 旋转，DOWN 软降，A 硬降，B 暂停，Ctrl+C 退出")
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
