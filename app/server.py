"""
FastAPI web server for CCTV Intelligence.

Endpoints:
- GET  /                         -> Dashboard page
- GET  /api/cameras              -> Camera list + status
- GET  /api/alerts               -> Recent alerts
- GET  /api/snapshot/{filename}  -> Serves a snapshot image
- GET  /stream/{cam_id}          -> MJPEG live stream (multipart)
- POST /api/test-email           -> Send a test email
- POST /api/record/{cam_id}      -> Toggle continuous recording for that camera

Inference runs every Nth frame to keep CPU usable for 4-8 cameras.
Recording uses the annotated frame so detections are baked in.
"""

import os
import json
import time
import traceback
from datetime import datetime
from typing import Dict, Optional

import cv2
import numpy as np
import requests as _requests
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from .camera_stream import CameraStream
from .inference_engine import InferenceEngine
from .alert_manager import AlertManager
from .recorder import Recorder


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config", "config.json")
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
RECORDINGS_DIR = os.path.join(BASE_DIR, "recordings")
SNAPSHOTS_DIR = os.path.join(BASE_DIR, "snapshots")
ALERTS_DIR = os.path.join(BASE_DIR, "alerts")

for d in (RECORDINGS_DIR, SNAPSHOTS_DIR, ALERTS_DIR):
    os.makedirs(d, exist_ok=True)


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


CONFIG = load_config()
INFERENCE_INTERVAL = max(1, int(CONFIG.get("ui", {}).get("inference_interval_frames", 5)))

app = FastAPI(title="CCTV Intelligence")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

engine = InferenceEngine(CONFIG["models"])
alert_mgr = AlertManager(CONFIG["email"], SNAPSHOTS_DIR, ALERTS_DIR)

# State per camera
CAMERAS: Dict[str, dict] = {}


def make_on_frame(cam_cfg: dict):
    """Build the per-camera frame callback (closure over the camera config)."""
    cam_id = cam_cfg["id"]
    cam_name = cam_cfg["name"]
    models = cam_cfg.get("models", [])
    alert_classes = cam_cfg.get("alert_classes", [])
    min_conf = float(cam_cfg.get("min_confidence", 0.5))
    auto_event = CONFIG.get("recording", {}).get("auto_record_on_alert", True)
    event_dur = int(CONFIG.get("recording", {}).get("alert_clip_duration_sec", 15))

    def on_frame(_cam_id: str, frame: np.ndarray) -> np.ndarray:
        state = CAMERAS[cam_id]
        state["frame_count"] += 1
        annotated = frame
        detections = []

        if models and (state["frame_count"] % INFERENCE_INTERVAL == 0):
            try:
                annotated, detections = engine.infer(frame, models, alert_classes, min_conf)
            except Exception:
                traceback.print_exc()
                annotated = frame
                detections = []

        # overlay timestamp
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        h, _ = annotated.shape[:2]
        cv2.rectangle(annotated, (0, h - 22), (260, h), (0, 0, 0), -1)
        cv2.putText(annotated, f"{cam_name}  {ts}",
                    (4, h - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)

        if detections and alert_mgr.should_alert(cam_id):
            alert_mgr.trigger_alert(cam_id, cam_name, annotated, detections)
            if auto_event:
                state["recorder"].trigger_event(annotated, event_dur)

        state["recorder"].write(annotated)
        return annotated

    return on_frame


def start_cameras():
    rec_cfg = CONFIG.get("recording", {})
    for cam_cfg in CONFIG["cameras"]:
        if not cam_cfg.get("enabled", True):
            continue
        cam_id = cam_cfg["id"]
        source = cam_cfg.get("source") or cam_cfg.get("rtsp_url") or cam_cfg.get("video_path")
        if not source:
            print(f"[WARN] camera {cam_id} has no source")
            continue

        recorder = Recorder(
            cam_id, cam_cfg["name"], RECORDINGS_DIR,
            fps=int(rec_cfg.get("fps", 15)),
            fourcc=rec_cfg.get("fourcc", "mp4v"),
        )
        alert_mgr.configure_cooldown(cam_id, int(cam_cfg.get("alert_cooldown_sec", 60)))

        CAMERAS[cam_id] = {
            "config": cam_cfg,
            "recorder": recorder,
            "frame_count": 0,
            "stream": None,
        }

        stream = CameraStream(
            cam_id=cam_id, name=cam_cfg["name"], source=source,
            on_frame=make_on_frame(cam_cfg),
            jpeg_quality=int(CONFIG.get("ui", {}).get("jpeg_quality", 70)),
        )
        CAMERAS[cam_id]["stream"] = stream
        stream.start_capture()
        print(f"[Camera] started {cam_id} ({cam_cfg['name']}) -> {source}")


@app.on_event("startup")
def _startup():
    start_cameras()


@app.on_event("shutdown")
def _shutdown():
    for c in CAMERAS.values():
        try: c["stream"].stop_capture()
        except Exception: pass
        try: c["recorder"].shutdown()
        except Exception: pass
    alert_mgr.stop()


# ---------------- Routes ----------------

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {})


