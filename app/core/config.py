from typing import Optional, List

# 간단한 설정 클래스 구현
class Settings:
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "Helios CCTV API"
    PROJECT_DESCRIPTION: str = "CCTV 데이터 관리 및 분석을 위한 API"
    VERSION: str = "0.1.0"
    
    # Database settings
    DATABASE_URL: Optional[str] = None
    
    # CORS settings
    BACKEND_CORS_ORIGINS = ["*"]

settings = Settings()
