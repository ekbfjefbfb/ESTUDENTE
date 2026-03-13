#!/usr/bin/env bash
set -euo pipefail

echo "🔧 Render build: installing dependencies"
python -m pip install --upgrade pip
pip install --no-cache-dir -r requirements.txt

echo "✅ Build complete"
