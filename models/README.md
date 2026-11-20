# YOLO model weights

The `.pt` weight files are not stored in this repository. Some are larger than GitHub's 100 MB
file limit, and Ultralytics downloads the official ones automatically the first time a model name
is used.

`run_from_source.sh` runs the app from this folder, so selecting `yolo11n.pt`, `yolo11m.pt`,
`yolo26s.pt` and so on downloads that file here on first use. Custom-trained weights can also be
placed here.

| Model | Size | Notes |
|---|---|---|
| `yolo11n.pt` / `yolo26n.pt` | ~6 MB | Fastest; good for CPU-only machines |
| `yolo26s.pt` | ~20 MB | |
| `yolo11m.pt` / `yolo26m.pt` | ~40 MB | Good balance on Apple Silicon or an NVIDIA GPU |
| `yolo11l.pt` / `yolo26l.pt` | ~52 MB | |
| `yolo11x.pt` / `yolo26x.pt` | ~115 MB | Most accurate, slowest |

Raspberry Pi with a Hailo AI HAT+ uses compiled `.hef` models instead. Those are in
[`../hailo_models/`](../hailo_models/).
