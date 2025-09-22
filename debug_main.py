#!/usr/bin/env python3
import sys
import traceback
import logging

# 더 자세한 로깅 설정
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("debug.log", encoding='utf-8')
    ]
)

logger = logging.getLogger(__name__)

try:
    logger.info("=== DEBUG MODE START ===")
    
    # .env 파일 로드
    logger.info("Loading .env file...")
    try:
        from dotenv import load_dotenv
        load_dotenv()
        logger.info(".env loaded successfully")
    except ImportError:
        logger.warning("python-dotenv not installed, using system environment variables")
    except Exception as e:
        logger.error(f"Error loading .env: {e}")
    
    # FastAPI imports
    logger.info("Importing FastAPI...")
    from fastapi import FastAPI, HTTPException
    logger.info("FastAPI imported successfully")
    
    # App imports
    logger.info("Importing app modules...")
    from app.api.api_v1.api import api_router
    from app.api.endpoints import analyze as analyze_ep
    from app.core.config import settings
    logger.info("App modules imported successfully")
    
    # Create FastAPI app
    logger.info("Creating FastAPI app...")
    app = FastAPI(
        root_path="/ai",
        title=settings.PROJECT_NAME,
        description=settings.PROJECT_DESCRIPTION,
        version=settings.VERSION,
        openapi_url="/openapi.json",
    )
    logger.info("FastAPI app created successfully")
    
    # Add routers
    logger.info("Adding routers...")
    app.include_router(api_router, prefix=settings.API_V1_STR)
    app.include_router(analyze_ep.router)
    logger.info("Routers added successfully")
    
    @app.get("/debug-test")
    def debug_test():
        return {"status": "ok", "message": "Debug endpoint working"}
    
    # Start server
    logger.info("Starting server...")
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=11100, log_level="debug")
    
except Exception as e:
    logger.error(f"FATAL ERROR: {e}")
    logger.error(f"Exception type: {type(e)}")
    logger.error(f"Traceback: {traceback.format_exc()}")
    sys.exit(1)
