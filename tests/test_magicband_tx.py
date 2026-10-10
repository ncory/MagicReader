"""The MagicBand TX action.

MagicBandTX (github.com/ncory/MagicBandTX) is an ESP32 that broadcasts the
Bluetooth cues a MagicBand+ responds to. It replaced the old MagicBand
Broadcast action, which posted to a /command endpoint that no longer exists.

Its cue parameters vary per effect - colour, zone, inner/outer, five indices,
rgb, duration, fade, vibration - far more than the editor's one value box could
model as fields. The device accepts all of them as a query string, so that is
what the value box holds, and the whole API stays reachable.

Everything here runs offline.
"""
import unittest

import _support  # noqa: F401
from sequence import Sequence
from sequenceAction import (MAGICBANDTX_COMMANDS, ActionType, SequenceAction)


def url(address="magicband-tx.local", port=-1, command="send", data=None):
    return SequenceAction.new_action_magicband_tx(
        address, port, command, data).buildMagicBandTxUrl()


class UrlMappingTests(unittest.TestCase):
    def test_a_cue_becomes_a_send_query(self):
        self.assertEqual(
            url(command="send", data="effect=color&color=21&duration=10"),
            "http://magicband-tx.local/api/send?effect=color&color=21&duration=10")

    def test_stop_takes_nothing(self):
        self.assertEqual(url(command="stop"),
                         "http://magicband-tx.local/api/stop")
        # ...and ignores anything left in the value box
        self.assertEqual(url(command="stop", data="effect=color"),
                         "http://magicband-tx.local/api/stop")

    def test_a_playlist_name_is_encoded_not_restricted(self):
        # The device's own example is "My Show"
        self.assertEqual(url(command="play", data="My Show"),
                         "http://magicband-tx.local/api/play?id=My+Show")
        self.assertEqual(url(command="play", data="Tap/In #2"),
                         "http://magicband-tx.local/api/play?id=Tap%2FIn+%232")

    def test_every_command_in_the_list_produces_a_url(self):
        # Guards against adding a command to the UI and forgetting the mapping
        for command in MAGICBANDTX_COMMANDS:
            data = {"send": "effect=color", "play": "Show"}.get(command)
            with self.subTest(command=command):
                self.assertIsNotNone(url(command=command, data=data))

    def test_a_command_is_matched_regardless_of_case_or_padding(self):
        self.assertEqual(url(command="  STOP "),
                         "http://magicband-tx.local/api/stop")

    def test_a_port_is_appended_when_set(self):
        self.assertEqual(url(port=8080, command="stop"),
                         "http://magicband-tx.local:8080/api/stop")

    def test_a_pasted_browser_url_is_accepted(self):
        for address in ("http://magicband-tx.local/", "magicband-tx.local/",
                        "  magicband-tx.local  "):
            with self.subTest(address=address):
                self.assertEqual(url(address=address, command="stop"),
                                 "http://magicband-tx.local/api/stop")


class CueEncodingTests(unittest.TestCase):
    def test_the_documented_cues_survive_encoding(self):
        cases = {
            "effect=color&color=21&duration=10": "effect=color&color=21&duration=10",
            # Five colours go as a comma string; the device parses that as
            # readily as a JSON array, so every effect fits in one field
            "effect=five&colors=21,2,25,0,8&vib=3":
                "effect=five&colors=21%2C2%2C25%2C0%2C8&vib=3",
            "hex=8301E905002E0EF5B0": "hex=8301E905002E0EF5B0",
            "effect=rgb&rgb=%23FF8000": "effect=rgb&rgb=%23FF8000",
            "effect=rgb&rgb=#FF8000": "effect=rgb&rgb=%23FF8000",
        }
        for given, expected in cases.items():
            with self.subTest(given=given):
                self.assertEqual(SequenceAction.encodeCueParams(given), expected)

    def test_text_pasted_from_the_devices_docs_is_not_encoded_twice(self):
        # Its README writes "?id=My%20Show" and "rgb=%23FF8000". Encoding those
        # again would send the literal characters "%23" as the colour.
        self.assertEqual(SequenceAction.encodeCueParams("rgb=%23FF8000"),
                         "rgb=%23FF8000")
        self.assertEqual(SequenceAction.encodeCueParams("label=My%20Show"),
                         "label=My+Show")
        # A literal percent that is not an escape still survives
        self.assertEqual(SequenceAction.encodeCueParams("label=100%"),
                         "label=100%25")

    def test_a_pasted_playlist_name_is_not_encoded_twice(self):
        self.assertEqual(
            SequenceAction.new_action_magicband_tx(
                "tx.local", -1, "play", "My%20Show").buildMagicBandTxUrl(),
            "http://tx.local/api/play?id=My+Show")

    def test_a_value_that_would_truncate_the_url_is_encoded(self):
        # Unencoded, the "#" would end the URL and a different cue would go out
        self.assertEqual(SequenceAction.encodeCueParams("effect=rgb&rgb=#FF8000"),
                         "effect=rgb&rgb=%23FF8000")
        self.assertEqual(SequenceAction.encodeCueParams("label=tap in"),
                         "label=tap+in")

    def test_a_leading_question_mark_and_stray_spacing_are_tolerated(self):
        for given in ("?effect=color&color=21", " effect=color & color=21 ",
                      "effect=color&&color=21", "effect=color&color=21&"):
            with self.subTest(given=given):
                self.assertEqual(SequenceAction.encodeCueParams(given),
                                 "effect=color&color=21")

    def test_a_valueless_key_is_kept(self):
        # The device treats a bare flag as present
        self.assertEqual(SequenceAction.encodeCueParams("wake"), "wake=")

    def test_unusable_cue_text_is_refused(self):
        for bad in (None, "", "   ", "&", "&&", "=novalue", 42):
            with self.subTest(given=repr(bad)):
                self.assertIsNone(SequenceAction.encodeCueParams(bad))


