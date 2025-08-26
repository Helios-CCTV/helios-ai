pipeline {
    agent any
    
    environment {
        DOCKER_IMAGE = 'helios-ai'
        BASE_IMAGE = 'helios-ai-base'
        DOCKER_TAG = "${BUILD_NUMBER}"
        DOCKER_REGISTRY = 'your-registry.com'  // 실제 레지스트리 주소로 변경
        CONTAINER_NAME = 'helios-ai-app'
        
        // 기존 스타일과 호환성을 위한 변수들
        BACKEND_IMAGE = "${DOCKER_IMAGE}"
        TAG = "${DOCKER_TAG}"
    }
    
    stages {
        stage('Checkout') {
            steps {
                checkout scm
                echo "체크아웃 완료: ${env.GIT_COMMIT}"
            }
        }
        
        stage('Check Requirements Changes') {
            steps {
                script {
                    // requirements.txt 변경 여부 확인
                    def requirementsChanged = sh(
                        script: "git diff HEAD~1 HEAD --name-only | grep requirements.txt || true",
                        returnStdout: true
                    ).trim()
                    
                    env.REBUILD_BASE = requirementsChanged ? "true" : "false"
                    
                    if (env.REBUILD_BASE == "true") {
                        echo "⚠️ requirements.txt가 변경되어 베이스 이미지를 다시 빌드합니다."
                    } else {
                        echo "✅ requirements.txt 변경 없음. 기존 베이스 이미지 사용."
                    }
                }
            }
        }
        
        stage('Build Base Image') {
            when {
                anyOf {
                    environment name: 'REBUILD_BASE', value: 'true'
                    not { 
                        script { 
                            return sh(
                                script: "docker image inspect ${DOCKER_REGISTRY}/${BASE_IMAGE}:latest >/dev/null 2>&1",
                                returnStatus: true
                            ) == 0 
                        }
                    }
                }
            }
            steps {
                script {
                    echo "베이스 이미지 빌드 시작..."
                    
                    def baseImageName = "${BASE_IMAGE}:latest"
                    
                    sh """
                        docker build -f Dockerfile.base -t ${baseImageName} .
                        docker tag ${baseImageName} ${DOCKER_REGISTRY}/${baseImageName}
                    """
                    
                    echo "베이스 이미지 빌드 완료: ${baseImageName}"
                }
            }
        }
        
        stage('Pull Base Image') {
            when {
                environment name: 'REBUILD_BASE', value: 'false'
            }
            steps {
                script {
                    echo "기존 베이스 이미지 pull 중..."
                    sh """
                        docker pull ${DOCKER_REGISTRY}/${BASE_IMAGE}:latest || echo "베이스 이미지 pull 실패 - 로컬 이미지 사용"
                        docker tag ${DOCKER_REGISTRY}/${BASE_IMAGE}:latest ${BASE_IMAGE}:latest || true
                    """
                }
            }
        }
        
        stage('Build App Image') {
            steps {
                script {
                    echo "애플리케이션 이미지 빌드 시작..."
                    
                    def imageName = "${DOCKER_IMAGE}:${DOCKER_TAG}"
                    def latestImageName = "${DOCKER_IMAGE}:latest"
                    
                    sh """
                        docker build -f Dockerfile.production -t ${imageName} -t ${latestImageName} .
                    """
                    
                    echo "애플리케이션 이미지 빌드 완료: ${imageName}"
                }
            }
        }
        
        stage('Test Container') {
            steps {
                script {
                    echo "컨테이너 테스트 시작..."
                    
                    def imageName = "${DOCKER_IMAGE}:${DOCKER_TAG}"
                    
                    // 테스트 컨테이너 실행
                    sh """
                        docker run --rm -d --name test-${BUILD_NUMBER} \
                        -p 8001:8000 \
                        ${imageName}
                    """
                    
                    // 헬스체크 대기
                    sleep(time: 30, unit: 'SECONDS')
                    
                    // 헬스체크 실행
                    script {
                        def healthCheck = sh(
                            script: "curl -f http://localhost:8001/health || exit 1",
                            returnStatus: true
                        )
                        
                        if (healthCheck != 0) {
                            error("헬스체크 실패")
                        }
                    }
                    
                    echo "컨테이너 테스트 성공"
                }
            }
            post {
                always {
                    // 테스트 컨테이너 정리
                    sh "docker stop test-${BUILD_NUMBER} || true"
                    sh "docker rm test-${BUILD_NUMBER} || true"
                }
            }
        }
        
        stage('Push to Registry') {
            when {
                anyOf {
                    branch 'main'
                    branch 'master'
                    branch 'feature/AI-result'
                }
            }
            steps {
                script {
                    echo "도커 레지스트리에 푸시 시작..."
                    
                    def imageName = "${DOCKER_IMAGE}:${DOCKER_TAG}"
                    def latestImageName = "${DOCKER_IMAGE}:latest"
                    
                    // 레지스트리에 로그인 (Jenkins credentials 사용)
                    docker.withRegistry("https://${DOCKER_REGISTRY}", 'docker-registry-credentials') {
                        // 앱 이미지 푸시
                        sh """
                            docker tag ${imageName} ${DOCKER_REGISTRY}/${imageName}
                            docker tag ${latestImageName} ${DOCKER_REGISTRY}/${latestImageName}
                            docker push ${DOCKER_REGISTRY}/${imageName}
                            docker push ${DOCKER_REGISTRY}/${latestImageName}
                        """
                        
                        // 베이스 이미지도 푸시 (변경된 경우)
                        if (env.REBUILD_BASE == "true") {
                            sh """
                                docker push ${DOCKER_REGISTRY}/${BASE_IMAGE}:latest
                            """
                        }
                    }
                    
                    echo "도커 레지스트리 푸시 완료"
                }
            }
        }
        
        stage('Export Docker Image') {
            steps {
                script {
                    def imageName = "${DOCKER_IMAGE}:${DOCKER_TAG}"
                    def tarFileName = "${DOCKER_IMAGE}-${DOCKER_TAG}.tar"
                    
                    sh """
                        echo "도커 이미지를 tar 파일로 내보내기..."
                        docker save -o ${tarFileName} ${imageName}
                        
                        echo "tar 파일 크기 확인..."
                        ls -lh ${tarFileName}
                        
                        echo "tar 파일 압축..."
                        gzip ${tarFileName}
                    """
                    
                    // tar 파일 정보를 환경변수로 저장
                    env.TAR_FILE_NAME = "${tarFileName}.gz"
                }
            }
        }
        
        stage('Upload to Object Storage') {
            steps {
                script {
                    sh """
                        echo "오브젝트 스토리지에 업로드 중..."
                        
                        # 실제 오브젝트 스토리지 API에 맞게 수정 필요
                        # 예시: AWS S3
                        # aws s3 cp ${env.TAR_FILE_NAME} s3://your-bucket/docker-images/
                        
                        # 예시: curl을 사용한 HTTP 업로드
                        # curl -X POST -H "Authorization: Bearer \${STORAGE_TOKEN}" \
                        #      -F "file=@${env.TAR_FILE_NAME}" \
                        #      https://your-storage-api/upload
                        
                        echo "업로드 완료: ${env.TAR_FILE_NAME}"
                    """
                }
            }
        }
        
        stage('Cleanup') {
            steps {
                script {
                    sh """
                        echo "임시 파일 정리..."
                        rm -f ${env.TAR_FILE_NAME}
                        
                        echo "오래된 도커 이미지 정리..."
                        docker image prune -f
                        
                        # 오래된 앱 이미지만 정리 (베이스 이미지는 유지)
                        docker images ${DOCKER_IMAGE} --format "table {{.Tag}}" | \
                        grep -E '^[0-9]+\$' | sort -n | head -n -5 | \
                        xargs -r -I {} docker rmi ${DOCKER_IMAGE}:{} || true
                    """
                }
            }
        }
    }
    
    post {
        always {
            cleanWs()
        }
        success {
            echo "파이프라인 성공! 🎉"
            script {
                if (env.REBUILD_BASE == "true") {
                    echo "📦 베이스 이미지가 업데이트되었습니다."
                }
            }
        }
        failure {
            echo "파이프라인 실패! ❌"
        }
    }
}
