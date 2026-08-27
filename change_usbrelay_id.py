"""Utilitar pentru schimbarea serialului (ID-ului) unei placi USB Relay.

Listarea placilor se face prin ``USB_RELAY_DEVICE.dll`` (vezi
``usb_relay_lib.py``), iar scrierea ID-ului prin pachetul ``hid``, pentru ca
biblioteca nativa nu expune o functie de setare a serialului.

Modulul poate fi folosit in doua feluri:

* rulat direct, ca utilitar de linie de comanda (``python change_usbrelay_id.py``);
* importat de interfata grafica ``relay_gui.py``, care refoloseste
  ``validate_id`` si ``change_id``.
"""

try:
    import hid
except ImportError as exc:  # pragma: no cover - depinde de mediul de rulare
    hid = None
    HID_IMPORT_ERROR = str(exc)
else:
    HID_IMPORT_ERROR = None

from usb_relay_lib import MAX_SERIAL_LENGTH as MAX_ID_LENGTH
from usb_relay_lib import RelayController, UsbRelayError, format_devices

VID = 0x16C0
PID = 0x05DF
CMD_SET_SERIAL = 0xFA
REPORT_LENGTH = 9
EXIT_COMMANDS = {"Q", "QUIT", "EXIT"}


def list_relays_output():
    """Return ``(success, text)`` cu placile detectate de biblioteca nativa."""
    controller = RelayController()
    try:
        devices = controller.scan()
    except UsbRelayError as exc:
        return False, str(exc)
    finally:
        controller.close()

    return True, format_devices(devices)


def list_relays():
    """Print relay devices detected by the native library."""
    print("\n--- placi USB Relay detectate ---")
    _, output = list_relays_output()
    print(output)
    print("--------------------------------\n")


def validate_id(new_id):
    if not new_id.isascii() or not new_id.isalnum():
        raise ValueError("ID-ul trebuie sa contina doar litere/cifre.")

    if not 1 <= len(new_id) <= MAX_ID_LENGTH:
        raise ValueError(f"ID-ul trebuie sa aiba intre 1 si {MAX_ID_LENGTH} caractere.")


def build_serial_report(new_id):
    validate_id(new_id)
    serial_bytes = new_id.encode("ascii").ljust(MAX_ID_LENGTH + 1, b"\x00")
    report = bytes([0x00, CMD_SET_SERIAL]) + serial_bytes + b"\x00"
    return report[:REPORT_LENGTH]


def change_id(new_id):
    report = build_serial_report(new_id)

    if hid is None:
        raise RuntimeError(
            "Pachetul Python 'hid' nu este disponibil "
            f"({HID_IMPORT_ERROR}). Instaleaza-l cu: pip install hid"
        )

    device = hid.device()
    try:
        device.open(VID, PID)
        device.send_feature_report(report)
    finally:
        device.close()


def prompt_id():
    return (
        input("Introdu noul ID, max 5 caractere, sau Q pentru iesire: ")
        .strip()
        .upper()
    )


def main():
    while True:
        list_relays()
        new_id = prompt_id()

        if new_id in EXIT_COMMANDS:
            break

        try:
            input(
                f"Conecteaza O SINGURA placa si apasa Enter "
                f"pentru a scrie ID-ul {new_id}..."
            )
            change_id(new_id)

            print("\nComanda trimisa. Scoate si reconecteaza placa USB.")
            input("Dupa reconectare, apasa Enter pentru verificare...")

            list_relays()
            input("Apasa Enter pentru urmatoarea placa...")
        except Exception as exc:
            print(f"\nEroare: {exc}")
            input("Apasa Enter ca sa continui...")


if __name__ == "__main__":
    main()
