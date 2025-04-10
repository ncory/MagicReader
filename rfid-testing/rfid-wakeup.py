#!/usr/bin/env python

#import time
import RPi.GPIO as GPIO
from mfrc522 import SimpleMFRC522
#import logging

# Create reader and fix logging level
reader = SimpleMFRC522()
reader.READER.logger.setLevel('CRITICAL')

print("Waking up RFID by calling read_id_no_block()", flush=True)
try:
    id = reader.read_id_no_block()
    #print(f"Read ID: {id}", flush=True)
except:
    print("Error", flush=True)

# Do cleanup
try:
	reader.READER.Close_MFRC522()
	GPIO.cleanup()
except:
	pass

print("Finished RFID wakeup")
