# syntax=docker/dockerfile:1.4
# Python 3.11 베이스 이미지 사용
FROM python:3.11-slim as base

# 빌드 인수 정의
ARG BUILD_DATE
ARG VCS_REF  
ARG BUILD_NUMBER
ARG TARGETPLATFORM
ARG TARGETARCH

# 메타데이터 라벨 추가
LABEL org.opencontainers.image.title="TravelOnNa AI Recommendation Service"
LABEL org.opencontainers.image.description="FastAPI-based AI recommendation service for TravelOnNa"
LABEL org.opencontainers.image.version="${BUILD_NUMBER}"
LABEL org.opencontainers.image.created="${BUILD_DATE}"
LABEL org.opencontainers.image.revision="${VCS_REF}"
LABEL org.opencontainers.image.vendor="TravelOnNa"
LABEL org.opencontainers.image.source="https://github.com/Beoduelchi05/TravelOnNa_AI.git"

# 작업 디렉토리 설정
WORKDIR /app

# 시스템 패키지 업데이트 및 필요한 패키지 설치
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Python 의존성 설치 단계 (캐시 최적화)
FROM base as deps
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 최종 실행 단계
FROM base as runtime

# Python 의존성 복사
COPY --from=deps /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin

# 애플리케이션 코드 복사
COPY . .

# 모델 디렉토리 생성 및 모델 파일 복사
RUN mkdir -p /app/models
COPY models/ /app/models/

# 시작 스크립트 실행 권한 부여
RUN chmod +x start.sh

# 플랫폼 정보 출력 (디버깅용)
RUN echo "Building for platform: $TARGETPLATFORM, architecture: $TARGETARCH"

# 헬스체크용 사용자 생성 (보안 강화)
RUN groupadd -r appuser && useradd -r -g appuser appuser
RUN chown -R appuser:appuser /app
USER appuser

# 실행할 포트 노출
EXPOSE 8000

# 헬스체크 추가 (더 안정적인 설정)
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 환경변수 설정
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# 애플리케이션 실행 (API 서버 + 배치 스케줄러)
CMD ["./start.sh"]