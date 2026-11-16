// Minimal Arduino API for running the Nod firmware on a desktop (simulator only).
#pragma once
#include <cstdint>
#include <cstring>
#include <cstdio>
#include <cstdlib>
#include <cmath>
#include <cctype>
#include <algorithm>
#include "Print.h"
typedef bool boolean;
class __FlashStringHelper;
class String {                       // just enough for Adafruit_GFX's String overloads
 public:
  String(const char *s = "") : s_(s) {}
  unsigned int length() const { return (unsigned int)strlen(s_); }
  const char *c_str() const { return s_; }
 private:
  const char *s_;
};
#ifndef PI
#define PI 3.14159265358979323846
#endif
#define radians(d) ((d) * PI / 180.0)
#define degrees(r) ((r) * 180.0 / PI)
typedef uint8_t byte;
#define HIGH 1
#define LOW 0
#define INPUT 0
#define OUTPUT 1
#define INPUT_PULLUP 2
#include <type_traits>
template <class A, class B> inline typename std::common_type<A, B>::type min(A a, B b) { return a < b ? a : b; }
template <class A, class B> inline typename std::common_type<A, B>::type max(A a, B b) { return a > b ? a : b; }
template <class T, class L, class H> inline T constrain(T x, L lo, H hi) { return x < lo ? lo : (x > hi ? hi : x); }
uint32_t millis();
void delay(uint32_t ms);
void pinMode(uint8_t, uint8_t);
int digitalRead(uint8_t pin);
void digitalWrite(uint8_t, uint8_t);
void analogWrite(uint8_t pin, int v);
int analogRead(uint8_t);
void analogReadResolution(int);
