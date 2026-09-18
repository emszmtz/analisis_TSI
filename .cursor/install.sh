#!/usr/bin/env bash
# Idempotent bootstrap for the TSI trading / backtesting project.
# Sets up a Python virtualenv (data + backtesting + IBKR bots) and installs
# the Node dependency used by the Dukascopy data downloader.
set -euo pipefail

cd "$(dirname "$0")/.."

# --- System package: python venv support (default image lacks ensurepip) ---
if ! python3 -m venv --help >/dev/null 2>&1 || ! python3 -c "import ensurepip" >/dev/null 2>&1; then
  echo "Installing python3-venv system package..."
  sudo apt-get update -qq
  sudo apt-get install -y -qq python3.12-venv
fi

# --- Python virtualenv ---
if [ ! -x venv/bin/python ]; then
  echo "Creating virtualenv in ./venv ..."
  python3 -m venv venv
fi

echo "Installing Python dependencies..."
./venv/bin/python -m pip install --upgrade pip
./venv/bin/python -m pip install -r requirements.txt

# --- Node dependencies (dukascopy-node data downloader) ---
if [ -f package-lock.json ]; then
  echo "Installing Node dependencies (npm ci)..."
  npm ci
else
  echo "Installing Node dependencies (npm install)..."
  npm install
fi

echo "Environment setup complete."
