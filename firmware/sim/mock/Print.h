#pragma once
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>
class Print {
 public:
  virtual ~Print() {}
  virtual size_t write(uint8_t) = 0;
  virtual size_t write(const uint8_t *b, size_t n) { size_t k = 0; while (n--) k += write(*b++); return k; }
  size_t write(const char *s) { return s ? write((const uint8_t *)s, strlen(s)) : 0; }
  size_t print(const char *s) { return write(s); }
  size_t print(char c) { return write((uint8_t)c); }
  size_t print(unsigned char v) { return printNum(v); }
  size_t print(int v) { return printNum(v); }
  size_t print(unsigned int v) { return printNum(v); }
  size_t print(long v) { return printNum(v); }
  size_t print(unsigned long v) { return printNum((long)v); }
  size_t print(double v) { char b[32]; snprintf(b, sizeof b, "%.2f", v); return write(b); }
  size_t println(const char *s = "") { return print(s) + print('\n'); }
 private:
  size_t printNum(long v) { char b[24]; snprintf(b, sizeof b, "%ld", v); return write(b); }
};
