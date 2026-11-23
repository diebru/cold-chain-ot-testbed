"""Regolatore di banco RC-10 (versione VULNERABILE).

Ogni banco frigorifero ha il suo regolatore locale: legge la sonda cablata,
accende e spegne il compressore, gestisce gli sbrinamenti. Il regolatore non ha
interfaccia web. Parla solo Modbus con il supervisore, sul bus di campo.

Nello stesso processo girano:
1. il modello fisico del banco (un thread che aggiorna la temperatura),
2. il server Modbus/TCP (porta 502), che negli impianti reali è di solito un
   bus seriale RS-485 raggiungibile solo dal supervisore.

Modbus non prevede autenticazione: chi raggiunge il bus scrive i registri.
"""

import json
import logging
import os
import threading
import time

from pymodbus.datastore import (
    ModbusSequentialDataBlock,
    ModbusServerContext,
    ModbusSlaveContext,
)
from pymodbus.device import ModbusDeviceIdentification
from pymodbus.server import StartTcpServer

# Parametri del banco (variabili d'ambiente, così lo stesso codice fa da congelatore o da banco frigo)
CASE_ID = os.environ.get("CASE_ID", "banco1")
SETPOINT_C = float(os.environ.get("SETPOINT_C", "-20"))
DEFROST_DURATION_MIN = float(os.environ.get("DEFROST_DURATION_MIN", "20"))
DEFROST_END_C = float(os.environ.get("DEFROST_END_C", "5"))
DEFROST_INTERVAL_MIN = float(os.environ.get("DEFROST_INTERVAL_MIN", "360"))

# Parametri della simulazione
SIM_SPEED = float(os.environ.get("SIM_SPEED", "60"))  # 60 = un secondo reale vale un minuto simulato
TICK_S = 0.5  # passo reale del simulatore, in secondi
AMBIENT_C = 20.0  # temperatura del negozio
TAU_MIN = 300.0  # costante di tempo delle dispersioni (minuti simulati)
COOLING_C_PER_MIN = 0.6  # raffreddamento del compressore acceso
HEATING_C_PER_MIN = 0.25  # riscaldamento della resistenza di sbrinamento
HYSTERESIS_C = 1.0  # isteresi del termostato attorno al setpoint
PLANT_DIR = os.environ.get("PLANT_DIR", "/plant")

MODEL = "RC-10"
FIRMWARE = "3.1"

log = logging.getLogger(CASE_ID)


class Case:
    """Stato e fisica del banco. Tutti i tempi sono in minuti simulati."""

    def __init__(self):
        self.lock = threading.Lock()
        self.temperature = SETPOINT_C
        self.setpoint = SETPOINT_C
        self.defrost_duration_min = DEFROST_DURATION_MIN
        self.defrost_end_temp = DEFROST_END_C
        self.defrost_interval_min = DEFROST_INTERVAL_MIN
        self.compressor_on = False
        self.heater_on = False
        self.defrost_active = False
        self.defrost_elapsed = 0.0
        self.since_last_defrost = 0.0

    def start_defrost(self):
        with self.lock:
            self.defrost_active = True
            self.defrost_elapsed = 0.0
            self.since_last_defrost = 0.0
        log.warning("sbrinamento avviato da comando Modbus")

    def set_param(self, name, value):
        # Nessun controllo di plausibilità: un setpoint di +50 °C viene accettato.
        with self.lock:
            old = getattr(self, name)
            setattr(self, name, value)
        log.warning("parametro %s: %s -> %s (scrittura Modbus)", name, old, value)

    def step(self, dt_min):
        with self.lock:
            self.since_last_defrost += dt_min
            if not self.defrost_active and self.since_last_defrost >= self.defrost_interval_min:
                self.defrost_active = True
                self.defrost_elapsed = 0.0
                self.since_last_defrost = 0.0
                log.info("sbrinamento programmato")

            if self.defrost_active:
                # Compressore spento, la resistenza scalda fino alla temperatura di
                # fine sbrinamento e la mantiene per tutta la durata impostata.
                self.compressor_on = False
                self.heater_on = self.temperature < self.defrost_end_temp
                self.defrost_elapsed += dt_min
                if self.defrost_elapsed >= self.defrost_duration_min:
                    self.defrost_active = False
                    self.heater_on = False
            else:
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

    def holding(self):
        with self.lock:
            return [to_reg(self.setpoint), int(self.defrost_duration_min) & 0xFFFF,
                    to_reg(self.defrost_end_temp), 1 if self.defrost_active else 0]

    def inputs(self):
        with self.lock:
            remaining = max(0.0, self.defrost_duration_min - self.defrost_elapsed) if self.defrost_active else 0.0
            return [to_reg(self.temperature), int(self.compressor_on), int(self.heater_on),
                    int(self.defrost_active), int(remaining)]


