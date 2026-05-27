/*
   _===_ _           _                  ______ _     _             _ _ _
  |  ___| |         | |                 | ___ (_)   | |           (_) | |
  | |__ | | ___  ___| |_ _ __ ___ ______| |_/ /_  __| | ___  _   _ _| | | ___ _   _ _ __
  |  __|| |/ _ \/ __| __| '__/ _ \______| ___ \ |/ _` |/ _ \| | | | | | |/ _ \ | | | '__|
  | |___| |  __/ (__| |_| | | (_) |     | |_/ / | (_| | (_) | |_| | | | |  __/ |_| | |
  \____/|_|\___|\___|\__|_|  \___/      \____/|_|\__,_|\___/ \__,_|_|_|_|\___|\__,_|_|

Si5351 Synthesizer Control/Configuration
Designed to run on an Arduino Nano (or LGT8F328P clone)
Electro-Bidouilleur - July 2019
*/

#include "si5351.h"
#include "Wire.h"
#include <string.h>
#include <EEPROM.h>
#include <stdlib.h>

// Constants
#define PLL_LED 11    // Si5351 PLL status LED pin

Si5351 si5351;

// Global variables
char commande;
char RxChar;
char RxStr[300]= "";
int ctr =0;
int commandCtr = 0;
char TempChar;
int TempInt;
String TempStr;
unsigned long long param1;
unsigned long long param2;
unsigned long long param3;


// Converts a String to an unsigned 64-bit integer.
unsigned long long convert_str_to_ULL(String InString)
{
unsigned long long  OutULL = 0;
  for (int i = 0; i < InString.length(); i++)
  {
    char c = InString.charAt(i);
    if (c < '0' || c > '9') break;
    OutULL *= 10;
    OutULL += (c - '0');
  }
  return OutULL;
}

// Converts a String to an unsigned byte integer.
unsigned char convert_str_to_int(String InString)
{
unsigned char  OutInt = 0;
  for (int i = 0; i < InString.length(); i++)
  {
    char c = InString.charAt(i);
    if (c < '0' || c > '9') break;
    OutInt *= 10;
    OutInt += (c - '0');
  }
  return OutInt;
}

// Writes the received parameter string from RAM to EEPROM.
void Write_RxString_to_EEPROM(int length)
{
  for (ctr=0;ctr < length;ctr++)
  {
    EEPROM.write(ctr,RxStr[ctr]);
  }
}

// Reads and parses the three parameters following a command from EEPROM.
void parse_params_from_EEPROM()
{
  TempStr = "";
  while (1)
  {   // First parameter
    TempChar = char(EEPROM.read(ctr));
    ctr++;
    if (TempChar != '|' && TempChar != ',') TempStr = TempStr + TempChar;
    else    // Field separator detected
    {
      param1 = convert_str_to_ULL(TempStr);   // Convert to unsigned 64-bit integer
      break;    // Exit loop
    }
  }
  TempStr = "";
  while (TempChar != '|')
  {   // Second parameter
    TempChar = char(EEPROM.read(ctr));
    ctr++;
    if (TempChar != '|' && TempChar != ',') TempStr = TempStr + TempChar;
    else     // Field separator detected
    {
      param2 = convert_str_to_ULL(TempStr);   // Convert to unsigned 64-bit integer
      break;    // Exit loop
    }
  }

  TempStr = "";
  while (TempChar != '|')
  {   // Third parameter
    TempChar = char(EEPROM.read(ctr));
    ctr++;
    if (TempChar != '|' && TempChar != ',') TempStr = TempStr + TempChar;
    else     // Field separator detected
    {
      param3 = convert_str_to_ULL(TempStr);   // Convert to unsigned 64-bit integer
      break;    // Exit loop
    }
  }
}

// Sends the formatted configuration from EEPROM to the Si5351.
void Send_Commands_From_EEPROM_to_Si5351()
{
  ctr = 1;    // Skip the '$' at EEPROM position 0
  while (1)
  {
    TempChar = char(EEPROM.read(ctr));  // Read the command character
    if (TempChar == '%') break;         // End of command string — stop
    ctr = ctr + 2;                      // Skip the comma separator
    commande = TempChar;
    parse_params_from_EEPROM();         // Parse command parameters

    if (commande == '1')                // INIT command
    {
      si5351.init(param1, param2, param3);
    }
    else if (commande == '2')           // SET_PLL_INPUT command
    {
      si5351.set_pll_input(param1, param2);
    }
    else if (commande == '3')           // SET_REF_FREQ command
    {
      si5351.set_ref_freq(param1, param2);
    }
    else if (commande == '4')           // SET_CORRECTION command
    {
      si5351.set_correction(param1, param2);
    }
    else if (commande == '5')           // SET_FREQ command
    {
      si5351.set_freq(param1, param2);
    }
    else if (commande == '6')           // OUTPUT_ENABLE command
    {
      si5351.output_enable(param1, param2);
    }
    else if (commande == '7')           // DRIVE_STRENGTH command
    {
      si5351.drive_strength(param1, param2);
    }
    else if (commande == '8')           // SET_CLOCK_INVERT command
    {
      si5351.set_clock_invert(param1, param2);
    }
    else if (commande == '9')           // PLL_RESET command
    {
      si5351.pll_reset(param1);
    }
  }
}

