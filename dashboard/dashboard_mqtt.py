#!/usr/bin/env python3
"""Dashboard MQTT ao vivo para o projeto_pet (Wokwi + MPU6050).

Assina os topicos publicados pelo sketch.ino no broker publico broker.hivemq.com
e plota os graficos em tempo real com matplotlib.

Uso:
    pip install -r requirements.txt
    python dashboard_mqtt.py            # conecta no broker MQTT de verdade
    python dashboard_mqtt.py --demo     # gera dados sinteticos (sem broker/sensor),
                                         # util para gravar/demonstrar o dashboard
"""
import argparse
import json
import math
import random
import time
from collections import deque
from threading import Lock, Thread

import matplotlib.animation as animation
import matplotlib.pyplot as plt
import paho.mqtt.client as mqtt
from matplotlib.colors import ListedColormap
from matplotlib.gridspec import GridSpec

BROKER = "broker.hivemq.com"
PORTA = 1883
TOPICO_PREFIXO = "projetopet/c282cf79"
TOPICO_TELEMETRIA = f"{TOPICO_PREFIXO}/telemetria"
TOPICO_RESUMO = f"{TOPICO_PREFIXO}/resumo"

JANELA = 200  # pontos mantidos na janela deslizante (~20s a 100ms por amostra)

ESTADOS = {0: "Parado", 1: "Caminhando", 2: "Correndo"}

# --- Paleta (validada com scripts/validate_palette.js da skill dataviz) ---
SURFACE = "#fcfcfb"
PRIMARY_INK = "#0b0b0b"
SECONDARY_INK = "#52514e"
MUTED_INK = "#898781"
GRIDLINE = "#e1e0d9"
BASELINE = "#c3c2b7"

COR_ACCEL_X = "#2a78d6"   # categorico slot 1 - azul
COR_ACCEL_Y = "#eb6834"   # categorico slot 2 - laranja
COR_ACCEL_Z = "#1baf7a"   # categorico slot 3 - agua
COR_INTENSIDADE = "#4a3aa7"  # categorico slot 7 - violeta
COR_PASSO = "#e34948"     # categorico slot 8 - vermelho (marca evento)

COR_PARADO = MUTED_INK
COR_CAMINHANDO = "#0ca30c"  # status "good"
COR_CORRENDO = "#fab219"    # status "warning"
CORES_ESTADO = {0: COR_PARADO, 1: COR_CAMINHANDO, 2: COR_CORRENDO}

LIMIAR_CAMINHANDO = 1.0
LIMIAR_CORRENDO = 4.0

# --- Estado compartilhado entre a thread MQTT/demo e a thread de desenho ---
lock = Lock()
tempos = deque(maxlen=JANELA)
accel_x = deque(maxlen=JANELA)
accel_y = deque(maxlen=JANELA)
accel_z = deque(maxlen=JANELA)
intensidade = deque(maxlen=JANELA)
passo_pulso = deque(maxlen=JANELA)
estado_hist = deque(maxlen=JANELA)
estado_atual = [0]
ultimo_resumo = [{"passos": 0, "distanciaM": 0.0, "velocidadeMediaMs": 0.0}]
contadores = [{"passosHoje": 0, "passosTotal": 0, "distanciaHojeM": 0.0, "distanciaTotalM": 0.0}]

inicio = time.time()


def processar_telemetria(dado):
    with lock:
        tempos.append(time.time() - inicio)
        accel_x.append(dado.get("accelX", 0.0))
        accel_y.append(dado.get("accelY", 0.0))
        accel_z.append(dado.get("accelZ", 0.0))
        intensidade.append(dado.get("intensidade", 0.0))
        passo_pulso.append(dado.get("passoPulso", 0.0))
        estado = dado.get("estado", 0)
        estado_hist.append(estado)
        estado_atual[0] = estado
        contadores[0] = {
            "passosHoje": dado.get("passosHoje", 0),
            "passosTotal": dado.get("passosTotal", 0),
            "distanciaHojeM": dado.get("distanciaHojeM", 0.0),
            "distanciaTotalM": dado.get("distanciaTotalM", 0.0),
        }


def processar_resumo(dado):
    with lock:
        ultimo_resumo[0] = dado


# --- MQTT ---

