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
                "timestamp": datetime.datetime.now(),
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
