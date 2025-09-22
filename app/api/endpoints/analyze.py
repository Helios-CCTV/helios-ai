from typing import List, Dict, Any

from fastapi import APIRouter, HTTPException, Query

from app.core.analyze_settings import analyze_settings
from app.services.analyzer_service import analyze_one_public_image  # 실제 YOLO 분석 서비스 사용
from app.services.analyze_utils import list_public_objects_for_date, resolve_swift_container_base, get_swift_base_and_headers
from app.db.mysql_client_safe import upsert_analyze_with_detections  # 안전한 MySQL 클라이언트


router = APIRouter(prefix="/analyze", tags=["analyze"]) 


@router.post("/date")
@router.get("/date")
def analyze_by_date(yyyymmdd: str = Query(..., regex=r"^\d{8}$"), keys: List[str] | None = None) -> Dict[str, Any]:
    """분석 실행: yyyymmdd 기준. 
    - keys를 주면 해당 파일명만 처리 (예: ["5044_20250913.jpg"]).
    - 없으면 프리픽스 규칙으로 URL을 구성하여 시도.
    """
    year = yyyymmdd[:4]
    mmdd = yyyymmdd[4:]
    processed: List[Dict[str, Any]] = []

    file_keys = keys or []
    if not file_keys:
        # 지정 날짜의 전체 파일 목록 조회
        try:
            pairs = list_public_objects_for_date(yyyymmdd)
        except ValueError as ve:
            raise HTTPException(status_code=400, detail=str(ve))
        if not pairs:
            raise HTTPException(status_code=404, detail="해당 날짜의 파일을 찾을 수 없습니다")
        # (name, url)
        file_keys = [name.split("/")[-1] for name, _ in pairs]
        url_map = {name.split("/")[-1]: url for name, url in pairs}
    else:
        base, _ = get_swift_base_and_headers()
        url_map = {fn: f"{base}/{year}/{mmdd}/{fn}" for fn in file_keys}

    for filename in file_keys:
        url = url_map[filename]
        try:
            payload = analyze_one_public_image(url, filename, save_to_swift=True)
            analyze_id = upsert_analyze_with_detections(payload)
            processed.append({"filename": filename, "analyze_id": analyze_id, "detections": payload["detections"], "swift_image_url": payload.get("swift_image_url")})
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"{filename} 처리 실패: {e}")

    return {"success": True, "count": len(processed), "items": processed}


@router.get("/debug/swift-base", tags=["analyze"], summary="Swift 베이스 확인")
def debug_swift_base() -> Dict[str, Any]:
    """런타임에서 해석된 Swift 베이스 URL과 인증 헤더 사용 여부를 확인합니다."""
    try:
        base, headers = get_swift_base_and_headers()
        return {"ok": True, "base": base, "uses_token": bool(headers)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Swift 설정 오류: {e}")