def on_connect(client, userdata, flags, reason_code, properties=None):
    print(f"Conectado ao broker {BROKER} (codigo {reason_code})")
    client.subscribe(TOPICO_TELEMETRIA)
    client.subscribe(TOPICO_RESUMO)
    print(f"Inscrito em {TOPICO_TELEMETRIA} e {TOPICO_RESUMO}")


def on_message(client, userdata, msg):
    try:
        dado = json.loads(msg.payload.decode())
    except (ValueError, UnicodeDecodeError):
        return
    if msg.topic == TOPICO_TELEMETRIA:
        processar_telemetria(dado)
    elif msg.topic == TOPICO_RESUMO:
        processar_resumo(dado)


# --- Gerador sintetico (--demo): reproduz a logica do firmware em Python ---

def gerar_dados_demo():
    passos_hoje = 0
    passos_total = 0
    dist_hoje = 0.0
    dist_total = 0.0
    intensidade_suav = 0.0
    pulso = 0.0
    ultimo_passo = 0.0
    inicio_demo = time.time()
    ultimo_resumo_ts = inicio_demo

    # Ciclo de atividade: parado -> caminhando -> correndo -> caminhando -> parado
    ciclo = [(0, 4), (1, 9), (2, 7), (1, 6), (0, 4)]

    while True:
        for estado_alvo, duracao_s in ciclo:
            fim = time.time() + duracao_s
            while time.time() < fim:
                t = time.time() - inicio_demo

                if estado_alvo == 0:
                    freq, amp, passo_intervalo = 0.6, 0.15, None
                elif estado_alvo == 1:
                    freq, amp, passo_intervalo = 2.0, 1.6, 0.55
                else:
                    freq, amp, passo_intervalo = 3.2, 5.5, 0.32

                accel_din = amp * abs(math.sin(freq * t * math.pi)) + random.uniform(0, 0.15)
                ax = random.uniform(-0.3, 0.3) * (1 if estado_alvo else 0.3)
                ay = random.uniform(-0.3, 0.3) * (1 if estado_alvo else 0.3)
                az = 9.80665 + (accel_din if random.random() > 0.5 else -accel_din)

                intensidade_suav = 0.2 * accel_din + 0.8 * intensidade_suav

                agora = time.time()
                passou_passo = (
                    passo_intervalo is not None
                    and (agora - ultimo_passo) >= passo_intervalo
                    and accel_din >= 1.0
                )
                if passou_passo:
                    ultimo_passo = agora
                    passos_hoje += 1
                    passos_total += 1
                    dist_hoje += 0.7
                    dist_total += 0.7
                    pulso = 5.0
                else:
                    pulso *= 0.7

                processar_telemetria({
                    "accelX": ax, "accelY": ay, "accelZ": az,
                    "intensidade": intensidade_suav,
                    "estado": estado_alvo,
                    "passoPulso": pulso,
                    "passosHoje": passos_hoje, "passosTotal": passos_total,
                    "distanciaHojeM": dist_hoje, "distanciaTotalM": dist_total,
                })

                if agora - ultimo_resumo_ts >= 20:
                    duracao = agora - ultimo_resumo_ts
                    processar_resumo({
                        "passos": passos_hoje,
                        "distanciaM": dist_hoje,
                        "velocidadeMediaMs": dist_hoje / duracao,
                    })
                    ultimo_resumo_ts = agora

                time.sleep(0.1)


# --- Figura ---

plt.rcParams.update({
    "font.size": 11,
    "text.color": PRIMARY_INK,
    "axes.edgecolor": BASELINE,
    "axes.labelcolor": SECONDARY_INK,
    "xtick.color": MUTED_INK,
    "ytick.color": MUTED_INK,
    "axes.facecolor": SURFACE,
    "figure.facecolor": SURFACE,
})

fig = plt.figure(figsize=(12, 8.5))
fig.canvas.manager.set_window_title("Dashboard")

gs = GridSpec(4, 1, figure=fig, height_ratios=[1.3, 2.6, 2.6, 0.35],
              hspace=0.65, top=0.93, bottom=0.07, left=0.07, right=0.96)

ax_kpi = fig.add_subplot(gs[0])
ax_accel = fig.add_subplot(gs[1])
ax_intens = fig.add_subplot(gs[2], sharex=ax_accel)
ax_state = fig.add_subplot(gs[3], sharex=ax_accel)

