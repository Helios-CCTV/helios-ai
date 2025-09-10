# Redis Stream Worker 시스템

## 개요

Spring Boot가 Redis Stream `stream:preprocess`에 넣은 작업을 FastAPI에서 비동기 워커로 소비하여, 기존 전처리 알고리즘을 호출해 결과를 생성하고 OpenStack Object Storage(Swift)에 업로드하는 시스템입니다.

## 주요 특징

- **비동기 워커**: Redis Stream을 소비하는 백그라운드 워커
- **동시성 제어**: 환경변수로 동시 처리 개수 제어 (기본 2개)
- **재시도 메커니즘**: 실패 시 자동 재시도, 최대 재시도 초과 시 DLQ 이동
- **기존 코드 호환**: 기존 detection.py 엔드포인트는 그대로 유지
- **실시간 모니터링**: 메트릭 및 워커 상태 API 제공

## 파일 구조

```
app/
├── config.py                    # 환경변수 설정 (pydantic-settings)
├── metrics.py                   # 메트릭 관리 (처리/실패/대기 카운터)
├── services/
│   ├── preprocess_adapter.py    # 기존 전처리 함수 호출 어댑터
│   └── storage_swift.py         # OpenStack Swift 업로더
├── worker/
│   └── stream_worker.py         # Redis Stream 소비 워커
└── main.py                      # FastAPI 앱 + 워커 수명주기 관리
```

## 환경변수 설정

`.env` 파일을 생성하고 아래 변수들을 설정하세요:

```bash
# Redis 설정
REDIS_URL=redis://localhost:6379
REDIS_PASSWORD=                    # (옵션)
REDIS_STREAM=stream:preprocess
REDIS_GROUP=workers
REDIS_BLOCK_MS=5000
REDIS_BATCH_COUNT=20
REDIS_VISIBILITY_TIMEOUT=300
REDIS_MAX_RETRY=3
REDIS_DLQ_STREAM=stream:preprocess:dlq

# 동시성 설정
MAX_CONCURRENCY=2                  # 기본 2개
GPU_MEMORY_GUARD=true              # VRAM 부족 시 처리 지연

# OpenStack Swift 설정
OS_AUTH_URL=https://your-openstack.com:5000/v3
OS_USERNAME=your_username
OS_PASSWORD=your_password
OS_PROJECT_NAME=your_project
OS_REGION_NAME=RegionOne
SWIFT_CONTAINER=cctv-preprocess
SWIFT_UPLOAD_PREFIX=preprocess/
```

## 설치 및 실행

1. **필요 패키지 설치**:
```bash
pip install -r requirements.txt
```

2. **환경변수 설정**:
```bash
cp .env.example .env
# .env 파일을 편집하여 실제 값으로 수정
```

3. **Redis 연결 테스트**:
```bash
python test_redis_worker.py
```

4. **FastAPI 서버 실행**:
```bash
python main.py
```

## 스트림 메시지 스키마

Spring Boot에서 Redis Stream에 추가하는 메시지 형식:

```json
{
  "cctvId": "cctv_001",           # CCTV 식별자
  "hls": "https://example.com/stream.m3u8",  # HLS URL
  "sec": "20",                    # 처리 시간(초)
  "attempt": "0",                 # 재시도 카운터
  "enqueuedAt": "1694000000000"   # 큐 추가 시간(ms epoch)
}
```

## API 엔드포인트

### 기존 Detection API
- `/api/v1/damage-detection/*` - 기존 모든 엔드포인트 그대로 유지

### 새로운 모니터링/제어 API
- `GET /health` - 서버 상태 확인
- `GET /metrics` - 워커 메트릭 조회
- `GET /worker/status` - 워커 상태 조회
- `POST /control/concurrency?n=2` - 런타임 동시성 변경

### 메트릭 예시
```json
{
  "counters": {
    "processed": 150,
    "failed": 5,
    "retried": 3,
    "dlq": 2,
    "pending": 0,
    "concurrency_current": 0
  },
  "uptime_seconds": 3600.5,
  "start_time": "2024-09-09T10:00:00"
}
```

## 처리 플로우

1. **메시지 수신**: Redis Stream에서 메시지 읽기
2. **GPU 메모리 체크**: VRAM 부족 시 처리 지연
3. **전처리 실행**: HLS에서 배경 추출 + 도로 파손 분석
4. **Swift 업로드**: 결과 파일들을 OpenStack Swift에 업로드
5. **완료 처리**: 성공 시 XACK, 실패 시 재시도/DLQ

## 업로드 파일 구조

Swift에 업로드되는 파일 구조:
```
preprocess/
  └── {cctvId}/
      └── {jobId}/
          └── {timestamp}/
              ├── background.jpg           # 추출된 배경 이미지
              ├── background_meta.json     # 배경 추출 메타데이터
              ├── damage_analysis.json     # 도로 파손 분석 결과
              ├── damage_result.jpg        # 분석 결과 이미지
              └── process_meta.json        # 전체 처리 메타데이터
```

## 성능 튜닝

### GPU 메모리 부족 시
```bash
MAX_CONCURRENCY=1
GPU_MEMORY_GUARD=true
```

### 높은 처리량 필요 시
```bash
MAX_CONCURRENCY=4
REDIS_BATCH_COUNT=30
REDIS_BLOCK_MS=1000
```

### 네트워크 지연이 큰 환경
```bash
REDIS_VISIBILITY_TIMEOUT=600
REDIS_BLOCK_MS=10000
```

## 트러블슈팅

### 워커가 메시지를 처리하지 않음
1. Redis 연결 확인: `python test_redis_worker.py`
2. 컨슈머 그룹 상태 확인: `GET /worker/status`
3. 로그 확인: 서버 실행 시 워커 시작 메시지 확인

### Swift 업로드 실패
1. OpenStack 인증 정보 확인
2. 컨테이너 권한 확인
3. 네트워크 연결 상태 확인

### GPU 메모리 부족
1. `MAX_CONCURRENCY=1`로 설정
2. `GPU_MEMORY_GUARD=true` 활성화
3. 다른 GPU 사용 프로세스 종료

## 로그 예시

```
INFO - Stream Worker 초기화: consumer=worker_a1b2c3d4, concurrency=2
INFO - Redis 연결 성공
INFO - Redis 컨슈머 그룹 생성: workers
INFO - Stream Worker 백그라운드 태스크 시작
INFO - 메시지 처리 시작: job_id=test_job_001, cctv_id=test_cctv_001, attempt=0
INFO - 전처리 시작: cctv_id=test_cctv_001, job_id=test_job_001, hls=https://example.com/test.m3u8, sec=10
INFO - 배경 추출 시작: https://example.com/test.m3u8
INFO - 배경 추출 완료: /tmp/preprocess_test_cctv_001_test_job_001_xyz/background.jpg
INFO - 도로 파손 분석 시작: https://example.com/test.m3u8
INFO - 도로 파손 분석 완료: 3개 탐지
INFO - 전처리 완료: cctv_id=test_cctv_001, job_id=test_job_001, artifacts=5개
INFO - 업로드할 파일 5개 발견: /tmp/preprocess_test_cctv_001_test_job_001_xyz
INFO - 디렉터리 업로드 완료: 5/5 파일 성공
INFO - 메시지 처리 완료: job_id=test_job_001, 업로드=5개 파일
```
