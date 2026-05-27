#!/usr/bin/env python3
"""
si5351_cli.py  —  Transfer Si5351 config from the command line.

Reads saved_settings.json (written by the GUI app) and transfers the config
to the board without opening any window.  Useful for scripting or for
re-applying a saved config after a power cycle.

Usage:
    python si5351_cli.py                                 use port saved in settings
    python si5351_cli.py COM10                           override port
    python si5351_cli.py COM10 --settings my.json
    python si5351_cli.py COM10 --settings saved_settings.cfg   (legacy format)
    python si5351_cli.py --list-ports

    # Single-channel modification (transfer full config with one channel changed):
    python si5351_cli.py COM10 --channel 2 --frequency 14100000 --enable
    python si5351_cli.py COM10 --channel 2 --frequency 14100000 --enable --permanent
    python si5351_cli.py COM10 --channel 0 --drive 8
    python si5351_cli.py COM10 --channel 1 --disable --permanent
    python si5351_cli.py        --channel 2 --frequency 14100000 --permanent  (no board: update file only)
"""

import json
import sys
import time
import argparse

import serial
import serial.tools.list_ports

# ---------------------------------------------------------------------------
# Si5351 constants (must match the sketch)
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

BAUD_DEFAULT = 2400  # Must NOT be 1200 (triggers LGT8F328P bootloader-touch)


# ---------------------------------------------------------------------------
# Settings loader  (reads the same file written by the GUI)
# ---------------------------------------------------------------------------

def _load_settings_legacy(lines: list) -> dict:
    return {
        "ref_freq":   float(lines[2]),
        "ref_corr":   float(lines[3]),
        "input_src":  int(lines[4]),
        "ch_freq":    [float(lines[5 + i])       for i in range(6)],
        "ch_enabled": [int(lines[11 + i])         for i in range(6)],
        "ch_invert":  [int(lines[17 + i])         for i in range(6)],
        "ch_drive":   [int(float(lines[23 + i]))  for i in range(6)],
        "port":       lines[29],
        "baud":       int(lines[30]) if len(lines) > 30 else BAUD_DEFAULT,
    }


def load_settings(path: str) -> dict:
    with open(path) as f:
        raw = f.read()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        print(f"Note: {path} is in legacy format — loading as plain text.")
        return _load_settings_legacy(raw.splitlines())
    ch_freq    = [10_000_000.0] * 6
    ch_enabled = [0] * 6
    ch_invert  = [0] * 6
    ch_drive   = [2] * 6
    for ch in data.get("channels", []):
        i = int(ch.get("channel", -1))
        if 0 <= i < 6:
            ch_freq[i]    = float(ch["freq"])
            ch_enabled[i] = int(ch["enabled"])
            ch_invert[i]  = int(ch["invert"])
            ch_drive[i]   = int(float(ch["drive"]))
    return {
        "ref_freq":   float(data["ref_freq"]),
        "ref_corr":   float(data["ref_corr"]),
        "input_src":  int(data["input_src"]),          # 1=External, 2=Crystal
        "ch_freq":    ch_freq,
        "ch_enabled": ch_enabled,
        "ch_invert":  ch_invert,
        "ch_drive":   ch_drive,
        "port":       data.get("port", ""),
        "baud":       int(data.get("baud", BAUD_DEFAULT)),
    }


# ---------------------------------------------------------------------------
# Transfer
# ---------------------------------------------------------------------------

def transfer(port: str, settings: dict, baud: int = BAUD_DEFAULT) -> bool:
    ref_freq = settings["ref_freq"]
    ref_corr = settings["ref_corr"]

    print(f"Opening {port} at {baud} baud...", end=" ", flush=True)
    ser = serial.Serial()
    ser.baudrate = baud
    ser.timeout  = 15
    ser.port     = port
    try:
        ser.open()
    except (OSError, serial.SerialException) as exc:
        print(f"\nERROR: {exc}")
        return False

    print("waiting for board...", end=" ", flush=True)
    recv = ser.read(1)
    if recv != b'R':
        diag = ("0x" + recv.hex()) if recv else "timeout"
        print(f"\nERROR: expected 'R', got {diag}")
        ser.close()
        return False
    print("ready.")

    def send(cmd: str):
        ser.write(cmd.encode("ascii"))

    send("$")
    send(f"{INIT},{SI5351_CRYSTAL_LOAD_0PF},{int(ref_freq)},{ref_corr * 1000}|")
    time.sleep(1)

    if settings["input_src"] == 2:
        send(f"{SET_PLL_INPUT},{SI5351_PLLA},{SI5351_PLL_INPUT_XO}|")
    else:
        send(f"{SET_REF_FREQ},{int(ref_freq)},{SI5351_PLL_INPUT_CLKIN}|")
        send(f"{SET_CORRECTION},{ref_corr * 1000},{SI5351_PLL_INPUT_CLKIN}|")
        send(f"{SET_PLL_INPUT},{SI5351_PLLA},{SI5351_PLL_INPUT_CLKIN}|")
        time.sleep(1)

    for clk in range(6):
        if settings["ch_enabled"][clk]:
            drive_idx = settings["ch_drive"][clk] // 2 - 1
            freq      = settings["ch_freq"][clk]
            invert    = settings["ch_invert"][clk]
            send(f"{SET_FREQ},{int(freq * 100)},{clk}|")
            send(f"{DRIVE_STRENGTH},{clk},{drive_idx}|")
            send(f"{SET_CLOCK_INVERT},{clk},{invert}|")
            time.sleep(1)

    send(f"{PLL_RESET},{SI5351_PLLA}|")
    send("%")
    while ser.out_waiting:
        pass

    for expected, msg in [
        (b'O', "Configuration received"),
        (b'E', "Saved to EEPROM"),
        (b'S', "Applied to Si5351"),
    ]:
        got = ser.read(1)
        if got == expected:
            print(f"  {msg}")
        else:
            diag = ("0x" + got.hex()) if got else "timeout"
            print(f"\nERROR: expected '{expected.decode()}', got {diag}")
            ser.close()
            return False

    ser.close()
    print("Done.")
    return True


