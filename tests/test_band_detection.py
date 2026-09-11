"""Disney band detection from an MFRC522 read.

SimpleMFRC522.read_id() runs one anticollision cascade and packs five bytes
into an integer: the cascade tag (0x88), the first three UID bytes, and the
BCC. For any 7-byte NXP tag those first two bytes are 0x88 0x04, so the value
always lands in 0x8804000000..0x8804FFFFFF - which is what the old "5841"
decimal prefix was really matching.
"""
import unittest

import _support  # noqa: F401
from rfid_mfrc522 import RfidMfrc522

# From data/bands.json and band-testing.txt on the live reader.
REAL_BANDS = {
    584194215538: "Nate's Blue Band",
    584189178015: "EPCOT 40th Band",
    584190630766: "Harmonious Band (a MagicBand+)",
    584192666045: "40th Band 2",
    584188110330: "MagicBand 2",
    584187545678: "MagicBand 2",
    584188126650: "MagicBand 2",
}
NON_DISNEY = {232229082205: "Orange/Blank"}


class BandDetectionTests(unittest.TestCase):
    def setUp(self):
        self.reader = RfidMfrc522.__new__(RfidMfrc522)

    def test_real_band_ids_are_recognised(self):
        for uid, label in REAL_BANDS.items():
            with self.subTest(uid=uid, band=label):
                self.assertTrue(self.reader.isDisneyBand(uid))

    def test_a_non_disney_tag_is_not_recognised(self):
        for uid, label in NON_DISNEY.items():
            with self.subTest(uid=uid, tag=label):
                self.assertFalse(self.reader.isDisneyBand(uid))

    def test_the_boundaries_of_the_uid_range(self):
        low = RfidMfrc522.UID_CASCADE_NXP_MIN
        high = RfidMfrc522.UID_CASCADE_NXP_MAX
        self.assertTrue(self.reader.isDisneyBand(low))
        self.assertTrue(self.reader.isDisneyBand(high))
        self.assertFalse(self.reader.isDisneyBand(low - 1))
        self.assertFalse(self.reader.isDisneyBand(high + 1))

    def test_malformed_ids_are_rejected(self):
        # The old prefix regex accepted these: "5841" followed by any digit
        # matched, so "58411abc" and absurdly long numbers counted as bands.
        for value in ("58411abc", "5841999999999999999", "5841", "", None, "abc", object()):
            with self.subTest(value=repr(value)):
                self.assertFalse(self.reader.isDisneyBand(value))

    def test_ids_are_accepted_as_str_or_int(self):
        for uid in REAL_BANDS:
            with self.subTest(uid=uid):
                self.assertTrue(self.reader.isDisneyBand(str(uid)))

    def test_magicband_plus_detection_is_a_documented_no_op(self):
        # read_id() never sees the last UID byte that separates a MagicBand+
        # from a MagicBand 2, so this cannot work and says so rather than
        # looking like an oversight.
        for uid in REAL_BANDS:
            self.assertFalse(RfidMfrc522.isIdMagicBandPlus(uid))


if __name__ == "__main__":
    unittest.main()
