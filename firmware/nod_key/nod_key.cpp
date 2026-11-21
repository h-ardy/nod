// Nod key firmware v0.2.1 (all code lives here; nod_key.ino is the Arduino entry file)
// 0.2.1: screen mirror over USB serial (docs/mirror.html), so the key can be tested before the screen is wired
//
// Board:  Seeed Studio XIAO nRF52840, Arduino package "Seeed nRF52 Boards" (the non-mbed one,
//         which includes the Bluefruit BLE library)
// Libs:   Adafruit GFX, Adafruit ST7735 and ST7789, ArduinoJson (v7), Adafruit NeoPixel (optional)
//
// One key can hold two Bluetooth connections at the same time and speaks a protocol on each:
//   * the Nod daemon on your computer (Claude Code CLI hooks, git, chat bridge):
//       {"t":"add"|"note"|"del"|"lane"|"pair", ...}  ->  {"t":"ans"|"ack"|"btn"|"hello", ...}
//   * the Claude desktop app's Hardware Buddy bridge (Claude Code Desktop and Cowork sessions),
//     protocol from github.com/anthropics/claude-desktop-buddy REFERENCE.md:
//       heartbeat {"total","running","waiting","msg","entries","prompt":{"id","tool","hint"}}
//       -> {"cmd":"permission","id":"...","decision":"once"|"deny"}, plus acks for {"cmd":...}
// Each connection's protocol is detected from its first message.
//
// Name: the key advertises as "Nod-XXXX" and works with any agent through the Nod daemon.
// The Claude desktop app's device picker only lists names that start with "Claude", so for that
// app turn on desktop-app mode: hold the key while the board powers up (plug in USB or press
// reset) for 3 s. The key then advertises as "Claude-Nod-XXXX" until you do the same again.
// The choice is saved in flash.
//
// Wiring (XIAO pin -> part)
//   D8  SCK  -> screen CLK          D10 MOSI -> screen DIN
//   D1       -> screen CS           D2       -> screen DC
//   D3       -> screen RST          D6       -> screen BL (backlight, PWM)
//   D0       -> key switch, other leg to GND (internal pull-up)
//   D7       -> NeoPixel Nano DIN (optional)
//   3V3/GND  -> screen VCC/GND, NeoPixel VDD/GND
//   BAT+/BAT- pads on the back -> LiPo

#include <Arduino.h>
#include <bluefruit.h>
#include <SPI.h>
#include <Adafruit_GFX.h>
#include <Adafruit_ST7789.h>
#include <ArduinoJson.h>
#include <Adafruit_LittleFS.h>
#include <InternalFileSystem.h>

#ifndef USE_KEY_LED
#define USE_KEY_LED 1          // NeoPixel under the keycap
#endif
#ifndef NOD_MIRROR
#define NOD_MIRROR 1           // copy the screen to a computer over USB (see docs/mirror.html), only while a page has the port open
#endif
#ifndef NOD_SECURE
#define NOD_SECURE 1           // require LE Secure Connections bonding (passkey shown on screen)
#endif
#if USE_KEY_LED
#include <Adafruit_NeoPixel.h>
#endif

#define FW_VERSION "0.2.1"

// ---------------------------------------------------------------- pins
const uint8_t PIN_KEY = 0, TFT_CS = 1, TFT_DC = 2, TFT_RST = 3, TFT_BL = 6, PIN_KEYLED = 7;

// ---------------------------------------------------------------- display + layout
const int16_t SW = 172, SH = 320;
const int16_t HIT_Y = 288;
const int16_t TILE_H = 64, TILE_H_READY = 96, TILE_GAP = 6, TILE_X = 6, TILE_W = SW - 12;
const uint16_t HOLD_MS = 1000, DOUBLE_MS = 320, PRESS_MS = 90, APPR_MS = 780, DENY_MS = 450;
const uint32_t BACKLIGHT_IDLE_MS = 30000;
const uint16_t C_BG = 0x0841, C_DIM = 0x8C51, C_LINE = 0x4A69, C_RED = 0xF208, C_CLAUDE = 0xDBAA;

Adafruit_ST7789 tft(TFT_CS, TFT_DC, TFT_RST);
GFXcanvas16 *frame = nullptr;       // 172 x 320 x 2 B = 110 KB, allocated at boot
#if USE_KEY_LED
Adafruit_NeoPixel keyLed(1, PIN_KEYLED, NEO_GRB + NEO_KHZ800);
#endif

// Nordic UART Service built by hand (not BLEUart) so each connection gets its own receive buffer.
BLEService nusSvc(BLEUART_UUID_SERVICE);
BLECharacteristic nusTx(BLEUART_UUID_CHR_TXD);   // key -> computer, notify
BLECharacteristic nusRx(BLEUART_UUID_CHR_RXD);   // computer -> key, write
BLEDis bledis;
char deviceName[20];

// ---------------------------------------------------------------- connections
enum Proto : uint8_t { P_UNKNOWN, P_NOD, P_BUDDY };
const int MAX_CONN = 2;
const size_t LINE_MAX = 1024;       // longer lines (big turn events) are dropped on purpose
struct Conn {
  bool used;
  uint16_t hdl;
  Proto proto;
  bool helloSent;
  char buf[LINE_MAX];
  size_t len;
  bool overflow;
  int prevRunning;
  char lastAnswered[48];            // buddy: ignore a prompt we just answered until the app catches up
};
Conn conns[MAX_CONN];

