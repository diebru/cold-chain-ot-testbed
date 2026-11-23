"""Scenario 3: silenziamento della sonda del monitoraggio indipendente.

La sonda accetta comandi di configurazione remota sul suo topic MQTT, senza
verificare chi li manda. Lo script legge il messaggio di presentazione della
sonda (pubblicato "retained", quindi visibile a chiunque si iscriva), ne ricava
il topic di configurazione e spegne l'invio delle letture.

  python scenario3_silenzia.py              spegne la sonda
  python scenario3_silenzia.py ripristina   la riaccende
"""

import argparse
import json
import os
import time
import uuid

import paho.mqtt.client as mqtt

BROKER = os.environ.get("BROKER_HOST", "10.77.10.20")
INFO_TOPIC = os.environ.get("INFO_TOPIC", "monitoraggio/+/+/info")


def find_sensors(client, wait_s=3):
    found = {}

    def store(c, userdata, msg):
        try:
            found[msg.topic] = json.loads(msg.payload)
        except ValueError:
            pass

    client.on_message = store
    client.subscribe(INFO_TOPIC)
    time.sleep(wait_s)
    client.unsubscribe(INFO_TOPIC)
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("azione", nargs="?", choices=["silenzia", "ripristina"], default="silenzia")
    args = parser.parse_args()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"att-{uuid.uuid4().hex[:6]}")
    client.connect(BROKER, 1883)
    client.loop_start()

    sensors = find_sensors(client)
    if not sensors:
        raise SystemExit("Nessuna sonda trovata sul broker")
    command = {"enabled": args.azione == "ripristina"}
    for topic, info in sensors.items():
        print(f"Trovata {info.get('model')} ({info.get('sensor')}), invio attivo: {info.get('enabled')}, "
              f"topic di configurazione {info['config_topic']}")
        client.publish(info["config_topic"], json.dumps(command)).wait_for_publish()
        print(f"  inviato {command}")
    time.sleep(1)
    client.disconnect()


if __name__ == "__main__":
    main()
