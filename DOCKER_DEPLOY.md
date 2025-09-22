# Helios AI Docker 배포 가이드

## 개요
Helios AI CCTV 도로 파손 탐지 시스템의 Docker 배포를 위한 문서입니다.

## 파일 구조
```
├── Dockerfile              # 메인 도커파일 (프로덕션용)
├── Dockerfile.alpine       # 경량화 도커파일 (Alpine Linux)
├── docker-compose.yml      # Docker Compose 설정
├── Jenkinsfile             # Jenkins 파이프라인
├── requirements.txt        # Python 의존성
├── nginx.conf              # Nginx 리버스 프록시 설정
├── .dockerignore           # Docker 빌드 제외 파일
├── build.sh                # Linux/Mac 빌드 스크립트
└── build.bat               # Windows 빌드 스크립트
```

## 로컬 빌드 및 실행

### 1. 도커 이미지 빌드
```bash
# Linux/Mac
./build.sh latest

# Windows
build.bat latest

# 수동 빌드
docker build -t helios-ai:latest .
```

### 2. 컨테이너 실행
```bash
# 기본 실행
docker run -d --name helios-ai -p 8000:8000 helios-ai:latest

# 환경변수와 볼륨 마운트
docker run -d --name helios-ai \
  -p 8000:8000 \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/models:/app/models \
  -e PYTHONUNBUFFERED=1 \
  helios-ai:latest
```

### 3. Docker Compose 사용
```bash
# 서비스 시작
docker-compose up -d

# 로그 확인
docker-compose logs -f

# 서비스 중지
docker-compose down
```

## Jenkins 파이프라인 설정

### 1. Jenkins 플러그인 설치
- Docker Pipeline
- Pipeline: Stage View
- Git

### 2. Jenkins 자격 증명 설정
- `docker-registry-credentials`: Docker 레지스트리 로그인 정보

### 3. 파이프라인 작업 생성
1. New Item → Pipeline 선택
2. Pipeline script from SCM 선택
3. Repository URL 입력
4. Script Path: `Jenkinsfile`

### 4. 환경 변수 수정 (Jenkinsfile)
```groovy
environment {
    DOCKER_REGISTRY = 'your-registry.com'  // 실제 레지스트리 주소
    // ... 기타 설정
}
```

## 배포 환경별 설정

### 개발 환경
```bash
docker run -d --name helios-ai-dev \
  -p 8000:8000 \
  -e ENVIRONMENT=development \
  -v $(pwd):/app \
  helios-ai:latest
```

### 스테이징 환경
```bash
docker run -d --name helios-ai-staging \
  -p 8000:8000 \
  -e ENVIRONMENT=staging \
  --restart unless-stopped \
  helios-ai:latest
```

### 프로덕션 환경
```bash
docker run -d --name helios-ai-prod \
  -p 8000:8000 \
  -e ENVIRONMENT=production \
  --restart unless-stopped \
  --memory 2g \
  --cpus 2.0 \
  helios-ai:latest
```

## 모니터링 및 로깅

### 헬스체크
```bash
curl -f http://localhost:8000/health
```

### 로그 확인
```bash
# 컨테이너 로그
docker logs helios-ai

# 실시간 로그
docker logs -f helios-ai
```

### 메트릭 확인
```bash
# 컨테이너 리소스 사용량
docker stats helios-ai

# 컨테이너 정보
docker inspect helios-ai
```

## 백업 및 복원

### 이미지 백업
```bash
# 이미지 저장
docker save helios-ai:latest > helios-ai-backup.tar

# 이미지 로드
docker load < helios-ai-backup.tar
```

### 데이터 백업
```bash
# 볼륨 백업
docker run --rm -v helios_models:/backup-source -v $(pwd):/backup alpine \
  tar czf /backup/models-backup.tar.gz -C /backup-source .
```

## 트러블슈팅

### 일반적인 문제들

1. **컨테이너 시작 실패**
   ```bash
   docker logs helios-ai
   ```

2. **포트 충돌**
   ```bash
   # 다른 포트 사용
   docker run -p 8001:8000 helios-ai:latest
   ```

3. **메모리 부족**
   ```bash
   # 메모리 제한 증가
   docker run --memory 4g helios-ai:latest
   ```

4. **GPU 사용 (CUDA)**
   ```bash
   # NVIDIA Container Runtime 필요
   docker run --gpus all helios-ai:latest
   ```

### 성능 최적화

1. **멀티스테이지 빌드 사용**
   - 현재 Dockerfile은 이미 멀티스테이지 구조

2. **이미지 크기 최적화**
   ```bash
   # Alpine 이미지 사용
   docker build -f Dockerfile.alpine -t helios-ai:alpine .
   ```

3. **캐시 최적화**
   ```bash
   # BuildKit 사용
   DOCKER_BUILDKIT=1 docker build -t helios-ai:latest .
   ```

## 보안 고려사항

1. **비root 사용자 실행** - Dockerfile에서 이미 구현됨
2. **최소 권한 원칙** - 필요한 포트만 노출
3. **시크릿 관리** - 환경 변수 사용
4. **이미지 스캔**
   ```bash
   # 취약점 스캔
   docker scan helios-ai:latest
   ```

## 연락처
- 개발팀: development@helios-cctv.com
- DevOps: devops@helios-cctv.com
