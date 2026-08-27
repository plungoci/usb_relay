"""USB Relay Controller - interfata grafica PySide6 peste USB_RELAY_DEVICE.dll.

Aplicatia are doua file:

* **Control relee** - scaneaza placile conectate, alegi cate folosesti (1-4)
  si comanzi fiecare canal sau toate deodata;
* **Schimba ID placa** - varianta grafica a utilitarului
  ``change_usbrelay_id.py``, pentru scrierea unui serial nou pe placa.

Biblioteca nativa nu este thread-safe, asa ca toate apelurile trec printr-un
singur thread de lucru (:class:`RelayService`), iar rezultatele ajung in
interfata prin semnale Qt.
"""

import sys
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import (
    QObject,
    QRegularExpression,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QFont, QRegularExpressionValidator
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from change_usbrelay_id import MAX_ID_LENGTH, change_id, validate_id
from usb_relay_lib import RelayController, format_devices

MIN_BOARD_COUNT = 1
MAX_BOARD_COUNT = 4
DEFAULT_BOARD_COUNT = MAX_BOARD_COUNT
SHUTDOWN_TIMEOUT_SECONDS = 5

ON_STYLE = """
QPushButton {
    background-color: #2e9e4f;
    color: #ffffff;
    font-weight: 600;
    border: 1px solid #24803f;
    border-radius: 4px;
    padding: 6px 12px;
}
QPushButton:disabled { background-color: #8ec5a0; color: #f0f0f0; }
"""

OFF_STYLE = """
QPushButton {
    background-color: #d6d6d6;
    color: #303030;
    font-weight: 600;
    border: 1px solid #b5b5b5;
    border-radius: 4px;
    padding: 6px 12px;
}
QPushButton:disabled { background-color: #ebebeb; color: #9a9a9a; }
"""


# --- operatii executate pe threadul de lucru ---------------------------------
# Fiecare functie primeste controllerul ca prim argument si ruleaza pe acelasi
# thread, pentru ca biblioteca nativa nu suporta apeluri concurente.


def op_scan(controller, board_count=None):
    """Rescaneaza placile si citeste starea celor folosite."""
    devices = controller.scan()
    serials = [device.serial for device in devices]
    if board_count is not None:
        serials = serials[:board_count]
    return devices, controller.read_all_states(serials)


def op_read_states(controller, serials):
    return controller.read_all_states(serials)


def op_set_channel(controller, serial, index, state):
    return serial, controller.set_channel(serial, index, state)


def op_set_boards(controller, serials, state):
    return controller.set_boards(serials, state)


def op_write_id(controller, new_id, target_id=None):
    """Elibereaza placile, apoi scrie noul serial prin stiva HID."""
    controller.release_devices()
    written_on = change_id(new_id, target_id)
    return new_id, written_on


class _CallSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)


class RelayService(QObject):
    """Executa operatiile pe biblioteca nativa pe un singur thread de lucru."""

    def __init__(self, controller=None, parent=None):
        super().__init__(parent)
        self.controller = controller if controller is not None else RelayController()
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="usbrelay"
        )
        self._calls = []

    def submit(self, fn, *args, on_result=None, on_error=None):
        signals = _CallSignals()
        self._calls.append(signals)

        def cleanup():
            if signals in self._calls:
                self._calls.remove(signals)

        if on_result is not None:
            signals.finished.connect(on_result)
        if on_error is not None:
            signals.failed.connect(on_error)

        signals.finished.connect(lambda _: cleanup())
        signals.failed.connect(lambda _: cleanup())

        self._executor.submit(self._run, signals, fn, args)
        return signals

    def _run(self, signals, fn, args):
        try:
            result = fn(self.controller, *args)
        except Exception as exc:  # noqa: BLE001 - orice eroare ajunge in interfata
            signals.failed.emit(str(exc))
        else:
            signals.finished.emit(result)

    def shutdown(self):
        self._executor.submit(self.controller.close)
        self._executor.shutdown(wait=True)


