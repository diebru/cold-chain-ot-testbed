"""Controller simulato di un banco congelatore. Versione VULNERABILE.

Nello stesso processo girano tre parti:
1. il modello fisico del congelatore (un thread che aggiorna la temperatura),
2. l'interfaccia web di gestione (Flask, porta 80),
3. il server Modbus/TCP (pymodbus, porta 502).

Nessuna delle due interfacce chiede autenticazione e nessuna controlla la
plausibilità dei valori. È la classe di debolezza che il banco riproduce:
funzioni di gestione previste dal prodotto, raggiungibili dalla rete e non protette.
"""

import json
import logging
import os
import threading
import time
from collections import deque
from datetime import datetime

from flask import Flask, jsonify, redirect, render_template, request
from pymodbus.datastore import (
    ModbusSequentialDataBlock,
    ModbusServerContext,
    ModbusSlaveContext,
)
from pymodbus.device import ModbusDeviceIdentification
from pymodbus.server import StartTcpServer
from werkzeug.serving import WSGIRequestHandler

# Parametri della simulazione (modificabili da variabili d'ambiente)
SIM_SPEED = float(os.environ.get("SIM_SPEED", "60"))  # 60 = un secondo reale vale un minuto simulato
TICK_S = 0.5  # passo reale del simulatore, in secondi
AMBIENT_C = 20.0  # temperatura del negozio
TAU_MIN = 300.0  # costante di tempo delle dispersioni (minuti simulati)
COOLING_C_PER_MIN = 0.6  # raffreddamento del compressore acceso
HEATING_C_PER_MIN = 0.25  # riscaldamento della resistenza di sbrinamento
HYSTERESIS_C = 1.0  # isteresi del termostato attorno al setpoint
PLANT_FILE = os.environ.get("PLANT_FILE", "/plant/state.json")

FIRMWARE = "1.4.2"
MODEL = "SR-100"

log = logging.getLogger("controller")


class Freezer:
    """Stato e fisica del congelatore virtuale. Tutti i tempi sono in minuti simulati."""

    def __init__(self):
        self.lock = threading.Lock()
        self.temperature = -20.0
        self.setpoint = -20.0
        self.defrost_duration_min = 20.0
        self.defrost_end_temp = 5.0
        self.defrost_interval_min = 360.0
        self.compressor_on = False
        self.heater_on = False
        self.defrost_active = False
        self.defrost_elapsed = 0.0
        self.since_last_defrost = 0.0
        self.sim_minutes = 0.0
        self.events = deque(maxlen=40)

    def log_event(self, text, source):
        entry = {"ora": datetime.now().strftime("%H:%M:%S"), "origine": source, "evento": text}
        self.events.appendleft(entry)
        log.warning("[%s] %s", source, text)

    def start_defrost(self, source):
        with self.lock:
            self.defrost_active = True
            self.defrost_elapsed = 0.0
            self.since_last_defrost = 0.0
        self.log_event("sbrinamento avviato", source)

    def set_params(self, source, setpoint=None, defrost_duration=None, defrost_end_temp=None):
        # Nessun controllo di plausibilità: un setpoint di +50 °C viene accettato.
        changes = []
        with self.lock:
            if setpoint is not None:
                changes.append(f"setpoint {self.setpoint:.1f} -> {setpoint:.1f} °C")
                self.setpoint = setpoint
            if defrost_duration is not None:
                changes.append(f"durata sbrinamento {self.defrost_duration_min:.0f} -> {defrost_duration:.0f} min")
                self.defrost_duration_min = defrost_duration
            if defrost_end_temp is not None:
                changes.append(f"fine sbrinamento {self.defrost_end_temp:.1f} -> {defrost_end_temp:.1f} °C")
                self.defrost_end_temp = defrost_end_temp
        for change in changes:
            self.log_event(change, source)

    def step(self, dt_min):
        with self.lock:
            self.sim_minutes += dt_min
            self.since_last_defrost += dt_min

            # Sbrinamento programmato, come in un banco reale
            if not self.defrost_active and self.since_last_defrost >= self.defrost_interval_min:
                self.defrost_active = True
                self.defrost_elapsed = 0.0
                self.since_last_defrost = 0.0
                self.log_event("sbrinamento programmato", "programma")

            if self.defrost_active:
                # Durante lo sbrinamento il compressore è spento e la resistenza scalda
                # fino alla temperatura di fine sbrinamento, per tutta la durata impostata.
                self.compressor_on = False
                self.heater_on = self.temperature < self.defrost_end_temp
                self.defrost_elapsed += dt_min
                if self.defrost_elapsed >= self.defrost_duration_min:
                    self.defrost_active = False
                    self.heater_on = False
            else:
                # Termostato con isteresi
                self.heater_on = False
                if self.temperature > self.setpoint + HYSTERESIS_C:
                    self.compressor_on = True
                elif self.temperature < self.setpoint - HYSTERESIS_C:
                    self.compressor_on = False

            rate = (AMBIENT_C - self.temperature) / TAU_MIN
            if self.compressor_on:
                rate -= COOLING_C_PER_MIN
            if self.heater_on:
                rate += HEATING_C_PER_MIN
            self.temperature += rate * dt_min

    def snapshot(self):
        with self.lock:
            remaining = max(0.0, self.defrost_duration_min - self.defrost_elapsed) if self.defrost_active else 0.0
            return {
                "modello": MODEL,
                "firmware": FIRMWARE,
                "temperatura_c": round(self.temperature, 2),
                "setpoint_c": self.setpoint,
                "compressore": self.compressor_on,
                "resistenza": self.heater_on,
                "sbrinamento_attivo": self.defrost_active,
                "sbrinamento_residuo_min": round(remaining, 1),
                "durata_sbrinamento_min": self.defrost_duration_min,
                "fine_sbrinamento_c": self.defrost_end_temp,
                "minuti_simulati": round(self.sim_minutes, 1),
            }


