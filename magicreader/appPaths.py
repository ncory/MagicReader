"""Absolute paths for the app's on-disk directories.

Everything is derived from this file's own location rather than the process
working directory, so the app behaves the same whether it is started by
systemd (which sets WorkingDirectory), by hand from another directory, or
under a debugger.

Layout: <repo>/magicreader/appPaths.py -> <repo>/data, <repo>/Sounds
"""
import os

APP_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(APP_DIR)
DATA_DIR = os.path.join(REPO_DIR, 'data')
SOUNDS_DIR = os.path.join(REPO_DIR, 'Sounds')
