# 🏗️ Helios AI 베이스 이미지 관리 가이드

## 📋 개요
Helios AI 프로젝트는 **베이스 이미지** + **애플리케이션 이미지** 구조로 빌드 효율성을 극대화합니다.

## 🎯 베이스 이미지란?
- **목적**: 모든 Python 의존성(라이브러리)이 미리 설치된 이미지
- **내용**: FastAPI, PyTorch, OpenCV, MySQL Connector 등
- **특징**: 애플리케이션 코드는 포함하지 않음
- **장점**: 코드 변경 시 빌드 시간 90% 단축

## 📁 파일 구조
```
├── Dockerfile.base         # 베이스 이미지용 (의존성만)
├── Dockerfile.production   # 앱 이미지용 (코드만)
├── build-base.sh           # 베이스 이미지 빌드 스크립트
└── requirements.txt        # Python 의존성 목록
```

## 🚀 사용 방법

### 1. 베이스 이미지 빌드 (최초 1회 또는 의존성 변경 시)
```bash
# 로컬에서 빌드
./build-base.sh latest

# 레지스트리에 푸시
./build-base.sh v1.0 your-registry.com
```

### 2. 애플리케이션 이미지 빌드 (코드 변경 시마다)
```bash
# 베이스 이미지 사용해서 빌드
docker build -f Dockerfile.production -t helios-ai:latest .
```

## 🔄 Jenkins 워크플로우

### 자동 베이스 이미지 관리
1. **requirements.txt 변경 감지** → 베이스 이미지 자동 리빌드
2. **변경 없음** → 기존 베이스 이미지 재사용
3. **애플리케이션 이미지** → 항상 최신 코드로 빌드

### 빌드 시간 비교
| 구분 | 기존 방식 | 베이스 이미지 방식 |
|------|-----------|-------------------|
| 최초 빌드 | 10분 | 10분 (베이스) + 2분 (앱) |
| 코드 변경 후 | 10분 | **2분** |
| 의존성 변경 후 | 10분 | 10분 (베이스) + 2분 (앱) |

## 📦 베이스 이미지에 포함된 패키지

### 🖥️ 시스템 패키지
- **빌드 도구**: gcc, g++, build-essential
- **OpenCV**: libgl1-mesa-glx, libgstreamer, ffmpeg
- **MySQL**: default-libmysqlclient-dev
- **암호화**: libffi-dev, libssl-dev

### 🐍 Python 패키지
- **웹 프레임워크**: FastAPI, Uvicorn, WebSockets
- **AI/ML**: PyTorch, Ultralytics (YOLO), OpenCV
- **데이터베이스**: MySQL Connector, PyMySQL
- **기타**: Pandas, NumPy, Pillow, Requests

## 🔧 베이스 이미지 업데이트

### 의존성 추가 시
1. `requirements.txt`에 새 패키지 추가
2. Git에 커밋 & 푸시
3. Jenkins가 자동으로 베이스 이미지 리빌드
4. 이후 모든 빌드에서 새 베이스 이미지 사용

### 시스템 패키지 추가 시
1. `Dockerfile.base`에 패키지 추가
2. 수동으로 베이스 이미지 리빌드
   ```bash
   ./build-base.sh v1.1 your-registry.com
   ```
3. `Dockerfile.production`에서 베이스 이미지 태그 업데이트

## 🏷️ 태깅 전략

### 베이스 이미지 태그
- `helios-ai-base:latest` - 최신 개발 버전
- `helios-ai-base:v1.0` - 안정 버전
- `helios-ai-base:python3.11` - Python 버전별

### 앱 이미지 태그
- `helios-ai:latest` - 최신 개발 버전
- `helios-ai:BUILD_NUMBER` - 빌드별 버전
- `helios-ai:v2.1.0` - 릴리스 버전

## 🔍 트러블슈팅

### Q: 베이스 이미지가 없다고 나올 때
```bash
# 베이스 이미지 pull 또는 빌드
docker pull your-registry.com/helios-ai-base:latest
# 또는
./build-base.sh latest
```

### Q: 패키지가 없다고 나올 때
```bash
# requirements.txt 확인 후 베이스 이미지 리빌드
./build-base.sh latest your-registry.com
```

### Q: 베이스 이미지 크기가 너무 클 때
- Alpine 기반 베이스 이미지 고려
- 불필요한 시스템 패키지 제거
- multi-stage build 활용

## 📊 모니터링

### 이미지 크기 확인
```bash
docker images | grep helios-ai
```

### 베이스 이미지 레이어 분석
```bash
docker history helios-ai-base:latest
```

### 사용하지 않는 이미지 정리
```bash
docker image prune -f
docker system prune -f
```

## 🎉 마무리
이 구조를 통해 Helios AI 프로젝트의 **개발 생산성**과 **배포 효율성**을 크게 향상시킬 수 있습니다!
