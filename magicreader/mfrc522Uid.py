"""Reads the complete UID of an ISO 14443-A tag through an MFRC522 over SPI.

The mfrc522 package's SimpleMFRC522.read_id() stops after the first
anticollision cascade level and returns the five bytes it got back - for a
7-byte tag that is the cascade tag 0x88, the first three UID bytes and a BCC
checksum, so four of the seven UID bytes are never read. Every MagicBand has a
7-byte UID.

This module runs the full ISO 14443-3 sequence instead: REQA, then
anticollision + SELECT at cascade level 1, 2 and 3 for as long as the tag's SAK
says the UID is not complete, then HLTA so the tag stays quiet until it leaves
the field. It talks to the chip directly with spidev and does not use the
mfrc522 package at all.
"""
import time
from dataclasses import dataclass

import spidev

# Registers (MFRC522 datasheet, section 9)
CommandReg = 0x01
ComIrqReg = 0x04
DivIrqReg = 0x05
ErrorReg = 0x06
FIFODataReg = 0x09
FIFOLevelReg = 0x0A
ControlReg = 0x0C
BitFramingReg = 0x0D
CollReg = 0x0E
ModeReg = 0x11
TxControlReg = 0x14
TxASKReg = 0x15
RFCfgReg = 0x26
TModeReg = 0x2A
TPrescalerReg = 0x2B
TReloadRegH = 0x2C
TReloadRegL = 0x2D
VersionReg = 0x37

# Chip commands
CMD_IDLE = 0x00
CMD_TRANSCEIVE = 0x0C
CMD_SOFT_RESET = 0x0F

# ISO 14443-3 commands
PICC_REQA = 0x26
PICC_HLTA = 0x50
PICC_CASCADE_TAG = 0x88
PICC_SEL_CL = (0x93, 0x95, 0x97)

SAK_UID_NOT_COMPLETE = 0x04

# RxGain field of RFCfgReg, in dB. 33 is the chip's reset value.
RX_GAIN_DB = {18: 0x00, 23: 0x10, 33: 0x40, 38: 0x50, 43: 0x60, 48: 0x70}


class NoTag(Exception):
    """Nothing answered - the normal result of polling an empty field."""


class ReadError(Exception):
    """A tag answered but the exchange failed (weak coupling, collision...)."""


@dataclass
class TagRead:
    uid: bytes
    atqa: bytes
    sak: int

    @property
    def uidHex(self) -> str:
        return self.uid.hex(" ").upper()


def crcA(data) -> bytes:
    """ISO 14443-A CRC_A (initial value 0x6363), low byte first."""
    crc = 0x6363
    for b in data:
        b = (b ^ (crc & 0xFF)) & 0xFF
        b = (b ^ (b << 4)) & 0xFF
        crc = ((crc >> 8) ^ (b << 8) ^ (b << 3) ^ (b >> 4)) & 0xFFFF
    return bytes([crc & 0xFF, crc >> 8])


def bcc(data) -> int:
    out = 0
    for b in data:
        out ^= b
    return out


def describeSak(sak: int) -> str:
    """A rough tag-family hint from SAK. Not authoritative."""
    if sak & SAK_UID_NOT_COMPLETE:
        return "UID incomplete"
    return {
        0x00: "MIFARE Ultralight / NTAG (Type 2)",
        0x08: "MIFARE Classic 1K",
        0x09: "MIFARE Mini",
        0x18: "MIFARE Classic 4K",
        0x10: "MIFARE Plus 2K",
        0x11: "MIFARE Plus 4K",
        0x20: "ISO 14443-4 (DESFire, etc.)",
        0x28: "MIFARE Classic 1K + ISO 14443-4",
        0x38: "MIFARE Classic 4K + ISO 14443-4",
    }.get(sak, f"unknown (SAK 0x{sak:02X})")


