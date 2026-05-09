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

If you don't run DeepStack, the Face Recognizer camera tile will show a connection error on the stream, but all other cameras continue to work normally.

### 3. Add sample videos

Place test videos in the `videos/` directory:

| File | Used by |
|------|---------|
| `sample1.mp4` | Main Entrance (person detection) |
| `sample1.mp4` | Face Recognizer (shared for demo — replace with a face video or RTSP) |
| `sample3.mp4` | ANPR Gate (license plate detection) |

Videos loop automatically. Replace any `source` value with an RTSP URL to use a real camera.

### 4. Configure email alerts

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

### 5. Run the app

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

| Type | Description |
|------|-------------|
| `yolo` | YOLOv8 object detection — detects any COCO class |
| `anpr` | License plate YOLO detector + EasyOCR text extraction |
| `deepstack_face` | DeepStack face detection and recognition via HTTP |

### DeepStack face model config

```json
"face_recognizer": {
  "type": "deepstack_face",
  "deepstack_url": "http://localhost:80"
}
```

Change `deepstack_url` if DeepStack is running on a different host or port.

### UI / performance settings

| Field | Default | Description |
|-------|---------|-------------|
| `inference_interval_frames` | 5 | Run AI every Nth frame. Raise to reduce CPU load. |
| `jpeg_quality` | 70 | MJPEG stream quality (0–100). Lower saves bandwidth. |

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
├── models/                    YOLO weight files (.pt) — downloaded by setup.bat
├── videos/                    Sample test videos — replace with real streams
├── snapshots/                 Alert JPEG snapshots (auto-created)
├── recordings/                MP4 recordings (auto-created)
├── alerts/
│   └── alerts.csv             Running alert log
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
- **DeepStack face database** persists in the `localstorage` Docker volume. It survives container restarts as long as you use the same volume name.
- **ANPR accuracy** — the included plate model works for general plates. For Indian plates, fine-tuning a model on Indian plate datasets (available on Roboflow) gives significantly better results in production.
