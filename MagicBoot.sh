#!/bin/bash
set -euo pipefail

echo "MagicBoot is deprecated; starting MagicReader.service directly."
sudo systemctl start MagicReader.service