struct Line { uint16_t hdl; char data[LINE_MAX]; };
const uint8_t QLEN = 6;
Line lineq[QLEN];
volatile uint8_t qHead = 0, qTail = 0;  // BLE task fills, loop() drains
volatile uint32_t droppedLines = 0;

Conn *connFor(uint16_t hdl) {
  for (int i = 0; i < MAX_CONN; i++)
    if (conns[i].used && conns[i].hdl == hdl) return &conns[i];
  return nullptr;
}

bool anyConn(Proto p) {
  for (int i = 0; i < MAX_CONN; i++)
    if (conns[i].used && conns[i].proto == p) return true;
  return false;
}

int connCount() {
  int n = 0;
  for (int i = 0; i < MAX_CONN; i++) n += conns[i].used ? 1 : 0;
  return n;
}

// ---------------------------------------------------------------- tiles
enum TileState : uint8_t { LIVE, APPROVED, DENIED };
struct Tile {
  char id[48];
  char src[17];
  char l1[25];
  char l2[61];
  char l3[41];
  uint16_t color;
  uint8_t r, g, b;
  bool risky, note;
  TileState state;
  float y;
  float ay;            // where the tile sat when it was approved
  uint32_t doneAt;
  uint16_t conn;
  Proto proto;
};
const int MAX_TILES = 8;
Tile tiles[MAX_TILES];
int tileCount = 0;

uint8_t laneNo = 0;
uint16_t moreCount = 0;           // requests the daemon is holding back until there is room
bool pairing = false;
uint8_t batteryPct = 100;
uint16_t batteryMv = 0;
uint32_t statAppr = 0, statDeny = 0;
char passkey[7] = {0};
uint32_t passkeyUntil = 0;

bool keyDown = false, holdUsed = false;
uint32_t keyDownAt = 0, lastTapAt = 0, pendingTapAt = 0, hintUntil = 0, lastActivity = 0;
float holdProgress = 0;

// ---------------------------------------------------------------- helpers
uint16_t hex565(const char *hex, uint8_t &r, uint8_t &g, uint8_t &b) {
  uint32_t v = strtoul(hex, nullptr, 16);
  r = (v >> 16) & 0xFF; g = (v >> 8) & 0xFF; b = v & 0xFF;
  return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3);
}

uint16_t inkFor(const Tile &t) {
  int lum = (t.r * 299 + t.g * 587 + t.b * 114) / 1000;
  return lum > 110 ? 0x10A2 : 0xFFFF;
}

int liveIndex(int k) {
  for (int i = 0, n = 0; i < tileCount; i++)
    if (tiles[i].state == LIVE && n++ == k) return i;
  return -1;
}
int lowestLive() { return liveIndex(0); }
bool lowestReady() {
  int i = lowestLive();
  return i >= 0 && tiles[i].y >= HIT_Y - TILE_H_READY - 12;
}

void wake() { lastActivity = millis(); }

void removeAt(int i) {
  for (int j = i; j < tileCount - 1; j++) tiles[j] = tiles[j + 1];
  tileCount--;
}

void removeWhere(uint16_t conn, bool onlyLiveAsks) {
  for (int i = tileCount - 1; i >= 0; i--) {
    Tile &t = tiles[i];
    if (t.conn != conn) continue;
    if (onlyLiveAsks && (t.note || t.state != LIVE)) continue;
    removeAt(i);
  }
}

int findTile(uint16_t conn, const char *id) {
  for (int i = 0; i < tileCount; i++)
    if (tiles[i].conn == conn && !strcmp(tiles[i].id, id)) return i;
  return -1;
}

// Plain-text risk check for prompts that arrive without a risk flag (desktop app prompts).
bool riskyText(const char *s) {
  static const char *pats[] = {"rm -r", "rm -f", "rm -rf", "sudo ", "--force", "push -f", "reset --hard",
                               "| sh", "| bash", "|sh", "|bash", "mkfs", "dd if=", "chmod 777", "drop table",
                               "npm publish", "terraform destroy", "kubectl delete", "branch -d", nullptr};
  char low[128];
  size_t n = strlen(s);
  if (n > sizeof(low) - 1) n = sizeof(low) - 1;
  for (size_t i = 0; i < n; i++) low[i] = tolower((unsigned char)s[i]);
  low[n] = 0;
  for (int i = 0; pats[i]; i++)
    if (strstr(low, pats[i])) return true;
  return false;
}

Tile *addTile(uint16_t conn, Proto proto, const char *id, const char *src, const char *hex,
              const char *l1, const char *l2, const char *l3, bool risky, bool note) {
  if (tileCount >= MAX_TILES) return nullptr;
  Tile &n = tiles[tileCount++];
  memset(&n, 0, sizeof(n));
  strlcpy(n.id, id, sizeof(n.id));
  strlcpy(n.src, src, sizeof(n.src));
  strlcpy(n.l1, l1, sizeof(n.l1));
  strlcpy(n.l2, l2, sizeof(n.l2));
  strlcpy(n.l3, l3, sizeof(n.l3));
  n.color = hex565(hex, n.r, n.g, n.b);
  n.risky = risky;
  n.note = note;
  n.state = LIVE;
  n.y = -TILE_H;
  n.conn = conn;
  n.proto = proto;
  wake();
  return &n;
}

