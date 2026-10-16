"""Band IDs and Disney band detection from an MFRC522 read.

Band IDs are the tag's full UID as uppercase hex. Every MagicBand has a 7-byte
NXP UID (first byte 0x04), ending in 0x80 on a MagicBand 2 and 0x90 on a
MagicBand+.
"""
import datetime
import queue
import types
import unittest

import _support  # noqa: F401
from mfrc522Uid import NoTag, ReadError, TagRead
from rfid_mfrc522 import RfidMfrc522

# Read identically by the MFRC522 and an ACS ACR1555U on the live reader.
MAGICBAND2 = ["04258D927E6180", "043A71E29C4980", "04794D82963F80",
              "0453652AC05F80", "044A887A056680"]
MAGICBAND_PLUS = ["04BEA3F2B41190"]
# Generic MIFARE Classic 1K bracelets: 4-byte UIDs. 7DA60804 ends in 0x04,
# which must not be mistaken for the NXP manufacturer byte.
GENERIC = ["7DA60804", "052CBFB6", "25682D03", "3611EE94"]


class BandDetectionTests(unittest.TestCase):
    def setUp(self):
        self.reader = RfidMfrc522.__new__(RfidMfrc522)

    def test_real_magicbands_are_recognised(self):
        for uid in MAGICBAND2 + MAGICBAND_PLUS:
            with self.subTest(uid=uid):
                self.assertTrue(self.reader.isDisneyBand(uid))

    def test_generic_bands_are_not_recognised(self):
        for uid in GENERIC:
            with self.subTest(uid=uid):
                self.assertFalse(self.reader.isDisneyBand(uid))

    def test_a_seven_byte_uid_from_another_manufacturer_is_not_recognised(self):
        self.assertFalse(self.reader.isDisneyBand("053652AC05F80A"))

    def test_lowercase_ids_are_accepted(self):
        self.assertTrue(self.reader.isDisneyBand("0453652ac05f80"))

    def test_malformed_ids_are_rejected(self):
        # Including the old truncated decimal IDs the previous reader code stored.
        for value in ("584188126650", "0453652AC05F", "0453652AC05F8", "zz", "", None, 584188126650, object()):
            with self.subTest(value=repr(value)):
                self.assertFalse(self.reader.isDisneyBand(value))
                self.assertFalse(RfidMfrc522.isIdMagicBandPlus(value))

    def test_magicband_plus_is_told_apart_from_magicband_2(self):
        for uid in MAGICBAND_PLUS:
            with self.subTest(uid=uid):
                self.assertTrue(RfidMfrc522.isIdMagicBandPlus(uid))
        for uid in MAGICBAND2 + GENERIC:
            with self.subTest(uid=uid):
                self.assertFalse(RfidMfrc522.isIdMagicBandPlus(uid))


class FakeChip:
    """Plays back a script of readTag() outcomes, then stops the app."""

    def __init__(self, app, outcomes):
        self.app = app
        self.outcomes = list(outcomes)

    def readTag(self):
        if not self.outcomes:
            self.app.is_active = False
            raise NoTag()
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class ReaderThreadTests(unittest.TestCase):
    def runThread(self, outcomes):
        app = types.SimpleNamespace(is_active=True, event_queue=queue.PriorityQueue())
        reader = RfidMfrc522.__new__(RfidMfrc522)
        reader.app = app
        reader.timeDelta = datetime.timedelta(seconds=3)
        reader.lastReadTime = datetime.datetime.now() - datetime.timedelta(seconds=10)
        reader.POLL_INTERVAL_SECONDS = 0
        reader.reader = FakeChip(app, outcomes)
        reader.runReaderThread()
        events = []
        while not app.event_queue.empty():
            events.append(app.event_queue.get()[1].data)
        return events

    def tag(self, uidHex, sak=0x20):
        return TagRead(uid=bytes.fromhex(uidHex), atqa=b"\x44\x00", sak=sak)

    def test_a_read_is_queued_with_the_full_uid_as_hex(self):
        events = self.runThread([NoTag(), self.tag("0453652AC05F80")])
        self.assertEqual([(e.id, e.isDisney) for e in events], [("0453652AC05F80", True)])

    def test_a_generic_band_is_queued_as_not_disney(self):
        events = self.runThread([self.tag("3611EE94", sak=0x08)])
        self.assertEqual([(e.id, e.isDisney) for e in events], [("3611EE94", False)])

    def test_partial_reads_are_retried_not_reported(self):
        events = self.runThread([ReadError("weak"), ReadError("weak"), self.tag("04BEA3F2B41190")])
        self.assertEqual([e.id for e in events], ["04BEA3F2B41190"])

    def test_a_second_band_within_the_debounce_time_is_dropped(self):
        events = self.runThread([self.tag("0453652AC05F80"), self.tag("3611EE94", sak=0x08)])
        self.assertEqual([e.id for e in events], ["0453652AC05F80"])


if __name__ == "__main__":
    unittest.main()
