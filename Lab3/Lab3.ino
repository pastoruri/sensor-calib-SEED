#include <Wire.h>
#include <Adafruit_VL53L1X.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>
#include <time.h>
#include <sys/time.h>

Adafruit_VL53L1X vl53 = Adafruit_VL53L1X();
#define TCA_ADDRESS       0x70
#define MAX_BUFFER_SIZE   4000
#define BLOCK_SIZE        10
#define ACK_TIMEOUT_MS    5000

BLECharacteristic *pCharacteristic;
bool deviceConnected = false;

#define SERVICE_UUID        "12345678-1234-1234-1234-1234567890ab"
#define CHARACTERISTIC_UUID "abcd1234-5678-90ab-cdef-1234567890ab"

const char SAMPLE_EX[] = "1747410717.502,122,397,260";

int bufferSize    = 4000;
int sampleRateHz  = 2;

typedef struct {
  uint64_t timestamp;
  int16_t dist1, dist2, dist3;
} SensorData;

SensorData dataBuffer[MAX_BUFFER_SIZE];
int dataIndex   = 0;
bool recording  = false;

uint64_t startEpochMs    = 0;
unsigned long syncMillis = 0;
unsigned long lastSampleTime = 0;

volatile int lastAckBlock = -1;

enum State { IDLE, PREPARE_SEND, SENDING_BLOCK, WAITING_ACK, FINISHED };
State currentState = IDLE;
unsigned long stateStartTime = 0;
int blockIndex = 0;

void tca_select(uint8_t channel) {
  if (channel > 7) return;
  Wire.beginTransmission(TCA_ADDRESS);
  Wire.write(1 << channel);
  Wire.endTransmission();
}

class MyServerCallbacks : public BLEServerCallbacks {
  void onConnect(BLEServer *pServer) override {
    deviceConnected = true;
    int usedSamples = dataIndex;
    size_t sampleSize = strlen(SAMPLE_EX);
    size_t usedBytes = usedSamples * sampleSize;
    char info[64];
    snprintf(info, sizeof(info), "ESP32 almacenadas: %d muestras (~%u bytes)", usedSamples, (unsigned)usedBytes);
    pCharacteristic->setValue(info);
    pCharacteristic->notify();
    Serial.print("🔔 Reconectado: "); Serial.println(info);
  }

  void onDisconnect(BLEServer *pServer) override {
    deviceConnected = false;
    Serial.println("⚠️ BLE desconectado, grabación continúa...");
    pServer->getAdvertising()->start();
  }
};

class CharCallback : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic *c) override {
    String msg = c->getValue().c_str();
    Serial.print("⚡ Recibí: "); Serial.println(msg);

    if (msg.startsWith("SYNC:")) {
      int Y,M,D,h,m,s,ms;
      if (sscanf(msg.c_str() + 5, "%d-%d-%d %d:%d:%d.%d", &Y,&M,&D,&h,&m,&s,&ms) == 7) {
        struct tm tm = {};
        tm.tm_year = Y - 1900; tm.tm_mon = M - 1; tm.tm_mday = D;
        tm.tm_hour = h; tm.tm_min = m; tm.tm_sec = s;
        time_t sec = mktime(&tm);
        startEpochMs = uint64_t(sec) * 1000 + ms;

        dataIndex = 0;
        for (int ch = 1; ch <= 3; ch++) {
          tca_select(ch);
          vl53.stopRanging(); delay(10);
          vl53.startRanging(); delay(10);
        }
        recording = true;
        syncMillis = millis();
        lastSampleTime = syncMillis - (1000UL / sampleRateHz);
        Serial.println("🎬 SYNC OK, grabando...");
      }
    }
    else if (msg == "FETCH") {
      Serial.println("📦 FETCH solicitado");
      recording = false;
      blockIndex = 0;
      lastAckBlock = -1;
      currentState = PREPARE_SEND;
      stateStartTime = millis();
    }
    else if (msg == "RESET") {
      dataIndex = 0;
      recording = false;
      currentState = IDLE;
      Serial.println("♻️ RESET");
    }
    else if (msg.startsWith("SET:")) {
      int comma = msg.indexOf(',');
      if (comma > 4) {
        bufferSize = constrain(msg.substring(4, comma).toInt(), 1, MAX_BUFFER_SIZE);
        sampleRateHz = 1;
        if ( msg.substring(comma+1).toInt() > 1){
          sampleRateHz = msg.substring(comma+1).toInt();
        }
        Serial.printf("⚙️ SET buf=%d Hz=%d\n", bufferSize, sampleRateHz);
      }
    }
    else if (msg.startsWith("ACK:BLOCK_")) {
      lastAckBlock = msg.substring(10).toInt();
      Serial.printf("✅ ACK: bloque %d\n", lastAckBlock);
    }
    else if (msg == "GET_MEM") {
      size_t freeHeap = ESP.getFreeHeap();
      String resp = "FREE_HEAP:" + String(freeHeap);
      pCharacteristic->setValue(resp);
      pCharacteristic->notify();
      Serial.printf("📊 Memoria libre: %u bytes\n", (unsigned)freeHeap);
    }
  }
};

