#!/bin/bash
# This script pulls the latest copy of the code from Github, then restarts the app using the MagicWand

# Git pull command
git pull origin main

# Start MagicWand service
sudo systemctl start MagicWand.service
