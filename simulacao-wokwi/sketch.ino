#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <Wire.h>
#include <WiFi.h>
#include <PubSubClient.h>

Adafruit_MPU6050 mpu;

// --- Configuracao MQTT ---
// No Wokwi, o ESP32 acessa a internet de verdade pela rede "Wokwi-GUEST" (sem senha).
const char* WIFI_SSID = "Wokwi-GUEST";
const char* WIFI_SENHA = "";

// Broker publico de teste. Prefixo de topico proprio para nao colidir com outros usuarios.
const char* MQTT_BROKER = "broker.hivemq.com";
const int MQTT_PORTA = 1883;
const char* TOPICO_PREFIXO = "projetopet/c282cf79";
char topicoTelemetria[64];
char topicoResumo[64];

WiFiClient wifiClient;
PubSubClient mqttClient(wifiClient);
unsigned long ultimaTentativaMqtt = 0;

const float GRAVIDADE = 9.80665;
const float LIMIAR_PASSO = 1.2;         // aceleração dinâmica (m/s^2) para contar um passo
const unsigned long DEBOUNCE_PASSO_MS = 300;
const float ALPHA_INTENSIDADE = 0.2;    // suavização (EMA) da intensidade de movimento

// Limiares de intensidade suavizada (m/s^2) que definem o estado da pessoa
const float LIMIAR_CAMINHANDO = 1.0;
const float LIMIAR_CORRENDO   = 4.0;

const float COMPRIMENTO_PASSO_M = 0.7;  // distância média por passo, usada para estimar deslocamento

// Duração de um "dia" simulado, para fechar os cálculos diários sem esperar 24h de verdade.
// Trocar para 86400000UL (24h) em um deploy real.
const unsigned long DURACAO_DIA_MS = 60000UL;

enum EstadoPessoa { PARADO = 0, CAMINHANDO = 1, CORRENDO = 2 };

unsigned long ultimoPasso = 0;
unsigned long inicioDia = 0;

float intensidadeSuavizada = 0;
float pulsoPasso = 0;

unsigned long passosHoje = 0;
unsigned long passosTotal = 0;
float distanciaHojeM = 0;
float distanciaTotalM = 0;

void conectarWiFi() {
  Serial.print("Conectando ao WiFi");
  WiFi.begin(WIFI_SSID, WIFI_SENHA);
  while (WiFi.status() != WL_CONNECTED) {
    delay(300);
    Serial.print(".");
  }
  Serial.print(" conectado! IP: ");
  Serial.println(WiFi.localIP());
}

void reconectarMqtt() {
  if (mqttClient.connected()) return;

  unsigned long agora = millis();
  if (agora - ultimaTentativaMqtt < 3000) return;  // evita martelar o broker
  ultimaTentativaMqtt = agora;

  String clientId = "xiao-pet-" + String((uint32_t)ESP.getEfuseMac(), HEX);
  Serial.print("Conectando ao broker MQTT...");
  if (mqttClient.connect(clientId.c_str())) {
    Serial.println(" conectado!");
  } else {
    Serial.print(" falhou, rc="); Serial.println(mqttClient.state());
  }
}

