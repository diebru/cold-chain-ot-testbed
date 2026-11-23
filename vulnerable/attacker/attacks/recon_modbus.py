"""Ricognizione Modbus/TCP: chi è il dispositivo e cosa contengono i suoi registri.

Modbus non ha autenticazione, quindi anche la sola lettura è libera. Lo script
chiede l'identificativo del dispositivo (function code 43) e legge i primi
registri (function code 3 e 4). Le letture non modificano nulla.

  python recon_modbus.py [indirizzo]
"""

import os
import sys

from pymodbus.client import ModbusTcpClient

HOST = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("CONTROLLER_HOST", "10.77.10.10")


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
    hr = client.read_holding_registers(0, 4, slave=1)
    ir = client.read_input_registers(0, 5, slave=1)
    print(f"Holding register 0-3 (lettura e scrittura): {[signed(r) for r in hr.registers]}")
    print(f"Input register 0-4 (sola lettura):         {[signed(r) for r in ir.registers]}")
    print("Un valore come -200 accanto a una temperatura misurata come -199 suggerisce decimi di grado:")
    print("il registro 0 è con buona probabilità il setpoint.")
    client.close()


if __name__ == "__main__":
    main()
