#!/bin/bash
set -euo pipefail

SERVICE_DIR="/etc/systemd/system"
START_SERVICE="true"

if [ "${1:-}" = "--no-start" ]; then
    START_SERVICE="false"
fi

# Install local service units.
sudo install -m 0644 MagicReader.service "$SERVICE_DIR/MagicReader.service"
sudo install -m 0644 MagicWand.service "$SERVICE_DIR/MagicWand.service"
sudo install -m 0644 MagicReboot.service "$SERVICE_DIR/MagicReboot.service"

# Keep the legacy helper installed for manual testing, but do not enable it.
sudo install -m 0644 MagicBoot.service "$SERVICE_DIR/MagicBoot.service"

# Reload systemd to recognize the services.
sudo systemctl daemon-reload

# MagicReader runs at boot. Helper services are started on demand.
sudo systemctl enable MagicReader.service
sudo systemctl disable MagicBoot.service || true
sudo systemctl disable MagicWand.service || true
sudo systemctl disable MagicReboot.service || true

if [ "$START_SERVICE" = "true" ]; then
    sudo systemctl restart MagicReader.service
fi
