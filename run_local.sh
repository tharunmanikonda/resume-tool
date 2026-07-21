#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if [ ! -x ".venv/bin/python" ]; then
  echo "Missing Python virtual environment at .venv."
  echo "Run ./setup.sh first."
  exit 1
fi

if [ ! -d "node_modules" ]; then
  echo "Installing frontend dependencies..."
  npm install
fi

echo "Building frontend assets..."
npm run build

echo "Starting app (FLASK_PORT from the environment or .env; default 5001)"
exec .venv/bin/python app.py
