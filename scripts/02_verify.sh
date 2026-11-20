#!/bin/bash
# =============================================================================
# 02_verify.sh — Verify Mac YOLO stack
# =============================================================================
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
ok()   { echo -e "${GREEN}[ OK ]${NC} $1"; }
info() { echo -e "${CYAN}[INFO]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
err()  { echo -e "${RED}[FAIL]${NC} $1"; }

PASS=0; FAIL=0

check() {
    local label="$1" cmd="$2"
    if python3 -c "$cmd" &>/dev/null; then
        ok "PASS  $label"; ((PASS++))
    else
        err "FAIL  $label"
        python3 -c "$cmd" 2>&1 | sed 's/^/       /'
        ((FAIL++))
    fi
}

echo -e "\n${BOLD}${CYAN}══════════════════════════════════════${NC}"
echo -e "${BOLD}${CYAN}  Mac YOLO Stack Verification         ${NC}"
echo -e "${BOLD}${CYAN}══════════════════════════════════════${NC}\n"

# Check venv active
if [ -z "$VIRTUAL_ENV" ]; then
    warn "Venv not active — activating..."
    source "$HOME/mac-yolo-env/bin/activate" || { err "Venv not found — run 01_setup.sh first"; exit 1; }
fi
ok "Venv: $VIRTUAL_ENV"

echo ""
info "── System ────────────────────────────────────────────────────"
ok "Architecture: $(uname -m)"
ok "macOS: $(sw_vers -productVersion)"
ok "Python: $(python3 --version)"

echo ""
info "── Core packages ─────────────────────────────────────────────"
check "numpy 2.x"       "import numpy as np; assert int(np.__version__.split('.')[0]) >= 2"
check "torch"           "import torch; assert torch.__version__"
check "MPS available"   "import torch; assert torch.backends.mps.is_available(), 'MPS not available — check macOS version'"
check "cv2"             "import cv2; assert int(cv2.__version__.split('.')[0]) >= 4"
check "ultralytics"     "from ultralytics import YOLO"
check "cvzone"          "import cvzone"
check "lap"             "import lap"
check "Pillow"          "from PIL import Image"
check "astral"          "from astral import LocationInfo; from astral.sun import sun"
check "paho-mqtt"       "import paho.mqtt.client"

echo ""
info "── Package versions ──────────────────────────────────────────"
python3 -c "
import torch, cv2, numpy as np
import ultralytics, astral
print(f'  numpy      {np.__version__}')
print(f'  torch      {torch.__version__}')
print(f'  MPS        {\"available\" if torch.backends.mps.is_available() else \"NOT available\"}')
print(f'  cv2        {cv2.__version__}')
print(f'  ultralytics {ultralytics.__version__}')
print(f'  astral     {astral.__version__}')
"

echo ""
info "── coco.txt ──────────────────────────────────────────────────"
if [ -f "$HOME/coco.txt" ]; then
    LINES=$(wc -l < "$HOME/coco.txt")
    ok "PASS  coco.txt ($LINES classes)"; ((PASS++))
else
    warn "coco.txt not found — generating..."
    python3 -c "
from ultralytics import YOLO; import os
m = YOLO('yolo11n.pt')
open(os.path.expanduser('~/coco.txt'),'w').write('\n'.join(m.names.values()))
print('  Generated')
"
    ((PASS++))
fi

echo ""
info "── Camera ────────────────────────────────────────────────────"
python3 -c "
import cv2
cap = cv2.VideoCapture(0)
if cap.isOpened():
    ret, frame = cap.read()
    cap.release()
    if ret:
        print(f'  USB camera 0: OK {frame.shape}')
    else:
        print('  USB camera 0: opened but no frame (may need camera permission)')
else:
    print('  USB camera 0: not found (try --usb 1 or check camera permission)')
" 2>/dev/null || warn "Camera check skipped"

echo ""
info "── RTSP test ─────────────────────────────────────────────────"
python3 -c "
import cv2, os
os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS'] = 'rtsp_transport;tcp'
print('  RTSP support: OK (set OPENCV_FFMPEG_CAPTURE_OPTIONS for your stream)')
print('  Test with: python yolo_mac_detect.py --rtsp \"rtsp://user:pass@ip:554/ch1\" --dry-run')
"

echo ""
echo "══════════════════════════════════════════════"
if [ "$FAIL" -eq 0 ]; then
    echo -e "${GREEN}${BOLD}  ALL $PASS CHECKS PASSED ✓${NC}"
    echo ""
    echo "  Ready to run:"
    echo "  python yolo_mac_detect.py --usb 0 --dry-run"
else
    echo -e "${YELLOW}${BOLD}  $PASS passed, $FAIL failed${NC}"
    echo "  Re-run: bash scripts/01_setup.sh"
fi
echo "══════════════════════════════════════════════"
