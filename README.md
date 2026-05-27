# VE2ZAZ Si5351 Synthesizer Board — Software and Firmware

Python 3 GUI and CLI tools for configuring a Si5351A/B/C synthesizer chip supervised by an Arduino-compatible board (Arduino Nano or LGT8F328P clone). Once configured, the Arduino reloads the Si5351 from EEPROM at every power-up.

Original software by Bert-VE2ZAZ (http://ve2zaz.net). Updated for Python 3 / Windows 11, May 2026.

---

## Files

| File | Purpose |
|------|---------|
| `Si5351_Synth_Board_Config_v2.py` | GUI configurator — set reference, 6 output channels, drive strength, invert |
| `Si5351_Raw_Data_Transfer_v2.py` | GUI raw register transfer — write individual Si5351 registers by address/value |
| `si5351_cli.py` | Command-line transfer — re-applies a saved `saved_settings.json` without opening a window |
| `Si5351C_Ext_Ref_Ctrl.ino` | Arduino sketch — receives config from PC, stores in EEPROM, applies to Si5351 |
| `About.html` | Detailed help for the GUI configurator |
| `About_Raw.html` | Detailed help for the raw register transfer tool |

---

## Requirements

- Python 3.8 or later (https://www.python.org/downloads/)
- PySerial: `pip install pyserial`
- Arduino IDE + the **Etherkit Si5351Arduino** library (install via Library Manager: Sketch → Include Library → Manage Libraries, search for "Si5351")

---

## Windows 11 / LGT8F328P note

Windows 10 and 11 include a built-in USB CDC driver — no extra driver needed for LGT8F328P-based boards ("USB Serial Device" in Device Manager).

**Never use 1200 baud.** On boards with native USB CDC (LGT8F328P), opening the port at exactly 1200 baud triggers the "bootloader touch" mechanism and the board enters ISP mode instead of running the sketch. The default baud rate in all tools is **2400**; any non-1200 value causes a normal app-reset.

---

## GUI configurator (`Si5351_Synth_Board_Config_v2.py`)

```
python Si5351_Synth_Board_Config_v2.py
```

- Select the COM port from the dropdown (click **Refresh** if the board was just plugged in).
- Choose baud rate (default 2400; do not use 1200).
- Set the input reference (Onboard Crystal or External Ref.), frequency, and correction offset in ppm.
- Enable output channels and set frequency (Hz), drive strength (mA), and phase invert.
- Click **Transfer** to send the configuration to the board. The board saves it to EEPROM and confirms with three status messages (Received / Saved / Applied).
- Click **Read Board** to load the configuration currently stored in the board's EEPROM back into the UI. Useful for verifying board state or moving a configuration to a different machine.

Settings are saved to `saved_settings.json` on exit and reloaded at next launch. The file is human-readable JSON and can be edited directly in any text editor.

**Migrating from an older install:** The GUI does not read the old `saved_settings.cfg`. On first launch it will start with defaults; the new JSON file is created automatically on exit. To migrate without re-entering settings manually, either:
- Use **Read Board** to load the current board configuration into the UI, then exit to save `saved_settings.json`, or
- Run the CLI against the old file: `python si5351_cli.py --settings saved_settings.cfg` — the legacy plain-text format is still accepted.

---

## Raw register transfer (`Si5351_Raw_Data_Transfer_v2.py`)

```
python Si5351_Raw_Data_Transfer_v2.py
```

Enter Si5351 register writes in the text area, one per line, in the format `address,value` (decimal). Lines beginning with `;` are treated as comments. Click **Transfer** to send to the board.

Register data is saved to `Raw_Data.txt` on exit.

---

## CLI tool (`si5351_cli.py`)

Re-applies a saved `saved_settings.json` from the command line — no GUI required.

```
python si5351_cli.py                        # use port saved in settings
python si5351_cli.py COM10                  # override port
python si5351_cli.py COM10 --settings my.json
python si5351_cli.py COM10 --settings saved_settings.cfg   # legacy format
python si5351_cli.py --list-ports
python si5351_cli.py --baud 9600 COM10
```

Single-channel modifications (the full config is transferred with one channel overridden):

```
python si5351_cli.py COM10 --channel 2 --frequency 14100000 --enable
python si5351_cli.py COM10 --channel 0 --drive 8 --permanent
python si5351_cli.py COM10 --channel 1 --disable --permanent
python si5351_cli.py       --channel 2 --frequency 14100000 --permanent  # update file only, no board
```

`--permanent` writes the modified settings back to the JSON file after a successful transfer. If no port is available it updates the file without transferring.

---

## Arduino sketch (`Si5351C_Ext_Ref_Ctrl.ino`)

Compile and upload with the Arduino IDE. Requires the **Etherkit Si5351Arduino** library.

The sketch implements the following serial protocol:

| Command sent by PC | Board response | Meaning |
|--------------------|----------------|---------|
| `$…%` | `O`, `E`, `S` | Formatted config (from GUI configurator) |
| `@…%` | `O`, `E`, `S` | Raw register config (from raw transfer tool) |
| `?` | EEPROM dump ending with `%`, or `!` if empty | Read back stored config |

At power-up the board re-applies whatever configuration is stored in EEPROM automatically.

---

## Legal

This software is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or any later version. See https://www.gnu.org/licenses/ for details. When modifying the software, a mention of the original author Bert-VE2ZAZ would be a gracious consideration.
