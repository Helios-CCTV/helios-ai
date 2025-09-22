import base64
import io
import re
from dataclasses import dataclass
from typing import List, Tuple, Dict, Any

import requests
from PIL import Image, ImageDraw, ImageFont

from app.core.analyze_settings import analyze_settings
import os
from urllib.parse import urlparse, urlunparse


_FILENAME_RE = re.compile(r"^(?P<cctv>\d+)_(?P<date>\d{8})\.jpg$", re.IGNORECASE)


def resolve_swift_container_base() -> str:
    """Env에서 Swift 퍼블릭 베이스 URL을 정규화해 컨테이너 경로까지 포함해 반환합니다.

    우선순위:
    1) analyze_settings.SWIFT_PUBLIC_BASE_URL
    2) app.core.config.settings.SWIFT_PUBLIC_BASE_URL (있으면)

    - 값이 비었거나 example.com이면 설정 오류로 간주합니다.
    - 값이 계정 경로(AUTH_xxx)까지만 있으면 컨테이너명을 덧붙입니다.
    - 반환값은 끝에 슬래시가 없는 형태로 통일합니다.
    """
    # 먼저 현재 프로세스 환경변수 우선 사용 (dotenv 적용 후 최신값 보장)
    base = (os.getenv("SWIFT_PUBLIC_BASE_URL") or analyze_settings.SWIFT_PUBLIC_BASE_URL or "").strip()
    if not base:
        try:
            from app.core.config import settings  # 지연 임포트로 순환참조 방지
            base = (getattr(settings, "SWIFT_PUBLIC_BASE_URL", "") or "").strip()
        except Exception:
            base = ""

    if not base or "example.com" in base:
        raise ValueError("SWIFT_PUBLIC_BASE_URL 환경변수가 올바르지 않습니다. .env 또는 환경변수를 확인하세요.")

    base = base.rstrip("/")
    container = analyze_settings.SWIFT_CONTAINER.strip("/")
    if not base.lower().endswith(f"/{container.lower()}"):
        base = f"{base}/{container}"

    # 'controller' 같은 내부 호스트명이 들어온 경우 외부 호스트로 교체
    parsed = urlparse(base)
    override_host = os.getenv("SWIFT_PUBLIC_HOST_OVERRIDE", "").strip()
    if override_host:
        if ":" in override_host:
            new_netloc = override_host
        else:
            new_netloc = f"{override_host}:{os.getenv('OS_OBJECT_STORE_PORT','8080')}"
        parsed = parsed._replace(netloc=new_netloc)
        base = urlunparse(parsed)
    elif parsed.hostname and parsed.hostname.lower() in {"controller", "controller.local"}:
        auth = urlparse(os.getenv("OS_AUTH_URL", ""))
        host = auth.hostname or parsed.hostname
        port = os.getenv("OS_OBJECT_STORE_PORT", "8080")
        parsed = parsed._replace(netloc=f"{host}:{port}")
        base = urlunparse(parsed)

    return base.rstrip("/")


def _keystone_get_storage_base_and_token() -> Tuple[str, str]:
    """Keystone v3 비밀번호 인증으로 Swift object-store 엔드포인트를 조회합니다.

    환경변수: OS_AUTH_URL, OS_USERNAME, OS_PASSWORD, OS_PROJECT_NAME,
    OS_USER_DOMAIN_NAME, OS_PROJECT_DOMAIN_NAME
    반환: (storage_base_without_container, token)
    예) (http://host:8080/v1/AUTH_xxx, eyJhbGciOi...)"""
    auth_url = os.getenv("OS_AUTH_URL", "").rstrip("/")
    if not auth_url:
        raise ValueError("OS_AUTH_URL이 비어 있습니다")
    url = f"{auth_url}/auth/tokens"
    username = os.getenv("OS_USERNAME")
    password = os.getenv("OS_PASSWORD")
    project = os.getenv("OS_PROJECT_NAME")
    user_domain = os.getenv("OS_USER_DOMAIN_NAME", "Default")
    proj_domain = os.getenv("OS_PROJECT_DOMAIN_NAME", "Default")
    if not (username and password and project):
        raise ValueError("OS_USERNAME/OS_PASSWORD/OS_PROJECT_NAME이 필요합니다")
    payload = {
        "auth": {
            "identity": {
                "methods": ["password"],
                "password": {
                    "user": {
                        "name": username,
                        "domain": {"name": user_domain},
                        "password": password,
                    }
                },
            },
            "scope": {
                "project": {
                    "name": project,
                    "domain": {"name": proj_domain},
                }
            },
        }
    }
    resp = requests.post(url, json=payload, timeout=30)
    resp.raise_for_status()
    token = resp.headers.get("X-Subject-Token")
    if not token:
        raise RuntimeError("Keystone 토큰을 받지 못했습니다")
    data = resp.json()
    catalog = data.get("token", {}).get("catalog", [])
    storage_url = None
    for svc in catalog:
        if svc.get("type") == "object-store":
            for ep in svc.get("endpoints", []):
                if ep.get("interface") == "public":
                    storage_url = ep.get("url")
                    break
        if storage_url:
            break
    if not storage_url:
        raise RuntimeError("Keystone 카탈로그에서 object-store public 엔드포인트를 찾지 못했습니다")
    return storage_url.rstrip("/"), token


