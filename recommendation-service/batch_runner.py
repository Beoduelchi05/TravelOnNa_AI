#!/usr/bin/env python3
"""
여행ON나 추천시스템 배치 처리 스케줄러

사용법:
  python batch_runner.py --mode scheduler    # 스케줄러 모드 (데몬)
  python batch_runner.py --mode full         # 전체 배치 처리 (일회성)
  python batch_runner.py --mode incremental  # 증분 배치 처리 (일회성)
"""

import argparse
import asyncio
import sys
import signal
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
sys.path.append(str(Path(__file__).parent))

from app.services.batch_service import BatchService
from app.utils.logger import get_logger

logger = get_logger(__name__)

class BatchRunner:
    """배치 처리 실행기"""
    
    def __init__(self):
        self.batch_service = BatchService()
        self.running = True
    
    def signal_handler(self, signum, frame):
        """시그널 핸들러 (Ctrl+C 등)"""
        logger.info(f"📡 시그널 {signum} 수신, 종료 처리 시작...")
        self.running = False
        self.batch_service.stop_scheduler()
        sys.exit(0)
    
    async def run_once(self, mode: str):
        """일회성 배치 실행"""
        logger.info(f"🎯 일회성 배치 실행: {mode}")
        
        try:
            if mode == "full":
                success = await self.batch_service.run_full_batch()
            elif mode == "incremental":
                success = await self.batch_service.run_incremental_batch()
            else:
                logger.error(f"❌ 지원하지 않는 모드: {mode}")
                return False
            
            if success:
                logger.info(f"✅ {mode} 배치 처리 성공")
                return True
            else:
                logger.error(f"❌ {mode} 배치 처리 실패")
                return False
                
        except Exception as e:
            logger.error(f"❌ 배치 실행 중 오류: {str(e)}")
            return False
    
    def run_scheduler(self):
        """스케줄러 모드 실행"""
        logger.info("🕐 스케줄러 모드 시작")
        logger.info("   - 초기 전체 배치: 즉시 실행")
        logger.info("   - 전체 배치: 매일 새벽 2시")
        logger.info("   - 증분 배치: 6시간마다")
        logger.info("   - 종료: Ctrl+C")
        
        # 시그널 핸들러 등록
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
        try:
            # 시작 시 즉시 전체 배치 실행
            logger.info("🚀 시작 시 초기 전체 배치 실행...")
            initial_success = asyncio.run(self.batch_service.run_full_batch())
            if initial_success:
                logger.info("✅ 초기 전체 배치 완료")
            else:
                logger.warning("⚠️ 초기 전체 배치 실패 - 스케줄러는 계속 실행")
            
            # 스케줄러 시작 (블로킹)
            self.batch_service.start_scheduler()
        except KeyboardInterrupt:
            logger.info("🛑 사용자 중단 요청")
        except Exception as e:
            logger.error(f"❌ 스케줄러 실행 오류: {str(e)}")
        finally:
            logger.info("⏹️ 배치 스케줄러 종료")

def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(
        description="여행ON나 추천시스템 배치 처리기",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
사용 예시:
  python batch_runner.py --mode scheduler      # 스케줄러 시작 (데몬 모드)
  python batch_runner.py --mode full           # 전체 배치 처리 실행
  python batch_runner.py --mode incremental    # 증분 배치 처리 실행
  
스케줄:
  - 전체 배치: 매일 새벽 2:00
  - 증분 배치: 6시간마다
        """
    )
    
    parser.add_argument(
        "--mode", 
        choices=["scheduler", "full", "incremental"],
        required=True,
        help="실행 모드 선택"
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="상세 로그 출력"
    )
    
    args = parser.parse_args()
    
    # 로거 레벨 설정
    if args.verbose:
        import logging
        logging.getLogger().setLevel(logging.DEBUG)
    
    runner = BatchRunner()
    
    try:
        if args.mode == "scheduler":
            # 스케줄러 모드
            runner.run_scheduler()
        else:
            # 일회성 실행 모드
            success = asyncio.run(runner.run_once(args.mode))
            exit_code = 0 if success else 1
            sys.exit(exit_code)
            
    except Exception as e:
        logger.error(f"❌ 프로그램 실행 오류: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main() 