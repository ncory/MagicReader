import rfid
from helpers import AppEvent, AppEventType, CancelReadException
from mfrc522 import SimpleMFRC522
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

    def __init__(self, app, port:str = None):
        super().__init__(app, port)
        # Create RFID reader and fix logging level
        self.reader = SimpleMFRC522()
        self.reader.READER.logger.setLevel('CRITICAL')

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
    
    # SimpleMFRC522.read_id() runs a single anticollision cascade and packs the
    # five bytes it gets back into one integer: the cascade tag (0x88), the
    # first three UID bytes, and the BCC checksum. For any 7-byte NXP tag -
    # which every MagicBand is - those bytes are 0x88, 0x04, then the UID, so
    # the value always falls in 0x8804000000..0x8804FFFFFF. That is 584182661120
    # to 584199438335 in decimal, which is where the old "5841" prefix came from.
    UID_CASCADE_NXP_MIN = 0x8804000000
    UID_CASCADE_NXP_MAX = 0x8804FFFFFF

    def isDisneyBand(self, id) -> bool:
        # Only one test is possible here - see isIdMagicBandPlus() for why
        # MagicBand+ cannot be told apart from a MagicBand 2 at this layer.
        return RfidMfrc522.isIdMagicBandOrMagicBand2(id)

    @staticmethod
    def isIdMagicBandOrMagicBand2(id) -> bool:
        """True if the id looks like a 7-byte NXP UID read at cascade level 1.

        Note this identifies the tag family, not Disney specifically: any
        7-byte NXP tag (NTAG, MIFARE Ultralight) lands in the same range.
        """
        try:
            value = int(id)
        except (TypeError, ValueError):
            return False
        return RfidMfrc522.UID_CASCADE_NXP_MIN <= value <= RfidMfrc522.UID_CASCADE_NXP_MAX

    @staticmethod
    def isIdMagicBandPlus(id) -> bool:
        """Always False - MagicBand+ cannot be detected with this reader setup.

        A MagicBand+ is distinguished from a MagicBand 2 by the last byte of
        its full 7-byte UID (0x90 rather than 0x80). read_id() only performs
        cascade level 1, so it never sees bytes 3-6 and that byte is simply not
        available. Telling them apart would need a second cascade level, which
        the mfrc522 library's MFRC522_Anticoll() does not implement.

        Kept as a named no-op so the intent is documented rather than looking
        like an oversight. The previous implementation matched
        "04[0-9a-zA-Z]+90" against the decimal id, which could never match:
        str(int) never starts with a zero.
        """
        return False
