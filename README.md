# The AI Pest Cannon

**AI-powered garden pest deterrent.** A live camera feed is watched by a YOLO neural network. When
a pest animal (cat, fox, bird, dog...) is confirmed inside your chosen zone, it fires a "cannon": a
water solenoid, sprinkler, light, horn or anything else on a relay, triggered over **MQTT** or
**Raspberry Pi GPIO**.

Runs on **macOS** (Apple Silicon / Metal), **Windows** (NVIDIA CUDA or CPU), **Linux**, and
**Raspberry Pi 5** with the **Hailo AI HAT+** NPU.

Current version: **V8**. See [CHANGELOG.md](CHANGELOG.md).
User Guide (PDF): [download](https://drive.google.com/file/d/1ckHpSCwEQqAl_zVuAT-dxXGfUbC_3At0/view?usp=share_link)

## Features

- Multi-class YOLO pest detection (YOLO11 / YOLO26 on Mac, Windows and Linux; YOLOv8 / YOLO11 `.hef` on Hailo)
- Multiple detection zones (ROI), plus **inverted ROI** exclusion zones (V8) to ignore false triggers
- **Safe-class suppression**: if a person (or any class you choose) is anywhere in view, the cannon never fires
- MQTT and/or GPIO relay output, with automatic OFF after the fire time and a hold-off cooldown
- RTSP network camera (VLC or OpenCV backend), USB webcam, or Raspberry Pi CSI camera
- Manual one-shot and timed cannon control (up to 60 minutes; handy for watering the lawn!)
- Detection images and clips saved, custom alert sound, settings remembered

## How it works

1. **Capture**: frames are read from an RTSP network camera, USB webcam or CSI camera.
2. **Inference**: each frame (or every Nth frame if `skip_frames` is set) goes through the YOLO model, which returns boxes, labels and confidence scores.
3. **Safe-class check**: if a safe-class object (e.g. a person) is anywhere in the frame, the cannon is suppressed, even if a pest is in a zone at the same time.
4. **ROI filtering**: pest detections are matched against your zones (and inverted zones).
5. **Confirmation**: after `confirm_frames` consecutive confirmed frames, the cannon fires.
6. **Output**: MQTT ON is published and/or a GPIO relay closes. After `fire_time` seconds MQTT OFF is sent automatically.
7. **Hold-off**: a cooldown stops the cannon re-firing straight away.

## Recommended hardware

- Raspberry Pi 5 with **AI HAT+ 26 TOPS**, plus an optional relay board on the GPIO
- 12 V ½" water solenoid valve with hose-lock style connectors (an impact sprinkler works very well)
- Camera: RTSP, USB or CSI (Raspberry Pi camera connector)
- Optional: Home Assistant with an MQTT broker and Wi-Fi plugs. Local control is recommended; I use Tuya plugs with Tuya Local installed in HA via HACS.

A recent Mac (e.g. MacBook Pro M4 Pro) or a Windows PC with a recent NVIDIA RTX GPU also gives
excellent results.

## Repository layout

| Folder | Contents |
|---|---|
| `app/` | `ai_pest_cannon.py` (the whole application), `custom.wav` (alert sound), `coco.txt` (class names for Hailo models) |
| `install/` | Installers and launchers for Raspberry Pi, Linux, macOS and Windows |
| `hailo_models/` | Compiled Hailo `.hef` models (`yolov11n`, `yolov11s`) for the Raspberry Pi AI HAT+ |
| `models/` | Where YOLO `.pt` weights go; they download automatically ([models/README.md](models/README.md)) |
| `scripts/` | macOS developer setup (`01_setup.sh`) and check (`02_verify.sh`) |
| `packaging/` | PyInstaller build kit for a standalone macOS `.app` or Windows `.exe` ([packaging/README.md](packaging/README.md)) |
| `docs/` | Troubleshooting and the original YOLO toolkit reference |

## Installation

### Easiest: download a release

Download the packaged app from the [Releases](../../releases) page, unzip it, and keep the app and
its `models` folder together. The macOS app is not code-signed, so the first time you open it,
right-click it and choose **Open**. For RTSP cameras, install [VLC](https://www.videolan.org/).

### Raspberry Pi 5 (with Hailo AI HAT+)

1. Create a bootable **Raspberry Pi OS Bookworm 64-bit Desktop** on a USB drive, SSD or SD card. **Do not use Trixie.**
2. Download this repository (green **Code** button → **Download ZIP**) and unzip it on the Pi.
3. In a terminal in the unzipped folder, run the installer and answer **Y** to its questions:
   ```sh
   chmod +x install/install_raspberry_pi_universal.sh
   ./install/install_raspberry_pi_universal.sh
   sudo reboot
   ```
   It creates `~/ai-pest-cannon` with a Python environment (`yolo-env`) and the launchers.
4. Copy the app files and models into place:
   ```sh
   cp app/ai_pest_cannon.py app/custom.wav app/coco.txt ~/ai-pest-cannon/
   cp -r hailo_models ~/
   ```
5. Start it by double-clicking `~/ai-pest-cannon/launch_ai_pest_cannon.sh`, or run it in a terminal. If the window doesn't appear, use `launch_ai_pest_cannon_xcb.sh` instead.

The app's default Hailo model is `~/hailo_models/yolov11m.hef`. This repo includes `yolov11n.hef`
and `yolov11s.hef`, so select one of those in Settings, or add `yolov11m.hef` from the Hailo Model Zoo.

### Linux, macOS or Windows (from source)

Run the matching installer from `install/`: `install_linux_universal.sh`, `install_mac_universal.sh`
or `install_windows_universal.bat`. Each one creates `~/ai-pest-cannon` (`%USERPROFILE%\ai-pest-cannon`
on Windows) with a `yolo-env` Python environment. Then copy `app/ai_pest_cannon.py` and
`app/custom.wav` into that folder and start it with the matching `launch_ai_pest_cannon_universal_*` launcher.

On a Mac, developers can instead run `bash scripts/01_setup.sh` and `bash scripts/02_verify.sh`
once, then start the app with `./run_from_source.sh`.

## Where things are saved

- Detections: `~/detections`
- Logs: `~/cannon-logs`
- Settings: `~/.config/ai_pest_cannon/settings.json` (`%APPDATA%\ai_pest_cannon\settings.json` on Windows)

## Tips

- Read the User Guide PDF.
- Make your own alert sound: just name it `custom.wav` and put it beside `ai_pest_cannon.py`.
- RTSP streams are convenient, but a USB or CSI camera gives the best inference speed and detection. Use the smaller models if needed (e.g. `yolov11n.hef`, or `yolo11n.pt` on CPU).
- The app works with CPU fallback, but it's very slow. On a Pi, the AI HAT+ 26 TOPS (or the Raspberry Pi AI Camera with its built-in Hailo NPU) is far better.
- Flashing lights, horns, or anything else that can be switched by a relay will scare off pests, but an impact sprinkler works very well. Choose your weapons wisely!
- You can train your own models: YOLOv8 or YOLO11 for Hailo on the Pi; v8, 11 or 26 on Mac, Windows and Linux.

Have fun and happy pest hunting :)

## Building the standalone app

See [packaging/README.md](packaging/README.md). Briefly: `bash packaging/build_mac.sh` on a Mac, or
`packaging\build_windows.bat` on Windows.

## Licence

**AGPL-3.0**: see [LICENSE](LICENSE). This project uses [Ultralytics YOLO](https://github.com/ultralytics/ultralytics),
which is also AGPL-3.0, and the AI Pest Cannon is released under the same licence.
