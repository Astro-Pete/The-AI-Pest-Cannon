#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-$HOME/ai-pest-cannon}"
VENV_DIR="${VENV_DIR:-$APP_DIR/yolo-env}"
APP_FILE="${APP_FILE:-ai_pest_cannon_universal_v1.py}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

printf '\n=== AI Pest Cannon Raspberry Pi installer - Hailo fixed ===\n'
printf 'App dir : %s\n' "$APP_DIR"
printf 'Venv dir: %s\n\n' "$VENV_DIR"

mkdir -p "$APP_DIR" "$HOME/hailo_models" "$HOME/detections" "$HOME/cannon-logs"

printf '
IMPORTANT MODEL FILE STEP
'
printf 'Copy your Hailo model folder to your home folder before using Hailo mode.
'
printf 'Expected default path:
'
printf '  %s/hailo_models/yolov11m.hef
' "$HOME"
printf 'Example copy command, adjust source path as needed:
'
printf '  cp -r /path/to/hailo_models %s/

' "$HOME"

printf '\n[1/7] Installing Raspberry Pi system packages...\n'
sudo apt update
sudo apt install -y \
  python3-pip \
  python3-venv \
  python3-opencv \
  python3-numpy \
  python3-picamera2 \
  python3-libcamera \
  python3-kms++ \
  python3-prctl \
  python3-gpiozero \
  python3-lgpio \
  v4l-utils \
  ffmpeg \
  rpicam-apps \
  vlc \
  libvlc-dev \
  alsa-utils \
  libatlas-base-dev \
  libopenblas-dev \
  libxcb-cursor0 \
  libxcb-xinerama0 \
  libxkbcommon-x11-0

printf '\n[2/7] Hailo AI HAT+ support...\n'
read -r -p "Install/reinstall Hailo AI HAT+ driver/runtime with apt install --reinstall hailo-all? [Y/n] " INSTALL_HAILO
INSTALL_HAILO="${INSTALL_HAILO:-Y}"
if [[ "$INSTALL_HAILO" =~ ^[Yy]$ ]]; then
  sudo apt install -y --reinstall hailo-all
  HAILO_REBOOT_REQUIRED=1
else
  HAILO_REBOOT_REQUIRED=0
fi

printf '\n[3/7] Creating/updating Python venv...\n'
if [[ ! -d "$VENV_DIR" ]]; then
  "$PYTHON_BIN" -m venv --system-site-packages "$VENV_DIR"
fi
# shellcheck source=/dev/null
source "$VENV_DIR/bin/activate"
python -m pip install --upgrade pip setuptools wheel

printf '\n[4/7] Installing required Python packages...\n'
python -m pip install "PySide6==6.8.0.2" paho-mqtt astral python-vlc
python -m pip install --force-reinstall "numpy==1.26.4"

printf '\n[5/7] Optional CPU fallback...\n'
read -r -p "Install CPU YOLO fallback packages: ultralytics torch torchvision? [Y/n] " INSTALL_CPU
INSTALL_CPU="${INSTALL_CPU:-Y}"
if [[ "$INSTALL_CPU" =~ ^[Yy]$ ]]; then
  python -m pip install --upgrade ultralytics torch torchvision
  python -m pip install --force-reinstall "numpy==1.26.4"
fi

printf '\n[6/7] Creating launcher...\n'
cat > "$APP_DIR/launch_ai_pest_cannon.sh" <<LAUNCH
#!/usr/bin/env bash
set -e
APP_DIR="$APP_DIR"
VENV_DIR="$VENV_DIR"
APP_FILE="\$APP_DIR/$APP_FILE"
cd "\$APP_DIR"
source "\$VENV_DIR/bin/activate"
python "\$APP_FILE"
LAUNCH
chmod +x "$APP_DIR/launch_ai_pest_cannon.sh"

cat > "$APP_DIR/launch_ai_pest_cannon_xcb.sh" <<LAUNCH
#!/usr/bin/env bash
set -e
export QT_QPA_PLATFORM=xcb
APP_DIR="$APP_DIR"
VENV_DIR="$VENV_DIR"
APP_FILE="\$APP_DIR/$APP_FILE"
cd "\$APP_DIR"
source "\$VENV_DIR/bin/activate"
python "\$APP_FILE"
LAUNCH
chmod +x "$APP_DIR/launch_ai_pest_cannon_xcb.sh"

printf '\n[7/7] Verification checks...\n'
python - <<'PY'
import importlib, sys
mods = ["PySide6", "cv2", "numpy", "paho.mqtt.client", "vlc", "astral", "gpiozero", "lgpio", "hailo_platform"]
for m in mods:
    try:
        mod = importlib.import_module(m)
        print(f"{m}: OK {getattr(mod, '__version__', '')}")
    except Exception as e:
        print(f"{m}: FAIL {e}")
print("python:", sys.executable)
PY

printf '\n--- Hailo checks ---\n'
if command -v hailortcli >/dev/null 2>&1; then
  hailortcli --version || true
else
  echo "hailortcli: NOT FOUND"
fi

if lsmod | grep -qi hailo; then
  echo "hailo kernel module: LOADED"
else
  echo "hailo kernel module: NOT LOADED YET"
fi

if command -v hailortcli >/dev/null 2>&1; then
  hailortcli fw-control identify || true
fi

printf '\n=== Install complete ===\n'
printf 'Copy the app script to: %s/%s\n' "$APP_DIR" "$APP_FILE"
printf 'Launch with: %s/launch_ai_pest_cannon.sh\n' "$APP_DIR"
printf 'If Qt/Wayland gives problems, launch with: %s/launch_ai_pest_cannon_xcb.sh\n' "$APP_DIR"

if [[ "${HAILO_REBOOT_REQUIRED:-0}" == "1" ]]; then
  printf '\nIMPORTANT: hailo-all was installed/reinstalled. Reboot now before expecting the Hailo driver to work:\n'
  printf '  sudo reboot\n'
fi
