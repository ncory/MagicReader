"""The unreachable-host cooldown.

A host that does not resolve costs a flat 5 s on a Pi, measured on hm4, and
mDNS has no negative answer to cache - you wait out the timeout every single
time. The REST queue is serial, so one dead WLED board delays every light cue
behind it, and the BrightSign/ChromaTeq actions resolve inline on the sequence
thread, stalling the sequence itself.

So the first failure is paid and the rest are skipped until the cooldown ends.
These tests drive the tracker directly; nothing here touches the network.
"""
import threading
import unittest

import _support  # noqa: F401
from rest import UnreachableHosts


class HostParsingTests(unittest.TestCase):
    def test_a_host_is_found_in_a_url_or_a_bare_address(self):
        cases = {
            "http://player1.local/api/stop": "player1.local",
            "http://player1.local:8080/api/next": "player1.local",
            "https://wled/win&PL=8": "wled",
            "player1.local": "player1.local",
            "player1.local:5000": "player1.local",
            "192.168.1.91": "192.168.1.91",
            "PLAYER1.LOCAL": "player1.local",   # one host, one entry
        }
        for target, expected in cases.items():
            with self.subTest(target=target):
                self.assertEqual(UnreachableHosts.hostOf(target), expected)

    def test_an_unusable_target_has_no_host(self):
        for bad in (None, "", "   ", 42, "http://"):
            with self.subTest(target=repr(bad)):
                self.assertIsNone(UnreachableHosts.hostOf(bad))

    def test_a_target_with_no_host_is_never_skipped(self):
        # Otherwise a malformed url would be silently swallowed instead of
        # failing where it can be seen
        for bad in (None, "", 42):
            with self.subTest(target=repr(bad)):
                self.assertFalse(UnreachableHosts.shouldSkip(bad))


class CooldownTests(unittest.TestCase):
    def setUp(self):
        UnreachableHosts.reset()
        self.original = UnreachableHosts.COOLDOWN
        self.addCleanup(self._restore)

    def _restore(self):
        UnreachableHosts.COOLDOWN = self.original
        UnreachableHosts.reset()

    def test_an_unknown_host_is_not_skipped(self):
        self.assertFalse(UnreachableHosts.shouldSkip("http://wled/win&PL=8"))

    def test_a_failure_puts_the_host_into_cooldown(self):
        UnreachableHosts.recordFailure("http://wled/win&PL=8", "gaierror")
        self.assertTrue(UnreachableHosts.shouldSkip("http://wled/win&PL=8"))

    def test_the_cooldown_covers_the_host_not_the_url(self):
        # One dead board must not be re-probed once per preset
        UnreachableHosts.recordFailure("http://wled/win&PL=8")
        for other in ("http://wled/win&PL=15", "http://wled:80/win&PL=16", "wled"):
            with self.subTest(other=other):
                self.assertTrue(UnreachableHosts.shouldSkip(other))

    def test_other_hosts_are_unaffected(self):
        UnreachableHosts.recordFailure("http://wled/win&PL=8")
        self.assertFalse(UnreachableHosts.shouldSkip("http://player1/api/stop"))

    def test_the_cooldown_expires_and_lets_one_call_through_to_probe(self):
        UnreachableHosts.COOLDOWN = 0.05
        UnreachableHosts.recordFailure("http://wled/x")
        self.assertTrue(UnreachableHosts.shouldSkip("http://wled/x"))
        threading.Event().wait(0.08)
        self.assertFalse(UnreachableHosts.shouldSkip("http://wled/x"))

    def test_success_clears_the_cooldown_immediately(self):
        UnreachableHosts.recordFailure("http://wled/x")
        self.assertTrue(UnreachableHosts.shouldSkip("http://wled/x"))
        UnreachableHosts.recordSuccess("http://wled/x")
        self.assertFalse(UnreachableHosts.shouldSkip("http://wled/x"))

    def test_success_on_a_host_that_never_failed_is_harmless(self):
        UnreachableHosts.recordSuccess("http://player1/api/stop")
        self.assertFalse(UnreachableHosts.shouldSkip("http://player1/api/stop"))

    def test_a_failure_after_the_cooldown_restarts_it(self):
        UnreachableHosts.COOLDOWN = 0.05
        UnreachableHosts.recordFailure("http://wled/x")
        threading.Event().wait(0.08)
        self.assertFalse(UnreachableHosts.shouldSkip("http://wled/x"))
        UnreachableHosts.recordFailure("http://wled/x")
        self.assertTrue(UnreachableHosts.shouldSkip("http://wled/x"))

    def test_concurrent_use_is_safe(self):
        # The REST queue thread and the sequence thread both reach this
        errors = []

        def hammer(n):
            try:
                for i in range(200):
                    UnreachableHosts.recordFailure(f"http://host{n}/x")
                    UnreachableHosts.shouldSkip(f"http://host{n}/x")
                    UnreachableHosts.recordSuccess(f"http://host{n}/x")
            except Exception as e:  # pragma: no cover
                errors.append(e)

        threads = [threading.Thread(target=hammer, args=(n,)) for n in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(10)
        self.assertEqual(errors, [])


class RestCallIntegrationTests(unittest.TestCase):
    """makeRestCall must skip a host in cooldown without touching the network."""

    def setUp(self):
        UnreachableHosts.reset()
        self.addCleanup(UnreachableHosts.reset)

    def test_a_failing_call_records_the_host_and_the_next_is_skipped(self):
        import rest
        attempts = []

        class Boom:
            def request(self, **kwargs):
                attempts.append(kwargs["uri"])
                raise OSError("Unable to find the server at wled")

        original = rest.RestHelpers._http_obj
        rest.RestHelpers._http_obj = Boom()
        try:
            self.assertFalse(rest.RestHelpers.makeRestCall("http://wled/win&PL=8"))
            self.assertEqual(len(attempts), 1)
            # The next three must not reach the network at all
            for preset in (15, 16, 8):
                self.assertFalse(rest.RestHelpers.makeRestCall(f"http://wled/win&PL={preset}"))
            self.assertEqual(len(attempts), 1, "a skipped call still hit the network")
        finally:
            rest.RestHelpers._http_obj = original

    def test_a_successful_call_clears_a_previous_failure(self):
        import rest

        class Fine:
            def request(self, **kwargs):
                return ({"status": "200"}, b"")

        UnreachableHosts.recordFailure("http://wled/x")
        original = rest.RestHelpers._http_obj
        originalCooldown = UnreachableHosts.COOLDOWN
        rest.RestHelpers._http_obj = Fine()
        try:
            UnreachableHosts.COOLDOWN = 0  # let the probe through
            self.assertTrue(rest.RestHelpers.makeRestCall("http://wled/x"))
            self.assertFalse(UnreachableHosts.shouldSkip("http://wled/x"))
        finally:
            rest.RestHelpers._http_obj = original
            UnreachableHosts.COOLDOWN = originalCooldown

    def test_an_http_error_status_is_not_a_dead_host(self):
        # A 404 is the host answering. Cooling it down would drop later cues
        import rest

        class NotFound:
            def request(self, **kwargs):
                return ({"status": "404"}, b"")

        original = rest.RestHelpers._http_obj
        rest.RestHelpers._http_obj = NotFound()
        try:
            self.assertTrue(rest.RestHelpers.makeRestCall("http://player1/api/nope"))
            self.assertFalse(UnreachableHosts.shouldSkip("http://player1/api/nope"))
        finally:
            rest.RestHelpers._http_obj = original


if __name__ == "__main__":
    unittest.main()
