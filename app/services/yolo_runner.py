from typing import List, Tuple

import numpy as np
from PIL import Image

from app.core.analyze_settings import analyze_settings


try:
    from ultralytics import YOLO
except Exception:  # pragma: no cover
    YOLO = None


_MODEL = None


def get_model():
    global _MODEL
    if _MODEL is None:
        if YOLO is None:
            raise RuntimeError("Ultralytics YOLO가 설치되어 있지 않습니다.")
        _MODEL = YOLO(analyze_settings.MODEL_PATH)
    return _MODEL


def run_inference(img: Image.Image, conf: float = None, iou: float = None) -> List[Tuple[int, float, Tuple[int, int, int, int]]]:
    """Return list of (class_id, confidence, bbox_xyxy)."""
    model = get_model()
    conf = conf if conf is not None else analyze_settings.YOLO_CONF_THRESH
    iou = iou if iou is not None else analyze_settings.YOLO_IOU_THRESH

    results = model.predict(img, conf=conf, iou=iou, verbose=False)
    out: List[Tuple[int, float, Tuple[int, int, int, int]]] = []
    for r in results:
        if not hasattr(r, "boxes") or r.boxes is None:
            continue
        for b in r.boxes:
            cls = int(b.cls.item())
            confv = float(b.conf.item())
            xyxy = b.xyxy.cpu().numpy().astype(np.int32).tolist()[0]
            out.append((cls, confv, (xyxy[0], xyxy[1], xyxy[2], xyxy[3])))
    return out
