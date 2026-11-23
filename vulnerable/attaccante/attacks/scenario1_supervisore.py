"""Scenario 1: modifica dei parametri e delle soglie d'allarme sul supervisore.

Riproduce l'azione osservata nel caso reale: accesso all'interfaccia con le
credenziali di fabbrica, soglia d'allarme alzata, sbrinamento lungo e caldo.
Usa solo funzioni previste dal supervisore.

  python scenario1_supervisore.py web
      login con le credenziali del manuale, soglia d'allarme a +60 °C,
      sbrinamento di 480 minuti fino a 50 °C

  python scenario1_supervisore.py web --lascia-soglie
      come sopra ma senza toccare la soglia: il supervisore darà l'allarme

  python scenario1_supervisore.py modbus [--lascia-soglie]
      la stessa azione tramite il gateway Modbus/TCP, che non ha login

  python scenario1_supervisore.py ripristina
      riporta parametri e soglie ai valori di fabbrica

Opzione comune: --banco 1 (congelatore, predefinito) oppure --banco 2 (banco frigo).
"""

import argparse
import os
import time

import requests
from pymodbus.client import ModbusTcpClient

SUPERVISOR = os.environ.get("SUPERVISOR_HOST", "10.77.10.10")
BASE_URL = f"http://{SUPERVISOR}"

# Dal manuale d'installazione pubblico (manuale_SR-100.md, paragrafo 2)
FACTORY_USER = "installatore"
FACTORY_PASSWORD = "SR100-inst"

# Valori di fabbrica dei due banchi, per il ripristino
FACTORY = {
    1: {"setpoint": -20, "durata_sbrinamento": 20, "fine_sbrinamento": 5, "soglia_allarme": -10, "ritardo_allarme": 5},
    2: {"setpoint": 3, "durata_sbrinamento": 15, "fine_sbrinamento": 10, "soglia_allarme": 12, "ritardo_allarme": 5},
}


def to_reg(value_c):
    return int(round(value_c * 10)) & 0xFFFF


def from_reg(reg):
    return (reg - 0x10000 if reg >= 0x8000 else reg) / 10.0


def login():
    s = requests.Session()
    r = s.get(f"{BASE_URL}/", timeout=5)
    print(f"GET / -> pagina di login ({r.url})")
    r = s.post(f"{BASE_URL}/login", data={"utente": FACTORY_USER, "password": FACTORY_PASSWORD}, timeout=5)
    if r.url.endswith("/login"):
        raise SystemExit("Login fallito: le credenziali di fabbrica sono state cambiate")
    print(f"POST /login con {FACTORY_USER} / {FACTORY_PASSWORD} (dal manuale) -> accesso riuscito")
    return s


def show_web(s, banco, label):
    data = s.get(f"{BASE_URL}/api/stato", timeout=5).json()
    c = data["banchi"][banco - 1]
    print(f"{label}: {c['nome']}, temperatura {c.get('temperatura_c')} °C, setpoint {c.get('setpoint_c')} °C, "
          f"sbrinamento {c.get('durata_sbrinamento_min')} min fino a {c.get('fine_sbrinamento_c')} °C, "
          f"soglia d'allarme {c['soglia_allarme_c']} °C")


def via_web(banco, duration, end_temp, threshold, keep_thresholds):
    s = login()
    show_web(s, banco, "Prima")
    params = {"durata_sbrinamento": duration, "fine_sbrinamento": end_temp}
    if not keep_thresholds:
        params["soglia_allarme"] = threshold
    s.post(f"{BASE_URL}/banco/banco{banco}/parametri", data=params, timeout=5)
    print(f"POST /banco/banco{banco}/parametri {params}")
    s.post(f"{BASE_URL}/banco/banco{banco}/sbrinamento", timeout=5)
    print(f"POST /banco/banco{banco}/sbrinamento")
    time.sleep(1.5)
    show_web(s, banco, "Dopo ")


def show_modbus(client, banco, label):
    hr = client.read_holding_registers(0, 6, slave=banco).registers
    ir = client.read_input_registers(0, 5, slave=banco).registers
    print(f"{label}: temperatura {from_reg(ir[0])} °C, setpoint {from_reg(hr[0])} °C, "
          f"sbrinamento {hr[1]} min fino a {from_reg(hr[2])} °C, soglia d'allarme {from_reg(hr[4])} °C")


def via_modbus(banco, duration, end_temp, threshold, keep_thresholds):
    client = ModbusTcpClient(SUPERVISOR, port=502)
    if not client.connect():
        raise SystemExit(f"Gateway Modbus/TCP non raggiungibile su {SUPERVISOR}:502")
    show_modbus(client, banco, "Prima")
    # Modbus non ha alcun concetto di utente: il login dell'interfaccia web qui non esiste.
    client.write_registers(1, [duration, to_reg(end_temp)], slave=banco)
    print(f"FC16 unità {banco}, registri 1-2 <- durata {duration} min, fine sbrinamento {end_temp} °C")
    if not keep_thresholds:
        client.write_register(4, to_reg(threshold), slave=banco)
        print(f"FC6  unità {banco}, registro 4 <- soglia d'allarme {threshold} °C")
    client.write_register(3, 1, slave=banco)
    print(f"FC6  unità {banco}, registro 3 <- 1 (avvio sbrinamento)")
    time.sleep(1.5)
    show_modbus(client, banco, "Dopo ")
    client.close()


def restore(banco):
    s = login()
    s.post(f"{BASE_URL}/banco/banco{banco}/parametri", data=FACTORY[banco], timeout=5)
    time.sleep(1.5)
    show_web(s, banco, "Ripristinato")
    print("Uno sbrinamento in corso da più minuti della durata di fabbrica termina subito.")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="via", required=True)
    for name in ("web", "modbus"):
        p = sub.add_parser(name)
        p.add_argument("--banco", type=int, choices=[1, 2], default=1)
        p.add_argument("--durata", type=int, default=480, help="minuti simulati")
        p.add_argument("--fine", type=float, default=50.0, help="°C")
        p.add_argument("--soglia", type=float, default=60.0, help="nuova soglia d'allarme, °C")
        p.add_argument("--lascia-soglie", action="store_true", help="non modificare la soglia d'allarme")
    r = sub.add_parser("ripristina")
    r.add_argument("--banco", type=int, choices=[1, 2], default=1)
    args = parser.parse_args()
    if args.via == "web":
        via_web(args.banco, args.durata, args.fine, args.soglia, args.lascia_soglie)
    elif args.via == "modbus":
        via_modbus(args.banco, args.durata, args.fine, args.soglia, args.lascia_soglie)
    else:
        restore(args.banco)


if __name__ == "__main__":
    main()
