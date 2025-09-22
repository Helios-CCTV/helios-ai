#!/bin/bash

# Helios AI 도커 빌드 스크립트

set -e  # 오류 발생 시 스크립트 중단

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 로그 함수
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 기본 설정
IMAGE_NAME="helios-ai"
TAG=${1:-"latest"}
REGISTRY=${2:-""}

# 도커 설치 확인
if ! command -v docker &> /dev/null; then
    log_error "Docker가 설치되어 있지 않습니다."
    exit 1
fi

# 도커 서비스 실행 확인
if ! docker info &> /dev/null; then
    log_error "Docker 서비스가 실행되고 있지 않습니다."
    exit 1
fi

log_info "도커 이미지 빌드 시작..."
log_info "이미지: ${IMAGE_NAME}:${TAG}"

# 이전 빌드 캐시 정리 (선택사항)
read -p "이전 빌드 캐시를 정리하시겠습니까? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    log_info "빌드 캐시 정리 중..."
    docker builder prune -f
fi

# 도커 이미지 빌드
log_info "도커 이미지 빌드 중..."
if docker build -t "${IMAGE_NAME}:${TAG}" .; then
    log_info "도커 이미지 빌드 성공!"
else
    log_error "도커 이미지 빌드 실패!"
    exit 1
fi

# latest 태그 생성
if [ "$TAG" != "latest" ]; then
    log_info "latest 태그 생성 중..."
    docker tag "${IMAGE_NAME}:${TAG}" "${IMAGE_NAME}:latest"
fi

# 이미지 크기 확인
log_info "빌드된 이미지 정보:"
docker images "${IMAGE_NAME}:${TAG}"

# 컨테이너 테스트
log_info "컨테이너 테스트 시작..."
CONTAINER_NAME="helios-ai-test-$$"

# 테스트 컨테이너 실행
if docker run -d --name "$CONTAINER_NAME" -p 8001:8000 "${IMAGE_NAME}:${TAG}"; then
    log_info "테스트 컨테이너 실행 성공"
    
    # 컨테이너 시작 대기
    log_info "컨테이너 시작 대기 중..."
    sleep 30
    
    # 헬스체크
    if curl -f http://localhost:8001/health &> /dev/null; then
        log_info "헬스체크 성공!"
    else
        log_warn "헬스체크 실패 - 컨테이너 로그 확인"
        docker logs "$CONTAINER_NAME"
    fi
    
    # 테스트 컨테이너 정리
    log_info "테스트 컨테이너 정리 중..."
    docker stop "$CONTAINER_NAME" &> /dev/null
    docker rm "$CONTAINER_NAME" &> /dev/null
else
    log_error "테스트 컨테이너 실행 실패!"
    exit 1
fi

# 레지스트리 푸시 (선택사항)
if [ -n "$REGISTRY" ]; then
    log_info "레지스트리에 푸시 중: $REGISTRY"
    
    # 레지스트리 태그 생성
    docker tag "${IMAGE_NAME}:${TAG}" "${REGISTRY}/${IMAGE_NAME}:${TAG}"
    docker tag "${IMAGE_NAME}:latest" "${REGISTRY}/${IMAGE_NAME}:latest"
    
    # 푸시
    if docker push "${REGISTRY}/${IMAGE_NAME}:${TAG}" && docker push "${REGISTRY}/${IMAGE_NAME}:latest"; then
        log_info "레지스트리 푸시 성공!"
    else
        log_error "레지스트리 푸시 실패!"
        exit 1
    fi
fi

log_info "빌드 완료! 🎉"
log_info "실행 명령어: docker run -d --name helios-ai -p 8000:8000 ${IMAGE_NAME}:${TAG}"
