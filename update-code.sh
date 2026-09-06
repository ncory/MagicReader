#!/bin/bash
set -euo pipefail

# This script pulls the latest copy of the code from Github, then restarts the app using the MagicWand

# Git pull command
git pull origin main

# Restart the app
sudo systemctl restart MagicReader.service