// ---------------------------------------------------------------- sending
void sendLine(uint16_t hdl, JsonDocument &doc) {
  if (!Bluefruit.connected(hdl)) return;
  char out[300];
  size_t n = serializeJson(doc, out, sizeof(out) - 1);
  out[n++] = '\n';
  const size_t CH = 180;                              // below the characteristic's max length
  for (size_t off = 0; off < n; off += CH) {
    size_t len = (n - off < CH) ? n - off : CH;
    for (int tries = 0; tries < 50; tries++) {        // wait for a free notification buffer
      if (nusTx.notify(hdl, out + off, (uint16_t)len)) break;
      delay(4);
    }
  }
}

void sendAnswer(Tile &t, bool allow) {
  Conn *c = connFor(t.conn);
  if (!c) return;
  JsonDocument doc;
  if (t.proto == P_NOD) {
    doc["t"] = t.note ? "ack" : "ans";
    doc["id"] = t.id;
    if (!t.note) doc["d"] = allow ? "allow" : "deny";
  } else {
    if (t.note) return;                               // desktop notes are local only
    doc["cmd"] = "permission";
    doc["id"] = t.id;
    doc["decision"] = allow ? "once" : "deny";
    strlcpy(c->lastAnswered, t.id, sizeof(c->lastAnswered));
  }
  sendLine(t.conn, doc);
}

void finish(int i, TileState s) {
  tiles[i].state = s;
  tiles[i].doneAt = millis();
  tiles[i].ay = tiles[i].y;
  if (s == APPROVED) statAppr++; else statDeny++;
  sendAnswer(tiles[i], s == APPROVED);
}

// ---------------------------------------------------------------- Nod daemon protocol
void handleNod(Conn &c, JsonDocument &doc) {
  if (!c.helloSent) {
    c.helloSent = true;
    JsonDocument h;
    h["t"] = "hello"; h["fw"] = FW_VERSION; h["bat"] = batteryPct;
    sendLine(c.hdl, h);
  }
  const char *t = doc["t"] | "";
  if (!strcmp(t, "add") || !strcmp(t, "note")) {
    addTile(c.hdl, P_NOD, doc["id"] | "", doc["src"] | "", doc["c"] | "E5B53A", doc["l1"] | "",
            doc["l2"] | "", doc["l3"] | "", (doc["risk"] | 0) != 0, !strcmp(t, "note"));
  } else if (!strcmp(t, "del")) {
    int i = findTile(c.hdl, doc["id"] | "");
    if (i >= 0) removeAt(i);
  } else if (!strcmp(t, "lane")) {
    laneNo = doc["n"] | 0;
    pairing = false;
  } else if (!strcmp(t, "pair")) {
    pairing = true;
    wake();
  } else if (!strcmp(t, "more")) {
    moreCount = doc["n"] | 0;
  }
}

// ---------------------------------------------------------------- Claude desktop Hardware Buddy protocol
void ack(Conn &c, const char *cmd, bool ok) {
  JsonDocument a;
  a["ack"] = cmd; a["ok"] = ok; a["n"] = 0;
  sendLine(c.hdl, a);
}

void handleBuddy(Conn &c, JsonDocument &doc) {
  if (doc["cmd"].is<const char *>()) {
    const char *cmd = doc["cmd"];
    if (!strcmp(cmd, "status")) {
      JsonDocument a;
      a["ack"] = "status"; a["ok"] = true;
      JsonObject d = a["data"].to<JsonObject>();
      d["name"] = deviceName;
      BLEConnection *bc = Bluefruit.Connection(c.hdl);
      d["sec"] = bc ? bc->secured() : false;
      d["bat"]["pct"] = batteryPct;
      if (batteryMv) d["bat"]["mV"] = batteryMv;
      d["sys"]["up"] = millis() / 1000;
      d["stats"]["appr"] = statAppr;
      d["stats"]["deny"] = statDeny;
      sendLine(c.hdl, a);
    } else if (!strcmp(cmd, "name") || !strcmp(cmd, "owner")) {
      ack(c, cmd, true);
    } else if (!strcmp(cmd, "unpair")) {
      Bluefruit.Periph.clearBonds();
      ack(c, cmd, true);
    }
    // folder push (char_begin ...) is declined by not acking, as the protocol allows
    return;
  }
  if (!doc["total"].is<int>() && !doc["prompt"].is<JsonObject>()) return;   // time sync, turn events

  JsonObject p = doc["prompt"];
  if (!p.isNull()) {
    const char *id = p["id"] | "";
    if (*id && strcmp(id, c.lastAnswered) && findTile(c.hdl, id) < 0) {
      removeWhere(c.hdl, true);                       // the app shows one prompt at a time
      const char *hint = p["hint"] | "";
      addTile(c.hdl, P_BUDDY, id, "CLAUDE APP", "D97757", p["tool"] | "Tool", hint,
              doc["msg"] | "", riskyText(hint), false);
    }
  } else {
    removeWhere(c.hdl, true);                         // answered in the app, or withdrawn
    c.lastAnswered[0] = 0;
  }
  int running = doc["running"] | 0, waiting = doc["waiting"] | 0, total = doc["total"] | 0;
  if (c.prevRunning > 0 && running == 0 && waiting == 0 && total > 0) {
    const char *last = doc["entries"][0] | (doc["msg"] | "");
    char nid[16];
    snprintf(nid, sizeof(nid), "done%lu", (unsigned long)millis());
    addTile(c.hdl, P_BUDDY, nid, "CLAUDE APP", "D97757", "Done", last, "", false, true);
  }
  c.prevRunning = running;
}