# ---------------------------------------------------------------------------
# Settings writer
# ---------------------------------------------------------------------------

def save_settings(path: str, settings: dict):
    data = {
        "ref_freq":  settings["ref_freq"],
        "ref_corr":  settings["ref_corr"],
        "input_src": settings["input_src"],
        "channels": [
            {
                "channel": i,
                "freq":    settings["ch_freq"][i],
                "enabled": settings["ch_enabled"][i],
                "invert":  settings["ch_invert"][i],
                "drive":   str(settings["ch_drive"][i]),
            }
            for i in range(6)
        ],
        "port": settings.get("port", ""),
        "baud": str(settings.get("baud", BAUD_DEFAULT)),
    }
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"  Settings saved to {path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        description="Transfer Si5351 config from command line (reads saved_settings.json)"
    )
    ap.add_argument("port", nargs="?",
                    help="COM port (e.g. COM10). Overrides the port saved in settings.")
    ap.add_argument("--settings", default="saved_settings.json",
                    metavar="FILE",
                    help="settings file to use (default: saved_settings.json; legacy saved_settings.cfg also accepted)")
    ap.add_argument("--baud", type=int, default=None,
                    help="baud rate (default: from settings or 2400; never use 1200)")
    ap.add_argument("--list-ports", action="store_true",
                    help="list available COM ports and exit")

    # Single-channel modification
    ch_grp = ap.add_argument_group("channel modification (all require --channel)")
    ch_grp.add_argument("--channel", type=int, metavar="N",
                        help="channel to modify (0-5)")
    ch_grp.add_argument("--frequency", type=float, metavar="HZ",
                        help="set channel frequency in Hz")
    ch_grp.add_argument("--drive", type=int, choices=[2, 4, 6, 8], metavar="MA",
                        help="set drive strength in mA (2, 4, 6, or 8)")
    en_ex = ch_grp.add_mutually_exclusive_group()
    en_ex.add_argument("--enable",  action="store_true", help="enable the channel")
    en_ex.add_argument("--disable", action="store_true", help="disable the channel")
    inv_ex = ch_grp.add_mutually_exclusive_group()
    inv_ex.add_argument("--invert",    action="store_true", help="invert channel output")
    inv_ex.add_argument("--no-invert", action="store_true", dest="no_invert",
                        help="clear channel output invert")

    ap.add_argument("--permanent", action="store_true",
                    help="write modified settings back to the JSON settings file")

    args = ap.parse_args()

    if args.list_ports:
        ports = list(serial.tools.list_ports.comports())
        if not ports:
            print("No COM ports found.")
        for p in sorted(ports):
            print(f"  {p.device:<12} {p.description}")
        sys.exit(0)

    try:
        settings = load_settings(args.settings)
    except (IOError, ValueError, IndexError) as exc:
        print(f"ERROR reading {args.settings}: {exc}")
        print("Run the GUI app first to create a saved settings file.")
        sys.exit(1)

    # Validate and apply channel modifications
    ch_flags = (args.frequency, args.drive, args.enable, args.disable,
                args.invert, args.no_invert)
    if any(ch_flags) and args.channel is None:
        ap.error("--channel N is required when using channel modification options")
    if args.channel is not None:
        clk = args.channel
        if not 0 <= clk <= 5:
            ap.error(f"--channel must be 0-5, got {clk}")
        if args.frequency is not None:
            settings["ch_freq"][clk] = args.frequency
        if args.enable:
            settings["ch_enabled"][clk] = 1
        if args.disable:
            settings["ch_enabled"][clk] = 0
        if args.drive is not None:
            settings["ch_drive"][clk] = args.drive
        if args.invert:
            settings["ch_invert"][clk] = 1
        if args.no_invert:
            settings["ch_invert"][clk] = 0

    port = args.port or settings.get("port")
    baud = args.baud or settings.get("baud", BAUD_DEFAULT)

    if port:
        ok = transfer(port, settings, baud=baud)
        if args.permanent and ok:
            save_settings(args.settings, settings)
        sys.exit(0 if ok else 1)
    elif args.permanent:
        # No board connected — just update the settings file
        save_settings(args.settings, settings)
        sys.exit(0)
    else:
        print("ERROR: no COM port specified and none found in settings file.")
        sys.exit(1)


if __name__ == "__main__":
    main()
