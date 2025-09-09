from typing import Optional, List
import os

# 간단한 설정 클래스 구현
class Settings:
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "도로 파손 탐지 AI API"
    PROJECT_DESCRIPTION: str = "CCTV 영상 및 이미지에서 도로 파손을 탐지하고 분석 결과를 제공하는 API"
    VERSION: str = "1.0.0"
    
    # 모델 설정
    MODEL_PATH: str = os.getenv("MODEL_PATH", "models/09-08-best-final-model.pt")
    
    # 결과 저장 경로
    RESULTS_DIR: str = os.getenv("RESULTS_DIR", "results")
    
    # CORS 설정 - Spring Boot와의 통신 허용
    BACKEND_CORS_ORIGINS = [
        "http://localhost:8080",
        "http://localhost:3000",
        "https://helios-cctv.com",
        "*"  # 개발 환경에서만 사용, 프로덕션에서는 제거
    ]
    
    # 서버 설정
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    
    # 로깅 설정
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

settings = Settings()
