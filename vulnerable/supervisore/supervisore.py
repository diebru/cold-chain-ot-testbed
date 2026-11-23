"""Supervisore di impianto SR-100 (versione VULNERABILE).

È il componente che nel caso reale è stato attaccato. Riunisce in un solo
dispositivo comando, misura e allarme:
- interroga i regolatori di banco sul bus di campo (Modbus, ogni secondo),
- mostra temperature e parametri in un'interfaccia web con login,
- permette di cambiare setpoint, sbrinamento e soglie d'allarme,
- genera gli allarmi e li notifica al centro di telegestione del manutentore,
- espone un gateway Modbus/TCP verso la rete del negozio, per l'integrazione
  con altri sistemi dell'edificio.

Debolezze volute:
- credenziali di fabbrica documentate nel manuale e mai cambiate,
- nessun limite ai tentativi di login, sessione firmata con una chiave fissa,
- traffico web in chiaro,
- nessun controllo di plausibilità su parametri e soglie,
- gateway Modbus senza autenticazione (il protocollo non la prevede).
"""

import functools
import logging
import os
import threading
import time
from collections import deque
from datetime import datetime

import requests
from flask import Flask, jsonify, redirect, render_template, request, session
from pymodbus.client import ModbusTcpClient
from pymodbus.datastore import (
    ModbusSequentialDataBlock,
    ModbusServerContext,
    ModbusSlaveContext,
)
from pymodbus.device import ModbusDeviceIdentification
from pymodbus.server import StartTcpServer
from werkzeug.serving import WSGIRequestHandler

MODEL = "SR-100"
FIRMWARE = "2.4.1"
SITE = os.environ.get("SITE_NAME", "Supermercato demo")
SIM_SPEED = float(os.environ.get("SIM_SPEED", "60"))
POLL_S = 1.0
NOTIFY_URL = os.environ.get("NOTIFY_URL", "http://telegestione:8080/notifica")

# Credenziali di fabbrica, identiche su ogni esemplare e scritte nel manuale.
# Nessuno le ha cambiate dopo l'installazione.
FACTORY_USERS = {"installatore": "SR100-inst"}

log = logging.getLogger("supervisore")
events = deque(maxlen=60)


def event(text, origin):
    events.appendleft({"ora": datetime.now().strftime("%H:%M:%S"), "origine": origin, "evento": text})
    log.warning("[%s] %s", origin, text)


def to_reg(value_c):
    return int(round(value_c * 10)) & 0xFFFF


def from_reg(reg):
    return (reg - 0x10000 if reg >= 0x8000 else reg) / 10.0


class CaseLink:
    """Collegamento con un regolatore di banco: polling, scritture, allarme."""

    def __init__(self, case_id, name, host, unit, threshold_c, delay_min):
        self.id = case_id
        self.name = name
        self.host = host
        self.unit = unit
        self.threshold_c = threshold_c
        self.delay_min = delay_min
        self.client = ModbusTcpClient(host, port=502, timeout=2)
        self.bus_lock = threading.Lock()
        self.lock = threading.Lock()
        self.hr = None
        self.ir = None
        self.online = None
        self.above_since = None
        self.alarm = False

    # Bus di campo

    def poll(self):
        with self.bus_lock:
            try:
                if not self.client.connected:
                    self.client.connect()
                hr = self.client.read_holding_registers(0, 4, slave=1)
                ir = self.client.read_input_registers(0, 5, slave=1)
                ok = not hr.isError() and not ir.isError()
            except Exception:  # bus irraggiungibile o risposta malformata
                ok = False
        with self.lock:
            was_online = self.online
            self.online = ok
            if ok:
                self.hr, self.ir = list(hr.registers), list(ir.registers)
        if was_online is None and ok:
            event(f"{self.name}: regolatore collegato", "supervisore")
        elif was_online is not None and was_online != ok:
            event(f"{self.name}: comunicazione {'ripristinata' if ok else 'persa'}", "supervisore")

    def write(self, address, values):
        with self.bus_lock:
            if not self.client.connected:
                self.client.connect()
            self.client.write_registers(address, values, slave=1)
        with self.lock:
            if self.hr is not None:
                for i, v in enumerate(values):
                    if address + i < 3:
                        self.hr[address + i] = v

    # Allarme

    def check_alarm(self):
        with self.lock:
            if self.ir is None:
                return
            temp = from_reg(self.ir[0])
            now = time.time()
            raise_alarm = clear_alarm = False
            if temp > self.threshold_c:
                if self.above_since is None:
                    self.above_since = now
                minutes_above = (now - self.above_since) * SIM_SPEED / 60.0
                if not self.alarm and minutes_above >= self.delay_min:
                    self.alarm = raise_alarm = True
            else:
                self.above_since = None
                if self.alarm:
                    self.alarm = False
                    clear_alarm = True
        if raise_alarm:
            text = f"{self.name}: ALLARME temperatura alta {temp:.1f} °C (soglia {self.threshold_c:.1f} °C)"
            event(text, "allarmi")
            notify(self.name, "ALLARME", temp, self.threshold_c)
        if clear_alarm:
            event(f"{self.name}: rientro dall'allarme, {temp:.1f} °C", "allarmi")
            notify(self.name, "RIENTRO", temp, self.threshold_c)

    def snapshot(self):
        with self.lock:
            base = {"id": self.id, "nome": self.name, "online": self.online, "allarme": self.alarm,
                    "soglia_allarme_c": self.threshold_c, "ritardo_allarme_min": self.delay_min}
            if self.hr is None:
                return base
            return base | {
                "temperatura_c": from_reg(self.ir[0]), "compressore": bool(self.ir[1]),
                "resistenza": bool(self.ir[2]), "sbrinamento_attivo": bool(self.ir[3]),
                "sbrinamento_residuo_min": self.ir[4], "setpoint_c": from_reg(self.hr[0]),
                "durata_sbrinamento_min": self.hr[1], "fine_sbrinamento_c": from_reg(self.hr[2]),
            }


