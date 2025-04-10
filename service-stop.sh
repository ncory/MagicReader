#!/bin/bash
# This script stops MagicReader.service and disables the service

# Stop service
sudo systemctl stop MagicReader.service

# Enable service
sudo systemctl disable MagicReader.service
