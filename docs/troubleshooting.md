# Troubleshooting — Mac YOLO Wildlife Detector

---

## Error 1: MPS not available
```
WARN: MPS not available — using CPU
```
**Cause:** macOS < 12.3 or Intel Mac.
**Fix:** MPS requires macOS 12.3+. On Intel Mac it falls back to CPU automatically —
slower but works. M4 Pro will always have MPS.

---

## Error 2: Camera permission denied
```
[ERROR] Could not open USB camera 0
```
**Cause:** macOS blocked camera access.
**Fix:** System Settings → Privacy & Security → Camera → enable Terminal (or your IDE).
Then restart Terminal and try again.

---

## Error 3: Wrong camera index
**Fix:** Find the right index:
```bash
python3 -c "import cv2; [print(i, 'available') for i in range(5) if cv2.VideoCapture(i).isOpened()]"
```
Try `--usb 0`, `--usb 1`, `--usb 2` etc.

---

## Error 4: RTSP stream timeout / hangs
```
Stream timeout triggered after 30000ms
```
**Fix:** The env var is set automatically in the script. If still hanging:
```bash
# Use ch1 (sub-stream, lower res, more stable)
python yolo_mac_detect.py --rtsp 'rtsp://user:pass@ip:554/ch1'
```

---

## Error 5: cv2 window doesn't appear
**Cause:** On macOS, cv2.imshow() needs to run on the main thread.
**Fix:** Always run the script directly from Terminal, not from an IDE's
run button. If using VS Code, run in the integrated terminal.

---

## Error 6: Homebrew Python vs system Python
```
command not found: python3.11
```
**Fix:**
```bash
brew install python@3.11
# Add to PATH if needed:
echo 'export PATH="/opt/homebrew/opt/python@3.11/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

---

## Error 7: Venv not activating
```
source: no such file or directory: ~/mac-yolo-env/bin/activate
```
**Fix:** Re-run setup: `bash mac-toolkit/scripts/01_setup.sh`

---

## Error 8: paho-mqtt connection refused (future)
```
Connection refused: 111
```
**Cause:** No MQTT broker on the Pi.
**Fix:** On Pi: `sudo apt install mosquitto mosquitto-clients && sudo systemctl enable mosquitto`
Then test: `mosquitto_pub -h 192.168.x.x -t test -m hello`

---

## Performance tips for M4 Pro

- Use `--model yolo11m.pt --imgsz 640` as your default — M4 handles it at 25+fps
- `--imgsz 1280` gives noticeably better detection of small distant objects (pigeons)
- `--conf 0.15 --imgsz 1280` is the best combo for distant/flying birds
- YOLO-World is slower (~20fps) but worth it for fox/badger by name
- `--device mps` is set automatically — don't override unless testing
