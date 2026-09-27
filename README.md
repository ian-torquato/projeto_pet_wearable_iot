# Wearable Fitness IoT — PET Eng Comp

Projeto desenvolvido para a etapa Core Project do processo seletivo do PET
Eng Comp (UFC). Tema sorteado: **IoT**.

## Sumário

- [O projeto implementado](#o-projeto-implementado)
- [Como rodar](#como-rodar)
- [O processo de desenvolvimento](#o-processo-de-desenvolvimento)
- [Aprendizados e desafios](#aprendizados-e-desafios)

---

## O projeto implementado

Um wearable de monitoramento de atividade física que:

- Lê um acelerômetro **MPU6050** conectado a um **XIAO ESP32-S3**
- Calcula a aceleração dinâmica (isolando a gravidade) e classifica o estado
  da pessoa em **Parado / Caminhando / Correndo**
- Detecta e conta passos, estimando distância percorrida
- Publica os dados em tempo real via **MQTT** (broker público HiveMQ)
- Exibe tudo em um **dashboard ao vivo** (Python + matplotlib), com KPIs,
  gráficos de aceleração e uma linha do tempo do estado da pessoa

**Simulação (Wokwi):** [cole aqui o link do projeto Wokwi]

### Arquitetura

```
MPU6050 → XIAO ESP32-S3 → Wi-Fi → Broker MQTT → dashboard_mqtt.py → Gráficos
```

## Como rodar

### 1. Simulação do firmware (Wokwi)

Os arquivos em `simulacao-wokwi/` (`sketch.ino`, `diagram.json`,
`libraries.txt`) podem ser importados diretamente em um novo projeto no
[Wokwi](https://wokwi.com), ou acessados pelo link da simulação acima.

### 2. Dashboard

```bash
cd dashboard
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Modo real (recebe dados do Wokwi via MQTT):
python dashboard_mqtt.py

# Modo demo (dados sintéticos, sem precisar da simulação rodando):
python dashboard_mqtt.py --demo
```

## O processo de desenvolvimento

*(preencher: linha do tempo semana 1 / semana 2, decisões técnicas —
por que MQTT, por que threshold em vez de ML, por que XIAO ESP32-S3,
por que pulso ou peitoral, etc.)*

## Aprendizados e desafios

*(preencher: dificuldades reais enfrentadas — ex: conflito de bibliotecas
MPU6050, calibração do threshold de passo, decisão de posicionamento do
sensor no corpo — e como a equipe resolveu cada uma)*

## Equipe

*(nomes dos 3 integrantes)*
