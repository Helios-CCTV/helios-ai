import base64
import io
import re
from dataclasses import dataclass
from typing import List, Tuple, Dict, Any

import requests
from PIL import Image, ImageDraw

from app.core.analyze_settings import analyze_settings


_FILENAME_RE = re.compile(r"^(?P<cctv>\d+)_(?P<date>\d{8})\.jpg$", re.IGNORECASE)


def list_public_objects_for_date(yyyymmdd: str) -> List[Tuple[str, str]]:
    """지정한 날짜(yyyymmdd)의 모든 객체 목록을 (key, url)로 반환합니다.
    Swift public container에서 prefix=YYYY/MMDD/ & format=json로 페이지네이션 조회합니다.
    """
    year = yyyymmdd[:4]
    mmdd = yyyymmdd[4:]
    prefix = f"{year}/{mmdd}/"
    base = analyze_settings.SWIFT_PUBLIC_BASE_URL.rstrip("/")

    items: List[Tuple[str, str]] = []
    marker = None
    session = requests.Session()

    while True:
        params = {"prefix": prefix, "format": "json", "limit": 1000}
        if marker:
            params["marker"] = marker
        resp = session.get(base, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list):
            break
        if not data:
            break
        for obj in data:
            name = obj.get("name")
            if not name or not name.lower().endswith(".jpg"):
                continue
            url = f"{base}/{name}"
            items.append((name, url))
            marker = name
        # 페이지가 꽉 찼으면 다음 루프 계속
        if len(data) < 1000:
            break

    return items


def parse_filename(filename: str) -> Tuple[int, str]:
    m = _FILENAME_RE.match(filename)
    if not m:
        raise ValueError(f"파일명 형식이 올바르지 않습니다: {filename}")
    return int(m.group("cctv")), m.group("date")


def http_get_image(url: str) -> Image.Image:
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return Image.open(io.BytesIO(resp.content)).convert("RGB")


def draw_bboxes(img: Image.Image, boxes: List[Tuple[int, int, int, int]], labels: List[str]) -> Image.Image:
    draw = ImageDraw.Draw(img)
    for box, label in zip(boxes, labels):
        x1, y1, x2, y2 = box
        draw.rectangle([x1, y1, x2, y2], outline=(255, 0, 0), width=3)
        draw.text((x1 + 4, max(0, y1 - 12)), label, fill=(255, 255, 0))
    return img


def resize_for_max_width(img: Image.Image, max_width: int) -> Image.Image:
    if img.width <= max_width:
        return img
    ratio = max_width / float(img.width)
    new_h = int(img.height * ratio)
    return img.resize((max_width, new_h))


def image_to_base64_jpeg(img: Image.Image, quality: int = 85) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return base64.b64encode(buf.getvalue())


@dataclass
class Detection:
    class_id: int
    damage_type: str
    confidence: float
    bbox: Tuple[int, int, int, int]
    severity: str
    area: float
    severity_score: float


def classify_severity(area_ratio: float) -> str:
    if area_ratio >= analyze_settings.SEVERITY_AREA_MED:
        return "high"
    if area_ratio >= analyze_settings.SEVERITY_AREA_LOW:
        return "medium"
    return "low"


def compute_analyze_score(detections: List[Detection]) -> float:
    if not detections:
        return 0.0
    # Simple score: sum(confidence * area_ratio * 100)
    score = sum(d.confidence * d.area * 100.0 for d in detections)
    return round(score, 2)
