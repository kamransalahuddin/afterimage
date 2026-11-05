"""Local face detection.

Primary: OpenCV's YuNet CNN detector (ONNX, ~230 KB, bundled in
`detection/models`). Fallback: OpenCV's Haar cascades, which ship with the
opencv package. Nothing leaves the machine.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from app.detection.types import Box

log = logging.getLogger("afterimage.detection")

YUNET_PATH = Path(__file__).parent / "models" / "face_detection_yunet_2023mar.onnx"
_MAX_SIDE = 1600
_lock = threading.Lock()


def backend_name() -> str:
    return "yunet" if YUNET_PATH.exists() and hasattr(cv2, "FaceDetectorYN") else "haar"


def _expand(box: Box, w: int, h: int, pad: float = 0.18) -> Box:
    dw, dh = (box.x1 - box.x0) * pad, (box.y1 - box.y0) * pad
    return Box(max(0, box.x0 - dw), max(0, box.y0 - dh * 1.3), min(w, box.x1 + dw), min(h, box.y1 + dh))


def detect_faces(img: Image.Image, *, threshold: float = 0.75) -> list[tuple[Box, float]]:
    rgb = np.asarray(img.convert("RGB"))
    h, w = rgb.shape[:2]
    scale = min(1.0, _MAX_SIDE / max(w, h))
    small = cv2.resize(rgb, (round(w * scale), round(h * scale))) if scale < 1 else rgb
    bgr = cv2.cvtColor(small, cv2.COLOR_RGB2BGR)
    sh, sw = bgr.shape[:2]

    results: list[tuple[Box, float]] = []
    if backend_name() == "yunet":
        with _lock:
            det = cv2.FaceDetectorYN.create(str(YUNET_PATH), "", (sw, sh), threshold, 0.3, 500)
            _, faces = det.detect(bgr)
        for f in faces if faces is not None else []:
            x, y, fw, fh, score = float(f[0]), float(f[1]), float(f[2]), float(f[3]), float(f[-1])
            box = Box(x / scale, y / scale, (x + fw) / scale, (y + fh) / scale)
            results.append((_expand(box, w, h), round(score, 2)))
    else:
        gray = cv2.equalizeHist(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY))
        cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        for x, y, fw, fh in cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=6, minSize=(24, 24)):
            box = Box(x / scale, y / scale, (x + fw) / scale, (y + fh) / scale)
            results.append((_expand(box, w, h), 0.6))
    return results