CASES = {
    "banco1": CaseLink("banco1", "Congelatore surgelati", os.environ.get("RC1_HOST", "regolatore1"), 1,
                       threshold_c=-10.0, delay_min=5),
    "banco2": CaseLink("banco2", "Banco latticini", os.environ.get("RC2_HOST", "regolatore2"), 2,
                       threshold_c=12.0, delay_min=5),
}


def notify(case_name, kind, temp, threshold):
    payload = {"impianto": SITE, "banco": case_name, "tipo": kind, "temperatura_c": round(temp, 1),
               "soglia_c": threshold, "ora": datetime.now().strftime("%H:%M:%S")}
    try:
        requests.post(NOTIFY_URL, json=payload, timeout=3)
    except requests.RequestException as exc:
        event(f"notifica non consegnata: {exc.__class__.__name__}", "allarmi")


def poll_loop():
    while True:
        for link in CASES.values():
            link.poll()
            link.check_alarm()
        time.sleep(POLL_S)


def apply_changes(link, origin, setpoint=None, duration=None, end_temp=None, threshold=None, delay=None):
    """Applica le modifiche e le registra. Nessun limite sui valori."""
    snap = link.snapshot()
    if setpoint is not None:
        link.write(0, [to_reg(setpoint)])
        event(f"{link.name}: setpoint {snap.get('setpoint_c')} -> {setpoint} °C", origin)
    if duration is not None:
        link.write(1, [int(duration) & 0xFFFF])
        event(f"{link.name}: durata sbrinamento {snap.get('durata_sbrinamento_min')} -> {int(duration)} min", origin)
    if end_temp is not None:
        link.write(2, [to_reg(end_temp)])
        event(f"{link.name}: fine sbrinamento {snap.get('fine_sbrinamento_c')} -> {end_temp} °C", origin)
    if threshold is not None:
        with link.lock:
            link.threshold_c = threshold
        event(f"{link.name}: soglia d'allarme {snap['soglia_allarme_c']} -> {threshold} °C", origin)
    if delay is not None:
        with link.lock:
            link.delay_min = delay
        event(f"{link.name}: ritardo d'allarme {snap['ritardo_allarme_min']} -> {delay} min", origin)


def start_defrost(link, origin):
    link.write(3, [1])
    event(f"{link.name}: sbrinamento avviato", origin)


# Gateway Modbus/TCP verso la rete del negozio

class GatewayHolding(ModbusSequentialDataBlock):
    """Holding register del gateway, uno spazio per ogni banco (unit id 1 e 2).

    0-3  come il regolatore: setpoint, durata e fine sbrinamento, comando di sbrinamento
    4    soglia d'allarme del supervisore, decimi di °C con segno
    5    ritardo d'allarme, minuti
    """

    def __init__(self, link):
        super().__init__(0, [0] * 6)
        self.link = link

    def getValues(self, address, count=1):
        s = self.link.snapshot()
        hr = [to_reg(s.get("setpoint_c", 0)), int(s.get("durata_sbrinamento_min", 0)),
              to_reg(s.get("fine_sbrinamento_c", 0)), int(s.get("sbrinamento_attivo", False)),
              to_reg(s["soglia_allarme_c"]), int(s["ritardo_allarme_min"])]
        return hr[address:address + count]

    def setValues(self, address, values):
        origin = "gateway modbus"
        for offset, value in enumerate(values):
            reg = address + offset
            if reg == 0:
                apply_changes(self.link, origin, setpoint=from_reg(value))
            elif reg == 1:
                apply_changes(self.link, origin, duration=value)
            elif reg == 2:
                apply_changes(self.link, origin, end_temp=from_reg(value))
            elif reg == 3 and value == 1:
                start_defrost(self.link, origin)
            elif reg == 4:
                apply_changes(self.link, origin, threshold=from_reg(value))
            elif reg == 5:
                apply_changes(self.link, origin, delay=float(value))


