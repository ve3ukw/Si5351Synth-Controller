#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Si5351 Raw Data Transfer
# Original by Bert - VE2ZAZ (http://ve2zaz.net), Version 0.3, April 2019
# Ported to Python 3 and cleaned up.
#
# Requires: pyserial (pip install pyserial)
#           tkinter  (ships with most Python installs; on Debian/Ubuntu:
#                     sudo apt install python3-tk)

import os
import sys
import time
import platform
import webbrowser

import serial                              # pyserial
from tkinter import (
    Tk, Canvas, Frame, Text, Scrollbar, Entry, Button,
    StringVar,
    END, NW, X, Y, BOTTOM, TOP, RIGHT, NORMAL, DISABLED,
)

# Baud rate used to talk to the board.
# NOTE: Must NOT be 1200 — the LGT8F328P treats a 1200-baud connect as the
# Arduino "bootloader touch" and enters ISP mode instead of running the sketch.
BAUD_RATE = 2400


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------
def is_number(s):
    """Return True if the string represents a number, without letters or punctuation."""
    try:
        float(s)
        return True
    except ValueError:
        return False


def ErrMsg(errorString):
    """Display an error message in the textbox at the bottom of the main window."""
    TextMessBox.config(fg="red")
    TextMessBox.insert(END, errorString)
    TextMessBox.see(END)
    TextMessBox.update()
    ser.close()
    Bouton_Transfert.config(state=NORMAL)


def successMsg(successString):
    """Display a success message in the textbox at the bottom of the main window."""
    TextMessBox.config(fg="blue")
    TextMessBox.insert(END, successString)
    TextMessBox.see(END)
    TextMessBox.update()


def Bascule_Bouton_About():
    """Open the About page in the default web browser."""
    webbrowser.open('file://' + os.path.realpath('About_Raw.html'), new=1, autoraise=True)


def Bascule_Bouton_Transfert():
    """Transfer the raw register data to the Arduino (Transfer button)."""
    Bouton_Transfert.config(state=DISABLED)
    time.sleep(0.1)

    # Validate the content: every non-comment line must be "number,number".
    TempText = DataBox.get("1.0", 'end-1c').splitlines()  # split the lines and remove the "\n"
    for line in TempText:
        if not line or line[0] == ";":
            continue
        line_params = line.replace(';', ',').split(",")
        if not (is_number(str(line_params[0])) and is_number(str(line_params[1]))):
            ErrMsg("\nError! One or more of the entry fields contain non-numerals "
                   "or is not properly formatted. Please correct...")
            return

    successMsg("\n-----------------------------------------"
               "\nConfiguration Transfer Initiated...")

    # Open the port and reset the Arduino (see notes in the configurator script).
    ser.baudrate = BAUD_RATE
    ser.timeout = 15        # board takes ~2.5 s to boot; 15 s gives ample margin
    ser.port = str(Serial_Port_Value.get())
    try:
        ser.open()
    except (OSError, serial.SerialException):
        ErrMsg("\nError! Serial port is unavailable or not present. Verify port naming")
        return

    # Opening at 2400 baud triggers a normal app-reset on the LGT8F328P.
    # No DTR manipulation needed — just wait for the sketch's startup 'R'.
    successMsg("\nWaiting for board to start…")
    recv = ser.read(1)
    if recv == b'R':
        successMsg("\nBoard ready")
    else:
        diag = ("0x" + recv.hex()) if recv else "nothing (timeout)"
        ErrMsg("\nError! Expected 'R' from board but received " + diag +
               ". Verify \n 1- proper processor board "
               "programming \n 2- proper USB connectivity to the processor board")
        return

    # Transmit the data
    ser.write(b"@")         # Signals the beginning of the raw parameter transmission
    for line in TempText:
        if not line or line[0] == ";":
            continue
        line_params = line.replace(';', ',').split(",")
        payload = str(line_params[0]) + "," + str(line_params[1]) + ";"
        print(payload)
        ser.write(payload.encode("ascii"))
        time.sleep(0.05)    # Pause required so the Arduino can swallow the characters before its Rx buffer fills
    ser.write(b"%")         # Signals the end of transmission
    while ser.out_waiting != 0:
        pass

    if ser.read(1) == b'O':
        successMsg("\nConfiguration data received by processor")
    else:
        ErrMsg("\nError! Software did not receive confirmation that the ATmega "
               "processor received the configuration data. Try again...")
        return
    if ser.read(1) == b'E':
        successMsg("\nConfiguration saved to the ATmega processor EEPROM")
    else:
        ErrMsg("\nError! Software did not receive confirmation that the "
               "configuration data was saved to the ATmega processor EEPROM. Try again...")
        return
    if ser.read(1) == b'S':
        successMsg("\nConfiguration data transferred from the ATmega processor to the Si5351")
    else:
        ErrMsg("\nError! Software did not receive confirmation that the "
               "configuration data transferred from the ATmega processor to the Si5351. Try again...")
        return

    ser.close()
    successMsg("\nConfiguration Success!")
    Bouton_Transfert.config(state=NORMAL)


def Bascule_Bouton_Sortie():
    """Save the raw data and the window settings, then exit (Exit button)."""
    try:
        with open(os.path.join(os.getcwd(), "Raw_Data.txt"), 'w') as Datafile:
            Datafile.write(DataBox.get("1.0", 'end-1c'))
    except IOError:
        ErrMsg("\nError! Software cannot save the raw data. "
               "Will revert to default values at next launch. Exiting...")
        time.sleep(5)

    # Save program settings
    try:
        with open("./saved_settings_raw.cfg", 'w') as f:
            f.write(str(Fenetre_Princ.winfo_x()) + "\n")  # Window X position
            f.write(str(Fenetre_Princ.winfo_y()) + "\n")  # Window Y position
            f.write(Serial_Port_Value.get() + "\n")
    except IOError:
        ErrMsg("\nError! Software cannot save its window settings. "
               "Will revert to default values at next launch. Exiting...")
        time.sleep(5)
    sys.exit()


