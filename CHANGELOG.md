# Changelog

## V8 (May 2026) — current

- Optional inverted ROI exclusion zones, on top of V7.
- Source file renamed from `ai_pest_cannon_universal_v8.py` to `app/ai_pest_cannon.py` when the project moved to `Documents/AI Python Apps` (2026-10-14 17:08 UTC).
- Windows and macOS build kit in `packaging/` (replaces `build_mac_app.sh`, which targeted the old `pest_canon_mac_gui_v4.py`).
- Packaged app fixes: torchvision ops and python-vlc are bundled, macOS asks for Local Network access (RTSP camera, MQTT), versions pinned to the working source environment, and the build runs a packaged self-test.
- Repository reorganised (2026-11-20): app in `app/`, installers and launchers in `install/` (now run `ai_pest_cannon.py` instead of the V1 script, and use the current user's home folder), `app/coco.txt` added for Hailo models, AGPL-3.0 licence added, old V1 / V5 scripts removed from the tree (still in git history). YOLO `.pt` weights are no longer stored in git; they download automatically.

## Earlier versions

- V7: clearer custom checkbox rendering (dark unchecked boxes, green tick).
- V1–V6 (May 2026): PySide6 GUI developed from `pest_canon_mac_v2.py` with YOLO detection, MQTT trigger and ROI.
- The original source files of V1–V7 remain in `~/mac-toolkit`.
