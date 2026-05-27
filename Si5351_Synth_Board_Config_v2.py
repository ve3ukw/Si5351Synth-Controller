#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Si5351 Synthesizer Board Configurator
# Original: Bert-VE2ZAZ, v0.5, December 2019  http://ve2zaz.net
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
from tkinter import Tk, StringVar, IntVar, DoubleVar, END
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText

# ---------------------------------------------------------------------------
# Si5351 library command identifiers
# ---------------------------------------------------------------------------
SI5351_PLLA             = 0
SI5351_PLL_INPUT_XO     = 0
SI5351_PLL_INPUT_CLKIN  = 1
SI5351_CRYSTAL_LOAD_0PF = 0

INIT             = "1"
SET_PLL_INPUT    = "2"
SET_REF_FREQ     = "3"
SET_CORRECTION   = "4"
SET_FREQ         = "5"
DRIVE_STRENGTH   = "7"
SET_CLOCK_INVERT = "8"
PLL_RESET        = "9"

# 1200 baud is intentionally excluded from the UI dropdown — the LGT8F328P
# treats a 1200-baud connect as its "bootloader touch" and enters ISP mode.
# Any other rate causes a normal app-reset; 2400 is the safe default.
BAUD_DEFAULT = "2400"
BAUD_CHOICES = ["2400", "4800", "9600", "19200", "38400", "57600", "115200"]

SETTINGS_FILE = "saved_settings.json"
CH_COLORS = ["#8B4513", "#8B0000", "#551A8B", "#B8860B", "#00688B", "#006400"]
INPUT_SRC_MAP = {"Onboard Crystal": 2, "External Ref.": 1}


