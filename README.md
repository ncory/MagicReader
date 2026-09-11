# MagicReader
A Raspberry Pi based RFID reader based on the MagicBand readers at Disney parks.


## Quick Install
1. Flash a fresh SD card with Raspberry Pi OS (Lite version is preferred.) Use Raspberry Pi Imager and pre-configure your WiFi network, login info, and enable SSH.
2. Boot the Pi and SSH into it
3. Run this command as your normal user - not with sudo. The installer calls sudo itself where it needs to, and refuses to run as root because the service must not be owned by root. It updates the Pi, enables SPI, clones the repo into `~/magicreader`, sets up the Python virtual environment and installs the systemd services.
```
curl -sL "https://github.com/ncory/MagicReader/raw/refs/heads/main/install.sh" | bash
```
The install is not tied to a user named `pi`: it uses whichever account you created when flashing the card.

## Operating system support
Tested on Raspberry Pi OS Bookworm (Python 3.11) on a Pi 4.

The GPIO stack differs by release, so `install.sh` picks the backend to match
the machine and prints which one it chose:

| OS | GPIO package | Why |
| --- | --- | --- |
| Bookworm and earlier | `RPi.GPIO` | mmaps `/dev/gpiomem`; works as it always has |
| Trixie and later | `rpi-lgpio` | Trixie's kernel dropped the sysfs GPIO interface `RPi.GPIO` relies on |
| Pi 5, any OS | `rpi-lgpio` | the RP1 chip means there is no `/dev/gpiomem`, only `/dev/gpiomem0`-`4` |

`rpi-lgpio` is a drop-in replacement: it installs the same `RPi.GPIO` module
name on top of the kernel's gpiochip device, so no application code changes.
The two **cannot be installed at the same time**.

To force a choice:
```
MAGICREADER_GPIO_PACKAGE=rpi-lgpio bash install.sh
```

The app logs the backend it detected at startup, e.g.
`GPIO backend: rpi-lgpio 0.6 (lgpio), device: /dev/gpiochip0`. Check that line
first if the reader does not come up.

## Audio
Sound goes `pygame.mixer` -> SDL2 -> an audio driver -> the hardware. SDL picks
the driver itself, trying `pulseaudio` before `alsa` and taking the first that
connects. On a Lite image nothing is listening on the PulseAudio socket, so it
falls through to ALSA and talks to the card directly. PipeWire, which replaces
PulseAudio on the Desktop image, sits at that same layer - it is not a
replacement for anything in pygame, and needs no application code changes.

The app logs what SDL settled on at startup:
```
Audio backend: pygame 2.6.1 | SDL 2.28.4 | driver: alsa | 44100Hz 16-bit mono | device: "bcm2835 Headphones, bcm2835 Headphones" (+2 more)
Audio drivers compiled in (priority order): pulseaudio, alsa, dsp, disk, dummy
```
Check that line first if there is no sound. The two usual causes are SDL
connecting to a sound server the service cannot reach, and the default device
being HDMI rather than the headphone jack - the log shows both. To force ALSA,
uncomment `SDL_AUDIODRIVER=alsa` in `MagicReader.service.template` and re-run
`service-install.sh`.

## System menu: restart, reboot, shutdown
These run as separate systemd units (`MagicWand`, `MagicReboot`, `MagicShutdown`)
rather than as scripts spawned by the app. A process the app spawns lives in
`MagicReader.service`'s cgroup, so the `systemctl stop MagicReader.service` such
a script has to run first kills the script itself before it gets any further -
systemd's default `KillMode` is `control-group`. A separate unit gets its own
cgroup and survives.

The app runs unprivileged, so `service-install.sh` installs
`/etc/sudoers.d/magicreader` granting the service user passwordless sudo for
exactly those three `systemctl start` calls and nothing else.

**On Trixie, run `./service-install.sh` yourself and type your password when
asked.** Raspberry Pi OS through Bookworm gave the first user blanket
passwordless sudo; Trixie does not, so the installer cannot grant itself the
access it needs - it needs one password from you, once. Until then the System
menu buttons return `ok` and do nothing, because every `sudo` behind them is
waiting for a password nobody can type.

## Tests
```
./tests/run.sh              # or: PYTHON=.venv/bin/python ./tests/run.sh
```
Standard library only - no test dependency to install - and every
hardware-facing module is stubbed, so the suite is **safe to run on a reader
that is currently driving a show**: it never claims a GPIO pin or opens the
audio device. It runs the same on a laptop with none of the Pi packages
installed.

Add `-v` for per-test names, or `MAGICREADER_TEST_VERBOSE=1` to also see the
app's own log output, which is otherwise suppressed so failures stay readable.

What it covers: the RestQueue singleton and its shutdown drain, crash-safe JSON
writes and backup recovery, GPIO pin validation, sequence parsing and
fractional delays, Disney band detection, sound path resolution, the event
loop's exception guard, and that the shipped default data files are
self-consistent.