case = Case()


def to_reg(value_c):
    """°C -> registro a 16 bit: decimi di grado in complemento a due."""
    return int(round(value_c * 10)) & 0xFFFF


def from_reg(reg):
    """Registro a 16 bit -> °C."""
    return (reg - 0x10000 if reg >= 0x8000 else reg) / 10.0


def simulation_loop():
    """Aggiorna la fisica e scrive la temperatura "vera" nel volume condiviso.

    Il file rappresenta l'aria dentro il banco. La sonda indipendente la misura
    da lì, senza passare dalla rete.
    """
    dt_min = TICK_S * SIM_SPEED / 60.0
    path = os.path.join(PLANT_DIR, f"{CASE_ID}.json")
    while True:
        case.step(dt_min)
        try:
            with open(path + ".tmp", "w") as f:
                json.dump({"temperature_c": case.temperature, "ts": time.time()}, f)
            os.replace(path + ".tmp", path)
        except OSError as exc:
            log.error("impossibile scrivere %s: %s", path, exc)
        time.sleep(TICK_S)


class HoldingRegisters(ModbusSequentialDataBlock):
    """Holding register (lettura e scrittura).

    0  setpoint, decimi di °C con segno
    1  durata dello sbrinamento, minuti
    2  temperatura di fine sbrinamento, decimi di °C con segno
    3  comando: scrivere 1 avvia uno sbrinamento
    """

    def __init__(self):
        super().__init__(0, [0] * 4)

    def getValues(self, address, count=1):
        return case.holding()[address:address + count]

    def setValues(self, address, values):
        for offset, value in enumerate(values):
            reg = address + offset
            if reg == 0:
                case.set_param("setpoint", from_reg(value))
            elif reg == 1:
                case.set_param("defrost_duration_min", float(value))
            elif reg == 2:
                case.set_param("defrost_end_temp", from_reg(value))
            elif reg == 3 and value == 1:
                case.start_defrost()


class InputRegisters(ModbusSequentialDataBlock):
    """Input register (sola lettura).

    0  temperatura della sonda cablata, decimi di °C con segno
    1  compressore acceso (0 o 1)
    2  resistenza accesa (0 o 1)
    3  sbrinamento in corso (0 o 1)
    4  minuti di sbrinamento residui
    """

    def __init__(self):
        super().__init__(0, [0] * 5)

    def getValues(self, address, count=1):
        return case.inputs()[address:address + count]


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    logging.getLogger("pymodbus").setLevel(logging.ERROR)
    os.makedirs(PLANT_DIR, exist_ok=True)
    threading.Thread(target=simulation_loop, daemon=True).start()
    log.info("regolatore %s %s avviato, setpoint %.1f °C, simulazione x%.0f", MODEL, FIRMWARE, SETPOINT_C, SIM_SPEED)
    store = ModbusSlaveContext(hr=HoldingRegisters(), ir=InputRegisters(), zero_mode=True)
    identity = ModbusDeviceIdentification(info_name={
        "VendorName": "Banco didattico", "ProductCode": MODEL,
        "ProductName": "Regolatore di banco", "MajorMinorRevision": FIRMWARE})
    StartTcpServer(context=ModbusServerContext(slaves=store, single=True), identity=identity,
                   address=("0.0.0.0", 502))


if __name__ == "__main__":
    main()
