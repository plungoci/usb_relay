import subprocess
import tkinter as tk
from tkinter import messagebox
import concurrent.futures

USBRELAY_EXE = "usbrelay.exe"

BOARDS = [
    "RLY01",
    "RLY02",
    "RLY03",
    "RLY04"
]

RELAYS_PER_BOARD = 4


def run_usbrelay(serial, relay, state):
    cmd = [
        USBRELAY_EXE,
        "-serial",
        serial,
        "-on" if state else "-off",
        str(relay)
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=5
        )

        return result.returncode == 0

    except Exception as e:
        print(e)
        return False


class RelayGUI:

    def __init__(self, root):

        self.root = root
        self.root.title("USB Relay Controller")

        self.states = {}

        top_frame = tk.Frame(root)
        top_frame.grid(
            row=0,
            column=0,
            columnspan=len(BOARDS),
            pady=10
        )

        tk.Button(
            top_frame,
            text="ALL ON",
            width=15,
            bg="lightgreen",
            command=self.all_on
        ).pack(side=tk.LEFT, padx=10)

        tk.Button(
            top_frame,
            text="ALL OFF",
            width=15,
            bg="tomato",
            command=self.all_off
        ).pack(side=tk.LEFT, padx=10)

        for col, serial in enumerate(BOARDS):

            frame = tk.LabelFrame(
                root,
                text=serial,
                padx=10,
                pady=10
            )

            frame.grid(
                row=1,
                column=col,
                padx=10,
                pady=10
            )

            for relay in range(1, RELAYS_PER_BOARD + 1):

                key = (serial, relay)

                tk.Label(
                    frame,
                    text=f"Relay {relay}"
                ).grid(
                    row=relay,
                    column=0,
                    padx=5,
                    pady=5
                )

                btn = tk.Button(
                    frame,
                    text="OFF",
                    width=10,
                    bg="lightgray",
                    command=lambda s=serial, r=relay:
                    self.toggle(s, r)
                )

                btn.grid(
                    row=relay,
                    column=1,
                    padx=5,
                    pady=5
                )

                self.states[key] = {
                    "on": False,
                    "button": btn
                }

    def update_button(self, key):

        btn = self.states[key]["button"]

        if self.states[key]["on"]:
            btn.config(
                text="ON",
                bg="lightgreen"
            )
        else:
            btn.config(
                text="OFF",
                bg="lightgray"
            )

    def toggle(self, serial, relay):

        key = (serial, relay)

        current = self.states[key]["on"]
        new_state = not current

        success = run_usbrelay(
            serial,
            relay,
            new_state
        )

        if success:

            self.states[key]["on"] = new_state
            self.update_button(key)

        else:

            messagebox.showerror(
                "Error",
                f"Nu pot controla {serial} Relay {relay}"
            )

    def set_all(self, state):

        commands = []

        for serial in BOARDS:
            for relay in range(1, RELAYS_PER_BOARD + 1):
                commands.append(
                    (serial, relay, state)
                )

        with concurrent.futures.ThreadPoolExecutor(
                max_workers=16) as executor:

            list(
                executor.map(
                    lambda x:
                    run_usbrelay(
                        x[0],
                        x[1],
                        x[2]
                    ),
                    commands
                )
            )

        for serial, relay, _ in commands:

            key = (serial, relay)

            self.states[key]["on"] = state
            self.update_button(key)

    def all_on(self):
        self.set_all(True)

    def all_off(self):
        self.set_all(False)


if __name__ == "__main__":

    root = tk.Tk()

    app = RelayGUI(root)

    root.mainloop()
