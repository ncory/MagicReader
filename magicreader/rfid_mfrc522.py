import rfid
from helpers import AppEvent, AppEventType, CancelReadException
from mfrc522 import SimpleMFRC522
from os import path
import RPi.GPIO as GPIO
import re
import spidev
import time
import datetime

class RfidMfrc522(rfid.RfidReader):
    SPI_BUS = 0
    SPI_DEVICE_NUMBER = 0
    SPI_DEVICE = '/dev/spidev0.0'
    GPIO_DEVICE = '/dev/gpiomem'
    RESET_PIN = 22
    VERSION_REG = 0x37
    STARTUP_TIMEOUT_SECONDS = 30
    VALID_VERSION_VALUES = {0x88, 0x90, 0x91, 0x92}

    def __init__(self, app, port:str = None):
        super().__init__(app, port)
        # Create RFID reader and fix logging level
        self.reader = SimpleMFRC522()
        self.reader.READER.logger.setLevel('CRITICAL')

    @classmethod
    def waitForMfrc522Hardware(cls):
        """Waits for the MFRC522 chip to respond over SPI."""
        required_devices = [cls.SPI_DEVICE, cls.GPIO_DEVICE]
        deadline = time.monotonic() + cls.STARTUP_TIMEOUT_SECONDS
        attempt = 1
        last_error = None
        last_version = None

        while time.monotonic() < deadline:
            missing_devices = [device for device in required_devices if not path.exists(device)]
            if missing_devices:
                last_error = f"missing device file(s): {', '.join(missing_devices)}"
                print(f"MFRC522 probe attempt {attempt}: {last_error}", flush=True)
                attempt += 1
                time.sleep(0.5)
                continue

            if not cls.resetMfrc522Hardware():
                last_error = "hardware reset failed"
                print(f"MFRC522 probe attempt {attempt}: {last_error}", flush=True)
                attempt += 1
                time.sleep(0.5)
                continue

            try:
                last_version = cls.readMfrc522VersionRegister()
                print(f"MFRC522 probe attempt {attempt}: VersionReg=0x{last_version:02x}", flush=True)
                if cls.isMfrc522VersionReady(last_version):
                    if last_version not in cls.VALID_VERSION_VALUES:
                        print(f"MFRC522 probe accepted unexpected VersionReg=0x{last_version:02x}", flush=True)
                    print("MFRC522 hardware ready", flush=True)
                    return True
                last_error = f"unexpected VersionReg=0x{last_version:02x}"
            except Exception as e:
                last_error = str(e)
                print(f"MFRC522 probe attempt {attempt}: {last_error}", flush=True)

            attempt += 1
            time.sleep(0.25)

        if last_version is not None:
            print(f"ERROR: MFRC522 hardware was not ready; last VersionReg=0x{last_version:02x}", flush=True)
        else:
            print(f"ERROR: MFRC522 hardware was not ready; {last_error}", flush=True)
        return False

    @classmethod
    def resetMfrc522Hardware(cls):
        current_mode = GPIO.getmode()
        if current_mode is None:
            GPIO.setmode(GPIO.BOARD)
        elif current_mode != GPIO.BOARD:
            print("ERROR: GPIO pin mode already differs from BOARD numbering", flush=True)
            return False

        GPIO.setwarnings(False)
        GPIO.setup(cls.RESET_PIN, GPIO.OUT)
        GPIO.output(cls.RESET_PIN, GPIO.LOW)
        time.sleep(0.05)
        GPIO.output(cls.RESET_PIN, GPIO.HIGH)
        time.sleep(0.1)
        return True

    @classmethod
    def readMfrc522VersionRegister(cls):
        spi = spidev.SpiDev()
        try:
            spi.open(cls.SPI_BUS, cls.SPI_DEVICE_NUMBER)
            spi.max_speed_hz = 1000000
            read_command = ((cls.VERSION_REG << 1) & 0x7E) | 0x80
            return spi.xfer2([read_command, 0])[1]
        finally:
            spi.close()

    @staticmethod
    def isMfrc522VersionReady(version):
        return version not in [None, 0x00, 0xff]

    def runReaderThread(self):
        print("Starting RFID read thread", flush=True)
        while self.app.is_active:
            # Perform RFID read
            print("RFID:: Waiting for RFID....", flush=True)
            id = None
            try:
                id = self.reader.read_id()
                if id is None:
                    continue
                # How long since last read?
                now = datetime.datetime.now()
                diff = now - self.lastReadTime
                if (diff > self.timeDelta):
                    # Enough time has passed, allow read
                    print(f"RFID:: Read RFID: {id}", flush=True)
                    # Pass to event queue
                    read = rfid.RfidRead(id, self.isDisneyBand(id))
                    event = AppEvent(AppEventType.ReadRfid, read)
                    self.app.event_queue.put((5, event))
                    # Update last read time
                    self.lastReadTime = now
            except CancelReadException:
                print("RFID:: Got CancelReadException!!", flush=True)
                return
            except Exception as e:
                if not self.app.is_active:
                    return
                print("RFID:: Error reading RFID", flush=True)
                print (e, flush=True)
    
    def stop(self):
        self.reader.READER.Close_MFRC522()
    
    REGEX_MAGICBAND = re.compile("5841[0-9]+")
    #REGEX_MAGICBAND = re.compile("04[0-9a-zA-Z]+80")
    REGEX_MAGICBAND_PLUS = re.compile("04[0-9a-zA-Z]+90")

    def isDisneyBand(self, id:str) -> bool:
        if not isinstance(id, str):
            id = str(id)
        if RfidMfrc522.isIdMagicBandOrMagicBand2(id):
            return True
        elif RfidMfrc522.isIdMagicBandOrMagicBand2(id):
            return True
        return False

    @staticmethod
    def isIdMagicBandOrMagicBand2(id: str) -> bool:
        if not isinstance(id, str):
            id = str(id)
        # Run RegEx on id
        if RfidMfrc522.REGEX_MAGICBAND.match(id):
            return True
        return False
    
    @staticmethod
    def isIdMagicBandPlus(id: str) -> bool:
        if not isinstance(id, str):
            id = str(id)
        # Run RegEx on id
        if RfidMfrc522.REGEX_MAGICBAND_PLUS.match(id):
            return True
        return False