void handleLine(uint16_t hdl, const char *line) {
  Conn *c = connFor(hdl);
  if (!c) return;
  JsonDocument doc;
  if (deserializeJson(doc, line)) return;
  if (c->proto == P_UNKNOWN) c->proto = doc["t"].is<const char *>() ? P_NOD : P_BUDDY;
  if (c->proto == P_NOD) handleNod(*c, doc);
  else handleBuddy(*c, doc);
}

// ---------------------------------------------------------------- BLE callbacks (run in the BLE task)
void onRxWrite(uint16_t hdl, BLECharacteristic *, uint8_t *data, uint16_t len) {
  Conn *c = connFor(hdl);
  if (!c) return;
  for (uint16_t i = 0; i < len; i++) {
    char ch = (char)data[i];
    if (ch == '\n') {
      if (!c->overflow && c->len > 0) {
        uint8_t next = (qHead + 1) % QLEN;
        if (next == qTail) {
          droppedLines = droppedLines + 1;
        } else {
          lineq[qHead].hdl = hdl;
          memcpy(lineq[qHead].data, c->buf, c->len);
          lineq[qHead].data[c->len] = 0;
          qHead = next;
        }
      }
      c->len = 0;
      c->overflow = false;
    } else if (ch != '\r') {
      if (c->len < LINE_MAX - 1) c->buf[c->len++] = ch;
      else c->overflow = true;
    }
  }
}

void onConnect(uint16_t hdl) {
  for (int i = 0; i < MAX_CONN; i++) {
    if (!conns[i].used) {
      memset(&conns[i], 0, sizeof(Conn));
      conns[i].used = true;
      conns[i].hdl = hdl;
      break;
    }
  }
  // With NOD_SECURE the encrypted characteristics make the host's first access start pairing.
  if (Bluefruit.connected() < MAX_CONN) Bluefruit.Advertising.start(0);   // let the second host find us
  wake();
}

void onDisconnect(uint16_t hdl, uint8_t) {
  removeWhere(hdl, false);                            // the daemon resends what is still pending
  Conn *c = connFor(hdl);
  if (c) c->used = false;
  bool anyNod = anyConn(P_NOD);
  if (!anyNod) { laneNo = 0; moreCount = 0; }
  wake();
}

bool onPasskey(uint16_t, uint8_t const code[6], bool) {
  memcpy(passkey, code, 6);
  passkey[6] = 0;
  passkeyUntil = millis() + 60000;
  wake();
  return true;
}

void onPairComplete(uint16_t, uint8_t) { passkeyUntil = 0; wake(); }

void drainLines() {
  while (qTail != qHead) {
    handleLine(lineq[qTail].hdl, lineq[qTail].data);
    qTail = (qTail + 1) % QLEN;
  }
}

// ---------------------------------------------------------------- key handling
void onTapConfirmed() {
  int i = lowestLive();
  if (i < 0) return;
  if (tiles[i].note) { sendAnswer(tiles[i], true); removeAt(i); return; }
  if (tiles[i].risky) { hintUntil = millis() + 900; return; }
  finish(i, APPROVED);
}

void sendBtn() {
  for (int i = 0; i < MAX_CONN; i++) {
    if (conns[i].used && conns[i].proto == P_NOD) {
      JsonDocument d; d["t"] = "btn";
      sendLine(conns[i].hdl, d);
    }
  }
}

void pollKey() {
  bool down = digitalRead(PIN_KEY) == LOW;
  uint32_t now = millis();
  static uint32_t lastEdge = 0;
  if (down != keyDown && now - lastEdge > 12) {        // 12 ms debounce
    lastEdge = now;
    keyDown = down;
    wake();
    if (down) {
      keyDownAt = now;
      holdUsed = false;
    } else if (!holdUsed) {
      if (pairing || lowestLive() < 0) {
        sendBtn();
        pairing = false;
      } else if (!lowestReady()) {
        // still falling: ignore, so a stray press never answers something you have not read
      } else if (pendingTapAt && now - lastTapAt < DOUBLE_MS) {
        pendingTapAt = 0;
        int i = lowestLive();
        if (i >= 0 && !tiles[i].note) finish(i, DENIED);
      } else {
        lastTapAt = now;
        pendingTapAt = now + DOUBLE_MS;
      }
    }
    holdProgress = 0;
  }
  int i = lowestLive();
  if (keyDown && !holdUsed && i >= 0 && tiles[i].risky && lowestReady()) {
    holdProgress = min(1.0f, (now - keyDownAt) / (float)HOLD_MS);
    if (holdProgress >= 1.0f) {
      holdUsed = true;
      holdProgress = 0;
      pendingTapAt = 0;
      finish(i, APPROVED);
    }
  } else if (!keyDown) {
    holdProgress = 0;
  }
  if (pendingTapAt && now >= pendingTapAt) { pendingTapAt = 0; onTapConfirmed(); }
}

// ---------------------------------------------------------------- drawing
void printClipped(const char *s, int16_t x, int16_t y, uint8_t size, int maxChars) {
  char buf[64];
  strlcpy(buf, s, sizeof(buf));
  if ((int)strlen(buf) > maxChars) { buf[maxChars - 1] = '.'; buf[maxChars] = 0; }
  frame->setTextSize(size);
  frame->setCursor(x, y);
  frame->print(buf);
}

