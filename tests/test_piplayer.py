"""The PiPlayer action.

PiPlayer (github.com/ncory/PiPlayer) is a fullscreen playlist player with an
unauthenticated REST API on the same trusted LAN. A reader tap turns into one
transport command.

The action stores the command exactly as PiPlayer's API names it, so these
tests are really checking one mapping: stored fields -> URL. Everything below
runs offline; buildPiPlayerUrl is deliberately separate from the call so the
mapping can be tested without a player on the network.
"""
import unittest

import _support  # noqa: F401
from sequence import Sequence
from sequenceAction import (PIPLAYER_COMMANDS, ActionType, SequenceAction)


def url(address="player1.local", port=-1, command="play", data=None):
    return SequenceAction.new_action_piplayer(address, port, command, data).buildPiPlayerUrl()


class UrlMappingTests(unittest.TestCase):
    def test_play_targets_the_playlist_endpoint(self):
        self.assertEqual(url(command="play", data="lobby"),
                         "http://player1.local/api/playlists/lobby/play")

    def test_play_without_a_playlist_resumes_or_restarts(self):
        # PiPlayer's POST /api/play with no playlist resumes if paused, else
        # restarts the last or default playlist. A useful cue on its own.
        for blank in (None, "", "   "):
            with self.subTest(data=repr(blank)):
                self.assertEqual(url(command="play", data=blank),
                                 "http://player1.local/api/play")

    def test_the_plain_transport_commands_map_to_their_endpoints(self):
        for command in ("stop", "next", "previous", "pause", "resume", "toggle"):
            with self.subTest(command=command):
                self.assertEqual(url(command=command),
                                 f"http://player1.local/api/{command}")

    def test_loop_item_carries_its_mode_as_the_enabled_parameter(self):
        self.assertEqual(url(command="loop-item", data="on"),
                         "http://player1.local/api/loop-item?enabled=true")
        self.assertEqual(url(command="loop-item", data="off"),
                         "http://player1.local/api/loop-item?enabled=false")
        # Unset or unrecognised means toggle, which is PiPlayer's own default
        for mode in (None, "", "toggle", "sideways"):
            with self.subTest(mode=repr(mode)):
                self.assertEqual(url(command="loop-item", data=mode),
                                 "http://player1.local/api/loop-item?enabled=toggle")

    def test_every_command_in_the_list_produces_a_url(self):
        # Guards against adding a command to the UI and forgetting the mapping
        for command in PIPLAYER_COMMANDS:
            with self.subTest(command=command):
                self.assertIsNotNone(url(command=command))

    def test_a_command_is_matched_regardless_of_case_or_padding(self):
        self.assertEqual(url(command=" PAUSE "), "http://player1.local/api/pause")


class AddressTests(unittest.TestCase):
    def test_a_port_is_appended_when_set(self):
        self.assertEqual(url(port=8080, command="stop"),
                         "http://player1.local:8080/api/stop")

    def test_no_port_means_piplayers_installed_default(self):
        for port in (-1, 0, None, "8080"):
            with self.subTest(port=repr(port)):
                self.assertEqual(url(port=port, command="stop"),
                                 "http://player1.local/api/stop")

    def test_a_port_in_the_address_wins(self):
        # Otherwise "player1.local:8080" plus a port field would produce
        # "player1.local:8080:80", which resolves to nothing
        self.assertEqual(url(address="player1.local:8080", port=9999, command="stop"),
                         "http://player1.local:8080/api/stop")

    def test_a_pasted_browser_url_is_accepted(self):
        for address in ("http://player1.local/", "https://player1.local",
                        "player1.local/", "  player1.local  "):
            with self.subTest(address=address):
                self.assertEqual(url(address=address, command="stop"),
                                 "http://player1.local/api/stop")


class RejectionTests(unittest.TestCase):
    def test_a_playlist_id_may_not_escape_the_path(self):
        # The id goes straight into a URL path. Without this, a sequence could
        # reach any PiPlayer endpoint, including system ones.
        for bad in ("../../api/system/restart-renderer", "a/b", "a?x=1",
                    "a#b", "UPPER", "with space", "x" * 65, "a%2Fb"):
            with self.subTest(playlist=bad):
                self.assertIsNone(url(command="play", data=bad))

    def test_a_valid_playlist_id_is_accepted(self):
        for good in ("lobby", "zz-test", "a_b-2", "x", "9", "x" * 64):
            with self.subTest(playlist=good):
                self.assertIsNotNone(url(command="play", data=good))

    def test_an_unknown_command_is_refused(self):
        for bad in ("explode", "", None, "restart-renderer", 7):
            with self.subTest(command=repr(bad)):
                self.assertIsNone(url(command=bad))

    def test_an_unusable_address_is_refused(self):
        for bad in (None, "", "   ", "http://", "/", 42):
            with self.subTest(address=repr(bad)):
                self.assertIsNone(url(address=bad, command="stop"))


class PersistenceTests(unittest.TestCase):
    def test_an_action_round_trips_through_a_saved_sequence(self):
        original = Sequence.createFromDict({
            "name": "Tap to play",
            "actions": [
                {"type": "piPlayer", "address": "player1.local", "port": 8080,
                 "command": "play", "data": "lobby", "delay": 0.25},
                {"type": "piPlayer", "address": "player1.local",
                 "command": "stop", "delay": 2},
            ],
        }, "tap")
        self.assertEqual([a.type for a in original.actions],
                         [ActionType.PiPlayer, ActionType.PiPlayer])
        # Saving writes toDict; loading reads it back
        again = Sequence.createFromDict(original.toDict(), "tap")
        self.assertEqual(again.toDict(), original.toDict())
        self.assertEqual(again.actions[0].buildPiPlayerUrl(),
                         "http://player1.local:8080/api/playlists/lobby/play")
        self.assertEqual(again.actions[0].delay, 0.25)
        self.assertEqual(again.actions[1].buildPiPlayerUrl(),
                         "http://player1.local/api/stop")

    def test_a_command_only_action_does_not_persist_an_empty_argument(self):
        action = SequenceAction.new_action_piplayer("player1.local", -1, "next")
        self.assertNotIn("data", action.toDict())


class DispatchTests(unittest.TestCase):
    """performAction must reach the PiPlayer branch and queue exactly one call."""

    def setUp(self):
        import rest
        self.sent = []
        self.original = rest.RestQueue.makeRestCallAsync
        rest.RestQueue.makeRestCallAsync = lambda _self, *a, **k: self.sent.append((a, k))

    def tearDown(self):
        import rest
        rest.RestQueue.makeRestCallAsync = self.original

    def test_a_valid_action_queues_one_post(self):
        action = SequenceAction.new_action_piplayer("player1.local", -1, "play", "lobby")
        self.assertTrue(action.performAction(None, None))
        self.assertEqual(len(self.sent), 1)
        args, _ = self.sent[0]
        self.assertEqual(args[0], "http://player1.local/api/playlists/lobby/play")
        self.assertEqual(args[1], "POST")

    def test_an_invalid_action_queues_nothing_and_reports_failure(self):
        action = SequenceAction.new_action_piplayer("player1.local", -1, "play", "../escape")
        self.assertFalse(action.performAction(None, None))
        self.assertEqual(self.sent, [])


if __name__ == "__main__":
    unittest.main()
