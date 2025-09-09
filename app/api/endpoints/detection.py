from fastapi import APIRouter, UploadFile, File, HTTPException, Form, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from typing import Optional, List, AsyncGenerator
from app.services.detection_service import DetectionService
from app.schemas.detection import DetectionResponse, VideoDetectionResponse, DetectionRequest, VideoDetectionRequest
import os
import cv2
import asyncio
import base64
from pathlib import Path
import tempfile
import shutil
import json
import datetime

router = APIRouter(prefix="/damage-detection", tags=["damage-detection"])

# 모델 경로 설정
MODEL_DIR = Path("models")
MODEL_PATH = MODEL_DIR / "09-08-best-final-model.pt"  # 업데이트된 최신 모델

# 서비스 인스턴스 생성
detection_service = None

def get_detection_service():
    """도로 파손 탐지 서비스 싱글톤 인스턴스 가져오기"""
    global detection_service
    if detection_service is None:
        if not os.path.exists(MODEL_PATH):
            raise HTTPException(status_code=500, detail=f"도로 파손 탐지 모델을 찾을 수 없습니다: {MODEL_PATH}")
        detection_service = DetectionService(str(MODEL_PATH))
    return detection_service

@router.post("/analyze", response_model=DetectionResponse)
async def analyze_road_damage(
    file: UploadFile = File(...),
    confidence: float = Form(0.1),
    include_image: bool = Form(True),
    location_lat: Optional[float] = Form(None, description="위도 정보"),
    location_lng: Optional[float] = Form(None, description="경도 정보"),
    image_id: Optional[str] = Form(None, description="이미지 식별자")
):
    """
    이미지에서 도로 파손 탐지 분석 수행
    
    - **file**: 분석할 도로 이미지 파일
    - **confidence**: 탐지 신뢰도 임계값 (0.0 ~ 1.0)
    - **include_image**: 결과 이미지를 Base64로 포함할지 여부
    - **location_lat**: 이미지 촬영 위치의 위도 (선택 사항)
    - **location_lng**: 이미지 촬영 위치의 경도 (선택 사항)
    - **image_id**: 이미지 식별자 (선택 사항)
    
    Returns:
        DetectionResponse: 도로 파손 분석 결과
    """
    try:
        # 이미지 읽기
        contents = await file.read()
        
        # 위치 정보 설정
        location = None
        if location_lat is not None and location_lng is not None:
            location = {"latitude": location_lat, "longitude": location_lng}
        
        # 탐지 서비스 가져오기
        service = get_detection_service()
        
        # 탐지 수행
        result = await service.analyze_road_damage(
            image_bytes=contents, 
            confidence=confidence,
            include_image=include_image,
            location=location,
            image_id=image_id
        )
        
        return result
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@router.post("/analyze-video", response_model=VideoDetectionResponse)
async def analyze_road_damage_video(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    confidence: float = Form(0.1),
    fps_interval: int = Form(1, description="몇 프레임마다 탐지를 수행할지 설정"),
    video_id: Optional[str] = Form(None, description="비디오 식별자")
):
    """
    비디오에서 도로 파손 탐지 분석 수행
    
    - **file**: 분석할 도로 영상 파일
    - **confidence**: 탐지 신뢰도 임계값 (0.0 ~ 1.0)
    - **fps_interval**: 몇 프레임마다 탐지를 수행할지 설정 (1: 모든 프레임, 2: 2프레임마다, 등)
    - **video_id**: 비디오 식별자 (선택 사항)
    
    Returns:
        VideoDetectionResponse: 도로 파손 분석 결과
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
        result = await service.analyze_road_damage_video(
            video_path=str(temp_file_path), 
            confidence=confidence,
            fps_interval=fps_interval,
            video_id=video_id
        )
        
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

@router.get("/statistics", tags=["statistics"])
async def get_damage_statistics(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    damage_type: Optional[str] = None,
    min_severity: Optional[float] = None,
    location_range: Optional[str] = None
):
    """
    탐지된 도로 파손의 통계 정보 조회
    
    - **start_date**: 시작 날짜 (YYYY-MM-DD 형식)
    - **end_date**: 종료 날짜 (YYYY-MM-DD 형식)
    - **damage_type**: 파손 유형 필터링 (예: pothole, crack, patch)
    - **min_severity**: 최소 심각도 필터링
    - **location_range**: 위치 범위 (형식: lat1,lng1,lat2,lng2)
    
    Returns:
        dict: 도로 파손 통계 정보
    """
    try:
        # 탐지 서비스 가져오기
        service = get_detection_service()
        
        # 통계 조회
        statistics = await service.get_damage_statistics(
            start_date=start_date,
            end_date=end_date,
            damage_type=damage_type,
            min_severity=min_severity,
            location_range=location_range
        )
        
        return statistics
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/batch-analyze")
async def batch_analyze_images(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    confidence: float = Form(0.1),
    include_images: bool = Form(False),
    job_id: Optional[str] = Form(None)
):
    """
    여러 이미지에 대한 일괄 도로 파손 분석 수행
    
    - **files**: 분석할 이미지 파일 목록
    - **confidence**: 탐지 신뢰도 임계값 (0.0 ~ 1.0)
    - **include_images**: 결과 이미지를 Base64로 포함할지 여부
    - **job_id**: 작업 식별자 (선택 사항)
    
    Returns:
        dict: 배치 분석 작업 정보
    """
    try:
        if not files:
            raise HTTPException(status_code=400, detail="이미지 파일이 제공되지 않았습니다.")
        
        # 작업 ID 생성
        if job_id is None:
            job_id = f"batch_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"
            
        # 임시 디렉토리 생성
        temp_dir = Path(tempfile.gettempdir()) / job_id
        os.makedirs(temp_dir, exist_ok=True)
        
        # 파일 저장
        file_paths = []
        for file in files:
            file_path = temp_dir / file.filename
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            file_paths.append(str(file_path))
        
        # 탐지 서비스 가져오기
        service = get_detection_service()
        
        # 백그라운드에서 배치 처리 시작
        background_tasks.add_task(
            service.process_batch_analysis,
            file_paths=file_paths,
            confidence=confidence,
            include_images=include_images,
            job_id=job_id
        )
        
        # 임시 파일 정리 (백그라운드에서 실행)
        background_tasks.add_task(shutil.rmtree, temp_dir)
        
        return {
            "success": True,
            "message": f"배치 분석이 시작되었습니다. job_id: {job_id}",
            "job_id": job_id,
            "file_count": len(files),
            "status": "processing"
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/batch-result/{job_id}")
async def get_batch_result(job_id: str):
    """
    배치 분석 결과 조회
    
    - **job_id**: 배치 작업 식별자
    
    Returns:
        dict: 배치 분석 결과
    """
    try:
        # 탐지 서비스 가져오기
        service = get_detection_service()
        
        # 배치 결과 조회
        result = await service.get_batch_result(job_id)
        
        if result is None:
            raise HTTPException(status_code=404, detail=f"배치 작업 {job_id}의 결과를 찾을 수 없거나 아직 처리 중입니다.")
        
        return result
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.websocket("/stream-live/{stream_id}")
async def stream_live(websocket: WebSocket, stream_id: str, stream_url: str = None, confidence: float = 0.15):
    """
    WebSocket을 통한 실시간 스트리밍 도로 파손 분석
    
    - **stream_id**: 스트림 식별자
    - **stream_url**: 스트리밍 URL
    - **confidence**: 탐지 신뢰도 임계값 (0.0 ~ 1.0)
    """
    await websocket.accept()
    
    try:
        # 파라미터 확인
        if not stream_url:
            params = await websocket.receive_json()
            stream_url = params.get("stream_url")
            confidence = params.get("confidence", confidence)
        
        if not stream_url:
            await websocket.send_json({"error": "스트림 URL이 필요합니다."})
            await websocket.close()
            return
        
        # 탐지 서비스 가져오기
        service = get_detection_service()
        
        # 영상 캡처 시작
        cap = cv2.VideoCapture(stream_url)
        if not cap.isOpened():
            await websocket.send_json({"error": f"스트림을 열 수 없습니다: {stream_url}"})
            await websocket.close()
            return
        
        try:
            # 실시간 처리 및 전송
            while True:
                # 연결 체크
                try:
                    # 비동기 처리 중에 연결 확인 메시지 수신
                    data = await asyncio.wait_for(websocket.receive_text(), timeout=0.01)
                    if data == "stop":
                        break
                except asyncio.TimeoutError:
                    # 타임아웃은 정상 - 연결이 유지되고 있음
                    pass
                
                # 프레임 읽기
                ret, frame = cap.read()
                if not ret:
                    # 영상 끝이나 오류 발생
                    await websocket.send_json({"error": "스트림 종료 또는 프레임을 읽을 수 없습니다."})
                    break
                
                # 탐지 실행
                result = service.process_frame(frame, confidence)
                
                # 결과 이미지 인코딩
                _, buffer = cv2.imencode('.jpg', result['image'])
                img_base64 = base64.b64encode(buffer).decode('utf-8')
                
                # 결과 전송
                await websocket.send_json({
                    "frame": img_base64,
                    "damages": result['damages'],
                    "damage_count": len(result['damages']),
                    "damage_summary": result['damage_summary'],
                    "timestamp": datetime.datetime.now().isoformat()
                })
                
                # 과부하 방지를 위한 대기
                await asyncio.sleep(0.1)  # 초당 최대 10프레임
        
        finally:
            # 자원 정리
            cap.release()
    
    except WebSocketDisconnect:
        # 클라이언트 연결 종료
        print(f"클라이언트 연결 종료: {stream_id}")
    except Exception as e:
        # 오류 처리
        print(f"스트리밍 처리 오류: {e}")
        try:
            await websocket.send_json({"error": str(e)})
        except:
            pass
    finally:
        # 소켓 종료
        try:
            await websocket.close()
        except:
            pass

@router.post("/analyze-stream", response_model=DetectionResponse)
async def analyze_stream(
    stream_url: str = Form(..., description="실시간 스트리밍 URL(HLS)"),
    confidence: float = Form(0.1),
    include_image: bool = Form(True),
    location_lat: Optional[float] = Form(None, description="위도 정보"),
    location_lng: Optional[float] = Form(None, description="경도 정보"),
    stream_id: Optional[str] = Form(None, description="스트림 식별자"),
    sample_interval: int = Form(10, description="샘플링 간격(초)")
):
    """
    실시간 스트리밍에서 도로 파손 탐지 분석 수행
    
    - **stream_url**: 스트리밍 URL (HLS 형식)
    - **confidence**: 탐지 신뢰도 임계값 (0.0 ~ 1.0)
    - **include_image**: 결과 이미지를 Base64로 포함할지 여부
    - **location_lat**: 위치 위도 (선택 사항)
    - **location_lng**: 위치 경도 (선택 사항)
    - **stream_id**: 스트림 식별자 (선택 사항)
    - **sample_interval**: 스트림에서 샘플링할 간격(초)
    
    Returns:
        DetectionResponse: 도로 파손 분석 결과
    """
    try:
        # 위치 정보 설정
        location = None
        if location_lat is not None and location_lng is not None:
            location = {"latitude": location_lat, "longitude": location_lng}
        
        # 탐지 서비스 가져오기
        service = get_detection_service()
        
        # 탐지 수행
        result = await service.analyze_stream(
            stream_url=stream_url,
            confidence=confidence,
            include_image=include_image,
            location=location,
            stream_id=stream_id,
            sample_interval=sample_interval
        )
        
        return result
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/stream-video")
async def stream_processed_video(
    stream_url: str,
    confidence: float = 0.25,
    fps: int = 10
):
    """
    실시간으로 처리된 비디오 스트림 제공 (MJPEG 형식)
    
    - **stream_url**: 스트리밍 URL (HLS, RTSP, HTTP 등)
    - **confidence**: 탐지 신뢰도 임계값 (0.0 ~ 1.0)
    - **fps**: 초당 프레임 수 (기본값: 10)
    
    Returns:
        StreamingResponse: MJPEG 형식으로 인코딩된 실시간 비디오 스트림
    """
    async def generate_frames():
        try:
            # 탐지 서비스 가져오기
            service = get_detection_service()
            
            # 비디오 캡처 시작
            cap = cv2.VideoCapture(stream_url)
            if not cap.isOpened():
                raise HTTPException(status_code=500, detail=f"스트림을 열 수 없습니다: {stream_url}")
            
            frame_interval = 1.0 / fps
            
            try:
                while True:
                    # 프레임 읽기
                    ret, frame = cap.read()
                    if not ret:
                        break
                    
                    # 탐지 실행
                    result = service.process_frame(frame, confidence)
                    processed_frame = result['image']
                    
                    # MJPEG 형식으로 인코딩
                    _, jpeg = cv2.imencode('.jpg', processed_frame)
                    frame_bytes = jpeg.tobytes()
                    
                    # 프레임 전송
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                    
                    # 프레임 간격 조절
                    await asyncio.sleep(frame_interval)
            
            finally:
                # 자원 정리
                cap.release()
                
        except Exception as e:
            print(f"스트리밍 오류: {e}")
            yield f"Error: {str(e)}".encode()
    
    # MJPEG 스트리밍 응답 반환
    return StreamingResponse(
        generate_frames(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )

@router.post("/extract-background")
async def extract_background_from_video(
    file: UploadFile = File(...),
    grid_width: int = Form(6, description="가로 구역 수"),
    grid_height: int = Form(4, description="세로 구역 수"),
    sample_interval: int = Form(1, description="몇 프레임마다 샘플링할지 (1=모든프레임)"),
    duration_seconds: int = Form(20, description="분석할 영상 길이(초)"),
    include_result_image: bool = Form(True, description="결과 이미지를 Base64로 포함할지 여부"),
    include_process_steps: bool = Form(False, description="과정 단계별 이미지 포함 여부 (발표용)")
):
    """
    CCTV 영상에서 차량 없는 배경 도로 이미지 추출
    
    각 구역에서 가장 많이 노출된 픽셀값을 사용하여 
    움직이는 객체(차량 등)가 제거된 깨끗한 배경 이미지를 생성합니다.
    
    - **file**: 분석할 CCTV 영상 파일 (MP4 등)
    - **grid_width**: 가로 구역 분할 수 (기본값: 6)
    - **grid_height**: 세로 구역 분할 수 (기본값: 4) 
    - **sample_interval**: 프레임 샘플링 간격 (기본값: 1)
    - **duration_seconds**: 분석할 영상 길이 (기본값: 20초)
    - **include_result_image**: 결과 이미지 Base64 포함 여부
    - **include_process_steps**: 과정 단계별 이미지 포함 여부 (발표용)
    
    Returns:
        JSON: 배경 추출 결과 및 이미지 (과정 단계 포함 가능)
    """
    try:
        # 임시 파일 저장
        temp_dir = tempfile.mkdtemp()
        temp_path = os.path.join(temp_dir, file.filename)
        
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # 배경 추출 수행
        service = get_detection_service()
        result = await service.extract_background_image(
            video_path=temp_path,
            grid_width=grid_width,
            grid_height=grid_height,
            sample_interval=sample_interval,
            duration_seconds=duration_seconds,
            include_result_image=include_result_image,
            include_process_steps=include_process_steps
        )
        
        # 임시 파일 정리
        shutil.rmtree(temp_dir)
        
        return JSONResponse(content=result)
        
    except Exception as e:
        # 오류 발생 시 임시 파일 정리
        if 'temp_dir' in locals():
            shutil.rmtree(temp_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"배경 추출 중 오류 발생: {str(e)}")

@router.post("/extract-background-stream")
async def extract_background_from_stream(
    stream_url: str = Form(..., description="HLS 또는 RTSP 스트리밍 URL"),
    grid_width: int = Form(6, description="가로 구역 수"),
    grid_height: int = Form(4, description="세로 구역 수"), 
    sample_interval: int = Form(1, description="몇 프레임마다 샘플링할지"),
    duration_seconds: int = Form(20, description="분석할 스트림 길이(초)"),
    include_result_image: bool = Form(True, description="결과 이미지를 Base64로 포함할지 여부")
):
    """
    실시간 스트리밍에서 차량 없는 배경 도로 이미지 추출
    
    HLS나 RTSP 스트리밍에서 실시간으로 배경 이미지를 추출합니다.
    추후 확장성을 위한 엔드포인트입니다.
    
    - **stream_url**: HLS 또는 RTSP 스트리밍 URL
    - **grid_width**: 가로 구역 분할 수 (기본값: 6)
    - **grid_height**: 세로 구역 분할 수 (기본값: 4)
    - **sample_interval**: 프레임 샘플링 간격 (기본값: 1)
    - **duration_seconds**: 분석할 스트림 길이 (기본값: 20초)
    - **include_result_image**: 결과 이미지 Base64 포함 여부
    
    Returns:
        JSON: 배경 추출 결과 및 이미지
    """
    try:
        # 스트리밍 배경 추출 수행
        service = get_detection_service()
        result = await service.extract_background_from_stream(
            stream_url=stream_url,
            grid_width=grid_width,
            grid_height=grid_height,
            sample_interval=sample_interval,
            duration_seconds=duration_seconds,
            include_result_image=include_result_image
        )
        
        return JSONResponse(content=result)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"스트림 배경 추출 중 오류 발생: {str(e)}")
