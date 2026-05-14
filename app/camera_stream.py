"""
Threaded source capture. Supports:
- RTSP URLs
- Local video files (loops, throttled to source FPS)
- Webcam indices

Each camera runs in a daemon thread, keeps the latest annotated frame
in memory for the streaming endpoint to fetch.
"""

import os
import time
import threading
from typing import Optional, Callable, Tuple

import cv2
import numpy as np


VIDEO_EXTS = (".mp4", ".avi", ".mov", ".mkv", ".webm", ".m4v", ".wmv", ".flv")


def _classify(src) -> str:
    if isinstance(src, int):
        return "webcam"
    s = str(src).strip()
    if s.isdigit():
        return "webcam"
    low = s.lower()
    if low.endswith(VIDEO_EXTS) or os.path.isfile(s):
        return "file"
    return "rtsp"


class CameraStream(threading.Thread):
    """One per camera. Reads frames, runs the on_frame callback, stores latest jpeg."""

    def __init__(
        self,
        cam_id: str,
        name: str,
        source: str,
        on_frame: Callable[[str, np.ndarray], np.ndarray],
        jpeg_quality: int = 70,
        resize_to: Optional[Tuple[int, int]] = None,
    ):
        super().__init__(daemon=True, name=f"cam-{cam_id}")
        self.cam_id = cam_id
        self.name = name
        self.source = source
        self.kind = _classify(source)
        self.on_frame = on_frame
        self.jpeg_quality = jpeg_quality
        # (width, height) — applied to every frame before inference and MJPEG encoding
        self._resize_to = resize_to

        self._running = False
        self._cap = None
        self._latest_jpeg: Optional[bytes] = None
        self._latest_ts: float = 0.0
        self._frame_count = 0
        self._fps_window_start = time.time()
        self._fps_window_frames = 0
        self.current_fps = 0.0
        self.status = "idle"
        self._lock = threading.Lock()

    def start_capture(self):
        self._running = True
        self.start()

    def stop_capture(self):
        self._running = False
        try:
            if self._cap is not None:
                self._cap.release()
        except Exception:
            pass

    def run(self):
        backoff = 1
        while self._running:
            try:
                self.status = f"connecting to {self.name}"
                if self.kind == "webcam":
                    self._cap = cv2.VideoCapture(int(str(self.source).strip()))
                else:
                    self._cap = cv2.VideoCapture(self.source, cv2.CAP_FFMPEG)
                if self.kind == "rtsp":
                    self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                if not self._cap.isOpened():
                    raise RuntimeError("cannot open source")

                fps = self._cap.get(cv2.CAP_PROP_FPS) or 0.0
                frame_delay = (1.0 / fps) if (self.kind == "file" and fps > 1.0) else 0.0

                self.status = "live"
                backoff = 1

                while self._running:
                    t0 = time.time()
                    ret, frame = self._cap.read()
                    if not ret or frame is None:
                        if self.kind == "file":
                            self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                            continue
                        raise RuntimeError("read failed")

                    self._frame_count += 1
                    self._fps_window_frames += 1

                    if self._resize_to:
                        frame = cv2.resize(frame, self._resize_to,
                                           interpolation=cv2.INTER_LINEAR)

                    # callback returns annotated frame (or original if no inference this tick)
                    annotated = self.on_frame(self.cam_id, frame)
                    if annotated is None:
                        annotated = frame

                    # Encode latest annotated frame as JPEG for streaming
                    ok, buf = cv2.imencode(
                        ".jpg", annotated,
                        [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality],
                    )
                    if ok:
                        with self._lock:
                            self._latest_jpeg = buf.tobytes()
                            self._latest_ts = time.time()

                    # FPS window
                    elapsed = time.time() - self._fps_window_start
                    if elapsed >= 1.0:
                        self.current_fps = self._fps_window_frames / elapsed
                        self._fps_window_frames = 0
                        self._fps_window_start = time.time()

                    if frame_delay > 0:
                        sleep_for = frame_delay - (time.time() - t0)
                        if sleep_for > 0:
                            time.sleep(sleep_for)

            except Exception as e:
                self.status = f"disconnected: {e}"
                try:
                    if self._cap is not None:
                        self._cap.release()
                except Exception:
                    pass
                self._cap = None
                for _ in range(backoff * 10):
                    if not self._running:
                        break
                    time.sleep(0.1)
                backoff = min(backoff * 2, 30)

    def get_latest_jpeg(self) -> Optional[bytes]:
        with self._lock:
            return self._latest_jpeg

    @property
    def frame_count(self) -> int:
        return self._frame_count
