"""Centrale del monitoraggio indipendente (versione VULNERABILE).

Riceve le letture della sonda TP-1 e genera gli allarmi su due livelli, come
molti sistemi di monitoraggio HACCP:
- allarme: temperatura sopra ALARM_HIGH_C per ALARM_DELAY_READINGS letture
  consecutive. Il ritardo evita falsi allarmi durante gli sbrinamenti brevi,
- allarme critico: una sola lettura sopra CRITICAL_C basta, senza ritardo.
  L'allarme critico resta memorizzato finché un operatore non lo riconosce.

Debolezze volute:
- accetta qualunque messaggio arrivi sul topic, senza verificarne l'origine,
- non controlla timestamp né numeri di sequenza (un messaggio ripetuto vale come nuovo),
- non ha heartbeat: se le letture smettono di arrivare, nessun allarme,
- chiunque raggiunga la pagina può riconoscere (cancellare) un allarme.
"""

import json
import logging
import os
import threading
import time
from collections import deque
from datetime import datetime

import paho.mqtt.client as mqtt
from flask import Flask, jsonify, redirect, render_template, request

BROKER = os.environ.get("BROKER_HOST", "broker")
PORT = int(os.environ.get("BROKER_PORT", "1883"))
TOPIC = os.environ.get("DATA_TOPIC", "monitoraggio/+/temperatura")
ALARM_HIGH_C = float(os.environ.get("ALARM_HIGH_C", "-10"))
ALARM_DELAY = int(os.environ.get("ALARM_DELAY_READINGS", "3"))
CRITICAL_C = float(os.environ.get("CRITICAL_C", "-5"))

log = logging.getLogger("centrale")


class AlarmState:
    def __init__(self):
        self.lock = threading.Lock()
        self.last = None
        self.last_received = None
        self.readings = 0
        self.above = 0
        self.below = 0
        self.level = "NORMALE"  # NORMALE, ALLARME, ALLARME CRITICO
        self.events = deque(maxlen=40)

    def event(self, text):
        self.events.appendleft({"ora": datetime.now().strftime("%H:%M:%S"), "evento": text})
        log.warning(text)

    def update(self, reading):
        temp = float(reading["temp_c"])
        with self.lock:
            self.last = reading
            self.last_received = time.time()
            self.readings += 1
            if temp > ALARM_HIGH_C:
                self.above += 1
                self.below = 0
            else:
                self.below += 1
                self.above = 0
            old = self.level
            if temp > CRITICAL_C:
                self.level = "ALLARME CRITICO"
            elif self.level == "NORMALE" and self.above >= ALARM_DELAY:
                self.level = "ALLARME"
            elif self.level == "ALLARME" and self.below >= ALARM_DELAY:
                self.level = "NORMALE"
            new = self.level
        if new != old:
            if new == "NORMALE":
                self.event(f"rientro dall'allarme: {temp:.1f} °C")
            else:
                self.event(f"{new}: {temp:.1f} °C (soglie {ALARM_HIGH_C:.1f} e {CRITICAL_C:.1f} °C)")

    def acknowledge(self, who):
        with self.lock:
            old = self.level
            self.level = "NORMALE"
            self.above = self.below = 0
        if old != "NORMALE":
            self.event(f"allarme riconosciuto da {who}")

    def snapshot(self):
        with self.lock:
            age = round(time.time() - self.last_received, 1) if self.last_received else None
            return {"livello": self.level, "allarme": self.level != "NORMALE", "ultima_lettura": self.last,
                    "eta_ultima_lettura_s": age, "letture_ricevute": self.readings,
                    "soglia_c": ALARM_HIGH_C, "ritardo_letture": ALARM_DELAY, "soglia_critica_c": CRITICAL_C,
                    "eventi": list(self.events)}


state = AlarmState()


def on_connect(client, userdata, flags, reason_code, properties):
    log.info("connesso al broker %s:%d, iscritto a %s", BROKER, PORT, TOPIC)
    client.subscribe(TOPIC)


def on_message(client, userdata, msg):
    try:
        reading = json.loads(msg.payload)
        float(reading["temp_c"])
    except (ValueError, KeyError, TypeError):
        log.info("messaggio non valido su %s ignorato", msg.topic)
        return
    state.update(reading)


app = Flask(__name__)


@app.get("/")
def dashboard():
    return render_template("dashboard.html", s=state.snapshot())


@app.post("/riconosci")
def acknowledge():
    # Nessuna autenticazione: anche un attaccante può cancellare l'allarme.
    state.acknowledge(request.remote_addr)
    return redirect("/", code=303)


@app.get("/api/stato")
def api_status():
    return jsonify(state.snapshot())


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="centrale")
    client.on_connect = on_connect
    client.on_message = on_message
    client.reconnect_delay_set(min_delay=1, max_delay=5)
    client.connect_async(BROKER, PORT)
    client.loop_start()
    state.event(f"centrale avviata: allarme sopra {ALARM_HIGH_C:.1f} °C dopo {ALARM_DELAY} letture, "
                f"critico sopra {CRITICAL_C:.1f} °C subito")
    app.run(host="0.0.0.0", port=8080, threaded=True, use_reloader=False)


if __name__ == "__main__":
    main()