void printCentered(const char *s, int16_t y, uint8_t size, uint16_t color) {
  frame->setTextSize(size);
  frame->setTextColor(color);
  int16_t w = strlen(s) * 6 * size;
  frame->setCursor((SW - w) / 2, y);
  frame->print(s);
}

// ---------------------------------------------------------------- the "yes" moment
// 1 slam: the tile squashes onto the line and whitens (90 ms)
// 2 impact: the lane flashes in the source color and the line lights up
// 3 shatter: the tile breaks into pixel blocks that fly up the lane
// 4 check: a ring and check mark draw themselves, pop, then fade (about 0.8 s in all)
uint16_t blend565(uint16_t a, uint16_t b, float t) {       // t = 0 gives a, 1 gives b
  if (t <= 0) return a;
  if (t >= 1) return b;
  int ar = a >> 11, ag = (a >> 5) & 63, ab = a & 31, br = b >> 11, bg = (b >> 5) & 63, bb = b & 31;
  return ((uint16_t)(ar + (br - ar) * t) << 11) | ((uint16_t)(ag + (bg - ag) * t) << 5) | (uint16_t)(ab + (bb - ab) * t);
}
float clamp01(float v) { return v < 0 ? 0 : (v > 1 ? 1 : v); }

// age of the newest approval animation in this frame, past the slam; -1 if none
long yesSince(uint32_t now, uint16_t &color) {
  for (int i = tileCount - 1; i >= 0; i--)
    if (tiles[i].state == APPROVED && !tiles[i].note) {
      color = tiles[i].color;
      return (long)(now - tiles[i].doneAt) - PRESS_MS;
    }
  return -1000000;
}

void thickTo(float x0, float y0, float x1, float y1, int16_t r, uint16_t c) {
  float d = sqrtf((x1 - x0) * (x1 - x0) + (y1 - y0) * (y1 - y0));
  int n = (int)(d / 2) + 1;
  for (int k = 0; k <= n; k++) {
    float q = (float)k / n;
    frame->fillCircle((int16_t)(x0 + (x1 - x0) * q), (int16_t)(y0 + (y1 - y0) * q), r, c);
  }
}

void drawYes(const Tile &t, uint32_t now) {
  uint32_t e = now - t.doneAt;
  float top = t.ay;
  if (e < PRESS_MS) {                                   // 1 slam
    float k = (float)e / PRESS_MS; k *= k;
    int16_t hh = (int16_t)(TILE_H_READY * (1 - 0.55f * k));
    int16_t yy = (int16_t)top + TILE_H_READY - hh;
    frame->fillRoundRect(TILE_X, yy, TILE_W, hh, 6, blend565(t.color, 0xFFFF, 0.6f * k));
    return;
  }
  float f = (float)(e - PRESS_MS);
  // 3 shatter: 8 x 3 blocks, the same scatter every time for a given tile
  uint32_t seed = 2166136261u;
  for (const char *p = t.id; *p; p++) seed = (seed ^ (uint8_t)*p) * 16777619u;
  auto rnd = [&seed]() { seed = seed * 1664525u + 1013904223u; return (seed >> 8) / 16777216.0f; };
  const int COLS = 8, ROWS = 3;
  float cw = TILE_W / (float)COLS, ch = TILE_H_READY * 0.45f / ROWS, y0 = top + TILE_H_READY * 0.55f;
  for (int r = 0; r < ROWS; r++)
    for (int q = 0; q < COLS; q++) {
      float vx = (rnd() - 0.5f) * 150, vy = -(230 + rnd() * 330), life = 420 + rnd() * 280;
      bool light = rnd() < 0.3f;
      float p = f / life;
      if (p >= 1) continue;
      float sec = f / 1000.0f, sz = 1 - 0.65f * p;
      int16_t px = (int16_t)(TILE_X + q * cw + vx * sec), py = (int16_t)(y0 + r * ch + vy * sec + 150 * sec * sec);
      uint16_t c = blend565(light ? 0xFFFF : t.color, C_BG, p * p);
      frame->fillRect(px, py, max(1, (int)(cw * sz) - 1), max(1, (int)(ch * sz) - 1), c);
    }
  // 4 ring and check
  float draw = clamp01((f - 30) / 210), pop = 1 + 0.2f * sinf(3.14159f * clamp01((f - 230) / 190));
  float fade = clamp01((f - (APPR_MS - PRESS_MS - 200)) / 200);
  uint16_t c = blend565(t.color, C_BG, fade);
  float cx = SW / 2, cy = 128, R = 42 * pop;
  int steps = (int)(90 * draw);
  for (int k = 0; k < steps; k++) {
    float a = -1.5708f + 6.2832f * k / 90;
    frame->fillCircle((int16_t)(cx + R * cosf(a)), (int16_t)(cy + R * sinf(a)), 2, c);
  }
  float pts[3][2] = {{cx - 24 * pop, cy + 2 * pop}, {cx - 7 * pop, cy + 19 * pop}, {cx + 26 * pop, cy - 20 * pop}};
  float seg0 = sqrtf(17 * 17 + 17 * 17) * pop, seg1 = sqrtf(33 * 33 + 39 * 39) * pop;
  float left = (seg0 + seg1) * clamp01((f - 90) / 190);
  if (left > 0) {
    float k0 = min(1.0f, left / seg0);
    thickTo(pts[0][0], pts[0][1], pts[0][0] + (pts[1][0] - pts[0][0]) * k0, pts[0][1] + (pts[1][1] - pts[0][1]) * k0, 4, c);
    left -= seg0;
    if (left > 0) {
      float k1 = min(1.0f, left / seg1);
      thickTo(pts[1][0], pts[1][1], pts[1][0] + (pts[2][0] - pts[1][0]) * k1, pts[1][1] + (pts[2][1] - pts[1][1]) * k1, 4, c);
    }
  }
  if (f > 170) printCentered("APPROVED", (int16_t)(cy + R + 12), 2, blend565(C_BG, c, clamp01((f - 170) / 140)));
}

