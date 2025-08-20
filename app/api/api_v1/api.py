from fastapi import APIRouter
from app.api.endpoints import detection

api_router = APIRouter()

# 탐지 관련 라우터 포함
api_router.include_router(detection.router)
