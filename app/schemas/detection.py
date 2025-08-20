from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class DetectionRequest(BaseModel):
    confidence: float = Field(0.25, description="객체 탐지 신뢰도 임계값 (0.0 ~ 1.0)")

class BoundingBox(BaseModel):
    x1: float
    y1: float
    x2: float
    y2: float

class Detection(BaseModel):
    class_id: int
    class_name: str
    confidence: float
    bbox: List[float]

class DetectionResponse(BaseModel):
    success: bool
    message: str
    process_time: Optional[float] = None
    detections: List[Detection] = []
    count: int
    result_image: Optional[str] = None  # Base64 인코딩된 결과 이미지

class VideoDetectionRequest(BaseModel):
    video_path: str
    confidence: float = Field(0.25, description="객체 탐지 신뢰도 임계값 (0.0 ~ 1.0)")
    save_path: Optional[str] = None

class VideoDetectionResponse(BaseModel):
    success: bool
    message: str
    process_time: Optional[float] = None
    detections: List[Detection] = []  # 마지막 프레임의 탐지 결과
    total_frames: Optional[int] = None
    result_video_path: Optional[str] = None