void drawTile(const Tile &t, bool ready, uint32_t now) {
  int16_t h = ready ? TILE_H_READY : TILE_H;
  int16_t y = (int16_t)t.y;
  int16_t x = TILE_X;
  float squash = 1.0f;
  if (t.state == APPROVED) { drawYes(t, now); return; }
  if (t.state == DENIED) {
    float p = min(1.0f, (now - t.doneAt) / (float)DENY_MS);
    x -= (int16_t)(p * 190);
    printCentered("DENIED", 60, 2, C_RED);
  }
  int16_t hh = (int16_t)(h * squash);
  int16_t yy = y + (h - hh);
  frame->fillRoundRect(x, yy, TILE_W, hh, 6, t.color);
  if (t.risky) frame->drawRoundRect(x - 3, yy - 3, TILE_W + 6, hh + 6, 8, C_RED);
  frame->setTextColor(inkFor(t));
  // text area is TILE_W - 16 = 144 px: 24 characters at size 1 (6 px), 12 at size 2 (12 px)
  printClipped(t.risky ? "RISKY" : t.src, x + 8, yy + 7, 1, 24);
  printClipped(t.l1, x + 8, yy + 20, 2, 12);
  printClipped(t.l2, x + 8, yy + 40, 1, 24);
  if (ready && hh > 70) {
    printClipped(t.l3, x + 8, yy + 54, 1, 24);
    if (t.risky) {
      frame->fillRect(x + 8, yy + hh - 12, TILE_W - 16, 5, 0xC618);
      frame->fillRect(x + 8, yy + hh - 12, (int16_t)((TILE_W - 16) * holdProgress), 5, C_RED);
    }
  }
}

void drawHeader() {
  frame->fillRect(0, 0, SW, 20, C_BG);               // drawn last so tiles never cover it
  frame->setTextSize(1);
  frame->setTextColor(C_DIM);
  frame->setCursor(8, 6);
  if (laneNo) { frame->print("0"); frame->print(laneNo); frame->print(" "); }
  if (anyConn(P_NOD)) frame->print("PC ");
  if (anyConn(P_BUDDY)) frame->print("APP");
  frame->setCursor(SW - 34, 6);
  frame->print(batteryPct); frame->print("%");
  if (moreCount) {                                   // more requests queued on the computer
    char more[16];
    snprintf(more, sizeof(more), "+%u MORE", (unsigned)moreCount);
    frame->fillRoundRect(SW / 2 - 30, 3, 60, 13, 3, 0xFFFF);
    printCentered(more, 6, 1, 0x10A2);
  }

}

#if NOD_MIRROR
// Screen mirror over USB serial, for testing without the screen and for screenshots.
// Frame: "NODF", width u16, height u16, then runs of (count u16, RGB565 colour u16), little endian,
// ending with a run of count 0. The UI is mostly flat colour, so a frame is usually a few KB.
// Sent at most 8 times a second, only while a program has the port open, and dropped (never waited
// on) if the computer isn't reading, so the key never stalls because of it.
static uint8_t mirBuf[64];
static size_t mirLen = 0;
static bool mirOk = true;

static void mirFlush() {
  if (!mirOk || mirLen == 0) { mirLen = 0; return; }
  uint32_t t0 = millis();
  while (Serial.availableForWrite() < (int)mirLen) {
    if (millis() - t0 > 15 || !Serial) { mirOk = false; mirLen = 0; return; }   // reader stalled: drop the frame
    yield();
  }
  Serial.write(mirBuf, mirLen);
  mirLen = 0;
}
static void mirPut16(uint16_t v) {
  if (mirLen + 2 > sizeof(mirBuf)) mirFlush();
  mirBuf[mirLen++] = v & 0xFF;
  mirBuf[mirLen++] = v >> 8;
}

void mirrorFrame() {
  static uint32_t last = 0;
  uint32_t now = millis();
  if (!frame || !Serial || now - last < 125) return;
  last = now;
  mirOk = true; mirLen = 0;
  const uint16_t *px = frame->getBuffer();
  const uint32_t n = (uint32_t)SW * SH;
  mirBuf[0] = 'N'; mirBuf[1] = 'O'; mirBuf[2] = 'D'; mirBuf[3] = 'F'; mirLen = 4;
  mirPut16(SW); mirPut16(SH);
  uint32_t i = 0;
  while (i < n && mirOk) {
    uint16_t c = px[i];
    uint32_t run = 1;
    while (i + run < n && px[i + run] == c && run < 0xFFFF) run++;
    mirPut16((uint16_t)run); mirPut16(c);
    i += run;
  }
  mirPut16(0); mirPut16(0);
  mirFlush();
}
#else
inline void mirrorFrame() {}
#endif

