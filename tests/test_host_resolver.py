"""The background host resolver.

Name resolution must never happen on the cue path. Measured on a reader: an
mDNS name that does not answer costs a flat 5s, paid again every call, and a
name whose device is online flaps - a live PiPlayer gave six consecutive 5.00s
failures before recovering. The resolver keeps a last-known-good address so a
cue is served from memory or not at all.

Nothing here touches the network: refreshOnce is driven with a stubbed
getaddrinfo, and the background thread is never started except where a test
says so.
"""
import threading
import unittest

import _support  # noqa: F401
import hostResolver
from hostResolver import HostResolver


class FakeDns:
    """Stands in for socket.getaddrinfo with a table that can change."""

    def __init__(self, table):
        self.table = table
        self.lookups = []

    def __call__(self, host, *args, **kwargs):
        self.lookups.append(host)
        ip = self.table.get(host)
        if ip is None:
            raise OSError(f"Unable to find the server at {host}")
        return [(2, 1, 6, "", (ip, 0))]


class ResolverTestCase(unittest.TestCase):
    def setUp(self):
        HostResolver.reset()
        self.originalDns = hostResolver.socket.getaddrinfo
        # Sweeps must not write to the real data directory
        self.originalPersist = HostResolver._persist
        HostResolver._persist = False
        self.addCleanup(self._restore)

    def _restore(self):
        hostResolver.socket.getaddrinfo = self.originalDns
        HostResolver._persist = self.originalPersist
        HostResolver.reset()

    def useDns(self, table):
        fake = FakeDns(table)
        hostResolver.socket.getaddrinfo = fake
        return fake


class RegistrationTests(ResolverTestCase):
    def test_a_name_is_registered_once(self):
        self.assertTrue(HostResolver.register("hm4-wled.local"))
        self.assertFalse(HostResolver.register("hm4-wled.local"))
        self.assertFalse(HostResolver.register("HM4-WLED.LOCAL"))  # same device
        self.assertEqual(list(HostResolver.snapshot()), ["hm4-wled.local"])

    def test_an_ip_literal_is_not_registered(self):
        # Nothing to resolve, and registering it would have the refresher do
        # pointless work forever
        for literal in ("192.168.1.135", "127.0.0.1", "::1"):
            with self.subTest(literal=literal):
                self.assertFalse(HostResolver.register(literal))
        self.assertEqual(HostResolver.snapshot(), {})

    def test_junk_is_ignored(self):
        for bad in (None, "", "   ", 42, object()):
            with self.subTest(value=repr(bad)):
                self.assertFalse(HostResolver.register(bad))

    def test_priming_returns_the_number_of_new_names(self):
        self.assertEqual(
            HostResolver.primeFrom(["a.local", "b.local", "a.local", "192.168.1.5"]), 2)
        self.assertEqual(HostResolver.primeFrom(None), 0)


class LookupTests(ResolverTestCase):
    def test_an_unknown_name_returns_none_and_registers_itself(self):
        # The first cue for a name still pays the system resolver, but the
        # next one is served from cache
        self.assertIsNone(HostResolver.addressFor("new.local"))
        self.assertIn("new.local", HostResolver.snapshot())

    def test_a_resolved_name_is_served_from_cache(self):
        self.useDns({"hm4-wled.local": "192.168.1.135"})
        HostResolver.register("hm4-wled.local")
        HostResolver.refreshOnce()
        self.assertEqual(HostResolver.addressFor("hm4-wled.local"), "192.168.1.135")
        self.assertEqual(HostResolver.addressFor("HM4-WLED.local"), "192.168.1.135")

    def test_an_ip_literal_is_never_substituted(self):
        self.assertIsNone(HostResolver.addressFor("192.168.1.135"))

    def test_a_flapping_name_keeps_serving_the_last_good_address(self):
        # This is the whole point: six consecutive failures against a device
        # that is still online must not stop cues reaching it
        dns = self.useDns({"player1.local": "192.168.1.235"})
        HostResolver.register("player1.local")
        HostResolver.refreshOnce()
        dns.table.clear()                      # mDNS starts failing
        for _ in range(6):
            HostResolver.refreshOnce()
        self.assertEqual(HostResolver.addressFor("player1.local"), "192.168.1.235")

    def test_a_moved_device_is_picked_up(self):
        # DHCP: the address can change, and a refresh must follow it
        dns = self.useDns({"player1.local": "192.168.1.235"})
        HostResolver.register("player1.local")
        HostResolver.refreshOnce()
        dns.table["player1.local"] = "192.168.1.240"
        HostResolver.refreshOnce()
        self.assertEqual(HostResolver.addressFor("player1.local"), "192.168.1.240")

    def test_a_last_good_address_is_dropped_once_it_is_too_old(self):
        self.useDns({"x.local": "10.0.0.1"})
        HostResolver.register("x.local")
        HostResolver.refreshOnce()
        original = HostResolver.STALE_AFTER
        try:
            HostResolver.STALE_AFTER = -1
            self.assertIsNone(HostResolver.addressFor("x.local"))
        finally:
            HostResolver.STALE_AFTER = original

    def test_a_name_that_never_resolved_returns_none(self):
        self.useDns({})
        HostResolver.register("gone.local")
        HostResolver.refreshOnce()
        self.assertIsNone(HostResolver.addressFor("gone.local"))


