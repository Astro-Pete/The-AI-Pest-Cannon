#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-$HOME/ai-pest-cannon}"
VENV_DIR="$APP_DIR/yolo-env"
LAUNCHER="$APP_DIR/launch_ai_pest_cannon_universal_linux.sh"

printf '\nAI Pest Cannon Universal - Linux installer\n'
printf 'Working folder: %s\n\n' "$APP_DIR"

sudo apt update
sudo apt install -y \
  python3-pip \
  python3-venv \
  ffmpeg \
  alsa-utils \
  vlc \
  libvlc-dev \
  libxcb-cursor0

mkdir -p "$APP_DIR" "$HOME/detections" "$HOME/cannon-logs"
cd "$APP_DIR"

if [ ! -d "$VENV_DIR" ]; then
  python3 -m venv "$VENV_DIR"
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
python ai_pest_cannon_universal_v1.py
LAUNCH
chmod +x "$LAUNCHER"

echo
echo "Install complete."
echo "Copy ai_pest_cannon_universal_v1.py into: $APP_DIR"
echo "Launch with: $LAUNCHER"
