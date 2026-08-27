"""USB Relay Controller - interfata grafica PySide6.

Aplicatia are doua sectiuni:

* **Control relee** - alegi cate placi folosesti (1-4) si comanzi fiecare
  releu individual sau toate deodata;
* **Schimba ID placa** - varianta grafica a utilitarului
  ``change_usbrelay_id.py``, pentru scrierea unui serial nou pe placa.
"""

import concurrent.futures
import subprocess
import sys

from PySide6.QtCore import (
    QObject,
    QRegularExpression,
    QRunnable,
    QThreadPool,
    Signal,
    Slot,
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

from change_usbrelay_id import MAX_ID_LENGTH, change_id, list_relays_output, validate_id

USBRELAY_EXE = "usbrelay.exe"
ALL_BOARDS = ("RLY01", "RLY02", "RLY03", "RLY04")
RELAYS_PER_BOARD = 4
MIN_BOARD_COUNT = 1
MAX_BOARD_COUNT = len(ALL_BOARDS)
DEFAULT_BOARD_COUNT = MAX_BOARD_COUNT
COMMAND_TIMEOUT_SECONDS = 5
MAX_WORKERS = MAX_BOARD_COUNT * RELAYS_PER_BOARD

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


def run_usbrelay(serial, relay, state):
    """Run usbrelay.exe for one relay and return ``(success, message)``."""
    cmd = [
        USBRELAY_EXE,
        "-serial",
        serial,
        "-on" if state else "-off",
        str(relay),
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT_SECONDS,
            shell=False,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"{serial} Relay {relay}: {exc}"

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        return False, f"{serial} Relay {relay}: {detail or result.returncode}"

    return True, ""


def run_all_commands(commands):
    """Run several relay commands in parallel and return the results."""
    if not commands:
        return []

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(commands)) as executor:
        return list(
            executor.map(
                lambda command: (command[0], command[1], *run_usbrelay(*command)),
                commands,
            )
        )


class WorkerSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)


class Worker(QRunnable):
    """Ruleaza o functie pe un thread din pool si trimite rezultatul prin semnale."""

    def __init__(self, fn, *args):
        super().__init__()
        self.setAutoDelete(False)
        self.signals = WorkerSignals()
        self._fn = fn
        self._args = args

    @Slot()
    def run(self):
        try:
            result = self._fn(*self._args)
        except Exception as exc:  # noqa: BLE001 - orice eroare ajunge in interfata
            self.signals.failed.emit(str(exc))
        else:
            self.signals.finished.emit(result)


class BackgroundPage(QWidget):
    """Pagina care poate trimite functii pe thread pool si anunta starea."""

    statusMessage = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._workers = []

    def submit(self, fn, *args, on_result=None, on_error=None):
        worker = Worker(fn, *args)
        self._workers.append(worker)

        def cleanup():
            if worker in self._workers:
                self._workers.remove(worker)

        if on_result is not None:
            worker.signals.finished.connect(on_result)
        if on_error is not None:
            worker.signals.failed.connect(on_error)

        worker.signals.finished.connect(lambda _: cleanup())
        worker.signals.failed.connect(lambda _: cleanup())

        QThreadPool.globalInstance().start(worker)
        return worker