class Mfrc522Uid:
    TIMEOUT_SECONDS = 0.05

    def __init__(self, bus=0, device=0, speedHz=1000000, resetPin=None, rxGainDb=None):
        """resetPin is a BOARD pin number driven by RPi.GPIO; None leaves the
        reset line alone (the caller has already brought the chip up)."""
        self.resetPin = resetPin
        if resetPin is not None:
            import RPi.GPIO as GPIO
            if GPIO.getmode() is None:
                GPIO.setmode(GPIO.BOARD)
            GPIO.setwarnings(False)
            GPIO.setup(resetPin, GPIO.OUT)
            GPIO.output(resetPin, GPIO.LOW)
            time.sleep(0.05)
            GPIO.output(resetPin, GPIO.HIGH)
            time.sleep(0.05)

        self.spi = spidev.SpiDev()
        self.spi.open(bus, device)
        self.spi.max_speed_hz = speedHz
        self.spi.mode = 0
        self.init(rxGainDb)

    # --- register access ----------------------------------------------------

    def write(self, reg, value):
        self.spi.xfer2([(reg << 1) & 0x7E, value])

    def writeMany(self, reg, values):
        # The chip keeps writing to the same address for every byte that
        # follows the address byte, which is how the FIFO is filled.
        self.spi.xfer2([(reg << 1) & 0x7E] + list(values))

    def read(self, reg):
        return self.spi.xfer2([((reg << 1) & 0x7E) | 0x80, 0])[1]

    def readMany(self, reg, count):
        if count <= 0:
            return b""
        addr = ((reg << 1) & 0x7E) | 0x80
        return bytes(self.spi.xfer2([addr] * count + [0])[1:])

    def setBits(self, reg, mask):
        self.write(reg, self.read(reg) | mask)

    def clearBits(self, reg, mask):
        self.write(reg, self.read(reg) & ~mask & 0xFF)

    # --- chip setup ---------------------------------------------------------

    def version(self) -> int:
        return self.read(VersionReg)

    def init(self, rxGainDb=None):
        self.write(CommandReg, CMD_SOFT_RESET)
        deadline = time.monotonic() + 0.15
        # PowerDown (bit 4) clears once the oscillator is running again.
        while self.read(CommandReg) & 0x10 and time.monotonic() < deadline:
            time.sleep(0.001)

        # Same timer and modulation settings the mfrc522 package uses: the
        # timer starts at the end of each transmission and fires after ~15 ms,
        # which is what ends a transceive when no tag answers.
        self.write(TModeReg, 0x8D)
        self.write(TPrescalerReg, 0x3E)
        self.write(TReloadRegL, 30)
        self.write(TReloadRegH, 0)
        self.write(TxASKReg, 0x40)  # force 100% ASK
        self.write(ModeReg, 0x3D)   # CRC preset 0x6363
        if rxGainDb is not None:
            if rxGainDb not in RX_GAIN_DB:
                raise ValueError(f"rxGainDb must be one of {sorted(RX_GAIN_DB)}")
            self.write(RFCfgReg, (self.read(RFCfgReg) & 0x8F) | RX_GAIN_DB[rxGainDb])
        self.antennaOn()

    def antennaOn(self):
        if (self.read(TxControlReg) & 0x03) != 0x03:
            self.setBits(TxControlReg, 0x03)

    def antennaOff(self):
        self.clearBits(TxControlReg, 0x03)

    def close(self):
        try:
            self.antennaOff()
        finally:
            self.spi.close()

    # --- ISO 14443-3 --------------------------------------------------------

    def transceive(self, data, txLastBits=0):
        """Sends a frame and returns (bytes, validBitsInLastByte).

        validBits is 0 when the last byte is complete. Raises NoTag on timeout
        and ReadError on a reception error.
        """
        self.write(CommandReg, CMD_IDLE)
        self.write(ComIrqReg, 0x7F)      # clear every interrupt request bit
        self.write(FIFOLevelReg, 0x80)   # flush the FIFO
        self.writeMany(FIFODataReg, data)
        self.write(BitFramingReg, txLastBits & 0x07)
        self.write(CommandReg, CMD_TRANSCEIVE)
        self.setBits(BitFramingReg, 0x80)  # StartSend

        deadline = time.monotonic() + self.TIMEOUT_SECONDS
        while True:
            irq = self.read(ComIrqReg)
            if irq & 0x30:   # RxIRq or IdleIRq: the exchange finished
                break
            if irq & 0x01:   # TimerIRq: nothing answered in time
                raise NoTag()
            if time.monotonic() > deadline:
                raise NoTag()
            # Polling an empty field means waiting out the whole ~15 ms
            # timeout on every pass; spinning on SPI for it held a quarter of
            # a Pi 4 core. A tag answers within a millisecond, so this costs a
            # read almost nothing.
            time.sleep(0.0005)
        self.clearBits(BitFramingReg, 0x80)

        error = self.read(ErrorReg)
        if error & 0x13:     # BufferOvfl, ParityErr, ProtocolErr
            raise ReadError(f"ErrorReg=0x{error:02X}")
        if error & 0x08:     # CollErr: more than one tag answered
            raise ReadError("collision - more than one tag in the field?")

        count = self.read(FIFOLevelReg)
        received = self.readMany(FIFODataReg, count)
        validBits = self.read(ControlReg) & 0x07
        return received, validBits

    def transceiveWithCrc(self, data):
        payload = bytes(data)
        received, _ = self.transceive(payload + crcA(payload))
        if len(received) < 3:
            raise ReadError(f"short reply {received.hex()}")
        if crcA(received[:-2]) != received[-2:]:
            raise ReadError(f"bad CRC on reply {received.hex()}")
        return received[:-2]

    def requestA(self) -> bytes:
        # Collisions on ATQA are normal with several tags; keep the bits.
        self.clearBits(CollReg, 0x80)
        atqa, validBits = self.transceive([PICC_REQA], txLastBits=7)
        if len(atqa) != 2 or validBits != 0:
            raise ReadError(f"bad ATQA {atqa.hex()} ({validBits} bits)")
        return atqa

    def haltA(self):
        try:
            self.transceive(bytes([PICC_HLTA, 0x00]) + crcA([PICC_HLTA, 0x00]))
        except NoTag:
            return  # a halted tag does not answer; that is success
        raise ReadError("tag answered HLTA")

    def readTag(self, halt=True) -> TagRead:
        """Reads the full UID of the tag in the field.

        Raises NoTag when the field is empty (or every tag in it is halted)
        and ReadError when a tag answered but the read did not complete.
        """
        atqa = self.requestA()
        uid = b""
        sak = None
        for level, sel in enumerate(PICC_SEL_CL, start=1):
            self.clearBits(CollReg, 0x80)
            frame, validBits = self.transceive([sel, 0x20])
            if len(frame) != 5 or validBits != 0:
                raise ReadError(f"CL{level} anticollision returned {frame.hex()}")
            if bcc(frame[:4]) != frame[4]:
                raise ReadError(f"CL{level} BCC mismatch in {frame.hex()}")

            reply = self.transceiveWithCrc(bytes([sel, 0x70]) + frame)
            if len(reply) != 1:
                raise ReadError(f"CL{level} SAK reply {reply.hex()}")
            sak = reply[0]

            if sak & SAK_UID_NOT_COMPLETE:
                if frame[0] != PICC_CASCADE_TAG:
                    raise ReadError(f"CL{level} SAK says more follows but no cascade tag")
                uid += frame[1:4]
            else:
                uid += frame[0:4]
                break
        else:
            raise ReadError("UID still incomplete after cascade level 3")

        if halt:
            self.haltA()
        return TagRead(uid=uid, atqa=atqa, sak=sak)
