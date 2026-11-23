"""Server degli allarmi. Versione VULNERABILE.

Si iscrive alle letture di temperatura e genera un allarme quando la temperatura
resta sopra la soglia per un certo numero di letture consecutive (ritardo
d'allarme, come nei sistemi reali, per non far scattare allarmi durante gli
sbrinamenti brevi).

Debolezze volute:
- accetta qualunque messaggio arrivi sul topic, senza verificarne l'origine,
- non controlla timestamp né numeri di sequenza (un messaggio ripetuto vale come nuovo),
- non ha heartbeat: se le letture smettono di arrivare, nessun allarme.
"""

import json
import logging
import os
import threading
import time
from collections import deque
from datetime import datetime

import paho.mqtt.client as mqtt
from flask import Flask, jsonify, render_template

BROKER = os.environ.get("BROKER_HOST", "broker")
PORT = int(os.environ.get("BROKER_PORT", "1883"))
TOPIC = os.environ.get("DATA_TOPIC", "store/+/temperature")
ALARM_HIGH_C = float(os.environ.get("ALARM_HIGH_C", "-10"))
ALARM_DELAY = int(os.environ.get("ALARM_DELAY_READINGS", "3"))

log = logging.getLogger("alarm")


class AlarmState:
    def __init__(self):
        self.lock = threading.Lock()
        self.last = None
        self.last_received = None
        self.readings = 0
        self.above = 0
        self.below = 0
        self.alarm = False
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
            raise_alarm = not self.alarm and self.above >= ALARM_DELAY
            clear_alarm = self.alarm and self.below >= ALARM_DELAY
            if raise_alarm:
                self.alarm = True
            if clear_alarm:
                self.alarm = False
        if raise_alarm:
            self.event(f"ALLARME temperatura alta: {temp:.1f} °C (soglia {ALARM_HIGH_C:.1f} °C)")
        if clear_alarm:
            self.event(f"rientro dall'allarme: {temp:.1f} °C")

    def snapshot(self):
        with self.lock:
            age = round(time.time() - self.last_received, 1) if self.last_received else None
            return {"allarme": self.alarm, "ultima_lettura": self.last, "eta_ultima_lettura_s": age,
                    "letture_ricevute": self.readings, "soglia_c": ALARM_HIGH_C,
                    "ritardo_letture": ALARM_DELAY, "eventi": list(self.events)}


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


@app.get("/api/stato")
def api_status():
    return jsonify(state.snapshot())


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="alarm-server")
    client.on_connect = on_connect
    client.on_message = on_message
    client.reconnect_delay_set(min_delay=1, max_delay=5)
    client.connect_async(BROKER, PORT)
    client.loop_start()
    state.event(f"server degli allarmi avviato, soglia {ALARM_HIGH_C:.1f} °C dopo {ALARM_DELAY} letture")
    app.run(host="0.0.0.0", port=8080, threaded=True, use_reloader=False)


if __name__ == "__main__":
    main()
