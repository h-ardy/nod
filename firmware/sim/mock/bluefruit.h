// Bluefruit API surface used by the Nod firmware, backed by TCP sockets in the simulator.
#pragma once
#include <Arduino.h>
typedef int err_t;
enum SecureMode_t { SECMODE_NO_ACCESS = 0x00, SECMODE_OPEN = 0x11, SECMODE_ENC_NO_MITM = 0x21, SECMODE_ENC_WITH_MITM = 0x31 };
#define CHR_PROPS_NOTIFY 0x10
#define CHR_PROPS_WRITE 0x08
#define CHR_PROPS_WRITE_WO_RESP 0x04
#define BANDWIDTH_MAX 4
#define BLE_GAP_ROLE_PERIPH 1
#define BLE_GAP_ADV_FLAGS_LE_ONLY_GENERAL_DISC_MODE 0x06
struct ble_gap_addr_t { uint8_t addr[6]; };
extern const uint8_t BLEUART_UUID_SERVICE[16], BLEUART_UUID_CHR_RXD[16], BLEUART_UUID_CHR_TXD[16];

class BLEService {
 public:
  BLEService(const uint8_t *) {}
  err_t begin() { return 0; }
};
class BLECharacteristic {
 public:
  typedef void (*write_cb_t)(uint16_t conn_hdl, BLECharacteristic *chr, uint8_t *data, uint16_t len);
  BLECharacteristic(const uint8_t *) {}
  void setProperties(uint8_t) {}
  void setPermission(SecureMode_t, SecureMode_t) {}
  void setMaxLen(uint16_t n) { maxLen = n; }
  void setWriteCallback(write_cb_t fp, bool = true) { wcb = fp; }
  err_t begin() { return 0; }
  bool notify(uint16_t conn_hdl, const void *data, uint16_t len);   // harness sends to the socket
  write_cb_t wcb = nullptr;
  uint16_t maxLen = 20;
};
class BLEDis {
 public:
  void setManufacturer(const char *) {}
  void setModel(const char *) {}
  err_t begin() { return 0; }
};
class BLEConnection {
 public:
  bool secured() { return false; }
};
typedef void (*ble_connect_callback_t)(uint16_t);
typedef void (*ble_disconnect_callback_t)(uint16_t, uint8_t);
struct BLEPeriphSim {
  ble_connect_callback_t ccb = nullptr;
  ble_disconnect_callback_t dcb = nullptr;
  int bondsCleared = 0;
  void setConnectCallback(ble_connect_callback_t f) { ccb = f; }
  void setDisconnectCallback(ble_disconnect_callback_t f) { dcb = f; }
  bool setConnInterval(uint16_t, uint16_t) { return true; }
  void clearBonds() { bondsCleared++; }
};
struct BLEAdvSim {
  int starts = 0;
  void addFlags(uint8_t) {}
  bool addTxPower() { return true; }
  bool addService(BLEService &) { return true; }
  void restartOnDisconnect(bool) {}
  void setInterval(uint16_t, uint16_t) {}
  void setFastTimeout(uint16_t) {}
  bool start(int) { starts++; return true; }
};
struct BLEScanRespSim { bool addName() { return true; } };
struct BLESecuritySim {
  typedef bool (*pair_passkey_cb_t)(uint16_t, uint8_t const[6], bool);
  typedef void (*pair_complete_cb_t)(uint16_t, uint8_t);
  void setIOCaps(bool, bool, bool) {}
  void setMITM(bool) {}
  bool setPairPasskeyCallback(pair_passkey_cb_t f) { pk = f; return true; }
  void setPairCompleteCallback(pair_complete_cb_t f) { pc = f; }
  pair_passkey_cb_t pk = nullptr;
  pair_complete_cb_t pc = nullptr;
};
class AdafruitBluefruitSim {
 public:
  BLEPeriphSim Periph;
  BLEAdvSim Advertising;
  BLEScanRespSim ScanResponse;
  BLESecuritySim Security;
  char name[32] = {0};
  void configPrphBandwidth(uint8_t) {}
  bool begin(uint8_t = 1, uint8_t = 0) { return true; }
  bool setTxPower(int8_t) { return true; }
  ble_gap_addr_t getAddr() { return ble_gap_addr_t{{0x3C, 0xA1, 0, 0, 0, 0}}; }
  void setName(const char *n) { strncpy(name, n, sizeof(name) - 1); }
  uint8_t connected();                 // harness: number of open sockets
  bool connected(uint16_t conn_hdl);   // harness
  BLEConnection *Connection(uint16_t conn_hdl);
  uint16_t getMaxMtu(uint8_t) { return 247; }
};
extern AdafruitBluefruitSim Bluefruit;
