"""
Recorder: continuous and event-triggered MP4 recording per camera.
"""

import os
import time
import threading
from datetime import datetime
from typing import Optional

import cv2


class Recorder:
    def __init__(self, cam_id, cam_name, recordings_dir, fps=15, fourcc="mp4v"):
        self.cam_id = cam_id
        self.cam_name = cam_name
        self.recordings_dir = recordings_dir
        self.fps = fps
        self.fourcc = fourcc
        os.makedirs(recordings_dir, exist_ok=True)

        self._writer: Optional[cv2.VideoWriter] = None
        self._continuous = False
        self._continuous_path: Optional[str] = None

        self._event_active = False
        self._event_until = 0.0
        self._event_path: Optional[str] = None
        self._event_writer: Optional[cv2.VideoWriter] = None

        self._lock = threading.Lock()

    def _filename(self, suffix: str) -> str:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe = "".join(c if c.isalnum() else "_" for c in self.cam_name)
        return os.path.join(self.recordings_dir, f"{safe}_{ts}_{suffix}.mp4")

    def _make_writer(self, path, frame_shape):
        h, w = frame_shape[:2]
        fourcc = cv2.VideoWriter_fourcc(*self.fourcc)
        writer = cv2.VideoWriter(path, fourcc, self.fps, (w, h))
        return writer if writer.isOpened() else None

    def start_continuous(self, sample_frame) -> Optional[str]:
        with self._lock:
            if self._continuous:
                return self._continuous_path
            path = self._filename("continuous")
            w = self._make_writer(path, sample_frame.shape)
            if w is None:
                return None
            self._writer = w
            self._continuous_path = path
            self._continuous = True
            return path

    def stop_continuous(self) -> Optional[str]:
        with self._lock:
            path = self._continuous_path
            if self._writer is not None:
                try:
                    self._writer.release()
                except Exception:
                    pass
            self._writer = None
            self._continuous = False
            self._continuous_path = None
            return path

    def is_continuous(self) -> bool:
        return self._continuous

    def trigger_event(self, sample_frame, duration_sec: int) -> Optional[str]:
        with self._lock:
            if self._event_active:
                self._event_until = max(self._event_until, time.time() + duration_sec)
                return self._event_path
            path = self._filename("event")
            w = self._make_writer(path, sample_frame.shape)
            if w is None:
                return None
            self._event_writer = w
            self._event_path = path
            self._event_active = True
            self._event_until = time.time() + duration_sec
            return path

    def write(self, frame):
        with self._lock:
            if self._writer is not None:
                try: self._writer.write(frame)
                except Exception: pass
            if self._event_active and self._event_writer is not None:
                try: self._event_writer.write(frame)
                except Exception: pass
                if time.time() >= self._event_until:
                    try: self._event_writer.release()
                    except Exception: pass
                    self._event_writer = None
                    self._event_active = False
                    self._event_path = None

    def shutdown(self):
        with self._lock:
            for w in (self._writer, self._event_writer):
                try:
                    if w is not None: w.release()
                except Exception:
                    pass
            self._writer = None
            self._event_writer = None
