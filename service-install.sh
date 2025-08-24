#!/bin/bash
# This script installs MagicReader.service and MagicWand.service, enables tehm, and starts the MagicWand

# Copy service files to systemd directory
sudo cp MagicReader.service /lib/systemd/system/MagicReader.service
sudo cp MagicWand.service /lib/systemd/system/MagicWand.service
sudo cp MagicBoot.service /lib/systemd/system/MagicBoot.service
sudo cp MagicReboot.service /lib/systemd/system/MagicReboot.service

# Set ownership for the service files
sudo chown root:root /lib/systemd/system/MagicReader.service
sudo chown root:root /lib/systemd/system/MagicWand.service
sudo chown root:root /lib/systemd/system/MagicBoot.service
sudo chown root:root /lib/systemd/system/MagicReboot.service

# Set permissions for the service files
sudo chmod 644 /lib/systemd/system/MagicReader.service
sudo chmod 644 /lib/systemd/system/MagicWand.service
sudo chmod 644 /lib/systemd/system/MagicBoot.service
sudo chmod 644 /lib/systemd/system/MagicReboot.service

# Reload systemd to recognize the new services
sudo systemctl daemon-reload

# Enable services
sudo systemctl enable MagicReader.service
sudo systemctl enable MagicWand.service
sudo systemctl enable MagicBoot.service
sudo systemctl enable MagicReboot.service

# Start MagicWand service
sudo systemctl start MagicWand.service
