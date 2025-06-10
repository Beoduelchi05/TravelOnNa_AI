import asyncio
import schedule
import time
from typing import List, Dict, Any
from datetime import datetime, timedelta

from app.services.database_service import DatabaseService
from app.services.als_service import ALSRecommendationService
from app.utils.logger import get_logger
from app.models.schemas import RecommendationType

logger = get_logger(__name__)

class BatchService:
    """추천 시스템 배치 처리 서비스"""
    
    def __init__(self):
        self.db_service = DatabaseService()
        self.rec_service = ALSRecommendationService()
        self.is_running = False
    
    async def run_full_batch(self) -> bool:
        """전체 사용자 추천 배치 처리"""
        logger.info("🚀 전체 추천 배치 처리 시작")
        
        # 대상 사용자 조회
        user_ids = self.db_service.get_users_for_batch_processing("full")
        if not user_ids:
            logger.warning("⚠️ 배치 처리 대상 사용자가 없습니다")
            return False
        
        # 배치 로그 생성 (실패해도 계속 진행)
        batch_id = self.db_service.create_batch_log("full", len(user_ids))
        if not batch_id:
            logger.info("ℹ️ DB 배치 로그 미사용 - 파일 로그만 사용하여 계속 진행")
            batch_id = -1  # 임시 ID
        
        try:
            all_recommendations = []
            processed_users = 0
            
            # 사용자별 추천 생성 (배치 단위로)
            batch_size = 100
            for i in range(0, len(user_ids), batch_size):
                batch_users = user_ids[i:i + batch_size]
                
                for user_id in batch_users:
                    try:
                        # 사용자별 추천 생성
                        user_recs = await self._generate_user_recommendations(user_id)
                        all_recommendations.extend(user_recs)
                        processed_users += 1
                        
                        # 진행상황 로깅
                        if processed_users % 50 == 0:
                            logger.info(f"📊 진행상황: {processed_users}/{len(user_ids)} 사용자 처리 완료")
                            
                    except Exception as e:
                        logger.error(f"❌ 사용자 {user_id} 추천 생성 실패: {str(e)}")
                        continue
                
                # 배치 단위로 DB 저장
                if all_recommendations:
                    success = self.db_service.save_recommendations_batch(
                        all_recommendations[-len(batch_users)*10:], batch_id if batch_id > 0 else 0
                    )
                    if not success:
                        logger.error("❌ 배치 저장 실패")
                        break
            
            # 최종 배치 로그 업데이트 (batch_id가 유효한 경우만)
            if batch_id > 0:
                self.db_service.update_batch_log(
                    batch_id, processed_users, len(all_recommendations), "completed"
                )
            
            logger.info(f"✅ 전체 배치 처리 완료: {processed_users}명, {len(all_recommendations)}건 추천")
            
            # 배치 로그를 파일에도 기록
            self._write_batch_log_to_file("full", processed_users, len(all_recommendations), "completed")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 전체 배치 처리 실패: {str(e)}")
            if batch_id > 0:
                self.db_service.update_batch_log(
                    batch_id, processed_users, 0, "failed", str(e)
                )
            self._write_batch_log_to_file("full", processed_users, 0, "failed", str(e))
            return False
    
    async def run_incremental_batch(self) -> bool:
        """증분 추천 배치 처리 (최근 활동 사용자만)"""
        logger.info("🔄 증분 추천 배치 처리 시작")
        
        # 최근 활동 사용자 조회
        user_ids = self.db_service.get_users_for_batch_processing("incremental")
        if not user_ids:
            logger.info("ℹ️ 증분 처리 대상 사용자가 없습니다")
            return True
        
        # 배치 로그 생성 (실패해도 계속 진행)
        batch_id = self.db_service.create_batch_log("incremental", len(user_ids))
        if not batch_id:
            logger.info("ℹ️ DB 배치 로그 미사용 - 파일 로그만 사용하여 계속 진행")
            batch_id = -1  # 임시 ID
        
        try:
            all_recommendations = []
            processed_users = 0
            
            for user_id in user_ids:
                try:
                    user_recs = await self._generate_user_recommendations(user_id)
                    all_recommendations.extend(user_recs)
                    processed_users += 1
                    
                except Exception as e:
                    logger.error(f"❌ 사용자 {user_id} 증분 추천 실패: {str(e)}")
                    continue
            
            # DB 저장
            if all_recommendations:
                success = self.db_service.save_recommendations_batch(
                    all_recommendations, batch_id if batch_id > 0 else 0
                )
                
                if success:
                    if batch_id > 0:
                        self.db_service.update_batch_log(
                            batch_id, processed_users, len(all_recommendations), "completed"
                        )
                    logger.info(f"✅ 증분 배치 처리 완료: {processed_users}명, {len(all_recommendations)}건 추천")
                    
                    # 배치 로그를 파일에도 기록
                    self._write_batch_log_to_file("incremental", processed_users, len(all_recommendations), "completed")
                    
                    return True
                else:
                    logger.error("❌ 증분 배치 저장 실패")
                    if batch_id > 0:
                        self.db_service.update_batch_log(
                            batch_id, processed_users, 0, "failed", "저장 실패"
                        )
                    self._write_batch_log_to_file("incremental", processed_users, 0, "failed", "저장 실패")
                    return False
            else:
                logger.info("ℹ️ 생성된 추천이 없습니다")
                if batch_id > 0:
                    self.db_service.update_batch_log(
                        batch_id, processed_users, 0, "completed"
                    )
                self._write_batch_log_to_file("incremental", processed_users, 0, "completed", "추천 없음")
                return True
                
        except Exception as e:
            logger.error(f"❌ 증분 배치 처리 실패: {str(e)}")
            if batch_id > 0:
                self.db_service.update_batch_log(
                    batch_id, processed_users, 0, "failed", str(e)
                )
            self._write_batch_log_to_file("incremental", processed_users, 0, "failed", str(e))
            return False
    
    async def run_mini_batch(self, user_limit: int = 50) -> bool:
        """Mini 배치 처리 (사용자 수 제한)"""
        logger.info(f"🔄 Mini 배치 처리 시작 (최대 {user_limit}명)")
        
        # 제한된 수의 사용자 조회
        all_user_ids = self.db_service.get_users_for_batch_processing("full")
        if not all_user_ids:
            logger.info("ℹ️ 배치 처리 대상 사용자가 없습니다")
            return True
        
        # 사용자 수 제한
        user_ids = all_user_ids[:user_limit]
        logger.info(f"📊 전체 사용자: {len(all_user_ids)}명, Mini 배치 대상: {len(user_ids)}명")
        
        # 배치 로그 생성
        batch_id = self.db_service.create_batch_log("mini", len(user_ids))
        if not batch_id:
            logger.info("ℹ️ DB 배치 로그 미사용 - 파일 로그만 사용하여 계속 진행")
            batch_id = -1
        
        try:
            all_recommendations = []
            processed_users = 0
            
            # 사용자별 추천 생성 (소규모 배치)
            batch_size = 20  # mini batch는 더 작은 단위로
            for i in range(0, len(user_ids), batch_size):
                batch_users = user_ids[i:i + batch_size]
                
                for user_id in batch_users:
                    try:
                        user_recs = await self._generate_user_recommendations(user_id)
                        all_recommendations.extend(user_recs)
                        processed_users += 1
                        
                        # 진행상황 로깅 (mini batch는 더 자주)
                        if processed_users % 10 == 0:
                            logger.info(f"📊 Mini 배치 진행: {processed_users}/{len(user_ids)} 사용자 처리 완료")
                            
                    except Exception as e:
                        logger.error(f"❌ 사용자 {user_id} 추천 생성 실패: {str(e)}")
                        continue
                
                # 배치 단위로 DB 저장
                if all_recommendations:
                    batch_recs = all_recommendations[-len(batch_users)*10:]
                    success = self.db_service.save_recommendations_batch(
                        batch_recs, batch_id if batch_id > 0 else 0
                    )
                    if not success:
                        logger.error("❌ Mini 배치 저장 실패")
                        break
            
            # 최종 배치 로그 업데이트
            if batch_id > 0:
                self.db_service.update_batch_log(
                    batch_id, processed_users, len(all_recommendations), "completed"
                )
            
            logger.info(f"✅ Mini 배치 처리 완료: {processed_users}명, {len(all_recommendations)}건 추천")
            
            # 파일 로그 기록
            self._write_batch_log_to_file("mini", processed_users, len(all_recommendations), "completed")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Mini 배치 처리 실패: {str(e)}")
            if batch_id > 0:
                self.db_service.update_batch_log(
                    batch_id, processed_users, 0, "failed", str(e)
                )
            self._write_batch_log_to_file("mini", processed_users, 0, "failed", str(e))
            return False
    
    async def _generate_user_recommendations(self, user_id: int) -> List[Dict[str, Any]]:
        """개별 사용자 추천 생성"""
        recommendations = []
        
        try:
            # 여행 기록 추천 (enum 사용)
            log_recs, algorithm = self.rec_service.get_recommendations(
                user_id=user_id, 
                rec_type=RecommendationType.RECORD, 
                limit=10
            )
            
            for rec_item in log_recs:
                recommendations.append({
                    "user_id": user_id,
                    "item_id": rec_item.item_id, 
                    "item_type": "log",
                    "score": rec_item.score
                })
                
        except Exception as e:
            logger.error(f"❌ 사용자 {user_id} 추천 생성 실패: {str(e)}")
            # 빈 추천 반환
            
        return recommendations
    
    def start_scheduler(self):
        """스케줄러 시작"""
        if self.is_running:
            logger.warning("⚠️ 스케줄러가 이미 실행 중입니다")
            return
        
        logger.info("🕐 추천 배치 스케줄러 시작")
        
        # 스케줄 등록
        schedule.every().day.at("02:00").do(self._run_full_batch_sync)      # 매일 새벽 2시
        schedule.every(6).hours.do(self._run_incremental_batch_sync)        # 6시간마다
        
        self.is_running = True
        
        # 스케줄러 실행 루프
        while self.is_running:
            try:
                schedule.run_pending()
                time.sleep(60)  # 1분마다 체크
            except KeyboardInterrupt:
                logger.info("🛑 스케줄러 중단 요청")
                break
            except Exception as e:
                logger.error(f"❌ 스케줄러 오류: {str(e)}")
                time.sleep(60)
        
        logger.info("⏹️ 추천 배치 스케줄러 종료")
    
    def stop_scheduler(self):
        """스케줄러 중지"""
        self.is_running = False
        schedule.clear()
        logger.info("🛑 스케줄러 중지됨")
    
    def _write_batch_log_to_file(self, batch_type: str, processed_users: int, 
                                total_recommendations: int, status: str, 
                                error_message: str = None):
        """배치 로그를 파일에 기록 (DB 실패 시 백업용)"""
        try:
            import os
            from datetime import datetime
            
            log_file = "/app/logs/batch.log"
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            log_entry = f"[{timestamp}] {batch_type.upper()} BATCH - "
            log_entry += f"Status: {status}, Users: {processed_users}, Recommendations: {total_recommendations}"
            
            if error_message:
                log_entry += f", Error: {error_message}"
            
            log_entry += "\n"
            
            # 로그 파일에 추가
            os.makedirs(os.path.dirname(log_file), exist_ok=True)
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(log_entry)
                
        except Exception as e:
            logger.error(f"❌ 파일 로그 기록 실패: {str(e)}")
    
    def _run_full_batch_sync(self):
        """동기 방식으로 전체 배치 실행 (스케줄러용)"""
        asyncio.run(self.run_full_batch())
    
    def _run_incremental_batch_sync(self):
        """동기 방식으로 증분 배치 실행 (스케줄러용)"""
        asyncio.run(self.run_incremental_batch())
    
    async def manual_batch_trigger(self, batch_type: str = "incremental", user_limit: int = None) -> Dict[str, Any]:
        """수동 배치 트리거 (API용)"""
        logger.info(f"🔧 수동 배치 트리거: {batch_type}" + (f" (최대 {user_limit}명)" if user_limit else ""))
        
        start_time = datetime.now()
        
        if batch_type == "full":
            success = await self.run_full_batch()
        elif batch_type == "mini":
            if user_limit is None:
                user_limit = 50  # 기본값
            success = await self.run_mini_batch(user_limit)
        else:  # incremental
            success = await self.run_incremental_batch()
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        return {
            "success": success,
            "batch_type": batch_type,
            "user_limit": user_limit if batch_type == "mini" else None,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "duration_seconds": duration
        } 