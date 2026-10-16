"""Full-UID reads through the MFRC522 (magicreader/mfrc522Uid.py).

The chip is not touched: transceive() is replaced with a fake tag that answers
the ISO 14443-3 frames, so the cascade logic is exercised on a laptop.
"""
import unittest

import _support  # noqa: F401
import mfrc522Uid
from mfrc522Uid import Mfrc522Uid, NoTag, ReadError, bcc, crcA

# Read identically by the MFRC522 and an ACS ACR1555U on the live reader.
MAGICBAND2_UID = bytes.fromhex("0453652AC05F80")
GENERIC_UID = bytes.fromhex("3611EE94")


class FakeTag:
    """Answers REQA, anticollision, SELECT and HLTA like an ISO 14443-A tag."""

    def __init__(self, uid, finalSak=0x00):
        self.uid = bytes(uid)
        self.finalSak = finalSak
        self.halted = False
        self.levels = {}
        if len(uid) == 4:
            chunks = [self.uid]
        elif len(uid) == 7:
            chunks = [b"\x88" + self.uid[:3], self.uid[3:7]]
        else:
            chunks = [b"\x88" + self.uid[:3], b"\x88" + self.uid[3:6], self.uid[6:10]]
        for i, chunk in enumerate(chunks):
            last = i == len(chunks) - 1
            self.levels[mfrc522Uid.PICC_SEL_CL[i]] = (chunk + bytes([bcc(chunk)]),
                                                     finalSak if last else 0x04)

    def transceive(self, data, txLastBits=0):
        data = bytes(data)
        if self.halted:
            raise NoTag()
        if data == bytes([mfrc522Uid.PICC_REQA]):
            return b"\x44\x00", 0
        if data[0] == mfrc522Uid.PICC_HLTA:
            self.halted = True
            raise NoTag()
        frame, sak = self.levels[data[0]]
        if data[1] == 0x20:
            return frame, 0
        if data[1] == 0x70 and data[2:7] == frame and data[7:] == crcA(data[:7]):
            return bytes([sak]) + crcA([sak]), 0
        raise AssertionError(f"unexpected frame {data.hex()}")


def readerFor(tag):
    reader = Mfrc522Uid.__new__(Mfrc522Uid)
    reader.transceive = tag.transceive
    reader.clearBits = lambda reg, mask: None
    return reader


class ChecksumTests(unittest.TestCase):
    def test_crc_a_matches_the_iso_14443_hlta_example(self):
        self.assertEqual(crcA([0x50, 0x00]), bytes([0x57, 0xCD]))

    def test_bcc_of_the_magicband_cl1_frame(self):
        self.assertEqual(bcc([0x88, 0x04, 0x53, 0x65]), 0xBA)


class ReadTagTests(unittest.TestCase):
    def test_seven_byte_uid_is_read_in_full(self):
        tag = FakeTag(MAGICBAND2_UID)
        read = readerFor(tag).readTag()
        self.assertEqual(read.uid, MAGICBAND2_UID)
        self.assertEqual(read.uidHex, "04 53 65 2A C0 5F 80")
        self.assertEqual(read.sak, 0x00)
        self.assertTrue(tag.halted)

    def test_four_byte_uid_is_read_in_full(self):
        read = readerFor(FakeTag(GENERIC_UID, finalSak=0x08)).readTag()
        self.assertEqual(read.uid, GENERIC_UID)
        self.assertEqual(read.sak, 0x08)

    def test_ten_byte_uid_is_read_in_full(self):
        uid = bytes.fromhex("0401020304050607080A")
        read = readerFor(FakeTag(uid, finalSak=0x20)).readTag()
        self.assertEqual(read.uid, uid)

    def test_halted_tag_is_not_read_again(self):
        reader = readerFor(FakeTag(MAGICBAND2_UID))
        reader.readTag()
        with self.assertRaises(NoTag):
            reader.readTag()

    def test_bad_bcc_is_a_read_error(self):
        tag = FakeTag(MAGICBAND2_UID)
        frame, sak = tag.levels[0x93]
        tag.levels[0x93] = (frame[:4] + bytes([frame[4] ^ 0xFF]), sak)
        with self.assertRaises(ReadError):
            readerFor(tag).readTag()


if __name__ == "__main__":
    unittest.main()
