"""Sequence and SequenceAction parsing.

Covers two fixes. Chained @classmethod/@staticmethod decorators were removed
from Python in 3.13; while they were there, createFromDict silently returned
None on 3.13 and every sequence loaded with no actions at all. And delays were
int-only, so a 0.25 typed into the editor became 0 - no sub-second cueing.
"""
import unittest

import _support  # noqa: F401
from sequence import Sequence
from sequenceAction import ActionType, SequenceAction


class ActionParsingTests(unittest.TestCase):
    def test_sequence_parses_all_its_actions(self):
        sequence = Sequence.createFromDict({
            "name": "Test Show",
            "cancel_allowed": False,
            "actions": [
                {"type": "delay", "delay": 2},
                {"type": "wledInternal", "data": 7, "delay": 0},
                {"type": "soundFile", "data": "TapIn.wav", "delay": 1},
                {"type": "gpioClosure", "data": "relay", "delay": 0},
            ],
        }, "test-seq")
        self.assertIsNotNone(sequence)
        self.assertEqual(sequence.id, "test-seq")
        self.assertEqual(sequence.name, "Test Show")
        self.assertFalse(sequence.cancel_allowed)
        self.assertEqual(
            [a.type for a in sequence.actions],
            [ActionType.Delay, ActionType.WLEDInternal,
             ActionType.SoundFile, ActionType.GPIOClosure],
        )

    def test_round_trip_through_toDict_preserves_actions(self):
        original = Sequence.createFromDict({
            "name": "Round Trip",
            "actions": [{"type": "url", "url": "http://x/y", "method": "POST", "delay": 1}],
        }, "rt")
        again = Sequence.createFromDict(original.toDict(), "rt")
        self.assertEqual(len(again.actions), 1)
        self.assertEqual(again.actions[0].url, "http://x/y")
        self.assertEqual(again.actions[0].method, "POST")

    def test_non_dict_input_is_rejected(self):
        self.assertIsNone(SequenceAction.createFromDict("not a dict"))
        self.assertIsNone(Sequence.createFromDict("not a dict", "id"))

    def test_unknown_action_type_is_rejected(self):
        self.assertIsNone(SequenceAction.createFromDict({"type": "teleport"}))


class DelayTests(unittest.TestCase):
    def test_fractional_delays_are_kept(self):
        for value in (0.25, 2.5, 0.001):
            with self.subTest(value=value):
                self.assertEqual(SequenceAction.coerceDelay(value), value)

    def test_whole_numbers_stay_ints_so_files_round_trip_unchanged(self):
        result = SequenceAction.coerceDelay(249)
        self.assertEqual(result, 249)
        self.assertIsInstance(result, int)

    def test_unusable_values_become_zero(self):
        for value in (-1, -0.5, "2", None, True, False,
                      float("inf"), float("nan"), object()):
            with self.subTest(value=repr(value)):
                self.assertEqual(SequenceAction.coerceDelay(value), 0)

    def test_a_fractional_delay_survives_parsing(self):
        action = SequenceAction.createFromDict(
            {"type": "soundFile", "data": "TapIn.wav", "delay": 0.25})
        self.assertEqual(action.delay, 0.25)
        self.assertEqual(SequenceAction.createFromDict(action.toDict()).delay, 0.25)


if __name__ == "__main__":
    unittest.main()
