import rfid
from helpers import AppEvent, AppEventType, CancelReadException
from mfrc522Uid import Mfrc522Uid, NoTag, ReadError
from os import path
import RPi.GPIO as GPIO
import gpioBackend
import spidev
import time
import datetime

class RfidMfrc522(rfid.RfidReader):
    SPI_BUS = 0
    SPI_DEVICE_NUMBER = 0
    SPI_DEVICE = '/dev/spidev0.0'
    RESET_PIN = 22
    VERSION_REG = 0x37
    STARTUP_TIMEOUT_SECONDS = 30
    VALID_VERSION_VALUES = {0x88, 0x90, 0x91, 0x92}
    POLL_INTERVAL_SECONDS = 0.05

    def __init__(self, app, port:str = None):
        super().__init__(app, port)
        # waitForMfrc522Hardware() has already pulsed the reset line, so the
        # reader is opened without touching it again.
        self.reader = Mfrc522Uid(self.SPI_BUS, self.SPI_DEVICE_NUMBER)

    @classmethod
    def waitForMfrc522Hardware(cls):
        """Waits for the MFRC522 chip to respond over SPI."""
        print(gpioBackend.describe(), flush=True)
        deadline = time.monotonic() + cls.STARTUP_TIMEOUT_SECONDS
        attempt = 1
        last_error = None
        last_version = None

        while time.monotonic() < deadline:
            # Which GPIO device to expect depends on the installed backend:
            # /dev/gpiomem for the classic RPi.GPIO, a gpiochip character
            # device for rpi-lgpio. Hardcoding /dev/gpiomem meant this probe
            # timed out on Trixie and on the Pi 5, where it does not exist.
            missing_devices = []
            if not path.exists(cls.SPI_DEVICE):
                missing_devices.append(cls.SPI_DEVICE)
            if gpioBackend.findGpioDevice() is None:
                missing_devices.append(
                    " or ".join(gpioBackend.requiredGpioDevices())
                )
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
        print("RFID:: Waiting for RFID....", flush=True)
        while self.app.is_active:
            try:
                # readTag() halts the band once it has been read, so one tap
                # gives one read however long the band is held there.
                tag = self.reader.readTag()
            except (NoTag, ReadError):
                # NoTag is an empty field. ReadError is usually a band at the
                # edge of the field answering only part of the exchange; the
                # next poll normally reads it cleanly.
                time.sleep(self.POLL_INTERVAL_SECONDS)
                continue
            except CancelReadException:
                print("RFID:: Got CancelReadException!!", flush=True)
                return
            except Exception as e:
                if not self.app.is_active:
                    return
                print("RFID:: Error reading RFID", flush=True)
                print (e, flush=True)
                time.sleep(self.POLL_INTERVAL_SECONDS)
                continue

            id = tag.uid.hex().upper()
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
                print("RFID:: Waiting for RFID....", flush=True)

    def stop(self):
        self.reader.close()

    # Band IDs are the tag's full UID as uppercase hex, e.g. "0453652AC05F80".
    # Every MagicBand has a 7-byte NXP UID - first byte 0x04, NXP's
    # manufacturer code - ending in 0x80 on a MagicBand 2 and 0x90 on a
    # MagicBand+.
    NXP_MANUFACTURER_CODE = 0x04
    MAGICBAND_PLUS_LAST_BYTE = 0x90

    @staticmethod
    def uidFromId(id) -> bytes | None:
        try:
            return bytes.fromhex(id)
        except (TypeError, ValueError):
            return None

    def isDisneyBand(self, id) -> bool:
        """True for a 7-byte NXP UID.

        Note this identifies the tag family, not Disney specifically: any
        7-byte NXP tag (NTAG, MIFARE Ultralight, DESFire) passes too.
        """
        uid = RfidMfrc522.uidFromId(id)
        return uid is not None and len(uid) == 7 and uid[0] == RfidMfrc522.NXP_MANUFACTURER_CODE

    @staticmethod
    def isIdMagicBandPlus(id) -> bool:
        uid = RfidMfrc522.uidFromId(id)
        return (uid is not None and len(uid) == 7
                and uid[0] == RfidMfrc522.NXP_MANUFACTURER_CODE
                and uid[-1] == RfidMfrc522.MAGICBAND_PLUS_LAST_BYTE)
