#!/bin/bash
# =============================================================================
# 01_setup.sh — Full setup for Mac YOLO Wildlife Detector
# macOS Tahoe / Apple Silicon M4
# =============================================================================
set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
ok()   { echo -e "${GREEN}[ OK ]${NC} $1"; }
info() { echo -e "${CYAN}[INFO]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
err()  { echo -e "${RED}[FAIL]${NC} $1"; }

echo -e "\n${BOLD}${CYAN}══════════════════════════════════════${NC}"
echo -e "${BOLD}${CYAN}  Mac YOLO Wildlife Detector — Setup  ${NC}"
echo -e "${BOLD}${CYAN}══════════════════════════════════════${NC}\n"

# ── Check Apple Silicon ───────────────────────────────────────────────────────
ARCH=$(uname -m)
if [ "$ARCH" = "arm64" ]; then
    ok "Apple Silicon detected ($ARCH) — MPS acceleration available"
else
    warn "Intel Mac detected — inference will use CPU (slower)"
fi

# ── Check Xcode CLI tools ─────────────────────────────────────────────────────
info "Checking Xcode Command Line Tools..."
if xcode-select -p &>/dev/null; then
    ok "Xcode CLI tools installed"
else
    err "Xcode CLI tools not found. Install with: xcode-select --install"
    exit 1
fi

# ── Check / install Homebrew ──────────────────────────────────────────────────
info "Checking Homebrew..."
if command -v brew &>/dev/null; then
    ok "Homebrew found: $(brew --version | head -1)"
else
    err "Homebrew not found."
    echo "  Install with:"
    echo '  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
    exit 1
fi

# ── Install Python 3.11 via Homebrew ──────────────────────────────────────────
info "Checking Python..."
if command -v python3.11 &>/dev/null; then
    ok "python3.11 found: $(python3.11 --version)"
else
    info "Installing Python 3.11 via Homebrew..."
    brew install python@3.11
fi

PYTHON=$(command -v python3.11 || command -v python3)
ok "Using Python: $($PYTHON --version) at $PYTHON"

# ── Install ffmpeg (needed for RTSP streams) ──────────────────────────────────
info "Checking ffmpeg..."
if command -v ffmpeg &>/dev/null; then
    ok "ffmpeg found"
else
    info "Installing ffmpeg..."
    brew install ffmpeg
fi

# ── Create venv ───────────────────────────────────────────────────────────────
VENV_DIR="$HOME/mac-yolo-env"
info "Creating venv at $VENV_DIR..."
if [ -d "$VENV_DIR" ]; then
    warn "Venv already exists"
    read -rp "  Recreate? [y/N] " ans
    [[ "$ans" =~ ^[Yy]$ ]] && rm -rf "$VENV_DIR" || { info "Keeping existing venv"; }
fi

if [ ! -d "$VENV_DIR" ]; then
    "$PYTHON" -m venv "$VENV_DIR"
    ok "Venv created"
fi

source "$VENV_DIR/bin/activate"
pip install --quiet --upgrade pip setuptools wheel

# ── Install Python packages ───────────────────────────────────────────────────
info "Installing numpy..."
pip install --quiet "numpy>=2.0.0"
ok "numpy $(python3 -c 'import numpy; print(numpy.__version__)')"

info "Installing PyTorch with MPS support..."
# On Apple Silicon, standard pip torch includes MPS support
pip install --quiet torch torchvision
TORCH=$(python3 -c "import torch; print(torch.__version__)")
MPS=$(python3 -c "import torch; print('YES' if torch.backends.mps.is_available() else 'NO')")
ok "torch $TORCH | MPS available: $MPS"

info "Installing OpenCV..."
# opencv-python on Mac includes display support natively
pip install --quiet opencv-python
CV2=$(python3 -c "import cv2; print(cv2.__version__)")
ok "cv2 $CV2"

info "Installing ultralytics..."
pip install --quiet ultralytics
ok "ultralytics $(python3 -c 'import ultralytics; print(ultralytics.__version__)')"

info "Installing cvzone..."
pip install --quiet cvzone

info "Installing lap (tracker dependency)..."
pip install --quiet "lap>=0.5.12"

info "Installing astral (sunrise/sunset scheduling)..."
pip install --quiet astral

info "Installing utility packages..."
pip install --quiet Pillow pandas matplotlib requests tqdm supervision

# paho-mqtt stub — install now so it's ready when you add MQTT later
info "Installing paho-mqtt (for future Pi cannon triggering)..."
pip install --quiet "paho-mqtt>=2.0.0"
ok "paho-mqtt ready for MQTT integration"

# ── Generate coco.txt ─────────────────────────────────────────────────────────
info "Generating coco.txt..."
python3 -c "
from ultralytics import YOLO
import os
m = YOLO('yolo11n.pt')
path = os.path.expanduser('~/coco.txt')
open(path, 'w').write('\n'.join(m.names.values()))
print(f'  Written {len(m.names)} classes to {path}')
"

# ── macOS camera permission reminder ─────────────────────────────────────────
echo ""
warn "macOS Camera Permission:"
warn "  The first time you run the script with --usb, macOS will ask for"
warn "  camera permission. Click Allow in the system dialog."
warn "  If denied: System Settings → Privacy & Security → Camera → allow Terminal"

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════════"
echo -e "${GREEN}${BOLD}  Setup complete ✓${NC}"
echo ""
echo "  Activate venv : source ~/mac-yolo-env/bin/activate"
echo "  Verify        : bash scripts/02_verify.sh"
echo "  Run           : ./run_from_source.sh"
echo "══════════════════════════════════════════════"
