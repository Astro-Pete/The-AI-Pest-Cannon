<!--
File: README.md
Description: How to build the AI Pest Cannon app on Windows or macOS.
Created: 2026-10-14 17:26 (UTC)
Last modified: 2026-10-14 17:43 (UTC)
Change log:
  2026-10-14 17:26 (UTC) - Initial creation, replacing build_mac_app.sh.
  2026-10-14 17:43 (UTC) - Pinned versions, VLC and Local Network notes, packaged self-test.
-->
# AI Pest Cannon build kit

Builds a one-folder app with PyInstaller: `AI Pest Cannon.exe` with its `_internal` folder on Windows, `AI Pest Cannon.app` on macOS. Build on the OS you are targeting.

## Windows

1. Install 64-bit Python 3.11 with the Python Launcher.
2. Copy the **whole AI Pest Cannon project folder** to the Windows PC (the build packages `app/` and copies the weights from `models/`).
3. Double-click `packaging\build_windows.bat` (set `PEST_PYTHON` to choose an interpreter).

The first build downloads PyTorch, Ultralytics, PySide6 and OpenCV (well over 1 GB) into `.venv-windows-amd64`. pip installs the **CPU** build of PyTorch. For an NVIDIA GPU, install the CUDA build of torch into that environment (see pytorch.org), then run the build with `--use-current-python` using that environment's Python.

Output: `packaging\dist\windows-amd64\AI Pest Cannon\` containing `AI Pest Cannon.exe`, `_internal\` and `models\`. Copy that whole folder to the target PC. `--models yolo11m.pt,yolo11n.pt` copies only the named weights.

## macOS

`bash packaging/build_mac.sh` (set `PEST_PYTHON=/opt/homebrew/bin/python3.11`). Output: `packaging/dist/macos-arm64/AI Pest Cannon.app` with `models/` beside it.

## What the build does

1. Creates `.venv-<os>-<arch>` here and installs `requirements-build.txt`. `--use-current-python` skips this.
2. Checks the dependencies (and reports whether CUDA is available) and compiles `app/ai_pest_cannon.py`.
3. Packages it with `AIPestCannon.spec`, bundling `custom.wav` and the Ultralytics data files.
4. Copies the YOLO weights to `models/` beside the app. The runtime hook `rthook_models_folder.py` starts the app in that folder, as `run_from_source.sh` does, so model names resolve there.
5. Runs the packaged self-test in `rthook_models_folder.py` (torchvision NMS, python-vlc with libVLC, the alert sound), then starts the app without a window and checks it is still running after 25 seconds.

Settings, detections and logs are stored per user as in a source run (`%APPDATA%\ai_pest_cannon\settings.json` on Windows, `~/detections`, `~/cannon-logs`). The dependency versions in `requirements-build.txt` are pinned to the ones that run from source in `~/mac-yolo-env`.

**On the target computer:**

- **VLC** must be installed for RTSP cameras (VLC.app on macOS, 64-bit VLC on Windows): python-vlc is bundled, libVLC comes from VLC.
- **macOS Local Network access** must be allowed for the app (System Settings → Privacy & Security → Local Network), or the RTSP camera and MQTT broker fail with *No route to host*. macOS asks on first use; an ad-hoc signed rebuild may need allowing again.
- **Windows Firewall** may ask to allow network access on first use.
- Camera access must be allowed for a USB camera. The optional Hailo backend is not packaged.