class GatewayInput(ModbusSequentialDataBlock):
    """Input register del gateway: le misure del regolatore, come lette dal supervisore."""

    def __init__(self, link):
        super().__init__(0, [0] * 5)
        self.link = link

    def getValues(self, address, count=1):
        with self.link.lock:
            ir = list(self.link.ir) if self.link.ir else [0] * 5
        return ir[address:address + count]


def run_gateway():
    slaves = {link.unit: ModbusSlaveContext(hr=GatewayHolding(link), ir=GatewayInput(link), zero_mode=True)
              for link in CASES.values()}
    identity = ModbusDeviceIdentification(info_name={
        "VendorName": "Banco didattico", "ProductCode": MODEL,
        "ProductName": "Supervisore refrigerazione", "MajorMinorRevision": FIRMWARE})
    StartTcpServer(context=ModbusServerContext(slaves=slaves, single=False), identity=identity,
                   address=("0.0.0.0", 502))


# Interfaccia web

app = Flask(__name__)
app.secret_key = "sr100"  # chiave fissa, uguale su ogni esemplare


class BannerHandler(WSGIRequestHandler):
    # Il banner con modello e versione è ciò che i motori di ricerca di dispositivi indicizzano.
    def version_string(self):
        return f"{MODEL}/{FIRMWARE}"


def login_required(view):
    @functools.wraps(view)
    def wrapper(*args, **kwargs):
        if "user" not in session:
            if request.path.startswith("/api/"):
                return jsonify({"errore": "login richiesto"}), 401
            return redirect("/login")
        return view(*args, **kwargs)
    return wrapper


def origin():
    return f"web {session.get('user', '?')}@{request.remote_addr}"


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        user = request.form.get("utente", "")
        password = request.form.get("password", "")
        # Nessun limite ai tentativi, nessun secondo fattore.
        if FACTORY_USERS.get(user) == password:
            session["user"] = user
            event(f"accesso riuscito come {user}", f"web {request.remote_addr}")
            return redirect("/", code=303)
        event(f"accesso fallito come {user!r}", f"web {request.remote_addr}")
        error = "Credenziali non valide"
    return render_template("login.html", model=MODEL, firmware=FIRMWARE, site=SITE, error=error)


@app.get("/logout")
def logout():
    session.clear()
    return redirect("/login")


@app.get("/")
@login_required
def index():
    return render_template("index.html", model=MODEL, firmware=FIRMWARE, site=SITE,
                           cases=[c.snapshot() for c in CASES.values()], user=session["user"])


@app.get("/api/stato")
@login_required
def api_status():
    return jsonify({"banchi": [c.snapshot() for c in CASES.values()], "eventi": list(events)})


def _float(name):
    value = request.values.get(name, "").strip()
    return float(value) if value else None


@app.post("/banco/<case_id>/parametri")
@login_required
def set_params(case_id):
    link = CASES.get(case_id)
    if link is None:
        return "banco inesistente", 404
    apply_changes(link, origin(), setpoint=_float("setpoint"), duration=_float("durata_sbrinamento"),
                  end_temp=_float("fine_sbrinamento"), threshold=_float("soglia_allarme"),
                  delay=_float("ritardo_allarme"))
    return redirect("/", code=303)


@app.post("/banco/<case_id>/sbrinamento")
@login_required
def defrost(case_id):
    link = CASES.get(case_id)
    if link is None:
        return "banco inesistente", 404
    start_defrost(link, origin())
    return redirect("/", code=303)


def run_web():
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    app.run(host="0.0.0.0", port=80, threaded=True, use_reloader=False, request_handler=BannerHandler)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    logging.getLogger("pymodbus").setLevel(logging.CRITICAL)
    threading.Thread(target=poll_loop, daemon=True).start()
    threading.Thread(target=run_web, daemon=True).start()
    event(f"supervisore {MODEL} {FIRMWARE} avviato", "supervisore")
    run_gateway()


if __name__ == "__main__":
    main()
