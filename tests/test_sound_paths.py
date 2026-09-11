"""SoundManager path handling.

SOUND_DIR used to be the relative string 'Sounds', and loadSound built paths by
prepending the literal "Sounds/". That worked only because the systemd unit
sets WorkingDirectory - started from anywhere else, the app found no sounds at
all. Paths now come from the module location.
"""
import os
import unittest

import _support  # noqa: F401
import appPaths
from soundManager import SoundManager


class SoundPathTests(unittest.TestCase):
    def setUp(self):
        self.sounds = SoundManager()

    def test_sound_dir_is_absolute_and_inside_the_repo(self):
        self.assertTrue(os.path.isabs(self.sounds.SOUND_DIR))
        self.assertEqual(self.sounds.SOUND_DIR, appPaths.SOUNDS_DIR)
        self.assertEqual(os.path.basename(self.sounds.SOUND_DIR), "Sounds")

    def test_resolution_does_not_depend_on_the_working_directory(self):
        original = os.getcwd()
        try:
            os.chdir(os.path.sep)
            self.assertTrue(os.path.isabs(self.sounds.getSoundsDirectory()))
            self.assertEqual(
                self.sounds.getSoundFilePath("TapIn.wav"),
                os.path.join(appPaths.SOUNDS_DIR, "TapIn.wav"),
            )
        finally:
            os.chdir(original)

    def test_a_name_is_accepted_bare_prefixed_or_absolute(self):
        for given in ("TapIn.wav",
                      "Sounds/TapIn.wav",
                      os.path.join(appPaths.SOUNDS_DIR, "TapIn.wav")):
            with self.subTest(given=given):
                self.assertEqual(self.sounds.normalizeSoundFilename(given), "TapIn.wav")

    def test_path_traversal_is_rejected(self):
        for bad in ("../secret.wav", "/etc/passwd", "..", ".", ".hidden.wav",
                    "sub/dir.wav", "a\\b.wav", "", None, 5):
            with self.subTest(bad=repr(bad)):
                normalized = self.sounds.normalizeSoundFilename(bad)
                self.assertTrue(normalized is None or "/" not in normalized)
                self.assertIsNone(self.sounds.getSoundFilePath(bad))

    def test_only_known_audio_extensions_are_valid(self):
        for good in ("a.wav", "b.MP3", "c.ogg", "d.flac", "e.m4a", "f.aac"):
            with self.subTest(name=good):
                self.assertTrue(self.sounds.isValidSoundFilename(good))
        for bad in ("script.sh", "notes.txt", "noextension", "a.wav.exe"):
            with self.subTest(name=bad):
                self.assertFalse(self.sounds.isValidSoundFilename(bad))

    def test_the_sounds_the_repo_ships_are_present(self):
        # The default settings and sequence templates reference these; if one
        # is renamed, a fresh install gets a dangling sound reference.
        for name in ("Error.wav", "Startup.wav", "TapIn.wav"):
            with self.subTest(name=name):
                self.assertTrue(os.path.exists(self.sounds.getSoundFilePath(name)))


class ShippedDefaultsTests(unittest.TestCase):
    """The templates a fresh install is seeded from must be self-consistent."""

    def setUp(self):
        import json
        data = os.path.join(_support.REPO_DIR, "data")

        def load(name):
            with open(os.path.join(data, name)) as handle:
                return json.load(handle)

        self.bands = load("bands.default.json")
        self.sequences = load("sequences.default.json")
        self.settings = load("settings.default.json")["settings"]

    def test_no_band_points_at_a_sequence_that_does_not_exist(self):
        for band_id, band in self.bands.items():
            for seq_id in band.get("sequences", []):
                with self.subTest(band=band_id, sequence=seq_id):
                    self.assertIn(seq_id, self.sequences)

    def test_every_sound_the_defaults_reference_is_shipped(self):
        sounds = SoundManager()
        referenced = set()
        for sequence in self.sequences.values():
            for action in sequence.get("actions", []):
                if action.get("type") in ("soundFile", "musicFile"):
                    referenced.add(action["data"])
        for key in ("sound_startup", "sound_waiting", "sound_error"):
            if self.settings.get(key):
                referenced.add(self.settings[key])
        for name in sorted(referenced):
            with self.subTest(sound=name):
                self.assertTrue(os.path.exists(sounds.getSoundFilePath(name)))

    def test_defaults_use_the_current_sequence_schema(self):
        # music / wled_preset / wait_delay were silently ignored by the parser.
        allowed = {"name", "actions", "cancel_allowed"}
        for seq_id, sequence in self.sequences.items():
            with self.subTest(sequence=seq_id):
                self.assertEqual(set(sequence) - allowed, set())


if __name__ == "__main__":
    unittest.main()
