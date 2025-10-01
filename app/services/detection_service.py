import os
import cv2
import torch
import numpy as np
from PIL import Image
import io
import base64
import time
import json
import datetime
from pathlib import Path
from ultralytics import YOLO
from typing import Dict, List, Optional, Any, Tuple
import asyncio
import uuid
import math

# 파손 유형 정의
DAMAGE_TYPES = {
    0: "pothole",       # 포트홀
    1: "crack",         # 균열
    2: "patch",         # 패치
    3: "manhole",       # 맨홀
    4: "crosswalk",     # 횡단보도
    5: "lane_marking"   # 차선
}

# 파손 심각도 계산 가중치
SEVERITY_WEIGHTS = {
    "pothole": 1.0,
    "crack": 0.7,
    "patch": 0.4,
    "manhole": 0.2,
    "crosswalk": 0.1,
    "lane_marking": 0.1
}

class DetectionService:
    def __init__(self, model_path: str):
        """
        도로 파손 탐지 서비스 초기화
        
        Args:
            model_path (str): YOLO 모델 파일(.pt) 경로
        """
        self.model_path = model_path
        self.model = None
        self.batch_results = {}  # 배치 작업 결과 저장
        self.results_dir = Path('results')
        self.results_dir.mkdir(exist_ok=True)
        self.load_model()
        
    def load_model(self):
        """모델 로드"""
        try:
            if not os.path.exists(self.model_path):
                raise FileNotFoundError(f"Model file not found: {self.model_path}")
            
            # YOLO 모델 로드
            self.model = YOLO(self.model_path)
            print(f"도로 파손 탐지 모델 로드 완료: {self.model_path}")
            
            # 클래스 이름 확인
            print(f"모델 클래스: {self.model.names}")
        except Exception as e:
            print(f"모델 로드 오류: {e}")
            raise
    
    def calculate_damage_area(self, bbox: List[float]) -> float:
        """
        바운딩 박스의 면적 계산
        
        Args:
            bbox (list): 바운딩 박스 좌표 [x1, y1, x2, y2]
            
        Returns:
            float: 면적
        """
        width = bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]
        return width * height
    
    def calculate_severity(self, damage_type: str, confidence: float, area: float, image_area: float) -> str:
        """
        파손의 심각도 계산
        
        Args:
            damage_type (str): 파손 유형
            confidence (float): 신뢰도
            area (float): 파손 면적
            image_area (float): 이미지 전체 면적
            
        Returns:
            str: 심각도 ("high", "medium", "low")
        """
        # 면적 비율 계산 (0.0 ~ 1.0)
        area_ratio = min(1.0, area / image_area)
        
        # 심각도 점수 계산 (0.0 ~ 100.0)
        weight = SEVERITY_WEIGHTS.get(damage_type, 0.5)
        severity_score = (confidence * 0.4 + area_ratio * 0.6) * 100 * weight
        
        # 심각도 등급 분류
        if severity_score >= 60:
            return "high"
        elif severity_score >= 30:
            return "medium"
        else:
            return "low"
    
    def calculate_severity_score(self, damage_type: str, confidence: float, area: float, image_area: float) -> float:
        """
        파손의 심각도 점수 계산 (0-100)
        
        Args:
            damage_type (str): 파손 유형
            confidence (float): 신뢰도
            area (float): 파손 면적
            image_area (float): 이미지 전체 면적
            
        Returns:
            float: 심각도 점수 (0-100)
        """
        area_ratio = min(1.0, area / image_area)
        weight = SEVERITY_WEIGHTS.get(damage_type, 0.5)
        return (confidence * 0.4 + area_ratio * 0.6) * 100 * weight
    
    async def analyze_road_damage(self, image_bytes: bytes, confidence: float = 0.25, 
                                include_image: bool = True, location: Dict = None, 
                                image_id: str = None) -> Dict:
        """
        이미지로부터 도로 파손 탐지 분석 수행
        
        Args:
            image_bytes (bytes): 이미지 바이트 데이터
            confidence (float): 객체 탐지 신뢰도 임계값
            include_image (bool): 결과 이미지를 Base64로 포함할지 여부
            location (dict): 위치 정보 (위도, 경도)
            image_id (str): 이미지 식별자
            
        Returns:
            dict: 파손 탐지 결과 정보
        """
        if self.model is None:
            self.load_model()
            
        try:
            # 이미지 변환
            image = Image.open(io.BytesIO(image_bytes))
            image_np = np.array(image)
            image_area = image.width * image.height
            
            # 이미지 ID 생성 (없는 경우)
            if image_id is None:
                image_id = f"img_{uuid.uuid4().hex[:8]}"
            
            # 탐지 실행
            start_time = time.time()
            results = self.model(image_np, conf=confidence)
            process_time = time.time() - start_time
            
            # 결과 이미지 생성
            img_str = None
            if include_image:
                result_img = results[0].plot()
                buffered = io.BytesIO()
                result_img_pil = Image.fromarray(result_img)
                result_img_pil.save(buffered, format="JPEG")
                img_str = base64.b64encode(buffered.getvalue()).decode('utf-8')
            
            # 결과 포맷팅
            damages = []
            damage_summary = {}
            total_damage_area = 0
            total_severity_score = 0
            
            # 각 탐지 결과 처리
            for result in results:
                boxes = result.boxes
                for i, box in enumerate(boxes):
                    class_id = int(box.cls.item())
                    damage_type = DAMAGE_TYPES.get(class_id, f"unknown_{class_id}")
                    confidence_val = float(box.conf.item())
                    bbox = box.xyxy.tolist()[0]  # [x1, y1, x2, y2]
                    
                    # 면적 계산
                    area = self.calculate_damage_area(bbox)
                    total_damage_area += area
                    
                    # 심각도 계산
                    severity = self.calculate_severity(damage_type, confidence_val, area, image_area)
                    severity_score = self.calculate_severity_score(damage_type, confidence_val, area, image_area)
                    total_severity_score += severity_score
                    
                    # 파손 정보 추가
                    damage_data = {
                        "class_id": class_id,
                        "damage_type": damage_type,
                        "confidence": confidence_val,
                        "bbox": bbox,
                        "severity": severity,
                        "area": area,
                        "severity_score": severity_score
                    }
                    damages.append(damage_data)
                    
                    # 파손 유형별 개수 업데이트
                    damage_summary[damage_type] = damage_summary.get(damage_type, 0) + 1
            
            # 전체 심각도 점수 계산 (100점 만점)
            overall_severity_score = 0
            if damages:
                overall_severity_score = min(100, total_severity_score / len(damages))
            
            return {
                "success": True,
                "message": "도로 파손 탐지 완료",
                "process_time": process_time,
                "timestamp": datetime.datetime.now().isoformat(),
                "image_id": image_id,
                "location": location,
                "damages": damages,
                "damage_count": len(damages),
                "damage_summary": damage_summary,
                "total_damage_area": total_damage_area,
                "severity_score": overall_severity_score,
                "result_image": img_str
            }
            
        except Exception as e:
            print(f"도로 파손 탐지 오류: {e}")
            return {
                "success": False,
                "message": f"도로 파손 탐지 중 오류 발생: {str(e)}",
                "damages": [],
                "damage_count": 0
            }
    
    async def analyze_road_damage_video(self, video_path: str, confidence: float = 0.25,
                                      fps_interval: int = 1, video_id: str = None) -> Dict:
        """
        비디오로부터 도로 파손 탐지 분석 수행
        
        Args:
            video_path (str): 비디오 파일 경로
            confidence (float): 객체 탐지 신뢰도 임계값
            fps_interval (int): 몇 프레임마다 탐지를 수행할지 설정
            video_id (str): 비디오 식별자
            
        Returns:
            dict: 파손 탐지 결과 정보
        """
        if self.model is None:
            self.load_model()
            
        try:
            # 비디오 로드
            if not os.path.exists(video_path):
                raise FileNotFoundError(f"Video file not found: {video_path}")
            
            # 비디오 ID 생성 (없는 경우)
            if video_id is None:
                video_id = f"vid_{uuid.uuid4().hex[:8]}"
                
            # 결과 경로 설정
            save_dir = self.results_dir
            save_path = str(save_dir / f"{video_id}_{Path(video_path).name}")
            
            # 탐지 실행
            start_time = time.time()
            
            # 커스텀 프레임 간격으로 처리하기 위해 직접 비디오 처리
            cap = cv2.VideoCapture(video_path)
            fps = cap.get(cv2.CAP_PROP_FPS)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            image_area = width * height
            
            # 결과 비디오 설정
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            out = cv2.VideoWriter(save_path, fourcc, fps, (width, height))
            
            damages_by_frame = {}
            processed_frames = 0
            damage_timeline = {damage_type: [0] * (total_frames // fps_interval + 1) for damage_type in DAMAGE_TYPES.values()}
            max_severity_frame = 0
            max_severity_score = 0
            
            frame_idx = 0
            while cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    break
                
                # fps_interval에 따라 프레임 처리
                if frame_idx % fps_interval == 0:
                    # 이 프레임에서 탐지 수행
                    results = self.model(frame, conf=confidence)
                    result_frame = results[0].plot()
                    
                    # 이 프레임의 파손 정보 추출
                    frame_damages = []
                    frame_severity_score = 0
                    
                    for result in results:
                        boxes = result.boxes
                        for box in boxes:
                            class_id = int(box.cls.item())
                            damage_type = DAMAGE_TYPES.get(class_id, f"unknown_{class_id}")
                            confidence_val = float(box.conf.item())
                            bbox = box.xyxy.tolist()[0]
                            
                            # 면적 계산
                            area = self.calculate_damage_area(bbox)
                            
                            # 심각도 계산
                            severity = self.calculate_severity(damage_type, confidence_val, area, image_area)
                            severity_score = self.calculate_severity_score(damage_type, confidence_val, area, image_area)
                            frame_severity_score += severity_score
                            
                            # 파손 정보 추가
                            damage_data = {
                                "class_id": class_id,
                                "damage_type": damage_type,
                                "confidence": confidence_val,
                                "bbox": bbox,
                                "severity": severity,
                                "area": area,
                                "frame": frame_idx
                            }
                            frame_damages.append(damage_data)
                            
                            # 타임라인 업데이트
                            timeline_idx = frame_idx // fps_interval
                            if timeline_idx < len(damage_timeline[damage_type]):
                                damage_timeline[damage_type][timeline_idx] += 1
                    
                    # 프레임별 파손 정보 저장
                    damages_by_frame[frame_idx] = frame_damages
                    
                    # 최대 심각도 프레임 업데이트
                    if frame_damages and frame_severity_score > max_severity_score:
                        max_severity_score = frame_severity_score
                        max_severity_frame = frame_idx
                    
                    processed_frames += 1
                else:
                    # 탐지 없이 원본 프레임 사용
                    result_frame = frame
                
                # 결과 비디오에 프레임 쓰기
                out.write(result_frame)
                frame_idx += 1
            
            cap.release()
            out.release()
            process_time = time.time() - start_time
            
            # 모든 프레임의 파손을 합쳐서 요약
            all_damages = []
            damage_summary = {}
            
            for frame_damages in damages_by_frame.values():
                for damage in frame_damages:
                    damage_type = damage["damage_type"]
                    damage_summary[damage_type] = damage_summary.get(damage_type, 0) + 1
                    all_damages.append(damage)
            
            # 평균 심각도 계산
            avg_severity_score = 0
            if all_damages:
                total_severity = sum([self.calculate_severity_score(
                    d["damage_type"], d["confidence"], d["area"], image_area
                ) for d in all_damages])
                avg_severity_score = total_severity / len(all_damages)
            
            return {
                "success": True,
                "message": "비디오 도로 파손 탐지 완료",
                "video_id": video_id,
                "process_time": process_time,
                "damages": all_damages[:100],  # 결과 크기 제한
                "total_frames": total_frames,
                "processed_frames": processed_frames,
                "damage_timeline": damage_timeline,
                "damage_summary": damage_summary,
                "average_severity_score": avg_severity_score,
                "max_severity_frame": max_severity_frame,
                "result_video_path": save_path
            }
            
        except Exception as e:
            print(f"비디오 도로 파손 탐지 오류: {e}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "message": f"비디오 도로 파손 탐지 중 오류 발생: {str(e)}",
                "damages": [],
                "damage_count": 0
            }
    
    async def get_damage_statistics(self, start_date=None, end_date=None, 
                                  damage_type=None, min_severity=None, 
                                  location_range=None) -> Dict:
        """
        저장된 파손 데이터의 통계 정보 조회
        
        Args:
            start_date (str): 시작 날짜 (YYYY-MM-DD 형식)
            end_date (str): 종료 날짜 (YYYY-MM-DD 형식)
            damage_type (str): 파손 유형 필터링
            min_severity (float): 최소 심각도 필터링
            location_range (str): 위치 범위 (형식: lat1,lng1,lat2,lng2)
            
        Returns:
            dict: 파손 통계 정보
        """
        try:
            # 이 예제에서는 실제 DB 연동이 없으므로 더미 데이터 반환
            return {
                "success": True,
                "time_range": {
                    "start_date": start_date or "2025-01-01",
                    "end_date": end_date or datetime.datetime.now().strftime("%Y-%m-%d")
                },
                "total_detections": 1256,
                "damage_counts": {
                    "pothole": 423,
                    "crack": 562,
                    "patch": 186,
                    "manhole": 85
                },
                "severity_distribution": {
                    "high": 287,
                    "medium": 498,
                    "low": 471
                },
                "timeline_data": {
                    "labels": ["2025-07-01", "2025-07-08", "2025-07-15", "2025-07-22", "2025-07-29", "2025-08-05", "2025-08-12", "2025-08-19"],
                    "pothole": [32, 41, 38, 45, 39, 42, 48, 43],
                    "crack": [56, 49, 61, 53, 58, 52, 47, 55],
                    "patch": [18, 21, 15, 19, 22, 17, 20, 24],
                    "manhole": [8, 6, 9, 11, 7, 10, 8, 9]
                },
                "top_locations": [
                    {"lat": 37.5665, "lng": 126.9780, "damage_count": 87, "most_common": "crack"},
                    {"lat": 37.5113, "lng": 127.0980, "damage_count": 76, "most_common": "pothole"},
                    {"lat": 37.4989, "lng": 127.0254, "damage_count": 64, "most_common": "crack"},
                    {"lat": 37.5838, "lng": 126.9671, "damage_count": 58, "most_common": "patch"},
                    {"lat": 37.5276, "lng": 126.8729, "damage_count": 49, "most_common": "pothole"}
                ]
            }
        except Exception as e:
            print(f"통계 조회 오류: {e}")
            return {
                "success": False,
                "message": f"통계 조회 중 오류 발생: {str(e)}"
            }
    
    async def process_batch_analysis(self, file_paths: List[str], confidence: float, 
                                  include_images: bool, job_id: str):
        """
        배치 파일에 대한 도로 파손 분석 수행 (비동기)
        
        Args:
            file_paths (List[str]): 이미지 파일 경로 목록
            confidence (float): 탐지 신뢰도 임계값
            include_images (bool): 결과 이미지를 Base64로 포함할지 여부
            job_id (str): 작업 식별자
        """
        try:
            results = []
            
            for file_path in file_paths:
                try:
                    with open(file_path, "rb") as f:
                        image_bytes = f.read()
                    
                    image_id = Path(file_path).name
                    result = await self.analyze_road_damage(
                        image_bytes=image_bytes,
                        confidence=confidence,
                        include_image=include_images,
                        image_id=image_id
                    )
                    
                    results.append(result)
                    
                except Exception as e:
                    print(f"파일 처리 오류 ({file_path}): {e}")
                    results.append({
                        "success": False,
                        "message": f"파일 처리 중 오류 발생: {str(e)}",
                        "image_id": Path(file_path).name
                    })
            
            # 배치 결과 요약
            total_damage_count = sum(r.get("damage_count", 0) for r in results if r.get("success", False))
            damage_summary = {}
            
            for result in results:
                if result.get("success", False):
                    for damage_type, count in result.get("damage_summary", {}).items():
                        damage_summary[damage_type] = damage_summary.get(damage_type, 0) + count
            
            batch_result = {
                "success": True,
                "job_id": job_id,
                "message": f"{len(results)}개 이미지 처리 완료",
                "processed_count": len(results),
                "success_count": sum(1 for r in results if r.get("success", False)),
                "total_damage_count": total_damage_count,
                "damage_summary": damage_summary,
                "results": results,
                "completed_at": datetime.datetime.now().isoformat()
            }
            
            # 결과 저장
            self.batch_results[job_id] = batch_result
            
            # 결과 파일로 저장 (선택 사항)
            result_path = self.results_dir / f"batch_{job_id}.json"
            with open(result_path, "w", encoding="utf-8") as f:
                json.dump(batch_result, f, ensure_ascii=False, default=str)
            
        except Exception as e:
            print(f"배치 처리 오류: {e}")
            self.batch_results[job_id] = {
                "success": False,
                "job_id": job_id,
                "message": f"배치 처리 중 오류 발생: {str(e)}",
                "completed_at": datetime.datetime.now().isoformat()
            }
    
    async def get_batch_result(self, job_id: str) -> Dict:
        """
        배치 처리 결과 조회
        
        Args:
            job_id (str): 작업 식별자
            
        Returns:
            dict: 배치 처리 결과
        """
        # 메모리에서 결과 조회
        result = self.batch_results.get(job_id)
        
        if result is None:
            # 파일에서 결과 조회 시도
            result_path = self.results_dir / f"batch_{job_id}.json"
            if result_path.exists():
                with open(result_path, "r", encoding="utf-8") as f:
                    result = json.load(f)
        
        return result
        
    async def analyze_stream(self, stream_url: str, confidence: float = 0.25, 
                           include_image: bool = True, location: dict = None, 
                           stream_id: str = None, sample_interval: int = 10) -> dict:
        """
        실시간 스트리밍에서 도로 파손 탐지 분석 수행
        
        Args:
            stream_url (str): 스트리밍 URL (HLS 형식)
            confidence (float): 탐지 신뢰도 임계값
            include_image (bool): 결과 이미지를 Base64로 포함할지 여부
            location (dict): 위치 정보
            stream_id (str): 스트림 식별자
            sample_interval (int): 샘플링 간격(초)
            
        Returns:
            dict: 파손 탐지 결과 정보
        """
        if self.model is None:
            self.load_model()
            
        try:
            import cv2
            import time
            import requests
            
            # 스트림 ID 생성 (없는 경우)
            if stream_id is None:
                stream_id = f"stream_{uuid.uuid4().hex[:8]}"
                
            print(f"스트림 URL 접근 시도: {stream_url}")
            
            # OpenCV로 스트림 처리
            cap = cv2.VideoCapture(stream_url)
            
            # 연결 확인
            if not cap.isOpened():
                raise Exception(f"스트림을 열 수 없습니다: {stream_url}")
            
            # 프레임 읽기
            ret, frame = cap.read()
            if not ret:
                raise Exception(f"스트림에서 프레임을 읽을 수 없습니다: {stream_url}")
            
            # 이미지 인코딩
            _, buffer = cv2.imencode(".jpg", frame)
            image_bytes = buffer.tobytes()
            
            # 자원 해제
            cap.release()
            
            # 기존 이미지 분석 함수로 처리
            result = await self.analyze_road_damage(
                image_bytes=image_bytes,
                confidence=confidence,
                include_image=include_image,
                location=location,
                image_id=stream_id
            )
            
            # 결과에 스트림 정보 추가
            result["stream_url"] = stream_url
            result["stream_id"] = stream_id
            result["sample_time"] = datetime.datetime.now().isoformat()
            
            return result
            
        except Exception as e:
            print(f"스트리밍 분석 오류: {e}")
            return {
                "success": False,
                "message": f"스트리밍 분석 중 오류 발생: {str(e)}",
                "stream_url": stream_url,
                "stream_id": stream_id,
                "damages": [],
                "damage_count": 0
            }
            
    def process_frame(self, frame, confidence: float = 0.25) -> dict:
        """
        단일 프레임에 대한 도로 파손 탐지 처리 (동기 방식)
        
        Args:
            frame: OpenCV 이미지 프레임
            confidence: 탐지 신뢰도 임계값
            
        Returns:
            dict: 프레임 처리 결과 및 탐지 정보
        """
        if self.model is None:
            self.load_model()
            
        try:
            # 이미지 크기 계산
            height, width = frame.shape[:2]
            image_area = height * width
            
            # 탐지 실행
            results = self.model(frame, conf=confidence)
            
            # 결과 이미지 생성
            result_img = results[0].plot()
            
            # 결과 포맷팅
            damages = []
            damage_summary = {}
            
            # 각 탐지 결과 처리
            for result in results:
                boxes = result.boxes
                for i, box in enumerate(boxes):
                    class_id = int(box.cls.item())
                    damage_type = DAMAGE_TYPES.get(class_id, f"unknown_{class_id}")
                    confidence_val = float(box.conf.item())
                    bbox = box.xyxy.tolist()[0]  # [x1, y1, x2, y2]
                    
                    # 면적 계산
                    area = self.calculate_damage_area(bbox)
                    
                    # 심각도 계산
                    severity = self.calculate_severity(damage_type, confidence_val, area, image_area)
                    severity_score = self.calculate_severity_score(damage_type, confidence_val, area, image_area)
                    
                    # 파손 정보 추가
                    damage_data = {
                        "class_id": class_id,
                        "damage_type": damage_type,
                        "confidence": confidence_val,
                        "bbox": bbox,
                        "severity": severity,
                        "area": area,
                        "severity_score": severity_score
                    }
                    damages.append(damage_data)
                    
                    # 파손 유형별 개수 업데이트
                    damage_summary[damage_type] = damage_summary.get(damage_type, 0) + 1
            
            return {
                "image": result_img,
                "damages": damages,
                "damage_summary": damage_summary
            }
            
        except Exception as e:
            print(f"프레임 처리 오류: {e}")
            # 오류 발생 시 원본 이미지 반환
            return {
                "image": frame,
                "damages": [],
                "damage_summary": {}
            }

    async def extract_background_image(
        self, 
        video_path: str,
        grid_width: int = 6,
        grid_height: int = 4,
        sample_interval: int = 1,
        duration_seconds: int = 20,
        include_result_image: bool = True,
        include_process_steps: bool = True
    ) -> Dict[str, Any]:
        """
        비디오에서 배경 이미지 추출 (과정 시각화 포함)
        
        Args:
            video_path: 비디오 파일 경로
            grid_width: 가로 구역 수
            grid_height: 세로 구역 수  
            sample_interval: 프레임 샘플링 간격
            duration_seconds: 분석할 길이(초)
            include_result_image: 결과 이미지 포함 여부
            include_process_steps: 과정 시각화 이미지 포함 여부
            
        Returns:
            Dict: 배경 추출 결과
        """
        try:
            # 비디오 열기
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                raise Exception(f"비디오를 열 수 없습니다: {video_path}")
            
            # 비디오 정보 가져오기
            fps = int(cap.get(cv2.CAP_PROP_FPS))
            total_frames = min(int(cap.get(cv2.CAP_PROP_FRAME_COUNT)), fps * duration_seconds)
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            
            print(f"비디오 정보: {width}x{height}, {fps}fps, {total_frames}프레임 분석")
            
            # 구역별 크기 계산
            grid_w = width // grid_width
            grid_h = height // grid_height
            
            # 각 구역별 픽셀값 누적을 위한 배열 (메모리 효율적)
            # [grid_y][grid_x][pixel_values] 형태로 저장
            grid_pixels = [[[] for _ in range(grid_width)] for _ in range(grid_height)]
            
            processed_frames = 0
            frame_count = 0
            
            # 과정 시각화를 위한 샘플 프레임들 저장
            sample_frames = []
            progress_steps = []
            
            print("프레임 처리 시작...")
            while frame_count < total_frames:
                ret, frame = cap.read()
                if not ret:
                    break
                
                # 샘플링 간격에 따라 프레임 건너뛰기
                if frame_count % sample_interval == 0:
                    # 발표용으로 첫 번째, 중간, 마지막 프레임들 저장
                    if include_process_steps and (processed_frames == 0 or 
                                                processed_frames == total_frames // (2 * sample_interval) or
                                                processed_frames == total_frames // sample_interval - 1):
                        sample_frames.append(frame.copy())
                    
                    # 각 구역별로 프레임 분할하여 처리
                    for grid_y in range(grid_height):
                        for grid_x in range(grid_width):
                            # 구역 좌표 계산
                            start_y = grid_y * grid_h
                            end_y = min((grid_y + 1) * grid_h, height)
                            start_x = grid_x * grid_w  
                            end_x = min((grid_x + 1) * grid_w, width)
                            
                            # 해당 구역의 픽셀값들 추출
                            region = frame[start_y:end_y, start_x:end_x]
                            grid_pixels[grid_y][grid_x].append(region)
                    
                    processed_frames += 1
                    if processed_frames % 50 == 0:
                        print(f"처리된 프레임: {processed_frames}")
                
                frame_count += 1
            
            cap.release()
            
            print("배경 이미지 생성 중...")
            # 각 구역에서 중간값으로 배경 계산
            background = np.zeros((height, width, 3), dtype=np.uint8)
            
            # 그리드 시각화를 위한 이미지 생성
            grid_overlay = np.zeros((height, width, 3), dtype=np.uint8)
            
            # 과정 시각화를 위한 단계별 배경 이미지들
            step_backgrounds = []
            
            for grid_y in range(grid_height):
                for grid_x in range(grid_width):
                    if grid_pixels[grid_y][grid_x]:
                        # 해당 구역의 모든 프레임에서 중간값 계산
                        region_stack = np.array(grid_pixels[grid_y][grid_x])
                        median_region = np.median(region_stack, axis=0).astype(np.uint8)
                        
                        # 배경 이미지에 적용
                        start_y = grid_y * grid_h
                        end_y = min((grid_y + 1) * grid_h, height)
                        start_x = grid_x * grid_w
                        end_x = min((grid_x + 1) * grid_w, width)
                        
                        background[start_y:end_y, start_x:end_x] = median_region
                        
                        # 과정 시각화: 각 구역이 완성될 때마다 중간 결과 저장
                        if include_process_steps and ((grid_y * grid_width + grid_x) % 4 == 0):
                            step_bg = background.copy()
                            # 아직 처리되지 않은 구역들을 회색으로 표시
                            for y in range(grid_height):
                                for x in range(grid_width):
                                    if y * grid_width + x > grid_y * grid_width + grid_x:
                                        sy = y * grid_h
                                        ey = min((y + 1) * grid_h, height)
                                        sx = x * grid_w
                                        ex = min((x + 1) * grid_w, width)
                                        step_bg[sy:ey, sx:ex] = [128, 128, 128]  # 회색
                            step_backgrounds.append(step_bg.copy())
                        
                        # 그리드 경계선 그리기 (시각화용)
                        cv2.rectangle(grid_overlay, (start_x, start_y), (end_x-1, end_y-1), 
                                    (0, 255, 0), 2)  # 초록색 경계선
                        
                        # 그리드 번호 표시
                        grid_num = grid_y * grid_width + grid_x
                        cv2.putText(grid_overlay, f"{grid_num}", 
                                  (start_x + 10, start_y + 30),
                                  cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)
            
            # 그리드가 표시된 최종 이미지 생성
            background_with_grid = background.copy()
            background_with_grid = cv2.addWeighted(background_with_grid, 0.8, grid_overlay, 0.2, 0)
            
            # 결과 준비
            result = {
                "success": True,
                "processed_frames": processed_frames,
                "total_frames": total_frames,
                "video_info": {
                    "width": width,
                    "height": height,
                    "fps": fps,
                    "duration_seconds": duration_seconds
                },
                "grid_info": {
                    "grid_width": grid_width,
                    "grid_height": grid_height,
                    "region_width": grid_w,
                    "region_height": grid_h
                },
                "processing_time": time.time()
            }
            
            # 결과 이미지 포함
            if include_result_image:
                # 1. 깨끗한 배경 이미지 (원본)
                _, img_encoded = cv2.imencode('.jpg', background)
                img_base64 = base64.b64encode(img_encoded).decode('utf-8')
                result["background_image"] = img_base64
                
                # 2. 그리드가 표시된 배경 이미지 (과정 보기용)
                _, grid_encoded = cv2.imencode('.jpg', background_with_grid)
                grid_base64 = base64.b64encode(grid_encoded).decode('utf-8')
                result["background_with_grid"] = grid_base64
                
                # 3. 그리드 오버레이만 (구역 분할 시각화)
                grid_only = np.zeros((height, width, 3), dtype=np.uint8)
                grid_only = cv2.addWeighted(grid_only, 0.3, grid_overlay, 0.7, 0)
                _, overlay_encoded = cv2.imencode('.jpg', grid_only)
                overlay_base64 = base64.b64encode(overlay_encoded).decode('utf-8')
                result["grid_overlay"] = overlay_base64
                
                # 4. 과정 시각화 이미지들 (발표용)
                if include_process_steps:
                    # 샘플 프레임들
                    result["sample_frames"] = []
                    for i, frame in enumerate(sample_frames):
                        _, frame_encoded = cv2.imencode('.jpg', frame)
                        frame_base64 = base64.b64encode(frame_encoded).decode('utf-8')
                        result["sample_frames"].append({
                            "step": i + 1,
                            "description": f"원본 프레임 {i + 1}",
                            "image": frame_base64
                        })
                    
                    # 배경 생성 단계별 이미지들
                    result["process_steps"] = []
                    for i, step_bg in enumerate(step_backgrounds):
                        _, step_encoded = cv2.imencode('.jpg', step_bg)
                        step_base64 = base64.b64encode(step_encoded).decode('utf-8')
                        completed_regions = (i + 1) * 4
                        result["process_steps"].append({
                            "step": i + 1,
                            "description": f"구역 {completed_regions}개 완성",
                            "image": step_base64
                        })
                    
                    # 전/후 비교 이미지 생성
                    if sample_frames:
                        # 첫 번째 프레임과 최종 배경 이미지 비교
                        first_frame = sample_frames[0]
                        comparison = np.hstack([first_frame, background])
                        
                        # 비교 텍스트 추가
                        cv2.putText(comparison, "BEFORE (Original Frame)", 
                                  (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                        cv2.putText(comparison, "AFTER (Background Extracted)", 
                                  (width + 10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                        
                        _, comp_encoded = cv2.imencode('.jpg', comparison)
                        comp_base64 = base64.b64encode(comp_encoded).decode('utf-8')
                        result["comparison_image"] = comp_base64
            
            # 배경 이미지 파일들로 저장
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # 원본 배경 저장
            result_filename = f"background_{timestamp}.jpg"
            result_path = self.results_dir / result_filename
            cv2.imwrite(str(result_path), background)
            result["saved_path"] = str(result_path)
            
            # 그리드 표시된 배경 저장
            grid_filename = f"background_grid_{timestamp}.jpg"
            grid_path = self.results_dir / grid_filename
            cv2.imwrite(str(grid_path), background_with_grid)
            result["saved_grid_path"] = str(grid_path)
            
            print(f"배경 추출 완료: {result_path}")
            return result
            
        except Exception as e:
            print(f"배경 추출 오류: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def extract_background_from_stream(
        self,
        stream_url: str,
        grid_width: int = 6,
        grid_height: int = 4,
        sample_interval: int = 1,
        duration_seconds: int = 20,
        include_result_image: bool = True
    ) -> Dict[str, Any]:
        """
        HLS 스트리밍에서 배경 이미지 추출
        
        Args:
            stream_url: HLS 스트리밍 URL
            grid_width: 가로 구역 수
            grid_height: 세로 구역 수
            sample_interval: 프레임 샘플링 간격
            duration_seconds: 분석할 길이(초)
            include_result_image: 결과 이미지 포함 여부
            
        Returns:
            Dict: 배경 추출 결과
        """
        try:
            print(f"스트림 URL 접근 시도: {stream_url}")
            
            cap = cv2.VideoCapture(stream_url)
            if not cap.isOpened():
                raise Exception(f"HLS 스트림을 열 수 없습니다: {stream_url}")
            
            # 스트림 정보 확인
            fps = cap.get(cv2.CAP_PROP_FPS)
            if fps <= 0:
                fps = 25  # 기본값 설정
            
            print(f"스트림 FPS: {fps}, 수집 시간: {duration_seconds}초")
            
            # 수집할 총 프레임 수 계산
            total_frames_needed = int(fps * duration_seconds)
            sample_frames = max(1, total_frames_needed // (grid_width * grid_height))
            
            print(f"총 필요 프레임: {total_frames_needed}, 샘플링 프레임: {sample_frames}")
            
            frames = []
            frame_count = 0
            collected_count = 0
            start_time = time.time()
            
            # 지정된 시간 동안 프레임 수집
            while True:
                ret, frame = cap.read()
                if not ret:
                    print("프레임 읽기 실패 또는 스트림 종료")
                    break
                
                # 경과 시간 체크
                elapsed_time = time.time() - start_time
                if elapsed_time >= duration_seconds:
                    print(f"수집 완료: {elapsed_time:.1f}초 경과")
                    break
                
                # 샘플링 간격에 따라 프레임 저장
                if frame_count % sample_interval == 0:
                    frames.append(frame.copy())
                    collected_count += 1
                    
                    # 진행상황 출력 (매 초마다)
                    if collected_count % max(1, int(fps)) == 0:
                        print(f"진행: {elapsed_time:.1f}/{duration_seconds}초, 수집된 프레임: {collected_count}")
                
                frame_count += 1
                
                # 너무 많은 프레임이 수집되지 않도록 제한
                if collected_count >= total_frames_needed:
                    print(f"최대 프레임 수집 완료: {collected_count}")
                    break
                
                # 비동기 처리를 위한 짧은 대기
                if frame_count % 10 == 0:
                    await asyncio.sleep(0.001)
            
            cap.release()
            
            if not frames:
                raise Exception("수집된 프레임이 없습니다")
            
            print(f"총 {len(frames)}개 프레임 수집 완료")
            
            # 배경 추출 로직 (기존 extract_background와 동일)
            frame_height, frame_width = frames[0].shape[:2]
            grid_rows = grid_height
            grid_cols = grid_width
            
            tile_height = frame_height // grid_rows
            tile_width = frame_width // grid_cols
            
            background = np.zeros((frame_height, frame_width, 3), dtype=np.uint8)
            
            # 각 구역별로 배경 추출
            for row in range(grid_rows):
                for col in range(grid_cols):
                    y1 = row * tile_height
                    y2 = (row + 1) * tile_height if row < grid_rows - 1 else frame_height
                    x1 = col * tile_width
                    x2 = (col + 1) * tile_width if col < grid_cols - 1 else frame_width
                    
                    # 해당 구역의 모든 프레임에서 타일 추출
                    tiles = []
                    for frame in frames:
                        tile = frame[y1:y2, x1:x2]
                        tiles.append(tile)
                    
                    if tiles:
                        # 중위값으로 배경 계산
                        tiles_array = np.array(tiles)
                        median_tile = np.median(tiles_array, axis=0).astype(np.uint8)
                        background[y1:y2, x1:x2] = median_tile
            
            result = {
                "success": True,
                "background_extracted": True,
                "frames_processed": len(frames),
                "grid_size": f"{grid_width}x{grid_height}",
                "processing_time": time.time() - start_time,
                "duration_seconds": duration_seconds
            }
            
            # 결과 이미지 포함
            if include_result_image:
                _, buffer = cv2.imencode('.jpg', background, [cv2.IMWRITE_JPEG_QUALITY, 85])
                background_base64 = base64.b64encode(buffer).decode('utf-8')
                result["background_image"] = background_base64
            
            return result
            
        except Exception as e:
            print(f"HLS 스트림 배경 추출 오류: {e}")
            return {
                "success": False,
                "error": str(e)
            }
