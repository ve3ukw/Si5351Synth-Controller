#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Si5351 Raw Data Transfer
# Original: Bert-VE2ZAZ, v0.3, April 2019  http://ve2zaz.net
# Rewritten with ttk UI for Python 3 / Windows 11
#
# Requires: pyserial  (pip install pyserial)

import json
import os
import sys
import time
import webbrowser

import serial
import serial.tools.list_ports
from tkinter import Tk, StringVar, END
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText

# 1200 baud is excluded from the UI — the LGT8F328P treats it as a
# "bootloader touch" and enters ISP mode instead of running the sketch.
BAUD_DEFAULT  = "2400"
BAUD_CHOICES  = ["2400", "4800", "9600", "19200", "38400", "57600", "115200"]
RAW_DATA_FILE = "Raw_Data.txt"
SETTINGS_FILE = "saved_settings_raw.json"


class RawTransferApp:
    def __init__(self, root: Tk):
        self.root = root
        self.root.title("Si5351 Raw Data Transfer")
        self.root.resizable(True, True)
        self.root.minsize(640, 460)
        self.ser = serial.Serial()

        style = ttk.Style()
        for theme in ("vista", "winnative", "aqua", "clam"):
            if theme in style.theme_names():
                style.theme_use(theme)
                break

        self._build_ui()
        self._load_settings()
        self._refresh_ports()
        self._load_raw_data()
        self._log("Si5351A/B/C Raw Data Transfer  -  VE2ZAZ v0.3  -  "
                  "http://ve2zaz.net\n", "dim")
        self._log("Data shown is from the last saved session, "
                  "not from board EEPROM.\n", "dim")

    # ── UI ─────────────────────────────────────────────────────────────────

    def _build_ui(self):
        r = self.root
        r.columnconfigure(0, weight=1)
        r.rowconfigure(1, weight=1)
        r.rowconfigure(3, weight=0)

        # Title
        ttk.Label(r, text="Si5351 Raw Data Transfer",
                  font=("Segoe UI", 15, "bold"), foreground="#000080"
                  ).grid(row=0, column=0, pady=(10, 4))
        ttk.Separator(r, orient="horizontal"
                      ).grid(row=0, column=0, sticky="ew", padx=10, pady=(40, 0))

        # Raw data text area
        data_frame = ttk.LabelFrame(r, text="Register Data  (format: address,value  — lines starting with ; are comments)",
                                    padding=(6, 4))
        data_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=4)
        data_frame.columnconfigure(0, weight=1)
        data_frame.rowconfigure(0, weight=1)

        self.data_box = ScrolledText(data_frame, font=("Consolas", 10),
                                     bg="white", relief="flat")
        self.data_box.grid(row=0, column=0, sticky="nsew")

        # Control bar
        ctrl = ttk.Frame(r, padding=(0, 4))
        ctrl.grid(row=2, column=0, sticky="ew", padx=10)

        ttk.Label(ctrl, text="Serial Port:").pack(side="left")
        self.port_combo = ttk.Combobox(ctrl, width=10)
        self.port_combo.pack(side="left", padx=(4, 2))
        self.serial_port = StringVar()
        self.port_combo.configure(textvariable=self.serial_port)
        ttk.Button(ctrl, text="Refresh", width=7,
                   command=self._refresh_ports).pack(side="left", padx=(2, 12))

        self.baud_rate = StringVar(value=BAUD_DEFAULT)
        ttk.Label(ctrl, text="Baud:").pack(side="left")
        ttk.Combobox(ctrl, textvariable=self.baud_rate, values=BAUD_CHOICES,
                     state="readonly", width=7).pack(side="left", padx=(4, 20))

        self.xfer_btn = ttk.Button(ctrl, text="Transfer", command=self.transfer)
        self.xfer_btn.pack(side="left", padx=6)
        ttk.Button(ctrl, text="About...", command=self._about).pack(side="left", padx=6)
        ttk.Button(ctrl, text="Exit",    command=self._exit ).pack(side="right", padx=6)

        # Log
        ttk.Separator(r, orient="horizontal"
                      ).grid(row=3, column=0, sticky="ew", padx=10, pady=(4, 0))
        self.log = ScrolledText(r, height=4, font=("Consolas", 9),
                                state="normal", bg="#f8f8f8", relief="flat", bd=1)
        self.log.tag_configure("info",  foreground="navy")
        self.log.tag_configure("ok",    foreground="#006400")
        self.log.tag_configure("error", foreground="red")
        self.log.tag_configure("dim",   foreground="#666666")
        self.log.grid(row=4, column=0, sticky="ew", padx=10, pady=(0, 10))

    # ── Logging ────────────────────────────────────────────────────────────

    def _log(self, msg: str, tag: str = "info"):
        self.log.insert(END, msg, tag)
        self.log.see(END)
        self.log.update()

    def _err(self, msg: str):
        self._log(msg + "\n", "error")
        if self.ser.is_open:
            self.ser.close()
        self.xfer_btn.config(state="normal")

    # ── Ports ──────────────────────────────────────────────────────────────

    def _refresh_ports(self):
        ports = [p.device for p in sorted(serial.tools.list_ports.comports())]
        self.port_combo["values"] = ports
        if self.serial_port.get() not in ports:
            self.serial_port.set(ports[0] if ports else "")

    # ── Menu actions ───────────────────────────────────────────────────────

    def _about(self):
        webbrowser.open("file://" + os.path.realpath("./About_Raw.html"),
                        new=1, autoraise=True)

    def _exit(self):
        self._save_raw_data()
        self._save_settings()
        sys.exit()

    # ── Transfer ───────────────────────────────────────────────────────────

    def transfer(self):
        self.xfer_btn.config(state="disabled")

        lines = self.data_box.get("1.0", "end-1c").splitlines()

        # Validate: every non-comment line must be "number,number"
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith(";"):
                continue
            parts = stripped.replace(";", ",").split(",")
            try:
                int(parts[0]); int(parts[1])
            except (ValueError, IndexError):
                self._err(
                    f"Invalid line: '{line}'\n"
                    "Each data line must be: address,value  (integers)"
                )
                return

        self._log("\n-----------------------------------------\n"
                  "Transfer initiated...\n")

        self.ser.baudrate = int(self.baud_rate.get())
        self.ser.timeout  = 15
        self.ser.port     = self.serial_port.get()
        try:
            self.ser.open()
        except (OSError, serial.SerialException) as exc:
            self._err(f"Error opening port: {exc}")
            return

        self._log("Waiting for board...\n")
        recv = self.ser.read(1)
        if recv != b'R':
            diag = ("0x" + recv.hex()) if recv else "nothing (timeout)"
            self._err(
                f"Expected 'R' from board, received {diag}.\n"
                "Check board programming and USB connection."
            )
            return
        self._log("Board ready.\n", "ok")

        self.ser.write(b"@")
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith(";"):
                continue
            parts = stripped.replace(";", ",").split(",")
            payload = f"{parts[0]},{parts[1]};"
            print(payload)
            self.ser.write(payload.encode("ascii"))
            time.sleep(0.05)
        self.ser.write(b"%")

        while self.ser.out_waiting:
            pass

        for expected, msg in [
            (b'O', "Configuration received by board"),
            (b'E', "Configuration saved to EEPROM"),
            (b'S', "Configuration applied to Si5351"),
        ]:
            got = self.ser.read(1)
            if got == expected:
                self._log(f"{msg}\n", "ok")
            else:
                diag = ("0x" + got.hex()) if got else "timeout"
                self._err(
                    f"Expected '{expected.decode()}' from board, got {diag}. Try again."
                )
                return

        self.ser.close()
        self._log("Configuration complete!\n", "ok")
        self.xfer_btn.config(state="normal")

    # ── Persistence ────────────────────────────────────────────────────────

    def _save_raw_data(self):
        try:
            with open(RAW_DATA_FILE, "w") as f:
                f.write(self.data_box.get("1.0", "end-1c"))
        except IOError:
            pass

    def _load_raw_data(self):
        try:
            with open(RAW_DATA_FILE) as f:
                self.data_box.insert(END, f.read())
        except IOError:
            pass

    def _save_settings(self):
        try:
            data = {
                "window": {"x": self.root.winfo_x(), "y": self.root.winfo_y()},
                "port": self.serial_port.get(),
                "baud": self.baud_rate.get(),
            }
            with open(SETTINGS_FILE, "w") as f:
                json.dump(data, f, indent=2)
        except IOError:
            pass

    def _load_settings(self):
        try:
            with open(SETTINGS_FILE) as f:
                data = json.load(f)
            win = data.get("window", {})
            if "x" in win and "y" in win:
                self.root.geometry(f"+{int(win['x'])}+{int(win['y'])}")
            self.serial_port.set(data.get("port", ""))
            baud = str(data.get("baud", BAUD_DEFAULT))
            if baud in BAUD_CHOICES:
                self.baud_rate.set(baud)
        except (IOError, ValueError, KeyError):
            pass


if __name__ == "__main__":
    root = Tk()
    app = RawTransferApp(root)
    root.protocol("WM_DELETE_WINDOW", app._exit)
    root.mainloop()