freezer = Freezer()


def simulation_loop():
    """Aggiorna la fisica e scrive la temperatura "vera" nel volume condiviso.

    Il file rappresenta l'aria dentro il congelatore: il sensore la misura da lì,
    senza passare dalla rete.
    """
    dt_min = TICK_S * SIM_SPEED / 60.0
    tmp_file = PLANT_FILE + ".tmp"
    while True:
        freezer.step(dt_min)
        try:
            with open(tmp_file, "w") as f:
                json.dump({"temperature_c": freezer.temperature, "ts": time.time()}, f)
            os.replace(tmp_file, PLANT_FILE)
        except OSError as exc:
            log.error("impossibile scrivere %s: %s", PLANT_FILE, exc)
        time.sleep(TICK_S)


# Modbus/TCP

def to_reg(value_c):
    """°C -> registro a 16 bit: decimi di grado in complemento a due."""
    return int(round(value_c * 10)) & 0xFFFF


def from_reg(reg):
    """Registro a 16 bit -> °C."""
    return (reg - 0x10000 if reg >= 0x8000 else reg) / 10.0


class HoldingRegisters(ModbusSequentialDataBlock):
    """Holding register (lettura e scrittura), mappati sullo stato del congelatore.

    0  setpoint, decimi di °C con segno
    1  durata dello sbrinamento, minuti
    2  temperatura di fine sbrinamento, decimi di °C con segno
    3  comando: scrivere 1 avvia uno sbrinamento
    """

    def __init__(self):
        super().__init__(0, [0] * 4)

    def getValues(self, address, count=1):
        s = freezer.snapshot()
        regs = [to_reg(s["setpoint_c"]), int(s["durata_sbrinamento_min"]) & 0xFFFF,
                to_reg(s["fine_sbrinamento_c"]), 1 if s["sbrinamento_attivo"] else 0]
        return regs[address:address + count]

    def setValues(self, address, values):
        for offset, value in enumerate(values):
            reg = address + offset
            if reg == 0:
                freezer.set_params("modbus", setpoint=from_reg(value))
            elif reg == 1:
                freezer.set_params("modbus", defrost_duration=float(value))
            elif reg == 2:
                freezer.set_params("modbus", defrost_end_temp=from_reg(value))
            elif reg == 3 and value == 1:
                freezer.start_defrost("modbus")


class InputRegisters(ModbusSequentialDataBlock):
    """Input register (sola lettura): misure e stati.

    0  temperatura, decimi di °C con segno
    1  compressore acceso (0 o 1)
    2  resistenza accesa (0 o 1)
    3  sbrinamento in corso (0 o 1)
    4  minuti di sbrinamento residui
    """

    def __init__(self):
        super().__init__(0, [0] * 5)

    def getValues(self, address, count=1):
        s = freezer.snapshot()
        regs = [to_reg(s["temperatura_c"]), int(s["compressore"]), int(s["resistenza"]),
                int(s["sbrinamento_attivo"]), int(s["sbrinamento_residuo_min"])]
        return regs[address:address + count]


def run_modbus():
    store = ModbusSlaveContext(hr=HoldingRegisters(), ir=InputRegisters(), zero_mode=True)
    context = ModbusServerContext(slaves=store, single=True)
    identity = ModbusDeviceIdentification(info_name={
        "VendorName": "Banco didattico",
        "ProductCode": MODEL,
        "ProductName": "Supervisore refrigerazione",
        "MajorMinorRevision": FIRMWARE,
    })
    StartTcpServer(context=context, identity=identity, address=("0.0.0.0", 502))


# Interfaccia web

app = Flask(__name__)


class BannerHandler(WSGIRequestHandler):
    # Il banner con modello e versione è ciò che i motori di ricerca di dispositivi indicizzano.
    def version_string(self):
        return f"{MODEL}/{FIRMWARE}"


@app.get("/")
def index():
    return render_template("index.html", s=freezer.snapshot(), events=list(freezer.events))


@app.get("/api/stato")
def api_status():
    return jsonify(freezer.snapshot() | {"eventi": list(freezer.events)})


def _float(name):
    value = request.values.get(name, "").strip()
    return float(value) if value else None


@app.post("/parametri")
def set_params():
    # Nessuna autenticazione, nessun token anti CSRF, nessun limite sui valori.
    source = f"web {request.remote_addr}"
    freezer.set_params(source, setpoint=_float("setpoint"),
                       defrost_duration=_float("durata_sbrinamento"),
                       defrost_end_temp=_float("fine_sbrinamento"))
    return redirect("/", code=303)


@app.post("/sbrinamento")
def defrost():
    freezer.start_defrost(f"web {request.remote_addr}")
    return redirect("/", code=303)


def run_web():
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    app.run(host="0.0.0.0", port=80, threaded=True, use_reloader=False, request_handler=BannerHandler)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    logging.getLogger("pymodbus").setLevel(logging.ERROR)
    os.makedirs(os.path.dirname(PLANT_FILE), exist_ok=True)
    threading.Thread(target=simulation_loop, daemon=True).start()
    threading.Thread(target=run_web, daemon=True).start()
    log.info("controller %s %s avviato, velocità di simulazione x%.0f", MODEL, FIRMWARE, SIM_SPEED)
    run_modbus()
