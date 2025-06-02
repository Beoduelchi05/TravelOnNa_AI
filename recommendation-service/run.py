#!/usr/bin/env python3
"""
TravelOnNa AI 추천 서비스 실행 스크립트
"""
import uvicorn
import os
import sys

def main():
    """FastAPI 서버 실행"""
    
    # 환경 설정
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 8000))
    reload = os.getenv("RELOAD", "true").lower() == "true"
    log_level = os.getenv("LOG_LEVEL", "info")
    
    print("🚀 TravelOnNa AI 추천 서비스 시작")
    print(f"   - 호스트: {host}")
    print(f"   - 포트: {port}")
    print(f"   - 리로드: {reload}")
    print(f"   - 로그레벨: {log_level}")
    print("   - 종료: Ctrl+C")
    print()
    
    try:
        uvicorn.run(
            "app.main:app",
            host=host,
            port=port,
            reload=reload,
            log_level=log_level,
            access_log=True
        )
    except KeyboardInterrupt:
        print("\n👋 서비스가 종료되었습니다.")
    except Exception as e:
        print(f"❌ 서버 시작 실패: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 