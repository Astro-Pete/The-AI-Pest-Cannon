# ==================================================
# File: rthook_models_folder.py
# Description: PyInstaller runtime hook: start the packaged app in its models folder; build self-test.
# Created: 2026-10-14 17:26 (UTC)
# Last modified: 2026-10-14 17:38 (UTC)
# Change log:
#   2026-10-14 17:26 - Initial creation.
#   2026-10-14 17:38 - Add the build self-test (AI_PEST_CANNON_SELF_TEST).
# ==================================================
# The app opens YOLO weights by name (yolo11m.pt etc.) from the working folder, as the source
# launcher does from models/. Do the same for the packaged app, whatever folder it was started from.
import os
import sys

if getattr(sys, "frozen", False):
    _folder = os.path.dirname(os.path.abspath(sys.executable))
    if sys.platform == "darwin" and _folder.endswith(".app/Contents/MacOS"):
        _folder = os.path.dirname(os.path.dirname(os.path.dirname(_folder)))
    _models = os.path.join(_folder, "models")
    os.makedirs(_models, exist_ok=True)
    os.chdir(_models)

# Build self-test: with AI_PEST_CANNON_SELF_TEST=<result file>, check the parts that were missing from
# the first packaged build (torchvision ops, python-vlc and libVLC, the alert sound), write the result
# to that file and exit before the GUI starts. A windowed app has no console, hence the file.
_result_file = os.environ.get("AI_PEST_CANNON_SELF_TEST")
if getattr(sys, "frozen", False) and _result_file:
    _lines, _ok = [], True
    try:
        import torch
        import torchvision.ops
        torchvision.ops.nms(torch.tensor([[0.0, 0.0, 1.0, 1.0]]), torch.tensor([1.0]), 0.5)
        _lines.append("PASS torchvision nms")
    except Exception as exc:  # noqa: BLE001
        _ok = False; _lines.append(f"FAIL torchvision nms: {exc!r}")
    try:
        import vlc
        _lines.append("PASS python-vlc" + (" with libVLC " + vlc.libvlc_get_version().decode() if vlc.libvlc_get_version() else ""))
    except Exception as exc:  # noqa: BLE001
        # python-vlc must be bundled; libVLC itself comes from the VLC installation on the computer.
        if isinstance(exc, ImportError):
            _ok = False
        _lines.append(f"{'FAIL' if isinstance(exc, ImportError) else 'WARN'} python-vlc/libVLC: {exc!r}")
    _wav = os.path.join(getattr(sys, "_MEIPASS", ""), "custom.wav")
    _ok = _ok and os.path.isfile(_wav)
    _lines.append(("PASS" if os.path.isfile(_wav) else "FAIL") + " custom.wav")
    with open(_result_file, "w", encoding="utf-8") as _f:
        _f.write("\n".join(_lines) + "\n")
    os._exit(0 if _ok else 1)
