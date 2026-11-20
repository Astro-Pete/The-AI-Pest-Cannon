# -*- mode: python ; coding: utf-8 -*-
# ==================================================
# File: AIPestCannon.spec
# Description: PyInstaller rules for the AI Pest Cannon (one-folder build; .exe on Windows, .app on macOS).
# Created: 2026-10-14 17:26 (UTC)
# Last modified: 2026-10-14 17:37 (UTC)
# Change log:
#   2026-10-14 17:26 - Initial creation, replacing build_mac_app.sh.
#   2026-10-14 17:37 - Bundle torchvision ops, python-vlc and lap; ask for Local Network access on macOS.
# ==================================================
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH).resolve()
APP = ROOT.parent / "app"
NAME = "AI Pest Cannon"

datas = [(str(APP / "custom.wav"), ".")]   # the alert sound is looked up beside the script
binaries = []
# vlc is imported inside the RTSP worker process; lap is used by the Ultralytics tracker.
hiddenimports = ["paho.mqtt.client", "vlc", "lap"]
# ultralytics: model configs and assets are data files. torchvision: its compiled ops (nms) are needed
# by YOLO post-processing and are missed without collect_all ("operator torchvision::nms does not exist").
for package in ("ultralytics", "torchvision"):
    d, b, h = collect_all(package)
    datas += d; binaries += b; hiddenimports += h

a = Analysis(
    [str(APP / "ai_pest_cannon.py")],
    datas=datas,
    binaries=binaries,
    hiddenimports=hiddenimports,
    runtime_hooks=[str(ROOT / "rthook_models_folder.py")],
    excludes=["tkinter"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name=NAME, console=False, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name=NAME, upx=False)
if sys.platform == "darwin":
    app = BUNDLE(coll, name=NAME + ".app", bundle_identifier="uk.peterdenny.aipestcannon",
                 info_plist={"NSCameraUsageDescription": "The AI Pest Cannon watches a camera for pests.",
                            # Without this, macOS blocks the RTSP camera and MQTT broker on the local network.
                            "NSLocalNetworkUsageDescription": "The AI Pest Cannon connects to your RTSP camera and MQTT broker on the local network."})
