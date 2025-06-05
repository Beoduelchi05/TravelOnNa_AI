#!/bin/bash

# TravelOnNa 추천 서비스 시작 스크립트
echo "🚀 TravelOnNa 추천 서비스 시작"

# 로그 디렉토리 생성
mkdir -p /app/logs

# 배경에서 배치 스케줄러 실행
echo "📅 배치 스케줄러 시작..."
python batch_runner.py --mode scheduler > /app/logs/batch.log 2>&1 &
BATCH_PID=$!

# API 서버 실행 (전면 프로세스)
echo "🌐 API 서버 시작..."
python run.py &
API_PID=$!

# 시그널 핸들러 설정
cleanup() {
    echo "🛑 서비스 종료 중..."
    kill $BATCH_PID 2>/dev/null
    kill $API_PID 2>/dev/null
    wait
    echo "✅ 서비스 종료 완료"
    exit 0
}

trap cleanup SIGTERM SIGINT

# 두 프로세스 모두 실행될 때까지 대기
wait $API_PID $BATCH_PID 