void setup() {
  Serial.begin(115200);
  Wire.begin(D4, D5);

  if (!mpu.begin()) {
    Serial.println("Falha ao encontrar o MPU6050!");
    while (1) delay(10);
  }
  Serial.println("MPU6050 conectado!");

  mpu.setAccelerometerRange(MPU6050_RANGE_8_G);
  mpu.setFilterBandwidth(MPU6050_BAND_21_HZ);

  snprintf(topicoTelemetria, sizeof(topicoTelemetria), "%s/telemetria", TOPICO_PREFIXO);
  snprintf(topicoResumo, sizeof(topicoResumo), "%s/resumo", TOPICO_PREFIXO);

  conectarWiFi();
  mqttClient.setServer(MQTT_BROKER, MQTT_PORTA);
  mqttClient.setBufferSize(384);  // payload JSON + topico passam do buffer padrao de 128 bytes

  inicioDia = millis();
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    conectarWiFi();
  }
  reconectarMqtt();
  mqttClient.loop();

  sensors_event_t a, g, temp;
  mpu.getEvent(&a, &g, &temp);

  unsigned long agora = millis();

  float magnitude = sqrt(a.acceleration.x * a.acceleration.x +
                          a.acceleration.y * a.acceleration.y +
                          a.acceleration.z * a.acceleration.z);
  float acelDinamica = fabs(magnitude - GRAVIDADE);

  intensidadeSuavizada = (ALPHA_INTENSIDADE * acelDinamica) +
                          ((1 - ALPHA_INTENSIDADE) * intensidadeSuavizada);

  EstadoPessoa estado = PARADO;
  if (intensidadeSuavizada >= LIMIAR_CORRENDO) estado = CORRENDO;
  else if (intensidadeSuavizada >= LIMIAR_CAMINHANDO) estado = CAMINHANDO;

  // Detecção de passo: pico de aceleração dinâmica acima do limiar, respeitando debounce
  if (acelDinamica >= LIMIAR_PASSO && (agora - ultimoPasso) >= DEBOUNCE_PASSO_MS) {
    ultimoPasso = agora;
    passosHoje++;
    passosTotal++;
    distanciaHojeM += COMPRIMENTO_PASSO_M;
    distanciaTotalM += COMPRIMENTO_PASSO_M;
    pulsoPasso = 5.0;  // pico visível no gráfico quando um passo é contado
  } else {
    pulsoPasso *= 0.7;  // decaimento do pico até voltar à linha de base
  }

  // Linha em tempo real, formatada para o Serial Plotter (Wokwi/Arduino IDE)
  Serial.print("AccelX:"); Serial.print(a.acceleration.x);
  Serial.print(" AccelY:"); Serial.print(a.acceleration.y);
  Serial.print(" AccelZ:"); Serial.print(a.acceleration.z);
  Serial.print(" Intensidade:"); Serial.print(intensidadeSuavizada);
  Serial.print(" Estado:"); Serial.print(estado);
  Serial.print(" Passo:"); Serial.println(pulsoPasso);

  if (mqttClient.connected()) {
    char payload[220];
    snprintf(payload, sizeof(payload),
      "{\"accelX\":%.3f,\"accelY\":%.3f,\"accelZ\":%.3f,\"intensidade\":%.3f,"
      "\"estado\":%d,\"passoPulso\":%.2f,\"passosHoje\":%lu,\"passosTotal\":%lu,"
      "\"distanciaHojeM\":%.2f,\"distanciaTotalM\":%.2f}",
      a.acceleration.x, a.acceleration.y, a.acceleration.z, intensidadeSuavizada,
      (int)estado, pulsoPasso, passosHoje, passosTotal, distanciaHojeM, distanciaTotalM);
    mqttClient.publish(topicoTelemetria, payload);
  }

  // Resumo do dia simulado, impresso fora da linha do gráfico para não distorcer a escala
  if (agora - inicioDia >= DURACAO_DIA_MS) {
    float duracaoDiaS = (agora - inicioDia) / 1000.0;
    float velocidadeMediaMs = distanciaHojeM / duracaoDiaS;

    Serial.println("== Resumo diario ==");
    Serial.print("Passos: "); Serial.println(passosHoje);
    Serial.print("Distancia andada: "); Serial.print(distanciaHojeM); Serial.println(" m");
    Serial.print("Velocidade media: "); Serial.print(velocidadeMediaMs); Serial.println(" m/s");
    Serial.println("====================");

    if (mqttClient.connected()) {
      char resumoPayload[160];
      snprintf(resumoPayload, sizeof(resumoPayload),
        "{\"passos\":%lu,\"distanciaM\":%.2f,\"velocidadeMediaMs\":%.3f}",
        passosHoje, distanciaHojeM, velocidadeMediaMs);
      mqttClient.publish(topicoResumo, resumoPayload);
    }

    passosHoje = 0;
    distanciaHojeM = 0;
    inicioDia = agora;
  }

  delay(100);
}
