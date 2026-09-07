"""Reports which audio path SDL actually chose, for the startup log.

pygame does not pick an audio backend; SDL does, and it does so silently. The
chain is:

    pygame.mixer -> SDL2 -> [driver] -> hardware

SDL tries its drivers in a fixed priority order and takes the first that
connects. On a Raspberry Pi OS Lite image nothing is listening on the
PulseAudio socket, so it falls through to ALSA and talks to the card directly.
Install a sound server - PipeWire on the Desktop image ships a PulseAudio
compatibility socket - and that first attempt starts succeeding instead, which
changes the path without changing any code. If the service then cannot reach
that socket, or the default sink is HDMI rather than the headphone jack, the
symptom is silence with nothing in the log to explain it.

Hence this module: one line at startup naming the driver and the devices SDL
can see. Every lookup is best-effort - this is diagnostics, and must never be
the reason the app fails to start.
"""
import ctypes
import ctypes.util
import glob
import os


def _loadSdl():
    """Returns a ctypes handle to the SDL2 that pygame is using, or None.

    pip's pygame wheels bundle their own SDL under pygame.libs/ rather than
    linking the system one, so look there first.
    """
    try:
        import pygame
        package_dir = os.path.dirname(os.path.abspath(pygame.__file__))
        bundled = glob.glob(
            os.path.join(os.path.dirname(package_dir), "pygame.libs", "libSDL2-2*.so*")
        )
        for candidate in bundled:
            try:
                return ctypes.CDLL(candidate)
            except OSError:
                continue
    except Exception:
        pass
    # Fall back to a system SDL, then to whatever is already in this process.
    for loader in (lambda: ctypes.CDLL(ctypes.util.find_library("SDL2")),
                   lambda: ctypes.CDLL(None)):
        try:
            handle = loader()
            handle.SDL_GetCurrentAudioDriver
            return handle
        except Exception:
            continue
    return None


def currentDriver():
    """Returns the SDL audio driver name in use ('alsa', 'pulseaudio', ...)."""
    sdl = _loadSdl()
    if sdl is None:
        return None
    try:
        sdl.SDL_GetCurrentAudioDriver.restype = ctypes.c_char_p
        name = sdl.SDL_GetCurrentAudioDriver()
        return name.decode() if name else None
    except Exception:
        return None


def availableDrivers():
    """Returns the drivers compiled into this SDL build, in priority order."""
    sdl = _loadSdl()
    if sdl is None:
        return []
    try:
        sdl.SDL_GetNumAudioDrivers.restype = ctypes.c_int
        sdl.SDL_GetAudioDriver.restype = ctypes.c_char_p
        sdl.SDL_GetAudioDriver.argtypes = [ctypes.c_int]
        return [sdl.SDL_GetAudioDriver(i).decode()
                for i in range(sdl.SDL_GetNumAudioDrivers())]
    except Exception:
        return []


def outputDevices():
    """Returns the playback devices SDL can see, first being its default."""
    sdl = _loadSdl()
    if sdl is None:
        return []
    try:
        sdl.SDL_GetNumAudioDevices.restype = ctypes.c_int
        sdl.SDL_GetNumAudioDevices.argtypes = [ctypes.c_int]
        sdl.SDL_GetAudioDeviceName.restype = ctypes.c_char_p
        sdl.SDL_GetAudioDeviceName.argtypes = [ctypes.c_int, ctypes.c_int]
        count = sdl.SDL_GetNumAudioDevices(0)      # 0 = playback, not capture
        names = []
        for i in range(max(count, 0)):
            name = sdl.SDL_GetAudioDeviceName(i, 0)
            if name:
                names.append(name.decode())
        return names
    except Exception:
        return []


def describe() -> str:
    """One line for the startup log. Never raises."""
    try:
        import pygame
        pygame_version = getattr(getattr(pygame, "version", None), "ver", "?")
        try:
            sdl_version = ".".join(str(v) for v in pygame.get_sdl_version())
        except Exception:
            sdl_version = "?"
        try:
            init = pygame.mixer.get_init()
        except Exception:
            init = None
    except Exception:
        return "Audio backend: unavailable"

    driver = currentDriver() or "unknown"
    # Joined with " | " rather than commas: ALSA device names contain commas
    # themselves ("bcm2835 Headphones, bcm2835 Headphones" is card, device),
    # which makes a comma-separated line look like it is repeating itself.
    parts = [f"pygame {pygame_version}", f"SDL {sdl_version}", f"driver: {driver}"]
    if init:
        frequency, size, channels = init[0], init[1], init[2]
        layout = "mono" if channels == 1 else f"{channels}ch"
        parts.append(f"{frequency}Hz {abs(size)}-bit {layout}")
    devices = outputDevices()
    if devices:
        # The first is SDL's default - the one that will actually play.
        more = f" (+{len(devices) - 1} more)" if len(devices) > 1 else ""
        parts.append(f'device: "{devices[0]}"{more}')
    return "Audio backend: " + " | ".join(parts)


def describeDrivers() -> str:
    """Second log line: what this SDL build could have used, in order."""
    drivers = availableDrivers()
    if not drivers:
        return "Audio drivers: unknown"
    return ("Audio drivers compiled in (priority order): " + ", ".join(drivers))
