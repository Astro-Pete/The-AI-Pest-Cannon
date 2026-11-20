#!/usr/bin/env bash
# ==================================================
# File: run_from_source.sh
# Description: Start the AI Pest Cannon GUI from source (macOS).
# Created: 2026-10-14 17:08 (UTC)
# Change log:
#   2026-10-14 17:08 (UTC) - Initial creation, replacing the Desktop launcher that ran from ~/mac-toolkit.
# ==================================================
# The YOLO model names (yolo11m.pt etc.) are looked up in the working folder, so run from models/.
# Ultralytics downloads a model into this folder if it is missing.

source "$HOME/mac-yolo-env/bin/activate"
cd "$(dirname "$0")/models" || exit 1
exec python ../app/ai_pest_cannon.py