fig.suptitle("Monitor de atividade", fontsize=16, fontweight="bold",
             color=PRIMARY_INK, x=0.07, ha="left")

# --- Cabecalho de KPIs (4 blocos fixos, nunca sobrepoe os graficos) ---
ax_kpi.axis("off")
ax_kpi.set_xlim(0, 1)
ax_kpi.set_ylim(0, 1)

KPI_X = [0.0, 0.27, 0.53, 0.79]
for x in KPI_X[1:]:
    ax_kpi.axvline(x - 0.02, color=GRIDLINE, linewidth=1)

kpi_label_kwargs = dict(fontsize=9.5, color=MUTED_INK, va="top")
kpi_value_kwargs = dict(fontsize=18, color=PRIMARY_INK, fontweight="bold", va="center")
kpi_caption_kwargs = dict(fontsize=9.5, color=SECONDARY_INK, va="bottom")

ax_kpi.text(KPI_X[0], 0.95, "ESTADO ATUAL", **kpi_label_kwargs)
dot_estado = ax_kpi.scatter([KPI_X[0] + 0.018], [0.5], s=220, color=COR_PARADO, zorder=3)
texto_estado = ax_kpi.text(KPI_X[0] + 0.05, 0.5, "Parado", fontsize=18, color=PRIMARY_INK,
                            fontweight="bold", va="center")

ax_kpi.text(KPI_X[1], 0.95, "PASSOS HOJE", **kpi_label_kwargs)
texto_passos_hoje = ax_kpi.text(KPI_X[1], 0.5, "0", **kpi_value_kwargs)
texto_passos_total = ax_kpi.text(KPI_X[1], 0.08, "total: 0", **kpi_caption_kwargs)

ax_kpi.text(KPI_X[2], 0.95, "DISTÂNCIA HOJE", **kpi_label_kwargs)
texto_dist_hoje = ax_kpi.text(KPI_X[2], 0.5, "0.0 m", **kpi_value_kwargs)
texto_dist_total = ax_kpi.text(KPI_X[2], 0.08, "total: 0.0 m", **kpi_caption_kwargs)

ax_kpi.text(KPI_X[3], 0.95, "VELOCIDADE MÉDIA", **kpi_label_kwargs)
texto_vel_media = ax_kpi.text(KPI_X[3], 0.5, "—", **kpi_value_kwargs)
texto_vel_caption = ax_kpi.text(KPI_X[3], 0.08, "último resumo diário", **kpi_caption_kwargs)

# --- Aceleracao ---
linha_x, = ax_accel.plot([], [], label="AccelX", color=COR_ACCEL_X, linewidth=2)
linha_y, = ax_accel.plot([], [], label="AccelY", color=COR_ACCEL_Y, linewidth=2)
linha_z, = ax_accel.plot([], [], label="AccelZ", color=COR_ACCEL_Z, linewidth=2)
ax_accel.set_title("Aceleração (3 eixos)", fontsize=12, color=PRIMARY_INK, loc="left", pad=28)
ax_accel.set_ylabel("m/s²", fontsize=10)
ax_accel.grid(axis="y", color=GRIDLINE, linewidth=1, alpha=0.9)
ax_accel.spines[["top", "right"]].set_visible(False)
ax_accel.tick_params(labelbottom=False)
leg_accel = ax_accel.legend(loc="lower center", bbox_to_anchor=(0.5, 1.02), ncol=3,
                             frameon=False, fontsize=10)

# --- Intensidade + evento de passo ---
linha_intensidade, = ax_intens.plot([], [], label="Intensidade de movimento",
                                     color=COR_INTENSIDADE, linewidth=2)
area_passo = ax_intens.fill_between([], [], color=COR_PASSO, alpha=0.25)
ax_intens.axhline(LIMIAR_CAMINHANDO, color=MUTED_INK, linestyle=":", linewidth=1)
ax_intens.axhline(LIMIAR_CORRENDO, color=MUTED_INK, linestyle=":", linewidth=1)
ax_intens.set_title("Intensidade de movimento e passos", fontsize=12, color=PRIMARY_INK,
                     loc="left", pad=28)
