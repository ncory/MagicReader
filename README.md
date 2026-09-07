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
