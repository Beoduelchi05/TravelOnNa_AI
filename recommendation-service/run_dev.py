#!/usr/bin/env python3
"""
개발 환경용 추천 서비스 실행 스크립트
"""

import os
import sys
import uvicorn
from pathlib import Path

# 현재 디렉토리를 Python 경로에 추가
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

# 환경변수 설정
os.environ.setdefault('SPRING_PROFILES_ACTIVE', 'default')
os.environ.setdefault('CONFIG_DIR', str(current_dir / 'config'))

if __name__ == "__main__":
    print("🚀 여행ON나 추천 서비스 시작 (개발 모드)")
    print(f"📁 설정 디렉토리: {os.environ['CONFIG_DIR']}")
    print(f"🔧 프로필: {os.environ['SPRING_PROFILES_ACTIVE']}")
    print("=" * 50)
    
    # FastAPI 애플리케이션 실행
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,  # 개발 모드에서는 자동 리로드
        log_level="info",
        access_log=True
    ) 