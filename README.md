# Helios CCTV AI

CCTV 위치 데이터를 수집하고 MySQL 데이터베이스에 저장하는 Python 애플리케이션입니다.

## 기능

- 한국 ITS 공개 API를 통한 CCTV 위치 데이터 수집
- MySQL 데이터베이스에 CCTV 데이터 저장
- 공간 인덱스를 활용한 효율적인 좌표 검색
- 행정구역과 CCTV 위치 매칭

## 설치 및 설정

### 1. 필요한 패키지 설치

```bash
pip install -r requirements.txt
```

또는 개별 설치:
```bash
pip install requests mysql-connector-python PyMySQL shapely python-dotenv pandas
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

### 기본 실행
```bash
python cctv_to_db.py
```

### 도움말
```bash
python cctv_to_db.py --help
```

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
