@echo off
echo [INFO] 헬리오스 AI 베이스 이미지 빌드 시작...

set IMAGE_NAME=helios-ai-base
set IMAGE_TAG=latest

echo [INFO] 베이스 이미지 빌드 중...
docker build --no-cache -f Dockerfile.base -t %IMAGE_NAME%:%IMAGE_TAG% .

if %ERRORLEVEL% neq 0 (
    echo [ERROR] ❌ 베이스 이미지 빌드 실패!
    exit /b 1
)

echo [INFO] ✅ 베이스 이미지 빌드 완료: %IMAGE_NAME%:%IMAGE_TAG%

echo [INFO] 패키지 임포트 테스트 중...
docker run --rm %IMAGE_NAME%:%IMAGE_TAG% python -c "import cv2, torch, ultralytics; print('✅ 모든 패키지 임포트 성공!')"

if %ERRORLEVEL% neq 0 (
    echo [ERROR] ❌ 패키지 임포트 테스트 실패!
    exit /b 1
)

echo [INFO] 🎉 베이스 이미지 준비 완료!
echo [INFO] 이제 'docker build -f Dockerfile.production .' 로 애플리케이션 이미지를 빌드할 수 있습니다.

pause
