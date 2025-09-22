import asyncio
import logging
import os

# .env 파일 로드 (선택)
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from app.core.config import settings

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("worker_main")


async def run_worker():
    from app.worker.stream_worker import get_stream_worker
    worker = get_stream_worker()
    logger.info("워커 프로세스 시작")

    try:
        await worker.start()
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"워커 오류: {e}")
    finally:
        logger.info("워커 종료")


def main():
    # API_STARTS_WORKER 플래그와 무관하게 순수 워커만 실행
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        logger.info("중단 요청 수신, 종료합니다")


if __name__ == "__main__":
    main()
