from typing import List, Dict, Any

from fastapi import APIRouter, HTTPException, Query

from app.core.analyze_settings import analyze_settings
from app.services.analyzer_service import analyze_one_public_image
from app.services.analyze_utils import list_public_objects_for_date
from app.db.mysql_client import upsert_analyze_with_detections


router = APIRouter(prefix="/analyze", tags=["analyze"]) 


@router.post("/date")
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
        pairs = list_public_objects_for_date(yyyymmdd)
        if not pairs:
            raise HTTPException(status_code=404, detail="해당 날짜의 파일을 찾을 수 없습니다")
        # (name, url)
        file_keys = [name.split("/")[-1] for name, _ in pairs]
        url_map = {name.split("/")[-1]: url for name, url in pairs}
    else:
        url_map = {fn: f"{analyze_settings.SWIFT_PUBLIC_BASE_URL}{year}/{mmdd}/{fn}" for fn in file_keys}

    for filename in file_keys:
        url = url_map[filename]
        try:
            payload = analyze_one_public_image(url, filename)
            analyze_id = upsert_analyze_with_detections(payload)
            processed.append({"filename": filename, "analyze_id": analyze_id, "detections": payload["detections"]})
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"{filename} 처리 실패: {e}")

    return {"success": True, "count": len(processed), "items": processed}
