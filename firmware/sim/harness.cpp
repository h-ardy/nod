// Runs the real Nod firmware (nod_key.cpp, compiled unchanged) on a desktop.
//
//   ./nod_sim AIR_PORT CTRL_PORT
//
// AIR_PORT : each TCP client is one Bluetooth central (the Nod daemon or a fake Claude desktop app).
//            Bytes the client sends arrive as GATT writes to the RX characteristic, in 20-byte pieces
//            like a default-MTU link; notifications come back on the same socket. Max 2 at once.
// CTRL_PORT: line commands for tests:
//            key 1 | key 0         press / release the switch
//            snap PATH             write the screen as a binary PPM
//            tiles | stat | led    JSON / text state
//            passkey NNNNNN | paired   drive the pairing screen
#include "../nod_key/nod_key.cpp"

#include <arpa/inet.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>
#include <chrono>
#include <map>
#include <string>
#include <thread>
#include <vector>

uint16_t g_screen[172 * 320];
uint32_t g_keyled = 0;
static int g_backlight = 0;
static bool g_keyPressed = false;
AdafruitBluefruitSim Bluefruit;
const uint8_t BLEUART_UUID_SERVICE[16] = {0}, BLEUART_UUID_CHR_RXD[16] = {0}, BLEUART_UUID_CHR_TXD[16] = {0};
static BLEConnection g_conn;
static std::map<uint16_t, int> g_fds;     // conn handle -> socket
static uint16_t g_nextHdl = 1;

static auto T0 = std::chrono::steady_clock::now();
uint32_t millis() {
  return (uint32_t)std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now() - T0).count();
}
void delay(uint32_t ms) { std::this_thread::sleep_for(std::chrono::milliseconds(ms)); }
void pinMode(uint8_t, uint8_t) {}
static uint32_t g_holdAtBoot = getenv("NOD_SIM_HOLD_BOOT") ? (uint32_t)atoi(getenv("NOD_SIM_HOLD_BOOT")) : 0;
int digitalRead(uint8_t pin) {
  if (pin != PIN_KEY) return HIGH;
  if (millis() < g_holdAtBoot) return LOW;            // key held while the board powers up
  return g_keyPressed ? LOW : HIGH;
}
void digitalWrite(uint8_t, uint8_t) {}
void analogWrite(uint8_t pin, int v) { if (pin == TFT_BL) g_backlight = v; }
int analogRead(uint8_t) { return 0; }
void analogReadResolution(int) {}

uint8_t AdafruitBluefruitSim::connected() { return (uint8_t)g_fds.size(); }
bool AdafruitBluefruitSim::connected(uint16_t h) { return g_fds.count(h) > 0; }
BLEConnection *AdafruitBluefruitSim::Connection(uint16_t h) { return g_fds.count(h) ? &g_conn : nullptr; }

bool BLECharacteristic::notify(uint16_t h, const void *data, uint16_t len) {
  auto it = g_fds.find(h);
  if (it == g_fds.end()) return false;
  if (len > maxLen) len = maxLen;              // real stack truncates to max length too
  const char *p = (const char *)data;
  while (len) {
    ssize_t n = send(it->second, p, len, MSG_NOSIGNAL);
    if (n <= 0) return false;
    p += n; len -= n;
  }
  return true;
}

static int listenOn(int port) {
  int s = socket(AF_INET, SOCK_STREAM, 0);
  int one = 1;
  setsockopt(s, SOL_SOCKET, SO_REUSEADDR, &one, sizeof one);
  sockaddr_in a{};
  a.sin_family = AF_INET;
  a.sin_port = htons(port);
  a.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
  if (bind(s, (sockaddr *)&a, sizeof a) || listen(s, 8)) { perror("bind"); exit(1); }
  fcntl(s, F_SETFL, O_NONBLOCK);
  return s;
}

static void writePPM(const char *path) {
  FILE *f = fopen(path, "wb");
  if (!f) return;
  fprintf(f, "P6\n172 320\n255\n");
  for (uint16_t c : g_screen) {
    uint8_t rgb[3] = {(uint8_t)(((c >> 11) & 0x1F) * 255 / 31), (uint8_t)(((c >> 5) & 0x3F) * 255 / 63),
                      (uint8_t)((c & 0x1F) * 255 / 31)};
    fwrite(rgb, 1, 3, f);
  }
  fclose(f);
}

static std::string jsonEsc(const char *s) {
  std::string o;
  for (; *s; s++) { if (*s == '"' || *s == '\\') o += '\\'; o += *s; }
  return o;
}

