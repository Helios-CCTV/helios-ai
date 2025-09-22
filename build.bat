@echo off
REM Helios AI 도커 빌드 스크립트 (Windows)

setlocal enabledelayedexpansion

REM 기본 설정
set IMAGE_NAME=helios-ai
set TAG=%1
if "%TAG%"=="" set TAG=latest
set REGISTRY=%2

echo [INFO] 도커 이미지 빌드 시작...
echo [INFO] 이미지: %IMAGE_NAME%:%TAG%

REM 도커 설치 확인
docker --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker가 설치되어 있지 않습니다.
    exit /b 1
)

REM 도커 서비스 실행 확인
docker info >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker 서비스가 실행되고 있지 않습니다.
    exit /b 1
)

REM 도커 이미지 빌드
echo [INFO] 도커 이미지 빌드 중...
docker build -t "%IMAGE_NAME%:%TAG%" .
if errorlevel 1 (
    echo [ERROR] 도커 이미지 빌드 실패!
    exit /b 1
)

echo [INFO] 도커 이미지 빌드 성공!

REM latest 태그 생성
if not "%TAG%"=="latest" (
    echo [INFO] latest 태그 생성 중...
    docker tag "%IMAGE_NAME%:%TAG%" "%IMAGE_NAME%:latest"
)

REM 이미지 크기 확인
echo [INFO] 빌드된 이미지 정보:
docker images "%IMAGE_NAME%:%TAG%"

REM 컨테이너 테스트
echo [INFO] 컨테이너 테스트 시작...
set CONTAINER_NAME=helios-ai-test-%RANDOM%

REM 테스트 컨테이너 실행
docker run -d --name "%CONTAINER_NAME%" -p 8001:8000 "%IMAGE_NAME%:%TAG%"
if errorlevel 1 (
    echo [ERROR] 테스트 컨테이너 실행 실패!
    exit /b 1
)

echo [INFO] 테스트 컨테이너 실행 성공

REM 컨테이너 시작 대기
echo [INFO] 컨테이너 시작 대기 중...
timeout /t 30 /nobreak >nul

REM 헬스체크
curl -f http://localhost:8001/health >nul 2>&1
if errorlevel 1 (
    echo [WARN] 헬스체크 실패 - 컨테이너 로그 확인
    docker logs "%CONTAINER_NAME%"
) else (
    echo [INFO] 헬스체크 성공!
)

REM 테스트 컨테이너 정리
echo [INFO] 테스트 컨테이너 정리 중...
docker stop "%CONTAINER_NAME%" >nul 2>&1
docker rm "%CONTAINER_NAME%" >nul 2>&1

REM 레지스트리 푸시 (선택사항)
if not "%REGISTRY%"=="" (
    echo [INFO] 레지스트리에 푸시 중: %REGISTRY%
    
    REM 레지스트리 태그 생성
    docker tag "%IMAGE_NAME%:%TAG%" "%REGISTRY%/%IMAGE_NAME%:%TAG%"
    docker tag "%IMAGE_NAME%:latest" "%REGISTRY%/%IMAGE_NAME%:latest"
    
    REM 푸시
    docker push "%REGISTRY%/%IMAGE_NAME%:%TAG%"
    docker push "%REGISTRY%/%IMAGE_NAME%:latest"
    if errorlevel 1 (
        echo [ERROR] 레지스트리 푸시 실패!
        exit /b 1
    )
    echo [INFO] 레지스트리 푸시 성공!
)

echo [INFO] 빌드 완료! 🎉
echo [INFO] 실행 명령어: docker run -d --name helios-ai -p 8000:8000 %IMAGE_NAME%:%TAG%

endlocal
