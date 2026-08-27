"""Scrierea rapoartelor HID de tip *feature*, fara dependinte native externe.

Pachetul Python ``hid`` este doar un invelis peste biblioteca nativa
``hidapi.dll``, care nu vine impreuna cu pachetul si lipseste pe multe
instalari de Windows (``pip install hid`` nu o aduce). De aceea, pe Windows
folosim direct API-ul din sistem - ``setupapi.dll`` pentru enumerarea
dispozitivelor HID si ``hid.dll`` pentru citirea/scrierea rapoartelor.

Pe alte sisteme se foloseste pachetul ``hid``, daca este disponibil.

Placile USB Relay isi tin ID-ul in primii 5 octeti ai raportului de tip
feature, asa ca putem identifica fiecare placa fara sa depindem de serialul
USB si putem scrie pe o placa anume, chiar daca sunt conectate mai multe.
"""

import ctypes
import os
from dataclasses import dataclass

IS_WINDOWS = os.name == "nt"

VID = 0x16C0
PID = 0x05DF
REPORT_LENGTH = 9
ID_LENGTH = 5


class HidError(RuntimeError):
    """Eroare la enumerarea sau accesarea dispozitivelor HID."""


@dataclass(frozen=True)
class HidRelayDevice:
    """O placa USB Relay vazuta prin stiva HID."""

    path: object
    board_id: str

    @property
    def display_path(self):
        if isinstance(self.path, bytes):
            return self.path.decode("ascii", "replace")
        return str(self.path)

    def label(self):
        return self.board_id or self.display_path


def decode_board_id(buffer):
    """Extrage ID-ul placii din raportul de feature citit de la dispozitiv."""
    payload = bytes(buffer[1 : 1 + ID_LENGTH])
    text = payload.split(b"\x00")[0].decode("ascii", "ignore").strip()
    return "".join(char for char in text if char.isprintable())


def select_device(devices, target_id=None):
    """Alege placa pe care se scrie, cu mesaje explicite cand nu e clar."""
    if target_id:
        for device in devices:
            if device.board_id == target_id:
                return device

        seen = ", ".join(device.label() for device in devices) or "niciuna"
        raise HidError(
            f"Nu am gasit placa cu ID-ul {target_id}. Placi vazute: {seen}."
        )

    if not devices:
        raise HidError(
            "Nicio placa USB Relay gasita pe magistrala HID. "
            "Verifica daca placa este conectata."
        )

    if len(devices) > 1:
        seen = ", ".join(device.label() for device in devices)
        raise HidError(
            f"Sunt conectate {len(devices)} placi ({seen}). "
            "Alege placa tinta sau lasa conectata o singura placa."
        )

    return devices[0]


# --------------------------------------------------------------------------
# Backend Windows: setupapi.dll + hid.dll
# --------------------------------------------------------------------------

DIGCF_PRESENT = 0x02
DIGCF_DEVICEINTERFACE = 0x10
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x01
FILE_SHARE_WRITE = 0x02
OPEN_EXISTING = 3
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class _SpDeviceInterfaceData(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_ulong),
        ("InterfaceClassGuid", _GUID),
        ("Flags", ctypes.c_ulong),
        ("Reserved", ctypes.c_void_p),
    ]


class _HiddAttributes(ctypes.Structure):
    _fields_ = [
        ("Size", ctypes.c_ulong),
        ("VendorID", ctypes.c_ushort),
        ("ProductID", ctypes.c_ushort),
        ("VersionNumber", ctypes.c_ushort),
    ]


