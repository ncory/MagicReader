"""Shared setup for the test suite.

Two jobs:

1. Put ``magicreader/`` on sys.path. The app's modules import each other flat
   (``import jsonStore``), so they need that directory on the path rather than
   the repo root.

2. Replace every module that talks to hardware with a stub, *always* - even on
   a Pi where the real ones are installed. Tests must be safe to run on a
   reader that is currently driving a show: importing the real RPi.GPIO and
   calling setup() would claim pins out from under the running service, and
   the real pygame would open the audio device. Stubbing also makes the tests
   runnable on a laptop, which is where they usually get run.

Import this module before importing anything from the app.
"""
import atexit
import os
import sys
import types

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(REPO_DIR, "magicreader")


def _stubModule(name):
    module = types.ModuleType(name)
    sys.modules[name] = module
    return module


def installHardwareStubs():
    """Installs fakes for the hardware-facing dependencies. Idempotent."""
    if sys.modules.get("_magicreader_stubs_installed"):
        return
    sys.modules["_magicreader_stubs_installed"] = True

    # --- RPi.GPIO -------------------------------------------------------
    rpi = _stubModule("RPi")
    gpio = _stubModule("RPi.GPIO")
    rpi.GPIO = gpio
    # Sentinels, not ints, so a test that mixes up a pin and a mode is obvious
    for constant in ("BOARD", "BCM", "OUT", "IN", "HIGH", "LOW"):
        setattr(gpio, constant, f"<{constant}>")
    gpio.calls = []

    def _record(name):
        def fn(*args, **kwargs):
            gpio.calls.append((name, args, kwargs))
        return fn

    for fn_name in ("setmode", "setup", "output", "cleanup", "setwarnings"):
        setattr(gpio, fn_name, _record(fn_name))
    gpio.getmode = lambda: None

    # --- spidev / mfrc522 ------------------------------------------------
    spidev = _stubModule("spidev")
    spidev.SpiDev = lambda *a, **k: None
    mfrc522 = _stubModule("mfrc522")
    mfrc522.SimpleMFRC522 = object

    # --- pygame ----------------------------------------------------------
    pygame = _stubModule("pygame")
    pygame.loaded = []
    music = types.SimpleNamespace(
        stop=lambda: None,
        load=lambda path: pygame.loaded.append(("music", path)),
        play=lambda *a, **k: None,
    )
    pygame.mixer = types.SimpleNamespace(
        pre_init=lambda *a, **k: None,
        init=lambda *a, **k: None,
        stop=lambda: None,
        get_init=lambda: (44100, -16, 1),
        get_num_channels=lambda: 8,
        Sound=lambda path, *a, **k: pygame.loaded.append(("sound", path)) or object(),
        music=music,
    )
    pygame.init = lambda *a, **k: None
    pygame.error = Exception
    pygame.version = types.SimpleNamespace(ver="stub")
    pygame.get_sdl_version = lambda: (0, 0, 0)

    # --- pure-python deps that may not be installed on a laptop ----------
    if "httplib2" not in sys.modules:
        try:
            import httplib2  # noqa: F401
        except ImportError:
            http = _stubModule("httplib2")
            http.Http = lambda *a, **k: None
    if "ordered_enum" not in sys.modules:
        try:
            import ordered_enum  # noqa: F401
        except ImportError:
            import enum
            module = _stubModule("ordered_enum")

            class OrderedEnum(enum.Enum):
                def __lt__(self, other):
                    if self.__class__ is not other.__class__:
                        return NotImplemented
                    members = list(type(self))
                    return members.index(self) < members.index(other)

            module.OrderedEnum = OrderedEnum
    if "serial" not in sys.modules:
        try:
            import serial  # noqa: F401
        except ImportError:
            _stubModule("serial").Serial = lambda *a, **k: None


def silenceAppOutput():
    """Sends the app's own print() output to nowhere.

    The app logs generously to stdout, which buries the test report. unittest
    writes its results to stderr, so dropping stdout keeps failures readable.
    Set MAGICREADER_TEST_VERBOSE=1 to see the app output while debugging.
    """
    if os.environ.get("MAGICREADER_TEST_VERBOSE"):
        return
    if getattr(sys, "_magicreader_stdout_silenced", False):
        return
    sys._magicreader_stdout_silenced = True
    sink = open(os.devnull, "w")
    sys.stdout = sink
    atexit.register(sink.close)


def setUpPath():
    installHardwareStubs()
    silenceAppOutput()
    if APP_DIR not in sys.path:
        sys.path.insert(0, APP_DIR)


setUpPath()
