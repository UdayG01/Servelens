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

import csv
import os
import json
import re
import time
import traceback
from datetime import datetime, timedelta
from typing import Dict, Optional

import cv2
import numpy as np
import requests as _requests
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Depends
from fastapi.responses import StreamingResponse, FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from starlette.requests import Request
import uuid
import secrets

from .camera_stream import CameraStream
from .inference_engine import InferenceEngine
from .alert_manager import AlertManager
from .recorder import Recorder
from .license import load_license, LicenseInfo, LicenseStatus
from .db import init_db, get_user_count, get_user_by_username, create_user, list_users, delete_user, create_session, get_session, delete_session
from .auth import hash_password, verify_password, generate_session_token


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

class AdminAuthRequired(Exception):
    pass

@app.exception_handler(AdminAuthRequired)
async def admin_auth_exception_handler(request: Request, exc: AdminAuthRequired):
    return RedirectResponse(url="/admin/login")

ADMIN_SESSIONS = set()

def get_current_admin(request: Request):
    token = request.cookies.get("admin_session")
    if not token or token not in ADMIN_SESSIONS:
        raise AdminAuthRequired()
    return "admin"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

engine = InferenceEngine(CONFIG["models"])
alert_mgr = AlertManager(CONFIG["email"], SNAPSHOTS_DIR, ALERTS_DIR)

# License state — populated on startup before any request is served
LICENSE: LicenseInfo = LicenseInfo()

# Live/write operations that require an active (non-expired) license
_LIVE_ONLY_RE = re.compile(
    r"^(/stream/|/api/count/|/api/record/|/api/test-email$"
    r"|/api/faces/register$|/api/faces/recent/delete$)"
)
# Paths that bypass the license gate entirely (status check + static assets + admin panel)
_ALWAYS_ALLOWED_RE = re.compile(r"^(/api/license|/static/|/favicon|/login|/register|/logout|/admin/)")

