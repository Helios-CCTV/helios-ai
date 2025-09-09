import os
import logging
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.api_v1.api import api_router
from app.core.config import settings

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# 결과 및 모델 디렉토리 생성
os.makedirs("results", exist_ok=True)
os.makedirs("models", exist_ok=True)

app = FastAPI(
    root_path="/ai",
    title=settings.PROJECT_NAME,
    description=settings.PROJECT_DESCRIPTION,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API 라우터 포함
app.include_router(api_router, prefix=settings.API_V1_STR)

# 정적 파일 서비스
app.mount("/results", StaticFiles(directory="results"), name="results")
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/", StaticFiles(directory=".", html=True), name="static")

@app.get("/", include_in_schema=False)
async def root():
    """루트 경로는 API 문서로 리다이렉트합니다."""
    return RedirectResponse(url="/docs")

@app.get("/stream-test", include_in_schema=False)
async def stream_test():
    """스트리밍 테스트 페이지로 리다이렉트합니다."""
    return RedirectResponse(url="/static/stream_test.html")

@app.get("/health", tags=["health"])
async def health_check():
    """API 상태 체크"""
    return {"status": "ok", "version": settings.VERSION}

if __name__ == "__main__":
    import uvicorn
    
    logger.info(f"Starting {settings.PROJECT_NAME} version {settings.VERSION}")
    uvicorn.run("main:app", host="10.246.246.63", port=11100, reload=True)