void pushFrame() {
  tft.drawRGBBitmap(0, 0, frame->getBuffer(), SW, SH);
  mirrorFrame();
}

void render() {
  if (!frame) return;
  uint32_t now = millis();
  uint16_t yesColor = 0;
  long since = yesSince(now, yesColor);
  frame->fillScreen(since >= 0 && since < 170 ? blend565(C_BG, yesColor, 0.34f * (1 - since / 170.0f)) : C_BG);
  frame->setTextWrap(false);
  frame->setTextSize(1);
  if (passkeyUntil && now < passkeyUntil) {
    printCentered("PAIR CODE", 110, 2, 0xFFFF);
    printCentered(passkey, 140, 3, C_CLAUDE);
    drawHeader();
    pushFrame();
    return;
  }
  if (connCount() == 0) printCentered("WAITING FOR COMPUTER", 150, 1, C_DIM);
  if (pairing) printCentered("PRESS", 140, 3, 0xFFFF);

  for (int i = 0; i < tileCount; i++)
    if (tiles[i].state != LIVE) drawTile(tiles[i], true, now);
  int low = lowestLive();
  for (int k = 0;; k++) {
    int i = liveIndex(k);
    if (i < 0) break;
    drawTile(tiles[i], (i == low) && lowestReady(), now);
  }

  for (int16_t x = 6; x < SW - 6; x += 6) frame->drawFastHLine(x, HIT_Y, 3, C_LINE);
  if (since >= 0 && since < 320)                     // the line lights up on impact
    frame->fillRect(6, HIT_Y - 1, SW - 12, 3, blend565(yesColor, C_BG, since / 320.0f));
  frame->setTextSize(1);
  if (low >= 0 && lowestReady()) {
    const Tile &t = tiles[low];
    frame->setTextColor(t.risky ? C_RED : t.color);
    frame->setCursor(8, HIT_Y + 10);
    if (t.note) frame->print("TAP TO CLEAR");
    else if (t.risky) frame->print(now < hintUntil ? "HOLD, DO NOT TAP" : "HOLD 1.0 S TO RUN");
    else frame->print("TAP OK   2 TAPS NO");
  } else if (tileCount == 0 && connCount() > 0 && !pairing) {
    printCentered("ALL CLEAR", 150, 1, C_DIM);
  }
  drawHeader();
  pushFrame();
}

void animate() {
  uint32_t now = millis();
  for (int i = tileCount - 1; i >= 0; i--) {
    uint32_t span = tiles[i].state == APPROVED ? APPR_MS : DENY_MS;
    if (tiles[i].state != LIVE && now - tiles[i].doneAt > span) removeAt(i);
  }
  int16_t slotBottom = HIT_Y;
  for (int k = 0;; k++) {
    int i = liveIndex(k);
    if (i < 0) break;
    int16_t h = (k == 0) ? TILE_H_READY : TILE_H;
    float target = slotBottom - h;
    Tile &t = tiles[i];
    if (t.y < target) t.y = min(target, t.y + 7.0f);
    if (t.y > target) t.y = target;
    slotBottom = (int16_t)target - TILE_GAP;
  }
}

bool busy() {
  if (tileCount > 0 || pairing || keyDown || (passkeyUntil && millis() < passkeyUntil)) return true;
  return millis() - lastActivity < 2000;
}

void updateLights() {
  bool on = tileCount > 0 || pairing || millis() - lastActivity < BACKLIGHT_IDLE_MS;
  analogWrite(TFT_BL, on ? 200 : 0);
#if USE_KEY_LED
  int i = lowestLive();
  if (i >= 0 && lowestReady()) {
    const Tile &t = tiles[i];
    if (t.risky) keyLed.setPixelColor(0, keyLed.Color(240, 68, 56));
    else keyLed.setPixelColor(0, keyLed.Color(t.r, t.g, t.b));
  } else {
    keyLed.setPixelColor(0, 0);
  }
  keyLed.show();
#endif
}

void readBattery() {
#if defined(VBAT_ENABLE) && defined(PIN_VBAT)
  digitalWrite(VBAT_ENABLE, LOW);
  delay(1);
  uint32_t raw = analogRead(PIN_VBAT);
  // 12-bit ADC, 3.6 V reference, about 1M/510k divider on the XIAO. Calibrate with a meter.
  float mv = raw * 3600.0f / 4096.0f * (1510.0f / 510.0f);
  batteryMv = (uint16_t)mv;
  int pct = (int)((mv - 3300.0f) / 9.0f);            // rough linear 3.3 V .. 4.2 V
  batteryPct = (uint8_t)constrain(pct, 0, 100);
#endif
}

// ---------------------------------------------------------------- setup / loop
// ---------------------------------------------------------------- name mode (saved in flash)
const char *APP_MODE_FILE = "/nod_appmode";
bool appMode = false;

