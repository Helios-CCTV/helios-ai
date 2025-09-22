from typing import Dict, Any
from app.core.analyze_settings import analyze_settings


def analyze_one_public_image(image_url: str, filename: str) -> Dict[str, Any]:
    """임시로 AI 분석 없이 더미 데이터 반환"""
    
    # 파일명에서 정보 추출
    import re
    match = re.match(r"(\d+)_(\d{8})\.jpg", filename)
    if match:
        cctv_id = match.group(1)
        date = match.group(2)
        analyzed_date = f"{date[:4]}-{date[4:6]}-{date[6:8]}"
    else:
        cctv_id = "unknown"
        analyzed_date = "2025-09-13"
    
    # 더미 응답 생성
    dummy_payload = {
        "cctv_id": cctv_id,
        "analyzed_date": analyzed_date,
        "message": f"임시 분석 완료: {filename}",
        "detection_count": 0,
        "severity_score": 0.0,
        "image_base64": b"",  # 빈 이미지
        "detections": []
    }
    
    return dummy_payload
