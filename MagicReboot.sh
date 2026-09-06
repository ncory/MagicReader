#!/bin/bash
set -euo pipefail

sudo systemctl stop MagicReader.service
sudo systemctl reboot
