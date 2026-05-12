#!/usr/bin/env python3
"""
The AI Pest Cannon — YOLO + MQTT + ROI

Modern PySide6 GUI version of pest_canon_mac_v2.py.

Install:
  python3 -m pip install PySide6 ultralytics opencv-python numpy paho-mqtt torch

Run:
  python3 ai_pest_cannon.py
"""

from __future__ import annotations

import dataclasses
import datetime
import json
import os
import platform
import sys
import threading
import multiprocessing as mp
import queue
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple
from urllib.parse import urlparse

import cv2
import numpy as np
import torch

try:
    from PySide6.QtCore import Qt, QThread, Signal, QRectF, QPointF, QTimer
    from PySide6.QtGui import QColor, QFont, QImage, QMouseEvent, QPainter, QPen, QWheelEvent
    from PySide6.QtWidgets import (
        QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog,
        QFormLayout, QFrame, QGroupBox, QHBoxLayout, QLabel,
        QLineEdit, QMainWindow, QMessageBox, QPushButton,
        QScrollArea, QSizePolicy, QSpinBox, QTabWidget, QTextEdit, QVBoxLayout, QWidget
    )
except ImportError:
    print("[ERROR] PySide6 is required for the GUI version.")
    print("Install it with: python3 -m pip install PySide6")
    raise

MODEL_CHOICES = [
    "yolov8n.pt", "yolov8s.pt", "yolov8m.pt", "yolov8l.pt", "yolov8x.pt",
    "yolo11n.pt", "yolo11s.pt", "yolo11m.pt", "yolo11l.pt", "yolo11x.pt",
    "yolo26n.pt", "yolo26s.pt", "yolo26m.pt", "yolo26l.pt", "yolo26x.pt",
]
DEFAULT_PEST_CLASSES = "fox,badger,bird,pigeon,cat,dog,wolf,squirrel,rabbit"
DEFAULT_SAFE_CLASSES = "person,"

@dataclass
class AppConfig:
    source: str = "rtsp"
    usb: int = 0
    rtsp: str = "rtsp://thingino:thingino@192.168.2.233:554/ch1"
    width: int = 1280
    height: int = 720
    fps: int = 30
    flip: bool = False
    night_vision: bool = False
    debug_camera: bool = False
    rtsp_stale_seconds: float = 8.0
    rtsp_reconnect_delay: float = 30.0
    rtsp_open_timeout_ms: int = 10000
    rtsp_read_timeout_ms: int = 10000
    rtsp_backend: str = "opencv"  # opencv, vlc
    backend: str = "auto"  # auto, hailo, cpu
    hef_model: str = "~/hailo_models/yolov11m.hef"
    model: str = "yolo11m.pt"
    classes: str = "coco.txt"
    conf: float = 0.35
    iou: float = 0.70
    imgsz: int = 1024
    skip_frames: int = 1
    device: str = "auto"
    pest_classes: str = DEFAULT_PEST_CLASSES
    safe_classes: str = DEFAULT_SAFE_CLASSES
    draw_all: bool = True
    roi_enabled: bool = True
    roi_rects: Optional[List[Tuple[int, int, int, int]]] = None
    confirm_frames: int = 4
    cannon_fire: float = 5.0
    cannon_holdoff: float = 15.0
    dry_run: bool = False
    save_detections: bool = True
    save_dir: str = "~/detections"
    save_every_detection: bool = False
    alert_sound: bool = True
    alert_sound_holdoff: float = 5.0
    log_save_dir: str = "~/cannon-logs"
    output_mode: str = "mqtt"  # dry, mqtt, gpio, both
    force_off_on_shutdown: bool = True
    gpio_enabled: bool = False
    gpio_pin: int = 17
    gpio_active_high: bool = True
    gpio_backend: str = "auto"  # auto, gpiozero, RPi.GPIO
    mqtt_enabled: bool = True
    mqtt_host: str = "192.168.1.120"
    mqtt_port: int = 1883
    mqtt_user: str = "mqtt-user"
    mqtt_pass: str = "mqttuser"
    mqtt_client_id: str = ""
    mqtt_topic: str = "pest"
    mqtt_payload: str = "ON"
    mqtt_off_topic: str = "pest"
    mqtt_off_payload: str = "OFF"
    mqtt_qos: int = 0
    mqtt_retain: bool = False
    mqtt_keepalive: int = 60
    mqtt_json: bool = False


def human_ts() -> str:
    return datetime.datetime.now().strftime("%H:%M:%S")


def file_ts() -> str:
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")


def parse_classes(csv: str) -> Set[str]:
    return {c.strip().lower() for c in csv.split(",") if c.strip()}


def detect_runtime_platform() -> Dict[str, object]:
    system = platform.system().lower()
    machine = platform.machine().lower()
    is_linux = system == "linux"
    is_raspberry_pi = False
    model_text = ""
    if is_linux:
        for probe_path in ("/sys/firmware/devicetree/base/model", "/proc/device-tree/model"):
            try:
                with open(probe_path, "r", encoding="utf-8", errors="ignore") as f:
                    model_text = f.read().strip()
                if "raspberry pi" in model_text.lower():
                    is_raspberry_pi = True
                    break
            except Exception:
                pass
    return {
        "system": system,
        "machine": machine,
        "is_windows": system == "windows",
        "is_macos": system == "darwin",
        "is_linux": is_linux,
        "is_raspberry_pi": is_raspberry_pi,
        "model": model_text,
    }


RUNTIME_PLATFORM = detect_runtime_platform()
FPS_REPORT_INTERVAL_SECONDS = 5.0


def default_settings_path() -> str:
    if platform.system().lower() == "windows":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return str(Path(base) / "ai_pest_cannon" / "settings.json")
    return os.path.expanduser("~/.config/ai_pest_cannon/settings.json")


def _normalize_roi_rects(raw_rects) -> List[Tuple[int, int, int, int]]:
    rects: List[Tuple[int, int, int, int]] = []
    if not isinstance(raw_rects, (list, tuple)):
        return rects
    for rect in raw_rects:
        if not isinstance(rect, (list, tuple)) or len(rect) != 4:
            continue
        try:
            x, y, w, h = [int(v) for v in rect]
        except Exception:
            continue
        if w > 0 and h > 0:
            rects.append((x, y, w, h))
    return rects


def app_config_from_dict(raw: Dict[str, object]) -> AppConfig:
    if not isinstance(raw, dict):
        return AppConfig()
    valid_keys = set(AppConfig.__dataclass_fields__.keys())
    cleaned: Dict[str, object] = {k: v for k, v in raw.items() if k in valid_keys}
    cfg = dataclasses.replace(AppConfig(), **cleaned)
    cfg.roi_rects = _normalize_roi_rects(cfg.roi_rects)
    return cfg




