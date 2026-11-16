#pragma once
#include <Arduino.h>
#define ST77XX_RED 0xF800
#define ST77XX_BLACK 0x0000
#define ST77XX_WHITE 0xFFFF
extern uint16_t g_screen[172 * 320];
class Adafruit_ST7789 {
 public:
  Adafruit_ST7789(int, int, int) {}
  void init(uint16_t, uint16_t) {}
  void setSPISpeed(uint32_t) {}
  void setRotation(uint8_t) {}
  void setTextColor(uint16_t) {}
  void setTextSize(uint8_t) {}
  void setCursor(int16_t, int16_t) {}
  void print(const char *) {}
  void fillScreen(uint16_t c) { for (auto &p : g_screen) p = c; }
  void drawRGBBitmap(int16_t, int16_t, uint16_t *buf, int16_t w, int16_t h) { memcpy(g_screen, buf, (size_t)w * h * 2); }
};
