import hid
import subprocess
import time
import os

VID = 0x16C0
PID = 0x05DF
CMD_SET_SERIAL = 0xFA
USBRELAY_EXE = "usbrelay.exe"

def list_relays():
    print("\n--- usbrelay.exe -list ---")
    subprocess.run([USBRELAY_EXE, "-list"], shell=False)
    print("--------------------------\n")

def change_id(new_id):
    if not new_id.isascii() or not new_id.isalnum():
        raise ValueError("ID-ul trebuie sa contina doar litere/cifre.")
    if len(new_id) < 1 or len(new_id) > 5:
        raise ValueError("ID-ul trebuie sa aiba intre 1 si 5 caractere.")

    serial_bytes = new_id.encode("ascii") + b"\x00"
    serial_bytes = serial_bytes.ljust(6, b"\x00")

    dev = hid.device()
    dev.open(VID, PID)

    report = bytes([0x00, CMD_SET_SERIAL]) + serial_bytes + b"\x00"
    dev.send_feature_report(report)
    dev.close()

while True:
    list_relays()

    new_id = input("Introdu noul ID, max 5 caractere, sau Q pentru iesire: ").strip().upper()

    if new_id in ("Q", "QUIT", "EXIT"):
        break

    try:
        input(f"Conecteaza O SINGURA placa si apasa Enter pentru a scrie ID-ul {new_id}...")
        change_id(new_id)

        print("\nComanda trimisa. Scoate si reconecteaza placa USB.")
        input("Dupa reconectare, apasa Enter pentru verificare...")

        list_relays()

        input("Apasa Enter pentru urmatoarea placa...")

    except Exception as e:
        print(f"\nEroare: {e}")
        input("Apasa Enter ca sa continui...")