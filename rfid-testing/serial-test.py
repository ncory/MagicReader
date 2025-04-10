import serial


try:
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
        # Convert to string
        line = line.decode('utf-8').strip()
        # Print read line
        print(f"Read RFID: {line}")

except KeyboardInterrupt:
    print("Caught keyboard interrupt...exiting")

except Exception as e:
    print(f"Error: {e}")

finally:
    # Close the serial port
    ser.close()
