import pickle
import pandas as pd
import numpy as np
from datetime import datetime
from typing import List, Dict, Optional, Tuple
import logging
from scipy.sparse import csr_matrix
from app.models.schemas import RecommendationItem, RecommendationType
from app.utils.logger import get_logger
from app.services.database_service import DatabaseService

logger = get_logger(__name__)

class ALSRecommendationService:
    def __init__(self, model_path: str = "/app/models"):
        self.model_path = model_path
        self.model = None
        self.user_item_matrix = None
        self.user_id_map = {}  # user_id -> matrix_index
        self.item_id_map = {}  # item_id -> matrix_index  
        self.reverse_user_map = {}  # matrix_index -> user_id
        self.reverse_item_map = {}  # matrix_index -> item_id
        self.item_metadata = {}
        self.is_loaded = False
        self.db_service = DatabaseService()
        self.load_models()
    
    def load_models(self) -> bool:
        """저장된 ALS 모델 로드 및 데이터 준비"""
        try:
            logger.info("ALS 모델 로딩 시작...")
            
            # ALS 모델 로드
            with open(f"{self.model_path}/als_model.pkl", "rb") as f:
                model_data = pickle.load(f)
            
            # 모델 데이터 구조 확인 및 분리
            if isinstance(model_data, dict):
                # 모델과 메타데이터가 함께 저장된 경우
                self.model = model_data.get('model')
                self.user_id_map = model_data.get('user_id_map', {})
                self.item_id_map = model_data.get('item_id_map', {})
                self.user_item_matrix = model_data.get('user_item_matrix')
            else:
                # 모델만 저장된 경우
                self.model = model_data
                # 데이터베이스에서 매핑 정보 재구성
                self._rebuild_mappings()
            
            # 역방향 매핑 생성
            self.reverse_user_map = {v: k for k, v in self.user_id_map.items()}
            self.reverse_item_map = {v: k for k, v in self.item_id_map.items()}
            
            logger.info(f"✅ ALS 모델 로딩 완료")
            logger.info(f"   - 사용자 수: {len(self.user_id_map)}")
            logger.info(f"   - 아이템 수: {len(self.item_id_map)}")
            logger.info(f"   - 모델 팩터 수: {getattr(self.model, 'n_components', 'N/A')}")
            
            # 아이템 메타데이터 로드 (DB에서)
            self._load_item_metadata()
            
            self.is_loaded = True
            logger.info("🎉 모든 데이터 로딩 완료!")
            return True
            
        except Exception as e:
            logger.error(f"❌ 모델 로딩 실패: {str(e)}")
            self.is_loaded = False
            return False
    
    def _rebuild_mappings(self):
        """데이터베이스에서 user-item 매핑 재구성"""
        logger.info("사용자-아이템 매핑 재구성 중...")
        
        # 실제 데이터베이스에서 상호작용 데이터 조회
        interactions = self.db_service.get_user_item_interactions()
        
        if interactions.empty:
            logger.warning("⚠️ 상호작용 데이터가 없습니다.")
            return
        
        users = sorted(interactions['user_id'].unique())
        items = sorted(interactions['item_id'].unique())
        
        self.user_id_map = {user_id: idx for idx, user_id in enumerate(users)}
        self.item_id_map = {item_id: idx for idx, item_id in enumerate(items)}
        
        # user-item matrix 재구성 (학습 시와 동일한 구조)
        rows = [self.user_id_map[user_id] for user_id in interactions['user_id']]
        cols = [self.item_id_map[item_id] for item_id in interactions['item_id']]
        data = interactions['rating'].values
        
        self.user_item_matrix = csr_matrix(
            (data, (rows, cols)), 
            shape=(len(users), len(items))
        )
        
        logger.info(f"✅ 매핑 재구성 완료: 사용자 {len(users)}명, 아이템 {len(items)}개")
    
    def _load_item_metadata(self):
        """데이터베이스에서 아이템 메타데이터 로드"""
        try:
            self.item_metadata = self.db_service.get_item_metadata(
                list(self.item_id_map.keys())
            )
            logger.info(f"✅ 아이템 메타데이터 로딩 완료: {len(self.item_metadata)}개")
        except Exception as e:
            logger.warning(f"⚠️ 메타데이터 로딩 실패: {str(e)}")
            self.item_metadata = {}
    
    def get_recommendations(
        self, 
        user_id: int, 
        rec_type: RecommendationType = RecommendationType.RECORD,
        limit: int = 10,
        filters: Optional[Dict] = None,
        exclude_items: Optional[List[int]] = None
    ) -> Tuple[List[RecommendationItem], str]:
        """사용자별 추천 생성"""
        
        if not self.is_loaded:
            raise RuntimeError("모델이 로드되지 않았습니다.")
        
        exclude_items = exclude_items or []
        
        try:
            if user_id in self.user_id_map:
                # 기존 사용자 - 협업 필터링
                recommendations, algorithm = self._get_collaborative_recommendations(
                    user_id, rec_type, limit, exclude_items
                )
            else:
                # 신규 사용자 - 인기도 기반
                recommendations, algorithm = self._get_user_based_recommendations(
                    user_id, rec_type, limit, exclude_items
                )
            
            # 필터 적용
            if filters:
                recommendations = self._apply_filters(recommendations, filters)
            
            return recommendations[:limit], algorithm
            
        except Exception as e:
            logger.error(f"추천 생성 실패 (user_id: {user_id}): {str(e)}")
            # fallback: 인기도 기반 추천
            return self._get_popularity_recommendations(rec_type, limit, exclude_items)
    
    def _get_collaborative_recommendations(
        self, 
        user_id: int, 
        rec_type: RecommendationType, 
        limit: int,
        exclude_items: List[int]
    ) -> Tuple[List[RecommendationItem], str]:
        """협업 필터링 기반 추천"""
        
        logger.info(f"협업 필터링 추천 생성 (user_id: {user_id})")
        
        # 사용자 인덱스 가져오기
        user_idx = self.user_id_map[user_id]
        
        # ALS 모델로 사용자의 아이템 점수 예측
        # model.predict(user_idx, item_indices)를 사용하거나
        # user/item factor를 직접 내적 계산
        user_factors = self.model.user_factors[user_idx]
        item_factors = self.model.item_factors
        
        # 모든 아이템에 대한 점수 계산
        scores = np.dot(item_factors, user_factors)
        
        # 이미 상호작용한 아이템 제외
        user_items = self.user_item_matrix[user_idx].indices
        scores[user_items] = -np.inf
        
        # 제외할 아이템들도 점수를 낮춤
        for item_id in exclude_items:
            if item_id in self.item_id_map:
                item_idx = self.item_id_map[item_id]
                scores[item_idx] = -np.inf
        
        # 상위 아이템 선택
        top_items = np.argsort(scores)[-limit * 2:][::-1]  # 여유분 확보
        
        recommendations = []
        for item_idx in top_items:
            if len(recommendations) >= limit:
                break
                
            item_id = self.reverse_item_map[item_idx]
            score = scores[item_idx]
            
            # 점수가 유효한 경우만 추가
            if score > -np.inf:
                metadata = self.item_metadata.get(str(item_id), {})
                
                recommendation = RecommendationItem(
                    item_id=item_id,
                    score=float(min(max(score, 0.0), 1.0)),  # 0-1 범위로 정규화
                    item_type=rec_type,
                    title=metadata.get("title"),
                    description=metadata.get("description"),
                    image_url=metadata.get("image_url"),
                    metadata={
                        "method": "collaborative_filtering",
                        "als_score": float(score),
                        "popularity_rank": metadata.get("popularity_rank"),
                        **metadata.get("extra", {})
                    }
                )
                recommendations.append(recommendation)
        
        return recommendations, "collaborative_filtering"
    
    def _get_popularity_recommendations(
        self, 
        rec_type: RecommendationType, 
        limit: int,
        exclude_items: List[int]
    ) -> Tuple[List[RecommendationItem], str]:
        """인기도 기반 추천 (콜드 스타트 대응)"""
        
        logger.info(f"인기도 기반 추천 생성 (타입: {rec_type})")
        
        # 먼저 DB에서 실제 인기 아이템 조회
        try:
            popular_items = self.db_service.get_popular_items(rec_type.value, limit * 3)
            logger.info(f"DB에서 조회한 인기 아이템: {popular_items}")
        except Exception as e:
            logger.error(f"DB 인기 아이템 조회 실패: {str(e)}")
            popular_items = []
        
        recommendations = []
        
        # DB 기반 인기 아이템이 있는 경우
        if popular_items:
            count = 0
            for item_id in popular_items:
                if count >= limit:
                    break
                    
                if item_id in exclude_items:
                    continue
                    
                metadata = self.item_metadata.get(str(item_id), {})
                
                # 순위 기반 점수 계산 (첫 번째가 가장 높음)
                normalized_score = max(0.1, 1.0 - (count * 0.1))
                
                recommendation = RecommendationItem(
                    item_id=int(item_id),
                    score=normalized_score,
                    item_type=rec_type,
                    title=metadata.get("title", f"여행 기록 {item_id}"),
                    description=metadata.get("description", ""),
                    image_url=metadata.get("image_url"),
                    metadata={
                        "method": "popularity_based_db",
                        "popularity_rank": count + 1,
                        "author_name": metadata.get("author_name"),
                        "author_nickname": metadata.get("author_nickname"),
                        **metadata.get("extra", {})
                    }
                )
                recommendations.append(recommendation)
                count += 1
                logger.info(f"인기 추천 추가: item_id={item_id}, score={normalized_score}")
        
        # Matrix 기반 백업 (DB 결과가 부족한 경우)
        elif self.user_item_matrix is not None and len(recommendations) < limit:
            logger.info("Matrix 기반 인기도 계산으로 백업")
            # 각 아이템별 상호작용 수 계산
            item_popularity = np.array(self.user_item_matrix.sum(axis=0)).flatten()
            popular_indices = np.argsort(item_popularity)[::-1]
            
            count = len(recommendations)
            for item_idx in popular_indices:
                if count >= limit:
                    break
                    
                item_id = self.reverse_item_map.get(item_idx)
                if not item_id or item_id in exclude_items:
                    continue
                    
                metadata = self.item_metadata.get(str(item_id), {})
                
                # 인기도 점수 계산
                popularity_score = item_popularity[item_idx]
                max_popularity = item_popularity.max()
                normalized_score = float(popularity_score / max_popularity) if max_popularity > 0 else 0.1
                
                recommendation = RecommendationItem(
                    item_id=int(item_id),
                    score=normalized_score,
                    item_type=rec_type,
                    title=metadata.get("title", f"여행 기록 {item_id}"),
                    description=metadata.get("description", ""),
                    image_url=metadata.get("image_url"),
                    metadata={
                        "method": "popularity_based_matrix",
                        "popularity_rank": count + 1,
                        "interaction_count": int(popularity_score),
                        **metadata.get("extra", {})
                    }
                )
                recommendations.append(recommendation)
                count += 1
        
        logger.info(f"인기도 기반 추천 완료: {len(recommendations)}개")
        return recommendations, "popularity_based"
    
    def _get_user_based_recommendations(
        self, 
        user_id: int,
        rec_type: RecommendationType, 
        limit: int,
        exclude_items: List[int]
    ) -> Tuple[List[RecommendationItem], str]:
        """실시간 사용자 기반 추천 (user_actions 테이블 직접 조회)"""
        
        logger.info(f"실시간 사용자 기반 추천 생성 (user_id: {user_id})")
        
        try:
            # 해당 사용자의 상호작용 데이터 조회
            user_interactions = self.db_service.get_user_item_interactions()
            user_data = user_interactions[user_interactions['user_id'] == user_id]
            
            if len(user_data) == 0:
                logger.info(f"사용자 {user_id}의 상호작용 데이터 없음 - 인기도 기반으로 전환")
                return self._get_popularity_recommendations(rec_type, limit, exclude_items)
            
            # 사용자가 상호작용한 아이템들
            user_items = set(user_data['item_id'].tolist())
            user_preferences = user_data.groupby('item_id')['rating'].mean().to_dict()
            
            logger.info(f"사용자 {user_id} 상호작용: {len(user_items)}개 아이템")
            
            # 전체 아이템에서 사용자가 아직 상호작용하지 않은 아이템 찾기
            all_interactions = self.db_service.get_user_item_interactions()
            all_items = set(all_interactions['item_id'].unique())
            candidate_items = all_items - user_items - set(exclude_items)
            
            logger.info(f"추천 후보 아이템: {len(candidate_items)}개")
            
            if not candidate_items:
                logger.info("추천 후보 아이템 없음 - 인기도 기반으로 전환")
                return self._get_popularity_recommendations(rec_type, limit, exclude_items)
            
            # 후보 아이템들의 인기도 계산
            item_popularity = all_interactions.groupby('item_id').agg({
                'rating': ['count', 'mean'],
                'user_id': 'nunique'
            }).reset_index()
            
            item_popularity.columns = ['item_id', 'interaction_count', 'avg_rating', 'unique_users']
            item_popularity = item_popularity[item_popularity['item_id'].isin(candidate_items)]
            
            # 사용자 선호도와 아이템 인기도를 결합한 점수 계산
            item_popularity['combined_score'] = (
                item_popularity['avg_rating'] * 0.4 +  # 평균 평점
                (item_popularity['interaction_count'] / item_popularity['interaction_count'].max()) * 0.6  # 정규화된 상호작용 수
            )
            
            # 상위 아이템 선택
            top_items = item_popularity.nlargest(limit, 'combined_score')
            
            recommendations = []
            for idx, row in top_items.iterrows():
                item_id = int(row['item_id'])
                score = float(row['combined_score'])
                
                metadata = self.item_metadata.get(str(item_id), {})
                
                recommendation = RecommendationItem(
                    item_id=item_id,
                    score=min(max(score, 0.1), 1.0),  # 0.1-1.0 범위로 정규화
                    item_type=rec_type,
                    title=metadata.get("title", f"여행 기록 {item_id}"),
                    description=metadata.get("description", ""),
                    image_url=metadata.get("image_url"),
                    metadata={
                        "method": "user_based_realtime",
                        "user_interactions": len(user_items),
                        "item_popularity": int(row['interaction_count']),
                        "avg_rating": float(row['avg_rating']),
                        "author_name": metadata.get("author_name"),
                        "author_nickname": metadata.get("author_nickname"),
                        **metadata.get("extra", {})
                    }
                )
                recommendations.append(recommendation)
            
            logger.info(f"실시간 사용자 기반 추천 완료: {len(recommendations)}개")
            return recommendations, "user_based_realtime"
            
        except Exception as e:
            logger.error(f"실시간 사용자 기반 추천 실패: {str(e)}")
            return self._get_popularity_recommendations(rec_type, limit, exclude_items)
    
    def _apply_filters(
        self, 
        recommendations: List[RecommendationItem], 
        filters: Dict
    ) -> List[RecommendationItem]:
        """추천 결과에 필터 적용"""
        
        if not filters:
            return recommendations
        
        filtered = []
        for rec in recommendations:
            # 카테고리 필터
            if "category" in filters:
                item_category = rec.metadata.get("category") if rec.metadata else None
                if item_category not in filters["category"]:
                    continue
            
            # 지역 필터  
            if "region" in filters:
                item_region = rec.metadata.get("region") if rec.metadata else None
                if item_region not in filters["region"]:
                    continue
            
            # 최소 점수 필터
            if "min_score" in filters:
                if rec.score < filters["min_score"]:
                    continue
            
            filtered.append(rec)
        
        return filtered
    
    def get_model_info(self) -> Dict:
        """모델 정보 반환"""
        if not self.is_loaded:
            return {"loaded": False}
        
        return {
            "loaded": True,
            "user_count": len(self.user_id_map),
            "item_count": len(self.item_id_map),
            "model_type": "ALS (Alternating Least Squares)",
            "factors": getattr(self.model, 'factors', 'unknown'),
            "regularization": getattr(self.model, 'regularization', 'unknown'),
            "iterations": getattr(self.model, 'iterations', 'unknown'),
            "matrix_shape": self.user_item_matrix.shape if self.user_item_matrix is not None else None
        }