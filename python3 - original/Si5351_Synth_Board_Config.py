#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Si5351 Synthesizer Board Configurator
# Original by Bert - VE2ZAZ (http://ve2zaz.net), Version 0.5, December 2019
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
    Tk, Canvas, Frame, Text, Scrollbar, Entry, Button, Checkbutton, OptionMenu,
    StringVar, IntVar, DoubleVar,
    END, NW, X, Y, BOTTOM, RIGHT, NORMAL, DISABLED,
)

# ---------------------------------------------------------------------------
# Constant definitions related to the Si5351 library
# ---------------------------------------------------------------------------
SI5351_CLK0 = 0
SI5351_CLK1 = 1
SI5351_CLK2 = 2
SI5351_CLK3 = 3
SI5351_CLK4 = 4
SI5351_CLK5 = 5
SI5351_CLK6 = 6
SI5351_CLK7 = 7
SI5351_PLLA = 0
SI5351_PLLB = 1
SI5351_CLK_SRC_XTAL = 0
SI5351_CLK_SRC_CLKIN = 1
SI5351_CLK_SRC_MS0 = 2
SI5351_CLK_SRC_MS = 3
SI5351_PLL_INPUT_XO = 0
SI5351_PLL_INPUT_CLKIN = 1
SI5351_CRYSTAL_LOAD_0PF = 0

# Constant definitions that identify the Si5351 library commands
INIT = "1"
SET_PLL_INPUT = "2"
SET_REF_FREQ = "3"
SET_CORRECTION = "4"
SET_FREQ = "5"
OUTPUT_ENABLE = "6"
DRIVE_STRENGTH = "7"
SET_CLOCK_INVERT = "8"
PLL_RESET = "9"

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


def send(command):
    """Send a command string to the serial port as bytes, and echo it to stdout."""
    print(command)
    ser.write(command.encode("ascii"))


def ErrMsg(errorString):
    """Display an error message in the textbox at the bottom of the main window."""
    TextMessBox.config(fg="red")
    TextMessBox.insert(END, errorString)
    TextMessBox.see(END)
    TextMessBox.update()
    ser.close()
    Transfer_Button.config(state=NORMAL)


def successMsg(successString):
    """Display a success message in the textbox at the bottom of the main window."""
    TextMessBox.config(fg="blue")
    TextMessBox.insert(END, successString)
    TextMessBox.see(END)
    TextMessBox.update()


def About_Button_Toggle():
    """Open the About page in the default web browser."""
    webbrowser.open('file://' + os.path.realpath('./About.html'), new=1, autoraise=True)


