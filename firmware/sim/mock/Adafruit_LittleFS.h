#pragma once
// Simulator stand-in for the board's flash file system: files live in $NOD_SIM_FS (default /tmp/nod_sim_fs).
#include <Arduino.h>
#include <string>
#include <cstdio>
#include <cstdlib>
#include <sys/stat.h>
#include <unistd.h>
namespace Adafruit_LittleFS_Namespace {
enum { FILE_O_READ = 0, FILE_O_WRITE = 1 };
class File {
 public:
  FILE *fp = nullptr;
  explicit File(FILE *f = nullptr) : fp(f) {}
  explicit operator bool() const { return fp != nullptr; }
  size_t write(const uint8_t *b, size_t n) { return fp ? fwrite(b, 1, n, fp) : 0; }
  void close() { if (fp) fclose(fp); fp = nullptr; }
};
}
class SimFS {
  std::string dir() {
    const char *d = getenv("NOD_SIM_FS");
    std::string s = d ? d : "/tmp/nod_sim_fs";
    mkdir(s.c_str(), 0755);
    return s;
  }
 public:
  bool begin() { dir(); return true; }
  bool exists(const char *p) { return access((dir() + p).c_str(), F_OK) == 0; }
  bool remove(const char *p) { return ::remove((dir() + p).c_str()) == 0; }
  Adafruit_LittleFS_Namespace::File open(const char *p, uint8_t mode = 0) {
    return Adafruit_LittleFS_Namespace::File(fopen((dir() + p).c_str(), mode ? "wb" : "rb"));
  }
};
inline SimFS InternalFS;
