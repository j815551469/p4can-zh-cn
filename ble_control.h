#pragma once
// ─── BLE 控制通道（手机不连热点也能控制） ───────────────────────────────
//
// 角色：ESP32 作 peripheral（GATT server），手机作 central。
// 传输：
//   CMD 特征（Write）  ：一行文本  "<id> <METHOD> <PATH>"
//                        例：7 POST /api/nag/update?enabled=1
//   RSP 特征（Notify） ：二进制分片
//                        [id_lo][id_hi][seq][flags] + data (最多 16B)
//                        flags & 0x01 = 最后一片
//                        拼接后的文本 = "<id>|<status>|<body>"
//   STA 特征（Read）   ：状态 JSON（当前实现/命令数/错误）
//
// 命令通过 127.0.0.1 回环调用本机 WebServer，后端处理器一行不用改；
// 只放行白名单里的端点，OTA / 系统重置 / profile 变更一律拒绝。
// 写入要求加密链路（Just Works 配对 + 绑定），未配对设备写不进来。

#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLECharacteristic.h>
#include <BLE2902.h>
#include <Preferences.h>
#include <HTTPClient.h>
#include <WiFi.h>
#include <BLEDescriptor.h>

#define BLE_CTRL_SERVICE_UUID "50433441-0000-1000-8000-00805F9B34FB"
#define BLE_CTRL_CMD_UUID     "50433441-0001-1000-8000-00805F9B34FB"
#define BLE_CTRL_RSP_UUID     "50433441-0002-1000-8000-00805F9B34FB"
#define BLE_CTRL_STA_UUID     "50433441-0003-1000-8000-00805F9B34FB"
#define BLE_CTRL_NAME         "P4-CAN-BLE"
#define BLE_CTRL_BODY_MAX     4096u

struct BleCtrlCmd {
  uint16_t id;
  char method[6];
  char path[120];
};

static bool bleCtrlEnabled = false;
static bool bleCtrlRunning = false;
static bool bleCtrlConnected = false;
static BLEServer *bleCtrlServer = nullptr;
static BLECharacteristic *bleCtrlCmdChar = nullptr;
static BLECharacteristic *bleCtrlRspChar = nullptr;
static BLECharacteristic *bleCtrlStaChar = nullptr;
static QueueHandle_t bleCtrlQueue = nullptr;
static TaskHandle_t bleCtrlTaskHandle = nullptr;
static char bleCtrlLastError[48] = "";
// 最近一次命令的结果，直接读 STA 特征就能看到，便于用 nRF Connect 手工验证
static uint16_t bleCtrlLastId = 0;
static int bleCtrlLastStatus = 0;
static char bleCtrlLastBody[300] = "";
static uint32_t bleCtrlCmdCount = 0;
static uint32_t bleCtrlDropCount = 0;

static void bleCtrlSetError(const char *text) {
  snprintf(bleCtrlLastError, sizeof(bleCtrlLastError), "%s", text ? text : "");
}

static bool bleCtrlActive() { return bleCtrlRunning; }

// ── 端点策略：放行 /api/*，危险端点见下面的拒绝前缀 ──────────────────
// 危险/与本机强相关的端点不予放行；其余 /api/* 都允许，整站才能走 BLE。
static const char *const BLE_CTRL_DENY_PREFIX[] = {
    "/update",              // OTA
    "/api/system/",         // 重置、重启、重初始化
    "/api/profile/",        // 改车型档案
    "/api/wifi/",           // 改热点
    "/api/s3xy/",           // 按键配对/重置
    "/api/researchcapture/",// 大块抓包
    "/api/drivermonitor/",
    "/api/ble/",            // 不让 BLE 自己关自己
};

