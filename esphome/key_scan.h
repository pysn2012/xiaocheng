#pragma once

// ============================================================================
// 键盘矩阵差分扫描（对齐 micropixel/mpup 的 xiaocheng-esp32s3 板级实现）
//
// 硬件：2 行（ESP32 原生 GPIO0 / GPIO46）× 3 列（XL9535 P0.0 / P0.4 / P0.6）
//       A/RIGHT/UP 在第 0 行，DOWN/B/LEFT 在第 1 行
//
// 为什么必须差分扫描（mpup board_config.hpp 的实测结论）：
//   本机列线既没有上拉也没有下拉 —— 悬空，用"把行拉低、看列是不是低"判定按下，
//   悬空列的随机电平会被当成按下 → 乱跳；真实按下的列又因为行线阻抗/寄生电容
//   建立太慢 → 没反应。
//   差分法：行拉低读一次、行拉高读一次，取异或。只有闭合的按键才能把行电平
//   耦合到列，所以 low ^ high 只有真按键才为 1，与列上拉/下拉/悬空无关。
//
// 行线平时保持**高阻输入**（不驱动），只在扫描的那一瞬间切成输出。
// 目的是让同时按下同一列的两个键时不会出现两个强驱动互相打架
// （空闲驱动高/低都会和扫描行形成推挽对打）。
//
// 引入方式：主配置 packages/hardware.yaml 不再用 switch 驱动行线，
// 扫描由 packages/script.yaml 的 key_scan 调用本文件；本文件经
// display_helpers.h 转发引入（主配置 esphome.includes 的入口头文件）。
// ============================================================================

#include "esphome.h"

#include <driver/gpio.h>

namespace xiaocheng {

// ---- 行线 ----
inline constexpr gpio_num_t KEY_ROW_A = GPIO_NUM_0;   // A / RIGHT / UP
inline constexpr gpio_num_t KEY_ROW_B = GPIO_NUM_46;  // DOWN / B / LEFT

// ---- 列位：XL9535 输入口 0（寄存器 0x00）的 bit0 / bit4 / bit6 ----
inline constexpr uint8_t KEY_COL_BIT0 = 1u << 0;  // P0.0
inline constexpr uint8_t KEY_COL_BIT4 = 1u << 4;  // P0.4
inline constexpr uint8_t KEY_COL_BIT6 = 1u << 6;  // P0.6
inline constexpr uint8_t KEY_COL_MASK = (uint8_t) (KEY_COL_BIT0 | KEY_COL_BIT4 | KEY_COL_BIT6);

// 行电平建立时间（mpup: kRowSettleUs = 150）。≤5ms 时 delay_microseconds_safe
// 是纯忙等、不 yield，保证"拉低→读"这一段不会被主循环切走。
inline constexpr uint32_t KEY_ROW_SETTLE_US = 150;

// 行线初始化为高阻输入（无上拉、无下拉）
inline void key_rows_init() {
  gpio_config_t config = {};
  config.pin_bit_mask = (1ULL << KEY_ROW_A) | (1ULL << KEY_ROW_B);
  config.mode = GPIO_MODE_INPUT;
  config.pull_up_en = GPIO_PULLUP_DISABLE;
  config.pull_down_en = GPIO_PULLDOWN_DISABLE;
  config.intr_type = GPIO_INTR_DISABLE;
  gpio_config(&config);
}

// 读 XL9535 输入口 0：一次 I2C 事务同时拿到三列（400kHz 下约 100µs）
inline uint8_t key_read_columns(esphome::xl9535::XL9535Component *hub) {
  uint8_t port = 0;
  hub->read_register(esphome::xl9535::XL9535_INPUT_PORT_0_REGISTER, &port, 1);
  return port;
}

// 差分扫描一行，返回本行闭合的列位掩码（KEY_COL_BIT*）
inline uint8_t key_scan_row(esphome::xl9535::XL9535Component *hub, gpio_num_t row) {
  gpio_set_direction(row, GPIO_MODE_OUTPUT);
  gpio_set_level(row, 0);
  esphome::delay_microseconds_safe(KEY_ROW_SETTLE_US);
  const uint8_t low = key_read_columns(hub);
  gpio_set_level(row, 1);
  esphome::delay_microseconds_safe(KEY_ROW_SETTLE_US);
  const uint8_t high = key_read_columns(hub);
  gpio_set_direction(row, GPIO_MODE_INPUT);  // 回到高阻
  return (uint8_t) (low ^ high) & KEY_COL_MASK;
}

}  // namespace xiaocheng
