#!/bin/bash
# This script stops MagicReader.service and disables the service

# Stop services
sudo systemctl stop MagicReader.service
sudo systemctl stop MagicWand.service

# Disable services
sudo systemctl disable MagicReader.service
sudo systemctl disable MagicWand.service
