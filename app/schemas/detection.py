from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime

class DetectionRequest(BaseModel):
    confidence: float = Field(0.25, description="객체 탐지 신뢰도 임계값 (0.0 ~ 1.0)")
    include_image: bool = Field(True, description="결과 이미지를 Base64로 포함할지 여부")

class BoundingBox(BaseModel):
    x1: float
    y1: float
    x2: float
    y2: float

class DamageDetection(BaseModel):
    class_id: int
    damage_type: str  # 파손 유형 (e.g., "pothole", "crack", "patch")
    confidence: float
    bbox: List[float]
    severity: Optional[str] = None  # 심각도 (e.g., "high", "medium", "low")
    area: Optional[float] = None  # 파손 면적 (픽셀 단위)

class DetectionResponse(BaseModel):
    success: bool
    message: str
    process_time: float
    timestamp: datetime = Field(default_factory=datetime.now)
    image_id: Optional[str] = None  # 이미지 식별자
    location: Optional[Dict[str, float]] = None  # 위치 정보 (경도, 위도)
    damages: List[DamageDetection] = []
    damage_count: int
    damage_summary: Dict[str, int] = {}  # 파손 유형별 개수
    total_damage_area: Optional[float] = None  # 총 파손 면적
    severity_score: Optional[float] = None  # 전체 심각도 점수 (0-100)
    result_image: Optional[str] = None  # Base64 인코딩된 결과 이미지

class VideoDetectionRequest(BaseModel):
    video_path: str
    confidence: float = Field(0.25, description="객체 탐지 신뢰도 임계값 (0.0 ~ 1.0)")
    save_path: Optional[str] = None
    fps_interval: int = Field(1, description="몇 프레임마다 탐지를 수행할지 설정")

class VideoDetectionResponse(BaseModel):
    success: bool
    message: str
    process_time: Optional[float] = None
    damages: List[DamageDetection] = []  # 마지막 프레임의 탐지 결과
    total_frames: Optional[int] = None
    processed_frames: Optional[int] = None
    damage_timeline: Optional[Dict[str, List[int]]] = None  # 시간에 따른 파손 유형별 개수
    damage_summary: Dict[str, int] = {}  # 파손 유형별 개수
    average_severity_score: Optional[float] = None  # 평균 심각도
    max_severity_frame: Optional[int] = None  # 최대 심각도를 보인 프레임
    result_video_path: Optional[str] = None
