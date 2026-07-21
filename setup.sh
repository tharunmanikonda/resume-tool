#!/bin/bash

# Resume Generator - One-Command Setup & Run
# This script installs all dependencies and starts the app

set -e  # Exit on error

echo "📄 Resume Generator - Setup & Run"
echo "=================================="

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.10 or higher."
    exit 1
fi

if ! python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
    echo "❌ Python 3.10 or newer is required."
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
echo "✅ Python $PYTHON_VERSION found"

# Get the script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# The runner and documentation use one consistent environment name.
if [ ! -d ".venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv .venv
    echo "✅ Virtual environment created"
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source .venv/bin/activate

# Upgrade pip
echo "📥 Upgrading pip..."
pip install --upgrade pip --quiet

# Install requirements
echo "📚 Installing dependencies..."
pip install -r requirements.txt --quiet
echo "✅ All dependencies installed"

if ! command -v node &> /dev/null || ! command -v npm &> /dev/null; then
    echo "❌ Node.js 20+ and npm are required to build the web app and extension."
    exit 1
fi

NODE_MAJOR=$(node -p 'Number(process.versions.node.split(".")[0])')
if [ "$NODE_MAJOR" -lt 20 ]; then
    echo "❌ Node.js 20 or newer is required."
    exit 1
fi

echo "📦 Installing frontend dependencies..."
npm install --quiet

echo "🏗️ Building the web app and browser extension..."
npm run build

if ! command -v soffice &> /dev/null && [ ! -x "/Applications/LibreOffice.app/Contents/MacOS/soffice" ]; then
    echo "⚠️ LibreOffice was not found. The app can start, but PDF conversion will remain unavailable."
    echo "   Install LibreOffice or set SOFFICE_PATH in .env."
fi

# Check for .env file
if [ ! -f ".env" ]; then
    echo "📋 Creating .env file from template..."
    cp .env.example .env
    echo "✅ .env file created"
fi

echo ""
echo "🚀 Starting Resume Generator..."
echo "📱 Visit the FLASK_PORT configured in the environment or .env (default: http://127.0.0.1:5001)"
echo "🛑 Press Ctrl+C to stop the server"
echo ""

# Run the app
exec .venv/bin/python app.py
