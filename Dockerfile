# 의존성(ultralytics/torch 등) 포함된 베이스
FROM helios-ai-base:latest
WORKDIR /app

# 코드만 복사 (.dockerignore로 불필요물 제외)
COPY . .

# 빌드 시 커밋 해시 주입(옵션)
ARG GIT_SHA=unknown
LABEL org.opencontainers.image.revision=$GIT_SHA

ENV PYTHONUNBUFFERED=1
# 필요 시 포트/엔트리포인트 조정
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
