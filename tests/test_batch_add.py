"""Batch-add mode: every tap is saved as a band until the page says Done.

A new band is saved with its ID as its nickname and no sequences; a known one
is left alone. Taps are captured in the event loop, so none of them plays a
sequence while the mode is on, and the mode ends itself if the page stops
polling.
"""
import json
import os
import shutil
import tempfile
import threading
import types
import unittest

import _support  # noqa: F401
import jsonStore
from bandManager import BandManager
from batchAdd import BatchAdd
from helpers import AppEvent, AppEventType
from rfid import RfidRead
from test_event_loop import makeApp

NEW_BAND = "0453652AC05F80"
KNOWN_BAND = "3611EE94"


class UsesTempDataDir(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.realDataDir = jsonStore.DATA_DIR
        jsonStore.DATA_DIR = self.dir
        self.bands = BandManager()
        self.bands.bands = {KNOWN_BAND: {"name": "Orange", "sequences": ["welcome"]}}
        self.batch = BatchAdd(self.bands)

    def tearDown(self):
        jsonStore.DATA_DIR = self.realDataDir
        shutil.rmtree(self.dir)

    def saved(self):
        with open(os.path.join(self.dir, BandManager.FILENAME)) as f:
            return json.load(f)


class BatchAddTests(UsesTempDataDir):
    def test_a_new_band_is_saved_named_after_its_id(self):
        self.batch.start()
        read = self.batch.capture(NEW_BAND, True)
        self.assertEqual((read["status"], read["name"], read["seq"]), ("added", NEW_BAND, 1))
        self.assertEqual(self.saved()[NEW_BAND], {"name": NEW_BAND, "sequences": []})

    def test_a_known_band_is_left_alone(self):
        self.batch.start()
        read = self.batch.capture(KNOWN_BAND)
        self.assertEqual((read["status"], read["name"]), ("known", "Orange"))
        self.assertEqual(self.bands.bands[KNOWN_BAND], {"name": "Orange", "sequences": ["welcome"]})
        self.assertFalse(os.path.exists(os.path.join(self.dir, BandManager.FILENAME)))

    def test_the_same_new_band_twice_is_added_once(self):
        self.batch.start()
        self.assertEqual([self.batch.capture(NEW_BAND)["status"] for _ in range(2)], ["added", "known"])

    def test_a_failed_save_is_reported(self):
        self.bands.saveToFile = lambda: False
        self.batch.start()
        self.assertEqual(self.batch.capture(NEW_BAND)["status"], "error")

    def test_poll_returns_only_reads_after_the_given_one(self):
        self.batch.start()
        self.batch.capture(NEW_BAND)
        self.batch.capture(KNOWN_BAND)
        self.assertEqual([r["id"] for r in self.batch.poll(0)["reads"]], [NEW_BAND, KNOWN_BAND])
        self.assertEqual([r["id"] for r in self.batch.poll(1)["reads"]], [KNOWN_BAND])
        self.assertEqual(self.batch.poll(2), {"active": True, "reads": []})

    def test_starting_again_clears_the_previous_reads(self):
        self.batch.start()
        self.batch.capture(NEW_BAND)
        self.batch.start()
        self.assertEqual(self.batch.poll(0)["reads"], [])

    def test_stop_ends_the_mode(self):
        self.batch.start()
        self.batch.stop()
        self.assertFalse(self.batch.isActive())
        self.assertFalse(self.batch.poll(0)["active"])

    def test_the_mode_ends_itself_when_the_page_stops_polling(self):
        self.batch.start()
        self.batch.lastPoll -= BatchAdd.IDLE_TIMEOUT_SECONDS + 1
        self.assertFalse(self.batch.isActive())

    def test_polling_keeps_the_mode_alive(self):
        self.batch.start()
        self.batch.lastPoll -= BatchAdd.IDLE_TIMEOUT_SECONDS - 1
        self.batch.poll(0)
        self.batch.lastPoll -= 2
        self.assertTrue(self.batch.isActive())


class EventLoopTests(UsesTempDataDir):
    def runTap(self, batchActive):
        app = makeApp()
        app.band_manager = self.bands
        app.batch_add = self.batch
        app.allowRead = True
        played = []
        app.onReadMagicBand = lambda band_id, isDisney: played.append(band_id)
        if batchActive:
            self.batch.start()
        thread = threading.Thread(target=app.runEventQueue, daemon=True)
        thread.start()
        try:
            app.event_queue.put((5, AppEvent(AppEventType.ReadRfid, RfidRead(NEW_BAND, True))))
            threading.Event().wait(0.3)
        finally:
            app.is_active = False
            app.event_queue.put((1, AppEvent(AppEventType.Blackout, False)))
        return played

    def test_a_tap_during_batch_add_is_captured_and_plays_nothing(self):
        self.assertEqual(self.runTap(batchActive=True), [])
        self.assertEqual([r["id"] for r in self.batch.poll(0)["reads"]], [NEW_BAND])
        self.assertIn(NEW_BAND, self.saved())

    def test_a_tap_with_batch_add_off_plays_as_usual(self):
        self.assertEqual(self.runTap(batchActive=False), [NEW_BAND])
        self.assertNotIn(NEW_BAND, self.bands.bands)


class ApiTests(UsesTempDataDir):
    """The /bands/batch routes through Flask's test client - needs Flask, as on a Pi."""

    @classmethod
    def setUpClass(cls):
        try:
            import flask  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("Flask is not installed")

    def setUp(self):
        super().setUp()
        import api
        captured = []
        realServe = api.serveApp
        api.serveApp = lambda app, port: captured.append(app)
        try:
            api.RunMagicApi(types.SimpleNamespace(band_manager=self.bands, batch_add=self.batch), port=0)
        finally:
            api.serveApp = realServe
        self.client = captured[0].test_client()

    def test_start_poll_and_stop(self):
        self.assertEqual(self.client.post("/bands/batch/start").get_json()["result"], "ok")
        self.batch.capture(NEW_BAND)
        self.batch.capture(KNOWN_BAND)
        data = self.client.get("/bands/batch?after=1").get_json()["data"]
        self.assertTrue(data["active"])
        self.assertEqual([(r["id"], r["status"]) for r in data["reads"]], [(KNOWN_BAND, "known")])
        self.assertEqual(self.client.post("/bands/batch/stop").get_json()["result"], "ok")
        self.assertFalse(self.client.get("/bands/batch").get_json()["data"]["active"])


if __name__ == "__main__":
    unittest.main()
