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
from typing import Dict, Any, Optional, List, DefaultDict
from collections import defaultdict
import redis.asyncio as redis
from app.core.config import settings
from app.metrics import metrics
from app.services.preprocess_only_adapter import get_preprocess_adapter
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
        # 소비할 스트림 집합 계산 (파티션/멀티스트림 지원)
        self.streams: List[str] = self._resolve_streams()
        # 배치 ACK 버퍼
        self._ack_buffers: DefaultDict[str, List[str]] = defaultdict(list)
        self._ack_lock = asyncio.Lock()
        
        logger.info(
            f"Stream Worker 초기화: consumer={self.consumer_name}, concurrency={self.current_concurrency}, streams={self.streams}"
        )

    def _resolve_streams(self) -> List[str]:
        """환경설정으로부터 소비할 스트림 목록 생성"""
        if getattr(settings, 'REDIS_STREAMS', None):
            return list(settings.REDIS_STREAMS)
        if getattr(settings, 'REDIS_STREAM_PREFIX', None) and getattr(settings, 'REDIS_STREAM_PARTITIONS', 0) > 0:
            prefix = settings.REDIS_STREAM_PREFIX
            parts = settings.REDIS_STREAM_PARTITIONS
            return [f"{prefix}:{i}" for i in range(parts)]
        # 기본 단일 스트림
        return [settings.REDIS_STREAM]
    
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
            
            # 컨슈머 그룹 자동 생성/복구 (모든 스트림)
            await self._ensure_consumer_group()
        
        return self.redis_client
    
    async def _ensure_consumer_group(self):
        """컨슈머 그룹 존재 확인 및 생성 (모든 스트림)"""
        assert self.redis_client is not None
        for stream in self.streams:
            try:
                await self.redis_client.xinfo_groups(stream)
                logger.info(f"Redis 컨슈머 그룹 확인 완료: stream={stream}, group={settings.REDIS_GROUP}")
            except redis.ResponseError as e:
                if "no such key" in str(e).lower():
                    logger.info(f"Redis 스트림 생성 및 그룹 설정: {stream}")
                    await self._create_consumer_group(stream)
                else:
                    logger.warning(f"컨슈머 그룹 확인 중 오류(stream={stream}): {e}")
                    await self._create_consumer_group(stream)
            except Exception as e:
                logger.warning(f"컨슈머 그룹 확인 실패(stream={stream}): {e}")
                await self._create_consumer_group(stream)
    
    async def _create_consumer_group(self, stream: str):
        """컨슈머 그룹 생성 (단일 스트림)"""
        assert self.redis_client is not None
        try:
            await self.redis_client.xgroup_create(
                stream,
                settings.REDIS_GROUP,
                id="$",
                mkstream=True
            )
            logger.info(f"Redis 컨슈머 그룹 생성: stream={stream}, group={settings.REDIS_GROUP}")
        except redis.ResponseError as e:
            if "BUSYGROUP" in str(e):
                logger.info(f"Redis 컨슈머 그룹 이미 존재: stream={stream}, group={settings.REDIS_GROUP}")
            else:
                logger.error(f"컨슈머 그룹 생성 실패(stream={stream}): {e}")
                raise
    
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
                    await self._requeue_message(stream_name, fields, attempt, "GPU 메모리 부족")
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
                        await self._requeue_message(stream_name, fields, attempt, f"HLS 연결 실패: {result['meta'].get('hls_connection_error', '알 수 없는 오류')}")
                        return
                    else:
                        # 3회 실패 시 부분 성공으로 처리하고 업로드
                        logger.warning(f"HLS 연결 지속 실패, 오류 정보만 업로드: job_id={job_id}")
                
                # Swift 업로드 (환경변수로 제어)
                uploaded_keys = []
                upload_enabled = settings.SWIFT_UPLOAD_ENABLED if hasattr(settings, 'SWIFT_UPLOAD_ENABLED') else True
                temp_dir = result.get("temp_dir")  # result에서 temp_dir 안전하게 가져오기
                
                if upload_enabled and temp_dir:
                    try:
                        uploader = get_swift_uploader()
                        
                        # 날짜별 폴더 구조: YYYY/MMDD/
                        now = datetime.now()
                        date_str = now.strftime("%Y/%m%d")  # 2025/0911
                        date_only = now.strftime("%Y%m%d")   # 20250911
                        
                        # 개별 파일 업로드 (파일명 변경)
                        uploaded_keys = []
                        from pathlib import Path
                        local_path = Path(temp_dir)
                        
                        for file_path in local_path.rglob('*'):
                            if not file_path.is_file():
                                continue
                            filename = file_path.name.lower()

                            # 정책: JSON은 업로드하지 않음, 배경 이미지만 업로드
                            if filename.endswith('.json'):
                                continue
                            if filename != 'background.jpg':
                                continue

                            # 파일명: {cctvId}_{YYYYMMDD}.jpg
                            new_filename = f"{cctv_id}_{date_only}.jpg"
                            object_key = f"{date_str}/{new_filename}"

                            # 이미지 컨텐츠 타입 및 인라인 표시로 업로드
                            uploaded_key = await uploader.upload_file(
                                str(file_path),
                                object_key,
                                content_type='image/jpeg',
                                content_disposition='inline'
                            )
                            uploaded_keys.append(uploaded_key)
                        
                        logger.info(f"Swift 업로드 완료: {len(uploaded_keys)}개 파일")
                    except Exception as e:
                        logger.error(f"Swift 업로드 실패: {e}")
                        # 업로드 실패해도 처리는 계속 진행
                else:
                    logger.info("Swift 업로드 비활성화됨 (SWIFT_UPLOAD_ENABLED=false)")
                
                # 임시 디렉터리 정리
                if temp_dir and os.path.exists(temp_dir):
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
                # 성공 처리 (모든 상태에서 ACK 스케줄)
                await self._schedule_ack(stream_name, message_id)
                
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
                redis_client = await self._get_redis_client()
                
                if attempt < settings.REDIS_MAX_RETRY:
                    await self._requeue_message(stream_name, fields, attempt, str(e))
                    # 재시도할 경우에만 XACK하지 않음 (원본 메시지는 유지)
                else:
                    # 최대 재시도 도달 시 DLQ로 이동하고 XACK
                    await self._move_to_dlq(fields, str(e))
                    await self._schedule_ack(stream_name, message_id)
                    logger.info(f"최대 재시도 도달, DLQ 이동 후 XACK: job_id={job_id}")
                    
            finally:
                metrics.decrement("concurrency_current")
    
    async def _requeue_message(self, stream_name: str, fields: Dict[str, str], attempt: int, error: str):
        """메시지 재큐"""
        try:
            # attempt 증가
            fields["attempt"] = str(attempt + 1)
            fields["last_error"] = error
            fields["retry_at"] = str(int(time.time() * 1000))
            
            redis_client = await self._get_redis_client()
            await redis_client.xadd(stream_name, fields)
            
            metrics.increment("retried")
            logger.info(f"메시지 재큐(stream={stream_name}): attempt={attempt + 1}, error={error}")
            
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
                streams_spec = {s: ">" for s in self.streams}
                messages = await redis_client.xreadgroup(
                    settings.REDIS_GROUP,
                    self.consumer_name,
                    streams_spec,
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
            except redis.ResponseError as e:
                if "NOGROUP" in str(e):
                    logger.warning(f"컨슈머 그룹 없음, 재생성 시도: {e}")
                    try:
                        await self._ensure_consumer_group()
                        logger.info("컨슈머 그룹 재생성 완료")
                        continue
                    except Exception as create_error:
                        logger.error(f"컨슈머 그룹 재생성 실패: {create_error}")
                        await asyncio.sleep(10)
                        continue
                else:
                    logger.error(f"Redis 응답 오류: {e}")
                    await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"소비 루프 오류: {e}")
                await asyncio.sleep(5)  # 오류 시 잠시 대기
    
    async def _get_pending_count(self) -> int:
        """대기 중인 메시지 수 조회"""
        try:
            redis_client = await self._get_redis_client()
            total = 0
            for stream in self.streams:
                try:
                    info = await redis_client.xpending(stream, settings.REDIS_GROUP)
                    total += info.get("pending", 0)
                except Exception:
                    continue
            return total
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
                
                # XAUTOCLAIM으로 타임아웃된 메시지 회수 (모든 스트림)
                for stream in self.streams:
                    try:
                        await redis_client.xautoclaim(
                            stream,
                            settings.REDIS_GROUP,
                            self.consumer_name,
                            min_idle_time=timeout_ms,
                            start_id="0-0",
                            count=10
                        )
                    except Exception as e:
                        logger.debug(f"XAUTOCLAIM 실패(stream={stream}): {e}")
                
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
            asyncio.create_task(self._visibility_timeout_loop()),
            asyncio.create_task(self._ack_flush_loop())
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
            
            # 남은 ACK 플러시
            try:
                await self._flush_acks()
            except Exception:
                pass

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

    async def _schedule_ack(self, stream_name: str, message_id: str):
        """ACK 버퍼에 메시지 추가 (배치 ACK)"""
        if not settings.BATCH_ACK_ENABLED:
            # 즉시 ACK 수행
            redis_client = await self._get_redis_client()
            try:
                await redis_client.xack(stream_name, settings.REDIS_GROUP, message_id)
            except Exception as e:
                logger.warning(f"즉시 ACK 실패(stream={stream_name}, id={message_id}): {e}")
            return
        async with self._ack_lock:
            self._ack_buffers[stream_name].append(message_id)

    async def _flush_acks(self):
        """버퍼된 ACK를 플러시"""
        if not settings.BATCH_ACK_ENABLED:
            return
        redis_client = await self._get_redis_client()
        async with self._ack_lock:
            for stream, ids in list(self._ack_buffers.items()):
                if not ids:
                    continue
                batch = ids[:]
                self._ack_buffers[stream].clear()
                try:
                    # xack는 가변 인자를 허용함
                    await redis_client.xack(stream, settings.REDIS_GROUP, *batch)
                    logger.debug(f"배치 ACK 완료(stream={stream}, count={len(batch)})")
                except Exception as e:
                    logger.error(f"배치 ACK 실패(stream={stream}, count={len(batch)}): {e}")

    async def _ack_flush_loop(self):
        """주기적으로 ACK 버퍼를 플러시"""
        interval = max(50, settings.ACK_FLUSH_MS) / 1000.0
        while self.running:
            try:
                await asyncio.sleep(interval)
                await self._flush_acks()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"ACK 플러시 루프 오류: {e}")


# 글로벌 워커 인스턴스
_stream_worker = None

def get_stream_worker() -> StreamWorker:
    """Stream Worker 싱글톤 인스턴스 반환"""
    global _stream_worker
    if _stream_worker is None:
        _stream_worker = StreamWorker()
    return _stream_worker