static bool bleCtrlPathAllowed(const char *method, const char *pathWithQuery) {
  if (!method || !pathWithQuery) return false;
  if (strcmp(method, "GET") != 0 && strcmp(method, "POST") != 0) return false;
  char path[120];
  size_t n = 0;
  while (pathWithQuery[n] && pathWithQuery[n] != '?' && n < sizeof(path) - 1) {
    path[n] = pathWithQuery[n];
    n++;
  }
  path[n] = '\0';
  if (strncmp(path, "/api/", 5) != 0) return false;
  // 页面启动时要读的几个只读端点，虽在被拒前缀下，但本身无害。
  if (strcmp(method, "GET") == 0) {
    if (strcmp(path, "/api/s3xy/stats") == 0) return true;
    if (strcmp(path, "/api/ble/status") == 0) return true;
    if (strcmp(path, "/api/wifi/status") == 0) return true;
    // 页面启动就靠它判断是否处于车型档案设置模式；读不到会误显示“首次启动”。
    if (strcmp(path, "/api/profile/status") == 0) return true;
    // 诊断页的只读数据（几 KB）。
    if (strcmp(path, "/api/system/stats") == 0) return true;
  }
  for (const char *deny : BLE_CTRL_DENY_PREFIX) {
    const size_t len = strlen(deny);
    if (strncmp(path, deny, len) == 0) return false;
  }
  return true;
}

static String bleCtrlJsonEscape(const char *in) {
  String out;
  for (const char *c = in; c && *c; c++) {
    if (*c == '"' || *c == '\\') out += '\\';
    if (*c == '\n' || *c == '\r') { out += ' '; continue; }
    out += *c;
  }
  return out;
}

static String bleCtrlStatusJson() {
  String j = "{\"enabled\":";
  j += bleCtrlEnabled ? "true" : "false";
  j += ",\"running\":";
  j += bleCtrlRunning ? "true" : "false";
  j += ",\"connected\":";
  j += bleCtrlConnected ? "true" : "false";
  j += ",\"commands\":";
  j += String((unsigned long)bleCtrlCmdCount);
  j += ",\"dropped\":";
  j += String((unsigned long)bleCtrlDropCount);
  j += ",\"error\":\"";
  j += bleCtrlLastError;
  j += "\",\"last\":{\"id\":";
  j += String((unsigned)bleCtrlLastId);
  j += ",\"status\":";
  j += String(bleCtrlLastStatus);
  j += ",\"body\":\"";
  j += bleCtrlJsonEscape(bleCtrlLastBody);
  j += "\"}}";
  return j;
}

static void bleCtrlNotifyText(uint16_t id, int status, const String &body) {
  if (!bleCtrlRunning || !bleCtrlRspChar || !bleCtrlConnected) return;
  String msg = String((unsigned)id) + "|" + String(status) + "|" + body;
  const size_t total = msg.length();
  // 按协商到的 MTU 分片：手机端 requestMtu(185) 后每片可发 ~180 B，
  // 否则整站页面（几 KB 的 JSON）会慢到不可用。
  size_t chunk = 16;
  if (bleCtrlServer) {
    const uint16_t mtu = bleCtrlServer->getPeerMTU(bleCtrlServer->getConnId());
    if (mtu > 27) {
      chunk = (size_t)mtu - 3 - 4;   // 去掉 ATT 头与我们的 4 字节帧头
      if (chunk > 180) chunk = 180;
    }
  }
  uint8_t seq = 0;
  for (size_t off = 0; off < total; off += chunk) {
    const size_t n = (total - off > chunk) ? chunk : (total - off);
    const bool last = (off + n >= total);
    uint8_t frame[4 + chunk];
    frame[0] = (uint8_t)(id & 0xFF);
    frame[1] = (uint8_t)(id >> 8);
    frame[2] = seq++;
    frame[3] = last ? 0x01 : 0x00;
    memcpy(frame + 4, msg.c_str() + off, n);
    bleCtrlRspChar->setValue(frame, 4 + n);
    bleCtrlRspChar->notify();
    vTaskDelay(pdMS_TO_TICKS(4));
  }
}

static bool bleCtrlParse(const String &line, BleCtrlCmd &out) {
  String t = line;
  t.trim();
  const int sp1 = t.indexOf(' ');
  if (sp1 <= 0) return false;
  const int sp2 = t.indexOf(' ', sp1 + 1);
  if (sp2 <= sp1) return false;
  const long id = t.substring(0, sp1).toInt();
  if (id < 0 || id > 65535) return false;
  String method = t.substring(sp1 + 1, sp2);
  method.trim();
  String path = t.substring(sp2 + 1);
  path.trim();
  if (!(method == "GET" || method == "POST")) return false;
  if (path.length() < 2 || path[0] != '/') return false;
  if (path.length() >= (int)sizeof(out.path)) return false;
  out.id = (uint16_t)id;
  memset(out.method, 0, sizeof(out.method));
  memset(out.path, 0, sizeof(out.path));
  strncpy(out.method, method.c_str(), sizeof(out.method) - 1);
  strncpy(out.path, path.c_str(), sizeof(out.path) - 1);
  return true;
}

