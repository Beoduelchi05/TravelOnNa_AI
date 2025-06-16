import pandas as pd
import pymysql
from sqlalchemy import create_engine, text
from sqlalchemy.pool import QueuePool
from typing import List, Dict, Any, Optional
from app.utils.logger import get_logger
from app.utils.config import get_settings

logger = get_logger(__name__)

class DatabaseService:
    """MySQL 데이터베이스 연동 서비스"""
    
    def __init__(self):
        self.settings = get_settings()
        self.engine = None
        self._connect()
    
    def _connect(self):
        """데이터베이스 연결 설정"""
        try:
            # YAML 설정에서 DB URL 가져오기
            db_url = self.settings.db_url
            
            if not db_url:
                # URL이 없으면 개별 설정으로 구성
                db_url = (
                    f"mysql+pymysql://{self.settings.db_user}:{self.settings.db_password}"
                    f"@{self.settings.db_host}:{self.settings.db_port}/{self.settings.db_name}"
                    f"?charset=utf8mb4"
                )
            
            # SQLAlchemy 엔진 생성
            pool_config = self.settings.get('datasource.pool', {})
            self.engine = create_engine(
                db_url,
                poolclass=QueuePool,
                pool_size=pool_config.get('size', 5),
                max_overflow=pool_config.get('max_overflow', 10),
                pool_pre_ping=pool_config.get('pre_ping', True),
                pool_recycle=pool_config.get('recycle', 3600),
                echo=self.settings.debug
            )
            
            # 연결 테스트
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            
            logger.info("✅ MySQL 데이터베이스 연결 성공")
            logger.info(f"   - 호스트: {self.settings.db_host}")
            logger.info(f"   - 데이터베이스: {self.settings.db_name}")
            
        except Exception as e:
            logger.error(f"❌ 데이터베이스 연결 실패: {str(e)}")
            raise
    
    def get_user_item_interactions(self) -> pd.DataFrame:
        """사용자-아이템 상호작용 데이터 조회 (user_actions 테이블 기반)"""
        query = """
        SELECT 
            ua.user_id,
            ua.target_id as item_id,
            CASE ua.action_type 
                WHEN 'post' THEN 5.0    -- 작성자 자신의 포스트 (높은 가중치)
                WHEN 'like' THEN 4.0    -- 좋아요 
                WHEN 'comment' THEN 3.0 -- 댓글
                WHEN 'view' THEN 1.0    -- 조회
                ELSE 1.0 
            END as rating,
            ua.action_time as created_at,
            ua.action_type,
            ua.target_type
        FROM user_actions ua
        WHERE ua.target_type IN ('log', 'place', 'plan')
          AND ua.action_time >= DATE_SUB(NOW(), INTERVAL 6 MONTH)  -- 최근 6개월
          AND (
              -- log 타입인 경우 공개 여부 확인
              (ua.target_type = 'log' AND EXISTS (
                  SELECT 1 FROM log l 
                  WHERE l.log_id = ua.target_id AND l.is_public = 1
              ))
              OR 
              -- place/plan 타입인 경우는 별도 체크 (현재는 모두 포함)
              ua.target_type IN ('place', 'plan')
          )
        ORDER BY ua.action_time DESC
        LIMIT 50000  -- 더 많은 데이터 로드
        """
        
        try:
            with self.engine.connect() as conn:
                df = pd.read_sql(query, conn)
            logger.info(f"✅ user_actions 기반 상호작용 데이터 조회 완료: {len(df)}건 (공개 로그만)")
            logger.info(f"   - 액션 타입별 분포:")
            if len(df) > 0:
                action_counts = df['action_type'].value_counts()
                for action, count in action_counts.items():
                    logger.info(f"     * {action}: {count}건")
                
                # 타겟 타입별 분포도 확인
                target_counts = df['target_type'].value_counts()
                logger.info(f"   - 타겟 타입별 분포:")
                for target, count in target_counts.items():
                    logger.info(f"     * {target}: {count}건")
            return df
        except Exception as e:
            logger.error(f"❌ user_actions 상호작용 데이터 조회 실패: {str(e)}")
            # 기존 방식으로 fallback
            return self._get_legacy_user_item_interactions()
    
    def _get_legacy_user_item_interactions(self) -> pd.DataFrame:
        """기존 방식의 상호작용 데이터 조회 (fallback용)"""
        query = """
        SELECT 
            ua.user_id,
            ua.log_id as item_id,
            ua.rating,
            ua.interaction_date as created_at
        FROM (
            -- 좋아요 데이터
            SELECT 
                lk.user_id,
                lk.log_id,
                5.0 as rating,
                'like' as action_type,
                NOW() as interaction_date
            FROM likes lk
            JOIN log l ON lk.log_id = l.log_id
            WHERE l.is_public = 1
            
            UNION ALL
            
            -- 댓글 데이터  
            SELECT 
                lc.user_id,
                lc.log_id,
                3.0 as rating,
                'comment' as action_type,
                lc.created_at as interaction_date
            FROM log_comment lc
            JOIN log l ON lc.log_id = l.log_id
            WHERE l.is_public = 1
              AND lc.created_at IS NOT NULL
            
            UNION ALL
            
            -- 작성자 자신의 기록 (높은 가중치)
            SELECT 
                l.user_id,
                l.log_id,
                4.0 as rating,
                'own' as action_type,
                l.created_at as interaction_date
            FROM log l
            WHERE l.is_public = 1
              AND l.created_at IS NOT NULL
        ) ua
        ORDER BY ua.interaction_date DESC
        LIMIT 10000
        """
        
        try:
            with self.engine.connect() as conn:
                df = pd.read_sql(query, conn)
            logger.info(f"✅ 기존 방식 상호작용 데이터 조회 완료: {len(df)}건")
            return df
        except Exception as e:
            logger.error(f"❌ 기존 방식 상호작용 데이터 조회 실패: {str(e)}")
            return pd.DataFrame()
    
    def get_item_metadata(self, item_ids: List[int]) -> Dict[str, Dict[str, Any]]:
        """아이템(여행 기록) 메타데이터 조회"""
        if not item_ids:
            return {}
            
        # 안전한 방식으로 수정: named parameter로 변경하기보다는 확실한 tuple 사용
        placeholders = ','.join(['%s'] * len(item_ids))
        query = f"""
        SELECT 
            l.log_id,
            l.comment as description,
            l.created_at,
            u.name as author_name,
            p.nickname as author_nickname,
            COUNT(DISTINCT lk.user_id) as like_count,
            COUNT(DISTINCT lc.loco_id) as comment_count
        FROM log l
        JOIN user u ON l.user_id = u.user_id
        LEFT JOIN profile p ON u.user_id = p.user_id
        LEFT JOIN likes lk ON l.log_id = lk.log_id  
        LEFT JOIN log_comment lc ON l.log_id = lc.log_id
        WHERE l.log_id IN ({placeholders})
          AND l.is_public = 1
        GROUP BY l.log_id, l.comment, l.created_at, u.name, p.nickname
        """
        
        try:
            with self.engine.connect() as conn:
                # pandas read_sql은 tuple을 안전하게 처리하지만, 명시적으로 변환
                df = pd.read_sql(query, conn, params=tuple(int(item_id) for item_id in item_ids))
            
            metadata = {}
            for _, row in df.iterrows():
                metadata[str(row['log_id'])] = {
                    "title": f"여행 기록 {row['log_id']}",  # 기본 제목
                    "description": row['description'][:200] if row['description'] else "",
                    "image_url": None,  # 실제 테이블에 없음
                    "category": "여행",  # 기본값
                    "location": "미지정",  # 기본값
                    "author_name": row['author_name'],
                    "author_nickname": row['author_nickname'],
                    "created_at": row['created_at'].isoformat() if row['created_at'] else None,
                    "popularity_rank": int(row['like_count']) + int(row['comment_count']),
                    "extra": {
                        "like_count": int(row['like_count']),
                        "comment_count": int(row['comment_count'])
                    }
                }
            
            logger.info(f"✅ 메타데이터 조회 완료: {len(metadata)}개")
            return metadata
            
        except Exception as e:
            logger.error(f"❌ 메타데이터 조회 실패: {str(e)}")
            return {}
    
    def get_popular_items(self, rec_type: str, limit: int) -> List[int]:
        """인기 아이템 조회 (user_actions 기반으로 수정)"""
        if rec_type == "record":
            # 먼저 user_actions 기반으로 인기도 계산 시도 (공개 로그만, 조건 완화)
            query = """
            SELECT 
                ua.target_id as log_id,
                COUNT(*) as popularity_score
            FROM user_actions ua
            JOIN log l ON ua.target_id = l.log_id
            WHERE ua.target_type = 'log'
              AND ua.action_type IN ('like', 'comment', 'view', 'post')
              AND ua.action_time >= DATE_SUB(NOW(), INTERVAL 12 MONTH)  -- 12개월로 확장
              AND l.is_public = 1  -- 공개 로그만
            GROUP BY ua.target_id
            ORDER BY popularity_score DESC, ua.action_time DESC
            LIMIT %s
            """
        elif rec_type == "place":
            query = """
            SELECT 
                p.place_id as log_id,
                COUNT(*) as popularity_score
            FROM place p
            JOIN plan pl ON p.plan_id = pl.plan_id
            WHERE pl.is_public = 1
              AND p.created_at >= DATE_SUB(NOW(), INTERVAL 6 MONTH)  -- 6개월로 확장
            GROUP BY p.place_id
            ORDER BY popularity_score DESC
            LIMIT %s
            """
        else:
            # 기본값: 최신 공개 기록
            query = """
            SELECT log_id
            FROM log
            WHERE is_public = 1
            ORDER BY created_at DESC
            LIMIT %s
            """
        
        try:
            with self.engine.connect() as conn:
                df = pd.read_sql(query, conn, params=(limit,))
            
            item_ids = df['log_id'].tolist()
            
            # user_actions 기반 결과가 부족하면 최신 공개 로그로 fallback
            if len(item_ids) < limit and rec_type == "record":
                logger.warning(f"⚠️ user_actions 기반 인기 아이템 부족 ({len(item_ids)}/{limit}), 최신 공개 로그로 보완")
                fallback_query = """
                SELECT log_id
                FROM log
                WHERE is_public = 1
                  AND log_id NOT IN ({})
                ORDER BY created_at DESC
                LIMIT %s
                """.format(','.join(map(str, item_ids)) if item_ids else '0')
                
                remaining_limit = limit - len(item_ids)
                df_fallback = pd.read_sql(fallback_query, conn, params=(remaining_limit,))
                fallback_ids = df_fallback['log_id'].tolist()
                item_ids.extend(fallback_ids)
            
            logger.info(f"✅ 인기 아이템 조회 완료: {len(item_ids)}개 (요청: {limit}개)")
            return item_ids
            
        except Exception as e:
            logger.error(f"❌ 인기 아이템 조회 실패: {str(e)}")
            # 최종 폴백: 최신 공개 로그 반환
            try:
                with self.engine.connect() as conn:
                    fallback_query = """
                    SELECT log_id
                    FROM log
                    WHERE is_public = 1
                    ORDER BY created_at DESC
                    LIMIT %s
                    """
                    df = pd.read_sql(fallback_query, conn, params=(limit,))
                    return df['log_id'].tolist()
            except:
                logger.error("❌ 최종 폴백도 실패, 순차적 ID 반환")
                return list(range(1, limit + 1))
    
    def get_user_preferences(self, user_id: int) -> Dict[str, Any]:
        """사용자 선호도 정보 조회"""
        query = """
        SELECT 
            u.user_id,
            p.nickname,
            -- 선호 카테고리 (가장 많이 좋아요한 카테고리)
            (SELECT l.category 
             FROM like_log lk 
             JOIN log l ON lk.log_id = l.log_id 
             WHERE lk.user_id = u.user_id 
             GROUP BY l.category 
             ORDER BY COUNT(*) DESC 
             LIMIT 1) as preferred_category,
            -- 선호 지역
            (SELECT l.location 
             FROM like_log lk 
             JOIN log l ON lk.log_id = l.log_id 
             WHERE lk.user_id = u.user_id 
             GROUP BY l.location 
             ORDER BY COUNT(*) DESC 
             LIMIT 1) as preferred_location
        FROM user u
        LEFT JOIN profile p ON u.user_id = p.user_id
        WHERE u.user_id = %(user_id)s
        """
        
        try:
            with self.engine.connect() as conn:
                df = pd.read_sql(query, conn, params={'user_id': int(user_id)})
            
            if len(df) > 0:
                row = df.iloc[0]
                return {
                    "user_id": int(row['user_id']),
                    "nickname": row['nickname'],
                    "preferred_category": row['preferred_category'],
                    "preferred_location": row['preferred_location']
                }
            else:
                return {"user_id": user_id}
                
        except Exception as e:
            logger.error(f"❌ 사용자 선호도 조회 실패: {str(e)}")
            return {"user_id": user_id}
    
    def close(self):
        """데이터베이스 연결 종료"""
        if self.engine:
            self.engine.dispose()
            logger.info("데이터베이스 연결 종료")
    
    def save_recommendations_batch(self, recommendations: List[Dict[str, Any]], batch_id: int) -> bool:
        """추천 결과를 recommendations 테이블에 배치 저장"""
        if not recommendations:
            return True
            
        try:
            # 기존 추천 결과 삭제 (사용자별)
            user_ids = list(set([rec['user_id'] for rec in recommendations]))
            
            with self.engine.begin() as conn:
                # 1. 기존 데이터 삭제 - named parameter 방식으로 수정
                if user_ids:
                    # 하나씩 삭제하는 방식으로 변경 (더 안전)
                    delete_query = text("DELETE FROM recommendations WHERE user_id = :user_id")
                    for user_id in user_ids:
                        conn.execute(delete_query, {'user_id': int(user_id)})
                    logger.info(f"🗑️ 기존 추천 데이터 삭제 완료: {len(user_ids)}명")
                
                # 2. 새 데이터 삽입 - 하나씩 삽입하는 안전한 방법
                insert_query = text("""
                    INSERT INTO recommendations 
                    (user_id, item_id, item_type, score, created_at)
                    VALUES (:user_id, :item_id, :item_type, :score, NOW())
                """)
                
                inserted_count = 0
                for rec in recommendations:
                    try:
                        conn.execute(insert_query, {
                            'user_id': int(rec['user_id']),
                            'item_id': int(rec['item_id']), 
                            'item_type': str(rec['item_type']),
                            'score': float(rec['score'])
                        })
                        inserted_count += 1
                    except Exception as insert_error:
                        logger.warning(f"⚠️ 개별 추천 삽입 실패: user_id={rec.get('user_id')}, item_id={rec.get('item_id')}, error={str(insert_error)}")
                        continue
            
            logger.info(f"✅ 추천 결과 배치 저장 완료: {inserted_count}/{len(recommendations)}건")
            return True
            
        except Exception as e:
            logger.error(f"❌ 추천 결과 배치 저장 실패: {str(e)}")
            import traceback
            logger.error(f"상세 오류: {traceback.format_exc()}")
            return False
    
    def create_batch_log(self, batch_type: str, total_users: int) -> Optional[int]:
        """배치 처리 로그 생성 (파일 로그만 사용)"""
        try:
            # DB 대신 파일 로그만 사용
            import os
            from datetime import datetime
            
            log_file = "/app/logs/batch.log"
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            log_entry = f"[{timestamp}] {batch_type.upper()} BATCH STARTED - "
            log_entry += f"Total Users: {total_users}, Status: started\n"
            
            # 로그 파일에 기록
            os.makedirs(os.path.dirname(log_file), exist_ok=True)
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(log_entry)
            
            logger.info(f"✅ 배치 로그 생성 (파일): type={batch_type}, users={total_users}")
            
            # 가짜 batch_id 반환 (타임스탬프 기반)
            batch_id = int(datetime.now().timestamp())
            return batch_id
            
        except Exception as e:
            logger.error(f"❌ 배치 로그 생성 실패: {str(e)}")
            return None
    
    def update_batch_log(self, batch_id: int, processed_users: int, 
                        total_recommendations: int, status: str, 
                        error_message: Optional[str] = None) -> bool:
        """배치 처리 로그 업데이트 (파일 로그만 사용)"""
        try:
            # DB 대신 파일 로그만 사용
            import os
            from datetime import datetime
            
            log_file = "/app/logs/batch.log"
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # 배치 타입 추정 (batch_id로는 알 수 없으므로 간단히 BATCH로 표시)
            log_entry = f"[{timestamp}] BATCH UPDATE - "
            log_entry += f"Status: {status}, Users: {processed_users}, Recommendations: {total_recommendations}"
            
            if error_message:
                log_entry += f", Error: {error_message}"
            
            log_entry += "\n"
            
            # 로그 파일에 기록
            os.makedirs(os.path.dirname(log_file), exist_ok=True)
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(log_entry)
            
            logger.info(f"✅ 배치 로그 업데이트 (파일): status={status}, users={processed_users}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 배치 로그 업데이트 실패: {str(e)}")
            return False
    
    def get_users_for_batch_processing(self, batch_type: str = "full") -> List[int]:
        """배치 처리 대상 사용자 조회"""
        if batch_type == "incremental":
            # 최근 활동한 사용자만 (24시간으로 확장)
            query = """
            SELECT DISTINCT user_id 
            FROM user_actions 
            WHERE action_time >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
            ORDER BY user_id
            LIMIT 1000
            """
        else:
            # 전체 사용자 (모든 user_actions 데이터, 날짜 제한 없음)
            query = """
            SELECT DISTINCT user_id 
            FROM user_actions 
            ORDER BY user_id
            """
        
        try:
            # 메인 쿼리 실행
            with self.engine.connect() as conn:
                df = pd.read_sql(query, conn)
            
            user_ids = df['user_id'].tolist()
            logger.info(f"✅ 배치 처리 대상 사용자 조회: {len(user_ids)}명 ({batch_type})")
            
            # 디버깅: 실제 user_actions 데이터 확인 (새로운 커넥션 사용)
            try:
                with self.engine.connect() as conn:
                    total_query = "SELECT COUNT(*) as total, COUNT(DISTINCT user_id) as unique_users FROM user_actions"
                    total_df = pd.read_sql(total_query, conn)
                    logger.info(f"📊 전체 user_actions: {total_df.iloc[0]['total']}건, 고유 사용자: {total_df.iloc[0]['unique_users']}명")
            except Exception as e:
                logger.warning(f"⚠️ 전체 통계 조회 실패 (무시함): {str(e)}")
            
            # 날짜별 분포도 확인 (새로운 커넥션 사용)
            if batch_type == "full":
                try:
                    with self.engine.connect() as conn:
                        date_query = """
                        SELECT 
                            DATE(action_time) as action_date,
                            COUNT(*) as daily_actions,
                            COUNT(DISTINCT user_id) as daily_users
                        FROM user_actions 
                        GROUP BY DATE(action_time)
                        ORDER BY action_date DESC
                        LIMIT 7
                        """
                        date_df = pd.read_sql(date_query, conn)
                        logger.info("📅 최근 7일간 user_actions 분포:")
                        for _, row in date_df.iterrows():
                            logger.info(f"   - {row['action_date']}: {row['daily_actions']}건, {row['daily_users']}명")
                except Exception as e:
                    logger.warning(f"⚠️ 날짜별 분포 조회 실패 (무시함): {str(e)}")
            
            return user_ids
            
        except Exception as e:
            logger.error(f"❌ 배치 처리 대상 사용자 조회 실패: {str(e)}")
            return []