class RelayControlPage(BackgroundPage):
    """Controlul releelor pentru numarul de placi selectat."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.states = {
            (serial, relay): False
            for serial in ALL_BOARDS
            for relay in range(1, RELAYS_PER_BOARD + 1)
        }
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

    def active_boards(self):
        return ALL_BOARDS[: self.board_count]

    def _rebuild_boards(self):
        while self.boards_layout.count():
            item = self.boards_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        self.buttons.clear()

        for serial in self.active_boards():
            self.boards_layout.addWidget(self._build_board(serial))

        self.boards_layout.addStretch(1)

    def _build_board(self, serial):
        box = QGroupBox(serial)
        box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        grid = QGridLayout(box)

        for relay in range(1, RELAYS_PER_BOARD + 1):
            grid.addWidget(QLabel(f"Relay {relay}"), relay - 1, 0)

            button = QPushButton()
            button.setMinimumWidth(90)
            button.clicked.connect(
                lambda _checked=False, s=serial, r=relay: self.toggle(s, r)
            )
            grid.addWidget(button, relay - 1, 1)

            self.buttons[(serial, relay)] = button
            self._refresh_button((serial, relay))

        return box

    def _refresh_button(self, key):
        button = self.buttons.get(key)
        if button is None:
            return

        is_on = self.states[key]
        button.setText("ON" if is_on else "OFF")
        button.setStyleSheet(ON_STYLE if is_on else OFF_STYLE)

    def _set_busy(self, keys, busy):
        for key in keys:
            button = self.buttons.get(key)
            if button is not None:
                button.setEnabled(not busy)

    def _set_global_busy(self, busy):
        self.all_on_button.setEnabled(not busy)
        self.all_off_button.setEnabled(not busy)
        self.board_selector.setEnabled(not busy)

    # -- actiuni ----------------------------------------------------------------
    def _on_board_count_changed(self, index):
        self.board_count = self.board_selector.itemData(index)
        self._rebuild_boards()
        self.statusMessage.emit(
            f"Placi active: {', '.join(self.active_boards())}"
        )

    def toggle(self, serial, relay):
        key = (serial, relay)
        new_state = not self.states[key]

        self._set_busy([key], True)
        self.statusMessage.emit(
            f"{serial} Relay {relay}: trimit {'ON' if new_state else 'OFF'}..."
        )
        self.submit(
            run_usbrelay,
            serial,
            relay,
            new_state,
            on_result=lambda result, k=key, s=new_state: self._finish_toggle(k, s, result),
            on_error=lambda message, k=key: self._finish_toggle(k, None, (False, message)),
        )

    def _finish_toggle(self, key, new_state, result):
        self._set_busy([key], False)
        success, message = result
        serial, relay = key

        if success:
            self.states[key] = new_state
            self._refresh_button(key)
            self.statusMessage.emit(
                f"{serial} Relay {relay} este {'ON' if new_state else 'OFF'}."
            )
            return

        self.statusMessage.emit(f"Eroare la {serial} Relay {relay}.")
        QMessageBox.critical(
            self,
            "Eroare",
            f"Nu pot controla {serial} Relay {relay}.\n\n{message}",
        )

    def set_all(self, state):
        commands = [
            (serial, relay, state)
            for serial in self.active_boards()
            for relay in range(1, RELAYS_PER_BOARD + 1)
        ]
        keys = [(serial, relay) for serial, relay, _ in commands]

        self._set_busy(keys, True)
        self._set_global_busy(True)
        self.statusMessage.emit(
            f"Trimit {'ON' if state else 'OFF'} catre {len(commands)} relee..."
        )
        self.submit(
            run_all_commands,
            commands,
            on_result=lambda results, s=state: self._finish_set_all(s, results),
            on_error=lambda message, k=keys: self._finish_set_all_error(k, message),
        )

    def _finish_set_all(self, state, results):
        failed = []

        for serial, relay, success, message in results:
            key = (serial, relay)
            self._set_busy([key], False)

            if success:
                self.states[key] = state
                self._refresh_button(key)
            else:
                failed.append(message)

        self._set_global_busy(False)

        if failed:
            self.statusMessage.emit(f"{len(failed)} relee nu au raspuns.")
            QMessageBox.critical(
                self,
                "Eroare",
                "Nu pot controla:\n" + "\n".join(failed),
            )
            return

        self.statusMessage.emit(
            f"Toate releele active sunt {'ON' if state else 'OFF'}."
        )

    def _finish_set_all_error(self, keys, message):
        self._set_busy(keys, False)
        self._set_global_busy(False)
        self.statusMessage.emit("Comanda globala a esuat.")
        QMessageBox.critical(self, "Eroare", message)


class ChangeIdPage(BackgroundPage):
    """Varianta grafica a utilitarului change_usbrelay_id."""

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)

        warning = QLabel(
            "Conecteaza O SINGURA placa inainte de a scrie ID-ul. "
            "Dupa scriere, deconecteaza si reconecteaza placa, apoi "
            "reimprospateaza lista pentru verificare."
        )
        warning.setWordWrap(True)
        warning.setStyleSheet("color: #a04000; font-weight: 600;")
        layout.addWidget(warning)

        layout.addWidget(QLabel(f"Placi detectate ({USBRELAY_EXE} -list):"))

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

    def _force_uppercase(self, text):
        if text != text.upper():
            self.id_edit.setText(text.upper())

    def _set_busy(self, busy):
        self.refresh_button.setEnabled(not busy)
        self.write_button.setEnabled(not busy)
        self.id_edit.setEnabled(not busy)

    def refresh_list(self):
        self._set_busy(True)
        self.statusMessage.emit("Citesc lista de placi...")
        self.submit(
            list_relays_output,
            on_result=self._show_list,
            on_error=lambda message: self._show_list((False, message)),
        )

    def _show_list(self, result):
        success, text = result
        self._set_busy(False)
        self.output.setPlainText(text)
        self.statusMessage.emit(
            "Lista actualizata." if success else "Nu pot citi lista de placi."
        )

    def write_id(self):
        new_id = self.id_edit.text().strip().upper()

        try:
            validate_id(new_id)
        except ValueError as exc:
            QMessageBox.warning(self, "ID invalid", str(exc))
            return

        confirm = QMessageBox.question(
            self,
            "Confirmare",
            f"Scriu ID-ul {new_id} pe placa conectata?\n\n"
            "Asigura-te ca este conectata O SINGURA placa USB Relay.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return

        self._set_busy(True)
        self.statusMessage.emit(f"Scriu ID-ul {new_id}...")
        self.submit(
            change_id,
            new_id,
            on_result=lambda _: self._finish_write(new_id),
            on_error=self._write_failed,
        )

    def _finish_write(self, new_id):
        self._set_busy(False)
        self.statusMessage.emit(f"ID-ul {new_id} a fost trimis catre placa.")
        QMessageBox.information(
            self,
            "Comanda trimisa",
            f"ID-ul {new_id} a fost trimis.\n\n"
            "Scoate si reconecteaza placa USB, apoi apasa "
            "'Reimprospateaza lista' pentru verificare.",
        )

    def _write_failed(self, message):
        self._set_busy(False)
        self.statusMessage.emit("Scrierea ID-ului a esuat.")
        QMessageBox.critical(self, "Eroare", f"Nu pot scrie ID-ul.\n\n{message}")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("USB Relay Controller")

        self.relay_page = RelayControlPage()
        self.change_id_page = ChangeIdPage()

        tabs = QTabWidget()
        tabs.addTab(self.relay_page, "Control relee")
        tabs.addTab(self.change_id_page, "Schimba ID placa")
        self.setCentralWidget(tabs)

        for page in (self.relay_page, self.change_id_page):
            page.statusMessage.connect(self._show_status)

        self.statusBar().showMessage(
            f"Placi active: {', '.join(self.relay_page.active_boards())}"
        )

    def _show_status(self, message):
        self.statusBar().showMessage(message, 8000)

    def closeEvent(self, event):
        QThreadPool.globalInstance().waitForDone(COMMAND_TIMEOUT_SECONDS * 1000)
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    QThreadPool.globalInstance().setMaxThreadCount(MAX_WORKERS)

    window = MainWindow()
    window.resize(880, 480)
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
