"""
Redis Stream 워커 - 비동기 소비 및 처리
"""
import asyncio
import json
import uuid
import time
import logging
import shutil
import os
from datetime import datetime
from typing import Dict, Any, Optional
import redis.asyncio as redis
from app.config import settings
from app.metrics import metrics
from app.services.preprocess_adapter import get_preprocess_adapter
from app.services.storage_swift import get_swift_uploader

logger = logging.getLogger(__name__)


class StreamWorker:
    """Redis Stream 워커"""
    
    def __init__(self):
        self.redis_client: Optional[redis.Redis] = None
        self.consumer_name = f"worker_{uuid.uuid4().hex[:8]}"
        self.running = False
        self.semaphore = asyncio.Semaphore(settings.MAX_CONCURRENCY)
        self.current_concurrency = settings.MAX_CONCURRENCY
        
        logger.info(f"Stream Worker 초기화: consumer={self.consumer_name}, concurrency={self.current_concurrency}")
    
    async def _get_redis_client(self) -> redis.Redis:
        """Redis 클라이언트 가져오기 (지연 초기화)"""
        if self.redis_client is None:
            redis_url = settings.REDIS_URL
            if settings.REDIS_PASSWORD:
                # URL에 패스워드 추가
                if "://" in redis_url:
                    protocol, rest = redis_url.split("://", 1)
                    redis_url = f"{protocol}://:{settings.REDIS_PASSWORD}@{rest}"
            
            self.redis_client = redis.from_url(redis_url, decode_responses=True)
            
            # 연결 테스트
            await self.redis_client.ping()
            logger.info("Redis 연결 성공")
            
            # 컨슈머 그룹 생성 (존재하지 않는 경우)
            try:
                await self.redis_client.xgroup_create(
                    settings.REDIS_STREAM,
                    settings.REDIS_GROUP,
                    id="$",
                    mkstream=True
                )
                logger.info(f"Redis 컨슈머 그룹 생성: {settings.REDIS_GROUP}")
            except redis.ResponseError as e:
                if "BUSYGROUP" not in str(e):
                    raise
                logger.info(f"Redis 컨슈머 그룹 이미 존재: {settings.REDIS_GROUP}")
        
        return self.redis_client
    
    async def _check_gpu_memory(self) -> bool:
        """GPU 메모리 확인 (옵션)"""
        if not settings.GPU_MEMORY_GUARD:
            return True
        
        try:
            import torch
            if torch.cuda.is_available():
                # 간단한 GPU 메모리 체크
                memory_allocated = torch.cuda.memory_allocated()
                memory_reserved = torch.cuda.memory_reserved()
                memory_free = torch.cuda.get_device_properties(0).total_memory - memory_reserved
                
                # 여유 메모리가 1GB 미만이면 처리 지연
                if memory_free < 1024 * 1024 * 1024:  # 1GB
                    logger.warning(f"GPU 메모리 부족: free={memory_free/1024/1024:.1f}MB")
                    return False
        except Exception as e:
            logger.warning(f"GPU 메모리 체크 실패: {e}")
        
        return True
    
    async def _process_message(self, stream_name: str, message_id: str, fields: Dict[str, str]):
        """단일 메시지 처리"""
        async with self.semaphore:
            metrics.increment("concurrency_current")
            job_id = None
            
            try:
                # 메시지 파싱
                cctv_id = fields.get("cctvId", "unknown")
                hls_url = fields.get("hls", "")
                sec = int(fields.get("sec", "20"))
                attempt = int(fields.get("attempt", "0"))
                enqueued_at = fields.get("enqueuedAt", "")
                # Spring Boot에서 jobId 없으면 message_id 사용, 테스트에서는 jobId 사용
                job_id = fields.get("jobId") or message_id
                
                logger.info(f"메시지 처리 시작: job_id={job_id}, cctv_id={cctv_id}, attempt={attempt}")
                
                if not hls_url:
                    raise ValueError("HLS URL이 비어있습니다")
                
                # GPU 메모리 체크
                if not await self._check_gpu_memory():
                    # 메모리 부족 시 재큐
                    await self._requeue_message(fields, attempt, "GPU 메모리 부족")
                    return
                
                # 전처리 실행
                adapter = get_preprocess_adapter()
                result = await adapter.run_preprocess_from_hls(
                    hls_url=hls_url,
                    sec=sec,
                    cctv_id=cctv_id
                )
                
                # 결과 상태 확인
                processing_status = result["meta"].get("processing_status", "unknown")
                hls_accessible = result["meta"].get("hls_accessible", True)
                
                # HLS 연결 실패 시 재시도 처리
                if not hls_accessible:
                    logger.warning(f"HLS 연결 실패: job_id={job_id}, hls={hls_url}")
                    
                    # HLS 연결 실패는 즉시 재시도하지 않고 지연 후 재시도
                    # Spring Boot는 attempt=1부터 시작하므로 3회까지 허용
                    if attempt < 3:  # HLS 연결 실패는 최대 3회까지만 재시도
                        await asyncio.sleep(30)  # 30초 후 재시도
                        await self._requeue_message(fields, attempt, f"HLS 연결 실패: {result['meta'].get('hls_connection_error', '알 수 없는 오류')}")
                        return
                    else:
                        # 3회 실패 시 부분 성공으로 처리하고 업로드
                        logger.warning(f"HLS 연결 지속 실패, 오류 정보만 업로드: job_id={job_id}")
                
                # Swift 업로드 (오류 정보라도 업로드)
                uploader = get_swift_uploader()
                temp_dir = result["temp_dir"]
                
                # 업로드 prefix 생성
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                upload_prefix = f"{settings.SWIFT_UPLOAD_PREFIX}{cctv_id}/{job_id}/{timestamp}"
                
                uploaded_keys = await uploader.upload_dir_to_swift(temp_dir, upload_prefix)
                
                # 임시 디렉터리 정리
                if temp_dir:
                    shutil.rmtree(temp_dir, ignore_errors=True)
                
                # 처리 상태에 따른 메트릭 업데이트
                if processing_status == "success":
                    metrics.increment("processed")
                    logger.info(f"메시지 처리 완료 (성공): job_id={job_id}, 업로드={len(uploaded_keys)}개 파일")
                elif processing_status == "partial_success":
                    metrics.increment("processed")
                    logger.info(f"메시지 처리 완료 (부분 성공): job_id={job_id}, 업로드={len(uploaded_keys)}개 파일")
                elif processing_status == "failed_hls_connection":
                    metrics.increment("processed")  # 오류 정보라도 처리했으므로
                    logger.warning(f"메시지 처리 완료 (HLS 실패): job_id={job_id}, 업로드={len(uploaded_keys)}개 파일")
                # 성공 처리 (모든 상태에서 XACK)
                redis_client = await self._get_redis_client()
                await redis_client.xack(settings.REDIS_STREAM, settings.REDIS_GROUP, message_id)
                
            except Exception as e:
                logger.error(f"메시지 처리 실패: job_id={job_id}, 오류: {e}")
                metrics.increment("failed")
                
                # 임시 디렉터리 정리 (오류 시에도)
                try:
                    if 'temp_dir' in locals() and temp_dir and os.path.exists(temp_dir):
                        shutil.rmtree(temp_dir, ignore_errors=True)
                except:
                    pass
                
                # 재시도 처리
                attempt = int(fields.get("attempt", "0"))
                if attempt < settings.REDIS_MAX_RETRY:
                    await self._requeue_message(fields, attempt, str(e))
                else:
                    await self._move_to_dlq(fields, str(e))
                    
            finally:
                metrics.decrement("concurrency_current")
    
    async def _requeue_message(self, fields: Dict[str, str], attempt: int, error: str):
        """메시지 재큐"""
        try:
            # attempt 증가
            fields["attempt"] = str(attempt + 1)
            fields["last_error"] = error
            fields["retry_at"] = str(int(time.time() * 1000))
            
            redis_client = await self._get_redis_client()
            await redis_client.xadd(settings.REDIS_STREAM, fields)
            
            metrics.increment("retried")
            logger.info(f"메시지 재큐: attempt={attempt + 1}, error={error}")
            
        except Exception as e:
            logger.error(f"메시지 재큐 실패: {e}")
    
    async def _move_to_dlq(self, fields: Dict[str, str], error: str):
        """메시지를 데드레터 큐로 이동"""
        try:
            fields["final_error"] = error
            fields["dlq_at"] = str(int(time.time() * 1000))
            
            redis_client = await self._get_redis_client()
            await redis_client.xadd(settings.REDIS_DLQ_STREAM, fields)
            
            metrics.increment("dlq")
            logger.warning(f"메시지 DLQ 이동: error={error}")
            
        except Exception as e:
            logger.error(f"DLQ 이동 실패: {e}")
    
    async def _consume_loop(self):
        """메시지 소비 루프"""
        logger.info("소비 루프 시작")
        redis_client = await self._get_redis_client()
        
        while self.running:
            try:
                logger.debug("메시지 대기 중...")
                # 메시지 읽기
                messages = await redis_client.xreadgroup(
                    settings.REDIS_GROUP,
                    self.consumer_name,
                    {settings.REDIS_STREAM: ">"},
                    count=settings.REDIS_BATCH_COUNT,
                    block=settings.REDIS_BLOCK_MS
                )
                
                if not messages:
                    logger.debug("메시지 없음, 계속 대기")
                    continue
                
                logger.info(f"수신된 메시지: {len(messages)}개 스트림")
                # 메시지 처리
                for stream_name, stream_messages in messages:
                    logger.info(f"스트림 {stream_name}에서 {len(stream_messages)}개 메시지 처리")
                    for message_id, fields in stream_messages:
                        if not self.running:
                            break
                        
                        # 비동기 처리 시작
                        asyncio.create_task(
                            self._process_message(stream_name, message_id, fields)
                        )
                        metrics.set("pending", await self._get_pending_count())
                
            except asyncio.CancelledError:
                logger.info("소비 루프 취소됨")
                break
            except Exception as e:
                logger.error(f"소비 루프 오류: {e}")
                await asyncio.sleep(5)  # 오류 시 잠시 대기
    
    async def _get_pending_count(self) -> int:
        """대기 중인 메시지 수 조회"""
        try:
            redis_client = await self._get_redis_client()
            info = await redis_client.xpending(settings.REDIS_STREAM, settings.REDIS_GROUP)
            return info.get("pending", 0)
        except:
            return 0
    
    async def _visibility_timeout_loop(self):
        """가시성 타임아웃 처리 루프"""
        redis_client = await self._get_redis_client()
        
        while self.running:
            try:
                # 타임아웃된 메시지 회수
                timeout_ms = settings.REDIS_VISIBILITY_TIMEOUT * 1000
                current_time = int(time.time() * 1000)
                
                # XAUTOCLAIM으로 타임아웃된 메시지 회수
                await redis_client.xautoclaim(
                    settings.REDIS_STREAM,
                    settings.REDIS_GROUP,
                    self.consumer_name,
                    min_idle_time=timeout_ms,
                    start_id="0-0",
                    count=10
                )
                
                # 30초마다 실행
                await asyncio.sleep(30)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"가시성 타임아웃 처리 오류: {e}")
                await asyncio.sleep(60)
    
    async def start(self):
        """워커 시작"""
        if self.running:
            logger.warning("워커가 이미 실행 중입니다")
            return
        
        self.running = True
        logger.info(f"Stream Worker 시작: {self.consumer_name}")
        
        # 동시성 설정 적용
        metrics.set("concurrency_current", 0)
        
        # 백그라운드 태스크 시작
        tasks = [
            asyncio.create_task(self._consume_loop()),
            asyncio.create_task(self._visibility_timeout_loop())
        ]
        
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            logger.info("워커 태스크 취소됨")
        finally:
            # 정리
            for task in tasks:
                if not task.done():
                    task.cancel()
            
            if self.redis_client:
                await self.redis_client.close()
    
    async def stop(self):
        """워커 중지"""
        logger.info("Stream Worker 중지 요청")
        self.running = False
    
    def update_concurrency(self, new_concurrency: int):
        """동시성 업데이트"""
        if new_concurrency < 1:
            new_concurrency = 1
        
        old_concurrency = self.current_concurrency
        self.current_concurrency = new_concurrency
        self.semaphore = asyncio.Semaphore(new_concurrency)
        
        logger.info(f"동시성 업데이트: {old_concurrency} -> {new_concurrency}")


# 글로벌 워커 인스턴스
_stream_worker = None

def get_stream_worker() -> StreamWorker:
    """Stream Worker 싱글톤 인스턴스 반환"""
    global _stream_worker
    if _stream_worker is None:
        _stream_worker = StreamWorker()
    return _stream_worker
