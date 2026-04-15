#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV_PATH="$SCRIPT_DIR/.venv"
if [ ! -d "$VENV_PATH" ]; then
  echo "Error: .venv not found at $VENV_PATH"
  exit 1
fi

source "$VENV_PATH/bin/activate"
python scripts/ws_chat.py