def play_alert_sound(log=None) -> None:
    """Play a non-blocking alert sound.

    custom.wav beside this Python script is preferred on every platform.

    If custom.wav is missing:
      - macOS uses the built-in system Ping sound.
      - Windows uses the built-in message beep.
      - Linux/Raspberry Pi logs a warning and plays nothing.

    Linux/Raspberry Pi intentionally do NOT search/play bundled system sounds.
    """
    try:
        system = platform.system().lower()
        script_dir = os.path.dirname(os.path.abspath(__file__))
        custom_path = os.path.join(script_dir, "custom.wav")

        if os.path.exists(custom_path):
            if system == "darwin":
                import subprocess
                subprocess.Popen(
                    ["afplay", custom_path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return

            if system == "windows":
                try:
                    import winsound
                    winsound.PlaySound(custom_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
                except Exception as e:
                    if log:
                        log(f"[SOUND] custom.wav failed: {e}")
                return

            # Linux / Raspberry Pi: custom.wav only. Do not fall back to old system sounds.
            import shutil
            import subprocess
            if shutil.which("aplay"):
                subprocess.Popen(
                    ["aplay", "-q", custom_path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return
            if shutil.which("paplay"):
                subprocess.Popen(
                    ["paplay", custom_path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return
            if shutil.which("ffplay"):
                subprocess.Popen(
                    ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", custom_path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return
            if log:
                log("[SOUND] custom.wav found but no supported Linux audio player is available. Install alsa-utils for aplay.")
            return

        # No custom.wav. macOS/Windows may use their platform defaults.
        if system == "darwin":
            import subprocess
            subprocess.Popen(
                ["afplay", "/System/Library/Sounds/Ping.aiff"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return

        if system == "windows":
            try:
                import winsound
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            except Exception:
                try:
                    import winsound
                    winsound.Beep(1200, 120)
                except Exception:
                    pass
            return

        # Linux / Raspberry Pi: no custom.wav means no sound by design.
        if log:
            log(f"[SOUND] custom.wav not found in {script_dir}; no alert sound played")
    except Exception as e:
        if log:
            log(f"[SOUND] Alert sound failed: {e}")

def format_payload(template: str, labels: Iterable[str]) -> str:
    labels_sorted = sorted(labels)
    return template.format(
        labels=",".join(labels_sorted),
        labels_json=json.dumps(labels_sorted),
        timestamp=datetime.datetime.now().isoformat(timespec="seconds"),
    )


def bgr_to_qimage(frame_bgr: np.ndarray) -> QImage:
    # Make the array explicitly contiguous before exposing it to Qt.
    # Some OpenCV/RTSP frames can have strides that otherwise make QImage
    # render the wrong region or appear offset/cropped.
    rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    rgb = np.ascontiguousarray(rgb)
    h, w, ch = rgb.shape
    return QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888).copy()


def clamp_roi(x: int, y: int, w: int, h: int, frame_w: int, frame_h: int) -> Optional[Tuple[int, int, int, int]]:
    x1 = max(0, min(frame_w - 1, int(x)))
    y1 = max(0, min(frame_h - 1, int(y)))
    x2 = max(0, min(frame_w, int(x + w)))
    y2 = max(0, min(frame_h, int(y + h)))
    if x2 < x1:
        x1, x2 = x2, x1
    if y2 < y1:
        y1, y2 = y2, y1
    rw = x2 - x1
    rh = y2 - y1
    if rw < 5 or rh < 5:
        return None
    return (x1, y1, rw, rh)



def _rtsp_process_main(cfg_dict, frame_queue, status_queue, stop_event):
    """RTSP worker process.

    OpenCV/FFmpeg runs in this child process so a hard native-code RTSP stall can
    be terminated without locking the Qt GUI / detection process.
    """
    import os as _os
    import time as _time

    import cv2 as _cv2

    rtsp_url = cfg_dict.get("rtsp", "")
    read_timeout_ms = int(cfg_dict.get("rtsp_read_timeout_ms", 5000))
    open_timeout_ms = int(cfg_dict.get("rtsp_open_timeout_ms", 8000))
    stimeout_us = int(read_timeout_ms * 1000)

    _os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
        f"rtsp_transport;tcp"
        f"|stimeout;{stimeout_us}"
        f"|rw_timeout;{stimeout_us}"
        f"|max_delay;500000"
    )

    cap = None
    try:
        status_queue.put(("info", f"Connecting RTSP process: {rtsp_url}"))
        cap = _cv2.VideoCapture(rtsp_url, _cv2.CAP_FFMPEG)
        try:
            cap.set(_cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, int(open_timeout_ms))
            cap.set(_cv2.CAP_PROP_READ_TIMEOUT_MSEC, int(read_timeout_ms))
            cap.set(_cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass

        if not cap or not cap.isOpened():
            status_queue.put(("error", "Could not open RTSP stream"))
            return

        status_queue.put(("ready", "RTSP process connected"))

        while not stop_event.is_set():
            try:
                ret, frame = cap.read()
            except Exception as e:
                status_queue.put(("error", f"RTSP read exception: {e}"))
                ret, frame = False, None

            if stop_event.is_set():
                break

            if ret and frame is not None:
                # Keep only the latest frame. Drop stale frames rather than
                # allowing a backlog to build while inference is busy.
                try:
                    while True:
                        frame_queue.get_nowait()
                except Exception:
                    pass
                try:
                    frame_queue.put_nowait((_time.time(), frame))
                except Exception:
                    pass
            else:
                _time.sleep(0.02)
    finally:
        try:
            if cap is not None:
                cap.release()
        except Exception:
            pass
        try:
            status_queue.put(("stopped", "RTSP process stopped"))
        except Exception:
            pass


class ProcessRTSPCapture:
    """RTSP capture backend using a separate child process."""

    def __init__(self, cfg: AppConfig, log):
        self.cfg = dataclasses.replace(cfg)
        self.log = log
        self._ctx = mp.get_context("spawn")
        self._frame_queue = self._ctx.Queue(maxsize=2)
        self._status_queue = self._ctx.Queue(maxsize=20)
        self._stop_event = self._ctx.Event()
        self._process: Optional[mp.Process] = None
        self._latest_frame: Optional[np.ndarray] = None
        self._last_good = 0.0
        self._last_status_poll = 0.0
        self._start_process()

    def _cfg_dict(self) -> Dict[str, object]:
        return {
            "rtsp": self.cfg.rtsp,
            "rtsp_read_timeout_ms": int(self.cfg.rtsp_read_timeout_ms),
            "rtsp_open_timeout_ms": int(self.cfg.rtsp_open_timeout_ms),
        }

    def _start_process(self) -> None:
        self._stop_event.clear()
        self._last_good = time.time()
        self.log(f"[CAM] Starting RTSP process: {self.cfg.rtsp}")
        self._process = self._ctx.Process(
            target=_rtsp_process_main,
            args=(self._cfg_dict(), self._frame_queue, self._status_queue, self._stop_event),
            daemon=True,
            name="RTSPCaptureProcess",
        )
        self._process.start()
        self.log(f"[CAM] RTSP process PID {self._process.pid}")

    def _poll_status(self) -> None:
        now = time.time()
        if now - self._last_status_poll < 0.25:
            return
        self._last_status_poll = now
        while True:
            try:
                level, message = self._status_queue.get_nowait()
            except queue.Empty:
                break
            except Exception:
                break
            self.log(f"[CAM] {message}")

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        self._poll_status()
        while True:
            try:
                ts, frame = self._frame_queue.get_nowait()
            except queue.Empty:
                break
            except Exception:
                break
            self._latest_frame = frame
            self._last_good = float(ts)

        if self._latest_frame is None:
            return False, None
        return True, self._latest_frame.copy()

    def age(self) -> float:
        self._poll_status()
        if self._process is not None and not self._process.is_alive():
            return 1e9
        if self._last_good <= 0:
            return 1e9
        return time.time() - self._last_good

    def close(self) -> None:
        self._stop_event.set()
        proc = self._process
        if proc is not None:
            proc.join(timeout=0.15)
            if proc.is_alive():
                self.log(f"[CAM] RTSP process PID {proc.pid} stuck — terminating")
                try:
                    proc.terminate()
                except Exception:
                    pass
                proc.join(timeout=0.20)
            if proc.is_alive():
                self.log(f"[CAM] RTSP process PID {proc.pid} still alive — killing/abandoning")
                try:
                    proc.kill()
                except Exception:
                    pass
                proc.join(timeout=0.10)
        self._process = None
        self._latest_frame = None
        for q in (self._frame_queue, self._status_queue):
            try:
                q.cancel_join_thread()
            except Exception:
                pass
            try:
                q.close()
            except Exception:
                pass


def _detect_rtsp_resolution(rtsp_url: str, timeout_s: float = 4.0) -> Optional[Tuple[int, int]]:
    """Return (width, height) for an RTSP stream using ffprobe when available.

    libVLC video callbacks need a fixed output size before playback starts.
    If ffprobe is not installed or cannot open the stream quickly, the caller
    falls back to the GUI width/height fields.
    """
    if not rtsp_url:
        return None
    try:
        import subprocess
        cmd = [
            "ffprobe",
            "-rtsp_transport", "tcp",
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "csv=s=x:p=0",
            rtsp_url,
        ]
        cp = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=float(timeout_s),
        )
        if cp.returncode == 0:
            lines = [ln.strip() for ln in (cp.stdout or "").splitlines() if ln.strip()]
            if lines and "x" in lines[0]:
                w_s, h_s = lines[0].split("x", 1)
                w, h = int(w_s), int(h_s)
                if w >= 160 and h >= 120:
                    return w, h
    except Exception:
        pass
    return None


def _vlc_rtsp_process_main(cfg_dict, frame_queue, status_queue, stop_event):
    """RTSP worker process using libVLC instead of OpenCV/FFmpeg.

    VLC is often more tolerant of RTSP jitter/H.264 stream damage than
    cv2.VideoCapture. Running it in a separate process keeps the GUI killable
    if the native decoder blocks.
    """
    import ctypes as _ctypes
    import time as _time
    import numpy as _np

    try:
        import vlc as _vlc
    except Exception as e:
        try:
            status_queue.put(("error", f"python-vlc/libVLC not available: {e}"))
        except Exception:
            pass
        return

    rtsp_url = str(cfg_dict.get("rtsp", ""))
    width = max(160, int(cfg_dict.get("width", 1280)))
    height = max(120, int(cfg_dict.get("height", 720)))
    read_timeout_ms = max(1000, int(cfg_dict.get("rtsp_read_timeout_ms", 5000)))
    open_timeout_ms = max(1000, int(cfg_dict.get("rtsp_open_timeout_ms", 8000)))
    network_cache_ms = max(150, min(2000, int(cfg_dict.get("vlc_network_cache_ms", 350))))
    detect_timeout_s = min(4.0, max(1.0, open_timeout_ms / 1000.0))
    detected = _detect_rtsp_resolution(rtsp_url, timeout_s=detect_timeout_s)
    if detected:
        width, height = detected

    pitch = width * 3
    buffer_size = pitch * height
    frame_buffer = (_ctypes.c_ubyte * buffer_size)()
    frame_ptr = _ctypes.cast(frame_buffer, _ctypes.c_void_p)
    first_frame_sent = [False]
    last_frame_time = [_time.time()]
    last_warning_time = [0.0]

    def _put_status(level, message):
        try:
            status_queue.put_nowait((level, message))
        except Exception:
            pass

    def _put_latest_frame(frame_bgr):
        try:
            while True:
                frame_queue.get_nowait()
        except Exception:
            pass
        try:
            frame_queue.put_nowait((_time.time(), frame_bgr))
        except Exception:
            pass

    @_vlc.CallbackDecorators.VideoLockCb
    def _lock_cb(opaque, planes):
        planes[0] = frame_ptr
        return None

    @_vlc.CallbackDecorators.VideoUnlockCb
    def _unlock_cb(opaque, picture, planes):
        return None

    @_vlc.CallbackDecorators.VideoDisplayCb
    def _display_cb(opaque, picture):
        try:
            # RV24 is RGB byte order. The rest of the app expects BGR frames.
            rgb = _np.frombuffer(frame_buffer, dtype=_np.uint8).reshape((height, width, 3)).copy()
            bgr = rgb[:, :, ::-1].copy()
            last_frame_time[0] = _time.time()
            if not first_frame_sent[0]:
                first_frame_sent[0] = True
                _put_status("ready", f"VLC RTSP first frame {width}x{height}")
            _put_latest_frame(bgr)
        except Exception as e:
            _put_status("error", f"VLC frame callback error: {e}")

    instance = None
    player = None
    try:
        _put_status("info", f"Starting VLC RTSP process: {rtsp_url}")
        if detected:
            _put_status("info", f"Auto-detected RTSP resolution {width}x{height}")
        else:
            _put_status("info", f"Could not auto-detect RTSP resolution — using GUI fallback {width}x{height}")
        instance = _vlc.Instance(
            "--no-audio",
            "--no-video-title-show",
            "--rtsp-tcp",
            f"--network-caching={network_cache_ms}",
            "--drop-late-frames",
            "--skip-frames",
            "--quiet",
        )
        media = instance.media_new(rtsp_url)
        media.add_option(":rtsp-tcp")
        media.add_option(f":network-caching={network_cache_ms}")
        media.add_option(":drop-late-frames")
        media.add_option(":skip-frames")

        player = instance.media_player_new()
        player.set_media(media)
        player.video_set_callbacks(_lock_cb, _unlock_cb, _display_cb, None)
        player.video_set_format("RV24", width, height, pitch)

        play_result = player.play()
        if play_result == -1:
            _put_status("error", "VLC failed to start RTSP playback")
            return

        _put_status("info", f"VLC RTSP connecting, output {width}x{height}, cache {network_cache_ms} ms")

        open_deadline = _time.time() + (open_timeout_ms / 1000.0)
        while not stop_event.is_set() and not first_frame_sent[0] and _time.time() < open_deadline:
            state = player.get_state()
            if state == _vlc.State.Error:
                _put_status("error", "VLC RTSP entered Error state during open")
                return
            _time.sleep(0.05)

        if not first_frame_sent[0]:
            _put_status("error", f"VLC RTSP open timeout after {open_timeout_ms} ms")

        while not stop_event.is_set():
            state = player.get_state()
            if state in (_vlc.State.Error, _vlc.State.Ended):
                _put_status("error", f"VLC RTSP stopped with state {state}")
                break
            age_ms = (_time.time() - last_frame_time[0]) * 1000.0
            if first_frame_sent[0] and age_ms > read_timeout_ms:
                now = _time.time()
                if now - last_warning_time[0] > 2.0:
                    last_warning_time[0] = now
                    _put_status("error", f"VLC RTSP stale frame age {age_ms:.0f} ms")
            _time.sleep(0.1)
    finally:
        try:
            if player is not None:
                player.stop()
        except Exception:
            pass
        try:
            if player is not None:
                player.release()
        except Exception:
            pass
        try:
            if instance is not None:
                instance.release()
        except Exception:
            pass
        _put_status("stopped", "VLC RTSP process stopped")


class VlcRTSPCapture:
    """RTSP capture backend using python-vlc/libVLC in a separate child process."""

    def __init__(self, cfg: AppConfig, log):
        self.cfg = dataclasses.replace(cfg)
        self.log = log
        self._ctx = mp.get_context("spawn")
        self._frame_queue = self._ctx.Queue(maxsize=2)
        self._status_queue = self._ctx.Queue(maxsize=30)
        self._stop_event = self._ctx.Event()
        self._process: Optional[mp.Process] = None
        self._latest_frame: Optional[np.ndarray] = None
        self._last_good = 0.0
        self._last_status_poll = 0.0
        self._start_process()

    def _cfg_dict(self) -> Dict[str, object]:
        return {
            "rtsp": self.cfg.rtsp,
            "width": int(self.cfg.width),
            "height": int(self.cfg.height),
            "fps": int(self.cfg.fps),
            "rtsp_read_timeout_ms": int(self.cfg.rtsp_read_timeout_ms),
            "rtsp_open_timeout_ms": int(self.cfg.rtsp_open_timeout_ms),
            "vlc_network_cache_ms": 350,
        }

    def _start_process(self) -> None:
        self._stop_event.clear()
        self._last_good = time.time()
        self.log(f"[CAM] Starting VLC RTSP process: {self.cfg.rtsp}")
        self._process = self._ctx.Process(
            target=_vlc_rtsp_process_main,
            args=(self._cfg_dict(), self._frame_queue, self._status_queue, self._stop_event),
            daemon=True,
            name="VLCRTSPCaptureProcess",
        )
        self._process.start()
        self.log(f"[CAM] VLC RTSP process PID {self._process.pid}")

    def _poll_status(self) -> None:
        now = time.time()
        if now - self._last_status_poll < 0.25:
            return
        self._last_status_poll = now
        while True:
            try:
                level, message = self._status_queue.get_nowait()
            except queue.Empty:
                break
            except Exception:
                break
            self.log(f"[CAM] {message}")

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        self._poll_status()
        while True:
            try:
                ts, frame = self._frame_queue.get_nowait()
            except queue.Empty:
                break
            except Exception:
                break
            self._latest_frame = frame
            self._last_good = float(ts)

        if self._latest_frame is None:
            return False, None
        return True, self._latest_frame.copy()

    def age(self) -> float:
        self._poll_status()
        if self._process is not None and not self._process.is_alive():
            return 1e9
        if self._last_good <= 0:
            return 1e9
        return time.time() - self._last_good

    def close(self) -> None:
        self._stop_event.set()
        proc = self._process
        if proc is not None:
            proc.join(timeout=0.15)
            if proc.is_alive():
                self.log(f"[CAM] VLC RTSP process PID {proc.pid} stuck — terminating")
                try:
                    proc.terminate()
                except Exception:
                    pass
                proc.join(timeout=0.20)
            if proc.is_alive():
                self.log(f"[CAM] VLC RTSP process PID {proc.pid} still alive — killing/abandoning")
                try:
                    proc.kill()
                except Exception:
                    pass
                proc.join(timeout=0.10)

        self._process = None
        self._latest_frame = None
        for q in (self._frame_queue, self._status_queue):
            try:
                q.cancel_join_thread()
            except Exception:
                pass
            try:
                q.close()
            except Exception:
                pass



class GpioOutput:
    def __init__(self, cfg: AppConfig, log):
        self.cfg = cfg
        self.log = log
        self.backend = None
        self.GPIO = None
        self.device = None
        self.ready = False
        if cfg.dry_run or not cfg.gpio_enabled:
            return
        preferred = (cfg.gpio_backend or "auto").lower()
        if preferred in ("auto", "gpiozero"):
            try:
                from gpiozero import OutputDevice
                self.device = OutputDevice(int(cfg.gpio_pin), active_high=bool(cfg.gpio_active_high), initial_value=False)
                self.backend = "gpiozero"
                self.ready = True
                self.log(f"[GPIO] Pin BCM {cfg.gpio_pin} ready via gpiozero/lgpio")
                return
            except Exception as e:
                self.log(f"[GPIO] gpiozero init failed: {e}")
                if preferred == "gpiozero":
                    return
        if preferred in ("auto", "rpi.gpio", "rpi_gpio"):
            try:
                import RPi.GPIO as GPIO
                self.GPIO = GPIO
                GPIO.setmode(GPIO.BCM)
                initial = GPIO.LOW if cfg.gpio_active_high else GPIO.HIGH
                GPIO.setup(int(cfg.gpio_pin), GPIO.OUT, initial=initial)
                self.backend = "RPi.GPIO"
                self.ready = True
                self.log(f"[GPIO] Pin BCM {cfg.gpio_pin} ready via RPi.GPIO")
            except Exception as e:
                self.log(f"[GPIO] RPi.GPIO init failed: {e}")

    def on(self):
        if self.cfg.dry_run or not self.ready:
            self.log("[GPIO] DRY/CONSOLE ON")
            return
        if self.backend == "gpiozero":
            self.device.on()
        elif self.backend == "RPi.GPIO":
            self.GPIO.output(int(self.cfg.gpio_pin), self.GPIO.HIGH if self.cfg.gpio_active_high else self.GPIO.LOW)
        self.log(f"[GPIO] ON pin BCM {self.cfg.gpio_pin}")

    def off(self):
        if self.cfg.dry_run or not self.ready:
            self.log("[GPIO] DRY/CONSOLE OFF")
            return
        if self.backend == "gpiozero":
            self.device.off()
        elif self.backend == "RPi.GPIO":
            self.GPIO.output(int(self.cfg.gpio_pin), self.GPIO.LOW if self.cfg.gpio_active_high else self.GPIO.HIGH)
        self.log(f"[GPIO] OFF pin BCM {self.cfg.gpio_pin}")

    def close(self):
        try:
            self.off()
        except Exception:
            pass
        try:
            if self.backend == "gpiozero" and self.device:
                self.device.close()
            elif self.backend == "RPi.GPIO" and self.GPIO:
                self.GPIO.cleanup(int(self.cfg.gpio_pin))
        except Exception:
            pass


class HailoDetector:
    name = "Hailo AI HAT+"

    def __init__(self, cfg: AppConfig, log):
        self.cfg = cfg
        self.log = log
        try:
            from hailo_platform import (
                HEF, VDevice, ConfigureParams, HailoStreamInterface,
                InferVStreams, InputVStreamParams, OutputVStreamParams,
                FormatType, HailoSchedulingAlgorithm
            )
        except Exception as e:
            raise RuntimeError("hailo_platform not available. Install with: sudo apt install hailo-all && sudo reboot") from e
        self.hp = dict(
            HEF=HEF, VDevice=VDevice, ConfigureParams=ConfigureParams,
            HailoStreamInterface=HailoStreamInterface, InferVStreams=InferVStreams,
            InputVStreamParams=InputVStreamParams, OutputVStreamParams=OutputVStreamParams,
            FormatType=FormatType, HailoSchedulingAlgorithm=HailoSchedulingAlgorithm,
        )
        self.classes = self._load_classes(cfg.classes)
        hef_path = os.path.expanduser(os.path.expandvars(cfg.hef_model))
        if not os.path.exists(hef_path):
            raise RuntimeError(f"HEF model not found: {hef_path}")
        self.log(f"[HAILO] Loading HEF: {hef_path}")
        self.hef = HEF(hef_path)
        vparams = VDevice.create_params()
        vparams.scheduling_algorithm = HailoSchedulingAlgorithm.ROUND_ROBIN
        self.vdevice = VDevice(vparams)
        configure_params = ConfigureParams.create_from_hef(self.hef, interface=HailoStreamInterface.PCIe)
        self.network_group = self.vdevice.configure(self.hef, configure_params)[0]
        self.input_info = self.hef.get_input_vstream_infos()[0]
        self.output_infos = self.hef.get_output_vstream_infos()
        self.input_name = self.input_info.name
        self.in_h, self.in_w, self.in_c = self.input_info.shape
        self.input_params = InputVStreamParams.make(self.network_group, quantized=True, format_type=FormatType.UINT8)
        self.output_params = OutputVStreamParams.make(self.network_group, format_type=FormatType.FLOAT32)
        self.pipeline = InferVStreams(self.network_group, self.input_params, self.output_params)
        self.pipeline.__enter__()
        self.log(f"[HAILO] Input: {self.input_name} shape={self.in_w}x{self.in_h}x{self.in_c}")
        for info in self.output_infos:
            self.log(f"[HAILO] Output: {info.name} shape={info.shape}")
        self.log("[HAILO] Ready")

    def _load_classes(self, path: str) -> List[str]:
        try:
            with open(os.path.expanduser(os.path.expandvars(path)), "r", encoding="utf-8") as f:
                return [line.strip() for line in f if line.strip()]
        except Exception:
            return [str(i) for i in range(80)]

    def infer(self, frame_rgb: np.ndarray) -> List[Tuple[str, float, int, int, int, int]]:
        h, w = frame_rgb.shape[:2]
        resized = cv2.resize(frame_rgb, (self.in_w, self.in_h), interpolation=cv2.INTER_LINEAR)
        batched = np.ascontiguousarray(resized.reshape(1, self.in_h, self.in_w, self.in_c), dtype=np.uint8)
        try:
            results = self.pipeline.infer({self.input_name: batched})
        except Exception as e:
            self.log(f"[HAILO] Inference error: {e}")
            return []
        dets: List[Tuple[str, float, int, int, int, int]] = []
        for out_name, output in results.items():
            dets.extend(self._parse_hailo_nms_output(output, w, h))
        return dets

    def _clip_box(self, x1, y1, x2, y2, w, h):
        x1 = max(0, min(w - 1, int(x1)))
        y1 = max(0, min(h - 1, int(y1)))
        x2 = max(0, min(w - 1, int(x2)))
        y2 = max(0, min(h - 1, int(y2)))
        return x1, y1, x2, y2

    def _parse_hailo_nms_output(self, output, frame_w, frame_h):
        dets = []
        if isinstance(output, np.ndarray):
            if output.shape and output.shape[0] == 1:
                output = output[0]
            if output.dtype == object:
                output = output.tolist()
        elif isinstance(output, (list, tuple)) and len(output) == 1:
            output = output[0]
        try:
            arr = np.asarray(output, dtype=np.float32)
            if arr.ndim == 3 and arr.shape[0] in (80, len(self.classes)):
                for cls_id in range(arr.shape[0]):
                    cls_arr = arr[cls_id]
                    if cls_arr.shape[0] == 5:
                        boxes = cls_arr.T
                    elif cls_arr.shape[-1] == 5:
                        boxes = cls_arr.reshape(-1, 5)
                    else:
                        continue
                    for row in boxes:
                        y1, x1, y2, x2, conf = [float(v) for v in row[:5]]
                        if conf < self.cfg.conf:
                            continue
                        if max(abs(x1), abs(y1), abs(x2), abs(y2)) <= 2.0:
                            x1, x2 = x1 * frame_w, x2 * frame_w
                            y1, y2 = y1 * frame_h, y2 * frame_h
                        x1, y1, x2, y2 = self._clip_box(x1, y1, x2, y2, frame_w, frame_h)
                        if x2 <= x1 or y2 <= y1:
                            continue
                        label = self.classes[cls_id] if cls_id < len(self.classes) else str(cls_id)
                        dets.append((label, float(conf), x1, y1, x2, y2))
                return dets
        except Exception as e:
            if self.cfg.debug_camera:
                self.log(f"[HAILO][DEBUG] NMS parse path-A failed: {e}")
        if isinstance(output, (list, tuple)):
            for cls_id, boxes in enumerate(output):
                try:
                    boxes = np.asarray(boxes, dtype=np.float32)
                except Exception:
                    continue
                if boxes.size == 0:
                    continue
                if boxes.ndim == 1 and boxes.size >= 5:
                    boxes = boxes.reshape(1, -1)
                if boxes.ndim != 2:
                    continue
                if boxes.shape[0] == 5:
                    boxes = boxes.T
                elif boxes.shape[1] != 5:
                    continue
                for row in boxes:
                    y1, x1, y2, x2, conf = [float(v) for v in row[:5]]
                    if conf < self.cfg.conf:
                        continue
                    if max(abs(x1), abs(y1), abs(x2), abs(y2)) <= 2.0:
                        x1, x2 = x1 * frame_w, x2 * frame_w
                        y1, y2 = y1 * frame_h, y2 * frame_h
                    x1, y1, x2, y2 = self._clip_box(x1, y1, x2, y2, frame_w, frame_h)
                    if x2 <= x1 or y2 <= y1:
                        continue
                    label = self.classes[cls_id] if cls_id < len(self.classes) else str(cls_id)
                    dets.append((label, float(conf), x1, y1, x2, y2))
        return dets

    def close(self):
        try:
            if getattr(self, "pipeline", None):
                self.pipeline.__exit__(None, None, None)
        except Exception:
            pass
        try:
            if getattr(self, "vdevice", None):
                self.vdevice.release()
        except Exception:
            pass

class MqttTrigger:
    """Thin wrapper around paho-mqtt.

    Design rules that prevent timing bugs:
    - _lock is held for the MINIMUM time: only while swapping the timer reference
      or reading/writing _is_on/_active_labels. NEVER while publishing or logging.
    - All publishes are fire-and-forget. paho loop_start() delivers in its own
      thread; we never wait for acknowledgement.
    - The OFF timer is started AFTER the ON publish returns so its countdown
      begins from the moment the message is handed to paho, not before.
    """

    def __init__(self, cfg: AppConfig, log):
        self.cfg = cfg
        self.log = log
        self.client = None
        mode = (getattr(cfg, "output_mode", "mqtt") or "mqtt").lower()
        self.use_mqtt = mode in ("mqtt", "both") and bool(cfg.mqtt_enabled)
        self.use_gpio = mode in ("gpio", "both") and bool(getattr(cfg, "gpio_enabled", False))
        self.enabled = self.use_mqtt and bool(cfg.mqtt_host) and not cfg.dry_run
        self.gpio = GpioOutput(cfg, log) if (self.use_gpio or (cfg.dry_run and bool(getattr(cfg, "gpio_enabled", False)))) else None
        self._off_timer: Optional[threading.Timer] = None
        self._lock = threading.Lock()
        self._active_labels: Set[str] = set()
        self._is_on = False
        if not self.use_mqtt:
            self.log("[MQTT] Disabled — no broker connection will be made")
            return
        if cfg.dry_run:
            self.log("[MQTT] DRY RUN — no MQTT messages will be sent")
            return
        if not cfg.mqtt_host:
            self.log("[MQTT] No broker configured — console alerts only")
            return
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            self.log("[MQTT] paho-mqtt not installed. Install with: pip install paho-mqtt")
            self.enabled = False
            return
        try:
            self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=cfg.mqtt_client_id)
            if cfg.mqtt_user:
                self.client.username_pw_set(cfg.mqtt_user, cfg.mqtt_pass)
            self.client.connect(cfg.mqtt_host, cfg.mqtt_port, cfg.mqtt_keepalive)
            self.client.loop_start()
            self.enabled = True
            self.log(f"[MQTT] Connected to {cfg.mqtt_host}:{cfg.mqtt_port} client_id={cfg.mqtt_client_id!r}")
        except Exception as e:
            self.log(f"[MQTT] Connect failed: {e}")
            self.enabled = False

    def _publish(self, topic: str, payload: str):
        """Fire-and-forget publish. Never blocks. Lock must NOT be held by caller."""
        if self.cfg.dry_run or not self.enabled or self.client is None:
            self.log(f"[MQTT] DRY/CONSOLE topic={topic!r} payload={payload!r}")
            return
        try:
            self.client.publish(topic, payload, qos=self.cfg.mqtt_qos, retain=self.cfg.mqtt_retain)
            self.log(f"[MQTT] Published topic={topic!r} payload={payload!r}")
        except Exception as e:
            self.log(f"[MQTT] Publish failed: {e}")

    def _cancel_off_timer(self):
        """Cancel any pending OFF timer. Must be called WITHOUT holding _lock."""
        with self._lock:
            t, self._off_timer = self._off_timer, None
        if t is not None:
            t.cancel()

    def output_on(self, labels: Iterable[str]):
        labels_set = set(labels)
        labels_sorted = sorted(labels_set)
        if self.cfg.mqtt_json:
            payload = json.dumps({"event": "pest", "state": "ON", "labels": labels_sorted,
                                  "timestamp": datetime.datetime.now().isoformat(timespec="seconds")})
        else:
            payload = format_payload(self.cfg.mqtt_payload, labels_sorted)
        if self.use_mqtt:
            self._publish(self.cfg.mqtt_topic, payload)
        elif self.cfg.dry_run:
            self.log(f"[MQTT] DRY/CONSOLE topic={self.cfg.mqtt_topic!r} payload={payload!r}")
        if self.gpio:
            self.gpio.on()

    def output_off(self, labels: Iterable[str]):
        labels_set = set(labels)
        labels_sorted = sorted(labels_set)
        if self.cfg.mqtt_json:
            payload = json.dumps({"event": "pest", "state": "OFF", "labels": labels_sorted,
                                  "timestamp": datetime.datetime.now().isoformat(timespec="seconds")})
        else:
            payload = format_payload(self.cfg.mqtt_off_payload, labels_sorted)
        if self.use_mqtt:
            self._publish(self.cfg.mqtt_off_topic, payload)
        elif self.cfg.dry_run:
            self.log(f"[MQTT] DRY/CONSOLE topic={self.cfg.mqtt_off_topic!r} payload={payload!r}")
        if self.gpio:
            self.gpio.off()

    def trigger_for(self, labels: Iterable[str], seconds: float):
        """Publish ON immediately, schedule OFF after seconds.

        No lock is held during publish or log calls.
        OFF timer starts AFTER publish so its countdown is accurate.
        """
        labels_set = set(labels)
        labels_sorted = sorted(labels_set)

        # Update state flags (lock held briefly, no IO)
        with self._lock:
            self._active_labels = set(labels_set)
            self._is_on = True

        # Log and publish — outside lock
        self.log(f"[ALERT] {human_ts()} PEST DETECTED: {labels_sorted}")
        self.output_on(labels_set)

        if not self.cfg.mqtt_off_topic and not self.gpio:
            return

        # Cancel previous timer and start a fresh one — lock held briefly
        self._cancel_off_timer()
        t = threading.Timer(float(seconds), self._off_callback, args=(labels_set,))
        t.daemon = True
        with self._lock:
            self._off_timer = t
        t.start()
        self.log(f"[MQTT] OFF scheduled in {seconds:.1f}s")

    def _off_callback(self, labels: Set[str]):
        """Called by the OFF timer thread. Clears timer ref then publishes."""
        with self._lock:
            self._off_timer = None
        self.off(labels)

    def off(self, labels: Iterable[str]):
        """Publish OFF and clear state. Safe to call directly (e.g. manual off)."""
        # Clear state flags before publish so a racing trigger_for sees clean state
        with self._lock:
            self._is_on = False
            self._active_labels = set()
        self.output_off(labels)

    def close(self, force_off: bool = True):
        """Cancel timer, optionally send OFF, disconnect cleanly."""
        self._cancel_off_timer()
        with self._lock:
            should_off = force_off and self._is_on and bool(self.cfg.mqtt_off_topic)
            labels_to_off = set(self._active_labels) if should_off else set()
            self._is_on = False

        if labels_to_off:
            self.log("[MQTT] Sending OFF during shutdown/stop")
            self.off(labels_to_off)

        if self.gpio is not None:
            try:
                self.gpio.close()
            except Exception:
                pass

        if self.client is not None:
            try:
                self.client.loop_stop()
                self.client.disconnect()
            except Exception:
                pass

class DetectionWorker(QThread):
    frameReady = Signal(object)
    logMessage = Signal(str)
    statusChanged = Signal(str)
    fpsUpdated = Signal(float)       # current inference FPS
    statsUpdated = Signal(int, int)  # (pest_count, fire_count) session totals
    stopped = Signal()
    manualStateChanged = Signal(str) # "IDLE" | "ONESHOT" | "MANUAL_ON"

    def __init__(self, cfg: AppConfig):
        super().__init__()
        self.cfg = dataclasses.replace(cfg)
        self._running = threading.Event()
        self._running.set()
        self._roi_lock = threading.Lock()
        self._roi_enabled = cfg.roi_enabled
        self._roi_rects = list(cfg.roi_rects or [])
        self.model = None
        self.detector = None
        self.class_names: List[str] = []
        self.device = "cpu"
        self.mqtt: Optional[MqttTrigger] = None
        self.cannon_state = "IDLE"
        self.cannon_state_time = 0.0
        self.confirm_count = 0
        self.confirm_labels: Set[str] = set()
        self.last_detections: List[Tuple[str, float, int, int, int, int]] = []
        self._last_alert_sound_time: float = 0.0
        self._session_pest_count: int = 0
        self._session_fire_count: int = 0
        self._manual_mode: str = "IDLE"  # "IDLE" | "ONESHOT" | "MANUAL_ON"
        self._manual_lock = threading.Lock()

    def log(self, msg: str):
        self.logMessage.emit(msg)

    def set_roi(self, enabled: bool, rects):
        with self._roi_lock:
            self._roi_enabled = enabled
            if rects is None:
                self._roi_rects = []
            elif isinstance(rects, tuple):
                self._roi_rects = [rects]
            else:
                self._roi_rects = list(rects)

    def stop(self):
        self._running.clear()

    def _load_device(self):
        backend = (getattr(self.cfg, "backend", "auto") or "auto").lower()
        is_pi = bool(RUNTIME_PLATFORM.get("is_raspberry_pi"))

        # Hailo is not a PyTorch CUDA/MPS device. Keep the Torch fallback
        # device as CPU unless Hailo successfully loads in _load_model().
        if is_pi and backend in ("auto", "hailo"):
            self.device = "cpu"
            self.log("[INFO] Hailo backend selected — using AI HAT+ if available")
            return

        if is_pi and backend == "cpu" and self.cfg.device == "auto":
            self.device = "cpu"
            self.log("[INFO] CPU YOLO backend selected on Raspberry Pi")
            return

        if self.cfg.device == "auto":
            try:
                if torch.cuda.is_available():
                    self.device = "cuda"
                    self.log("[INFO] Using CUDA")
                    return
            except Exception:
                pass
            try:
                if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                    self.device = "mps"
                    self.log("[INFO] Using MPS (Apple Metal)")
                    return
            except Exception:
                pass
            self.device = "cpu"
            self.log("[INFO] PyTorch CUDA/MPS unavailable — using CPU YOLO backend")
        else:
            self.device = self.cfg.device
            self.log(f"[INFO] Device: {self.device}")

    def _load_model(self):
        backend = (getattr(self.cfg, "backend", "auto") or "auto").lower()
        # Only try Hailo on Raspberry Pi. On Mac/Windows/non-Pi Linux, "auto" means CPU/GPU YOLO.
        is_pi = bool(RUNTIME_PLATFORM.get("is_raspberry_pi"))
        if is_pi and backend in ("auto", "hailo"):
            try:
                self.detector = HailoDetector(self.cfg, self.log)
                self.class_names = list(getattr(self.detector, "classes", []))
                self.device = "hailo"
                return
            except Exception as e:
                if backend == "hailo":
                    raise
                self.device = "cpu"
                if os.environ.get("CUDA_VISIBLE_DEVICES", "").lower() == "hailo":
                    os.environ.pop("CUDA_VISIBLE_DEVICES", None)
                self.log(f"[AUTO] Hailo unavailable, falling back to CPU YOLO: {e}")
                self.log("[AUTO] CPU YOLO fallback device set to cpu")
        if self.device == "hailo":
            self.device = "cpu"
        from ultralytics import YOLO
        self.log(f"[INFO] Loading {self.cfg.model}...")
        self.model = YOLO(self.cfg.model)
        if hasattr(self.model, "names") and self.model.names:
            self.class_names = list(self.model.names.values())
        else:
            try:
                with open(os.path.expanduser(self.cfg.classes)) as f:
                    self.class_names = [line.strip() for line in f if line.strip()]
            except FileNotFoundError:
                self.class_names = []
        self.log(f"[INFO] {len(self.class_names)} classes loaded")
        # Move the underlying torch model to device once at load time so
        # predict() does not reallocate buffers on every call.
        try:
            self.model.to(self.device)
        except Exception as e:
            self.log(f"[WARN] Could not move model to {self.device}: {e}")
        # Run a warm-up pass so MPS JIT compiles the graph before the
        # capture loop starts — avoids a stall on the first real frame.
        try:
            dummy = np.zeros((self.cfg.imgsz, self.cfg.imgsz, 3), dtype=np.uint8)
            with torch.no_grad():
                self.model.predict(dummy, imgsz=self.cfg.imgsz, conf=0.9,
                                   verbose=False, device=self.device)
            if self.device == "mps":
                torch.mps.empty_cache()
            self.log("[INFO] Model warm-up done")
        except Exception as e:
            self.log(f"[WARN] Warm-up failed (non-fatal): {e}")

    def _open_capture(self):
        if self.cfg.source == "rtsp":
            # stimeout is in microseconds. CAP_PROP_READ_TIMEOUT_MSEC is often
            # ignored by the FFMPEG backend on macOS; the env var is authoritative.
            stimeout_us = self.cfg.rtsp_read_timeout_ms * 1000
            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
                f"rtsp_transport;tcp|stimeout;{stimeout_us}"
            )
            self.log(f"[CAM] Connecting RTSP: {self.cfg.rtsp} "
                     f"(timeout {self.cfg.rtsp_read_timeout_ms/1000:.0f}s)")
            cap = cv2.VideoCapture(self.cfg.rtsp, cv2.CAP_FFMPEG)
            if not cap.isOpened():
                cap.release()
                raise RuntimeError("Could not open RTSP stream")
            self.log("[CAM] Active: RTSP")
            return cap
        self.log(f"[CAM] Opening USB camera {self.cfg.usb}")
        cap = cv2.VideoCapture(int(self.cfg.usb))
        if not cap.isOpened():
            cap.release()
            raise RuntimeError(f"Could not open USB camera {self.cfg.usb}")
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.cfg.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.cfg.height)
        cap.set(cv2.CAP_PROP_FPS, self.cfg.fps)
        for _ in range(5):
            cap.read()
            time.sleep(0.03)
        self.log(f"[CAM] Active: USB {self.cfg.usb} {int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))}")
        return cap

    def _save_detection(self, plain_bgr: Optional[np.ndarray], annotated_bgr: np.ndarray, labels: Iterable[str], reason: str):
        if not (self.cfg.save_detections or self.cfg.save_every_detection) or plain_bgr is None:
            return
        save_dir = os.path.expanduser(self.cfg.save_dir)
        os.makedirs(save_dir, exist_ok=True)
        label = "_".join(sorted(labels)) or "unknown"
        ts = file_ts()
        plain_path = os.path.join(save_dir, f"{ts}_{reason}_{label}_plain.jpg")
        ann_path = os.path.join(save_dir, f"{ts}_{reason}_{label}_annotated.jpg")
        cv2.imwrite(plain_path, plain_bgr)
        cv2.imwrite(ann_path, annotated_bgr)
        self.log(f"[SAVE] {os.path.basename(plain_path)} + {os.path.basename(ann_path)}")

    def _roi_accepts(self, x1: int, y1: int, x2: int, y2: int) -> bool:
        with self._roi_lock:
            enabled = self._roi_enabled
            rects = list(self._roi_rects)
        if not enabled or not rects:
            return True
        cx = (x1 + x2) / 2.0
        cy = (y1 + y2) / 2.0
        for rx, ry, rw, rh in rects:
            if rx <= cx <= rx + rw and ry <= cy <= ry + rh:
                return True
        return False

    def _overlay_style(self, frame: np.ndarray, base_scale: float = 1.0,
                       min_scale: float = 0.35, max_scale: float = 1.25) -> Tuple[float, int]:
        """Return OpenCV text scale/thickness based on the source image size.

        This keeps overlays readable on 1080p ch0 while avoiding huge labels on
        smaller substreams such as 640x360 ch1. The GUI may then scale the image
        up/down, but the overlay proportions stay tied to the actual video frame.
        """
        h, w = frame.shape[:2]
        ref = min(w / 1280.0, h / 720.0)
        scale = max(min_scale, min(max_scale, ref * base_scale))
        thickness = max(1, int(round(scale * 2.0)))
        return scale, thickness

    def _draw_text(self, frame: np.ndarray, text: str, pos: Tuple[int, int],
                   color: Tuple[int, int, int] = (255, 255, 255),
                   base_scale: float = 0.7, min_scale: float = 0.32,
                   max_scale: float = 1.0, thickness: Optional[int] = None):
        scale, auto_thick = self._overlay_style(frame, base_scale, min_scale, max_scale)
        thick = auto_thick if thickness is None else thickness
        x, y = pos
        cv2.putText(frame, text, (int(x), int(y)), cv2.FONT_HERSHEY_SIMPLEX,
                    scale, color, thick, cv2.LINE_AA)

    def _draw_status(self, frame: np.ndarray, status: str, color: Tuple[int, int, int]):
        """Draw state label at lower-left above the model indicator.

        The fill is 50% alpha so it does not obscure the image.
        """
        h, w = frame.shape[:2]
        scale, thick = self._overlay_style(frame, 0.85, 0.34, 1.05)
        while scale > 0.30:
            (tw, th), baseline = cv2.getTextSize(status, cv2.FONT_HERSHEY_SIMPLEX, scale, thick)
            if tw <= int(w * 0.55):
                break
            scale *= 0.9
            thick = max(1, int(round(scale * 2.0)))
        pad_x = max(5, int(10 * scale))
        pad_y = max(4, int(7 * scale))
        box_w = tw + pad_x * 2
        box_h = th + baseline + pad_y * 2
        x0 = max(4, int(8 * scale))
        model_reserved = max(26, int(42 * scale))
        y0 = max(4, h - model_reserved - box_h)
        x1 = min(w - 1, x0 + box_w)
        y1 = min(h - 1, y0 + box_h)
        # Draw filled rectangle directly — avoids full-frame copy for alpha blend
        sub = frame[y0:y1, x0:x1]
        if sub.size > 0:
            # Fast 50% blend on just the badge region, not the whole frame
            badge = np.full_like(sub, color[::-1])  # BGR color
            cv2.addWeighted(badge, 0.5, sub, 0.5, 0, sub)
            frame[y0:y1, x0:x1] = sub
        cv2.putText(frame, status, (x0 + pad_x, y0 + pad_y + th),
                    cv2.FONT_HERSHEY_SIMPLEX, scale, (255, 255, 255), thick, cv2.LINE_AA)

    def _enter_confirming(self, labels: Iterable[str]):
        self.cannon_state = "CONFIRMING"
        self.confirm_count = 1
        self.confirm_labels = set(labels)
        self._session_pest_count += 1
        self.statsUpdated.emit(self._session_pest_count, self._session_fire_count)
        self.log(f"[CANNON] Confirming: {sorted(self.confirm_labels)}")

    def _enter_firing(self, now: float, labels: Iterable[str], plain_bgr: np.ndarray, annotated_bgr: np.ndarray):
        labels_set = set(labels)
        self.cannon_state = "FIRING"
        self.cannon_state_time = now
        self.confirm_count = 0
        self.confirm_labels = set(labels_set)
        # MQTT ON first — publish is non-blocking, relay turns on immediately.
        if self.mqtt:
            self.mqtt.trigger_for(labels_set, self.cfg.cannon_fire)
        # Alert sound — platform-specific and non-blocking.
        if self.cfg.alert_sound:
            _t = time.time()
            if _t - self._last_alert_sound_time >= self.cfg.alert_sound_holdoff:
                self._last_alert_sound_time = _t
                play_alert_sound(self.log)
        self._session_fire_count += 1
        self.statsUpdated.emit(self._session_pest_count, self._session_fire_count)
        self.log(f"[CANNON] TRIGGER — {sorted(labels_set)} | fire {self.cfg.cannon_fire}s | holdoff {self.cfg.cannon_holdoff}s")
        # Save images in a daemon thread — cv2.imwrite can take 50-200ms
        # and must not delay the MQTT publish or the frame loop.
        if plain_bgr is not None:
            _p, _a, _l = plain_bgr.copy(), annotated_bgr.copy(), set(labels_set)
            threading.Thread(
                target=self._save_detection,
                args=(_p, _a, _l, "confirmed"),
                daemon=True
            ).start()

    def _enter_holdoff(self, now: float):
        self.cannon_state = "HOLDOFF"
        self.cannon_state_time = now
        self.log(f"[CANNON] HOLDOFF {self.cfg.cannon_holdoff}s")

    def _enter_idle(self, now: float):
        self.cannon_state = "IDLE"
        self.cannon_state_time = now
        self.confirm_count = 0
        self.confirm_labels = set()
        self.log("[CANNON] IDLE — ready")

    def _run_inference_pass(self, rgb: np.ndarray, safe_classes: Set[str]) -> Set[str]:
        all_detections: List[Tuple[str, float, int, int, int, int]] = []
        roi_detections: List[Tuple[str, float, int, int, int, int]] = []
        if self.detector is not None:
            dets = self.detector.infer(rgb)
            if self.cfg.debug_camera:
                self.log(f"[DET] {len(dets)} Hailo box(es) at conf>={self.cfg.conf}")
            for label, conf, x1, y1, x2, y2 in dets:
                label_str = str(label)
                all_detections.append((label_str, conf, x1, y1, x2, y2))
                if self._roi_accepts(x1, y1, x2, y2):
                    roi_detections.append((label_str, conf, x1, y1, x2, y2))
        else:
            # stream=True makes ultralytics yield one Results object at a
            # time rather than building a list — avoids accumulating tensor
            # references that the MPS allocator cannot reclaim mid-loop.
            with torch.no_grad():
                result_gen = self.model.predict(
                    rgb,
                    imgsz=self.cfg.imgsz,
                    conf=self.cfg.conf,
                    iou=self.cfg.iou,
                    device=self.device,
                    stream=True,
                    verbose=False,
                )
                result = next(iter(result_gen))
            boxes = result.boxes
            if self.cfg.debug_camera:
                n_boxes = len(boxes) if boxes is not None else 0
                self.log(f"[DET] {n_boxes} box(es) at conf>={self.cfg.conf}")
            if boxes is not None:
                for box in boxes:
                    class_id = int(box.cls)
                    conf = float(box.conf)
                    label = self.model.names.get(class_id) if hasattr(self.model, "names") else None
                    label = label or (self.class_names[class_id] if class_id < len(self.class_names) else str(class_id))
                    x1, y1, x2, y2 = box.xyxy.int()[0].tolist()
                    label_str = str(label)
                    all_detections.append((label_str, conf, x1, y1, x2, y2))
                    if self._roi_accepts(x1, y1, x2, y2):
                        roi_detections.append((label_str, conf, x1, y1, x2, y2))
            # Explicitly release the result and flush the MPS page cache.
            del result, boxes
            if self.device == "mps":
                torch.mps.empty_cache()

        self.last_detections = roi_detections
        safe_this_frame: Set[str] = set()
        for label, _, _, _, _, _ in all_detections:
            label_lower = label.lower()
            if label_lower in safe_classes:
                safe_this_frame.add(label_lower)
        return safe_this_frame

    def _advance_cannon_state(
        self,
        now: float,
        pest_this_frame: Set[str],
        safe_this_frame: Set[str],
        manual_active: bool,
        plain: Optional[np.ndarray],
        draw: np.ndarray,
    ) -> None:
        if manual_active:
            return
        # Safe class anywhere in the frame suppresses automatic triggering.
        if safe_this_frame:
            if self.cannon_state == "CONFIRMING":
                self.log(f"[CANNON] Safe class detected ({sorted(safe_this_frame)}) — resetting")
                self._enter_idle(now)
            return
        if self.cannon_state == "IDLE" and pest_this_frame:
            self._enter_confirming(pest_this_frame)
        elif self.cannon_state == "CONFIRMING":
            if pest_this_frame:
                self.confirm_count += 1
                self.confirm_labels |= pest_this_frame
                if self.confirm_count >= self.cfg.confirm_frames:
                    self.log(f"[CANNON] Confirmed {self.confirm_count} frames: {sorted(self.confirm_labels)}")
                    self._enter_firing(now, self.confirm_labels, plain, draw)
            else:
                self.log(f"[CANNON] False positive ({self.confirm_count}/{self.cfg.confirm_frames})")
                self._enter_idle(now)

    # ── Manual cannon control ─────────────────────────────────────────
    def manual_oneshot(self):
        """Fire once for the configured fire duration, block auto-detections.
        Runs in a daemon thread — publishes ON/OFF directly without using
        trigger_for to avoid double-timer races.
        """
        with self._manual_lock:
            self._manual_mode = "ONESHOT"
        self.manualStateChanged.emit("ONESHOT")
        fire_secs = self.cfg.cannon_fire

        def _run_oneshot():
            self.log(f"[MANUAL] ONE-SHOT — firing cannon for {fire_secs:.1f}s")
            if self.mqtt:
                self.mqtt.output_on(["manual"])
            # Sleep the exact fire duration
            time.sleep(fire_secs)
            if self.mqtt:
                self.mqtt.output_off(["manual"])
            with self._manual_lock:
                if self._manual_mode == "ONESHOT":
                    self._manual_mode = "IDLE"
            self.manualStateChanged.emit("IDLE")
            self.log("[MANUAL] ONE-SHOT complete — auto-detection resumed")

        t = threading.Thread(target=_run_oneshot, daemon=True)
        t.start()

    def manual_on(self, timeout_seconds: float = 900.0):
        """Force cannon ON until manual_off is called (by GUI countdown or button).
        Publishes ON directly — no internal OFF timer. The GUI QTimer countdown
        is the sole mechanism that calls manual_off().
        """
        with self._manual_lock:
            self._manual_mode = "MANUAL_ON"
        self.manualStateChanged.emit("MANUAL_ON")
        self.log(f"[MANUAL] CANNON ON — auto-off in {timeout_seconds/60:.0f} min")
        if self.mqtt:
            self.mqtt.output_on(["manual"])

    def manual_off(self):
        """Release manual hold, send MQTT OFF, resume auto-detection."""
        with self._manual_lock:
            prev = self._manual_mode
            self._manual_mode = "IDLE"
        self.manualStateChanged.emit("IDLE")
        self.log("[MANUAL] CANNON OFF — auto-detection resumed")
        if self.mqtt and prev in ("MANUAL_ON", "ONESHOT"):
            # Cancel any pending trigger_for OFF timer (shouldn't exist, but safety)
            self.mqtt._cancel_off_timer()
            self.mqtt.off({"manual"})

    def run(self):
        cap = None
        try:
            self._load_device()
            self._load_model()
            self.mqtt = MqttTrigger(self.cfg, self.log)
            pest_classes = parse_classes(self.cfg.pest_classes)
            safe_classes = parse_classes(self.cfg.safe_classes)
            rtsp_capture = None
            if self.cfg.source == "rtsp":
                if getattr(self.cfg, "rtsp_backend", "opencv") == "vlc":
                    rtsp_capture = VlcRTSPCapture(self.cfg, self.log)
                else:
                    rtsp_capture = ProcessRTSPCapture(self.cfg, self.log)
            else:
                cap = self._open_capture()
            last_ok = time.time()
            frame_count = 0
            fps_count = 0
            fps_last = time.time()
            last_debug = 0.0
            self.statusChanged.emit("Running")

            def _do_reconnect():
                """Reconnect RTSP process capture or reopen USB capture."""
                nonlocal cap, rtsp_capture
                if rtsp_capture is not None:
                    try:
                        rtsp_capture.close()
                    except Exception:
                        pass
                    end_wait = time.time() + self.cfg.rtsp_reconnect_delay
                    while self._running.is_set() and time.time() < end_wait:
                        time.sleep(0.1)
                    if not self._running.is_set():
                        return False
                    try:
                        if getattr(self.cfg, "rtsp_backend", "opencv") == "vlc":
                            rtsp_capture = VlcRTSPCapture(self.cfg, self.log)
                        else:
                            rtsp_capture = ProcessRTSPCapture(self.cfg, self.log)
                        return True
                    except Exception as e:
                        self.log(f"[CAM] Reconnect failed: {e}")
                        return False

                try:
                    if cap is not None:
                        cap.release()
                except Exception:
                    pass
                cap = None
                try:
                    cap = self._open_capture()
                    return True
                except Exception as e:
                    self.log(f"[CAM] Reconnect failed: {e}")
                    return False

            while self._running.is_set():
                now = time.time()
                if self.cannon_state == "FIRING" and now - self.cannon_state_time >= self.cfg.cannon_fire:
                    self._enter_holdoff(now)
                elif self.cannon_state == "HOLDOFF" and now - self.cannon_state_time >= self.cfg.cannon_holdoff:
                    self._enter_idle(now)

                if rtsp_capture is not None:
                    ret, frame = rtsp_capture.read()
                    if not ret or frame is None:
                        if rtsp_capture.age() > self.cfg.rtsp_stale_seconds:
                            self.log(f"[CAM] RTSP stale > {self.cfg.rtsp_stale_seconds:.1f}s — reconnecting after {self.cfg.rtsp_reconnect_delay:.0f}s")
                            if not _do_reconnect():
                                break
                            last_ok = time.time()
                            continue
                        time.sleep(0.02)
                        continue
                else:
                    ret, frame = cap.read() if cap is not None else (False, None)
                    if not ret or frame is None:
                        time.sleep(0.03)
                        continue
                last_ok = time.time()
                if self.cfg.debug_camera and now - last_debug >= 5:
                    self.log(f"[CAMDBG] shape={frame.shape} dtype={frame.dtype} min={frame.min()} max={frame.max()} mean={frame.mean():.2f}")
                    last_debug = now
                if self.cfg.flip:
                    frame = cv2.flip(frame, -1)
                # Keep a plain copy when any save mode is enabled.
                plain = frame.copy() if (self.cfg.save_detections or self.cfg.save_every_detection) else None
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                if self.cfg.night_vision:
                    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
                    draw = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
                else:
                    draw = plain.copy() if plain is not None else frame.copy()
                frame_count += 1
                run_inference = (frame_count % max(1, self.cfg.skip_frames) == 0)
                safe_this_frame: Set[str] = set()
                pest_this_frame: Set[str] = set()
                if run_inference:
                    fps_count += 1
                    safe_this_frame = self._run_inference_pass(rgb, safe_classes)
                    if time.time() - fps_last >= FPS_REPORT_INTERVAL_SECONDS:
                        elapsed_fps = time.time() - fps_last
                        self.fpsUpdated.emit(fps_count / max(0.001, elapsed_fps))
                        fps_count = 0
                        fps_last = time.time()
                for label, conf, x1, y1, x2, y2 in self.last_detections:
                    label_lower = label.lower()
                    is_pest = label_lower in pest_classes
                    is_safe = label_lower in safe_classes
                    if not self.cfg.draw_all and not (is_pest or is_safe):
                        continue
                    if is_pest:
                        pest_this_frame.add(label_lower)
                        color = (0, 0, 255)
                    elif is_safe:
                        safe_this_frame.add(label_lower)
                        color = (0, 255, 0)
                    else:
                        color = (0, 165, 255)
                    cv2.rectangle(draw, (x1, y1), (x2, y2), color, max(1, int(round(min(draw.shape[:2]) / 360))))
                    label_y = max(16, y1 - 5)
                    self._draw_text(draw, f"{label} {conf * 100:.0f}%", (max(0, x1), label_y),
                                    color=color, base_scale=0.62, min_scale=0.30, max_scale=0.85)
                if self.cfg.save_every_detection and run_inference and pest_this_frame:
                    self._save_detection(plain, draw, pest_this_frame, "pest")
                # ── Stats and auto-detection cannon logic ─────────────────────
                with self._manual_lock:
                    _manual_active = self._manual_mode != "IDLE"
                if run_inference:
                    self._advance_cannon_state(
                        now=now,
                        pest_this_frame=pest_this_frame,
                        safe_this_frame=safe_this_frame,
                        manual_active=_manual_active,
                        plain=plain,
                        draw=draw,
                    )
                elapsed = time.time() - self.cannon_state_time
                if self.cannon_state == "CONFIRMING":
                    status, color = f"CONFIRMING {self.confirm_count}/{self.cfg.confirm_frames}", (0, 200, 200)
                elif self.cannon_state == "FIRING":
                    status, color = f"TRIGGER {max(0, self.cfg.cannon_fire - elapsed):.1f}s", (0, 0, 220)
                elif self.cannon_state == "HOLDOFF":
                    status, color = f"HOLDOFF {max(0, self.cfg.cannon_holdoff - elapsed):.0f}s", (0, 140, 255)
                else:
                    status, color = "READY", (0, 180, 0)
                self._draw_status(draw, status, color)
                if pest_this_frame or self.cannon_state == "CONFIRMING":
                    labels_show = pest_this_frame or self.confirm_labels
                    ref = min(draw.shape[1] / 1280.0, draw.shape[0] / 720.0)
                    self._draw_text(draw, f"PEST: {', '.join(sorted(labels_show))}",
                                    (max(8, int(18 * ref)), max(42, int(84 * ref))),
                                    color=(0, 0, 255), base_scale=0.72, min_scale=0.32, max_scale=0.95)
                indicator = f"{self.detector.name if self.detector is not None else os.path.basename(self.cfg.model)} | {self.device.upper()}"
                self._draw_text(draw, indicator, (10, max(18, draw.shape[0] - 14)),
                                color=(220, 220, 220), base_scale=0.62, min_scale=0.30, max_scale=0.85)
                self.frameReady.emit(draw)
        except Exception as e:
            self.log(f"[ERROR] {e}")
            self.statusChanged.emit("Error")
        finally:
            try:
                if 'rtsp_capture' in locals() and rtsp_capture is not None:
                    rtsp_capture.close()
            except Exception as e:
                self.log(f"[CAM] RTSP process close error: {e}")
            try:
                if cap is not None:
                    cap.release()
            except Exception:
                pass
            try:
                if self.detector is not None:
                    self.detector.close()
            except Exception:
                pass
            try:
                if self.mqtt is not None:
                    self.mqtt.close()
            except Exception:
                pass
            self.statusChanged.emit("Stopped")
            self.stopped.emit()

class VideoView(QFrame):
    roiChanged = Signal(object)
    def __init__(self):
        super().__init__()
        self.setMinimumSize(640, 360)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)
        self.qimage: Optional[QImage] = None
        self.frame_w = 0
        self.frame_h = 0
        self.zoom = 1.0
        self.pan = QPointF(0.0, 0.0)
        self.roi_enabled = False
        self.roi_rect: Optional[Tuple[int, int, int, int]] = None
        self.roi_rects: List[Tuple[int, int, int, int]] = []
        self._dragging_roi = False
        self._panning = False
        self._drag_start_img: Optional[Tuple[int, int]] = None
        self._last_mouse = QPointF(0.0, 0.0)
        self.setStyleSheet("VideoView { background: #0b0f14; border: 1px solid #243040; border-radius: 14px; }")

    def set_frame(self, frame_bgr: np.ndarray):
        new_h, new_w = frame_bgr.shape[:2]
        # If the stream changes resolution, reset the viewport so the next frame
        # starts in the top-left and is not left panned/zoomed from an old stream.
        if (new_w, new_h) != (self.frame_w, self.frame_h):
            self.zoom = 1.0
            self.pan = QPointF(0.0, 0.0)
        self.frame_h, self.frame_w = new_h, new_w
        self.qimage = bgr_to_qimage(frame_bgr)
        self.update()

    def set_roi_enabled(self, enabled: bool):
        self.roi_enabled = enabled
        self.update()
        self.roiChanged.emit(list(self.roi_rects) if enabled else None)

    def reset_view(self):
        self.zoom = 1.0
        self.pan = QPointF(0.0, 0.0)
        self.update()

    def clear_roi(self):
        self.roi_rect = None
        self.roi_rects = []
        self.update()
        self.roiChanged.emit([] if self.roi_enabled else None)

    def _transform(self):
        if not self.qimage or self.frame_w <= 0 or self.frame_h <= 0:
            return 1.0, 0.0, 0.0
        # Fit the whole image inside the preview, anchored at the top-left.
        # This makes RTSP substreams start from the expected image origin.
        base = min(self.width() / self.frame_w, self.height() / self.frame_h)
        scale = base * self.zoom
        xoff = self.pan.x()
        yoff = self.pan.y()
        return scale, xoff, yoff

    def _widget_to_img(self, pos) -> Optional[Tuple[int, int]]:
        if not self.qimage:
            return None
        scale, xoff, yoff = self._transform()
        x = int((pos.x() - xoff) / scale)
        y = int((pos.y() - yoff) / scale)
        if x < 0 or y < 0 or x >= self.frame_w or y >= self.frame_h:
            return None
        return (x, y)

    def _img_rect_to_widget(self, rect: Tuple[int, int, int, int]) -> QRectF:
        scale, xoff, yoff = self._transform()
        x, y, w, h = rect
        return QRectF(xoff + x * scale, yoff + y * scale, w * scale, h * scale)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.fillRect(self.rect(), QColor("#0b0f14"))
        if self.qimage:
            scale, xoff, yoff = self._transform()
            target = QRectF(xoff, yoff, self.frame_w * scale, self.frame_h * scale)
            painter.drawImage(target, self.qimage)
        else:
            painter.setPen(QColor("#8ea0b8"))
            painter.setFont(QFont("Helvetica Neue", 18))
            painter.drawText(self.rect(), Qt.AlignCenter, "Camera preview will appear here")
        if self.roi_enabled:
            painter.setPen(QPen(QColor("white"), 1.0))
            painter.setBrush(Qt.NoBrush)
            rects_to_draw = list(self.roi_rects)
            if self._dragging_roi and self.roi_rect is not None:
                rects_to_draw.append(self.roi_rect)
            if rects_to_draw:
                painter.setFont(QFont("Helvetica Neue", 11))
                for idx, rect in enumerate(rects_to_draw, start=1):
                    rr = self._img_rect_to_widget(rect)
                    painter.drawRect(rr)
                    painter.drawText(rr.topLeft() + QPointF(6, -6), f"ROI {idx}")
            else:
                painter.setFont(QFont("Helvetica Neue", 11))
                painter.setPen(QColor("#e8eef7"))
                painter.drawText(16, 26, "ROI enabled — drag on image to add detection regions")
        painter.end()

    def wheelEvent(self, event: QWheelEvent):
        if not self.qimage:
            return
        # Zoom around the mouse position so the point under the cursor stays
        # roughly stationary while zooming.
        old_scale, old_xoff, old_yoff = self._transform()
        pos = event.position()
        img_x = (pos.x() - old_xoff) / old_scale
        img_y = (pos.y() - old_yoff) / old_scale
        self.zoom = min(8.0, self.zoom * 1.15) if event.angleDelta().y() > 0 else max(0.2, self.zoom / 1.15)
        new_scale, _, _ = self._transform()
        self.pan = QPointF(pos.x() - img_x * new_scale, pos.y() - img_y * new_scale)
        self.update()

    def mousePressEvent(self, event: QMouseEvent):
        self._last_mouse = QPointF(event.position())
        if event.button() == Qt.LeftButton and self.roi_enabled:
            img = self._widget_to_img(event.position())
            if img is not None:
                self._dragging_roi = True
                self._drag_start_img = img
                self.roi_rect = (img[0], img[1], 1, 1)
                self.update()
                return
        if event.button() in (Qt.MiddleButton, Qt.RightButton) or (event.button() == Qt.LeftButton and not self.roi_enabled):
            self._panning = True

    def mouseMoveEvent(self, event: QMouseEvent):
        pos = QPointF(event.position())
        if self._dragging_roi and self._drag_start_img is not None:
            img = self._widget_to_img(event.position())
            if img is not None:
                x0, y0 = self._drag_start_img
                x1, y1 = img
                self.roi_rect = clamp_roi(min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0), self.frame_w, self.frame_h)
                self.update()
        elif self._panning:
            self.pan += pos - self._last_mouse
            self.update()
        self._last_mouse = pos

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self._dragging_roi:
            self._dragging_roi = False
            if self.roi_rect is not None:
                self.roi_rects.append(self.roi_rect)
            self.roiChanged.emit(list(self.roi_rects))
        if self._panning:
            self._panning = False


class StepSpinner(QWidget):
    """A QSpinBox/QDoubleSpinBox wrapped with visible − / + buttons.

    Exposes the same interface used in the rest of the app:
      .value(), .setValue(), .setRange(), .setSingleStep(),
      .setSuffix(), .setEnabled(), .setToolTip()
    valueChanged signal forwarded from the inner spinbox.
    """
    def __init__(self, is_double=False, parent=None):
        super().__init__(parent)
        self._spin = QDoubleSpinBox() if is_double else QSpinBox()
        self._spin.setButtonSymbols(QDoubleSpinBox.NoButtons if is_double else QSpinBox.NoButtons)
        self._spin.setStyleSheet("")  # inherit app style
        minus = QPushButton("−")
        plus  = QPushButton("+")
        for btn in (minus, plus):
            btn.setFixedSize(28, 28)
            btn.setStyleSheet(
                "QPushButton { background:#1e3148; border:1px solid #34465c; "
                "border-radius:6px; color:#7aaee0; font-size:16px; font-weight:bold; padding:0; }"
                "QPushButton:hover { background:#2a5090; color:#b8d8f8; }"
                "QPushButton:pressed { background:#2266aa; }"
                "QPushButton:disabled { background:#1a2535; color:#3a4654; }"
            )
        minus.clicked.connect(lambda: self._spin.setValue(
            self._spin.value() - self._spin.singleStep()))
        plus.clicked.connect(lambda: self._spin.setValue(
            self._spin.value() + self._spin.singleStep()))
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(3)
        row.addWidget(minus)
        row.addWidget(self._spin, 1)
        row.addWidget(plus)
        self._minus = minus
        self._plus  = plus
        # forward the signal
        self.valueChanged = self._spin.valueChanged

    def value(self):           return self._spin.value()
    def setValue(self, v):     self._spin.setValue(v)
    def setRange(self, a, b):  self._spin.setRange(a, b)
    def setSingleStep(self, s):self._spin.setSingleStep(s)
    def setSuffix(self, s):    self._spin.setSuffix(s)
    def setToolTip(self, t):
        super().setToolTip(t)
        self._spin.setToolTip(t)
    def setEnabled(self, e):
        super().setEnabled(e)
        self._spin.setEnabled(e)
        self._minus.setEnabled(e)
        self._plus.setEnabled(e)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.platform_info = RUNTIME_PLATFORM
        self.is_raspberry_pi = bool(self.platform_info.get("is_raspberry_pi"))
        self.is_windows = bool(self.platform_info.get("is_windows"))
        self.is_macos = bool(self.platform_info.get("is_macos"))
        self.is_linux = bool(self.platform_info.get("is_linux"))
        self.setWindowTitle("The AI Pest Cannon")
        self.resize(1600, 880)
        self.worker: Optional[DetectionWorker] = None
        self._last_cfg: Optional[AppConfig] = None
        self._intentional_stop = False
        self._closing = False
        self._restart_attempts = 0
        self._max_restart_attempts = 999
        self._restart_delay_ms = 5000
        self.video = VideoView()
        self._fs_window = None
        self._left_layout = None  # set in _build_ui
        self._manual_countdown_secs = 0
        self._manual_countdown_timer = QTimer(self)
        self._manual_countdown_timer.setInterval(1000)  # tick every second
        self._manual_countdown_timer.timeout.connect(self._manual_countdown_tick)
        self._settings_path = default_settings_path()
        self.log_box = QTextEdit(); self.log_box.setReadOnly(True); self.log_box.setMaximumHeight(120)
        self._build_ui()
        self._apply_style()
        self._load_settings()
        # Ensure buttons are in the correct initial (stopped) state after the UI
        # is fully constructed and the stylesheet has been applied.
        self._set_controls_running(False)

    def _apply_style(self):
        self.setStyleSheet("""
            QMainWindow, QWidget { background: #101820; color: #e8edf5; font-family: "Helvetica Neue", Arial; }
            QGroupBox { border: 1px solid #2a3a4e; border-radius: 12px; margin-top: 10px; padding: 10px; font-weight: 600; }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; color: #b7c7d9; }
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit { background: #172230; border: 1px solid #34465c; border-radius: 8px; padding: 5px; color: #f3f7fb; }
            QPushButton { background: #2266aa; border: 0; border-radius: 10px; padding: 8px 12px; color: white; font-weight: 600; }
            QPushButton:hover { background: #2f7fcf; }
            QPushButton:disabled { background: #3a4654; color: #9aa8b6; }
            QTabWidget::pane { border: 1px solid #2a3a4e; border-radius: 12px; }
            QTabBar::tab { background: #172230; padding: 9px 12px; border-radius: 8px; margin: 2px; }
            QTabBar::tab:selected { background: #2266aa; }
        """)

    def _form_group(self, title: str):
        group = QGroupBox(title)
        form = QFormLayout(group)
        form.setLabelAlignment(Qt.AlignRight)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(5)
        form.setContentsMargins(10, 6, 10, 8)
        return group, form

    def _make_spinner(self, lo, hi, val, step=1, suffix="", tip="", is_double=False):
        w = StepSpinner(is_double=is_double)
        w.setRange(lo, hi)
        w.setSingleStep(step)
        w.setValue(val)
        if suffix: w.setSuffix(suffix)
        if tip:    w.setToolTip(tip)
        return w

    def _make_wide_line_edit(self, text: str = "", min_width: int = 430) -> QLineEdit:
        edit = QLineEdit(text)
        edit.setMinimumWidth(min_width)
        edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        edit.setCursorPosition(0)
        edit.setToolTip(text)
        edit.textChanged.connect(lambda t, e=edit: e.setToolTip(t))
        return edit

    def _build_ui(self):
        central = QWidget(); root = QHBoxLayout(central); root.setContentsMargins(10,10,10,10); root.setSpacing(10)
        left = QVBoxLayout(); left.setSpacing(6); left.addWidget(self.video, 1)
        self._left_layout = left
        transport = QHBoxLayout(); transport.setSpacing(6)
        self.start_btn = QPushButton("Start capture"); self.stop_btn = QPushButton("Stop")
        self.fullscreen_btn = QPushButton("Fullscreen")
        self.reset_view_btn = QPushButton("Reset zoom/pan"); self.clear_roi_btn = QPushButton("Clear ROI")
        transport.addWidget(self.start_btn); transport.addWidget(self.stop_btn); transport.addStretch()
        transport.addWidget(self.fullscreen_btn); transport.addWidget(self.reset_view_btn); transport.addWidget(self.clear_roi_btn)
        left.addLayout(transport)
        # ── Stats bar (FPS · pest count · safe count) above the log ──────
        stats_row = QHBoxLayout(); stats_row.setContentsMargins(0, 2, 0, 0)
        stats_row.addWidget(QLabel("Log"))
        stats_row.addStretch()
        self.fps_label   = QLabel("FPS: —")
        self.pest_count_label = QLabel("Pests: 0")
        self.fire_count_label = QLabel("Fired: 0")
        for lbl in (self.fps_label, self.pest_count_label, self.fire_count_label):
            lbl.setStyleSheet("color: #8ab4d4; font-size: 11px;")
            stats_row.addWidget(lbl)
            if lbl is not self.fire_count_label:
                sep = QLabel("|"); sep.setStyleSheet("color: #3a5060; font-size: 11px;")
                stats_row.addWidget(sep)
        left.addLayout(stats_row)
        left.addWidget(self.log_box)
        self.tabs = QTabWidget(); self.tabs.setMinimumWidth(650); self.tabs.setMaximumWidth(820)
        self._build_camera_tab(); self._build_model_tab(); self._build_detection_tab(); self._build_output_tab(); self._build_mqtt_tab()
        # Wrap tabs in a scroll area so the panel is usable on smaller screens
        self._tab_scroll = QScrollArea()
        self._tab_scroll.setWidget(self.tabs)
        self._tab_scroll.setWidgetResizable(True)
        self._tab_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._tab_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._tab_scroll.setMinimumWidth(670)
        self._tab_scroll.setMaximumWidth(840)
        self._tab_scroll.setFrameShape(QFrame.NoFrame)
        root.addLayout(left, 1); root.addWidget(self._tab_scroll); self.setCentralWidget(central)
        self.start_btn.clicked.connect(self.start_capture); self.stop_btn.clicked.connect(self.stop_capture)
        self.reset_view_btn.clicked.connect(self.video.reset_view); self.clear_roi_btn.clicked.connect(self.clear_roi)
        self.fullscreen_btn.clicked.connect(self.toggle_fullscreen)
        self.video.roiChanged.connect(self.on_roi_changed)

    def _build_camera_tab(self):
        tab = QWidget(); layout = QVBoxLayout(tab); layout.setSpacing(6); layout.setContentsMargins(6,6,6,6)
        group, form = self._form_group("Camera")
        self.source_combo = QComboBox(); self.source_combo.addItems(["rtsp", "usb", "csi"] if self.is_raspberry_pi else ["rtsp", "usb"]); self.source_combo.setMinimumWidth(160)
        self.rtsp_backend_combo = QComboBox(); self.rtsp_backend_combo.addItems(["opencv", "vlc"]); self.rtsp_backend_combo.setMinimumWidth(160)
        self.usb_spin = self._make_spinner(0, 20, 0)
        self.rtsp_edit = self._make_wide_line_edit("rtsp://thingino:thingino@192.168.2.233:554/ch1", 520)
        self.width_spin = self._make_spinner(160, 7680, 1280)
        self.height_spin = self._make_spinner(120, 4320, 720)
        self.fps_spin = self._make_spinner(1, 120, 30)
        self.flip_check = QCheckBox("Rotate 180°"); self.night_check = QCheckBox("Greyscale night vision"); self.debug_cam_check = QCheckBox("Print camera debug")
        for label, widget in [("Source",self.source_combo),("RTSP backend",self.rtsp_backend_combo),("USB index",self.usb_spin),("RTSP URL",self.rtsp_edit),("USB width",self.width_spin),("USB height",self.height_spin),("USB FPS",self.fps_spin),("",self.flip_check),("",self.night_check),("",self.debug_cam_check)]: form.addRow(label, widget)
        layout.addWidget(group)
        group2, form2 = self._form_group("RTSP reliability")
        self.stale_spin = self._make_spinner(1, 120, 8.0, step=0.5, suffix=" s", is_double=True)
        self.reconnect_spin = self._make_spinner(1, 600, 30.0, step=5.0, suffix=" s", is_double=True)
        self.open_timeout_spin = self._make_spinner(1000, 120000, 10000, step=1000, suffix=" ms")
        self.read_timeout_spin = self._make_spinner(1000, 120000, 10000, step=1000, suffix=" ms")
        for label, widget in [("Stale after",self.stale_spin),("Reconnect wait",self.reconnect_spin),("Open timeout",self.open_timeout_spin),("Read timeout",self.read_timeout_spin)]: form2.addRow(label, widget)
        layout.addWidget(group2); layout.addStretch(); self.tabs.addTab(tab, "Camera")

    def _build_model_tab(self):
        tab = QWidget(); layout = QVBoxLayout(tab); layout.setSpacing(6); layout.setContentsMargins(6,6,6,6); group, form = self._form_group("Model")
        self.backend_combo = QComboBox(); self.backend_combo.addItems(["auto", "hailo", "cpu"] if self.is_raspberry_pi else ["auto", "cpu"]); self.backend_combo.setCurrentText("auto")
        self.hef_edit = self._make_wide_line_edit("~/hailo_models/yolov11m.hef", 430)
        self.model_combo = QComboBox(); self.model_combo.setEditable(True); self.model_combo.setMinimumWidth(430); self.model_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed); self.model_combo.addItems(MODEL_CHOICES); self.model_combo.setCurrentText("yolo11m.pt")
        self.classes_edit = self._make_wide_line_edit("coco.txt", 430)
        self.conf_spin = self._make_spinner(0.01, 0.99, 0.35, step=0.05, is_double=True)
        self.iou_spin = self._make_spinner(0.1, 0.99, 0.70, step=0.05, is_double=True)
        self.imgsz_spin = self._make_spinner(160, 1920, 1024, step=32)
        self.skip_spin = self._make_spinner(1, 30, 1)
        self.device_combo = QComboBox(); self.device_combo.addItems(["auto", "cuda", "mps", "cpu"])
        for label, widget in [("Backend",self.backend_combo),("Hailo HEF",self.hef_edit),("Model",self.model_combo),("Class file",self.classes_edit),("Confidence",self.conf_spin),("IoU",self.iou_spin),("Image size",self.imgsz_spin),("Skip frames",self.skip_spin),("Device",self.device_combo)]: form.addRow(label, widget)
        layout.addWidget(group); layout.addStretch(); self.tabs.addTab(tab, "Model")

    def _build_detection_tab(self):
        tab = QWidget(); layout = QVBoxLayout(tab); layout.setSpacing(6); layout.setContentsMargins(6,6,6,6); group, form = self._form_group("Detection / ROI")
        self.pest_edit = self._make_wide_line_edit(DEFAULT_PEST_CLASSES, 320); self.safe_edit = self._make_wide_line_edit(DEFAULT_SAFE_CLASSES, 320)
        self.draw_all_check = QCheckBox("Draw all detections"); self.draw_all_check.setChecked(True)
        self.alert_sound_check = QCheckBox("Play sound on detection"); self.alert_sound_check.setChecked(True); self.alert_sound_check.setToolTip("Plays custom.wav from the script folder. If missing, macOS/Windows use a default sound; Linux/Raspberry Pi log a warning and play nothing.")
        self.alert_sound_holdoff_spin = self._make_spinner(1, 300, 5.0, step=0.5, suffix=" s", is_double=True)
        self.roi_enable_check = QCheckBox("Enable ROI"); self.roi_enable_check.setChecked(True); self.roi_label = QLabel("No ROI"); self.roi_label.setStyleSheet("color: #b7c7d9;")
        for label, widget in [("Pest classes",self.pest_edit),("Safe classes",self.safe_edit),("",self.draw_all_check),("",self.alert_sound_check),("Sound holdoff",self.alert_sound_holdoff_spin),("",self.roi_enable_check),("ROI",self.roi_label)]: form.addRow(label, widget)
        layout.addWidget(group)
        group2, form2 = self._form_group("Trigger / Saving")
        self.confirm_spin = self._make_spinner(1, 30, 4)
        self.fire_spin = self._make_spinner(0.1, 120, 5.0, step=0.5, suffix=" s", is_double=True)
        self.holdoff_spin = self._make_spinner(0, 3600, 15.0, step=5.0, suffix=" s", is_double=True)
        self.dry_run_check = QCheckBox("Dry run"); self.dry_run_check.setChecked(False)
        self.save_check = QCheckBox("Save confirmed detections"); self.save_check.setChecked(True); self.save_every_check = QCheckBox("Save every pest frame")
        self.save_dir_edit = self._make_wide_line_edit("~/detections", 430); self.save_browse_btn = QPushButton("Browse…")
        save_row = QHBoxLayout(); save_row.addWidget(self.save_dir_edit); save_row.addWidget(self.save_browse_btn)
        for label, widget in [("Confirm frames",self.confirm_spin),("Fire time",self.fire_spin),("Holdoff",self.holdoff_spin),("",self.dry_run_check),("",self.save_check),("",self.save_every_check),("Save dir",save_row)]: form2.addRow(label, widget)
        layout.addWidget(group2)
        # ── Manual control group ──────────────────────────────────────────
        group3, form3 = self._form_group("Manual Cannon Control")
        self.manual_timeout_spin = self._make_spinner(1, 60, 15, suffix=" min",
            tip="Maximum time Cannon ON will stay active before auto-switching off")
        form3.addRow("Max ON time", self.manual_timeout_spin)
        self.oneshot_btn  = QPushButton("One-shot fire")
        self.manual_on_btn  = QPushButton("Cannon ON")
        self.manual_off_btn = QPushButton("Cannon OFF")
        self.manual_status_label = QLabel("Auto")
        self.manual_status_label.setStyleSheet("color: #4aaa55; font-weight: bold;")
        self.manual_countdown_label = QLabel("")
        self.manual_countdown_label.setStyleSheet("color: #dd3333; font-size: 11px; font-weight: bold;")
        btn_row = QHBoxLayout()
        btn_row.addWidget(self.oneshot_btn)
        btn_row.addWidget(self.manual_on_btn)
        btn_row.addWidget(self.manual_off_btn)
        btn_row.addStretch()
        btn_row.addWidget(self.manual_status_label)
        btn_row.addWidget(self.manual_countdown_label)
        form3.addRow("", btn_row)
        layout.addWidget(group3)
        # ── Log saving group ──────────────────────────────────────────────
        group4, form4 = self._form_group("Log Saving")
        self.log_dir_edit = self._make_wide_line_edit("~/cannon-logs", 340)
        self.log_browse_btn = QPushButton("Browse…")
        self.save_log_btn = QPushButton("Save current log")
        self.save_settings_btn = QPushButton("Save settings")
        log_dir_row = QHBoxLayout()
        log_dir_row.addWidget(self.log_dir_edit)
        log_dir_row.addWidget(self.log_browse_btn)
        form4.addRow("Log dir", log_dir_row)
        form4.addRow("", self.save_log_btn)
        form4.addRow("", self.save_settings_btn)
        layout.addWidget(group4)
        layout.addStretch(); self.tabs.addTab(tab, "Detection")
        self.roi_enable_check.toggled.connect(self.video.set_roi_enabled)
        self.video.set_roi_enabled(self.roi_enable_check.isChecked())
        self.save_browse_btn.clicked.connect(self.browse_save_dir)
        self.log_browse_btn.clicked.connect(self.browse_log_dir)
        self.save_log_btn.clicked.connect(self.save_log)
        self.save_settings_btn.clicked.connect(self.save_settings)
        self.oneshot_btn.clicked.connect(self.manual_oneshot)
        self.manual_on_btn.clicked.connect(self.manual_cannon_on)
        self.manual_off_btn.clicked.connect(self.manual_cannon_off)
        # Initial button states — disabled until capture is running
        self.oneshot_btn.setEnabled(False)
        self.manual_on_btn.setEnabled(False)
        self.manual_off_btn.setEnabled(False)

    def _build_output_tab(self):
        tab = QWidget(); layout = QVBoxLayout(tab); layout.setSpacing(6); layout.setContentsMargins(6,6,6,6)
        group, form = self._form_group("Output / GPIO")
        self.output_mode_combo = QComboBox(); self.output_mode_combo.addItems(["dry", "mqtt", "gpio", "both"] if self.is_raspberry_pi else ["dry", "mqtt"]); self.output_mode_combo.setCurrentText("both" if self.is_raspberry_pi else "mqtt")
        self.force_off_check = QCheckBox("Force OFF during stop/shutdown"); self.force_off_check.setChecked(True)
        self.gpio_enabled_check = QCheckBox("GPIO enabled"); self.gpio_enabled_check.setChecked(self.is_raspberry_pi)
        self.gpio_pin_spin = self._make_spinner(0, 27, 17)
        self.gpio_active_high_check = QCheckBox("Active high"); self.gpio_active_high_check.setChecked(True)
        self.gpio_backend_combo = QComboBox(); self.gpio_backend_combo.addItems(["auto", "gpiozero", "RPi.GPIO"])
        form.addRow("Output mode", self.output_mode_combo)
        form.addRow("Shutdown", self.force_off_check)
        if self.is_raspberry_pi:
            form.addRow("GPIO", self.gpio_enabled_check)
            form.addRow("GPIO BCM pin", self.gpio_pin_spin)
            form.addRow("GPIO polarity", self.gpio_active_high_check)
            form.addRow("GPIO backend", self.gpio_backend_combo)
        else:
            info = QLabel("GPIO controls are available only on Raspberry Pi.")
            info.setStyleSheet("color: #b7c7d9;")
            form.addRow("GPIO", info)
        layout.addWidget(group); layout.addStretch(); self.tabs.addTab(tab, "Output")

    def _build_mqtt_tab(self):
        tab = QWidget(); layout = QVBoxLayout(tab); layout.setSpacing(6); layout.setContentsMargins(6,6,6,6); group, form = self._form_group("MQTT")
        self.mqtt_enable_check = QCheckBox("Enable MQTT connection and ON/OFF trigger")
        self.mqtt_enable_check.setChecked(True)
        self.mqtt_host_edit = self._make_wide_line_edit("192.168.1.120", 430); self.mqtt_port_spin = self._make_spinner(1, 65535, 1883, step=1)
        self.mqtt_user_edit = self._make_wide_line_edit("mqtt-user", 430); self.mqtt_pass_edit = self._make_wide_line_edit("mqttuser", 430); self.mqtt_pass_edit.setEchoMode(QLineEdit.Password)
        self.mqtt_client_edit = self._make_wide_line_edit("", 430); self.mqtt_topic_edit = self._make_wide_line_edit("pest", 430); self.mqtt_payload_edit = self._make_wide_line_edit("ON", 430)
        self.mqtt_off_topic_edit = self._make_wide_line_edit("pest", 430); self.mqtt_off_payload_edit = self._make_wide_line_edit("OFF", 430)
        self.mqtt_qos_spin = self._make_spinner(0, 2, 0); self.mqtt_retain_check = QCheckBox("Retain")
        self.mqtt_keepalive_spin = self._make_spinner(10, 600, 60, step=10)
        self.mqtt_json_check = QCheckBox("Publish JSON payload")
        for label, widget in [("",self.mqtt_enable_check),("Broker",self.mqtt_host_edit),("Port",self.mqtt_port_spin),("User",self.mqtt_user_edit),("Password",self.mqtt_pass_edit),("Client ID",self.mqtt_client_edit),("ON topic",self.mqtt_topic_edit),("ON payload",self.mqtt_payload_edit),("OFF topic",self.mqtt_off_topic_edit),("OFF payload",self.mqtt_off_payload_edit),("QoS",self.mqtt_qos_spin),("",self.mqtt_retain_check),("Keepalive",self.mqtt_keepalive_spin),("",self.mqtt_json_check)]: form.addRow(label, widget)
        layout.addWidget(group)
        # ── Test group ────────────────────────────────────────────────
        group_test, form_test = self._form_group("Test MQTT")
        self.mqtt_test_on_btn = QPushButton("Send ON payload")
        self.mqtt_test_off_btn = QPushButton("Send OFF payload")
        test_row = QHBoxLayout()
        test_row.addWidget(self.mqtt_test_on_btn)
        test_row.addWidget(self.mqtt_test_off_btn)
        test_row.addStretch()
        form_test.addRow("", test_row)
        layout.addWidget(group_test)
        layout.addStretch(); self.tabs.addTab(tab, "MQTT")
        self.mqtt_test_on_btn.clicked.connect(self._mqtt_test_on)
        self.mqtt_test_off_btn.clicked.connect(self._mqtt_test_off)

    def browse_save_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Choose save directory", os.path.expanduser(self.save_dir_edit.text()))
        if d: self.save_dir_edit.setText(d)

    def clear_roi(self):
        self.video.clear_roi(); self.roi_label.setText("No ROI")
        if self.worker is not None:
            self.worker.set_roi(self.roi_enable_check.isChecked(), [])

    def on_roi_changed(self, rects):
        if rects is None:
            self.roi_label.setText("No ROI" if self.roi_enable_check.isChecked() else "ROI disabled")
            rect_list = []
        elif isinstance(rects, tuple):
            rect_list = [rects]
        else:
            rect_list = list(rects)
        if rects is not None:
            if not rect_list:
                self.roi_label.setText("No ROI")
            elif len(rect_list) == 1:
                x, y, w, h = rect_list[0]
                self.roi_label.setText(f"ROI 1: x={x}, y={y}, w={w}, h={h}")
            else:
                self.roi_label.setText(f"{len(rect_list)} ROIs")
        if self.worker is not None:
            self.worker.set_roi(self.roi_enable_check.isChecked(), rect_list)

    def _set_combo_text(self, combo: QComboBox, value: str):
        if value is None:
            return
        idx = combo.findText(str(value))
        if idx >= 0:
            combo.setCurrentIndex(idx)
        else:
            combo.setCurrentText(str(value))

    def _apply_config_to_ui(self, cfg: AppConfig):
        self._set_combo_text(self.source_combo, cfg.source)
        self.usb_spin.setValue(int(cfg.usb))
        self.rtsp_edit.setText(str(cfg.rtsp))
        self._set_combo_text(self.rtsp_backend_combo, cfg.rtsp_backend)
        self.width_spin.setValue(int(cfg.width))
        self.height_spin.setValue(int(cfg.height))
        self.fps_spin.setValue(int(cfg.fps))
        self.flip_check.setChecked(bool(cfg.flip))
        self.night_check.setChecked(bool(cfg.night_vision))
        self.debug_cam_check.setChecked(bool(cfg.debug_camera))
        self.stale_spin.setValue(float(cfg.rtsp_stale_seconds))
        self.reconnect_spin.setValue(float(cfg.rtsp_reconnect_delay))
        self.open_timeout_spin.setValue(int(cfg.rtsp_open_timeout_ms))
        self.read_timeout_spin.setValue(int(cfg.rtsp_read_timeout_ms))

        self._set_combo_text(self.backend_combo, cfg.backend)
        self.hef_edit.setText(str(cfg.hef_model))
        self._set_combo_text(self.model_combo, cfg.model)
        self.classes_edit.setText(str(cfg.classes))
        self.conf_spin.setValue(float(cfg.conf))
        self.iou_spin.setValue(float(cfg.iou))
        self.imgsz_spin.setValue(int(cfg.imgsz))
        self.skip_spin.setValue(int(cfg.skip_frames))
        self._set_combo_text(self.device_combo, cfg.device)

        self.pest_edit.setText(str(cfg.pest_classes))
        self.safe_edit.setText(str(cfg.safe_classes))
        self.draw_all_check.setChecked(bool(cfg.draw_all))
        self.alert_sound_check.setChecked(bool(cfg.alert_sound))
        self.alert_sound_holdoff_spin.setValue(float(cfg.alert_sound_holdoff))
        self.roi_enable_check.setChecked(bool(cfg.roi_enabled))
        self.video.roi_rect = None
        self.video.roi_rects = _normalize_roi_rects(cfg.roi_rects)
        self.video.set_roi_enabled(self.roi_enable_check.isChecked())
        self.on_roi_changed(list(self.video.roi_rects) if self.video.roi_enabled else None)

        self.confirm_spin.setValue(int(cfg.confirm_frames))
        self.fire_spin.setValue(float(cfg.cannon_fire))
        self.holdoff_spin.setValue(float(cfg.cannon_holdoff))
        self.dry_run_check.setChecked(bool(cfg.dry_run))
        self.save_check.setChecked(bool(cfg.save_detections))
        self.save_dir_edit.setText(str(cfg.save_dir))
        self.save_every_check.setChecked(bool(cfg.save_every_detection))
        self.log_dir_edit.setText(str(cfg.log_save_dir))

        self._set_combo_text(self.output_mode_combo, cfg.output_mode)
        self.force_off_check.setChecked(bool(cfg.force_off_on_shutdown))
        self.gpio_enabled_check.setChecked(bool(cfg.gpio_enabled))
        self.gpio_pin_spin.setValue(int(cfg.gpio_pin))
        self.gpio_active_high_check.setChecked(bool(cfg.gpio_active_high))
        self._set_combo_text(self.gpio_backend_combo, cfg.gpio_backend)

        self.mqtt_enable_check.setChecked(bool(cfg.mqtt_enabled))
        self.mqtt_host_edit.setText(str(cfg.mqtt_host))
        self.mqtt_port_spin.setValue(int(cfg.mqtt_port))
        self.mqtt_user_edit.setText(str(cfg.mqtt_user))
        self.mqtt_pass_edit.setText(str(cfg.mqtt_pass))
        self.mqtt_client_edit.setText(str(cfg.mqtt_client_id))
        self.mqtt_topic_edit.setText(str(cfg.mqtt_topic))
        self.mqtt_payload_edit.setText(str(cfg.mqtt_payload))
        self.mqtt_off_topic_edit.setText(str(cfg.mqtt_off_topic))
        self.mqtt_off_payload_edit.setText(str(cfg.mqtt_off_payload))
        self.mqtt_qos_spin.setValue(int(cfg.mqtt_qos))
        self.mqtt_retain_check.setChecked(bool(cfg.mqtt_retain))
        self.mqtt_keepalive_spin.setValue(int(cfg.mqtt_keepalive))
        self.mqtt_json_check.setChecked(bool(cfg.mqtt_json))

    def _save_settings_to_disk(self, cfg: AppConfig, log_success: bool = True):
        path = os.path.expanduser(self._settings_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        payload = dataclasses.asdict(cfg)
        payload["roi_rects"] = [list(r) for r in (cfg.roi_rects or [])]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        if log_success:
            self.log(f"[SETTINGS] Saved to {path}")

    def _load_settings(self):
        path = os.path.expanduser(self._settings_path)
        if not os.path.exists(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            cfg = app_config_from_dict(raw)
            self._apply_config_to_ui(cfg)
            self.log(f"[SETTINGS] Loaded {path}")
        except Exception as e:
            self.log(f"[SETTINGS] Load failed: {e}")

    def save_settings(self):
        try:
            self._save_settings_to_disk(self.collect_config(), log_success=True)
        except Exception as e:
            self.log(f"[SETTINGS] Save failed: {e}")

    def collect_config(self) -> AppConfig:
        cfg = AppConfig()
        cfg.source = self.source_combo.currentText(); cfg.usb = self.usb_spin.value(); cfg.rtsp = self.rtsp_edit.text().strip(); cfg.rtsp_backend = self.rtsp_backend_combo.currentText()
        cfg.width = self.width_spin.value(); cfg.height = self.height_spin.value(); cfg.fps = self.fps_spin.value(); cfg.flip = self.flip_check.isChecked(); cfg.night_vision = self.night_check.isChecked(); cfg.debug_camera = self.debug_cam_check.isChecked()
        cfg.rtsp_stale_seconds = self.stale_spin.value(); cfg.rtsp_reconnect_delay = self.reconnect_spin.value(); cfg.rtsp_open_timeout_ms = self.open_timeout_spin.value(); cfg.rtsp_read_timeout_ms = self.read_timeout_spin.value()
        cfg.backend = self.backend_combo.currentText(); cfg.hef_model = self.hef_edit.text().strip(); cfg.model = self.model_combo.currentText().strip(); cfg.classes = self.classes_edit.text().strip(); cfg.conf = self.conf_spin.value(); cfg.iou = self.iou_spin.value(); cfg.imgsz = self.imgsz_spin.value(); cfg.skip_frames = self.skip_spin.value(); cfg.device = self.device_combo.currentText()
        cfg.pest_classes = self.pest_edit.text().strip(); cfg.safe_classes = self.safe_edit.text().strip(); cfg.draw_all = self.draw_all_check.isChecked(); cfg.roi_enabled = self.roi_enable_check.isChecked(); cfg.roi_rects = _normalize_roi_rects(self.video.roi_rects if cfg.roi_enabled else [])
        cfg.confirm_frames = self.confirm_spin.value(); cfg.cannon_fire = self.fire_spin.value(); cfg.cannon_holdoff = self.holdoff_spin.value(); cfg.dry_run = self.dry_run_check.isChecked(); cfg.save_detections = self.save_check.isChecked(); cfg.save_dir = self.save_dir_edit.text().strip(); cfg.save_every_detection = self.save_every_check.isChecked(); cfg.alert_sound = self.alert_sound_check.isChecked(); cfg.alert_sound_holdoff = self.alert_sound_holdoff_spin.value(); cfg.log_save_dir = self.log_dir_edit.text().strip()
        cfg.output_mode = self.output_mode_combo.currentText(); cfg.force_off_on_shutdown = self.force_off_check.isChecked(); cfg.gpio_enabled = self.gpio_enabled_check.isChecked() if self.is_raspberry_pi else False; cfg.gpio_pin = self.gpio_pin_spin.value(); cfg.gpio_active_high = self.gpio_active_high_check.isChecked(); cfg.gpio_backend = self.gpio_backend_combo.currentText();
        if not self.is_raspberry_pi and cfg.output_mode in ("gpio", "both"):
            cfg.output_mode = "mqtt"
        cfg.mqtt_enabled = self.mqtt_enable_check.isChecked(); cfg.mqtt_host = self.mqtt_host_edit.text().strip(); cfg.mqtt_port = self.mqtt_port_spin.value(); cfg.mqtt_user = self.mqtt_user_edit.text().strip(); cfg.mqtt_pass = self.mqtt_pass_edit.text(); cfg.mqtt_client_id = self.mqtt_client_edit.text().strip(); cfg.mqtt_topic = self.mqtt_topic_edit.text().strip(); cfg.mqtt_payload = self.mqtt_payload_edit.text(); cfg.mqtt_off_topic = self.mqtt_off_topic_edit.text().strip(); cfg.mqtt_off_payload = self.mqtt_off_payload_edit.text(); cfg.mqtt_qos = self.mqtt_qos_spin.value(); cfg.mqtt_retain = self.mqtt_retain_check.isChecked(); cfg.mqtt_keepalive = self.mqtt_keepalive_spin.value(); cfg.mqtt_json = self.mqtt_json_check.isChecked()
        return cfg

    def _set_controls_running(self, running: bool):
        """Lock settings while capture is active; always keep Stop correctly toggled.

        The tab bar stays enabled so the user can inspect settings during capture.
        Transport buttons (Start/Stop/Reset/Clear ROI) are set explicitly AFTER
        the tab-sweep so that findChildren can never accidentally override them.
        """
        self.tabs.setEnabled(True)
        # PySide6 findChildren only accepts a single type -- iterate each separately.
        _editable_types = (QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QCheckBox)
        for page_index in range(self.tabs.count()):
            page = self.tabs.widget(page_index)
            for widget_type in _editable_types:
                for child in page.findChildren(widget_type):
                    child.setEnabled(not running)
            # Settings-page action buttons (e.g. Browse) follow the same lock.
            # Transport buttons live outside the tabs so this loop cannot touch them.
            for child in page.findChildren(QPushButton):
                child.setEnabled(not running)

        # ── Transport buttons — set LAST so they cannot be overridden above ──
        self.start_btn.setEnabled(not running)
        self.stop_btn.setEnabled(running)

        # View controls remain available at all times.
        self.clear_roi_btn.setEnabled(True)
        self.reset_view_btn.setEnabled(True)
        self.fullscreen_btn.setEnabled(True)
        # MQTT test buttons — only available when capture is NOT running.
        self.mqtt_test_on_btn.setEnabled(not running)
        self.mqtt_test_off_btn.setEnabled(not running)
        # Manual cannon buttons — only active while capture is running.
        self.oneshot_btn.setEnabled(running)
        self.manual_on_btn.setEnabled(running)
        self.manual_off_btn.setEnabled(running)
        # Save log always available.
        self.save_log_btn.setEnabled(True)
        self.save_settings_btn.setEnabled(True)

    def _start_worker(self, cfg: AppConfig, clear_log: bool = False):
        if clear_log:
            self.log_box.clear()
        self._last_cfg = dataclasses.replace(cfg)
        self.worker = DetectionWorker(cfg)
        self.worker.frameReady.connect(self.video.set_frame)
        self.worker.logMessage.connect(self.log)
        self.worker.statusChanged.connect(lambda s: self.statusBar().showMessage(s))
        self.worker.fpsUpdated.connect(lambda fps: self.fps_label.setText(f"FPS: {fps:.1f}"))
        self.worker.statsUpdated.connect(self._update_stats)
        self.worker.manualStateChanged.connect(self._on_manual_state)
        self.worker.stopped.connect(self.on_worker_stopped)
        self.video.set_roi_enabled(cfg.roi_enabled)
        self.worker.set_roi(cfg.roi_enabled, cfg.roi_rects or [])
        self.worker.start()
        self._set_controls_running(True)

    def start_capture(self):
        cfg = self.collect_config()
        if cfg.source == "rtsp":
            rtsp_url = cfg.rtsp.strip()
            if not rtsp_url:
                QMessageBox.warning(self, "Missing RTSP URL", "Please enter an RTSP URL or select USB.")
                return
            parsed = urlparse(rtsp_url)
            if parsed.scheme.lower() not in ("rtsp", "rtsps") or not parsed.netloc:
                QMessageBox.warning(self, "Invalid RTSP URL", "Please enter a valid rtsp:// or rtsps:// URL before starting capture.")
                return
        try:
            self._save_settings_to_disk(cfg, log_success=False)
        except Exception as e:
            self.log(f"[SETTINGS] Auto-save failed: {e}")
        self._intentional_stop = False
        self._closing = False
        self._restart_attempts = 0
        self.log_box.clear()
        self.log("[GUI] Starting capture…")
        self._start_worker(cfg, clear_log=False)

    def _reset_manual_ui_state(self):
        self._manual_countdown_timer.stop()
        self._manual_countdown_secs = 0
        self.manual_countdown_label.setText("")
        self.manual_status_label.setText("Auto")
        self.manual_status_label.setStyleSheet("color: #4aaa55; font-weight: bold;")

    def stop_capture(self):
        self.fps_label.setText("FPS: —")
        self._reset_manual_ui_state()
        # Treat Stop as intentional so the watchdog does not restart the worker.
        # Keep the Stop button enabled visually until the worker actually emits
        # stopped; this avoids the UI looking dead if shutdown takes a moment.
        self._intentional_stop = True
        if self.worker is not None:
            self.log("[GUI] Stopping capture…")
            self.worker.stop()
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
        else:
            self._set_controls_running(False)

    def _restart_worker_after_fault(self):
        if self._closing or self._intentional_stop or self.worker is not None:
            return
        if self._last_cfg is None:
            self._set_controls_running(False)
            return
        self._restart_attempts += 1
        self.log(f"[WATCHDOG] Restarting capture attempt {self._restart_attempts}/{self._max_restart_attempts}…")
        try:
            self._start_worker(dataclasses.replace(self._last_cfg), clear_log=False)
        except Exception as e:
            self.log(f"[WATCHDOG] Restart failed: {e}")
            if self._restart_attempts < self._max_restart_attempts:
                QTimer.singleShot(self._restart_delay_ms, self._restart_worker_after_fault)
            else:
                self._set_controls_running(False)

    def on_worker_stopped(self):
        self._reset_manual_ui_state()
        self.worker = None
        if self._closing:
            self.log("[GUI] Capture stopped for shutdown")
            self._set_controls_running(False)
            return
        if self._intentional_stop:
            self.log("[GUI] Capture stopped")
            self._set_controls_running(False)
            return
        # Unexpected stop: keep settings locked and restart the detection worker.
        self.log(f"[WATCHDOG] Capture worker stopped unexpectedly — restarting in {self._restart_delay_ms/1000:.0f}s")
        self._set_controls_running(True)
        QTimer.singleShot(self._restart_delay_ms, self._restart_worker_after_fault)

    def log(self, msg: str):
        self.log_box.append(f"{human_ts()} {msg}"); self.log_box.verticalScrollBar().setValue(self.log_box.verticalScrollBar().maximum())

    def browse_log_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Choose log directory",
                                             os.path.expanduser(self.log_dir_edit.text()))
        if d:
            self.log_dir_edit.setText(d)

    def save_log(self):
        """Write the current log box contents to a timestamped file."""
        raw_dir = self.log_dir_edit.text().strip() if hasattr(self, 'log_dir_edit') else "~/cannon-logs"
        log_dir = os.path.expanduser(raw_dir or "~/cannon-logs")
        try:
            os.makedirs(log_dir, exist_ok=True)
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            path = os.path.join(log_dir, f"cannon_log_{ts}.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.log_box.toPlainText())
            self.log(f"[LOG] Saved to {path}")
        except Exception as e:
            self.log(f"[LOG] Save failed: {e}")

    def manual_oneshot(self):
        if self.worker is not None:
            self.worker.manual_oneshot()

    def manual_cannon_on(self):
        if self.worker is not None:
            timeout_mins = self.manual_timeout_spin.value()
            timeout_secs = timeout_mins * 60
            self._manual_countdown_secs = timeout_secs
            self._manual_countdown_timer.start()
            self.worker.manual_on(timeout_seconds=float(timeout_secs))

    def manual_cannon_off(self):
        self._manual_countdown_timer.stop()
        self._manual_countdown_secs = 0
        self.manual_countdown_label.setText("")
        if self.worker is not None:
            self.worker.manual_off()

    def _manual_countdown_tick(self):
        """Called every second while Cannon ON is active."""
        self._manual_countdown_secs -= 1
        if self._manual_countdown_secs <= 0:
            # Time expired — auto-off
            self._manual_countdown_timer.stop()
            self._manual_countdown_secs = 0
            self.manual_countdown_label.setText("")
            if self.worker is not None:
                self.worker.manual_off()
        else:
            mins, secs = divmod(self._manual_countdown_secs, 60)
            self.manual_countdown_label.setText(f"{mins:02d}:{secs:02d}")

    def _on_manual_state(self, state: str):
        """Update manual status label and button states."""
        if state == "ONESHOT":
            self.manual_status_label.setText("ONE-SHOT")
            self.manual_status_label.setStyleSheet("color: #e8a020; font-weight: bold;")
            self.oneshot_btn.setEnabled(False)
            self.manual_on_btn.setEnabled(False)
            self.manual_off_btn.setEnabled(False)
        elif state == "MANUAL_ON":
            self.manual_status_label.setText("MANUAL ON")
            self.manual_status_label.setStyleSheet("color: #dd3333; font-weight: bold;")
            self.oneshot_btn.setEnabled(False)
            self.manual_on_btn.setEnabled(False)
            self.manual_off_btn.setEnabled(True)
        else:  # IDLE
            self.manual_status_label.setText("Auto")
            self.manual_status_label.setStyleSheet("color: #4aaa55; font-weight: bold;")
            self.manual_countdown_label.setText("")
            self._manual_countdown_timer.stop()
            self._manual_countdown_secs = 0
            self.oneshot_btn.setEnabled(True)
            self.manual_on_btn.setEnabled(True)
            self.manual_off_btn.setEnabled(False)

    def _mqtt_test_send(self, state: str):
        cfg = self.collect_config()
        cfg.dry_run = False
        state_upper = state.upper()
        if state_upper not in ("ON", "OFF"):
            self.log(f"[MQTT-TEST] Unsupported state: {state}")
            return
        topic = cfg.mqtt_topic if state_upper == "ON" else (cfg.mqtt_off_topic or cfg.mqtt_topic)
        payload = cfg.mqtt_payload if state_upper == "ON" else cfg.mqtt_off_payload
        if cfg.mqtt_json:
            payload = json.dumps(
                {
                    "event": "test",
                    "state": state_upper,
                    "labels": ["test"],
                    "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
                }
            )
        client = None
        try:
            import paho.mqtt.client as mqtt
            client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=cfg.mqtt_client_id)
            if cfg.mqtt_user:
                client.username_pw_set(cfg.mqtt_user, cfg.mqtt_pass)
            client.connect(cfg.mqtt_host, cfg.mqtt_port, cfg.mqtt_keepalive)
            client.loop_start()
            info = client.publish(topic, payload, qos=cfg.mqtt_qos, retain=cfg.mqtt_retain)
            try:
                info.wait_for_publish(timeout=1.0)
            except TypeError:
                info.wait_for_publish()
            if hasattr(info, "is_published") and not info.is_published():
                self.log("[MQTT-TEST] Publish may still be queued after timeout")
            self.log(f"[MQTT-TEST] {state_upper} sent → topic={topic!r} payload={payload!r}")
        except Exception as e:
            self.log(f"[MQTT-TEST] {state_upper} failed: {e}")
        finally:
            if client is not None:
                try:
                    client.loop_stop()
                except Exception:
                    pass
                try:
                    client.disconnect()
                except Exception:
                    pass

    def _mqtt_test_on(self):
        """Send a test ON payload using the current MQTT tab settings."""
        self._mqtt_test_send("ON")

    def _mqtt_test_off(self):
        """Send a test OFF payload using the current MQTT tab settings."""
        self._mqtt_test_send("OFF")

    def toggle_fullscreen(self):
        if self._fs_window is None:
            # Reparent the VideoView into a borderless fullscreen window.
            self._fs_window = QWidget()
            self._fs_window.setStyleSheet("background: black;")
            layout = QVBoxLayout(self._fs_window)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(self.video)
            self._fs_window.showFullScreen()
            self.fullscreen_btn.setText("Exit fullscreen")
            self._fs_window.installEventFilter(self)
        else:
            self._exit_fullscreen()

    def _exit_fullscreen(self):
        if self._fs_window is None:
            return
        # Return the VideoView to the main window left layout.
        self._fs_window.layout().removeWidget(self.video)
        self._left_layout.insertWidget(0, self.video, 1)
        self._fs_window.close()
        self._fs_window = None
        self.fullscreen_btn.setText("Fullscreen")

    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent
        if self._fs_window and obj is self._fs_window:
            if event.type() == QEvent.KeyPress and event.key() == Qt.Key_Escape:
                self._exit_fullscreen()
                return True
        return super().eventFilter(obj, event)

    def _update_stats(self, pest_count: int, fire_count: int):
        self.pest_count_label.setText(f"Pests: {pest_count}")
        self.fire_count_label.setText(f"Fired: {fire_count}")
        # Highlight pest label in amber when non-zero
        self.pest_count_label.setStyleSheet(
            "color: #e8a020; font-size: 11px; font-weight: bold;" if pest_count > 0
            else "color: #8ab4d4; font-size: 11px;")
        # Highlight fire label in red when non-zero
        self.fire_count_label.setStyleSheet(
            "color: #dd3333; font-size: 11px; font-weight: bold;" if fire_count > 0
            else "color: #8ab4d4; font-size: 11px;")

    def shutdown(self):
        """Called from closeEvent — stop the worker cleanly before the window closes.

        Steps:
          1. Set flags so the watchdog and stopped-signal handler do nothing.
          2. Signal the worker to stop (clears its _running event).
          3. Wait up to 5 s for the thread to finish.
          4. If it hasn't finished, terminate it forcibly so the process exits.
          5. Release OpenCV windows.
        """
        self._closing = True
        self._intentional_stop = True
        try:
            self._save_settings_to_disk(self.collect_config(), log_success=False)
        except Exception as e:
            self.log(f"[SETTINGS] Auto-save failed during shutdown: {e}")
        self._exit_fullscreen()
        if self.worker is not None:
            self.log("[GUI] Shutting down capture worker…")
            self.worker.stop()
            # Process any queued Qt signals (e.g. frameReady) so the event loop
            # does not block waiting for slots that will never be delivered after
            # the window closes.
            QApplication.processEvents()
            if not self.worker.wait(5000):
                self.log("[WARN] Worker did not stop within 5 s — terminating thread")
                self.worker.terminate()
                self.worker.wait(1000)
            self.worker = None
        try:
            cv2.destroyAllWindows()
        except Exception:
            pass

    def closeEvent(self, event):
        # Hide immediately so the window appears to close right away even if the
        # worker takes a moment to wind down.
        self.hide()
        self.shutdown()
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("The AI Pest Cannon")
    win = MainWindow(); win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    mp.freeze_support()
    main()
