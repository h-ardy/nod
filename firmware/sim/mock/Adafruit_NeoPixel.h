#pragma once
#include <Arduino.h>
#define NEO_GRB 0
#define NEO_KHZ800 0
extern uint32_t g_keyled;
class Adafruit_NeoPixel {
 public:
  Adafruit_NeoPixel(int, int, int) {}
  void begin() {}
  void setBrightness(uint8_t) {}
  static uint32_t Color(uint8_t r, uint8_t g, uint8_t b) { return ((uint32_t)r << 16) | ((uint32_t)g << 8) | b; }
  void setPixelColor(int, uint32_t c) { pending = c; }
  void show() { g_keyled = pending; }
 private:
  uint32_t pending = 0;
};
