"""The {band_id} variable in action values.

A tap's band ID is passed down to every action of the sequence it starts and
replaces {band_id} in the action's URL, value and command - so a URL action
can carry the band to another system: http://host/hit?band={band_id}.
"""
import threading
import unittest

import _support  # noqa: F401
import magicreader
from sequence import Sequence
from sequenceAction import SequenceAction
from test_event_loop import makeApp

BAND = "0453652AC05F80"


class CapturesRestCalls(unittest.TestCase):
    def setUp(self):
        import rest
        self.sent = []
        self.original = rest.RestQueue.makeRestCallAsync
        rest.RestQueue.makeRestCallAsync = lambda _self, *a, **k: self.sent.append(a)

    def tearDown(self):
        import rest
        rest.RestQueue.makeRestCallAsync = self.original

    def sentUrls(self):
        return [args[0] for args in self.sent]


class ActionTests(CapturesRestCalls):
    def test_the_variable_is_replaced_in_a_url(self):
        action = SequenceAction.new_action_url("http://host/hit?band={band_id}&src=reader")
        self.assertTrue(action.performAction(None, None, band_id=BAND))
        self.assertEqual(self.sentUrls(), [f"http://host/hit?band={BAND}&src=reader"])

    def test_every_occurrence_is_replaced(self):
        action = SequenceAction.new_action_url("http://host/{band_id}/hit?band={band_id}")
        action.performAction(None, None, band_id=BAND)
        self.assertEqual(self.sentUrls(), [f"http://host/{BAND}/hit?band={BAND}"])

    def test_the_stored_action_keeps_its_variable_for_the_next_tap(self):
        action = SequenceAction.new_action_url("http://host/hit?band={band_id}")
        action.performAction(None, None, band_id=BAND)
        action.performAction(None, None, band_id="3611EE94")
        self.assertEqual(action.url, "http://host/hit?band={band_id}")
        self.assertEqual(self.sentUrls(), [f"http://host/hit?band={BAND}",
                                           "http://host/hit?band=3611EE94"])

    def test_without_a_band_the_variable_is_empty(self):
        # A sequence played from the web UI has no band behind it
        action = SequenceAction.new_action_url("http://host/hit?band={band_id}")
        self.assertTrue(action.performAction(None, None))
        self.assertEqual(self.sentUrls(), ["http://host/hit?band="])

    def test_a_json_value_is_filled_in_without_touching_its_braces(self):
        # The editor stores a URL action's value as parsed JSON when it parses
        data = {"band": "{band_id}", "tags": ["{band_id}", "x"], "count": 3, "on": True}
        action = SequenceAction.new_action_url("http://host/", "POST", data)
        resolved = action.withBandId(BAND)
        self.assertEqual(resolved.data, {"band": BAND, "tags": [BAND, "x"], "count": 3, "on": True})
        self.assertEqual(action.data["band"], "{band_id}")

    def test_other_braces_are_left_alone(self):
        action = SequenceAction.new_action_url("http://host/?q={band}&id={band_id}&x={}")
        self.assertEqual(action.withBandId(BAND).url, f"http://host/?q={{band}}&id={BAND}&x={{}}")

    def test_the_variable_is_replaced_in_a_command(self):
        action = SequenceAction.new_action_brightsign("10.0.0.5", 5000, "tap:{band_id}")
        self.assertEqual(action.withBandId(BAND).command, f"tap:{BAND}")

    def test_an_action_without_the_variable_is_not_copied(self):
        action = SequenceAction.new_action_url("http://host/hit")
        self.assertIs(action.withBandId(BAND), action)


class SequenceTests(CapturesRestCalls):
    def test_every_action_in_the_sequence_gets_the_band(self):
        sequence = Sequence("s", "S")
        sequence.addAction(SequenceAction.new_action_url("http://a/?b={band_id}"))
        sequence.addAction(SequenceAction.new_action_url("http://b/{band_id}"))
        self.assertTrue(sequence.play(None, None, band_id=BAND))
        self.assertEqual(self.sentUrls(), [f"http://a/?b={BAND}", f"http://b/{BAND}"])


class AppTests(CapturesRestCalls):
    def test_a_tap_passes_its_band_to_the_sequence_it_starts(self):
        app = makeApp()
        started = []
        app.setState = lambda *a, **k: None
        app.band_manager = type("B", (), {"lookupBandId": staticmethod(lambda band_id, isDisney: "welcome")})()
        app.sequence_manager = type("M", (), {"getSequenceById": staticmethod(lambda seq_id: object())})()
        app.playSequence = lambda seq_id, band_id=None: started.append((seq_id, band_id)) or True
        app.onReadMagicBand(BAND, True)
        self.assertEqual(started, [("welcome", BAND)])

    def test_the_sequence_thread_plays_with_the_band(self):
        sequence = Sequence("welcome", "Welcome")
        sequence.addAction(SequenceAction.new_action_url("http://host/hit?band={band_id}"))
        app = makeApp()
        app.setState = lambda *a, **k: None
        app.wledManager = app.gpioManager = None
        app.sequence_manager = type("M", (), {"getSequenceById": staticmethod(lambda seq_id: sequence)})()
        self.assertTrue(app.playSequence("welcome", BAND))
        app.sequence_thread.join(timeout=2)
        self.assertEqual(self.sentUrls(), [f"http://host/hit?band={BAND}"])


if __name__ == "__main__":
    unittest.main()
