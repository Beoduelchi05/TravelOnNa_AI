#!/bin/bash
set -e

echo "🚀 여행ON나 AI 추천 서비스 시작..."

# 환경 변수 확인
if [ -z "$CONFIG_DIR" ]; then
    export CONFIG_DIR="/app/config"
fi

echo "📁 설정 디렉토리: $CONFIG_DIR"

# 설정 파일 존재 확인
if [ ! -f "$CONFIG_DIR/application.yml" ]; then
    echo "❌ 설정 파일을 찾을 수 없습니다: $CONFIG_DIR/application.yml"
    exit 1
fi

# 모델 파일 존재 확인
if [ ! -f "/app/models/als_model.pkl" ]; then
    echo "❌ ALS 모델 파일을 찾을 수 없습니다: /app/models/als_model.pkl"
    exit 1
fi

# 로그 디렉토리 생성
mkdir -p /app/logs

# Python path 설정
export PYTHONPATH="/app:$PYTHONPATH"

# 배치 스케줄러 백그라운드 실행
echo "🕐 배치 스케줄러 시작..."
python /app/batch_runner.py --mode scheduler &
BATCH_PID=$!

# FastAPI 서버 시작
echo "🌐 FastAPI 서버 시작 (포트: 8000)..."
cd /app
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 &
SERVER_PID=$!

# 시그널 핸들러
cleanup() {
    echo "🛑 서비스 종료 중..."
    kill $BATCH_PID 2>/dev/null || true
    kill $SERVER_PID 2>/dev/null || true
    wait
    echo "✅ 서비스 종료 완료"
    exit 0
}

trap cleanup SIGTERM SIGINT

# 프로세스 대기
wait 