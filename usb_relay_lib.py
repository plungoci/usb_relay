"""Binding ctypes peste ``USB_RELAY_DEVICE.dll`` (USB Relay Device Library v2).

Modulul inlocuieste apelurile catre ``usbrelay.exe`` cu apeluri directe in
biblioteca nativa livrata in directorul ``lib/``.

Doua constrangeri din documentatia bibliotecii se reflecta in cod:

* biblioteca **nu este thread-safe** - toate apelurile trebuie facute dintr-un
  singur thread (interfata grafica foloseste un executor cu un singur worker);
* biblioteca **nu detecteaza conectarea/deconectarea la cald** - lista de placi
  se reimprospateaza doar la o rescanare explicita.
"""

import ctypes
import os
import sys
from ctypes import POINTER, Structure, c_char_p, c_int, c_ssize_t, c_uint
from dataclasses import dataclass

LIB_PATH_ENV = "USB_RELAY_DLL"
LIB_DIR_NAME = "lib"
WINDOWS_LIB_NAMES = ("USB_RELAY_DEVICE.dll", "usb_relay_device.dll")
POSIX_LIB_NAMES = ("libusb_relay_device.so", "usb_relay_device.so")

MAX_SERIAL_LENGTH = 5

# Coduri de retur documentate in usb_relay_device.h
RESULT_OK = 0
RESULT_ERROR = 1
RESULT_INVALID_INDEX = 2


class UsbRelayError(RuntimeError):
    """Eroare raportata de biblioteca nativa sau de incarcarea acesteia."""


class UsbRelayDeviceInfo(Structure):
    """Oglindeste ``struct usb_relay_device_info`` din usb_relay_device.h."""


UsbRelayDeviceInfo._fields_ = [
    ("serial_number", c_char_p),
    ("device_path", c_char_p),
    ("type", c_ssize_t),
    ("next", POINTER(UsbRelayDeviceInfo)),
]


@dataclass(frozen=True)
class RelayDevice:
    """Descrierea unei placi detectate."""

    serial: str
    device_path: str
    channels: int

    def label(self):
        return f"{self.serial} ({self.channels} canale)"


def find_library_path():
    """Cauta biblioteca nativa langa scripturi, apoi lasa loader-ul sa caute."""
    names = WINDOWS_LIB_NAMES if os.name == "nt" else POSIX_LIB_NAMES

    # O cale setata explicit are prioritate si nu este inlocuita in tacere,
    # ca mesajul de eroare sa arate exact ce a cerut utilizatorul.
    from_env = os.environ.get(LIB_PATH_ENV)
    if from_env:
        return from_env

    candidates = []
    base_dir = os.path.dirname(os.path.abspath(__file__))
    for directory in (os.path.join(base_dir, LIB_DIR_NAME), base_dir, os.getcwd()):
        candidates.extend(os.path.join(directory, name) for name in names)

    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate

    return names[0]


def _load_error_message(path, exc):
    lines = [f"Nu pot incarca biblioteca USB Relay ({path}): {exc}"]

    if not os.path.isfile(path):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        lines.append(
            f"Fisierul nu a fost gasit. Pune biblioteca in "
            f"{os.path.join(base_dir, LIB_DIR_NAME)} sau seteaza variabila "
            f"{LIB_PATH_ENV} catre calea ei."
        )

    if os.name != "nt":
        lines.append(
            "USB_RELAY_DEVICE.dll ruleaza doar pe Windows. Pe alte sisteme "
            f"seteaza variabila {LIB_PATH_ENV} catre o biblioteca compatibila."
        )
    elif sys.maxsize <= 2**32:
        lines.append(
            "Rulezi Python pe 32 de biti, iar DLL-ul din lib/ este pe 64 de biti. "
            "Foloseste Python 64-bit sau DLL-ul pe 32 de biti."
        )
    else:
        lines.append(
            "Verifica daca DLL-ul are aceeasi arhitectura ca Python si daca "
            "este instalat pachetul VC++ redistributable."
        )

    return "\n".join(lines)


