#pragma once
#include "esphome.h"

// 屏幕右上角状态图标：电量（10 级 + 充电中）/ WiFi / Home Assistant
// Material Design Icons 编码点，从右往左：电池(常显) → WiFi → HA
static const char *BATTERY_ICONS[10] = {
    "\U000F007A", "\U000F007B", "\U000F007C", "\U000F007D", "\U000F007E",
    "\U000F007F", "\U000F0080", "\U000F0081", "\U000F0082", "\U000F0079"};
static const char *BATTERY_CHARGING_ICONS[10] = {
    "\U000F089C", "\U000F0086", "\U000F0087", "\U000F0088", "\U000F089D",
    "\U000F0089", "\U000F089E", "\U000F008A", "\U000F008B", "\U000F0085"};

static void draw_battery(esphome::display::Display &it,
                         esphome::font::Font *font,
                         esphome::Color color,
                         esphome::sensor::Sensor *percent,
                         esphome::sensor::Sensor *voltage,
                         esphome::binary_sensor::BinarySensor *api_status) {
  float p = percent->state;
  if (isnan(p))
    return;
  int pct = (int) (p + 0.5f);
  if (pct < 1)
    pct = 1;
  if (pct > 100)
    pct = 100;
  // 充电判定（启发式）：电压 >= 4.2V 视为充电中（充电时电池电压会被拉高）
  bool charging = !isnan(voltage->state) && voltage->state >= 4.2f;
  const char *batt = (charging ? BATTERY_CHARGING_ICONS : BATTERY_ICONS)[(pct - 1) / 10];

  const int icon_w = 20;  // 图标占位宽
  int x = it.get_width();
  // 电池图标（最右，常显）
  x -= icon_w;
  it.printf(x, 0, font, color, esphome::display::TextAlign::TOP_LEFT, "%s", batt);
  // WiFi 图标（连接时显示）
  if (esphome::wifi::global_wifi_component != nullptr &&
      esphome::wifi::global_wifi_component->is_connected()) {
    x -= icon_w;
    it.printf(x, 0, font, color, esphome::display::TextAlign::TOP_LEFT, "%s", "\U000F05A9");
  }
  // Home Assistant 图标（API 连接时显示，状态来自 status binary_sensor）
  if (api_status != nullptr && api_status->state) {
    x -= icon_w;
    it.printf(x, 0, font, color, esphome::display::TextAlign::TOP_LEFT, "%s", "\U000F07B0");
  }
}

// 文本自动换行（UTF-8 逐字符累积，超宽则换行）
// ts: 文本传感器；font/color: 字体颜色；start_y: 起始 y；
// max_width: 每行最大像素宽；max_lines: 最多行数；line_height: 行高
static void draw_wrapped(esphome::display::Display &it,
                         esphome::text_sensor::TextSensor *ts,
                         esphome::font::Font *font,
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
