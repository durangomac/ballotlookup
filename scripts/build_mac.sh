#!/usr/bin/env bash
set -euo pipefail
if ! command -v pyinstaller >/dev/null 2>&1; then
  pip install pyinstaller
fi
pyinstaller --noconfirm --windowed --name "BallotFinder" \
  --add-data "config.json:." app.py
echo "Built to dist/BallotFinder.app"
