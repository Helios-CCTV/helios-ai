# Helios CCTV AI & 도로 파손 탐지 API

이 프로젝트는 두 가지 주요 기능을 제공합니다:
1. CCTV 위치 데이터를 수집하고 MySQL 데이터베이스에 저장하는 기능
2. CCTV 영상 및 이미지에서 도로 파손을 탐지하고 분석하는 API 기능

## 주요 기능

### 1. CCTV 데이터 수집 (cctv_to_db.py)
- 한국 ITS 공개 API를 통한 CCTV 위치 데이터 수집
- MySQL 데이터베이스에 CCTV 데이터 저장
- 공간 인덱스를 활용한 효율적인 좌표 검색
- 행정구역과 CCTV 위치 매칭

### 2. 도로 파손 탐지 API (main.py)
- 이미지에서 도로 파손 탐지 (포트홀, 균열, 패치 등)
- 비디오에서 도로 파손 탐지 및 시간별 분석
- 파손 심각도 계산 및 분석
- 배치 프로세싱을 통한 다중 이미지 분석
- 파손 통계 데이터 제공

## 설치 및 설정

### 1. 필요한 패키지 설치

#### CCTV 데이터 수집용
```bash
pip install -r requirements.txt
```

또는 개별 설치:
```bash
pip install requests mysql-connector-python PyMySQL shapely python-dotenv pandas
```

#### 도로 파손 탐지 API용
```bash
# 가상환경 생성 (권장)
python -m venv fastapi-venv

# 가상환경 활성화 (Windows)
fastapi-venv\Scripts\activate

# 가상환경 활성화 (Linux/Mac)
source fastapi-venv/bin/activate

# 필요 패키지 설치
pip install -r requirements-fastapi.txt
```

### 2. MySQL 설정

MySQL 서버에 공간 함수 지원이 활성화되어 있어야 합니다:

```sql
-- 데이터베이스 생성
CREATE DATABASE helios_cctv DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE helios_cctv;
```

### 3. 환경 설정

`.env.example` 파일을 `.env`로 복사하고 설정값을 입력하세요:

```bash
cp .env.example .env
```

`.env` 파일에서 다음 항목들을 설정하세요:
- `ITS_API_KEY`: ITS 공개 API 키
- `DB_HOST`: MySQL 호스트 (기본값: localhost)
- `DB_NAME`: 데이터베이스 이름 (기본값: helios_cctv)
- `DB_USER`: MySQL 사용자 (기본값: root)
- `DB_PASSWORD`: MySQL 비밀번호
- `DB_PORT`: MySQL 포트 (기본값: 3306)

### 4. 데이터베이스 테이블 생성

**주의: 테이블은 이미 생성되어 있어야 합니다.**

실제 테이블 구조:
- **cctvs**: CCTV 정보 저장 테이블
- **regions**: 행정구역 폴리곤 정보 테이블 (`sgg_nm`, `polygon` 컬럼 사용)

## 사용법

### CCTV 데이터 수집
```bash
# 기본 실행
python cctv_to_db.py

# 도움말
python cctv_to_db.py --help

# API 데이터만 조회 (DB 저장 안 함)
python cctv_to_db.py --api-only
```

### 도로 파손 탐지 API

```bash
# 가상환경 활성화
fastapi-venv\Scripts\activate  # Windows
source fastapi-venv/bin/activate  # Linux/Mac

# 개발 모드로 실행
uvicorn main:app --reload

# 프로덕션 모드로 실행
uvicorn main:app --host 0.0.0.0 --port 8000
```

API 문서는 서버 실행 후 다음 URL에서 확인할 수 있습니다:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## API 엔드포인트

### 1. 이미지에서 도로 파손 탐지

```
POST /api/v1/damage-detection/analyze
```

- 요청: multipart/form-data
  - `file`: 이미지 파일
  - `confidence`: 신뢰도 임계값 (기본값: 0.25)
  - `include_image`: 결과 이미지를 Base64로 포함할지 여부 (기본값: true)
  - `location_lat`, `location_lng`: 위치 정보 (선택 사항)
  - `image_id`: 이미지 식별자 (선택 사항)

### 2. 실시간 스트리밍에서 도로 파손 탐지 (단일 프레임)

```
POST /api/v1/damage-detection/analyze-stream
```

- 요청: form-data
  - `stream_url`: 스트리밍 URL (HLS, RTSP, HTTP 등)
  - `confidence`: 신뢰도 임계값 (기본값: 0.25)
  - `include_image`: 결과 이미지를 Base64로 포함할지 여부 (기본값: true)
  - `location_lat`, `location_lng`: 위치 정보 (선택 사항)
  - `stream_id`: 스트림 식별자 (선택 사항)
  - `sample_interval`: 샘플링 간격(초) (기본값: 10)

### 3. 실시간 스트리밍 비디오 (MJPEG)

```
GET /api/v1/damage-detection/stream-video?stream_url={STREAM_URL}&confidence=0.25&fps=10
```

