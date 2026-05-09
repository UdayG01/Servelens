# ServeLens AI — Raspberry Pi Setup Guide

Tested against **Raspberry Pi 5 (4 GB / 8 GB)** running **Raspberry Pi OS Bookworm 64-bit**.  
A Pi 4 with 4 GB RAM is the minimum viable hardware for this stack; 8 GB is recommended for running all three cameras simultaneously with face recognition.

---

## Hardware Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| Model | Raspberry Pi 4 (4 GB) | Raspberry Pi 5 (8 GB) |
| Storage | 16 GB microSD (Class 10) | 64 GB microSD or USB SSD |
| OS | Raspberry Pi OS Bookworm 64-bit | Same |
| Cooling | Heatsink | Active cooler — this workload runs the SoC hot |
| Power | Official 5V/3A adapter | Official 27W USB-C (Pi 5) |

> **Why 64-bit OS?** PyTorch, YOLO, and EasyOCR only have prebuilt 64-bit ARM (aarch64) wheels. The 32-bit OS requires compiling from source — avoid it.

---

## 1. Prepare the OS

Flash **Raspberry Pi OS Bookworm (64-bit)** using the [Raspberry Pi Imager](https://www.raspberrypi.com/software/).  
In the imager's advanced settings, pre-configure:
- Hostname (e.g. `servelens`)
- Wi-Fi credentials
- SSH enabled
- Your username and password

Boot the Pi, then SSH in or open a terminal:

```bash
ssh pi@servelens.local
```

Update the system first:

```bash
sudo apt update && sudo apt full-upgrade -y
sudo reboot
```

---

## 2. Install System Dependencies

```bash
sudo apt install -y \
  python3-pip \
  python3-venv \
  git \
  ffmpeg \
  libgl1 \
  libglib2.0-0 \
  libsm6 \
  libxext6 \
  libxrender-dev \
  libatlas-base-dev \
  libjpeg-dev \
  libopenblas-dev
```

- `ffmpeg` — required by OpenCV for RTSP stream decoding
- `libgl1`, `libglib2.0-0` — required by OpenCV even in headless mode
- `libatlas-base-dev`, `libopenblas-dev` — accelerate NumPy operations on ARM

---

## 3. Increase Swap Space

The Pi's default swap (100 MB) is too small for loading PyTorch and YOLO models. Increase it to 2 GB before installing dependencies:

```bash
sudo dphys-swapfile swapoff
sudo nano /etc/dphys-swapfile
```

Find and change:

```
CONF_SWAPSIZE=100
```

to:

```
CONF_SWAPSIZE=2048
```

Save (`Ctrl+O`, `Enter`, `Ctrl+X`), then re-enable:

```bash
sudo dphys-swapfile setup
sudo dphys-swapfile swapon
```

Verify:

```bash
free -h
# Swap should now show ~2.0G
```

---

## 4. Clone the Repository

```bash
git clone <your-repo-url> ~/servelens
cd ~/servelens
```

---

## 5. Create Python Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate
```

Upgrade pip first:

```bash
pip install --upgrade pip setuptools wheel
```

---

## 6. Install Python Dependencies

> **Pi-specific note:** The `requirements.txt` uses `opencv-python` which pulls in X11/GUI libraries. On a headless Pi, use `opencv-python-headless` instead — it is functionally identical for this application.

Install everything in one step:

```bash
pip install \
  fastapi==0.115.4 \
  "uvicorn[standard]==0.32.0" \
  jinja2==3.1.4 \
  opencv-python-headless \
  "numpy==1.26.4" \
  "ultralytics==8.3.40" \
  easyocr==1.7.2 \
  "requests>=2.31.0"
```

Then install PyTorch separately (the ARM64 CPU-only build):

```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
```

> This downloads ~300 MB. On a slow connection, expect 10–20 minutes.  
> If the install fails or hangs, try adding `--no-cache-dir` to the pip command.

Verify PyTorch installed correctly:

```bash
python3 -c "import torch; print(torch.__version__)"
```

---

## 7. Download Model Weights

The YOLO model weights are not included in the repository. Download them manually:

```bash
mkdir -p models

# YOLOv8 nano — used by person detector and vehicle detector
wget -O models/yolov8n.pt https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov8n.pt

# License plate detector
wget -O models/license_plate_detector.pt \
  https://github.com/Muhammad-Zeerak-Khan/Automatic-License-Plate-Recognition-using-YOLOv8/raw/main/license_plate_detector.pt
```

---

## 8. Install Docker and Start DeepStack (Face Recognition)

Skip this section if you do not need face recognition.

### Install Docker

```bash
curl -sSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker
```

Verify:

```bash
docker run hello-world
```

### Configure the ARM image and start DeepStack

The project uses Docker Compose so you only configure the container once and start it with a single command from then on.

Copy the environment file and select the Pi image:

```bash
cp .env.example .env
nano .env
```

In the editor, **comment out** the x86 line and **uncomment** the Pi line so it reads:

```bash
# Windows / Linux x86 desktop
# DEEPSTACK_IMAGE=deepquestai/deepstack

# Raspberry Pi 4 / 5 (64-bit ARM)
DEEPSTACK_IMAGE=deepquestai/deepstack:arm64v8-cpu
```

Save and exit (`Ctrl+O`, `Enter`, `Ctrl+X`).

Start DeepStack:

```bash
docker compose up -d
```

Docker will pull the ARM64 image on first run (~500 MB), then start the container in the background. The face database persists in the `deepstack_data` volume between restarts. The `restart: unless-stopped` policy means DeepStack comes back up automatically on every Pi reboot — no manual intervention needed.

Check that it is running:

```bash
docker compose ps
# deepstack should show status "running"
```

Test the API:

```bash
curl http://localhost:80/v1/vision/face/list
# Expected: {"success":true,"faces":[]}
```

To stop DeepStack:

```bash
docker compose down
```

---

## 9. Create Sample Video Directories

```bash
mkdir -p videos snapshots recordings alerts
```

Place your test videos in `videos/`:

```bash
# Copy from another machine
scp your_video.mp4 pi@servelens.local:~/servelens/videos/sample1.mp4
```

Or download a free test clip:

```bash
wget -O videos/sample1.mp4 "https://www.pexels.com/video/..." # use any royalty-free clip
```

---

## 10. Configure for Raspberry Pi Performance

Open `config/config.json` and make these Pi-specific adjustments:

```json
{
  "ui": {
    "inference_interval_frames": 15,
    "jpeg_quality": 60
  }
}
```

**Why:**
- `inference_interval_frames: 15` — run AI every 15th frame instead of every 5th. The Pi CPU is ~3–5× slower than a desktop; this keeps the stream smooth across all cameras.
- `jpeg_quality: 60` — reduces the size of each MJPEG frame sent to the browser, lowering bandwidth and CPU encode time.

If running all three cameras simultaneously is too slow, disable one:

```json
{
  "id": "cam2",
  "enabled": false
}
```

---

## 11. Run the Application

Make sure the virtual environment is active:

```bash
cd ~/servelens
source venv/bin/activate
uvicorn app.server:app --host 0.0.0.0 --port 8000
```

Open in a browser on any device on the same network:

```
http://servelens.local:8000
```

Or by IP address (find it with `hostname -I`):

```
http://192.168.x.x:8000
```

---

## 12. Auto-Start on Boot (systemd)

To have ServeLens start automatically every time the Pi powers on, create a systemd service.

Create the service file:

```bash
sudo nano /etc/systemd/system/servelens.service
```

Paste the following — **replace `pi` with your actual username if different**:

```ini
[Unit]
Description=ServeLens AI Surveillance
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/servelens
ExecStart=/home/pi/servelens/venv/bin/uvicorn app.server:app --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

Enable and start the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable servelens
sudo systemctl start servelens
```

Check status:

```bash
sudo systemctl status servelens
```

View live logs:

```bash
journalctl -u servelens -f
```

---

## 13. Performance Expectations on Pi

| Operation | Pi 4 (1.8 GHz) | Pi 5 (2.4 GHz) |
|-----------|----------------|----------------|
| YOLO inference per frame | ~800 ms | ~400 ms |
| ANPR (YOLO + OCR) per frame | ~1.5 s | ~800 ms |
| DeepStack face recognition per frame | ~2–3 s | ~1.5 s |
| MJPEG stream FPS (no inference) | 25 fps | 25 fps |
| MJPEG stream FPS (inference every 15th frame) | 10–15 fps | 15–20 fps |

The stream remains smooth because inference runs asynchronously — frames are served from the latest annotated buffer while inference runs in the background.

**Practical recommendation for Pi 5:**
- `inference_interval_frames: 15` for person detection and ANPR
- `inference_interval_frames: 20–30` for face recognition (DeepStack is slower)
- Run no more than 2 cameras with active inference simultaneously on Pi 4; 3 cameras on Pi 5

---

## 14. Connecting Real IP Cameras

Change the `source` in `config/config.json` for any camera to its RTSP URL:

```json
"source": "rtsp://admin:password@192.168.1.100:554/Streaming/Channels/102"
```

Use the camera's **sub-stream** (channel `102` on Hikvision, `stream2` on Dahua) — it runs at lower resolution (typically 640×360 or 720p at 5–10 fps), which is much lighter on the Pi's CPU and network than the main 1080p/4K stream.

For a USB camera plugged directly into the Pi:

```json
"source": 0
```

For the official Raspberry Pi Camera Module (using libcamera):

```bash
# First check the camera is detected
libcamera-hello --list-cameras
```

Then use it as a V4L2 device:

```json
"source": "/dev/video0"
```

---

## 15. Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `ImportError: libGL.so.1` | Missing system lib | `sudo apt install libgl1` |
| `torch` install hangs | Slow pip on Pi | Add `--no-cache-dir`, try again |
| Stream shows `STREAM ERROR` | Wrong source path or RTSP URL | Test RTSP in VLC on another device first |
| Face recognizer shows `DeepStack:` error | DeepStack not running | `docker start deepstack` |
| DeepStack container exits immediately | Wrong image for Pi | Check `.env` — the Pi line (`arm64v8-cpu`) must be uncommented, not the x86 line |
| Very high CPU temperature | Sustained inference load | Add active cooling, raise `inference_interval_frames` |
| `OSError: [Errno 28] No space left` | Snapshots / recordings filled the SD card | Delete old files in `snapshots/` and `recordings/` |
| EasyOCR slow first run | Downloading text models (~64 MB) | One-time download, subsequent runs are fine |
| `systemctl status servelens` shows failed | Path or permission issue | Check `WorkingDirectory` and username in the service file |

---

## Quick Reference

```bash
# Activate environment
cd ~/servelens && source venv/bin/activate

# Start manually
uvicorn app.server:app --host 0.0.0.0 --port 8000

# Start / stop / restart as a service
sudo systemctl start servelens
sudo systemctl stop servelens
sudo systemctl restart servelens

# View logs
journalctl -u servelens -f

# Start / stop DeepStack
docker compose up -d
docker compose down

# Check DeepStack is responding
curl http://localhost:80/v1/vision/face/list

# Find Pi's IP address
hostname -I
```
