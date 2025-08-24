#!/bin/bash
# This script runs the MagicReader.service at boot, with a delay
echo "This is the Magic Boot"

# Start it the first time
sudo systemctl start MagicReader.service

# Wait
sleep 12

# Stop it
sudo systemctl stop MagicReader.service

# Start a second time
sudo systemctl start MagicReader.service
