"""Scenario 1: modifica del setpoint e sbrinamento forzato.

Usa solo funzioni previste dal controller, raggiungibili senza credenziali.

  python scenario1_parametri.py web [--setpoint 25]
      cambia il setpoint dal modulo dell'interfaccia web (HTTP POST)

  python scenario1_parametri.py modbus [--durata 480] [--fine 50]
      imposta uno sbrinamento lungo e caldo e lo avvia via Modbus/TCP
      (function code 16 per scrivere più registri, 6 per il comando)

  python scenario1_parametri.py ripristina
      riporta i parametri ai valori di fabbrica del banco
"""

import argparse
import os

import requests
from pymodbus.client import ModbusTcpClient

CONTROLLER = os.environ.get("CONTROLLER_HOST", "10.77.10.10")


def to_reg(value_c):
    return int(round(value_c * 10)) & 0xFFFF


def from_reg(reg):
    return (reg - 0x10000 if reg >= 0x8000 else reg) / 10.0


def show_web(label):
    s = requests.get(f"http://{CONTROLLER}/api/stato", timeout=5).json()
    print(f"{label}: temperatura {s['temperatura_c']} °C, setpoint {s['setpoint_c']} °C, "
          f"sbrinamento {s['durata_sbrinamento_min']} min fino a {s['fine_sbrinamento_c']} °C, "
          f"in corso: {s['sbrinamento_attivo']}")


def via_web(setpoint):
    show_web("Prima")
    # Nessun login: la richiesta è identica a quella del modulo della pagina.
    r = requests.post(f"http://{CONTROLLER}/parametri", data={"setpoint": setpoint},
                      allow_redirects=False, timeout=5)
    print(f"POST /parametri setpoint={setpoint} -> HTTP {r.status_code}")
    show_web("Dopo ")


def show_modbus(client, label):
    hr = client.read_holding_registers(0, 4, slave=1).registers
    ir = client.read_input_registers(0, 5, slave=1).registers
    print(f"{label}: temperatura {from_reg(ir[0])} °C, setpoint {from_reg(hr[0])} °C, "
          f"sbrinamento {hr[1]} min fino a {from_reg(hr[2])} °C, in corso: {bool(ir[3])}")


def via_modbus(duration, end_temp):
    client = ModbusTcpClient(CONTROLLER, port=502)
    if not client.connect():
        raise SystemExit(f"Modbus/TCP non raggiungibile su {CONTROLLER}:502")
    show_modbus(client, "Prima")
    # Modbus non ha alcun concetto di utente: chi raggiunge la porta 502 può scrivere.
    client.write_registers(1, [duration, to_reg(end_temp)], slave=1)
    print(f"FC16 registri 1-2 <- durata {duration} min, fine sbrinamento {end_temp} °C")
    client.write_register(3, 1, slave=1)
    print("FC6  registro 3 <- 1 (avvio sbrinamento)")
    show_modbus(client, "Dopo ")
    client.close()


def restore():
    requests.post(f"http://{CONTROLLER}/parametri",
                  data={"setpoint": -20, "durata_sbrinamento": 20, "fine_sbrinamento": 5},
                  allow_redirects=False, timeout=5)
    show_web("Ripristinato")
    print("Uno sbrinamento in corso da più di 20 minuti simulati termina subito.")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="via", required=True)
    web = sub.add_parser("web")
    web.add_argument("--setpoint", type=float, default=25.0)
    mb = sub.add_parser("modbus")
    mb.add_argument("--durata", type=int, default=480, help="minuti simulati")
    mb.add_argument("--fine", type=float, default=50.0, help="°C")
    sub.add_parser("ripristina")
    args = parser.parse_args()
    if args.via == "web":
        via_web(args.setpoint)
    elif args.via == "modbus":
        via_modbus(args.durata, args.fine)
    else:
        restore()


if __name__ == "__main__":
    main()
