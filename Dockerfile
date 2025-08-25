# 멀티스테이지 빌드를 위한 베이스 이미지
FROM python:3.9-slim as base

# 시스템 패키지 업데이트 및 필수 도구 설치
RUN apt-get update && apt-get install -y \
    build-essential \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    libgl1-mesa-dev \
    libgstreamer1.0-0 \
    libgstreamer-plugins-base1.0-0 \
    libgtk-3-0 \
    wget \
    curl \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# 작업 디렉토리 설정
WORKDIR /app

# Python 의존성 설치를 위한 단계
FROM base as dependencies

# pip 업그레이드
RUN pip install --upgrade pip

# requirements.txt 복사 및 의존성 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# YOLO 모델 다운로드 (선택사항 - 필요시 활성화)
# RUN python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"

# 최종 프로덕션 이미지
FROM base as production

# 의존성 복사
COPY --from=dependencies /usr/local/lib/python3.9/site-packages /usr/local/lib/python3.9/site-packages
COPY --from=dependencies /usr/local/bin /usr/local/bin

# 애플리케이션 코드 복사
COPY . .

# 비root 사용자 생성
RUN useradd -m -u 1000 appuser

# models 디렉토리 생성 및 권한 설정
RUN mkdir -p /app/models /app/results /app/data && \
    chown -R appuser:appuser /app

# 포트 노출
EXPOSE 8000

# 환경 변수 설정
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# 헬스체크 추가
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 사용자 전환
USER appuser

# 애플리케이션 시작
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
