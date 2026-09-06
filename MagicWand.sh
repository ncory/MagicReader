#!/bin/bash
set -euo pipefail

echo "Restarting MagicReader.service..."
sudo systemctl restart MagicReader.service
echo "Finished restarting MagicReader.service"
