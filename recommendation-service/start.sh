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

# 로그 디렉토리 생성 및 권한 설정
mkdir -p /app/logs
chmod 755 /app/logs

# Python path 설정
export PYTHONPATH="/app:$PYTHONPATH"

# 프로세스 관리를 위한 변수
BATCH_PID=""
SERVER_PID=""

# 시그널 핸들러
cleanup() {
    echo "🛑 서비스 종료 중..."
    if [ ! -z "$BATCH_PID" ]; then
        kill $BATCH_PID 2>/dev/null || true
    fi
    if [ ! -z "$SERVER_PID" ]; then
        kill $SERVER_PID 2>/dev/null || true
    fi
    sleep 2
    echo "✅ 서비스 종료 완료"
    exit 0
}

trap cleanup SIGTERM SIGINT

# 배치 스케줄러 백그라운드 실행
echo "🕐 배치 스케줄러 시작..."
nohup python /app/batch_runner.py --mode scheduler > /app/logs/batch.log 2>&1 &
BATCH_PID=$!
echo "📝 배치 스케줄러 PID: $BATCH_PID"

# 잠시 대기 (스케줄러 초기화)
sleep 3

# FastAPI 서버 시작
echo "🌐 FastAPI 서버 시작 (포트: 8000)..."
cd /app
nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 > /app/logs/server.log 2>&1 &
SERVER_PID=$!
echo "📝 FastAPI 서버 PID: $SERVER_PID"

# 프로세스 상태 확인
sleep 2
if kill -0 $BATCH_PID 2>/dev/null; then
    echo "✅ 배치 스케줄러 실행 중"
else
    echo "❌ 배치 스케줄러 실행 실패"
fi

if kill -0 $SERVER_PID 2>/dev/null; then
    echo "✅ FastAPI 서버 실행 중"
else
    echo "❌ FastAPI 서버 실행 실패"
fi

echo "🎉 모든 서비스 시작 완료!"
echo "📄 로그 파일:"
echo "   - 배치 로그: /app/logs/batch.log"
echo "   - 서버 로그: /app/logs/server.log"

# 두 프로세스가 모두 실행되는 동안 대기
while kill -0 $BATCH_PID 2>/dev/null && kill -0 $SERVER_PID 2>/dev/null; do
    sleep 10
done

echo "⚠️ 하나 이상의 프로세스가 종료되었습니다"
cleanup 