def _deepstack_url() -> str:
    for cfg in CONFIG.get("models", {}).values():
        if cfg.get("type") == "deepstack_face":
            return cfg.get("deepstack_url", "http://localhost:80").rstrip("/")
    return "http://localhost:80"


@app.get("/api/cameras")
def list_cameras():
    out = []
    for cam_id, c in CAMERAS.items():
        s = c["stream"]
        has_face_rec = any(
            CONFIG["models"].get(m, {}).get("type") == "deepstack_face"
            for m in c["config"].get("models", [])
        )
        out.append({
            "id": cam_id,
            "name": c["config"]["name"],
            "models": c["config"].get("models", []),
            "alert_classes": c["config"].get("alert_classes", []),
            "status": s.status if s else "uninit",
            "fps": round(s.current_fps, 1) if s else 0.0,
            "recording": c["recorder"].is_continuous(),
            "face_recognition": has_face_rec,
        })
    return {"cameras": out}


@app.get("/api/alerts")
def list_alerts(limit: int = 50):
    return {"alerts": alert_mgr.get_recent(limit=limit)}


@app.get("/api/snapshot/{filename}")
def get_snapshot(filename: str):
    path = os.path.join(SNAPSHOTS_DIR, os.path.basename(filename))
    if not os.path.exists(path):
        raise HTTPException(404, "snapshot not found")
    return FileResponse(path, media_type="image/jpeg")


@app.get("/stream/{cam_id}")
def stream(cam_id: str):
    if cam_id not in CAMERAS:
        raise HTTPException(404, "unknown camera")

    boundary = b"--frame"

    def gen():
        last_ts = 0.0
        while True:
            stream = CAMERAS[cam_id]["stream"]
            jpeg = stream.get_latest_jpeg() if stream else None
            now = time.time()
            if jpeg and now - last_ts > 0.05:  # ~20fps cap
                last_ts = now
                yield boundary + b"\r\nContent-Type: image/jpeg\r\nContent-Length: " + \
                      str(len(jpeg)).encode() + b"\r\n\r\n" + jpeg + b"\r\n"
            else:
                time.sleep(0.03)

    return StreamingResponse(gen(), media_type="multipart/x-mixed-replace; boundary=frame")


@app.post("/api/test-email")
def test_email():
    try:
        alert_mgr.send_test_email()
        return {"ok": True, "message": "Test email sent"}
    except Exception as e:
        raise HTTPException(500, f"Email failed: {e}")


@app.get("/api/faces/list")
def faces_list():
    url = f"{_deepstack_url()}/v1/vision/face/list"
    try:
        resp = _requests.get(url, timeout=5.0)
        result = resp.json()
    except Exception as e:
        raise HTTPException(503, f"DeepStack unreachable: {e}")
    if not result.get("success"):
        raise HTTPException(502, result.get("error", "DeepStack error"))
    return {"faces": result.get("faces", [])}


@app.post("/api/faces/register")
async def faces_register(
    name: str = Form(...),
    images: list[UploadFile] = File(...),
):
    import asyncio
    url = f"{_deepstack_url()}/v1/vision/face/register"
    results = []
    for img_file in images:
        img_bytes = await img_file.read()
        def _post(b=img_bytes, fn=img_file.filename):
            return _requests.post(
                url,
                files={"image": (fn, b, "image/jpeg")},
                data={"userid": name},
                timeout=10.0,
            ).json()
        try:
            result = await asyncio.to_thread(_post)
            results.append({
                "filename": img_file.filename,
                "success": result.get("success", False),
                "message": result.get("message", ""),
            })
        except Exception as e:
            results.append({"filename": img_file.filename, "success": False, "message": str(e)})
    return {"registered": name, "results": results}


@app.delete("/api/faces/{name}")
def faces_delete(name: str):
    url = f"{_deepstack_url()}/v1/vision/face/delete"
    try:
        resp = _requests.post(url, data={"userid": name}, timeout=5.0)
        result = resp.json()
    except Exception as e:
        raise HTTPException(503, f"DeepStack unreachable: {e}")
    if not result.get("success"):
        raise HTTPException(502, result.get("error", "DeepStack error"))
    return {"deleted": name, "success": True}


@app.post("/api/record/{cam_id}")
def toggle_record(cam_id: str):
    if cam_id not in CAMERAS:
        raise HTTPException(404, "unknown camera")
    state = CAMERAS[cam_id]
    rec = state["recorder"]
    if rec.is_continuous():
        path = rec.stop_continuous()
        return {"recording": False, "path": path}
    # need a sample frame to size the writer
    jpeg = state["stream"].get_latest_jpeg() if state["stream"] else None
    if not jpeg:
        raise HTTPException(503, "no frame yet — wait for stream to start")
    arr = np.frombuffer(jpeg, dtype=np.uint8)
    sample = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if sample is None:
        raise HTTPException(503, "cannot decode current frame")
    path = rec.start_continuous(sample)
    if not path:
        raise HTTPException(500, "failed to start recording")
    return {"recording": True, "path": path}
