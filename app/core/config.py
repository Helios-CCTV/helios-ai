from typing import Optional, List
import os

# 간단한 설정 클래스 구현
class Settings:
    def __init__(self):
        self.API_V1_STR: str = "/api/v1"
        self.PROJECT_NAME: str = "도로 파손 탐지 AI API"
        self.PROJECT_DESCRIPTION: str = "CCTV 영상 및 이미지에서 도로 파손을 탐지하고 분석 결과를 제공하는 API"
        self.VERSION: str = "1.0.0"
        
        # 모델 설정
        self.MODEL_PATH: str = os.getenv("MODEL_PATH", "models/09-08-best-final-model.pt")
        
        # 결과 저장 경로
        self.RESULTS_DIR: str = os.getenv("RESULTS_DIR", "results")
        
        # CORS 설정 - Spring Boot와의 통신 허용
        self.BACKEND_CORS_ORIGINS = [
            "http://localhost:8080",
            "http://localhost:3000",
            "https://helios-cctv.com",
            "*"  # 개발 환경에서만 사용, 프로덕션에서는 제거
        ]
        
        # 서버 설정
        self.HOST: str = os.getenv("HOST", "0.0.0.0")
        self.PORT: int = int(os.getenv("PORT", "8000"))
        
        # 로깅 설정
        self.LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
        
        # Redis Stream 설정
        self.REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379")
        self.REDIS_PASSWORD: str = os.getenv("REDIS_PASSWORD", "")
        self.REDIS_STREAM: str = os.getenv("REDIS_STREAM", "stream:preprocess")
        self.REDIS_GROUP: str = os.getenv("REDIS_GROUP", "workers")
        self.REDIS_BLOCK_MS: int = int(os.getenv("REDIS_BLOCK_MS", "5000"))
        self.REDIS_BATCH_COUNT: int = int(os.getenv("REDIS_BATCH_COUNT", "20"))
        self.REDIS_VISIBILITY_TIMEOUT: int = int(os.getenv("REDIS_VISIBILITY_TIMEOUT", "300"))
        self.REDIS_MAX_RETRY: int = int(os.getenv("REDIS_MAX_RETRY", "3"))
        self.REDIS_DLQ_STREAM: str = os.getenv("REDIS_DLQ_STREAM", "stream:preprocess:dlq")
        
        # 동시성 설정
        self.MAX_CONCURRENCY: int = int(os.getenv("MAX_CONCURRENCY", "2"))
        self.GPU_MEMORY_GUARD: bool = os.getenv("GPU_MEMORY_GUARD", "true").lower() == "true"
        
        # OpenStack Swift 설정
        self.OS_AUTH_URL: str = os.getenv("OS_AUTH_URL", "")
        self.OS_USERNAME: str = os.getenv("OS_USERNAME", "")
        self.OS_PASSWORD: str = os.getenv("OS_PASSWORD", "")
        self.OS_PROJECT_NAME: str = os.getenv("OS_PROJECT_NAME", "")
        self.OS_USER_DOMAIN_NAME: str = os.getenv("OS_USER_DOMAIN_NAME", "Default")
        self.OS_PROJECT_DOMAIN_NAME: str = os.getenv("OS_PROJECT_DOMAIN_NAME", "Default")
        self.OS_REGION_NAME: str = os.getenv("OS_REGION_NAME", "RegionOne")
        self.SWIFT_CONTAINER: str = os.getenv("SWIFT_CONTAINER", "cctv-preprocess")
        self.SWIFT_UPLOAD_PREFIX: str = os.getenv("SWIFT_UPLOAD_PREFIX", "preprocess/")
        self.SWIFT_UPLOAD_ENABLED: bool = os.getenv("SWIFT_UPLOAD_ENABLED", "true").lower() == "true"

settings = Settings()