class SweepTests(ResolverTestCase):
    def test_a_slow_name_does_not_delay_the_others(self):
        # A name that does not answer costs a flat 5s on a reader. Serially,
        # six of them is half a minute and the refresher never gets ahead.
        import time as clock

        def slow(host, *args, **kwargs):
            clock.sleep(0.3)
            if host == "good.local":
                return [(2, 1, 6, "", ("10.0.0.9", 0))]
            raise OSError("no answer")

        hostResolver.socket.getaddrinfo = slow
        names = [f"dead{i}.local" for i in range(6)] + ["good.local"]
        HostResolver.primeFrom(names)

        started = clock.monotonic()
        HostResolver.refreshOnce()
        elapsed = clock.monotonic() - started

        serial = 0.3 * len(names)
        self.assertLess(elapsed, serial / 2,
                        f"sweep took {elapsed:.2f}s; serial would be {serial:.2f}s")
        # And it still recorded every result correctly
        self.assertEqual(HostResolver.addressFor("good.local"), "10.0.0.9")
        for i in range(6):
            self.assertIsNone(HostResolver.addressFor(f"dead{i}.local"))

    def test_a_sweep_with_nothing_registered_is_harmless(self):
        self.useDns({})
        HostResolver.refreshOnce()
        self.assertEqual(HostResolver.snapshot(), {})


class SubstitutionTests(ResolverTestCase):
    def setUp(self):
        super().setUp()
        self.useDns({"hm4-wled.local": "192.168.1.135",
                     "player1.local": "192.168.1.235"})
        HostResolver.primeFrom(["hm4-wled.local", "player1.local"])
        HostResolver.refreshOnce()

    def test_the_url_forms_the_app_actually_builds(self):
        cases = {
            # WLED, which has no path separator before its query
            "http://hm4-wled.local/win&PL=8":
                ("http://192.168.1.135/win&PL=8", "hm4-wled.local"),
            # PiPlayer
            "http://player1.local/api/playlists/lobby/play":
                ("http://192.168.1.235/api/playlists/lobby/play", "player1.local"),
            "http://player1.local:8080/api/next":
                ("http://192.168.1.235:8080/api/next", "player1.local:8080"),
            "http://player1.local/api/loop-item?enabled=toggle":
                ("http://192.168.1.235/api/loop-item?enabled=toggle", "player1.local"),
            # MagicBand broadcast
            "http://player1.local/command":
                ("http://192.168.1.235/command", "player1.local"),
        }
        for url, expected in cases.items():
            with self.subTest(url=url):
                self.assertEqual(HostResolver.substitute(url), expected)

    def test_a_bare_host_url_keeps_its_shape(self):
        self.assertEqual(HostResolver.substitute("http://player1.local"),
                         ("http://192.168.1.235", "player1.local"))
        self.assertEqual(HostResolver.substitute("http://player1.local/"),
                         ("http://192.168.1.235/", "player1.local"))

    def test_an_unknown_or_literal_host_is_left_alone(self):
        for url in ("http://nobody.local/x", "http://192.168.1.99/win&PL=1",
                    "not a url", "", None, "ftp:/nope"):
            with self.subTest(url=repr(url)):
                self.assertEqual(HostResolver.substitute(url), (url, None))

    def test_a_url_with_credentials_is_left_alone(self):
        # Rewriting one correctly is not worth the risk, and the app does not
        # produce them
        url = "http://user:pw@player1.local/x"
        self.assertEqual(HostResolver.substitute(url), (url, None))


class RestIntegrationTests(ResolverTestCase):
    def test_a_call_uses_the_cached_address_and_keeps_the_host_header(self):
        import rest
        from rest import UnreachableHosts
        UnreachableHosts.reset()
        self.addCleanup(UnreachableHosts.reset)
        self.useDns({"hm4-wled.local": "192.168.1.135"})
        HostResolver.register("hm4-wled.local")
        HostResolver.refreshOnce()

        seen = {}

        class Recorder:
            def request(self, **kwargs):
                seen.update(kwargs)
                return ({"status": "200"}, b"")

        original = rest.RestHelpers._http_obj
        rest.RestHelpers._http_obj = Recorder()
        try:
            self.assertTrue(rest.RestHelpers.makeRestCall("http://hm4-wled.local/win&PL=8"))
        finally:
            rest.RestHelpers._http_obj = original
        self.assertEqual(seen["uri"], "http://192.168.1.135/win&PL=8")
        self.assertEqual(seen["headers"].get("Host"), "hm4-wled.local")

    def test_an_unresolved_name_is_passed_through_unchanged(self):
        import rest
        from rest import UnreachableHosts
        UnreachableHosts.reset()
        self.addCleanup(UnreachableHosts.reset)
        seen = {}

        class Recorder:
            def request(self, **kwargs):
                seen.update(kwargs)
                return ({"status": "200"}, b"")

        original = rest.RestHelpers._http_obj
        rest.RestHelpers._http_obj = Recorder()
        try:
            rest.RestHelpers.makeRestCall("http://unknown.local/x")
        finally:
            rest.RestHelpers._http_obj = original
        self.assertEqual(seen["uri"], "http://unknown.local/x")
        self.assertNotIn("Host", seen["headers"])


