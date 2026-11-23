"""Sonda TP-1 del monitoraggio indipendente (versione VULNERABILE).

È un sistema separato dal supervisore, come quello che all'EFS ha dato
l'allarme mentre il supervisore era compromesso. Misura il banco 1 con una
sonda propria e pubblica le letture via MQTT verso una centrale propria.

Pubblica in chiaro, senza credenziali e senza firma. Accetta comandi di
configurazione remota (intervallo di invio, attivazione) da chiunque possa
pubblicare sul suo topic di configurazione.

Sorgente delle letture (variabile SENSOR_SOURCE):
  plant     temperatura del banco virtuale, letta dal volume condiviso con il regolatore
  synthetic dati sintetici attorno a -20 °C
  ds18b20   sonda reale DS18B20 sul bus 1-Wire del Raspberry Pi
"""

import glob
import json
import logging
import math
import os
import random
import time

import paho.mqtt.client as mqtt

BROKER = os.environ.get("BROKER_HOST", "broker")
PORT = int(os.environ.get("BROKER_PORT", "1883"))
SOURCE = os.environ.get("SENSOR_SOURCE", "plant")
SENSOR_ID = os.environ.get("SENSOR_ID", "sonda1")
BASE = os.environ.get("TOPIC_BASE", "monitoraggio/banco1")
PLANT_FILE = os.environ.get("PLANT_FILE", "/plant/banco1.json")

DATA_TOPIC = f"{BASE}/temperatura"
CONFIG_TOPIC = f"{BASE}/{SENSOR_ID}/config"
INFO_TOPIC = f"{BASE}/{SENSOR_ID}/info"

log = logging.getLogger("sonda")

config = {"enabled": True, "interval_s": float(os.environ.get("INTERVAL_S", "2"))}


def read_plant():
    with open(PLANT_FILE) as f:
        return json.load(f)["temperature_c"] + random.gauss(0, 0.1)


def read_synthetic():
    return -20.0 + 0.5 * math.sin(time.time() / 60.0) + random.gauss(0, 0.1)


def read_ds18b20():
    # Il kernel espone ogni sonda in /sys/bus/w1/devices/28-*/w1_slave
    # La seconda riga termina con "t=" seguito dai millesimi di grado.
    path = glob.glob("/sys/bus/w1/devices/28-*/w1_slave")[0]
    with open(path) as f:
        lines = f.read().splitlines()
    if not lines[0].endswith("YES"):
        raise OSError("CRC della sonda non valido")
    return int(lines[1].split("t=")[1]) / 1000.0


READERS = {"plant": read_plant, "synthetic": read_synthetic, "ds18b20": read_ds18b20}


def publish_info(client):
    # Messaggio "retained" di presentazione: chiunque si iscriva lo riceve subito.
    # È comodo per l'integratore e altrettanto comodo per un attaccante.
    info = {"model": "TP-1 sonda MQTT", "firmware": "2.0.1", "sensor": SENSOR_ID,
            "source": SOURCE, "data_topic": DATA_TOPIC, "config_topic": CONFIG_TOPIC} | config
    client.publish(INFO_TOPIC, json.dumps(info), retain=True)


def on_connect(client, userdata, flags, reason_code, properties):
    log.info("connesso al broker %s:%d (%s)", BROKER, PORT, reason_code)
    client.subscribe(CONFIG_TOPIC)
    publish_info(client)


def on_message(client, userdata, msg):
    # Nessuna verifica di chi ha mandato il comando: basta poter pubblicare sul topic.
    try:
        new = json.loads(msg.payload)
    except ValueError:
        log.warning("configurazione non valida ignorata: %r", msg.payload[:80])
        return
    if "enabled" in new:
        config["enabled"] = bool(new["enabled"])
    if "interval_s" in new:
        config["interval_s"] = max(0.5, float(new["interval_s"]))
    log.warning("configurazione remota applicata: %s", config)
    publish_info(client)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    read = READERS[SOURCE]
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"sensor-{SENSOR_ID}")
    client.on_connect = on_connect
    client.on_message = on_message
    client.reconnect_delay_set(min_delay=1, max_delay=5)
    client.connect_async(BROKER, PORT)
    client.loop_start()

    seq = 0
    while True:
        if config["enabled"] and client.is_connected():
            try:
                temp = read()
            except (OSError, IndexError, KeyError, ValueError) as exc:
                log.error("lettura fallita: %s", exc)
            else:
                seq += 1
                payload = {"sensor": SENSOR_ID, "temp_c": round(temp, 2), "ts": int(time.time()), "seq": seq}
                client.publish(DATA_TOPIC, json.dumps(payload))
        time.sleep(config["interval_s"])


if __name__ == "__main__":
    main()
