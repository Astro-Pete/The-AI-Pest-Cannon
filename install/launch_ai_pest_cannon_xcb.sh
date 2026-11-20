#!/usr/bin/env bash
set -e
export QT_QPA_PLATFORM=xcb
APP_DIR="${APP_DIR:-$HOME/ai-pest-cannon}"
VENV_DIR="${VENV_DIR:-$APP_DIR/yolo-env}"
APP_FILE="$APP_DIR/ai_pest_cannon.py"
cd "$APP_DIR"
source "$VENV_DIR/bin/activate"
python "$APP_FILE"
