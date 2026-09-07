"""Identifies which library is providing the RPi.GPIO API, and what it needs.

Two different packages install a module named RPi.GPIO and they cannot both be
present at once:

  RPi.GPIO   the original. Talks to the hardware by mmap'ing /dev/gpiomem, and
             uses the sysfs GPIO interface for edge detection. Shipped with
             Raspberry Pi OS through Bookworm.
  rpi-lgpio  a drop-in replacement that implements the same API on top of the
             kernel's gpiochip character device. Needed from Trixie onward,
             where the sysfs interface is gone, and on the Pi 5, whose RP1
             means there is no /dev/gpiomem at all.

The app's own GPIO use is small enough to work on either - setmode, setup,
output, getmode, cleanup, setwarnings and the constants, with no edge detection
or PWM - so nothing here switches behaviour. This module exists so the hardware
probe checks for the right device node, and so the log says which stack is
actually in use when something goes wrong.
"""
import importlib.metadata
import os

# The distribution names each implementation registers under.
LGPIO_DISTRIBUTIONS = ("rpi-lgpio",)
CLASSIC_DISTRIBUTIONS = ("rpi-gpio", "RPi.GPIO")

# mmap'd memory devices, used by the classic library. gpiomem0 is where the
# Pi 5 puts the equivalent of the older gpiomem.
MEMORY_DEVICES = ("/dev/gpiomem", "/dev/gpiomem0")
# Character devices, used by rpi-lgpio. It defaults to chip 4 on a Pi 5 and
# chip 0 everywhere else.
CHARACTER_DEVICES = ("/dev/gpiochip0", "/dev/gpiochip4")


def _installed(names):
    for name in names:
        try:
            return name, importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            continue
        except Exception:
            continue
    return None, None


def describeBackend() -> tuple:
    """Returns (kind, distribution, version).

    kind is 'lgpio', 'classic' or 'unknown'. 'unknown' is not an error - it
    just means neither distribution registered metadata we recognise, so the
    device check falls back to accepting any GPIO device node.
    """
    name, version = _installed(LGPIO_DISTRIBUTIONS)
    if name is not None:
        return "lgpio", name, version
    name, version = _installed(CLASSIC_DISTRIBUTIONS)
    if name is not None:
        return "classic", name, version
    return "unknown", None, None


def requiredGpioDevices() -> tuple:
    """Returns the device nodes that would satisfy the installed backend.

    Any one of them existing is enough - which is why the probe checks for a
    set rather than the single hardcoded /dev/gpiomem it used to.
    """
    kind, _, _ = describeBackend()
    if kind == "lgpio":
        return CHARACTER_DEVICES
    if kind == "classic":
        return MEMORY_DEVICES
    return MEMORY_DEVICES + CHARACTER_DEVICES


def findGpioDevice():
    """Returns the first present device node the backend can use, or None."""
    for device in requiredGpioDevices():
        if os.path.exists(device):
            return device
    return None


def describe() -> str:
    """One line for the startup log, so a failure elsewhere is diagnosable."""
    kind, name, version = describeBackend()
    if kind == "unknown":
        library = "unrecognised RPi.GPIO provider"
    else:
        library = f"{name} {version}"
    device = findGpioDevice() or "none found"
    return f"GPIO backend: {library} ({kind}), device: {device}"