// Sends raw register data from EEPROM to the Si5351.
void Send_RawData_From_EEPROM_to_Si5351()
{
unsigned char address_5351;
unsigned char data_5351;

  ctr = 1;    // Skip the '@' marker
  TempStr = "";
  while (1)
  {
    TempChar = char(EEPROM.read(ctr));
    if (TempChar == '%') break;         // End of command string — stop
    ctr++;
    if (TempChar != ',' && TempChar != ';' && TempChar != '\n') TempStr = TempStr + TempChar;
    else if (TempChar == ',')
    {
      address_5351 = convert_str_to_int(TempStr);
      TempStr = "";
    }
    else if (TempChar == ';')           // Semicolon delimiter — write the register
    {
      data_5351 = convert_str_to_int(TempStr);
      TempStr = "";
      Si5351_write(address_5351,data_5351);
      delay(100);
    }
  }
}

// Reads a Si5351 register. Required because the library's si5351_read() causes
// unwanted address auto-increment.
unsigned char Si5351_read(unsigned char addr)
{
  Wire.begin();
  Wire.beginTransmission(SI5351_BUS_BASE_ADDR);
  Wire.write(addr);
  Wire.endTransmission();
  Wire.requestFrom(SI5351_BUS_BASE_ADDR, 1, true);
  return Wire.read();
}

// Writes a Si5351 register.
unsigned char Si5351_write(unsigned char addr, unsigned char data)
{
  Wire.begin();
  Wire.beginTransmission(SI5351_BUS_BASE_ADDR);
  Wire.write(addr);
  Wire.write(data);
  return Wire.endTransmission();
}

void setup()
{
  TempStr.reserve(20);              // Reserve string buffer
  Serial.begin(2400);               // Open USB serial port at 2400 bps
  pinMode(PLL_LED, OUTPUT);         // Configure PLL status LED pin

  // Reload Si5351 configuration from EEPROM at power-up
  TempChar = char(EEPROM.read(0));
  if (TempChar == '$') Send_Commands_From_EEPROM_to_Si5351();   // Formatted config
  else if (TempChar == '@') Send_RawData_From_EEPROM_to_Si5351(); // Raw register config
  Serial.print("R");                // Notify PC that the Arduino reset is complete
  delay(500);                       // 500 ms pause
}

// Main Arduino loop: receives configuration from the PC and monitors PLL lock status.
void loop()
{
  bool rawData;     // Flag: true if incoming data is in raw register format
  if (Serial.available()>0)         // Characters available in the serial receive buffer?
  {
    RxChar = Serial.read();         // Read one character
    if (RxChar == '?')              // Read-back request: dump EEPROM config to host
    {
      char firstByte = char(EEPROM.read(0));
      if (firstByte == '$' || firstByte == '@') {
        for (int i = 0; i < (int)EEPROM.length(); i++) {
          char c = char(EEPROM.read(i));
          Serial.print(c);
          if (c == '%') break;
        }
      } else {
        Serial.print('!');          // No valid config stored yet
      }
    }
    else if (RxChar == '$' || RxChar == '@')  // Start-of-parameters character?
    {
      rawData = false;
      if (RxChar == '@') rawData = true;  // Raw format marker — set the raw flag
      RxStr[0] = RxChar;            // Store the first character
      ctr = 1;
      while (RxChar != '%')         // Keep reading until end-of-parameters '%'
      {
        if (Serial.available()>0)   // Characters available in the Rx buffer?
        {
          RxChar = Serial.read();   // Read the character
          RxStr[ctr] = RxChar;      // Store it in the RAM buffer
          ctr++;                    // Increment the counter
        }
      }
      Serial.print("O");            // Notify PC: parameters received

      // Save commands and parameters to EEPROM
      Write_RxString_to_EEPROM(ctr);
      Serial.print("E");            // Notify PC: saved to EEPROM

      // Apply parameters from EEPROM to Si5351
      if (rawData) Send_RawData_From_EEPROM_to_Si5351();  // Raw register config
      else Send_Commands_From_EEPROM_to_Si5351();          // Formatted config
      Serial.println("S");          // Notify PC: configuration applied to Si5351
    }
  }
  // Update PLL status LED. Read status register directly
  // (library status functions do not behave reliably).
  // LOL (Loss of Lock) bit is more stable than LOS (Loss of Signal).
  digitalWrite(PLL_LED,!((si5351.si5351_read(0) & 0b00100000)>>5));
}
