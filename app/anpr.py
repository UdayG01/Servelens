"""
ANPR: YOLO plate detector + EasyOCR text reader.
"""

import re
import threading
import cv2
import numpy as np


_PLATE_CLEAN_RE = re.compile(r"[^A-Z0-9]")


def _clean(raw: str) -> str:
    return _PLATE_CLEAN_RE.sub("", (raw or "").upper())


class ANPRDetector:
    def __init__(self, weights_path, device="cpu", img_size=640,
                 ocr_languages=None, ocr_min_confidence=0.3):
        self.weights_path = weights_path
        self.device = device
        self.img_size = img_size
        self.ocr_languages = ocr_languages or ["en"]
        self.ocr_min_confidence = ocr_min_confidence
        self._yolo = None
        self._reader = None
        self._lock = threading.Lock()
        self._load_lock = threading.Lock()

    def _ensure_loaded(self):
        if self._yolo is not None and self._reader is not None:
            return
        with self._load_lock:
            if self._yolo is None:
                from ultralytics import YOLO
                self._yolo = YOLO(self.weights_path)
            if self._reader is None:
                import easyocr
                self._reader = easyocr.Reader(
                    self.ocr_languages,
                    gpu=(self.device != "cpu"),
                    verbose=False,
                )

    def _read_text(self, crop):
        if crop.size == 0:
            return ""
        h, w = crop.shape[:2]
        if h < 30 or w < 60:
            scale = max(2.0, 60 / max(w, 1))
            crop = cv2.resize(crop, (int(w * scale), int(h * scale)),
                              interpolation=cv2.INTER_CUBIC)
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
        gray = cv2.bilateralFilter(gray, 7, 50, 50)
        try:
            results = self._reader.readtext(gray, detail=1, paragraph=False)
        except Exception:
            return ""
        best, best_score = "", 0.0
        for _, text, conf in results:
            if conf < self.ocr_min_confidence:
                continue
            cleaned = _clean(text)
            if len(cleaned) < 4:
                continue
            score = len(cleaned) * conf
            if score > best_score:
                best, best_score = cleaned, score
        return best

    def infer(self, frame, min_confidence):
        self._ensure_loaded()
        annotated = frame.copy()
        detections = []
        with self._lock:
            results = self._yolo.predict(
                source=frame, imgsz=self.img_size, device=self.device,
                conf=min_confidence, verbose=False,
            )
        if not results:
            return annotated, detections
        r = results[0]
        if r.boxes is None:
            return annotated, detections
        H, W = frame.shape[:2]
        for box in r.boxes:
            conf = float(box.conf[0]) if box.conf is not None else 0.0
            if conf < min_confidence:
                continue
            xy = box.xyxy[0].cpu().numpy().astype(int)
            x1 = max(0, int(xy[0])); y1 = max(0, int(xy[1]))
            x2 = min(W, int(xy[2])); y2 = min(H, int(xy[3]))
            if x2 <= x1 or y2 <= y1:
                continue
            pad_x = int((x2 - x1) * 0.05)
            pad_y = int((y2 - y1) * 0.10)
            crop = frame[max(0, y1-pad_y):min(H, y2+pad_y),
                         max(0, x1-pad_x):min(W, x2+pad_x)]
            text = self._read_text(crop)
            detections.append({
                "model": "anpr", "class": "license_plate",
                "confidence": conf, "bbox": [x1, y1, x2, y2],
                "plate_text": text,
            })
            cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 255), 2)
            label = text if text else f"plate {conf:.2f}"
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            cv2.rectangle(annotated, (x1, y1-th-8), (x1+tw+6, y1), (0, 255, 255), -1)
            cv2.putText(annotated, label, (x1+3, y1-5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
        return annotated, detections