class WindowsHidBackend:
    """Enumerare si acces HID prin API-ul Windows."""

    name = "windows"

    def __init__(self):
        self._setupapi = ctypes.WinDLL("setupapi")
        self._hid = ctypes.WinDLL("hid")
        self._kernel32 = ctypes.WinDLL("kernel32")
        self._configure_prototypes()

    def _configure_prototypes(self):
        setupapi, hid, kernel32 = self._setupapi, self._hid, self._kernel32

        setupapi.SetupDiGetClassDevsW.argtypes = [
            ctypes.POINTER(_GUID),
            ctypes.c_wchar_p,
            ctypes.c_void_p,
            ctypes.c_ulong,
        ]
        setupapi.SetupDiGetClassDevsW.restype = ctypes.c_void_p

        setupapi.SetupDiEnumDeviceInterfaces.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.POINTER(_GUID),
            ctypes.c_ulong,
            ctypes.POINTER(_SpDeviceInterfaceData),
        ]
        setupapi.SetupDiEnumDeviceInterfaces.restype = ctypes.c_int

        setupapi.SetupDiGetDeviceInterfaceDetailW.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(_SpDeviceInterfaceData),
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.POINTER(ctypes.c_ulong),
            ctypes.c_void_p,
        ]
        setupapi.SetupDiGetDeviceInterfaceDetailW.restype = ctypes.c_int

        setupapi.SetupDiDestroyDeviceInfoList.argtypes = [ctypes.c_void_p]
        setupapi.SetupDiDestroyDeviceInfoList.restype = ctypes.c_int

        hid.HidD_GetHidGuid.argtypes = [ctypes.POINTER(_GUID)]
        hid.HidD_GetHidGuid.restype = None

        hid.HidD_GetAttributes.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(_HiddAttributes),
        ]
        hid.HidD_GetAttributes.restype = ctypes.c_ubyte

        for func in (hid.HidD_GetFeature, hid.HidD_SetFeature):
            func.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
            func.restype = ctypes.c_ubyte

        kernel32.CreateFileW.argtypes = [
            ctypes.c_wchar_p,
            ctypes.c_ulong,
            ctypes.c_ulong,
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.c_ulong,
            ctypes.c_void_p,
        ]
        kernel32.CreateFileW.restype = ctypes.c_void_p

        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel32.CloseHandle.restype = ctypes.c_int

    # -- primitive ----------------------------------------------------------
    def _open(self, path, access=0):
        """Deschide interfata HID. ``access`` 0 permite doar interogari."""
        handle = self._kernel32.CreateFileW(
            path,
            access,
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            None,
            OPEN_EXISTING,
            0,
            None,
        )

        if handle is None or handle == INVALID_HANDLE_VALUE:
            return None
        return handle

    def _interface_paths(self):
        """Return caile tuturor interfetelor HID prezente in sistem."""
        guid = _GUID()
        self._hid.HidD_GetHidGuid(ctypes.byref(guid))

        dev_info = self._setupapi.SetupDiGetClassDevsW(
            ctypes.byref(guid), None, None, DIGCF_PRESENT | DIGCF_DEVICEINTERFACE
        )
        if dev_info is None or dev_info == INVALID_HANDLE_VALUE:
            raise HidError("Nu pot enumera dispozitivele HID (SetupDiGetClassDevs).")

        # Dimensiunea ceruta de API difera intre 32 si 64 de biti.
        detail_size = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6
        paths = []

        try:
            index = 0
            while True:
                interface = _SpDeviceInterfaceData()
                interface.cbSize = ctypes.sizeof(_SpDeviceInterfaceData)

                if not self._setupapi.SetupDiEnumDeviceInterfaces(
                    dev_info, None, ctypes.byref(guid), index, ctypes.byref(interface)
                ):
                    break

                index += 1
                required = ctypes.c_ulong(0)
                self._setupapi.SetupDiGetDeviceInterfaceDetailW(
                    dev_info, ctypes.byref(interface), None, 0,
                    ctypes.byref(required), None,
                )

                if required.value == 0:
                    continue

                buffer = ctypes.create_string_buffer(required.value)
                ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ulong))[0] = detail_size

                if not self._setupapi.SetupDiGetDeviceInterfaceDetailW(
                    dev_info, ctypes.byref(interface), buffer, required,
                    None, None,
                ):
                    continue

                # DevicePath incepe imediat dupa campul cbSize (4 octeti).
                path = ctypes.wstring_at(ctypes.addressof(buffer) + 4)
                if path:
                    paths.append(path)
        finally:
            self._setupapi.SetupDiDestroyDeviceInfoList(dev_info)

        return paths

    def _matches(self, handle, vid, pid):
        attributes = _HiddAttributes()
        attributes.Size = ctypes.sizeof(_HiddAttributes)

        if not self._hid.HidD_GetAttributes(handle, ctypes.byref(attributes)):
            return False

        return attributes.VendorID == vid and attributes.ProductID == pid

    def _read_board_id(self, path):
        handle = self._open(path, GENERIC_READ)
        if handle is None:
            return ""

        try:
            buffer = ctypes.create_string_buffer(REPORT_LENGTH)
            buffer[0] = b"\x00"
            if not self._hid.HidD_GetFeature(handle, buffer, REPORT_LENGTH):
                return ""
            return decode_board_id(buffer.raw)
        finally:
            self._kernel32.CloseHandle(handle)

    # -- interfata backendului ----------------------------------------------
    def list_devices(self, vid=VID, pid=PID):
        devices = []

        for path in self._interface_paths():
            handle = self._open(path)
            if handle is None:
                continue

            try:
                if not self._matches(handle, vid, pid):
                    continue
            finally:
                self._kernel32.CloseHandle(handle)

            devices.append(HidRelayDevice(path, self._read_board_id(path)))

        return devices

    def send_feature_report(self, device, report):
        handle = self._open(device.path, GENERIC_READ | GENERIC_WRITE)
        if handle is None:
            raise HidError(
                f"Nu pot deschide placa {device.label()} pentru scriere. "
                "Inchide alte programe care o folosesc si incearca din nou."
            )

        try:
            buffer = ctypes.create_string_buffer(bytes(report), len(report))
            if not self._hid.HidD_SetFeature(handle, buffer, len(report)):
                raise HidError(
                    "Scrierea raportului HID a esuat "
                    f"(cod Windows {ctypes.GetLastError()})."
                )
        finally:
            self._kernel32.CloseHandle(handle)


