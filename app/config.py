"""
환경변수 설정 (pydantic-settings)
"""
try:
    from pydantic_settings import BaseSettings
except ImportError:
    # pydantic v1 호환성
    from pydantic import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """애플리케이션 설정"""
    
    # Redis 설정
    REDIS_URL: str = "redis://localhost:6379"
    REDIS_PASSWORD: Optional[str] = None
    REDIS_STREAM: str = "stream:preprocess"
    REDIS_GROUP: str = "workers"
    REDIS_BLOCK_MS: int = 5000
    REDIS_BATCH_COUNT: int = 20
    REDIS_VISIBILITY_TIMEOUT: int = 300
    REDIS_MAX_RETRY: int = 3
    REDIS_DLQ_STREAM: str = "stream:preprocess:dlq"
    
    # 동시성 설정
    MAX_CONCURRENCY: int = 2
    GPU_MEMORY_GUARD: bool = True
    
    # Swift (OpenStack Object Storage) 설정
    OS_AUTH_URL: Optional[str] = None
    OS_USERNAME: Optional[str] = None
    OS_PASSWORD: Optional[str] = None
    OS_PROJECT_NAME: Optional[str] = None
    OS_REGION_NAME: Optional[str] = None
    SWIFT_CONTAINER: Optional[str] = None
    SWIFT_UPLOAD_PREFIX: str = "preprocess/"
    
    # 기존 FastAPI 설정 (main.py에서 import)
    PROJECT_NAME: str = "Helios CCTV AI API"
    PROJECT_DESCRIPTION: str = "도로 파손 탐지 및 CCTV 분석 API"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    BACKEND_CORS_ORIGINS: list = ["*"]
    
    class Config:
        env_file = ".env"
        case_sensitive = True


# 싱글톤 설정 인스턴스
settings = Settings()