static std::string control(const std::string &line) {
  char arg[256] = {0};
  if (sscanf(line.c_str(), "key %255s", arg) == 1) { g_keyPressed = arg[0] == '1'; return "ok"; }
  if (sscanf(line.c_str(), "snap %255s", arg) == 1) { writePPM(arg); return "ok"; }
  if (sscanf(line.c_str(), "passkey %6s", arg) == 1) {
    uint8_t code[6]; memcpy(code, arg, 6);
    Bluefruit.Security.pk(1, code, false);
    return "ok";
  }
  if (line == "paired") { Bluefruit.Security.pc(1, 0); return "ok"; }
  if (line == "led") { char b[16]; snprintf(b, sizeof b, "%06X", (unsigned)g_keyled); return b; }
  if (line == "tiles") {
    std::string o = "[";
    for (int i = 0; i < tileCount; i++) {
      const Tile &t = tiles[i];
      char b[512];
      snprintf(b, sizeof b,
               "%s{\"id\":\"%s\",\"src\":\"%s\",\"l1\":\"%s\",\"l2\":\"%s\",\"state\":%d,\"risky\":%s,\"note\":%s,"
               "\"y\":%.0f,\"conn\":%d,\"proto\":%d}",
               i ? "," : "", jsonEsc(t.id).c_str(), jsonEsc(t.src).c_str(), jsonEsc(t.l1).c_str(),
               jsonEsc(t.l2).c_str(), (int)t.state, t.risky ? "true" : "false", t.note ? "true" : "false", t.y,
               t.conn, (int)t.proto);
      o += b;
    }
    return o + "]";
  }
  if (line == "stat") {
    char b[256];
    snprintf(b, sizeof b,
             "{\"conns\":%d,\"lane\":%d,\"appr\":%u,\"deny\":%u,\"pairing\":%s,\"dropped\":%u,\"backlight\":%d,"
             "\"name\":\"%s\",\"bonds_cleared\":%d,\"adv_starts\":%d,\"more\":%u}",
             (int)g_fds.size(), laneNo, (unsigned)statAppr, (unsigned)statDeny, pairing ? "true" : "false",
             (unsigned)droppedLines, g_backlight, Bluefruit.name, Bluefruit.Periph.bondsCleared,
             Bluefruit.Advertising.starts, (unsigned)moreCount);
    return b;
  }
  return "?";
}

int main(int argc, char **argv) {
  int airPort = argc > 1 ? atoi(argv[1]) : 47900, ctlPort = argc > 2 ? atoi(argv[2]) : 47901;
  int air = listenOn(airPort), ctl = listenOn(ctlPort);
  std::map<int, std::string> ctlBufs;
  setup();
  printf("nod_sim ready air=%d ctl=%d name=%s\n", airPort, ctlPort, Bluefruit.name);
  fflush(stdout);
  for (;;) {
    int c;
    while ((c = accept(air, nullptr, nullptr)) >= 0) {
      if (g_fds.size() >= (size_t)MAX_CONN) { close(c); continue; }   // radio allows two centrals
      fcntl(c, F_SETFL, O_NONBLOCK);
      uint16_t h = g_nextHdl++;
      g_fds[h] = c;
      Bluefruit.Periph.ccb(h);
    }
    std::vector<uint16_t> gone;
    for (auto &kv : g_fds) {
      uint8_t buf[4096];
      ssize_t n = recv(kv.second, buf, sizeof buf, 0);
      if (n == 0 || (n < 0 && errno != EAGAIN && errno != EWOULDBLOCK)) { gone.push_back(kv.first); continue; }
      for (ssize_t off = 0; n > 0 && off < n; off += 20) {          // 20-byte writes, like MTU 23
        uint16_t len = (uint16_t)std::min<ssize_t>(20, n - off);
        nusRx.wcb(kv.first, &nusRx, buf + off, len);
      }
    }
    for (uint16_t h : gone) {
      close(g_fds[h]);
      g_fds.erase(h);
      Bluefruit.Periph.dcb(h, 0x13);
    }
    while ((c = accept(ctl, nullptr, nullptr)) >= 0) { fcntl(c, F_SETFL, O_NONBLOCK); ctlBufs[c] = ""; }
    std::vector<int> ctlGone;
    for (auto &kv : ctlBufs) {
      char buf[512];
      ssize_t n = recv(kv.first, buf, sizeof buf, 0);
      if (n == 0 || (n < 0 && errno != EAGAIN && errno != EWOULDBLOCK)) { ctlGone.push_back(kv.first); continue; }
      if (n > 0) kv.second.append(buf, n);
      size_t pos;
      while ((pos = kv.second.find('\n')) != std::string::npos) {
        std::string line = kv.second.substr(0, pos);
        kv.second.erase(0, pos + 1);
        if (line == "quit") return 0;
        std::string r = control(line) + "\n";
        send(kv.first, r.data(), r.size(), MSG_NOSIGNAL);
      }
    }
    for (int f : ctlGone) { close(f); ctlBufs.erase(f); }
    loop();
  }
}
