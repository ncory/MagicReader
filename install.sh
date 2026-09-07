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
sudo apt-get install -y python3 python3-pip python3-venv git
# Optional: only useful if you later rebuild the venv with system site packages.
# Not fatal if the package name has changed, since pygame comes from pip below.
sudo apt-get install -y python3-pygame || echo "python3-pygame unavailable - continuing (pygame is installed via pip)"

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

##### Choose the GPIO backend
# Two different packages install a module named RPi.GPIO, and they cannot both
# be present. The original RPi.GPIO mmaps /dev/gpiomem and uses the sysfs GPIO
# interface; Trixie's kernel dropped sysfs GPIO, and the Pi 5 has no
# /dev/gpiomem at all. rpi-lgpio is a drop-in replacement on top of the
# gpiochip character device that covers everything this app uses.
# Override with MAGICREADER_GPIO_PACKAGE=RPi.GPIO or =rpi-lgpio to force one.
DEBIAN_VERSION="$(. /etc/os-release && echo "${VERSION_ID:-0}")"
if [ -n "${MAGICREADER_GPIO_PACKAGE:-}" ]; then
    GPIO_PACKAGE="$MAGICREADER_GPIO_PACKAGE"
    GPIO_REASON="forced by MAGICREADER_GPIO_PACKAGE"
elif [ "$DEBIAN_VERSION" -ge 13 ] 2>/dev/null; then
    GPIO_PACKAGE="rpi-lgpio"
    GPIO_REASON="Debian $DEBIAN_VERSION (Trixie or newer) has no sysfs GPIO"
elif [ ! -e /dev/gpiomem ]; then
    GPIO_PACKAGE="rpi-lgpio"
    GPIO_REASON="no /dev/gpiomem on this board"
else
    GPIO_PACKAGE="RPi.GPIO"
    GPIO_REASON="Debian $DEBIAN_VERSION with /dev/gpiomem present"
fi
echo "GPIO backend: $GPIO_PACKAGE ($GPIO_REASON)"

##### Install PIP package requirements
pip install "$GPIO_PACKAGE" pygame Flask waitress httplib2 spidev ordered_enum mfrc522 pyserial

##### Confirm the GPIO backend actually imports before going further
if ! python -c "import RPi.GPIO" 2>/dev/null; then
    echo "ERROR: '$GPIO_PACKAGE' installed but 'import RPi.GPIO' failed." >&2
    echo "Try the other backend: MAGICREADER_GPIO_PACKAGE=<other> re-run this script." >&2
    exit 1
fi
PYTHONPATH="$TARGET_DIR/magicreader" python -c \
    "import gpioBackend; print(gpioBackend.describe())" \
    || echo "(backend details unavailable until the app runs)"

##### Install services
"$TARGET_DIR/service-install.sh" --no-start

##### Finished
echo "Finished installing MagicReader. Please reboot your Raspberry Pi to apply SPI changes; MagicReader will start automatically after reboot."
