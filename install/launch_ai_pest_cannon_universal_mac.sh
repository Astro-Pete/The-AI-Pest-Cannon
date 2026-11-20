#!/usr/bin/env bash
set -e
APP_DIR="${APP_DIR:-$HOME/ai-pest-cannon}"
cd "$APP_DIR"
source "$APP_DIR/yolo-env/bin/activate"
python ai_pest_cannon.py