class UsbRelayLibrary:
    """Invelis subtire peste functiile exportate de biblioteca nativa."""

    def __init__(self, library_path=None):
        self.path = library_path or find_library_path()

        try:
            self._lib = ctypes.CDLL(self.path)
        except OSError as exc:
            raise UsbRelayError(_load_error_message(self.path, exc)) from exc

        self._configure_prototypes()
        self._initialized = False

    def _configure_prototypes(self):
        lib = self._lib

        lib.usb_relay_init.argtypes = []
        lib.usb_relay_init.restype = c_int

        lib.usb_relay_exit.argtypes = []
        lib.usb_relay_exit.restype = c_int

        lib.usb_relay_device_enumerate.argtypes = []
        lib.usb_relay_device_enumerate.restype = POINTER(UsbRelayDeviceInfo)

        lib.usb_relay_device_free_enumerate.argtypes = [POINTER(UsbRelayDeviceInfo)]
        lib.usb_relay_device_free_enumerate.restype = None

        lib.usb_relay_device_open_with_serial_number.argtypes = [c_char_p, c_uint]
        lib.usb_relay_device_open_with_serial_number.restype = c_ssize_t

        lib.usb_relay_device_close.argtypes = [c_ssize_t]
        lib.usb_relay_device_close.restype = None

        for name in (
            "usb_relay_device_open_one_relay_channel",
            "usb_relay_device_close_one_relay_channel",
        ):
            func = getattr(lib, name)
            func.argtypes = [c_ssize_t, c_int]
            func.restype = c_int

        for name in (
            "usb_relay_device_open_all_relay_channel",
            "usb_relay_device_close_all_relay_channel",
            "usb_relay_device_get_status_bitmap",
            "usb_relay_device_get_num_relays",
        ):
            func = getattr(lib, name)
            func.argtypes = [c_ssize_t]
            func.restype = c_int

        lib.usb_relay_device_lib_version.argtypes = []
        lib.usb_relay_device_lib_version.restype = c_int

    # -- ciclul de viata --------------------------------------------------------
    def init(self):
        if self._initialized:
            return

        if self._lib.usb_relay_init() != RESULT_OK:
            raise UsbRelayError("usb_relay_init() a esuat.")

        self._initialized = True

    def exit(self):
        if not self._initialized:
            return

        self._initialized = False
        self._lib.usb_relay_exit()

    def version(self):
        """Versiunea bibliotecii (doar cei mai putin semnificativi 16 biti)."""
        return self._lib.usb_relay_device_lib_version() & 0xFFFF

    # -- enumerare --------------------------------------------------------------
    def enumerate_devices(self):
        """Return lista de :class:`RelayDevice` pentru placile conectate."""
        head = self._lib.usb_relay_device_enumerate()
        if not head:
            return []

        devices = []
        try:
            node = head
            while node:
                info = node.contents
                serial = (info.serial_number or b"").decode("ascii", "replace")
                device_path = (info.device_path or b"").decode("ascii", "replace")

                # get_num_relays primeste pointerul ca intreg de dimensiunea
                # unui pointer, conform functiilor ajutatoare din DLL.
                node_as_int = ctypes.cast(node, ctypes.c_void_p).value
                channels = self._lib.usb_relay_device_get_num_relays(node_as_int)
                if channels <= 0:
                    channels = int(info.type) if info.type > 0 else 0

                devices.append(RelayDevice(serial, device_path, channels))
                node = info.next
        finally:
            self._lib.usb_relay_device_free_enumerate(head)

        return devices

    # -- comenzi ----------------------------------------------------------------
    def open_device(self, serial):
        encoded = serial.encode("ascii")
        handle = self._lib.usb_relay_device_open_with_serial_number(
            encoded, len(encoded)
        )

        if not handle:
            raise UsbRelayError(f"Nu pot deschide placa {serial}.")

        return handle

    def close_device(self, handle):
        self._lib.usb_relay_device_close(handle)

    def set_channel(self, handle, index, state):
        func = (
            self._lib.usb_relay_device_open_one_relay_channel
            if state
            else self._lib.usb_relay_device_close_one_relay_channel
        )
        self._check(func(handle, index), f"canalul {index}")

    def set_all_channels(self, handle, state):
        func = (
            self._lib.usb_relay_device_open_all_relay_channel
            if state
            else self._lib.usb_relay_device_close_all_relay_channel
        )
        self._check(func(handle), "toate canalele")

    def get_status_bitmap(self, handle):
        status = self._lib.usb_relay_device_get_status_bitmap(handle)
        if status < 0:
            raise UsbRelayError("Nu pot citi starea releelor.")
        return status

    @staticmethod
    def _check(result, what):
        if result == RESULT_OK:
            return
        if result == RESULT_INVALID_INDEX:
            raise UsbRelayError(f"Index invalid pentru {what}.")
        raise UsbRelayError(f"Comanda a esuat pentru {what}.")


