#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-$HOME/ai-pest-cannon}"
VENV_DIR="$APP_DIR/yolo-env"
APP_FILE="ai_pest_cannon.py"
LAUNCHER="$APP_DIR/launch_ai_pest_cannon_universal_mac.sh"

printf '\nAI Pest Cannon Universal - macOS installer\n'
printf 'Working folder: %s\n\n' "$APP_DIR"

if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew is required. Install it first from https://brew.sh/"
  exit 1
fi

brew install python@3.11 ffmpeg || true
brew install --cask vlc || true

mkdir -p "$APP_DIR" "$HOME/detections" "$HOME/cannon-logs"
cd "$APP_DIR"

if [ ! -d "$VENV_DIR" ]; then
  python3.11 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"
python -m pip install --upgrade pip setuptools wheel
python -m pip install "numpy==1.26.4"
python -m pip install PySide6 opencv-python paho-mqtt ultralytics python-vlc
python -m pip install torch torchvision torchaudio
python -m pip install --force-reinstall "numpy==1.26.4"

cat > "$LAUNCHER" <<'LAUNCH'
#!/usr/bin/env bash
set -e
APP_DIR="${APP_DIR:-$HOME/ai-pest-cannon}"
cd "$APP_DIR"
source "$APP_DIR/yolo-env/bin/activate"
python ai_pest_cannon.py
LAUNCH
chmod +x "$LAUNCHER"

echo
echo "Install complete."
echo "Copy ai_pest_cannon.py into: $APP_DIR"
echo "Launch with: $LAUNCHER"
