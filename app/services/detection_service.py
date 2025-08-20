import os
import cv2
import torch
import numpy as np
from PIL import Image
import io
import base64
import time
from pathlib import Path
from ultralytics import YOLO

class DetectionService:
    def __init__(self, model_path: str):
        """
        YOLO 객체 탐지 서비스 초기화
        
        Args:
            model_path (str): YOLO 모델 파일(.pt) 경로
        """
        self.model_path = model_path
        self.model = None
        self.load_model()
        
    def load_model(self):
        """모델 로드"""
        try:
            if not os.path.exists(self.model_path):
                raise FileNotFoundError(f"Model file not found: {self.model_path}")
            
            # YOLO 모델 로드
            self.model = YOLO(self.model_path)
            print(f"모델 로드 완료: {self.model_path}")
        except Exception as e:
            print(f"모델 로드 오류: {e}")
            raise
    
    async def detect_from_image(self, image_bytes: bytes, confidence: float = 0.25):
        """
        이미지로부터 객체 탐지 수행
        
        Args:
            image_bytes (bytes): 이미지 바이트 데이터
            confidence (float): 객체 탐지 신뢰도 임계값
            
        Returns:
            dict: 탐지 결과 정보
        """
        if self.model is None:
            self.load_model()
            
        try:
            # 이미지 변환
            image = Image.open(io.BytesIO(image_bytes))
            
            # 탐지 실행
            start_time = time.time()
            results = self.model(image, conf=confidence)
            process_time = time.time() - start_time
            
            # 결과 이미지 생성
            result_img = results[0].plot()
            buffered = io.BytesIO()
            result_img_pil = Image.fromarray(result_img)
            result_img_pil.save(buffered, format="JPEG")
            img_str = base64.b64encode(buffered.getvalue()).decode('utf-8')
            
            # 결과 포맷팅
            detections = []
            for result in results:
                boxes = result.boxes
                for i, box in enumerate(boxes):
                    data = {
                        "class_id": int(box.cls.item()),
                        "class_name": result.names[int(box.cls.item())],
                        "confidence": float(box.conf.item()),
                        "bbox": box.xyxy.tolist()[0]  # [x1, y1, x2, y2]
                    }
                    detections.append(data)
            
            return {
                "success": True,
                "message": "Detection completed",
                "process_time": process_time,
                "detections": detections,
                "count": len(detections),
                "result_image": img_str
            }
            
        except Exception as e:
            print(f"탐지 오류: {e}")
            return {
                "success": False,
                "message": f"Error during detection: {str(e)}",
                "detections": [],
                "count": 0
            }
    
    async def detect_from_video(self, video_path: str, confidence: float = 0.25, save_path: str = None):
        """
        비디오로부터 객체 탐지 수행
        
        Args:
            video_path (str): 비디오 파일 경로
            confidence (float): 객체 탐지 신뢰도 임계값
            save_path (str, optional): 결과 비디오 저장 경로
            
        Returns:
            dict: 탐지 결과 정보
        """
        if self.model is None:
            self.load_model()
            
        try:
            # 비디오 로드
            if not os.path.exists(video_path):
                raise FileNotFoundError(f"Video file not found: {video_path}")
                
            # 결과 경로 설정
            if save_path is None:
                save_dir = Path('results')
                save_dir.mkdir(exist_ok=True)
                save_path = str(save_dir / Path(video_path).name)
            
            # 탐지 실행
            start_time = time.time()
            results = self.model(video_path, conf=confidence, save=True, project='results')
            process_time = time.time() - start_time
            
            # 결과 포맷팅 (마지막 프레임의 결과만 반환)
            detections = []
            for result in results:
                boxes = result.boxes
                for i, box in enumerate(boxes):
                    data = {
                        "class_id": int(box.cls.item()),
                        "class_name": result.names[int(box.cls.item())],
                        "confidence": float(box.conf.item()),
                        "bbox": box.xyxy.tolist()[0]  # [x1, y1, x2, y2]
                    }
                    detections.append(data)
            
            # 결과 비디오 경로
            result_videos = list(Path('results').glob(f"*{Path(video_path).stem}*"))
            result_video_path = str(result_videos[0]) if result_videos else None
            
            return {
                "success": True,
                "message": "Video detection completed",
                "process_time": process_time,
                "detections": detections,  # 마지막 프레임의 탐지 결과
                "total_frames": len(results),
                "result_video_path": result_video_path
            }
            
        except Exception as e:
            print(f"비디오 탐지 오류: {e}")
            return {
                "success": False,
                "message": f"Error during video detection: {str(e)}",
                "detections": [],
                "count": 0
            }
