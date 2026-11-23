"""Ricognizione Modbus/TCP: chi è il dispositivo e cosa contengono i suoi registri.

Modbus non ha autenticazione, quindi anche la sola lettura è libera. Lo script
chiede l'identificativo del dispositivo (function code 43) e legge i registri
(function code 3 e 4) delle unità 1 e 2. Le letture non modificano nulla.

  python recon_modbus.py [indirizzo]
"""

import os
import sys

from pymodbus.client import ModbusTcpClient

HOST = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("SUPERVISOR_HOST", "10.77.10.10")


def signed(reg):
    return reg - 0x10000 if reg >= 0x8000 else reg


def main():
    client = ModbusTcpClient(HOST, port=502, timeout=3)
    if not client.connect():
        raise SystemExit(f"{HOST}:502 non raggiungibile")
    ident = client.read_device_information(slave=1)
    if not ident.isError():
        for key, value in sorted(ident.information.items()):
            print(f"Identificativo {key}: {value.decode(errors='replace')}")
    for unit in (1, 2):
        hr = client.read_holding_registers(0, 6, slave=unit)
        ir = client.read_input_registers(0, 5, slave=unit)
        if hr.isError() or ir.isError():
            print(f"Unità {unit}: nessuna risposta")
            continue
        print(f"Unità {unit}, holding register 0-5 (lettura e scrittura): {[signed(r) for r in hr.registers]}")
        print(f"Unità {unit}, input register 0-4 (sola lettura):         {[signed(r) for r in ir.registers]}")
    print("Il manuale pubblico dell'SR-100 spiega il significato di ogni registro.")
    client.close()


if __name__ == "__main__":
    main()
