pipeline {
    agent any
    
    environment {
        // Git 설정
        GIT_URL = 'https://github.com/Helios-CCTV/helios-ai.git'
        GIT_BRANCH = 'main'
        GIT_CREDENTIALSID = 'github-credentials'
        
        // 이미지 설정
        BASE_IMAGE = 'helios-ai-base'
        BACKEND_IMAGE = 'helios-ai'
        TAG = "${BUILD_NUMBER}"
        
        // 베이스 이미지 강제 재빌드 여부 (수동 설정)
        REBUILD_BASE = "${params.REBUILD_BASE ?: 'false'}"
    }
    
    parameters {
        booleanParam(
            name: 'REBUILD_BASE',
            defaultValue: false,
            description: '베이스 이미지를 강제로 재빌드할지 여부'
        )
    }
    
    stages {
        stage('Git Clone') {
            steps {
                git branch: "${GIT_BRANCH}", credentialsId: "${GIT_CREDENTIALSID}", url: "${GIT_URL}"
            }
        }
        
        stage('Check Base Image Requirements') {
            steps {
                script {
                    // requirements.txt 변경 감지
                    def requirementsChanged = sh(
                        script: "git diff HEAD~1 HEAD --name-only | grep -q requirements.txt || echo 'no-change'",
                        returnStdout: true
                    ).trim()
                    
                    if (requirementsChanged != 'no-change') {
                        echo "📦 requirements.txt 변경 감지 - 베이스 이미지 재빌드 필요"
                        env.REBUILD_BASE = 'true'
                    }
                    
                    // 베이스 이미지 존재 확인
                    def baseExists = sh(
                        script: "docker image inspect ${BASE_IMAGE}:latest >/dev/null 2>&1",
                        returnStatus: true
                    )
                    
                    if (baseExists != 0) {
                        echo "🔍 베이스 이미지가 없음 - 베이스 이미지 빌드 필요"
                        env.REBUILD_BASE = 'true'
                    }
                }
            }
        }
        
        stage('Build Base Image') {
            when {
                environment name: 'REBUILD_BASE', value: 'true'
            }
            steps {
                script {
                    echo "🏗️ 베이스 이미지 빌드 시작..."
                    
                    sh '''bash -Eeuo pipefail -c '
                        # 베이스 이미지 빌드
                        echo "[INFO] 베이스 이미지 빌드 중..."
                        docker build --no-cache -f Dockerfile.base -t ${BASE_IMAGE}:latest .
                        
                        # 베이스 이미지 테스트
                        echo "[INFO] 베이스 이미지 패키지 테스트..."
                        docker run --rm ${BASE_IMAGE}:latest python -c "
import fastapi
import torch
import cv2
import numpy as np
import mysql.connector
print('✅ 베이스 이미지 패키지 테스트 성공!')
"
                        
                        echo "[INFO] ✅ 베이스 이미지 빌드 완료"
                    ' '''
                }
            }
        }
        
        stage('Build Application Image') {
            steps {
                script {
                    echo "🚀 애플리케이션 이미지 빌드 시작..."
                    
                    sh '''bash -Eeuo pipefail -c '
                        if docker buildx version >/dev/null 2>&1; then
                            echo "[INFO] buildx detected. Using docker buildx…"
                            
                            mkdir -p /tmp/.buildx-cache /tmp/.buildx-cache-new
                            
                            # 오래된 캐시 정리
                            docker buildx prune -f --keep-storage 2GB || true
                            
                            # 애플리케이션 이미지 빌드 (베이스 이미지 사용)
                            docker buildx build \
                                --cache-from=type=local,src=/tmp/.buildx-cache \
                                --cache-to=type=local,dest=/tmp/.buildx-cache-new,mode=max \
                                -t ${BACKEND_IMAGE}:${TAG} -t ${BACKEND_IMAGE}:latest \
                                --load \
                                -f Dockerfile .
                            
                            # 캐시 디렉토리 교체
                            rm -rf /tmp/.buildx-cache
                            mv /tmp/.buildx-cache-new /tmp/.buildx-cache
                        else
                            echo "[INFO] buildx not found. Using standard docker build."
                            export DOCKER_BUILDKIT=1
                            
                            # 애플리케이션 이미지 빌드
                            docker build \
                                -t ${BACKEND_IMAGE}:${TAG} -t ${BACKEND_IMAGE}:latest \
                                -f Dockerfile .
                        fi
                        
                        echo "[INFO] ✅ 애플리케이션 이미지 빌드 완료"
                        
                        # 이미지 크기 비교
                        echo "[INFO] === 이미지 크기 비교 ==="
                        docker images | grep -E "(${BASE_IMAGE}|${BACKEND_IMAGE})" || true
                    ' '''
                }
            }
        }
        
        stage('Stream Upload to Swift (gz)') {
            steps {
                withCredentials([usernamePassword(
                    credentialsId: 'openstack-cred',
                    usernameVariable: 'OS_USERNAME',
                    passwordVariable: 'OS_PASSWORD'
                )]) {
                    sh '''bash -Eeuo pipefail -c '
                        export OS_AUTH_URL=http://controller:5000/v3
                        export OS_PROJECT_NAME=NETCC_Helios
                        export OS_USER_DOMAIN_NAME=Default
                        export OS_PROJECT_DOMAIN_NAME=Default
                        export OS_IDENTITY_API_VERSION=3
                        
                        CONTAINER="artifacts"
                        SEGMENT_CONTAINER="artifacts_segments"
                        SEGMENT_SIZE=$((1024*1024*1024))   # 1GiB
                        PREFIX="mainback"
                        NAME="$(basename "${BACKEND_IMAGE}")"
                        
                        # 컨테이너 생성
                        swift post "$CONTAINER" || true
                        swift post "$SEGMENT_CONTAINER" || true
                        
                        # 압축 도구 선택
                        if command -v pigz >/dev/null 2>&1; then
                            COMPRESSOR="pigz -c -n -p $(nproc)"
                        else
                            COMPRESSOR="gzip -c -n"
                        fi
                        
                        # TAG 버전 업로드
                        echo "[INFO] ${BACKEND_IMAGE}:${TAG} 업로드 중..."
                        docker save "${BACKEND_IMAGE}:${TAG}" \
                            | ${COMPRESSOR} \
                            | swift upload "$CONTAINER" - \
                                --object-name "${PREFIX}/${NAME}_${TAG}.tar.gz" \
                                --segment-size "$SEGMENT_SIZE" \
                                --segment-container "$SEGMENT_CONTAINER" \
                                --use-slo
                        
                        # latest 버전 업로드
                        echo "[INFO] ${BACKEND_IMAGE}:latest 업로드 중..."
                        docker save "${BACKEND_IMAGE}:latest" \
                            | ${COMPRESSOR} \
                            | swift upload "$CONTAINER" - \
                                --object-name "${PREFIX}/${NAME}_latest.tar.gz" \
                                --segment-size "$SEGMENT_SIZE" \
                                --segment-container "$SEGMENT_CONTAINER" \
                                --use-slo
                        
                        echo "[INFO] ✅ Swift 업로드 완료"
                    ' '''
                }
            }
        }
        
        stage('Cleanup') {
            steps {
                script {
                    sh '''bash -Eeuo pipefail -c '
                        # 애플리케이션 이미지만 정리 (베이스 이미지는 보존)
                        docker rmi -f "${BACKEND_IMAGE}:${TAG}" "${BACKEND_IMAGE}:latest" || true
                        
                        # 불필요한 이미지 정리
                        docker image prune -f || true
                        docker builder prune -f --filter type=exec.cachemount || true
                        
                        echo "[INFO] ✅ 정리 완료"
                    ' '''
                }
            }
        }
    }
    
    post {
        always {
            script {
                // 빌드 결과 요약
                def baseStatus = env.REBUILD_BASE == 'true' ? '🔄 재빌드됨' : '✅ 기존 사용'
                def summary = """
                📊 **빌드 요약**
                - 베이스 이미지: ${baseStatus}
                - 애플리케이션 이미지: ${BACKEND_IMAGE}:${TAG}
                - 빌드 시간: ${currentBuild.durationString}
                """
                echo summary
            }
        }
        success {
            echo "🎉 배포 성공! 이미지가 Swift에 업로드되었습니다."
        }
        failure {
            echo "❌ 배포 실패. 로그를 확인해주세요."
        }
    }
}