class PersistenceTests(ResolverTestCase):
    def setUp(self):
        super().setUp()
        import tempfile, os
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "resolver-cache.json")
        self.addCleanup(lambda: __import__("shutil").rmtree(self.dir, ignore_errors=True))

    def test_addresses_survive_a_restart(self):
        # The point: a reader that reboots while mDNS is not answering must
        # still reach its devices
        self.useDns({"hm4-wled.local": "192.168.1.135",
                     "player1.local": "192.168.1.235"})
        HostResolver.primeFrom(["hm4-wled.local", "player1.local"])
        HostResolver.refreshOnce()
        self.assertTrue(HostResolver.saveCache(self.path))

        HostResolver.reset()                       # as if restarted
        self.useDns({})                            # ...with mDNS dead
        self.assertEqual(HostResolver.loadCache(self.path), 2)
        self.assertEqual(HostResolver.addressFor("hm4-wled.local"), "192.168.1.135")
        self.assertEqual(HostResolver.addressFor("player1.local"), "192.168.1.235")

    def test_a_remembered_address_is_corrected_by_the_next_sweep(self):
        import json
        with open(self.path, "w") as handle:
            json.dump({"player1.local": {"ip": "192.168.1.99", "savedAt": 0}}, handle)
        HostResolver.loadCache(self.path)
        self.assertEqual(HostResolver.addressFor("player1.local"), "192.168.1.99")
        self.useDns({"player1.local": "192.168.1.235"})
        HostResolver.refreshOnce()
        self.assertEqual(HostResolver.addressFor("player1.local"), "192.168.1.235")

    def test_only_resolved_names_are_written(self):
        import json
        self.useDns({"good.local": "10.0.0.1"})
        HostResolver.primeFrom(["good.local", "bad.local"])
        HostResolver.refreshOnce()
        HostResolver.saveCache(self.path)
        with open(self.path) as handle:
            written = json.load(handle)
        self.assertEqual(list(written), ["good.local"])

    def test_a_missing_or_corrupt_cache_is_harmless(self):
        import os
        self.assertEqual(HostResolver.loadCache(os.path.join(self.dir, "nope.json")), 0)
        with open(self.path, "w") as handle:
            handle.write("{not json")
        self.assertEqual(HostResolver.loadCache(self.path), 0)

    def test_junk_entries_are_skipped(self):
        import json
        with open(self.path, "w") as handle:
            json.dump({"a.local": {"ip": "not-an-ip"},
                       "b.local": {"ip": None},
                       "c.local": "wrong shape",
                       "": {"ip": "10.0.0.1"},
                       "d.local": {"ip": "10.0.0.2"}}, handle)
        self.assertEqual(HostResolver.loadCache(self.path), 1)
        self.assertEqual(HostResolver.addressFor("d.local"), "10.0.0.2")

    def test_saving_with_nothing_resolved_writes_no_file(self):
        import os
        self.useDns({})
        HostResolver.primeFrom(["nope.local"])
        HostResolver.refreshOnce()
        self.assertFalse(HostResolver.saveCache(self.path))
        self.assertFalse(os.path.exists(self.path))


class ThreadTests(ResolverTestCase):
    def test_start_is_idempotent_and_stop_ends_the_thread(self):
        self.useDns({"a.local": "10.0.0.1"})
        HostResolver.register("a.local")
        try:
            self.assertTrue(HostResolver.start())
            self.assertFalse(HostResolver.start(), "a second thread was started")
            # It resolves without anyone asking
            deadline = threading.Event()
            for _ in range(50):
                if HostResolver.addressFor("a.local"):
                    break
                deadline.wait(0.02)
            self.assertEqual(HostResolver.addressFor("a.local"), "10.0.0.1")
        finally:
            HostResolver.stop()
        self.assertFalse(
            HostResolver._thread is not None and HostResolver._thread.is_alive())

    def test_registering_a_new_name_wakes_the_refresher(self):
        self.useDns({"b.local": "10.0.0.2"})
        original = HostResolver.REFRESH_INTERVAL
        try:
            HostResolver.REFRESH_INTERVAL = 3600  # only a wake can help
            HostResolver.start()
            HostResolver.register("b.local")
            waiter = threading.Event()
            for _ in range(100):
                if HostResolver.addressFor("b.local"):
                    break
                waiter.wait(0.02)
            self.assertEqual(HostResolver.addressFor("b.local"), "10.0.0.2")
        finally:
            HostResolver.stop()
            HostResolver.REFRESH_INTERVAL = original


if __name__ == "__main__":
    unittest.main()
