#!/usr/bin/env python

import time
import RPi.GPIO as GPIO
from mfrc522 import SimpleMFRC522
import logging

# Create reader and fix logging level
reader = SimpleMFRC522()
reader.READER.logger.setLevel('CRITICAL')

print("Waiting for RFID....", flush=True)
try:
    id, text = reader.read()
    print(f"Read ID: {id}", flush=True)
    # Sleep to wait
    time.sleep(1)
except:
    print("Error")

# Do cleanup
try:
	reader.READER.Close_MFRC522()
	GPIO.cleanup()
except:
	pass