ax_intens.set_ylabel("m/s²", fontsize=10)
ax_intens.set_xlabel("Tempo (s)", fontsize=10)
ax_intens.grid(axis="y", color=GRIDLINE, linewidth=1, alpha=0.9)
ax_intens.spines[["top", "right"]].set_visible(False)
leg_intens = ax_intens.legend(
    handles=[linha_intensidade,
             plt.Line2D([0], [0], color=COR_PASSO, linewidth=8, alpha=0.35, label="Passo detectado")],
    loc="lower center", bbox_to_anchor=(0.5, 1.02), ncol=2, frameon=False, fontsize=10,
)

# --- Faixa de estado (linha do tempo colorida) ---
CMAP_ESTADO = ListedColormap([COR_PARADO, COR_CAMINHANDO, COR_CORRENDO])
im_estado = ax_state.imshow([[0]], cmap=CMAP_ESTADO, vmin=0, vmax=2, aspect="auto",
                             extent=(0, 1, 0, 1), interpolation="nearest")
ax_state.set_yticks([])
ax_state.set_xlabel("")
for spine in ax_state.spines.values():
    spine.set_visible(False)
ax_state.tick_params(bottom=False, labelbottom=False)

legenda_estado = [
    plt.Line2D([0], [0], marker="o", color="none", markerfacecolor=COR_PARADO, markersize=9, label="Parado"),
    plt.Line2D([0], [0], marker="o", color="none", markerfacecolor=COR_CAMINHANDO, markersize=9, label="Caminhando"),
    plt.Line2D([0], [0], marker="o", color="none", markerfacecolor=COR_CORRENDO, markersize=9, label="Correndo"),
]
ax_state.legend(handles=legenda_estado, loc="upper center", bbox_to_anchor=(0.5, -0.9),
                 ncol=3, frameon=False, fontsize=9.5)


def atualizar(frame):
    with lock:
        t = list(tempos)
        ax_data = (list(accel_x), list(accel_y), list(accel_z))
        intens = list(intensidade)
        pulso = list(passo_pulso)
        estados = list(estado_hist)
        estado = estado_atual[0]
        c = dict(contadores[0])
        r = dict(ultimo_resumo[0])

    if len(t) < 2:
        return

    linha_x.set_data(t, ax_data[0])
    linha_y.set_data(t, ax_data[1])
    linha_z.set_data(t, ax_data[2])
    linha_intensidade.set_data(t, intens)

    global area_passo
    area_passo.remove()
    area_passo = ax_intens.fill_between(t, 0, pulso, color=COR_PASSO, alpha=0.25, linewidth=0)

    xmin, xmax = max(0, t[-1] - 20), t[-1] + 0.5
    ax_accel.set_xlim(xmin, xmax)
    ax_accel.relim()
    ax_accel.autoscale_view(scalex=False)
    ax_intens.relim()
    ax_intens.autoscale_view(scalex=False)
    ax_intens.set_ylim(bottom=0)

    im_estado.set_data([estados])
    im_estado.set_extent((t[0], t[-1], 0, 1))
    ax_state.set_xlim(xmin, xmax)

    dot_estado.set_color(CORES_ESTADO.get(estado, MUTED_INK))
    texto_estado.set_text(ESTADOS.get(estado, "?"))

    texto_passos_hoje.set_text(f"{c['passosHoje']}")
    texto_passos_total.set_text(f"total: {c['passosTotal']}")
    texto_dist_hoje.set_text(f"{c['distanciaHojeM']:.1f} m")
    texto_dist_total.set_text(f"total: {c['distanciaTotalM']:.1f} m")

    if r.get("velocidadeMediaMs") is not None and (r.get("passos", 0) or r.get("distanciaM", 0)):
        texto_vel_media.set_text(f"{r.get('velocidadeMediaMs', 0):.2f} m/s")
    else:
        texto_vel_media.set_text("—")


def iniciar_mqtt():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"projetopet-dash-{int(time.time())}")
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(BROKER, PORTA, keepalive=60)
    client.loop_start()
    return client


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true",
                         help="usa dados sinteticos em vez de conectar no broker MQTT")
    args = parser.parse_args()

    client = None
    if args.demo:
        print("Modo demo: gerando dados sinteticos (parado -> caminhando -> correndo -> ...)")
        Thread(target=gerar_dados_demo, daemon=True).start()
    else:
        client = iniciar_mqtt()

    ani = animation.FuncAnimation(fig, atualizar, interval=200, blit=False, cache_frame_data=False)

    try:
        plt.show()
    finally:
        if client is not None:
            client.loop_stop()
            client.disconnect()