# ---------------------------------------------------------------------------
# Main Window Creation
# ---------------------------------------------------------------------------
bgcolor = 'snow3'
Main_Window_Width_x = 800
Main_Window_Width_y = 540

Fenetre_Princ = Tk()
Fenetre_Princ.title("Si5351 Raw Data Transfer")
Fenetre_Princ.geometry('{}x{}'.format(Main_Window_Width_x, Main_Window_Width_y))
Fenetre_Princ.resizable(False, False)

canvas = Canvas(Fenetre_Princ, width=Main_Window_Width_x, height=Main_Window_Width_y - 61, bd=0)
canvas.pack()

canvas.create_text(270, 5, text="Si5351 Raw Data Transfer",
                   font=("Helvetica", 16), fill="blue", anchor=NW)

# Absolute positioning reference point for all elements
first_element_offset_x = 30
first_element_offset_y = 10

# Text box for the raw data
DataBoxFrm = Frame(Fenetre_Princ)
DataBoxFrm.place(x=0, y=50, width=Main_Window_Width_x, height=350)
DataBox = Text(DataBoxFrm, font=("Monospace", 12), state=NORMAL, bg="light gray",
               borderwidth=1, undo=True, wrap='word', relief="sunken")
DataS = Scrollbar(DataBoxFrm, orient="vertical", command=DataBox.yview)
DataBox.configure(yscrollcommand=DataS.set)
DataS.pack(fill=Y, side=RIGHT)
DataBox.pack(side=TOP, fill=X)
DataBox.config(fg="black")
DataBox.update()

# Message area
TextMessBoxFrm = Frame(Fenetre_Princ, width=Main_Window_Width_x, height=60)
TextMessBoxFrm.pack(side=BOTTOM, fill=X)
TextMessBox = Text(TextMessBoxFrm, font=("Helvetica", 10), fg="blue", state=NORMAL,
                   bg="light gray", borderwidth=1, undo=True, wrap='word')
S = Scrollbar(TextMessBoxFrm, orient="vertical", command=TextMessBox.yview)
TextMessBox.configure(yscrollcommand=S.set)
S.pack(fill=Y, side=RIGHT)
TextMessBox.pack(side=BOTTOM, fill=X)

# Serial port entry box
canvas.create_text(first_element_offset_x + 68, first_element_offset_y + 402,
                   text="Serial Port", font=("Helvetica", 10), fill="blue", anchor=NW)
Serial_Port_Value = StringVar(Fenetre_Princ)
Serial_Port = Entry(Fenetre_Princ, textvariable=Serial_Port_Value)
Serial_Port.place(x=first_element_offset_x + 55, y=first_element_offset_y + 417)
if platform.system() == "Windows":
    Serial_Port_Value.set("COM1")
    Serial_Port.config(width=13, relief="sunken", borderwidth=3)
else:
    Serial_Port_Value.set("/dev/ttyUSB0")      # Default Linux serial port
    Serial_Port.config(width=10, relief="sunken", borderwidth=3)

# Buttons
# Transfer button
Bouton_Transfert_Label = StringVar()
Bouton_Transfert_Label.set("Transfer")
Bouton_Transfert = Button(Fenetre_Princ, textvariable=Bouton_Transfert_Label, width=10,
                          relief="raised", border=3, command=Bascule_Bouton_Transfert)
Bouton_Transfert.place(x=first_element_offset_x + 150, y=first_element_offset_y + 415)

# Exit button
Bouton_Sortie_Label = StringVar()
Bouton_Sortie_Label.set("Exit")
Bouton_Sortie = Button(Fenetre_Princ, textvariable=Bouton_Sortie_Label, width=10,
                       relief="raised", border=3, command=Bascule_Bouton_Sortie)
Bouton_Sortie.place(x=first_element_offset_x + 550, y=first_element_offset_y + 415)

# About button
Bouton_About_Label = StringVar()
Bouton_About_Label.set("About...")
Bouton_About = Button(Fenetre_Princ, textvariable=Bouton_About_Label, width=10,
                      relief="raised", border=3, command=Bascule_Bouton_About)
Bouton_About.place(x=first_element_offset_x + 350, y=first_element_offset_y + 415)

# Serial Port definition
ser = serial.Serial()

# Read the configuration file
try:
    with open(os.path.join(os.getcwd(), "saved_settings_raw.cfg"), 'r') as f:
        Fenetre_Princ.geometry('%dx%d+%d+%d' % (Main_Window_Width_x, Main_Window_Width_y,
                                                int(f.readline()), int(f.readline())))
        Serial_Port_Value.set(f.readline()[0:-1])
except (IOError, ValueError):
    ErrMsg("\nError! Software cannot retrieve its window settings. Reverting to default values...")

# Load the raw data into the window
try:
    with open(os.path.join(os.getcwd(), "Raw_Data.txt"), 'r') as Datafile:
        DataBox.insert(END, Datafile.read())
        DataBox.update()
except (IOError, ValueError):
    ErrMsg("\nError! Software cannot retrieve the raw data. Reverting to default values...")

canvas.pack()  # Refreshes the canvas text

successMsg("Welcome to the Si5351A/B/C Raw Data Transfer Software, by Bert-VE2ZAZ, "
           "Version 0.3, April 2019. http://ve2zaz.net")
successMsg("\nPlease note that the settings shown are retrieved from the last session, "
           "not from the ATmega processor EEPROM.")

Fenetre_Princ.mainloop()
