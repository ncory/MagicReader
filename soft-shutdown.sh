#!/bin/bash
# This script stops MagicReader.service and shuts down the Pi

# Stop services
sudo systemctl stop MagicReader.service
sudo systemctl stop MagicWand.service

# Shutdown
sudo shutdown
