#!/usr/bin/env python

import RPi.GPIO as GPIO
from mfrc522 import SimpleMFRC522
import time

print("Starting RFID test reader")

reader = SimpleMFRC522()

#while True:
try:
	print("Waiting for RFID...")
	id = reader.read_id()
	print(id)
	time.sleep(1)
	#print(text)
except:
	print("Error")
	#break

print("RFID test reader finished")

try:
	reader.READER.Close_MFRC522()
	GPIO.cleanup()
except:
	pass