void setup() {
  Serial.begin(115200);
  Wire.begin();

  for (int ch = 1; ch <= 3; ch++) {
    tca_select(ch);
    if (vl53.begin()) {
      vl53.startRanging();
      Serial.printf("✅ Sensor %d OK\n", ch);
    } else {
      Serial.printf("❌ Sensor %d FAIL\n", ch);
    }
    delay(200);
  }

  BLEDevice::init("ESP32-VL53L1X");
  BLEServer *pServer = BLEDevice::createServer();
  pServer->setCallbacks(new MyServerCallbacks());

  BLEService *pService = pServer->createService(SERVICE_UUID);
  pCharacteristic = pService->createCharacteristic(
    CHARACTERISTIC_UUID,
    BLECharacteristic::PROPERTY_READ    |
    BLECharacteristic::PROPERTY_NOTIFY  |
    BLECharacteristic::PROPERTY_WRITE   |
    BLECharacteristic::PROPERTY_WRITE_NR
  );
  pCharacteristic->addDescriptor(new BLE2902());
  pCharacteristic->setCallbacks(new CharCallback());
  pCharacteristic->setValue("Esperando SYNC...");
  pService->start();
  pServer->getAdvertising()->start();
  Serial.println("🔵 BLE listo");
}

void loop() {
  if (recording && dataIndex < bufferSize) {
    unsigned long now = millis();
    if (now - lastSampleTime >= (1000UL / sampleRateHz)) {
      lastSampleTime = now;
      uint64_t ts_ms = startEpochMs + (now - syncMillis);
      SensorData d{ ts_ms, -1, -1, -1 };

      for (int ch = 1; ch <= 3; ch++) {
        tca_select(ch);
        delay(10);
        if (vl53.dataReady()) {
          int dist = vl53.distance();
          if (ch == 1) d.dist1 = dist;
          else if (ch == 2) d.dist2 = dist;
          else d.dist3 = dist;
          vl53.clearInterrupt();
        }
        delay(30);
      }

      dataBuffer[dataIndex++] = d;
      Serial.printf("📍 %lu.%03u,%d,%d,%d\n",
        (unsigned long)(ts_ms / 1000),
        (unsigned int)(ts_ms % 1000),
        d.dist1, d.dist2, d.dist3);
    }
  }

  if (currentState == PREPARE_SEND) {
    Serial.println("📤 Enviando bloque 0...");
    currentState = SENDING_BLOCK;
  }
  else if (currentState == SENDING_BLOCK) {
    int start = blockIndex * BLOCK_SIZE;
    int end = min(start + BLOCK_SIZE, dataIndex);

    for (int i = start; i < end; i++) {
      SensorData d = dataBuffer[i];
      char out[80];
      sprintf(out, "%d,%lu.%03u,%d,%d,%d",
        i,
        (unsigned long)(d.timestamp / 1000),
        (unsigned)(d.timestamp % 1000),
        d.dist1, d.dist2, d.dist3);
      pCharacteristic->setValue(out);
      pCharacteristic->notify();
      delay(40);
    }

    char wait[32];
    sprintf(wait, "WAIT_ACK:%d", blockIndex);
    pCharacteristic->setValue(wait);
    pCharacteristic->notify();

    currentState = WAITING_ACK;
    stateStartTime = millis();
  }
  else if (currentState == WAITING_ACK) {
    if (lastAckBlock == blockIndex) {
      blockIndex++;
      if (blockIndex * BLOCK_SIZE >= dataIndex) {
        pCharacteristic->setValue("END");
        pCharacteristic->notify();
        stateStartTime = millis();
        currentState = FINISHED;
        Serial.println("🏁 Envío completo, esperando ACK:BLOCK_9999");
      } else {
        currentState = SENDING_BLOCK;
      }
    }
    else if (millis() - stateStartTime > ACK_TIMEOUT_MS) {
      Serial.printf("❌ Timeout esperando ACK bloque %d\n", blockIndex);
      currentState = IDLE;
    }
  }
  else if (currentState == FINISHED) {
    if (lastAckBlock == 9999) {
      Serial.println("✅ ACK final recibido. Transferencia completa.");
      currentState = IDLE;
    }
    else if (millis() - stateStartTime > ACK_TIMEOUT_MS) {
      Serial.println("❌ Timeout esperando ACK final");
      currentState = IDLE;
    }
  }
}
