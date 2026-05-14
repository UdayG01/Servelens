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