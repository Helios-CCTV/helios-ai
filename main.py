import os
import logging
import asyncio
from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# .env 파일 로드
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("python-dotenv not installed, using system environment variables")

from app.api.api_v1.api import api_router
from app.api.endpoints import analyze as analyze_ep
from app.core.config import settings
from app.metrics import metrics

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
    openapi_url="/openapi.json",  # root_path와 함께 /ai/openapi.json이 됩니다
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
app.include_router(analyze_ep.router)

# 메트릭 및 상태 확인 엔드포인트들
@app.get("/health", tags=["health"])
async def health_check():
    """API 상태 체크"""
    return {"status": "ok", "version": settings.VERSION}

@app.get("/metrics", tags=["monitoring"])
async def get_metrics():
    """메트릭 조회"""
    return metrics.get_all()

# 리버스 프록시용 중복 엔드포인트 (개발/테스트용)
@app.get("/ai/health", tags=["health"], include_in_schema=False)
async def health_check_proxy():
    """API 상태 체크 (프록시용)"""
    return {"status": "ok", "version": settings.VERSION}

@app.get("/ai/metrics", tags=["monitoring"], include_in_schema=False)
async def get_metrics_proxy():
    """메트릭 조회 (프록시용)"""
    return metrics.get_all()

@app.get("/ai/openapi.json", include_in_schema=False)
async def openapi_proxy():
    """OpenAPI 스키마 (프록시용)"""
    return app.openapi()

# 워커 상태 확인 엔드포인트
@app.get("/worker/status", tags=["monitoring"])
async def get_worker_status():
    """워커 상태 조회"""
    try:
        # 지연 임포트로 의존성 문제 최소화
        from app.worker.stream_worker import get_stream_worker
        worker = get_stream_worker()
        return {
            "running": worker.running,
            "consumer_name": worker.consumer_name,
            "current_concurrency": worker.current_concurrency,
            "max_concurrency": settings.MAX_CONCURRENCY
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"워커 상태 조회 실패: {str(e)}")

@app.get("/ai/worker/status", tags=["monitoring"], include_in_schema=False)
async def get_worker_status_proxy():
    """워커 상태 조회 (프록시용)"""
    try:
        from app.worker.stream_worker import get_stream_worker
        worker = get_stream_worker()
        return {
            "running": worker.running,
            "consumer_name": worker.consumer_name,
            "current_concurrency": worker.current_concurrency,
            "max_concurrency": settings.MAX_CONCURRENCY
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"워커 상태 조회 실패: {str(e)}")

# Stream Worker 관리용 변수
worker_task = None

@app.on_event("startup")
async def startup_event():
    """앱 시작 시 워커 시작"""
    global worker_task
    try:
        if settings.API_STARTS_WORKER:
            # Stream Worker 시작 (옵션)
            from app.worker.stream_worker import get_stream_worker
            worker = get_stream_worker()
            worker_task = asyncio.create_task(worker.start())
            logger.info("Stream Worker 백그라운드 태스크 시작")
        else:
            logger.info("API_STARTS_WORKER=false: API만 시작, 워커는 시작하지 않음")
    except Exception as e:
        logger.error(f"Stream Worker 시작 실패: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    """앱 종료 시 워커 정리"""
    global worker_task
    try:
        if worker_task:
            # 워커 중지
            from app.worker.stream_worker import get_stream_worker
            worker = get_stream_worker()
            await worker.stop()
            
            # 태스크 취소 및 대기
            worker_task.cancel()
            try:
                await worker_task
            except asyncio.CancelledError:
                pass
            
            logger.info("Stream Worker 정리 완료")
    except Exception as e:
        logger.error(f"Stream Worker 정리 실패: {e}")

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

@app.post("/control/concurrency", tags=["control"])
async def update_concurrency(n: int):
    """런타임 동시성 변경"""
    if n < 1 or n > 10:
        raise HTTPException(status_code=400, detail="동시성은 1-10 사이여야 합니다")
    
    try:
        from app.worker.stream_worker import get_stream_worker
        worker = get_stream_worker()
        worker.update_concurrency(n)
        return {"success": True, "new_concurrency": n, "message": f"동시성이 {n}으로 변경되었습니다"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"동시성 변경 실패: {str(e)}")

@app.get("/worker/status", tags=["monitoring"])
async def get_worker_status():
    """워커 상태 조회"""
    try:
        from app.worker.stream_worker import get_stream_worker
        worker = get_stream_worker()
        return {
            "running": worker.running,
            "consumer_name": worker.consumer_name,
            "current_concurrency": worker.current_concurrency,
            "max_concurrency": settings.MAX_CONCURRENCY
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"워커 상태 조회 실패: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    
    logger.info(f"Starting {settings.PROJECT_NAME} version {settings.VERSION}")
    uvicorn.run("main:app", host="0.0.0.0", port=11100, reload=False)