class RelayControlPage(QWidget):
    """Controlul canalelor pentru placile detectate."""

    statusMessage = Signal(str)

    def __init__(self, service, parent=None):
        super().__init__(parent)
        self.service = service
        self.devices = []
        self.states = {}
        self.buttons = {}
        self.board_count = DEFAULT_BOARD_COUNT

        layout = QVBoxLayout(self)
        layout.addLayout(self._build_toolbar())

        self.boards_layout = QHBoxLayout()
        self.boards_layout.setSpacing(12)
        layout.addLayout(self.boards_layout)
        layout.addStretch(1)

        self._rebuild_boards()

    # -- constructia interfetei -------------------------------------------------
    def _build_toolbar(self):
        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Placi de relee folosite:"))

        self.board_selector = QComboBox()
        for count in range(MIN_BOARD_COUNT, MAX_BOARD_COUNT + 1):
            label = "1 placa" if count == 1 else f"{count} placi"
            self.board_selector.addItem(label, count)
        self.board_selector.setCurrentIndex(DEFAULT_BOARD_COUNT - MIN_BOARD_COUNT)
        self.board_selector.currentIndexChanged.connect(self._on_board_count_changed)
        toolbar.addWidget(self.board_selector)

        self.scan_button = QPushButton("Scaneaza placi")
        self.scan_button.clicked.connect(self.scan)
        toolbar.addWidget(self.scan_button)

        self.read_button = QPushButton("Citeste starea")
        self.read_button.clicked.connect(self.read_states)
        toolbar.addWidget(self.read_button)

        toolbar.addStretch(1)

        self.all_on_button = QPushButton("ALL ON")
        self.all_on_button.setStyleSheet(ON_STYLE)
        self.all_on_button.clicked.connect(lambda: self.set_all(True))
        toolbar.addWidget(self.all_on_button)

        self.all_off_button = QPushButton("ALL OFF")
        self.all_off_button.setStyleSheet(OFF_STYLE)
        self.all_off_button.clicked.connect(lambda: self.set_all(False))
        toolbar.addWidget(self.all_off_button)

        return toolbar

    def used_devices(self):
        return self.devices[: self.board_count]

    def used_serials(self):
        return [device.serial for device in self.used_devices()]

    def _rebuild_boards(self):
        while self.boards_layout.count():
            item = self.boards_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        self.buttons.clear()

        # placile au inaltimi diferite (4 sau 8 canale), deci le aliniem sus
        for device in self.used_devices():
            self.boards_layout.addWidget(self._build_board(device), 0, Qt.AlignTop)

        for position in range(len(self.used_devices()) + 1, self.board_count + 1):
            self.boards_layout.addWidget(
                self._build_missing_board(position), 0, Qt.AlignTop
            )

        self.boards_layout.addStretch(1)

    def _build_board(self, device):
        box = QGroupBox(device.label())
        box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        grid = QGridLayout(box)

        states = self.states.get(device.serial) or [False] * device.channels

        for index in range(1, device.channels + 1):
            grid.addWidget(QLabel(f"Relay {index}"), index - 1, 0)

            button = QPushButton()
            button.setMinimumWidth(90)
            button.clicked.connect(
                lambda _checked=False, s=device.serial, i=index: self.toggle(s, i)
            )
            grid.addWidget(button, index - 1, 1)

            self.buttons[(device.serial, index)] = button

        self.states.setdefault(device.serial, states)
        self._refresh_board_buttons(device.serial)
        return box

    def _build_missing_board(self, position):
        box = QGroupBox(f"Placa {position}")
        box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        box.setEnabled(False)

        layout = QVBoxLayout(box)
        layout.addWidget(QLabel("neconectata"))
        return box

    def _refresh_board_buttons(self, serial):
        states = self.states.get(serial) or []

        for index, is_on in enumerate(states, start=1):
            button = self.buttons.get((serial, index))
            if button is None:
                continue
            button.setText("ON" if is_on else "OFF")
            button.setStyleSheet(ON_STYLE if is_on else OFF_STYLE)

    def _set_busy(self, busy):
        for button in self.buttons.values():
            button.setEnabled(not busy)

        self.scan_button.setEnabled(not busy)
        self.read_button.setEnabled(not busy)
        self.all_on_button.setEnabled(not busy)
        self.all_off_button.setEnabled(not busy)
        self.board_selector.setEnabled(not busy)

    def _apply_state_results(self, results):
        """Actualizeaza butoanele din ``{serial: (states, error)}``."""
        failures = []

        for serial, (states, error) in results.items():
            if error is None:
                self.states[serial] = states
                self._refresh_board_buttons(serial)
            else:
                failures.append(f"{serial}: {error}")

        return failures

    # -- actiuni ----------------------------------------------------------------
    def invalidate(self):
        """Marcheaza lista de placi ca invechita, dupa schimbarea unui ID."""
        self.devices = []
        self.states = {}
        self._rebuild_boards()
        self.statusMessage.emit("Lista de placi s-a schimbat. Apasa 'Scaneaza placi'.")

    def sync_devices(self, devices):
        """Preia o lista de placi scanata din alta parte a interfetei."""
        self.devices = devices
        self.states = {}
        self._rebuild_boards()

        if devices:
            self.read_states()
        else:
            self.statusMessage.emit("Nicio placa detectata.")

    def _on_board_count_changed(self, index):
        self.board_count = self.board_selector.itemData(index)
        self._rebuild_boards()

        if not self.devices:
            return

        detected = len(self.devices)
        if detected < self.board_count:
            self.statusMessage.emit(
                f"Ai ales {self.board_count} placi, dar sunt detectate {detected}."
            )
        else:
            self.statusMessage.emit(f"Placi active: {', '.join(self.used_serials())}")

    def scan(self):
        self._set_busy(True)
        self.statusMessage.emit("Scanez placile conectate...")
        self.service.submit(
            op_scan,
            self.board_count,
            on_result=self._finish_scan,
            on_error=self._fail,
        )

    def _finish_scan(self, result):
        devices, results = result
        self.devices = devices
        self.states = {}
        self._rebuild_boards()

        failures = self._apply_state_results(results)
        self._set_busy(False)

        if not devices:
            self.statusMessage.emit("Nicio placa detectata.")
            return

        message = f"Detectate {len(devices)} placi: " + ", ".join(
            device.label() for device in devices
        )
        if len(devices) < self.board_count:
            message += f" (ai ales {self.board_count})"
        self.statusMessage.emit(message)

        if failures:
            QMessageBox.warning(
                self, "Atentie", "Nu pot citi starea:\n" + "\n".join(failures)
            )

    def read_states(self):
        serials = self.used_serials()
        if not serials:
            self.statusMessage.emit("Nicio placa activa. Apasa 'Scaneaza placi'.")
            return

        self._set_busy(True)
        self.statusMessage.emit("Citesc starea releelor...")
        self.service.submit(
            op_read_states,
            serials,
            on_result=self._finish_read_states,
            on_error=self._fail,
        )

    def _finish_read_states(self, results):
        failures = self._apply_state_results(results)
        self._set_busy(False)

        if failures:
            self.statusMessage.emit("Nu pot citi starea tuturor placilor.")
            QMessageBox.critical(self, "Eroare", "\n".join(failures))
            return

        self.statusMessage.emit("Stare actualizata din hardware.")

    def toggle(self, serial, index):
        states = self.states.get(serial) or []
        new_state = not (states[index - 1] if index <= len(states) else False)

        self._set_busy(True)
        self.statusMessage.emit(
            f"{serial} Relay {index}: trimit {'ON' if new_state else 'OFF'}..."
        )
        self.service.submit(
            op_set_channel,
            serial,
            index,
            new_state,
            on_result=self._finish_toggle,
            on_error=self._fail,
        )

    def _finish_toggle(self, result):
        serial, states = result
        self.states[serial] = states
        self._refresh_board_buttons(serial)
        self._set_busy(False)
        self.statusMessage.emit(
            f"{serial}: " + " ".join(
                f"{index}={'ON' if is_on else 'OFF'}"
                for index, is_on in enumerate(states, start=1)
            )
        )

    def set_all(self, state):
        serials = self.used_serials()
        if not serials:
            self.statusMessage.emit("Nicio placa activa. Apasa 'Scaneaza placi'.")
            return

        self._set_busy(True)
        self.statusMessage.emit(
            f"Trimit {'ON' if state else 'OFF'} catre {len(serials)} placi..."
        )
        self.service.submit(
            op_set_boards,
            serials,
            state,
            on_result=lambda results, s=state: self._finish_set_all(s, results),
            on_error=self._fail,
        )

    def _finish_set_all(self, state, results):
        failures = self._apply_state_results(results)
        self._set_busy(False)

        if failures:
            self.statusMessage.emit(f"{len(failures)} placi nu au raspuns.")
            QMessageBox.critical(
                self, "Eroare", "Nu pot controla:\n" + "\n".join(failures)
            )
            return

        self.statusMessage.emit(
            f"Toate releele active sunt {'ON' if state else 'OFF'}."
        )

    def _fail(self, message):
        self._set_busy(False)
        self.statusMessage.emit("Operatia a esuat.")
        QMessageBox.critical(self, "Eroare", message)


