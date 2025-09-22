def upsert_analyze_with_detections(payload):
    """임시로 MySQL 없이 더미 ID 반환"""
    import random
    dummy_id = random.randint(1000, 9999)
    print(f"더미 MySQL: 분석 결과 저장됨 (ID: {dummy_id})")
    print(f"  - CCTV ID: {payload.get('cctv_id')}")
    print(f"  - 분석 날짜: {payload.get('analyzed_date')}")
    print(f"  - 탐지 수: {payload.get('detection_count', 0)}")
    return dummy_id