- 쿼리 파라미터:
  - `stream_url`: 스트리밍 URL (필수)
  - `confidence`: 탐지 신뢰도 임계값 (기본값: 0.25)
  - `fps`: 초당 프레임 수 (기본값: 10)

- 반환: MJPEG 형식의 실시간 처리된 비디오 스트림
- 사용 예: `<img src="http://localhost:8000/api/v1/damage-detection/stream-video?stream_url=YOUR_STREAM_URL">`

### 4. 웹소켓을 통한 실시간 스트리밍

```
WebSocket: /api/v1/damage-detection/stream-live/{stream_id}
```

- URL 파라미터:
  - `stream_id`: 스트림 식별자
  
- 연결 후 JSON으로 전송:
  ```json
  {
    "stream_url": "RTSP_OR_HLS_URL",
    "confidence": 0.25
  }
  ```
  
- 응답 (JSON):
  ```json
  {
    "frame": "BASE64_ENCODED_IMAGE",
    "damages": [...],
    "damage_count": 2,
    "damage_summary": {"crack": 1, "pothole": 1},
    "timestamp": "2025-08-20T12:34:56.789"
  }
  ```

### 5. 비디오에서 도로 파손 탐지

```
POST /api/v1/damage-detection/analyze-video
```

- 요청: multipart/form-data
  - `file`: 비디오 파일
  - `confidence`: 신뢰도 임계값 (기본값: 0.25)
  - `fps_interval`: 프레임 간격 (기본값: 1)
  - `video_id`: 비디오 식별자 (선택 사항)

### 6. 통계 데이터 조회

```
GET /api/v1/damage-detection/statistics
```

- 쿼리 파라미터:
  - `start_date`: 시작 날짜 (YYYY-MM-DD)
  - `end_date`: 종료 날짜 (YYYY-MM-DD)
  - `damage_type`: 파손 유형
  - `min_severity`: 최소 심각도
  - `location_range`: 위치 범위

## 데이터베이스 스키마

### cctvs 테이블
- `id`: 기본 키 (AUTO_INCREMENT)
- `location`: 설치 위치 (VARCHAR(255))
- `latitude`: 위도 (DECIMAL(9,6))
- `longitude`: 경도 (DECIMAL(9,6))
- `point`: 공간 좌표 (POINT, SRID 4326)
- `status`: 상태 (VARCHAR(20), 기본값: 'active')
- `region_id`: 행정구역 FK (INT)
- `created_at`: 생성 시간
- `updated_at`: 수정 시간

### regions 테이블
- `id`: 기본 키 (AUTO_INCREMENT)
- `name`: 행정구역명 (VARCHAR(100))
- `code`: 행정구역 코드 (VARCHAR(20))
- `polygon_geom`: 폴리곤 지오메트리 (POLYGON, SRID 4326)
- `created_at`: 생성 시간
- `updated_at`: 수정 시간

## API 정보

이 프로그램은 한국 ITS(Intelligent Transport Systems) 공개 API를 사용합니다:
- API URL: https://openapi.its.go.kr:9443/cctvInfo
- 필요한 매개변수:
  - `apiKey`: API 키
  - `type`: 도로 유형 (기본값: all)
  - `cctvType`: CCTV 유형 (기본값: 2)
  - `minX`, `maxX`: 경도 범위
  - `minY`, `maxY`: 위도 범위
  - `getType`: 출력 형식 (기본값: json)

## 좌표 범위

기본 설정은 한국 전체 지역을 대상으로 합니다:
- 경도: 125.864 ~ 128.304
- 위도: 36.846 ~ 37.903

필요에 따라 `main()` 함수에서 좌표 범위를 수정할 수 있습니다.

## 공간 검색 예시

MySQL에서 공간 함수를 사용한 검색 예시:

```sql
-- 특정 좌표에서 1km 반경 내 CCTV 찾기
SELECT * FROM cctvs 
WHERE ST_Distance_Sphere(point, ST_GeomFromText('POINT(127.0276 37.4979)', 4326)) <= 1000;

-- 특정 행정구역 내 CCTV 개수
SELECT r.name, COUNT(c.id) as cctv_count
FROM regions r
LEFT JOIN cctvs c ON r.id = c.region_id
GROUP BY r.id, r.name;
```

## 요구사항

- Python 3.7+
- MySQL 5.7+ (공간 함수 지원)
- 유효한 ITS API 키

## 문제 해결

### MySQL 공간 함수 오류
MySQL에서 공간 함수가 작동하지 않는 경우:
```sql
-- MySQL 버전 확인
SELECT VERSION();

-- 공간 함수 지원 확인
SHOW ENGINES;
```

### 테이블 생성 오류
- 외래키 제약조건으로 인한 오류가 발생할 수 있습니다.
- regions 테이블을 먼저 생성한 후 cctvs 테이블을 생성하세요.

## 라이센스

MIT License
