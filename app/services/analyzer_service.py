from typing import Dict, Any, List
import base64
import io
import asyncio
import threading

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
from app.services.storage_swift import get_swift_uploader


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


def analyze_one_public_image(url: str, filename: str, save_to_swift: bool = False) -> Dict[str, Any]:
    """Run detection and build analyze/detections payloads.
    Returns dict with keys: cctv_id, analyzed_date (YYYY-MM-DD), message, detection_count,
    severity_score, image_base64, detections(list of dicts)
    
    Args:
        url: 이미지 URL
        filename: 파일명
        save_to_swift: 분석된 이미지를 Swift에 저장할지 여부
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

    # Swift에 저장 (옵션)
    swift_url = None
    image_binary = None  # 데이터베이스 저장용 바이너리 데이터
    
    # 이미지 바이너리 데이터 준비 (SpringBoot 방식 참고 - 20MB 제한)
    try:
        # PIL 이미지를 JPEG 바이트로 변환
        img_bytes_io = io.BytesIO()
        annotated.save(img_bytes_io, format='JPEG', quality=analyze_settings.JPEG_QUALITY)
        img_bytes = img_bytes_io.getvalue()
        
        # 크기 체크 (SpringBoot와 동일하게 20MB 제한)
        MAX_BYTES = 20 * 1024 * 1024  # 20MB
        if len(img_bytes) > MAX_BYTES:
            print(f"이미지 크기가 너무 큽니다: {len(img_bytes)} bytes (최대 20MB)")
            img_bytes = None
        else:
            image_binary = img_bytes  # 데이터베이스 저장용으로 사용
            print(f"이미지 바이너리 준비 완료: {len(img_bytes)} bytes")
    except Exception as e:
        print(f"이미지 바이너리 변환 실패: {e}")
    
    # Swift 저장 (오브젝트 스토리지)
    if save_to_swift and image_binary:
        try:
            # Swift 업로드를 위한 object key 생성
            # 형식: analyzes/날짜/cctv_id.jpg (예: analyzes/2025-09-22/cctv_123.jpg)
            analyzed_date = f"{yyyymmdd[:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:]}"
            # filename에서 cctv_id 추출 (예: "cctv_123.jpg" -> "cctv_123")
            cctv_id = filename.split('.')[0] if '.' in filename else filename
            object_key = f"analyzes/{analyzed_date}/{cctv_id}.jpg"
            
            # Swift 업로더 가져오기 및 업로드
            import asyncio
            import threading
            uploader = get_swift_uploader()
            
            # 새로운 스레드에서 비동기 함수 실행
            def upload_in_thread():
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        loop.run_until_complete(uploader.upload_bytes(image_binary, object_key, "image/jpeg"))
                    finally:
                        loop.close()
                except Exception as e:
                    print(f"스레드 내 업로드 실패: {e}")
            
            # 스레드 실행
            thread = threading.Thread(target=upload_in_thread)
            thread.start()
            thread.join(timeout=10)  # 최대 10초 대기
            
            # Swift URL 생성 (공개 접근 가능한 URL)
            swift_url = f"http://116.89.191.2:8080/v1/AUTH_5ec66c4e21054d7d89b918f1fa287f24/cctv-preprocess/{object_key}"
            print(f"Swift 저장 성공: {object_key}")
            
        except Exception as e:
            print(f"Swift 이미지 저장 실패: {e}")
            # Swift 저장 실패해도 분석은 계속 진행

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
        "image_binary": image_binary,  # 데이터베이스 image 컬럼 저장용 바이너리 데이터
        "swift_image_url": swift_url,  # Swift에 저장된 이미지 URL (없으면 None)
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
