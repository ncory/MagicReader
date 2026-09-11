#!/bin/bash
set -euo pipefail

# Installs the MagicReader systemd units.
#
# The unit files that reference a user or a path are templates: this script
# renders them for whoever is installing and wherever the repo actually lives,
# so the app is not tied to a user named "pi" with a home at /home/pi. Recent
# Raspberry Pi OS images ask for a username at flash time and do not create
# "pi" by default.

SERVICE_DIR="/etc/systemd/system"
START_SERVICE="true"

if [ "${1:-}" = "--no-start" ]; then
    START_SERVICE="false"
fi

# Absolute path of the directory holding this script - the repo root.
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Run the service as whoever invoked us. Under sudo that is SUDO_USER, since
# the units must not end up running as root.
SERVICE_USER="${SUDO_USER:-$(id -un)}"
if [ "$SERVICE_USER" = "root" ]; then
    echo "ERROR: refusing to install MagicReader to run as root." >&2
    echo "Run this script as the user that should own the service." >&2
    exit 1
fi
if ! SERVICE_UID="$(id -u "$SERVICE_USER" 2>/dev/null)"; then
    echo "ERROR: user '$SERVICE_USER' does not exist." >&2
    exit 1
fi

echo "Installing MagicReader services"
echo "  user: $SERVICE_USER (uid $SERVICE_UID)"
echo "  path: $REPO_DIR"

# Render a .service.template into the systemd directory.
render_unit () {
    local name="$1"
    local template="$REPO_DIR/$name.template"
    if [ ! -f "$template" ]; then
        echo "ERROR: missing template $template" >&2
        exit 1
    fi
    sed \
        -e "s|@SERVICE_USER@|$SERVICE_USER|g" \
        -e "s|@SERVICE_UID@|$SERVICE_UID|g" \
        -e "s|@REPO_DIR@|$REPO_DIR|g" \
        "$template" | sudo tee "$SERVICE_DIR/$name" > /dev/null
    sudo chmod 0644 "$SERVICE_DIR/$name"
    # A leftover placeholder means a template gained a new one without this
    # script learning to substitute it; systemd would fail obscurely later.
    if sudo grep -q '@[A-Z_]\+@' "$SERVICE_DIR/$name"; then
        echo "ERROR: unsubstituted placeholder left in $SERVICE_DIR/$name" >&2
        sudo grep -n '@[A-Z_]\+@' "$SERVICE_DIR/$name" >&2
        exit 1
    fi
}

# Units that reference the user or the install path.
render_unit MagicReader.service
# Keep the legacy helper installed for manual testing, but do not enable it.
render_unit MagicBoot.service

# Units that only call systemctl and need no substitution.
sudo install -m 0644 "$REPO_DIR/MagicWand.service" "$SERVICE_DIR/MagicWand.service"
sudo install -m 0644 "$REPO_DIR/MagicReboot.service" "$SERVICE_DIR/MagicReboot.service"

# Reload systemd to recognize the services.
sudo systemctl daemon-reload

# MagicReader runs at boot. The helpers are started on demand by the web UI and
# have no [Install] section, so they cannot be enabled and need no disabling -
# calling systemctl disable on them just prints a wall of explanation.
sudo systemctl enable MagicReader.service

if [ "$START_SERVICE" = "true" ]; then
    sudo systemctl restart MagicReader.service
fi

echo "Finished installing MagicReader services"
