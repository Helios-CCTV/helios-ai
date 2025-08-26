# ---------- builder: 의존성 설치 ----------
FROM python:3.11-slim AS builder

# 빌드에 필요한 OS 패키지 (컴파일러 등)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# venv 생성 (site-packages를 깔끔하게 묶기 위함)
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# requirements만 먼저 복사 → 캐시 최대로 활용
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# 소스 복사
COPY . .

# (필요 시) 모델/데이터는 빌드 타임에 받지 말고 런타임/볼륨으로


# ---------- production: 런타임만 ----------
FROM python:3.11-slim AS production

# 런타임에 필요한 OS 라이브러리만 (GUI/FFmpeg 등 꼭 필요한 것만)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 libsm6 libxext6 libxrender1 libgomp1 libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# builder의 가상환경만 복사 (훨씬 작고 깔끔)
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1

# 앱 코드만 복사
COPY . .

# 비루트 사용자
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# 헬스체크 (curl 필요시 이미지에 추가 설치하거나 python 요청으로 대체)
# HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
#   CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
