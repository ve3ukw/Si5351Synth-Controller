#!/usr/bin/env python3
"""
Si5351 board serial diagnostic.

Usage:
    python serial_diag.py              — list available COM ports
    python serial_diag.py COM10        — probe that port

Runs four strategies in order, stopping at the first one that receives 'R'.

  A  Open → listen immediately (no reset attempt).
     Catches 'R' if the board sends it the moment a host connects.
     *** Run this immediately after unplugging and replugging the USB cable. ***

  B  DTR toggle (original approach, works on Windows 10).
     Open → dtr=False → dtr=True → listen.

  C  Close / reopen  (USB disconnect as reset trigger).
     Open briefly → close → wait 4 s → reopen → listen.

  D  Manual reset.
     User presses the RESET button on the board; script listens for 10 s.
"""

import sys
import time
import serial
import serial.tools.list_ports


def list_ports():
    ports = list(serial.tools.list_ports.comports())
    if not ports:
        print("No COM ports found.")
        return
    print(f"{'Port':<12} {'Description'}")
    print("-" * 60)
    for p in sorted(ports):
        print(f"{p.device:<12} {p.description}")


BAUD_RATE = 2400   # 1200 triggers the LGT8F328P's 1200-baud-touch bootloader entry


def _open(port: str, timeout: float = 0.1) -> serial.Serial:
    s = serial.Serial()
    s.baudrate = BAUD_RATE
    s.timeout = timeout
    s.port = port
    s.dsrdtr = False
    s.rtscts = False
    s.open()
    return s


def _listen(s: serial.Serial, seconds: float, label: str = "") -> list:
    if label:
        print(f"  [{label}] listening for {seconds:.0f} s …")
    received = []
    start = time.time()
    while time.time() - start < seconds:
        b = s.read(1)
        if b:
            elapsed = time.time() - start
            ch = chr(b[0]) if 32 <= b[0] < 127 else "."
            print(f"    t={elapsed:5.2f}s  0x{b.hex().upper()}  '{ch}'")
            received.append(b)
    return received


def strategy_a(port: str) -> bool:
    """Open and listen immediately — no reset attempt."""
    print("\n=== Strategy A: open → listen immediately (no reset) ===")
    print("TIP: for the best result, unplug the board's USB cable,")
    print("     plug it back in, then immediately run this script.\n")
    try:
        s = _open(port)
    except serial.SerialException as e:
        print(f"Could not open {port}: {e}")
        return False
    received = _listen(s, 10.0, "A")
    s.close()
    if received and received[0] == b'R':
        print("\n*** Strategy A: board sends 'R' on initial connect. ***")
        print("    Fix: Python app must open port WITHOUT any reset dance.")
        return True
    if not received:
        print("  Nothing received.")
    return False


def strategy_b(port: str) -> bool:
    """DTR toggle (original)."""
    print("\n=== Strategy B: DTR toggle ===")
    try:
        s = _open(port)
    except serial.SerialException as e:
        print(f"Could not open {port}: {e}")
        return False
    time.sleep(0.1)
    s.dtr = False
    print(f"  DTR → False (s.dtr reads back: {s.dtr})")
    time.sleep(0.05)
    s.reset_input_buffer()
    s.dtr = True
    print(f"  DTR → True  (s.dtr reads back: {s.dtr})")
    received = _listen(s, 5.0, "B")
    s.close()
    if received and received[0] == b'R':
        print("\n*** Strategy B: DTR toggle works here. ***")
        return True
    if not received:
        print("  Nothing received.")
    return False


def strategy_c(port: str) -> bool:
    """Close / reopen (USB disconnect as reset)."""
    print("\n=== Strategy C: close / reopen ===")
    try:
        s = _open(port)
    except serial.SerialException as e:
        print(f"Could not open {port}: {e}")
        return False
    time.sleep(0.5)
    s.reset_input_buffer()
    s.close()
    print("  Port closed (USB disconnect sent to board).")
    print("  Waiting 4 s for re-enumeration …")
    time.sleep(4.0)
    try:
        s = _open(port)
    except serial.SerialException as e:
        print(f"  Could not reopen {port}: {e}")
        return False
    received = _listen(s, 10.0, "C")
    s.close()
    if received and received[0] == b'R':
        print("\n*** Strategy C: close/reopen works. ***")
        return True
    if not received:
        print("  Nothing received.")
    return False


def strategy_d(port: str) -> bool:
    """Manual reset."""
    print("\n=== Strategy D: manual reset ===")
    print("  Open the port first, then press RESET on the board …")
    try:
        s = _open(port)
    except serial.SerialException as e:
        print(f"Could not open {port}: {e}")
        return False
    input("  Press RESET on the board, then press Enter here: ")
    s.reset_input_buffer()
    received = _listen(s, 10.0, "D")
    s.close()
    if received and received[0] == b'R':
        print("\n*** Strategy D: manual reset works. ***")
        print("    A 'Manual Reset' mode can be added to the app UI as a fallback.")
        return True
    if not received:
        print("  Nothing received even after manual reset.")
        print("  Check: is the correct sketch loaded? Does it run Serial.print(\"R\") in setup()?")
    return False


def probe(port: str):
    print(f"\nProbing {port} …")
    for fn in (strategy_a, strategy_b, strategy_c, strategy_d):
        if fn(port):
            return
    print("\n--- All strategies failed ---")
    print("Check USB cable, Device Manager driver, and that the correct sketch is on the board.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        list_ports()
    else:
        try:
            probe(sys.argv[1])
        except serial.SerialException as exc:
            print(f"Serial error: {exc}")
        except KeyboardInterrupt:
            print("\nAborted.")
