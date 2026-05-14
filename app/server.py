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
RECENT_FACES_DIR = os.path.join(BASE_DIR, "recent_faces")

for d in (RECORDINGS_DIR, SNAPSHOTS_DIR, ALERTS_DIR, RECENT_FACES_DIR):
    os.makedirs(d, exist_ok=True)

RECENT_FACES_COOLDOWN = {}


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
                for det in detections:
                    if det.get("class") == "face":
                        label = det.get("name", "Unknown")
                        cam_lbl_key = f"{cam_id}_{label}"
                        now_sec = time.time()
                        if now_sec - RECENT_FACES_COOLDOWN.get(cam_lbl_key, 0) > 2.0:
                            RECENT_FACES_COOLDOWN[cam_lbl_key] = now_sec
                            x1, y1, x2, y2 = det.get("bbox", [0,0,0,0])
                            h, w = frame.shape[:2]
                            fh, fw = y2 - y1, x2 - x1
                            my, mx = int(fh * 0.2), int(fw * 0.2)
                            nx1, ny1 = max(0, x1 - mx), max(0, y1 - my)
                            nx2, ny2 = min(w, x2 + mx), min(h, y2 + my)
                            face_crop = frame[ny1:ny2, nx1:nx2]
                            if face_crop.size > 0:
                                ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                                safe_lbl = "".join(c for c in label if c.isalnum() or c in " _-")
                                label_dir = os.path.join(RECENT_FACES_DIR, safe_lbl)
                                os.makedirs(label_dir, exist_ok=True)
                                fn = f"{safe_lbl}_{cam_id}_{ts_str}.jpg"
                                cv2.imwrite(os.path.join(label_dir, fn), face_crop)
                                files = [os.path.join(label_dir, f) for f in os.listdir(label_dir) if f.endswith(".jpg")]
                                if len(files) > 100:
                                    files.sort(key=os.path.getmtime)
                                    for f in files[:-100]:
                                        try: os.remove(f)
                                        except: pass
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

        CAMERAS[cam_id]["last_detections"] = detections

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
            "last_detections": [],
        }

        ui_cfg = CONFIG.get("ui", {})
        rw = cam_cfg.get("frame_width") or ui_cfg.get("frame_width")
        rh = cam_cfg.get("frame_height") or ui_cfg.get("frame_height")
        resize_to = (int(rw), int(rh)) if rw and rh else None

        stream = CameraStream(
            cam_id=cam_id, name=cam_cfg["name"], source=source,
            on_frame=make_on_frame(cam_cfg),
            jpeg_quality=int(ui_cfg.get("jpeg_quality", 70)),
            resize_to=resize_to,
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

@app.get("/faces", response_class=HTMLResponse)
def faces_page(request: Request):
    return templates.TemplateResponse(request, "faces.html", {})


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
        supports_count = "person" in [
            cl.lower() for cl in c["config"].get("alert_classes", [])
        ]
        out.append({
            "id": cam_id,
            "name": c["config"]["name"],
            "models": c["config"].get("models", []),
            "alert_classes": c["config"].get("alert_classes", []),
            "status": s.status if s else "uninit",
            "fps": round(s.current_fps, 1) if s else 0.0,
            "recording": c["recorder"].is_continuous(),
            "face_recognition": has_face_rec,
            "supports_count": supports_count,
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
        resp = _requests.post(url, timeout=5.0)
        result = resp.json()
    except Exception as e:
        raise HTTPException(503, f"DeepStack unreachable: {e}")
    if not result.get("success"):
        raise HTTPException(502, result.get("error", "DeepStack error"))
    return {"faces": result.get("faces", [])}


@app.post("/api/faces/register")
async def faces_register(
    name: str = Form(...),
    images: Optional[list[UploadFile]] = File(None),
    recent_filenames: Optional[str] = Form(None),
):
    import asyncio
    url = f"{_deepstack_url()}/v1/vision/face/register"
    results = []
    
    tasks_to_run = []
    
    if images and images[0].filename:
        for img_file in images:
            img_bytes = await img_file.read()
            tasks_to_run.append((img_file.filename, img_bytes, False))
            
    if recent_filenames:
        import json
        try:
            rnames = json.loads(recent_filenames)
        except:
            rnames = []
        for rname in rnames:
            # rname is expected to be "label/filename.jpg"
            p = os.path.join(RECENT_FACES_DIR, rname.replace("\\", "/"))
            if os.path.exists(p) and RECENT_FACES_DIR in os.path.abspath(p):
                with open(p, "rb") as f:
                    tasks_to_run.append((rname, f.read(), True))

    for fn, img_bytes, is_recent in tasks_to_run:
        def _post(b=img_bytes, fname=fn):
            rec_url = f"{_deepstack_url()}/v1/vision/face/recognize"
            rec_resp = _requests.post(
                rec_url,
                files={"image": (fn, b, "image/jpeg")},
                timeout=10.0
            ).json()
            
            if rec_resp.get("success"):
                faces = rec_resp.get("predictions", [])
                if len(faces) == 0:
                    return {"success": False, "message": "No faces found in image."}
                if len(faces) > 1:
                    return {"success": False, "message": f"Multiple faces ({len(faces)}) found. Please use photos with only one person."}

            return _requests.post(
                url,
                files={"image": (fname, b, "image/jpeg")},
                data={"userid": name},
                timeout=10.0,
            ).json()
        try:
            result = await asyncio.to_thread(_post)
            if result.get("success") and is_recent:
                p = os.path.join(RECENT_FACES_DIR, os.path.basename(fn))
                if os.path.exists(p):
                    try: os.remove(p)
                    except: pass
            results.append({
                "filename": fn,
                "success": result.get("success", False),
                "message": result.get("message", ""),
            })
        except Exception as e:
            results.append({"filename": fn, "success": False, "message": str(e)})
    return {"registered": name, "results": results}


@app.get("/api/faces/recent")
def list_recent_faces():
    out = []
    if os.path.exists(RECENT_FACES_DIR):
        for root, dirs, files in os.walk(RECENT_FACES_DIR):
            for f in files:
                if f.endswith(".jpg"):
                    full_path = os.path.join(root, f)
                    rel_path = os.path.relpath(full_path, RECENT_FACES_DIR).replace("\\", "/")
                    parts = f.rsplit("_", 3)
                    label = parts[0] if len(parts) >= 4 else "Unknown"
                    mtime = os.path.getmtime(full_path)
                    out.append({"filename": rel_path, "label": label, "mtime": mtime})
        out.sort(key=lambda x: x["mtime"], reverse=True)
    return {"recent": out}


@app.post("/api/faces/recent/delete")
async def delete_recent_faces(filenames: str = Form(...)):
    import json
    try:
        fnames = json.loads(filenames)
    except:
        fnames = []
        
    deleted = 0
    for fn in fnames:
        # fn is expected to be "label/filename.jpg"
        p = os.path.join(RECENT_FACES_DIR, fn.replace("\\", "/"))
        if os.path.exists(p) and RECENT_FACES_DIR in os.path.abspath(p):
            try: 
                os.remove(p)
                deleted += 1
            except: 
                pass
    return {"success": True, "deleted": deleted}


@app.get("/api/faces/recent/{label}/{filename}")
def get_recent_face(label: str, filename: str):
    path = os.path.join(RECENT_FACES_DIR, label, os.path.basename(filename))
    if not os.path.exists(path):
        raise HTTPException(404, "face not found")
    return FileResponse(path, media_type="image/jpeg")


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


@app.get("/api/count/{cam_id}")
def get_count(cam_id: str):
    if cam_id not in CAMERAS:
        raise HTTPException(404, "unknown camera")
    dets = CAMERAS[cam_id].get("last_detections", [])
    alert_classes = {c.lower() for c in CAMERAS[cam_id]["config"].get("alert_classes", [])}
    counts: Dict[str, int] = {}
    for d in dets:
        cls = d["class"].lower()
        if cls in alert_classes:
            counts[cls] = counts.get(cls, 0) + 1
    return {"cam_id": cam_id, "counts": counts, "total": sum(counts.values())}


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