// 回环调用本机 WebServer：复用现有 /api/* 处理器
static bool bleCtrlLoopback(const BleCtrlCmd &c, int &status, String &body) {
  HTTPClient http;
  WiFiClient client;
  http.setConnectTimeout(1500);
  http.setTimeout(3000);
  // 用 AP 自己的地址做回环（lwIP 不一定编了 127.0.0.1 回环接口）；
  // BLE 只在 AP 起来之后启动，所以这里一定有值。
  IPAddress host = WiFi.softAPIP();
  String url = String("http://") + host.toString() + c.path;
  if (!http.begin(client, url)) {
    bleCtrlSetError("loopback begin failed");
    return false;
  }
  http.addHeader("X-P4-BLE", "1");
  status = (strcmp(c.method, "POST") == 0) ? http.POST("") : http.GET();
  if (status > 0) body = http.getString();
  http.end();
  if (status <= 0) {
    bleCtrlSetError("loopback request failed");
    return false;
  }
  return true;
}

static void bleCtrlTaskFn(void *arg) {
  (void)arg;
  BleCtrlCmd cmd;
  for (;;) {
    if (xQueueReceive(bleCtrlQueue, &cmd, portMAX_DELAY) != pdTRUE) continue;
    int status = 0;
    String body;
    if (!bleCtrlLoopback(cmd, status, body)) {
      status = 0;
      body = "loopback failed";
    }
    if (body.length() > BLE_CTRL_BODY_MAX) body = body.substring(0, BLE_CTRL_BODY_MAX);
    bleCtrlLastId = cmd.id;
    bleCtrlLastStatus = status;
    snprintf(bleCtrlLastBody, sizeof(bleCtrlLastBody), "%s", body.c_str());
    if (bleCtrlStaChar) bleCtrlStaChar->setValue(bleCtrlStatusJson().c_str());
    bleCtrlNotifyText(cmd.id, status, body);
  }
}

class BleCtrlServerCallbacks : public BLEServerCallbacks {
  void onConnect(BLEServer *) override {
    bleCtrlConnected = true;
    bleCtrlSetError("");
  }
  void onDisconnect(BLEServer *) override {
    bleCtrlConnected = false;
    if (bleCtrlRunning) BLEDevice::startAdvertising();
  }
};

class BleCtrlCmdCallbacks : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic *ch) override {
    const String value = ch->getValue();
    BleCtrlCmd cmd;
    if (!bleCtrlParse(value, cmd)) {
      bleCtrlDropCount++;
      bleCtrlSetError("bad command format");
      // id 都解析不出来时用 0 号回一个错误，方便手机侧定位
      bleCtrlNotifyText(0, 400, "bad command: expect \"<id> <GET|POST> <path>\"");
      return;
    }
    if (!bleCtrlPathAllowed(cmd.method, cmd.path)) {
      bleCtrlDropCount++;
      bleCtrlSetError("endpoint not allowed");
      bleCtrlNotifyText(cmd.id, 403, "endpoint not allowed");
      return;
    }
    if (!bleCtrlQueue || xQueueSend(bleCtrlQueue, &cmd, 0) != pdTRUE) {
      bleCtrlDropCount++;
      bleCtrlSetError("queue full");
      bleCtrlNotifyText(cmd.id, 429, "busy");
      return;
    }
    bleCtrlCmdCount++;
  }
};

static BleCtrlServerCallbacks bleCtrlServerCb;
static BleCtrlCmdCallbacks bleCtrlCmdCb;

static void bleCtrlLoadConfig() {
  Preferences p;
  if (p.begin("blectl", true)) {
    bleCtrlEnabled = p.getBool("on", false);
    p.end();
  }
}

static bool bleCtrlPersist(bool on) {
  Preferences p;
  if (!p.begin("blectl", false)) return false;
  const size_t n = p.putBool("on", on);
  p.end();
  if (n == 0) return false;
  bleCtrlEnabled = on;
  return true;
}