class ChangeIdPage(QWidget):
    """Varianta grafica a utilitarului change_usbrelay_id."""

    statusMessage = Signal(str)
    devicesRefreshed = Signal(list)
    boardsChanged = Signal()

    def __init__(self, service, parent=None):
        super().__init__(parent)
        self.service = service

        layout = QVBoxLayout(self)

        warning = QLabel(
            "Alege placa tinta sau lasa conectata o singura placa. "
            "Dupa scriere, deconecteaza si reconecteaza placa, apoi "
            "reimprospateaza lista pentru verificare."
        )
        warning.setWordWrap(True)
        warning.setStyleSheet("color: #a04000; font-weight: 600;")
        layout.addWidget(warning)

        layout.addWidget(QLabel("Placi detectate (USB_RELAY_DEVICE.dll):"))

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setFont(QFont("Courier New", 10))
        self.output.setPlaceholderText("Apasa 'Reimprospateaza lista'.")
        layout.addWidget(self.output, 1)

        self.refresh_button = QPushButton("Reimprospateaza lista")
        self.refresh_button.clicked.connect(self.refresh_list)

        refresh_row = QHBoxLayout()
        refresh_row.addWidget(self.refresh_button)
        refresh_row.addStretch(1)
        layout.addLayout(refresh_row)

        target_row = QHBoxLayout()
        target_row.addWidget(QLabel("Placa tinta:"))

        self.target_selector = QComboBox()
        self.target_selector.setMinimumWidth(220)
        self._fill_targets([])
        target_row.addWidget(self.target_selector)
        target_row.addStretch(1)
        layout.addLayout(target_row)

        id_row = QHBoxLayout()
        id_row.addWidget(QLabel("ID nou:"))

        self.id_edit = QLineEdit()
        self.id_edit.setMaxLength(MAX_ID_LENGTH)
        self.id_edit.setPlaceholderText(f"max {MAX_ID_LENGTH} caractere, ex. RLY01")
        self.id_edit.setValidator(
            QRegularExpressionValidator(
                QRegularExpression(f"[A-Za-z0-9]{{0,{MAX_ID_LENGTH}}}")
            )
        )
        self.id_edit.textChanged.connect(self._force_uppercase)
        self.id_edit.returnPressed.connect(self.write_id)
        id_row.addWidget(self.id_edit)

        self.write_button = QPushButton("Scrie ID pe placa")
        self.write_button.clicked.connect(self.write_id)
        id_row.addWidget(self.write_button)

        layout.addLayout(id_row)

    def _fill_targets(self, devices):
        """Reincarca lista de placi tinta, pastrand selectia daca se poate."""
        previous = self.target_selector.currentData()
        self.target_selector.clear()
        self.target_selector.addItem("(placa unica conectata)", None)

        for device in devices:
            self.target_selector.addItem(device.label(), device.serial)

        if previous is not None:
            index = self.target_selector.findData(previous)
            if index >= 0:
                self.target_selector.setCurrentIndex(index)

    def _force_uppercase(self, text):
        if text != text.upper():
            self.id_edit.setText(text.upper())

    def _set_busy(self, busy):
        self.refresh_button.setEnabled(not busy)
        self.write_button.setEnabled(not busy)
        self.id_edit.setEnabled(not busy)
        self.target_selector.setEnabled(not busy)

    def refresh_list(self):
        self._set_busy(True)
        self.statusMessage.emit("Citesc lista de placi...")
        self.service.submit(
            op_scan,
            on_result=self._show_list,
            on_error=self._fail,
        )

    def _show_list(self, result):
        devices, _ = result
        self._set_busy(False)
        self.output.setPlainText(format_devices(devices))
        self._fill_targets(devices)
        self.statusMessage.emit(f"Lista actualizata: {len(devices)} placi.")
        self.devicesRefreshed.emit(devices)

    def write_id(self):
        new_id = self.id_edit.text().strip().upper()

        try:
            validate_id(new_id)
        except ValueError as exc:
            QMessageBox.warning(self, "ID invalid", str(exc))
            return

        target_id = self.target_selector.currentData()
        target_text = (
            f"placa {target_id}" if target_id else "placa conectata"
        )

        confirm = QMessageBox.question(
            self,
            "Confirmare",
            f"Scriu ID-ul {new_id} pe {target_text}?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return

        self._set_busy(True)
        self.statusMessage.emit(f"Scriu ID-ul {new_id}...")
        self.service.submit(
            op_write_id,
            new_id,
            target_id,
            on_result=self._finish_write,
            on_error=self._fail,
        )

    def _finish_write(self, result):
        new_id, written_on = result
        self._set_busy(False)
        self.statusMessage.emit(f"ID-ul {new_id} a fost trimis catre {written_on}.")
        self.boardsChanged.emit()
        QMessageBox.information(
            self,
            "Comanda trimisa",
            f"ID-ul {new_id} a fost trimis catre {written_on}.\n\n"
            "Scoate si reconecteaza placa USB, apoi apasa "
            "'Reimprospateaza lista' pentru verificare.",
        )

    def _fail(self, message):
        self._set_busy(False)
        self.statusMessage.emit("Operatia a esuat.")
        QMessageBox.critical(self, "Eroare", message)


class MainWindow(QMainWindow):
    def __init__(self, service=None):
        super().__init__()
        self.setWindowTitle("USB Relay Controller")

        self.service = service if service is not None else RelayService()
        self.relay_page = RelayControlPage(self.service)
        self.change_id_page = ChangeIdPage(self.service)

        tabs = QTabWidget()
        tabs.addTab(self.relay_page, "Control relee")
        tabs.addTab(self.change_id_page, "Schimba ID placa")
        self.setCentralWidget(tabs)

        for page in (self.relay_page, self.change_id_page):
            page.statusMessage.connect(self._show_status)

        self.change_id_page.devicesRefreshed.connect(self.relay_page.sync_devices)
        self.change_id_page.boardsChanged.connect(self.relay_page.invalidate)

        self.statusBar().showMessage("Scanez placile conectate...")
        QTimer.singleShot(0, self.relay_page.scan)

    def _show_status(self, message):
        self.statusBar().showMessage(message, 8000)

    def closeEvent(self, event):
        self.service.shutdown()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    window = MainWindow()
    window.resize(920, 520)
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