@app.middleware("http")
async def _license_gate(request: Request, call_next):
    path = request.url.path

    if _ALWAYS_ALLOWED_RE.match(path):
        return await call_next(request)

    wants_html = "text/html" in request.headers.get("accept", "")

    # 1. First-run redirection: if there are 0 users, always redirect HTML requests to /register
    if get_user_count() == 0:
        if wants_html:
            if path != "/register":
                return RedirectResponse("/register")
        else:
            return JSONResponse({"detail": "setup_required", "message": "No users registered. Please register first."}, status_code=400)

    # 2. Authentication check
    session_token = request.cookies.get("session_token")
    session = get_session(session_token) if session_token else None

    if not session:
        if wants_html:
            return RedirectResponse("/login")
        return JSONResponse({"detail": "unauthorized", "message": "Please log in"}, status_code=401)

    # 3. License checks
    if LICENSE.status == LicenseStatus.INVALID:
        if wants_html:
            return HTMLResponse(
                content=f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="UTF-8">
                    <title>Servelens - License Required</title>
                    <style>
                        body {{ font-family: 'Inter', sans-serif; background: #0a0a0f; color: #ffffff; display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; }}
                        .container {{ background: #1a1a24; padding: 40px; border-radius: 12px; box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5); max-width: 500px; width: 100%; text-align: center; border: 1px solid #333; }}
                        h1 {{ color: #ef4444; margin-bottom: 20px; font-size: 1.8rem; }}
                        p {{ color: #ccc; line-height: 1.6; margin-bottom: 20px; }}
                        .contact {{ margin-top: 30px; font-size: 0.9rem; color: #888; border-top: 1px solid #333; padding-top: 20px; }}
                        a {{ color: #2563eb; text-decoration: none; font-weight: 500; }}
                        a:hover {{ text-decoration: underline; }}
                    </style>
                </head>
                <body>
                    <div class="container">
                        <h1>License Status: Invalid</h1>
                        <p>{LICENSE.message}</p>
                        <div class="contact">
                            <p>For licensing issues, upgrades, or renewals, please contact Renata IoT at <a href="mailto:support@renataiot.com">support@renataiot.com</a>.</p>
                            <p style="margin-top: 15px;">System Administrator? <a href="/admin/license">Access Admin Panel to Configure License</a></p>
                        </div>
                    </div>
                </body>
                </html>
                """,
                status_code=403
            )
        return JSONResponse({"detail": "invalid_license", "message": LICENSE.message}, status_code=403)

    if LICENSE.status == LicenseStatus.EXPIRED:
        if _LIVE_ONLY_RE.match(path) or request.method in ("POST", "PUT", "DELETE"):
            return JSONResponse({"detail": "license_expired", "message": LICENSE.message}, status_code=403)
        # Otherwise, allow read-only GET requests for historic logs, configurations, etc.

    return await call_next(request)

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
    init_db()
    global LICENSE
    LICENSE = load_license()
    tag = LICENSE.status.value.upper()
    client = LICENSE.issued_to or "N/A"
    expires = LICENSE.expiry_date or "N/A"
    print(f"[License] {tag} | client={client} | expires={expires} | {LICENSE.message or 'OK'}")

    if LICENSE.status == LicenseStatus.VALID:
        start_cameras()
    elif LICENSE.status == LicenseStatus.EXPIRED:
        print("[License] Running in read-only mode — live feeds and detections disabled.")
    else:
        print(f"[License] Access locked — {LICENSE.message}")


@app.on_event("shutdown")
def _shutdown():
    for c in CAMERAS.values():
        try: c["stream"].stop_capture()
        except Exception: pass
        try: c["recorder"].shutdown()
        except Exception: pass
    alert_mgr.stop()


# ---------------- Routes ----------------

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, error: str = None):
    return templates.TemplateResponse(request, "login.html", {"license": LICENSE.as_dict(), "error": error, "user_count": get_user_count()})

@app.post("/login")
def login_submit(username: str = Form(...), password: str = Form(...)):
    user = get_user_by_username(username)
    if not user or not verify_password(password, user["password_hash"]):
        return RedirectResponse("/login?error=Invalid credentials", status_code=303)
    
    token = generate_session_token()
    create_session(user["id"], token)
    
    response = RedirectResponse("/", status_code=303)
    response.set_cookie("session_token", token, httponly=True)
    return response

@app.get("/logout")
def logout(request: Request):
    token = request.cookies.get("session_token")
    if token:
        delete_session(token)
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie("session_token")
    return response

@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request, error: str = None):
    return templates.TemplateResponse(request, "register.html", {"license": LICENSE.as_dict(), "error": error, "user_count": get_user_count()})

@app.post("/register")
def register_submit(username: str = Form(...), password: str = Form(...)):
    if LICENSE.max_users > 0 and get_user_count() >= LICENSE.max_users:
        return RedirectResponse("/register?error=too_many_users", status_code=303)
    
    pwd_hash = hash_password(password)
    success = create_user(username, pwd_hash)
    if not success:
        return RedirectResponse("/register?error=Username already exists", status_code=303)
    
    return RedirectResponse("/login?error=Registration successful, please log in", status_code=303)

@app.get("/admin/users", response_class=HTMLResponse)
def admin_users_page(request: Request, _ = Depends(get_current_admin)):
    users = list_users()
    return templates.TemplateResponse(request, "admin_users.html", {"license": LICENSE.as_dict(), "users": users})

@app.post("/admin/users/add")
def admin_add_user(username: str = Form(...), password: str = Form(...), _ = Depends(get_current_admin)):
    if LICENSE.max_users > 0 and get_user_count() >= LICENSE.max_users:
        return RedirectResponse("/admin/users?error=max_users_reached", status_code=303)
    
    success = create_user(username, hash_password(password))
    return RedirectResponse("/admin/users", status_code=303)

@app.post("/admin/users/{user_id}/delete")
def admin_delete_user(user_id: int, _ = Depends(get_current_admin)):
    delete_user(user_id)
    return RedirectResponse("/admin/users", status_code=303)


@app.get("/admin/login", response_class=HTMLResponse)
def admin_login_page(request: Request, error: str = None):
    return templates.TemplateResponse(request, "admin_login.html", {"error": error})

@app.post("/admin/login")
def admin_login_submit(username: str = Form(...), password: str = Form(...)):
    admin_cfg = CONFIG.get("admin", {})
    correct_username = secrets.compare_digest(username, admin_cfg.get("admin_username", "admin"))
    correct_password = secrets.compare_digest(password, admin_cfg.get("admin_password", "password123"))
    
    if not (correct_username and correct_password):
        return RedirectResponse("/admin/login?error=Invalid credentials", status_code=303)
        
    token = secrets.token_urlsafe(32)
    ADMIN_SESSIONS.add(token)
    
    response = RedirectResponse("/admin/license", status_code=303)
    response.set_cookie("admin_session", token, httponly=True)
    return response

@app.get("/admin/logout")
def admin_logout(request: Request):
    token = request.cookies.get("admin_session")
    if token in ADMIN_SESSIONS:
        ADMIN_SESSIONS.remove(token)
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie("admin_session")
    return response

@app.get("/admin/license", response_class=HTMLResponse)
def admin_license_page(request: Request, _ = Depends(get_current_admin)):
    return templates.TemplateResponse(request, "admin_license.html", {"license": LICENSE.as_dict()})

@app.post("/admin/license")
def admin_license_generate(
    client_id: str = Form(...),
    issued_to: str = Form(...),
    expiry: str = Form(...),
    max_users: int = Form(0),
    _ = Depends(get_current_admin)
):
    from tools.generate_license import generate_license
    output_path = os.path.join(BASE_DIR, "config", "license.json")
    try:
        generate_license(client_id, issued_to, expiry, max_users, output_path)
        global LICENSE
        LICENSE = load_license()
        if LICENSE.status == LicenseStatus.VALID and len(CAMERAS) == 0:
            start_cameras()
        return RedirectResponse("/admin/license", status_code=303)
    except Exception as e:
        raise HTTPException(500, f"Error generating license: {e}")

@app.get("/api/license/status")
def license_status():
    return LICENSE.as_dict()


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {"license": LICENSE.as_dict()})

@app.get("/faces", response_class=HTMLResponse)
def faces_page(request: Request):
    return templates.TemplateResponse(request, "faces.html", {"license": LICENSE.as_dict()})


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


@app.get("/camera/{cam_id}", response_class=HTMLResponse)
def camera_detail_page(cam_id: str, request: Request):
    if cam_id not in CAMERAS:
        raise HTTPException(404, "unknown camera")
    cam_cfg = CAMERAS[cam_id]["config"]
    return templates.TemplateResponse(request, "camera_detail.html", {
        "cam_id": cam_id,
        "cam_name": cam_cfg["name"],
        "license": LICENSE.as_dict(),
    })


@app.get("/api/recordings/{cam_id}")
def get_recordings(cam_id: str):
    if cam_id not in CAMERAS:
        raise HTTPException(404, "unknown camera")
    cam_name = CAMERAS[cam_id]["config"]["name"]
    safe_name = "".join(c if c.isalnum() else "_" for c in cam_name)

    results = []
    if os.path.isdir(RECORDINGS_DIR):
        for fname in sorted(os.listdir(RECORDINGS_DIR)):
            if not fname.endswith(".mp4"):
                continue
            if not fname.startswith(safe_name + "_"):
                continue
            fpath = os.path.join(RECORDINGS_DIR, fname)
            # filename: {safe_name}_{YYYYMMDD}_{HHMMSS}_{suffix}.mp4
            rest = fname[len(safe_name) + 1:-4]
            parts = rest.split("_")
            start_iso = None
            rec_type = "unknown"
            if len(parts) >= 3:
                try:
                    start_dt = datetime.strptime(f"{parts[0]}_{parts[1]}", "%Y%m%d_%H%M%S")
                    start_iso = start_dt.isoformat()
                    rec_type = "_".join(parts[2:])
                except ValueError:
                    pass
            duration = 0.0
            try:
                cap = cv2.VideoCapture(fpath)
                cap_fps = cap.get(cv2.CAP_PROP_FPS) or 15
                frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                duration = round(frame_count / cap_fps, 2) if cap_fps > 0 else 0.0
                cap.release()
            except Exception:
                pass
            results.append({
                "filename": fname,
                "start_time": start_iso,
                "duration": duration,
                "type": rec_type,
                "size_mb": round(os.path.getsize(fpath) / (1024 * 1024), 2),
            })
    return {"recordings": results, "cam_id": cam_id}


@app.get("/recordings/{filename}")
async def serve_recording(filename: str, request: Request):
    path = os.path.join(RECORDINGS_DIR, os.path.basename(filename))
    if not os.path.exists(path):
        raise HTTPException(404, "recording not found")
    file_size = os.path.getsize(path)
    range_hdr = request.headers.get("range", "")
    m = re.match(r"bytes=(\d+)-(\d*)", range_hdr)
    if m:
        start = int(m.group(1))
        end = int(m.group(2)) if m.group(2) else file_size - 1
        end = min(end, file_size - 1)
        chunk = end - start + 1

        def _iter():
            with open(path, "rb") as f:
                f.seek(start)
                remaining = chunk
                while remaining > 0:
                    data = f.read(min(65536, remaining))
                    if not data:
                        break
                    remaining -= len(data)
                    yield data

        headers = {
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(chunk),
        }
        return StreamingResponse(_iter(), status_code=206, headers=headers, media_type="video/mp4")
    return FileResponse(path, media_type="video/mp4", headers={"Accept-Ranges": "bytes"})


@app.get("/api/events/{cam_id}")
def get_camera_events(cam_id: str, limit: int = 500):
    if cam_id not in CAMERAS:
        raise HTTPException(404, "unknown camera")
    events: dict = {}
    csv_path = os.path.join(ALERTS_DIR, "alerts.csv")
    if os.path.exists(csv_path):
        try:
            with open(csv_path, "r", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    if row.get("camera_id") == cam_id:
                        ts = row["timestamp"]
                        events[ts] = {
                            "timestamp": ts,
                            "classes": row.get("classes", ""),
                            "plates": [p.strip() for p in row.get("plates", "").split(",") if p.strip()],
                            "names": [],
                            "snapshot": os.path.basename(row.get("snapshot_path", "")),
                        }
        except Exception as e:
            print(f"[Events] CSV read error: {e}")
    for a in alert_mgr.get_recent(200):
        if a["cam_id"] == cam_id:
            events[a["timestamp"]] = {
                "timestamp": a["timestamp"],
                "classes": a["classes"],
                "plates": a["plates"],
                "names": a.get("names", []),
                "snapshot": a["snapshot"],
            }
    sorted_evts = sorted(events.values(), key=lambda x: x["timestamp"], reverse=True)
    return {"events": sorted_evts[:limit], "cam_id": cam_id}


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


@app.get("/analytics", response_class=HTMLResponse)
def analytics_page(request: Request):
    return templates.TemplateResponse(request, "analytics.html", {"license": LICENSE.as_dict()})


@app.get("/api/analytics")
def get_analytics(days: int = 7):
    from collections import defaultdict

    days = max(1, min(days, 365))
    now = datetime.now()
    cutoff = now - timedelta(days=days)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    csv_path = os.path.join(ALERTS_DIR, "alerts.csv")
    all_events = []
    seen_keys: set = set()

    if os.path.exists(csv_path):
        try:
            with open(csv_path, "r", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    try:
                        ts = datetime.fromisoformat(row["timestamp"])
                        if ts < cutoff:
                            continue
                        key = (row["timestamp"], row.get("camera_id", ""))
                        if key in seen_keys:
                            continue
                        seen_keys.add(key)
                        classes = [c.strip() for c in row.get("classes", "").split(",") if c.strip()]
                        plates = [p.strip() for p in row.get("plates", "").split(",") if p.strip()]
                        all_events.append({
                            "ts": ts,
                            "cam_id": row.get("camera_id", ""),
                            "cam_name": row.get("camera_name", ""),
                            "classes": classes,
                            "plates": plates,
                            "snapshot": os.path.basename(row.get("snapshot_path", "")),
                        })
                    except Exception:
                        pass
        except Exception as e:
            print(f"[Analytics] CSV read error: {e}")

    for a in alert_mgr.get_recent(200):
        try:
            key = (a["timestamp"], a["cam_id"])
            if key in seen_keys:
                continue
            ts = datetime.fromisoformat(a["timestamp"])
            if ts < cutoff:
                continue
            seen_keys.add(key)
            classes = [c.strip() for c in a["classes"].split(",") if c.strip()]
            all_events.append({
                "ts": ts,
                "cam_id": a["cam_id"],
                "cam_name": a["cam_name"],
                "classes": classes,
                "plates": a.get("plates", []),
                "snapshot": a.get("snapshot", ""),
            })
        except Exception:
            pass

    all_events.sort(key=lambda x: x["ts"])
    today_events = [e for e in all_events if e["ts"] >= today_start]

    cam_name_map = {cam_id: c["config"]["name"] for cam_id, c in CAMERAS.items()}
    for cam_cfg in CONFIG.get("cameras", []):
        cam_name_map.setdefault(cam_cfg["id"], cam_cfg["name"])

    cam_counts: dict = defaultdict(int)
    class_counts: dict = defaultdict(int)
    plate_tracker: dict = defaultdict(lambda: {"count": 0, "last_seen": None})

    for e in all_events:
        cam_counts[e["cam_id"]] += 1
        for cls in e["classes"]:
            class_counts[cls.lower()] += 1
        for p in e["plates"]:
            plate_tracker[p]["count"] += 1
            if plate_tracker[p]["last_seen"] is None or e["ts"] > plate_tracker[p]["last_seen"]:
                plate_tracker[p]["last_seen"] = e["ts"]

    most_active = max(cam_counts.items(), key=lambda x: x[1]) if cam_counts else None
    top_cls = max(class_counts.items(), key=lambda x: x[1]) if class_counts else None

    summary = {
        "total_events": len(all_events),
        "events_today": len(today_events),
        "cameras_active": len(cam_counts),
        "most_active_camera": {
            "id": most_active[0],
            "name": cam_name_map.get(most_active[0], most_active[0]),
            "count": most_active[1],
        } if most_active else None,
        "top_detection_class": {"class": top_cls[0], "count": top_cls[1]} if top_cls else None,
        "unique_plates": len(plate_tracker),
        "fire_smoke_alerts": class_counts.get("fire", 0) + class_counts.get("smoke", 0),
        "person_detections": class_counts.get("person", 0),
        "face_detections": class_counts.get("face", 0),
        "plate_reads": class_counts.get("license_plate", 0),
    }

    by_hour = [0] * 24
    for e in all_events:
        by_hour[e["ts"].hour] += 1
    events_by_hour = [{"hour": h, "count": by_hour[h]} for h in range(24)]

    by_day: dict = defaultdict(int)
    for e in all_events:
        by_day[e["ts"].strftime("%Y-%m-%d")] += 1
    events_by_day = [
        {"date": (cutoff + timedelta(days=i + 1)).strftime("%Y-%m-%d"),
         "count": by_day.get((cutoff + timedelta(days=i + 1)).strftime("%Y-%m-%d"), 0)}
        for i in range(days)
    ]

    events_by_camera = sorted(
        [{"cam_id": cid, "cam_name": cam_name_map.get(cid, cid), "count": cnt}
         for cid, cnt in cam_counts.items()],
        key=lambda x: -x["count"],
    )

    events_by_class = sorted(
        [{"class": cls, "count": cnt} for cls, cnt in class_counts.items()],
        key=lambda x: -x["count"],
    )

    heatmap = [[0] * 24 for _ in range(7)]
    for e in all_events:
        heatmap[e["ts"].weekday()][e["ts"].hour] += 1
    heatmap_max = max((max(row) for row in heatmap if row), default=1) or 1

    top_plates = sorted(
        [{"plate": p, "count": v["count"],
          "last_seen": v["last_seen"].isoformat() if v["last_seen"] else None}
         for p, v in plate_tracker.items()],
        key=lambda x: -x["count"],
    )[:15]

    recent_events = [
        {
            "timestamp": e["ts"].isoformat(),
            "cam_id": e["cam_id"],
            "cam_name": cam_name_map.get(e["cam_id"], e["cam_id"]),
            "classes": ", ".join(e["classes"]),
            "plates": e["plates"],
            "snapshot": e["snapshot"],
        }
        for e in reversed(all_events[-50:])
    ]

    return {
        "period_days": days,
        "summary": summary,
        "events_by_hour": events_by_hour,
        "events_by_day": events_by_day,
        "events_by_camera": events_by_camera,
        "events_by_class": events_by_class,
        "heatmap": {"data": heatmap, "max": heatmap_max},
        "top_plates": top_plates,
        "recent_events": recent_events,
    }


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