void bootNameMode() {
  using namespace Adafruit_LittleFS_Namespace;
  InternalFS.begin();
  appMode = InternalFS.exists(APP_MODE_FILE);
  if (digitalRead(PIN_KEY) != LOW) return;           // normal boot
  tft.fillScreen(ST77XX_BLACK);
  tft.setTextColor(ST77XX_WHITE);
  tft.setTextSize(2);
  tft.setCursor(10, 120);
  tft.print("KEEP HOLDING");
  uint32_t t0 = millis();
  while (digitalRead(PIN_KEY) == LOW && millis() - t0 < 3000) delay(10);
  if (millis() - t0 < 3000) return;                   // let go early: no change
  appMode = !appMode;
  if (appMode) {
    File f = InternalFS.open(APP_MODE_FILE, FILE_O_WRITE);
    if (f) { f.write((const uint8_t *)"1", 1); f.close(); }
  } else {
    InternalFS.remove(APP_MODE_FILE);
  }
  tft.fillScreen(ST77XX_BLACK);
  tft.setCursor(10, 110);
  tft.print("DESKTOP APP");
  tft.setCursor(10, 135);
  tft.print(appMode ? "MODE ON" : "MODE OFF");
  while (digitalRead(PIN_KEY) == LOW) delay(10);      // wait for release so it isn't read as a tap
  delay(1200);
}

void setup() {
  pinMode(PIN_KEY, INPUT_PULLUP);
  pinMode(TFT_BL, OUTPUT);
#if defined(VBAT_ENABLE)
  pinMode(VBAT_ENABLE, OUTPUT);
#endif
  analogReadResolution(12);
#if defined(PIN_CHARGING_CURRENT)
  pinMode(PIN_CHARGING_CURRENT, OUTPUT);             // LOW = 100 mA USB-C charging (board default is 50 mA);
  digitalWrite(PIN_CHARGING_CURRENT, LOW);           // fine for any 250 mAh+ cell
#endif

#if NOD_MIRROR
  Serial.begin(115200);                               // USB serial for the screen mirror; doesn't wait for a computer
#endif
  tft.init(SW, SH);
  tft.setSPISpeed(32000000);
  tft.setRotation(0);
  bootNameMode();
  frame = new GFXcanvas16(SW, SH);
  if (!frame || !frame->getBuffer()) {
    tft.fillScreen(ST77XX_RED);                       // not enough RAM for the frame buffer
    frame = nullptr;
  }
#if USE_KEY_LED
  keyLed.begin();
  keyLed.setBrightness(80);
#endif

  Bluefruit.configPrphBandwidth(BANDWIDTH_MAX);       // bigger MTU, fewer packets per line
  Bluefruit.begin(MAX_CONN, 0);
  Bluefruit.setTxPower(0);
  ble_gap_addr_t a = Bluefruit.getAddr();
  snprintf(deviceName, sizeof(deviceName), appMode ? "Claude-Nod-%02X%02X" : "Nod-%02X%02X",
           a.addr[1], a.addr[0]);                     // Claude desktop picker needs the "Claude" prefix
  Bluefruit.setName(deviceName);
  Bluefruit.Periph.setConnectCallback(onConnect);
  Bluefruit.Periph.setDisconnectCallback(onDisconnect);
  Bluefruit.Periph.setConnInterval(24, 48);

#if NOD_SECURE
  Bluefruit.Security.setIOCaps(true, false, false);   // DisplayOnly: we show the passkey
  Bluefruit.Security.setMITM(true);
  Bluefruit.Security.setPairPasskeyCallback(onPasskey);
  Bluefruit.Security.setPairCompleteCallback(onPairComplete);
  const SecureMode_t SEC = SECMODE_ENC_WITH_MITM;
#else
  const SecureMode_t SEC = SECMODE_OPEN;
#endif

  bledis.setManufacturer("Nod");
  bledis.setModel("Nod key v1");
  bledis.begin();

  nusSvc.begin();
  uint16_t mtu = Bluefruit.getMaxMtu(BLE_GAP_ROLE_PERIPH);
  nusTx.setProperties(CHR_PROPS_NOTIFY);
  nusTx.setPermission(SEC, SECMODE_NO_ACCESS);
  nusTx.setMaxLen(mtu);
  nusTx.begin();
  nusRx.setProperties(CHR_PROPS_WRITE | CHR_PROPS_WRITE_WO_RESP);
  nusRx.setPermission(SECMODE_NO_ACCESS, SEC);
  nusRx.setMaxLen(mtu);
  nusRx.setWriteCallback(onRxWrite, false);           // runs in the BLE task; only copies bytes
  nusRx.begin();

  Bluefruit.Advertising.addFlags(BLE_GAP_ADV_FLAGS_LE_ONLY_GENERAL_DISC_MODE);
  Bluefruit.Advertising.addTxPower();
  Bluefruit.Advertising.addService(nusSvc);
  Bluefruit.ScanResponse.addName();
  Bluefruit.Advertising.restartOnDisconnect(true);
  Bluefruit.Advertising.setInterval(160, 800);
  Bluefruit.Advertising.setFastTimeout(30);
  Bluefruit.Advertising.start(0);

  readBattery();
  wake();
  render();
}

void loop() {
  static uint32_t lastFrame = 0, lastBat = 0;
  drainLines();
  pollKey();
  uint32_t now = millis();
  if (now - lastBat > 60000) { lastBat = now; readBattery(); }
  if (busy()) {
    if (now - lastFrame >= 33) {
      lastFrame = now;
      animate();
      render();
      updateLights();
    }
  } else if (now - lastFrame >= 1000) {
    lastFrame = now;
    animate();
    render();
    updateLights();
  }
  delay(2);
}
