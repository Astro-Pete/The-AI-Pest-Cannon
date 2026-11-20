#!/usr/bin/env bash
# ==================================================
# File: build_mac.sh
# Description: Build the AI Pest Cannon macOS app from any working directory.
# Created: 2026-10-14 17:26 (UTC)
# Last modified: 2026-10-14 17:26 (UTC)
# Change log:
#   2026-10-14 17:26 - Initial creation, replacing build_mac_app.sh.
# ==================================================

set -euo pipefail
cd "$(dirname "$0")"
exec "${PEST_PYTHON:-python3}" build.py "$@"