static bool bleCtrlStart() {
  if (bleCtrlRunning) return true;
  if (!p4NetworkAllowsBle()) {
    bleCtrlSetError("AP not ready");
    return false;
  }
  if (!BLEDevice::getInitialized() && !BLEDevice::init(BLE_CTRL_NAME)) {
    bleCtrlSetError("BLE host init failed");
    return false;
  }
  // Just Works + 绑定 + Secure Connections：写入要求加密链路即可挡住陌生人
  BLESecurity::setCapability(ESP_IO_CAP_NONE);
  BLESecurity::setAuthenticationMode(true, false, true);
  BLESecurity::setKeySize(16);
  BLESecurity::setInitEncryptionKey(ESP_BLE_ENC_KEY_MASK | ESP_BLE_ID_KEY_MASK);
  BLESecurity::setRespEncryptionKey(ESP_BLE_ENC_KEY_MASK | ESP_BLE_ID_KEY_MASK);

  if (bleCtrlServer) {
    // 服务已建过（之前 disable 过），只需恢复广播，避免重复建服务。
    BLEDevice::startAdvertising();
    bleCtrlRunning = true;
    bleCtrlSetError("");
    return true;
  }
  if (!bleCtrlServer) {
    bleCtrlServer = BLEDevice::createServer();
    if (!bleCtrlServer) {
      bleCtrlSetError("GATT server create failed");
      return false;
    }
    bleCtrlServer->setCallbacks(&bleCtrlServerCb);
  }
  BLEService *svc = bleCtrlServer->createService(BLE_CTRL_SERVICE_UUID);
  if (!svc) {
    bleCtrlSetError("service create failed");
    return false;
  }
  bleCtrlCmdChar = svc->createCharacteristic(
      BLE_CTRL_CMD_UUID, BLECharacteristic::PROPERTY_WRITE | BLECharacteristic::PROPERTY_WRITE_NR);
  bleCtrlCmdChar->setCallbacks(&bleCtrlCmdCb);
  bleCtrlCmdChar->setAccessPermissions(ESP_GATT_PERM_WRITE_ENCRYPTED);

  bleCtrlRspChar = svc->createCharacteristic(BLE_CTRL_RSP_UUID, BLECharacteristic::PROPERTY_NOTIFY);
  bleCtrlRspChar->addDescriptor(new BLE2902());
  bleCtrlRspChar->setAccessPermissions(ESP_GATT_PERM_READ_ENCRYPTED);

  bleCtrlStaChar = svc->createCharacteristic(BLE_CTRL_STA_UUID, BLECharacteristic::PROPERTY_READ);
  bleCtrlStaChar->setAccessPermissions(ESP_GATT_PERM_READ_ENCRYPTED);
  bleCtrlStaChar->setValue(bleCtrlStatusJson().c_str());

  svc->start();

  BLEAdvertising *adv = BLEDevice::getAdvertising();
  // 与 S3XY 共用同一个 BLE host：谁先 init 谁定 GAP 名字（S3XY 那边叫
  // P4-CAN_S3XY_MULTI）。这里强制把广播名改成控制通道的名字，避免手机扫到两台。
  adv->setName(BLE_CTRL_NAME);
  adv->addServiceUUID(BLE_CTRL_SERVICE_UUID);
  adv->setScanResponse(true);
  BLEDevice::startAdvertising();

  if (!bleCtrlQueue) bleCtrlQueue = xQueueCreate(16, sizeof(BleCtrlCmd));
  if (!bleCtrlQueue) {
    bleCtrlSetError("queue create failed");
    return false;
  }
  if (!bleCtrlTaskHandle) {
    if (xTaskCreatePinnedToCore(bleCtrlTaskFn, "bleCtrl", 8192, nullptr, 1, &bleCtrlTaskHandle, 0) != pdPASS) {
      bleCtrlTaskHandle = nullptr;
      bleCtrlSetError("task create failed");
      return false;
    }
  }
  bleCtrlRunning = true;
  bleCtrlSetError("");
  return true;
}

static void bleCtrlStop() {
  if (!bleCtrlRunning) return;
  BLEDevice::stopAdvertising();
  bleCtrlConnected = false;
  bleCtrlRunning = false;
}

// webTask 在热点起来之后调用
static void bleCtrlBootStart() {
  bleCtrlLoadConfig();
  if (!bleCtrlEnabled) return;
  bleCtrlStart();
}
