#!/bin/bash

# Helios AI 베이스 이미지 빌드 스크립트

set -e

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 설정
BASE_IMAGE_NAME="helios-ai-base"
BASE_TAG=${1:-"latest"}
REGISTRY=${2:-""}

log_info "베이스 이미지 빌드 시작..."
log_info "이미지: ${BASE_IMAGE_NAME}:${BASE_TAG}"

# requirements.txt 존재 확인
if [ ! -f "requirements.txt" ]; then
    log_error "requirements.txt 파일이 없습니다."
    exit 1
fi

# 베이스 이미지 빌드
log_info "베이스 이미지 빌드 중..."
if docker build --no-cache -f Dockerfile.base -t "${BASE_IMAGE_NAME}:${BASE_TAG}" .; then
    log_info "✅ 베이스 이미지 빌드 성공!"
else
    log_error "❌ 베이스 이미지 빌드 실패!"
    exit 1
fi

# latest 태그 생성
if [ "$BASE_TAG" != "latest" ]; then
    log_info "latest 태그 생성 중..."
    docker tag "${BASE_IMAGE_NAME}:${BASE_TAG}" "${BASE_IMAGE_NAME}:latest"
fi

# 이미지 크기 확인
log_info "베이스 이미지 정보:"
docker images "${BASE_IMAGE_NAME}:${BASE_TAG}"

# 베이스 이미지 테스트 (Python 패키지 import 테스트)
log_info "베이스 이미지 테스트 중..."
TEST_CONTAINER="base-test-$$"

if docker run --rm --name "$TEST_CONTAINER" "${BASE_IMAGE_NAME}:${BASE_TAG}" python -c "
import fastapi
import torch
import cv2
import numpy as np
import mysql.connector
try:
    import ultralytics
    print('✅ ultralytics 패키지 포함!')
except ImportError:
    print('⚠️  ultralytics 패키지 없음 (선택사항)')
print('✅ 필수 패키지 import 성공!')
"; then
    log_info "✅ 베이스 이미지 테스트 성공!"
else
    log_error "❌ 베이스 이미지 테스트 실패!"
    exit 1
fi

# 레지스트리 푸시 (선택사항)
if [ -n "$REGISTRY" ]; then
    log_info "레지스트리에 푸시 중: $REGISTRY"
    
    # 레지스트리 태그 생성
    docker tag "${BASE_IMAGE_NAME}:${BASE_TAG}" "${REGISTRY}/${BASE_IMAGE_NAME}:${BASE_TAG}"
    docker tag "${BASE_IMAGE_NAME}:latest" "${REGISTRY}/${BASE_IMAGE_NAME}:latest"
    
    # 푸시
    if docker push "${REGISTRY}/${BASE_IMAGE_NAME}:${BASE_TAG}" && docker push "${REGISTRY}/${BASE_IMAGE_NAME}:latest"; then
        log_info "✅ 레지스트리 푸시 성공!"
    else
        log_error "❌ 레지스트리 푸시 실패!"
        exit 1
    fi
fi

log_info "🎉 베이스 이미지 빌드 완료!"
log_info "사용법: docker build -f Dockerfile.production -t helios-ai:latest ."
