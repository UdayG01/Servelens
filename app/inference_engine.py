"""
Loads detection backends once. Dispatches to YOLO or ANPR per model type.
"""

import threading
from typing import Dict, List, Tuple

import cv2
import numpy as np

from .anpr import ANPRDetector
from .face_recognizer import FaceRecognizer


class InferenceEngine:
    def __init__(self, models_config: dict):
        self.models_config = models_config
        self._models: Dict[str, object] = {}
        self._locks: Dict[str, threading.Lock] = {}
        self._load_lock = threading.Lock()

    def _get(self, name: str):
        if name in self._models:
            return self._models[name]
        with self._load_lock:
            if name in self._models:
                return self._models[name]
            cfg = self.models_config[name]
            mtype = cfg.get("type", "yolo")
            if mtype == "yolo":
                from ultralytics import YOLO
                model = YOLO(cfg["weights"])
            elif mtype == "anpr":
                model = ANPRDetector(
                    weights_path=cfg["weights"],
                    device=cfg.get("device", "cpu"),
                    img_size=cfg.get("img_size", 640),
                    ocr_languages=cfg.get("ocr_languages", ["en"]),
                    ocr_min_confidence=cfg.get("ocr_min_confidence", 0.3),
                )
            elif mtype == "deepstack_face":
                model = FaceRecognizer(
                    deepstack_url=cfg.get("deepstack_url", "http://localhost:80"),
                )
            else:
                raise ValueError(f"Unknown model type: {mtype}")
            self._models[name] = model
            self._locks[name] = threading.Lock()
            return model

    def infer(self, frame, model_names, alert_classes, min_confidence) -> Tuple[np.ndarray, List[dict]]:
        annotated = frame.copy()
        all_dets: List[dict] = []
        alert_set = {c.lower() for c in alert_classes} if alert_classes else None

        for name in model_names:
            try:
                model = self._get(name)
            except Exception as e:
                cv2.putText(annotated, f"Model load error ({name}): {e}",
                            (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
                continue

            cfg = self.models_config[name]
            mtype = cfg.get("type", "yolo")

            if mtype in ("anpr", "deepstack_face"):
                with self._locks[name]:
                    annotated, dets = model.infer(annotated, min_confidence)
                all_dets.extend(dets)
                continue

            with self._locks[name]:
                results = model.predict(
                    source=frame, imgsz=cfg.get("img_size", 640),
                    device=cfg.get("device", "cpu"),
                    conf=min_confidence, verbose=False,
                )
            if not results:
                continue
            r = results[0]
            names = r.names
            if r.boxes is None:
                continue
            for box in r.boxes:
                conf = float(box.conf[0]) if box.conf is not None else 0.0
                cls_id = int(box.cls[0]) if box.cls is not None else -1
                cls_name = (names.get(cls_id, str(cls_id))
                            if isinstance(names, dict) else names[cls_id])
                if conf < min_confidence:
                    continue
                xy = box.xyxy[0].cpu().numpy().astype(int)
                x1, y1, x2, y2 = int(xy[0]), int(xy[1]), int(xy[2]), int(xy[3])
                if alert_set and cls_name.lower() not in alert_set:
                    cv2.rectangle(annotated, (x1, y1), (x2, y2), (160, 160, 160), 1)
                    continue
                all_dets.append({
                    "model": name, "class": cls_name,
                    "confidence": conf, "bbox": [x1, y1, x2, y2],
                })
                cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 0, 255), 2)
                label = f"{cls_name} {conf:.2f}"
                (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                cv2.rectangle(annotated, (x1, y1-th-6), (x1+tw+4, y1), (0, 0, 255), -1)
                cv2.putText(annotated, label, (x1+2, y1-4),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        return annotated, all_dets
