#!/usr/bin/env bash
set -e
export QT_QPA_PLATFORM=xcb
APP_DIR="/home/pete/ai-pest-cannon"
VENV_DIR="/home/pete/ai-pest-cannon/yolo-env"
APP_FILE="$APP_DIR/ai_pest_cannon_universal_v1.py"
cd "$APP_DIR"
source "$VENV_DIR/bin/activate"
python "$APP_FILE"
