from typing import Dict, Any, List

from PIL import Image

from app.core.analyze_settings import analyze_settings
from app.services.analyze_utils import (
    parse_filename,
    http_get_image,
    draw_bboxes,
    resize_for_max_width,
    image_to_base64_jpeg,
    Detection,
    classify_severity,
    compute_analyze_score,
)
from app.services.yolo_runner import run_inference


# 한국어 damage type 매핑 (class_id -> string)
CLASS_MAP = {
    0: "반사균열",
    1: "세로방향균열",
    2: "밀림균열",
    3: "러팅",
    4: "코루게이션및쇼빙",
    5: "함몰",
    6: "포트홀",
    7: "라벨링",
    8: "박리",
    9: "정상",
    10: "단부균열",
    11: "시공균열",
    12: "거북등",
}


def analyze_one_public_image(url: str, filename: str) -> Dict[str, Any]:
    """Run detection and build analyze/detections payloads.
    Returns dict with keys: cctv_id, analyzed_date (YYYY-MM-DD), message, detection_count,
    severity_score, image_base64, detections(list of dicts)
    """
    cctv_id, yyyymmdd = parse_filename(filename)
    img = http_get_image(url)

    # Run YOLO
    preds = run_inference(img)
    W, H = img.width, img.height

    detections: List[Detection] = []
    boxes = []
    labels = []
    for cls, conf, (x1, y1, x2, y2) in preds:
        area_ratio = max(0.0, float((x2 - x1) * (y2 - y1)) / float(W * H))
        sev = classify_severity(area_ratio)
        det = Detection(
            class_id=cls,
            damage_type=CLASS_MAP.get(cls, str(cls)),
            confidence=conf,
            bbox=(x1, y1, x2, y2),
            severity=sev,
            area=area_ratio,
            severity_score=conf * area_ratio * 100.0,
        )
        detections.append(det)
        boxes.append((x1, y1, x2, y2))
        labels.append(f"{det.damage_type}:{conf:.2f}")

    # Draw
    annotated = img.copy()
    annotated = draw_bboxes(annotated, boxes, labels) if detections else annotated
    annotated = resize_for_max_width(annotated, analyze_settings.OUTPUT_MAX_WIDTH)
    img_b64 = image_to_base64_jpeg(annotated, analyze_settings.JPEG_QUALITY)

    score = compute_analyze_score(detections)
    msg = (
        f"파손 {len(detections)}건, 최고 {max((d.confidence for d in detections), default=0.0):.2f}"
        if detections else "감지 없음"
    )

    return {
        "cctv_id": cctv_id,
        "analyzed_date": f"{yyyymmdd[:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:]}",
        "message": msg,
        "detection_count": len(detections),
        "severity_score": score,
        "image_base64": img_b64,
        "detections": [
            {
                "class_id": d.class_id,
                "damage_type": d.damage_type,
                "confidence": round(d.confidence, 5),
                "bbox": [d.bbox[0], d.bbox[1], d.bbox[2], d.bbox[3]],
                "severity": d.severity,
                "area": d.area,
                "severity_score": d.severity_score,
            }
            for d in detections
        ],
        "original_width": W,
        "original_height": H,
    }
