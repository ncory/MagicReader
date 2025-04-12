import serial
from serial.tools import list_ports

from bandManager import BandManager

try:
    # Create band manager
    band_manager = BandManager()

    print("Available serial ports:")
    port = list(list_ports.comports())
    for p in port:
        print(f"\t{p.device}")

    # open serial port
    print("Opening serial port...")
    ser = serial.Serial('/dev/ttyUSB0')

    # Print name
    print(f"Opened serial port: {ser.name}")

    # While loop
    while True:
        print("Waiting for RFID read...")
        # Read to next line
        line = ser.readline()
        print(f"Read data: {line}")
        # Convert to ASCII
        ascii = line.decode('ascii').strip()
        print(f"\tASCII: {ascii}")
        # Convert to UTF-8
        utf8 = line.decode('utf-8').strip()
        print(f"\tUTF-8: {utf8}")
        # Does it match as a Disney band?
        if (band_manager.isIdDisneyBand(utf8)):
            print("\tIs a Disney band")

except KeyboardInterrupt:
    print("Caught keyboard interrupt...exiting")

except Exception as e:
    print(f"Error: {e}")

finally:
    # Close the serial port
    ser.close()