def bitmap_to_states(bitmap, channels):
    """Transforma masca de biti returnata de biblioteca in lista de bool."""
    return [bool(bitmap & (1 << index)) for index in range(channels)]


def format_devices(devices):
    """Text lizibil cu placile detectate, pentru afisare in interfata sau CLI."""
    if not devices:
        return "Nicio placa detectata."

    lines = []
    for position, device in enumerate(devices, start=1):
        lines.append(
            f"{position}. ID: {device.serial:<6} canale: {device.channels}"
        )
        # Unele versiuni ale bibliotecii returneaza "NOTHING" ca substitut
        # pentru calea dispozitivului; nu are rost afisata.
        path = device.device_path
        if path and path.upper() != "NOTHING":
            lines.append(f"   cale: {path}")

    return "\n".join(lines)


class RelayController:
    """Gestioneaza biblioteca si handle-urile placilor detectate.

    Clasa **nu este thread-safe**: toate metodele trebuie apelate din acelasi
    thread, asa cum cere biblioteca nativa.
    """

    def __init__(self, library=None, library_path=None):
        self._library = library
        self._library_path = library_path
        self._devices = []
        self._handles = {}

    @property
    def library(self):
        if self._library is None:
            self._library = UsbRelayLibrary(self._library_path)
            self._library.init()
        return self._library

    @property
    def devices(self):
        return list(self._devices)

    def device(self, serial):
        for device in self._devices:
            if device.serial == serial:
                return device
        raise UsbRelayError(f"Placa {serial} nu mai este in lista detectata.")

    def scan(self):
        """Reimprospateaza lista de placi; inchide handle-urile vechi."""
        self.release_devices()
        self._devices = self.library.enumerate_devices()
        return self.devices

    def release_devices(self):
        """Inchide toate handle-urile deschise, fara a inchide biblioteca.

        Necesar inainte de scrierea unui ID nou prin ``hid``, ca placa sa nu
        ramana ocupata de biblioteca nativa.
        """
        for handle in self._handles.values():
            try:
                self._library.close_device(handle)
            except Exception:  # noqa: BLE001 - inchiderea nu trebuie sa arunce
                pass
        self._handles.clear()

    def close(self):
        self.release_devices()
        self._devices = []

        if self._library is not None:
            self._library.exit()
            self._library = None

    def _handle(self, serial):
        if serial not in self._handles:
            self._handles[serial] = self.library.open_device(serial)
        return self._handles[serial]

    def read_states(self, serial):
        device = self.device(serial)
        bitmap = self.library.get_status_bitmap(self._handle(serial))
        return bitmap_to_states(bitmap, device.channels)

    def set_channel(self, serial, index, state):
        self.library.set_channel(self._handle(serial), index, state)
        return self.read_states(serial)

    def set_board(self, serial, state):
        self.library.set_all_channels(self._handle(serial), state)
        return self.read_states(serial)

    def read_all_states(self, serials):
        """Return ``{serial: (states, error)}`` pentru placile cerute."""
        results = {}
        for serial in serials:
            try:
                results[serial] = (self.read_states(serial), None)
            except UsbRelayError as exc:
                results[serial] = (None, str(exc))
        return results

    def set_boards(self, serials, state):
        """Aplica aceeasi comanda pe mai multe placi, secvential."""
        results = {}
        for serial in serials:
            try:
                results[serial] = (self.set_board(serial, state), None)
            except UsbRelayError as exc:
                results[serial] = (None, str(exc))
        return results
