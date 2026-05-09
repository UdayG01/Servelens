"""
Alert manager: cooldown logic, snapshot save, CSV log, background Gmail SMTP.
"""

import os
import csv
import time
import smtplib
import threading
from datetime import datetime
from email.message import EmailMessage
from queue import Queue, Empty
from typing import List

import cv2


class AlertManager:
    def __init__(self, email_config: dict, snapshot_dir: str, alerts_dir: str):
        self.email_config = email_config
        self.snapshot_dir = snapshot_dir
        self.alerts_dir = alerts_dir
        os.makedirs(snapshot_dir, exist_ok=True)
        os.makedirs(alerts_dir, exist_ok=True)

        self._last_alert_ts = {}
        self._cooldowns = {}
        self._lock = threading.Lock()

        self._email_queue: Queue = Queue()
        self._stop = threading.Event()
        self._email_thread = threading.Thread(target=self._email_loop, daemon=True)
        self._email_thread.start()

        self._csv_path = os.path.join(self.alerts_dir, "alerts.csv")
        if not os.path.exists(self._csv_path):
            with open(self._csv_path, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(
                    ["timestamp", "camera_id", "camera_name", "classes", "plates", "snapshot_path"]
                )

        # Recent alerts in memory for the UI
        self._recent: List[dict] = []
        self._recent_lock = threading.Lock()

    def configure_cooldown(self, cam_id: str, seconds: int):
        self._cooldowns[cam_id] = seconds

    def should_alert(self, cam_id: str) -> bool:
        cooldown = self._cooldowns.get(cam_id, 60)
        with self._lock:
            last = self._last_alert_ts.get(cam_id, 0)
            now = time.time()
            if now - last >= cooldown:
                self._last_alert_ts[cam_id] = now
                return True
            return False

    def trigger_alert(self, cam_id, cam_name, annotated_frame, detections) -> str:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{cam_id}_{ts}.jpg"
        snapshot_path = os.path.join(self.snapshot_dir, filename)
        try:
            cv2.imwrite(snapshot_path, annotated_frame)
        except Exception as e:
            print(f"[Alert] snapshot save failed: {e}")
            snapshot_path = ""

        classes = ", ".join(sorted({d["class"] for d in detections}))
        plates = sorted({d["plate_text"] for d in detections if d.get("plate_text")})
        plates_str = ", ".join(plates)
        face_names = sorted({
            d["name"] for d in detections
            if d.get("name") and d["name"].lower() not in ("unknown", "")
        })

        try:
            with open(self._csv_path, "a", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow([
                    datetime.now().isoformat(timespec="seconds"),
                    cam_id, cam_name, classes, plates_str, snapshot_path,
                ])
        except Exception as e:
            print(f"[Alert] csv log failed: {e}")

        record = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "cam_id": cam_id,
            "cam_name": cam_name,
            "classes": classes,
            "plates": plates,
            "names": face_names,
            "snapshot": os.path.basename(snapshot_path) if snapshot_path else "",
        }
        with self._recent_lock:
            self._recent.insert(0, record)
            self._recent = self._recent[:200]

        if self.email_config.get("enabled", False):
            self._email_queue.put({
                "cam_id": cam_id, "cam_name": cam_name, "classes": classes,
                "plates": plates, "snapshot_path": snapshot_path,
                "detections": detections,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })

        return snapshot_path

    def get_recent(self, limit: int = 50) -> List[dict]:
        with self._recent_lock:
            return list(self._recent[:limit])

    def _email_loop(self):
        while not self._stop.is_set():
            try:
                payload = self._email_queue.get(timeout=0.5)
            except Empty:
                continue
            try:
                self._send_email(payload)
            except Exception as e:
                print(f"[Alert] email send failed: {e}")

    def _send_email(self, payload: dict):
        cfg = self.email_config
        msg = EmailMessage()
        plate_suffix = f" PLATE: {', '.join(payload['plates'])}" if payload["plates"] else ""
        msg["Subject"] = (
            f"{cfg.get('subject_prefix', '[ALERT]')} {payload['cam_name']} - {payload['classes']}{plate_suffix}"
        )
        msg["From"] = cfg["sender_email"]
        msg["To"] = ", ".join(cfg["recipients"])

        body = [
            f"Camera: {payload['cam_name']} ({payload['cam_id']})",
            f"Time: {payload['timestamp']}",
            f"Detected: {payload['classes']}",
        ]
        if payload["plates"]:
            body.append(f"Plate(s): {', '.join(payload['plates'])}")
        body += ["", "Detections:"]
        for d in payload["detections"]:
            line = f"  - {d['class']} (conf={d['confidence']:.2f}) by {d['model']}"
            if d.get("plate_text"):
                line += f"  -> PLATE: {d['plate_text']}"
            body.append(line)
        msg.set_content("\n".join(body))

        snap = payload["snapshot_path"]
        if snap and os.path.exists(snap):
            with open(snap, "rb") as f:
                msg.add_attachment(f.read(), maintype="image", subtype="jpeg",
                                   filename=os.path.basename(snap))

        with smtplib.SMTP(cfg["smtp_server"], cfg["smtp_port"], timeout=20) as smtp:
            smtp.ehlo(); smtp.starttls()
            smtp.login(cfg["sender_email"], cfg["sender_app_password"])
            smtp.send_message(msg)

    def send_test_email(self):
        cfg = self.email_config
        msg = EmailMessage()
        msg["Subject"] = f"{cfg.get('subject_prefix', '[ALERT]')} Test"
        msg["From"] = cfg["sender_email"]
        msg["To"] = ", ".join(cfg["recipients"])
        msg.set_content("Test email from CCTV Intelligence web app.")
        with smtplib.SMTP(cfg["smtp_server"], cfg["smtp_port"], timeout=15) as smtp:
            smtp.ehlo(); smtp.starttls()
            smtp.login(cfg["sender_email"], cfg["sender_app_password"])
            smtp.send_message(msg)

    def stop(self):
        self._stop.set()
