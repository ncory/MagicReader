#!/bin/bash
# This script stops MagicReader.service and reboots the Pi

# Stop services
sudo systemctl stop MagicWand.service
sudo systemctl stop MagicReader.service

# Shutdown
sudo reboot
