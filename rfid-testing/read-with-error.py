#!/usr/bin/env python

import time
import RPi.GPIO as GPIO
from mfrc522 import SimpleMFRC522
import logging
import signal

# Configure SIGTERM handler
def signal_term_handler(sigNum, frame):
    # on receiving a signal initiate a normal exit
    raise SystemExit('Got SIGTERM')

# Register the SIGTERM handler
signal.signal(signal.SIGTERM, signal_term_handler)

print("Starting RFID read test script", flush=True)

# Create reader and fix logging level
reader = SimpleMFRC522()
reader.READER.logger.setLevel('CRITICAL')

try:
        while True:
                print("Waiting for RFID....", flush=True)
                # Do low-level read with status
                (status, TagType) = reader.READER.MFRC522_Request(reader.READER.PICC_REQIDL)
                if status == reader.READER.MI_OK:
                        print("Reader status: OK", flush=True)
                        # Now actually read
                        (status, uid) = reader.READER.MFRC522_Anticoll()
                        if status == reader.READER.MI_OK:
                                id = reader.uid_to_num(uid)
                                print(f"Read ID: {id}", flush=True)
                elif status == reader.READER.MI_NOTAGERR:
                        print("Reader status: NO TAG", flush=True)
                elif status == reader.READER.MI_ERR:
                        print("Reader status: ERROR", flush=True)
                else:
                        print("Reader status: Unknown", flush=True)
                # Sleep to wait
                time.sleep(1)
                print("Finished while loop", flush=True)
except KeyboardInterrupt:
        print("Keyboard interrupt", flush=True)
except SystemExit:
        print("Caught SystemExit (SIGTERM) exception", flush=True)
except:
        print("Error")

print("Finishing RFID read test script", flush=True)

# Do cleanup
try:
        reader.READER.Close_MFRC522()
        #GPIO.cleanup()
        pass
except:
        pass

