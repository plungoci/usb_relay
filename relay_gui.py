import concurrent.futures
import subprocess
import tkinter as tk
from functools import partial
from tkinter import messagebox

USBRELAY_EXE = "usbrelay.exe"
BOARDS = ("RLY01", "RLY02", "RLY03", "RLY04")
RELAYS_PER_BOARD = 4
COMMAND_TIMEOUT_SECONDS = 5
MAX_WORKERS = len(BOARDS) * RELAYS_PER_BOARD


def run_usbrelay(serial, relay, state):
    """Run usbrelay.exe for one relay and return True on success."""
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
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"usbrelay command failed for {serial} relay {relay}: {exc}")
        return False

    if result.returncode != 0:
        error_output = (result.stderr or result.stdout).strip()
        print(f"usbrelay returned {result.returncode}: {error_output}")
        return False

    return True


class RelayGUI:
    """Tkinter UI for controlling configured USB relay boards."""

    def __init__(self, root):
        self.root = root
        self.root.title("USB Relay Controller")
        self.states = {}
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS)

        self._build_controls()
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def _build_controls(self):
        top_frame = tk.Frame(self.root)
        top_frame.grid(row=0, column=0, columnspan=len(BOARDS), pady=10)

        tk.Button(
            top_frame,
            text="ALL ON",
            width=15,
            bg="lightgreen",
            command=partial(self.set_all, True),
        ).pack(side=tk.LEFT, padx=10)

        tk.Button(
            top_frame,
            text="ALL OFF",
            width=15,
            bg="tomato",
            command=partial(self.set_all, False),
        ).pack(side=tk.LEFT, padx=10)

        for col, serial in enumerate(BOARDS):
            self._build_board(self.root, serial, col)

    def _build_board(self, parent, serial, column):
        frame = tk.LabelFrame(parent, text=serial, padx=10, pady=10)
        frame.grid(row=1, column=column, padx=10, pady=10)

        for relay in range(1, RELAYS_PER_BOARD + 1):
            key = (serial, relay)

            tk.Label(frame, text=f"Relay {relay}").grid(
                row=relay,
                column=0,
                padx=5,
                pady=5,
            )

            button = tk.Button(
                frame,
                text="OFF",
                width=10,
                bg="lightgray",
                command=partial(self.toggle, serial, relay),
            )
            button.grid(row=relay, column=1, padx=5, pady=5)

            self.states[key] = {"on": False, "button": button}

    def _set_button_busy(self, key, busy):
        self.states[key]["button"].config(state=tk.DISABLED if busy else tk.NORMAL)

    def update_button(self, key):
        button = self.states[key]["button"]
        is_on = self.states[key]["on"]
        button.config(
            text="ON" if is_on else "OFF",
            bg="lightgreen" if is_on else "lightgray",
        )

    def toggle(self, serial, relay):
        key = (serial, relay)
        new_state = not self.states[key]["on"]
        self._set_button_busy(key, True)

        future = self.executor.submit(run_usbrelay, serial, relay, new_state)
        future.add_done_callback(
            lambda completed: self.root.after(0, self._finish_toggle, key, new_state, completed)
        )

    def _finish_toggle(self, key, new_state, future):
        self._set_button_busy(key, False)

        if future.result():
            self.states[key]["on"] = new_state
            self.update_button(key)
            return

        serial, relay = key
        messagebox.showerror("Error", f"Nu pot controla {serial} Relay {relay}")

    def set_all(self, state):
        commands = [
            (serial, relay, state)
            for serial in BOARDS
            for relay in range(1, RELAYS_PER_BOARD + 1)
        ]

        for serial, relay, _ in commands:
            self._set_button_busy((serial, relay), True)

        future = self.executor.submit(self._run_all_commands, commands)
        future.add_done_callback(
            lambda completed: self.root.after(0, self._finish_set_all, state, completed)
        )

    @staticmethod
    def _run_all_commands(commands):
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            return list(
                executor.map(
                    lambda command: (*command[:2], run_usbrelay(*command)),
                    commands,
                )
            )

    def _finish_set_all(self, state, future):
        results = future.result()
        failed = []

        for serial, relay, success in results:
            key = (serial, relay)
            self._set_button_busy(key, False)

            if success:
                self.states[key]["on"] = state
                self.update_button(key)
            else:
                failed.append(f"{serial} Relay {relay}")

        if failed:
            messagebox.showerror("Error", "Nu pot controla:\n" + "\n".join(failed))

    def close(self):
        self.executor.shutdown(wait=False, cancel_futures=True)
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    RelayGUI(root)
    root.mainloop()
