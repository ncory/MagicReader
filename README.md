# MagicReader
A Raspberry Pi based RFID reader based on the MagicBand readers at Disney parks.


## Quick Install
1. Flash a fresh SD card with Raspberry Pi OS (Lite version is preferred.) Use Raspberry Pi Imager and pre-configure your WiFi network, login info, and enable SSH.
2. Boot the Pi and SSH into it
3. Run this command. It will download the installer script and run it in Bash as root. This will update the Pi, enable SPI, clone the code repo, setup the Python virtual environment, etc.
'''
sudo curl -sL "https://github.com/ncory/MagicReader/raw/refs/heads/main/install.sh" | bash
'''
