#pragma once
#include "esphome.h"

// 屏幕右上角电池角标：电压 + 电量百分比
static void draw_battery(esphome::display::Display &it,
                         esphome::display::Font *font,
                         esphome::Color color,
                         esphome::sensor::Sensor *voltage,
                         esphome::sensor::Sensor *percent) {
  float v = voltage->state;
  float p = percent->state;
  if (isnan(v) || isnan(p))
    return;
  int pct = (int) (p + 0.5f);
  it.printf(it.get_width(), 0, font, color, esphome::display::TextAlign::TOP_RIGHT,
            "%.1fV %d%%", v, pct);
}

// 文本自动换行（UTF-8 逐字符累积，超宽则换行）
// ts: 文本传感器；font/color: 字体颜色；start_y: 起始 y；
// max_width: 每行最大像素宽；max_lines: 最多行数；line_height: 行高
static void draw_wrapped(esphome::display::Display &it,
                         esphome::text_sensor::TextSensor *ts,
                         esphome::display::Font *font,
                         esphome::Color color,
                         int start_y, int max_width, int max_lines, int line_height) {
  std::string text = ts->state.c_str();
  int y = start_y;
  std::string line;
  for (size_t i = 0; i < text.size() && y < start_y + max_lines * line_height;) {
    uint8_t c = text[i];
    int len =
      (c & 0x80) == 0x00 ? 1 :
      (c & 0xE0) == 0xC0 ? 2 :
      (c & 0xF0) == 0xE0 ? 3 : 4;
    std::string next = line + text.substr(i, len);
    int x1, y1, w, h;
    it.get_text_bounds(0, y, next.c_str(), font, esphome::display::TextAlign::TOP_LEFT, &x1, &y1, &w, &h);
    if (w > max_width) {
      it.printf(0, y, font, color, "%s", line.c_str());
      y += line_height;
      line.clear();
    } else {
      line = next;
      i += len;
    }
  }
  if (!line.empty() && y < start_y + max_lines * line_height) {
    it.printf(0, y, font, color, "%s", line.c_str());
  }
}
