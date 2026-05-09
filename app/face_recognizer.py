"""
DeepStack face recognition detector.

Sends frames to a running DeepStack instance via HTTP.
DeepStack setup (Docker):
  docker run -e VISION-FACE=True -v localstorage:/datastore -p 80:5000 deepquestai/deepstack

Training new faces:
  Use POST /api/faces/register (handled in server.py) — each image uploaded for a
  named person adds a training sample to DeepStack's persistent face database.
  More images per person = better recognition accuracy.
"""

import cv2
import requests

_GREEN = (0, 200, 0)   # known face
_RED   = (0, 0, 255)   # unknown face


class FaceRecognizer:
    def __init__(self, deepstack_url: str = "http://localhost:80"):
        self.deepstack_url = deepstack_url.rstrip("/")
        self._url = f"{self.deepstack_url}/v1/vision/face/recognize"

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
            cv2.putText(annotated, f"DeepStack: {e}",
                        (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.5, _RED, 1)
            return annotated, detections

        if not result.get("success"):
            msg = result.get("error", "unknown error")
            cv2.putText(annotated, f"DeepStack: {msg}",
                        (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.5, _RED, 1)
            return annotated, detections

        for pred in result.get("predictions", []):
            name = (pred.get("userid") or "unknown").strip()
            conf = float(pred.get("confidence") or 0.0)
            x1, y1 = int(pred.get("x_min", 0)), int(pred.get("y_min", 0))
            x2, y2 = int(pred.get("x_max", 0)), int(pred.get("y_max", 0))

            is_known = name.lower() not in ("unknown", "")
            color = _GREEN if is_known else _RED
            label = f"{name} {conf:.2f}" if is_known else "Unknown"

            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
            cv2.rectangle(annotated, (x1, y1 - th - 6), (x1 + tw + 4, y1), color, -1)
            cv2.putText(annotated, label, (x1 + 2, y1 - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)

            detections.append({
                "model": "face_recognizer",
                "class": "face",
                "name": name if is_known else "Unknown",
                "confidence": conf,
                "bbox": [x1, y1, x2, y2],
            })

        return annotated, detections