def get_swift_base_and_headers() -> Tuple[str, Dict[str, str]]:
    """Swift 컨테이너 베이스 URL과 요청 헤더를 반환합니다.
    1) SWIFT_PUBLIC_BASE_URL이 유효하면 그 값 사용 (헤더 없음)
    2) 아니면 Keystone 인증으로 object-store 퍼블릭 URL + 컨테이너 경로 생성 (X-Auth-Token 헤더 포함)
    """
    # SWIFT_PUBLIC_BASE_URL가 존재하면 무조건 퍼블릭 URL 사용 (토큰 불필요)
    env_base = (os.getenv("SWIFT_PUBLIC_BASE_URL") or "").strip()
    if env_base:
        return resolve_swift_container_base(), {}
    try:
        base = resolve_swift_container_base()
        return base, {}
    except Exception:
        storage_base, token = _keystone_get_storage_base_and_token()
        # Keystone가 내부 호스트명(controller 등)을 돌려줄 수 있어 외부 접근 가능한 호스트로 치환
        override_host = os.getenv("SWIFT_PUBLIC_HOST_OVERRIDE", "").strip()
        parsed = urlparse(storage_base)
        new_netloc = parsed.netloc
        if override_host:
            # host[:port] 형식 허용, 포트 없으면 기본 8080 사용
            if ":" in override_host:
                new_netloc = override_host
            else:
                new_netloc = f"{override_host}:{os.getenv('OS_OBJECT_STORE_PORT','8080')}"
        elif parsed.hostname and parsed.hostname.lower() in {"controller", "controller.local"}:
            # OS_AUTH_URL의 호스트를 사용, 포트는 기본 8080
            auth = urlparse(os.getenv("OS_AUTH_URL", ""))
            host = auth.hostname or parsed.hostname
            port = os.getenv("OS_OBJECT_STORE_PORT", "8080")
            new_netloc = f"{host}:{port}"
        if new_netloc != parsed.netloc:
            parsed = parsed._replace(netloc=new_netloc)
            storage_base = urlunparse(parsed)
        container = analyze_settings.SWIFT_CONTAINER.strip("/")
        base = f"{storage_base.rstrip('/')}/{container}"
        return base.rstrip("/"), {"X-Auth-Token": token}


def list_public_objects_for_date(yyyymmdd: str) -> List[Tuple[str, str]]:
    """지정한 날짜(yyyymmdd)의 모든 객체 목록을 (key, url)로 반환합니다.
    Swift public container에서 prefix=YYYY/MMDD/ & format=json로 페이지네이션 조회합니다.
    """
    year = yyyymmdd[:4]
    mmdd = yyyymmdd[4:]
    prefix = f"{year}/{mmdd}/"
    base, headers = get_swift_base_and_headers()

    items: List[Tuple[str, str]] = []
    marker = None
    session = requests.Session()

    while True:
        params = {"prefix": prefix, "format": "json", "limit": 1000}
        if marker:
            params["marker"] = marker
        resp = session.get(base, params=params, headers=headers or None, timeout=30)
        try:
            resp.raise_for_status()
        except requests.HTTPError as he:
            status = getattr(getattr(he, "response", None), "status_code", None)
            if status == 404:
                # 컨테이너/경로 없음 -> 빈 목록 처리
                return []
            raise
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
    
    # 한글 폰트 설정 시도
    font = None
    try:
        # Windows 기본 한글 폰트 시도
        font_paths = [
            "C:/Windows/Fonts/malgun.ttf",    # 맑은 고딕
            "C:/Windows/Fonts/gulim.ttc",     # 굴림
            "C:/Windows/Fonts/batang.ttc",    # 바탕
            "C:/Windows/Fonts/NanumGothic.ttf" # 나눔고딕 (설치된 경우)
        ]
        
        for font_path in font_paths:
            try:
                font = ImageFont.truetype(font_path, 14)
                break
            except:
                continue
                
        if font is None:
            # 시스템 기본 폰트 사용
            font = ImageFont.load_default()
    except:
        font = ImageFont.load_default()
    
    for box, label in zip(boxes, labels):
        x1, y1, x2, y2 = box
        draw.rectangle([x1, y1, x2, y2], outline=(255, 0, 0), width=3)
        draw.text((x1 + 4, max(0, y1 - 18)), label, fill=(255, 255, 0), font=font)
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
