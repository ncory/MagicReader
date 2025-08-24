#!/bin/bash
# This script stops MagicReader.service and disables the service

# Stop services
sudo systemctl stop MagicReader.service
sudo systemctl stop MagicWand.service
sudo systemctl stop MagicBoot.service
sudo systemctl stop MagicReboot.service

# Disable services
sudo systemctl disable MagicReader.service
sudo systemctl disable MagicWand.service
sudo systemctl disable MagicBoot.service
sudo systemctl disable MagicReboot.service
