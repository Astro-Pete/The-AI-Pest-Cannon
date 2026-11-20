# ==================================================
# File: build.py
# Description: Build the AI Pest Cannon for this OS (Windows folder with .exe, or macOS .app) with a start-up check.
# Created: 2026-10-14 17:26 (UTC)
# Last modified: 2026-10-14 17:38 (UTC)
# Change log:
#   2026-10-14 17:26 - Initial creation, following the ComSim app build kits.
#   2026-10-14 17:38 - Run the packaged self-test before the start-up check.
# ==================================================

import argparse
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
APP_NAME = "AI Pest Cannon"


def run(command, *, env=None, log=None, cwd=ROOT):
    print("Running:", subprocess.list2cmdline([str(x) for x in command]), flush=True)
    if log is None:
        subprocess.run(command, cwd=cwd, env=env, check=True)
    else:
        with log.open("w", encoding="utf-8") as output:
            result = subprocess.run(command, cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT)
        if result.returncode:
            print(log.read_text(encoding="utf-8", errors="replace")[-12000:])
            raise RuntimeError(f"Build failed; full log: {log}")


def check_starts(exe, env, seconds=25):
    """The app has no self-test: start it without a visible window and make sure it keeps running."""
    env = dict(env, QT_QPA_PLATFORM="offscreen")
    process = subprocess.Popen([str(exe)], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        time.sleep(seconds)
        if process.poll() is not None:
            raise RuntimeError("The packaged app exited during start-up:\n" + process.stdout.read().decode(errors="replace"))
        print(f"PASS: packaged app started and was still running after {seconds} s.", flush=True)
    finally:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()


def self_test(exe, env, work):
    """Run the packaged checks in rthook_models_folder.py (torchvision ops, python-vlc, alert sound)."""
    result = work / "self-test.txt"
    result.unlink(missing_ok=True)
    code = subprocess.run([str(exe)], env=dict(env, AI_PEST_CANNON_SELF_TEST=str(result)), timeout=300).returncode
    text = result.read_text(encoding="utf-8") if result.is_file() else "(no result written)\n"
    print(text, end="", flush=True)
    if code:
        raise RuntimeError("Packaged self-test failed; see the lines above.")


def main():
    parser = argparse.ArgumentParser(description="Build the AI Pest Cannon for this machine's OS and architecture.")
    parser.add_argument("--use-current-python", action="store_true", help="Use already installed dependencies; skip venv/pip setup.")
    parser.add_argument("--models", default="all", help="Comma-separated model files to copy from ../models (default: all).")
    args = parser.parse_args()
    if sys.platform not in ("darwin", "win32"):
        parser.error("Run on Windows for an .exe or on macOS for an .app.")
    if not (3, 10) <= sys.version_info[:2] <= (3, 12):
        parser.error("Use Python 3.10-3.12 (3.11 recommended); set PEST_PYTHON to its executable.")
    kind = "macos" if sys.platform == "darwin" else "windows"
    target = f"{kind}-{platform.machine().lower()}"
    work = ROOT / "build" / target
    dist = ROOT / "dist" / target
    work.mkdir(parents=True, exist_ok=True)
    python = Path(sys.executable)
    if not args.use_current_python:
        venv = ROOT / (".venv-" + target)
        python = venv / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        if not python.exists():
            run([sys.executable, "-m", "venv", str(venv)])
        run([str(python), "-m", "pip", "install", "--upgrade", "pip"])
        run([str(python), "-m", "pip", "install", "--upgrade", "-r", str(ROOT / "requirements-build.txt")])
    run([str(python), "-c", "import PyInstaller, PySide6, ultralytics, cv2, torch, paho.mqtt.client; "
                            "print('Build dependencies available; torch', torch.__version__, "
                            "'CUDA' if torch.cuda.is_available() else 'no CUDA')"])
    run([str(python), "-m", "py_compile", str(PROJECT / "app" / "ai_pest_cannon.py")])
    env = dict(os.environ, PYINSTALLER_CONFIG_DIR=str(work / "pyinstaller-cache"))
    log = work / "pyinstaller.log"
    print(f"Packaging (this takes several minutes); log: {log}", flush=True)
    run([str(python), "-m", "PyInstaller", "--noconfirm", "--clean",
         "--distpath", str(dist), "--workpath", str(work / "pyinstaller"),
         str(ROOT / "AIPestCannon.spec")], env=env, log=log)
    if sys.platform == "darwin":
        shutil.rmtree(dist / APP_NAME, ignore_errors=True)   # the one-folder copy is inside the .app
        exe, home = dist / (APP_NAME + ".app") / "Contents/MacOS" / APP_NAME, dist
    else:
        home = dist / APP_NAME
        exe = home / (APP_NAME + ".exe")
    if not exe.is_file():
        raise RuntimeError(f"Missing built executable: {exe}")
    # The YOLO weights are opened by name from models/ beside the app (see rthook_models_folder.py).
    models = home / "models"
    models.mkdir(exist_ok=True)
    wanted = None if args.models == "all" else {m.strip() for m in args.models.split(",") if m.strip()}
    for weights in sorted((PROJECT / "models").glob("*.pt")):
        if wanted is None or weights.name in wanted:
            shutil.copy2(weights, models / weights.name)
    print(f"Copied {len(list(models.glob('*.pt')))} model files to {models}", flush=True)
    self_test(exe, env, work)
    check_starts(exe, env)
    print(f"Build complete: {home}")
    print("Copy the whole folder (the app and its models folder) to the target computer.")


if __name__ == "__main__":
    try:
        main()
    except (subprocess.CalledProcessError, OSError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