# --------------------------------------------------------------------------
# Backend de rezerva: pachetul Python `hid`
# --------------------------------------------------------------------------


class HidPackageBackend:
    """Foloseste pachetul ``hid`` (necesita biblioteca nativa hidapi)."""

    name = "hid"

    def __init__(self):
        import hid  # noqa: PLC0415 - import intentionat tarziu

        self._hid = hid

    def list_devices(self, vid=VID, pid=PID):
        devices = []

        for entry in self._hid.enumerate(vid, pid):
            path = entry.get("path")
            devices.append(HidRelayDevice(path, self._read_board_id(path)))

        return devices

    def _read_board_id(self, path):
        device = self._hid.device()
        try:
            device.open_path(path)
            report = device.get_feature_report(0, REPORT_LENGTH)
        except Exception:  # noqa: BLE001 - placa poate refuza citirea
            return ""
        else:
            return decode_board_id(bytes(report))
        finally:
            try:
                device.close()
            except Exception:  # noqa: BLE001
                pass

    def send_feature_report(self, device, report):
        handle = self._hid.device()
        try:
            handle.open_path(device.path)
            handle.send_feature_report(report)
        finally:
            handle.close()


def _backend_error():
    if IS_WINDOWS:
        return HidError(
            "Nu pot accesa stiva HID a sistemului (setupapi.dll / hid.dll)."
        )

    return HidError(
        "Scrierea ID-ului are nevoie de pachetul Python 'hid' pe acest sistem. "
        "Instaleaza-l cu: pip install hid"
    )


def get_backend():
    """Return backendul HID disponibil, preferandu-l pe cel nativ Windows."""
    if IS_WINDOWS:
        try:
            return WindowsHidBackend()
        except (OSError, AttributeError):
            pass

    try:
        return HidPackageBackend()
    except Exception:  # noqa: BLE001 - pachetul lipseste sau nu isi gaseste hidapi
        raise _backend_error() from None


def list_relay_devices(vid=VID, pid=PID):
    return get_backend().list_devices(vid, pid)


def write_feature_report(report, vid=VID, pid=PID, target_id=None):
    """Scrie raportul pe placa aleasa si return eticheta placii folosite."""
    backend = get_backend()
    device = select_device(backend.list_devices(vid, pid), target_id)
    backend.send_feature_report(device, report)
    return device.label()
