"""jsonStore: writes survive a power cut, and a bad file is recoverable.

The data files are rewritten every time the web UI changes something. Writing
in place truncates first, so a cut at the wrong moment used to leave a partial
file - and a partial file stopped the service from starting at all.
"""
import json
import os
import shutil
import stat
import tempfile
import threading
import unittest

import _support  # noqa: F401
import jsonStore


class AtomicWriteTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "bands.json")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    @staticmethod
    def read(path):
        with open(path) as handle:
            return json.load(handle)

    @staticmethod
    def write(path, text):
        with open(path, "w") as handle:
            handle.write(text)

    def test_write_keeps_previous_contents_as_backup(self):
        self.assertTrue(jsonStore.saveJsonAtomic(self.path, {"gen": 1}))
        self.assertFalse(os.path.exists(self.path + ".bak"),
                         "first write should not produce a backup")
        self.assertTrue(jsonStore.saveJsonAtomic(self.path, {"gen": 2}))
        self.assertEqual(self.read(self.path), {"gen": 2})
        self.assertEqual(self.read(self.path + ".bak"), {"gen": 1})

    def test_no_temp_files_left_behind(self):
        jsonStore.saveJsonAtomic(self.path, {"gen": 1})
        leftovers = [f for f in os.listdir(self.dir) if f.startswith(".tmp-")]
        self.assertEqual(leftovers, [])

    def test_truncated_file_is_recovered_from_backup(self):
        jsonStore.saveJsonAtomic(self.path, {"gen": 1})
        jsonStore.saveJsonAtomic(self.path, {"gen": 2})
        with open(self.path, "w") as f:      # a cut partway through a write
            f.write('{"gen": 2, "trunca')
        self.assertEqual(jsonStore.loadJson(self.path), {"gen": 1})

    def test_corrupt_file_is_never_copied_over_a_good_backup(self):
        # Without this guard, recovering from a corrupt file and then saving
        # would overwrite the good .bak with the corrupt content, leaving
        # nothing usable.
        jsonStore.saveJsonAtomic(self.path, {"gen": 1})
        jsonStore.saveJsonAtomic(self.path, {"gen": 2})
        with open(self.path, "w") as f:
            f.write("not json at all")
        jsonStore.saveJsonAtomic(self.path, {"gen": 3})
        self.assertEqual(self.read(self.path), {"gen": 3})
        self.assertEqual(self.read(self.path + ".bak"), {"gen": 1},
                         "backup was clobbered with corrupt content")

    def test_both_files_unreadable_returns_none_rather_than_raising(self):
        jsonStore.saveJsonAtomic(self.path, {"gen": 1})
        jsonStore.saveJsonAtomic(self.path, {"gen": 2})
        self.write(self.path, "garbage")
        self.write(self.path + ".bak", "garbage")
        self.assertIsNone(jsonStore.loadJson(self.path))

    def test_failed_write_leaves_the_original_intact(self):
        jsonStore.saveJsonAtomic(self.path, {"keep": "me"})

        class Unserializable:
            pass

        self.assertFalse(jsonStore.saveJsonAtomic(self.path, {"bad": Unserializable()}))
        self.assertEqual(self.read(self.path), {"keep": "me"})
        self.assertEqual([f for f in os.listdir(self.dir) if f.startswith(".tmp-")], [])

    def test_permissions_of_the_replaced_file_are_preserved(self):
        # mkstemp() creates 0600; without carrying the mode over, every save
        # would quietly tighten permissions on the data files.
        for mode in (0o644, 0o664, 0o600):
            self.write(self.path, "{}")
            os.chmod(self.path, mode)
            jsonStore.saveJsonAtomic(self.path, {"a": 1})
            self.assertEqual(stat.S_IMODE(os.stat(self.path).st_mode), mode)

    def test_concurrent_readers_never_see_a_partial_file(self):
        jsonStore.saveJsonAtomic(self.path, {"n": 0})
        stop = threading.Event()
        torn = []

        def writer(n):
            while not stop.is_set():
                jsonStore.saveJsonAtomic(self.path, {"n": n, "pad": "x" * 5000})

        def reader():
            while not stop.is_set():
                data = jsonStore.loadJson(self.path, useBackup=False)
                if data is None or "n" not in data:
                    torn.append(data)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(3)]
        threads += [threading.Thread(target=reader) for _ in range(3)]
        for t in threads:
            t.start()
        stop.wait(1.0)
        stop.set()
        for t in threads:
            t.join()
        self.assertEqual(torn, [], f"{len(torn)} torn reads")


class SeedingTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self._realDataDir = jsonStore.DATA_DIR
        jsonStore.DATA_DIR = self.dir
        shutil.copyfile(
            os.path.join(_support.REPO_DIR, "data", "sequences.default.json"),
            os.path.join(self.dir, "sequences.default.json"),
        )

    def tearDown(self):
        jsonStore.DATA_DIR = self._realDataDir
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_missing_runtime_file_is_created_from_the_template(self):
        target = os.path.join(self.dir, "sequences.json")
        self.assertFalse(os.path.exists(target))
        self.assertTrue(jsonStore.seedDataFileFromDefault("sequences.json"))
        with open(target) as handle:
            self.assertIn("welcome", json.load(handle))

    def test_existing_file_is_never_overwritten(self):
        jsonStore.saveJsonAtomic(jsonStore.dataPath("sequences.json"), {"mine": "edited"})
        self.assertTrue(jsonStore.seedDataFileFromDefault("sequences.json"))
        with open(os.path.join(self.dir, "sequences.json")) as handle:
            self.assertEqual(json.load(handle), {"mine": "edited"})

    def test_missing_template_reports_failure(self):
        self.assertFalse(jsonStore.seedDataFileFromDefault("nosuchthing.json"))


if __name__ == "__main__":
    unittest.main()
