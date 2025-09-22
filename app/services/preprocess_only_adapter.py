"""
전처리 전용 어댑터 - 배경 추출만 수행
"""
import tempfile
import shutil
import uuid
import os
import json
import base64
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any
from app.services.detection_service import DetectionService

logger = logging.getLogger(__name__)


class PreprocessAdapter:
    """HLS 스트림에서 배경 추출만 수행하는 전처리 어댑터"""
    
    def __init__(self):
        self._detection_service = None
    
    def _get_detection_service(self) -> DetectionService:
        """탐지 서비스 가져오기 (지연 초기화)"""
        if self._detection_service is None:
            from app.api.endpoints.detection import get_detection_service
            self._detection_service = get_detection_service()
        return self._detection_service
    
    async def run_preprocess_from_hls(self, hls_url: str, sec: int, *, cctv_id: str) -> Dict[str, Any]:
        """
        HLS 스트림에서 배경 추출만 수행 (AI 분석 제외)
        
        Args:
            hls_url: HLS 스트리밍 URL
            sec: 처리할 시간(초)
            cctv_id: CCTV 식별자
            
        Returns:
            dict: {"artifacts": [...], "meta": {...}, "temp_dir": "..."} 형태
        """
        job_id = str(uuid.uuid4())
        temp_dir = None
        
        try:
            # 임시 작업 디렉터리 생성
            temp_dir = tempfile.mkdtemp(prefix=f"preprocess_{cctv_id}_{job_id}_")
            logger.info(f"전처리 시작 (배경 추출만): cctv_id={cctv_id}, job_id={job_id}, hls={hls_url}, sec={sec}")
            
            service = self._get_detection_service()
            artifacts = []
            meta = {
                "cctv_id": cctv_id,
                "job_id": job_id,
                "hls_url": hls_url,
                "duration_seconds": sec,
                "processing_timestamp": None,
                "background_extracted": False,
                "processing_mode": "preprocessing_only"
            }
            
            # 1. HLS 연결 테스트
            try:
                logger.info(f"HLS 연결 테스트: {hls_url}")
                import cv2
                cap = cv2.VideoCapture(hls_url)
                if not cap.isOpened():
                    raise ValueError(f"HLS 스트림에 연결할 수 없습니다: {hls_url}")
                
                # 첫 번째 프레임 읽기 테스트
                ret, frame = cap.read()
                cap.release()
                
                if not ret or frame is None:
                    raise ValueError(f"HLS 스트림에서 프레임을 읽을 수 없습니다: {hls_url}")
                
                logger.info(f"HLS 연결 성공: {hls_url}")
                meta["hls_accessible"] = True
                
            except Exception as e:
                logger.error(f"HLS 연결 실패: {e}")
                meta["hls_connection_error"] = str(e)
                meta["hls_accessible"] = False
                
                # 오류 정보 파일 생성
                error_path = os.path.join(temp_dir, "hls_error.json")
                with open(error_path, "w", encoding="utf-8") as f:
                    json.dump({
                        "error": str(e),
                        "hls_url": hls_url,
                        "timestamp": datetime.now().isoformat(),
                        "cctv_id": cctv_id,
                        "job_id": job_id
                    }, f, ensure_ascii=False, indent=2)
                
                artifacts.append({
                    "type": "error_log",
                    "path": error_path,
                    "filename": "hls_error.json",
                    "description": "HLS 연결 오류 정보"
                })
                
                # HLS 연결 실패 시 처리 중단하고 오류 결과 반환
                meta["processing_timestamp"] = datetime.now().isoformat()
                meta["processing_status"] = "failed_hls_connection"
                
                final_meta_path = os.path.join(temp_dir, "process_meta.json")
                with open(final_meta_path, "w", encoding="utf-8") as f:
                    json.dump(meta, f, ensure_ascii=False, indent=2)
                
                artifacts.append({
                    "type": "process_metadata",
                    "path": final_meta_path,
                    "filename": "process_meta.json",
                    "description": "전체 처리 메타데이터 (HLS 연결 실패)"
                })
                
                # HLS 연결 실패여도 결과는 반환 (오류 정보 포함)
                return {
                    "artifacts": artifacts,
                    "meta": meta,
                    "temp_dir": temp_dir
                }
            
            # 2. 배경 추출만 수행
            try:
                logger.info(f"배경 추출 시작: {hls_url}")
                background_result = await service.extract_background_from_stream(
                    stream_url=hls_url,
                    grid_width=6,
                    grid_height=4,
                    sample_interval=1,
                    duration_seconds=sec,
                    include_result_image=True
                )
                
                if background_result.get("success"):
                    # 배경 이미지 저장
                    background_path = os.path.join(temp_dir, "background.jpg")
                    if background_result.get("background_image"):
                        with open(background_path, "wb") as f:
                            f.write(base64.b64decode(background_result["background_image"]))
                        
                        artifacts.append({
                            "type": "background_image",
                            "path": background_path,
                            "filename": "background.jpg",
                            "description": "추출된 배경 이미지"
                        })
                        meta["background_extracted"] = True
                        logger.info(f"배경 추출 완료: {background_path}")
                
                # 배경 추출 메타데이터 저장
                meta_path = os.path.join(temp_dir, "background_meta.json")
                with open(meta_path, "w", encoding="utf-8") as f:
                    json.dump(background_result, f, ensure_ascii=False, indent=2)
                
                artifacts.append({
                    "type": "metadata",
                    "path": meta_path,
                    "filename": "background_meta.json",
                    "description": "배경 추출 메타데이터"
                })
                
            except Exception as e:
                logger.error(f"배경 추출 실패: {e}")
                meta["background_error"] = str(e)
                meta["background_extracted"] = False
                
                # 배경 추출 실패 정보를 파일로 저장
                bg_error_path = os.path.join(temp_dir, "background_error.json")
                with open(bg_error_path, "w", encoding="utf-8") as f:
                    json.dump({
                        "error": str(e),
                        "stage": "background_extraction",
                        "timestamp": datetime.now().isoformat()
                    }, f, ensure_ascii=False, indent=2)
                
                artifacts.append({
                    "type": "error_log",
                    "path": bg_error_path,
                    "filename": "background_error.json",
                    "description": "배경 추출 오류 정보"
                })
            
            # 3. 전처리 완료 (AI 분석 생략)
            logger.info(f"전처리 완료 (배경 추출만): cctv_id={cctv_id}")
            
            # 최종 메타데이터 생성
            meta["processing_timestamp"] = datetime.now().isoformat()
            meta["processing_status"] = "success" if meta["background_extracted"] else "partial_success"
            
            # 최종 메타데이터 저장
            final_meta_path = os.path.join(temp_dir, "process_meta.json")
            with open(final_meta_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)
            
            artifacts.append({
                "type": "process_metadata",
                "path": final_meta_path,
                "filename": "process_meta.json",
                "description": "전체 처리 메타데이터 (전처리만)"
            })
            
            logger.info(f"전처리 작업 완료: artifacts={len(artifacts)}개")
            return {
                "artifacts": artifacts,
                "meta": meta,
                "temp_dir": temp_dir
            }
            
        except Exception as e:
            logger.error(f"전처리 실패: cctv_id={cctv_id}, job_id={job_id}, 오류: {e}")
            # 임시 디렉터리 정리
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
            raise


# 싱글톤 인스턴스
_preprocess_adapter = None

def get_preprocess_adapter() -> PreprocessAdapter:
    """전처리 어댑터 싱글톤 가져오기"""
    global _preprocess_adapter
    if _preprocess_adapter is None:
        _preprocess_adapter = PreprocessAdapter()
    return _preprocess_adapter