def Transfer_Button_Toggle():
    """Transfer the configuration parameters to the Arduino (Transfer button)."""
    Transfer_Button.config(state=DISABLED)  # Disable transfer button

    # Validation that all entry fields contain only numbers (digits)
    if not (is_number(Ref_Freq_Value.get()) and
            is_number(Ref_Freq_Corr_Value.get()) and
            is_number(Out0_freq_Value.get()) and
            is_number(Out1_freq_Value.get()) and
            is_number(Out2_freq_Value.get()) and
            is_number(Out3_freq_Value.get()) and
            is_number(Out4_freq_Value.get()) and
            is_number(Out5_freq_Value.get())):
        ErrMsg("\nError! One or more of the entry fields contain non-numerals "
               "or is not properly formatted. Please correct...")
        return

    successMsg("\n-----------------------------------------"
               "\nConfiguration Transfer Initiated...")
    time.sleep(0.1)

    # Open the port and reset the Arduino. Opening the port toggles DTR, which
    # resets an Arduino Nano. We drive the reset explicitly and then wait for the
    # bootloader to finish before listening for the sketch's 'R' startup byte.
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

    send("$")               # Character that signals the beginning of the parameter transmission string

    # Configure the crystal
    send(INIT + "," + str(SI5351_CRYSTAL_LOAD_0PF) + "," +
         str(Ref_Freq_Value.get()) + "," + str(Ref_Freq_Corr_Value.get() * 1000) + "|")
    time.sleep(1)           # Pause required so the Arduino can swallow all characters before its Rx buffer fills

    if Input_Reference_choices[Pulldown_Input_Source_Value.get()] == 2:
        # Configuration when the crystal is the timing source
        send(SET_PLL_INPUT + "," + str(SI5351_PLLA) + "," + str(SI5351_PLL_INPUT_XO) + "|")
    if Input_Reference_choices[Pulldown_Input_Source_Value.get()] == 1:
        # Configuration when the external reference is the timing source
        send(SET_REF_FREQ + "," + str(Ref_Freq_Value.get()) + "," + str(SI5351_PLL_INPUT_CLKIN) + "|")
        send(SET_CORRECTION + "," + str(Ref_Freq_Corr_Value.get() * 1000) + "," + str(SI5351_PLL_INPUT_CLKIN) + "|")
        send(SET_PLL_INPUT + "," + str(SI5351_PLLA) + "," + str(SI5351_PLL_INPUT_CLKIN) + "|")
        time.sleep(1)

    # Per-output configuration. Group the widgets so the six channels share one loop.
    channels = (
        (SI5351_CLK0, Out_check_Value_0, Out0_freq_Value, Pulldown0_Value, Out_Inv_check_Value_0),
        (SI5351_CLK1, Out_check_Value_1, Out1_freq_Value, Pulldown1_Value, Out_Inv_check_Value_1),
        (SI5351_CLK2, Out_check_Value_2, Out2_freq_Value, Pulldown2_Value, Out_Inv_check_Value_2),
        (SI5351_CLK3, Out_check_Value_3, Out3_freq_Value, Pulldown3_Value, Out_Inv_check_Value_3),
        (SI5351_CLK4, Out_check_Value_4, Out4_freq_Value, Pulldown4_Value, Out_Inv_check_Value_4),
        (SI5351_CLK5, Out_check_Value_5, Out5_freq_Value, Pulldown5_Value, Out_Inv_check_Value_5),
    )
    for clk, enabled, freq, drive, invert in channels:
        if enabled.get() == 1:
            send(SET_FREQ + "," + str(freq.get() * 100) + "," + str(clk) + "|")
            # Drive index: 2/4/6/8 mA maps to 0/1/2/3. Use integer (floor) division.
            send(DRIVE_STRENGTH + "," + str(clk) + "," + str(drive.get() // 2 - 1) + "|")
            send(SET_CLOCK_INVERT + "," + str(clk) + "," + str(invert.get()) + "|")
            time.sleep(1)   # Pause required so the Arduino can swallow all characters before its Rx buffer fills

    # New in version 0.5: required to ensure proper phase alignment between the outputs.
    send(PLL_RESET + "," + str(SI5351_PLLA) + "|")

    send("%")               # This character signals the end of parameter transmission
    while ser.out_waiting != 0:  # Wait for all characters to be transmitted
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
    Transfer_Button.config(state=NORMAL)    # Re-enable transfer button


def Exit_Button():
    """Save the program configuration to a text file, then exit (Exit button / window close)."""
    try:
        with open("./saved_settings.cfg", 'w') as f:
            f.write(str(Main_Window.winfo_x()) + "\n")  # Window X position
            f.write(str(Main_Window.winfo_y()) + "\n")  # Window Y position
            f.write(str(Ref_Freq_Value.get()) + "\n")
            f.write(str(Ref_Freq_Corr_Value.get()) + "\n")
            f.write(str(Input_Reference_choices[Pulldown_Input_Source_Value.get()]) + "\n")
            f.write(str(Out0_freq_Value.get()) + "\n")
            f.write(str(Out1_freq_Value.get()) + "\n")
            f.write(str(Out2_freq_Value.get()) + "\n")
            f.write(str(Out3_freq_Value.get()) + "\n")
            f.write(str(Out4_freq_Value.get()) + "\n")
            f.write(str(Out5_freq_Value.get()) + "\n")
            f.write(str(Out_check_Value_0.get()) + "\n")
            f.write(str(Out_check_Value_1.get()) + "\n")
            f.write(str(Out_check_Value_2.get()) + "\n")
            f.write(str(Out_check_Value_3.get()) + "\n")
            f.write(str(Out_check_Value_4.get()) + "\n")
            f.write(str(Out_check_Value_5.get()) + "\n")
            f.write(str(Out_Inv_check_Value_0.get()) + "\n")
            f.write(str(Out_Inv_check_Value_1.get()) + "\n")
            f.write(str(Out_Inv_check_Value_2.get()) + "\n")
            f.write(str(Out_Inv_check_Value_3.get()) + "\n")
            f.write(str(Out_Inv_check_Value_4.get()) + "\n")
            f.write(str(Out_Inv_check_Value_5.get()) + "\n")
            f.write(str(Pulldown0_Value.get()) + "\n")
            f.write(str(Pulldown1_Value.get()) + "\n")
            f.write(str(Pulldown2_Value.get()) + "\n")
            f.write(str(Pulldown3_Value.get()) + "\n")
            f.write(str(Pulldown4_Value.get()) + "\n")
            f.write(str(Pulldown5_Value.get()) + "\n")
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
Main_Window_Width_x = 800       # Main window dimensions
Main_Window_Width_y = 540
Main_Window = Tk()
Main_Window.title("Si5351 Synthesizer Configuration")
Main_Window.geometry('{}x{}'.format(Main_Window_Width_x, Main_Window_Width_y))
Main_Window.resizable(False, False)

# Main window Canvas creation
canvas = Canvas(Main_Window, width=Main_Window_Width_x, height=Main_Window_Width_y - 61, bd=0)
canvas.create_rectangle(0, 0, Main_Window_Width_x, Main_Window_Width_y, fill=bgcolor, width=0)
canvas.pack()

# Text message box creation
TextMessBoxFrm = Frame(Main_Window, width=800, height=60)
TextMessBoxFrm.pack(side=BOTTOM, fill=X)
TextMessBox = Text(TextMessBoxFrm, font=("Helvetica", 10), fg="blue", state=NORMAL,
                   bg="light gray", borderwidth=1, undo=True, wrap='word')
S = Scrollbar(TextMessBoxFrm, orient="vertical", command=TextMessBox.yview)
TextMessBox.configure(yscrollcommand=S.set)
S.pack(fill=Y, side=RIGHT)
TextMessBox.pack(side=BOTTOM, fill=X)

# Main Title
canvas.create_text(230, 5, text="Si5351 Synthesizer Configuration",
                   font=("Helvetica", 16), fill="blue", anchor=NW)

# Input Reference selection choices in pull-down menus
Input_Reference_choices = {'External Ref.': 1, 'Onboard Crystal': 2}
# Output Drive Strength choices in pull-down menus
drive_choices = {'2', '4', '6', '8'}
# Channel colors
ch0_Color = "DarkOrange4"
ch1_Color = "firebrick4"
ch2_Color = "purple4"
ch3_Color = "DarkGoldenrod4"
ch4_Color = "DeepSkyBlue4"
ch5_Color = "dark green"

# Absolute positioning reference point (all widgets refer to this reference)
first_element_offset_x = 30
first_element_offset_y = 10

# Reference Selection pulldown menu
inSelect_pulld_x = 0
inSelect_pulld_y = 100
canvas.create_text(first_element_offset_x + inSelect_pulld_x + 25,
                   first_element_offset_y + inSelect_pulld_y - 20,
                   text="Input Select", font=("Helvetica", 10), fill="blue", anchor=NW)
Pulldown_Input_Source_Value = StringVar(Main_Window)
Pulldown_Input_Source_Value.set('Onboard Crystal')  # set the default option
Pulldown_Input_Source = OptionMenu(Main_Window, Pulldown_Input_Source_Value, *Input_Reference_choices)
Pulldown_Input_Source.place(x=first_element_offset_x + inSelect_pulld_x,
                            y=first_element_offset_y + inSelect_pulld_y)

# Reference Frequency entry box
inFreq_box_x = 150
inFreq_box_y = 58
canvas.create_text(first_element_offset_x + inFreq_box_x, first_element_offset_y + inFreq_box_y,
                   text="Input Frequency (Hz)", font=("Helvetica", 10), fill="blue", anchor=NW)
Ref_Freq_Value = DoubleVar(Main_Window)
Ref_Freq_Value.set(25000000)
Ref_Freq = Entry(Main_Window, textvariable=Ref_Freq_Value)
Ref_Freq.config(width=10, relief="sunken", borderwidth=3)
Ref_Freq.place(x=first_element_offset_x + inFreq_box_x + 18, y=first_element_offset_y + inFreq_box_y + 18)

# Reference Frequency Correction entry box
inFreq_Corr_box_x = inFreq_box_x
inFreq_Corr_box_y = inFreq_box_y + 50
canvas.create_text(first_element_offset_x + inFreq_Corr_box_x, first_element_offset_y + inFreq_Corr_box_y,
                   text="Frequency Offset (ppm)", font=("Helvetica", 10), fill="blue", anchor=NW)
Ref_Freq_Corr_Value = DoubleVar(Main_Window)
Ref_Freq_Corr_Value.set(0)
Ref_Freq_Corr = Entry(Main_Window, textvariable=Ref_Freq_Corr_Value)
Ref_Freq_Corr.config(width=10, relief="sunken", borderwidth=3)
Ref_Freq_Corr.place(x=first_element_offset_x + inFreq_Corr_box_x + 18, y=first_element_offset_y + inFreq_Corr_box_y + 18)

# Channel 0 widget positioning
outFreq_box_0_x = inFreq_box_x + 250
outFreq_box_0_y = inFreq_box_y
outCheck_0_x = outFreq_box_0_x - 50
outCheck_0_y = outFreq_box_0_y
OutDrive_pulld_0_x = outFreq_box_0_x + 200
OutDrive_pulld_0_y = outFreq_box_0_y + 14
outInvCheck_0_x = outCheck_0_x + 350
outInvCheck_0_y = outCheck_0_y
# Channel 0 Widgets
# Checkbox Enable
canvas.create_text(first_element_offset_x + outCheck_0_x, first_element_offset_y + outCheck_0_y,
                   text="Enable", font=("Helvetica", 10), fill=ch0_Color, anchor=NW)
Out_check_Value_0 = IntVar(Main_Window)
Out_check_0 = Checkbutton(Main_Window, variable=Out_check_Value_0, bg=bgcolor, relief="sunken", borderwidth=1)
Out_check_0.place(x=first_element_offset_x + outCheck_0_x + 8, y=first_element_offset_y + outCheck_0_y + 18)
Out_check_Value_0.set(1)
# Output Frequency
canvas.create_text(first_element_offset_x + outFreq_box_0_x, first_element_offset_y + outFreq_box_0_y,
                   text="Output 0 Frequency (Hz)", font=("Helvetica", 10), fill=ch1_Color, anchor=NW)
Out0_freq_Value = DoubleVar(Main_Window)
Out0_freq_Value.set(24000000.00)
Out0_freq = Entry(Main_Window, textvariable=Out0_freq_Value)
Out0_freq.config(width=13, relief="sunken", borderwidth=3)
Out0_freq.place(x=first_element_offset_x + outFreq_box_0_x + 18, y=first_element_offset_y + outFreq_box_0_y + 18)
# Drive pulldown menu
Pulldown0_Value = IntVar(Main_Window)
Pulldown0_Value.set(2)  # set the default option
Pulldown0 = OptionMenu(Main_Window, Pulldown0_Value, *drive_choices)
Pulldown0.place(x=first_element_offset_x + OutDrive_pulld_0_x, y=first_element_offset_y + OutDrive_pulld_0_y)
canvas.create_text(first_element_offset_x + OutDrive_pulld_0_x - 30, first_element_offset_y + OutDrive_pulld_0_y - 19,
                   text="Output 0 Drive (mA)", font=("Helvetica", 10), fill=ch0_Color, anchor=NW)
# Checkbox Invert
canvas.create_text(first_element_offset_x + outInvCheck_0_x, first_element_offset_y + outInvCheck_0_y,
                   text="Invert", font=("Helvetica", 10), fill=ch0_Color, anchor=NW)
Out_Inv_check_Value_0 = IntVar(Main_Window)
Out_Inv_check_0 = Checkbutton(Main_Window, variable=Out_Inv_check_Value_0, bg=bgcolor, relief="sunken", borderwidth=1)
Out_Inv_check_0.place(x=first_element_offset_x + outInvCheck_0_x + 4, y=first_element_offset_y + outInvCheck_0_y + 18)
Out_Inv_check_Value_0.set(0)

# Channel 1 widget positioning
outFreq_box_1_x = outFreq_box_0_x
outFreq_box_1_y = outFreq_box_0_y + 50
outCheck_1_x = outFreq_box_1_x - 50
outCheck_1_y = outFreq_box_1_y
OutDrive_pulld_1_x = outFreq_box_1_x + 200
OutDrive_pulld_1_y = outFreq_box_1_y + 14
outInvCheck_1_x = outCheck_1_x + 350
outInvCheck_1_y = outCheck_1_y
# Channel 1 Widgets
# Checkbox
canvas.create_text(first_element_offset_x + outCheck_1_x, first_element_offset_y + outCheck_1_y,
                   text="Enable", font=("Helvetica", 10), fill=ch1_Color, anchor=NW)
Out_check_Value_1 = IntVar(Main_Window)
Out_check_1 = Checkbutton(Main_Window, variable=Out_check_Value_1, bg=bgcolor, relief="sunken", borderwidth=1)
Out_check_1.place(x=first_element_offset_x + outCheck_1_x + 8, y=first_element_offset_y + outCheck_1_y + 18)
# Output Frequency
canvas.create_text(first_element_offset_x + outFreq_box_1_x, first_element_offset_y + outFreq_box_1_y,
                   text="Output 1 Frequency (Hz)", font=("Helvetica", 10), fill=ch1_Color, anchor=NW)
Out1_freq_Value = DoubleVar(Main_Window)
Out1_freq_Value.set(10000000)
Out1_freq = Entry(Main_Window, textvariable=Out1_freq_Value)
Out1_freq.config(width=13, relief="sunken", borderwidth=3)
Out1_freq.place(x=first_element_offset_x + outFreq_box_1_x + 18, y=first_element_offset_y + outFreq_box_1_y + 18)
# Drive pulldown menu
Pulldown1_Value = IntVar(Main_Window)
Pulldown1_Value.set(2)  # set the default option
Pulldown1 = OptionMenu(Main_Window, Pulldown1_Value, *drive_choices)
Pulldown1.place(x=first_element_offset_x + OutDrive_pulld_1_x, y=first_element_offset_y + OutDrive_pulld_1_y)
canvas.create_text(first_element_offset_x + OutDrive_pulld_1_x - 30, first_element_offset_y + OutDrive_pulld_1_y - 19,
                   text="Output 1 Drive (mA)", font=("Helvetica", 10), fill=ch1_Color, anchor=NW)
# Checkbox Invert
canvas.create_text(first_element_offset_x + outInvCheck_1_x, first_element_offset_y + outInvCheck_1_y,
                   text="Invert", font=("Helvetica", 10), fill=ch1_Color, anchor=NW)
Out_Inv_check_Value_1 = IntVar(Main_Window)
Out_Inv_check_1 = Checkbutton(Main_Window, variable=Out_Inv_check_Value_1, bg=bgcolor, relief="sunken", borderwidth=1)
Out_Inv_check_1.place(x=first_element_offset_x + outInvCheck_1_x + 4, y=first_element_offset_y + outInvCheck_1_y + 18)
Out_Inv_check_Value_1.set(0)

# Channel 2 widget positioning
outFreq_box_2_x = outFreq_box_1_x
outFreq_box_2_y = outFreq_box_1_y + 50
outCheck_2_x = outFreq_box_2_x - 50
outCheck_2_y = outFreq_box_2_y
OutDrive_pulld_2_x = outFreq_box_2_x + 200
OutDrive_pulld_2_y = outFreq_box_2_y + 14
outInvCheck_2_x = outCheck_2_x + 350
outInvCheck_2_y = outCheck_2_y
# Channel 2 Widgets
# Checkbox
canvas.create_text(first_element_offset_x + outCheck_2_x, first_element_offset_y + outCheck_2_y,
                   text="Enable", font=("Helvetica", 10), fill=ch2_Color, anchor=NW)
Out_check_Value_2 = IntVar(Main_Window)
Out_check_2 = Checkbutton(Main_Window, variable=Out_check_Value_2, bg=bgcolor, relief="sunken", borderwidth=1)
Out_check_2.place(x=first_element_offset_x + outCheck_2_x + 8, y=first_element_offset_y + outCheck_2_y + 18)
# Output Frequency
canvas.create_text(first_element_offset_x + outFreq_box_2_x, first_element_offset_y + outFreq_box_2_y,
                   text="Output 2 Frequency (Hz)", font=("Helvetica", 10), fill=ch2_Color, anchor=NW)
Out2_freq_Value = DoubleVar(Main_Window)
Out2_freq_Value.set(10000000)
Out2_freq = Entry(Main_Window, textvariable=Out2_freq_Value)
Out2_freq.config(width=13, relief="sunken", borderwidth=3)
Out2_freq.place(x=first_element_offset_x + outFreq_box_2_x + 18, y=first_element_offset_y + outFreq_box_2_y + 18)
# Drive pulldown menu
Pulldown2_Value = IntVar(Main_Window)
Pulldown2_Value.set(2)  # set the default option
Pulldown2 = OptionMenu(Main_Window, Pulldown2_Value, *drive_choices)
Pulldown2.place(x=first_element_offset_x + OutDrive_pulld_2_x, y=first_element_offset_y + OutDrive_pulld_2_y)
canvas.create_text(first_element_offset_x + OutDrive_pulld_2_x - 30, first_element_offset_y + OutDrive_pulld_2_y - 19,
                   text="Output 2 Drive (mA)", font=("Helvetica", 10), fill=ch2_Color, anchor=NW)
# Checkbox Invert
canvas.create_text(first_element_offset_x + outInvCheck_2_x, first_element_offset_y + outInvCheck_2_y,
                   text="Invert", font=("Helvetica", 10), fill=ch2_Color, anchor=NW)
Out_Inv_check_Value_2 = IntVar(Main_Window)
Out_Inv_check_2 = Checkbutton(Main_Window, variable=Out_Inv_check_Value_2, bg=bgcolor, relief="sunken", borderwidth=1)
Out_Inv_check_2.place(x=first_element_offset_x + outInvCheck_2_x + 4, y=first_element_offset_y + outInvCheck_2_y + 18)
Out_Inv_check_Value_2.set(0)

# Channel 3 widget positioning
outFreq_box_3_x = outFreq_box_2_x
outFreq_box_3_y = outFreq_box_2_y + 50
outCheck_3_x = outFreq_box_3_x - 50
outCheck_3_y = outFreq_box_3_y
OutDrive_pulld_3_x = outFreq_box_3_x + 200
OutDrive_pulld_3_y = outFreq_box_3_y + 14
outInvCheck_3_x = outCheck_3_x + 350
outInvCheck_3_y = outCheck_3_y
# Channel 3 Widgets
# Checkbox
canvas.create_text(first_element_offset_x + outCheck_3_x, first_element_offset_y + outCheck_3_y,
                   text="Enable", font=("Helvetica", 10), fill=ch3_Color, anchor=NW)
Out_check_Value_3 = IntVar(Main_Window)
Out_check_3 = Checkbutton(Main_Window, variable=Out_check_Value_3, bg=bgcolor, relief="sunken", borderwidth=1)
Out_check_3.place(x=first_element_offset_x + outCheck_3_x + 8, y=first_element_offset_y + outCheck_3_y + 18)
# Output Frequency
canvas.create_text(first_element_offset_x + outFreq_box_3_x, first_element_offset_y + outFreq_box_3_y,
                   text="Output 3 Frequency (Hz)", font=("Helvetica", 10), fill=ch3_Color, anchor=NW)
Out3_freq_Value = DoubleVar(Main_Window)
Out3_freq_Value.set(10000000)
Out3_freq = Entry(Main_Window, textvariable=Out3_freq_Value)
Out3_freq.config(width=13, relief="sunken", borderwidth=3)
Out3_freq.place(x=first_element_offset_x + outFreq_box_3_x + 18, y=first_element_offset_y + outFreq_box_3_y + 18)
# Drive pulldown menu
Pulldown3_Value = IntVar(Main_Window)
Pulldown3_Value.set(2)  # set the default option
Pulldown3 = OptionMenu(Main_Window, Pulldown3_Value, *drive_choices)
Pulldown3.place(x=first_element_offset_x + OutDrive_pulld_3_x, y=first_element_offset_y + OutDrive_pulld_3_y)
canvas.create_text(first_element_offset_x + OutDrive_pulld_3_x - 30, first_element_offset_y + OutDrive_pulld_3_y - 19,
                   text="Output 3 Drive (mA)", font=("Helvetica", 10), fill=ch3_Color, anchor=NW)
# Checkbox Invert
canvas.create_text(first_element_offset_x + outInvCheck_3_x, first_element_offset_y + outInvCheck_3_y,
                   text="Invert", font=("Helvetica", 10), fill=ch3_Color, anchor=NW)
Out_Inv_check_Value_3 = IntVar(Main_Window)
Out_Inv_check_3 = Checkbutton(Main_Window, variable=Out_Inv_check_Value_3, bg=bgcolor, relief="sunken", borderwidth=1)
Out_Inv_check_3.place(x=first_element_offset_x + outInvCheck_3_x + 4, y=first_element_offset_y + outInvCheck_3_y + 18)
Out_Inv_check_Value_3.set(0)

# Channel 4 widget positioning
outFreq_box_4_x = outFreq_box_3_x
outFreq_box_4_y = outFreq_box_3_y + 50
outCheck_4_x = outFreq_box_4_x - 50
outCheck_4_y = outFreq_box_4_y
OutDrive_pulld_4_x = outFreq_box_4_x + 200
OutDrive_pulld_4_y = outFreq_box_4_y + 14
outInvCheck_4_x = outCheck_4_x + 350
outInvCheck_4_y = outCheck_4_y
# Channel 4 Widgets
# Checkbox
canvas.create_text(first_element_offset_x + outCheck_4_x, first_element_offset_y + outCheck_4_y,
                   text="Enable", font=("Helvetica", 10), fill=ch4_Color, anchor=NW)
Out_check_Value_4 = IntVar(Main_Window)
Out_check_4 = Checkbutton(Main_Window, variable=Out_check_Value_4, bg=bgcolor, relief="sunken", borderwidth=1)
Out_check_4.place(x=first_element_offset_x + outCheck_4_x + 8, y=first_element_offset_y + outCheck_4_y + 18)
# Output Frequency
canvas.create_text(first_element_offset_x + outFreq_box_4_x, first_element_offset_y + outFreq_box_4_y,
                   text="Output 4 Frequency (Hz)", font=("Helvetica", 10), fill=ch4_Color, anchor=NW)
Out4_freq_Value = DoubleVar(Main_Window)
Out4_freq_Value.set(10000000)
Out4_freq = Entry(Main_Window, textvariable=Out4_freq_Value)
Out4_freq.config(width=13, relief="sunken", borderwidth=3)
Out4_freq.place(x=first_element_offset_x + outFreq_box_4_x + 18, y=first_element_offset_y + outFreq_box_4_y + 18)
# Drive pulldown menu
Pulldown4_Value = IntVar(Main_Window)
Pulldown4_Value.set(2)  # set the default option
Pulldown4 = OptionMenu(Main_Window, Pulldown4_Value, *drive_choices)
Pulldown4.place(x=first_element_offset_x + OutDrive_pulld_4_x, y=first_element_offset_y + OutDrive_pulld_4_y)
canvas.create_text(first_element_offset_x + OutDrive_pulld_4_x - 30, first_element_offset_y + OutDrive_pulld_4_y - 19,
                   text="Output 4 Drive (mA)", font=("Helvetica", 10), fill=ch4_Color, anchor=NW)
# Checkbox Invert
canvas.create_text(first_element_offset_x + outInvCheck_4_x, first_element_offset_y + outInvCheck_4_y,
                   text="Invert", font=("Helvetica", 10), fill=ch4_Color, anchor=NW)
Out_Inv_check_Value_4 = IntVar(Main_Window)
Out_Inv_check_4 = Checkbutton(Main_Window, variable=Out_Inv_check_Value_4, bg=bgcolor, relief="sunken", borderwidth=1)
Out_Inv_check_4.place(x=first_element_offset_x + outInvCheck_4_x + 4, y=first_element_offset_y + outInvCheck_4_y + 18)
Out_Inv_check_Value_4.set(0)

# Channel 5 widget positioning
outFreq_box_5_x = outFreq_box_4_x
outFreq_box_5_y = outFreq_box_4_y + 50
outCheck_5_x = outFreq_box_5_x - 50
outCheck_5_y = outFreq_box_5_y
OutDrive_pulld_5_x = outFreq_box_5_x + 200
OutDrive_pulld_5_y = outFreq_box_5_y + 14
outInvCheck_5_x = outCheck_5_x + 350
outInvCheck_5_y = outCheck_5_y
# Channel 5 Widgets
# Checkbox
canvas.create_text(first_element_offset_x + outCheck_5_x, first_element_offset_y + outCheck_5_y,
                   text="Enable", font=("Helvetica", 10), fill=ch5_Color, anchor=NW)
Out_check_Value_5 = IntVar(Main_Window)
Out_check_5 = Checkbutton(Main_Window, variable=Out_check_Value_5, bg=bgcolor, relief="sunken", borderwidth=1)
Out_check_5.place(x=first_element_offset_x + outCheck_5_x + 8, y=first_element_offset_y + outCheck_5_y + 18)
# Output Frequency
canvas.create_text(first_element_offset_x + outFreq_box_5_x, first_element_offset_y + outFreq_box_5_y,
                   text="Output 5 Frequency (Hz)", font=("Helvetica", 10), fill=ch5_Color, anchor=NW)
Out5_freq_Value = DoubleVar(Main_Window)
Out5_freq_Value.set(10000000)
Out5_freq = Entry(Main_Window, textvariable=Out5_freq_Value)
Out5_freq.config(width=13, relief="sunken", borderwidth=3)
Out5_freq.place(x=first_element_offset_x + outFreq_box_5_x + 18, y=first_element_offset_y + outFreq_box_5_y + 18)
# Drive pulldown menu
Pulldown5_Value = IntVar(Main_Window)
Pulldown5_Value.set(2)  # set the default option
Pulldown5 = OptionMenu(Main_Window, Pulldown5_Value, *drive_choices)
Pulldown5.place(x=first_element_offset_x + OutDrive_pulld_5_x, y=first_element_offset_y + OutDrive_pulld_5_y)
canvas.create_text(first_element_offset_x + OutDrive_pulld_5_x - 30, first_element_offset_y + OutDrive_pulld_5_y - 19,
                   text="Output 5 Drive (mA)", font=("Helvetica", 10), fill=ch5_Color, anchor=NW)
# Checkbox Invert
canvas.create_text(first_element_offset_x + outInvCheck_5_x, first_element_offset_y + outInvCheck_5_y,
                   text="Invert", font=("Helvetica", 10), fill=ch5_Color, anchor=NW)
Out_Inv_check_Value_5 = IntVar(Main_Window)
Out_Inv_check_5 = Checkbutton(Main_Window, variable=Out_Inv_check_Value_5, bg=bgcolor, relief="sunken", borderwidth=1)
Out_Inv_check_5.place(x=first_element_offset_x + outInvCheck_5_x + 4, y=first_element_offset_y + outInvCheck_5_y + 18)
Out_Inv_check_Value_5.set(0)

# Serial port entry box
canvas.create_text(first_element_offset_x + 68, first_element_offset_y + 402,
                   text="Serial Port", font=("Helvetica", 10), fill="blue", anchor=NW)
Serial_Port_Value = StringVar(Main_Window)
Serial_Port = Entry(Main_Window, textvariable=Serial_Port_Value)
Serial_Port.place(x=first_element_offset_x + 55, y=first_element_offset_y + 417)
if platform.system() == "Windows":
    Serial_Port_Value.set("COM1")              # Default Windows serial port
    Serial_Port.config(width=13, relief="sunken", borderwidth=3)
else:
    Serial_Port_Value.set("/dev/ttyUSB0")      # Default Linux serial port
    Serial_Port.config(width=10, relief="sunken", borderwidth=3)

# Buttons
# Transfer button
Transfer_Button_Label = StringVar()
Transfer_Button_Label.set("Transfer")
Transfer_Button = Button(Main_Window, textvariable=Transfer_Button_Label, width=10,
                         relief="raised", border=3, command=Transfer_Button_Toggle)
Transfer_Button.place(x=first_element_offset_x + 150, y=first_element_offset_y + 415)
# Exit button
Exit_Button_Label = StringVar()
Exit_Button_Label.set("Exit")
Exit_Button_Widget = Button(Main_Window, textvariable=Exit_Button_Label, width=10,
                            relief="raised", border=3, command=Exit_Button)
Exit_Button_Widget.place(x=first_element_offset_x + 550, y=first_element_offset_y + 415)
# About button
About_Button_Label = StringVar()
About_Button_Label.set("About...")
About_Button_Widget = Button(Main_Window, textvariable=About_Button_Label, width=10,
                             relief="raised", border=3, command=About_Button_Toggle)
About_Button_Widget.place(x=first_element_offset_x + 350, y=first_element_offset_y + 415)

# Serial Port definition
ser = serial.Serial()

# Window configuration and position retrieval
try:        # Tries to load the window configuration and position from a text file.
    with open(os.path.join(os.getcwd(), "saved_settings.cfg"), 'r') as f:
        Main_Window.geometry('%dx%d+%d+%d' % (Main_Window_Width_x, Main_Window_Width_y,
                                              int(f.readline()), int(f.readline())))
        Ref_Freq_Value.set(float(f.readline()))
        Ref_Freq_Corr_Value.set(float(f.readline()))
        if f.readline()[0:-1] == "1":
            Pulldown_Input_Source_Value.set("External Ref.")
        else:
            Pulldown_Input_Source_Value.set("Onboard Crystal")
        Out0_freq_Value.set(float(f.readline()))
        Out1_freq_Value.set(float(f.readline()))
        Out2_freq_Value.set(float(f.readline()))
        Out3_freq_Value.set(float(f.readline()))
        Out4_freq_Value.set(float(f.readline()))
        Out5_freq_Value.set(float(f.readline()))
        Out_check_Value_0.set(int(f.readline()))
        Out_check_Value_1.set(int(f.readline()))
        Out_check_Value_2.set(int(f.readline()))
        Out_check_Value_3.set(int(f.readline()))
        Out_check_Value_4.set(int(f.readline()))
        Out_check_Value_5.set(int(f.readline()))
        Out_Inv_check_Value_0.set(int(f.readline()))
        Out_Inv_check_Value_1.set(int(f.readline()))
        Out_Inv_check_Value_2.set(int(f.readline()))
        Out_Inv_check_Value_3.set(int(f.readline()))
        Out_Inv_check_Value_4.set(int(f.readline()))
        Out_Inv_check_Value_5.set(int(f.readline()))
        Pulldown0_Value.set(int(f.readline()))
        Pulldown1_Value.set(int(f.readline()))
        Pulldown2_Value.set(int(f.readline()))
        Pulldown3_Value.set(int(f.readline()))
        Pulldown4_Value.set(int(f.readline()))
        Pulldown5_Value.set(int(f.readline()))
        Serial_Port_Value.set(f.readline()[0:-1])
except (IOError, ValueError):
    ErrMsg("\nError! Software cannot retrieve its window settings. Reverting to default values...")

canvas.pack()  # Refreshes the canvas text

successMsg("Welcome to the Si5351A/B/C Synthesizer Configuration Software, by Bert-VE2ZAZ, "
           "Version 0.5, December 2019. http://ve2zaz.net")
successMsg("\nPlease note that the settings shown are retrieved from the last session, "
           "not from the ATmega processor EEPROM.")

# Calls the Exit function when the window "X" icon (upper-right corner) is clicked
Main_Window.protocol("WM_DELETE_WINDOW", Exit_Button)

# The script waits here in a loop for any action (button clicked)
Main_Window.mainloop()
