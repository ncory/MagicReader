#!/bin/bash
set -euo pipefail

# This is the installer script for MagicReader

### CONFIG
REPO_URL="https://github.com/ncory/MagicReader.git"
# Absolute, and based on the invoking user's home rather than a hardcoded
# /home/pi - recent Raspberry Pi OS images ask for a username at flash time and
# do not create a "pi" user by default.
TARGET_DIR="$HOME/magicreader"
VENV_NAME="$TARGET_DIR/.venv"

if [ "$(id -u)" -eq 0 ]; then
    echo "ERROR: run this installer as your normal user, not root." >&2
    echo "It calls sudo itself where it needs to." >&2
    exit 1
fi

# Enable SPI using raspi-config
sudo raspi-config nonint do_spi 0
echo "SPI enabled. Reboot required for changes to take effect."

##### Update Raspberry Pi OS
sudo apt-get update
sudo apt-get upgrade -y
# Install pre-requisite packages
sudo apt-get install -y python3 python3-pip python3-venv python3-pygame git

##### Clone git repo to get source code
git clone "$REPO_URL" "$TARGET_DIR"
echo "Repository cloned successfully into $TARGET_DIR"
# Change owner for repo folder
sudo chown -R "$(id -un):$(id -gn)" "$TARGET_DIR"

##### Create Python virtual environment
echo "Creating Python virtual environment '$VENV_NAME'..."
python3 -m venv "$VENV_NAME"
echo "Virtual environment '$VENV_NAME' created successfully."
# Modify permissions on virtual environment
#sudo chmod -R a+rwx "$VENV_NAME"
# Activate the virtual environment
echo "Activating virtual environment..."
source "$VENV_NAME/bin/activate"
echo "Virtual environment activated."

##### Install PIP package requirements
pip install RPi.GPIO pygame Flask waitress httplib2 spidev ordered_enum mfrc522 pyserial

##### Install services
"$TARGET_DIR/service-install.sh" --no-start

##### Finished
echo "Finished installing MagicReader. Please reboot your Raspberry Pi to apply SPI changes; MagicReader will start automatically after reboot."
