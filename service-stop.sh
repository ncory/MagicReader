#!/bin/bash
set -euo pipefail

# This script stops MagicReader.service and disables the service

# Stop services
sudo systemctl stop MagicReader.service || true
sudo systemctl stop MagicWand.service || true
sudo systemctl stop MagicBoot.service || true
sudo systemctl stop MagicReboot.service || true

# Disable services
sudo systemctl disable MagicReader.service || true
sudo systemctl disable MagicWand.service || true
sudo systemctl disable MagicBoot.service || true
sudo systemctl disable MagicReboot.service || true
