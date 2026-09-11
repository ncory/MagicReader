"""GPIOManager: only real GPIO pins can be configured as outputs.

The original check accepted any pin from 1 to 40, which includes the 3.3V and
5V rails, every ground, the HAT ID EEPROM, and the SPI pins and reset line the
RFID reader owns. Driving a supply rail as an output shorts it through the pin
driver; taking pin 22 would kill the reader.
"""
import unittest

import _support  # noqa: F401
from gpioManager import GPIOManager

POWER_PINS = {1: "3.3V", 2: "5V", 4: "5V", 17: "3.3V"}
GROUND_PINS = {6, 9, 14, 20, 25, 30, 34, 39}
EEPROM_PINS = {27, 28}
READER_PINS = {19: "MOSI", 21: "MISO", 22: "reset", 23: "SCLK", 24: "CE0", 26: "CE1"}


class PinValidationTests(unittest.TestCase):
    def test_power_pins_are_rejected(self):
        for pin, label in POWER_PINS.items():
            with self.subTest(pin=pin, rail=label):
                self.assertIsNotNone(GPIOManager.describeInvalidPin(pin))

    def test_ground_pins_are_rejected(self):
        for pin in sorted(GROUND_PINS):
            with self.subTest(pin=pin):
                self.assertFalse(GPIOManager.isUsablePin(pin))

    def test_eeprom_pins_are_rejected(self):
        for pin in sorted(EEPROM_PINS):
            with self.subTest(pin=pin):
                self.assertFalse(GPIOManager.isUsablePin(pin))

    def test_reader_pins_are_rejected_and_say_why(self):
        for pin, label in READER_PINS.items():
            with self.subTest(pin=pin, signal=label):
                reason = GPIOManager.describeInvalidPin(pin)
                self.assertIsNotNone(reason)
                self.assertIn("MFRC522", reason)

    def test_out_of_range_pins_are_rejected(self):
        for pin in (0, -1, 41, 99, "seven", None):
            with self.subTest(pin=pin):
                self.assertFalse(GPIOManager.isUsablePin(pin))

    def test_usable_pins_do_not_overlap_anything_reserved(self):
        usable = set(GPIOManager.getUsablePins())
        self.assertEqual(
            usable & (set(POWER_PINS) | GROUND_PINS | EEPROM_PINS | set(READER_PINS)),
            set(),
        )
        self.assertEqual(len(usable), 20)

    def test_normalizeOutputs_drops_bad_pins_and_keeps_good_ones(self):
        outputs = GPIOManager.normalizeOutputs([
            {"id": "relay", "pin": 38, "trigger_state": "LOW", "pulse_seconds": 0.5},
            {"id": "rail", "pin": 2, "trigger_state": "LOW", "pulse_seconds": 0.5},
            {"id": "reader", "pin": 22, "trigger_state": "LOW", "pulse_seconds": 0.5},
        ])
        self.assertEqual([o["id"] for o in outputs], ["relay"])

    def test_normalizeOutputs_rejects_duplicate_ids(self):
        outputs = GPIOManager.normalizeOutputs([
            {"id": "a", "pin": 38, "trigger_state": "LOW", "pulse_seconds": 0.5},
            {"id": "a", "pin": 40, "trigger_state": "LOW", "pulse_seconds": 0.5},
        ])
        self.assertEqual(len(outputs), 1)


class ReaderPinConsistencyTests(unittest.TestCase):
    def test_reader_reset_pin_is_in_the_reserved_set(self):
        # rfid_mfrc522 defines the reset pin; gpioManager has to exclude it.
        # If the two drift apart a sequence could be handed the reader's reset
        # line. magicreader.py warns about this at startup; assert it here too.
        from rfid_mfrc522 import RfidMfrc522
        self.assertIn(RfidMfrc522.RESET_PIN, GPIOManager.RESERVED_PINS)


if __name__ == "__main__":
    unittest.main()
