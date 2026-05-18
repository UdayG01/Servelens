# ServeLens AI — Multi-Camera Surveillance Dashboard

A real-time, browser-based surveillance platform with AI-powered object detection, face recognition, and license plate reading. Streams live annotated video from IP cameras (RTSP), USB webcams, or local video files directly to your browser — no plugins required.

---

## Features

### Live Video Dashboard
- View multiple camera feeds simultaneously in a responsive grid layout
- MJPEG streaming works natively in all browsers, including mobile
- Per-tile status indicators: connection state, live FPS counter
- Control-room dark theme with amber accents

### AI Detection Engines

| Camera | Detector | What it detects |
|--------|----------|-----------------|
| Main Entrance | Person Detector (YOLOv8) | People |
| Face Recognizer | Face Recognition (DeepStack) | Known / unknown faces with names |
| ANPR Gate | License Plate Reader (YOLO + EasyOCR) | Vehicle plates + extracted text |
| Fire & Smoke | FireNET (DeepStack custom model) | Fire and smoke |

### Fire & Smoke Detection
- Powered by **DeepStack FireNET** — a custom model loaded into the same DeepStack container used for face recognition
- Orange-red bounding box = fire detected, grey bounding box = smoke detected
- Early smoke detection warns before visible flames appear
- Alert cooldown keeps notifications manageable in active environments
- See [Custom DeepStack Models](#custom-deepstack-models--firenet) for setup instructions

### Face Recognition
- Powered by **DeepStack** running locally as a Docker container (no cloud, fully private)
- Green bounding box = recognized person (name + confidence shown)
- Red bounding box = unknown / unregistered person
- Train new faces directly from the web UI — upload one or more photos per person
- More photos per person improves accuracy
- Manage registered profiles (view list, delete) from the same UI panel

### Alert System
- Configurable alert classes per camera (person, face, license plate, vehicle, etc.)
- Per-camera cooldown prevents alert spam
- Each alert saves an annotated snapshot JPEG to `snapshots/`
- Alert sidebar with thumbnails — click any entry to view full snapshot
- Recognized face names shown as green badges in the alert log
- License plate text shown as yellow badges in the alert log
- CSV log of all alerts at `alerts/alerts.csv`

### Email Notifications
- Alert emails sent via Gmail SMTP with the snapshot attached
- Configurable sender, recipients, and subject prefix
- Test Email button in the header to verify setup

### Video Recording
- Toggle continuous recording per camera from the dashboard tile
- Auto-record 15-second event clips on every alert trigger (configurable duration)
- Recordings saved as MP4 to `recordings/`

---

## System Requirements

> **Commercial deployment note:** This system is designed for 24/7 operation with continuous AI inference across multiple live camera feeds. Consumer-grade hardware that can *run* the software is not sufficient — it must sustain the full workload without thermal throttling, FPS degradation, or reliability risk over weeks of uninterrupted operation. A **dedicated desktop PC with a discrete NVIDIA GPU is the minimum viable deployment target.** Laptops are unsuitable for commercial 24/7 use regardless of specs; sustained GPU/CPU load will cause thermal throttling, fan wear, and reduced hardware lifespan.

### Why GPU is mandatory

Running all four AI models on CPU (`device: "cpu"`) consumes close to 100% of a modern CPU under continuous 4-camera load: YOLOv8 Nano takes ~30–50 ms per inference on CPU; at 6 inferences/sec across 4 cameras that is already ~1.2 seconds of CPU time demanded per second before EasyOCR's 200–600 ms OCR spikes, DeepStack HTTP round-trips (~100–300 ms each), OpenCV decode, MJPEG encode, and MP4 write overhead. Any consumer PC running this profile 24/7 will thermally throttle within hours, dropping frames, stalling alerts, and degrading hardware. GPU inference brings per-frame latency down to ~3–8 ms, reducing total AI CPU time by 85–90% and making sustained operation practical.

### Minimum — sustained 24/7 commercial operation

| Component | Minimum specification | Justification |
|-----------|----------------------|---------------|
| **Form factor** | Desktop PC (tower) | Laptops thermally throttle under sustained 24/7 AI + recording load. A desktop chassis provides adequate airflow, replaceable cooling, and no battery degradation risk. |
| **OS** | Windows 10 Pro 64-bit (22H2+) or Windows 11 Pro 64-bit | Pro edition provides better process scheduling, Remote Desktop access for remote management, and Group Policy support needed in commercial settings. |
| **CPU** | 8-core / 16-thread x86-64 — e.g. Intel Core i7-10700, AMD Ryzen 7 3700X | With GPU handling inference, the CPU still manages 4 OpenCV capture threads, 4 MJPEG encode loops, concurrent MP4 writes, FastAPI request handling, and DeepStack HTTP dispatch simultaneously. An 8-core desktop CPU keeps all of these below 50% utilisation, leaving thermal headroom for 24/7 operation. A 6-core i5-class CPU pushes past 70% under full load — inadequate for sustained commercial use. |
| **RAM** | 16 GB DDR4 | Working set breakdown: Python process (CUDA PyTorch + 2× YOLOv8 Nano + EasyOCR + OpenCV buffers + FastAPI): ~3.5 GB. DeepStack container (4.28 GB image, FireNET 169 MB + face recognition + runtime): ~2.5 GB resident. Docker Desktop daemon: ~500 MB. Windows 10/11 idle: ~3–4 GB. Total: ~10 GB. 16 GB provides the minimum safe headroom for stable 24/7 operation without risking OOM kills under recording spikes or transient inference bursts. 8 GB leaves ~0 headroom and is not viable for commercial deployment. |
| **GPU** | NVIDIA GTX 1660 Super 6 GB VRAM or RTX 2060 6 GB VRAM (CUDA 11.8+) | 6 GB VRAM is the minimum to run both the Python CUDA inference process and DeepStack GPU container simultaneously without VRAM exhaustion. VRAM budget: Python CUDA (2× YOLOv8 Nano ~500 MB + EasyOCR ~200 MB + CUDA runtime ~300 MB) ≈ 1 GB. DeepStack GPU (FireNET ~400 MB + face recognition model ~800 MB + CUDA overhead ~400 MB) ≈ 1.6 GB. Total: ~2.6 GB — 4 GB GPUs are marginal and risk OOM under concurrent inference load; 6 GB gives reliable headroom. GPU must support CUDA 11.8+. |
| **Disk — system** | 256 GB NVMe SSD | Storage breakdown: Windows + Docker Desktop: ~30 GB. Python venv with CUDA PyTorch: ~4 GB (CPU-only venv is ~1.2 GB but CUDA build adds ~3 GB). DeepStack CPU image (measured at 4.28 GB): ~5 GB with Docker overhead. DeepStack GPU image: ~7 GB. Model weights (YOLOv8n + plate + FireNET): ~200 MB. EasyOCR English model: ~200 MB. Application code: ~50 MB. Working headroom: ~15 GB. NVMe is required — SATA SSD works but HDD causes frame-drop artifacts when 4 MP4 writers compete for the same disk. |
| **Disk — recording storage** | 1 TB dedicated drive (HDD or NAS) | 4-camera continuous recording at 854×480 @ 15 FPS H.264 generates approximately 200–450 MB/hour per camera depending on scene motion. At 300 MB/hour average: 4 cameras × 300 MB × 24 h = **~28 GB/day**, ~860 GB/month. A separate recording drive (or NAS mount) prevents recording I/O from competing with the OS and Docker volumes on the system SSD. |
| **Network** | Gigabit LAN | 4 RTSP sub-streams (480p) at ~2 Mbps each = 8 Mbps inbound. MJPEG streams to browser clients: ~3–5 Mbps per camera per viewer — two concurrent viewers watching all 4 feeds = ~40 Mbps outbound. Gigabit is the practical minimum; 100 Mbps becomes a bottleneck with more than one simultaneous viewer. |
| **Python** | 3.10+ | Required by `ultralytics` ≥ 8.x and `fastapi` 0.115. |
| **Docker** | Docker Desktop 4.25+ (Windows) | Required for DeepStack (Face Recognizer + Fire & Smoke cameras). Docker Desktop 4.25+ includes the compose V2 plugin and improved WSL 2 memory reclamation critical for long-running containers. |

### Recommended — commercial 24/7 with operational headroom

| Component | Recommended specification | Justification |
|-----------|--------------------------|---------------|
| **Form factor** | Desktop PC (tower) with active chassis cooling | Same as minimum — desktop only. Prefer cases with positive pressure and dust filters for deployments in dusty commercial environments (warehouses, factories, construction sites). |
| **OS** | Windows 11 Pro 64-bit | Improved scheduler for hybrid CPU architectures; better WSL 2 integration; longer support lifecycle. |
| **CPU** | Intel Core i7-13700 / i9-13900 or AMD Ryzen 7 7700X (8+ cores, 16+ threads) | Efficient-core architectures handle background tasks (recording, network, OS) on E-cores while P-cores stay available for inference dispatch and OpenCV. Keeps all threads below 40% average utilisation, providing a large thermal buffer for commercial 24/7. |
| **RAM** | 32 GB DDR5 | Allows adding more cameras, switching to heavier YOLO models (YOLOv8m/l), running a local operator dashboard browser, and Remote Desktop sessions without touching the swap file. Swap activity on a 24/7 server causes unpredictable latency spikes in recording and alert delivery. |
| **GPU** | NVIDIA RTX 3060 12 GB or RTX 4060 Ti 8 GB (CUDA 12.x) | 12 GB VRAM (RTX 3060) allows running the full Python CUDA stack + DeepStack GPU simultaneously with headroom for more cameras or larger YOLO models. The RTX 4060 Ti 8 GB is the better choice for new purchases — higher efficiency (Ada Lovelace), lower TDP (165 W vs 170 W), and longer driver support lifecycle. Both are desktop-class GPUs with adequate cooling for sustained load. |
| **Disk — system** | 500 GB NVMe SSD (Gen4 preferred) | Accommodates both the CPU and GPU Docker images, multiple Python venvs, and leaves ~250 GB for short-term snapshot/clip retention before offloading to archive storage. |
| **Disk — recording archive** | 4 TB HDD (7200 RPM) or NAS mount | At 28 GB/day (4 cameras), a 4 TB drive holds ~140 days of continuous footage. A NAS mount allows expanding capacity without touching the host PC. |
| **Network** | Gigabit LAN with PoE switch | PoE switch (802.3af/at) powers IP cameras directly over the same Ethernet cable used for RTSP, eliminating separate camera power runs in commercial installations. |
| **UPS** | 1500 VA / 900 W or larger | Uninterruptible power supply prevents abrupt MP4 file corruption and Docker volume corruption on power loss — both cause data loss that is unacceptable in a commercial surveillance context. |
| **Python** | 3.11 | ~10–15% throughput improvement over 3.10 for CPU-bound tasks (OpenCV decode, JPEG encode); fully compatible with all pinned dependency versions. |
| **Docker** | Docker Desktop 4.30+ (Windows) | Latest stable release with best WSL 2 memory management and CUDA container support. |

### Enabling GPU inference

Install the CUDA-enabled PyTorch build inside the venv, then set `"device": "cuda"` for each model in `config/config.json`. EasyOCR picks up the GPU automatically when device is not `"cpu"`.

```cmd
venv\Scripts\activate
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
```

For DeepStack GPU mode, edit `.env` to select the GPU image variant (see `.env.example`) — this requires NVIDIA drivers 525+ installed on the host before starting the container.

---

## Setup

### Prerequisites

- Python 3.10 or newer
- Docker Desktop — only required for the Face Recognizer camera
- Git

### 1. Clone and install dependencies

```cmd
git clone <repo-url>
cd Servelens
setup.bat
```

`setup.bat` creates a virtual environment, installs all Python dependencies, and downloads the YOLO model weights. This takes around 5 minutes on first run (PyTorch and EasyOCR are large).

Or manually:

```cmd
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Start DeepStack (Face Recognition only)

DeepStack must be running before you start the app if the Face Recognizer camera is enabled.

**First-time setup — copy the environment file:**

```cmd
copy .env.example .env
```

Open `.env` and uncomment the line matching your hardware. On Windows x86 the default is already correct — no change needed.

**Start DeepStack:**

```cmd
docker compose up -d
```

The container starts in the background, auto-restarts on reboot, and the face database persists in the `deepstack_data` Docker volume between restarts.

To stop it:

```cmd
docker compose down
```

If you don't run DeepStack, the Face Recognizer and Fire & Smoke camera tiles will show a connection error on their streams, but all other cameras continue to work normally.

### 3. Download custom DeepStack models

The Fire & Smoke camera uses the **FireNET** model served through DeepStack's custom model endpoint. `setup.bat` downloads this automatically — if you ran setup.bat you can skip this step.

**Manual download (if needed):**

```cmd
powershell -Command "Invoke-WebRequest -Uri 'https://github.com/DeepQuestAI/DeepStack_FireNET/releases/download/v2/firenetv2.pt' -OutFile 'deepstack_models\fire-detection.pt'"
```

The filename must be exactly `fire-detection.pt` — this is what `config/config.json` references. After placing the file, restart DeepStack so it loads the model:

```cmd
docker compose restart deepstack
```

Verify it loaded:

```cmd
curl -X POST http://localhost:80/v1/vision/custom/fire-detection -F "image=@any_image.jpg"
```

A response of `{"success": true, ...}` confirms the model is active.

### 4. Add sample videos

Place test videos in the `videos/` directory:

| File | Used by |
|------|---------|
| `sample1.mp4` | Main Entrance (person detection) |
| `sample1.mp4` | Face Recognizer (shared for demo — replace with a face video or RTSP) |
| `sample3.mp4` | ANPR Gate (license plate detection) |

Videos loop automatically. Replace any `source` value with an RTSP URL to use a real camera.

### 5. Configure email alerts

Edit `config/config.json` — find the `email` section:

```json
"email": {
  "enabled": true,
  "smtp_server": "smtp.gmail.com",
  "smtp_port": 587,
  "sender_email": "your@gmail.com",
  "sender_app_password": "xxxx xxxx xxxx xxxx",
  "recipients": ["notify@example.com"],
  "subject_prefix": "[CCTV ALERT]"
}
```

The `sender_app_password` is a Gmail App Password, not your account password.
Generate one at: https://myaccount.google.com/apppasswords (requires 2-Step Verification to be enabled).

### 6. Run the app

```cmd
run.bat
```

Or manually:

```cmd
venv\Scripts\activate
uvicorn app.server:app --host 0.0.0.0 --port 8000
```

Open **http://localhost:8000** in any browser.  
Other devices on your LAN can reach it at `http://<your-machine-ip>:8000`.

---

## Connecting Camera Streams

The `source` field in each camera config entry accepts:

| Source type | Example value | Notes |
|-------------|---------------|-------|
| Local video file | `"videos/sample1.mp4"` | Loops automatically |
| RTSP IP camera | `"rtsp://admin:pass@192.168.1.100/stream1"` | Auto-reconnects on drop |
| USB / built-in webcam | `0` | Integer index |

**RTSP tip:** Use the camera's sub-stream (e.g. Hikvision channel `102` instead of `101`). Sub-streams run at lower resolution and framerate, which is much lighter on CPU.

```json
"source": "rtsp://admin:password@192.168.1.100:554/Streaming/Channels/102"
```

---

## Face Recognition — Adding New Faces

### Via the web UI

1. Open the dashboard at `http://localhost:8000`
2. On the **Face Recognizer** camera tile, click the **⊙ FACES** button
3. In the panel that opens:
   - Enter the person's name in the **Person name** field
   - Click **Choose images…** and select one or more clear face photos (JPEG or PNG)
   - Click **+ Register**
4. The registered name appears in the **Registered Faces** list immediately
5. Repeat with additional photos for the same name to improve accuracy

### Tips for better recognition accuracy

- Use well-lit, front-facing photos where the face is clearly visible
- Avoid heavy shadows, sunglasses, hats, or masks in training images
- Register at least 3–5 images per person covering slight angle variations
- Portrait crops where the face fills most of the frame work better than full-body shots

### Deleting a face profile

Open **⊙ FACES** on the Face Recognizer tile → click **Delete** next to the name.

### Via the API

```bash
# Register face images for a person
curl -X POST http://localhost:8000/api/faces/register \
  -F "name=Jane Smith" \
  -F "images=@photo1.jpg" \
  -F "images=@photo2.jpg"

# List all registered face profiles
curl http://localhost:8000/api/faces/list

# Delete a face profile
curl -X DELETE "http://localhost:8000/api/faces/Jane%20Smith"
```

---

## Custom DeepStack Models — FireNET

DeepStack supports loading any custom model via its `/v1/vision/custom/{model_name}` endpoint. ServeLens uses this for fire and smoke detection through the **FireNET** model.

### How it works

```
deepstack_models/
└── fire-detection.pt          ← model file on the host
        ↓ mounted via docker-compose.yml
/modelstore/detection/         ← inside the DeepStack container
        ↓ served automatically at
POST /v1/vision/custom/fire-detection
```

The `docker-compose.yml` mounts `./deepstack_models` into the container at `/modelstore/detection`. Any `.pt` file placed there becomes available as an endpoint named after the file (without extension). No container rebuild is needed — only a restart.

### FireNET setup (step by step)

| Step | Action |
|------|--------|
| 1 | Go to `https://github.com/DeepQuestAI/DeepStack_FireNET` |
| 2 | Download `fire-detection.pt` from the releases or `models/` folder |
| 3 | Place it at `deepstack_models/fire-detection.pt` |
| 4 | Run `docker compose restart deepstack` |
| 5 | Verify: `curl -X POST http://localhost:80/v1/vision/custom/fire-detection -F "image=@any.jpg"` |

### How it maps to config.json

```json
"fire_smoke_detector": {
    "type": "deepstack_custom",
    "deepstack_url": "http://localhost:80",
    "model_name": "fire-detection"
}
```

- `type: "deepstack_custom"` — routes inference through `DeepStackDetector` in `app/deepstack_detector.py`
- `model_name` — must match the filename without `.pt`
- `deepstack_url` — change if DeepStack runs on a different host or port

### Adding a different custom model

The same pattern works for any DeepStack-compatible `.pt` model:

1. Place `your-model.pt` in `deepstack_models/`
2. Run `docker compose restart deepstack`
3. Add a model entry to `config/config.json`:
   ```json
   "your_detector": {
       "type": "deepstack_custom",
       "deepstack_url": "http://localhost:80",
       "model_name": "your-model"
   }
   ```
4. Reference it in the camera's `"models"` array and set `"alert_classes"` to the label names the model outputs.

### Why model files are not in the repository

DeepStack model files are large binaries (50–200 MB each). They are excluded via `.gitignore` (`deepstack_models/*.pt`). The `deepstack_models/` directory itself is tracked via `.gitkeep` so the mount point exists after a fresh clone. Each developer downloads the model files separately using the instructions above.

---

## Configuration Reference

### Camera fields (`config/config.json` → `cameras` array)

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique camera identifier (e.g. `"cam1"`) |
| `name` | string | Display name shown on the tile and in alerts |
| `source` | string / int | Video file path, RTSP URL, or webcam index |
| `enabled` | bool | `false` skips this camera on startup |
| `models` | array | Model keys to run (references keys in the `models` section) |
| `alert_classes` | array | Detection class names that trigger alerts |
| `min_confidence` | float | Minimum detection confidence threshold (0.0–1.0) |
| `alert_cooldown_sec` | int | Minimum seconds between consecutive alerts for this camera |

### Model types

| Type | Description | Required fields |
|------|-------------|-----------------|
| `yolo` | YOLOv8 object detection — detects any COCO class | `weights`, `img_size`, `device` |
| `anpr` | License plate YOLO detector + EasyOCR text extraction | `weights`, `img_size`, `device`, `ocr_languages`, `ocr_min_confidence` |
| `deepstack_face` | DeepStack face recognition via HTTP | `deepstack_url` |
| `deepstack_custom` | Any custom model served by DeepStack | `deepstack_url`, `model_name` |

### DeepStack model config examples

```json
"face_recognizer": {
    "type": "deepstack_face",
    "deepstack_url": "http://localhost:80"
},
"fire_smoke_detector": {
    "type": "deepstack_custom",
    "deepstack_url": "http://localhost:80",
    "model_name": "fire-detection"
}
```

`deepstack_url` defaults to `http://localhost:80`. Change it if DeepStack runs on a different host or port (e.g. a separate machine on the network).

### UI / performance settings

| Field | Default | Description |
|-------|---------|-------------|
| `inference_interval_frames` | 5 | Run AI every Nth frame. Raise to reduce CPU load. |
| `jpeg_quality` | 70 | MJPEG stream quality (0–100). Lower saves bandwidth. |
| `frame_width` | _(none)_ | Resize every frame to this width before inference and streaming. |
| `frame_height` | _(none)_ | Resize every frame to this height. Must be set together with `frame_width`. |

`frame_width` and `frame_height` can also be set per-camera to override the global value for that camera only.

---

## Performance Tuning (Multiple Cameras)

| Config change | Effect |
|---------------|--------|
| `"inference_interval_frames": 10` | Halves AI inference load |
| `"jpeg_quality": 50` | Reduces stream bandwidth to browser |
| Use RTSP sub-stream | Big CPU saving vs main stream |
| `"device": "cuda"` (NVIDIA GPU) | 5–10× inference speedup |
| `"img_size": 480` | Smaller input = faster inference, slightly lower accuracy |

For GPU: install CUDA-enabled PyTorch from https://pytorch.org/get-started/locally/ then set `"device": "cuda"` for any model in config.

---

## Directory Structure

```
Servelens/
├── app/
│   ├── server.py              FastAPI routes, camera startup, face management API
│   ├── camera_stream.py       Per-camera OpenCV capture thread (RTSP / file / webcam)
│   ├── inference_engine.py    Model loader and inference dispatcher
│   ├── face_recognizer.py     DeepStack face recognition HTTP client
│   ├── deepstack_detector.py  Generic DeepStack custom model client (fire, smoke, etc.)
│   ├── anpr.py                YOLO plate detector + EasyOCR pipeline
│   ├── alert_manager.py       Cooldown logic, snapshots, CSV log, Gmail SMTP
│   ├── recorder.py            Continuous and event-clip MP4 recording
│   ├── static/
│   │   ├── app.js             Dashboard UI logic (polling, face modal, alerts)
│   │   └── style.css          Dark control-room theme
│   └── templates/
│       └── index.html         Dashboard HTML + face management modal
├── config/
│   └── config.json            All configuration (cameras, models, email, recording)
├── deepstack_models/          Custom DeepStack model files (.pt) — not in repo, download separately
│   └── .gitkeep               Keeps the directory tracked in git after a fresh clone
├── models/                    YOLO weight files (.pt) — downloaded by setup.bat, not in repo
├── videos/                    Sample test videos — not in repo, provide your own
├── snapshots/                 Alert JPEG snapshots (auto-created at runtime)
├── recordings/                MP4 recordings (auto-created at runtime)
├── alerts/
│   └── alerts.csv             Running alert log (auto-created at runtime)
├── docker-compose.yml         DeepStack container definition
├── .env.example               Environment variable template — copy to .env and configure
├── requirements.txt
├── run.bat
└── setup.bat
```

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Dashboard |
| GET | `/stream/{cam_id}` | Live MJPEG stream |
| GET | `/api/cameras` | Camera list with status, FPS, recording state |
| GET | `/api/alerts?limit=50` | Recent alert history |
| GET | `/api/snapshot/{filename}` | Serve an alert snapshot image |
| POST | `/api/test-email` | Send a test alert email |
| POST | `/api/record/{cam_id}` | Toggle continuous recording for a camera |
| GET | `/api/faces/list` | List registered face profiles from DeepStack |
| POST | `/api/faces/register` | Upload images and register a face (multipart form) |
| DELETE | `/api/faces/{name}` | Delete a face profile from DeepStack |

---

## Common Issues

| Symptom | Fix |
|---------|-----|
| Tile shows "STREAM ERROR" | Source path or RTSP URL is wrong. Test RTSP in VLC first. |
| Face Recognizer shows "DeepStack: ..." | DeepStack container is not running. Start it with the Docker command above. |
| Face Recognizer shows "no registered faces" | No faces have been trained yet. Use ⊙ FACES to register some. |
| Test Email fails with auth error | App Password is wrong, or Gmail 2-Step Verification is not enabled. |
| ANPR is slow on first detection | EasyOCR downloads its English text model (~64 MB) once on first use. |
| High CPU across all cameras | Raise `inference_interval_frames`, switch to RTSP sub-stream, or reduce `img_size` to 480. |
| Black / unplayable recording files | Try `"fourcc": "avc1"` instead of `"mp4v"` in the recording config. |
| LAN devices can't reach the dashboard | Allow port 8000 through Windows Defender Firewall. |

---

## Notes

- **No authentication** is built in — restrict access to your local network, or place the app behind a reverse proxy (e.g. Nginx + Basic Auth) before exposing it externally.
- **Storage grows unbounded** — snapshots and recordings accumulate indefinitely. Set up a scheduled cleanup task for long-running deployments.
- **DeepStack face database** persists in the `deepstack_data` Docker volume. It survives container restarts and `docker compose down` as long as you use the same volume name.
- **ANPR accuracy** — the included plate model works for general plates. For Indian plates, fine-tuning a model on Indian plate datasets (available on Roboflow) gives significantly better results in production.



## For live camera

Change any camera's `source` in `config/config.json` from a video file to your RTSP URL:

```json
{
    "id": "cam2",
    "name": "Face Recognizer",
    "source": "rtsp://admin:yourpassword@192.168.1.100:554/stream2",
    "enabled": true,
    "models": ["face_recognizer"],
    "alert_classes": ["face"],
    "min_confidence": 0.75,
    "alert_cooldown_sec": 30
}
```

> **Security:** Do not commit `config/config.json` with real credentials to a public repository. Add it to `.gitignore`, or replace credentials with environment variable references before committing.