class Si5351App:
    def __init__(self, root: Tk):
        self.root = root
        self.root.title("Si5351 Synthesizer Configuration")
        self.root.resizable(True, True)
        self.root.minsize(780, 460)
        self.ser = serial.Serial()

        style = ttk.Style()
        for theme in ("vista", "winnative", "aqua", "clam"):
            if theme in style.theme_names():
                style.theme_use(theme)
                break

        self._init_vars()
        self._build_ui()
        self._load_settings()
        self._refresh_ports()
        self._log("Si5351A/B/C Synthesizer Configuration  -  VE2ZAZ v0.5  -  "
                  "http://ve2zaz.net\n", "dim")
        self._log("Settings shown are from the last saved session, "
                  "not from board EEPROM.\n", "dim")

    # ── Variables ──────────────────────────────────────────────────────────

    def _init_vars(self):
        self.ref_freq    = DoubleVar(value=25_000_000.0)
        self.ref_corr    = DoubleVar(value=0.0)
        self.input_src   = StringVar(value="Onboard Crystal")
        self.serial_port = StringVar()
        self.ch_enabled  = [IntVar(value=1 if i == 0 else 0) for i in range(6)]
        self.ch_freq     = [DoubleVar(value=24_000_000.0 if i == 0 else 10_000_000.0)
                            for i in range(6)]
        self.ch_drive    = [StringVar(value="2") for _ in range(6)]
        self.ch_invert   = [IntVar(value=0) for _ in range(6)]
        self.baud_rate   = StringVar(value=BAUD_DEFAULT)

    # ── UI ─────────────────────────────────────────────────────────────────

    def _build_ui(self):
        r = self.root
        r.columnconfigure(1, weight=1)
        r.rowconfigure(5, weight=1)

        # Title
        ttk.Label(r, text="Si5351 Synthesizer Configuration",
                  font=("Segoe UI", 15, "bold"), foreground="#000080"
                  ).grid(row=0, column=0, columnspan=2, pady=(10, 4))
        ttk.Separator(r, orient="horizontal"
                      ).grid(row=1, column=0, columnspan=2,
                             sticky="ew", padx=10, pady=(0, 2))

        # Input reference panel
        inp = ttk.LabelFrame(r, text="Input Reference", padding=(12, 8))
        inp.grid(row=2, column=0, sticky="nsew", padx=(10, 5), pady=4)

        ttk.Label(inp, text="Source").grid(row=0, column=0, sticky="w")
        ttk.Combobox(inp, textvariable=self.input_src,
                     values=list(INPUT_SRC_MAP), state="readonly", width=14
                     ).grid(row=0, column=1, sticky="w", padx=(6, 0))

        ttk.Label(inp, text="Frequency (Hz)"
                  ).grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(inp, textvariable=self.ref_freq, width=15
                  ).grid(row=1, column=1, sticky="w", padx=(6, 0), pady=(8, 0))

        ttk.Label(inp, text="Offset (ppm)"
                  ).grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(inp, textvariable=self.ref_corr, width=15
                  ).grid(row=2, column=1, sticky="w", padx=(6, 0), pady=(8, 0))

        # Output channel table
        out = ttk.LabelFrame(r, text="Output Channels", padding=(12, 8))
        out.grid(row=2, column=1, sticky="nsew", padx=(5, 10), pady=4)

        headers = ["Ch", "Enable", "Frequency (Hz)", "Drive (mA)", "Invert"]
        for col, h in enumerate(headers):
            ttk.Label(out, text=h, font=("Segoe UI", 9, "bold")
                      ).grid(row=0, column=col, padx=6, pady=(0, 2))
        ttk.Separator(out, orient="horizontal"
                      ).grid(row=1, column=0, columnspan=5, sticky="ew")

        for i in range(6):
            row = i + 2
            ttk.Label(out, text=str(i), foreground=CH_COLORS[i],
                      width=2, anchor="center"
                      ).grid(row=row, column=0, padx=6, pady=3)
            ttk.Checkbutton(out, variable=self.ch_enabled[i]
                            ).grid(row=row, column=1, padx=6, pady=3)
            ttk.Entry(out, textvariable=self.ch_freq[i], width=16
                      ).grid(row=row, column=2, padx=6, pady=3)
            ttk.Combobox(out, textvariable=self.ch_drive[i],
                         values=["2", "4", "6", "8"], state="readonly", width=5
                         ).grid(row=row, column=3, padx=6, pady=3)
            ttk.Checkbutton(out, variable=self.ch_invert[i]
                            ).grid(row=row, column=4, padx=6, pady=3)

        # Control bar
        ctrl = ttk.Frame(r, padding=(0, 4))
        ctrl.grid(row=3, column=0, columnspan=2, sticky="ew", padx=10)

        ttk.Label(ctrl, text="Serial Port:").pack(side="left")
        self.port_combo = ttk.Combobox(ctrl, textvariable=self.serial_port, width=10)
        self.port_combo.pack(side="left", padx=(4, 2))
        ttk.Button(ctrl, text="Refresh", width=7,
                   command=self._refresh_ports).pack(side="left", padx=(2, 12))

        ttk.Label(ctrl, text="Baud:").pack(side="left")
        ttk.Combobox(ctrl, textvariable=self.baud_rate, values=BAUD_CHOICES,
                     state="readonly", width=7).pack(side="left", padx=(4, 20))

        self.xfer_btn = ttk.Button(ctrl, text="Transfer", command=self.transfer)
        self.xfer_btn.pack(side="left", padx=6)
        self.read_btn = ttk.Button(ctrl, text="Read Board", command=self._read_from_board)
        self.read_btn.pack(side="left", padx=6)
        ttk.Button(ctrl, text="About...", command=self._about).pack(side="left", padx=6)
        ttk.Button(ctrl, text="Exit",    command=self._exit ).pack(side="right", padx=6)

        # Log
        ttk.Separator(r, orient="horizontal"
                      ).grid(row=4, column=0, columnspan=2,
                             sticky="ew", padx=10, pady=(4, 0))
        self.log = ScrolledText(r, height=5, font=("Consolas", 9),
                                state="normal", bg="#f8f8f8", relief="flat", bd=1)
        self.log.tag_configure("info",  foreground="navy")
        self.log.tag_configure("ok",    foreground="#006400")
        self.log.tag_configure("error", foreground="red")
        self.log.tag_configure("dim",   foreground="#666666")
        self.log.grid(row=5, column=0, columnspan=2,
                      sticky="nsew", padx=10, pady=(0, 10))

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
        if hasattr(self, 'read_btn'):
            self.read_btn.config(state="normal")

    # ── Ports ──────────────────────────────────────────────────────────────

    def _refresh_ports(self):
        ports = [p.device for p in sorted(serial.tools.list_ports.comports())]
        self.port_combo["values"] = ports
        if self.serial_port.get() not in ports:
            self.serial_port.set(ports[0] if ports else "")

    # ── Menu actions ───────────────────────────────────────────────────────

    def _about(self):
        webbrowser.open("file://" + os.path.realpath("./About.html"),
                        new=1, autoraise=True)

    def _exit(self):
        self._save_settings()
        sys.exit()

    # ── Transfer ───────────────────────────────────────────────────────────

    def transfer(self):
        self.xfer_btn.config(state="disabled")

        try:
            ref_freq = float(self.ref_freq.get())
            ref_corr = float(self.ref_corr.get())
            ch_freqs = [float(v.get()) for v in self.ch_freq]
        except (ValueError, TypeError):
            self._err("Error: non-numeric value in a frequency field.")
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

        def send(cmd: str):
            print(cmd)
            self.ser.write(cmd.encode("ascii"))

        send("$")
        send(f"{INIT},{SI5351_CRYSTAL_LOAD_0PF},{int(ref_freq)},{ref_corr * 1000}|")
        time.sleep(1)

        src = INPUT_SRC_MAP[self.input_src.get()]
        if src == 2:
            send(f"{SET_PLL_INPUT},{SI5351_PLLA},{SI5351_PLL_INPUT_XO}|")
        else:
            send(f"{SET_REF_FREQ},{int(ref_freq)},{SI5351_PLL_INPUT_CLKIN}|")
            send(f"{SET_CORRECTION},{ref_corr * 1000},{SI5351_PLL_INPUT_CLKIN}|")
            send(f"{SET_PLL_INPUT},{SI5351_PLLA},{SI5351_PLL_INPUT_CLKIN}|")
            time.sleep(1)

        for clk in range(6):
            if self.ch_enabled[clk].get():
                drive_idx = int(self.ch_drive[clk].get()) // 2 - 1
                send(f"{SET_FREQ},{int(ch_freqs[clk] * 100)},{clk}|")
                send(f"{DRIVE_STRENGTH},{clk},{drive_idx}|")
                send(f"{SET_CLOCK_INVERT},{clk},{self.ch_invert[clk].get()}|")
                time.sleep(1)

        send(f"{PLL_RESET},{SI5351_PLLA}|")
        send("%")
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

    # ── Read from board ────────────────────────────────────────────────────

    def _read_from_board(self):
        self.read_btn.config(state="disabled")
        self.xfer_btn.config(state="disabled")

        self._log("\n-----------------------------------------\n"
                  "Reading configuration from board...\n")

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

        self.ser.write(b'?')
        self.ser.timeout = 5
        buf = []
        while True:
            ch = self.ser.read(1)
            if not ch:
                self._err("Timeout: no EEPROM data received from board.")
                return
            c = ch.decode("ascii", errors="?")
            buf.append(c)
            if c in ('%', '!'):
                break

        self.ser.close()
        text = "".join(buf)

        if text == '!':
            self._log("No configuration stored in EEPROM yet.\n", "error")
            self.read_btn.config(state="normal")
            self.xfer_btn.config(state="normal")
            return

        self._parse_eeprom_dump(text)
        self._log("Board configuration loaded into UI.\n", "ok")
        self.read_btn.config(state="normal")
        self.xfer_btn.config(state="normal")

    def _parse_eeprom_dump(self, data: str):
        inner = data.lstrip("$").rstrip("%").strip()
        segments = inner.split("|")

        for i in range(6):
            self.ch_enabled[i].set(0)

        for seg in segments:
            parts = seg.strip().split(",")
            if len(parts) < 2:
                continue
            cmd = parts[0]
            try:
                if cmd == INIT and len(parts) >= 4:
                    self.ref_freq.set(int(float(parts[2])))
                    self.ref_corr.set(float(parts[3]) / 1000.0)
                elif cmd == SET_PLL_INPUT and len(parts) >= 3:
                    src = int(float(parts[2]))
                    self.input_src.set("Onboard Crystal" if src == SI5351_PLL_INPUT_XO
                                       else "External Ref.")
                elif cmd == SET_FREQ and len(parts) >= 3:
                    clk = int(float(parts[2]))
                    freq_hz = int(float(parts[1])) / 100.0
                    if 0 <= clk < 6:
                        self.ch_enabled[clk].set(1)
                        self.ch_freq[clk].set(freq_hz)
                elif cmd == DRIVE_STRENGTH and len(parts) >= 3:
                    clk = int(float(parts[1]))
                    drive_idx = int(float(parts[2]))
                    if 0 <= clk < 6:
                        self.ch_drive[clk].set(str((drive_idx + 1) * 2))
                elif cmd == SET_CLOCK_INVERT and len(parts) >= 3:
                    clk = int(float(parts[1]))
                    invert = int(float(parts[2]))
                    if 0 <= clk < 6:
                        self.ch_invert[clk].set(invert)
            except (ValueError, IndexError):
                continue

    # ── Settings persistence ────────────────────────────────────────────────

    def _save_settings(self):
        try:
            data = {
                "window":   {"x": self.root.winfo_x(), "y": self.root.winfo_y()},
                "ref_freq": self.ref_freq.get(),
                "ref_corr": self.ref_corr.get(),
                "input_src": INPUT_SRC_MAP[self.input_src.get()],
                "channels": [
                    {
                        "channel": i,
                        "freq":    self.ch_freq[i].get(),
                        "enabled": self.ch_enabled[i].get(),
                        "invert":  self.ch_invert[i].get(),
                        "drive":   self.ch_drive[i].get(),
                    }
                    for i in range(6)
                ],
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
            self.ref_freq.set(float(data["ref_freq"]))
            self.ref_corr.set(float(data["ref_corr"]))
            self.input_src.set("External Ref." if data["input_src"] == 1
                               else "Onboard Crystal")
            for ch in data.get("channels", []):
                i = int(ch.get("channel", -1))
                if 0 <= i < 6:
                    self.ch_freq[i].set(float(ch["freq"]))
                    self.ch_enabled[i].set(int(ch["enabled"]))
                    self.ch_invert[i].set(int(ch["invert"]))
                    self.ch_drive[i].set(str(int(float(ch["drive"]))))
            self.serial_port.set(data.get("port", ""))
            baud = str(data.get("baud", BAUD_DEFAULT))
            if baud in BAUD_CHOICES:
                self.baud_rate.set(baud)
        except (IOError, ValueError, KeyError):
            pass


if __name__ == "__main__":
    root = Tk()
    app = Si5351App(root)
    root.protocol("WM_DELETE_WINDOW", app._exit)
    root.mainloop()
