#!/bin/bash

# This is the installer script for MagicReader

### CONFIG
REPO_URL="https://github.com/ncory/MagicReader.git"
TARGET_DIR="magicreader"
VENV_NAME="magicreader/.venv"

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
# Check if the clone was successful
if [ $? -eq 0 ]; then
  echo "Repository cloned successfully into $TARGET_DIR"
else
  echo "Error: Failed to clone the repository."
  exit 1
fi
# Change owner for rep folder
sudo chown -R pi "$TARGET_DIR"

##### Create Python virtual environment
echo "Creating Python virtual environment '$VENV_NAME'..."
python3 -m venv "$VENV_NAME"
# Check if the virtual environment was created successfully
if [ -d "$VENV_NAME" ]; then
    echo "Virtual environment '$VENV_NAME' created successfully."
else
    echo "Error: Failed to create virtual environment '$VENV_NAME'."
    exit 1
fi
# Modify permissions on virtual environment
#sudo chmod -R a+rwx "$VENV_NAME"
# Activate the virtual environment
echo "Activating virtual environment..."
source "$VENV_NAME/bin/activate"
echo "Virtual environment activated."

#### Install PIP package requirements
pip install RPi.GPIO pygame Flask httplib2 spidev ordered_enum mfrc522 pyserial