class RejectionTests(unittest.TestCase):
    def test_send_without_parameters_is_refused(self):
        # Firing /api/send bare would be a silent no-op, since the queue does
        # not read the device's error back
        for bad in (None, "", "   ", "="):
            with self.subTest(data=repr(bad)):
                self.assertIsNone(url(command="send", data=bad))

    def test_play_without_a_playlist_name_is_refused(self):
        for bad in (None, "", "   "):
            with self.subTest(data=repr(bad)):
                self.assertIsNone(url(command="play", data=bad))

    def test_an_unknown_command_is_refused(self):
        for bad in ("build", "config", "explode", "", None, 7):
            with self.subTest(command=repr(bad)):
                self.assertIsNone(url(command=bad, data="effect=color"))

    def test_an_unusable_address_is_refused(self):
        for bad in (None, "", "   ", "http://", "/", 42):
            with self.subTest(address=repr(bad)):
                self.assertIsNone(url(address=bad, command="stop"))


class PersistenceTests(unittest.TestCase):
    def test_an_action_round_trips_through_a_saved_sequence(self):
        original = Sequence.createFromDict({
            "name": "Tap",
            "actions": [
                {"type": "magicBandTX", "address": "magicband-tx.local",
                 "command": "send", "data": "effect=color&color=21&duration=10",
                 "delay": 0.25},
                {"type": "magicBandTX", "address": "magicband-tx.local",
                 "command": "stop", "delay": 3},
            ],
        }, "tap")
        self.assertEqual([a.type for a in original.actions],
                         [ActionType.MagicBandTX, ActionType.MagicBandTX])
        again = Sequence.createFromDict(original.toDict(), "tap")
        self.assertEqual(again.toDict(), original.toDict())
        self.assertEqual(again.actions[0].delay, 0.25)
        self.assertEqual(
            again.actions[0].buildMagicBandTxUrl(),
            "http://magicband-tx.local/api/send?effect=color&color=21&duration=10")

    def test_stop_does_not_persist_an_empty_argument(self):
        action = SequenceAction.new_action_magicband_tx(
            "magicband-tx.local", -1, "stop")
        self.assertNotIn("data", action.toDict())


class RetiredBroadcastTests(unittest.TestCase):
    """The old action is gone, and old files holding it must still load."""

    def test_the_old_type_no_longer_exists(self):
        self.assertFalse(hasattr(ActionType, "MagicBandBroadcast"))
        self.assertIsNone(SequenceAction.createFromDict(
            {"type": "magicBandBroadcast", "address": "x", "data": "y"}))

    def test_a_sequence_holding_one_still_loads_without_it(self):
        # The owner accepted this as a breaking change: the old actions are
        # dropped on load rather than blocking the sequence they sit in
        sequence = Sequence.createFromDict({
            "name": "Old Show",
            "actions": [
                {"type": "soundFile", "data": "TapIn.wav", "delay": 0},
                {"type": "magicBandBroadcast", "address": "old", "data": "cue", "delay": 1},
                {"type": "wledInternal", "data": 7, "delay": 0},
            ],
        }, "old")
        self.assertIsNotNone(sequence)
        self.assertEqual(sequence.name, "Old Show")
        self.assertEqual([a.type for a in sequence.actions],
                         [ActionType.SoundFile, ActionType.WLEDInternal])
        # And saving it writes the sequence without the retired action
        self.assertNotIn("magicBandBroadcast", str(sequence.toDict()))


class DispatchTests(unittest.TestCase):
    def setUp(self):
        import rest
        self.sent = []
        self.original = rest.RestQueue.makeRestCallAsync
        rest.RestQueue.makeRestCallAsync = lambda _self, *a, **k: self.sent.append((a, k))
        self.addCleanup(self._restore)

    def _restore(self):
        import rest
        rest.RestQueue.makeRestCallAsync = self.original

    def test_a_valid_action_queues_one_get(self):
        action = SequenceAction.new_action_magicband_tx(
            "magicband-tx.local", -1, "send", "effect=color&color=21")
        self.assertTrue(action.performAction(None, None))
        self.assertEqual(len(self.sent), 1)
        args, _ = self.sent[0]
        self.assertEqual(args[0],
                         "http://magicband-tx.local/api/send?effect=color&color=21")
        self.assertEqual(args[1], "GET")

    def test_an_invalid_action_queues_nothing(self):
        action = SequenceAction.new_action_magicband_tx(
            "magicband-tx.local", -1, "send", "")
        self.assertFalse(action.performAction(None, None))
        self.assertEqual(self.sent, [])


if __name__ == "__main__":
    unittest.main()
