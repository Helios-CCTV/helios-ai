from fastapi import APIRouter, UploadFile, File, HTTPException, Form, BackgroundTasks
from fastapi.responses import FileResponse
from typing import Optional
from app.services.detection_service import DetectionService
from app.schemas.detection import DetectionResponse, VideoDetectionResponse, DetectionRequest, VideoDetectionRequest
import os
from pathlib import Path
import tempfile
import shutil

router = APIRouter(prefix="/detection", tags=["detection"])

# 모델 경로 설정
MODEL_DIR = Path("models")
MODEL_PATH = MODEL_DIR / "yolo_model.pt"  # 여기에 실제 모델 파일 이름을 넣으세요

# 서비스 인스턴스 생성
detection_service = None

def get_detection_service():
    """Detection 서비스 싱글톤 인스턴스 가져오기"""
    global detection_service
    if detection_service is None:
        if not os.path.exists(MODEL_PATH):
            raise HTTPException(status_code=500, detail=f"Model not found at {MODEL_PATH}")
        detection_service = DetectionService(str(MODEL_PATH))
    return detection_service

@router.post("/image", response_model=DetectionResponse)
async def detect_objects_from_image(
    file: UploadFile = File(...),
    confidence: float = Form(0.25)
):
    """
    이미지에서 객체 탐지 수행
    
    - **file**: 탐지할 이미지 파일
    - **confidence**: 탐지 신뢰도 임계값 (0.0 ~ 1.0)
    
    Returns:
        DetectionResponse: 탐지 결과
    """
    try:
        # 이미지 읽기
        contents = await file.read()
        
        # 탐지 서비스 가져오기
        service = get_detection_service()
        
        # 탐지 수행
        result = await service.detect_from_image(contents, confidence)
        
        return result
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@router.post("/video", response_model=VideoDetectionResponse)
async def detect_objects_from_video(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    confidence: float = Form(0.25)
):
    """
    비디오에서 객체 탐지 수행
    
    - **file**: 탐지할 비디오 파일
    - **confidence**: 탐지 신뢰도 임계값 (0.0 ~ 1.0)
    
    Returns:
        VideoDetectionResponse: 탐지 결과
    """
    try:
        # 임시 파일 생성
        temp_dir = Path(tempfile.gettempdir())
        temp_file_path = temp_dir / file.filename
        
        # 업로드된 파일을 임시 파일로 저장
        with open(temp_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # 탐지 서비스 가져오기
        service = get_detection_service()
        
        # 탐지 수행
        result = await service.detect_from_video(str(temp_file_path), confidence)
        
        # 임시 파일 정리 (백그라운드에서 실행)
        background_tasks.add_task(os.remove, temp_file_path)
        
        return result
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@router.get("/result-video/{filename}")
async def get_result_video(filename: str):
    """
    처리된 비디오 결과 파일 다운로드
    
    - **filename**: 결과 비디오 파일 이름
    
    Returns:
        FileResponse: 비디오 파일
    """
    file_path = Path("results") / filename
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"File {filename} not found")
    
    return FileResponse(
        path=str(file_path),
        media_type="video/mp4",
        filename=filename
    )
