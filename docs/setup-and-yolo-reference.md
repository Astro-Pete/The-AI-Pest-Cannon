<!--
File: setup-and-yolo-reference.md
Note (2026-10-14 17:08 UTC): this is the README of the original Mac YOLO toolkit (April 2026). Its setup and verify steps still apply (scripts/01_setup.sh, scripts/02_verify.sh); its run commands refer to the earlier yolo_mac_detect.py script, which the GUI (app/ai_pest_cannon.py) has replaced.
-->
# Mac YOLO Wildlife Detector Toolkit
## YOLO11 Object Detection — macOS Tahoe / Apple Silicon M4
### No GPIO — Detection + alerting only

Tested target: MacBook Pro M4 Pro 24GB — macOS Tahoe 26.x
Python: 3.11+ (via Homebrew)
Inference: Apple MPS (Metal Performance Shaders) — uses Neural Engine + GPU

---

## Prerequisites

Xcode Command Line Tools (needed for Homebrew and Python builds):
```bash
xcode-select --install
```

Homebrew (if not already installed):
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

---

## Install — Run Once

```bash
cd ~
bash mac-toolkit/scripts/01_setup.sh
source ~/mac-yolo-env/bin/activate
bash mac-toolkit/scripts/02_verify.sh
```

---

## Generate class names then run

```bash
source ~/mac-yolo-env/bin/activate
cd ~

# Generate coco.txt
python3 -c "from ultralytics import YOLO; m=YOLO('yolo11n.pt'); open('coco.txt','w').write('\n'.join(m.names.values()))"

# Test with USB camera (dry run — just shows detections, no cannon)
python yolo_mac_detect.py --usb 0 --dry-run

# Test with RTSP stream
python yolo_mac_detect.py --rtsp 'rtsp://user:pass@192.168.x.x:554/ch1' --dry-run
```

---

## Quick Command Reference

```bash
source ~/mac-yolo-env/bin/activate

# ── USB camera ────────────────────────────────────────────────────────────────
python yolo_mac_detect.py --usb 0
python yolo_mac_detect.py --usb 0 --dry-run
python yolo_mac_detect.py --usb 0 --night-vision
python yolo_mac_detect.py --usb 0 --display-scale 0.75
python yolo_mac_detect.py --usb 0 --model yolo11s.pt
python yolo_mac_detect.py --usb 0 --model yolo11m.pt   # M4 handles this easily

# ── RTSP camera (Thingino etc) — always single quotes ─────────────────────────
python yolo_mac_detect.py --rtsp 'rtsp://user:pass@192.168.x.x:554/ch1'
python yolo_mac_detect.py --rtsp 'rtsp://user:pass@192.168.x.x:554/ch0' --display-scale 0.5

# ── YOLO-World (fox, badger by name — zero-shot) ──────────────────────────────
python yolo_mac_detect.py --usb 0 --model-type world \
    --world-classes "fox,badger,pigeon,rabbit,squirrel,cat,dog,person"

# ── Model sizes (M4 Pro handles all of these well) ────────────────────────────
python yolo_mac_detect.py --usb 0 --model yolo11n.pt   # nano  fastest
python yolo_mac_detect.py --usb 0 --model yolo11s.pt   # small
python yolo_mac_detect.py --usb 0 --model yolo11m.pt   # medium — recommended on M4
python yolo_mac_detect.py --usb 0 --model yolo11l.pt   # large
python yolo_mac_detect.py --usb 0 --model yolo11x.pt   # xlarge — max accuracy

# ── Tune detection ────────────────────────────────────────────────────────────
python yolo_mac_detect.py --usb 0 --conf 0.15 --imgsz 640  # sensitive, high res
python yolo_mac_detect.py --usb 0 --conf 0.35 --imgsz 320  # default
python yolo_mac_detect.py --usb 0 --conf 0.5               # conservative

# ── Pest / safe class customisation ──────────────────────────────────────────
python yolo_mac_detect.py --usb 0 \
    --pest-classes "fox,badger,bird,pigeon,cat,dog,rabbit,squirrel" \
    --safe-classes "person,car,truck"

# ── Stopping ──────────────────────────────────────────────────────────────────
# Q in camera window  |  q + Enter in terminal  |  Ctrl+C
```

---

## Detection Behaviour

| Detected | Action | Box colour |
|----------|--------|------------|
| dog, cat, bird, bear, horse, sheep, cow | ALERT (console print) | Red |
| person, car, truck, bus, bicycle | Nothing | Green |
| anything else | Nothing | Orange |

In dry-run mode (always on for now — no GPIO on Mac):
- Prints detection to console
- Shows countdown overlay on screen
- Ready for MQTT trigger when you add it later

---

## Adding MQTT Later

When you're ready to trigger the Pi cannon remotely, install:
```bash
pip install paho-mqtt
```
The script has a stub function `on_pest_detected()` ready to receive MQTT code.

---

## Performance on M4 Pro

| Model | Expected FPS |
|-------|-------------|
| yolo11n | 60+ fps |
| yolo11s | 40+ fps |
| yolo11m | 25+ fps |
| yolo11l | 15+ fps |
| yolov8s-world | 20+ fps |

Inference runs on MPS (Metal) automatically — uses the Neural Engine.
