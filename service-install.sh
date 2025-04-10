#!/bin/bash
# This script installs MagicReader.service, enables it, and starts the service

# Copy service file to systemd directory
sudo cp MagicReader.service /lib/systemd/system/MagicReader.service

# Set ownership for the service file
sudo chown root:root /lib/systemd/system/MagicReader.service

# Set permissions for the service file
sudo chmod 644 /lib/systemd/system/MagicReader.service

# Reload systemd to recognize the new service
sudo systemctl daemon-reload

# Enable service
sudo systemctl enable MagicReader.service

# Start service
sudo systemctl start MagicReader.service