"""
Generic DeepStack custom model detector.
Uses POST /v1/vision/custom/{model_name} endpoint.

Setup:
  1. Place your .pt model file in ./deepstack_models/
  2. Restart DeepStack  (docker compose restart deepstack)
  3. Set model_name in config to the filename without .pt

Fire/smoke model (fireNET):
  Download fire-detection.pt from the DeepStack open model zoo and place it
  in ./deepstack_models/fire-detection.pt

Response format from DeepStack custom endpoint:
  {"success": true, "predictions": [{"label": "fire", "confidence": 0.87,
                                      "y_min": 10, "x_min": 20,
                                      "y_max": 100, "x_max": 120}]}
"""

import cv2
import requests

_CLASS_COLORS = {
    "fire":  (0, 100, 255),    # orange-red  (BGR)
    "smoke": (180, 180, 180),  # light grey
    "flame": (0, 69, 255),     # deep orange
}
_DEFAULT_COLOR = (0, 0, 255)


class DeepStackDetector:
    def __init__(self, deepstack_url: str, model_name: str):
        self.deepstack_url = deepstack_url.rstrip("/")
        self.model_name = model_name
        self._url = f"{self.deepstack_url}/v1/vision/custom/{model_name}"

    def infer(self, frame, min_confidence):
        annotated = frame.copy()
        detections = []

        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        img_bytes = buf.tobytes()

        try:
            resp = requests.post(
                self._url,
                files={"image": ("frame.jpg", img_bytes, "image/jpeg")},
                data={"min_confidence": min_confidence},
                timeout=2.0,
            )
            result = resp.json()
        except Exception as e:
            cv2.putText(annotated, f"DeepStack ({self.model_name}): {e}",
                        (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.5, _DEFAULT_COLOR, 1)
            return annotated, detections

        if not result.get("success"):
            msg = result.get("error", "unknown error")
            cv2.putText(annotated, f"DeepStack ({self.model_name}): {msg}",
                        (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.5, _DEFAULT_COLOR, 1)
            return annotated, detections

        for pred in result.get("predictions", []):
            label = (pred.get("label") or "unknown").strip().lower()
            conf = float(pred.get("confidence") or 0.0)
            x1, y1 = int(pred.get("x_min", 0)), int(pred.get("y_min", 0))
            x2, y2 = int(pred.get("x_max", 0)), int(pred.get("y_max", 0))

            color = _CLASS_COLORS.get(label, _DEFAULT_COLOR)
            display = f"{label} {conf:.2f}"

            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
            (tw, th), _ = cv2.getTextSize(display, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
            cv2.rectangle(annotated, (x1, y1 - th - 6), (x1 + tw + 4, y1), color, -1)
            cv2.putText(annotated, display, (x1 + 2, y1 - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)

            detections.append({
                "model": f"deepstack/{self.model_name}",
                "class": label,
                "confidence": conf,
                "bbox": [x1, y1, x2, y2],
            })

        return annotated, detections
