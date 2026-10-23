"""Assigning sequences to several bands at once.

The Bands page sends {"bands": [...], "sequences": [...], "mode": ...} to
PUT /bands/sequences, which changes only the sequence lists - band names stay
- and writes bands.json once. If any band is missing, nothing changes.
"""
import copy
import json
import os
import shutil
import tempfile
import types
import unittest

import _support  # noqa: F401
import jsonStore
from bandManager import BandManager

BANDS = {
    "0453652AC05F80": {"name": "Blue", "sequences": ["welcome"]},
    "04BEA3F2B41190": {"name": "Plus", "sequences": ["welcome", "anthem"]},
    # Saved before bands could have several sequences
    "3611EE94": {"name": "Orange", "sequence": "anthem"},
    "unknown": {"name": "Unknown Bands", "sequences": ["welcome"]},
}


def manager():
    bands = BandManager()
    bands.bands = copy.deepcopy(BANDS)
    return bands


class AssignSequencesTests(unittest.TestCase):
    def test_replace_gives_every_band_exactly_the_sequences(self):
        bands = manager()
        self.assertEqual(bands.assignSequences(["0453652AC05F80", "04BEA3F2B41190"], ["fireworks", "anthem"]), [])
        self.assertEqual(bands.bands["0453652AC05F80"]["sequences"], ["fireworks", "anthem"])
        self.assertEqual(bands.bands["04BEA3F2B41190"]["sequences"], ["fireworks", "anthem"])

    def test_add_keeps_what_each_band_has_and_skips_duplicates(self):
        bands = manager()
        bands.assignSequences(["0453652AC05F80", "04BEA3F2B41190"], ["anthem", "fireworks"], "add")
        self.assertEqual(bands.bands["0453652AC05F80"]["sequences"], ["welcome", "anthem", "fireworks"])
        self.assertEqual(bands.bands["04BEA3F2B41190"]["sequences"], ["welcome", "anthem", "fireworks"])

    def test_remove_takes_the_sequences_off_where_present(self):
        bands = manager()
        bands.assignSequences(["0453652AC05F80", "04BEA3F2B41190"], ["welcome"], "remove")
        self.assertEqual(bands.bands["0453652AC05F80"]["sequences"], [])
        self.assertEqual(bands.bands["04BEA3F2B41190"]["sequences"], ["anthem"])

    def test_replace_with_nothing_clears_the_sequences(self):
        bands = manager()
        bands.assignSequences(["0453652AC05F80"], [])
        self.assertEqual(bands.bands["0453652AC05F80"]["sequences"], [])

    def test_names_and_unselected_bands_are_untouched(self):
        bands = manager()
        bands.assignSequences(["0453652AC05F80"], ["fireworks"])
        self.assertEqual(bands.bands["0453652AC05F80"]["name"], "Blue")
        self.assertEqual(bands.bands["04BEA3F2B41190"], BANDS["04BEA3F2B41190"])
        self.assertEqual(bands.bands["unknown"], BANDS["unknown"])

    def test_an_old_single_sequence_band_is_folded_into_a_list(self):
        bands = manager()
        bands.assignSequences(["3611EE94"], ["welcome"], "add")
        self.assertEqual(bands.bands["3611EE94"], {"name": "Orange", "sequences": ["anthem", "welcome"]})

    def test_the_fallback_entries_can_be_assigned_too(self):
        bands = manager()
        bands.assignSequences(["unknown"], ["fireworks"], "add")
        self.assertEqual(bands.bands["unknown"]["sequences"], ["welcome", "fireworks"])

    def test_a_missing_band_changes_nothing_and_is_reported(self):
        bands = manager()
        self.assertEqual(bands.assignSequences(["0453652AC05F80", "GONE"], ["fireworks"]), ["GONE"])
        self.assertEqual(bands.bands, BANDS)

    def test_junk_sequence_ids_are_dropped(self):
        bands = manager()
        bands.assignSequences(["0453652AC05F80"], ["a", "", None, 7, "a", "b"])
        self.assertEqual(bands.bands["0453652AC05F80"]["sequences"], ["a", "b"])

    def test_an_unknown_mode_is_refused(self):
        with self.assertRaises(ValueError):
            manager().assignSequences(["0453652AC05F80"], ["a"], "merge")


class ApiTests(unittest.TestCase):
    """PUT /bands/sequences through Flask's test client - needs Flask, as on a Pi."""

    @classmethod
    def setUpClass(cls):
        try:
            import flask  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("Flask is not installed")

    def setUp(self):
        import api
        self.dir = tempfile.mkdtemp()
        self.realDataDir = jsonStore.DATA_DIR
        jsonStore.DATA_DIR = self.dir
        self.bands = manager()
        captured = []
        realServe = api.serveApp
        api.serveApp = lambda app, port: captured.append(app)
        try:
            api.RunMagicApi(types.SimpleNamespace(band_manager=self.bands), port=0)
        finally:
            api.serveApp = realServe
        self.client = captured[0].test_client()

    def tearDown(self):
        jsonStore.DATA_DIR = self.realDataDir
        shutil.rmtree(self.dir)

    def put(self, body):
        return self.client.put("/bands/sequences", json=body).get_json()

    def saved(self):
        with open(os.path.join(self.dir, BandManager.FILENAME)) as f:
            return json.load(f)

    def test_a_change_is_saved_and_the_band_list_returned(self):
        result = self.put({"bands": ["0453652AC05F80", "3611EE94"], "sequences": ["fireworks"], "mode": "add"})
        self.assertEqual(result["result"], "ok")
        returned = {band["band_id"]: band["sequences"] for band in result["data"]}
        self.assertEqual(returned["0453652AC05F80"], ["welcome", "fireworks"])
        self.assertEqual(self.saved()["3611EE94"], {"name": "Orange", "sequences": ["anthem", "fireworks"]})

    def test_the_mode_defaults_to_replace(self):
        self.put({"bands": ["04BEA3F2B41190"], "sequences": ["fireworks"]})
        self.assertEqual(self.saved()["04BEA3F2B41190"]["sequences"], ["fireworks"])

    def test_a_missing_band_is_an_error_and_nothing_is_saved(self):
        result = self.put({"bands": ["0453652AC05F80", "GONE"], "sequences": ["fireworks"]})
        self.assertEqual(result["result"], "error")
        self.assertEqual(result["data"]["missing"], ["GONE"])
        self.assertFalse(os.path.exists(os.path.join(self.dir, BandManager.FILENAME)))
        self.assertEqual(self.bands.bands, BANDS)

    def test_bad_requests_are_errors(self):
        for body in ({"bands": [], "sequences": ["a"]},
                     {"sequences": ["a"]},
                     {"bands": ["0453652AC05F80"], "sequences": ["a"], "mode": "merge"},
                     ["0453652AC05F80"]):
            with self.subTest(body=body):
                result = self.put(body)
                self.assertEqual(result["result"], "error")
                self.assertIn("message", result["data"])
        self.assertEqual(self.bands.bands, BANDS)


if __name__ == "__main__":
    unittest.main()
