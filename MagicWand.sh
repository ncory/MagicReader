#!/bin/bash
# This script runs the MagicReader.service
echo "This is the Magic Wand"

# Stop service
echo "Stopping MagicReader service (just in case it is running)..."
sudo systemctl stop MagicReader.service

# Start service
echo "Starting MagicReader service..."
sudo systemctl start MagicReader.service
echo "Finished starting MagicReader service"